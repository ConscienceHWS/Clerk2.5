# Copyright (c) Opendatalab. All rights reserved.

"""JSON转换模块 v2 - 独立版本，不依赖v1"""

from typing import Dict, Any, Optional, List
import re
import os
from copy import deepcopy
from PIL import Image

from ..utils.logging_config import get_logger
from ..utils.paddleocr_fallback import fallback_parse_with_paddleocr, call_paddleocr
from .document_type import detect_document_type
from .noise_parser import parse_noise_detection_record
from .electromagnetic_parser import parse_electromagnetic_detection_record
from .investment_parser import parse_investment_record
from .table_parser import parse_operational_conditions, parse_operational_conditions_v2, parse_operational_conditions_opstatus, parse_operational_conditions_format3_5

logger = get_logger("pdf_converter_v2.parser.json")

NOISE_HEADER_FIELDS = [
    "project",
    "standardReferences",
    "soundLevelMeterMode",
    "soundCalibratorMode",
    "calibrationValueBefore",
    "calibrationValueAfter",
]

WEATHER_VALUE_FIELDS = ["weather", "temp", "humidity", "windSpeed", "windDirection"]


def _normalize_date(date: Optional[str]) -> str:
    if not date:
        return ""
    return date.strip().rstrip(".")


def _merge_weather_lists(
    primary: Optional[List[Dict[str, Any]]],
    secondary: Optional[List[Dict[str, Any]]]
) -> List[Dict[str, Any]]:
    if not primary and not secondary:
        return []
    if not primary:
        return deepcopy(secondary or [])

    merged = deepcopy(primary)
    if not secondary:
        return merged

    date_to_index: Dict[str, int] = {}
    empty_indices: List[int] = []
    for idx, item in enumerate(merged):
        norm_date = _normalize_date(item.get("monitorAt"))
        if norm_date:
            date_to_index.setdefault(norm_date, idx)
        else:
            empty_indices.append(idx)

    for src in secondary:
        norm_date = _normalize_date(src.get("monitorAt"))
        target = None
        if norm_date and norm_date in date_to_index:
            target = merged[date_to_index[norm_date]]
        elif empty_indices:
            target = merged[empty_indices.pop(0)]

        if target:
            if not _normalize_date(target.get("monitorAt")) and src.get("monitorAt"):
                target["monitorAt"] = src["monitorAt"]
            for field in WEATHER_VALUE_FIELDS:
                if (not target.get(field) or not str(target.get(field)).strip()) and src.get(field):
                    target[field] = src[field]
        else:
            merged.append(deepcopy(src))

    return merged


def _merge_noise_records(
    primary: Optional[Dict[str, Any]],
    secondary: Optional[Dict[str, Any]],
    preserve_primary_noise: bool = True
) -> Dict[str, Any]:
    if not primary and not secondary:
        return {}

    merged = deepcopy(primary) if primary else {}
    secondary = secondary or {}

    for field in NOISE_HEADER_FIELDS:
        primary_value = merged.get(field) if merged else ""
        secondary_value = secondary.get(field)
        if (not primary_value or not str(primary_value).strip()) and secondary_value:
            merged[field] = secondary_value

    merged["weather"] = _merge_weather_lists(merged.get("weather"), secondary.get("weather"))

    if not merged.get("operationalConditions") and secondary.get("operationalConditions"):
        merged["operationalConditions"] = deepcopy(secondary["operationalConditions"])

    if preserve_primary_noise and primary and primary.get("noise"):
        merged["noise"] = deepcopy(primary["noise"])
    elif not merged.get("noise") and secondary.get("noise"):
        merged["noise"] = deepcopy(secondary["noise"])

    return merged


