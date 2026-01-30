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
    InvestmentItem,
    FinalAccountRecord,
    FinalAccountItem
)
from .table_parser import extract_table_with_rowspan_colspan

logger = get_logger("pdf_converter_v2.parser.investment")


def detect_investment_type(markdown_content: str) -> Optional[str]:
    """
    检测投资估算表格类型
    
    Returns:
        str: 类型名称
            - "fsApproval" - 可研批复
            - "fsReview" - 可研评审
            - "pdApproval" - 初设批复
            - None - 无法识别
    """
    # 检查标题关键词
    if "可研批复" in markdown_content or "可行性研究报告的批复" in markdown_content:
        # 检查是否有建设规模相关列（可研批复特有）
        if "架空线" in markdown_content or "间隔" in markdown_content:
            logger.info("[投资估算] 检测到类型: 可研批复投资估算")
            return "fsApproval"
    
    if "可研评审" in markdown_content or "可行性研究报告的评审意见" in markdown_content:
        logger.info("[投资估算] 检测到类型: 可研评审投资估算")
        return "fsReview"
    
    if "初设批复" in markdown_content or "初步设计的批复" in markdown_content:
        logger.info("[投资估算] 检测到类型: 初设批复概算投资")
        return "pdApproval"
    
    logger.warning("[投资估算] 无法识别投资估算表格类型")
    return None


