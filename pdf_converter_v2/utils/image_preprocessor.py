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


def crop_header_footer(
    image_path: str,
    output_path: Optional[str] = None,
    header_ratio: float = 0.05,
    footer_ratio: float = 0.05,
    auto_detect: bool = False
) -> str:
    """
    裁剪图片的页眉和页脚区域
    
    通过按比例裁剪图片顶部和底部来去除页眉页脚
    
    Args:
        image_path: 输入图片路径
        output_path: 输出图片路径，默认在原文件名后加 _cropped
        header_ratio: 页眉裁剪比例（0-1），默认0.05表示裁剪顶部5%
        footer_ratio: 页脚裁剪比例（0-1），默认0.05表示裁剪底部5%
        auto_detect: 是否自动检测页眉页脚边界（忽略 header_ratio 和 footer_ratio）
    
    Returns:
        处理后的图片路径
    """
    if not CV2_AVAILABLE:
        logger.warning("[裁剪页眉页脚] OpenCV 未安装，跳过处理")
        return image_path
    
    logger.info(f"[裁剪页眉页脚] 开始处理: {image_path}")
    
    # 读取图片
    img = cv2.imread(image_path)
    if img is None:
        logger.error(f"[裁剪页眉页脚] 无法读取图片: {image_path}")
        return image_path
    
    height, width = img.shape[:2]
    logger.info(f"[裁剪页眉页脚] 原始尺寸: {width}x{height}")
    
    if auto_detect:
        # 自动检测页眉页脚边界
        logger.info("[裁剪页眉页脚] 使用自动检测模式")
        header_pixels, footer_pixels = _detect_header_footer_boundaries(img)
        logger.info(f"[裁剪页眉页脚] 自动检测结果: 页眉={header_pixels}px, 页脚={footer_pixels}px")
    else:
        # 使用固定比例
        logger.info(f"[裁剪页眉页脚] 使用固定比例: 页眉={header_ratio}, 页脚={footer_ratio}")
        header_pixels = int(height * header_ratio)
        footer_pixels = int(height * footer_ratio)
    
    # 裁剪图片（保留中间部分）
    top = header_pixels
    bottom = height - footer_pixels
    
    if top >= bottom:
        logger.warning("[裁剪页眉页脚] 裁剪区域无效，跳过处理")
        return image_path
    
    result = img[top:bottom, :]
    
    new_height = result.shape[0]
    logger.info(f"[裁剪页眉页脚] 裁剪后尺寸: {width}x{new_height}")
    logger.info(f"[裁剪页眉页脚] 裁剪了顶部 {header_pixels}px，底部 {footer_pixels}px")
    
    # 确定输出路径
    if output_path is None:
        path = Path(image_path)
        output_path = str(path.parent / f"{path.stem}_cropped{path.suffix}")
    
    # 保存结果
    cv2.imwrite(output_path, result)
    logger.info(f"[裁剪页眉页脚] 处理完成，保存到: {output_path}")
    
    return output_path


def _detect_header_footer_boundaries(img: np.ndarray) -> Tuple[int, int]:
    """
    自动检测页眉页脚边界
    
    使用多种方法综合判断：
    1. 水平线检测 - 检测分隔线
    2. 文本密度分析 - 页眉页脚通常文字较少
    3. 空白区域检测 - 检测大面积空白
    
    Args:
        img: 输入图片（BGR格式）
    
    Returns:
        (header_pixels, footer_pixels): 页眉和页脚的像素高度
    """
    height, width = img.shape[:2]
    
    # 转为灰度图
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 定义搜索范围（页眉页脚通常在顶部/底部 15% 以内）
    search_range = int(height * 0.15)
    min_margin = int(height * 0.02)  # 最小边距 2%
    
    # 方法1: 检测水平线
    header_line = _find_horizontal_line(gray, 0, search_range, from_top=True)
    footer_line = _find_horizontal_line(gray, height - search_range, height, from_top=False)
    
    # 方法2: 分析文本密度变化
    header_density = _find_content_boundary(gray, 0, search_range, from_top=True)
    footer_density = _find_content_boundary(gray, height - search_range, height, from_top=False)
    
    # 综合判断：取最可靠的结果
    # 优先使用水平线检测结果，其次使用密度分析结果
    if header_line > min_margin:
        header_pixels = header_line
        logger.debug(f"[自动检测] 页眉: 使用水平线检测结果 {header_pixels}px")
    elif header_density > min_margin:
        header_pixels = header_density
        logger.debug(f"[自动检测] 页眉: 使用密度分析结果 {header_pixels}px")
    else:
        header_pixels = min_margin
        logger.debug(f"[自动检测] 页眉: 使用最小边距 {header_pixels}px")
    
    if footer_line > min_margin:
        footer_pixels = footer_line
        logger.debug(f"[自动检测] 页脚: 使用水平线检测结果 {footer_pixels}px")
    elif footer_density > min_margin:
        footer_pixels = footer_density
        logger.debug(f"[自动检测] 页脚: 使用密度分析结果 {footer_pixels}px")
    else:
        footer_pixels = min_margin
        logger.debug(f"[自动检测] 页脚: 使用最小边距 {footer_pixels}px")
    
    return header_pixels, footer_pixels