def _merge_electromagnetic_records(
    primary: Optional[Dict[str, Any]],
    secondary: Optional[Dict[str, Any]],
    preserve_primary_electric_magnetic: bool = True
) -> Dict[str, Any]:
    """合并电磁检测记录的原始和fallback解析结果
    
    Args:
        primary: 原始解析结果
        secondary: fallback解析结果
        preserve_primary_electric_magnetic: 是否保留原始的电测数据（默认True）
        
    Returns:
        合并后的数据
    """
    if not primary and not secondary:
        return {}
    
    merged = deepcopy(primary) if primary else {}
    secondary = secondary or {}
    
    logger.info(f"[合并数据] 开始合并，primary project: {repr(merged.get('project'))}, secondary project: {repr(secondary.get('project'))}")
    
    # 合并头部字段（如果原始结果中字段为空，使用fallback结果）
    header_fields = ["project", "standardReferences", "deviceName", "deviceMode", "deviceCode", "monitorHeight"]
    for field in header_fields:
        primary_value = merged.get(field) if merged else ""
        secondary_value = secondary.get(field)
        logger.info(f"[合并数据] 检查字段 {field}: primary={repr(primary_value)}, secondary={repr(secondary_value)}")
        if (not primary_value or not str(primary_value).strip()) and secondary_value:
            merged[field] = secondary_value
            logger.info(f"[合并数据] 从fallback结果补充头部字段: {field} = {secondary_value}")
        else:
            logger.info(f"[合并数据] 字段 {field} 不满足合并条件，跳过")
    
    # 合并天气信息
    primary_weather = merged.get("weather", {}) if merged else {}
    secondary_weather = secondary.get("weather", {}) or {}
    for field in ["weather", "temp", "humidity", "windSpeed", "windDirection"]:
        primary_value = primary_weather.get(field) if primary_weather else ""
        secondary_value = secondary_weather.get(field)
        if (not primary_value or not str(primary_value).strip()) and secondary_value:
            if "weather" not in merged:
                merged["weather"] = {}
            merged["weather"][field] = secondary_value
    
    # 合并电测数据：优先保留原始数据，如果原始数据为空则使用fallback数据
    # 但是需要合并每个数据项的address字段（如果原始数据中address为空，使用fallback数据）
    if preserve_primary_electric_magnetic and primary and primary.get("electricMagnetic"):
        merged["electricMagnetic"] = deepcopy(primary["electricMagnetic"])
        # 合并每个数据项的address字段
        secondary_electric_magnetic = secondary.get("electricMagnetic", [])
        if secondary_electric_magnetic:
            # 建立编号到数据项的映射
            code_to_em = {em.get("code", "").upper(): em for em in merged["electricMagnetic"]}
            # 从secondary中提取address并填充到merged中
            for sec_em in secondary_electric_magnetic:
                sec_code = sec_em.get("code", "").upper()
                sec_address = sec_em.get("address", "")
                if sec_code in code_to_em and sec_address:
                    # 如果merged中对应数据项的address为空，使用secondary的address
                    if not code_to_em[sec_code].get("address") or not str(code_to_em[sec_code].get("address")).strip():
                        code_to_em[sec_code]["address"] = sec_address
                        logger.info(f"[合并数据] 从fallback结果补充地址: {sec_code} -> {sec_address}")
    elif not merged.get("electricMagnetic") and secondary.get("electricMagnetic"):
        merged["electricMagnetic"] = deepcopy(secondary["electricMagnetic"])
    
    return merged


