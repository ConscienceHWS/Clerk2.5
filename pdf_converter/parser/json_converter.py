# Copyright (c) Opendatalab. All rights reserved.

"""JSON转换模块"""

from typing import Dict, Any, Optional
from PIL import Image
from ..utils.logging_config import get_logger

logger = get_logger("pdf_converter.parser.json")

from .document_type import detect_document_type
from .noise_parser import parse_noise_detection_record
from .electromagnetic_parser import parse_electromagnetic_detection_record

def parse_markdown_to_json(markdown_content: str, first_page_image: Optional[Image.Image] = None, output_dir: Optional[str] = None) -> Dict[str, Any]:
    """将Markdown内容转换为JSON"""
    doc_type = detect_document_type(markdown_content)
    
    if doc_type == "noise_detection":
        data = parse_noise_detection_record(markdown_content, first_page_image, output_dir).to_dict()
        return {"document_type": doc_type, "data": data}
    
    if doc_type == "electromagnetic_detection":
        data = parse_electromagnetic_detection_record(markdown_content).to_dict()
        return {"document_type": doc_type, "data": data}
    
    return {"document_type": "unknown", "data": {}, "error": "无法识别的文档类型"}

