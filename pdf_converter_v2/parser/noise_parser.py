# Copyright (c) Opendatalab. All rights reserved.

"""噪声检测记录解析模块 v2 - 独立版本，不依赖OCR"""

from typing import Optional, List
import re
from ..utils.logging_config import get_logger
from ..models.data_models import NoiseDetectionRecord, WeatherData, NoiseData
from .table_parser import extract_table_with_rowspan_colspan, parse_operational_conditions

logger = get_logger("pdf_converter_v2.parser.noise")


def parse_weather_from_text(weather_text: str, record: NoiseDetectionRecord) -> None:
    """从文本中解析天气数据，支持多条记录
    
    文本格式示例：
    日期:2025.9.23 天气 多云 温度26.7-27.4℃湿度66.6-67.4%RH 风速0.9-1.0 m/s 风向东偏北 日期:2025.9.24 天气 多云 温度24.5-28.6℃湿度65.3-67.1%RH 风速1.4-1.5 m/s 风向东偏北
    """
    if not weather_text or "日期" not in weather_text:
        return
    
    # 直接使用分段解析方式，因为第一个正则表达式太复杂且容易出错
    # 首先尝试分段解析，按日期分段，然后逐字段提取
    date_pattern = r'日期[:：]\s*([\d.\-]+)'
    weather_pattern_simple = r'天气\s+([^\s温度湿度风速风向日期]+)'
    # 温度模式：温度后跟数字，直到遇到"℃"或"湿度"
    temp_pattern = r'温度\s*([0-9.\-]+)[℃°C]?'
    # 湿度模式：湿度后跟数字，直到遇到"%RH"或"风速"
    humidity_pattern = r'湿度\s*([0-9.\-]+)[%RH]?'
    # 风速模式：风速后跟数字和"m/s"
    wind_speed_pattern = r'风速\s*([0-9.\-]+)\s*m/s'
    # 风向模式：风向后跟方向描述，直到遇到"日期"或文本结束
    wind_dir_pattern = r'风向\s*([^\s日期温度湿度风速]+)'
    
    # 找到所有日期位置，然后为每个日期解析一条记录
    dates = list(re.finditer(date_pattern, weather_text))
    if not dates:
        logger.warning(f"[噪声检测] 未找到日期信息: {weather_text[:100]}")
        return
    
    weather_found = False
    for idx, date_match in enumerate(dates):
        date_start = date_match.start()
        # 找到下一个日期位置或文本末尾
        if idx + 1 < len(dates):
            next_date_match = dates[idx + 1]
            section_end = next_date_match.start()
        else:
            section_end = len(weather_text)
        
        section = weather_text[date_start:section_end]
        logger.debug(f"[噪声检测] 解析天气段落: {section}")
        
        weather = WeatherData()
        weather.monitorAt = date_match.group(1).strip()
        
        # 提取天气（格式：天气 多云 或 天气多云）
        w_match = re.search(weather_pattern_simple, section)
        if w_match:
            weather.weather = w_match.group(1).strip()
            logger.debug(f"[噪声检测] 提取到天气: {weather.weather}")
        
        # 提取温度（格式：温度26.7-27.4℃ 或 温度 26.7-27.4℃）
        t_match = re.search(temp_pattern, section)
        if t_match:
            temp = t_match.group(1).strip()
            weather.temp = temp
            logger.debug(f"[噪声检测] 提取到温度: {weather.temp}")
        
        # 提取湿度（格式：湿度66.6-67.4%RH 或 湿度 66.6-67.4%RH）
        h_match = re.search(humidity_pattern, section)
        if h_match:
            humidity = h_match.group(1).strip()
            weather.humidity = humidity
            logger.debug(f"[噪声检测] 提取到湿度: {weather.humidity}")
        
        # 提取风速（格式：风速0.9-1.0 m/s 或 风速 0.9-1.0 m/s）
        ws_match = re.search(wind_speed_pattern, section)
        if ws_match:
            wind_speed = ws_match.group(1).strip()
            weather.windSpeed = wind_speed
            logger.debug(f"[噪声检测] 提取到风速: {weather.windSpeed}")
        
        # 提取风向（格式：风向东北 或 风向 东北）
        wd_match = re.search(wind_dir_pattern, section)
        if wd_match:
            weather.windDirection = wd_match.group(1).strip()
            logger.debug(f"[噪声检测] 提取到风向: {weather.windDirection}")
        
        # 如果至少有一个字段不为空，则添加这条记录
        if any([weather.monitorAt, weather.weather, weather.temp, weather.humidity, weather.windSpeed, weather.windDirection]):
            record.weather.append(weather)
            weather_found = True
            logger.info(f"[噪声检测] 解析到天气记录: {weather.to_dict()}")
        else:
            logger.warning(f"[噪声检测] 天气记录字段全为空，跳过: {section}")
    
    # 如果分段解析成功，就不需要继续执行后面的代码
    if weather_found:
        return
    
    # 如果分段解析没有成功，尝试其他方式（向后兼容）
    if not weather_found:
        # 尝试分段解析，更精确地匹配格式：日期:2025.9.23 天气 多云 温度26.7-27.4℃湿度66.6-67.4%RH 风速0.9-1.0 m/s 风向东北
        # 注意：格式中字段和值之间可能没有空格，如"温度26.7-27.4℃"、"湿度66.6-67.4%RH"、"风速0.9-1.0 m/s"
        # 需要在遇到单位符号或下一个字段名时停止匹配
        date_pattern = r'日期[:：]\s*([\d.\-]+)'
        weather_pattern_simple = r'天气\s+([^\s温度湿度风速风向日期]+)'
        # 温度模式：温度后跟数字和单位，直到遇到"湿度"或其他字段
        temp_pattern = r'温度\s*([0-9.\-]+)[℃°C]?'
        # 湿度模式：湿度后跟数字和单位，直到遇到"风速"或其他字段
        humidity_pattern = r'湿度\s*([0-9.\-]+)[%RH]?'
        # 风速模式：风速后跟数字和单位，直到遇到"风向"或其他字段
        wind_speed_pattern = r'风速\s*([0-9.\-]+)\s*m/s'
        # 风向模式：风向后跟方向描述，直到遇到"日期"或文本结束
        wind_dir_pattern = r'风向\s*([^\s日期温度湿度风速]+)'
        
        # 找到所有日期位置，然后为每个日期解析一条记录
        dates = list(re.finditer(date_pattern, weather_text))
        if not dates:
            logger.warning(f"[噪声检测] 未找到日期信息: {weather_text[:100]}")
            return
        
        for idx, date_match in enumerate(dates):
            date_start = date_match.start()
            # 找到下一个日期位置或文本末尾
            if idx + 1 < len(dates):
                next_date_match = dates[idx + 1]
                section_end = next_date_match.start()
            else:
                section_end = len(weather_text)
            
            section = weather_text[date_start:section_end]
            logger.debug(f"[噪声检测] 解析天气段落: {section}")
            
            weather = WeatherData()
            weather.monitorAt = date_match.group(1).strip()
            
            # 提取天气（格式：天气 多云 或 天气多云）
            w_match = re.search(weather_pattern_simple, section)
            if w_match:
                weather.weather = w_match.group(1).strip()
                logger.debug(f"[噪声检测] 提取到天气: {weather.weather}")
            
            # 提取温度（格式：温度26.7-27.4℃ 或 温度 26.7-27.4℃）
            t_match = re.search(temp_pattern, section)
            if t_match:
                temp = t_match.group(1).strip()
                weather.temp = temp
                logger.debug(f"[噪声检测] 提取到温度: {weather.temp}")
            
            # 提取湿度（格式：湿度66.6-67.4%RH 或 湿度 66.6-67.4%RH）
            h_match = re.search(humidity_pattern, section)
            if h_match:
                humidity = h_match.group(1).strip()
                weather.humidity = humidity
                logger.debug(f"[噪声检测] 提取到湿度: {weather.humidity}")
            
            # 提取风速（格式：风速0.9-1.0 m/s 或 风速 0.9-1.0 m/s）
            ws_match = re.search(wind_speed_pattern, section)
            if ws_match:
                wind_speed = ws_match.group(1).strip()
                weather.windSpeed = wind_speed
                logger.debug(f"[噪声检测] 提取到风速: {weather.windSpeed}")
            
            # 提取风向（格式：风向东北 或 风向 东北）
            wd_match = re.search(wind_dir_pattern, section)
            if wd_match:
                weather.windDirection = wd_match.group(1).strip()
                logger.debug(f"[噪声检测] 提取到风向: {weather.windDirection}")
            
            # 如果至少有一个字段不为空，则添加这条记录
            if any([weather.monitorAt, weather.weather, weather.temp, weather.humidity, weather.windSpeed, weather.windDirection]):
                record.weather.append(weather)
                logger.info(f"[噪声检测] 解析到天气记录(简化模式): {weather.to_dict()}")
            else:
                logger.warning(f"[噪声检测] 天气记录字段全为空，跳过: {section}")


