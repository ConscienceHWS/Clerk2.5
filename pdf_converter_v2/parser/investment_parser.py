# Copyright (c) Opendatalab. All rights reserved.

"""
投资估算表格解析模块
支持三种类型:
1. 可研批复投资估算
2. 可研评审投资估算
3. 初设批复概算投资
"""

from typing import List, Optional
import re
from ..utils.logging_config import get_logger
from ..models.data_models import (
    FeasibilityApprovalInvestment,
    FeasibilityReviewInvestment,
    PreliminaryApprovalInvestment,
    InvestmentItem
)
from .table_parser import extract_table_with_rowspan_colspan

logger = get_logger("pdf_converter_v2.parser.investment")


def detect_investment_type(markdown_content: str) -> Optional[str]:
    """
    检测投资估算表格类型
    
    Returns:
        str: 类型名称
            - "feasibilityApprovalInvestment" - 可研批复
            - "feasibilityReviewInvestment" - 可研评审
            - "preliminaryApprovalInvestment" - 初设批复
            - None - 无法识别
    """
    # 检查标题关键词
    if "可研批复" in markdown_content or "可行性研究报告的批复" in markdown_content:
        # 检查是否有建设规模相关列（可研批复特有）
        if "架空线" in markdown_content or "间隔" in markdown_content:
            logger.info("[投资估算] 检测到类型: 可研批复投资估算")
            return "feasibilityApprovalInvestment"
    
    if "可研评审" in markdown_content or "可行性研究报告的评审意见" in markdown_content:
        logger.info("[投资估算] 检测到类型: 可研评审投资估算")
        return "feasibilityReviewInvestment"
    
    if "初设批复" in markdown_content or "初步设计的批复" in markdown_content:
        logger.info("[投资估算] 检测到类型: 初设批复概算投资")
        return "preliminaryApprovalInvestment"
    
    logger.warning("[投资估算] 无法识别投资估算表格类型")
    return None


def determine_level(text: str) -> str:
    """
    判断明细等级
    
    规则:
    - 大写中文数字(一、二、三等) -> 第一级
    - 小写阿拉伯数字(1、2、3等) -> 第二级  
    - 带括号的数字(1)、2)等) -> 第三级
    - 合计 -> 0
    
    Args:
        text: 序号或名称文本
        
    Returns:
        str: "0"(合计), "1"(一级), "2"(二级), "3"(三级), ""(无法判断)
    """
    if not text:
        return ""
    
    text = text.strip()
    
    # 合计行
    if "合计" in text:
        return "0"
    
    # 第一级: 大写中文数字
    if re.match(r'^[一二三四五六七八九十]+[、，,.]', text):
        return "1"
    
    # 第二级: 小写阿拉伯数字
    if re.match(r'^\d+[、，,.]', text) and not text.startswith('(') and not text.startswith('（'):
        return "2"
    
    # 第三级: 带括号的数字
    if re.match(r'^[(（]\d+[)）]', text):
        return "3"
    
    return ""


def clean_number_string(value: str) -> str:
    """
    清理数字字符串
    - 移除千位分隔符
    - 移除单位
    - 保留小数点
    
    Args:
        value: 原始数字字符串
        
    Returns:
        str: 清理后的数字字符串
    """
    if not value or not value.strip():
        return ""
    
    value = value.strip()
    
    # 移除常见单位
    value = re.sub(r'[万元元]', '', value)
    
    # 移除千位分隔符
    value = value.replace(',', '').replace('，', '')
    
    # 移除空格
    value = value.replace(' ', '')
    
    return value


