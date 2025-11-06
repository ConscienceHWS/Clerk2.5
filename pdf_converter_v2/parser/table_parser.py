# Copyright (c) Opendatalab. All rights reserved.

"""
表格解析模块 v2 - 独立版本，不依赖v1
"""

from typing import List
import re
from ..utils.logging_config import get_logger
from ..models.data_models import OperationalCondition, OperationalConditionV2

logger = get_logger("pdf_converter_v2.parser.table")


def parse_table_cell(cell_content: str) -> str:
    """解析表格单元格内容"""
    if not cell_content:
        return ""
    cell_content = re.sub(r'<[^>]+>', '', cell_content)
    cell_content = re.sub(r'\s+', ' ', cell_content).strip()
    return cell_content


def extract_table_data(markdown_content: str) -> List[List[List[str]]]:
    """从Markdown内容中提取表格数据"""
    tables: List[List[List[str]]] = []
    table_matches = re.findall(r'<table>(.*?)</table>', markdown_content, re.DOTALL)
    logger.debug(f"[extract_table_data] 共找到 {len(table_matches)} 个表格")
    
    for table_idx, table_content in enumerate(table_matches):
        table_rows: List[List[str]] = []
        tr_matches = re.findall(r'<tr[^>]*>(.*?)</tr>', table_content, re.DOTALL)
        logger.debug(f"[extract_table_data] 表格{table_idx}, 行数: {len(tr_matches)}")
        
        for row_idx, tr_content in enumerate(tr_matches):
            td_matches = re.findall(r'<td[^>]*>(.*?)</td>', tr_content)
            row: List[str] = [parse_table_cell(td) for td in td_matches]
            if row:
                table_rows.append(row)
        
        if table_rows:
            tables.append(table_rows)
    
    logger.debug(f"[extract_table_data] 总表格: {len(tables)}")
    return tables


def extract_table_with_rowspan_colspan(markdown_content: str) -> List[List[List[str]]]:
    """提取表格数据，处理rowspan和colspan属性"""
    tables: List[List[List[str]]] = []
    table_matches = re.findall(r'<table>(.*?)</table>', markdown_content, re.DOTALL)
    logger.debug(f"[extract_table_with_rowspan_colspan] 共找到 {len(table_matches)} 个表格")
    
    for table_idx, table_content in enumerate(table_matches):
        tr_matches = re.findall(r'<tr[^>]*>(.*?)</tr>', table_content, re.DOTALL)
        logger.debug(f"[extract_table_with_rowspan_colspan] 表格{table_idx}, 行数: {len(tr_matches)}")
        
        if not tr_matches:
            continue
        
        # 用于存储rowspan的值（跨行的单元格值）
        rowspan_values = {}  # {(row_idx, col_idx): (value, remaining_rows)}
        
        # 先构建一个矩阵来存储所有单元格
        max_cols = 0
        table_matrix = []
        
        for row_idx, tr_content in enumerate(tr_matches):
            # 找到所有td标签，包括属性
            td_pattern = r'<td[^>]*>(.*?)</td>'
            td_matches_with_attrs = re.finditer(td_pattern, tr_content, re.DOTALL)
            
            row = []
            col_idx = 0
            
            for td_match in td_matches_with_attrs:
                full_td = td_match.group(0)
                cell_content = td_match.group(1)
                
                # 提取rowspan和colspan属性
                rowspan_match = re.search(r'rowspan=["\']?(\d+)["\']?', full_td)
                colspan_match = re.search(r'colspan=["\']?(\d+)["\']?', full_td)
                
                rowspan = int(rowspan_match.group(1)) if rowspan_match else 1
                colspan = int(colspan_match.group(1)) if colspan_match else 1
                
                # 解析单元格内容
                cell_text = parse_table_cell(cell_content)
                
                # 跳过被rowspan占用的列
                while (row_idx, col_idx) in rowspan_values:
                    row.append(rowspan_values[(row_idx, col_idx)][0])  # 使用rowspan的值
                    remaining = rowspan_values[(row_idx, col_idx)][1] - 1
                    if remaining > 0:
                        rowspan_values[(row_idx + 1, col_idx)] = (rowspan_values[(row_idx, col_idx)][0], remaining)
                    del rowspan_values[(row_idx, col_idx)]
                    col_idx += 1
                
                # 添加单元格内容
                for c in range(colspan):
                    row.append(cell_text if c == 0 else "")
                    
                    # 如果有rowspan，记录到后续行
                    if rowspan > 1 and c == 0:
                        rowspan_values[(row_idx + 1, col_idx)] = (cell_text, rowspan - 1)
                    
                    col_idx += 1
            
            # 处理剩余的被rowspan占用的列
            while (row_idx, col_idx) in rowspan_values:
                row.append(rowspan_values[(row_idx, col_idx)][0])
                remaining = rowspan_values[(row_idx, col_idx)][1] - 1
                if remaining > 0:
                    rowspan_values[(row_idx + 1, col_idx)] = (rowspan_values[(row_idx, col_idx)][0], remaining)
                del rowspan_values[(row_idx, col_idx)]
                col_idx += 1
            
            if row:
                table_matrix.append(row)
                max_cols = max(max_cols, len(row))
                logger.debug(f"[extract_table_with_rowspan_colspan] 表格{table_idx} 第{row_idx}行, 内容: {row}")
        
        # 统一列数（可选，确保每行列数一致）
        for row in table_matrix:
            while len(row) < max_cols:
                row.append("")
        
        if table_matrix:
            tables.append(table_matrix)
    
    logger.debug(f"[extract_table_with_rowspan_colspan] 总表格: {len(tables)}")
    return tables


