from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional, Literal

import re

import pandas as pd

try:
    import pdfplumber
    _PDFPLUMBER_AVAILABLE = True
except ImportError as e:
    _PDFPLUMBER_AVAILABLE = False
    _PDFPLUMBER_IMPORT_ERROR = str(e)
except Exception as e:
    # 捕获其他可能的导入错误
    _PDFPLUMBER_AVAILABLE = False
    _PDFPLUMBER_IMPORT_ERROR = str(e)
else:
    _PDFPLUMBER_IMPORT_ERROR = None


# 文档类型 -> 表头规则
TABLE_TYPE_RULES: Dict[str, List[dict]] = {
    # 结算报告类
    "settlementReport": [
        {
            "name": "审定结算汇总表",
            "keywords": ["序号", "审计内容", "送审金额（含税）", "审定金额（含税）", "审定金额（不含税）", "增减金额", "备注"],
            "match_mode": "all",
        },
        {
            "name": "合同执行情况",
            "keywords": ["施工单位", "中标通知书金额", "中标通知书编号", "合同金额", "结算送审金额", "差额"],
            "match_mode": "all",
        },
        {
            "name": "赔偿合同",
            "keywords": ["合同对方", "赔偿事项", "合同金额", "结算送审金额", "差额"],
            "match_mode": "all",
        },
        {
            "name": "物资采购合同1",
            "keywords": ["物料名称", "合同数量", "施工图数量", "单价（不含税）", "差额"],
            "match_mode": "all",
        },
        {
            "name": "物资采购合同2",
            "keywords": ["物料名称", "合同金额（不含税）", "入账金额", "差额", "备注"],
            "match_mode": "all",
        },
        {
            "name": "其他服务类合同",
            "keywords": ["服务商", "中标通知书", "合同金额", "送审金额", "结算金额"],
            "match_mode": "all",
        },
    ],
    # 初设评审类
    "designReview": [
        {
            "name": "初设评审的概算投资",
            "keywords": ["序号", "工程名称", "建设规模", "静态投资", "其中：建设场地征用及清理费", "动态投资"],
            "match_mode": "all",
        },
    ],
}


EXCLUDE_RULES: List[str] = []

# 是否启用跨页合并
ENABLE_MERGE_CROSS_PAGE_TABLES: bool = True


def extract_tables_with_pdfplumber(
    pdf_path: str,
    pages: str = "all",
) -> List[Tuple[int, pd.DataFrame, tuple]]:
    """
    使用 pdfplumber 提取 PDF 中的表格。

    Returns:
        List[Tuple[int, pd.DataFrame, tuple]]: [(页码, DataFrame, bbox), ...]
    """
    # 运行时再次尝试导入，因为模块加载时可能失败但运行时环境可能不同
    global _PDFPLUMBER_AVAILABLE, pdfplumber, _PDFPLUMBER_IMPORT_ERROR
    if not _PDFPLUMBER_AVAILABLE:
        try:
            import pdfplumber
            _PDFPLUMBER_AVAILABLE = True
            _PDFPLUMBER_IMPORT_ERROR = None
        except ImportError as e:
            error_msg = f"pdfplumber 库未安装，无法提取表格（请安装 pdfplumber）"
            if _PDFPLUMBER_IMPORT_ERROR:
                error_msg += f"\n模块加载时导入错误: {_PDFPLUMBER_IMPORT_ERROR}"
            error_msg += f"\n运行时导入错误: {e}"
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"pdfplumber 库导入失败: {e}"
            if _PDFPLUMBER_IMPORT_ERROR:
                error_msg += f"\n模块加载时导入错误: {_PDFPLUMBER_IMPORT_ERROR}"
            raise RuntimeError(error_msg)

    tables_data: List[Tuple[int, pd.DataFrame, tuple]] = []

    with pdfplumber.open(pdf_path) as pdf:
        # 确定要处理的页面
        if pages == "all":
            pages_to_process = pdf.pages
        else:
            # 解析页面范围（如 "1-5,7,9-10"）
            page_numbers: List[int] = []
            for part in pages.split(","):
                part = part.strip()
                if not part:
                    continue
                if "-" in part:
                    start, end = map(int, part.split("-"))
                    page_numbers.extend(range(start, end + 1))
                else:
                    page_numbers.append(int(part))
            pages_to_process = [
                pdf.pages[i - 1] for i in page_numbers if 0 < i <= len(pdf.pages)
            ]

        # 提取每一页的表格
        for page in pages_to_process:
            page_num = page.page_number

            table_settings = {
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "intersection_tolerance": 3,
                "min_words_vertical": 1,
                "min_words_horizontal": 1,
            }

            tables = page.find_tables(table_settings=table_settings)
            for table in tables:
                table_data = table.extract()
                if table_data and len(table_data) > 0:
                    df = pd.DataFrame(table_data)
                    bbox = table.bbox  # (x0, top, x1, bottom)
                    tables_data.append((page_num, df, bbox))

    return tables_data