def parse_feasibility_approval_investment(markdown_content: str) -> FeasibilityApprovalInvestment:
    """
    解析可研批复投资估算
    
    包含字段:
    - No: 序号
    - name: 工程或费用名称
    - Level: 明细等级
    - constructionScaleOverheadLine: 建设规模-架空线
    - constructionScaleBay: 建设规模-间隔
    - constructionScaleSubstation: 建设规模-变电
    - constructionScaleOpticalCable: 建设规模-光缆
    - staticInvestment: 静态投资（元）
    - dynamicInvestment: 动态投资（元）
    """
    record = FeasibilityApprovalInvestment()
    
    tables = extract_table_with_rowspan_colspan(markdown_content)
    
    if not tables:
        logger.warning("[可研批复投资] 未能提取出任何表格内容")
        return record
    
    # 找到包含投资估算的表格（通常包含"工程或费用名称"、"静态投资"等关键词）
    target_table = None
    for table in tables:
        for row in table:
            row_text = " ".join([str(cell) for cell in row])
            if "工程或费用名称" in row_text and "静态投资" in row_text:
                target_table = table
                logger.info(f"[可研批复投资] 找到投资估算表格, 行数: {len(table)}")
                break
        if target_table:
            break
    
    if not target_table:
        logger.warning("[可研批复投资] 未找到包含投资估算的表格")
        return record
    
    # 识别表头行和列索引
    header_row_idx = -1
    no_idx = -1
    name_idx = -1
    overhead_line_idx = -1
    bay_idx = -1
    substation_idx = -1
    optical_cable_idx = -1
    static_investment_idx = -1
    dynamic_investment_idx = -1
    
    for row_idx, row in enumerate(target_table):
        row_text = " ".join([str(cell) for cell in row])
        
        # 找到表头行
        if "工程或费用名称" in row_text or "序号" in row_text:
            header_row_idx = row_idx
            logger.debug(f"[可研批复投资] 找到表头行: 第{row_idx}行")
            
            # 识别各列
            for col_idx, cell in enumerate(row):
                cell_text = str(cell).strip()
                if "序号" in cell_text:
                    no_idx = col_idx
                elif "工程或费用名称" in cell_text or "名称" in cell_text:
                    name_idx = col_idx
                elif "架空线" in cell_text:
                    overhead_line_idx = col_idx
                elif "间隔" in cell_text:
                    bay_idx = col_idx
                elif "变电" in cell_text:
                    substation_idx = col_idx
                elif "光缆" in cell_text:
                    optical_cable_idx = col_idx
                elif "静态投资" in cell_text:
                    static_investment_idx = col_idx
                elif "动态投资" in cell_text:
                    dynamic_investment_idx = col_idx
            
            logger.info(f"[可研批复投资] 列索引: 序号={no_idx}, 名称={name_idx}, "
                       f"架空线={overhead_line_idx}, 间隔={bay_idx}, 变电={substation_idx}, "
                       f"光缆={optical_cable_idx}, 静态投资={static_investment_idx}, 动态投资={dynamic_investment_idx}")
            break
    
    if header_row_idx == -1:
        logger.warning("[可研批复投资] 未找到表头行")
        return record
    
    # 解析数据行
    for row_idx in range(header_row_idx + 1, len(target_table)):
        row = target_table[row_idx]
        
        if len(row) < 3:
            continue
        
        # 检查是否是有效数据行（至少有名称）
        if name_idx >= 0 and name_idx < len(row):
            name = str(row[name_idx]).strip()
            if not name or name in ["", "nan", "None"]:
                continue
            
            item = InvestmentItem()
            
            # 提取序号
            if no_idx >= 0 and no_idx < len(row):
                item.no = str(row[no_idx]).strip()
            
            # 提取名称
            item.name = name
            
            # 判断等级（先从序号判断，如果没有序号则从名称判断）
            if item.no:
                item.level = determine_level(item.no + item.name)
            else:
                item.level = determine_level(item.name)
            
            # 只保留"四"及以下的数据（即跳过"一"、"二"、"三"）
            if item.level == "1":
                # 检查是否是"一"、"二"、"三"（需要跳过）
                if any(prefix in (item.no + item.name) for prefix in ["一、", "一，", "二、", "二，", "三、", "三，"]):
                    logger.debug(f"[可研批复投资] 跳过一二三级数据: {item.name}")
                    continue
            
            # 提取建设规模
            if overhead_line_idx >= 0 and overhead_line_idx < len(row):
                item.constructionScaleOverheadLine = str(row[overhead_line_idx]).strip()
            
            if bay_idx >= 0 and bay_idx < len(row):
                item.constructionScaleBay = str(row[bay_idx]).strip()
            
            if substation_idx >= 0 and substation_idx < len(row):
                item.constructionScaleSubstation = str(row[substation_idx]).strip()
            
            if optical_cable_idx >= 0 and optical_cable_idx < len(row):
                item.constructionScaleOpticalCable = str(row[optical_cable_idx]).strip()
            
            # 提取投资金额
            if static_investment_idx >= 0 and static_investment_idx < len(row):
                item.staticInvestment = clean_number_string(str(row[static_investment_idx]))
            
            if dynamic_investment_idx >= 0 and dynamic_investment_idx < len(row):
                item.dynamicInvestment = clean_number_string(str(row[dynamic_investment_idx]))
            
            record.items.append(item)
            logger.info(f"[可研批复投资] 解析到数据: No={item.no}, Name={item.name}, Level={item.level}")
    
    logger.info(f"[可研批复投资] 共解析到 {len(record.items)} 条数据")
    return record


