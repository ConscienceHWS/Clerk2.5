# Copyright (c) Opendatalab. All rights reserved.

"""JSON转换模块 v2 - 独立版本，不依赖v1"""

from typing import Dict, Any, Optional, List
import re
from copy import deepcopy
from PIL import Image

from ..utils.logging_config import get_logger
from ..utils.paddleocr_fallback import fallback_parse_with_paddleocr
from .document_type import detect_document_type
from .noise_parser import parse_noise_detection_record
from .electromagnetic_parser import parse_electromagnetic_detection_record
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
    
    if forced_document_type:
        if forced_document_type == "noiseMonitoringRecord":
            data = parse_noise_detection_record(markdown_content, first_page_image=None, output_dir=output_dir).to_dict()
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
            
            # 2. 检查是否为格式3/5（附件 2 工况信息，电压列第一列存储时间段）
            if "附件" in markdown_content and "工况信息" in markdown_content:
                logger.info("[JSON转换] 检测到'附件 2 工况信息'格式，尝试使用格式3/5解析")
                op_list = parse_operational_conditions_format3_5(markdown_content)
                if op_list:
                    # 格式3/5返回OperationalConditionV2格式
                    serialized = [oc.to_dict() if hasattr(oc, "to_dict") else oc for oc in op_list]
                    logger.info(f"[JSON转换] 格式3/5解析成功，共解析到 {len(serialized)} 条记录")
                    return {"document_type": forced_document_type, "data": {"operationalConditions": serialized}}
                else:
                    logger.debug("[JSON转换] 格式3/5解析未找到结果，继续尝试其他格式")
            
            # 3. 检查是否为opStatus格式（附件 工况及工程信息，且不包含"表1检测工况"）
            if "附件" in markdown_content and "工况" in markdown_content:
                logger.info("[JSON转换] 检测到'附件 工况及工程信息'格式，使用opStatus格式解析")
                op_list = parse_operational_conditions_opstatus(markdown_content)
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
        else:
            result = {"document_type": forced_document_type, "data": {}}
        
        # 对于forced_document_type，也检查数据完整性
        if enable_paddleocr_fallback and result.get("document_type") in ["noiseMonitoringRecord", "electromagneticTestRecord"]:
            try:
                from ..utils.paddleocr_fallback import check_json_data_completeness
                is_complete = check_json_data_completeness(result, result.get("document_type"))
                
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
                            data = parse_electromagnetic_detection_record(fallback_markdown).to_dict()
                            result = {"document_type": "electromagneticTestRecord", "data": data}
                        logger.info("[JSON转换] 使用PaddleOCR结果重新解析完成")
            except Exception as e:
                logger.exception(f"[JSON转换] PaddleOCR备用解析过程出错: {e}")
        
        return result

    doc_type = detect_document_type(markdown_content)
    
    if doc_type == "noise_detection":
        # v2版本不依赖OCR，first_page_image参数会被忽略
        data = parse_noise_detection_record(markdown_content, first_page_image=None, output_dir=output_dir).to_dict()
        result = {"document_type": doc_type, "data": data}
    elif doc_type == "electromagnetic_detection":
        data = parse_electromagnetic_detection_record(markdown_content).to_dict()
        result = {"document_type": doc_type, "data": data}
    else:
        result = {"document_type": "unknown", "data": {}, "error": "无法识别的文档类型"}
    
    # 检查数据完整性，如果缺失则使用PaddleOCR备用解析
    if enable_paddleocr_fallback and result.get("document_type") != "unknown":
        try:
            # 检查是否需要备用解析
            from ..utils.paddleocr_fallback import check_json_data_completeness
            is_complete = check_json_data_completeness(result, result.get("document_type"))
            
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
                        data = parse_electromagnetic_detection_record(fallback_markdown).to_dict()
                        result = {"document_type": "electromagneticTestRecord", "data": data}
                    logger.info("[JSON转换] 使用PaddleOCR结果重新解析完成")
        except Exception as e:
            logger.exception(f"[JSON转换] PaddleOCR备用解析过程出错: {e}")
            # 即使备用解析失败，也返回原始结果
    
    return result

