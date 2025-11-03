# Copyright (c) Opendatalab. All rights reserved.

"""噪声检测记录解析模块 v2 - 独立版本，不依赖OCR"""

from typing import Optional, List
import re
from ..utils.logging_config import get_logger
from ..models.data_models import NoiseDetectionRecord, WeatherData, NoiseData
from .table_parser import extract_table_with_rowspan_colspan, parse_operational_conditions

logger = get_logger("pdf_converter_v2.parser.noise")

def parse_noise_detection_record(markdown_content: str, first_page_image: Optional = None, output_dir: Optional[str] = None) -> NoiseDetectionRecord:
    """解析噪声检测记录 - v2版本不依赖OCR，只从markdown内容解析"""
    record = NoiseDetectionRecord()
    # 使用支持rowspan和colspan的函数提取表格，因为噪声检测表有复杂的表头结构
    tables = extract_table_with_rowspan_colspan(markdown_content)
    
    if not tables:
        logger.warning(f"[噪声检测] 未能提取出任何表格内容")
        return record

    first_table = tables[0]
    for row in first_table:
        logger.debug(f"[噪声检测][ROW] len={len(row)}, content={row}")
        if len(row) >= 2:
            if "项目名称" in row[0]:
                for i, cell in enumerate(row):
                    if "项目名称" in cell and i + 1 < len(row):
                        record.project = row[i + 1]
                        if not record.project.strip():
                            logger.error(f"[噪声检测] 项目名称 为空，行数据: {row}")
                        break
            if any(k in row[0] for k in ["检测依据", "监测依据"]):
                for i, cell in enumerate(row):
                    if any(k in cell for k in ["检测依据", "监测依据"]) and i + 1 < len(row):
                        record.standardReferences = row[i + 1]
                        if not record.standardReferences.strip():
                            logger.error(f"[噪声检测] 检测/监测依据 为空，行数据: {row}")
                        break
            if any(k in row[0] for k in ["声纹计型号", "声级计型号"]):
                for i, cell in enumerate(row):
                    if any(k in cell for k in ["声纹计型号", "声级计型号"]) and i + 1 < len(row):
                        record.soundLevelMeterMode = row[i + 1]
                        if not record.soundLevelMeterMode.strip():
                            logger.error(f"[噪声检测] 声级计型号 为空，行数据: {row}")
                        break
            if any(k in row[0] for k in ["声纹准器型号", "声级计校准器型号"]):
                for i, cell in enumerate(row):
                    if any(k in cell for k in ["声纹准器型号", "声级计校准器型号"]) and i + 1 < len(row):
                        record.soundCalibratorMode = row[i + 1]
                        if not record.soundCalibratorMode.strip():
                            logger.error(f"[噪声检测] 声级计校准器型号 为空，行数据: {row}")
                        break
            if "检测前校准值" in row[0]:
                for i, cell in enumerate(row):
                    if "检测前校准值" in cell and i + 1 < len(row):
                        record.calibrationValueBefore = row[i + 1]
                        if not record.calibrationValueBefore.strip():
                            logger.error(f"[噪声检测] 检测前校准值 为空，行数据: {row}")
                        break
            if "检测后校准值" in row[0]:
                for i, cell in enumerate(row):
                    if "检测后校准值" in cell and i + 1 < len(row):
                        record.calibrationValueAfter = row[i + 1]
                        if not record.calibrationValueAfter.strip():
                            logger.error(f"[噪声检测] 检测后校准值 为空，行数据: {row}")
                        break

    # 解析气象条件 - 支持多条记录
    for row in first_table:
        if len(row) >= 2 and "气象条件" in row[0]:
            text = " ".join(row[1:])
            
            # 使用正则表达式匹配所有天气记录（以"日期："开始）
            # 匹配模式：日期：xxx 天气xxx 温度xxx 湿度xxx 风速xxx 风向xxx
            weather_pattern = r'日期[:：]\s*([\d.\-]+).*?(?:天气[:：]\s*([^\s温度湿度风速风向]+))?.*?(?:温度[:：]?\s*([0-9.\-\s~]+))?.*?(?:湿度[:：]?\s*([0-9.\-\s~]+))?.*?(?:风速[:：]?\s*([0-9.\-\s~]+))?.*?(?:风向[:：]?\s*([^\s温度湿度风速日期]+))?'
            weather_matches = re.finditer(weather_pattern, text, re.DOTALL | re.IGNORECASE)
            
            weather_found = False
            for match in weather_matches:
                weather = WeatherData()
                if match.group(1):
                    weather.monitorAt = match.group(1).strip()
                if match.group(2):
                    weather.weather = match.group(2).strip()
                if match.group(3):
                    weather.temp = match.group(3).strip()
                if match.group(4):
                    weather.humidity = match.group(4).strip()
                if match.group(5):
                    weather.windSpeed = match.group(5).strip()
                if match.group(6):
                    weather.windDirection = match.group(6).strip()
                
                # 如果至少有一个字段不为空，则添加这条记录
                if any([weather.monitorAt, weather.weather, weather.temp, weather.humidity, weather.windSpeed, weather.windDirection]):
                    record.weather.append(weather)
                    weather_found = True
            
            # 如果没有找到匹配的记录，使用旧的单条记录解析方式（向后兼容）
            if not weather_found:
                weather = WeatherData()
                m = re.search(r'日期[:：]\s*([\d.\-]+)', text)
                if m: weather.monitorAt = m.group(1).strip()
                m = re.search(r'天气[:：]\s*([^\s]+)', text)
                if m: weather.weather = m.group(1).strip()
                m = re.search(r'温度[:：]?\s*([0-9.\-]+)', text)
                if m: weather.temp = m.group(1).strip()
                m = re.search(r'湿度[:：]?\s*([0-9.\-]+)', text)
                if m: weather.humidity = m.group(1).strip()
                m = re.search(r'风速[:：]?\s*([0-9.\-]+)', text)
                if m: weather.windSpeed = m.group(1).strip()
                m = re.search(r'风向[:：]?\s*([^\s]+)', text)
                if m: weather.windDirection = m.group(1).strip()
                
                # 如果至少有一个字段不为空，则添加这条记录
                if any([weather.monitorAt, weather.weather, weather.temp, weather.humidity, weather.windSpeed, weather.windDirection]):
                    record.weather.append(weather)
            break

    for table in tables:
        # 首先识别表头，找到各列的索引
        code_idx = -1
        address_idx = -1
        source_idx = -1
        dayMonitorAt_idx = -1
        dayMonitorValue_idx = -1
        dayMonitorBackgroundValue_idx = -1
        nightMonitorAt_idx = -1
        nightMonitorValue_idx = -1
        nightMonitorBackgroundValue_idx = -1
        remark_idx = -1
        
        header_start_row = -1
        # 查找表头行（通常包含"编号"、"测点位置"、"昼间"、"夜间"等关键词）
        for row_idx, row in enumerate(table):
            row_text = " ".join(row).lower()
            # 检查是否是表头行
            if ("编号" in row_text or "测点位置" in row_text or "测点" in row_text) and \
               ("昼间" in row_text or "夜间" in row_text or "测量值" in row_text or "检测时间" in row_text):
                header_start_row = row_idx
                logger.debug(f"[噪声检测] 找到表头行: 第{row_idx}行, 内容: {row}")
                
                # 在第一行表头中查找列索引
                for col_idx, cell in enumerate(row):
                    cell_lower = cell.lower().strip()
                    if "编号" in cell:
                        code_idx = col_idx
                    elif "测点位置" in cell or "测点" in cell:
                        address_idx = col_idx
                    elif "主要声源" in cell or "声源" in cell:
                        source_idx = col_idx
                    elif "昼间" in cell and ("检测时间" in cell or "时间" in cell):
                        dayMonitorAt_idx = col_idx
                    elif "昼间" in cell and ("测量值" in cell or "测量" in cell):
                        dayMonitorValue_idx = col_idx
                    elif "昼间" in cell and ("背景值" in cell or "背景" in cell):
                        dayMonitorBackgroundValue_idx = col_idx
                    elif "夜间" in cell and ("检测时间" in cell or "时间" in cell):
                        nightMonitorAt_idx = col_idx
                    elif "夜间" in cell and ("测量值" in cell or "测量" in cell):
                        nightMonitorValue_idx = col_idx
                    elif "夜间" in cell and ("背景值" in cell or "背景" in cell):
                        nightMonitorBackgroundValue_idx = col_idx
                    elif "备注" in cell:
                        remark_idx = col_idx
                
                # 如果第一行表头没有找到所有列，检查下一行（如果是两行表头）
                if row_idx + 1 < len(table):
                    next_row = table[row_idx + 1]
                    next_row_text = " ".join(next_row).lower()
                    # 如果是第二行表头（通常是详细的列名）
                    if "检测时间" in next_row_text or "测量值" in next_row_text or "背景值" in next_row_text:
                        logger.debug(f"[噪声检测] 找到第二行表头: 第{row_idx + 1}行, 内容: {next_row}")
                        # 检查第一行表头，找到"昼间"和"夜间"的列范围
                        day_start_col = -1
                        day_end_col = -1
                        night_start_col = -1
                        night_end_col = -1
                        
                        for col_idx, cell in enumerate(row):
                            cell_lower = cell.lower().strip()
                            if "昼间" in cell_lower:
                                day_start_col = col_idx
                                # 查找昼间结束位置（通常是下一个非空单元格或"夜间"开始）
                                for next_col in range(col_idx + 1, len(row)):
                                    if "夜间" in row[next_col].lower() or row[next_col].strip():
                                        day_end_col = next_col - 1
                                        break
                                if day_end_col == -1:
                                    day_end_col = len(row) - 1
                            elif "夜间" in cell_lower:
                                night_start_col = col_idx
                                # 查找夜间结束位置
                                for next_col in range(col_idx + 1, len(row)):
                                    if "备注" in row[next_col].lower() or (next_col == len(row) - 1):
                                        night_end_col = next_col - 1
                                        break
                                if night_end_col == -1:
                                    night_end_col = len(row) - 1
                        
                        # 在第二行表头中查找列索引
                        for col_idx, cell in enumerate(next_row):
                            cell_lower = cell.lower().strip()
                            if "检测时间" in cell or "时间" in cell:
                                # 根据列位置判断是昼间还是夜间
                                if day_start_col >= 0 and day_start_col <= col_idx <= day_end_col and dayMonitorAt_idx == -1:
                                    dayMonitorAt_idx = col_idx
                                elif night_start_col >= 0 and night_start_col <= col_idx <= night_end_col and nightMonitorAt_idx == -1:
                                    nightMonitorAt_idx = col_idx
                                elif dayMonitorAt_idx == -1:
                                    dayMonitorAt_idx = col_idx
                                elif nightMonitorAt_idx == -1:
                                    nightMonitorAt_idx = col_idx
                            elif "测量值" in cell or "测量" in cell:
                                if day_start_col >= 0 and day_start_col <= col_idx <= day_end_col and dayMonitorValue_idx == -1:
                                    dayMonitorValue_idx = col_idx
                                elif night_start_col >= 0 and night_start_col <= col_idx <= night_end_col and nightMonitorValue_idx == -1:
                                    nightMonitorValue_idx = col_idx
                                elif dayMonitorValue_idx == -1:
                                    dayMonitorValue_idx = col_idx
                                elif nightMonitorValue_idx == -1:
                                    nightMonitorValue_idx = col_idx
                            elif "背景值" in cell or "背景" in cell:
                                if day_start_col >= 0 and day_start_col <= col_idx <= day_end_col and dayMonitorBackgroundValue_idx == -1:
                                    dayMonitorBackgroundValue_idx = col_idx
                                elif night_start_col >= 0 and night_start_col <= col_idx <= night_end_col and nightMonitorBackgroundValue_idx == -1:
                                    nightMonitorBackgroundValue_idx = col_idx
                                elif dayMonitorBackgroundValue_idx == -1:
                                    dayMonitorBackgroundValue_idx = col_idx
                                elif nightMonitorBackgroundValue_idx == -1:
                                    nightMonitorBackgroundValue_idx = col_idx
                
                # 如果仍然没有找到某些列，使用默认顺序
                if code_idx == -1:
                    code_idx = 0
                if address_idx == -1:
                    address_idx = 1
                if source_idx == -1:
                    source_idx = 2
                if dayMonitorAt_idx == -1:
                    dayMonitorAt_idx = 3
                if dayMonitorValue_idx == -1:
                    dayMonitorValue_idx = 4
                if dayMonitorBackgroundValue_idx == -1:
                    dayMonitorBackgroundValue_idx = 5
                if nightMonitorAt_idx == -1:
                    nightMonitorAt_idx = 6
                if nightMonitorValue_idx == -1:
                    nightMonitorValue_idx = 7
                if nightMonitorBackgroundValue_idx == -1:
                    nightMonitorBackgroundValue_idx = 8
                if remark_idx == -1:
                    remark_idx = 9
                
                logger.info(f"[噪声检测] 列索引映射: 编号={code_idx}, 测点位置={address_idx}, 主要声源={source_idx}, "
                          f"昼间检测时间={dayMonitorAt_idx}, 昼间测量值={dayMonitorValue_idx}, 昼间背景值={dayMonitorBackgroundValue_idx}, "
                          f"夜间检测时间={nightMonitorAt_idx}, 夜间测量值={nightMonitorValue_idx}, 夜间背景值={nightMonitorBackgroundValue_idx}, "
                          f"备注={remark_idx}")
                break
        
        # 如果找到了表头，从表头之后开始解析数据行
        data_start_row = header_start_row + 2 if header_start_row >= 0 and header_start_row + 1 < len(table) and \
                          any(k in " ".join(table[header_start_row + 1]).lower() for k in ["检测时间", "测量值", "背景值"]) else \
                         (header_start_row + 1 if header_start_row >= 0 else 0)
        
        # 解析数据行
        for row_idx in range(data_start_row, len(table)):
            row = table[row_idx]
            # 跳过空行和表头行
            if not row or len(row) < 3:
                continue
            
            # 检查是否是数据行（第一列应该是编号，通常是N1、N2或M1、M2等格式）
            first_cell = row[0].strip() if len(row) > 0 else ""
            if not first_cell or first_cell in ["编号", "备注"] or not (first_cell[0].upper() in ['N', 'M'] and first_cell[1:].isdigit()):
                # 如果不是标准编号格式，也可能是有编号但格式不同，继续检查
                if not (first_cell and (first_cell[0].isalnum() or first_cell.startswith('N') or first_cell.startswith('M'))):
                    continue
            
            logger.debug(f"[噪声检测] 解析数据行 {row_idx}: {row}")
            nd = NoiseData()
            
            # 使用识别的列索引来提取数据
            if code_idx >= 0 and code_idx < len(row):
                nd.code = row[code_idx].strip()
            if address_idx >= 0 and address_idx < len(row):
                nd.address = row[address_idx].strip()
            if source_idx >= 0 and source_idx < len(row):
                nd.source = row[source_idx].strip()
            if dayMonitorAt_idx >= 0 and dayMonitorAt_idx < len(row):
                nd.dayMonitorAt = row[dayMonitorAt_idx].strip()
            if dayMonitorValue_idx >= 0 and dayMonitorValue_idx < len(row):
                nd.dayMonitorValue = row[dayMonitorValue_idx].strip()
            if dayMonitorBackgroundValue_idx >= 0 and dayMonitorBackgroundValue_idx < len(row):
                nd.dayMonitorBackgroundValue = row[dayMonitorBackgroundValue_idx].strip()
            if nightMonitorAt_idx >= 0 and nightMonitorAt_idx < len(row):
                nd.nightMonitorAt = row[nightMonitorAt_idx].strip()
            if nightMonitorValue_idx >= 0 and nightMonitorValue_idx < len(row):
                nd.nightMonitorValue = row[nightMonitorValue_idx].strip()
            if nightMonitorBackgroundValue_idx >= 0 and nightMonitorBackgroundValue_idx < len(row):
                nd.nightMonitorBackgroundValue = row[nightMonitorBackgroundValue_idx].strip()
            if remark_idx >= 0 and remark_idx < len(row):
                nd.remark = row[remark_idx].strip()
            
            # 验证数据有效性（至少应该有编号和测点位置）
            if nd.code and nd.address:
                logger.info(f"[噪声检测] 解析到数据: {nd.to_dict()}")
                record.noise.append(nd)
            else:
                logger.warning(f"[噪声检测] 跳过无效数据行: {row}")
    
    # 解析工况信息
    operational_conditions = parse_operational_conditions(markdown_content)
    record.operationalConditions = operational_conditions
    
    # v2版本不依赖OCR，只从markdown内容解析
    # 如果某些字段为空，会在日志中记录警告，但不进行OCR补充识别
    
    return record

