# Copyright (c) Opendatalab. All rights reserved.

"""JSON转换模块 v3 - 适配PaddleOCR输出"""

from typing import Dict, Any, Optional

from ..utils.logging_config import get_logger
from .noise_parser import parse_noise_detection_record
from .electromagnetic_parser import parse_electromagnetic_detection_record
from .table_parser import (
    parse_operational_conditions,
    parse_operational_conditions_v2,
    parse_operational_conditions_opstatus,
)

logger = get_logger("pdf_converter_v2.parser.json")

NOISE_KEYWORDS = (
    "噪声检测原始记录表",
    "污染源噪声检测",
    "噪声原始记录",
)
EM_KEYWORDS = (
    "工频电场/磁场环境检测原始记录表",
    "工频电场磁场环境检测原始记录表",
    "电磁原始记录",
)
OP_KEYWORDS = (
    "工况信息",
    "工况记录",
    "检测工况",
)


def detect_document_type(markdown_content: str) -> Optional[str]:
    """基于PaddleOCR输出的文本快速识别文档类型"""
    content = markdown_content.replace(" ", "")
    if any(keyword in content for keyword in NOISE_KEYWORDS):
        return "noiseMonitoringRecord"
    if any(keyword in content for keyword in EM_KEYWORDS):
        return "electromagneticTestRecord"
    if any(keyword in content for keyword in OP_KEYWORDS):
        return "operatingConditionInfo"
    return None


def parse_operational_info(markdown_content: str):
    """根据现有逻辑解析工况信息"""
    if "表1检测工况" in markdown_content or "表 1 检测工况" in markdown_content:
        logger.info("[JSON转换] 解析表1检测工况格式")
        op_list = parse_operational_conditions_v2(markdown_content)
    elif "附件" in markdown_content and "工况" in markdown_content:
        logger.info("[JSON转换] 解析附件工况格式")
        op_list = parse_operational_conditions_opstatus(markdown_content)
    else:
        op_list = parse_operational_conditions(markdown_content, require_title=True)
        if not op_list:
            op_list = parse_operational_conditions(markdown_content, require_title=False)
    serialized = [oc.to_dict() if hasattr(oc, "to_dict") else oc for oc in (op_list or [])]
    return {"document_type": "operatingConditionInfo", "data": {"operationalConditions": serialized}}


def parse_markdown_to_json(
    markdown_content: str,
    first_page_image=None,
    output_dir: Optional[str] = None,
    forced_document_type: Optional[str] = None,
    enable_paddleocr_fallback: bool = False,
    input_file: Optional[str] = None,
) -> Dict[str, Any]:
    """
    将PaddleOCR输出的Markdown转换为JSON。
    v3版本不再触发备用解析，直接依赖Paddle产出的结构化Markdown。
    """
    doc_type = forced_document_type or detect_document_type(markdown_content)

    if doc_type == "noiseMonitoringRecord":
        data = parse_noise_detection_record(markdown_content, first_page_image=None, output_dir=output_dir).to_dict()
        return {"document_type": doc_type, "data": data}

    if doc_type == "electromagneticTestRecord":
        data = parse_electromagnetic_detection_record(markdown_content).to_dict()
        return {"document_type": doc_type, "data": data}

    if doc_type == "operatingConditionInfo":
        return parse_operational_info(markdown_content)

    logger.warning("[JSON转换] 无法识别文档类型，返回占位数据")
    return {"document_type": "unknown", "data": {}, "error": "unsupported_document_type"}

