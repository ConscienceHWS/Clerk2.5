# Copyright (c) Opendatalab. All rights reserved.

"""
文档类型检测
"""


def detect_document_type(markdown_content: str) -> str:
    """检测文档类型"""
    if "污染源噪声检测原始记录表" in markdown_content:
        return "noise_detection"
    if "工频电场/磁场环境检测原始记录表" in markdown_content or "工频电场磁场环境检测原始记录表" in markdown_content:
        return "electromagnetic_detection"
    return "unknown"