def parse_feasibility_review_investment(markdown_content: str) -> FeasibilityReviewInvestment:
    """
    解析可研评审投资估算
    
    包含字段:
    - No: 序号
    - name: 工程或费用名称
    - Level: 明细等级
    - staticInvestment: 静态投资（元）
    - dynamicInvestment: 动态投资（元）
    """
    record = FeasibilityReviewInvestment()
    
    tables = extract_table_with_rowspan_colspan(markdown_content)
    
    if not tables:
        logger.warning("[可研评审投资] 未能提取出任何表格内容")
        return record
    
    # 找到包含投资估算的表格
    target_table = None
    for table in tables:
        for row in table:
            row_text = " ".join([str(cell) for cell in row])
            if "工程或费用名称" in row_text or ("序号" in row_text and "静态投资" in row_text):
                target_table = table
                logger.info(f"[可研评审投资] 找到投资估算表格, 行数: {len(table)}")
                break
        if target_table:
            break
    
    if not target_table:
        logger.warning("[可研评审投资] 未找到包含投资估算的表格")
        return record
    
    # 识别表头行和列索引
    header_row_idx = -1
    no_idx = -1
    name_idx = -1
    static_investment_idx = -1
    dynamic_investment_idx = -1
    
    for row_idx, row in enumerate(target_table):
        row_text = " ".join([str(cell) for cell in row])
        
        if "工程或费用名称" in row_text or "序号" in row_text:
            header_row_idx = row_idx
            logger.debug(f"[可研评审投资] 找到表头行: 第{row_idx}行")
            
            for col_idx, cell in enumerate(row):
                cell_text = str(cell).strip()
                if "序号" in cell_text:
                    no_idx = col_idx
                elif "工程或费用名称" in cell_text or "名称" in cell_text:
                    name_idx = col_idx
                elif "静态投资" in cell_text:
                    static_investment_idx = col_idx
                elif "动态投资" in cell_text:
                    dynamic_investment_idx = col_idx
            
            logger.info(f"[可研评审投资] 列索引: 序号={no_idx}, 名称={name_idx}, "
                       f"静态投资={static_investment_idx}, 动态投资={dynamic_investment_idx}")
            break
    
    if header_row_idx == -1:
        logger.warning("[可研评审投资] 未找到表头行")
        return record
    
    # 解析数据行
    for row_idx in range(header_row_idx + 1, len(target_table)):
        row = target_table[row_idx]
        
        if len(row) < 2:
            continue
        
        if name_idx >= 0 and name_idx < len(row):
            name = str(row[name_idx]).strip()
            if not name or name in ["", "nan", "None"]:
                continue
            
            item = InvestmentItem()
            
            if no_idx >= 0 and no_idx < len(row):
                item.no = str(row[no_idx]).strip()
            
            item.name = name
            
            # 判断等级
            if item.no:
                item.level = determine_level(item.no + item.name)
            else:
                item.level = determine_level(item.name)
            
            # 提取投资金额
            if static_investment_idx >= 0 and static_investment_idx < len(row):
                item.staticInvestment = clean_number_string(str(row[static_investment_idx]))
            
            if dynamic_investment_idx >= 0 and dynamic_investment_idx < len(row):
                item.dynamicInvestment = clean_number_string(str(row[dynamic_investment_idx]))
            
            record.items.append(item)
            logger.info(f"[可研评审投资] 解析到数据: No={item.no}, Name={item.name}, Level={item.level}")
    
    logger.info(f"[可研评审投资] 共解析到 {len(record.items)} 条数据")
    return record