def check_table_header(table_df: pd.DataFrame, rule: dict) -> Tuple[bool, str]:
    """
    检查表格是否匹配指定的表头规则（固定匹配：必须包含所有关键词）
    处理表头换行（多行表头）并对关键字做去空格匹配。
    """
    if table_df.empty:
        return False, ""

    rule_name = rule.get("name", "未知规则")

    if rule_name in EXCLUDE_RULES:
        return False, ""

    # 默认从第一行开始
    start_row = 0

    # 合并前几行作为完整表头（通常表头可能占 1-3 行）
    header_rows_to_check = min(3, len(table_df) - start_row)
    header_text_parts: List[str] = []

    for row_idx in range(start_row, start_row + header_rows_to_check):
        if row_idx >= len(table_df):
            break
        row = table_df.iloc[row_idx].astype(str).str.strip()
        for cell in row:
            cell_text = str(cell).strip()
            if cell_text and cell_text.lower() not in ["nan", "none", ""]:
                # 将单元格内的换行符替换为空格（处理 xlsx 中的换行）
                cell_text = cell_text.replace("\n", " ").replace("\r", " ")
                header_text_parts.append(cell_text)

    # 合并所有表头文本
    header_text = " ".join(header_text_parts)
    # 规范空白：多个空格合并
    header_text = re.sub(r"\s+", " ", header_text).strip()
    # 去掉所有空白，用于处理“中标通知\n书金额”这类情况
    header_text_no_space = re.sub(r"\s+", "", header_text)

    keywords = rule.get("keywords", [])
    match_mode = rule.get("match_mode", "all")

    if not keywords:
        return False, ""

    if match_mode == "all":
        all_match = True
        for keyword in keywords:
            keyword_no_space = re.sub(r"\s+", "", keyword)
            if keyword in header_text or keyword_no_space in header_text_no_space:
                continue
            all_match = False
            break
        if all_match:
            return True, rule_name
    elif match_mode == "any":
        for keyword in keywords:
            keyword_no_space = re.sub(r"\s+", "", keyword)
            if keyword in header_text or keyword_no_space in header_text_no_space:
                return True, rule_name

    return False, ""


def is_likely_header_only(table_df: pd.DataFrame, min_data_rows: int = 1) -> bool:
    """
    判断表格是否可能只包含表头（数据行很少）。
    """
    if table_df.empty:
        return True

    header_rows = min(3, len(table_df))
    return len(table_df) <= header_rows + min_data_rows


def has_similar_structure(table1_df: pd.DataFrame, table2_df: pd.DataFrame, tolerance: int = 1) -> bool:
    """
    判断两个表格是否有相似的结构（列数接近）。
    """
    if table1_df.empty or table2_df.empty:
        return False

    cols1 = len(table1_df.columns)
    cols2 = len(table2_df.columns)
    return abs(cols1 - cols2) <= tolerance


def _merge_all_tables(
    tables: List[Tuple[int, pd.DataFrame, int]],
) -> List[Tuple[int, pd.DataFrame, int]]:
    """
    合并所有跨页表格（不进行过滤）：
    - 只处理"表头在当前页，内容在下一页"的典型情况；
    - 严格限制只合并相邻页，且列结构相似。
    """
    if not ENABLE_MERGE_CROSS_PAGE_TABLES or not tables:
        return tables

    # page -> [(idx, df)]
    page_map: Dict[int, List[Tuple[int, pd.DataFrame]]] = {}
    for orig_idx, df, page in tables:
        page_map.setdefault(page, []).append((orig_idx, df))

    merged: List[Tuple[int, pd.DataFrame, int]] = []
    processed: set[int] = set()

    sorted_pages = sorted(page_map.keys())

    for page in sorted_pages:
        current_list = page_map[page]
        for orig_idx, df in current_list:
            if orig_idx in processed:
                continue

            current_df = df
            did_merge = False

            # 情况：当前表格只有表头，尝试合并下一页
            if is_likely_header_only(current_df):
                next_page = page + 1
                if next_page in page_map:
                    for next_orig_idx, next_df in page_map[next_page]:
                        if next_orig_idx in processed:
                            continue

                        if not has_similar_structure(current_df, next_df):
                            continue

                        # 合并：保留当前页表头，拼接下一页数据
                        header_rows = min(3, len(current_df))
                        header_df = current_df.iloc[:header_rows].copy()
                        next_data_df = next_df.copy()

                        # 对齐列数
                        if len(header_df.columns) != len(next_data_df.columns):
                            if len(next_data_df.columns) < len(header_df.columns):
                                for _ in range(len(next_data_df.columns), len(header_df.columns)):
                                    next_data_df[len(next_data_df.columns)] = ""

                        merged_df = pd.concat([header_df, next_data_df], ignore_index=True)
                        merged.append((orig_idx, merged_df, page))
                        processed.add(orig_idx)
                        processed.add(next_orig_idx)
                        did_merge = True
                        break

            if not did_merge and orig_idx not in processed:
                merged.append((orig_idx, current_df, page))
                processed.add(orig_idx)

    return merged


