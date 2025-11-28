# Copyright (c) Opendatalab. All rights reserved.

"""电磁检测记录解析模块 v2 - 独立版本"""

from typing import List
import re
from ..utils.logging_config import get_logger
from ..models.data_models import ElectromagneticDetectionRecord, ElectromagneticData
from .table_parser import extract_table_with_rowspan_colspan

logger = get_logger("pdf_converter_v2.parser.electromagnetic")


def validate_height(value: str) -> str:
    """校验高度值格式
    高度可以为空，但不应包含冒号（排除时间格式如 "14:50"）
    
    Args:
        value: 原始高度值
        
    Returns:
        校验后的高度值，如果包含冒号则返回空字符串
    """
    if not value or not value.strip():
        return ""
    
    value = value.strip()
    
    # 如果包含冒号，认为是时间格式，返回空字符串
    if ':' in value:
        logger.warning(f"[电磁检测] 高度值包含冒号（可能是时间格式），已忽略: '{value}'")
        return ""
    
    return value


def calculate_average(values: List[str]) -> str:
    """计算平均值，处理空值和无效值"""
    numeric_values = []
    for val in values:
        if val and val.strip():
            # 尝试提取数字（可能包含单位）
            try:
                # 移除可能的单位（如V/m, T等）和空格
                cleaned = re.sub(r'[^\d.\-]', '', val.strip())
                if cleaned:
                    num = float(cleaned)
                    numeric_values.append(num)
            except (ValueError, AttributeError):
                continue
    
    if numeric_values:
        avg = sum(numeric_values) / len(numeric_values)
        # 保留原始格式，如果是整数则返回整数格式
        if avg == int(avg):
            return str(int(avg))
        else:
            # 保留适当的小数位
            return f"{avg:.3f}".rstrip('0').rstrip('.')
    return ""


