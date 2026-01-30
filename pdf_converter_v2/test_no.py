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
from utils.logging_config import get_logger

# 初始化日志
logger = get_logger("pdf_converter_v2.attachment_splitter")

# 尝试导入 OCR 相关库
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
    logger.info("[附件切割] Tesseract OCR 可用")
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("[附件切割] Tesseract OCR 不可用")

# 尝试导入 PaddleOCR 作为备用
try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
    logger.info("[附件切割] PaddleOCR 可用")
    # 初始化 PaddleOCR（延迟到实际使用时）
    _paddle_ocr = None
except ImportError:
    PADDLEOCR_AVAILABLE = False
    logger.warning("[附件切割] PaddleOCR 不可用")

try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
    logger.info("[附件切割] PyPDF2 可用")
except ImportError:
    PYPDF2_AVAILABLE = False
    logger.error("[附件切割] PyPDF2 未安装，无法切割 PDF")
    logger.info("[附件切割] 安装命令: pip install PyPDF2")

# 配置
PDF_PATH = '/home/hws/workspace/GitLab/Clerk2.5/pdf_converter_v2/2-数据源/1-（可研评审）晋电经研规划〔2017〕187号(盖章)国网山西经研院关于山西晋城周村220kV输变电工程可行性研究报告的评审意见.pdf'
OUTPUT_DIR = Path('附件页')
USE_OCR = True  # 是否启用 OCR
OCR_LANG = 'chi_sim+eng'  # OCR 语言
DEBUG_MODE = False  # 是否启用调试模式（显示每页的文本内容）

# 去水印配置
REMOVE_WATERMARK = False  # 是否对切割后的附件页PDF去水印
WATERMARK_LIGHT_THRESHOLD = 200  # 水印亮度阈值（0-255），高于此值的浅色像素可能是水印
WATERMARK_SATURATION_THRESHOLD = 30  # 水印饱和度阈值（0-255），低于此值的低饱和度像素可能是水印
WATERMARK_DPI = 200  # PDF转图片的DPI（用于去水印）

# 表格附件过滤配置
TABLE_ONLY = True  # 是否只保留包含表格的附件页（过滤掉示意图、评审意见等）

# 附件页识别关键词
ATTACHMENT_START_KEYWORDS = [
    '附件:',
    '附件：',
    '附 件:',
    '附 件：',
]

# 表格附件识别关键词（用于过滤只保留包含表格的附件）
TABLE_ATTACHMENT_KEYWORDS = [
    '项目表',
    '投资估算',
    '工程投资',
    '建设规模',
    '技术方案',
    '变电工程',
    '线路工程',
    '静态投资',
    '动态投资',
    '单位造价',
    '设备购置费',
    '安装工程费',
    '建筑工程费',
    '其他费用',
    '基本预备费',
]

# 非表格附件识别关键词（用于识别需要跳过的附件）
NON_TABLE_ATTACHMENT_KEYWORDS = [
    '示意图',
    '接入系统示意图',
    '母线间隔排列图',
    '评审意见',
    '技术监督意见',
    '参会单位',
    '人员一览表',
    '经济性评价',
    '财务合规',
    '审核结果',
    '预算编制衔接',
]

