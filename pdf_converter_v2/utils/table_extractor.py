from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional, Literal

import re
import json
import logging

import pandas as pd

logger = logging.getLogger(__name__)

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
        total_pages = len(pdf.pages)
        logger.info(f"[pdfplumber] 打开 PDF，共 {total_pages} 页")
        
        # 确定要处理的页面
        if pages == "all":
            pages_to_process = pdf.pages
            logger.info(f"[pdfplumber] 处理所有页面: 1-{total_pages}")
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
            logger.info(f"[pdfplumber] 处理指定页面: {page_numbers}")

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
            page_table_count = 0
            for table in tables:
                table_data = table.extract()
                if table_data and len(table_data) > 0:
                    df = pd.DataFrame(table_data)
                    bbox = table.bbox  # (x0, top, x1, bottom)
                    tables_data.append((page_num, df, bbox))
                    page_table_count += 1
            
            if page_table_count > 0:
                logger.debug(f"[pdfplumber] 页面 {page_num}: 提取到 {page_table_count} 个表格")

    logger.info(f"[pdfplumber] 提取完成: 共提取到 {len(tables_data)} 个表格")
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


def parse_settlement_summary_table(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    解析"审定结算汇总表"，提取数据并生成 JSON 格式。
    
    返回格式:
    [{
        "No": int,  # 序号
        "name": str,  # 项目名称（审计内容）
        "settledVerifiedTaxExclusiveInvestment": float,  # 结算审定不含税投资（元，两位小数）
        "settledVerifiedTaxInclusiveInvestment": float,  # 结算审定含税投资（元，两位小数）
    }, ...]
    """
    if df.empty:
        return []
    
    # 尝试识别表头行（通常在前几行）
    header_row_idx = None
    for i in range(min(3, len(df))):
        row_text = " ".join(df.iloc[i].astype(str).str.strip().tolist())
        # 检查是否包含表头关键词
        if any(kw in row_text for kw in ["序号", "审计内容", "审定金额（含税）", "审定金额（不含税）"]):
            header_row_idx = i
            break
    
    if header_row_idx is None:
        # 如果没有找到明确的表头，假设第一行是表头
        header_row_idx = 0
    
    # 合并前几行作为表头（处理多行表头的情况）
    header_rows_to_check = min(3, len(df) - header_row_idx)
    header_texts = []  # 每列的合并文本
    num_cols = len(df.columns)
    
    for col_idx in range(num_cols):
        col_text_parts = []
        for row_idx in range(header_row_idx, header_row_idx + header_rows_to_check):
            if row_idx < len(df):
                cell_val = str(df.iloc[row_idx, col_idx]).strip()
                if cell_val and cell_val.lower() not in ['nan', 'none', '']:
                    # 清理换行符
                    cell_val = cell_val.replace('\n', ' ').replace('\r', ' ')
                    col_text_parts.append(cell_val)
        # 合并该列的所有表头文本
        header_texts.append(' '.join(col_text_parts).strip())
    
    col_no = None  # 序号列
    col_name = None  # 审计内容列（项目名称）
    col_tax_exclusive = None  # 审定金额（不含税）列
    col_tax_inclusive = None  # 审定金额（含税）列
    
    for idx, header_text in enumerate(header_texts):
        cell_lower = header_text.lower()
        if "序号" in header_text or "no" in cell_lower:
            col_no = idx
        elif "审计内容" in header_text or "项目名称" in header_text or "name" in cell_lower:
            col_name = idx
        elif "审定金额（不含税）" in header_text or ("不含税" in header_text and "审定" in header_text):
            col_tax_exclusive = idx
        elif "审定金额（含税）" in header_text or ("审定金额" in header_text and "含税" in header_text):
            col_tax_inclusive = idx
    
    # 如果关键列未找到，尝试通过位置推断
    if col_no is None:
        col_no = 0
    if col_name is None:
        col_name = 1
    
    # 如果金额列未找到，尝试从后往前找（通常金额列在表格右侧）
    if col_tax_exclusive is None or col_tax_inclusive is None:
        for idx in range(len(header_texts) - 1, -1, -1):
            header_text = header_texts[idx]
            if "不含税" in header_text and col_tax_exclusive is None:
                col_tax_exclusive = idx
            elif "含税" in header_text and "审定" in header_text and col_tax_inclusive is None:
                col_tax_inclusive = idx
            if col_tax_exclusive is not None and col_tax_inclusive is not None:
                break
    
    logger.debug(f"[审定结算汇总表] 列识别: 序号={col_no}, 项目名称={col_name}, 不含税={col_tax_exclusive}, 含税={col_tax_inclusive}")
    
    # 从数据行开始解析（跳过表头行）
    data_rows = df.iloc[header_row_idx + 1:].reset_index(drop=True)
    
    result = []
    
    def parse_number(value: Any) -> float:
        """解析数字，支持中文数字格式，保留两位小数"""
        if pd.isna(value):
            return 0.0
        value_str = str(value).strip()
        # 移除常见的非数字字符（保留小数点、负号）
        value_str = re.sub(r'[^\d.\-]', '', value_str)
        if not value_str or value_str == '-':
            return 0.0
        try:
            return round(float(value_str), 2)
        except ValueError:
            return 0.0
    
    for idx, row in data_rows.iterrows():
        # 跳过空行
        if row.isna().all():
            continue
        
        # 提取各列数据
        no_val = row.iloc[col_no] if col_no is not None and col_no < len(row) else None
        name_val = row.iloc[col_name] if col_name is not None and col_name < len(row) else None
        tax_exclusive_val = row.iloc[col_tax_exclusive] if col_tax_exclusive is not None and col_tax_exclusive < len(row) else None
        tax_inclusive_val = row.iloc[col_tax_inclusive] if col_tax_inclusive is not None and col_tax_inclusive < len(row) else None
        
        # 解析序号
        no = None
        no_str = ""
        if no_val is not None and not pd.isna(no_val):
            no_str = str(no_val).strip()
            if no_str:
                try:
                    no = int(float(no_str))
                except (ValueError, TypeError):
                    pass
        
        # 跳过序号为空的行（这些通常是合计、其中等说明行）
        if not no_str or pd.isna(no_val):
            continue
        
        # 解析项目名称（审计内容），清理换行符
        name = str(name_val).strip() if name_val is not None and not pd.isna(name_val) else ""
        # 清理换行符，替换为空格
        name = name.replace('\n', ' ').replace('\r', ' ')
        # 清理多余空格
        name = re.sub(r'\s+', ' ', name).strip()
        
        # 跳过空行
        if not name or name == "":
            continue
        
        # 判断是否为合计行（合计行需要跳过）
        is_total = any(kw in name for kw in ["合计", "总计", "总计", "合计金额"])
        if is_total:
            continue
        
        # 解析投资金额
        settled_verified_tax_exclusive = parse_number(tax_exclusive_val)
        settled_verified_tax_inclusive = parse_number(tax_inclusive_val)
        
        # 添加到结果
        result.append({
            "No": no if no is not None else idx + 1,
            "name": name,
            "settledVerifiedTaxExclusiveInvestment": settled_verified_tax_exclusive,
            "settledVerifiedTaxInclusiveInvestment": settled_verified_tax_inclusive,
        })
    
    return result


def parse_contract_execution_table(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    解析"合同执行情况"表，提取数据并生成 JSON 格式。
    
    返回格式:
    [{
        "No": int,  # 序号
        "constructionUnit": str,  # 施工单位
        "bidNoticeAmount": float,  # 中标通知书金额（元，两位小数）
        "bidNoticeNo": str,  # 中标通知书编号
        "contractAmount": float,  # 合同金额（元，两位小数）
        "settlementSubmittedAmount": float,  # 结算送审金额（元，两位小数）
        "differenceAmount": float,  # 差额（元，两位小数）
    }, ...]
    """
    if df.empty:
        return []
    
    # 尝试识别表头行（通常在前几行）
    header_row_idx = None
    for i in range(min(3, len(df))):
        row_text = " ".join(df.iloc[i].astype(str).str.strip().tolist())
        # 检查是否包含表头关键词
        if any(kw in row_text for kw in ["序号", "施工单位", "中标通知书金额", "中标通知书编号", "合同金额", "结算送审金额", "差额"]):
            header_row_idx = i
            break
    
    if header_row_idx is None:
        # 如果没有找到明确的表头，假设第一行是表头
        header_row_idx = 0
    
    # 合并前几行作为表头（处理多行表头的情况）
    header_rows_to_check = min(3, len(df) - header_row_idx)
    header_texts = []  # 每列的合并文本
    num_cols = len(df.columns)
    
    for col_idx in range(num_cols):
        col_text_parts = []
        for row_idx in range(header_row_idx, header_row_idx + header_rows_to_check):
            if row_idx < len(df):
                cell_val = str(df.iloc[row_idx, col_idx]).strip()
                if cell_val and cell_val.lower() not in ['nan', 'none', '']:
                    # 清理换行符
                    cell_val = cell_val.replace('\n', ' ').replace('\r', ' ')
                    col_text_parts.append(cell_val)
        # 合并该列的所有表头文本
        header_texts.append(' '.join(col_text_parts).strip())
    
    col_no = None  # 序号列
    col_construction_unit = None  # 施工单位列
    col_bid_notice_amount = None  # 中标通知书金额列
    col_bid_notice_no = None  # 中标通知书编号列
    col_contract_amount = None  # 合同金额列
    col_settlement_submitted = None  # 结算送审金额列
    col_difference = None  # 差额列
    
    for idx, header_text in enumerate(header_texts):
        cell_lower = header_text.lower()
        if "序号" in header_text or "no" in cell_lower:
            col_no = idx
        elif "施工单位" in header_text:
            col_construction_unit = idx
        elif "中标通知书金额" in header_text:
            col_bid_notice_amount = idx
        elif "中标通知书编号" in header_text:
            col_bid_notice_no = idx
        elif "合同金额" in header_text and "结算" not in header_text:
            col_contract_amount = idx
        elif "结算送审金额" in header_text or ("送审金额" in header_text and "结算" in header_text):
            col_settlement_submitted = idx
        elif "差额" in header_text:
            col_difference = idx
    
    # 如果关键列未找到，尝试通过位置推断
    if col_no is None:
        col_no = 0
    if col_construction_unit is None:
        col_construction_unit = 1
    
    # 如果金额列未找到，尝试从后往前找（通常金额列在表格右侧）
    # 同时检查列名中是否包含关键词的部分匹配
    if col_bid_notice_amount is None:
        for idx, header_text in enumerate(header_texts):
            if "中标" in header_text and "金额" in header_text:
                col_bid_notice_amount = idx
                break
    
    if col_bid_notice_no is None:
        for idx, header_text in enumerate(header_texts):
            if "中标" in header_text and "编号" in header_text:
                col_bid_notice_no = idx
                break
    
    if col_contract_amount is None:
        for idx, header_text in enumerate(header_texts):
            if "合同" in header_text and "金额" in header_text and "结算" not in header_text:
                col_contract_amount = idx
                break
    
    if col_settlement_submitted is None:
        for idx, header_text in enumerate(header_texts):
            if "送审" in header_text and "金额" in header_text:
                col_settlement_submitted = idx
                break
    
    if col_difference is None:
        for idx, header_text in enumerate(header_texts):
            if "差额" in header_text:
                col_difference = idx
                break
    
    logger.debug(f"[合同执行情况] 列识别: 序号={col_no}, 施工单位={col_construction_unit}, "
                f"中标金额={col_bid_notice_amount}, 中标编号={col_bid_notice_no}, "
                f"合同金额={col_contract_amount}, 送审金额={col_settlement_submitted}, 差额={col_difference}")
    
    # 从数据行开始解析（跳过表头行）
    data_rows = df.iloc[header_row_idx + 1:].reset_index(drop=True)
    
    result = []
    
    def parse_number(value: Any) -> float:
        """解析数字，支持中文数字格式，保留两位小数"""
        if pd.isna(value):
            return 0.0
        value_str = str(value).strip()
        # 移除常见的非数字字符（保留小数点、负号）
        value_str = re.sub(r'[^\d.\-]', '', value_str)
        if not value_str or value_str == '-':
            return 0.0
        try:
            return round(float(value_str), 2)
        except ValueError:
            return 0.0
    
    for idx, row in data_rows.iterrows():
        # 跳过空行
        if row.isna().all():
            continue
        
        # 提取各列数据
        no_val = row.iloc[col_no] if col_no is not None and col_no < len(row) else None
        construction_unit_val = row.iloc[col_construction_unit] if col_construction_unit is not None and col_construction_unit < len(row) else None
        bid_notice_amount_val = row.iloc[col_bid_notice_amount] if col_bid_notice_amount is not None and col_bid_notice_amount < len(row) else None
        bid_notice_no_val = row.iloc[col_bid_notice_no] if col_bid_notice_no is not None and col_bid_notice_no < len(row) else None
        contract_amount_val = row.iloc[col_contract_amount] if col_contract_amount is not None and col_contract_amount < len(row) else None
        settlement_submitted_val = row.iloc[col_settlement_submitted] if col_settlement_submitted is not None and col_settlement_submitted < len(row) else None
        difference_val = row.iloc[col_difference] if col_difference is not None and col_difference < len(row) else None
        
        # 解析序号
        no = None
        no_str = ""
        if no_val is not None and not pd.isna(no_val):
            no_str = str(no_val).strip()
            if no_str:
                try:
                    no = int(float(no_str))
                except (ValueError, TypeError):
                    pass
        
        # 跳过序号为空的行（这些通常是合计、其中等说明行）
        if not no_str or pd.isna(no_val):
            continue
        
        # 解析施工单位，清理换行符
        construction_unit = str(construction_unit_val).strip() if construction_unit_val is not None and not pd.isna(construction_unit_val) else ""
        # 清理换行符，替换为空格
        construction_unit = construction_unit.replace('\n', ' ').replace('\r', ' ')
        # 清理多余空格
        construction_unit = re.sub(r'\s+', ' ', construction_unit).strip()
        
        # 跳过空行
        if not construction_unit or construction_unit == "":
            continue
        
        # 判断是否为合计行（合计行需要跳过）
        is_total = any(kw in construction_unit for kw in ["合计", "总计", "总计", "合计金额"])
        if is_total:
            continue
        
        # 解析中标通知书编号，清理换行符
        bid_notice_no = str(bid_notice_no_val).strip() if bid_notice_no_val is not None and not pd.isna(bid_notice_no_val) else ""
        bid_notice_no = bid_notice_no.replace('\n', ' ').replace('\r', ' ')
        bid_notice_no = re.sub(r'\s+', ' ', bid_notice_no).strip()
        
        # 解析金额（保留两位小数）
        bid_notice_amount = parse_number(bid_notice_amount_val)
        contract_amount = parse_number(contract_amount_val)
        settlement_submitted_amount = parse_number(settlement_submitted_val)
        difference_amount = parse_number(difference_val)
        
        # 添加到结果
        result.append({
            "No": no if no is not None else idx + 1,
            "constructionUnit": construction_unit,
            "bidNoticeAmount": bid_notice_amount,
            "bidNoticeNo": bid_notice_no,
            "contractAmount": contract_amount,
            "settlementSubmittedAmount": settlement_submitted_amount,
            "differenceAmount": difference_amount,
        })
    
    return result


def parse_compensation_contract_table(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    解析"赔偿合同"表，提取数据并生成 JSON 格式。
    
    返回格式:
    [{
        "No": int,  # 序号
        "contractCounterpartyName": str,  # 合同对方名称
        "compensationItem": str,  # 赔偿事项
        "contractAmount": float,  # 合同金额（元，两位小数）
        "settlementSubmittedAmount": float,  # 结算送审金额（元，两位小数）
        "differenceAmount": float,  # 差额（元，两位小数）
    }, ...]
    """
    if df.empty:
        return []
    
    # 尝试识别表头行（通常在前几行）
    header_row_idx = None
    for i in range(min(3, len(df))):
        row_text = " ".join(df.iloc[i].astype(str).str.strip().tolist())
        # 检查是否包含表头关键词
        if any(kw in row_text for kw in ["序号", "合同对方", "赔偿事项", "合同金额", "结算送审金额", "差额"]):
            header_row_idx = i
            break
    
    if header_row_idx is None:
        # 如果没有找到明确的表头，假设第一行是表头
        header_row_idx = 0
    
    # 合并前几行作为表头（处理多行表头的情况）
    header_rows_to_check = min(3, len(df) - header_row_idx)
    header_texts = []  # 每列的合并文本
    num_cols = len(df.columns)
    
    for col_idx in range(num_cols):
        col_text_parts = []
        for row_idx in range(header_row_idx, header_row_idx + header_rows_to_check):
            if row_idx < len(df):
                cell_val = str(df.iloc[row_idx, col_idx]).strip()
                if cell_val and cell_val.lower() not in ['nan', 'none', '']:
                    # 清理换行符
                    cell_val = cell_val.replace('\n', ' ').replace('\r', ' ')
                    col_text_parts.append(cell_val)
        # 合并该列的所有表头文本
        header_texts.append(' '.join(col_text_parts).strip())
    
    col_no = None  # 序号列
    col_counterparty_name = None  # 合同对方名称列
    col_compensation_item = None  # 赔偿事项列
    col_contract_amount = None  # 合同金额列
    col_settlement_submitted = None  # 结算送审金额列
    col_difference = None  # 差额列
    
    for idx, header_text in enumerate(header_texts):
        cell_lower = header_text.lower()
        if "序号" in header_text or "no" in cell_lower:
            col_no = idx
        elif "合同对方" in header_text:
            col_counterparty_name = idx
        elif "赔偿事项" in header_text:
            col_compensation_item = idx
        elif "合同金额" in header_text and "结算" not in header_text:
            col_contract_amount = idx
        elif "结算送审金额" in header_text or ("送审金额" in header_text and "结算" in header_text):
            col_settlement_submitted = idx
        elif "差额" in header_text:
            col_difference = idx
    
    # 如果关键列未找到，尝试通过位置推断
    if col_no is None:
        col_no = 0
    if col_counterparty_name is None:
        col_counterparty_name = 1
    if col_compensation_item is None:
        col_compensation_item = 2
    
    # 如果金额列未找到，尝试从后往前找（通常金额列在表格右侧）
    if col_contract_amount is None or col_settlement_submitted is None or col_difference is None:
        for idx in range(len(header_texts) - 1, -1, -1):
            header_text = header_texts[idx]
            if "差额" in header_text and col_difference is None:
                col_difference = idx
            elif "送审" in header_text and "金额" in header_text and col_settlement_submitted is None:
                col_settlement_submitted = idx
            elif "合同金额" in header_text and col_contract_amount is None:
                col_contract_amount = idx
            if col_contract_amount is not None and col_settlement_submitted is not None and col_difference is not None:
                break
    
    logger.debug(f"[赔偿合同] 列识别: 序号={col_no}, 合同对方={col_counterparty_name}, "
                f"赔偿事项={col_compensation_item}, 合同金额={col_contract_amount}, "
                f"送审金额={col_settlement_submitted}, 差额={col_difference}")
    
    # 从数据行开始解析（跳过表头行）
    data_rows = df.iloc[header_row_idx + 1:].reset_index(drop=True)
    
    result = []
    
    def parse_number(value: Any) -> float:
        """解析数字，支持中文数字格式，保留两位小数"""
        if pd.isna(value):
            return 0.0
        value_str = str(value).strip()
        # 移除常见的非数字字符（保留小数点、负号）
        value_str = re.sub(r'[^\d.\-]', '', value_str)
        if not value_str or value_str == '-':
            return 0.0
        try:
            return round(float(value_str), 2)
        except ValueError:
            return 0.0
    
    for idx, row in data_rows.iterrows():
        # 跳过空行
        if row.isna().all():
            continue
        
        # 提取各列数据
        no_val = row.iloc[col_no] if col_no is not None and col_no < len(row) else None
        counterparty_name_val = row.iloc[col_counterparty_name] if col_counterparty_name is not None and col_counterparty_name < len(row) else None
        compensation_item_val = row.iloc[col_compensation_item] if col_compensation_item is not None and col_compensation_item < len(row) else None
        contract_amount_val = row.iloc[col_contract_amount] if col_contract_amount is not None and col_contract_amount < len(row) else None
        settlement_submitted_val = row.iloc[col_settlement_submitted] if col_settlement_submitted is not None and col_settlement_submitted < len(row) else None
        difference_val = row.iloc[col_difference] if col_difference is not None and col_difference < len(row) else None
        
        # 解析序号
        no = None
        no_str = ""
        if no_val is not None and not pd.isna(no_val):
            no_str = str(no_val).strip()
            if no_str:
                try:
                    no = int(float(no_str))
                except (ValueError, TypeError):
                    pass
        
        # 跳过序号为空的行（这些通常是合计、其中等说明行）
        if not no_str or pd.isna(no_val):
            continue
        
        # 解析合同对方名称，清理换行符
        counterparty_name = str(counterparty_name_val).strip() if counterparty_name_val is not None and not pd.isna(counterparty_name_val) else ""
        counterparty_name = counterparty_name.replace('\n', ' ').replace('\r', ' ')
        counterparty_name = re.sub(r'\s+', ' ', counterparty_name).strip()
        
        # 跳过空行
        if not counterparty_name or counterparty_name == "":
            continue
        
        # 判断是否为合计行（合计行需要跳过）
        is_total = any(kw in counterparty_name for kw in ["合计", "总计", "总计", "合计金额"])
        if is_total:
            continue
        
        # 解析赔偿事项，清理换行符
        compensation_item = str(compensation_item_val).strip() if compensation_item_val is not None and not pd.isna(compensation_item_val) else ""
        compensation_item = compensation_item.replace('\n', ' ').replace('\r', ' ')
        compensation_item = re.sub(r'\s+', ' ', compensation_item).strip()
        
        # 解析金额（保留两位小数）
        contract_amount = parse_number(contract_amount_val)
        settlement_submitted_amount = parse_number(settlement_submitted_val)
        difference_amount = parse_number(difference_val)
        
        # 添加到结果
        result.append({
            "No": no if no is not None else idx + 1,
            "contractCounterpartyName": counterparty_name,
            "compensationItem": compensation_item,
            "contractAmount": contract_amount,
            "settlementSubmittedAmount": settlement_submitted_amount,
            "differenceAmount": difference_amount,
        })
    
    return result


def parse_design_review_table(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    解析 designReview 类型的表格，提取数据并生成 JSON 格式。
    
    返回格式:
    [{
        "No": int,  # 序号
        "name": str,  # 工程名称
        "Level": int,  # 明细等级（根据缩进或层级判断，合计为0）
        "staticInvestment": float,  # 静态投资（单位：元）
        "dynamicInvestment": float,  # 动态投资（单位：元）
    }, ...]
    """
    if df.empty:
        return []
    
    # 尝试识别表头行（通常在前几行）
    header_row_idx = None
    for i in range(min(3, len(df))):
        row_text = " ".join(df.iloc[i].astype(str).str.strip().tolist())
        # 检查是否包含表头关键词
        if any(kw in row_text for kw in ["序号", "工程名称", "建设规模", "静态投资", "动态投资"]):
            header_row_idx = i
            break
    
    if header_row_idx is None:
        # 如果没有找到明确的表头，假设第一行是表头
        header_row_idx = 0
    
    # 从表头行识别列索引
    header_row = df.iloc[header_row_idx].astype(str).str.strip()
    
    col_no = None  # 序号列
    col_name = None  # 工程名称列
    col_scale = None  # 建设规模列（用于判断层级）
    col_static = None  # 静态投资列
    col_dynamic = None  # 动态投资列
    
    for idx, cell in enumerate(header_row):
        cell_lower = cell.lower()
        if "序号" in cell or "no" in cell_lower:
            col_no = idx
        elif "工程名称" in cell or "name" in cell_lower:
            col_name = idx
        elif "建设规模" in cell or "规模" in cell:
            col_scale = idx
        elif "静态投资" in cell or "static" in cell_lower:
            col_static = idx
        elif "动态投资" in cell or "dynamic" in cell_lower:
            col_dynamic = idx
    
    # 如果关键列未找到，尝试通过位置推断（通常顺序：序号、工程名称、建设规模、静态投资、动态投资）
    if col_no is None:
        col_no = 0
    if col_name is None:
        col_name = 1
    if col_static is None:
        # 从后往前找
        for idx in range(len(df.columns) - 1, -1, -1):
            if "投资" in str(df.iloc[header_row_idx, idx]) or "元" in str(df.iloc[header_row_idx, idx]):
                if col_dynamic is None:
                    col_dynamic = idx
                elif col_static is None:
                    col_static = idx
                    break
    
    # 从数据行开始解析（跳过表头行）
    data_rows = df.iloc[header_row_idx + 1:].reset_index(drop=True)
    
    result = []
    total_static = 0.0
    total_dynamic = 0.0
    
    def parse_number(value: Any) -> float:
        """解析数字，支持中文数字格式"""
        if pd.isna(value):
            return 0.0
        value_str = str(value).strip()
        # 移除常见的非数字字符（保留小数点、负号）
        value_str = re.sub(r'[^\d.\-]', '', value_str)
        if not value_str or value_str == '-':
            return 0.0
        try:
            return float(value_str)
        except ValueError:
            return 0.0
    
    def determine_level(name: str) -> int:
        """根据工程名称的缩进或前缀判断明细等级"""
        if not name or pd.isna(name):
            return 1
        name_str = str(name).strip()
        # 如果包含"合计"、"总计"等关键词，返回0
        if any(kw in name_str for kw in ["合计", "总计", "总计", "合计金额"]):
            return 0
        # 根据缩进判断（假设空格或特殊字符表示层级）
        # 这里可以根据实际表格格式调整
        if name_str.startswith("  ") or name_str.startswith("\t"):
            return 2
        return 1
    
    for idx, row in data_rows.iterrows():
        # 跳过空行
        if row.isna().all():
            continue
        
        # 提取各列数据
        no_val = row.iloc[col_no] if col_no is not None and col_no < len(row) else None
        name_val = row.iloc[col_name] if col_name is not None and col_name < len(row) else None
        static_val = row.iloc[col_static] if col_static is not None and col_static < len(row) else None
        dynamic_val = row.iloc[col_dynamic] if col_dynamic is not None and col_dynamic < len(row) else None
        
        # 解析序号
        no = None
        no_str = ""
        if no_val is not None and not pd.isna(no_val):
            no_str = str(no_val).strip()
            if no_str:
                try:
                    no = int(float(no_str))
                except (ValueError, TypeError):
                    pass
        
        # 跳过序号为空的行（这些通常是"其中："等说明行）
        if not no_str or pd.isna(no_val):
            continue
        
        # 解析工程名称
        name = str(name_val).strip() if name_val is not None and not pd.isna(name_val) else ""
        
        # 跳过空行
        if not name or name == "":
            continue
        
        # 判断是否为合计行（合计行需要跳过）
        is_total = any(kw in name for kw in ["合计", "总计", "总计", "合计金额"])
        if is_total:
            continue
        
        # 解析投资金额
        static_investment = parse_number(static_val)
        dynamic_investment = parse_number(dynamic_val)
        
        # 判断明细等级
        level = determine_level(name)
        
        # 普通数据行
        result.append({
            "No": no if no is not None else idx + 1,
            "name": name,
            "Level": level,
            "staticInvestment": static_investment,
            "dynamicInvestment": dynamic_investment,
        })
    
    return result


def parse_settlement_report_tables(
    merged_tables: List[Tuple[int, pd.DataFrame, str, int]]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    解析 settlementReport 类型的所有表格，按表名组织返回。
    
    返回格式:
    {
      "审定结算汇总表": [...],
      "合同执行情况": [],
      "赔偿合同": [],
      "物资采购合同1": [],
      "物资采购合同2": [],
      "其他服务类合同": [],
    }
    """
    result = {
        "审定结算汇总表": [],
        "合同执行情况": [],
        "赔偿合同": [],
        "物资采购合同1": [],
        "物资采购合同2": [],
        "其他服务类合同": [],
    }
    
    for orig_idx, df, rule_name, page in merged_tables:
        try:
            if rule_name == "审定结算汇总表":
                parsed_data = parse_settlement_summary_table(df)
                if parsed_data:
                    result[rule_name] = parsed_data
            elif rule_name == "合同执行情况":
                parsed_data = parse_contract_execution_table(df)
                if parsed_data:
                    result[rule_name] = parsed_data
            elif rule_name == "赔偿合同":
                parsed_data = parse_compensation_contract_table(df)
                if parsed_data:
                    result[rule_name] = parsed_data
            # 其他表暂时留空，后续实现
            # elif rule_name == "物资采购合同1":
            #     result[rule_name] = parse_material_purchase_contract1_table(df)
            # ...
        except Exception as e:
            # 如果解析失败，记录错误但不影响其他表格
            logger.warning(f"解析 {rule_name} 表格失败: {e}")
    
    return result


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

    logger.info(f"[表格提取] 开始处理 PDF: {pdf_path}, 文档类型: {doc_type}")

    # 1. 使用 pdfplumber 从 PDF 提取所有表格（不限制页数）
    logger.info("[表格提取] 步骤1: 使用 pdfplumber 提取所有表格...")
    tables_data = extract_tables_with_pdfplumber(str(pdf_path_obj), pages="all")
    logger.info(f"[表格提取] 步骤1完成: 共提取到 {len(tables_data)} 个表格")

    # 2. 保存所有原始表格为 xlsx，命名: table_page{page}_{index}.xlsx
    logger.info("[表格提取] 步骤2: 保存所有原始表格到 extracted_tables...")
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
    logger.info(f"[表格提取] 步骤2完成: 已保存 {len(all_tables)} 个原始表格")

    # 3. 合并所有跨页表格（不进行过滤），保存到 merged_tables
    logger.info("[表格提取] 步骤3: 合并跨页表格...")
    merged_all_tables = _merge_all_tables(all_tables)
    logger.info(f"[表格提取] 步骤3完成: 从 {len(all_tables)} 个原始表格合并为 {len(merged_all_tables)} 个表格")
    
    merged_page_table_count: Dict[int, int] = {}
    merged_meta: List[Dict[str, Any]] = []
    
    logger.info("[表格提取] 步骤3.1: 保存合并后的表格到 merged_tables...")
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
    logger.info(f"[表格提取] 步骤3.1完成: 已保存 {len(merged_meta)} 个合并后的表格")

    # 4. 根据 doc_type 选择对应的表头规则
    logger.info(f"[表格提取] 步骤4: 加载表头规则，文档类型: {doc_type}")
    header_rules = TABLE_TYPE_RULES.get(doc_type, [])
    logger.info(f"[表格提取] 步骤4完成: 找到 {len(header_rules)} 个表头规则")

    # 如果没有规则，直接返回（保留 extracted_tables 和 merged_tables）
    if not header_rules:
        logger.warning("[表格提取] 未找到表头规则，跳过筛选步骤")
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
    logger.info("[表格提取] 步骤5: 从合并后的表格中筛选匹配规则的表格...")
    matched_for_merge: List[Tuple[int, pd.DataFrame, str, int]] = []
    for merged_idx, (orig_idx, df, page) in enumerate(merged_all_tables):
        rule_name: Optional[str] = None
        for rule in header_rules:
            is_match, rn = check_table_header(df, rule)
            if is_match:
                rule_name = rn
                logger.info(f"[表格提取] 表格 {merged_idx + 1} (页面 {page}) 匹配规则: {rule_name}")
                break
        if rule_name:
            matched_for_merge.append((orig_idx, df.copy(), rule_name, page))
    logger.info(f"[表格提取] 步骤5完成: 共匹配到 {len(matched_for_merge)} 个表格")

    # 如果没有匹配到表格，直接返回（保留 extracted_tables 和 merged_tables）
    if not matched_for_merge:
        logger.warning("[表格提取] 未匹配到任何表格，跳过后续处理")
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
    logger.info("[表格提取] 步骤6: 对已匹配规则的表格进行跨页合并...")
    merged_tables = _merge_cross_page_tables(matched_for_merge, header_rules)
    logger.info(f"[表格提取] 步骤6完成: 跨页合并后剩余 {len(merged_tables)} 个表格")

    # 7. 保存筛选+合并后的表格到 filtered_dir，命名仍然按 page + 序号
    logger.info("[表格提取] 步骤7: 保存筛选+合并后的表格到 filtered_tables...")
    filtered_page_table_count: Dict[int, int] = {}
    filtered_meta: List[Dict[str, Any]] = []

    parsed_data = None
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
    logger.info(f"[表格提取] 步骤7完成: 已保存 {len(filtered_meta)} 个筛选后的表格")
    
    # 8. 根据文档类型解析表格数据
    logger.info(f"[表格提取] 步骤8: 解析表格数据，文档类型: {doc_type}...")
    if doc_type == "designReview":
        # 对于 designReview 类型，解析第一个匹配的表格生成 JSON 数据
        for orig_idx, df, rule_name, page in merged_tables:
            if parsed_data is None:
                try:
                    logger.info(f"[表格提取] 解析 designReview 表格: {rule_name} (页面 {page})")
                    parsed_data = parse_design_review_table(df)
                    logger.info(f"[表格提取] 解析完成: 共 {len(parsed_data)} 条数据")
                    break
                except Exception as e:
                    # 如果解析失败，记录错误但不影响其他流程
                    logger.warning(f"[表格提取] 解析 designReview 表格失败: {e}")
    elif doc_type == "settlementReport":
        # 对于 settlementReport 类型，解析所有匹配的表格，按表名组织
        try:
            logger.info(f"[表格提取] 解析 settlementReport 表格，共 {len(merged_tables)} 个表格")
            parsed_data = parse_settlement_report_tables(merged_tables)
            # 统计每个表的解析结果
            for table_name, table_data in parsed_data.items():
                if table_data:
                    logger.info(f"[表格提取] {table_name}: 解析完成，共 {len(table_data)} 条数据")
                else:
                    logger.info(f"[表格提取] {table_name}: 未匹配到数据")
        except Exception as e:
            logger.warning(f"[表格提取] 解析 settlementReport 表格失败: {e}")
    logger.info("[表格提取] 步骤8完成: 表格数据解析完成")

    result = {
        "tables_root": str(tables_root),
        "extracted_dir": str(extracted_dir),
        "merged_dir": str(merged_dir),
        "filtered_dir": str(filtered_dir),
        "all_tables": all_tables_meta,
        "merged_tables": merged_meta,
        "filtered_tables": filtered_meta,
    }
    
    # 添加解析后的 JSON 数据
    if parsed_data is not None:
        result["parsed_data"] = parsed_data
        result["parsed_data_json"] = json.dumps(parsed_data, ensure_ascii=False, indent=2)
        logger.info("[表格提取] JSON 数据已生成")
    
    logger.info(f"[表格提取] 处理完成: 原始表格 {len(all_tables_meta)} 个, 合并后 {len(merged_meta)} 个, 筛选后 {len(filtered_meta)} 个")
    return result