def _merge_cross_page_tables(
    tables: List[Tuple[int, pd.DataFrame, str, int]],
    header_rules: List[dict],
) -> List[Tuple[int, pd.DataFrame, str, int]]:
    """
    简化版跨页合并逻辑（用于已匹配规则的表格）：
    - 只处理"表头在当前页，内容在下一页"的典型情况；
    - 严格限制只合并相邻页，且列结构相似；
    - 如果下一页第一行看起来像新的表头，则不合并。
    """
    if not ENABLE_MERGE_CROSS_PAGE_TABLES or not tables:
        return tables

    # page -> [(idx, df, rule_name)]
    page_map: Dict[int, List[Tuple[int, pd.DataFrame, str]]] = {}
    for orig_idx, df, rule_name, page in tables:
        page_map.setdefault(page, []).append((orig_idx, df, rule_name))

    merged: List[Tuple[int, pd.DataFrame, str, int]] = []
    processed: set[int] = set()

    sorted_pages = sorted(page_map.keys())

    for page in sorted_pages:
        current_list = page_map[page]
        for orig_idx, df, rule_name in current_list:
            if orig_idx in processed:
                continue

            current_df = df
            did_merge = False

            # 情况：当前表格只有表头，尝试合并下一页
            if is_likely_header_only(current_df):
                next_page = page + 1
                if next_page in page_map:
                    for next_orig_idx, next_df, next_rule_name in page_map[next_page]:
                        if next_orig_idx in processed:
                            continue

                        if rule_name and next_rule_name and rule_name != next_rule_name:
                            continue

                        if not has_similar_structure(current_df, next_df):
                            continue

                        # 判断下一页第一行是否像表头
                        next_first_row_text = ""
                        if not next_df.empty:
                            next_first_row_text = " ".join(
                                next_df.iloc[0].astype(str).str.strip().tolist()
                            )

                        keyword_count = 0
                        if header_rules and rule_name:
                            for rule in header_rules:
                                if rule.get("name") == rule_name:
                                    kws = rule.get("keywords", [])
                                    keyword_count = sum(
                                        1 for kw in kws if kw in next_first_row_text
                                    )
                                    break

                        # 如果下一页第一行包含较多关键词，认为是新表头，不合并
                        if keyword_count >= 2:
                            continue

                        # 合并：保留当前页表头，拼接下一页数据
                        header_rows = min(3, len(current_df))
                        header_df = current_df.iloc[:header_rows].copy()
                        next_data_df = next_df.copy()

                        # 对齐列数
                        if len(header_df.columns) != len(next_data_df.columns):
                            if len(next_data_df.columns) < len(header_df.columns):
                                for _ in range(len(next_data_df.columns), len(header_df.columns)):
                                    next_data_df[len(next_data_df.columns)] = ""

                        merged_df = pd.concat([header_df, next_data_df], ignore_index=True)
                        merged.append((orig_idx, merged_df, rule_name, page))
                        processed.add(orig_idx)
                        processed.add(next_orig_idx)
                        did_merge = True
                        break

            if not did_merge and orig_idx not in processed:
                merged.append((orig_idx, current_df, rule_name, page))
                processed.add(orig_idx)

    return merged


