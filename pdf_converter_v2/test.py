from pathlib import Path
import pandas as pd
from tqdm import tqdm
import time
import re
from typing import List, Optional, Tuple
import subprocess
import os

# 导入 pdfplumber 用于提取表格
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    print("⚠ pdfplumber 未安装，无法提取表格")
    print("  安装命令: pip install pdfplumber")

# 导入 PyMuPDF 用于提取文本
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    print("⚠ PyMuPDF 未安装，无法提取表格前的文本")
    print("  安装命令: pip install PyMuPDF")

# ==================== 配置区域 ====================
pdf_path = '/home/hws/workspace/GitLab/Clerk2.5/pdf_converter_v2/2-数据源/5-（初设批复）晋电建设〔2019〕566号　国网山西省电力公司关于晋城周村220kV输变电工程初步设计的批复 .ceb'
output_dir = Path('extracted_tables')  # 原始表格输出目录（包含表格前文本）
merged_output_dir = Path('merged_tables')  # 合并后的表格输出目录（已剔除表格前文本）
filtered_output_dir = Path('filtered_tables')  # 筛选后的表格输出目录

# CEB 转 PDF 配置
AUTO_CONVERT_CEB = True  # 是否自动尝试转换 CEB 文件
CEB_CONVERTED_DIR = Path('converted_pdfs')  # CEB 转换后的 PDF 存放目录

# 表头规则配置：根据PDF文件名匹配对应的表头规则（固定匹配模式）
# 每个规则可以包含多个表头定义，表头必须包含所有关键词才匹配
TABLE_HEADER_RULES = {
    # 规则1: 结算报告类
    "9-（结算报告）山西晋城周村220kV输变电工程结算审计报告.pdf": [
        {
            "name": "审定结算汇总表",
            "keywords": ["序号", "审计内容", "送审金额（含税）", "审定金额（含税）", "审定金额（不含税）", "增减金额", "备注"],
            "match_mode": "all"  # 表头必须包含所有关键词才匹配（固定匹配）
        },
        {
            "name": "合同执行情况",
            "keywords": ["施工单位", "中标通知书金额", "中标通知书编号", "合同金额", "结算送审金额", "差额"],
            "match_mode": "all"  # 表头必须包含所有关键词才匹配（固定匹配）
        },
        {
            "name": "赔偿合同",
            "keywords": ["合同对方", "赔偿事项", "合同金额", "结算送审金额", "差额"],
            "match_mode": "all"  # 表头必须包含所有关键词才匹配（固定匹配）
        },
        {
            "name": "物资采购合同1",
            "keywords": ["物料名称", "合同数量", "施工图数量", "单价（不含税）", "差额"],
            "match_mode": "all"  # 表头必须包含所有关键词才匹配（固定匹配）
        },
        {
            "name": "物资采购合同2",
            "keywords": ["物料名称", "合同金额（不含税）", "入账金额", "差额", "备注"],
            "match_mode": "all"  # 表头必须包含所有关键词才匹配（固定匹配）
        },
        {
            "name": "其他服务类合同",
            "keywords": ["服务商", "中标通知书", "合同金额", "送审金额", "结算金额"],
            "match_mode": "all"  # 表头必须包含所有关键词才匹配（固定匹配）
        }
    ],
    "4-（初设评审）中电联电力建设技术经济咨询中心技经〔2019〕201号关于山西周村220kV输变电工程初步设计的评审意见.pdf":[
              {
            "name": "初设评审的概算投资",
            "keywords": ["序号", "工程名称", "建设规模", "静态投资", "其中：建设场地征用及清理费", "动态投资"],
            "match_mode": "all"  # 表头必须包含所有关键词才匹配（固定匹配）
        },
    ]
    # 可以添加更多文件的规则
    # "其他文件名.pdf": [
    #     {Ctrl+Shift+P
    #         "name": "表头名称",
    #         "keywords": ["关键词1", "关键词2"],
    #         "match_mode": "all"  # "all" 表示必须包含所有关键词（固定匹配）
    #     }
    # ]
}

# 是否启用表头过滤（如果为False，则提取所有表格）
ENABLE_HEADER_FILTER = True

# 要排除的规则名称列表（如果某个规则匹配了不该匹配的表格，可以在这里排除）
# 例如: EXCLUDE_RULES = ["物资采购合同2"] 将不会匹配该规则
EXCLUDE_RULES = []

# 是否启用表格内多表头检测和分割（如果一个表格中包含多个表头，自动分割）
# 已禁用此功能，改用基于文本的合并策略
# ENABLE_SPLIT_MULTI_HEADER_TABLES = True

# 是否提取表格前的文本（用于更好地识别表格类型）
EXTRACT_TEXT_BEFORE_TABLE = True

# 提取表格前多少行文本（用于识别表格标题和上下文）
TEXT_LINES_BEFORE_TABLE = 5

# 是否显示所有表格的表头预览（用于帮助确定过滤条件）
SHOW_HEADER_PREVIEW = True

# 是否显示匹配的规则名称
SHOW_MATCHED_RULE_NAME = True

# 是否启用跨页表格合并（基于表格前文本判断）
ENABLE_MERGE_CROSS_PAGE_TABLES = True

# 跨页表格检测的页面范围（检查前后几页）
CROSS_PAGE_SEARCH_RANGE = 10  # 增加范围以支持长表格

# 是否从已生成的xlsx文件中过滤（而不是从PDF提取）
FILTER_FROM_EXISTING_XLSX = True  # 设置为True
XLSX_INPUT_DIR = 'extracted_tables'  # 初始读取目录（会在流程中更新为 merged_tables）
# ==================================================

def check_table_header(table_df: pd.DataFrame, rule: dict) -> Tuple[bool, str]:
    """
    检查表格是否匹配指定的表头规则（固定匹配：必须包含所有关键词）
    支持处理表头换行的情况（合并前几行作为表头）
    
    Args:
        table_df: 表格DataFrame
        rule: 表头规则字典，包含 name, keywords, match_mode
    
    Returns:
        tuple: (是否匹配, 规则名称)
    """
    if table_df.empty:
        return False, ""
    
    rule_name = rule.get("name", "未知规则")
    
    # 检查是否在排除列表中
    if rule_name in EXCLUDE_RULES:
        return False, ""
    
    # 检查第一行是否是文本信息（以 "[表格前文本]" 开头）
    start_row = 0
    if len(table_df) > 0:
        first_cell = str(table_df.iloc[0, 0]).strip()
        if first_cell.startswith("[表格前文本]"):
            start_row = 1  # 跳过第一行
    
    # 处理表头换行：合并前几行作为完整表头（通常表头可能占1-3行）
    # 检查前3行，合并所有非空单元格内容
    header_rows_to_check = min(3, len(table_df) - start_row)
    header_text_parts = []
    
    for row_idx in range(start_row, start_row + header_rows_to_check):
        if row_idx >= len(table_df):
            break
        row = table_df.iloc[row_idx].astype(str).str.strip()
        # 收集该行的所有非空单元格内容
        for cell in row:
            cell_text = str(cell).strip()
            # 过滤掉空值、NaN等
            if cell_text and cell_text.lower() not in ['nan', 'none', '']:
                # 将单元格内的换行符替换为空格（处理xlsx中的换行）
                cell_text = cell_text.replace('\n', ' ').replace('\r', ' ')
                header_text_parts.append(cell_text)
    
    # 合并所有表头文本（去除换行符和多余空格）
    header_text = " ".join(header_text_parts)
    # 进一步清理：将多个连续空格替换为单个空格（包括换行符转换后的空格）
    header_text = re.sub(r'\s+', ' ', header_text).strip()
    # 创建一个无空格的版本用于匹配（处理换行导致的空格问题）
    header_text_no_space = re.sub(r'\s+', '', header_text)
    
    keywords = rule.get("keywords", [])
    match_mode = rule.get("match_mode", "all")  # 默认使用 "all"（固定匹配）
    
    if not keywords:
        return False, ""
    
    # 固定匹配：必须包含所有关键词
    # 匹配时同时检查原文本和无空格版本，以处理换行导致的空格问题
    if match_mode == "all":
        all_match = True
        for keyword in keywords:
            # 同时检查原文本和无空格版本
            keyword_no_space = re.sub(r'\s+', '', keyword)
            if keyword in header_text or keyword_no_space in header_text_no_space:
                continue
            else:
                all_match = False
                break
        if all_match:
            return True, rule_name
    elif match_mode == "any":
        # 保留此选项，但不推荐使用（模糊匹配）
        for keyword in keywords:
            keyword_no_space = re.sub(r'\s+', '', keyword)
            if keyword in header_text or keyword_no_space in header_text_no_space:
                return True, rule_name
    
    return False, ""