def parse_operational_conditions(markdown_content: str) -> List[OperationalCondition]:
    """解析工况信息表格"""
    conditions: List[OperationalCondition] = []
    
    # 查找工况信息相关的表格
    if "附件2 工况信息" not in markdown_content and "工况信息" not in markdown_content:
        logger.debug("[工况信息] 未找到工况信息标识")
        return conditions
    
    # 提取表格数据（支持rowspan和colspan）
    tables = extract_table_with_rowspan_colspan(markdown_content)
    
    if not tables:
        logger.warning("[工况信息] 未能提取出任何表格内容")
        return conditions
    
    # 查找工况信息表格（通常包含"检测时间"、"电压"、"电流"等关键词）
    for table in tables:
        if not table or len(table) < 2:
            continue
        
        # 检查表头是否包含工况信息的关键词
        header_row = table[0]
        has_operational_keywords = any(
            keyword in " ".join(header_row)
            for keyword in ["检测时间", "电压", "电流", "有功功率", "无功功率", "项目"]
        )
        
        if not has_operational_keywords:
            continue
        
        logger.info(f"[工况信息] 找到工况信息表格，行数: {len(table)}")
        
        # 找到表头行的列索引
        header_row = table[0]
        monitor_at_idx = -1
        project_idx = -1
        name_idx = -1
        voltage_idx = -1
        current_idx = -1
        active_power_idx = -1
        reactive_power_idx = -1
        
        for idx, cell in enumerate(header_row):
            cell_lower = cell.lower()
            if "检测时间" in cell or "监测时间" in cell:
                monitor_at_idx = idx
            elif "项目" in cell:
                # 项目列可能有colspan，需要找到实际的列
                if project_idx == -1:
                    project_idx = idx
                # 检查下一列是否是名称列（如果项目列colspan=2，下一列可能是名称）
                if idx + 1 < len(header_row) and name_idx == -1:
                    next_cell = header_row[idx + 1]
                    if not any(k in next_cell.lower() for k in ["电压", "电流", "有功", "无功", "检测"]):
                        name_idx = idx + 1
            elif "电压" in cell or "电压(kv)" in cell_lower:
                voltage_idx = idx
            elif "电流" in cell or "电流(a)" in cell_lower:
                current_idx = idx
            elif "有功功率" in cell or ("有功" in cell and "功率" in cell):
                active_power_idx = idx
            elif "无功功率" in cell or ("无功" in cell and "功率" in cell):
                reactive_power_idx = idx
            elif ("名称" in cell or "主变" in cell) and name_idx == -1:
                name_idx = idx
        
        logger.debug(f"[工况信息] 列索引: 检测时间={monitor_at_idx}, 项目={project_idx}, 名称={name_idx}, "
                    f"电压={voltage_idx}, 电流={current_idx}, 有功功率={active_power_idx}, 无功功率={reactive_power_idx}")
        
        # 处理数据行（从第二行开始，第一行是表头）
        current_monitor_at = ""
        current_project = ""
        
        for row_idx in range(1, len(table)):
            row = table[row_idx]
            if len(row) < 4:  # 至少需要检测时间、项目、名称等基本字段
                continue
            
            # 检测时间
            if monitor_at_idx >= 0 and monitor_at_idx < len(row) and row[monitor_at_idx].strip():
                current_monitor_at = row[monitor_at_idx].strip()
            
            # 项目名称
            if project_idx >= 0 and project_idx < len(row) and row[project_idx].strip():
                current_project = row[project_idx].strip()
            
            # 名称（如1#主变）
            name_value = ""
            if name_idx >= 0 and name_idx < len(row):
                name_value = row[name_idx].strip()
            elif project_idx >= 0 and project_idx + 1 < len(row):
                # 如果名称列在项目列后面
                name_value = row[project_idx + 1].strip()
            
            # 只有当名称存在时才创建工况信息记录（因为有rowspan的情况）
            if name_value and any(k in name_value for k in ["主变", "#"]):
                oc = OperationalCondition()
                oc.monitorAt = current_monitor_at
                oc.project = current_project
                oc.name = name_value
                
                # 电压
                if voltage_idx >= 0 and voltage_idx < len(row):
                    oc.voltage = row[voltage_idx].strip()
                
                # 电流
                if current_idx >= 0 and current_idx < len(row):
                    oc.current = row[current_idx].strip()
                
                # 有功功率
                if active_power_idx >= 0 and active_power_idx < len(row):
                    oc.activePower = row[active_power_idx].strip()
                
                # 无功功率
                if reactive_power_idx >= 0 and reactive_power_idx < len(row):
                    oc.reactivePower = row[reactive_power_idx].strip()
                
                conditions.append(oc)
                logger.debug(f"[工况信息] 解析到: {oc.to_dict()}")
        
        # 只处理第一个匹配的表格
        if conditions:
            break
    
    logger.info(f"[工况信息] 共解析到 {len(conditions)} 条工况信息")
    return conditions