def _find_horizontal_line(
    gray: np.ndarray,
    start_y: int,
    end_y: int,
    from_top: bool = True
) -> int:
    """
    在指定区域内查找水平分隔线
    
    Args:
        gray: 灰度图
        start_y: 搜索起始y坐标
        end_y: 搜索结束y坐标
        from_top: True表示从上往下找，False表示从下往上找
    
    Returns:
        分隔线位置（像素），如果没找到返回0
    """
    height, width = gray.shape
    
    # 使用 Canny 边缘检测
    edges = cv2.Canny(gray[start_y:end_y, :], 50, 150)
    
    # 使用霍夫变换检测直线
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi/180,
        threshold=int(width * 0.5),  # 线长度至少为图片宽度的50%
        minLineLength=int(width * 0.4),
        maxLineGap=20
    )
    
    if lines is None:
        return 0
    
    # 筛选水平线（角度接近0或180度）
    horizontal_lines = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        # 计算角度
        angle = abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
        # 水平线角度应该接近 0 或 180
        if angle < 5 or angle > 175:
            avg_y = (y1 + y2) // 2 + start_y
            horizontal_lines.append(avg_y)
    
    if not horizontal_lines:
        return 0
    
    # 根据方向返回最合适的线
    if from_top:
        # 从上往下，返回最下面的水平线（作为页眉下边界）
        return max(horizontal_lines)
    else:
        # 从下往上，返回距离底部的距离
        return height - min(horizontal_lines)


def _find_content_boundary(
    gray: np.ndarray,
    start_y: int,
    end_y: int,
    from_top: bool = True
) -> int:
    """
    通过分析文本/内容密度找到内容边界
    
    原理：页眉页脚区域通常是空白或只有少量文字，
    正文区域文字密度较高。通过检测密度突变点来确定边界。
    
    Args:
        gray: 灰度图
        start_y: 搜索起始y坐标
        end_y: 搜索结束y坐标
        from_top: True表示从上往下找，False表示从下往上找
    
    Returns:
        内容边界位置（像素），如果没找到返回0
    """
    height, width = gray.shape
    
    # 二值化
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    
    # 计算每一行的像素密度（黑色像素占比）
    row_densities = []
    for y in range(start_y, end_y):
        row = binary[y, :]
        density = np.sum(row > 0) / width
        row_densities.append((y, density))
    
    if not row_densities:
        return 0
    
    # 使用滑动窗口平滑密度曲线
    window_size = 10
    smoothed = []
    for i in range(len(row_densities)):
        start = max(0, i - window_size // 2)
        end = min(len(row_densities), i + window_size // 2)
        avg_density = sum(d[1] for d in row_densities[start:end]) / (end - start)
        smoothed.append((row_densities[i][0], avg_density))
    
    # 找到密度突变点
    # 定义阈值：当密度从低于 0.01 变化到高于 0.02 时，认为进入正文区域
    low_threshold = 0.005
    high_threshold = 0.02
    
    if from_top:
        # 从上往下，找到第一个连续高密度区域的起始位置
        in_content = False
        content_start = 0
        consecutive_high = 0
        
        for y, density in smoothed:
            if density > high_threshold:
                consecutive_high += 1
                if consecutive_high >= 5 and not in_content:
                    # 连续5行高密度，认为进入正文
                    in_content = True
                    content_start = y - 5  # 往上回退一点
                    break
            else:
                consecutive_high = 0
        
        return max(0, content_start - start_y)
    else:
        # 从下往上，找到最后一个连续高密度区域的结束位置
        in_content = False
        content_end = height
        consecutive_high = 0
        
        for y, density in reversed(smoothed):
            if density > high_threshold:
                consecutive_high += 1
                if consecutive_high >= 5 and not in_content:
                    in_content = True
                    content_end = y + 5
                    break
            else:
                consecutive_high = 0
        
        return max(0, height - content_end)