def extract_and_filter_tables_for_pdf(
    pdf_path: str,
    base_output_dir: str,
    doc_type: Literal["settlementReport", "designReview"],
) -> Dict[str, Any]:
    """
    从指定 PDF 提取所有表格 + 合并后的表格 + 筛选后的表格，全部落盘。

    返回结构:
    {
      "tables_root": str,
      "extracted_dir": str,
      "merged_dir": str,
      "filtered_dir": str,
      "all_tables": [
        {"page": int, "index_on_page": int, "excel_path": str}
      ],
      "merged_tables": [
        {"page": int, "index_on_page": int, "excel_path": str}
      ],
      "filtered_tables": [
        {"page": int, "index_on_page": int, "rule_name": str, "excel_path": str}
      ],
    }
    """
    pdf_path_obj = Path(pdf_path)
    base_output = Path(base_output_dir)

    tables_root = base_output / "tables"
    extracted_dir = tables_root / "extracted_tables"
    merged_dir = tables_root / "merged_tables"
    filtered_dir = tables_root / "filtered_tables"

    extracted_dir.mkdir(parents=True, exist_ok=True)
    merged_dir.mkdir(parents=True, exist_ok=True)
    filtered_dir.mkdir(parents=True, exist_ok=True)

    # 1. 使用 pdfplumber 从 PDF 提取所有表格（不限制页数）
    tables_data = extract_tables_with_pdfplumber(str(pdf_path_obj), pages="all")

    # 2. 保存所有原始表格为 xlsx，命名: table_page{page}_{index}.xlsx
    page_table_count: Dict[int, int] = {}
    all_tables_meta: List[Dict[str, Any]] = []

    # 给每个表格一个全局索引，方便后续合并/去重
    all_tables: List[Tuple[int, pd.DataFrame, int]] = []  # (orig_idx, df, page)
    for orig_idx, (page, df, _bbox) in enumerate(tables_data):
        page_table_count[page] = page_table_count.get(page, 0) + 1
        idx_on_page = page_table_count[page]

        excel_path = extracted_dir / f"table_page{page}_{idx_on_page}.xlsx"
        df.to_excel(str(excel_path), index=False, header=False)

        all_tables_meta.append(
            {
                "page": page,
                "index_on_page": idx_on_page,
                "excel_path": str(excel_path),
            }
        )
        all_tables.append((orig_idx, df.copy(), page))

    # 3. 合并所有跨页表格（不进行过滤），保存到 merged_tables
    merged_all_tables = _merge_all_tables(all_tables)
    
    merged_page_table_count: Dict[int, int] = {}
    merged_meta: List[Dict[str, Any]] = []
    
    for merged_idx, (orig_idx, df, page) in enumerate(merged_all_tables):
        merged_page_table_count[page] = merged_page_table_count.get(page, 0) + 1
        idx_on_page = merged_page_table_count[page]
        
        excel_path = merged_dir / f"table_{merged_idx + 1}.xlsx"
        df.to_excel(str(excel_path), index=False, header=False)
        
        merged_meta.append(
            {
                "page": page,
                "index_on_page": idx_on_page,
                "excel_path": str(excel_path),
            }
        )

    # 4. 根据 doc_type 选择对应的表头规则
    header_rules = TABLE_TYPE_RULES.get(doc_type, [])

    # 如果没有规则，直接返回（保留 extracted_tables 和 merged_tables）
    if not header_rules:
        return {
            "tables_root": str(tables_root),
            "extracted_dir": str(extracted_dir),
            "merged_dir": str(merged_dir),
            "filtered_dir": str(filtered_dir),
            "all_tables": all_tables_meta,
            "merged_tables": merged_meta,
            "filtered_tables": [],
        }

    # 5. 从合并后的表格中过滤出匹配规则的表格
    matched_for_merge: List[Tuple[int, pd.DataFrame, str, int]] = []
    for merged_idx, (orig_idx, df, page) in enumerate(merged_all_tables):
        rule_name: Optional[str] = None
        for rule in header_rules:
            is_match, rn = check_table_header(df, rule)
            if is_match:
                rule_name = rn
                break
        if rule_name:
            matched_for_merge.append((orig_idx, df.copy(), rule_name, page))

    # 如果没有匹配到表格，直接返回（保留 extracted_tables 和 merged_tables）
    if not matched_for_merge:
        return {
            "tables_root": str(tables_root),
            "extracted_dir": str(extracted_dir),
            "merged_dir": str(merged_dir),
            "filtered_dir": str(filtered_dir),
            "all_tables": all_tables_meta,
            "merged_tables": merged_meta,
            "filtered_tables": [],
        }

    # 6. 对已匹配规则的表格再次进行跨页合并（处理规则匹配后的特殊情况）
    merged_tables = _merge_cross_page_tables(matched_for_merge, header_rules)

    # 7. 保存筛选+合并后的表格到 filtered_dir，命名仍然按 page + 序号
    filtered_page_table_count: Dict[int, int] = {}
    filtered_meta: List[Dict[str, Any]] = []

    for orig_idx, df, rule_name, page in merged_tables:
        filtered_page_table_count[page] = filtered_page_table_count.get(page, 0) + 1
        idx_on_page = filtered_page_table_count[page]

        excel_path = filtered_dir / f"table_page{page}_{idx_on_page}.xlsx"
        df.to_excel(str(excel_path), index=False, header=False)

        filtered_meta.append(
            {
                "page": page,
                "index_on_page": idx_on_page,
                "rule_name": rule_name,
                "excel_path": str(excel_path),
            }
        )

    return {
        "tables_root": str(tables_root),
        "extracted_dir": str(extracted_dir),
        "merged_dir": str(merged_dir),
        "filtered_dir": str(filtered_dir),
        "all_tables": all_tables_meta,
        "merged_tables": merged_meta,
        "filtered_tables": filtered_meta,
    }


