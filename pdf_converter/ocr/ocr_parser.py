# Copyright (c) Opendatalab. All rights reserved.

"""OCR文本解析模块"""

from typing import Dict
import re
import html
from ..utils.logging_config import get_logger

logger = get_logger("pdf_converter.ocr.parser")


def parse_noise_detection_record_from_ocr(ocr_text: str) -> Dict:
    """从OCR文本中解析噪声检测记录的基本字段"""
    result = {
        "project": "",
        "standardReferences": "",
        "soundLevelMeterMode": "",
        "soundCalibratorMode": "",
        "calibrationValueBefore": "",
        "calibrationValueAfter": "",
        "weather": []  # 改为数组，支持多条天气记录
    }
    
    if not ocr_text:
        return result
    
    # 如果包含HTML标签，从HTML表格单元格中提取文本
    if '<table' in ocr_text or '<td' in ocr_text or '<tr' in ocr_text:
        # 从HTML表格中提取每个单元格的内容
        import html
        # 提取所有td标签中的文本内容
        td_pattern = r'<td[^>]*>(.*?)</td>'
        td_matches = re.findall(td_pattern, ocr_text, re.DOTALL | re.IGNORECASE)
        
        # 提取每个单元格的纯文本
        cell_texts = []
        for td_content in td_matches:
            # 移除嵌套标签，保留文本
            cell_text = re.sub(r'<[^>]+>', '', td_content)
            # 解码HTML实体
            cell_text = html.unescape(cell_text)
            # 移除所有HTML标签字符（以防万一）
            cell_text = re.sub(r'[<>/]+', '', cell_text)
            # 清理空格
            cell_text = re.sub(r'\s+', ' ', cell_text).strip()
            if cell_text:
                cell_texts.append(cell_text)
        
        # 将单元格文本连接起来，用于正则匹配
        # 同时也保存每个单元格的原始文本，方便按位置提取
        full_text = ' '.join(cell_texts)
        logger.debug(f"[OCR解析] HTML表格单元格文本: {cell_texts}")
        logger.debug(f"[OCR解析] HTML提取后的文本: {full_text[:200]}...")
        
        # 尝试从单元格中直接提取值（按位置）
        # 根据HTML表格结构：第一行包含项目编号、项目名称等，第二行包含声级计、校准值等
        if len(cell_texts) >= 8:
            # 第二行的单元格（索引4-7）：
            # 索引4：声级计型号/编号
            # 索引5：声校准器型号/编号
            # 索引6：检测前校准值
            # 索引7：检测后校准值
            if len(cell_texts) > 6:
                # 检测前校准值（索引6）
                before_cell = cell_texts[6].strip()
                before_match = re.search(r'检测前[：:]\s*校准值[：:]\s*(.*)', before_cell)
                if not before_match:
                    before_match = re.search(r'检测前校准值[：:]\s*(.*)', before_cell)
                if before_match:
                    before_val = before_match.group(1).strip()
                    before_val = re.sub(r'[<>/]+', '', before_val).strip()
                    if before_val and before_val not in ['___', '____', '']:
                        result["calibrationValueBefore"] = before_val
                        logger.debug(f"[OCR解析] 从单元格提取检测前校准值: {before_val}")
            
            if len(cell_texts) > 7:
                # 检测后校准值（索引7）
                after_cell = cell_texts[7].strip()
                after_match = re.search(r'检测后[：:]\s*校准值[：:]\s*(.*)', after_cell)
                if not after_match:
                    after_match = re.search(r'检测后校准值[：:]\s*(.*)', after_cell)
                if after_match:
                    after_val = after_match.group(1).strip()
                    after_val = re.sub(r'[<>/]+', '', after_val).strip()
                    if after_val and after_val not in ['___', '____', '']:
                        result["calibrationValueAfter"] = after_val
                        logger.debug(f"[OCR解析] 从单元格提取检测后校准值: {after_val}")
            
            if len(cell_texts) > 4:
                # 声级计型号/编号（索引4）
                meter_cell = cell_texts[4].strip()
                meter_match = re.search(r'声级计型号[：:/\s]*编号[：:]\s*(.*)', meter_cell)
                if not meter_match:
                    meter_match = re.search(r'声级计[：:/\s]*编号[：:]\s*(.*)', meter_cell)
                if meter_match:
                    meter_val = meter_match.group(1).strip()
                    meter_val = re.sub(r'[<>/]+', '', meter_val).strip()
                    meter_val = re.sub(r'[_\-\—]+', '', meter_val).strip()
                    if meter_val and meter_val not in ['___', '____', '']:
                        result["soundLevelMeterMode"] = meter_val
                        logger.debug(f"[OCR解析] 从单元格提取声级计型号: {meter_val}")
            
            if len(cell_texts) > 5:
                # 声校准器型号/编号（索引5）
                calibrator_cell = cell_texts[5].strip()
                calibrator_match = re.search(r'声校准器型号[：:/\s]*编号[：:]\s*(.*)', calibrator_cell)
                if not calibrator_match:
                    calibrator_match = re.search(r'校准器型号[：:/\s]*编号[：:]\s*(.*)', calibrator_cell)
                if calibrator_match:
                    calibrator_val = calibrator_match.group(1).strip()
                    calibrator_val = re.sub(r'[<>/]+', '', calibrator_val).strip()
                    calibrator_val = re.sub(r'[_\-\—]+', '', calibrator_val).strip()
                    if calibrator_val and calibrator_val not in ['___', '____', '']:
                        result["soundCalibratorMode"] = calibrator_val
                        logger.debug(f"[OCR解析] 从单元格提取声校准器型号: {calibrator_val}")
    else:
        # 按行分割文本，处理多行情况
        lines = [line.strip() for line in ocr_text.split('\n') if line.strip()]
        full_text = ' '.join(lines)
    
    # 项目名称 - 需要在"项目名称："和下一个字段之间提取
    # 项目名称后面可能是"检测依据"、"声级计"、"日期"等
    project_patterns = [
        r'项目名称[：:]\s*([^检测]+?)(?=(?:检测依据|监测依据|声级计|日期|项目编号|$))',
        r'项目名称[：:]\s*([^：:]+?)(?=(?:检测|声级|日期|项目编号|$))',
        r'项目名称[：:]\s*([^\n]+?)(?=\s*(?:检测依据|监测依据|声级计|日期))',
    ]
    for pattern in project_patterns:
        project_match = re.search(pattern, full_text)
        if project_match:
            result["project"] = project_match.group(1).strip()
            # 移除可能包含的其他字段标识
            result["project"] = re.sub(r'\s*(?:检测依据|监测依据|声级计|日期).*$', '', result["project"]).strip()
            break
    
    # 检测依据/监测依据 - 提取到下一个字段或行尾
    reference_patterns = [
        r'(?:检测依据|监测依据)[：:]\s*([^声级计]+?)(?=(?:声级计|日期|项目编号|气象条件|$))',
        r'(?:检测依据|监测依据)[：:]\s*([^\n]+?)(?=\s*(?:声级计|日期|气象条件))',
        r'(?:检测依据|监测依据)[：:]\s*([^\n]+)',
    ]
    for pattern in reference_patterns:
        reference_match = re.search(pattern, full_text)
        if reference_match:
            ref_text = reference_match.group(1).strip()
            # 移除可能的"声级计型号/编号"等后续内容
            ref_text = re.sub(r'\s*声级计.*$', '', ref_text).strip()
            # 移除可能的日期等后续内容
            ref_text = re.sub(r'\s*日期.*$', '', ref_text).strip()
            result["standardReferences"] = ref_text
            break
    
    # 声级计型号/编号 - 可能在同一行或下一行
    # 支持多种格式：声级计型号/编号、声级计型号、声级计编号等
    # 格式示例：声级计型号/编号：___ AY2201 ___ 或 声级计型号/编号：AY2201
    # 从HTML表格中提取：<td>声级计型号/编号：</td>
    meter_patterns = [
        r'声级计型号[：:/\s]*编号[：:]\s*(?:___\s*)?([A-Za-z0-9\-]+(?:\s*[A-Za-z0-9\-]+)?)(?:\s*___)?(?=\s*(?:声校准|检测|日期|校准|气象条件|</td>|$))',
        r'声级计型号[：:/\s]*编号[：:]\s*([A-Za-z0-9\-/]+(?:\s*[A-Za-z0-9\-/]+)?)(?=\s*(?:声校准|检测|日期|校准|气象条件|</td>|$))',
        r'声级计型号[：:]\s*(?:___\s*)?([A-Za-z0-9\-]+(?:\s*[A-Za-z0-9\-]+)?)(?:\s*___)?(?=\s*(?:声校准|检测|日期|校准|气象条件|</td>|$))',
        r'声级计[：:/\s]*编号[：:]\s*(?:___\s*)?([A-Za-z0-9\-]+(?:\s*[A-Za-z0-9\-]+)?)(?:\s*___)?(?=\s*(?:声校准|检测|日期|校准|气象条件|</td>|$))',
        # 处理空值情况（只有标签没有内容）
        r'声级计型号[：:/\s]*编号[：:]\s*$',
    ]
    for pattern in meter_patterns:
        meter_match = re.search(pattern, full_text)
        if meter_match:
            if len(meter_match.groups()) > 0 and meter_match.group(1):
                meter_text = meter_match.group(1).strip()
                # 移除所有占位符（___、____、——等）
                meter_text = re.sub(r'[_\-\—]+', '', meter_text).strip()
                # 移除多余空格
                meter_text = re.sub(r'\s+', ' ', meter_text).strip()
                # 移除HTML标签残留
                meter_text = re.sub(r'<[^>]+>', '', meter_text).strip()
                if meter_text and len(meter_text) > 0:
                    result["soundLevelMeterMode"] = meter_text
                    break
    
    # 声级计校准器型号（可能写作"声校准器"）
    # 格式示例：声校准器型号/编号：___ AY2204 ___ 或 声级计校准器型号：AY2204
    calibrator_patterns = [
        r'声校准器型号[：:/\s]*编号[：:]\s*(?:___\s*)?([A-Za-z0-9\-]+(?:\s*[A-Za-z0-9\-]+)?)(?:\s*___)?(?=\s*(?:检测|日期|校准|气象条件|</td>|$))',
        r'(?:声级计|声)校准器型号[：:/\s]*编号[：:]\s*(?:___\s*)?([A-Za-z0-9\-]+(?:\s*[A-Za-z0-9\-]+)?)(?:\s*___)?(?=\s*(?:检测|日期|校准|气象条件|</td>|$))',
        r'(?:声级计|声)校准器型号[：:]\s*(?:___\s*)?([A-Za-z0-9\-]+(?:\s*[A-Za-z0-9\-]+)?)(?:\s*___)?(?=\s*(?:检测|日期|校准|气象条件|</td>|$))',
        r'校准器型号[：:/\s]*编号[：:]\s*(?:___\s*)?([A-Za-z0-9\-]+(?:\s*[A-Za-z0-9\-]+)?)(?:\s*___)?(?=\s*(?:检测|日期|校准|气象条件|</td>|$))',
    ]
    for pattern in calibrator_patterns:
        calibrator_match = re.search(pattern, full_text)
        if calibrator_match:
            if len(calibrator_match.groups()) > 0 and calibrator_match.group(1):
                calibrator_text = calibrator_match.group(1).strip()
                # 移除所有占位符（___、____、——等）
                calibrator_text = re.sub(r'[_\-\—]+', '', calibrator_text).strip()
                # 移除多余空格
                calibrator_text = re.sub(r'\s+', ' ', calibrator_text).strip()
                # 移除HTML标签残留
                calibrator_text = re.sub(r'<[^>]+>', '', calibrator_text).strip()
                if calibrator_text and len(calibrator_text) > 0:
                    result["soundCalibratorMode"] = calibrator_text
                    break
    
    # 检测前校准值
    # 格式示例：检测前校准值：93.8 dB（A） 或 检测前校准值：___ 93.8 dB（A）
    # 从HTML表格中提取：<td>检测前校准值：93.8 dB（A）</td>
    before_patterns = [
        r'检测前[：:]\s*校准值[：:]\s*(?:___\s*)?([^\s检测后日期校准<>]+(?:\s+[^\s检测后日期校准<>]+)*)(?=\s*(?:检测后|日期|气象条件|校准|$))',
        r'检测前校准值[：:]\s*(?:___\s*)?([^\s检测后日期校准<>]+(?:\s+[^\s检测后日期校准<>]+)*)(?=\s*(?:检测后|日期|气象条件|$))',
        r'检测前[：:]\s*(?:___\s*)?([^\s检测后日期校准<>]+(?:\s+[^\s检测后日期校准<>]+)*)(?=\s*(?:检测后|日期|气象条件|$))',
    ]
    for pattern in before_patterns:
        before_match = re.search(pattern, full_text)
        if before_match:
            if len(before_match.groups()) > 0 and before_match.group(1):
                before_text = before_match.group(1).strip()
                # 移除所有占位符（___、____、——等）
                before_text = re.sub(r'[_\-\—]+', '', before_text).strip()
                # 移除检测后等后续内容
                before_text = re.sub(r'\s*(?:检测后|日期|校准).*$', '', before_text).strip()
                # 移除所有HTML标签（包括闭合标签）
                before_text = re.sub(r'<[^>]+>', '', before_text).strip()
                # 移除可能的HTML标签字符（<、>、/）
                before_text = re.sub(r'[<>/]+', '', before_text).strip()
                # 移除多余空格
                before_text = re.sub(r'\s+', ' ', before_text).strip()
                if before_text and len(before_text) > 0:
                    result["calibrationValueBefore"] = before_text
                    break
    
    # 检测后校准值
    # 格式示例：检测后校准值：94.0 dB（A） 或 检测后校准值：___ 94.0 dB（A）
    # 从HTML表格中提取：<td>检测后校准值：94.0 dB（A）</td>
    after_patterns = [
        r'检测后[：:]\s*校准值[：:]\s*(?:___\s*)?([^\s日期气象条件校准<>]+(?:\s+[^\s日期气象条件校准<>]+)*)(?=\s*(?:日期|气象条件|校准|$))',
        r'检测后校准值[：:]\s*(?:___\s*)?([^\s日期气象条件校准<>]+(?:\s+[^\s日期气象条件校准<>]+)*)(?=\s*(?:日期|气象条件|$))',
        r'检测后[：:]\s*(?:___\s*)?([^\s日期气象条件校准<>]+(?:\s+[^\s日期气象条件校准<>]+)*)(?=\s*(?:日期|气象条件|$))',
    ]
    for pattern in after_patterns:
        after_match = re.search(pattern, full_text)
        if after_match:
            if len(after_match.groups()) > 0 and after_match.group(1):
                after_text = after_match.group(1).strip()
                # 移除所有占位符（___、____、——等）
                after_text = re.sub(r'[_\-\—]+', '', after_text).strip()
                # 移除日期等后续内容
                after_text = re.sub(r'\s*(?:日期|校准).*$', '', after_text).strip()
                # 移除所有HTML标签（包括闭合标签）
                after_text = re.sub(r'<[^>]+>', '', after_text).strip()
                # 移除可能的HTML标签字符（<、>、/）
                after_text = re.sub(r'[<>/]+', '', after_text).strip()
                # 移除多余空格
                after_text = re.sub(r'\s+', ' ', after_text).strip()
                if after_text and len(after_text) > 0:
                    result["calibrationValueAfter"] = after_text
                    break
    
    # 气象条件 - 可能有多条记录
    # 使用改进的解析方式，先按日期分割，然后分别解析每个字段
    weather_records = []
    
    # 方法1：尝试使用正则表达式匹配完整的天气记录段落
    # 每条记录从"日期："开始，到下一个"日期："、"气象条件"或文本结束
    weather_pattern = r'日期[：:]\s*([\d.\-]+).*?(?=(?:日期[：:]|气象条件|项目编号|项目名称|检测依据|$))'
    weather_sections = re.finditer(weather_pattern, full_text, re.DOTALL | re.IGNORECASE)
    
    for section_match in weather_sections:
        weather_text = section_match.group(0)
        # 移除"气象条件"文本，避免影响字段匹配
        weather_text = re.sub(r'\s*气象条件\s*', '', weather_text).strip()
        weather_data = {}
        
        # 解析日期
        date_match = re.search(r'日期[：:]\s*([\d.\-]+)', weather_text)
        if date_match:
            weather_data["monitorAt"] = date_match.group(1).strip()
        
        # 解析天气 - 匹配"天气"后面的中文词，直到遇到下一个关键词或空格
        weather_val_match = re.search(r'天气\s*([^\s温度湿度风速风向]+?)(?=\s*(?:温度|湿度|风速|风向|$))', weather_text)
        if weather_val_match:
            weather_data["weather"] = weather_val_match.group(1).strip()
        
        # 解析温度（支持范围和单位）- 匹配"温度"后面的数字范围，直到遇到单位℃或空格
        # 格式：温度26.7-27.4 ℃ 或 温度26.7 ℃
        temp_match = re.search(r'温度\s*([0-9.]+(?:-[0-9.]+)?)\s*℃?', weather_text)
        if temp_match:
            temp_val = temp_match.group(1).strip()
            weather_data["temp"] = temp_val
        
        # 解析湿度（支持范围和单位）- 匹配"湿度"后面的数字范围，直到遇到单位%RH或空格
        # 格式：湿度66.6-67.4 %RH 或 湿度66.6 %RH
        humidity_match = re.search(r'湿度\s*([0-9.]+(?:-[0-9.]+)?)\s*%?RH?', weather_text)
        if humidity_match:
            humidity_val = humidity_match.group(1).strip()
            weather_data["humidity"] = humidity_val
        
        # 解析风速（支持范围和单位）- 匹配"风速"后面的数字范围，直到遇到单位m/s或空格
        # 格式：风速0.9-1.0 m/s 或 风速0.9 m/s
        wind_speed_match = re.search(r'风速\s*([0-9.]+(?:-[0-9.]+)?)\s*m/?s?', weather_text)
        if wind_speed_match:
            wind_speed_val = wind_speed_match.group(1).strip()
            weather_data["windSpeed"] = wind_speed_val
        
        # 解析风向 - 匹配"风向"后面的中文字符，直到遇到下一个关键词或空格
        wind_dir_match = re.search(r'风向\s*([^\s温度湿度风速日期]+?)(?=\s*(?:温度|湿度|风速|日期|气象条件|$))', weather_text)
        if wind_dir_match:
            weather_data["windDirection"] = wind_dir_match.group(1).strip()
        
        # 如果至少有一个字段不为空，则添加这条记录
        if any(weather_data.values()):
            weather_records.append(weather_data)
    
    # 如果没有找到匹配的记录，尝试使用改进的解析方式
    if not weather_records:
        # 尝试提取所有包含日期的段落，每条记录从"日期："开始，到下一个"日期："或"气象条件"或文本结束
        # 注意：要包含"气象条件"之前的最后一个日期段落
        date_pattern = r'日期[：:]\s*([\d.\-]+).*?(?=(?:日期[：:]|气象条件|项目编号|项目名称|检测依据|$))'
        date_sections = re.finditer(date_pattern, full_text, re.DOTALL)
        
        for date_section in date_sections:
            weather_text = date_section.group(0)
            # 移除"气象条件"文本，避免影响字段匹配
            weather_text = re.sub(r'\s*气象条件\s*', '', weather_text).strip()
            weather_data = {}
            
            # 解析日期
            date_match = re.search(r'日期[：:]\s*([\d.\-]+)', weather_text)
            if date_match:
                weather_data["monitorAt"] = date_match.group(1).strip()
            
            # 解析天气 - 匹配"天气"后面的中文词，直到遇到下一个关键词或空格
            weather_val_match = re.search(r'天气\s*([^\s温度湿度风速风向]+?)(?=\s*(?:温度|湿度|风速|风向|$))', weather_text)
            if weather_val_match:
                weather_data["weather"] = weather_val_match.group(1).strip()
            
            # 解析温度（支持范围和单位）
            temp_match = re.search(r'温度\s*([0-9.]+(?:-[0-9.]+)?)\s*℃?', weather_text)
            if temp_match:
                temp_val = temp_match.group(1).strip()
                weather_data["temp"] = temp_val
            
            # 解析湿度（支持范围和单位）
            humidity_match = re.search(r'湿度\s*([0-9.]+(?:-[0-9.]+)?)\s*%?RH?', weather_text)
            if humidity_match:
                humidity_val = humidity_match.group(1).strip()
                weather_data["humidity"] = humidity_val
            
            # 解析风速（支持范围和单位）
            wind_speed_match = re.search(r'风速\s*([0-9.]+(?:-[0-9.]+)?)\s*m/?s?', weather_text)
            if wind_speed_match:
                wind_speed_val = wind_speed_match.group(1).strip()
                weather_data["windSpeed"] = wind_speed_val
            
            # 解析风向
            wind_dir_match = re.search(r'风向\s*([^\s温度湿度风速日期]+?)(?=\s*(?:温度|湿度|风速|日期|气象条件|$))', weather_text)
            if wind_dir_match:
                weather_data["windDirection"] = wind_dir_match.group(1).strip()
            
            # 如果至少有一个字段不为空，则添加这条记录
            if any(weather_data.values()):
                weather_records.append(weather_data)
    
    # 将解析到的天气记录添加到结果中
    if weather_records:
        result["weather"] = weather_records
    
    # 最终清理所有字段中的HTML标签残留
    for key in ["project", "standardReferences", "soundLevelMeterMode", "soundCalibratorMode", 
                "calibrationValueBefore", "calibrationValueAfter"]:
        if result[key]:
            # 移除所有HTML标签
            result[key] = re.sub(r'<[^>]+>', '', result[key])
            # 移除HTML标签字符
            result[key] = re.sub(r'[<>/]+', '', result[key])
            # 清理空格
            result[key] = re.sub(r'\s+', ' ', result[key]).strip()
    
    logger.debug(f"[OCR解析] 原始文本: {ocr_text[:200]}")
    logger.debug(f"[OCR解析] 解析结果: {result}")
    return result

