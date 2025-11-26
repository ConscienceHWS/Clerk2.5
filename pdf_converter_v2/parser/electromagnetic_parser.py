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
                if cell_value in METADATA_LABELS:
                    return "", j  # 返回空值和下一个标签的位置
                # 找到非标签的值，返回它
                return cell_value, j + 1
        return "", len(row)
    
    first_table = tables[0]
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
                record.project = value
                if not record.project.strip():
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
                m = re.search(r'([0-9.\-]+)\s*℃', text)
                if m: record.weather.temp = m.group(1)
                m = re.search(r'([0-9.\-]+)\s*%RH', text)
                if m: record.weather.humidity = m.group(1)
                m = re.search(r'([0-9.\-]+)\s*m/s', text)
                if m: record.weather.windSpeed = m.group(1)
                m = re.search(r'天气[：:]*\s*([^\s温度湿度风速]+)', text)
                if m: record.weather.weather = m.group(1).strip()
                # 天气为空、":"或只有冒号时，如果其它气象字段有任意一个不为空，默认填入"晴"
                weather_value = record.weather.weather.strip() if record.weather.weather else ""
                if (not weather_value or weather_value == ":") and any([
                    record.weather.temp, record.weather.humidity, record.weather.windSpeed
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
                em.address = row[1] if len(row) > 1 else ""
                # 高度字段校验：可以为空，但不应包含冒号
                height_value = row[2] if len(row) > 2 else ""
                em.height = validate_height(height_value)
                em.monitorAt = row[3] if len(row) > 3 else ""
                
                # 动态检测数据列位置：跳过空列，找到第一个数值列
                # 从第4列开始查找（跳过编号、地址、高度、时间）
                data_start_idx = 4
                # 如果第4列为空，继续查找
                while data_start_idx < len(row) and (not row[data_start_idx] or not row[data_start_idx].strip()):
                    data_start_idx += 1
                
                # 电场强度（从data_start_idx开始，共6列：1-5和均值）
                if len(row) > data_start_idx: em.powerFrequencyEFieldStrength1 = row[data_start_idx]
                if len(row) > data_start_idx + 1: em.powerFrequencyEFieldStrength2 = row[data_start_idx + 1]
                if len(row) > data_start_idx + 2: em.powerFrequencyEFieldStrength3 = row[data_start_idx + 2]
                if len(row) > data_start_idx + 3: em.powerFrequencyEFieldStrength4 = row[data_start_idx + 3]
                if len(row) > data_start_idx + 4: em.powerFrequencyEFieldStrength5 = row[data_start_idx + 4]
                if len(row) > data_start_idx + 5: em.avgPowerFrequencyEFieldStrength = row[data_start_idx + 5]
                
                # 磁感应强度（从data_start_idx + 6开始，共6列：1-5和均值）
                magnetic_start_idx = data_start_idx + 6
                if len(row) > magnetic_start_idx: em.powerFrequencyMagneticDensity1 = row[magnetic_start_idx]
                if len(row) > magnetic_start_idx + 1: em.powerFrequencyMagneticDensity2 = row[magnetic_start_idx + 1]
                if len(row) > magnetic_start_idx + 2: em.powerFrequencyMagneticDensity3 = row[magnetic_start_idx + 2]
                if len(row) > magnetic_start_idx + 3: em.powerFrequencyMagneticDensity4 = row[magnetic_start_idx + 3]
                if len(row) > magnetic_start_idx + 4: em.powerFrequencyMagneticDensity5 = row[magnetic_start_idx + 4]
                if len(row) > magnetic_start_idx + 5: em.avgPowerFrequencyMagneticDensity = row[magnetic_start_idx + 5]
                
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
    
    return record