def ocr_page_image(image) -> str:
    """
    对图片进行 OCR 识别（优先使用 Tesseract，备用 PaddleOCR）
    
    Args:
        image: PIL Image 对象
    
    Returns:
        str: 识别出的文本
    """
    # 优先使用 Tesseract
    if TESSERACT_AVAILABLE:
        try:
            text = pytesseract.image_to_string(image, lang=OCR_LANG)
            logger.debug(f"[附件切割] Tesseract OCR识别成功，文本长度: {len(text)}")
            return text
        except Exception as e:
            logger.error(f"[附件切割] Tesseract OCR识别失败: {e}")
            # 失败后尝试 PaddleOCR
    
    # 备用：使用 PaddleOCR
    if PADDLEOCR_AVAILABLE:
        try:
            global _paddle_ocr
            if _paddle_ocr is None:
                logger.info("[附件切割] 初始化 PaddleOCR...")
                _paddle_ocr = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
            
            # 将PIL图片转换为numpy数组
            import numpy as np
            img_array = np.array(image)
            
            # 执行OCR
            result = _paddle_ocr.ocr(img_array, cls=True)
            
            # 提取文本
            if result and result[0]:
                texts = [line[1][0] for line in result[0] if line[1][0]]
                text = '\n'.join(texts)
                logger.debug(f"[附件切割] PaddleOCR识别成功，文本长度: {len(text)}")
                return text
            else:
                logger.warning("[附件切割] PaddleOCR未识别出文本")
                return ""
        except Exception as e:
            logger.error(f"[附件切割] PaddleOCR识别失败: {e}")
            return ""
    
    logger.warning("[附件切割] 没有可用的OCR工具")
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
        logger.debug(f"[附件切割] 第{page.page_number}页: 成功提取文本层，长度: {len(text)}")
        return text
    
    # 如果没有文本层，使用 OCR
    if use_ocr and (TESSERACT_AVAILABLE or PADDLEOCR_AVAILABLE):
        logger.info(f"[附件切割] 第{page.page_number}页: 文本层为空，使用OCR识别")
        try:
            img = page.to_image(resolution=150)  # 降低分辨率加快速度
            pil_img = img.original
            text = ocr_page_image(pil_img)
            return text
        except Exception as e:
            logger.error(f"[附件切割] 第{page.page_number}页: OCR识别失败: {e}")
            return ""
    
    logger.warning(f"[附件切割] 第{page.page_number}页: 无法提取文本（OCR未启用或不可用）")
    return ""