def parse_header_from_combined_cell(cell_text: str) -> dict:
    """从组合单元格中解析头部信息
    
    单元格格式示例：
    项目名称:武汉黄陂路102号南站改造工程竣工验收检测依据:GB 12348-2008 □GB3096-2008 □其他:声级计型号/编号:AY2201 声校准器型号/编号:AY2204 检测前校准值:93.8 dB(A) 检测后校准值:94.0 dB(A)气象条件...
    """
    result = {
        "project": "",
        "standardReferences": "",
        "soundLevelMeterMode": "",
        "soundCalibratorMode": "",
        "calibrationValueBefore": "",
        "calibrationValueAfter": ""
    }
    
    if not cell_text or "项目名称" not in cell_text:
        return result
    
    # 解析项目名称：项目名称:xxx（后面跟着检测依据或其他字段，可能没有分隔符）
    # 匹配模式：项目名称:xxx（直到检测依据、监测依据、声级计、声校准器、检测前、检测后或气象条件）
    # 注意：项目名称后面可能直接跟着"检测依据"没有分隔符
    project_match = re.search(r'项目名称[:：](.+?)(?:检测依据|监测依据|声级计|声校准器|检测前|检测后|气象条件)', cell_text)
    if project_match:
        result["project"] = project_match.group(1).strip()
    
    # 解析检测依据：检测依据:GB 12348-2008 □GB3096-2008 □其他:声级计...
    # 也可能格式为：检测依据:xxx或监测依据:xxx
    # 注意：检测依据后面可能跟着"□其他:"，需要截断到"声级计"或"声校准器"或"检测前"或"检测后"或"气象条件"
    standard_match = re.search(r'(?:检测依据|监测依据)[:：](.+?)(?:声级计|声校准器|检测前|检测后|气象条件)', cell_text)
    if standard_match:
        standard_text = standard_match.group(1).strip()
        # 去掉可能的"□其他:"部分（如果存在）
        standard_text = re.sub(r'□其他[:：]?$', '', standard_text).strip()
        # 提取所有GB标准（格式如 GB 12348-2008 或 GB3096-2008）
        gb_standards = re.findall(r'GB\s*\d+[-\.]?\d*[-\.]?\d*', standard_text)
        if gb_standards:
            result["standardReferences"] = " ".join(gb_standards)
        else:
            # 如果没有找到GB标准，保留原文本（去掉可能的□标记）
            result["standardReferences"] = re.sub(r'□\s*', '', standard_text).strip()
    
    # 解析声级计型号/编号：声级计型号/编号:AY2201 或 声级计型号:AY2201
    sound_meter_match = re.search(r'声级计型号[/：:]?(?:编号)?[:：]\s*([A-Z0-9]+)', cell_text)
    if sound_meter_match:
        result["soundLevelMeterMode"] = sound_meter_match.group(1).strip()
    
    # 解析声校准器型号/编号：声校准器型号/编号:AY2204 或 声校准器型号:AY2204
    calibrator_match = re.search(r'声校准器型号[/：:]?(?:编号)?[:：]\s*([A-Z0-9]+)', cell_text)
    if calibrator_match:
        result["soundCalibratorMode"] = calibrator_match.group(1).strip()
    
    # 解析检测前校准值：检测前校准值:93.8 dB(A)
    before_cal_match = re.search(r'检测前校准值[:：]\s*([0-9.]+)\s*dB\(A\)', cell_text)
    if before_cal_match:
        cal_value = before_cal_match.group(1).strip()
        result["calibrationValueBefore"] = f"{cal_value} dB(A)"
    else:
        # 如果没有单位，只提取数值
        before_cal_match2 = re.search(r'检测前校准值[:：]\s*([0-9.]+)', cell_text)
        if before_cal_match2:
            result["calibrationValueBefore"] = before_cal_match2.group(1).strip()
    
    # 解析检测后校准值：检测后校准值:94.0 dB(A)
    after_cal_match = re.search(r'检测后校准值[:：]\s*([0-9.]+)\s*dB\(A\)', cell_text)
    if after_cal_match:
        cal_value = after_cal_match.group(1).strip()
        result["calibrationValueAfter"] = f"{cal_value} dB(A)"
    else:
        # 如果没有单位，只提取数值
        after_cal_match2 = re.search(r'检测后校准值[:：]\s*([0-9.]+)', cell_text)
        if after_cal_match2:
            result["calibrationValueAfter"] = after_cal_match2.group(1).strip()
    
    return result


