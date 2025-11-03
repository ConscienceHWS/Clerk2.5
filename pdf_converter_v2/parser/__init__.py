# Copyright (c) Opendatalab. All rights reserved.

"""JSON解析模块 v2 - 独立版本"""

from .json_converter import parse_markdown_to_json
from .document_type import detect_document_type
from .noise_parser import parse_noise_detection_record
from .electromagnetic_parser import parse_electromagnetic_detection_record

__all__ = [
    'parse_markdown_to_json',
    'detect_document_type',
    'parse_noise_detection_record',
    'parse_electromagnetic_detection_record'
]