def parse_electromagnetic_detection_record(markdown_content: str) -> ElectromagneticDetectionRecord:
    """解析电磁检测记录"""
    record = ElectromagneticDetectionRecord()
    
    # 首先从OCR关键词注释中提取项目名称（优先级高，因为OCR可能识别到了表格中缺失的信息）
    # 先提取Markdown关键词补充（优先级高）
    md_keywords_comment_match = re.search(r'<!--\s*Markdown关键词补充:(.*?)-->', markdown_content, re.DOTALL)
    if md_keywords_comment_match:
        keywords_text = md_keywords_comment_match.group(1)
        logger.info("[电磁检测] 发现Markdown关键词补充，开始提取（优先级高）")
        
        # 提取项目名称
        project_match = re.search(r'项目名称[:：]([^\n]+)', keywords_text)
        if project_match:
            record.project = project_match.group(1).strip()
            logger.debug(f"[电磁检测] 从Markdown关键词补充提取到项目名称: {record.project}")
    
    # 然后提取OCR关键词补充（优先级低，只在字段为空时补充）
    ocr_keywords_comment_match = re.search(r'<!--\s*OCR关键词补充:(.*?)-->', markdown_content, re.DOTALL)
    if ocr_keywords_comment_match:
        keywords_text = ocr_keywords_comment_match.group(1)
        logger.info("[电磁检测] 发现OCR关键词补充，开始提取（优先级低，仅在字段为空时补充）")
        
        # 提取项目名称（仅在字段为空时）
        project_match = re.search(r'项目名称[:：]([^\n]+)', keywords_text)
        if project_match and (not record.project or not record.project.strip()):
            record.project = project_match.group(1).strip()
            logger.debug(f"[电磁检测] 从OCR关键词补充提取到项目名称: {record.project}")
    
    tables = extract_table_with_rowspan_colspan(markdown_content)
    
    if not tables:
        logger.warning(f"[电磁检测] 未能提取出任何表格内容")
        return record

    # 定义元数据标签关键词，用于识别标签（避免将标签误认为值）
    METADATA_LABELS = {"项目名称", "监测依据", "仪器名称", "仪器型号", "仪器编号", 
                       "测量高度", "检测高度", "检测环境条件", "测点分布示意图", 
                       "工况及工程信息", "备注", "备注："}
    
    def find_next_non_empty_value(row: List[str], start_idx: int) -> tuple[str, int]:
        """从指定索引开始查找下一个非空值（遇到下一个标签时停止）
        
        Args:
            row: 行数据
            start_idx: 起始索引（标签所在位置）
            
        Returns:
            (value, next_idx): 找到的值和下一个索引位置
        """
        for j in range(start_idx + 1, len(row)):
            cell_value = row[j].strip() if row[j] else ""
            if cell_value:
                # 如果找到的值是另一个标签，说明当前标签没有值，停止查找
                # 但要注意：标签可能包含在值中（如"监测依据"可能出现在"☐HJ681-2013"中），所以要精确匹配
                is_label = False
                for label in METADATA_LABELS:
                    # 精确匹配：单元格值完全等于标签，或者单元格值以标签开头且后面是冒号等分隔符
                    if cell_value == label or cell_value.startswith(label + ":") or cell_value.startswith(label + "："):
                        is_label = True
                        break
                
                if is_label:
                    return "", j  # 返回空值和下一个标签的位置
                # 找到非标签的值，返回它
                return cell_value, j + 1
        return "", len(row)
    
    # 查找包含头部信息的表格（可能不是第一个表格，特别是fallback后可能有多个表格）
    # 头部信息表格的特征：包含"项目名称"、"仪器名称"等关键词
    header_table = None
    for table in tables:
        for row in table:
            if row and any("项目名称" in str(cell) or "仪器名称" in str(cell) or "监测依据" in str(cell) for cell in row if cell):
                header_table = table
                logger.debug(f"[电磁检测] 找到包含头部信息的表格，行数: {len(table)}")
                break
        if header_table:
            break
    
    # 如果没找到包含头部信息的表格，使用第一个表格
    if not header_table:
        header_table = tables[0]
        logger.debug(f"[电磁检测] 未找到包含头部信息的表格，使用第一个表格")
    
    first_table = header_table
    for row in first_table:
        logger.debug(f"[电磁检测][ROW] len={len(row)}, content={row}")
        i = 0
        while i < len(row):
            cell = row[i]
            if not cell or not cell.strip():
                i += 1
                continue
            
            if "项目名称" in cell:
                value, next_idx = find_next_non_empty_value(row, i)
                # 只有当value不为空，且record.project为空时，才从表格中提取
                # 这样可以保留从OCR关键词补充中提取的项目名称
                if value and (not record.project or not record.project.strip()):
                    record.project = value
                    logger.debug(f"[电磁检测] 从表格中提取到项目名称: {record.project}")
                elif not record.project or not record.project.strip():
                    # 如果表格中也没有值，记录警告
                    logger.warning(f"[电磁检测] 项目名称 为空，行数据: {row}")
                i = next_idx
                continue
            if "监测依据" in cell:
                value, next_idx = find_next_non_empty_value(row, i)
                record.standardReferences = value
                if not record.standardReferences.strip():
                    logger.warning(f"[电磁检测] 监测依据 为空，行数据: {row}")
                i = next_idx
                continue
            if "仪器名称" in cell:
                value, next_idx = find_next_non_empty_value(row, i)
                record.deviceName = value
                if not record.deviceName.strip():
                    logger.warning(f"[电磁检测] 仪器名称 为空，行数据: {row}")
                i = next_idx
                continue
            if "仪器型号" in cell:
                value, next_idx = find_next_non_empty_value(row, i)
                record.deviceMode = value
                if not record.deviceMode.strip():
                    logger.warning(f"[电磁检测] 仪器型号 为空，行数据: {row}")
                i = next_idx
                continue
            if "仪器编号" in cell:
                value, next_idx = find_next_non_empty_value(row, i)
                record.deviceCode = value
                if not record.deviceCode.strip():
                    logger.warning(f"[电磁检测] 仪器编号 为空，行数据: {row}")
                i = next_idx
                continue
            if any(k in cell for k in ["测量高度", "检测高度"]):
                value, next_idx = find_next_non_empty_value(row, i)
                record.monitorHeight = value
                if not record.monitorHeight.strip():
                    logger.warning(f"[电磁检测] 检测/测量高度 为空，行数据: {row}")
                i = next_idx
                continue
            if "检测环境条件" in cell:
                value, next_idx = find_next_non_empty_value(row, i)
                text = value
                # 解析天气字段，即使字段为空也保留（ElectromagneticWeatherData的__init__已初始化所有字段为空字符串）
                # 温度：匹配格式如 "29.5-35.0℃" 或 "29.5-35.0 ℃"
                m = re.search(r'([0-9.\-]+)\s*℃', text)
                if m: 
                    record.weather.temp = m.group(1)
                # 如果没有匹配到，字段保持为空字符串（已在__init__中初始化）
                
                # 湿度：匹配格式如 "74.0-74.1%RH" 或 "74.0-74.1 %RH"
                m = re.search(r'([0-9.\-]+)\s*%RH', text)
                if m: 
                    record.weather.humidity = m.group(1)
                # 如果没有匹配到，字段保持为空字符串（已在__init__中初始化）
                
                # 风速：匹配格式如 "0.4-0.5 m/s" 或 "0.4-0.5m/s"
                m = re.search(r'([0-9.\-]+)\s*m/s', text)
                if m: 
                    record.weather.windSpeed = m.group(1)
                # 如果没有匹配到，字段保持为空字符串（已在__init__中初始化）
                
                # 天气：匹配格式如 "天气：晴" 或 "天气 晴"
                m = re.search(r'天气[：:]*\s*([^\s温度湿度风速]+)', text)
                if m: 
                    record.weather.weather = m.group(1).strip()
                # 如果没有匹配到，字段保持为空字符串（已在__init__中初始化）
                
                # 解析风向
                m = re.search(r'风向[：:]*\s*([^\s温度湿度风速天气]+)', text)
                if m: record.weather.windDirection = m.group(1).strip()

                # 天气为空、":"或只有冒号时，如果其它气象字段有任意一个不为空，默认填入"晴"
                weather_value = record.weather.weather.strip() if record.weather.weather else ""
                if (not weather_value or weather_value == ":") and any([
                    record.weather.temp, record.weather.humidity, record.weather.windSpeed, record.weather.windDirection
                ]):
                    record.weather.weather = "晴"
                i = next_idx
                continue
            i += 1

    # 表头关键词：用于识别表头行
    EXCLUDED_HEADERS = {"编号", "备注"}  # 使用集合提高查找效率
    HEADER_KEYWORDS = {"1", "2", "3", "4", "5", "均值", "工频电场强度", "工频磁感应强度", 
                       "监测地点", "线高", "时间", "V/m", "μT"}  # 表头常见关键词
    # 元数据行关键词：这些行的第一列包含这些关键词，应该被排除
    METADATA_KEYWORDS = {"项目名称", "监测依据", "仪器名称", "仪器型号", "仪器编号", 
                         "测量高度", "检测高度", "检测环境条件", "测点分布示意图", 
                         "工况及工程信息", "备注", "备注："}
    
    def is_valid_data_row(row: List[str]) -> bool:
        """判断是否为有效的数据行
        
        有效数据行的特征：
        1. 第一列应该是测点编号（如ZB1, ZB2, EB1等），不能是表头关键词或元数据关键词
        2. 第一列不能为空
        3. 行中不应包含表头关键词（如"1", "2", "3", "4", "5", "均值"等）
        4. 至少需要8列数据
        """
        if len(row) < 8:
            return False
        
        first_cell = row[0].strip() if row[0] else ""
        
        # 第一列为空，跳过
        if not first_cell:
            return False
        
        # 第一列是表头关键词或元数据关键词，跳过
        if first_cell in EXCLUDED_HEADERS or first_cell in METADATA_KEYWORDS:
            return False
        
        # 检查第一列是否包含元数据关键词（部分匹配）
        for keyword in METADATA_KEYWORDS:
            if keyword in first_cell:
                logger.debug(f"[电磁检测] 跳过元数据行（第一列包含'{keyword}'）: {row[0]}")
                return False
        
        # 检查第一列是否是有效的测点编号格式（ZB/EB开头，或至少是字母+数字）
        # 如果第一列是纯数字（如"1", "2"）或表头关键词，跳过
        if first_cell in HEADER_KEYWORDS or (first_cell.isdigit() and len(first_cell) == 1):
            return False
        
        # 检查行中是否包含表头关键词（如果第一列为空但其他列包含"1", "2", "均值"等，可能是表头行）
        # 特别检查第4-9列（电场强度列）和第10-15列（磁感应强度列）是否包含表头关键词
        header_keyword_count = 0
        for i in range(min(16, len(row))):
            cell = row[i].strip() if i < len(row) and row[i] else ""
            if cell in HEADER_KEYWORDS:
                header_keyword_count += 1
        
        # 如果行中包含多个表头关键词（>=3个），很可能是表头行
        if header_keyword_count >= 3:
            logger.debug(f"[电磁检测] 跳过表头行（包含{header_keyword_count}个表头关键词）: {row[:5]}")
            return False
        
        # 如果第一列不是以ZB/EB开头，但行中前几列都是表头关键词，可能是表头行
        if not (first_cell.startswith("ZB") or first_cell.startswith("EB")):
            # 检查前4列是否都是表头关键词或数字
            first_four_are_headers = True
            for i in range(min(4, len(row))):
                cell = row[i].strip() if i < len(row) and row[i] else ""
                if cell and cell not in HEADER_KEYWORDS and not (cell.isdigit() and len(cell) == 1):
                    first_four_are_headers = False
                    break
            if first_four_are_headers:
                logger.debug(f"[电磁检测] 跳过表头行（前4列都是表头关键词）: {row[:5]}")
                return False
        
        return True
    
    # 使用集合跟踪已添加的测点编号，避免重复添加（处理跨页重复的情况）
    seen_codes = set()
    
    for table in tables:
        for row in table:
            if is_valid_data_row(row):
                code = row[0].strip() if row[0] else ""
                
                # 检查是否已经添加过该测点编号
                if code in seen_codes:
                    logger.debug(f"[电磁检测] 跳过重复的测点编号: {code}")
                    continue
                
                logger.info(row)
                em = ElectromagneticData()
                em.code = code
                
                # 智能识别列位置：由于表格可能有colspan，不能简单按索引
                # 1. 地址列：在编号之后，通常是第一个或第二个非空列（如果地址为空则跳过）
                # 2. 高度列：包含"m"单位的列（如"24m"）
                # 3. 时间列：包含日期格式的列（如"2025.7.21 10:35"）
                # 4. 数据列：时间列之后的所有数值列
                
                address_idx = -1
                height_idx = -1
                monitor_at_idx = -1
                
                # 从第1列开始查找（跳过编号列0）
                for i in range(1, len(row)):
                    cell = row[i].strip() if i < len(row) and row[i] else ""
                    if not cell:
                        continue
                    
                    # 先检查是否是时间列（包含日期格式）- 优先级最高，因为格式最明确
                    if re.search(r'\d{4}[.\-]\d{1,2}[.\-]\d{1,2}', cell):
                        if monitor_at_idx == -1:
                            monitor_at_idx = i
                            logger.debug(f"[电磁检测] 识别到时间列: 索引{i}, 值={cell}")
                            continue
                    
                    # 检查是否是高度列（包含"m"单位，且不是时间格式）
                    if "m" in cell and not re.search(r'\d{4}[.\-]\d{1,2}[.\-]\d{1,2}', cell):
                        # 进一步确认：高度通常是数字+m（如"24m"），不包含日期
                        if re.match(r'^\d+[.\d]*m', cell) and height_idx == -1:
                            height_idx = i
                            logger.debug(f"[电磁检测] 识别到高度列: 索引{i}, 值={cell}")
                            continue
                    
                    # 如果既不是高度也不是时间，且地址索引未设置，可能是地址
                    # 地址通常是中文地名（包含中文字符），且不是纯数字
                    if address_idx == -1:
                        # 检查是否是中文地名（包含中文字符）
                        if re.search(r'[\u4e00-\u9fa5]', cell) and not re.match(r'^[\d.\-:\s]+$', cell):
                            address_idx = i
                            logger.debug(f"[电磁检测] 识别到地址列: 索引{i}, 值={cell}")
                
                # 如果通过智能识别没找到高度和时间，使用默认位置（向后兼容）
                if height_idx == -1:
                    # 尝试默认位置：第2列（索引2）
                    if len(row) > 2 and row[2]:
                        height_value = row[2].strip()
                        if height_value:
                            height_idx = 2
                            logger.debug(f"[电磁检测] 使用默认高度列位置: 索引2")
                
                if monitor_at_idx == -1:
                    # 尝试默认位置：第3列（索引3）
                    if len(row) > 3 and row[3]:
                        time_value = row[3].strip()
                        if time_value:
                            monitor_at_idx = 3
                            logger.debug(f"[电磁检测] 使用默认时间列位置: 索引3")
                
                # 提取字段值
                if address_idx >= 0 and address_idx < len(row):
                    em.address = row[address_idx].strip()
                
                if height_idx >= 0 and height_idx < len(row):
                    height_value = row[height_idx].strip()
                    em.height = validate_height(height_value)
                
                if monitor_at_idx >= 0 and monitor_at_idx < len(row):
                    em.monitorAt = row[monitor_at_idx].strip()
                
                # 数据列从时间列之后开始，如果时间列未找到，从高度列之后开始
                # 如果高度列也未找到，从地址列之后开始，如果地址列也未找到，从第4列开始
                if monitor_at_idx >= 0:
                    data_start_idx = monitor_at_idx + 1
                elif height_idx >= 0:
                    data_start_idx = height_idx + 1
                elif address_idx >= 0:
                    data_start_idx = address_idx + 1
                else:
                    data_start_idx = 4
                
                # 跳过空列，找到第一个数值列（应该是电场强度的第一个值）
                while data_start_idx < len(row) and (not row[data_start_idx] or not row[data_start_idx].strip()):
                    data_start_idx += 1
                
                logger.debug(f"[电磁检测] 数据列起始索引: {data_start_idx}, 行数据: {row[data_start_idx:data_start_idx+12] if len(row) > data_start_idx else 'N/A'}")
                
                # 电场强度（从data_start_idx开始，共6列：1-5和均值）
                # 注意：均值列可能在"均值"标签之后，也可能直接是第6个数值
                if len(row) > data_start_idx: em.powerFrequencyEFieldStrength1 = row[data_start_idx]
                if len(row) > data_start_idx + 1: em.powerFrequencyEFieldStrength2 = row[data_start_idx + 1]
                if len(row) > data_start_idx + 2: em.powerFrequencyEFieldStrength3 = row[data_start_idx + 2]
                if len(row) > data_start_idx + 3: em.powerFrequencyEFieldStrength4 = row[data_start_idx + 3]
                if len(row) > data_start_idx + 4: em.powerFrequencyEFieldStrength5 = row[data_start_idx + 4]
                
                # 电场强度均值：跳过可能的"均值"标签，找到下一个数值
                avg_field_idx = data_start_idx + 5
                while avg_field_idx < len(row) and (not row[avg_field_idx] or not row[avg_field_idx].strip() or row[avg_field_idx].strip() == "均值"):
                    avg_field_idx += 1
                if len(row) > avg_field_idx:
                    # 检查是否是数值（可能是均值，也可能是磁感应强度的第一个值）
                    avg_value = row[avg_field_idx].strip()
                    # 如果看起来像电场强度值（较大的数字，如9.xxx），则使用它
                    # 如果看起来像磁感应强度值（较小的数字，如0.xxx），则跳过，使用计算的平均值
                    try:
                        avg_float = float(avg_value)
                        # 电场强度通常在1-1000范围内，磁感应强度通常在0-10范围内
                        if avg_float > 1.0:  # 可能是电场强度均值
                            em.avgPowerFrequencyEFieldStrength = avg_value
                            magnetic_start_idx = avg_field_idx + 1
                        else:  # 可能是磁感应强度的第一个值，跳过
                            magnetic_start_idx = avg_field_idx
                    except ValueError:
                        # 不是数字，跳过
                        magnetic_start_idx = avg_field_idx + 1
                else:
                    magnetic_start_idx = data_start_idx + 6
                
                # 磁感应强度均值：同样需要跳过"均值"标签
                avg_magnetic_idx = magnetic_start_idx + 5
                while avg_magnetic_idx < len(row) and (not row[avg_magnetic_idx] or not row[avg_magnetic_idx].strip() or row[avg_magnetic_idx].strip() == "均值"):
                    avg_magnetic_idx += 1
                
                # 磁感应强度（从magnetic_start_idx开始，共6列：1-5和均值）
                if len(row) > magnetic_start_idx: em.powerFrequencyMagneticDensity1 = row[magnetic_start_idx]
                if len(row) > magnetic_start_idx + 1: em.powerFrequencyMagneticDensity2 = row[magnetic_start_idx + 1]
                if len(row) > magnetic_start_idx + 2: em.powerFrequencyMagneticDensity3 = row[magnetic_start_idx + 2]
                if len(row) > magnetic_start_idx + 3: em.powerFrequencyMagneticDensity4 = row[magnetic_start_idx + 3]
                if len(row) > magnetic_start_idx + 4: em.powerFrequencyMagneticDensity5 = row[magnetic_start_idx + 4]
                if len(row) > avg_magnetic_idx: 
                    em.avgPowerFrequencyMagneticDensity = row[avg_magnetic_idx]
                elif len(row) > magnetic_start_idx + 5:
                    em.avgPowerFrequencyMagneticDensity = row[magnetic_start_idx + 5]
                
                # 如果平均电场强度为空，则计算平均值
                if not em.avgPowerFrequencyEFieldStrength or not em.avgPowerFrequencyEFieldStrength.strip():
                    field_values = [
                        em.powerFrequencyEFieldStrength1,
                        em.powerFrequencyEFieldStrength2,
                        em.powerFrequencyEFieldStrength3,
                        em.powerFrequencyEFieldStrength4,
                        em.powerFrequencyEFieldStrength5
                    ]
                    calculated_avg = calculate_average(field_values)
                    if calculated_avg:
                        em.avgPowerFrequencyEFieldStrength = calculated_avg
                        logger.debug(f"计算平均电场强度: {calculated_avg} (基于前5个值)")
                
                # 如果平均磁感应强度为空，则计算平均值
                if not em.avgPowerFrequencyMagneticDensity or not em.avgPowerFrequencyMagneticDensity.strip():
                    density_values = [
                        em.powerFrequencyMagneticDensity1,
                        em.powerFrequencyMagneticDensity2,
                        em.powerFrequencyMagneticDensity3,
                        em.powerFrequencyMagneticDensity4,
                        em.powerFrequencyMagneticDensity5
                    ]
                    calculated_avg = calculate_average(density_values)
                    if calculated_avg:
                        em.avgPowerFrequencyMagneticDensity = calculated_avg
                        logger.debug(f"计算平均磁感应强度: {calculated_avg} (基于前5个值)")
                
                # 标记该测点编号已添加
                seen_codes.add(code)
                record.electricMagnetic.append(em)
    
    # 矫正编号：按照数据顺序重新分配编号为 EB1, EB2, EB3...
    # 同时建立原始编号到新编号的映射，用于从OCR关键词中提取地址
    code_mapping = {}  # 原始编号 -> 新编号
    for idx, em in enumerate(record.electricMagnetic, start=1):
        original_code = em.code
        new_code = f"EB{idx}"
        code_mapping[original_code.upper()] = new_code
        em.code = new_code
        if original_code != new_code:
            logger.info(f"[电磁检测] 编号矫正: {original_code} -> {new_code}")
    
    # 从OCR关键词注释中提取地址信息并填充到对应的数据项中
    # 先提取Markdown关键词补充（优先级高）
    md_keywords_comment_match = re.search(r'<!--\s*Markdown关键词补充:(.*?)-->', markdown_content, re.DOTALL)
    if md_keywords_comment_match:
        keywords_text = md_keywords_comment_match.group(1)
        logger.info("[电磁检测] 发现Markdown关键词补充，开始提取地址信息（优先级高）")
        
        # 提取监测地点映射
        address_matches = re.findall(r'监测地点-([A-Z0-9]+)[：:]([^\n]+)', keywords_text)
        for code, address in address_matches:
            code_upper = code.upper()
            address = address.strip()
            if address:
                # 查找对应的数据项（使用原始编号或新编号）
                target_code = code_mapping.get(code_upper, code_upper)
                for em in record.electricMagnetic:
                    if em.code == target_code and (not em.address or not em.address.strip()):
                        em.address = address
                        logger.debug(f"[电磁检测] 从Markdown关键词补充提取到地址: {em.code} -> {address}")
    
    # 然后提取OCR关键词补充（优先级低，只在字段为空时补充）
    ocr_keywords_comment_match = re.search(r'<!--\s*OCR关键词补充:(.*?)-->', markdown_content, re.DOTALL)
    if ocr_keywords_comment_match:
        keywords_text = ocr_keywords_comment_match.group(1)
        logger.info("[电磁检测] 发现OCR关键词补充，开始提取地址信息（优先级低，仅在字段为空时补充）")
        
        # 提取监测地点映射
        address_matches = re.findall(r'监测地点-([A-Z0-9]+)[：:]([^\n]+)', keywords_text)
        for code, address in address_matches:
            code_upper = code.upper()
            address = address.strip()
            if address:
                # 查找对应的数据项（使用原始编号或新编号）
                target_code = code_mapping.get(code_upper, code_upper)
                for em in record.electricMagnetic:
                    if em.code == target_code and (not em.address or not em.address.strip()):
                        em.address = address
                        logger.debug(f"[电磁检测] 从OCR关键词补充提取到地址: {em.code} -> {address}")
    
    return record

