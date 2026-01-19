from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional, Literal

import re
import json
import logging
import sys

import pandas as pd

# 尝试使用统一的日志系统
try:
    from ..utils.logging_config import get_logger
    logger = get_logger("pdf_converter_v2.utils.table_extractor")
except (ImportError, ValueError):
    # 如果无法导入，使用标准 logging
    logger = logging.getLogger(__name__)
    # 确保日志系统正确配置
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

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
        {
            "name": "初设评审的概算投资明细",
            "keywords": ["序号", "工程或费用名称", "建筑工程费", "设备购置费", "安装工程费", "其他费用", "合计"],
            "match_mode": "all",
        },
        {
            "name": "初设评审的概算投资费用",
            "keywords": ["序号", "工程或费用名称", "费用金额", "各项占静态投资", "单位投资"],
            "match_mode": "all",
        },
    ],
}


EXCLUDE_RULES: List[str] = []

# 是否启用跨页合并
ENABLE_MERGE_CROSS_PAGE_TABLES: bool = True


def extract_table_title_from_page(page, table_bbox: tuple, max_lines: int = 10) -> str:
    """
    从 PDF 页面中提取表格上方的文本作为表格标题。
    优先查找包含工程名称的行（如 "XXX变电站新建工程总概算表"）。
    
    Args:
        page: pdfplumber page 对象
        table_bbox: 表格的边界框 (x0, top, x1, bottom)
        max_lines: 最多向上搜索的行数
    
    Returns:
        str: 表格标题，如果未找到则返回空字符串
    """
    if not table_bbox:
        return ""
    
    table_top = table_bbox[1]  # 表格顶部 y 坐标
    page_width = page.width
    
    # 在表格上方区域搜索文本（向上搜索到页面顶部）
    search_top = 0  # 从页面顶部开始搜索
    search_bottom = table_top - 5  # 留一点边距
    
    if search_bottom <= search_top:
        return ""
    
    # 提取表格上方区域的文本
    crop_box = (0, search_top, page_width, search_bottom)
    try:
        cropped = page.within_bbox(crop_box)
        text = cropped.extract_text() or ""
    except Exception:
        return ""
    
    if not text.strip():
        return ""
    
    # 取所有行
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
    if not lines:
        return ""
    
    # 排除的关键词（这些不是工程名称）
    exclude_keywords = ["工程规模", "金额单位", "建设规模", "附表", "附件"]
    
    def is_valid_title(line: str) -> bool:
        """检查是否是有效的工程名称标题"""
        # 排除包含排除关键词的行
        if any(kw in line for kw in exclude_keywords):
            return False
        # 必须包含工程相关关键词
        if not any(kw in line for kw in ["工程", "概算表", "估算表"]):
            return False
        return True
    
    # 优先查找包含 "总概算表" 的行（最可能是工程名称）
    for line in reversed(lines):
        if "总概算表" in line and is_valid_title(line):
            # 进一步检查是否包含具体工程类型
            if any(kw in line for kw in ["变电站", "线路", "间隔", "kV", "KV", "千伏"]):
                return line.strip()
    
    # 次优先：查找包含 "概算表" 但不是 "总概算表" 的行
    for line in reversed(lines):
        if "概算表" in line and "总概算表" not in line and is_valid_title(line):
            if any(kw in line for kw in ["变电站", "线路", "间隔", "kV", "KV", "千伏"]):
                return line.strip()
    
    # 再次优先：查找包含 "变电站"/"线路"/"间隔" + "工程" 的行
    for line in reversed(lines):
        if is_valid_title(line):
            if any(kw in line for kw in ["变电站", "线路", "间隔"]) and "工程" in line:
                return line.strip()
    
    # 查找包含电压等级 + "工程" 的行
    for line in reversed(lines):
        if is_valid_title(line):
            if any(kw in line for kw in ["kV", "KV", "千伏", "kv"]) and "工程" in line:
                return line.strip()
    
    # 最后：返回任何包含工程关键词的有效行
    for line in reversed(lines):
        if is_valid_title(line):
            return line.strip()
    
    return ""


