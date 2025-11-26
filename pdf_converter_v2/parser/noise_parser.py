# Copyright (c) Opendatalab. All rights reserved.

"""噪声检测记录解析模块 v2 - 独立版本，不依赖OCR"""

from typing import Optional, List
import re
from ..utils.logging_config import get_logger
from ..models.data_models import NoiseDetectionRecord, WeatherData, NoiseData
from .table_parser import extract_table_with_rowspan_colspan, parse_operational_conditions, parse_operational_conditions_opstatus

logger = get_logger("pdf_converter_v2.parser.noise")


def clean_project_field(project: str) -> str:
    """清理project字段：如果包含"检测依据"，删除"检测依据"及其后面的所有字符
    同时清理末尾的标点符号（逗号、句号、分号等）
    
    Args:
        project: 原始project字段值
        
    Returns:
        清理后的project字段值
    """
    if not project:
        return project
    
    # 查找"检测依据"的位置
    if "检测依据" in project:
        idx = project.find("检测依据")
        project = project[:idx].strip()
        logger.debug(f"[噪声检测] 清理project字段，删除'检测依据'及之后内容: {project}")
    
    # 清理末尾的标点符号（逗号、句号、分号、冒号等）
    project = re.sub(r'[，。；：,.;:]+$', '', project).strip()
    
    return project


def normalize_standard_text(text: str) -> str:
    """标准字段中可能包含数学/LaTeX格式，需先清理"""
    if not text:
        return text
    
    # 去掉美元符号和常见LaTeX指令（例如 \mathrm、\left、\right、\cdot 等）
    text = text.replace("$", "")
    text = re.sub(r"\\(mathrm|left|right|cdot|cdots|ldots|frac|overline|underline|mathbf|mathbf|mathit|mathsf|mathtt|mathcal)\b", "", text)
    # 删除其他未知的反斜杠命令，保留紧跟其后的文本
    text = re.sub(r"\\[a-zA-Z]+", "", text)
    # 去掉多余的大括号
    text = re.sub(r"[{}]", "", text)
    # 合并多余空白
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_standard_references(text: str) -> str:
    """解析检测/监测依据，支持包含数学格式的文本"""
    if not text:
        return ""
    
    text = normalize_standard_text(text.strip())
    text = re.sub(r'□其他[:：]?$', '', text).strip()
    gb_standards = re.findall(r'GB\s*\d+[-\.]?\d*[-\.]?\d*', text)
    if gb_standards:
        return " ".join(gb_standards)
    return re.sub(r'□\s*', '', text).strip()


