# Copyright (c) Opendatalab. All rights reserved.

"""电磁检测记录解析模块 v2 - 独立版本"""

from typing import List
import re
from ..utils.logging_config import get_logger
from ..models.data_models import ElectromagneticDetectionRecord, ElectromagneticData
from .table_parser import extract_table_data

logger = get_logger("pdf_converter_v2.parser.electromagnetic")

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

    for table in tables:
        for row in table:
            if len(row) >= 8 and row[0] and row[0] not in ["编号", "备注"] and row[0].startswith("EB"):
                logger.info(row)
                em = ElectromagneticData()
                em.code = row[0]
                em.address = row[1] if len(row) > 1 else ""
                em.height = row[2] if len(row) > 2 else ""
                em.monitorAt = row[3] if len(row) > 3 else ""
                
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