def has_table_header(table_df: pd.DataFrame, header_rules: List[dict]) -> Tuple[bool, str]:
    """
    检查表格是否有表头（匹配任何一个规则）
    
    Args:
        table_df: 表格DataFrame
        header_rules: 表头规则列表
    
    Returns:
        tuple: (是否有表头, 匹配的规则名称)
    """
    for rule in header_rules:
        is_match, rule_name = check_table_header(table_df, rule)
        if is_match:
            return True, rule_name
    return False, ""

def has_text_before_table(table_df: pd.DataFrame) -> Tuple[bool, str]:
    """
    检查表格是否有前文本（判断是否是新表格的开始）
    
    Args:
        table_df: 表格DataFrame
    
    Returns:
        tuple: (是否有前文本, 前文本内容)
    """
    if table_df.empty or len(table_df) == 0:
        return False, ""
    
    first_cell = str(table_df.iloc[0, 0]).strip()
    if first_cell.startswith("[表格前文本]"):
        # 提取文本内容（去掉标记）
        text_content = first_cell.replace("[表格前文本]", "").strip()
        return True, text_content
    
    return False, ""

def remove_text_row(table_df: pd.DataFrame) -> pd.DataFrame:
    """
    移除表格第一行的文本信息（如果存在）
    
    Args:
        table_df: 表格DataFrame
    
    Returns:
        pd.DataFrame: 移除文本行后的表格
    """
    has_text, _ = has_text_before_table(table_df)
    if has_text:
        return table_df.iloc[1:].reset_index(drop=True)
    return table_df

def convert_ceb_to_pdf(ceb_path: str) -> Optional[str]:
    """
    尝试将 CEB 文件转换为 PDF
    
    CEB 是中国电子公文格式，需要专门的工具转换。
    此函数会检查是否已有转换后的 PDF，如果没有则提示用户手动转换。
    
    Args:
        ceb_path: CEB 文件路径
    
    Returns:
        str: 转换后的 PDF 文件路径，如果转换失败返回 None
    """
    ceb_path = Path(ceb_path)
    
    if not ceb_path.exists():
        print(f"⚠ CEB 文件不存在: {ceb_path}")
        return None
    
    # 创建转换目录
    converted_dir = CEB_CONVERTED_DIR
    converted_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成 PDF 文件名
    pdf_filename = ceb_path.stem + '.pdf'
    pdf_path = converted_dir / pdf_filename
    
    # 如果已经转换过，直接返回
    if pdf_path.exists():
        print(f"✓ 发现已转换的 PDF: {pdf_path}")
        return str(pdf_path)
    
    print(f"\n检测到 CEB 文件: {ceb_path.name}")
    print("=" * 60)
    print("CEB 是中国电子公文格式，需要手动转换为 PDF")
    print("=" * 60)
    print("\n推荐转换方法:")
    print("1. 使用方正 Apabi Reader (官方工具)")
    print("   - 下载: http://www.apabi.com/")
    print("   - 打开 CEB 文件后，选择 '文件' -> '另存为' -> 'PDF'")
    print("\n2. 使用在线转换工具")
    print("   - https://convertio.co/zh/ceb-pdf/")
    print("   - https://www.aconvert.com/cn/document/ceb-to-pdf/")
    print("\n3. 使用 CEB 阅读器导出")
    print("   - 安装任意支持 CEB 格式的阅读器")
    print("   - 打开文件后导出为 PDF")
    print("\n" + "=" * 60)
    print(f"请将转换后的 PDF 文件放到: {converted_dir.absolute()}")
    print(f"文件名: {pdf_filename}")
    print("=" * 60)
    
    return None

def check_and_convert_file(file_path: str) -> str:
    """
    检查文件类型，如果是 CEB 则尝试转换为 PDF
    
    Args:
        file_path: 文件路径
    
    Returns:
        str: PDF 文件路径
    """
    file_path = Path(file_path)
    
    # 检查文件扩展名
    if file_path.suffix.lower() == '.ceb':
        if AUTO_CONVERT_CEB:
            pdf_path = convert_ceb_to_pdf(str(file_path))
            if pdf_path:
                return pdf_path
            else:
                print("\n请手动转换 CEB 文件后重新运行脚本")
                exit(1)
        else:
            print(f"⚠ 检测到 CEB 文件，但自动转换已禁用: {file_path}")
            print("  请设置 AUTO_CONVERT_CEB = True 或手动转换为 PDF")
            exit(1)
    
    return str(file_path)

def clean_newlines(table_df: pd.DataFrame) -> pd.DataFrame:
    """
    清理单元格内的换行符
    
    Args:
        table_df: 表格DataFrame
    
    Returns:
        pd.DataFrame: 清理后的表格
    """
    if table_df.empty:
        return table_df
    
    df = table_df.copy()
    
    # 先转换为 object 类型避免 dtype 警告
    df = df.astype(object)
    
    # 遍历所有单元格，移除换行符
    for i in range(len(df)):
        for j in range(len(df.columns)):
            cell_val = df.iloc[i, j]
            if cell_val is not None and not pd.isna(cell_val):
                # 移除换行符
                df.iloc[i, j] = str(cell_val).replace('\n', '').replace('\r', '')
    
    return df

def merge_broken_rows(table_df: pd.DataFrame, header_rows: int = 1, debug: bool = False) -> pd.DataFrame:
    """
    合并被截断的行（跨页时一行被分成多行）
    
    检测规则：如果某一行前N列有内容，但后面的列大部分是空的（超过50%），
    则认为是上一行的延续，合并到上一行对应的列
    
    Args:
        table_df: 表格DataFrame
        header_rows: 表头行数，跳过表头不处理
        debug: 是否输出调试信息
    
    Returns:
        pd.DataFrame: 合并后的表格
    """
    if table_df.empty or len(table_df) <= header_rows:
        return table_df
    
    df = table_df.copy()
    rows_to_remove = []
    
    if debug:
        print(f"    [DEBUG] merge_broken_rows: 检查 {len(df)} 行，跳过前 {header_rows} 行表头")
    
    # 从表头后开始检查
    for i in range(header_rows, len(df)):
        # 统计有内容的列和空列
        non_empty_cols = []
        empty_cols = []
        
        for j in range(len(df.columns)):
            val = df.iloc[i, j]
            val_str = str(val).strip()
            is_empty = val is None or pd.isna(val) or not val_str or val_str.lower() in ['nan', 'none', '']
            
            if is_empty:
                empty_cols.append(j)
            else:
                non_empty_cols.append(j)
        
        # 如果没有非空列，跳过
        if not non_empty_cols:
            continue
        
        # 计算空列比例
        empty_ratio = len(empty_cols) / len(df.columns)
        
        if debug:
            print(f"    [DEBUG] 行 {i}: 非空列={non_empty_cols}, 空列比例={empty_ratio:.2f}")
        
        # 如果空列超过50%，且不是第一行数据，认为是被截断的行
        if empty_ratio > 0.5 and i > header_rows:
            # 检查上一行对应位置是否有内容
            can_merge = True
            for col_idx in non_empty_cols:
                prev_val = df.iloc[i-1, col_idx]
                if prev_val is None or pd.isna(prev_val) or str(prev_val).strip() == '':
                    can_merge = False
                    break
            
            if can_merge:
                if debug:
                    print(f"    [DEBUG]   ✓ 合并行 {i} 到行 {i-1}")
                
                # 合并每个非空列到上一行对应的列
                for col_idx in non_empty_cols:
                    prev_val = df.iloc[i-1, col_idx]
                    curr_val = df.iloc[i, col_idx]
                    df.iloc[i-1, col_idx] = str(prev_val) + str(curr_val)
                    if debug:
                        print(f"    [DEBUG]     列 {col_idx}: '{prev_val}' + '{curr_val}'")
                
                rows_to_remove.append(i)
            else:
                if debug:
                    print(f"    [DEBUG]   ✗ 上一行对应列为空，跳过合并")
        else:
            if debug and empty_ratio > 0:
                print(f"    [DEBUG]   ✗ 空列比例不足50%或是第一行数据，跳过")
    
    # 删除已合并的行
    if rows_to_remove:
        df = df.drop(rows_to_remove).reset_index(drop=True)
        if debug:
            print(f"    ✓ 合并了 {len(rows_to_remove)} 个被截断的行")
    else:
        if debug:
            print(f"    ℹ 没有发现需要合并的被截断行")
    
    return df