def _normalize_weather_text(weather_text: str) -> str:
    """标准化气象字段文本，插入缺失的分隔符，移除HTML"""
    if not weather_text:
        return weather_text
    
    text = weather_text
    text = re.sub(r'<[^>]+>', ' ', text)  # 移除HTML标签
    text = text.replace("&nbsp;", " ")
    text = text.replace("．", ".")
    text = text.replace("，", " ")
    text = text.replace("：", ":")
    text = text.replace("℃C", "℃")
    
    # 为不同字段增加缺失的空格，避免如 "℃湿度" 无法拆分
    text = re.sub(r'([℃°C])\s*湿度', r'\1 湿度', text)
    text = re.sub(r'([℃°C])\s*风速', r'\1 风速', text)
    text = re.sub(r'(%RH)\s*风速', r'\1 风速', text, flags=re.IGNORECASE)
    text = re.sub(r'(％RH)\s*风速', r'%RH 风速', text)
    text = re.sub(r'(m/s)\s*风向', r'\1 风向', text, flags=re.IGNORECASE)
    text = re.sub(r'(M/S)\s*风向', r'm/s 风向', text)
    text = re.sub(r'风速([0-9])', r'风速 \1', text)
    
    # 保证冒号后有空格，便于分段
    text = re.sub(r'(日期|天气|温度|湿度|风速|风向)\s*[:：]', r'\1: ', text)
    
    # 合并多余空白
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def parse_weather_from_text(weather_text: str, record: NoiseDetectionRecord) -> None:
    """从文本中解析天气数据，支持多条记录
    
    文本格式示例：
    日期:2025.9.23 天气 多云 温度26.7-27.4℃湿度66.6-67.4%RH 风速0.9-1.0 m/s 风向东偏北 日期:2025.9.24 天气 多云 温度24.5-28.6℃湿度65.3-67.1%RH 风速1.4-1.5 m/s 风向东偏北
    """
    weather_text = _normalize_weather_text(weather_text)
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
    # 注意：不能排除"风"字，否则"南风"只能匹配到"南"
    wind_dir_pattern = r'风向\s*([^\s日期温度湿度]+?)(?=\s*(?:日期|温度|湿度|风速)|$)'
    
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
            weather_value = w_match.group(1).strip()
            # 如果提取到的值不是"温度"，则认为是天气值
            if weather_value and weather_value != "温度":
                weather.weather = weather_value
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
        # 注意：风向值不应该包含"日期"关键词，如果匹配到包含"日期"的内容，说明匹配错误
        wd_match = re.search(wind_dir_pattern, section)
        if wd_match:
            wind_dir_value = wd_match.group(1).strip()
            # 验证风向值：不应该包含"日期"、"温度"、"湿度"、"风速"等关键词
            if wind_dir_value and "日期" not in wind_dir_value and "温度" not in wind_dir_value and \
               "湿度" not in wind_dir_value and "风速" not in wind_dir_value and \
               not wind_dir_value.startswith("日期") and len(wind_dir_value) < 50:  # 风向值不应该太长
                weather.windDirection = wind_dir_value
                logger.debug(f"[噪声检测] 提取到风向: {weather.windDirection}")
            else:
                logger.warning(f"[噪声检测] 风向值验证失败，跳过: {wind_dir_value}")
        
        # weather 为空且其它气象字段有任意一个不为空时，默认填入“晴”
        if not weather.weather.strip() and any([weather.temp, weather.humidity, weather.windSpeed, weather.windDirection]):
            weather.weather = "晴"
        
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
        # 注意：不能排除"风"字，否则"南风"只能匹配到"南"
        wind_dir_pattern = r'风向\s*([^\s日期温度湿度]+?)(?=\s*(?:日期|温度|湿度|风速)|$)'
        
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
            # 注意：风向值不应该包含"日期"关键词，如果匹配到包含"日期"的内容，说明匹配错误
            wd_match = re.search(wind_dir_pattern, section)
            if wd_match:
                wind_dir_value = wd_match.group(1).strip()
                # 验证风向值：不应该包含"日期"、"温度"、"湿度"、"风速"等关键词
                if wind_dir_value and "日期" not in wind_dir_value and "温度" not in wind_dir_value and \
                   "湿度" not in wind_dir_value and "风速" not in wind_dir_value and \
                   not wind_dir_value.startswith("日期") and len(wind_dir_value) < 50:  # 风向值不应该太长
                    weather.windDirection = wind_dir_value
                    logger.debug(f"[噪声检测] 提取到风向: {weather.windDirection}")
                else:
                    logger.warning(f"[噪声检测] 风向值验证失败，跳过: {wind_dir_value}")
            
            # weather 为空且其它气象字段有任意一个不为空时，默认填入“晴”
            if not weather.weather.strip() and any([weather.temp, weather.humidity, weather.windSpeed, weather.windDirection]):
                weather.weather = "晴"
            
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
    
    if not cell_text:
        return result
    
    # 检查是否包含任何需要解析的字段
    has_any_field = any(keyword in cell_text for keyword in [
        "项目名称", "检测依据", "监测依据", "声级计型号", "声校准器型号", 
        "检测前校准值", "检测后校准值", "声纹计型号", "声级计校准器型号"
    ])
    if not has_any_field:
        return result
    
    # 解析项目名称：项目名称:xxx（后面跟着检测依据或其他字段，可能没有分隔符）
    # 匹配模式：项目名称:xxx（直到检测依据、监测依据、声级计、声校准器、检测前、检测后或气象条件，或到字符串末尾）
    # 注意：项目名称后面可能直接跟着"检测依据"没有分隔符，也可能后面没有其他字段
    project_match = re.search(r'项目名称[:：](.+?)(?:检测依据|监测依据|声级计|声校准器|检测前|检测后|气象条件|</td>|</tr>|$)', cell_text)
    if project_match:
        result["project"] = project_match.group(1).strip()
        # 如果提取到的项目名称为空，可能是正则表达式匹配到了但内容为空
        if not result["project"]:
            # 尝试更简单的匹配：项目名称:后面直到行尾或换行
            project_match2 = re.search(r'项目名称[:：]([^<]+?)(?:</td>|</tr>|$)', cell_text)
            if project_match2:
                result["project"] = project_match2.group(1).strip()
        # 清理project字段，删除"检测依据"及之后的内容（防止正则表达式没有完全匹配到的情况）
        result["project"] = clean_project_field(result["project"])
    
    # 解析检测依据：检测依据:GB 12348-2008 □GB3096-2008 □其他:声级计...
    # 也可能格式为：检测依据:xxx或监测依据:xxx
    # 注意：检测依据后面可能跟着"□其他:"，需要截断到"声级计"或"声校准器"或"检测前"或"检测后"或"气象条件"
    standard_match = re.search(r'(?:检测依据|监测依据)[:：](.+?)(?:声级计|声校准器|检测前|检测后|气象条件)', cell_text)
    if standard_match:
        standard_text = extract_standard_references(standard_match.group(1))
        if standard_text:
            result["standardReferences"] = standard_text
    else:
        # 如果第一个正则没有匹配到，尝试更宽松的匹配：匹配到行尾或下一个字段
        standard_match2 = re.search(r'(?:检测依据|监测依据)[:：]([^声级计声校准器检测前检测后气象条件]+?)(?:声级计|声校准器|检测前|检测后|气象条件|$)', cell_text)
        if standard_match2:
            standard_text = extract_standard_references(standard_match2.group(1))
            if standard_text:
                result["standardReferences"] = standard_text
    
    # 解析声级计型号/编号：声级计型号/编号:AY2201 或 声级计型号:AY2201 或 声级计型号/编号：AWA628+/AY2249
    # 支持包含+号和斜杠的型号，如 AWA628+/AY2249
    sound_meter_match = re.search(r'声级计型号[/：:]?(?:编号)?[:：]\s*([A-Z0-9+/]+)', cell_text)
    if sound_meter_match:
        result["soundLevelMeterMode"] = sound_meter_match.group(1).strip()
    
    # 解析声校准器型号/编号：声校准器型号/编号:AY2204 或 声校准器型号:AY2204
    # 支持包含+号和斜杠的型号
    calibrator_match = re.search(r'声校准器型号[/：:]?(?:编号)?[:：]\s*([A-Z0-9+/]+)', cell_text)
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
    
    # 首先提取OCR关键词补充（如果存在）
    ocr_keywords_comment_match = re.search(r'<!--\s*OCR关键词补充:(.*?)-->', markdown_content, re.DOTALL)
    if ocr_keywords_comment_match:
        keywords_text = ocr_keywords_comment_match.group(1)
        logger.info("[噪声检测] 发现OCR关键词补充，开始提取")
        
        # 提取项目名称
        project_match = re.search(r'项目名称[:：]([^\n]+)', keywords_text)
        if project_match:
            record.project = clean_project_field(project_match.group(1).strip())
            logger.debug(f"[噪声检测] 从OCR关键词补充提取到项目名称: {record.project}")
        
        # 提取检测依据
        standard_match = re.search(r'检测依据[:：]([^\n]+)', keywords_text)
        if standard_match:
            record.standardReferences = extract_standard_references(standard_match.group(1))
            logger.debug(f"[噪声检测] 从OCR关键词补充提取到检测依据: {record.standardReferences}")
        
        # 提取声级计型号/编号
        sound_meter_match = re.search(r'声级计型号/编号[:：]([^\n]+)', keywords_text)
        if sound_meter_match:
            record.soundLevelMeterMode = sound_meter_match.group(1).strip()
            logger.debug(f"[噪声检测] 从OCR关键词补充提取到声级计型号: {record.soundLevelMeterMode}")
        
        # 提取声校准器型号/编号
        calibrator_match = re.search(r'声校准器型号/编号[:：]([^\n]+)', keywords_text)
        if calibrator_match:
            record.soundCalibratorMode = calibrator_match.group(1).strip()
            logger.debug(f"[噪声检测] 从OCR关键词补充提取到声校准器型号: {record.soundCalibratorMode}")
        
        # 提取检测前校准值
        before_cal_match = re.search(r'检测前校准值[:：]([^\n]+)', keywords_text)
        if before_cal_match:
            record.calibrationValueBefore = before_cal_match.group(1).strip()
            logger.debug(f"[噪声检测] 从OCR关键词补充提取到检测前校准值: {record.calibrationValueBefore}")
        
        # 提取检测后校准值
        after_cal_match = re.search(r'检测后校准值[:：]([^\n]+)', keywords_text)
        if after_cal_match:
            record.calibrationValueAfter = after_cal_match.group(1).strip()
            logger.debug(f"[噪声检测] 从OCR关键词补充提取到检测后校准值: {record.calibrationValueAfter}")
        
        # 提取天气信息
        weather_lines = re.findall(r'日期[:：]([^\n]+)', keywords_text)
        for weather_line in weather_lines:
            weather = WeatherData()
            # 解析天气行：日期：xxx 天气：xxx 温度：xxx 湿度：xxx 风速：xxx 风向：xxx
            date_match = re.search(r'日期[:：]\s*([\d.\-]+)', weather_line)
            if date_match:
                weather.monitorAt = date_match.group(1).strip()
            
            weather_match = re.search(r'天气[:：]\s*([^\s温度]+)', weather_line)
            if weather_match:
                weather.weather = weather_match.group(1).strip()
            
            temp_match = re.search(r'温度[:：]\s*([0-9.\-]+)', weather_line)
            if temp_match:
                weather.temp = temp_match.group(1).strip()
            
            humidity_match = re.search(r'湿度[:：]\s*([0-9.\-]+)', weather_line)
            if humidity_match:
                weather.humidity = humidity_match.group(1).strip()
            
            wind_speed_match = re.search(r'风速[:：]\s*([0-9.\-]+)', weather_line)
            if wind_speed_match:
                weather.windSpeed = wind_speed_match.group(1).strip()
            
            # 注意：不能排除"风"字，否则"南风"只能匹配到"南"
            # 使用非贪婪匹配，匹配到下一个字段名或行尾
            wind_dir_match = re.search(r'风向[:：]\s*([^\s日期温度湿度]+?)(?=\s*(?:日期|温度|湿度|风速)|$)', weather_line)
            if wind_dir_match:
                wind_dir_value = wind_dir_match.group(1).strip()
                # 验证风向值：不应该包含"日期"、"温度"、"湿度"、"风速"等关键词
                if wind_dir_value and "日期" not in wind_dir_value and "温度" not in wind_dir_value and \
                   "湿度" not in wind_dir_value and "风速" not in wind_dir_value and \
                   not wind_dir_value.startswith("日期") and len(wind_dir_value) < 50:  # 风向值不应该太长
                    weather.windDirection = wind_dir_value
                else:
                    logger.warning(f"[噪声检测] 风向值验证失败，跳过: {wind_dir_value}")
            
            # 如果天气为空但其他字段有值，默认为"晴"
            if not weather.weather or not weather.weather.strip():
                if any([weather.temp, weather.humidity, weather.windSpeed, weather.windDirection]):
                    weather.weather = "晴"
            
            # 如果至少有一个字段不为空，添加到记录（即使monitorAt为空也先添加，后续会从表格中补充）
            if any([weather.weather, weather.temp, weather.humidity, weather.windSpeed, weather.windDirection]):
                record.weather.append(weather)
                logger.debug(f"[噪声检测] 从OCR关键词补充提取到天气信息: {weather.to_dict()}")
    
    # 保存OCR提取的天气信息（用于后续与表格解析结果合并）
    ocr_weather_list = record.weather.copy() if record.weather else []
    # 清空record.weather，让表格解析重新填充
    record.weather = []
    
    # 使用支持rowspan和colspan的函数提取表格，因为噪声检测表有复杂的表头结构
    tables = extract_table_with_rowspan_colspan(markdown_content)
    
    if not tables:
        logger.warning(f"[噪声检测] 未能提取出任何表格内容")
        return record

    first_table = tables[0]
    
    # 首先尝试从组合单元格中解析头部信息（这种情况是多个字段都在一个单元格中，或者单个字段也在同一单元格中）
    # 同时也支持字段名和值在不同单元格的情况（新格式）
    header_extracted = False
    weather_extracted = False
    for row_idx, row in enumerate(first_table):
        # 先尝试从同一单元格解析（旧格式）
        for cell in row:
            # 检查单元格是否包含头部字段的关键词（放宽条件，支持单个字段的情况）
            # 如果单元格包含字段名和冒号，说明值就在同一单元格中
            has_header_field = any(keyword in cell for keyword in [
                "项目名称", "检测依据", "监测依据", "声级计型号", "声校准器型号", 
                "检测前校准值", "检测后校准值", "声纹计型号", "声级计校准器型号"
            ])
            has_colon = ":" in cell or "：" in cell
            
            if has_header_field and has_colon:
                logger.debug(f"[噪声检测] 发现包含字段信息的单元格，尝试解析: {cell[:100]}...")
                # 清理HTML标签，只保留文本内容
                cell_clean = re.sub(r'<[^>]+>', '', cell).strip()
                parsed_header = parse_header_from_combined_cell(cell_clean)
                
                # 更新字段（如果解析到值）
                if parsed_header["project"] and not record.project:
                    record.project = clean_project_field(parsed_header["project"])
                    header_extracted = True
                    logger.debug(f"[噪声检测] 从单元格解析到项目名称: {record.project}")
                if parsed_header["standardReferences"] and not record.standardReferences:
                    record.standardReferences = parsed_header["standardReferences"]
                    logger.debug(f"[噪声检测] 从单元格解析到检测依据: {record.standardReferences}")
                if parsed_header["soundLevelMeterMode"] and not record.soundLevelMeterMode:
                    record.soundLevelMeterMode = parsed_header["soundLevelMeterMode"]
                    logger.debug(f"[噪声检测] 从单元格解析到声级计型号: {record.soundLevelMeterMode}")
                if parsed_header["soundCalibratorMode"] and not record.soundCalibratorMode:
                    record.soundCalibratorMode = parsed_header["soundCalibratorMode"]
                    logger.debug(f"[噪声检测] 从单元格解析到声校准器型号: {record.soundCalibratorMode}")
                if parsed_header["calibrationValueBefore"] and not record.calibrationValueBefore:
                    record.calibrationValueBefore = parsed_header["calibrationValueBefore"]
                    logger.debug(f"[噪声检测] 从单元格解析到检测前校准值: {record.calibrationValueBefore}")
                if parsed_header["calibrationValueAfter"] and not record.calibrationValueAfter:
                    record.calibrationValueAfter = parsed_header["calibrationValueAfter"]
                    logger.debug(f"[噪声检测] 从单元格解析到检测后校准值: {record.calibrationValueAfter}")
                
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
                
        # 尝试从不同单元格解析（新格式：字段名和值在不同单元格）
        for col_idx, cell in enumerate(row):
            cell_clean = re.sub(r'<[^>]+>', '', cell).strip()
            
            # 声级计型号/编号：在单元格中，值在下一列
            if "声级计型号" in cell_clean and (":" in cell_clean or "：" in cell_clean) and not record.soundLevelMeterMode:
                if col_idx + 1 < len(row) and row[col_idx + 1].strip():
                    record.soundLevelMeterMode = row[col_idx + 1].strip()
                    header_extracted = True
                    logger.debug(f"[噪声检测] 从不同单元格解析到声级计型号: {record.soundLevelMeterMode}")
            
            # 声校准器型号/编号：在单元格中，值在下一列
            if "声校准器型号" in cell_clean and (":" in cell_clean or "：" in cell_clean) and not record.soundCalibratorMode:
                if col_idx + 1 < len(row) and row[col_idx + 1].strip():
                    record.soundCalibratorMode = row[col_idx + 1].strip()
                    header_extracted = True
                    logger.debug(f"[噪声检测] 从不同单元格解析到声校准器型号: {record.soundCalibratorMode}")
            
            # 检测前校准值：在单元格中，值在下一列
            if "检测前校准值" in cell_clean and (":" in cell_clean or "：" in cell_clean) and not record.calibrationValueBefore:
                if col_idx + 1 < len(row) and row[col_idx + 1].strip():
                    cal_value = row[col_idx + 1].strip()
                    # 如果包含单位，保留；否则添加单位
                    if "dB" in cal_value or "dB（A）" in cal_value or "dB(A)" in cal_value:
                        record.calibrationValueBefore = cal_value
                    else:
                        record.calibrationValueBefore = f"{cal_value} dB(A)"
                    header_extracted = True
                    logger.debug(f"[噪声检测] 从不同单元格解析到检测前校准值: {record.calibrationValueBefore}")
            
            # 检测后校准值：在单元格中，值在下一列
            if "检测后校准值" in cell_clean and (":" in cell_clean or "：" in cell_clean) and not record.calibrationValueAfter:
                if col_idx + 1 < len(row) and row[col_idx + 1].strip():
                    cal_value = row[col_idx + 1].strip()
                    # 如果包含单位，保留；否则添加单位
                    if "dB" in cal_value or "dB（A）" in cal_value or "dB(A)" in cal_value:
                        record.calibrationValueAfter = cal_value
                    else:
                        record.calibrationValueAfter = f"{cal_value} dB(A)"
                    header_extracted = True
                    logger.debug(f"[噪声检测] 从不同单元格解析到检测后校准值: {record.calibrationValueAfter}")
        
                # 如果已经解析到所有需要的字段，可以提前结束
                if record.project and record.soundLevelMeterMode and record.calibrationValueBefore and record.calibrationValueAfter:
                    logger.info(f"[噪声检测] 从单元格成功解析到所有头部信息: project={record.project}, "
                              f"soundLevelMeterMode={record.soundLevelMeterMode}, "
                              f"calibrationValueBefore={record.calibrationValueBefore}, "
                              f"calibrationValueAfter={record.calibrationValueAfter}")
                    if not weather_extracted:
                        break
    
    # 如果还没有提取到头部信息，使用原来的方法（假设字段分布在不同的单元格中）
    # 但也要尝试从同一单元格中提取（如果单元格包含字段名和冒号）
    if not header_extracted:
        for row in first_table:
            logger.debug(f"[噪声检测][ROW] len={len(row)}, content={row}")
            for i, cell in enumerate(row):
                # 尝试从同一单元格中提取项目名称（如果包含冒号）
                if "项目名称" in cell and (":" in cell or "：" in cell) and not record.project:
                    # 使用 parse_header_from_combined_cell 解析
                    parsed = parse_header_from_combined_cell(cell)
                    if parsed["project"]:
                        record.project = clean_project_field(parsed["project"])
                        header_extracted = True
                        logger.debug(f"[噪声检测] 从单元格 {i} 解析到项目名称: {record.project}")
                        break
                
                # 如果同一单元格没有值，尝试从下一个单元格获取（向后兼容）
                if "项目名称" in cell and i + 1 < len(row) and not record.project:
                    # 检查下一个单元格是否有内容
                    if row[i + 1].strip():
                        record.project = clean_project_field(row[i + 1].strip())
                        if not record.project.strip():
                            logger.error(f"[噪声检测] 项目名称 为空，行数据: {row}")
                        else:
                            header_extracted = True
                            logger.debug(f"[噪声检测] 从单元格 {i+1} 解析到项目名称: {record.project}")
                        break
                if any(k in row[0] for k in ["检测依据", "监测依据"]):
                    for i, cell in enumerate(row):
                        if any(k in cell for k in ["检测依据", "监测依据"]) and i + 1 < len(row):
                            candidate_standard = extract_standard_references(row[i + 1])
                            if candidate_standard:
                                record.standardReferences = candidate_standard
                                logger.debug(f"[噪声检测] 从行数据解析到检测依据: {record.standardReferences}")
                            else:
                                logger.error(f"[噪声检测] 检测/监测依据 为空或无法解析，行数据: {row}")
                            break
                # 尝试从同一单元格或下一个单元格提取声级计型号
                for i, cell in enumerate(row):
                    if any(k in cell for k in ["声纹计型号", "声级计型号"]) and not record.soundLevelMeterMode:
                        # 先尝试从同一单元格提取（如果包含冒号）
                        if (":" in cell or "：" in cell):
                            parsed = parse_header_from_combined_cell(cell)
                            if parsed["soundLevelMeterMode"]:
                                record.soundLevelMeterMode = parsed["soundLevelMeterMode"]
                                logger.debug(f"[噪声检测] 从单元格 {i} 解析到声级计型号: {record.soundLevelMeterMode}")
                                break
                        # 如果同一单元格没有值，尝试从下一个单元格获取
                        elif i + 1 < len(row) and row[i + 1].strip():
                            record.soundLevelMeterMode = row[i + 1].strip()
                            if not record.soundLevelMeterMode.strip():
                                logger.error(f"[噪声检测] 声级计型号 为空，行数据: {row}")
                            else:
                                logger.debug(f"[噪声检测] 从单元格 {i+1} 解析到声级计型号: {record.soundLevelMeterMode}")
                            break
                
                # 尝试从同一单元格或下一个单元格提取声校准器型号
                for i, cell in enumerate(row):
                    if any(k in cell for k in ["声纹准器型号", "声校准器型号", "声级计校准器型号"]) and not record.soundCalibratorMode:
                        # 先尝试从同一单元格提取（如果包含冒号）
                        if (":" in cell or "：" in cell):
                            parsed = parse_header_from_combined_cell(cell)
                            if parsed["soundCalibratorMode"]:
                                record.soundCalibratorMode = parsed["soundCalibratorMode"]
                                logger.debug(f"[噪声检测] 从单元格 {i} 解析到声校准器型号: {record.soundCalibratorMode}")
                                break
                        # 如果同一单元格没有值，尝试从下一个单元格获取
                        elif i + 1 < len(row) and row[i + 1].strip():
                            record.soundCalibratorMode = row[i + 1].strip()
                            if not record.soundCalibratorMode.strip():
                                logger.error(f"[噪声检测] 声级计校准器型号 为空，行数据: {row}")
                            else:
                                logger.debug(f"[噪声检测] 从单元格 {i+1} 解析到声校准器型号: {record.soundCalibratorMode}")
                            break
                
                # 尝试从同一单元格或下一个单元格提取检测前校准值
                for i, cell in enumerate(row):
                    if "检测前校准值" in cell and not record.calibrationValueBefore:
                        # 先尝试从同一单元格提取（如果包含冒号）
                        if (":" in cell or "：" in cell):
                            parsed = parse_header_from_combined_cell(cell)
                            if parsed["calibrationValueBefore"]:
                                record.calibrationValueBefore = parsed["calibrationValueBefore"]
                                logger.debug(f"[噪声检测] 从单元格 {i} 解析到检测前校准值: {record.calibrationValueBefore}")
                                break
                        # 如果同一单元格没有值，尝试从下一个单元格获取
                        elif i + 1 < len(row) and row[i + 1].strip():
                            record.calibrationValueBefore = row[i + 1].strip()
                            if not record.calibrationValueBefore.strip():
                                logger.error(f"[噪声检测] 检测前校准值 为空，行数据: {row}")
                            else:
                                logger.debug(f"[噪声检测] 从单元格 {i+1} 解析到检测前校准值: {record.calibrationValueBefore}")
                            break
                
                # 尝试从同一单元格或下一个单元格提取检测后校准值
                for i, cell in enumerate(row):
                    if "检测后校准值" in cell and not record.calibrationValueAfter:
                        # 先尝试从同一单元格提取（如果包含冒号）
                        if (":" in cell or "：" in cell):
                            parsed = parse_header_from_combined_cell(cell)
                            if parsed["calibrationValueAfter"]:
                                record.calibrationValueAfter = parsed["calibrationValueAfter"]
                                logger.debug(f"[噪声检测] 从单元格 {i} 解析到检测后校准值: {record.calibrationValueAfter}")
                                break
                        # 如果同一单元格没有值，尝试从下一个单元格获取
                        elif i + 1 < len(row) and row[i + 1].strip():
                            record.calibrationValueAfter = row[i + 1].strip()
                            if not record.calibrationValueAfter.strip():
                                logger.error(f"[噪声检测] 检测后校准值 为空，行数据: {row}")
                            else:
                                logger.debug(f"[噪声检测] 从单元格 {i+1} 解析到检测后校准值: {record.calibrationValueAfter}")
                            break

    # 解析气象条件 - 支持多条记录（如果还没有从组合单元格中提取到天气数据）
    if not weather_extracted:
        # 首先尝试从表格结构中解析（气象条件在第一列，日期在第二列，天气在第三列等）
        for row_idx, row in enumerate(first_table):
            if len(row) < 2:
                continue
            
            # 检查是否是气象条件行（第一列包含"气象条件"）
            if "气象条件" in row[0]:
                # 尝试从表格单元格中解析天气信息
                # 格式：气象条件 | 日期：xxx | 天气 | 温度 | xxx | ...
                # 或者：气象条件 | 日期：xxx | 天气 | 多云 | 温度 | xxx | ...
                
                # 找到日期列（包含"日期"的列）
                date_col_idx = -1
                weather_col_idx = -1
                temp_col_idx = -1
                
                for col_idx, cell in enumerate(row):
                    if "日期" in cell and "：" in cell:
                        date_col_idx = col_idx
                    elif cell.strip() == "天气" or "天气" in cell:
                        weather_col_idx = col_idx
                    elif cell.strip() == "温度" or "温度" in cell:
                        temp_col_idx = col_idx
                
                # 如果找到日期列，尝试解析多行天气数据
                if date_col_idx >= 0:
                    # 从当前行开始，查找所有包含日期的行
                    for check_row_idx in range(row_idx, min(row_idx + 5, len(first_table))):  # 最多检查5行
                        check_row = first_table[check_row_idx]
                        if len(check_row) <= date_col_idx:
                            continue
                        
                        date_cell = check_row[date_col_idx]
                        # 检查是否包含日期
                        date_match = re.search(r'日期[:：]\s*([\d.\-]+)', date_cell)
                        if not date_match:
                            continue
                        
                        weather = WeatherData()
                        weather.monitorAt = date_match.group(1).strip()
                        
                        # 在当前行中重新查找列索引（因为不同行的列结构可能不同）
                        current_weather_col_idx = -1
                        current_temp_col_idx = -1
                        for col_idx, cell in enumerate(check_row):
                            if cell.strip() == "天气" or "天气" in cell:
                                current_weather_col_idx = col_idx
                            elif cell.strip() == "温度" or "温度" in cell:
                                current_temp_col_idx = col_idx
                        
                        # 提取天气（在日期列之后查找）
                        # 天气值在"天气"标签的下一列（如果下一列不是"温度"）
                        if current_weather_col_idx >= 0 and len(check_row) > current_weather_col_idx + 1:
                            weather_value = check_row[current_weather_col_idx + 1].strip()
                            # 如果下一列是天气值（不是"天气"标签，不是"温度"标签，且不是数字），则使用
                            if weather_value and weather_value != "天气" and weather_value != "温度" and not re.match(r'^[\d.\-]+$', weather_value):
                                weather.weather = weather_value
                        else:
                            # 尝试从日期列之后查找"天气"标签，然后取下一列
                            for col_idx in range(date_col_idx + 1, min(date_col_idx + 5, len(check_row))):
                                cell = check_row[col_idx].strip()
                                if cell == "天气" and col_idx + 1 < len(check_row):
                                    # 找到"天气"标签，取下一列的值
                                    next_cell = check_row[col_idx + 1].strip()
                                    if next_cell and next_cell != "天气" and next_cell != "温度" and not re.match(r'^[\d.\-]+$', next_cell):
                                        weather.weather = next_cell
                                        break
                                elif cell and cell != "天气" and cell != "温度" and not re.match(r'^[\d.\-]+$', cell) and col_idx == date_col_idx + 1:
                                    # 日期列之后的第一列可能是天气值（如果格式正确）
                                    weather.weather = cell
                                    break
                        
                        # 提取温度
                        # 温度值在"温度"标签的下一列
                        if current_temp_col_idx >= 0 and len(check_row) > current_temp_col_idx + 1:
                            temp_value = check_row[current_temp_col_idx + 1].strip()
                            # 如果下一列是温度值（包含数字和-），则使用
                            if temp_value and re.match(r'[\d.\-]+', temp_value):
                                weather.temp = temp_value
                        else:
                            # 尝试从日期列之后查找"温度"标签，然后取下一列
                            for col_idx in range(date_col_idx + 1, min(date_col_idx + 6, len(check_row))):
                                cell = check_row[col_idx].strip()
                                if cell == "温度" and col_idx + 1 < len(check_row):
                                    # 找到"温度"标签，取下一列的值
                                    temp_value = check_row[col_idx + 1].strip()
                                    if temp_value and re.match(r'[\d.\-]+', temp_value):
                                        weather.temp = temp_value
                                        break
                                elif "℃" in cell or (re.match(r'[\d.\-]+', cell) and "温度" not in cell):
                                    # 如果直接找到温度值（包含℃或数字），也使用
                                    weather.temp = cell.replace("℃", "").strip()
                                    break
                        
                        # 提取湿度
                        # 注意：新格式中"℃ 湿度"可能在同一个单元格中
                        for col_idx, cell in enumerate(check_row):
                            if "湿度" in cell:
                                # 如果单元格包含"℃ 湿度"，湿度值在下一列
                                if "℃ 湿度" in cell or ("℃" in cell and "湿度" in cell):
                                    if col_idx + 1 < len(check_row):
                                        humidity_value = check_row[col_idx + 1].strip()
                                        if humidity_value and humidity_value != "湿度":
                                            weather.humidity = humidity_value.replace("%RH", "").strip()
                                            break
                                elif col_idx + 1 < len(check_row):
                                    humidity_value = check_row[col_idx + 1].strip()
                                    if humidity_value and humidity_value != "湿度":
                                        weather.humidity = humidity_value.replace("%RH", "").strip()
                                        break
                        
                        # 提取风速
                        # 注意：新格式中"%RH 风速"可能在同一个单元格中
                        for col_idx, cell in enumerate(check_row):
                            if "风速" in cell:
                                # 如果单元格包含"%RH 风速"，风速值在下一列
                                if "%RH 风速" in cell or ("%RH" in cell and "风速" in cell):
                                    if col_idx + 1 < len(check_row):
                                        wind_speed_value = check_row[col_idx + 1].strip()
                                        if wind_speed_value and wind_speed_value != "风速":
                                            weather.windSpeed = wind_speed_value.replace("m/s", "").strip()
                                            break
                                elif col_idx + 1 < len(check_row):
                                    wind_speed_value = check_row[col_idx + 1].strip()
                                    if wind_speed_value and wind_speed_value != "风速":
                                        weather.windSpeed = wind_speed_value.replace("m/s", "").strip()
                                        break
                        
                        # 提取风向
                        for col_idx, cell in enumerate(check_row):
                            if "风向" in cell and col_idx + 1 < len(check_row):
                                wind_dir_value = check_row[col_idx + 1].strip()
                                # 验证风向值：不应该包含"日期"、"温度"、"湿度"、"风速"等关键词
                                if wind_dir_value and wind_dir_value != "风向" and \
                                   "日期" not in wind_dir_value and "温度" not in wind_dir_value and \
                                   "湿度" not in wind_dir_value and "风速" not in wind_dir_value and \
                                   not wind_dir_value.startswith("日期") and len(wind_dir_value) < 50:
                                    weather.windDirection = wind_dir_value
                                    break
                        
                        # 如果天气为空但其他字段有值，默认为"晴"
                        if not weather.weather or not weather.weather.strip():
                            if any([weather.temp, weather.humidity, weather.windSpeed, weather.windDirection]):
                                weather.weather = "晴"
                                logger.debug(f"[噪声检测] 天气字段为空，但其他字段有值，默认为'晴': {weather.monitorAt}")
                        
                        # 如果至少有一个字段不为空，则添加这条记录
                        if any([weather.monitorAt, weather.weather, weather.temp, weather.humidity, weather.windSpeed, weather.windDirection]):
                            record.weather.append(weather)
                            weather_extracted = True
                            logger.info(f"[噪声检测] 从表格解析到天气记录: {weather.to_dict()}")
                    
                    if weather_extracted:
                        break
                
                # 如果表格解析失败，尝试文本解析
                if not weather_extracted:
                    text = " ".join(row[1:])
                    parse_weather_from_text(text, record)
                    if record.weather:
                        weather_extracted = True
                    break
            
    # 将OCR提取的天气信息与表格解析的天气信息进行合并
    # 按顺序匹配风向：第一条OCR天气信息对应第一条表格天气信息，以此类推
    if ocr_weather_list:
        logger.debug(f"[噪声检测] 开始合并OCR和表格解析的天气信息，OCR提取了 {len(ocr_weather_list)} 条，表格解析了 {len(record.weather)} 条")
        
        # 提取OCR风向数组，按顺序匹配到表格解析的天气记录
        ocr_wind_directions = []
        for ocr_weather in ocr_weather_list:
            if ocr_weather.windDirection and ocr_weather.windDirection.strip():
                ocr_wind_directions.append(ocr_weather.windDirection.strip())
            else:
                ocr_wind_directions.append("")  # 保持顺序，即使为空
        
        logger.debug(f"[噪声检测] 从OCR提取的风向数组: {ocr_wind_directions}")
        
        # 按顺序将OCR风向填充到表格解析的天气记录中
        for i, table_weather in enumerate(record.weather):
            if i < len(ocr_wind_directions) and ocr_wind_directions[i]:
                if not table_weather.windDirection or not table_weather.windDirection.strip():
                    table_weather.windDirection = ocr_wind_directions[i]
                    logger.debug(f"[噪声检测] 按顺序填充第{i}条表格天气记录的风向: {table_weather.windDirection}")
        
        # 原有的合并逻辑（用于补充其他字段，如日期、天气、温度等）
        for ocr_weather in ocr_weather_list:
            # 如果OCR提取的天气信息中monitorAt为空，尝试从表格解析的天气信息中匹配
            matched_in_first_branch = False
            if not ocr_weather.monitorAt or not ocr_weather.monitorAt.strip():
                # 根据温度、湿度、风速等字段匹配表格解析的天气信息
                matched = False
                for table_weather in record.weather:
                    # 匹配条件：温度、湿度、风速、风向相同或相似
                    # 确保返回布尔值，避免空字符串导致类型错误
                    temp_match = bool(ocr_weather.temp and table_weather.temp and 
                                     ocr_weather.temp.strip() == table_weather.temp.strip())
                    humidity_match = bool(ocr_weather.humidity and table_weather.humidity and 
                                        ocr_weather.humidity.strip() == table_weather.humidity.strip())
                    wind_speed_match = bool(ocr_weather.windSpeed and table_weather.windSpeed and 
                                           ocr_weather.windSpeed.strip() == table_weather.windSpeed.strip())
                    wind_dir_match = bool(ocr_weather.windDirection and table_weather.windDirection and 
                                         ocr_weather.windDirection.strip() == table_weather.windDirection.strip())
                    
                    # 如果至少有两个字段匹配，认为这是同一条天气记录
                    # 或者如果表格解析的天气记录只有部分字段（如只有windDirection），也尝试合并
                    match_count = sum([temp_match, humidity_match, wind_speed_match, wind_dir_match])
                    # 如果表格解析的天气记录只有windDirection，也尝试合并（通过日期匹配）
                    has_only_wind_dir = (table_weather.windDirection and not table_weather.weather and 
                                        not table_weather.temp and not table_weather.humidity and 
                                        not table_weather.windSpeed)
                    
                    if (match_count >= 2 and table_weather.monitorAt) or (has_only_wind_dir and table_weather.monitorAt):
                        ocr_weather.monitorAt = table_weather.monitorAt
                        logger.debug(f"[噪声检测] 从表格解析结果补充OCR天气信息的日期: {ocr_weather.monitorAt}")
                        # 将OCR提取的所有字段补充到表格解析的天气信息中
                        if not table_weather.weather and ocr_weather.weather:
                            table_weather.weather = ocr_weather.weather
                            logger.debug(f"[噪声检测] 从OCR补充表格解析的天气: {table_weather.weather}")
                        if not table_weather.temp and ocr_weather.temp:
                            table_weather.temp = ocr_weather.temp
                            logger.debug(f"[噪声检测] 从OCR补充表格解析的温度: {table_weather.temp}")
                        if not table_weather.humidity and ocr_weather.humidity:
                            table_weather.humidity = ocr_weather.humidity
                            logger.debug(f"[噪声检测] 从OCR补充表格解析的湿度: {table_weather.humidity}")
                        if not table_weather.windSpeed and ocr_weather.windSpeed:
                            table_weather.windSpeed = ocr_weather.windSpeed
                            logger.debug(f"[噪声检测] 从OCR补充表格解析的风速: {table_weather.windSpeed}")
                        if not table_weather.windDirection and ocr_weather.windDirection:
                            table_weather.windDirection = ocr_weather.windDirection
                            logger.debug(f"[噪声检测] 从OCR补充表格解析的风向: {table_weather.windDirection}")
                        matched = True
                        matched_in_first_branch = True  # 标记已在第一个分支匹配成功
                        break  # 匹配成功后立即退出循环，避免继续匹配
                
                # 如果没有匹配到，但OCR天气信息有其他字段，也添加到记录中（日期为空）
                if not matched:
                    logger.debug(f"[噪声检测] OCR天气信息未匹配到表格解析结果，保留原信息（日期为空）")
            
            # 如果OCR天气信息有日期，且未在第一个分支匹配成功，检查是否与表格解析的天气信息重复
            if ocr_weather.monitorAt and ocr_weather.monitorAt.strip() and not matched_in_first_branch:
                # 检查是否已存在相同日期的天气记录
                # 处理日期格式不一致的情况（如 205.7.10 vs 2025.7.10）
                ocr_date = ocr_weather.monitorAt.strip()
                # 如果日期格式是 205.7.10，尝试修正为 2025.7.10
                if re.match(r'^205\.', ocr_date):  # 匹配 205 开头的日期（OCR识别错误）
                    ocr_date_normalized = re.sub(r'^205\.', '2025.', ocr_date)
                elif re.match(r'^20[0-4]\.', ocr_date):  # 匹配其他 200-204 开头的日期
                    ocr_date_normalized = re.sub(r'^20[0-4]\.', '2025.', ocr_date)
                else:
                    ocr_date_normalized = ocr_date
                
                exists = False
                for table_weather in record.weather:
                    table_date = table_weather.monitorAt.strip() if table_weather.monitorAt else ""
                    # 处理表格日期格式（可能包含末尾的点号，如 "2025.03.28."）
                    table_date_clean = table_date.rstrip('.')
                    ocr_date_clean = ocr_date.rstrip('.')
                    ocr_date_normalized_clean = ocr_date_normalized.rstrip('.')
                    
                    # 直接比较或比较归一化后的日期（忽略末尾的点号）
                    if table_date_clean and (table_date_clean == ocr_date_clean or table_date_clean == ocr_date_normalized_clean):
                        exists = True
                        # 如果表格解析的天气信息不完整，用OCR信息补充
                        if not table_weather.weather and ocr_weather.weather:
                            table_weather.weather = ocr_weather.weather
                            logger.debug(f"[噪声检测] 从OCR补充表格解析的天气: {table_weather.weather}")
                        if not table_weather.temp and ocr_weather.temp:
                            table_weather.temp = ocr_weather.temp
                            logger.debug(f"[噪声检测] 从OCR补充表格解析的温度: {table_weather.temp}")
                        if not table_weather.humidity and ocr_weather.humidity:
                            table_weather.humidity = ocr_weather.humidity
                            logger.debug(f"[噪声检测] 从OCR补充表格解析的湿度: {table_weather.humidity}")
                        if not table_weather.windSpeed and ocr_weather.windSpeed:
                            table_weather.windSpeed = ocr_weather.windSpeed
                            logger.debug(f"[噪声检测] 从OCR补充表格解析的风速: {table_weather.windSpeed}")
                        if not table_weather.windDirection and ocr_weather.windDirection:
                            table_weather.windDirection = ocr_weather.windDirection
                            logger.debug(f"[噪声检测] 从OCR补充表格解析的风向: {table_weather.windDirection}")
                        logger.debug(f"[噪声检测] OCR天气信息与表格解析结果合并: {table_weather.to_dict()}")
                        break  # 找到匹配的记录后立即退出
                
                # 如果不存在相同日期的记录，且OCR信息完整，添加到记录中
                if not exists and any([ocr_weather.weather, ocr_weather.temp, ocr_weather.humidity, 
                                      ocr_weather.windSpeed, ocr_weather.windDirection]):
                    record.weather.append(ocr_weather)
                    logger.debug(f"[噪声检测] 添加OCR天气信息到记录: {ocr_weather.to_dict()}")
            elif not matched_in_first_branch and any([ocr_weather.weather, ocr_weather.temp, ocr_weather.humidity, 
                     ocr_weather.windSpeed, ocr_weather.windDirection]):
                # 如果OCR天气信息没有日期但有其他字段，且未在第一个分支匹配成功，也添加到记录中
                record.weather.append(ocr_weather)
                logger.debug(f"[噪声检测] 添加OCR天气信息到记录（无日期）: {ocr_weather.to_dict()}")
        
        # 最终去重和合并：按日期分组，合并相同日期的记录，补齐空白字段
        if record.weather:
            logger.debug(f"[噪声检测] 合并前天气记录数: {len(record.weather)}")
            deduplicated_weather = {}
            for weather in record.weather:
                date_key = weather.monitorAt.strip() if weather.monitorAt else ""
                if not date_key:
                    # 如果没有日期，跳过（不应该出现，但为了安全）
                    continue
                
                # 处理日期格式不一致的情况（如 205.7.10 vs 2025.7.10）
                if re.match(r'^205\.', date_key):
                    date_key = re.sub(r'^205\.', '2025.', date_key)
                elif re.match(r'^20[0-4]\.', date_key):
                    date_key = re.sub(r'^20[0-4]\.', '2025.', date_key)
                
                if date_key not in deduplicated_weather:
                    # 创建新的天气记录
                    merged_weather = WeatherData()
                    merged_weather.monitorAt = date_key
                    deduplicated_weather[date_key] = merged_weather
                else:
                    merged_weather = deduplicated_weather[date_key]
                
                # 合并字段：如果当前记录的字段有值且合并记录的字段为空，则补齐
                if not merged_weather.weather and weather.weather:
                    merged_weather.weather = weather.weather
                if not merged_weather.temp and weather.temp:
                    merged_weather.temp = weather.temp
                if not merged_weather.humidity and weather.humidity:
                    merged_weather.humidity = weather.humidity
                if not merged_weather.windSpeed and weather.windSpeed:
                    merged_weather.windSpeed = weather.windSpeed
                if not merged_weather.windDirection and weather.windDirection:
                    merged_weather.windDirection = weather.windDirection
            
            # 更新record.weather为去重后的列表
            record.weather = list(deduplicated_weather.values())
            logger.debug(f"[噪声检测] 合并后天气记录数: {len(record.weather)}")
            for weather in record.weather:
                logger.debug(f"[噪声检测] 最终天气记录: {weather.to_dict()}")

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
    
    # 矫正编号：按照数据顺序重新分配编号为 N1, N2, N3...
    for idx, nd in enumerate(record.noise, start=1):
        original_code = nd.code
        nd.code = f"N{idx}"
        if original_code != nd.code:
            logger.info(f"[噪声检测] 编号矫正: {original_code} -> {nd.code}")
    
    # 解析工况信息
    # 优先使用opStatus格式解析（附件 工况及工程信息），如果失败则使用旧格式
    if "附件" in markdown_content and "工况" in markdown_content:
        operational_conditions = parse_operational_conditions_opstatus(markdown_content)
        if operational_conditions:
            logger.info(f"[噪声检测] 使用opStatus格式解析到 {len(operational_conditions)} 条工况信息")
            record.operationalConditions = operational_conditions
        else:
            # 如果opStatus格式解析失败，尝试旧格式
            operational_conditions = parse_operational_conditions(markdown_content)
            record.operationalConditions = operational_conditions
    else:
        operational_conditions = parse_operational_conditions(markdown_content)
        record.operationalConditions = operational_conditions
    
    # v2版本不依赖OCR，只从markdown内容解析
    # 如果某些字段为空，会在日志中记录警告，但不进行OCR补充识别
    
    return record

