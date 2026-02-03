#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF去水印工具
将PDF转换为图片，去除水印后再转回PDF
"""

from pathlib import Path
from typing import List, Optional
import tempfile
import shutil

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def _pdf_to_pil_images(input_pdf: str, dpi: int = 200) -> Optional[List["Image.Image"]]:
    """
    将 PDF 转为 PIL 图片列表。优先 pdf2image（需 poppler），失败时用 pypdfium2（无需 poppler）。
    """
    # 1) 尝试 pdf2image（需系统安装 poppler-utils）
    try:
        from pdf2image import convert_from_path
        return convert_from_path(input_pdf, dpi=dpi)
    except Exception as e:
        err_msg = str(e).lower()
        if "pdfinfo" in err_msg or "poppler" in err_msg or "no such file" in err_msg:
            pass  # 无 poppler，尝试 pypdfium2
        else:
            raise
    # 2) 备用：pypdfium2（无需 poppler）
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(input_pdf)
        try:
            scale = dpi / 72.0
            images = []
            for i in range(len(pdf)):
                page = pdf[i]
                bitmap = page.render(scale=scale)
                try:
                    pil_image = bitmap.to_pil()
                    images.append(pil_image)
                finally:
                    bitmap.close()
            return images
        finally:
            try:
                pdf.close()
            except Exception:
                pass
    except ImportError:
        raise FileNotFoundError(
            "PDF 转图片需要 pdf2image+poppler 或 pypdfium2。"
            " 安装其一：apt install poppler-utils 或 pip install pypdfium2"
        )


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
        from PIL import Image
        from utils.image_preprocessor import remove_watermark, check_opencv_available
        
        if not check_opencv_available():
            print("⚠ OpenCV 未安装，无法进行去水印处理")
            return False
        
        temp_dir = tempfile.mkdtemp(prefix="pdf_watermark_")
        temp_path = Path(temp_dir)
        
        try:
            print(f"正在将PDF转换为图片（DPI={dpi}）...")
            images = _pdf_to_pil_images(input_pdf, dpi=dpi)
            if not images:
                print("⚠ 未得到任何页面图片")
                return False
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
        print("请安装: pip install pypdfium2 或 pdf2image pillow PyPDF2 opencv-python；pdf2image 需系统安装 poppler-utils")
        return False
    except FileNotFoundError as e:
        print(f"⚠ {e}")
        return False
    except Exception as e:
        print(f"⚠ 去水印处理失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def crop_header_footer_from_pdf(
    input_pdf: str,
    output_pdf: str,
    header_ratio: float = 0.05,
    footer_ratio: float = 0.05,
    auto_detect: bool = False,
    dpi: int = 200
) -> bool:
    """
    对 PDF 文件进行页眉页脚裁剪处理。

    处理流程：
    1. 将 PDF 的每一页转换为图片
    2. 对每张图片进行页眉页脚裁剪
    3. 将处理后的图片合并为新的 PDF

    Args:
        input_pdf: 输入 PDF 文件路径
        output_pdf: 输出 PDF 文件路径
        header_ratio: 页眉裁剪比例（0-1），默认 0.05 表示裁剪顶部 5%
        footer_ratio: 页脚裁剪比例（0-1），默认 0.05 表示裁剪底部 5%
        auto_detect: 是否自动检测页眉页脚边界
        dpi: PDF 转图片的 DPI

    Returns:
        bool: 是否成功
    """
    try:
        from PIL import Image
        from utils.image_preprocessor import crop_header_footer, check_opencv_available

        if not check_opencv_available():
            print("⚠ OpenCV 未安装，无法进行页眉页脚裁剪")
            return False

        temp_dir = tempfile.mkdtemp(prefix="pdf_crop_hf_")
        temp_path = Path(temp_dir)

        try:
            print(f"正在将 PDF 转换为图片（DPI={dpi}）...")
            images = _pdf_to_pil_images(input_pdf, dpi=dpi)
            if not images:
                print("⚠ 未得到任何页面图片")
                return False
            print(f"✓ 转换完成，共 {len(images)} 页")

            processed_images = []
            for i, image in enumerate(images, 1):
                print(f"处理第 {i}/{len(images)} 页...", end="\r")
                original_path = temp_path / f"page_{i}_original.png"
                image.save(str(original_path), "PNG")
                cropped_path = temp_path / f"page_{i}_cropped.png"
                crop_header_footer(
                    str(original_path),
                    output_path=str(cropped_path),
                    header_ratio=header_ratio,
                    footer_ratio=footer_ratio,
                    auto_detect=auto_detect,
                )
                processed_img = Image.open(cropped_path)
                processed_images.append(processed_img)

            print("\n✓ 所有页面处理完成")
            print("正在生成 PDF...")
            if processed_images:
                first_image = processed_images[0]
                other_images = processed_images[1:] if len(processed_images) > 1 else []
                first_image.save(
                    output_pdf,
                    "PDF",
                    resolution=dpi,
                    save_all=True,
                    append_images=other_images,
                )
                print(f"✓ PDF 生成完成: {output_pdf}")
                return True
            else:
                print("⚠ 没有处理任何图片")
                return False
        finally:
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"⚠ 清理临时目录失败: {e}")
    except ImportError as e:
        print(f"⚠ 缺少必要的库: {e}")
        print("请安装: pip install pypdfium2 或 pdf2image pillow opencv-python；pdf2image 需系统安装 poppler-utils")
        return False
    except FileNotFoundError as e:
        print(f"⚠ {e}")
        return False
    except Exception as e:
        print(f"⚠ 页眉页脚裁剪失败: {e}")
        import traceback
        traceback.print_exc()
        return False