def parse_operational_conditions_v2(markdown_content: str) -> List[OperationalConditionV2]:
    """解析工况信息表格（新格式：表1检测工况）
    
    表格结构：
    - 第一行：名称、时间，电压(kV)（colspan=2），电流(A)（colspan=2），有功(MW)（colspan=2），无功(Mvar)（colspan=2）
    - 第二行：最大值、最小值（重复4次）
    - 数据行：名称、时间、电压最大值、电压最小值、电流最大值、电流最小值、有功最大值、有功最小值、无功最大值、无功最小值
    """
    conditions: List[OperationalConditionV2] = []
    
    # 检查是否包含"表1检测工况"标识
    if "表1检测工况" not in markdown_content:
        logger.debug("[工况信息V2] 未找到'表1检测工况'标识")
        return conditions
    
    logger.debug("[工况信息V2] 检测到'表1检测工况'格式，第一列将映射到project字段，name字段为空")
    
    # 提取表格数据（支持rowspan和colspan）
    tables = extract_table_with_rowspan_colspan(markdown_content)
    
    if not tables:
        logger.warning("[工况信息V2] 未能提取出任何表格内容")
        return conditions
    
    # 查找包含"表1检测工况"的表格
    # 表格结构：第一行是名称、时间，然后是电压、电流、有功、无功（各占2列）
    for table in tables:
        if not table or len(table) < 3:  # 至少需要表头2行和数据1行
            continue
        
        # 检查第一行表头是否包含"名称"、"时间"、"电压"等关键词
        first_row = table[0]
        first_row_text = " ".join(first_row).lower()
        has_keywords = any(k in first_row_text for k in ["名称", "时间", "电压", "电流", "有功", "无功"])
        
        if not has_keywords:
            continue
        
        logger.info(f"[工况信息V2] 找到工况信息表格，行数: {len(table)}")
        
        # 列索引映射（根据表格结构）
        # 列0: 项目名称（映射到project字段）
        # 列1: 时间
        # 列2: 电压最大值
        # 列3: 电压最小值
        # 列4: 电流最大值
        # 列5: 电流最小值
        # 列6: 有功最大值
        # 列7: 有功最小值
        # 列8: 无功最大值
        # 列9: 无功最小值
        # 注意：对于"表1检测工况"格式，第一列映射到project，name字段为空
        
        project_idx = 0  # 第一列是项目名称（如"500kV 江黄Ⅰ线"）
        time_idx = 1
        voltage_max_idx = 2
        voltage_min_idx = 3
        current_max_idx = 4
        current_min_idx = 5
        active_power_max_idx = 6
        active_power_min_idx = 7
        reactive_power_max_idx = 8
        reactive_power_min_idx = 9
        
        # 从第三行开始解析数据（前两行是表头）
        logger.debug(f"[工况信息V2] 表格总行数: {len(table)}, 开始从第3行（索引2）解析数据行")
        for row_idx in range(2, len(table)):
            row = table[row_idx]
            logger.debug(f"[工况信息V2] 处理第{row_idx}行（索引{row_idx}）: 列数={len(row)}, 内容={row[:5]}...")  # 只打印前5列用于调试
            
            # 至少需要10列（名称、时间、电压max/min、电流max/min、有功max/min、无功max/min）
            if len(row) < 10:
                logger.warning(f"[工况信息V2] 第{row_idx}行列数不足10列，跳过: {len(row)}列")
                continue
            
            # 检查是否是数据行（第一列应该有项目名称，且不是"名称"、"最大值"、"最小值"等表头关键词）
            first_cell = row[project_idx].strip() if project_idx < len(row) else ""
            if not first_cell or first_cell in ["名称", "最大值", "最小值", "时间"]:
                logger.debug(f"[工况信息V2] 第{row_idx}行第一列为表头关键词或为空，跳过: '{first_cell}'")
                continue
            
            # 跳过完全空的行（但允许某些字段为空）
            if not any(cell.strip() for cell in row[:2]):  # 至少项目名称或时间应该有值
                logger.debug(f"[工况信息V2] 第{row_idx}行前两列为空，跳过")
                continue
            
            oc = OperationalConditionV2()
            
            # 项目名称（列0，映射到project字段）
            if project_idx < len(row):
                oc.project = row[project_idx].strip()
            
            # name字段为空（对于"表1检测工况"格式）
            oc.name = ""
            
            # 时间（列1）
            if time_idx < len(row):
                oc.monitorAt = row[time_idx].strip()
            
            # 电压最大值（列2）
            if voltage_max_idx < len(row):
                oc.maxVoltage = row[voltage_max_idx].strip()
            
            # 电压最小值（列3）
            if voltage_min_idx < len(row):
                oc.minVoltage = row[voltage_min_idx].strip()
            
            # 电流最大值（列4）
            if current_max_idx < len(row):
                oc.maxCurrent = row[current_max_idx].strip()
            
            # 电流最小值（列5）
            if current_min_idx < len(row):
                oc.minCurrent = row[current_min_idx].strip()
            
            # 有功功率最大值（列6）
            if active_power_max_idx < len(row):
                oc.maxActivePower = row[active_power_max_idx].strip()
            
            # 有功功率最小值（列7）
            if active_power_min_idx < len(row):
                oc.minActivePower = row[active_power_min_idx].strip()
            
            # 无功功率最大值（列8）
            if reactive_power_max_idx < len(row):
                oc.maxReactivePower = row[reactive_power_max_idx].strip()
            
            # 无功功率最小值（列9）
            if reactive_power_min_idx < len(row):
                oc.minReactivePower = row[reactive_power_min_idx].strip()
            
            # 添加记录（只要项目名称不为空）
            if oc.project:
                conditions.append(oc)
                logger.info(f"[工况信息V2] 解析到第{len(conditions)}条记录: project='{oc.project}', 时间='{oc.monitorAt}'")
            else:
                logger.warning(f"[工况信息V2] 第{row_idx}行项目名称为空，跳过该行: {row[:3]}")
        
        # 只处理第一个匹配的表格
        if conditions:
            break
    
    logger.info(f"[工况信息V2] 共解析到 {len(conditions)} 条工况信息")
    return conditions

