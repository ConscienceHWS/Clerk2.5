"""
图像预处理工具 - 包含去水印等功能

支持的预处理操作：
- 去水印（颜色过滤法）
- 灰度转换
- 二值化
- 去噪
"""

import numpy as np
from pathlib import Path
from typing import Optional, Tuple
from loguru import logger

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("[图像预处理] PIL 未安装，部分功能不可用")

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.warning("[图像预处理] OpenCV 未安装，部分功能不可用")


def remove_watermark(
    image_path: str,
    output_path: Optional[str] = None,
    light_threshold: int = 200,
    saturation_threshold: int = 30,
    method: str = "auto"
) -> str:
    """
    去除图片水印
    
    原理：大多数水印是浅色或半透明的，通过以下方式去除：
    1. 将浅色像素（亮度高、饱和度低）替换为白色
    2. 保留深色文字内容
    
    Args:
        image_path: 输入图片路径
        output_path: 输出图片路径，默认在原文件名后加 _nowm
        light_threshold: 亮度阈值（0-255），高于此值的浅色像素可能是水印
        saturation_threshold: 饱和度阈值（0-255），低于此值的低饱和度像素可能是水印
        method: 去水印方法
            - "auto": 自动选择最佳方法
            - "light": 基于亮度的简单方法（快速）
            - "hsv": 基于HSV颜色空间的方法（更精确）
            - "adaptive": 自适应阈值方法
    
    Returns:
        处理后的图片路径
    """
    if not CV2_AVAILABLE:
        logger.warning("[去水印] OpenCV 未安装，跳过去水印处理")
        return image_path
    
    logger.info(f"[去水印] 开始处理: {image_path}")
    logger.info(f"[去水印] 方法: {method}, 亮度阈值: {light_threshold}, 饱和度阈值: {saturation_threshold}")
    
    # 读取图片
    img = cv2.imread(image_path)
    if img is None:
        logger.error(f"[去水印] 无法读取图片: {image_path}")
        return image_path
    
    original_shape = img.shape
    logger.info(f"[去水印] 图片尺寸: {original_shape[1]}x{original_shape[0]}")
    
    # 根据方法选择处理逻辑
    if method == "auto":
        # 自动检测：先尝试 HSV 方法，如果效果不好则用 adaptive
        method = "hsv"
    
    if method == "light":
        # 简单亮度方法：将浅色像素替换为白色
        result = _remove_watermark_light(img, light_threshold)
    elif method == "hsv":
        # HSV 方法：基于亮度和饱和度
        result = _remove_watermark_hsv(img, light_threshold, saturation_threshold)
    elif method == "adaptive":
        # 自适应方法：使用自适应阈值
        result = _remove_watermark_adaptive(img)
    else:
        logger.warning(f"[去水印] 未知方法: {method}，使用 hsv")
        result = _remove_watermark_hsv(img, light_threshold, saturation_threshold)
    
    # 确定输出路径
    if output_path is None:
        path = Path(image_path)
        output_path = str(path.parent / f"{path.stem}_nowm{path.suffix}")
    
    # 保存结果
    cv2.imwrite(output_path, result)
    logger.info(f"[去水印] 处理完成，保存到: {output_path}")
    
    return output_path


def _remove_watermark_light(img: np.ndarray, threshold: int = 200) -> np.ndarray:
    """
    简单亮度方法：将浅色像素替换为白色
    
    适用于：浅色/灰色水印
    """
    # 转为灰度图
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 创建掩码：亮度高于阈值的区域
    mask = gray > threshold
    
    # 将掩码区域设为白色
    result = img.copy()
    result[mask] = [255, 255, 255]
    
    return result


def _remove_watermark_hsv(
    img: np.ndarray,
    light_threshold: int = 200,
    saturation_threshold: int = 30
) -> np.ndarray:
    """
    HSV 方法：基于亮度和饱和度去除水印
    
    原理：水印通常是高亮度、低饱和度的
    适用于：彩色水印、半透明水印
    """
    # 转换到 HSV 颜色空间
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # 分离通道
    h, s, v = cv2.split(hsv)
    
    # 创建水印掩码：高亮度 AND 低饱和度
    watermark_mask = (v > light_threshold) & (s < saturation_threshold)
    
    # 将水印区域设为白色
    result = img.copy()
    result[watermark_mask] = [255, 255, 255]
    
    # 可选：对边缘进行平滑处理
    # kernel = np.ones((3, 3), np.uint8)
    # watermark_mask_dilated = cv2.dilate(watermark_mask.astype(np.uint8), kernel, iterations=1)
    # result[watermark_mask_dilated == 1] = [255, 255, 255]
    
    return result


def _remove_watermark_adaptive(img: np.ndarray) -> np.ndarray:
    """
    自适应阈值方法
    
    适用于：复杂背景、不均匀光照
    """
    # 转为灰度图
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 使用自适应阈值
    # 这会根据局部区域计算阈值，保留文字，去除背景和水印
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=15,
        C=10
    )
    
    # 转回 BGR（3通道）
    result = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    
    return result


def enhance_for_ocr(
    image_path: str,
    output_path: Optional[str] = None,
    remove_wm: bool = True,
    denoise: bool = True,
    sharpen: bool = False
) -> str:
    """
    OCR 预处理增强
    
    组合多种预处理操作，优化 OCR 识别效果
    
    Args:
        image_path: 输入图片路径
        output_path: 输出图片路径
        remove_wm: 是否去除水印
        denoise: 是否去噪
        sharpen: 是否锐化
    
    Returns:
        处理后的图片路径
    """
    if not CV2_AVAILABLE:
        logger.warning("[OCR预处理] OpenCV 未安装，跳过预处理")
        return image_path
    
    logger.info(f"[OCR预处理] 开始处理: {image_path}")
    
    # 读取图片
    img = cv2.imread(image_path)
    if img is None:
        logger.error(f"[OCR预处理] 无法读取图片: {image_path}")
        return image_path
    
    result = img.copy()
    
    # 1. 去水印
    if remove_wm:
        result = _remove_watermark_hsv(result)
        logger.info("[OCR预处理] 已去除水印")
    
    # 2. 去噪
    if denoise:
        result = cv2.fastNlMeansDenoisingColored(result, None, 10, 10, 7, 21)
        logger.info("[OCR预处理] 已去噪")
    
    # 3. 锐化
    if sharpen:
        kernel = np.array([[-1, -1, -1],
                          [-1,  9, -1],
                          [-1, -1, -1]])
        result = cv2.filter2D(result, -1, kernel)
        logger.info("[OCR预处理] 已锐化")
    
    # 确定输出路径
    if output_path is None:
        path = Path(image_path)
        output_path = str(path.parent / f"{path.stem}_enhanced{path.suffix}")
    
    # 保存结果
    cv2.imwrite(output_path, result)
    logger.info(f"[OCR预处理] 处理完成，保存到: {output_path}")
    
    return output_path


def check_opencv_available() -> bool:
    """检查 OpenCV 是否可用"""
    return CV2_AVAILABLE
