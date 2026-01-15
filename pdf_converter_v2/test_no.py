#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF 附件页识别和切割工具
支持 OCR 识别扫描版 PDF
"""

import pdfplumber
from pathlib import Path
from PIL import Image
import io
import re

# 尝试导入 OCR 相关库
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    print("⚠ PyPDF2 未安装，无法切割 PDF")
    print("  安装命令: pip install PyPDF2")

# 配置
PDF_PATH = '/home/hws/workspace/GitLab/Clerk2.5/pdf_converter_v2/2-数据源/4-（初设评审）中电联电力建设技术经济咨询中心技经〔2019〕201号关于山西周村220kV输变电工程初步设计的评审意见.pdf'
OUTPUT_DIR = Path('附件页')
USE_OCR = True  # 是否启用 OCR
OCR_LANG = 'chi_sim+eng'  # OCR 语言
DEBUG_MODE = True  # 是否启用调试模式（显示每页的文本内容）

# 附件页识别关键词
ATTACHMENT_START_KEYWORDS = [
    '附件:',
    '附件：',
    '附 件:',
    '附 件：',
]

def ocr_page_image(image) -> str:
    """
    对图片进行 OCR 识别
    
    Args:
        image: PIL Image 对象
    
    Returns:
        str: 识别出的文本
    """
    if not TESSERACT_AVAILABLE:
        return ""
    
    try:
        text = pytesseract.image_to_string(image, lang=OCR_LANG)
        return text
    except Exception as e:
        print(f"    OCR 失败: {e}")
        return ""

def extract_page_text(page, use_ocr: bool = False) -> str:
    """
    提取页面文本（支持 OCR）
    
    Args:
        page: pdfplumber page 对象
        use_ocr: 是否使用 OCR
    
    Returns:
        str: 页面文本
    """
    # 先尝试提取文本层
    text = page.extract_text()
    
    if text and text.strip():
        return text
    
    # 如果没有文本层，使用 OCR
    if use_ocr and TESSERACT_AVAILABLE:
        try:
            img = page.to_image(resolution=150)  # 降低分辨率加快速度
            pil_img = img.original
            text = ocr_page_image(pil_img)
            return text
        except Exception as e:
            print(f"    OCR 失败: {e}")
            return ""
    
    return ""

def is_attachment_start_page(text: str) -> bool:
    """
    判断是否是附件清单页（附件开始的前一页）
    
    Args:
        text: 页面文本
    
    Returns:
        bool: 是否是附件清单页
    """
    if not text:
        return False
    
    # 去除所有空格后再匹配（处理OCR识别出的空格问题）
    text_no_space = text.replace(' ', '').replace('\u3000', '')  # 移除普通空格和全角空格
    
    # 检查是否包含"附件:"字样
    for keyword in ATTACHMENT_START_KEYWORDS:
        keyword_no_space = keyword.replace(' ', '').replace('\u3000', '')
        if keyword_no_space in text_no_space:
            return True
    
    # 额外检查：是否包含"附件"后面跟数字（如"附件1"、"附件 1"等）
    import re
    if re.search(r'附件\s*[0-9１２３４５６７８９０一二三四五六七八九十]', text_no_space):
        return True
    
    return False

def find_attachment_start_page(pdf_path: str, use_ocr: bool = False, debug: bool = False) -> int:
    """
    查找附件开始的页码
    
    策略：找到包含"附件:"的页面，附件从下一页开始
    
    Args:
        pdf_path: PDF 文件路径
        use_ocr: 是否使用 OCR
        debug: 是否输出调试信息
    
    Returns:
        int: 附件开始页码（从1开始），如果未找到返回 0
    """
    pdf_path = Path(pdf_path)
    
    if not pdf_path.exists():
        print(f"⚠ PDF 文件不存在: {pdf_path}")
        return 0
    
    print(f"正在扫描 PDF: {pdf_path.name}")
    print("=" * 60)
    
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        print(f"总页数: {total_pages}")
        
        if use_ocr and not TESSERACT_AVAILABLE:
            print("⚠ OCR 不可用，仅检查文本层")
            use_ocr = False
        
        print(f"OCR: {'启用' if use_ocr else '禁用'}")
        print(f"调试模式: {'启用' if debug else '禁用'}")
        print("=" * 60)
        
        for page_num, page in enumerate(pdf.pages, start=1):
            if not debug:
                print(f"\r扫描进度: {page_num}/{total_pages}", end='', flush=True)
            else:
                print(f"\n[DEBUG] 页面 {page_num}/{total_pages}")
            
            # 提取文本
            text = extract_page_text(page, use_ocr=use_ocr)
            
            if debug:
                # 显示文本长度和前200字符
                text_preview = text[:200].replace('\n', ' ') if text else "[无文本]"
                print(f"  文本长度: {len(text)} 字符")
                print(f"  文本预览: {text_preview}...")
                
                # 去除空格后的文本预览
                text_no_space = text.replace(' ', '').replace('\u3000', '')
                text_no_space_preview = text_no_space[:100] if text_no_space else "[无文本]"
                print(f"  去空格后: {text_no_space_preview}...")
                
                # 检查是否包含关键词
                matched_keywords = []
                for kw in ATTACHMENT_START_KEYWORDS:
                    kw_no_space = kw.replace(' ', '').replace('\u3000', '')
                    if kw_no_space in text_no_space:
                        matched_keywords.append(kw)
                
                # 检查是否包含"附件"后跟数字
                import re
                if re.search(r'附件\s*[0-9１２３４５６７８９０一二三四五六七八九十]', text_no_space):
                    matched_keywords.append("附件+数字")
                
                if matched_keywords:
                    print(f"  ✓ 匹配关键词: {', '.join(matched_keywords)}")
                else:
                    print(f"  ✗ 未匹配任何关键词")
            
            # 判断是否是附件清单页
            if is_attachment_start_page(text):
                # 检查是否直接是"附件1"开头（说明当前页就是附件页）
                text_no_space = text.replace(' ', '').replace('\u3000', '')
                import re
                if re.search(r'附件\s*[1１一]', text_no_space[:50]):  # 检查前50个字符
                    # 当前页就是附件开始页
                    attachment_start = page_num
                    print(f"\n\n✓ 发现附件页（直接开始）: 第 {page_num} 页")
                    print(f"✓ 附件开始页: 第 {attachment_start} 页")
                else:
                    # 附件从下一页开始
                    attachment_start = page_num + 1
                    print(f"\n\n✓ 发现附件清单页: 第 {page_num} 页")
                    print(f"✓ 附件开始页: 第 {attachment_start} 页")
                
                # 显示匹配的关键词
                matched_keywords = []
                for kw in ATTACHMENT_START_KEYWORDS:
                    kw_no_space = kw.replace(' ', '').replace('\u3000', '')
                    if kw_no_space in text_no_space:
                        matched_keywords.append(kw)
                if re.search(r'附件\s*[0-9１２３４５６７８９０一二三四五六七八九十]', text_no_space):
                    matched_keywords.append("附件+数字")
                print(f"  匹配关键词: {', '.join(matched_keywords)}")
                
                # 显示部分文本
                preview = text[:300].replace('\n', ' ')
                print(f"  文本预览: {preview}...")
                
                return attachment_start
        
        print(f"\n\n未找到附件清单页")
        return 0

def extract_pages(pdf_path: str, page_numbers: list, output_path: str):
    """
    从 PDF 中提取指定页面并保存为新 PDF
    
    Args:
        pdf_path: 源 PDF 文件路径
        page_numbers: 要提取的页码列表（从1开始）
        output_path: 输出 PDF 文件路径
    """
    if not PYPDF2_AVAILABLE:
        print("⚠ PyPDF2 未安装，无法切割 PDF")
        return
    
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)
    
    # 创建输出目录
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 读取源 PDF
    with open(pdf_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        writer = PyPDF2.PdfWriter()
        
        # 添加指定页面
        for page_num in page_numbers:
            if 1 <= page_num <= len(reader.pages):
                writer.add_page(reader.pages[page_num - 1])  # PyPDF2 页码从0开始
        
        # 保存新 PDF
        with open(output_path, 'wb') as output_file:
            writer.write(output_file)
    
    print(f"✓ 已保存到: {output_path}")

def split_attachment_pages(pdf_path: str, output_dir: Path, use_ocr: bool = False, debug: bool = False):
    """
    查找并切割附件页
    
    Args:
        pdf_path: PDF 文件路径
        output_dir: 输出目录
        use_ocr: 是否使用 OCR
        debug: 是否输出调试信息
    """
    # 查找附件开始页
    attachment_start = find_attachment_start_page(pdf_path, use_ocr=use_ocr, debug=debug)
    
    if attachment_start == 0:
        print("\n未找到附件页")
        return
    
    # 获取总页数
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
    
    # 附件页范围：从附件开始页到最后一页
    attachment_pages = list(range(attachment_start, total_pages + 1))
    
    print(f"\n附件页范围: 第 {attachment_start} 页 到 第 {total_pages} 页")
    print(f"共 {len(attachment_pages)} 页")
    
    # 切割附件页
    print("\n" + "=" * 60)
    print("开始切割附件页")
    print("=" * 60)
    
    pdf_path = Path(pdf_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存所有附件页为一个文件
    output_file = output_dir / f"{pdf_path.stem}_附件页_{attachment_start}-{total_pages}.pdf"
    extract_pages(pdf_path, attachment_pages, output_file)
    
    print(f"\n✓ 切割完成！")
    print(f"附件页数: {len(attachment_pages)} 页")
    print(f"输出目录: {output_dir.absolute()}")

if __name__ == '__main__':
    print("=" * 60)
    print("PDF 附件页识别和切割工具")
    print("=" * 60)
    
    # 检查依赖
    if not TESSERACT_AVAILABLE and USE_OCR:
        print("\n⚠ OCR 功能不可用")
        print("安装方法:")
        print("  pip install pytesseract")
        print("  sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim")
        print("\n将继续使用文本层检测（可能无法识别扫描版）\n")
    
    if not PYPDF2_AVAILABLE:
        print("\n⚠ PDF 切割功能不可用")
        print("安装方法:")
        print("  pip install PyPDF2\n")
    
    # 执行切割
    split_attachment_pages(PDF_PATH, OUTPUT_DIR, use_ocr=USE_OCR, debug=DEBUG_MODE)
