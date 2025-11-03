# Copyright (c) Opendatalab. All rights reserved.

"""
图片处理工具函数
"""

import base64
import os
import re
from pathlib import Path
from PIL import Image

from .logging_config import get_logger

logger = get_logger("pdf_converter.utils.image")


def crop_image(image: Image.Image, top=0, bottom=0, left=0, right=0) -> Image.Image:
    """
    裁剪图片
    
    Args:
        image: PIL Image对象
        top: 上方裁剪像素数
        bottom: 下方裁剪像素数
        left: 左侧裁剪像素数
        right: 右侧裁剪像素数
    
    Returns:
        裁剪后的PIL Image对象
    """
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    width, height = image.size
    logger.debug(f"原图尺寸: {width} x {height}")
    
    # 计算裁剪区域 (left, top, right, bottom)
    crop_box = (left, top, width - right, height - bottom)
    
    # 验证裁剪参数
    new_width = width - left - right
    new_height = height - top - bottom
    
    if new_width <= 0 or new_height <= 0:
        logger.warning(f"裁剪后的图片尺寸无效: {new_width} x {new_height}，使用原图")
        return image
    
    if left + right >= width or top + bottom >= height:
        logger.warning(f"裁剪区域超出图片范围，使用原图")
        return image
    
    # 执行裁剪
    cropped_img = image.crop(crop_box)
    logger.debug(f"裁剪后尺寸: {cropped_img.size}")
    
    return cropped_img


def image_to_base64(image_path):
    """将图片转换为base64编码"""
    with open(image_path, 'rb') as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def replace_image_with_base64(markdown_text, image_dir_path):
    """将Markdown中的图片链接替换为base64编码"""
    pattern = r'\!\[(?:[^\]]*)\]\(([^)]+)\)'

    def replace(match):
        relative_path = match.group(1)
        full_path = os.path.join(image_dir_path, relative_path)
        if os.path.exists(full_path):
            base64_image = image_to_base64(full_path)
            # 判断图片格式
            ext = Path(full_path).suffix.lower()
            mime_type = "image/jpeg" if ext in ['.jpg', '.jpeg'] else f"image/{ext[1:]}" if ext else "image/png"
            return f'![{relative_path}](data:{mime_type};base64,{base64_image})'
        return match.group(0)

    return re.sub(pattern, replace, markdown_text)

