# Copyright (c) Opendatalab. All rights reserved.

"""电磁检测记录解析模块 v2 - 独立版本"""

from typing import List
import re
from ..utils.logging_config import get_logger
from ..models.data_models import ElectromagneticDetectionRecord, ElectromagneticData
from .table_parser import extract_table_data

logger = get_logger("pdf_converter_v2.parser.electromagnetic")


def is_valid_height(value: str) -> bool:
    """校验高度值格式
    高度应该是数字（可能包含单位如m、cm等），不应该是时间格式或日期格式
    """
    if not value or not value.strip():
        return False
    
    value = value.strip()
    
    # 排除时间格式（如 "14:50", "14:50:30"）
    if re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', value):
        return False
    
    # 排除日期格式（如 "2025.09.08", "2025-09-08", "2025年9月8日" 等）
    date_patterns = [
        r'^\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}',  # 2025.09.08, 2025-09-08, 2025/09/08
        r'^\d{4}\d{2}\d{2}',  # 20250908
        r'^\d{4}年\d{1,2}月\d{1,2}日',  # 2025年9月8日
    ]
    for pattern in date_patterns:
        if re.match(pattern, value):
            return False
    
    # 如果包含年月日相关的关键词，排除
    if any(keyword in value for keyword in ['年', '月', '日']):
        return False
    
    # 检查是否包含数字（高度应该包含数字）
    if not re.search(r'\d', value):
        return False
    
    # 如果只包含数字和常见单位（m, cm, mm等），认为是有效的高度
    if re.match(r'^[\d.\-]+\s*(m|cm|mm|M|CM|MM)?$', value):
        return True
    
    # 如果包含其他字符，但主要是数字，也认为是有效的（可能是 "1.5m" 或 "1.5 m" 等）
    numeric_part = re.sub(r'[^\d.\-]', '', value)
    if numeric_part and len(numeric_part) >= 1:
        # 确保不是日期格式（日期通常有4位年份）
        if len(numeric_part) >= 8 and numeric_part[:4].isdigit() and int(numeric_part[:4]) >= 1900:
            return False
        return True
    
    return False