def determine_level(text: str, name: str = "", strict_mode: bool = True) -> str:
    """
    判断明细等级
    
    规则:
    - 大写中文数字(一、二、三等) -> 第一级（顶级大类）
      - strict_mode=True: 需要名称包含电压等级+输变电工程才是一级，否则降为二级
      - strict_mode=False: 中文数字直接判断为一级（用于 fsReview、pdApproval）
    - 小写阿拉伯数字(1、2、3等) -> 第二级  
    - 带括号的数字(1)、2)等) -> 第三级
    - 合计 -> 0
    
    Args:
        text: 序号或名称文本
        name: 可选，名称文本，用于辅助判断（区分顶级大类和子项）
        strict_mode: 是否使用严格模式（默认True，用于 fsApproval 区分顶级大类）
        
    Returns:
        str: "0"(合计), "1"(一级), "2"(二级), "3"(三级), ""(无法判断)
    """
    if not text:
        return ""
    
    text = text.strip()
    
    # 合计行（包含"合 计"这种带空格的情况）
    text_no_space = text.replace(" ", "")
    if "合计" in text_no_space or "小计" in text_no_space:
        return "0"
    
    # 第一级: 大写中文数字
    # 匹配: "一、", "一，", "一.", "一 ", "一" (后面可以跟任意字符或结束)
    # 注意：需要排除"十一"、"十二"等多位数字，只匹配单个中文数字
    is_chinese_numeral = False
    if re.match(r'^[一二三四五六七八九十]+[、，,.\s]', text):
        is_chinese_numeral = True
    # 如果序号后面直接跟汉字（没有标点），也可能是第一级
    # 例如: "一变电工程", "二线路工程"
    elif re.match(r'^[一二三四五六七八九十]+[\u4e00-\u9fa5]', text):
        is_chinese_numeral = True
    # 如果只是单独的中文数字（没有后续字符），也可能是第一级
    # 例如: "一", "二", "三"
    elif re.match(r'^[一二三四五六七八九十]+$', text):
        is_chinese_numeral = True
    
    if is_chinese_numeral:
        # 非严格模式：中文数字直接判断为一级（用于 fsReview、pdApproval）
        if not strict_mode:
            return "1"
        
        # 严格模式：进一步判断，区分顶级大类和子项目（用于 fsApproval）
        # 顶级大类特征：名称包含电压等级（如"220千伏"、"500kV"）+ 输变电工程
        # 子项目特征：简单的工程类型名称（变电工程、线路工程、配套通信工程）
        
        name_to_check = name if name else text
        
        # 1. 检查是否是顶级大类（包含电压等级 + 输变电工程）
        # 电压等级模式：220千伏、500kV、110kv、35千伏等
        has_voltage = bool(re.search(r'\d+\s*(千伏|kV|KV|kv)', name_to_check, re.IGNORECASE))
        has_project_type = "输变电" in name_to_check or "变电站" in name_to_check or "送出工程" in name_to_check
        
        if has_voltage and has_project_type:
            # 包含电压等级和工程类型，是顶级大类
            return "1"
        
        # 2. 检查是否是子项目（固定名称，人为错误可能把"3"写成"三"）
        # 子项目名称通常较短且是固定的工程类型
        subitem_exact = ["变电工程", "线路工程", "配套通信工程", "通信工程"]
        is_exact_subitem = name_to_check in subitem_exact
        
        if is_exact_subitem:
            # 完全匹配子项目名称，按二级处理
            logger.debug(f"[等级判断] 中文数字序号但名称是子项目，按二级处理: text={text}, name={name}")
            return "2"
        
        # 3. 其他情况：如果名称较长（>10字符），可能是顶级大类；否则按二级处理
        if len(name_to_check) > 10:
            # 较长的名称可能是顶级大类（即使没有匹配到电压等级模式）
            return "1"
        else:
            # 较短的名称，按二级处理
            logger.debug(f"[等级判断] 中文数字序号但名称较短，按二级处理: text={text}, name={name}")
            return "2"
    
    # 第二级: 小写阿拉伯数字
    # 匹配: "1、", "1，", "1.", "1 " (后面跟标点或空格)
    if re.match(r'^\d+[、，,.\s]', text) and not text.startswith('(') and not text.startswith('（'):
        return "2"
    # 如果数字后面直接跟汉字（没有标点），也认为是第二级
    # 例如: "1周村220kV变电站"
    if re.match(r'^\d+[\u4e00-\u9fa5]', text) and not text.startswith('(') and not text.startswith('（'):
        return "2"
    # 如果只是单独的阿拉伯数字（没有后续字符），也是第二级
    # 例如: "1", "2", "3"
    if re.match(r'^\d+$', text) and not text.startswith('(') and not text.startswith('（'):
        return "2"
    
    # 第三级: 带括号的数字，或者数字后跟右括号
    # 匹配: "(1)", "（1）", "1)", "1）"
    if re.match(r'^[(（]\d+[)）]', text):
        return "3"
    # 数字后跟右括号，如 "1)", "2)"
    if re.match(r'^\d+[)）]', text):
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
    
    # 找到所有投资估算表格并合并
    # 因为OCR可能将一个大表格拆分成多个<table>
    all_matching_tables = []
    for table_idx, table in enumerate(tables):
        table_text = ""
        for row in table:
            table_text += " ".join([str(cell) for cell in row])
        # 移除空格后再匹配
        table_text_no_space = table_text.replace(" ", "")
        # 选择包含"工程或费用名称"和"静态投资"的表格
        if "工程或费用名称" in table_text_no_space and "静态投资" in table_text_no_space:
            all_matching_tables.append((table_idx, table))
            logger.info(f"[可研批复投资] 找到投资估算表格 (表格{table_idx+1}), 行数: {len(table)}")
    
    if not all_matching_tables:
        logger.warning("[可研批复投资] 未找到包含投资估算的表格")
        return record
    
    # 如果只有一个表格，直接使用
    if len(all_matching_tables) == 1:
        target_table = all_matching_tables[0][1]
    else:
        # 多个表格：合并所有表格的数据行（跳过重复的表头行）
        logger.info(f"[可研批复投资] 发现 {len(all_matching_tables)} 个投资估算表格，将进行合并")
        target_table = []
        first_table = True
        for table_idx, table in all_matching_tables:
            if first_table:
                # 第一个表格：保留全部内容（包括表头）
                target_table.extend(table)
                first_table = False
            else:
                # 后续表格：跳过表头行（前几行包含"序号"、"工程或费用名称"等）
                header_end_idx = 0
                for row_idx, row in enumerate(table):
                    row_text = " ".join([str(cell) for cell in row]).replace(" ", "")
                    # 如果这行包含表头关键词，继续跳过
                    if "序号" in row_text or "工程或费用名称" in row_text or "建设规模" in row_text:
                        header_end_idx = row_idx + 1
                    # 如果第一列是中文数字（一、二、三...），说明是数据行开始
                    elif len(row) > 0:
                        first_cell = str(row[0]).strip()
                        if first_cell in ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]:
                            break
                # 只添加数据行
                target_table.extend(table[header_end_idx:])
                logger.debug(f"[可研批复投资] 表格{table_idx+1}: 跳过前{header_end_idx}行表头，添加{len(table)-header_end_idx}行数据")
        
        logger.info(f"[可研批复投资] 合并后总行数: {len(target_table)}")
    
    # 识别表头行和列索引
    # 注意：表格可能有多层表头（rowspan），需要扫描前几行来找到所有列名
    header_row_idx = -1
    no_idx = -1
    name_idx = -1
    overhead_line_idx = -1
    bay_idx = -1
    substation_idx = -1
    optical_cable_idx = -1
    static_investment_idx = -1
    dynamic_investment_idx = -1
    # 新增费用列索引
    construction_project_cost_idx = -1  # 建筑工程费
    equipment_purchase_cost_idx = -1  # 设备购置费
    installation_project_cost_idx = -1  # 安装工程费
    other_expenses_idx = -1  # 其他费用（合计）
    
    # 扫描前几行（最多5行）来识别列索引
    for row_idx in range(min(5, len(target_table))):
        row = target_table[row_idx]
        row_text = " ".join([str(cell) for cell in row])
        row_text_no_space = row_text.replace(" ", "")
        
        # 识别各列（遍历所有行的所有列）
        for col_idx, cell in enumerate(row):
            cell_text = str(cell).strip()
            cell_text_no_space = cell_text.replace(" ", "")
            
            if "序号" in cell_text and no_idx == -1:
                no_idx = col_idx
            elif ("工程或费用名称" in cell_text_no_space) and name_idx == -1:
                name_idx = col_idx
            elif "架空线" in cell_text_no_space and overhead_line_idx == -1:
                overhead_line_idx = col_idx
            elif "间隔" in cell_text and bay_idx == -1:
                bay_idx = col_idx
            elif "变电" in cell_text and substation_idx == -1:
                substation_idx = col_idx
            elif "光缆" in cell_text and optical_cable_idx == -1:
                optical_cable_idx = col_idx
            elif "静态投资" in cell_text_no_space and static_investment_idx == -1:
                static_investment_idx = col_idx
            elif "动态投资" in cell_text_no_space and dynamic_investment_idx == -1:
                dynamic_investment_idx = col_idx
            # 新增费用字段识别
            elif "建筑工程费" in cell_text_no_space and construction_project_cost_idx == -1:
                construction_project_cost_idx = col_idx
            elif "设备购置费" in cell_text_no_space and equipment_purchase_cost_idx == -1:
                equipment_purchase_cost_idx = col_idx
            elif "安装工程费" in cell_text_no_space and installation_project_cost_idx == -1:
                installation_project_cost_idx = col_idx
            elif ("其他费用" in cell_text_no_space or "合计" == cell_text_no_space) and other_expenses_idx == -1:
                # 其他费用列通常标题为"合计"或"其他费用"
                # 注意：表头可能有"合计"列在"其他费用"下面
                if "其他费用" in cell_text_no_space:
                    other_expenses_idx = col_idx
        
        # 如果这一行包含"序号"或"工程或费用名称"，记录为表头结束行
        if ("序号" in row_text or "工程或费用名称" in row_text_no_space) and header_row_idx == -1:
            header_row_idx = row_idx
    
    # 表头结束行应该是最后一个包含表头内容的行
    # 找到第一个数据行（通常是"一"、"二"等开头）
    for row_idx in range(min(5, len(target_table))):
        row = target_table[row_idx]
        if len(row) > 0:
            first_cell = str(row[0]).strip()
            # 如果第一列是中文数字或阿拉伯数字（不是"序号"），这是数据行
            if first_cell and first_cell not in ["序号", ""] and (first_cell in ["一", "二", "三", "四", "五"] or first_cell.isdigit()):
                header_row_idx = row_idx - 1
                logger.debug(f"[可研批复投资] 根据数据行确定表头结束于第{header_row_idx}行")
                break
    
    logger.info(f"[可研批复投资] 表头行: {header_row_idx}")
    logger.info(f"[可研批复投资] 列索引: 序号={no_idx}, 名称={name_idx}, "
               f"架空线={overhead_line_idx}, 间隔={bay_idx}, 变电={substation_idx}, "
               f"光缆={optical_cable_idx}, 静态投资={static_investment_idx}, 动态投资={dynamic_investment_idx}")
    logger.info(f"[可研批复投资] 费用列索引: 建筑工程费={construction_project_cost_idx}, "
               f"设备购置费={equipment_purchase_cost_idx}, 安装工程费={installation_project_cost_idx}, "
               f"其他费用={other_expenses_idx}")
    
    if header_row_idx == -1:
        logger.warning("[可研批复投资] 未找到表头行")
        return record
    
    # 解析数据行（输出全部数据，不再只筛选"四"区域）
    for row_idx in range(header_row_idx + 1, len(target_table)):
        row = target_table[row_idx]
        
        if len(row) < 3:
            continue
        
        # 检查是否是有效数据行（至少有名称）
        if name_idx >= 0 and name_idx < len(row):
            name = str(row[name_idx]).strip()
            if not name or name in ["", "nan", "None"]:
                continue
            
            # 提取序号
            no = ""
            if no_idx >= 0 and no_idx < len(row):
                no = str(row[no_idx]).strip()
            
            # 判断等级，传入 name 辅助区分顶级大类和子项
            level_input = (no + name) if no else name
            level = determine_level(level_input, name)
            
            item = InvestmentItem()
            item.no = no
            item.name = name
            item.level = level
            
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
            
            # 提取费用明细
            if construction_project_cost_idx >= 0 and construction_project_cost_idx < len(row):
                item.constructionProjectCost = clean_number_string(str(row[construction_project_cost_idx]))
            
            if equipment_purchase_cost_idx >= 0 and equipment_purchase_cost_idx < len(row):
                item.equipmentPurchaseCost = clean_number_string(str(row[equipment_purchase_cost_idx]))
            
            if installation_project_cost_idx >= 0 and installation_project_cost_idx < len(row):
                item.installationProjectCost = clean_number_string(str(row[installation_project_cost_idx]))
            
            if other_expenses_idx >= 0 and other_expenses_idx < len(row):
                item.otherExpenses = clean_number_string(str(row[other_expenses_idx]))
            
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
    
    注意：文档中可能包含多个表格，只解析"输变电工程建设规模及投资估算表"
    排除"总估算表"类型的表格
    """
    record = FeasibilityReviewInvestment()
    
    # 使用正则表达式查找表格及其前面的标题
    # 查找 "输变电工程" + "投资估算表" 的标题，排除 "总估算表"
    import re
    
    # 找到目标表格的标题位置
    # 标题格式如: # 山西晋城周村220kV输变电工程建设规模及投资估算表
    target_table_pattern = re.compile(
        r'#\s*[^#\n]*?(输变电工程|输变电|变电工程)[^#\n]*?(建设规模及)?投资估算表',
        re.IGNORECASE
    )
    
    # 排除"总估算表"的模式
    exclude_pattern = re.compile(r'总估算表', re.IGNORECASE)
    
    # 查找所有匹配的标题
    target_title_match = None
    for match in target_table_pattern.finditer(markdown_content):
        title_text = match.group(0)
        if not exclude_pattern.search(title_text):
            target_title_match = match
            logger.info(f"[可研评审投资] 找到目标表格标题: {title_text}")
            break
    
    if not target_title_match:
        logger.warning("[可研评审投资] 未找到'输变电工程投资估算表'标题")
        # 回退到原有逻辑
        tables = extract_table_with_rowspan_colspan(markdown_content)
        if not tables:
            logger.warning("[可研评审投资] 未能提取出任何表格内容")
            return record
        target_table = None
        for table in tables:
            for row in table:
                row_text = " ".join([str(cell) for cell in row])
                row_text_no_space = row_text.replace(" ", "")
                if "工程或费用名称" in row_text_no_space or ("序号" in row_text and "静态投资" in row_text_no_space):
                    target_table = table
                    logger.info(f"[可研评审投资] 回退: 找到投资估算表格, 行数: {len(table)}")
                    break
            if target_table:
                break
        if not target_table:
            logger.warning("[可研评审投资] 未找到包含投资估算的表格")
            return record
    else:
        # 提取标题后面到下一个标题之间的内容（包含目标表格）
        title_end = target_title_match.end()
        
        # 找到下一个标题或文档结束
        next_title_pattern = re.compile(r'\n#\s+[^#]')
        next_title_match = next_title_pattern.search(markdown_content, title_end)
        
        if next_title_match:
            section_content = markdown_content[target_title_match.start():next_title_match.start()]
        else:
            section_content = markdown_content[target_title_match.start():]
        
        logger.debug(f"[可研评审投资] 提取表格区域内容长度: {len(section_content)} 字符")
        
        # 从该区域提取表格
        tables = extract_table_with_rowspan_colspan(section_content)
        
        if not tables:
            logger.warning("[可研评审投资] 目标区域未能提取出任何表格内容")
            return record
        
        # 选择第一个有效表格
        target_table = None
        for table in tables:
            for row in table:
                row_text = " ".join([str(cell) for cell in row])
                row_text_no_space = row_text.replace(" ", "")
                if "工程或费用名称" in row_text_no_space or ("序号" in row_text and "静态投资" in row_text_no_space):
                    target_table = table
                    logger.info(f"[可研评审投资] 找到目标投资估算表格, 行数: {len(table)}")
                    break
            if target_table:
                break
        
        if not target_table:
            logger.warning("[可研评审投资] 目标区域未找到包含投资估算的表格")
            return record
    
    # 识别表头行和列索引（多行表头处理）
    # 这个表格有多行表头（rowspan/colspan），需要扫描前几行来找到所有列索引
    no_idx = -1
    name_idx = -1
    static_investment_idx = -1
    dynamic_investment_idx = -1
    header_row_idx = -1
    
    # 扫描前5行查找列索引
    scan_rows = min(5, len(target_table))
    for row_idx in range(scan_rows):
        row = target_table[row_idx]
        for col_idx, cell in enumerate(row):
            cell_text = str(cell).strip()
            cell_text_no_space = cell_text.replace(" ", "")
            
            if "序号" in cell_text and no_idx == -1:
                no_idx = col_idx
            elif ("工程或费用名称" in cell_text_no_space or "工程名称" in cell_text_no_space) and name_idx == -1:
                name_idx = col_idx
            elif "静态投资" in cell_text_no_space and static_investment_idx == -1:
                static_investment_idx = col_idx
            elif "动态投资" in cell_text_no_space and dynamic_investment_idx == -1:
                dynamic_investment_idx = col_idx
    
    logger.info(f"[可研评审投资] 列索引: 序号={no_idx}, 名称={name_idx}, "
               f"静态投资={static_investment_idx}, 动态投资={dynamic_investment_idx}")
    
    # 确定表头结束行（第一个数据行的前一行）
    # 数据行特征：第一列是中文数字（一、二、三）或阿拉伯数字
    for row_idx in range(len(target_table)):
        row = target_table[row_idx]
        if len(row) > 0:
            first_cell = str(row[0]).strip()
            # 检查是否是数据行（以中文数字或阿拉伯数字开头）
            if re.match(r'^[一二三四五六七八九十]+$', first_cell) or re.match(r'^\d+$', first_cell):
                # 排除表头行（检查第二列是否是表头关键词）
                if len(row) > 1:
                    second_cell = str(row[1]).strip().replace(" ", "")
                    if second_cell not in ["工程或费用名称", "工程名称", "名称", ""]:
                        header_row_idx = row_idx - 1
                        logger.debug(f"[可研评审投资] 确定表头结束行: 第{header_row_idx}行")
                        break
    
    if header_row_idx == -1:
        header_row_idx = 2  # 默认假设前3行是表头
        logger.debug(f"[可研评审投资] 使用默认表头结束行: 第{header_row_idx}行")
    
    # 解析数据行
    for row_idx in range(header_row_idx + 1, len(target_table)):
        row = target_table[row_idx]
        
        if len(row) < 2:
            continue
        
        if name_idx >= 0 and name_idx < len(row):
            name = str(row[name_idx]).strip()
            if not name or name in ["", "nan", "None"]:
                continue
            
            # 跳过重复的表头行
            name_no_space = name.replace(" ", "")
            if name_no_space in ["工程或费用名称", "工程名称", "名称"]:
                logger.debug(f"[可研评审投资] 跳过表头行: {name}")
                continue
            
            item = InvestmentItem()
            
            if no_idx >= 0 and no_idx < len(row):
                item.no = str(row[no_idx]).strip()
            
            # 跳过表头中的序号列
            if item.no == "序号":
                continue
            
            item.name = name
            
            # 判断等级 - 使用 no 和 name 分别判断
            # fsReview 使用非严格模式，中文数字直接判断为一级
            if item.no:
                # 优先使用 no 判断等级
                item.level = determine_level(item.no, item.name, strict_mode=False)
                if not item.level:
                    # 如果 no 没有匹配，尝试使用 name
                    item.level = determine_level(item.name, item.name, strict_mode=False)
            else:
                item.level = determine_level(item.name, item.name, strict_mode=False)
            
            # 提取投资金额
            if static_investment_idx >= 0 and static_investment_idx < len(row):
                item.staticInvestment = clean_number_string(str(row[static_investment_idx]))
            
            if dynamic_investment_idx >= 0 and dynamic_investment_idx < len(row):
                item.dynamicInvestment = clean_number_string(str(row[dynamic_investment_idx]))
            
            record.items.append(item)
            logger.info(f"[可研评审投资] 解析到数据: No={item.no}, Name={item.name}, Level={item.level}, "
                       f"静态投资={item.staticInvestment}, 动态投资={item.dynamicInvestment}")
    
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
    logger.info("[初设批复投资] ========== 开始解析初设批复概算投资 ==========")
    logger.debug(f"[初设批复投资] Markdown内容长度: {len(markdown_content)} 字符")
    
    record = PreliminaryApprovalInvestment()
    
    logger.info("[初设批复投资] 开始提取表格...")
    tables = extract_table_with_rowspan_colspan(markdown_content)
    logger.info(f"[初设批复投资] 提取到 {len(tables) if tables else 0} 个表格")
    
    if not tables:
        logger.warning("[初设批复投资] 未能提取出任何表格内容")
        return record
    
    # 找到包含投资估算的表格
    logger.info("[初设批复投资] 开始查找投资估算表格...")
    target_table = None
    for table_idx, table in enumerate(tables):
        logger.debug(f"[初设批复投资] 检查表格 {table_idx + 1}/{len(tables)}, 行数: {len(table)}")
        for row_idx, row in enumerate(table):
            row_text = " ".join([str(cell) for cell in row])
            # 移除空格后再匹配，以处理OCR可能产生的空格
            row_text_no_space = row_text.replace(" ", "")
            
            # 输出前几行用于调试
            if row_idx < 3:
                logger.debug(f"[初设批复投资] 表格{table_idx+1} 第{row_idx+1}行: {row_text[:100]}")
            
            if "工程名称" in row_text_no_space or ("序号" in row_text and "静态投资" in row_text_no_space):
                target_table = table
                logger.info(f"[初设批复投资] ✓ 找到投资估算表格 (表格{table_idx+1}), 行数: {len(table)}")
                logger.debug(f"[初设批复投资] 匹配行内容: {row_text}")
                break
        if target_table:
            break
    
    if not target_table:
        logger.warning("[初设批复投资] ✗ 未找到包含投资估算的表格")
        logger.warning("[初设批复投资] 查找条件: 包含'工程名称' 或 ('序号' 且 '静态投资')")
        return record
    
    # 识别表头行和列索引
    logger.info("[初设批复投资] 开始识别表头行和列索引...")
    header_row_idx = -1
    no_idx = -1
    name_idx = -1
    static_investment_idx = -1
    dynamic_investment_idx = -1
    
    for row_idx, row in enumerate(target_table):
        row_text = " ".join([str(cell) for cell in row])
        # 移除空格后再匹配，以处理OCR可能产生的空格
        row_text_no_space = row_text.replace(" ", "")
        
        logger.debug(f"[初设批复投资] 检查第{row_idx}行: {row_text[:80]}")
        
        if "工程名称" in row_text_no_space or "序号" in row_text:
            header_row_idx = row_idx
            logger.info(f"[初设批复投资] ✓ 找到表头行: 第{row_idx}行")
            logger.debug(f"[初设批复投资] 表头内容: {row}")
            
            for col_idx, cell in enumerate(row):
                cell_text = str(cell).strip()
                # 移除空格后再匹配，以处理OCR可能产生的空格
                cell_text_no_space = cell_text.replace(" ", "")
                
                logger.debug(f"[初设批复投资] 列{col_idx}: '{cell_text}' (去空格: '{cell_text_no_space}')")
                
                if "序号" in cell_text:
                    no_idx = col_idx
                    logger.debug(f"[初设批复投资] → 序号列: {col_idx}")
                elif "工程名称" in cell_text_no_space or "名称" in cell_text:
                    name_idx = col_idx
                    logger.debug(f"[初设批复投资] → 名称列: {col_idx}")
                elif "静态投资" in cell_text_no_space:
                    static_investment_idx = col_idx
                    logger.debug(f"[初设批复投资] → 静态投资列: {col_idx}")
                elif "动态投资" in cell_text_no_space:
                    dynamic_investment_idx = col_idx
                    logger.debug(f"[初设批复投资] → 动态投资列: {col_idx}")
            
            logger.info(f"[初设批复投资] ✓ 列索引识别完成: 序号={no_idx}, 名称={name_idx}, "
                       f"静态投资={static_investment_idx}, 动态投资={dynamic_investment_idx}")
            break
    
    if header_row_idx == -1:
        logger.warning("[初设批复投资] ✗ 未找到表头行")
        logger.warning("[初设批复投资] 查找条件: 包含'工程名称' 或 '序号'")
        return record
    
    # 解析数据行
    logger.info(f"[初设批复投资] 开始解析数据行 (从第{header_row_idx + 1}行到第{len(target_table)}行)...")
    parsed_count = 0
    skipped_count = 0
    
    for row_idx in range(header_row_idx + 1, len(target_table)):
        row = target_table[row_idx]
        
        logger.debug(f"[初设批复投资] 处理第{row_idx}行, 列数: {len(row)}")
        
        if len(row) < 2:
            logger.debug(f"[初设批复投资] 跳过第{row_idx}行: 列数不足 ({len(row)} < 2)")
            skipped_count += 1
            continue
        
        if name_idx >= 0 and name_idx < len(row):
            name = str(row[name_idx]).strip()
            logger.debug(f"[初设批复投资] 第{row_idx}行名称: '{name}'")
            
            if not name or name in ["", "nan", "None"]:
                logger.debug(f"[初设批复投资] 跳过第{row_idx}行: 名称为空")
                skipped_count += 1
                continue
            
            item = InvestmentItem()
            
            if no_idx >= 0 and no_idx < len(row):
                item.no = str(row[no_idx]).strip()
            
            item.name = name
            
            # 判断等级 - pdApproval 使用非严格模式，中文数字直接判断为一级
            level_input = (item.no + item.name) if item.no else item.name
            item.level = determine_level(level_input, item.name, strict_mode=False)
            logger.debug(f"[初设批复投资] 等级判断: '{level_input}' -> Level={item.level}")
            
            # 提取投资金额
            if static_investment_idx >= 0 and static_investment_idx < len(row):
                raw_static = str(row[static_investment_idx])
                item.staticInvestment = clean_number_string(raw_static)
                logger.debug(f"[初设批复投资] 静态投资: '{raw_static}' -> '{item.staticInvestment}'")
            
            if dynamic_investment_idx >= 0 and dynamic_investment_idx < len(row):
                raw_dynamic = str(row[dynamic_investment_idx])
                item.dynamicInvestment = clean_number_string(raw_dynamic)
                logger.debug(f"[初设批复投资] 动态投资: '{raw_dynamic}' -> '{item.dynamicInvestment}'")
            
            record.items.append(item)
            parsed_count += 1
            logger.info(f"[初设批复投资] ✓ 解析到数据 #{parsed_count}: No={item.no}, Name={item.name}, Level={item.level}, "
                       f"静态={item.staticInvestment}, 动态={item.dynamicInvestment}")
        else:
            logger.debug(f"[初设批复投资] 跳过第{row_idx}行: name_idx={name_idx} 超出范围 (行长度={len(row)})")
            skipped_count += 1
    
    logger.info(f"[初设批复投资] ========== 解析完成 ==========")
    logger.info(f"[初设批复投资] 成功解析: {parsed_count} 条")
    logger.info(f"[初设批复投资] 跳过: {skipped_count} 条")
    logger.info(f"[初设批复投资] 总计: {len(record.items)} 条数据")
    
    return record


def parse_investment_record(markdown_content: str, investment_type: Optional[str] = None):
    """
    解析投资估算记录（统一入口）
    
    Args:
        markdown_content: Markdown内容
        investment_type: 投资类型（可选，如果不提供则自动检测）
            - "fsApproval" - 可研批复
            - "fsReview" - 可研评审
            - "pdApproval" - 初设批复
    
    Returns:
        解析后的记录对象
    """
    logger.info("=" * 80)
    logger.info("[投资估算] 开始解析投资估算记录")
    logger.info(f"[投资估算] Markdown内容长度: {len(markdown_content)} 字符")
    
    # 如果没有指定类型，自动检测
    if not investment_type:
        logger.info("[投资估算] 未指定类型，开始自动检测...")
        investment_type = detect_investment_type(markdown_content)
        logger.info(f"[投资估算] 自动检测结果: {investment_type}")
    else:
        logger.info(f"[投资估算] 指定类型: {investment_type}")
    
    if not investment_type:
        logger.error("[投资估算] 无法识别投资估算类型")
        logger.error(f"[投资估算] Markdown前500字符: {markdown_content[:500]}")
        return None
    
    # 根据类型调用对应的解析函数
    logger.info(f"[投资估算] 调用解析函数: {investment_type}")
    
    result = None
    if investment_type == "fsApproval" or investment_type == "safety_fsApproval":
        # fsApproval 和 safety_fsApproval 使用相同的解析逻辑
        result = parse_feasibility_approval_investment(markdown_content)
    elif investment_type == "fsReview":
        result = parse_feasibility_review_investment(markdown_content)
    elif investment_type == "pdApproval":
        result = parse_preliminary_approval_investment(markdown_content)
    else:
        logger.error(f"[投资估算] 未知的投资估算类型: {investment_type}")
        return None
    
    if result:
        logger.info(f"[投资估算] 解析完成，返回对象类型: {type(result).__name__}")
        logger.info(f"[投资估算] 记录数量: {len(result.items)}")
    else:
        logger.error("[投资估算] 解析函数返回 None")
    
    logger.info("=" * 80)
    return result


def parse_final_account_record(markdown_content: str) -> Optional[FinalAccountRecord]:
    """
    解析决算报告中的单项工程投资完成情况表格
    
    从OCR输出的Markdown中提取表格数据：
    - 表格结构：费用项目 | 概算金额 | 决算金额(审定-不含税) | 增值税额 | 超节支金额 | 超节支率
    - 需要提取4个单项工程的投资完成情况
    
    Args:
        markdown_content: OCR转换后的Markdown内容
    
    Returns:
        FinalAccountRecord 对象，包含所有单项工程的费用明细
    """
    logger.info("=" * 80)
    logger.info("[决算报告] 开始解析决算报告")
    logger.info(f"[决算报告] Markdown内容长度: {len(markdown_content)} 字符")
    
    record = FinalAccountRecord()
    
    # 使用正则表达式提取单项工程名称和对应的表格
    # 匹配模式：数字序号 + 工程名称（在"单项工程的投资完成情况"章节内）
    project_patterns = [
        # 匹配 "1、周村 220kV 输变电工程变电站新建工程" 格式
        (r'(\d+)[、\.．]\s*(.+?(?:工程|扩建))(?:\n|$)', 1),
        # 匹配 "# 1、周村220kV变电站新建工程" 格式（带标题标记）
        (r'#\s*(\d+)[、\.．]\s*(.+?(?:工程|扩建))(?:\n|$)', 2),
    ]
    
    # 找到"单项工程的投资完成情况"章节的起始位置
    section_start = 0
    section_patterns = [
        r'单项工程的?(?:投资)?完成情况',
        r'#\s*单项工程',
    ]
    for pattern in section_patterns:
        match = re.search(pattern, markdown_content)
        if match:
            section_start = match.start()
            logger.info(f"[决算报告] 找到单项工程章节起始位置: {section_start}")
            break
    
    # 找到所有项目标题及其位置
    project_positions = []
    for pattern, priority in project_patterns:
        for match in re.finditer(pattern, markdown_content):
            # 只处理单项工程章节内的项目
            if match.start() < section_start:
                continue
            project_no = int(match.group(1))
            project_name = match.group(2).strip()
            # 清理项目名称中的多余空格和特殊字符
            project_name = re.sub(r'\s+', '', project_name)
            project_name = re.sub(r'\\[()\[\]]', '', project_name)
            # 清理LaTeX数学公式格式
            project_name = re.sub(r'\\mathrm\{([^}]+)\}', r'\1', project_name)
            project_name = re.sub(r'\\[a-zA-Z]+', '', project_name)
            project_positions.append({
                "no": project_no,
                "name": project_name,
                "start": match.start(),
                "end": match.end(),
                "priority": priority
            })
    
    # 按位置排序并去重
    project_positions.sort(key=lambda x: x["start"])
    seen_positions = set()
    unique_projects = []
    for proj in project_positions:
        # 避免重复的项目（位置相近的同名项目）
        key = (proj["no"], proj["start"] // 100)
        if key not in seen_positions:
            seen_positions.add(key)
            unique_projects.append(proj)
    
    logger.info(f"[决算报告] 找到 {len(unique_projects)} 个单项工程")
    for proj in unique_projects:
        logger.debug(f"[决算报告] 项目 {proj['no']}: {proj['name']}")
    
    # 提取HTML表格及其位置
    table_pattern = r'<table[^>]*>(.*?)</table>'
    table_matches = list(re.finditer(table_pattern, markdown_content, re.DOTALL | re.IGNORECASE))
    logger.info(f"[决算报告] 找到 {len(table_matches)} 个HTML表格")
    
    # 解析每个表格
    for table_idx, table_match in enumerate(table_matches):
        table_html = table_match.group(1)
        table_pos = table_match.start()
        
        # 检查是否为单项工程投资完成情况表格
        if not _is_final_account_table(table_html, table_pos, section_start):
            logger.debug(f"[决算报告] 表格 {table_idx + 1} 不是单项工程投资完成情况表格，跳过")
            continue
        
        # 查找最近的项目
        matched_project = None
        for proj in unique_projects:
            if proj["end"] < table_pos:
                matched_project = proj
        
        if not matched_project:
            # 如果没有找到匹配的项目，使用表格索引作为项目序号
            logger.warning(f"[决算报告] 表格 {table_idx + 1} 未找到对应的项目名称")
            matched_project = {"no": table_idx + 1, "name": f"未知工程{table_idx + 1}"}
        
        logger.info(f"[决算报告] 解析表格 {table_idx + 1}，关联项目: {matched_project['no']}-{matched_project['name']}")
        
        # 解析表格内容
        items = _parse_final_account_table_html(table_html, matched_project["no"], matched_project["name"])
        record.items.extend(items)
    
    logger.info(f"[决算报告] 解析完成，共 {len(record.items)} 条记录")
    logger.info("=" * 80)
    
    return record


def _is_final_account_table(table_html: str, table_pos: int, section_start: int) -> bool:
    """
    判断表格是否为单项工程投资完成情况表格
    
    特征：
    1. 位于"单项工程的投资完成情况"章节内
    2. 包含"费用项目"、"概算金额"、"决算金额"、"超"、"节"等关键词
    
    Args:
        table_html: 表格HTML内容
        table_pos: 表格在Markdown中的位置
        section_start: 单项工程章节的起始位置
    """
    # 表格必须在单项工程章节内
    if table_pos < section_start:
        return False
    
    table_text = table_html.lower()
    
    # 必须包含的关键词
    required_keywords = ["概算金额", "决算金额"]
    # 至少包含一个的关键词
    optional_keywords = ["费用项目", "建筑安装", "设备购置", "其他费用", "审定金额"]
    
    has_required = all(kw.lower() in table_text for kw in required_keywords)
    has_optional = any(kw.lower() in table_text for kw in optional_keywords)
    
    return has_required and has_optional


def _parse_final_account_table_html(table_html: str, project_no: int, project_name: str) -> List[FinalAccountItem]:
    """
    解析HTML表格内容
    
    表格结构：
    费用项目 | 概算金额 | 审定金额(不含税) | 增值税额 | 超节支金额 | 超节支率
    
    Args:
        table_html: HTML表格内容
        project_no: 项目序号
        project_name: 项目名称
    
    Returns:
        FinalAccountItem 列表
    """
    items = []
    
    # 提取所有行
    row_pattern = r'<tr[^>]*>(.*?)</tr>'
    rows = re.findall(row_pattern, table_html, re.DOTALL | re.IGNORECASE)
    
    if not rows:
        return items
    
    # 提取每行的单元格
    cell_pattern = r'<td[^>]*>(.*?)</td>'
    
    # 跳过表头行（通常前2-3行是表头）
    data_start_idx = 0
    for i, row in enumerate(rows):
        cells = re.findall(cell_pattern, row, re.DOTALL | re.IGNORECASE)
        row_text = " ".join(cells).lower()
        # 检测数据开始行（包含"建筑安装"等费用项目名称）
        if "建筑安装" in row_text or "设备购置" in row_text or "其他费用" in row_text:
            data_start_idx = i
            break
        # 跳过表头行（包含"1"、"2"、"3"等列序号）
        if re.match(r'^[\d\s=\-/]+$', row_text.replace(" ", "")):
            continue
    
    # 解析数据行
    for row in rows[data_start_idx:]:
        cells = re.findall(cell_pattern, row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 2:
            continue
        
        # 清理单元格内容
        cells = [_clean_cell_text(cell) for cell in cells]
        
        # 跳过空行
        if not any(cells):
            continue
        
        # 获取费用项目名称（第一列）
        fee_name = cells[0] if len(cells) > 0 else ""
        
        # 跳过合计行
        if any(kw in fee_name for kw in ["合计", "总计", "小计"]):
            continue
        
        # 只保留主要费用项目
        valid_fee_names = ["建筑安装工程", "建筑安装", "设备购置", "其他费用"]
        is_valid = any(kw in fee_name for kw in valid_fee_names)
        if not is_valid:
            continue
        
        # 创建记录项
        item = FinalAccountItem()
        item.no = project_no
        item.name = project_name
        item.feeName = fee_name
        
        # 解析数值列
        # 根据列数确定索引
        if len(cells) >= 6:
            item.estimatedCost = _parse_number_str(cells[1])
            item.approvedFinalAccountExcludingVat = _parse_number_str(cells[2])
            item.vatAmount = _parse_number_str(cells[3])
            item.costVariance = _parse_number_str(cells[4])
            item.varianceRate = _parse_rate_str(cells[5])
        elif len(cells) >= 5:
            item.estimatedCost = _parse_number_str(cells[1])
            item.approvedFinalAccountExcludingVat = _parse_number_str(cells[2])
            item.vatAmount = _parse_number_str(cells[3])
            item.costVariance = _parse_number_str(cells[4])
            item.varianceRate = ""
        
        items.append(item)
        logger.debug(f"[决算报告] 解析记录: {project_name} - {fee_name} = {item.estimatedCost}")
    
    return items


def _clean_cell_text(cell: str) -> str:
    """清理单元格文本，移除HTML标签和多余空格"""
    # 移除HTML标签
    text = re.sub(r'<[^>]+>', '', cell)
    # 移除多余空格
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _parse_number_str(value: str) -> str:
    """解析数字字符串，保留原始精度"""
    if not value or not value.strip():
        return "0"
    value = value.strip()
    # 移除千分位逗号
    value = value.replace(',', '')
    # 移除非数字字符（保留负号和小数点）
    cleaned = re.sub(r'[^\d.\-]', '', value)
    if not cleaned or cleaned == '-':
        return "0"
    return cleaned


def _parse_rate_str(value: str) -> str:
    """解析百分比字符串"""
    if not value or not value.strip():
        return "0%"
    value = value.strip()
    if '%' not in value:
        # 提取数字部分并添加百分号
        num_str = re.sub(r'[^\d.\-]', '', value)
        if num_str and num_str != '-':
            return f"{num_str}%"
        return "0%"
    return value
