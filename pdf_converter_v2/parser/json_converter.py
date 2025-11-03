# Copyright (c) Opendatalab. All rights reserved.

"""JSON转换模块 v2 - 独立版本，不依赖v1"""

from typing import Dict, Any, Optional
from PIL import Image

from ..utils.logging_config import get_logger
from .document_type import detect_document_type
from .noise_parser import parse_noise_detection_record
from .electromagnetic_parser import parse_electromagnetic_detection_record

logger = get_logger("pdf_converter_v2.parser.json")

def parse_markdown_to_json(markdown_content: str, first_page_image: Optional[Image.Image] = None, output_dir: Optional[str] = None) -> Dict[str, Any]:
    """将Markdown内容转换为JSON - v2独立版本，不依赖v1和OCR"""
    doc_type = detect_document_type(markdown_content)
    
    if doc_type == "noise_detection":
        # v2版本不依赖OCR，first_page_image参数会被忽略
        data = parse_noise_detection_record(markdown_content, first_page_image=None, output_dir=output_dir).to_dict()
        return {"document_type": doc_type, "data": data}
    
    if doc_type == "electromagnetic_detection":
        data = parse_electromagnetic_detection_record(markdown_content).to_dict()
        return {"document_type": doc_type, "data": data}
    
    return {"document_type": "unknown", "data": {}, "error": "无法识别的文档类型"}