def extract_tables_with_pdfplumber(
    pdf_path: str,
    pages: str = "all",
    extract_titles: bool = False,
) -> List[Tuple[int, pd.DataFrame, tuple, str]]:
    """
    使用 pdfplumber 提取 PDF 中的表格。

    Args:
        pdf_path: PDF 文件路径
        pages: 页码范围，如 "all" 或 "1-5,7,9-10"
        extract_titles: 是否提取表格标题

    Returns:
        List[Tuple[int, pd.DataFrame, tuple, str]]: [(页码, DataFrame, bbox, title), ...]
        如果 extract_titles=False，title 为空字符串
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

    tables_data: List[Tuple[int, pd.DataFrame, tuple, str]] = []

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
                    # 提取表格标题
                    title = ""
                    if extract_titles:
                        title = extract_table_title_from_page(page, bbox)
                        if title:
                            logger.debug(f"[pdfplumber] 页面 {page_num}: 表格标题: {title}")
                    tables_data.append((page_num, df, bbox, title))
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
    tables: List[Tuple[int, pd.DataFrame, str, int, str]],
    header_rules: List[dict],
) -> List[Tuple[int, pd.DataFrame, str, int, str]]:
    """
    简化版跨页合并逻辑（用于已匹配规则的表格）：
    - 只处理"表头在当前页，内容在下一页"的典型情况；
    - 严格限制只合并相邻页，且列结构相似；
    - 如果下一页第一行看起来像新的表头，则不合并。
    
    元组格式: (orig_idx, df, rule_name, page, title)
    """
    if not ENABLE_MERGE_CROSS_PAGE_TABLES or not tables:
        return tables

    # page -> [(idx, df, rule_name, title)]
    page_map: Dict[int, List[Tuple[int, pd.DataFrame, str, str]]] = {}
    for orig_idx, df, rule_name, page, title in tables:
        page_map.setdefault(page, []).append((orig_idx, df, rule_name, title))

    merged: List[Tuple[int, pd.DataFrame, str, int, str]] = []
    processed: set[int] = set()

    sorted_pages = sorted(page_map.keys())

    for page in sorted_pages:
        current_list = page_map[page]
        for orig_idx, df, rule_name, title in current_list:
            if orig_idx in processed:
                continue

            current_df = df
            did_merge = False

            # 情况：当前表格只有表头，尝试合并下一页
            if is_likely_header_only(current_df):
                next_page = page + 1
                if next_page in page_map:
                    for next_orig_idx, next_df, next_rule_name, next_title in page_map[next_page]:
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
                        merged.append((orig_idx, merged_df, rule_name, page, title))
                        processed.add(orig_idx)
                        processed.add(next_orig_idx)
                        did_merge = True
                        break

            if not did_merge and orig_idx not in processed:
                merged.append((orig_idx, current_df, rule_name, page, title))
                processed.add(orig_idx)

    return merged


def _fix_broken_cells(table_df: pd.DataFrame, header_row_count: int = 1) -> pd.DataFrame:
    """
    修复被错误分割的单元格（一个单元格的内容被识别成多行）
    
    检测规则：
    1. 如果某一行的前N列有内容，但后面的列大部分为空（超过50%）
    2. 且上一行对应列有内容，则认为当前行是上一行的延续，需要合并
    
    Args:
        table_df: 表格DataFrame
        header_row_count: 表头行数，跳过表头不处理
    
    Returns:
        pd.DataFrame: 修复后的表格
    """
    if table_df.empty or len(table_df) <= header_row_count:
        return table_df
    
    df = table_df.copy()
    rows_to_remove = []
    
    # 从表头后开始检查
    for i in range(header_row_count, len(df)):
        if i <= header_row_count:
            continue  # 跳过第一行数据
        
        # 获取当前行
        current_row = df.iloc[i]
        prev_row = df.iloc[i-1]
        
        # 统计有内容的列和空列
        non_empty_cols = []
        empty_cols = []
        
        for j in range(len(df.columns)):
            val = current_row.iloc[j]
            val_str = str(val).strip()
            is_empty = (val is None or pd.isna(val) or not val_str or 
                       val_str.lower() in ['nan', 'none', '', '0', '0.0'])
            
            if is_empty:
                empty_cols.append(j)
            else:
                non_empty_cols.append(j)
        
        # 如果没有非空列，跳过
        if not non_empty_cols:
            continue
        
        # 计算空列比例
        empty_ratio = len(empty_cols) / len(df.columns) if len(df.columns) > 0 else 0
        
        # 如果空列超过50%，可能是被截断的行
        if empty_ratio > 0.5:
            # 检查上一行对应位置是否有内容
            can_merge = True
            merge_cols = []
            
            for col_idx in non_empty_cols:
                prev_val = prev_row.iloc[col_idx]
                prev_val_str = str(prev_val).strip()
                curr_val = current_row.iloc[col_idx]
                curr_val_str = str(curr_val).strip()
                
                # 如果上一行对应列有内容，可以合并
                if prev_val_str and prev_val_str.lower() not in ['nan', 'none', '', '0', '0.0']:
                    merge_cols.append(col_idx)
                else:
                    # 如果上一行对应列为空，但当前行有内容，可能是新行，不合并
                    # 但如果只有前几列有内容，且都是文本（不是数字），可能是延续
                    if col_idx < len(df.columns) * 0.5:  # 前50%的列
                        # 检查是否是文本（不是纯数字）
                        if not curr_val_str.replace('.', '').replace('-', '').isdigit():
                            merge_cols.append(col_idx)
                        else:
                            can_merge = False
                            break
                    else:
                        can_merge = False
                        break
            
            if can_merge and merge_cols:
                # 合并每个非空列到上一行对应的列
                for col_idx in merge_cols:
                    prev_val = str(prev_row.iloc[col_idx]).strip()
                    curr_val = str(current_row.iloc[col_idx]).strip()
                    # 合并（移除换行符）
                    merged_val = prev_val + curr_val.replace('\n', '').replace('\r', '')
                    df.iloc[i-1, col_idx] = merged_val
                
                rows_to_remove.append(i)
                logger.debug(f"[跨行合并] 合并行 {i} 到行 {i-1}，列: {merge_cols}")
    
    # 删除已合并的行
    if rows_to_remove:
        df = df.drop(rows_to_remove).reset_index(drop=True)
        logger.info(f"[跨行合并] 修复了 {len(rows_to_remove)} 个被错误分割的单元格（跨行）")
    
    return df


def _format_header_text(cell_val: str) -> str:
    """
    格式化表头文本：移除换行符和多余空格，用于匹配。
    
    Args:
        cell_val: 原始单元格值
    
    Returns:
        格式化后的文本（移除所有空格，用于精确匹配）
    """
    if not cell_val or str(cell_val).lower() in ['nan', 'none', '']:
        return ""
    # 清理换行符，直接移除
    text = str(cell_val).strip().replace('\n', '').replace('\r', '')
    # 移除所有空格，用于匹配
    text = re.sub(r'\s+', '', text)
    return text


def _detect_header_rows(df: pd.DataFrame, header_row_idx: int, header_keywords: List[str]) -> int:
    """
    智能检测表头行数，避免把数据行当作表头。
    
    Args:
        df: 数据框
        header_row_idx: 已识别的表头行索引
        header_keywords: 表头关键词列表
    
    Returns:
        表头行数（从 header_row_idx 开始）
    """
    header_rows_to_check = 1
    
    # 检查后续行是否是表头的延续
    for i in range(header_row_idx + 1, min(header_row_idx + 3, len(df))):
        row = df.iloc[i]
        row_text = " ".join(row.astype(str).str.strip().tolist())
        
        # 检查是否包含表头关键词
        keyword_count = sum(1 for kw in header_keywords if kw in row_text)
        
        # 如果包含关键词，进一步判断
        if keyword_count >= 2:  # 至少包含2个关键词才可能是表头
            # 检查是否主要是数字（如果是，则不是表头）
            numeric_count = sum(1 for cell in row if str(cell).strip().replace('.', '').replace('-', '').isdigit())
            numeric_ratio = numeric_count / len(row) if len(row) > 0 else 0
            
            # 检查是否包含明显的公司名称、人名等（如果是，则不是表头）
            has_company_name = any(
                '公司' in str(cell) or '有限' in str(cell) or '股份' in str(cell) or 
                '工程' in str(cell) or '集团' in str(cell) or '局' in str(cell)
                for cell in row
            )
            
            # 如果数字占比小于30%且不包含公司名称，可能是表头
            if numeric_ratio < 0.3 and not has_company_name:
                header_rows_to_check += 1
            else:
                # 包含公司名称或数字占比高，是数据行，停止
                break
        else:
            # 关键词太少，不是表头，停止
            break
    
    return header_rows_to_check


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
    
    # 先修复跨行单元格（在识别表头之前）
    df = _fix_broken_cells(df, header_row_count=header_row_idx + 1)
    
    # 合并前几行作为表头（处理多行表头的情况）
    header_keywords = ["序号", "审计内容", "送审金额", "审定金额", "增减金额", "备注"]
    header_rows_to_check = _detect_header_rows(df, header_row_idx, header_keywords)
    header_texts = []  # 每列的合并文本
    num_cols = len(df.columns)
    
    # 打印原始表头行（用于调试）
    logger.info(f"[审定结算汇总表] 原始表头行 (从第 {header_row_idx + 1} 行开始，共检查 {header_rows_to_check} 行):")
    for row_idx in range(header_row_idx, min(header_row_idx + header_rows_to_check, len(df))):
        row_data = [str(df.iloc[row_idx, col_idx]).strip() for col_idx in range(num_cols)]
        logger.info(f"[审定结算汇总表]   第 {row_idx + 1} 行: {row_data}")
    
    for col_idx in range(num_cols):
        col_text_parts = []
        for row_idx in range(header_row_idx, header_row_idx + header_rows_to_check):
            if row_idx < len(df):
                cell_val = str(df.iloc[row_idx, col_idx]).strip()
                if cell_val and cell_val.lower() not in ['nan', 'none', '']:
                    # 格式化表头文本（移除换行符和空格）
                    formatted_text = _format_header_text(cell_val)
                    if formatted_text:
                        col_text_parts.append(formatted_text)
        # 合并该列的所有表头文本（已经是格式化后的，无空格）
        merged_text = ''.join(col_text_parts)
        header_texts.append(merged_text)
    
    logger.info(f"[审定结算汇总表] 合并后的表头文本（已格式化）: {header_texts}")
    
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
    
    logger.info(f"[审定结算汇总表] 列识别: 序号={col_no}, 项目名称={col_name}, 不含税={col_tax_exclusive}, 含税={col_tax_inclusive}")
    
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
        name = name.replace('\n', '').replace('\r', '')  # 直接移除换行符，不替换为空格
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
    
    # 先修复跨行单元格（在识别表头之前）
    df = _fix_broken_cells(df, header_row_count=header_row_idx + 1)
    
    # 合并前几行作为表头（处理多行表头的情况）
    # 智能判断表头行数：表头行通常不包含纯数字（除了序号列）
    header_rows_to_check = 1
    for i in range(header_row_idx + 1, min(header_row_idx + 3, len(df))):
        row = df.iloc[i]
        # 检查这一行是否像表头（包含关键词且不全是数字）
        row_text = " ".join(row.astype(str).str.strip().tolist())
        has_keywords = any(kw in row_text for kw in ["施工单位", "中标", "合同", "结算", "送审", "差额"])
        # 如果包含关键词且看起来不像数据行（不全是数字），则可能是表头的一部分
        if has_keywords:
            # 检查是否主要是数字（如果是，则不是表头）
            numeric_count = sum(1 for cell in row if str(cell).strip().replace('.', '').replace('-', '').isdigit())
            if numeric_count < len(row) * 0.5:  # 如果数字占比小于50%，可能是表头
                header_rows_to_check += 1
            else:
                break
        else:
            break
    
    header_texts = []  # 每列的合并文本
    num_cols = len(df.columns)
    
    # 打印原始表头行（用于调试）
    logger.info(f"[合同执行情况] 原始表头行 (从第 {header_row_idx + 1} 行开始，共检查 {header_rows_to_check} 行):")
    for row_idx in range(header_row_idx, min(header_row_idx + header_rows_to_check, len(df))):
        row_data = [str(df.iloc[row_idx, col_idx]).strip() for col_idx in range(num_cols)]
        logger.info(f"[合同执行情况]   第 {row_idx + 1} 行: {row_data}")
    
    for col_idx in range(num_cols):
        col_text_parts = []
        for row_idx in range(header_row_idx, header_row_idx + header_rows_to_check):
            if row_idx < len(df):
                cell_val = str(df.iloc[row_idx, col_idx]).strip()
                if cell_val and cell_val.lower() not in ['nan', 'none', '']:
                    # 格式化表头文本（移除换行符和空格）
                    formatted_text = _format_header_text(cell_val)
                    if formatted_text:
                        col_text_parts.append(formatted_text)
        # 合并该列的所有表头文本（已经是格式化后的，无空格）
        merged_text = ''.join(col_text_parts)
        header_texts.append(merged_text)
    
    logger.info(f"[合同执行情况] 合并后的表头文本（已格式化）: {header_texts}")
    
    col_no = None  # 序号列
    col_construction_unit = None  # 施工单位列
    col_bid_notice_amount = None  # 中标通知书金额列
    col_bid_notice_no = None  # 中标通知书编号列
    col_contract_amount = None  # 合同金额列
    col_settlement_submitted = None  # 结算送审金额列
    col_difference = None  # 差额列
    
    for idx, header_text in enumerate(header_texts):
        cell_lower = header_text.lower()
        # header_text 已经是格式化后的（无空格），直接使用
        
        if "序号" in header_text or "no" in cell_lower:
            col_no = idx
        elif "施工单位" in header_text:
            col_construction_unit = idx
        elif "中标" in header_text and "金额" in header_text:
            col_bid_notice_amount = idx
        elif "中标" in header_text and "编号" in header_text:
            col_bid_notice_no = idx
        elif ("合同金额" in header_text or 
              ("合同" in header_text and "金额" in header_text and 
               "结算" not in header_text and "送审" not in header_text)):
            col_contract_amount = idx
        elif ("结算送审金额" in header_text or 
              ("送审" in header_text and "金额" in header_text) or
              ("结算" in header_text and "送审" in header_text)):
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
        # 尝试更灵活的匹配：合同金额可能在"合同"和"金额"分开的列中
        for idx, header_text in enumerate(header_texts):
            # header_text 已经是格式化后的（无空格），直接使用
            # 检查是否包含"合同"和"金额"，且不包含"结算"、"送审"等
            if ("合同" in header_text and "金额" in header_text and
                "结算" not in header_text and "送审" not in header_text):
                col_contract_amount = idx
                break
    
    if col_settlement_submitted is None:
        # 尝试更灵活的匹配：结算送审金额可能在"结算"、"送审"、"金额"分开的列中
        for idx, header_text in enumerate(header_texts):
            # header_text 已经是格式化后的（无空格），直接使用
            # 检查是否包含"送审"和"金额"，或者"结算"和"送审"
            if (("送审" in header_text and "金额" in header_text) or
                ("结算" in header_text and "送审" in header_text) or
                "结算送审金额" in header_text):
                col_settlement_submitted = idx
                break
    
    if col_difference is None:
        for idx, header_text in enumerate(header_texts):
            if "差额" in header_text:
                col_difference = idx
                break
    
    logger.info(f"[合同执行情况] 列识别: 序号={col_no}, 施工单位={col_construction_unit}, "
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
        # 清理换行符，直接移除
        construction_unit = construction_unit.replace('\n', '').replace('\r', '')
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
        bid_notice_no = bid_notice_no.replace('\n', '').replace('\r', '')
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
    
    # 先修复跨行单元格（在识别表头之前）
    df = _fix_broken_cells(df, header_row_count=header_row_idx + 1)
    
    # 合并前几行作为表头（处理多行表头的情况）
    header_keywords = ["序号", "合同对方", "赔偿事项", "合同金额", "结算送审金额", "差额"]
    header_rows_to_check = _detect_header_rows(df, header_row_idx, header_keywords)
    header_texts = []  # 每列的合并文本
    num_cols = len(df.columns)
    
    # 打印原始表头行（用于调试）
    logger.info(f"[赔偿合同] 原始表头行 (从第 {header_row_idx + 1} 行开始，共检查 {header_rows_to_check} 行):")
    for row_idx in range(header_row_idx, min(header_row_idx + header_rows_to_check, len(df))):
        row_data = [str(df.iloc[row_idx, col_idx]).strip() for col_idx in range(num_cols)]
        logger.info(f"[赔偿合同]   第 {row_idx + 1} 行: {row_data}")
    
    for col_idx in range(num_cols):
        col_text_parts = []
        for row_idx in range(header_row_idx, header_row_idx + header_rows_to_check):
            if row_idx < len(df):
                cell_val = str(df.iloc[row_idx, col_idx]).strip()
                if cell_val and cell_val.lower() not in ['nan', 'none', '']:
                    # 格式化表头文本（移除换行符和空格）
                    formatted_text = _format_header_text(cell_val)
                    if formatted_text:
                        col_text_parts.append(formatted_text)
        # 合并该列的所有表头文本（已经是格式化后的，无空格）
        merged_text = ''.join(col_text_parts)
        header_texts.append(merged_text)
    
    logger.info(f"[赔偿合同] 合并后的表头文本（已格式化）: {header_texts}")
    
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
    
    logger.info(f"[赔偿合同] 列识别: 序号={col_no}, 合同对方={col_counterparty_name}, "
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
        counterparty_name = counterparty_name.replace('\n', '').replace('\r', '')
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
        compensation_item = compensation_item.replace('\n', '').replace('\r', '')
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


def parse_material_purchase_contract1_table(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    解析"物资采购合同1"表，提取数据并生成 JSON 格式。
    
    返回格式:
    [{
        "No": int,  # 序号
        "materialName": str,  # 物料名称
        "contractQuantity": float,  # 合同数量
        "drawingQuantity": float,  # 施工图数量
        "unitPriceExcludingTax": float,  # 单价（不含税）（元，两位小数）
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
        if any(kw in row_text for kw in ["序号", "物料名称", "合同数量", "施工图数量", "单价（不含税）", "差额"]):
            header_row_idx = i
            break
    
    if header_row_idx is None:
        # 如果没有找到明确的表头，假设第一行是表头
        header_row_idx = 0
    
    # 先修复跨行单元格（在识别表头之前）
    df = _fix_broken_cells(df, header_row_count=header_row_idx + 1)
    
    # 合并前几行作为表头（处理多行表头的情况）
    header_keywords = ["序号", "物料名称", "合同数量", "施工图数量", "单价", "差额"]
    header_rows_to_check = _detect_header_rows(df, header_row_idx, header_keywords)
    header_texts = []  # 每列的合并文本
    num_cols = len(df.columns)
    
    # 打印原始表头行（用于调试）
    logger.info(f"[物资采购合同1] 原始表头行 (从第 {header_row_idx + 1} 行开始，共检查 {header_rows_to_check} 行):")
    for row_idx in range(header_row_idx, min(header_row_idx + header_rows_to_check, len(df))):
        row_data = [str(df.iloc[row_idx, col_idx]).strip() for col_idx in range(num_cols)]
        logger.info(f"[物资采购合同1]   第 {row_idx + 1} 行: {row_data}")
    
    for col_idx in range(num_cols):
        col_text_parts = []
        for row_idx in range(header_row_idx, header_row_idx + header_rows_to_check):
            if row_idx < len(df):
                cell_val = str(df.iloc[row_idx, col_idx]).strip()
                if cell_val and cell_val.lower() not in ['nan', 'none', '']:
                    # 格式化表头文本（移除换行符和空格）
                    formatted_text = _format_header_text(cell_val)
                    if formatted_text:
                        col_text_parts.append(formatted_text)
        # 合并该列的所有表头文本（已经是格式化后的，无空格）
        merged_text = ''.join(col_text_parts)
        header_texts.append(merged_text)
    
    logger.info(f"[物资采购合同1] 合并后的表头文本（已格式化）: {header_texts}")
    
    col_no = None  # 序号列
    col_material_name = None  # 物料名称列
    col_contract_quantity = None  # 合同数量列
    col_drawing_quantity = None  # 施工图数量列
    col_unit_price = None  # 单价（不含税）列
    col_difference = None  # 差额列
    
    for idx, header_text in enumerate(header_texts):
        cell_lower = header_text.lower()
        if "序号" in header_text or "no" in cell_lower:
            col_no = idx
        elif "物料名称" in header_text:
            col_material_name = idx
        elif "合同数量" in header_text:
            col_contract_quantity = idx
        elif "施工图数量" in header_text:
            col_drawing_quantity = idx
        elif "单价" in header_text and "不含税" in header_text:
            col_unit_price = idx
        elif "差额" in header_text:
            col_difference = idx
    
    # 如果关键列未找到，尝试通过位置推断
    if col_no is None:
        col_no = 0
    if col_material_name is None:
        col_material_name = 1
    
    # 如果数量列未找到，尝试查找
    if col_contract_quantity is None:
        for idx, header_text in enumerate(header_texts):
            if "合同" in header_text and "数量" in header_text:
                col_contract_quantity = idx
                break
    
    if col_drawing_quantity is None:
        for idx, header_text in enumerate(header_texts):
            if "施工图" in header_text and "数量" in header_text:
                col_drawing_quantity = idx
                break
    
    # 如果金额列未找到，尝试从后往前找（通常金额列在表格右侧）
    if col_unit_price is None:
        for idx, header_text in enumerate(header_texts):
            if "单价" in header_text:
                col_unit_price = idx
                break
    
    if col_difference is None:
        for idx in range(len(header_texts) - 1, -1, -1):
            if "差额" in header_texts[idx]:
                col_difference = idx
                break
    
    logger.info(f"[物资采购合同1] 列识别: 序号={col_no}, 物料名称={col_material_name}, "
                f"合同数量={col_contract_quantity}, 施工图数量={col_drawing_quantity}, "
                f"单价={col_unit_price}, 差额={col_difference}")
    
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
        material_name_val = row.iloc[col_material_name] if col_material_name is not None and col_material_name < len(row) else None
        contract_quantity_val = row.iloc[col_contract_quantity] if col_contract_quantity is not None and col_contract_quantity < len(row) else None
        drawing_quantity_val = row.iloc[col_drawing_quantity] if col_drawing_quantity is not None and col_drawing_quantity < len(row) else None
        unit_price_val = row.iloc[col_unit_price] if col_unit_price is not None and col_unit_price < len(row) else None
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
        
        # 解析物料名称，清理换行符
        material_name = str(material_name_val).strip() if material_name_val is not None and not pd.isna(material_name_val) else ""
        material_name = material_name.replace('\n', '').replace('\r', '')
        material_name = re.sub(r'\s+', ' ', material_name).strip()
        
        # 跳过空行
        if not material_name or material_name == "":
            continue
        
        # 判断是否为合计行（合计行需要跳过）
        is_total = any(kw in material_name for kw in ["合计", "总计", "总计", "合计金额"])
        if is_total:
            continue
        
        # 解析数量（合同数量和施工图数量可能是整数或小数）
        contract_quantity = parse_number(contract_quantity_val)
        drawing_quantity = parse_number(drawing_quantity_val)
        
        # 解析金额（保留两位小数）
        unit_price_excluding_tax = parse_number(unit_price_val)
        difference_amount = parse_number(difference_val)
        
        # 添加到结果
        result.append({
            "No": no if no is not None else idx + 1,
            "materialName": material_name,
            "contractQuantity": contract_quantity,
            "drawingQuantity": drawing_quantity,
            "unitPriceExcludingTax": unit_price_excluding_tax,
            "differenceAmount": difference_amount,
        })
    
    return result


def parse_material_purchase_contract2_table(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    解析"物资采购合同2"表，提取数据并生成 JSON 格式。
    
    返回格式:
    [{
        "No": int,  # 序号
        "materialName": str,  # 物料名称
        "contractAmount": float,  # 合同金额（元，两位小数）
        "bookedAmount": float,  # 入账金额（元，两位小数）
        "differenceAmount": float,  # 差额（元，两位小数）
        "remark": str,  # 备注
    }, ...]
    """
    if df.empty:
        return []
    
    # 尝试识别表头行（通常在前几行）
    header_row_idx = None
    for i in range(min(3, len(df))):
        row_text = " ".join(df.iloc[i].astype(str).str.strip().tolist())
        # 检查是否包含表头关键词
        if any(kw in row_text for kw in ["序号", "物料名称", "合同金额（不含税）", "入账金额", "差额", "备注"]):
            header_row_idx = i
            break
    
    if header_row_idx is None:
        # 如果没有找到明确的表头，假设第一行是表头
        header_row_idx = 0
    
    # 先修复跨行单元格（在识别表头之前）
    df = _fix_broken_cells(df, header_row_count=header_row_idx + 1)
    
    # 合并前几行作为表头（处理多行表头的情况）
    header_keywords = ["序号", "物料名称", "合同金额", "入账金额", "差额", "备注"]
    header_rows_to_check = _detect_header_rows(df, header_row_idx, header_keywords)
    header_texts = []  # 每列的合并文本
    num_cols = len(df.columns)
    
    # 打印原始表头行（用于调试）
    logger.info(f"[物资采购合同2] 原始表头行 (从第 {header_row_idx + 1} 行开始，共检查 {header_rows_to_check} 行):")
    for row_idx in range(header_row_idx, min(header_row_idx + header_rows_to_check, len(df))):
        row_data = [str(df.iloc[row_idx, col_idx]).strip() for col_idx in range(num_cols)]
        logger.info(f"[物资采购合同2]   第 {row_idx + 1} 行: {row_data}")
    
    for col_idx in range(num_cols):
        col_text_parts = []
        for row_idx in range(header_row_idx, header_row_idx + header_rows_to_check):
            if row_idx < len(df):
                cell_val = str(df.iloc[row_idx, col_idx]).strip()
                if cell_val and cell_val.lower() not in ['nan', 'none', '']:
                    # 格式化表头文本（移除换行符和空格）
                    formatted_text = _format_header_text(cell_val)
                    if formatted_text:
                        col_text_parts.append(formatted_text)
        # 合并该列的所有表头文本（已经是格式化后的，无空格）
        merged_text = ''.join(col_text_parts)
        header_texts.append(merged_text)
    
    logger.info(f"[物资采购合同2] 合并后的表头文本（已格式化）: {header_texts}")
    
    col_no = None  # 序号列
    col_material_name = None  # 物料名称列
    col_contract_amount = None  # 合同金额（不含税）列
    col_booked_amount = None  # 入账金额列
    col_difference = None  # 差额列
    col_remark = None  # 备注列
    
    for idx, header_text in enumerate(header_texts):
        cell_lower = header_text.lower()
        if "序号" in header_text or "no" in cell_lower:
            col_no = idx
        elif "物料名称" in header_text:
            col_material_name = idx
        elif "合同金额" in header_text and "不含税" in header_text:
            col_contract_amount = idx
        elif "入账金额" in header_text:
            col_booked_amount = idx
        elif "差额" in header_text:
            col_difference = idx
        elif "备注" in header_text:
            col_remark = idx
    
    # 如果关键列未找到，尝试通过位置推断
    if col_no is None:
        col_no = 0
    if col_material_name is None:
        col_material_name = 1
    
    # 如果金额列未找到，尝试查找
    if col_contract_amount is None:
        for idx, header_text in enumerate(header_texts):
            if "合同金额" in header_text:
                col_contract_amount = idx
                break
    
    if col_booked_amount is None:
        for idx, header_text in enumerate(header_texts):
            if "入账" in header_text and "金额" in header_text:
                col_booked_amount = idx
                break
    
    # 如果差额列未找到，尝试从后往前找（通常差额列在表格右侧）
    if col_difference is None:
        for idx in range(len(header_texts) - 1, -1, -1):
            if "差额" in header_texts[idx]:
                col_difference = idx
                break
    
    # 备注列通常在最后
    if col_remark is None:
        for idx in range(len(header_texts) - 1, -1, -1):
            if "备注" in header_texts[idx]:
                col_remark = idx
                break
    
    logger.info(f"[物资采购合同2] 列识别: 序号={col_no}, 物料名称={col_material_name}, "
                f"合同金额={col_contract_amount}, 入账金额={col_booked_amount}, "
                f"差额={col_difference}, 备注={col_remark}")
    
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
        material_name_val = row.iloc[col_material_name] if col_material_name is not None and col_material_name < len(row) else None
        contract_amount_val = row.iloc[col_contract_amount] if col_contract_amount is not None and col_contract_amount < len(row) else None
        booked_amount_val = row.iloc[col_booked_amount] if col_booked_amount is not None and col_booked_amount < len(row) else None
        difference_val = row.iloc[col_difference] if col_difference is not None and col_difference < len(row) else None
        remark_val = row.iloc[col_remark] if col_remark is not None and col_remark < len(row) else None
        
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
        
        # 解析物料名称，清理换行符
        material_name = str(material_name_val).strip() if material_name_val is not None and not pd.isna(material_name_val) else ""
        material_name = material_name.replace('\n', '').replace('\r', '')
        material_name = re.sub(r'\s+', ' ', material_name).strip()
        
        # 跳过空行
        if not material_name or material_name == "":
            continue
        
        # 判断是否为合计行（合计行需要跳过）
        is_total = any(kw in material_name for kw in ["合计", "总计", "总计", "合计金额"])
        if is_total:
            continue
        
        # 解析金额（保留两位小数）
        contract_amount = parse_number(contract_amount_val)
        booked_amount = parse_number(booked_amount_val)
        difference_amount = parse_number(difference_val)
        
        # 解析备注，清理换行符
        remark = str(remark_val).strip() if remark_val is not None and not pd.isna(remark_val) else ""
        remark = remark.replace('\n', '').replace('\r', '')
        remark = re.sub(r'\s+', ' ', remark).strip()
        
        # 添加到结果
        result.append({
            "No": no if no is not None else idx + 1,
            "materialName": material_name,
            "contractAmount": contract_amount,
            "bookedAmount": booked_amount,
            "differenceAmount": difference_amount,
            "remark": remark,
        })
    
    return result