def parse_noise_detection_record(markdown_content: str, first_page_image: Optional = None, output_dir: Optional[str] = None) -> NoiseDetectionRecord:
    """解析噪声检测记录 - v2版本不依赖OCR，只从markdown内容解析"""
    record = NoiseDetectionRecord()
    # 使用支持rowspan和colspan的函数提取表格，因为噪声检测表有复杂的表头结构
    tables = extract_table_with_rowspan_colspan(markdown_content)
    
    if not tables:
        logger.warning(f"[噪声检测] 未能提取出任何表格内容")
        return record

    first_table = tables[0]
    
    # 首先尝试从组合单元格中解析头部信息（这种情况是多个字段都在一个单元格中）
    header_extracted = False
    weather_extracted = False
    for row in first_table:
        for cell in row:
            # 检查单元格是否包含多个头部字段的关键词
            if "项目名称" in cell and ("检测依据" in cell or "监测依据" in cell or "声级计" in cell or "声校准器" in cell):
                logger.debug(f"[噪声检测] 发现组合单元格，尝试解析: {cell[:100]}...")
                parsed_header = parse_header_from_combined_cell(cell)
                if parsed_header["project"]:
                    record.project = parsed_header["project"]
                    header_extracted = True
                if parsed_header["standardReferences"]:
                    record.standardReferences = parsed_header["standardReferences"]
                if parsed_header["soundLevelMeterMode"]:
                    record.soundLevelMeterMode = parsed_header["soundLevelMeterMode"]
                if parsed_header["soundCalibratorMode"]:
                    record.soundCalibratorMode = parsed_header["soundCalibratorMode"]
                if parsed_header["calibrationValueBefore"]:
                    record.calibrationValueBefore = parsed_header["calibrationValueBefore"]
                if parsed_header["calibrationValueAfter"]:
                    record.calibrationValueAfter = parsed_header["calibrationValueAfter"]
                
                # 如果单元格中包含气象条件，也从这里解析
                if "气象条件" in cell:
                    weather_text = cell
                    # 从"气象条件"之后的内容开始解析
                    if "气象条件" in weather_text:
                        # 提取气象条件部分（从"气象条件"开始到字符串末尾或下一个主要字段）
                        weather_section = weather_text.split("气象条件")[-1] if "气象条件" in weather_text else weather_text
                        parse_weather_from_text(weather_section, record)
                        weather_extracted = True
                        logger.info(f"[噪声检测] 从组合单元格解析到天气信息: {len(record.weather)} 条记录")
                
                if header_extracted:
                    logger.info(f"[噪声检测] 从组合单元格解析到头部信息: project={record.project}, "
                              f"standardReferences={record.standardReferences}, "
                              f"soundLevelMeterMode={record.soundLevelMeterMode}, "
                              f"soundCalibratorMode={record.soundCalibratorMode}")
                    if not weather_extracted:
                        break
    
    # 如果还没有提取到头部信息，使用原来的方法（假设字段分布在不同的单元格中）
    if not header_extracted:
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

    # 解析气象条件 - 支持多条记录（如果还没有从组合单元格中提取到天气数据）
    if not weather_extracted:
        for row in first_table:
            if len(row) >= 2 and "气象条件" in row[0]:
                text = " ".join(row[1:])
                parse_weather_from_text(text, record)
                break
            
            # 也检查是否在其他单元格中有气象条件
            for cell in row:
                if "气象条件" in cell and "日期" in cell:
                    # 提取气象条件部分
                    weather_section = cell.split("气象条件")[-1] if "气象条件" in cell else cell
                    parse_weather_from_text(weather_section, record)
                    weather_extracted = True
                    break
            if weather_extracted:
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