def fix_broken_cells(table_df: pd.DataFrame, header_row_count: int = 1) -> pd.DataFrame:
    """
    修复被错误分割的单元格（一个单元格的内容被识别成多行）
    
    检测规则：
    1. 如果某一行的第一列有内容，但其他列全部为空
    2. 则认为当前行是上一行第一列内容的延续，需要合并
    
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
        # 获取当前行
        current_row = df.iloc[i]
        
        # 检查第一列是否有内容
        first_col = str(current_row.iloc[0]).strip()
        if not first_col or first_col.lower() in ['nan', 'none', '']:
            continue
        
        # 检查其他列是否全部为空
        other_cols = current_row.iloc[1:]
        all_empty = all(str(val).strip() in ['', 'nan', 'None', 'NaN'] for val in other_cols)
        
        if all_empty and i > header_row_count:
            # 其他列全部为空，合并到上一行的第一列
            prev_first_col = str(df.iloc[i-1, 0]).strip()
            if prev_first_col and prev_first_col.lower() not in ['nan', 'none', '']:
                # 合并到上一行的第一列（移除换行符）
                df.iloc[i-1, 0] = prev_first_col + first_col.replace('\n', '').replace('\r', '')
                rows_to_remove.append(i)
    
    # 删除已合并的行
    if rows_to_remove:
        df = df.drop(rows_to_remove).reset_index(drop=True)
        print(f"    修复了 {len(rows_to_remove)} 个被错误分割的单元格（跨行）")
    
    return df

def fix_split_cells_across_columns(table_df: pd.DataFrame, header_row_count: int = 1) -> pd.DataFrame:
    """
    修复被错误分割到多列的单元格
    
    例如："3" 和 "工程物资" 被分成两列，应该合并为 "3 工程物资"
    
    检测规则：
    1. 如果某一行的前两列都有内容，但第一列内容很短（1-2个字符）
    2. 且第二列看起来像是第一列的延续（都是文字）
    3. 则合并这两列
    
    Args:
        table_df: 表格DataFrame
        header_row_count: 表头行数，跳过表头不处理
    
    Returns:
        pd.DataFrame: 修复后的表格
    """
    if table_df.empty or len(table_df) <= header_row_count or len(table_df.columns) < 2:
        return table_df
    
    df = table_df.copy()
    merge_count = 0
    
    # 从表头后开始检查
    for i in range(header_row_count, len(df)):
        first_col = str(df.iloc[i, 0]).strip()
        second_col = str(df.iloc[i, 1]).strip()
        
        # 检查第一列和第二列是否都有内容
        if (first_col and first_col.lower() not in ['nan', 'none', ''] and
            second_col and second_col.lower() not in ['nan', 'none', '']):
            
            # 检查第一列是否很短（1-3个字符，通常是序号或简短文字）
            # 且第三列及之后的列是否有数据（说明这不是正常的多列数据）
            if len(first_col) <= 3:
                # 检查第三列及之后是否有数据
                has_data_after = False
                if len(df.columns) > 2:
                    for col_idx in range(2, len(df.columns)):
                        val = str(df.iloc[i, col_idx]).strip()
                        if val and val.lower() not in ['nan', 'none', '']:
                            has_data_after = True
                            break
                
                # 如果第三列及之后有数据，说明这可能是被错误分割的
                # 或者如果第一列是纯数字（序号），也可能需要合并
                if has_data_after or first_col.isdigit():
                    # 合并第一列和第二列
                    df.iloc[i, 1] = first_col + ' ' + second_col
                    df.iloc[i, 0] = ''
                    merge_count += 1
    
    if merge_count > 0:
        print(f"    修复了 {merge_count} 个被错误分割的单元格（跨列）")
    
    return df

def remove_empty_columns(table_df: pd.DataFrame, header_row_count: int = 1, empty_threshold: float = 0.8) -> pd.DataFrame:
    """
    移除空列（整列都是空值或大部分为空）
    
    Args:
        table_df: 表格DataFrame
        header_row_count: 表头行数
        empty_threshold: 空值比例阈值（超过此比例认为是空列）
    
    Returns:
        pd.DataFrame: 移除空列后的表格
    """
    if table_df.empty:
        return table_df
    
    df = table_df.copy()
    cols_to_remove = []
    
    # 检查每一列
    for col_idx in range(len(df.columns)):
        # 获取该列的所有值（包括表头）
        col_values = df.iloc[:, col_idx]
        
        # 计算空值比例（检查整列）
        empty_count = sum(1 for val in col_values if str(val).strip() in ['', 'nan', 'None', 'NaN'])
        empty_ratio = empty_count / len(col_values) if len(col_values) > 0 else 1.0
        
        # 如果空值比例超过阈值，标记为待删除
        if empty_ratio >= empty_threshold:
            cols_to_remove.append(col_idx)
    
    # 删除空列
    if cols_to_remove:
        df = df.drop(df.columns[cols_to_remove], axis=1)
        df.columns = range(len(df.columns))  # 重置列索引
        print(f"    移除了 {len(cols_to_remove)} 个空列")
    
    return df

def clean_cell_text(table_df: pd.DataFrame) -> pd.DataFrame:
    """
    清理单元格内的文本（移除换行符等）
    
    Args:
        table_df: 表格DataFrame
    
    Returns:
        pd.DataFrame: 清理后的表格
    """
    if table_df.empty:
        return table_df
    
    df = table_df.copy()
    
    # 先将整个 DataFrame 转换为 object 类型（字符串类型），避免 dtype 警告
    df = df.astype(object)
    
    # 遍历所有单元格，移除换行符
    for i in range(len(df)):
        for j in range(len(df.columns)):
            cell_val = str(df.iloc[i, j])
            if cell_val and cell_val.lower() not in ['nan', 'none', '']:
                # 移除换行符，用空字符串替换
                cleaned_val = cell_val.replace('\n', '').replace('\r', '')
                df.iloc[i, j] = cleaned_val
    
    return df

def fix_merged_header_cells(table_df: pd.DataFrame, expected_keywords: list = None) -> pd.DataFrame:
    """
    修复表头中被错误合并的单元格
    
    例如："施工图数量 单价（不含税）" 应该分成两列："施工图数量" 和 "单价（不含税）"
    
    注意：这个函数会增加列数，但不会自动调整数据行。
    建议在调用此函数前先移除空列。
    
    Args:
        table_df: 表格DataFrame
        expected_keywords: 期望的关键词列表，用于检测是否需要分割
    
    Returns:
        pd.DataFrame: 修复后的表格
    """
    if table_df.empty or len(table_df) == 0:
        return table_df
    
    df = table_df.copy()
    
    # 检查第一行（表头）是否有需要分割的单元格
    header_row = df.iloc[0]
    cols_to_split = []
    
    for col_idx in range(len(header_row)):
        cell_val = str(header_row.iloc[col_idx]).strip()
        
        # 检查是否包含多个关键词（用空格分隔）
        # 常见的分割模式：包含多个中文词组，且中间有空格
        if ' ' in cell_val and cell_val not in ['nan', 'None', 'NaN', '']:
            # 尝试分割
            parts = cell_val.split(' ')
            # 如果分割后有多个非空部分，且每个部分都有实际内容
            valid_parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 1]
            if len(valid_parts) >= 2:
                cols_to_split.append((col_idx, valid_parts))
    
    # 如果没有需要分割的列，直接返回
    if not cols_to_split:
        return df
    
    # 从后往前处理，避免索引变化
    for col_idx, parts in reversed(cols_to_split):
        print(f"    分割表头列 {col_idx}: '{header_row.iloc[col_idx]}' -> {parts}")
        
        # 获取原列的数据
        original_col = df.iloc[:, col_idx].tolist()
        
        # 删除原列
        df = df.drop(df.columns[col_idx], axis=1)
        
        # 创建新列并插入
        for part_idx, part in enumerate(parts):
            new_col_data = []
            for row_idx in range(len(original_col)):
                if row_idx == 0:
                    # 表头行：使用分割后的部分
                    new_col_data.append(part)
                else:
                    # 数据行：第一个新列保留原数据，其他新列为空
                    if part_idx == 0:
                        new_col_data.append(original_col[row_idx])
                    else:
                        new_col_data.append('')
            
            # 使用唯一的临时列名插入
            temp_col_name = f'temp_col_{col_idx}_{part_idx}'
            df.insert(col_idx + part_idx, temp_col_name, new_col_data)
    
    # 重置列索引
    df.columns = range(len(df.columns))
    
    return df

def extract_text_before_table(pdf_path: str, page_num: int, table_bbox: tuple, num_lines: int = 5) -> str:
    """
    提取表格前的文本
    
    Args:
        pdf_path: PDF文件路径
        page_num: 页码（从1开始）
        table_bbox: 表格边界框 (x0, top, x1, bottom)，pdfplumber格式
        num_lines: 提取多少行文本
    
    Returns:
        str: 表格前的文本
    """
    if not PYMUPDF_AVAILABLE or not EXTRACT_TEXT_BEFORE_TABLE:
        return ""
    
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_num - 1]  # PyMuPDF 页码从0开始
        
        # pdfplumber 的 bbox 格式: (x0, top, x1, bottom)，坐标系原点在左上角
        # PyMuPDF 的坐标系也是原点在左上角，可以直接使用
        table_top = table_bbox[1]  # top
        
        # 获取页面所有文本块
        blocks = page.get_text("dict")["blocks"]
        
        # 筛选表格上方的文本块
        text_blocks_above = []
        for block in blocks:
            if block["type"] == 0:  # 文本块
                block_bottom = block["bbox"][3]  # block 的底部
                
                # 如果文本块在表格上方
                if block_bottom < table_top:
                    # 提取文本
                    block_text = ""
                    for line in block["lines"]:
                        line_text = ""
                        for span in line["spans"]:
                            line_text += span["text"]
                        block_text += line_text.strip() + "\n"
                    
                    text_blocks_above.append({
                        "y": block["bbox"][1],  # 使用 top 坐标排序
                        "text": block_text.strip()
                    })
        
        # 按 y 坐标排序（从上到下）
        text_blocks_above.sort(key=lambda x: x["y"])
        
        # 取最后 num_lines 行（最接近表格的文本）
        recent_texts = [block["text"] for block in text_blocks_above[-num_lines:]]
        
        doc.close()
        
        return "\n".join(recent_texts)
    
    except Exception as e:
        print(f"⚠ 提取表格前文本失败: {e}")
        return ""

def extract_tables_with_pdfplumber(pdf_path: str, pages: str = 'all') -> List[Tuple[int, pd.DataFrame, tuple]]:
    """
    使用 pdfplumber 提取 PDF 中的表格
    
    Args:
        pdf_path: PDF文件路径
        pages: 页面范围，'all' 表示所有页面
    
    Returns:
        List[Tuple[int, pd.DataFrame, tuple]]: [(页码, DataFrame, bbox), ...]
    """
    if not PDFPLUMBER_AVAILABLE:
        raise ImportError("pdfplumber 未安装")
    
    tables_data = []
    
    with pdfplumber.open(pdf_path) as pdf:
        # 确定要处理的页面
        if pages == 'all':
            pages_to_process = pdf.pages
        else:
            # 解析页面范围（如 "1-5,7,9-10"）
            page_numbers = []
            for part in pages.split(','):
                if '-' in part:
                    start, end = map(int, part.split('-'))
                    page_numbers.extend(range(start, end + 1))
                else:
                    page_numbers.append(int(part))
            pages_to_process = [pdf.pages[i-1] for i in page_numbers if 0 < i <= len(pdf.pages)]
        
        # 提取每一页的表格
        for page in pages_to_process:
            page_num = page.page_number
            
            # 使用 pdfplumber 的表格识别
            # table_settings 可以调整识别精度
            table_settings = {
                "vertical_strategy": "lines",  # 使用线条识别垂直边界
                "horizontal_strategy": "lines",  # 使用线条识别水平边界
                "intersection_tolerance": 3,  # 交叉点容差
                "min_words_vertical": 1,  # 最少垂直单词数
                "min_words_horizontal": 1,  # 最少水平单词数
            }
            
            tables = page.find_tables(table_settings=table_settings)
            
            for table in tables:
                # 提取表格数据
                table_data = table.extract()
                
                if table_data and len(table_data) > 0:
                    # 转换为 DataFrame
                    df = pd.DataFrame(table_data)
                    
                    # 获取表格边界框
                    bbox = table.bbox  # (x0, top, x1, bottom)
                    
                    tables_data.append((page_num, df, bbox))
        
    return tables_data

def is_likely_header_only(table_df: pd.DataFrame, min_data_rows: int = 2) -> bool:
    """
    判断表格是否只包含表头（没有数据行或数据行很少）
    
    Args:
        table_df: 表格DataFrame
        min_data_rows: 最少数据行数，少于这个数认为是只有表头
    
    Returns:
        bool: 是否只包含表头
    """
    if table_df.empty:
        return True
    
    # 如果总行数少于等于表头行数（假设表头占1-3行）+ 最小数据行数
    header_rows = min(3, len(table_df))
    return len(table_df) <= header_rows + min_data_rows

def has_similar_structure(table1_df: pd.DataFrame, table2_df: pd.DataFrame, 
                          tolerance: int = 1) -> bool:
    """
    判断两个表格是否有相似的结构（列数相近）
    
    Args:
        table1_df: 第一个表格DataFrame
        table2_df: 第二个表格DataFrame
        tolerance: 允许的列数差异
    
    Returns:
        bool: 是否有相似结构
    """
    if table1_df.empty or table2_df.empty:
        return False
    
    cols1 = len(table1_df.columns)
    cols2 = len(table2_df.columns)
    return abs(cols1 - cols2) <= tolerance

def merge_cross_page_tables(matched_tables: List[Tuple[int, object]], 
                           tables: object, header_rules: List[dict]) -> List[Tuple[int, pd.DataFrame, str]]:
    """
    合并跨页表格
    
    处理两种情况：
    1. 表头在上一页，内容在下一页
    2. 表格在上一页未显示完，下一页继续（包括未匹配到规则的表格）
    
    Args:
        matched_tables: 已匹配的表格列表 [(原始索引, table对象), ...]
        tables: 所有表格对象
        header_rules: 表头规则列表
    
    Returns:
        List[Tuple[int, pd.DataFrame, str]]: 合并后的表格列表 [(原始索引, 合并后的DataFrame, 规则名称), ...]
    """
    if not ENABLE_MERGE_CROSS_PAGE_TABLES:
        # 不启用跨页合并，直接返回原表格
        result = []
        for orig_idx, table in matched_tables:
            result.append((orig_idx, table.df, ""))
        return result
    
    print("\n正在检测和合并跨页表格...")
    
    # 构建页面索引映射：page -> [(table_index, table, rule_name), ...]
    # 同时记录所有表格（包括未匹配的），用于跨页合并
    page_to_tables = {}
    page_to_all_tables = {}  # 所有表格（包括未匹配的）
    table_to_rule = {}
    matched_indices = set()  # 已匹配的表格索引
    
    # 先记录所有表格
    for i, table in enumerate(tables):
        page = table.page
        if page not in page_to_all_tables:
            page_to_all_tables[page] = []
        page_to_all_tables[page].append((i, table))
    
    # 记录已匹配的表格
    for orig_idx, table in matched_tables:
        page = table.page
        matched_indices.add(orig_idx)
        if page not in page_to_tables:
            page_to_tables[page] = []
        
        # 找到匹配的规则名称
        rule_name = ""
        for rule in header_rules:
            is_match, name = check_table_header(table.df, rule)
            if is_match:
                rule_name = name
                break
        
        page_to_tables[page].append((orig_idx, table, rule_name))
        table_to_rule[orig_idx] = rule_name
    
    merged_results = []
    processed_indices = set()
    
    # 按页面顺序处理
    sorted_pages = sorted(page_to_tables.keys())
    
    for page_idx, current_page in enumerate(sorted_pages):
        for orig_idx, table, rule_name in page_to_tables[current_page]:
            if orig_idx in processed_indices:
                continue
            
            # 检查是否是只有表头的表格（可能在上一页结尾）
            is_header_only = is_likely_header_only(table.df)
            current_df = table.df.copy()
            
            # 情况1: 当前表格只有表头，检查下一页是否有内容
            # 限制：最多只能跨1页（只检查下一页）
            if is_header_only:
                # 只检查下一页（页面号相差1），不检查更多页
                if page_idx + 1 < len(sorted_pages):
                    next_page = sorted_pages[page_idx + 1]
                    
                    # 严格检查：页面号必须相差1
                    if abs(next_page - current_page) == 1:
                        # 先检查已匹配的表格
                        if next_page in page_to_tables:
                            for next_orig_idx, next_table, next_rule_name in page_to_tables[next_page]:
                                if next_orig_idx in processed_indices:
                                    continue
                                
                                # 检查是否有相似结构且规则名称匹配
                                if (has_similar_structure(current_df, next_table.df) and 
                                    rule_name == next_rule_name):
                                    
                                    # 合并：保留当前表格的表头，添加下一页的数据
                                    # 假设表头占前3行
                                    header_rows = min(3, len(current_df))
                                    header_df = current_df.iloc[:header_rows].copy()
                                    
                                    # 下一页的数据（跳过可能的重复表头）
                                    next_data_df = next_table.df.copy()
                                    # 如果下一页第一行看起来像表头，跳过
                                    if len(next_data_df) > 0:
                                        first_row_text = " ".join(next_data_df.iloc[0].astype(str).str.strip().tolist())
                                        # 简单判断：如果第一行包含很多关键词，可能是表头
                                        keyword_count = sum(1 for kw in header_rules[0].get('keywords', []) if kw in first_row_text) if header_rules else 0
                                        if keyword_count >= 2:
                                            next_data_df = next_data_df.iloc[1:].copy()
                                    
                                    # 合并
                                    merged_df = pd.concat([header_df, next_data_df], ignore_index=True)
                                    merged_results.append((orig_idx, merged_df, rule_name))
                                    processed_indices.add(orig_idx)
                                    processed_indices.add(next_orig_idx)
                                    print(f"  ✓ 合并跨页表格: 页面 {current_page} (表头) + 页面 {next_page} (内容) -> 规则: {rule_name}")
                                    break
                            
                            if orig_idx in processed_indices:
                                break
                        
                        # 如果已匹配的表格没有找到，检查所有表格（包括未匹配的）
                        if orig_idx not in processed_indices and next_page in page_to_all_tables:
                            for next_orig_idx, next_table in page_to_all_tables[next_page]:
                                if next_orig_idx in processed_indices:
                                    continue
                                
                                # 检查是否有相似结构（列数相同或相近）
                                # 同时检查下一页表格是否匹配相同的规则（防止不同规则的表格被合并）
                                next_table_rule_name = ""
                                if header_rules:
                                    for rule in header_rules:
                                        is_match, name = check_table_header(next_table.df, rule)
                                        if is_match:
                                            next_table_rule_name = name
                                            break
                                
                                # 只有规则名称匹配且结构相似时，才考虑合并
                                if (has_similar_structure(current_df, next_table.df) and 
                                    (rule_name == next_table_rule_name or next_table_rule_name == "")):
                                    # 检查下一页第一行是否像表头
                                    next_first_row_text = ""
                                    if not next_table.df.empty:
                                        next_first_row_text = " ".join(next_table.df.iloc[0].astype(str).str.strip().tolist())
                                    
                                    # 检查是否包含表头关键词
                                    keyword_count = 0
                                    if header_rules and rule_name:
                                        for rule in header_rules:
                                            if rule.get('name') == rule_name:
                                                keywords = rule.get('keywords', [])
                                                keyword_count = sum(1 for kw in keywords if kw in next_first_row_text)
                                                break
                                    
                                    # 如果下一页第一行不像表头（关键词少于2个），认为是表格的继续
                                    # 但如果下一页匹配了不同的规则，则不合并
                                    if keyword_count < 2 and (rule_name == next_table_rule_name or next_table_rule_name == ""):
                                        # 合并：保留当前表格的表头，添加下一页的数据
                                        header_rows = min(3, len(current_df))
                                        header_df = current_df.iloc[:header_rows].copy()
                                        next_data_df = next_table.df.copy()
                                        
                                        # 如果列数不同，尝试对齐列
                                        if len(header_df.columns) != len(next_data_df.columns):
                                            # 如果下一页列数少，添加空列
                                            if len(next_data_df.columns) < len(header_df.columns):
                                                for i in range(len(next_data_df.columns), len(header_df.columns)):
                                                    next_data_df[len(next_data_df.columns)] = ""
                                        
                                        merged_df = pd.concat([header_df, next_data_df], ignore_index=True)
                                        merged_results.append((orig_idx, merged_df, rule_name))
                                        processed_indices.add(orig_idx)
                                        processed_indices.add(next_orig_idx)
                                        print(f"  ✓ 合并跨页表格: 页面 {current_page} (表头) + 页面 {next_page} (内容，未匹配) -> 规则: {rule_name}")
                                        break
                            
                            if orig_idx in processed_indices:
                                break
            
            # 情况2: 当前表格有内容，检查上一页是否有表头
            # 限制：最多只能跨1页（只检查上一页）
            if orig_idx not in processed_indices and not is_header_only:
                # 只检查上一页（页面号相差1），不检查更多页
                if page_idx > 0:
                    prev_page = sorted_pages[page_idx - 1]
                    
                    # 严格检查：页面号必须相差1
                    if abs(prev_page - current_page) == 1:
                    
                        if prev_page in page_to_tables:
                            for prev_orig_idx, prev_table, prev_rule_name in page_to_tables[prev_page]:
                                if prev_orig_idx in processed_indices:
                                    continue
                                
                                # 检查上一页是否只有表头，且结构相似
                                if (is_likely_header_only(prev_table.df) and 
                                    has_similar_structure(prev_table.df, current_df) and
                                    rule_name == prev_rule_name):
                                    
                                    # 合并：使用上一页的表头 + 当前页的数据
                                    header_rows = min(3, len(prev_table.df))
                                    header_df = prev_table.df.iloc[:header_rows].copy()
                                    
                                    # 当前页的数据（跳过可能的重复表头）
                                    current_data_df = current_df.copy()
                                    if len(current_data_df) > 0:
                                        first_row_text = " ".join(current_data_df.iloc[0].astype(str).str.strip().tolist())
                                        keyword_count = sum(1 for kw in header_rules[0].get('keywords', []) if kw in first_row_text) if header_rules else 0
                                        if keyword_count >= 2:
                                            current_data_df = current_data_df.iloc[1:].copy()
                                    
                                    merged_df = pd.concat([header_df, current_data_df], ignore_index=True)
                                    merged_results.append((orig_idx, merged_df, rule_name))
                                    processed_indices.add(orig_idx)
                                    processed_indices.add(prev_orig_idx)
                                    print(f"  ✓ 合并跨页表格: 页面 {prev_page} (表头) + 页面 {current_page} (内容) -> 规则: {rule_name}")
                                    break
                            
                            if orig_idx in processed_indices:
                                break
            
            # 情况3: 表格跨页继续（上一页未显示完，下一页继续）
            # 检查相邻页面的所有表格（包括未匹配到规则的），如果列数相同且第一行不像表头，则合并
            # 限制：最多只能跨1页（只检查下一页，不检查更多页）
            if orig_idx not in processed_indices:
                # 只检查下一页（页面号相差1），不检查更多页
                if page_idx + 1 < len(sorted_pages):
                    next_page = sorted_pages[page_idx + 1]
                    
                    # 严格检查：页面号必须相差1
                    if abs(next_page - current_page) == 1:
                        # 检查下一页的所有表格（包括未匹配的）
                        if next_page in page_to_all_tables:
                    
                            for next_orig_idx, next_table in page_to_all_tables[next_page]:
                                if next_orig_idx in processed_indices:
                                    continue
                                
                                # 检查结构是否相似（列数相同或相近）
                                # 同时检查下一页表格是否匹配相同的规则（防止不同规则的表格被合并）
                                next_table_rule_name = ""
                                if header_rules:
                                    for rule in header_rules:
                                        is_match, name = check_table_header(next_table.df, rule)
                                        if is_match:
                                            next_table_rule_name = name
                                            break
                                
                                # 只有规则名称匹配且结构相似时，才考虑合并
                                if (has_similar_structure(current_df, next_table.df) and 
                                    (rule_name == next_table_rule_name or next_table_rule_name == "")):
                                    # 检查下一页第一行是否像表头
                                    next_first_row_text = ""
                                    if not next_table.df.empty:
                                        next_first_row_text = " ".join(next_table.df.iloc[0].astype(str).str.strip().tolist())
                                    
                                    # 检查是否包含表头关键词
                                    keyword_count = 0
                                    if header_rules and rule_name:
                                        for rule in header_rules:
                                            if rule.get('name') == rule_name:
                                                keywords = rule.get('keywords', [])
                                                keyword_count = sum(1 for kw in keywords if kw in next_first_row_text)
                                                break
                                    
                                    # 检查合并后的表格是否包含新的表头（防止跨多页合并）
                                    # 检查下一页的数据中是否包含其他规则的表头
                                    has_other_header = False
                                    if len(next_table.df) > 0:
                                        # 检查前几行是否包含其他规则的关键词
                                        for check_row_idx in range(min(3, len(next_table.df))):
                                            check_row_text = " ".join(next_table.df.iloc[check_row_idx].astype(str).str.strip().tolist())
                                            # 检查是否包含其他规则的关键词
                                            for other_rule in header_rules:
                                                if other_rule.get('name') != rule_name:
                                                    other_keywords = other_rule.get('keywords', [])
                                                    other_keyword_count = sum(1 for kw in other_keywords if kw in check_row_text)
                                                    if other_keyword_count >= 2:
                                                        has_other_header = True
                                                        break
                                            if has_other_header:
                                                break
                                    
                                    # 如果下一页第一行不像表头（关键词少于2个），且不包含其他表头，且规则匹配，认为是表格的继续
                                    # 注意：如果下一页第一行是表头（keyword_count >= 2），或匹配了不同的规则，则不合并
                                    if (keyword_count < 2 and not has_other_header and 
                                        (rule_name == next_table_rule_name or next_table_rule_name == "")):
                                        # 合并：当前表格 + 下一页的数据
                                        next_data_df = next_table.df.copy()
                                        merged_df = pd.concat([current_df, next_data_df], ignore_index=True)
                                        merged_results.append((orig_idx, merged_df, rule_name))
                                        processed_indices.add(orig_idx)
                                        processed_indices.add(next_orig_idx)
                                        next_rule_display = rule_name if next_orig_idx in matched_indices else "未匹配"
                                        print(f"  ✓ 合并跨页表格: 页面 {current_page} + 页面 {next_page} (继续) -> 规则: {rule_name} (下一页表格: {next_rule_display})")
                                        break
                            
                            if orig_idx in processed_indices:
                                break
            
            # 如果没有被合并，单独添加
            if orig_idx not in processed_indices:
                merged_results.append((orig_idx, current_df, rule_name))
                processed_indices.add(orig_idx)
    
    print(f"✓ 跨页表格合并完成，共 {len(merged_results)} 个表格（含合并后的）")
    return merged_results

def load_tables_from_xlsx(xlsx_dir: Path) -> List[Tuple[int, pd.DataFrame, int]]:
    """
    从xlsx文件中加载表格，按页面和表格顺序排序
    
    Args:
        xlsx_dir: xlsx文件所在目录
    
    Returns:
        List[Tuple[int, pd.DataFrame, int]]: [(索引, DataFrame, 页面号), ...]
    """
    xlsx_files = list(xlsx_dir.glob("*.xlsx"))
    if not xlsx_files:
        print(f"⚠ 在目录 {xlsx_dir} 中未找到xlsx文件")
        return []
    
    # 解析文件名并排序：先按页码，再按表格序号
    file_info = []
    for xlsx_file in xlsx_files:
        # 支持两种格式：
        # 1. 新格式：table_page8_1of3.xlsx -> page=8, table_num=1, total=3
        # 2. 旧格式：table_page8_3.xlsx -> page=8, table_num=3
        match_new = re.search(r'page(\d+)_(\d+)of(\d+)', xlsx_file.stem)
        match_old = re.search(r'page(\d+)_(\d+)', xlsx_file.stem)
        
        if match_new:
            page_num = int(match_new.group(1))
            table_num = int(match_new.group(2))
            file_info.append((xlsx_file, page_num, table_num))
        elif match_old:
            page_num = int(match_old.group(1))
            table_num = int(match_old.group(2))
            file_info.append((xlsx_file, page_num, table_num))
        else:
            # 如果无法解析，尝试只提取页码
            page_match = re.search(r'page(\d+)', xlsx_file.stem)
            if page_match:
                page_num = int(page_match.group(1))
                file_info.append((xlsx_file, page_num, 0))
            else:
                # 完全无法解析，使用默认值
                file_info.append((xlsx_file, 9999, 0))
    
    # 按页码和表格序号排序
    file_info.sort(key=lambda x: (x[1], x[2]))
    
    tables = []
    for idx, (xlsx_file, page_num, table_num) in enumerate(file_info):
        try:
            df = pd.read_excel(xlsx_file, header=None)
            tables.append((idx, df, page_num))
        except Exception as e:
            print(f"⚠ 读取文件 {xlsx_file.name} 失败: {e}")
    
    return tables

def get_header_rules_for_file(pdf_path: str) -> List[dict]:
    """
    根据PDF文件名获取对应的表头规则（精确匹配文件名）
    
    Args:
        pdf_path: PDF文件路径
    
    Returns:
        List[dict]: 表头规则列表
    """
    pdf_filename = Path(pdf_path).name
    
    # 精确匹配文件名（固定匹配，不进行模糊匹配）
    if pdf_filename in TABLE_HEADER_RULES:
        return TABLE_HEADER_RULES[pdf_filename]
    
    return []

def preview_table_headers(tables, max_preview: int = 10):
    """预览表格表头，帮助用户确定过滤条件（支持多行表头）"""
    print("\n" + "=" * 60)
    print("表格表头预览（前几个表格，包含多行表头）:")
    print("=" * 60)
    
    preview_count = min(max_preview, tables.n)
    for i in range(preview_count):
        table = tables[i]
        if table.df.empty:
            print(f"表格 {i+1} (页面 {table.page}): [空表格]")
            continue
        
        # 合并前3行作为表头预览（处理换行情况）
        header_rows_to_check = min(3, len(table.df))
        header_parts = []
        for row_idx in range(header_rows_to_check):
            row = table.df.iloc[row_idx].astype(str).str.strip()
            for cell in row[:5]:  # 只显示前5列
                cell_text = str(cell).strip()
                if cell_text and cell_text.lower() not in ['nan', 'none', '']:
                    header_parts.append(cell_text)
        
        header_text = " | ".join(header_parts[:10])  # 最多显示10个部分
        if len(header_parts) > 10:
            header_text += " ..."
        print(f"表格 {i+1} (页面 {table.page}): {header_text}")
    
    if tables.n > max_preview:
        print(f"... 还有 {tables.n - max_preview} 个表格未显示")
    print("=" * 60 + "\n")

# 检查并转换文件（如果是 CEB）
pdf_path = check_and_convert_file(pdf_path)
print(f"处理文件: {pdf_path}\n")

# 创建输出目录
output_dir.mkdir(exist_ok=True)

# 判断是从PDF提取还是从xlsx文件过滤
if FILTER_FROM_EXISTING_XLSX and XLSX_INPUT_DIR:
    xlsx_input_path = Path(XLSX_INPUT_DIR)
    
    # 检查xlsx文件是否存在
    xlsx_files = list(xlsx_input_path.glob("*.xlsx")) if xlsx_input_path.exists() else []
    
    if not xlsx_files:
        print("=" * 60)
        print("未找到xlsx文件，先从PDF生成xlsx文件...")
        print("=" * 60)
        
        # 先创建目录
        xlsx_input_path.mkdir(parents=True, exist_ok=True)
        
        # 从PDF提取所有表格
        print("\n正在读取PDF文件并提取表格，请稍候...")
        start_time = time.time()
        
        # 使用 pdfplumber 提取表格
        tables_data = extract_tables_with_pdfplumber(pdf_path, pages='all')
        
        extract_time = time.time() - start_time
        
        print(f"\n✓ 表格提取完成！共提取到 {len(tables_data)} 个表格 (耗时: {extract_time:.2f}秒)")
        
        # 保存到 extracted_tables 目录（包含表格前文本）
        extracted_output_dir = Path('extracted_tables')
        extracted_output_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n正在保存所有表格为xlsx文件到: {extracted_output_dir}")
        
        # 先统计每页的表格数量
        page_table_counts = {}
        for page_num, df, bbox in tables_data:
            if page_num not in page_table_counts:
                page_table_counts[page_num] = 0
            page_table_counts[page_num] += 1
        
        # 为每个页面维护一个计数器
        page_current_index = {}
        
        # 保存所有表格为xlsx文件，使用新的命名格式
        saved_count = 0
        for i, (page_num, df, bbox) in tqdm(enumerate(tables_data), total=len(tables_data), 
                                            desc="保存xlsx", unit="个", ncols=80):
            # 更新该页面的当前索引
            if page_num not in page_current_index:
                page_current_index[page_num] = 0
            page_current_index[page_num] += 1
            
            current_num = page_current_index[page_num]
            total_num = page_table_counts[page_num]
            
            # 使用新的命名格式: table_page{page}_{current}of{total}.xlsx
            xlsx_file = extracted_output_dir / f"table_page{page_num}_{current_num}of{total_num}.xlsx"
            
            try:
                # 提取表格前的文本
                text_before = ""
                if EXTRACT_TEXT_BEFORE_TABLE and PYMUPDF_AVAILABLE:
                    text_before = extract_text_before_table(pdf_path, page_num, bbox, TEXT_LINES_BEFORE_TABLE)
                
                # 如果有文本，将其添加到表格的第一行
                if text_before:
                    # 创建一个新的 DataFrame，第一行是文本信息
                    text_row = pd.DataFrame([[f"[表格前文本] {text_before}"]], columns=[0])
                    # 将原表格的列数调整为与文本行一致
                    table_df = df.copy()
                    # 如果表格列数大于1，在文本行后面填充空值
                    if len(table_df.columns) > 1:
                        for col_idx in range(1, len(table_df.columns)):
                            text_row[col_idx] = ""
                    
                    # 合并文本行和表格
                    combined_df = pd.concat([text_row, table_df], ignore_index=True)
                    combined_df.to_excel(str(xlsx_file), index=False, header=False)
                else:
                    # 没有文本，直接保存表格
                    df.to_excel(str(xlsx_file), index=False, header=False)
                
                saved_count += 1
            except Exception as e:
                tqdm.write(f"⚠ 表格 {i+1} (页面 {page_num}) 保存失败: {e}")
        
        print(f"\n✓ 已保存 {saved_count} 个xlsx文件到 {extracted_output_dir}")
        
        # 更新 xlsx_input_path 指向 extracted_tables
        xlsx_input_path = extracted_output_dir
        
        print(f"\n✓ 已保存 {saved_count} 个xlsx文件到 {extracted_output_dir}")
        
        # 更新 xlsx_input_path 指向 extracted_tables
        xlsx_input_path = extracted_output_dir
        print("=" * 60)
        print("现在开始合并跨页表格...")
        print("=" * 60)
    
    # ========== 步骤2: 合并跨页表格 ==========
    # 从 extracted_tables 读取，合并后保存到 merged_tables（不进行过滤）
    
    # 检查 merged_tables 是否已经存在
    merged_files_exist = list(merged_output_dir.glob("*.xlsx")) if merged_output_dir.exists() else []
    
    if not merged_files_exist:
        print(f"\n正在从 {xlsx_input_path} 读取表格...")
        start_time = time.time()
        extracted_tables = load_tables_from_xlsx(xlsx_input_path)
        load_time = time.time() - start_time
        
        if not extracted_tables:
            print("⚠ 未找到任何xlsx文件")
            exit(1)
        
        print(f"✓ 加载完成！共加载 {len(extracted_tables)} 个xlsx文件 (耗时: {load_time:.2f}秒)")
        
        # 执行合并（合并所有表格，不进行过滤）
        print("\n正在合并跨页表格（基于表格前文本）...")
        merged_tables_list = []
        i = 0
        
        while i < len(extracted_tables):
            idx, df, page = extracted_tables[i]
            
            # 检查是否有表格前文本
            has_text, text_content = has_text_before_table(df)
            
            if not has_text:
                # 没有前文本，跳过（孤立数据）
                print(f"  ⚠ 跳过表格 {idx} (页面 {page}): 没有表格前文本")
                i += 1
                continue
            # 有前文本，这是一个新表格的开始
            # 移除文本行，获取纯表格数据
            merged_df = remove_text_row(df)
            
            # 判断是否是 table_3（用于调试）
            is_table_3 = (len(merged_tables_list) == 2)  # table_3 是第3个表格（索引2）
            
            # 先合并被截断的行（在清理换行符之前，这样可以保留原始的 NaN 值）
            if is_table_3:
                print(f"\n[DEBUG] 处理 table_3 (索引 {len(merged_tables_list)})")
            merged_df = merge_broken_rows(merged_df, header_rows=1, debug=is_table_3)
            
            # 再清理换行符
            merged_df = clean_newlines(merged_df)
            
            merged_count = 0
            merged_pages = [page]
            merged_indices = [idx]
            j = i + 1
            
            # 检查后续表格是否需要合并
            while j < len(extracted_tables):
                next_idx, next_df, next_page = extracted_tables[j]
                
                # 检查下一个表格是否有前文本
                next_has_text, _ = has_text_before_table(next_df)
                
                if next_has_text:
                    # 下一个表格有前文本，是新表格的开始，停止合并
                    break
                
                # 下一个表格没有前文本，检查是否应该合并
                page_diff = next_page - merged_pages[-1]
                next_df_clean = remove_text_row(next_df)
                
                # 先合并被截断的行
                next_df_clean = merge_broken_rows(next_df_clean, header_rows=0)
                
                # 再清理换行符
                next_df_clean = clean_newlines(next_df_clean)
                
                if page_diff <= CROSS_PAGE_SEARCH_RANGE and has_similar_structure(merged_df, next_df_clean):
                    # 合并
                    merged_df = pd.concat([merged_df, next_df_clean], ignore_index=True)
                    merged_count += 1
                    merged_pages.append(next_page)
                    merged_indices.append(next_idx)
                    print(f"  ✓ 合并: 页面 {page} + 页面 {next_page} [文本: {text_content[:40]}...]")
                    j += 1
                else:
                    # 页面距离太远或结构不同，停止合并
                    break
            
            # 跨页合并完成后，再次处理被截断的行
            if merged_count > 0:
                if is_table_3:
                    print(f"\n[DEBUG] table_3 跨页合并后，再次检查被截断的行")
                merged_df = merge_broken_rows(merged_df, header_rows=1, debug=is_table_3)
            
            # 添加合并后的表格（保存所有表格，不进行过滤）
            merged_tables_list.append((idx, merged_df, page, text_content))
            i = j if merged_count > 0 else i + 1
        
        print(f"\n✓ 合并完成！从 {len(extracted_tables)} 个原始表格合并为 {len(merged_tables_list)} 个表格")
        
        # 保存合并后的表格到 merged_tables 目录（保存所有表格）
        merged_output_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n正在保存合并后的表格到: {merged_output_dir}...")
        
        saved_count = 0
        for idx, (orig_idx, merged_df, page, text_content) in tqdm(enumerate(merged_tables_list), 
                                                                    total=len(merged_tables_list),
                                                                    desc="保存合并表格", unit="个", ncols=80):
            # 使用简单的命名: table_1.xlsx, table_2.xlsx, ...
            xlsx_file = merged_output_dir / f"table_{idx+1}.xlsx"
            try:
                # 保存纯表格数据（已经移除了文本行）
                merged_df.to_excel(str(xlsx_file), index=False, header=False)
                saved_count += 1
            except Exception as e:
                tqdm.write(f"⚠ 表格 {idx+1} 保存失败: {e}")
        
        print(f"\n✓ 已保存 {saved_count} 个合并后的表格到 {merged_output_dir}")
    else:
        print(f"\n✓ 发现已存在的合并表格，跳过合并步骤")
    
    print("=" * 60)
    print("现在开始从合并表格中过滤...")
    print("=" * 60)
    
    # ========== 步骤3: 从 merged_tables 加载用于过滤 ==========
    # 从 merged_tables 读取（只从这一个目录读取）
    print(f"\n正在从 {merged_output_dir} 读取合并后的表格...")
    start_time = time.time()
    xlsx_tables = load_tables_from_xlsx(merged_output_dir)
    load_time = time.time() - start_time
    
    if not xlsx_tables:
        print("⚠ 未找到任何xlsx文件")
        exit(1)
    
    print(f"\n✓ 加载完成！共加载 {len(xlsx_tables)} 个xlsx文件 (耗时: {load_time:.2f}秒)")
    
    # 验证 merged_tables 中没有文本行
    text_row_count = 0
    for idx, df, page in xlsx_tables:
        has_text, _ = has_text_before_table(df)
        if has_text:
            text_row_count += 1
            print(f"  ⚠ 警告: 表格 {idx+1} 仍包含 [表格前文本] 行")
    
    if text_row_count > 0:
        print(f"\n⚠ 发现 {text_row_count} 个表格仍包含文本行，这不应该发生！")
        print("  merged_tables 应该只包含纯表格数据")
    else:
        print(f"✓ 验证通过：所有表格都不包含 [表格前文本] 行")
    
    # 转换为类似camelot tables的对象结构
    class XlsxTable:
        def __init__(self, df, page):
            self.df = df
            self.page = page
    
    # 创建模拟的tables对象
    class XlsxTables:
        def __init__(self, xlsx_tables):
            self.n = len(xlsx_tables)
            self._tables = [XlsxTable(df, page) for _, df, page in xlsx_tables]
        
        def __getitem__(self, idx):
            return self._tables[idx]
        
        def __iter__(self):
            return iter(self._tables)
    
    tables = XlsxTables(xlsx_tables)
    
else:
    print("=" * 60)
    print("开始提取PDF表格...")
    print("=" * 60)
    
    # 提取表格
    print("\n正在读取PDF文件并提取表格，请稍候...")
    start_time = time.time()
    
    # 使用 pdfplumber 提取表格
    tables_data = extract_tables_with_pdfplumber(pdf_path, pages='all')
    
    extract_time = time.time() - start_time
    
    print(f"\n✓ 表格提取完成！共提取到 {len(tables_data)} 个表格 (耗时: {extract_time:.2f}秒)")
    
    # 转换为类似的对象结构以兼容后续代码
    class PdfPlumberTable:
        def __init__(self, df, page):
            self.df = df
            self.page = page
    
    class PdfPlumberTables:
        def __init__(self, tables_data):
            self.n = len(tables_data)
            self._tables = [PdfPlumberTable(df, page) for page, df, bbox in tables_data]
        
        def __getitem__(self, idx):
            return self._tables[idx]
        
        def __iter__(self):
            return iter(self._tables)
    
    tables = PdfPlumberTables(tables_data)

# 显示表头预览
if SHOW_HEADER_PREVIEW:
    preview_table_headers(tables)

# 获取当前文件对应的表头规则
if FILTER_FROM_EXISTING_XLSX:
    # 从xlsx过滤时，使用PDF文件名来匹配规则（如果xlsx是从该PDF生成的）
    header_rules = get_header_rules_for_file(pdf_path)
else:
    header_rules = get_header_rules_for_file(pdf_path)

# 过滤表格
if ENABLE_HEADER_FILTER:
    if not header_rules:
        print(f"\n⚠ 警告: 未找到文件 '{Path(pdf_path).name}' 对应的表头规则！")
        print("请在 TABLE_HEADER_RULES 中添加该文件的规则配置")
        print("或者设置 ENABLE_HEADER_FILTER = False 来提取所有表格")
        user_input = input("\n是否继续提取所有表格？(y/n): ").strip().lower()
        if user_input != 'y':
            exit(0)
        
        # 根据数据源类型处理
        if FILTER_FROM_EXISTING_XLSX and xlsx_tables:
            matched_tables = [(idx, df, page) for idx, df, page in xlsx_tables]
        else:
            matched_tables = [(i, table.df, table.page) for i, table in enumerate(tables)]
        print(f"✓ 将处理所有 {len(matched_tables)} 个表格")
        merged_tables_final = [(idx, df, "") for idx, df, page in matched_tables]
    else:
        print(f"\n找到 {len(header_rules)} 个表头规则:")
        for rule in header_rules:
            print(f"  - {rule['name']}: {', '.join(rule['keywords'][:3])}...")
        
        print("\n正在根据表头规则过滤表格...")
        
        # 根据数据源类型过滤
        if FILTER_FROM_EXISTING_XLSX and xlsx_tables:
            # 从 merged_tables 文件过滤 - 这些表格已经合并过了，不需要再合并
            all_tables_info = []  # [(索引, DataFrame, 页面号, 是否匹配, 规则名称), ...]
            
            for idx, df, page in xlsx_tables:
                # 检查是否匹配任何规则（merged_tables 中已经没有文本行了）
                matched = False
                matched_rule = ""
                
                for rule in header_rules:
                    is_match, rule_name = check_table_header(df, rule)
                    if is_match:
                        matched = True
                        matched_rule = rule_name
                        break
                
                all_tables_info.append((idx, df, page, matched, matched_rule))
            
            print(f"✓ 检查了 {len(all_tables_info)} 个表格")
            
            # 只保留匹配的表格（不需要合并，因为已经在 merged_tables 中合并过了）
            merged_tables_final = [(idx, df, rule_name) 
                                  for idx, df, page, matched, rule_name in all_tables_info if matched]
            
            if len(merged_tables_final) == 0:
                print("\n⚠ 警告: 没有找到匹配的表格！")
                print("请检查 TABLE_HEADER_RULES 配置")
                exit(1)
        else:
            # 从 PDF 提取
            matched_tables = []
            matched_rules_info = {}  # 记录每个表格匹配的规则
            
            for i, table in enumerate(tables):
                for rule in header_rules:
                    is_match, rule_name = check_table_header(table.df, rule)
                    if is_match:
                        matched_tables.append((i, table))
                        matched_rules_info[i] = rule_name
                        break  # 匹配到一个规则就停止
            
            print(f"✓ 匹配到 {len(matched_tables)} 个符合条件的表格")
            
            if len(matched_tables) == 0:
                print("\n⚠ 警告: 没有找到匹配的表格！")
                print("请检查 TABLE_HEADER_RULES 配置")
                print("如果 SHOW_HEADER_PREVIEW=True，可以查看上面的表头预览来调整配置")
                exit(1)
            
            # 合并跨页表格（从 PDF）
            # TODO: 实现 PDF 的跨页合并（暂时不实现）
            merged_tables_final = [(orig_idx, table.df, matched_rules_info.get(orig_idx, "")) 
                           for orig_idx, table in matched_tables]
        
        # 显示匹配的表格信息（支持多行表头）
        print("\n匹配的表格:")
        for idx, (orig_idx, table_df, rule_name) in enumerate(merged_tables_final):
            if table_df.empty:
                header_preview = "[空表格]"
            else:
                # 合并前3行作为表头预览（处理换行情况）
                header_rows_to_check = min(3, len(table_df))
                header_parts = []
                for row_idx in range(header_rows_to_check):
                    row = table_df.iloc[row_idx].astype(str).str.strip()
                    for cell in row[:3]:  # 只显示前3列
                        cell_text = str(cell).strip()
                        if cell_text and cell_text.lower() not in ['nan', 'none', '']:
                            # 去除换行符
                            cell_text = cell_text.replace('\n', '').replace('\r', '')
                            header_parts.append(cell_text)
                header_preview = " | ".join(header_parts[:6])  # 最多显示6个部分
                if len(header_parts) > 6:
                    header_preview += " ..."
            
            if SHOW_MATCHED_RULE_NAME:
                print(f"  {idx+1}. 原表格 {orig_idx+1} [{rule_name}]: {header_preview} (行数: {len(table_df)})")
            else:
                print(f"  {idx+1}. 原表格 {orig_idx+1}: {header_preview} (行数: {len(table_df)})")
        
        # 更新matched_tables为合并后的结果，保留页面信息
        # 需要从原始 xlsx_tables 中获取页面信息
        matched_tables = []
        for orig_idx, table_df, _ in merged_tables_final:
            # 查找原始表格的页面信息
            page = 0
            if isinstance(orig_idx, str):
                # 如果是分割后的表格（格式：idx_subidx）
                base_idx = int(orig_idx.split('_')[0])
            else:
                base_idx = orig_idx
            
            # 从 xlsx_tables 中查找页面号
            for idx, df, p in xlsx_tables:
                if idx == base_idx:
                    page = p
                    break
            
            matched_tables.append((orig_idx, table_df, page))
else:
    # 不启用表头过滤
    if FILTER_FROM_EXISTING_XLSX and xlsx_tables:
        matched_tables = [(idx, df, page) for idx, df, page in xlsx_tables]
    else:
        matched_tables = [(i, table.df, table.page) for i, table in enumerate(tables)]
    print(f"✓ 未启用表头过滤，将处理所有 {len(matched_tables)} 个表格")

# 确定输出目录：如果启用了表头过滤，使用筛选后的目录，否则使用原始目录
if ENABLE_HEADER_FILTER:
    final_output_dir = filtered_output_dir
    print(f"\n开始保存筛选后的表格文件到: {final_output_dir}...\n")
else:
    final_output_dir = output_dir
    print(f"\n开始保存表格文件到: {final_output_dir}...\n")

# 创建输出目录
final_output_dir.mkdir(parents=True, exist_ok=True)

# 保存为Excel，使用tqdm显示进度
success_count = 0
error_count = 0

for idx, (orig_idx, table_df, page) in tqdm(enumerate(matched_tables), total=len(matched_tables), 
                                    desc="处理表格", unit="个", ncols=80):
    # 使用简单的命名格式: table_1.xlsx, table_2.xlsx, ...
    excel_path = final_output_dir / f"table_{idx+1}.xlsx"
    
    try:
        # 直接使用DataFrame的to_excel方法
        table_df.to_excel(str(excel_path), index=False, header=False)
        success_count += 1
    except Exception as e:
        tqdm.write(f"⚠ 表格 {idx+1} (原表格 {orig_idx}) Excel保存失败: {e}")
        error_count += 1

total_time = time.time() - start_time

print("\n" + "=" * 60)
print("处理完成！")
print("=" * 60)
if ENABLE_HEADER_FILTER:
    if FILTER_FROM_EXISTING_XLSX and xlsx_tables:
        print(f"📊 原始表格总数: {len(xlsx_tables)}")
    else:
        print(f"📊 原始表格总数: {tables.n}")
    print(f"✅ 匹配的表格数: {len(matched_tables)}")
print(f"✓ 成功保存: {success_count} 个表格")
if error_count > 0:
    print(f"⚠ 保存失败: {error_count} 个表格")
print(f"📁 输出目录: {final_output_dir.absolute()}")
if ENABLE_HEADER_FILTER:
    print(f"📁 原始表格目录: {output_dir.absolute()}")
print(f"⏱  总耗时: {total_time:.2f}秒")
print("=" * 60)