def parse_other_service_contract_table(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    解析"其他服务类合同"表，提取数据并生成 JSON 格式。
    
    返回格式:
    [{
        "No": int,  # 序号
        "serviceProvider": str,  # 服务商
        "bidNotice": str,  # 中标通知书
        "contractAmount": float,  # 合同金额（元，两位小数）
        "submittedAmount": float,  # 送审金额（元，两位小数）
        "settlementAmount": float,  # 结算金额（元，两位小数）
    }, ...]
    """
    if df.empty:
        return []
    
    # 尝试识别表头行（通常在前几行）
    header_row_idx = None
    for i in range(min(3, len(df))):
        row_text = " ".join(df.iloc[i].astype(str).str.strip().tolist())
        # 检查是否包含表头关键词
        if any(kw in row_text for kw in ["序号", "服务商", "中标通知书", "合同金额", "送审金额", "结算金额"]):
            header_row_idx = i
            break
    
    if header_row_idx is None:
        # 如果没有找到明确的表头，假设第一行是表头
        header_row_idx = 0
    
    # 先修复跨行单元格（在识别表头之前）
    df = _fix_broken_cells(df, header_row_count=header_row_idx + 1)
    
    # 合并前几行作为表头（处理多行表头的情况）
    header_keywords = ["序号", "服务商", "中标通知书", "合同金额", "送审金额", "结算金额"]
    header_rows_to_check = _detect_header_rows(df, header_row_idx, header_keywords)
    header_texts = []  # 每列的合并文本
    num_cols = len(df.columns)
    
    # 打印原始表头行（用于调试）
    logger.info(f"[其他服务类合同] 原始表头行 (从第 {header_row_idx + 1} 行开始，共检查 {header_rows_to_check} 行):")
    for row_idx in range(header_row_idx, min(header_row_idx + header_rows_to_check, len(df))):
        row_data = [str(df.iloc[row_idx, col_idx]).strip() for col_idx in range(num_cols)]
        logger.info(f"[其他服务类合同]   第 {row_idx + 1} 行: {row_data}")
    
    for col_idx in range(num_cols):
        col_text_parts = []
        for row_idx in range(header_row_idx, header_row_idx + header_rows_to_check):
            if row_idx < len(df):
                cell_val = str(df.iloc[row_idx, col_idx]).strip()
                if cell_val and cell_val.lower() not in ['nan', 'none', '']:
                    # 格式化表头文本（移除换行符和空格）
                    formatted_text = _format_header_text(cell_val)
                    if formatted_text:
                        col_text_parts.append(formatted_text)
        # 合并该列的所有表头文本（已经是格式化后的，无空格）
        merged_text = ''.join(col_text_parts)
        header_texts.append(merged_text)
    
    logger.info(f"[其他服务类合同] 合并后的表头文本（已格式化）: {header_texts}")
    
    col_no = None  # 序号列
    col_service_provider = None  # 服务商列
    col_bid_notice = None  # 中标通知书列
    col_contract_amount = None  # 合同金额列
    col_submitted_amount = None  # 送审金额列
    col_settlement_amount = None  # 结算金额列
    
    for idx, header_text in enumerate(header_texts):
        cell_lower = header_text.lower()
        if "序号" in header_text or "no" in cell_lower:
            col_no = idx
        elif "服务商" in header_text:
            col_service_provider = idx
        elif "中标通知书" in header_text:
            col_bid_notice = idx
        elif "合同金额" in header_text and "送审" not in header_text and "结算" not in header_text:
            col_contract_amount = idx
        elif "送审金额" in header_text:
            col_submitted_amount = idx
        elif "结算金额" in header_text:
            col_settlement_amount = idx
    
    # 如果关键列未找到，尝试通过位置推断
    if col_no is None:
        col_no = 0
    if col_service_provider is None:
        col_service_provider = 1
    
    # 如果金额列未找到，尝试查找
    if col_contract_amount is None:
        for idx, header_text in enumerate(header_texts):
            if "合同" in header_text and "金额" in header_text:
                col_contract_amount = idx
                break
    
    if col_submitted_amount is None:
        for idx, header_text in enumerate(header_texts):
            if "送审" in header_text and "金额" in header_text:
                col_submitted_amount = idx
                break
    
    if col_settlement_amount is None:
        for idx, header_text in enumerate(header_texts):
            if "结算" in header_text and "金额" in header_text:
                col_settlement_amount = idx
                break
    
    # 如果中标通知书列未找到，尝试查找
    if col_bid_notice is None:
        for idx, header_text in enumerate(header_texts):
            if "中标" in header_text and "通知" in header_text:
                col_bid_notice = idx
                break
    
    logger.info(f"[其他服务类合同] 列识别: 序号={col_no}, 服务商={col_service_provider}, "
                f"中标通知书={col_bid_notice}, 合同金额={col_contract_amount}, "
                f"送审金额={col_submitted_amount}, 结算金额={col_settlement_amount}")
    
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
        service_provider_val = row.iloc[col_service_provider] if col_service_provider is not None and col_service_provider < len(row) else None
        bid_notice_val = row.iloc[col_bid_notice] if col_bid_notice is not None and col_bid_notice < len(row) else None
        contract_amount_val = row.iloc[col_contract_amount] if col_contract_amount is not None and col_contract_amount < len(row) else None
        submitted_amount_val = row.iloc[col_submitted_amount] if col_submitted_amount is not None and col_submitted_amount < len(row) else None
        settlement_amount_val = row.iloc[col_settlement_amount] if col_settlement_amount is not None and col_settlement_amount < len(row) else None
        
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
        
        # 解析服务商，清理换行符
        service_provider = str(service_provider_val).strip() if service_provider_val is not None and not pd.isna(service_provider_val) else ""
        service_provider = service_provider.replace('\n', '').replace('\r', '')
        service_provider = re.sub(r'\s+', ' ', service_provider).strip()
        
        # 跳过空行
        if not service_provider or service_provider == "":
            continue
        
        # 判断是否为合计行（合计行需要跳过）
        is_total = any(kw in service_provider for kw in ["合计", "总计", "总计", "合计金额"])
        if is_total:
            continue
        
        # 解析中标通知书，清理换行符
        bid_notice = str(bid_notice_val).strip() if bid_notice_val is not None and not pd.isna(bid_notice_val) else ""
        bid_notice = bid_notice.replace('\n', '').replace('\r', '')
        bid_notice = re.sub(r'\s+', ' ', bid_notice).strip()
        
        # 解析金额（保留两位小数）
        contract_amount = parse_number(contract_amount_val)
        submitted_amount = parse_number(submitted_amount_val)
        settlement_amount = parse_number(settlement_amount_val)
        
        # 添加到结果
        result.append({
            "No": no if no is not None else idx + 1,
            "serviceProvider": service_provider,
            "bidNotice": bid_notice,
            "contractAmount": contract_amount,
            "submittedAmount": submitted_amount,
            "settlementAmount": settlement_amount,
        })
    
    return result


def parse_design_review_table(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    解析 designReview 类型的表格，提取数据并生成结构化的 JSON 格式。
    
    返回格式:
    [{
        "name": str,  # 大类名称（如"变电工程"、"线路工程"）
        "Level": 0,  # 大类层级
        "staticInvestment": float,  # 静态投资总计
        "dynamicInvestment": float,  # 动态投资总计
        "items": [  # 子项列表
            {
                "No": int,  # 序号
                "name": str,  # 工程名称
                "Level": 1,  # 子项层级
                "staticInvestment": float,  # 静态投资
                "dynamicInvestment": float,  # 动态投资
            },
            ...
        ]
    }, ...]
    """
    if df.empty:
        return []
    
    # 中文数字映射（用于识别序号格式）
    CHINESE_NUMBERS = {
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
        '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15, '十六': 16, '十七': 17, '十八': 18, '十九': 19, '二十': 20
    }
    
    def is_category_by_serial(no_str: str) -> bool:
        """
        通过序号格式判断是否为大类
        大类：序号为中文数字，如"一"、"二"、"三"（不含括号）
        子类：序号为带括号的中文数字，如"（一）"、"（二）"、"（三）"
        """
        if not no_str:
            return False
        
        no_str = str(no_str).strip()
        
        # 如果包含括号，是子类
        if '（' in no_str or '(' in no_str or '）' in no_str or ')' in no_str:
            return False
        
        # 检查是否是中文数字（大类）
        # 移除可能的空格和标点
        cleaned = no_str.replace(' ', '').replace('、', '').replace('.', '').replace('。', '')
        
        # 检查是否以中文数字开头
        for chinese_num in CHINESE_NUMBERS.keys():
            if cleaned.startswith(chinese_num):
                return True
        
        return False
    
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
    
    # 先解析所有行
    all_items = []
    for idx, row in data_rows.iterrows():
        # 跳过空行
        if row.isna().all():
            continue
        
        # 提取各列数据
        no_val = row.iloc[col_no] if col_no is not None and col_no < len(row) else None
        name_val = row.iloc[col_name] if col_name is not None and col_name < len(row) else None
        static_val = row.iloc[col_static] if col_static is not None and col_static < len(row) else None
        dynamic_val = row.iloc[col_dynamic] if col_dynamic is not None and col_dynamic < len(row) else None
        
        # 解析序号（保留原始字符串）
        no = None
        no_str = ""
        if no_val is not None and not pd.isna(no_val):
            no_str = str(no_val).strip()
            if no_str:
                # 先尝试解析为数字
                try:
                    no = int(float(no_str))
                except (ValueError, TypeError):
                    # 如果不是数字，尝试解析中文数字
                    cleaned = no_str.replace(' ', '').replace('、', '').replace('.', '').replace('。', '')
                    # 移除括号
                    cleaned_no_brackets = cleaned.replace('（', '').replace('(', '').replace('）', '').replace(')', '')
                    if cleaned_no_brackets in CHINESE_NUMBERS:
                        no = CHINESE_NUMBERS[cleaned_no_brackets]
                    else:
                        # 尝试匹配中文数字前缀
                        for chinese_num, num_val in CHINESE_NUMBERS.items():
                            if cleaned_no_brackets.startswith(chinese_num):
                                no = num_val
                                break
        
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
        
        # 判断是否为大类：通过序号格式识别
        is_category = is_category_by_serial(no_str)
        
        all_items.append({
            "No": no if no is not None else idx + 1,
            "name": name,
            "isCategory": is_category,
            "staticInvestment": static_investment,
            "dynamicInvestment": dynamic_investment,
        })
    
    # 构建层级结构
    result = []
    current_category = None
    
    for item in all_items:
        if item["isCategory"]:
            # 如果遇到新的大类，先保存之前的大类（如果有）
            if current_category is not None:
                result.append(current_category)
            # 创建新的大类
            current_category = {
                "name": item["name"],
                "Level": 0,
                "staticInvestment": item["staticInvestment"],
                "dynamicInvestment": item["dynamicInvestment"],
                "items": []
            }
        else:
            # 子项，添加到当前大类
            if current_category is not None:
                current_category["items"].append({
                    "No": item["No"],
                    "name": item["name"],
                    "Level": 1,
                    "staticInvestment": item["staticInvestment"],
                    "dynamicInvestment": item["dynamicInvestment"],
                })
            else:
                # 如果没有大类，作为独立项（不应该发生，但容错处理）
                result.append({
                    "name": item["name"],
                    "Level": 1,
                    "staticInvestment": item["staticInvestment"],
                    "dynamicInvestment": item["dynamicInvestment"],
                    "items": []
                })
    
    # 保存最后一个大类
    if current_category is not None:
        result.append(current_category)
    
    return result


def parse_design_review_detail_table(df: pd.DataFrame, table_title: str) -> List[Dict[str, Any]]:
    """
    解析 designReview 类型的概算投资明细表格（规则2）。
    
    表头格式：
    序号 | 工程或费用名称 | 建筑工程费 | 设备购置费 | 安装工程费 | 其他费用 | 合计 | ...
    
    Args:
        df: 表格 DataFrame
        table_title: 表格标题（如"周村 220kV 变电站新建工程总概算表"），用于提取工程名称
    
    返回格式:
    [{
        "No": int,  # 序号
        "Level": int,  # 明细等级
        "name": str,  # 单项工程名称（从标题提取，如"周村220KV变电站新建工程"）
        "projectOrExpenseName": str,  # 工程或费用名称
        "constructionProjectCost": float,  # 建筑工程费（元）
        "equipmentPurchaseCost": float,  # 设备购置费（元）
        "installationProjectCost": float,  # 安装工程费（元）
        "otherExpenses": float,  # 其他费用（元）
    }, ...]
    """
    if df.empty:
        return []
    
    # 从标题中提取工程名称
    # 标题格式如："周村 220kV 变电站新建工程总概算表" -> "周村220kV变电站新建工程"
    project_name = table_title
    if project_name:
        # 移除"总概算表"、"概算表"、"估算表"等后缀
        project_name = re.sub(r'(总概算表|概算表|估算表|汇总表)$', '', project_name)
        # 移除多余空格
        project_name = re.sub(r'\s+', '', project_name)
    
    # 中文数字映射（用于判断层级）
    CHINESE_NUMBERS = {
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
        '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15, '十六': 16, '十七': 17, '十八': 18, '十九': 19, '二十': 20
    }
    
    # 特殊的"其中："项，应作为 Level 1（独立大类）而非子项
    SPECIAL_LEVEL1_ITEMS = [
        "可抵扣固定资产增值税额",
    ]
    
    def determine_level(no_str: str, expense_name: str = "") -> int:
        """
        根据序号格式和费用名称判断层级：
        - 中文数字（一、二、三）：Level 1（大类）
        - 阿拉伯数字（1、2、3）：Level 1（大类）
        - 带括号的数字（(1)、（一））：Level 2（子项）
        - 以"其中："开头的行：Level 2（子项），但特殊项除外
        """
        no_str = str(no_str).strip() if no_str else ""
        expense_name = str(expense_name).strip() if expense_name else ""
        
        # 移除"其中："前缀用于判断
        name_without_prefix = expense_name
        if expense_name.startswith("其中："):
            name_without_prefix = expense_name[3:]
        elif expense_name.startswith("其中:"):
            name_without_prefix = expense_name[3:]
        
        # 检查是否为特殊的 Level 1 项
        for special_item in SPECIAL_LEVEL1_ITEMS:
            if special_item in name_without_prefix:
                return 1
        
        # 以"其中："或"其中:"开头的 -> Level 2（子项）
        if expense_name.startswith("其中：") or expense_name.startswith("其中:"):
            return 2
        
        # 序号为空的情况，默认 Level 1
        if not no_str:
            return 1
        
        # 带括号的 -> Level 2（子项）
        if '（' in no_str or '(' in no_str or '）' in no_str or ')' in no_str:
            return 2
        
        # 中文数字（一、二、三等）-> Level 1（大类）
        cleaned = no_str.replace(' ', '').replace('、', '').replace('.', '').replace('。', '')
        for chinese_num in CHINESE_NUMBERS.keys():
            if cleaned == chinese_num or cleaned.startswith(chinese_num):
                return 1
        
        # 阿拉伯数字（1、2、3等）-> Level 1（大类）
        if re.match(r'^\d+\.?$', cleaned):
            return 1
        
        return 1  # 默认
    
    def parse_number(value: Any) -> float:
        """解析数字"""
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
    
    # 识别表头行（可能有多行表头，需要扫描多行来找到列索引）
    # 先找到包含 "序号" 的行作为起始行
    header_start_idx = None
    for i in range(min(5, len(df))):
        row_text = " ".join(df.iloc[i].astype(str).str.strip().tolist())
        row_text_no_space = row_text.replace(" ", "")
        if "序号" in row_text_no_space:
            header_start_idx = i
            break
    
    if header_start_idx is None:
        header_start_idx = 0
        logger.warning(f"[表格解析] 未找到包含'序号'的表头行，使用第一行作为表头")
    
    # 扫描表头区域（可能是多行表头），收集所有列的关键词
    col_no = None
    col_name = None
    col_construction = None
    col_equipment = None
    col_installation = None
    col_other = None
    
    # 打印前几行表头用于调试
    logger.debug(f"[表格解析] DataFrame 形状: {df.shape}")
    for i in range(min(3, len(df))):
        row_vals = df.iloc[i].astype(str).tolist()
        logger.debug(f"[表格解析] 第{i}行: {row_vals}")
    
    # 扫描前几行表头（多行表头情况）
    header_end_idx = header_start_idx
    for i in range(header_start_idx, min(header_start_idx + 3, len(df))):
        row = df.iloc[i].astype(str).str.strip()
        for idx, cell in enumerate(row):
            # 移除所有空格、换行符等
            cell_no_space = re.sub(r'\s+', '', cell)
            if ("序号" in cell_no_space or cell_no_space == "No") and col_no is None:
                col_no = idx
            elif ("工程或费用名称" in cell_no_space or "费用名称" in cell_no_space) and col_name is None:
                col_name = idx
            # 增强列名匹配 - 使用更宽松的匹配
            elif col_construction is None and any(kw in cell_no_space for kw in ["建筑工程费", "建筑工程", "建筑"]):
                col_construction = idx
            elif col_equipment is None and any(kw in cell_no_space for kw in ["设备购置费", "设备购置", "设备"]):
                col_equipment = idx
            elif col_installation is None and any(kw in cell_no_space for kw in ["安装工程费", "安装工程", "安装"]):
                col_installation = idx
            elif col_other is None and "其他费用" in cell_no_space:
                col_other = idx
        
        # 检查这一行是否像数据行（第一列是数字或中文数字）
        first_cell = row.iloc[0] if len(row) > 0 else ""
        first_cell_clean = re.sub(r'\s+', '', first_cell).replace("、", "")
        chinese_nums = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
        if first_cell_clean and (first_cell_clean.isdigit() or first_cell_clean in chinese_nums):
            # 这一行可能是数据行，表头到此结束
            header_end_idx = i - 1
            break
        header_end_idx = i
    
    # 如果关键列未找到，尝试位置推断
    if col_no is None:
        col_no = 0
    if col_name is None:
        col_name = 1
    
    # 如果费用列未找到，尝试按位置推断
    # 假设顺序：序号(0)、名称(1)、建筑(2)、设备(3)、安装(4)、其他(5)、合计(6)...
    logger.info(f"[表格解析] 列数: {len(df.columns)}, 当前列索引: 建筑={col_construction}, 设备={col_equipment}, 安装={col_installation}, 其他={col_other}")
    
    if col_construction is None or col_equipment is None or col_installation is None or col_other is None:
        num_cols = len(df.columns)
        if num_cols >= 7:
            # 按位置推断
            if col_construction is None:
                col_construction = 2
            if col_equipment is None:
                col_equipment = 3
            if col_installation is None:
                col_installation = 4
            if col_other is None:
                col_other = 5
            logger.info(f"[表格解析] 按位置推断列索引: 建筑={col_construction}, 设备={col_equipment}, 安装={col_installation}, 其他={col_other}")
        else:
            logger.warning(f"[表格解析] 列数不足({num_cols}<7)，无法按位置推断费用列")
    
    logger.info(f"[表格解析] 列索引: 序号={col_no}, 名称={col_name}, 建筑={col_construction}, 设备={col_equipment}, 安装={col_installation}, 其他={col_other}")
    logger.info(f"[表格解析] 表头范围: 行 {header_start_idx} - {header_end_idx}")
    
    # 从数据行开始解析（跳过表头行）
    data_rows = df.iloc[header_end_idx + 1:].reset_index(drop=True)
    
    result = []
    for idx, row in data_rows.iterrows():
        # 跳过空行
        if row.isna().all():
            continue
        
        # 提取各列数据
        no_val = row.iloc[col_no] if col_no is not None and col_no < len(row) else None
        name_val = row.iloc[col_name] if col_name is not None and col_name < len(row) else None
        construction_val = row.iloc[col_construction] if col_construction is not None and col_construction < len(row) else None
        equipment_val = row.iloc[col_equipment] if col_equipment is not None and col_equipment < len(row) else None
        installation_val = row.iloc[col_installation] if col_installation is not None and col_installation < len(row) else None
        other_val = row.iloc[col_other] if col_other is not None and col_other < len(row) else None
        
        # 解析序号
        no = None
        no_str = ""
        if no_val is not None and not pd.isna(no_val):
            no_str = str(no_val).strip()
            if no_str:
                try:
                    no = int(float(no_str))
                except (ValueError, TypeError):
                    # 尝试中文数字
                    cleaned = no_str.replace(' ', '').replace('、', '').replace('.', '').replace('。', '')
                    cleaned_no_brackets = cleaned.replace('（', '').replace('(', '').replace('）', '').replace(')', '')
                    if cleaned_no_brackets in CHINESE_NUMBERS:
                        no = CHINESE_NUMBERS[cleaned_no_brackets]
        
        # 解析工程或费用名称（提前解析，用于判断是否为"其中："行）
        expense_name = str(name_val).strip() if name_val is not None and not pd.isna(name_val) else ""
        
        # 跳过空行
        if not expense_name:
            continue
        
        # 判断是否为"其中："开头的行（这类行序号通常为空，但需要保留）
        is_sub_item = expense_name.startswith("其中：") or expense_name.startswith("其中:")
        
        # 跳过序号为空或无效的行（但"其中："行除外）
        if (not no_str or pd.isna(no_val)) and not is_sub_item:
            continue
        
        # 跳过合计行
        if any(kw in expense_name for kw in ["合计", "总计", "小计"]):
            continue
        
        # 判断层级（传入费用名称用于判断"其中："）
        level = determine_level(no_str, expense_name)
        
        # 去除"其中："前缀
        clean_expense_name = expense_name
        if expense_name.startswith("其中："):
            clean_expense_name = expense_name[3:]
        elif expense_name.startswith("其中:"):
            clean_expense_name = expense_name[3:]
        
        # 解析费用金额
        construction_cost = parse_number(construction_val)
        equipment_cost = parse_number(equipment_val)
        installation_cost = parse_number(installation_val)
        other_cost = parse_number(other_val)
        
        result.append({
            "No": no if no is not None else idx + 1,
            "Level": level,
            "name": project_name,  # 从标题提取的工程名称
            "projectOrExpenseName": clean_expense_name,
            "constructionProjectCost": construction_cost,
            "equipmentPurchaseCost": equipment_cost,
            "installationProjectCost": installation_cost,
            "otherExpenses": other_cost,
        })
    
    logger.info(f"[表格解析] 解析完成: 工程名称={project_name}, 共 {len(result)} 条数据")
    return result


def parse_design_review_cost_table(df: pd.DataFrame, table_title: str) -> List[Dict[str, Any]]:
    """
    解析 designReview 类型的概算投资费用表格（规则3）。
    
    表头格式：
    序号 | 工程或费用名称 | 费用金额 | 各项占静态投资% | 单位投资万元/km
    
    Args:
        df: 表格 DataFrame
        table_title: 表格标题（如"周村 220kV 变电站新建工程总概算表"），用于提取工程名称
    
    返回格式:
    [{
        "No": int,  # 序号
        "Level": int,  # 明细等级
        "name": str,  # 单项工程名称（从标题提取）
        "projectOrExpenseName": str,  # 工程或费用名称
        "cost": float,  # 费用金额（元）
    }, ...]
    """
    if df.empty:
        return []
    
    # 从标题中提取工程名称
    project_name = table_title
    if project_name:
        # 移除"总概算表"、"概算表"、"估算表"等后缀
        project_name = re.sub(r'(总概算表|概算表|估算表|汇总表)$', '', project_name)
        # 移除多余空格
        project_name = re.sub(r'\s+', '', project_name)
    
    # 中文数字映射（用于判断层级）
    CHINESE_NUMBERS = {
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
        '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15, '十六': 16, '十七': 17, '十八': 18, '十九': 19, '二十': 20
    }
    
    # 特殊的"其中："项，应作为 Level 1（独立大类）而非子项
    SPECIAL_LEVEL1_ITEMS = [
        "可抵扣固定资产增值税额",
    ]
    
    def determine_level(no_str: str, expense_name: str = "") -> int:
        """
        根据序号格式和费用名称判断层级：
        - 中文数字（一、二、三）：Level 1（大类）
        - 阿拉伯数字（1、2、3）：Level 1（大类）
        - 带括号的数字（(1)、（一））：Level 2（子项）
        - 以"其中："开头的行：Level 2（子项），但特殊项除外
        """
        no_str = str(no_str).strip() if no_str else ""
        expense_name = str(expense_name).strip() if expense_name else ""
        
        # 移除"其中："前缀用于判断
        name_without_prefix = expense_name
        if expense_name.startswith("其中："):
            name_without_prefix = expense_name[3:]
        elif expense_name.startswith("其中:"):
            name_without_prefix = expense_name[3:]
        
        # 检查是否为特殊的 Level 1 项
        for special_item in SPECIAL_LEVEL1_ITEMS:
            if special_item in name_without_prefix:
                return 1
        
        # 以"其中："或"其中:"开头的 -> Level 2（子项）
        if expense_name.startswith("其中：") or expense_name.startswith("其中:"):
            return 2
        
        # 序号为空的情况，默认 Level 1
        if not no_str:
            return 1
        
        # 带括号的 -> Level 2（子项）
        if '（' in no_str or '(' in no_str or '）' in no_str or ')' in no_str:
            return 2
        
        # 中文数字（一、二、三等）-> Level 1（大类）
        cleaned = no_str.replace(' ', '').replace('、', '').replace('.', '').replace('。', '')
        for chinese_num in CHINESE_NUMBERS.keys():
            if cleaned == chinese_num or cleaned.startswith(chinese_num):
                return 1
        
        # 阿拉伯数字（1、2、3等）-> Level 1（大类）
        if re.match(r'^\d+\.?$', cleaned):
            return 1
        
        return 1
    
    def parse_number(value: Any) -> float:
        """解析数字"""
        if pd.isna(value):
            return 0.0
        value_str = str(value).strip()
        value_str = re.sub(r'[^\d.\-]', '', value_str)
        if not value_str or value_str == '-':
            return 0.0
        try:
            return float(value_str)
        except ValueError:
            return 0.0
    
    # 识别表头行
    header_row_idx = None
    for i in range(min(5, len(df))):
        row_text = " ".join(df.iloc[i].astype(str).str.strip().tolist())
        row_text_no_space = row_text.replace(" ", "")
        if "工程或费用名称" in row_text_no_space and "费用金额" in row_text_no_space:
            header_row_idx = i
            break
        elif "序号" in row_text and "费用金额" in row_text:
            header_row_idx = i
            break
    
    if header_row_idx is None:
        header_row_idx = 0
        logger.warning(f"[表格解析] 未找到明确表头，使用第一行作为表头")
    
    # 从表头行识别列索引
    header_row = df.iloc[header_row_idx].astype(str).str.strip()
    
    col_no = None
    col_name = None
    col_cost = None
    
    for idx, cell in enumerate(header_row):
        cell_no_space = cell.replace(" ", "")
        if "序号" in cell_no_space or cell_no_space == "No":
            col_no = idx
        elif "工程或费用名称" in cell_no_space or "费用名称" in cell_no_space:
            col_name = idx
        elif "费用金额" in cell_no_space:
            col_cost = idx
    
    if col_no is None:
        col_no = 0
    if col_name is None:
        col_name = 1
    if col_cost is None:
        col_cost = 2
    
    logger.info(f"[表格解析] 列索引: 序号={col_no}, 名称={col_name}, 费用金额={col_cost}")
    
    # 从数据行开始解析
    data_rows = df.iloc[header_row_idx + 1:].reset_index(drop=True)
    
    result = []
    for idx, row in data_rows.iterrows():
        if row.isna().all():
            continue
        
        no_val = row.iloc[col_no] if col_no is not None and col_no < len(row) else None
        name_val = row.iloc[col_name] if col_name is not None and col_name < len(row) else None
        cost_val = row.iloc[col_cost] if col_cost is not None and col_cost < len(row) else None
        
        # 解析序号
        no = None
        no_str = ""
        if no_val is not None and not pd.isna(no_val):
            no_str = str(no_val).strip()
            if no_str:
                try:
                    no = int(float(no_str))
                except (ValueError, TypeError):
                    cleaned = no_str.replace(' ', '').replace('、', '').replace('.', '').replace('。', '')
                    cleaned_no_brackets = cleaned.replace('（', '').replace('(', '').replace('）', '').replace(')', '')
                    if cleaned_no_brackets in CHINESE_NUMBERS:
                        no = CHINESE_NUMBERS[cleaned_no_brackets]
        
        # 解析工程或费用名称（提前解析，用于判断是否为"其中："行）
        expense_name = str(name_val).strip() if name_val is not None and not pd.isna(name_val) else ""
        
        if not expense_name:
            continue
        
        # 判断是否为"其中："开头的行（这类行序号通常为空，但需要保留）
        is_sub_item = expense_name.startswith("其中：") or expense_name.startswith("其中:")
        
        # 跳过序号为空或无效的行（但"其中："行除外）
        if (not no_str or pd.isna(no_val)) and not is_sub_item:
            continue
        
        if any(kw in expense_name for kw in ["合计", "总计", "小计"]):
            continue
        
        # 判断层级（传入费用名称用于判断"其中："）
        level = determine_level(no_str, expense_name)
        
        # 去除"其中："前缀
        clean_expense_name = expense_name
        if expense_name.startswith("其中："):
            clean_expense_name = expense_name[3:]
        elif expense_name.startswith("其中:"):
            clean_expense_name = expense_name[3:]
        
        cost = parse_number(cost_val)
        
        result.append({
            "No": no if no is not None else idx + 1,
            "Level": level,
            "name": project_name,
            "projectOrExpenseName": clean_expense_name,
            "cost": cost,
        })
    
    logger.info(f"[表格解析] 解析完成: 工程名称={project_name}, 共 {len(result)} 条数据")
    return result


def _group_items_by_name(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    将平铺的项目列表按 name 字段分组，并按 Level 嵌套：
    - Level 1 的项作为大类
    - Level 2 的项作为大类的子项（放入 items 中）
    
    输入:
    [
        {"No": "一", "Level": 1, "name": "工程A", "projectOrExpenseName": "主辅生产工程", ...},
        {"No": "(一)", "Level": 2, "name": "工程A", "projectOrExpenseName": "主要生产工程", ...},
        {"No": "(二)", "Level": 2, "name": "工程A", "projectOrExpenseName": "辅助生产工程", ...},
        {"No": "二", "Level": 1, "name": "工程A", "projectOrExpenseName": "其他费用", ...},
        {"No": "", "Level": 2, "name": "工程A", "projectOrExpenseName": "其中：建设场地征用", ...},
    ]
    
    输出:
    [
        {
            "name": "工程A",
            "items": [
                {
                    "No": "一", "Level": 1, "projectOrExpenseName": "主辅生产工程", ...,
                    "items": [
                        {"No": "(一)", "Level": 2, "projectOrExpenseName": "主要生产工程", ...},
                        {"No": "(二)", "Level": 2, "projectOrExpenseName": "辅助生产工程", ...},
                    ]
                },
                {
                    "No": "二", "Level": 1, "projectOrExpenseName": "其他费用", ...,
                    "items": [
                        {"No": "", "Level": 2, "projectOrExpenseName": "其中：建设场地征用", ...},
                    ]
                }
            ]
        }
    ]
    """
    if not items:
        return []
    
    from collections import OrderedDict
    
    # 第一步：按工程名称（name）分组
    grouped_by_name: OrderedDict[str, List[Dict[str, Any]]] = OrderedDict()
    
    for item in items:
        name = item.get("name", "未知工程")
        if name not in grouped_by_name:
            grouped_by_name[name] = []
        # 复制 item 并移除 name 字段
        item_copy = {k: v for k, v in item.items() if k != "name"}
        grouped_by_name[name].append(item_copy)
    
    # 第二步：在每个工程组内，按 Level 建立父子关系
    result = []
    for name, group_items in grouped_by_name.items():
        nested_items = []
        current_parent = None
        
        for item in group_items:
            level = item.get("Level", 1)
            
            if level == 1:
                # Level 1 是大类，创建新的父项
                item_with_children = dict(item)
                item_with_children["items"] = []
                nested_items.append(item_with_children)
                current_parent = item_with_children
            elif level == 2:
                # Level 2 是子项，放入当前父项的 items 中
                if current_parent is not None:
                    # 移除 Level 字段（子项统一在父项下，不需要重复标识）
                    child_item = {k: v for k, v in item.items()}
                    current_parent["items"].append(child_item)
                else:
                    # 没有父项，作为独立项处理
                    nested_items.append(item)
            else:
                # 其他 Level，作为独立项
                nested_items.append(item)
        
        result.append({
            "name": name,
            "items": nested_items
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
            logger.info(f"[表格解析] 开始解析表格: {rule_name} (页面 {page}, 行数: {len(df)})")
            if rule_name == "审定结算汇总表":
                parsed_data = parse_settlement_summary_table(df)
                if parsed_data:
                    result[rule_name] = parsed_data
                    logger.info(f"[表格解析] {rule_name}: 解析成功，共 {len(parsed_data)} 条数据")
            elif rule_name == "合同执行情况":
                parsed_data = parse_contract_execution_table(df)
                if parsed_data:
                    result[rule_name] = parsed_data
                    logger.info(f"[表格解析] {rule_name}: 解析成功，共 {len(parsed_data)} 条数据")
            elif rule_name == "赔偿合同":
                parsed_data = parse_compensation_contract_table(df)
                if parsed_data:
                    result[rule_name] = parsed_data
                    logger.info(f"[表格解析] {rule_name}: 解析成功，共 {len(parsed_data)} 条数据")
            elif rule_name == "物资采购合同1":
                parsed_data = parse_material_purchase_contract1_table(df)
                if parsed_data:
                    result[rule_name] = parsed_data
                    logger.info(f"[表格解析] {rule_name}: 解析成功，共 {len(parsed_data)} 条数据")
            elif rule_name == "物资采购合同2":
                parsed_data = parse_material_purchase_contract2_table(df)
                if parsed_data:
                    result[rule_name] = parsed_data
                    logger.info(f"[表格解析] {rule_name}: 解析成功，共 {len(parsed_data)} 条数据")
            elif rule_name == "其他服务类合同":
                parsed_data = parse_other_service_contract_table(df)
                if parsed_data:
                    result[rule_name] = parsed_data
                    logger.info(f"[表格解析] {rule_name}: 解析成功，共 {len(parsed_data)} 条数据")
            else:
                logger.warning(f"[表格解析] 未知的表格类型: {rule_name}")
        except Exception as e:
            # 如果解析失败，记录错误但不影响其他表格
            logger.warning(f"[表格解析] 解析 {rule_name} 表格失败: {e}", exc_info=True)
    
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

    # 立即输出日志，确保日志系统正常工作
    logger.info(f"[表格提取] ========== 开始处理 PDF ==========")
    logger.info(f"[表格提取] PDF 路径: {pdf_path}")
    logger.info(f"[表格提取] 文档类型: {doc_type}")
    logger.info(f"[表格提取] PDF 文件存在: {Path(pdf_path).exists()}")
    if Path(pdf_path).exists():
        logger.info(f"[表格提取] PDF 文件大小: {Path(pdf_path).stat().st_size} bytes")
    logger.info(f"[表格提取] 输出目录: {base_output_dir}")

    # 1. 使用 pdfplumber 从 PDF 提取所有表格（不限制页数）
    # 对于 designReview 类型，启用标题提取（用于识别多个概算表）
    extract_titles = (doc_type == "designReview")
    logger.info("[表格提取] 步骤1: 使用 pdfplumber 提取所有表格...")
    tables_data = extract_tables_with_pdfplumber(str(pdf_path_obj), pages="all", extract_titles=extract_titles)
    logger.info(f"[表格提取] 步骤1完成: 共提取到 {len(tables_data)} 个表格")

    # 2. 保存所有原始表格为 xlsx，命名: table_page{page}_{index}.xlsx
    logger.info("[表格提取] 步骤2: 保存所有原始表格到 extracted_tables...")
    page_table_count: Dict[int, int] = {}
    all_tables_meta: List[Dict[str, Any]] = []

    # 存储表格标题映射（用于后续解析）
    table_titles: Dict[int, str] = {}  # orig_idx -> title

    # 给每个表格一个全局索引，方便后续合并/去重
    all_tables: List[Tuple[int, pd.DataFrame, int]] = []  # (orig_idx, df, page)
    for orig_idx, (page, df, _bbox, title) in enumerate(tables_data):
        # 保存标题映射
        if title:
            table_titles[orig_idx] = title
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
    # 增加 title 字段: (orig_idx, df, rule_name, page, title)
    matched_for_merge: List[Tuple[int, pd.DataFrame, str, int, str]] = []
    for merged_idx, (orig_idx, df, page) in enumerate(merged_all_tables):
        rule_name: Optional[str] = None
        for rule in header_rules:
            is_match, rn = check_table_header(df, rule)
            if is_match:
                rule_name = rn
                # 获取表格标题
                title = table_titles.get(orig_idx, "")
                logger.info(f"[表格提取] 表格 {merged_idx + 1} (页面 {page}) 匹配规则: {rule_name}, 标题: {title}")
                break
        if rule_name:
            title = table_titles.get(orig_idx, "")
            matched_for_merge.append((orig_idx, df.copy(), rule_name, page, title))
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
    for orig_idx, df, rule_name, page, title in merged_tables:
        filtered_page_table_count[page] = filtered_page_table_count.get(page, 0) + 1
        idx_on_page = filtered_page_table_count[page]

        excel_path = filtered_dir / f"table_page{page}_{idx_on_page}.xlsx"
        df.to_excel(str(excel_path), index=False, header=False)

        filtered_meta.append(
            {
                "page": page,
                "index_on_page": idx_on_page,
                "rule_name": rule_name,
                "title": title,
                "excel_path": str(excel_path),
            }
        )
    logger.info(f"[表格提取] 步骤7完成: 已保存 {len(filtered_meta)} 个筛选后的表格")
    
    # 8. 根据文档类型解析表格数据
    logger.info(f"[表格提取] 步骤8: 解析表格数据，文档类型: {doc_type}...")
    logger.info(f"[表格提取] 待解析的表格列表: {[(rule_name, page, title) for _, _, rule_name, page, title in merged_tables]}")
    if doc_type == "designReview":
        # 对于 designReview 类型，返回类似 settlementReport 的结构
        # 按规则类型分组：
        # - 初设评审的概算投资（规则1）: 嵌套结构
        # - 初设评审的概算投资明细（规则2）: 平铺结构，多个表格
        # - 初设评审的概算投资费用（规则3）: 平铺结构，多个表格
        parsed_data = {
            "初设评审的概算投资": [],
            "初设评审的概算投资明细": [],
            "初设评审的概算投资费用": [],
        }
        
        for orig_idx, df, rule_name, page, title in merged_tables:
            if rule_name == "初设评审的概算投资":
                # 规则1：嵌套结构
                try:
                    logger.info(f"[表格提取] 解析 designReview 表格(规则1): {rule_name} (页面 {page}, 行数: {len(df)})")
                    summary_data = parse_design_review_table(df)
                    if summary_data:
                        parsed_data["初设评审的概算投资"] = summary_data
                        logger.info(f"[表格提取] 解析完成: 共 {len(summary_data)} 条数据")
                except Exception as e:
                    logger.warning(f"[表格提取] 解析 designReview 表格(规则1)失败: {e}", exc_info=True)
            elif rule_name == "初设评审的概算投资明细":
                # 规则2：使用标题作为工程名称
                try:
                    logger.info(f"[表格提取] 解析 designReview 表格(规则2): {rule_name} (页面 {page}, 标题: {title}, 行数: {len(df)})")
                    detail_data = parse_design_review_detail_table(df, title)
                    if detail_data:
                        parsed_data["初设评审的概算投资明细"].extend(detail_data)
                        logger.info(f"[表格提取] 解析完成: 共 {len(detail_data)} 条数据")
                except Exception as e:
                    logger.warning(f"[表格提取] 解析 designReview 表格(规则2)失败: {e}", exc_info=True)
            elif rule_name == "初设评审的概算投资费用":
                # 规则3：使用标题作为工程名称
                try:
                    logger.info(f"[表格提取] 解析 designReview 表格(规则3): {rule_name} (页面 {page}, 标题: {title}, 行数: {len(df)})")
                    cost_data = parse_design_review_cost_table(df, title)
                    if cost_data:
                        parsed_data["初设评审的概算投资费用"].extend(cost_data)
                        logger.info(f"[表格提取] 解析完成: 共 {len(cost_data)} 条数据")
                except Exception as e:
                    logger.warning(f"[表格提取] 解析 designReview 表格(规则3)失败: {e}", exc_info=True)
        
        # 将规则2和规则3的平铺结果按工程名称分组为嵌套结构
        for rule_key in ["初设评审的概算投资明细", "初设评审的概算投资费用"]:
            if rule_key in parsed_data and parsed_data[rule_key]:
                flat_items = parsed_data[rule_key]
                grouped = _group_items_by_name(flat_items)
                parsed_data[rule_key] = grouped
        
        # 统计解析结果
        logger.info(f"[表格提取] 解析结果统计:")
        total_records = 0
        for table_type, table_data in parsed_data.items():
            if table_data:
                if isinstance(table_data, list):
                    # 嵌套结构，统计所有 items
                    record_count = sum(len(item.get("items", [])) for item in table_data) if table_data and isinstance(table_data[0], dict) and "items" in table_data[0] else len(table_data)
                else:
                    record_count = len(table_data)
                total_records += record_count
                logger.info(f"[表格提取]   - {table_type}: {len(table_data)} 个工程，共 {record_count} 条明细")
            else:
                logger.info(f"[表格提取]   - {table_type}: 未匹配到数据")
        logger.info(f"[表格提取] 总计: {total_records} 条数据")
            
    elif doc_type == "settlementReport":
        # 对于 settlementReport 类型，解析所有匹配的表格，按表名组织
        try:
            logger.info(f"[表格提取] 解析 settlementReport 表格，共 {len(merged_tables)} 个表格")
            # 转换为4元组格式以兼容现有的 parse_settlement_report_tables 函数
            tables_4tuple = [(orig_idx, df, rule_name, page) for orig_idx, df, rule_name, page, title in merged_tables]
            parsed_data = parse_settlement_report_tables(tables_4tuple)
            # 统计每个表的解析结果
            logger.info(f"[表格提取] 解析结果统计:")
            total_records = 0
            for table_name, table_data in parsed_data.items():
                if table_data:
                    record_count = len(table_data)
                    total_records += record_count
                    logger.info(f"[表格提取]   - {table_name}: {record_count} 条数据")
                else:
                    logger.info(f"[表格提取]   - {table_name}: 未匹配到数据")
            logger.info(f"[表格提取] 总计: {total_records} 条数据")
        except Exception as e:
            logger.warning(f"[表格提取] 解析 settlementReport 表格失败: {e}", exc_info=True)
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