def parse_preliminary_approval_investment(markdown_content: str) -> PreliminaryApprovalInvestment:
    """
    解析初设批复概算投资
    
    包含字段:
    - No: 序号
    - name: 工程名称
    - Level: 明细等级
    - staticInvestment: 静态投资（元）
    - dynamicInvestment: 动态投资（元）
    
    Note: 需要包含合计行，合计的level为0
    """
    record = PreliminaryApprovalInvestment()
    
    tables = extract_table_with_rowspan_colspan(markdown_content)
    
    if not tables:
        logger.warning("[初设批复投资] 未能提取出任何表格内容")
        return record
    
    # 找到包含投资估算的表格
    target_table = None
    for table in tables:
        for row in table:
            row_text = " ".join([str(cell) for cell in row])
            if "工程名称" in row_text or ("序号" in row_text and "静态投资" in row_text):
                target_table = table
                logger.info(f"[初设批复投资] 找到投资估算表格, 行数: {len(table)}")
                break
        if target_table:
            break
    
    if not target_table:
        logger.warning("[初设批复投资] 未找到包含投资估算的表格")
        return record
    
    # 识别表头行和列索引
    header_row_idx = -1
    no_idx = -1
    name_idx = -1
    static_investment_idx = -1
    dynamic_investment_idx = -1
    
    for row_idx, row in enumerate(target_table):
        row_text = " ".join([str(cell) for cell in row])
        
        if "工程名称" in row_text or "序号" in row_text:
            header_row_idx = row_idx
            logger.debug(f"[初设批复投资] 找到表头行: 第{row_idx}行")
            
            for col_idx, cell in enumerate(row):
                cell_text = str(cell).strip()
                if "序号" in cell_text:
                    no_idx = col_idx
                elif "工程名称" in cell_text or "名称" in cell_text:
                    name_idx = col_idx
                elif "静态投资" in cell_text:
                    static_investment_idx = col_idx
                elif "动态投资" in cell_text:
                    dynamic_investment_idx = col_idx
            
            logger.info(f"[初设批复投资] 列索引: 序号={no_idx}, 名称={name_idx}, "
                       f"静态投资={static_investment_idx}, 动态投资={dynamic_investment_idx}")
            break
    
    if header_row_idx == -1:
        logger.warning("[初设批复投资] 未找到表头行")
        return record
    
    # 解析数据行
    for row_idx in range(header_row_idx + 1, len(target_table)):
        row = target_table[row_idx]
        
        if len(row) < 2:
            continue
        
        if name_idx >= 0 and name_idx < len(row):
            name = str(row[name_idx]).strip()
            if not name or name in ["", "nan", "None"]:
                continue
            
            item = InvestmentItem()
            
            if no_idx >= 0 and no_idx < len(row):
                item.no = str(row[no_idx]).strip()
            
            item.name = name
            
            # 判断等级
            if item.no:
                item.level = determine_level(item.no + item.name)
            else:
                item.level = determine_level(item.name)
            
            # 提取投资金额
            if static_investment_idx >= 0 and static_investment_idx < len(row):
                item.staticInvestment = clean_number_string(str(row[static_investment_idx]))
            
            if dynamic_investment_idx >= 0 and dynamic_investment_idx < len(row):
                item.dynamicInvestment = clean_number_string(str(row[dynamic_investment_idx]))
            
            record.items.append(item)
            logger.info(f"[初设批复投资] 解析到数据: No={item.no}, Name={item.name}, Level={item.level}")
    
    logger.info(f"[初设批复投资] 共解析到 {len(record.items)} 条数据")
    return record


def parse_investment_record(markdown_content: str, investment_type: Optional[str] = None):
    """
    解析投资估算记录（统一入口）
    
    Args:
        markdown_content: Markdown内容
        investment_type: 投资类型（可选，如果不提供则自动检测）
            - "feasibilityApprovalInvestment" - 可研批复
            - "feasibilityReviewInvestment" - 可研评审
            - "preliminaryApprovalInvestment" - 初设批复
    
    Returns:
        解析后的记录对象
    """
    # 如果没有指定类型，自动检测
    if not investment_type:
        investment_type = detect_investment_type(markdown_content)
    
    if not investment_type:
        logger.error("[投资估算] 无法识别投资估算类型")
        return None
    
    # 根据类型调用对应的解析函数
    if investment_type == "feasibilityApprovalInvestment":
        return parse_feasibility_approval_investment(markdown_content)
    elif investment_type == "feasibilityReviewInvestment":
        return parse_feasibility_review_investment(markdown_content)
    elif investment_type == "preliminaryApprovalInvestment":
        return parse_preliminary_approval_investment(markdown_content)
    else:
        logger.error(f"[投资估算] 未知的投资估算类型: {investment_type}")
        return None
