#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF去水印工具
将PDF转换为图片，去除水印后再转回PDF
"""

from pathlib import Path
from typing import Optional
import tempfile
import shutil

def remove_watermark_from_pdf(
    input_pdf: str,
    output_pdf: str,
    light_threshold: int = 200,
    saturation_threshold: int = 30,
    dpi: int = 200
) -> bool:
    """
    对PDF文件进行去水印处理
    
    处理流程：
    1. 将PDF的每一页转换为图片
    2. 对每张图片进行去水印处理
    3. 将处理后的图片合并为新的PDF
    
    Args:
        input_pdf: 输入PDF文件路径
        output_pdf: 输出PDF文件路径
        light_threshold: 水印亮度阈值（0-255），高于此值的浅色像素可能是水印
        saturation_threshold: 水印饱和度阈值（0-255），低于此值的低饱和度像素可能是水印
        dpi: PDF转图片的DPI，影响图片质量和处理速度
    
    Returns:
        bool: 是否成功
    """
    try:
        # 导入必要的库
        from pdf2image import convert_from_path
        from PIL import Image
        import PyPDF2
        from ..utils.image_preprocessor import remove_watermark, check_opencv_available
        
        # 检查OpenCV是否可用
        if not check_opencv_available():
            print("⚠ OpenCV 未安装，无法进行去水印处理")
            return False
        
        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix="pdf_watermark_")
        temp_path = Path(temp_dir)
        
        try:
            print(f"正在将PDF转换为图片（DPI={dpi}）...")
            # 将PDF转换为图片
            images = convert_from_path(input_pdf, dpi=dpi)
            print(f"✓ 转换完成，共 {len(images)} 页")
            
            # 处理每一页
            processed_images = []
            for i, image in enumerate(images, 1):
                print(f"处理第 {i}/{len(images)} 页...", end='\r')
                
                # 保存原始图片
                original_path = temp_path / f"page_{i}_original.png"
                image.save(str(original_path), "PNG")
                
                # 去水印
                nowm_path = temp_path / f"page_{i}_nowm.png"
                processed_path = remove_watermark(
                    str(original_path),
                    output_path=str(nowm_path),
                    light_threshold=light_threshold,
                    saturation_threshold=saturation_threshold,
                    method="hsv"
                )
                
                # 加载处理后的图片
                processed_img = Image.open(processed_path)
                processed_images.append(processed_img)
            
            print(f"\n✓ 所有页面处理完成")
            
            # 将图片合并为PDF
            print("正在生成PDF...")
            if processed_images:
                # 第一张图片作为主图片
                first_image = processed_images[0]
                # 其余图片作为附加页
                other_images = processed_images[1:] if len(processed_images) > 1 else []
                
                # 保存为PDF
                first_image.save(
                    output_pdf,
                    "PDF",
                    resolution=dpi,
                    save_all=True,
                    append_images=other_images
                )
                print(f"✓ PDF生成完成: {output_pdf}")
                return True
            else:
                print("⚠ 没有处理任何图片")
                return False
                
        finally:
            # 清理临时目录
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"⚠ 清理临时目录失败: {e}")
    
    except ImportError as e:
        print(f"⚠ 缺少必要的库: {e}")
        print("请安装: pip install pdf2image pillow PyPDF2 opencv-python")
        return False
    except Exception as e:
        print(f"⚠ 去水印处理失败: {e}")
        import traceback
        traceback.print_exc()
        return False