def is_table_attachment_page(text: str, page) -> bool:
    """
    判断是否是包含表格的附件页
    
    Args:
        text: 页面文本
        page: pdfplumber page 对象
    
    Returns:
        bool: 是否是表格附件页
    """
    if not text:
        return False
    
    text_no_space = text.replace(' ', '').replace('\u3000', '')
    
    # 检查是否包含非表格附件关键词（如示意图、评审意见等）
    for keyword in NON_TABLE_ATTACHMENT_KEYWORDS:
        keyword_no_space = keyword.replace(' ', '').replace('\u3000', '')
        if keyword_no_space in text_no_space:
            logger.debug(f"[附件切割] 检测到非表格附件关键词: {keyword}")
            return False
    
    # 检查是否包含表格附件关键词
    has_table_keyword = False
    for keyword in TABLE_ATTACHMENT_KEYWORDS:
        keyword_no_space = keyword.replace(' ', '').replace('\u3000', '')
        if keyword_no_space in text_no_space:
            logger.debug(f"[附件切割] 检测到表格关键词: {keyword}")
            has_table_keyword = True
            break
    
    # 如果有表格关键词，直接返回True
    if has_table_keyword:
        return True
    
    # 检查页面是否包含表格（使用pdfplumber的表格检测）
    if page is not None:
        try:
            tables = page.extract_tables()
            if tables and len(tables) > 0:
                # 检查表格是否足够大（至少有3行3列的数据表格）
                for table in tables:
                    if table and len(table) >= 3:
                        # 检查是否有多列
                        non_empty_rows = [row for row in table if row and any(cell for cell in row if cell)]
                        if len(non_empty_rows) >= 3:
                            row_with_most_cols = max(non_empty_rows, key=lambda r: len([c for c in r if c]))
                            if len([c for c in row_with_most_cols if c]) >= 3:
                                logger.debug(f"[附件切割] 检测到表格: {len(non_empty_rows)}行")
                                return True
        except Exception as e:
            logger.warning(f"[附件切割] 表格检测失败: {e}")
    
    return False


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
            logger.debug(f"[附件切割] 检测到附件关键词: {keyword}")
            return True
    
    # 额外检查：是否包含"附件"后面跟数字（如"附件1"、"附件 1"等）
    if re.search(r'附件\s*[0-9１２３４５６７８９０一二三四五六七八九十]', text_no_space):
        logger.debug("[附件切割] 检测到附件+数字模式")
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
        logger.error(f"[附件切割] PDF 文件不存在: {pdf_path}")
        print(f"⚠ PDF 文件不存在: {pdf_path}")
        return 0
    
    logger.info(f"[附件切割] 开始扫描PDF: {pdf_path.name}")
    print(f"正在扫描 PDF: {pdf_path.name}")
    print("=" * 60)
    
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        logger.info(f"[附件切割] PDF总页数: {total_pages}")
        print(f"总页数: {total_pages}")
        
        if use_ocr and not (TESSERACT_AVAILABLE or PADDLEOCR_AVAILABLE):
            logger.warning("[附件切割] OCR 不可用（Tesseract和PaddleOCR都不可用），仅检查文本层")
            print("⚠ OCR 不可用，仅检查文本层")
            use_ocr = False
        elif use_ocr:
            ocr_tool = "Tesseract" if TESSERACT_AVAILABLE else "PaddleOCR"
            logger.info(f"[附件切割] 使用 {ocr_tool} 进行OCR识别")
        
        logger.info(f"[附件切割] OCR: {'启用' if use_ocr else '禁用'}, 调试模式: {'启用' if debug else '禁用'}")
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
                if re.search(r'附件\s*[1１一]', text_no_space[:50]):  # 检查前50个字符
                    # 当前页就是附件开始页
                    attachment_start = page_num
                    logger.info(f"[附件切割] 发现附件页（直接开始）: 第 {page_num} 页")
                    print(f"\n\n✓ 发现附件页（直接开始）: 第 {page_num} 页")
                    print(f"✓ 附件开始页: 第 {attachment_start} 页")
                else:
                    # 附件从下一页开始
                    attachment_start = page_num + 1
                    logger.info(f"[附件切割] 发现附件清单页: 第 {page_num} 页，附件开始页: 第 {attachment_start} 页")
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
                logger.info(f"[附件切割] 匹配关键词: {', '.join(matched_keywords)}")
                print(f"  匹配关键词: {', '.join(matched_keywords)}")
                
                # 显示部分文本
                preview = text[:300].replace('\n', ' ')
                logger.debug(f"[附件切割] 文本预览: {preview}...")
                print(f"  文本预览: {preview}...")
                
                return attachment_start
        
        logger.warning("[附件切割] 未找到附件清单页")
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
        logger.error("[附件切割] PyPDF2 未安装，无法切割 PDF")
        print("⚠ PyPDF2 未安装，无法切割 PDF")
        return
    
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)
    
    logger.info(f"[附件切割] 开始提取页面: {page_numbers} 从 {pdf_path.name}")
    
    # 创建输出目录
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 读取源 PDF
    with open(pdf_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        writer = PyPDF2.PdfWriter()
        
        total_source_pages = len(reader.pages)
        logger.info(f"[附件切割] 源PDF总页数: {total_source_pages}")
        
        # 添加指定页面
        extracted_count = 0
        for page_num in page_numbers:
            if 1 <= page_num <= total_source_pages:
                writer.add_page(reader.pages[page_num - 1])  # PyPDF2 页码从0开始
                extracted_count += 1
            else:
                logger.warning(f"[附件切割] 页码 {page_num} 超出范围 (1-{total_source_pages})，跳过")
        
        logger.info(f"[附件切割] 成功提取 {extracted_count}/{len(page_numbers)} 页")
        
        # 保存新 PDF
        with open(output_path, 'wb') as output_file:
            writer.write(output_file)
    
    logger.info(f"[附件切割] 已保存到: {output_path}")
    print(f"✓ 已保存到: {output_path}")

def split_attachment_pages(pdf_path: str, output_dir: Path, use_ocr: bool = False, debug: bool = False, 
                          remove_watermark: bool = False, watermark_light_threshold: int = 200,
                          watermark_saturation_threshold: int = 30, watermark_dpi: int = 200,
                          table_only: bool = False):
    """
    查找并切割附件页
    
    Args:
        pdf_path: PDF 文件路径
        output_dir: 输出目录
        use_ocr: 是否使用 OCR
        debug: 是否输出调试信息
        remove_watermark: 是否对切割后的附件页PDF去水印
        watermark_light_threshold: 水印亮度阈值（0-255）
        watermark_saturation_threshold: 水印饱和度阈值（0-255）
        watermark_dpi: PDF转图片的DPI
        table_only: 是否只保留包含表格的附件页（过滤掉示意图、评审意见等）
    """
    logger.info(f"[附件切割] 开始处理PDF: {pdf_path}")
    logger.info(f"[附件切割] 只保留表格附件: {'是' if table_only else '否'}")
    
    # 查找附件开始页
    attachment_start = find_attachment_start_page(pdf_path, use_ocr=use_ocr, debug=debug)
    
    if attachment_start == 0:
        logger.warning(f"[附件切割] 未找到附件页: {pdf_path}")
        print("\n未找到附件页")
        return
    
    # 获取总页数和筛选表格附件页
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        
        if table_only:
            # 只保留包含表格的附件页
            logger.info(f"[附件切割] 启用表格附件过滤，开始筛选...")
            print(f"\n启用表格附件过滤，开始筛选...")
            
            attachment_pages = []
            current_table_section = []  # 当前表格区段的页面
            in_table_section = False  # 是否在表格区段内
            
            for page_num in range(attachment_start, total_pages + 1):
                page = pdf.pages[page_num - 1]
                text = extract_page_text(page, use_ocr=use_ocr)
                
                is_table_page = is_table_attachment_page(text, page)
                
                if debug:
                    print(f"  页面 {page_num}: {'表格页' if is_table_page else '非表格页'}")
                
                if is_table_page:
                    if not in_table_section:
                        # 开始新的表格区段
                        in_table_section = True
                        current_table_section = [page_num]
                        logger.debug(f"[附件切割] 开始表格区段: 第 {page_num} 页")
                    else:
                        # 继续当前表格区段
                        current_table_section.append(page_num)
                else:
                    if in_table_section:
                        # 结束当前表格区段，保存
                        attachment_pages.extend(current_table_section)
                        logger.info(f"[附件切割] 表格区段结束: {current_table_section[0]}-{current_table_section[-1]}")
                        current_table_section = []
                        in_table_section = False
            
            # 处理最后一个表格区段
            if in_table_section and current_table_section:
                attachment_pages.extend(current_table_section)
                logger.info(f"[附件切割] 最后表格区段: {current_table_section[0]}-{current_table_section[-1]}")
            
            if not attachment_pages:
                logger.warning(f"[附件切割] 未找到包含表格的附件页")
                print("\n未找到包含表格的附件页")
                return
            
            logger.info(f"[附件切割] 筛选后的表格附件页: {attachment_pages}")
            print(f"\n筛选后的表格附件页: {attachment_pages}")
            print(f"共 {len(attachment_pages)} 页")
        else:
            # 附件页范围：从附件开始页到最后一页
            attachment_pages = list(range(attachment_start, total_pages + 1))
            
            logger.info(f"[附件切割] 附件页范围: {attachment_start}-{total_pages}, 共 {len(attachment_pages)} 页")
            print(f"\n附件页范围: 第 {attachment_start} 页 到 第 {total_pages} 页")
            print(f"共 {len(attachment_pages)} 页")
    
    # 切割附件页
    print("\n" + "=" * 60)
    print("开始切割附件页")
    print("=" * 60)
    
    pdf_path = Path(pdf_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存所有附件页为一个文件
    if table_only:
        # 表格附件模式：使用筛选后的页面范围
        page_range_str = f"{min(attachment_pages)}_{max(attachment_pages)}" if attachment_pages else "none"
        output_file = output_dir / f"{pdf_path.stem}_表格附件页_{page_range_str}.pdf"
    else:
        output_file = output_dir / f"{pdf_path.stem}_附件页_{attachment_start}-{total_pages}.pdf"
    
    logger.info(f"[附件切割] 输出文件: {output_file}")
    extract_pages(pdf_path, attachment_pages, output_file)
    
    logger.info(f"[附件切割] 切割完成: {len(attachment_pages)} 页附件已保存")
    print(f"\n✓ 切割完成！")
    print(f"附件页数: {len(attachment_pages)} 页")
    print(f"输出文件: {output_file}")
    
    # 如果启用去水印，对切割后的附件页PDF进行去水印处理
    if remove_watermark:
        logger.info(f"[附件切割] 开始对附件页PDF进行去水印处理...")
        print("\n" + "=" * 60)
        print("开始去水印处理")
        print("=" * 60)
        
        try:
            # 导入去水印模块
            import sys
            from pathlib import Path as PathLib
            sys.path.insert(0, str(PathLib(__file__).parent))
            
            from utils.pdf_watermark_remover import remove_watermark_from_pdf
            
            # 去水印后的PDF路径
            nowm_output_file = output_dir / f"{output_file.stem}_nowm.pdf"
            
            logger.info(f"[附件切割] 去水印参数: 亮度阈值={watermark_light_threshold}, 饱和度阈值={watermark_saturation_threshold}, DPI={watermark_dpi}")
            print(f"去水印参数:")
            print(f"  - 亮度阈值: {watermark_light_threshold}")
            print(f"  - 饱和度阈值: {watermark_saturation_threshold}")
            print(f"  - DPI: {watermark_dpi}")
            
            # 执行去水印
            success = remove_watermark_from_pdf(
                input_pdf=str(output_file),
                output_pdf=str(nowm_output_file),
                light_threshold=watermark_light_threshold,
                saturation_threshold=watermark_saturation_threshold,
                dpi=watermark_dpi
            )
            
            if success and nowm_output_file.exists():
                logger.info(f"[附件切割] 去水印完成: {nowm_output_file}")
                print(f"\n✓ 去水印完成！")
                print(f"去水印后的文件: {nowm_output_file}")
            else:
                logger.warning(f"[附件切割] 去水印失败")
                print(f"\n⚠ 去水印失败，请检查日志")
        except ImportError as e:
            logger.error(f"[附件切割] 导入去水印模块失败: {e}")
            print(f"\n⚠ 去水印模块导入失败: {e}")
            print("请确保 utils/pdf_watermark_remover.py 文件存在")
        except Exception as e:
            logger.exception(f"[附件切割] 去水印处理失败: {e}")
            print(f"\n⚠ 去水印处理失败: {e}")
    
    print(f"\n输出目录: {output_dir.absolute()}")

if __name__ == '__main__':
    logger.info("[附件切割] " + "=" * 50)
    logger.info("[附件切割] PDF 附件页识别和切割工具启动")
    logger.info("[附件切割] " + "=" * 50)
    
    print("=" * 60)
    print("PDF 附件页识别和切割工具")
    print("=" * 60)
    
    # 显示配置信息
    print("\n配置信息:")
    print(f"  - PDF文件: {PDF_PATH}")
    print(f"  - 输出目录: {OUTPUT_DIR}")
    print(f"  - OCR: {'启用' if USE_OCR else '禁用'}")
    print(f"  - 调试模式: {'启用' if DEBUG_MODE else '禁用'}")
    print(f"  - 只保留表格附件: {'启用' if TABLE_ONLY else '禁用'}")
    print(f"  - 去水印: {'启用' if REMOVE_WATERMARK else '禁用'}")
    if REMOVE_WATERMARK:
        print(f"    * 亮度阈值: {WATERMARK_LIGHT_THRESHOLD}")
        print(f"    * 饱和度阈值: {WATERMARK_SATURATION_THRESHOLD}")
        print(f"    * DPI: {WATERMARK_DPI}")
    
    # 检查依赖
    if not TESSERACT_AVAILABLE and USE_OCR:
        logger.warning("[附件切割] OCR 功能不可用")
        print("\n⚠ OCR 功能不可用")
        print("安装方法:")
        print("  pip install pytesseract")
        print("  sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim")
        print("\n将继续使用文本层检测（可能无法识别扫描版）\n")
    
    if not PYPDF2_AVAILABLE:
        logger.error("[附件切割] PDF 切割功能不可用")
        print("\n⚠ PDF 切割功能不可用")
        print("安装方法:")
        print("  pip install PyPDF2\n")
    
    if REMOVE_WATERMARK:
        print("\n⚠ 去水印功能需要以下依赖:")
        print("  - OpenCV (cv2)")
        print("  - Pillow (PIL)")
        print("  - pdf2image")
        print("  - PyPDF2")
        print("安装命令:")
        print("  pip install opencv-python pillow pdf2image PyPDF2\n")
    
    # 执行切割
    logger.info(f"[附件切割] 配置: PDF={PDF_PATH}, 输出={OUTPUT_DIR}, OCR={USE_OCR}, DEBUG={DEBUG_MODE}, 表格附件={TABLE_ONLY}, 去水印={REMOVE_WATERMARK}")
    split_attachment_pages(
        PDF_PATH, 
        OUTPUT_DIR, 
        use_ocr=USE_OCR, 
        debug=DEBUG_MODE,
        remove_watermark=REMOVE_WATERMARK,
        watermark_light_threshold=WATERMARK_LIGHT_THRESHOLD,
        watermark_saturation_threshold=WATERMARK_SATURATION_THRESHOLD,
        watermark_dpi=WATERMARK_DPI,
        table_only=TABLE_ONLY
    )
    logger.info("[附件切割] 程序执行完成")
