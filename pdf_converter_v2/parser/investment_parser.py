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
    
    # 合计行（包含"合 计"这种带空格的情况）
    text_no_space = text.replace(" ", "")
    if "合计" in text_no_space or "小计" in text_no_space:
        return "0"
    
    # 第一级: 大写中文数字
    # 匹配: "一、", "一，", "一.", "一 ", "一" (后面可以跟任意字符或结束)
    # 注意：需要排除"十一"、"十二"等多位数字，只匹配单个中文数字
    if re.match(r'^[一二三四五六七八九十]+[、，,.\s]', text):
        return "1"
    # 如果序号后面直接跟汉字（没有标点），也认为是第一级
    # 例如: "一变电工程", "二线路工程"
    if re.match(r'^[一二三四五六七八九十]+[\u4e00-\u9fa5]', text):
        return "1"
    # 如果只是单独的中文数字（没有后续字符），也是第一级
    # 例如: "一", "二", "三"
    if re.match(r'^[一二三四五六七八九十]+$', text):
        return "1"
    
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
    
    # 找到包含"四"（山西晋城周村）的投资估算表格
    # 因为用户只需要"四"及以下的数据
    target_table = None
    for table_idx, table in enumerate(tables):
        table_text = ""
        for row in table:
            table_text += " ".join([str(cell) for cell in row])
        # 移除空格后再匹配
        table_text_no_space = table_text.replace(" ", "")
        # 优先选择包含"四"（晋城周村）的表格
        if "四" in table_text and "周村" in table_text and "静态投资" in table_text_no_space:
            target_table = table
            logger.info(f"[可研批复投资] 找到包含'四'的投资估算表格 (表格{table_idx+1}), 行数: {len(table)}")
            break
        # 否则选择第一个包含投资估算的表格
        elif target_table is None and "工程或费用名称" in table_text_no_space and "静态投资" in table_text_no_space:
            target_table = table
            logger.info(f"[可研批复投资] 找到投资估算表格 (表格{table_idx+1}), 行数: {len(table)}")
    
    if not target_table:
        logger.warning("[可研批复投资] 未找到包含投资估算的表格")
        return record
    
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
    
    if header_row_idx == -1:
        logger.warning("[可研批复投资] 未找到表头行")
        return record
    
    # 解析数据行
    # 使用状态变量跟踪是否在"四"区域内
    in_section_four = False
    
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
            
            # 判断等级
            level_input = (no + name) if no else name
            level = determine_level(level_input)
            
            # 检查是否是大类（Level=1）
            if level == "1":
                no_cleaned = no.strip()
                # 检查是否进入或退出"四"区域
                if no_cleaned == "四" or "四、" in no or "四，" in no:
                    in_section_four = True
                    logger.info(f"[可研批复投资] 进入'四'区域: {name}")
                elif no_cleaned in ["一", "二", "三", "五", "六", "七", "八", "九", "十"] or \
                     any(prefix in no for prefix in ["一、", "二、", "三、", "五、", "六、", "七、", "八、", "九、", "十、"]):
                    # 遇到其他大类，退出"四"区域
                    if in_section_four:
                        logger.info(f"[可研批复投资] 退出'四'区域: {name}")
                    in_section_four = False
            
            # 只保留"四"区域内的数据
            if not in_section_four:
                logger.debug(f"[可研批复投资] 跳过非'四'区域数据: No={no}, Name={name}")
                continue
            
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
            if item.no:
                # 优先使用 no 判断等级
                item.level = determine_level(item.no)
                if not item.level:
                    # 如果 no 没有匹配，尝试使用 name
                    item.level = determine_level(item.name)
            else:
                item.level = determine_level(item.name)
            
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
            
            # 判断等级
            level_input = (item.no + item.name) if item.no else item.name
            item.level = determine_level(level_input)
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
            - "feasibilityApprovalInvestment" - 可研批复
            - "feasibilityReviewInvestment" - 可研评审
            - "preliminaryApprovalInvestment" - 初设批复
    
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
    if investment_type == "feasibilityApprovalInvestment":
        result = parse_feasibility_approval_investment(markdown_content)
    elif investment_type == "feasibilityReviewInvestment":
        result = parse_feasibility_review_investment(markdown_content)
    elif investment_type == "preliminaryApprovalInvestment":
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