def is_valid_monitor_time(value: str) -> bool:
    """校验监测时间格式
    监测时间应该是日期格式（如 "2025.09.08", "2025-09-08" 等），不应该是简单的时间格式（如 "14:50"）
    """
    if not value or not value.strip():
        return False
    
    value = value.strip()
    
    # 排除简单的时间格式（如 "14:50", "14:50:30"）
    if re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', value):
        return False
    
    # 检查是否是日期格式（包含年月日）
    # 支持格式：2025.09.08, 2025-09-08, 2025/09/08, 20250908 等
    date_patterns = [
        r'^\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}',  # 2025.09.08, 2025-09-08, 2025/09/08
        r'^\d{4}\d{2}\d{2}',  # 20250908
        r'^\d{4}年\d{1,2}月\d{1,2}日',  # 2025年9月8日
    ]
    
    for pattern in date_patterns:
        if re.match(pattern, value):
            return True
    
    # 如果包含年月日相关的关键词，也认为是有效的
    if any(keyword in value for keyword in ['年', '月', '日', '-', '.', '/']):
        # 确保包含数字
        if re.search(r'\d', value):
            return True
    
    return False


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
    tables = extract_table_data(markdown_content)
    
    if not tables:
        logger.warning(f"[电磁检测] 未能提取出任何表格内容")
        return record

    first_table = tables[0]
    for row in first_table:
        logger.debug(f"[电磁检测][ROW] len={len(row)}, content={row}")
        i = 0
        while i < len(row):
            cell = row[i]
            if i+1 >= len(row):
                break
            value = row[i+1]
            if "项目名称" in cell:
                record.project = value
                if not record.project.strip():
                    logger.error(f"[电磁检测] 项目名称 为空，行数据: {row}")
                i += 2
                continue
            if "监测依据" in cell:
                record.standardReferences = value
                if not record.standardReferences.strip():
                    logger.error(f"[电磁检测] 监测依据 为空，行数据: {row}")
                i += 2
                continue
            if "仪器名称" in cell:
                record.deviceName = value
                if not record.deviceName.strip():
                    logger.error(f"[电磁检测] 仪器名称 为空，行数据: {row}")
                i += 2
                continue
            if "仪器型号" in cell:
                record.deviceMode = value
                if not record.deviceMode.strip():
                    logger.error(f"[电磁检测] 仪器型号 为空，行数据: {row}")
                i += 2
                continue
            if "仪器编号" in cell:
                record.deviceCode = value
                if not record.deviceCode.strip():
                    logger.error(f"[电磁检测] 仪器编号 为空，行数据: {row}")
                i += 2
                continue
            if any(k in cell for k in ["测量高度", "检测高度"]):
                record.monitorHeight = value
                if not record.monitorHeight.strip():
                    logger.error(f"[电磁检测] 检测/测量高度 为空，行数据: {row}")
                i += 2
                continue
            if "检测环境条件" in cell:
                text = value
                m = re.search(r'([0-9.\-]+)\s*℃', text)
                if m: record.weather.temp = m.group(1)
                m = re.search(r'([0-9.\-]+)\s*%RH', text)
                if m: record.weather.humidity = m.group(1)
                m = re.search(r'([0-9.\-]+)\s*m/s', text)
                if m: record.weather.windSpeed = m.group(1)
                m = re.search(r'天气[：:]*\s*([^\s]+)', text)
                if m: record.weather.weather = m.group(1)
                # 天气为空但其它气象字段有任意一个不为空时，默认填入“晴”
                if (not record.weather.weather or not record.weather.weather.strip()) and any([
                    record.weather.temp, record.weather.humidity, record.weather.windSpeed
                ]):
                    record.weather.weather = "晴"
                i += 2
                continue
            i += 1

    # 数据行代码匹配模式：以EB或ZB开头（不区分大小写）
    CODE_PATTERN = re.compile(r'^(EB|ZB)', re.IGNORECASE)
    EXCLUDED_HEADERS = {"编号", "备注"}  # 使用集合提高查找效率
    
    def is_valid_data_row(row: List[str]) -> bool:
        """判断是否为有效的数据行"""
        if len(row) < 8 or not row[0]:
            return False
        first_cell = row[0].strip()
        return (first_cell not in EXCLUDED_HEADERS 
                and CODE_PATTERN.match(first_cell) is not None)
    
    for table in tables:
        for row in table:
            if is_valid_data_row(row):
                logger.info(row)
                em = ElectromagneticData()
                em.code = row[0]
                em.address = row[1] if len(row) > 1 else ""
                
                # 高度字段格式校验
                height_value = row[2] if len(row) > 2 else ""
                if height_value and is_valid_height(height_value):
                    em.height = height_value
                else:
                    if height_value:
                        logger.warning(f"[电磁检测] 高度值格式无效，已忽略: '{height_value}' (行: {row})")
                    em.height = ""
                
                # 监测时间字段格式校验
                monitor_at_value = row[3] if len(row) > 3 else ""
                if monitor_at_value and is_valid_monitor_time(monitor_at_value):
                    em.monitorAt = monitor_at_value
                else:
                    if monitor_at_value:
                        logger.warning(f"[电磁检测] 监测时间格式无效，已忽略: '{monitor_at_value}' (行: {row})")
                    em.monitorAt = ""
                
                # 电场强度
                if len(row) > 4: em.powerFrequencyEFieldStrength1 = row[4]
                if len(row) > 5: em.powerFrequencyEFieldStrength2 = row[5]
                if len(row) > 6: em.powerFrequencyEFieldStrength3 = row[6]
                if len(row) > 7: em.powerFrequencyEFieldStrength4 = row[7]
                if len(row) > 8: em.powerFrequencyEFieldStrength5 = row[8]
                if len(row) > 9: em.avgPowerFrequencyEFieldStrength = row[9]
                
                # 磁感应强度
                if len(row) > 10: em.powerFrequencyMagneticDensity1 = row[10]
                if len(row) > 11: em.powerFrequencyMagneticDensity2 = row[11]
                if len(row) > 12: em.powerFrequencyMagneticDensity3 = row[12]
                if len(row) > 13: em.powerFrequencyMagneticDensity4 = row[13]
                if len(row) > 14: em.powerFrequencyMagneticDensity5 = row[14]
                if len(row) > 15: em.avgPowerFrequencyMagneticDensity = row[15]
                
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
                
                record.electricMagnetic.append(em)
    
    return record