def parse_markdown_to_json(markdown_content: str, first_page_image: Optional[Image.Image] = None, output_dir: Optional[str] = None, forced_document_type: Optional[str] = None, enable_paddleocr_fallback: bool = True, input_file: Optional[str] = None) -> Dict[str, Any]:
    """将Markdown内容转换为JSON - v2独立版本，不依赖v1和OCR
    如果提供 forced_document_type（正式全称），则优先按指定类型解析。
    支持映射：
      - noiseMonitoringRecord -> 使用噪声解析
      - electromagneticTestRecord -> 使用电磁解析
      - 其他类型：返回空数据占位
    
    Args:
        markdown_content: markdown内容
        first_page_image: 第一页图片（v2版本不使用）
        output_dir: 输出目录（用于查找图片进行备用解析）
        forced_document_type: 强制文档类型
        enable_paddleocr_fallback: 是否启用PaddleOCR备用解析（默认True）
        input_file: 原始输入文件路径（PDF或图片），用于从PDF提取第一页
    """
    original_markdown = markdown_content
    
    logger.info(f"[JSON转换] 开始解析，forced_document_type={forced_document_type}")
    
    if forced_document_type:
        auto_weather_default = False
        if forced_document_type == "noiseMonitoringRecord":
            noise_record = parse_noise_detection_record(markdown_content, first_page_image=None, output_dir=output_dir)
            auto_weather_default = getattr(noise_record, "_auto_weather_default_used", False)
            data = noise_record.to_dict()
            result = {"document_type": forced_document_type, "data": data}
        elif forced_document_type == "electromagneticTestRecord":
            data = parse_electromagnetic_detection_record(markdown_content).to_dict()
            result = {"document_type": forced_document_type, "data": data}
        elif forced_document_type == "operatingConditionInfo":
            # 仅解析工况信息
            # 优先级：表1检测工况格式 > 格式3/5 > opStatus格式 > 旧格式
            # 1. 检查是否为"表1检测工况"格式（使用正则表达式，允许中间有空格）
            # 支持：表1检测工况、表 1 检测工况、表 1检测工况、表1 检测工况 等变体
            pattern = r'表\s*1\s*检测工况'
            if re.search(pattern, markdown_content):
                logger.info("[JSON转换] 检测到'表1检测工况'标识（包括空格变体），使用新格式解析")
                op_list = parse_operational_conditions_v2(markdown_content)
                serialized = [oc.to_dict() if hasattr(oc, "to_dict") else oc for oc in (op_list or [])]
                return {"document_type": forced_document_type, "data": {"operationalConditions": serialized}}
            
            # 2. 检查是否为格式3/5（附件 2 工况信息 或 附件 2 工况及工程信息，电压列第一列存储时间段）
            # 更精确的判断：必须包含"附件"和"2"，且包含"工况信息"或"工况及工程信息"
            # 排除格式4（"附件 工况及工程信息"没有"2"）
            has_attachment_2 = re.search(r'附件\s*2', markdown_content) or ("附件2" in markdown_content)
            has_condition_info = "工况信息" in markdown_content or "工况及工程信息" in markdown_content
            
            if has_attachment_2 and has_condition_info:
                logger.info("[JSON转换] 检测到'附件 2 工况信息'或'附件 2 工况及工程信息'格式，尝试使用格式3/5解析")
                op_list = parse_operational_conditions_format3_5(markdown_content)
                if op_list:
                    # 格式3/5返回OperationalConditionV2格式
                    serialized = [oc.to_dict() if hasattr(oc, "to_dict") else oc for oc in op_list]
                    logger.info(f"[JSON转换] 格式3/5解析成功，共解析到 {len(serialized)} 条记录")
                    
                    # 检查是否有缺失字段（如minReactivePower为空）
                    has_missing_fields = False
                    required_fields = ["maxVoltage", "minVoltage", "maxCurrent", "minCurrent", 
                                     "maxActivePower", "minActivePower", "maxReactivePower", "minReactivePower"]
                    for record in serialized:
                        for field in required_fields:
                            if not record.get(field) or record.get(field) == "":
                                has_missing_fields = True
                                logger.warning(f"[JSON转换] 检测到缺失字段: {field} 在记录 {record.get('name', 'unknown')} 中为空")
                                break
                        if has_missing_fields:
                            break
                    
                    # 如果有缺失字段，调用paddle ocr获取JSON来补充缺失字段
                    if has_missing_fields and enable_paddleocr_fallback and (output_dir or input_file):
                        logger.info("[JSON转换] 检测到缺失字段，调用PaddleOCR OCR获取JSON来补充")
                        try:
                            # 查找图片路径
                            image_path = None
                            if output_dir:
                                from ..utils.paddleocr_fallback import extract_image_from_markdown
                                image_path = extract_image_from_markdown(markdown_content, output_dir)
                            
                            # 如果从markdown中找不到图片，尝试从input_file提取
                            if not image_path and input_file:
                                from ..utils.paddleocr_fallback import extract_first_page_from_pdf, detect_file_type
                                file_type = detect_file_type(input_file)
                                if file_type == 'pdf':
                                    image_path = extract_first_page_from_pdf(input_file, output_dir)
                                elif file_type in ['png', 'jpeg', 'jpg']:
                                    image_path = input_file
                            
                            if image_path and os.path.exists(image_path):
                                logger.info(f"[JSON转换] 使用PaddleOCR OCR解析图片: {image_path}")
                                from ..utils.paddleocr_fallback import call_paddleocr_ocr, supplement_missing_fields_from_ocr_json
                                
                                # 调用OCR获取JSON
                                ocr_save_path = os.path.dirname(image_path) if image_path else output_dir
                                ocr_texts, ocr_json_path = call_paddleocr_ocr(image_path, ocr_save_path)
                                
                                if ocr_json_path and os.path.exists(ocr_json_path):
                                    logger.info(f"[JSON转换] 从OCR JSON文件补充缺失字段: {ocr_json_path}")
                                    # 使用OCR JSON补充缺失字段
                                    serialized = supplement_missing_fields_from_ocr_json(serialized, ocr_json_path)
                                    logger.info("[JSON转换] OCR字段补充完成")
                                else:
                                    logger.warning("[JSON转换] 未找到OCR JSON文件，无法补充缺失字段")
                            else:
                                logger.warning("[JSON转换] 未找到可用的图片文件，无法使用PaddleOCR OCR补充")
                        except Exception as e:
                            logger.exception(f"[JSON转换] PaddleOCR OCR补充过程出错: {e}")
                    
                    return {"document_type": forced_document_type, "data": {"operationalConditions": serialized}}
                else:
                    logger.debug("[JSON转换] 格式3/5解析未找到结果，继续尝试其他格式")
            
            # 3. 检查是否为opStatus格式（附件 工况及工程信息，没有"2"，表格结构是U/I/P/Q）
            # 格式4：附件 工况及工程信息（没有"2"），且表格结构是U/I/P/Q（不是"检测时间 项目"格式）
            # 先检查表格结构，避免误判包含"检测时间"和"项目"列的格式2
            is_opstatus_format = False
            if "附件" in markdown_content and "工况" in markdown_content and not has_attachment_2:
                # 检查表格结构：opStatus格式的表头应该是"名称 时间 U (kV) I (A) P (MW) Q (Mvar)"
                # 而不是"检测时间 项目 电压 电流 有功功率 无功功率"
                from ..parser.table_parser import extract_table_with_rowspan_colspan
                tables = extract_table_with_rowspan_colspan(markdown_content)
                for table in tables:
                    if table and len(table) > 0:
                        first_row = table[0]
                        first_row_text = " ".join(first_row).lower()
                        # 如果包含"检测时间"和"项目"，则不是opStatus格式（可能是格式2）
                        if "检测时间" in first_row_text and "项目" in first_row_text:
                            logger.debug("[JSON转换] 表格包含'检测时间'和'项目'列，不是opStatus格式，跳过")
                            is_opstatus_format = False
                            break
                        # 如果包含"运行工况"或"U (kV)"、"I (A)"等，则是opStatus格式
                        if "运行工况" in first_row_text or ("u" in first_row_text and "kv" in first_row_text):
                            is_opstatus_format = True
                            break
            
            if is_opstatus_format:
                logger.info("[JSON转换] 检测到'附件 工况及工程信息'格式（格式4），使用opStatus格式解析，返回OperationalCondition格式")
                op_list = parse_operational_conditions_opstatus(markdown_content)
                # 格式4直接返回OperationalCondition格式（旧格式），不转换为V2格式
                serialized = [oc.to_dict() if hasattr(oc, "to_dict") else oc for oc in (op_list or [])]
                return {"document_type": forced_document_type, "data": {"operationalConditions": serialized}}
            
            # 3. 使用旧格式解析（先尝试有标题模式，如果失败则尝试无标题模式）
            logger.info("[JSON转换] 未检测到特殊格式标识，使用旧格式解析")
            op_list = parse_operational_conditions(markdown_content, require_title=True)
            # 如果没有找到结果，尝试无标题模式（仅根据表格结构判断）
            if not op_list:
                logger.info("[JSON转换] 有标题模式未找到结果，尝试无标题模式解析")
                op_list = parse_operational_conditions(markdown_content, require_title=False)
            serialized = [oc.to_dict() if hasattr(oc, "to_dict") else oc for oc in (op_list or [])]
            result = {"document_type": forced_document_type, "data": {"operationalConditions": serialized}}
        elif forced_document_type in ["fsApproval", "fsReview", "pdApproval", "safetyFsApproval"]:
            # 投资估算类型处理
            logger.info(f"[JSON转换] 处理投资估算类型: {forced_document_type}")
            logger.debug(f"[JSON转换] Markdown内容长度: {len(markdown_content)} 字符")
            
            investment_record = parse_investment_record(markdown_content, forced_document_type)
            
            if investment_record:
                data = investment_record.to_dict()
                # safetyFsApproval 可能返回 {"projectInfo": {...}, "data": [...]}，取列表用于条数与摘要
                record_list = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                logger.info(f"[JSON转换] 投资估算解析成功，共 {len(record_list)} 条记录")
                if record_list:
                    for idx, item in enumerate(record_list[:3]):
                        if isinstance(item, dict):
                            logger.debug(f"[JSON转换] 记录 {idx+1}: No={item.get('No', '')}, Name={item.get('name', '')}, Level={item.get('Level', '')}")
                result = {"document_type": forced_document_type, "data": data}
            else:
                logger.error("[JSON转换] 投资估算解析失败：parse_investment_record 返回 None")
                result = {"document_type": forced_document_type, "data": [], "error": "投资估算解析失败"}
        elif forced_document_type == "finalAccount":
            # 决算报告类型处理
            logger.info(f"[JSON转换] 处理决算报告类型: {forced_document_type}")
            logger.debug(f"[JSON转换] Markdown内容长度: {len(markdown_content)} 字符")
            
            from .investment_parser import parse_final_account_record
            final_account_record = parse_final_account_record(markdown_content)
            
            if final_account_record:
                data = final_account_record.to_dict()
                logger.info(f"[JSON转换] 决算报告解析成功，共 {len(data)} 条记录")
                
                # 输出前3条记录的摘要
                if data:
                    for idx, item in enumerate(data[:3]):
                        logger.debug(f"[JSON转换] 记录 {idx+1}: No={item.get('No', '')}, Name={item.get('name', '')}, feeName={item.get('feeName', '')}")
                
                result = {"document_type": forced_document_type, "data": data}
            else:
                logger.error("[JSON转换] 决算报告解析失败：parse_final_account_record 返回 None")
                result = {"document_type": forced_document_type, "data": [], "error": "决算报告解析失败"}
        else:
            result = {"document_type": forced_document_type, "data": {}}
        
        # 对于forced_document_type，也检查数据完整性
        if enable_paddleocr_fallback and result.get("document_type") in ["noiseMonitoringRecord", "electromagneticTestRecord"]:
            try:
                from ..utils.paddleocr_fallback import check_json_data_completeness
                is_complete = check_json_data_completeness(result, result.get("document_type"))
                if auto_weather_default and result.get("document_type") == "noiseMonitoringRecord":
                    logger.warning("[JSON转换] 检测到天气字段使用默认值，尝试使用PaddleOCR备用解析")
                    is_complete = False
                
                if not is_complete:
                    logger.warning(f"[JSON转换] 检测到数据缺失，尝试使用PaddleOCR备用解析")
                    fallback_markdown = fallback_parse_with_paddleocr(
                        result,
                        original_markdown,
                        output_dir=output_dir,
                        document_type=result.get("document_type"),
                        input_file=input_file
                    )
                    
                    if fallback_markdown:
                        logger.info("[JSON转换] PaddleOCR备用解析成功，重新解析JSON")
                        if result.get("document_type") == "noiseMonitoringRecord":
                            original_data = result.get("data", {}) or {}
                            fallback_data = parse_noise_detection_record(fallback_markdown, first_page_image=None, output_dir=output_dir).to_dict()
                            merged_data = _merge_noise_records(
                                primary=original_data,
                                secondary=fallback_data,
                                preserve_primary_noise=True
                            )
                            result = {"document_type": "noiseMonitoringRecord", "data": merged_data}
                        elif result.get("document_type") == "electromagneticTestRecord":
                            original_data = result.get("data", {}) or {}
                            fallback_data = parse_electromagnetic_detection_record(fallback_markdown).to_dict()
                            logger.info(f"[JSON转换] fallback_data project: {repr(fallback_data.get('project'))}, EB1 address: {repr(fallback_data.get('electricMagnetic', [{}])[0].get('address') if fallback_data.get('electricMagnetic') else '')}")
                            merged_data = _merge_electromagnetic_records(
                                primary=original_data,
                                secondary=fallback_data,
                                preserve_primary_electric_magnetic=True
                            )
                            logger.info(f"[JSON转换] merged_data project: {repr(merged_data.get('project'))}, EB1 address: {repr(merged_data.get('electricMagnetic', [{}])[0].get('address') if merged_data.get('electricMagnetic') else '')}")
                            result = {"document_type": "electromagneticTestRecord", "data": merged_data}
                        logger.info("[JSON转换] 使用PaddleOCR结果重新解析完成")
            except Exception as e:
                logger.exception(f"[JSON转换] PaddleOCR备用解析过程出错: {e}")
        
        return result

    auto_weather_default = False
    doc_type = detect_document_type(markdown_content)
    
    if doc_type == "noiseRec":
        # v2版本不依赖OCR，first_page_image参数会被忽略
        noise_record = parse_noise_detection_record(markdown_content, first_page_image=None, output_dir=output_dir)
        auto_weather_default = getattr(noise_record, "_auto_weather_default_used", False)
        data = noise_record.to_dict()
        result = {"document_type": doc_type, "data": data}
    elif doc_type == "emRec":
        data = parse_electromagnetic_detection_record(markdown_content).to_dict()
        result = {"document_type": doc_type, "data": data}
    elif doc_type in ["fsApproval", "fsReview", "pdApproval", "safetyFsApproval"]:
        # 新增：投资估算类型
        logger.info(f"[JSON转换] 检测到投资估算类型: {doc_type}")
        logger.debug(f"[JSON转换] Markdown内容长度: {len(markdown_content)} 字符")
        
        investment_record = parse_investment_record(markdown_content, doc_type)
        
        if investment_record:
            data = investment_record.to_dict()
            # safetyFsApproval 可能返回 {"projectInfo": {...}, "data": [...]}，取列表用于条数与摘要
            record_list = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            logger.info(f"[JSON转换] 投资估算解析成功，共 {len(record_list)} 条记录")
            if record_list:
                for idx, item in enumerate(record_list[:3]):
                    if isinstance(item, dict):
                        logger.debug(f"[JSON转换] 记录 {idx+1}: No={item.get('No', '')}, Name={item.get('name', '')}, Level={item.get('Level', '')}")
            result = {"document_type": doc_type, "data": data}
        else:
            logger.error("[JSON转换] 投资估算解析失败：parse_investment_record 返回 None")
            result = {"document_type": doc_type, "data": [], "error": "投资估算解析失败"}
    else:
        result = {"document_type": "unknown", "data": {}, "error": "无法识别的文档类型"}
    
    # 检查数据完整性，如果缺失则使用PaddleOCR备用解析
    if enable_paddleocr_fallback and result.get("document_type") != "unknown":
        try:
            # 检查是否需要备用解析
            from ..utils.paddleocr_fallback import check_json_data_completeness
            is_complete = check_json_data_completeness(result, result.get("document_type"))
            if auto_weather_default and result.get("document_type") in ["noiseMonitoringRecord", "noise_detection"]:
                logger.warning("[JSON转换] 检测到天气字段使用默认值，尝试使用PaddleOCR备用解析")
                is_complete = False
            
            if not is_complete:
                logger.warning(f"[JSON转换] 检测到数据缺失，尝试使用PaddleOCR备用解析")
                # 尝试使用PaddleOCR补充
                fallback_markdown = fallback_parse_with_paddleocr(
                    result,
                    original_markdown,
                    output_dir=output_dir,
                    document_type=result.get("document_type"),
                    input_file=input_file
                )
                
                if fallback_markdown:
                    logger.info("[JSON转换] PaddleOCR备用解析成功，重新解析JSON")
                    # 使用PaddleOCR的结果重新解析
                    if result.get("document_type") == "noiseMonitoringRecord" or doc_type == "noise_detection":
                        original_data = result.get("data", {}) or {}
                        fallback_data = parse_noise_detection_record(fallback_markdown, first_page_image=None, output_dir=output_dir).to_dict()
                        merged_data = _merge_noise_records(
                            primary=original_data,
                            secondary=fallback_data,
                            preserve_primary_noise=True
                        )
                        result = {"document_type": "noiseMonitoringRecord", "data": merged_data}
                    elif result.get("document_type") == "electromagneticTestRecord" or doc_type == "electromagnetic_detection":
                        original_data = result.get("data", {}) or {}
                        fallback_data = parse_electromagnetic_detection_record(fallback_markdown).to_dict()
                        merged_data = _merge_electromagnetic_records(
                            primary=original_data,
                            secondary=fallback_data,
                            preserve_primary_electric_magnetic=True
                        )
                        result = {"document_type": "electromagneticTestRecord", "data": merged_data}
                    logger.info("[JSON转换] 使用PaddleOCR结果重新解析完成")
        except Exception as e:
            logger.exception(f"[JSON转换] PaddleOCR备用解析过程出错: {e}")
            # 即使备用解析失败，也返回原始结果
    
    return result

