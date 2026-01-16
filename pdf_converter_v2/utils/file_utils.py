# Copyright (c) Opendatalab. All rights reserved.

"""
文件处理工具函数
"""

import os
import re
from pathlib import Path
from typing import Tuple

from .logging_config import get_logger

logger = get_logger("pdf_converter_v2.utils.file")


def safe_stem(file_path):
    """安全地提取文件名（去除不安全字符）"""
    stem = Path(file_path).stem
    return re.sub(r'[^\w.]', '_', stem)


def check_pdf_has_text_layer(pdf_path: str, min_text_length: int = 100) -> Tuple[bool, str]:
    """
    检查 PDF 是否有文本层
    
    Args:
        pdf_path: PDF 文件路径
        min_text_length: 最小文本长度阈值，低于此值认为没有有效文本层
        
    Returns:
        Tuple[bool, str]: (是否有文本层, 提取的文本内容)
    """
    try:
        import pdfplumber
        
        text_content = ""
        with pdfplumber.open(pdf_path) as pdf:
            # 检查前几页的文本
            pages_to_check = min(5, len(pdf.pages))
            for i in range(pages_to_check):
                page = pdf.pages[i]
                page_text = page.extract_text() or ""
                text_content += page_text
                
                # 如果已经有足够的文本，直接返回
                if len(text_content) >= min_text_length:
                    logger.info(f"[PDF检测] 文件有文本层，前{i+1}页提取到 {len(text_content)} 字符")
                    return True, text_content
        
        # 检查总文本长度
        if len(text_content) >= min_text_length:
            logger.info(f"[PDF检测] 文件有文本层，共提取到 {len(text_content)} 字符")
            return True, text_content
        else:
            logger.warning(f"[PDF检测] 文件文本层不足，仅提取到 {len(text_content)} 字符（阈值: {min_text_length}）")
            return False, text_content
            
    except Exception as e:
        logger.error(f"[PDF检测] 检测文本层失败: {e}")
        return False, ""

