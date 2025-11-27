# Copyright (c) Opendatalab. All rights reserved.

"""PaddleOCR备用解析模块 - 当MinerU解析结果缺失时使用"""

import json
import os
import subprocess
import tempfile
import time
import random
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import ast
import re

from ..utils.logging_config import get_logger

logger = get_logger("pdf_converter_v2.utils.paddleocr")

try:
    import pypdfium2 as pdfium
    PDFIUM_AVAILABLE = True
except ImportError:
    PDFIUM_AVAILABLE = False
    logger.warning("[PaddleOCR备用] pypdfium2未安装，无法从PDF提取图片")

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("[PaddleOCR备用] PIL未安装，无法处理图片")


def detect_file_type(file_path: str) -> Optional[str]:
    """通过文件内容（魔数）检测文件类型，不依赖扩展名
    
    Args:
        file_path: 文件路径
        
    Returns:
        文件类型：'pdf', 'png', 'jpeg', 'jpg' 或 None
    """
    if not file_path or not os.path.exists(file_path):
        return None
    
    try:
        with open(file_path, 'rb') as f:
            # 读取文件头部（前16字节足够识别常见格式）
            header = f.read(16)
            
            if not header:
                return None
            
            # PDF文件：以 %PDF 开头
            if header.startswith(b'%PDF'):
                return 'pdf'
            
            # PNG图片：以 \x89PNG\r\n\x1a\n 开头
            if header.startswith(b'\x89PNG\r\n\x1a\n'):
                return 'png'
            
            # JPEG图片：以 \xff\xd8\xff 开头
            if header.startswith(b'\xff\xd8\xff'):
                return 'jpeg'
            
            # 其他格式可以继续扩展
            return None
            
    except Exception as e:
        logger.debug(f"[PaddleOCR备用] 检测文件类型失败: {e}")
        return None


def check_json_data_completeness(json_data: Dict[str, Any], document_type: str) -> bool:
    """检查JSON数据是否大面积缺失
    
    Args:
        json_data: 解析后的JSON数据
        document_type: 文档类型
        
    Returns:
        True表示数据完整，False表示数据缺失
    """
    if not json_data or "data" not in json_data:
        return False
    
    data = json_data["data"]
    
    # 根据文档类型检查关键字段
    if document_type == "noiseMonitoringRecord":
        # 检查噪声检测记录的关键字段（不包括noise数组，noise数组由表格解析生成，不依赖OCR）
        required_fields = ["project", "standardReferences", "soundLevelMeterMode", "soundCalibratorMode"]
        missing_count = sum(1 for field in required_fields if not data.get(field))
        
        # 如果超过一半的关键字段缺失，认为数据缺失
        if missing_count >= len(required_fields) / 2:
            logger.warning(f"[数据完整性检查] 关键字段缺失过多: {missing_count}/{len(required_fields)}")
            return False

        # 检查天气字段是否异常（例如解析成“天气”标签或风向全部缺失）
        weather_list = data.get("weather") or []
        if weather_list:
            weather_label_tokens = {"天气", "天气状况", "天气情况"}
            has_label_as_value = any(
                (item.get("weather") or "").strip() in weather_label_tokens for item in weather_list
            )
            all_wind_direction_missing = all(
                not (item.get("windDirection") or "").strip() for item in weather_list
            )
            if has_label_as_value:
                logger.warning("[数据完整性检查] 天气字段疑似被解析为标签，触发备用解析")
                return False
            if all_wind_direction_missing:
                logger.warning("[数据完整性检查] 风向字段全部缺失，触发备用解析")
                return False
        
        return True
    
    elif document_type == "electromagneticTestRecord":
        # 检查电磁检测记录的关键字段
        # 区分必需字段和可选字段：
        # - deviceName 和 deviceMode 是必需字段（仪器信息）
        # - project 和 standardReferences 可能为空（某些文档可能没有填写）
        required_fields = ["deviceName", "deviceMode"]  # 必需字段
        optional_fields = ["project", "standardReferences"]  # 可选字段
        
        # 检查必需字段
        missing_required = sum(1 for field in required_fields if not data.get(field) or not str(data.get(field)).strip())
        # 检查可选字段（如果所有可选字段都为空，也算缺失）
        missing_optional = sum(1 for field in optional_fields if not data.get(field) or not str(data.get(field)).strip())
        
        # 检查电磁数据
        em_list = data.get("electricMagnetic", [])
        if len(em_list) == 0:
            logger.warning("[数据完整性检查] 电磁数据列表为空")
            return False
        
        # 如果必需字段缺失，认为数据不完整
        if missing_required > 0:
            logger.warning(f"[数据完整性检查] 必需字段缺失: {missing_required}/{len(required_fields)} (deviceName, deviceMode)")
            return False
        
        # 如果所有字段（必需+可选）都缺失，也认为数据不完整
        if missing_required + missing_optional >= len(required_fields) + len(optional_fields):
            logger.warning(f"[数据完整性检查] 所有关键字段都缺失: {missing_required + missing_optional}/{len(required_fields) + len(optional_fields)}")
            return False
        
        return True
    
    elif document_type == "operatingConditionInfo":
        # 检查工况信息
        op_list = data.get("operationalConditions", [])
        if len(op_list) == 0:
            logger.warning("[数据完整性检查] 工况信息列表为空")
            return False
        
        return True
    
    # 未知类型，默认认为完整
    return True


def parse_paddleocr_output(output_text: str) -> Dict[str, Any]:
    """解析paddleocr的输出文本
    
    Args:
        output_text: paddleocr命令的输出文本
        
    Returns:
        解析后的字典，包含parsing_res_list
    """
    try:
        # 清理输出文本，移除可能的额外空白
        output_text = output_text.strip()
        
        # 尝试直接eval（因为输出是Python字典格式）
        # 先处理np.float32等numpy类型
        output_text = output_text.replace('np.float32', 'float')
        output_text = output_text.replace('np.int32', 'int')
        output_text = output_text.replace('np.int64', 'int')
        
        # 尝试使用ast.literal_eval安全解析
        try:
            result = ast.literal_eval(output_text)
        except (ValueError, SyntaxError):
            # 如果literal_eval失败，尝试使用eval（不推荐，但paddleocr输出可能需要）
            logger.warning("[PaddleOCR解析] literal_eval失败，尝试使用eval")
            # 创建一个安全的eval环境
            safe_dict = {"__builtins__": {}}
            result = eval(output_text, safe_dict)
        
        if isinstance(result, dict):
            # 检查是否有res键
            if "res" in result:
                parsing_res_list = result.get("res", {}).get("parsing_res_list", [])
                return {"parsing_res_list": parsing_res_list}
            # 也可能直接包含parsing_res_list
            elif "parsing_res_list" in result:
                return {"parsing_res_list": result.get("parsing_res_list", [])}
        
        return {"parsing_res_list": []}
    except Exception as e:
        logger.error(f"[PaddleOCR解析] 解析输出失败: {e}")
        logger.debug(f"[PaddleOCR解析] 输出内容: {output_text[:500]}")
        return {"parsing_res_list": []}


def paddleocr_to_markdown(paddleocr_result: Dict[str, Any]) -> str:
    """将paddleocr的解析结果转换为markdown格式
    
    Args:
        paddleocr_result: paddleocr解析结果
        
    Returns:
        markdown格式的文本
    """
    markdown_parts = []
    parsing_res_list = paddleocr_result.get("parsing_res_list", [])
    
    for item in parsing_res_list:
        block_label = item.get("block_label", "")
        block_content = item.get("block_content", "")
        
        if block_label == "table":
            # 表格直接使用HTML格式
            markdown_parts.append(block_content)
        elif block_label in ["header", "title", "figure_title"]:
            # 标题使用markdown标题格式
            markdown_parts.append(f"# {block_content}")
        elif block_label == "text":
            # 普通文本
            markdown_parts.append(block_content)
        else:
            # 其他类型直接添加内容
            markdown_parts.append(block_content)
    
    return "\n\n".join(markdown_parts)


def call_paddleocr(image_path: str) -> Optional[Dict[str, Any]]:
    """调用paddleocr命令解析图片
    
    Args:
        image_path: 图片路径
        
    Returns:
        paddleocr解析结果，如果失败返回None
    """
    try:
        # 检查图片文件是否存在
        if not os.path.exists(image_path):
            logger.error(f"[PaddleOCR] 图片文件不存在: {image_path}")
            return None
        
        # 生成输出目录和基础文件名
        image_dir = os.path.dirname(image_path)
        image_basename = os.path.splitext(os.path.basename(image_path))[0]
        save_path_base = os.path.join(image_dir, image_basename)
        
        # 构建paddleocr命令，添加所有参数
        # PaddleOCR会在save_path下创建目录，文件保存在该目录内
        cmd = [
            "paddleocr", "doc_parser", "-i", image_path,
            "--precision", "fp32",
            "--use_doc_unwarping", "False",
            "--use_doc_orientation_classify", "True",
            "--use_chart_recognition", "True",
            "--save_path", save_path_base
        ]
        
        # 设置环境变量，限制GPU内存使用
        # env = os.environ.copy()
        # 设置PaddlePaddle的GPU内存分配策略，使用更保守的内存分配
        # env["FLAGS_fraction_of_gpu_memory_to_use"] = "0.3"  # 只使用30%的GPU内存
        # env["FLAGS_allocator_strategy"] = "auto_growth"  # 使用自动增长策略，避免一次性分配过多内存
        
        logger.info(f"[PaddleOCR] 执行命令: {' '.join(cmd)}")
        
        # 执行命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5分钟超时
            check=False,
        )
        
        if result.returncode != 0:
            logger.error(f"[PaddleOCR] 命令执行失败，返回码: {result.returncode}")
            logger.error(f"[PaddleOCR] 错误输出: {result.stderr}")
            return None
        
        # 从保存的Markdown文件中读取结果
        # PaddleOCR会在save_path下创建目录，文件路径为: {save_path}/{basename}.md
        md_file = os.path.join(save_path_base, f"{image_basename}.md")
        if os.path.exists(md_file):
            logger.info(f"[PaddleOCR] 从Markdown文件读取结果: {md_file}")
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
                    if markdown_content.strip():
                        # 将markdown内容转换为标准格式
                        # 为了兼容现有代码，我们需要将markdown转换回parsing_res_list格式
                        # 但实际上，我们可以直接返回markdown内容，让调用方处理
                        # 这里我们返回一个特殊标记，表示这是markdown格式
                        logger.info(f"[PaddleOCR] 成功读取Markdown文件，内容长度: {len(markdown_content)} 字符")
                        # 返回markdown内容，使用特殊键标记
                        return {"markdown_content": markdown_content}
                    else:
                        logger.warning("[PaddleOCR] Markdown文件内容为空")
            except Exception as e:
                logger.exception(f"[PaddleOCR] 读取Markdown文件失败: {e}")
        else:
            logger.warning(f"[PaddleOCR] Markdown文件不存在: {md_file}")
        
        # 如果Markdown文件不存在或读取失败，尝试从stdout解析
        output_text = result.stdout.strip()
        if output_text:
            logger.info("[PaddleOCR] 从stdout解析输出")
            parsed_result = parse_paddleocr_output(output_text)
            logger.info(f"[PaddleOCR] 解析成功，获得 {len(parsed_result.get('parsing_res_list', []))} 个区块")
            return parsed_result
        else:
            logger.warning("[PaddleOCR] stdout输出为空，且未找到Markdown文件")
            return None
        
    except subprocess.TimeoutExpired:
        logger.error("[PaddleOCR] 命令执行超时")
        return None
    except Exception as e:
        logger.exception(f"[PaddleOCR] 调用失败: {e}")
        return None


def extract_first_page_from_pdf(pdf_path: str, output_dir: str) -> Optional[str]:
    """从PDF文件中提取第一页作为图片
    
    Args:
        pdf_path: PDF文件路径
        output_dir: 输出目录，用于保存提取的图片
        
    Returns:
        提取的图片路径，如果失败返回None
    """
    if not PDFIUM_AVAILABLE or not PIL_AVAILABLE:
        logger.error("[PaddleOCR备用] 缺少必要的库（pypdfium2或PIL），无法从PDF提取图片")
        return None
    
    try:
        if not os.path.exists(pdf_path):
            logger.error(f"[PaddleOCR备用] PDF文件不存在: {pdf_path}")
            return None
        
        # 打开PDF文件
        pdf = pdfium.PdfDocument(pdf_path)
        try:
            if len(pdf) == 0:
                logger.error("[PaddleOCR备用] PDF文件为空")
                return None
            
            # 获取第一页
            page = pdf[0]
            
            # 渲染为图片（使用较低的DPI以减小文件大小，150 DPI通常足够OCR使用）
            # 原始200 DPI会导致文件过大（4-5MB），降低到150 DPI可以显著减小文件大小
            bitmap = page.render(scale=150/72)  # 150 DPI = 150/72 scale
            
            # 转换为PIL Image
            pil_image = bitmap.to_pil()
            
            # 保存图片，使用压缩优化以减小文件大小
            os.makedirs(output_dir, exist_ok=True)
            image_filename = f"paddleocr_fallback_page0_{int(time.time() * 1000)}_{random.randint(1000, 9999)}.png"
            image_path = os.path.join(output_dir, image_filename)
            # 使用optimize=True和compress_level=6来平衡文件大小和质量
            pil_image.save(image_path, "PNG", optimize=True, compress_level=6)
            
            logger.info(f"[PaddleOCR备用] 从PDF提取第一页图片: {image_path}")
            
            # 清理资源
            bitmap.close()
            return image_path
            
        finally:
            pdf.close()
            
    except Exception as e:
        logger.exception(f"[PaddleOCR备用] 从PDF提取图片失败: {e}")
        return None


def find_pdf_file(output_dir: str) -> Optional[str]:
    """在输出目录中查找PDF文件
    
    Args:
        output_dir: 输出目录
        
    Returns:
        PDF文件路径，如果未找到返回None
    """
    if not os.path.exists(output_dir):
        return None
    
    # 查找PDF文件
    pdf_files = list(Path(output_dir).rglob("*.pdf"))
    if pdf_files:
        # 返回第一个找到的PDF文件
        return str(pdf_files[0])
    
    return None


def markdown_to_plain_text(markdown_content: str) -> List[str]:
    """将Markdown内容转换为纯文本列表（按行分割）
    
    Args:
        markdown_content: Markdown格式的文本
        
    Returns:
        纯文本列表，每行一个元素
    """
    if not markdown_content:
        return []
    
    lines = []
    in_code_block = False
    
    # 先处理HTML表格：提取整个表格，转换为文本行
    # 查找所有<table>...</table>块
    table_pattern = r'<table[^>]*>.*?</table>'
    tables = re.findall(table_pattern, markdown_content, re.DOTALL)
    
    # 将表格内容替换为占位符，稍后处理
    table_placeholders = []
    for i, table in enumerate(tables):
        placeholder = f"__TABLE_PLACEHOLDER_{i}__"
        table_placeholders.append((placeholder, table))
        markdown_content = markdown_content.replace(table, placeholder, 1)
    
    # 处理每一行
    for line in markdown_content.split('\n'):
        line = line.rstrip()  # 只移除右侧空格
        
        # 检测代码块
        if line.strip().startswith('```'):
            in_code_block = not in_code_block
            continue
        
        if in_code_block:
            # 代码块内的内容保留原样
            if line.strip():
                lines.append(line)
            continue
        
        # 处理表格占位符
        if '__TABLE_PLACEHOLDER_' in line:
            # 找到对应的表格
            for placeholder, table_html in table_placeholders:
                if placeholder in line:
                    # 提取表格中的所有单元格文本
                    table_lines = extract_table_text(table_html)
                    lines.extend(table_lines)
                    break
            continue
        
        # 检测Markdown表格（以 | 开头）
        if '|' in line and line.strip().startswith('|'):
            # 处理表格行：移除首尾的 |，分割单元格
            cells = [cell.strip() for cell in line.split('|') if cell.strip()]
            # 移除表格分隔行（只包含 - 和 |）
            if all(c in ['-', ':', ' '] for c in ''.join(cells)):
                continue
            # 合并单元格内容，用空格分隔
            table_line = ' '.join(cells)
            if table_line.strip():
                lines.append(table_line)
            continue
        
        # 移除Markdown语法标记
        # 移除标题标记 (# ## ### 等)
        line = re.sub(r'^#+\s*', '', line)
        # 移除列表标记 (- * + 等)
        line = re.sub(r'^[-*+]\s+', '', line)
        # 移除数字列表标记
        line = re.sub(r'^\d+\.\s+', '', line)
        # 移除粗体和斜体标记
        line = re.sub(r'\*\*([^*]+)\*\*', r'\1', line)  # **bold**
        line = re.sub(r'\*([^*]+)\*', r'\1', line)  # *italic*
        line = re.sub(r'__([^_]+)__', r'\1', line)  # __bold__
        line = re.sub(r'_([^_]+)_', r'\1', line)  # _italic_
        # 移除链接格式 [text](url) -> text
        line = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', line)
        # 移除图片格式 ![alt](url) -> alt
        line = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', r'\1', line)
        # 移除行内代码标记
        line = re.sub(r'`([^`]+)`', r'\1', line)
        
        # 移除HTML标签（div、span等）
        line = re.sub(r'<div[^>]*>', '', line)
        line = re.sub(r'</div>', '', line)
        line = re.sub(r'<span[^>]*>', '', line)
        line = re.sub(r'</span>', '', line)
        line = re.sub(r'<[^>]+>', '', line)  # 移除其他HTML标签
        
        # 清理多余空格
        line = line.strip()
        
        if line:  # 只保留非空行
            lines.append(line)
    
    return lines


def extract_table_text(table_html: str) -> List[str]:
    """从HTML表格中提取文本，每行一个元素
    
    Args:
        table_html: HTML表格字符串
        
    Returns:
        文本行列表
    """
    table_lines = []
    
    try:
        # 提取所有<tr>标签
        tr_pattern = r'<tr[^>]*>(.*?)</tr>'
        tr_matches = re.findall(tr_pattern, table_html, re.DOTALL)
        
        for tr_content in tr_matches:
            # 提取所有<td>和<th>标签内的文本
            cell_pattern = r'<(?:td|th)[^>]*>(.*?)</(?:td|th)>'
            cells = re.findall(cell_pattern, tr_content, re.DOTALL)
            
            if cells:
                # 清理每个单元格的文本
                cleaned_cells = []
                for cell in cells:
                    # 移除嵌套的HTML标签
                    cleaned = re.sub(r'<[^>]+>', '', cell)
                    # 移除HTML实体
                    cleaned = cleaned.replace('&nbsp;', ' ')
                    cleaned = cleaned.strip()
                    if cleaned:
                        cleaned_cells.append(cleaned)
                
                if cleaned_cells:
                    # 合并单元格内容，用空格分隔
                    table_line = ' '.join(cleaned_cells)
                    if table_line.strip():
                        table_lines.append(table_line)
    except Exception as e:
        logger.warning(f"[Markdown转换] 提取表格文本失败: {e}")
    
    return table_lines


def call_paddleocr_ocr(image_path: str, save_path: str) -> tuple[Optional[List[str]], Optional[str]]:
    """调用paddleocr ocr命令提取文本（用于API接口）
    
    Args:
        image_path: 图片路径
        save_path: 保存路径（目录）
        
    Returns:
        (OCR识别的文本列表, JSON文件路径)，如果失败返回(None, None)
    """
    try:
        if not os.path.exists(image_path):
            logger.error(f"[PaddleOCR OCR] 图片文件不存在: {image_path}")
            return None, None

        # 构建paddleocr ocr命令
        cmd = ["paddleocr", "ocr", "-i", image_path, "--save_path", save_path]

        logger.info(f"[PaddleOCR OCR] 执行命令: {' '.join(cmd)}")

        # 执行命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5分钟超时
            check=False,
        )

        if result.returncode != 0:
            logger.error(f"[PaddleOCR OCR] 命令执行失败，返回码: {result.returncode}")
            logger.error(f"[PaddleOCR OCR] 错误输出: {result.stderr}")
            return None, None

        # 查找保存的JSON文件
        # OCR命令会在save_path下生成 {basename}_res.json
        image_basename = os.path.splitext(os.path.basename(image_path))[0]
        json_file = os.path.join(save_path, f"{image_basename}_res.json")

        if not os.path.exists(json_file):
            logger.warning(f"[PaddleOCR OCR] JSON文件不存在: {json_file}")
            return None, None

        # 读取JSON文件
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                ocr_data = json.load(f)

            # 优先提取rec_texts字段（如果存在）
            if "rec_texts" in ocr_data and isinstance(ocr_data["rec_texts"], list):
                texts = ocr_data["rec_texts"]
                logger.info(f"[PaddleOCR OCR] 成功提取 {len(texts)} 个文本片段（从rec_texts）")
                return texts, json_file
            
            # 如果没有rec_texts，尝试从parsing_res_list中提取block_content
            if "parsing_res_list" in ocr_data and isinstance(ocr_data["parsing_res_list"], list):
                texts = []
                for item in ocr_data["parsing_res_list"]:
                    if isinstance(item, dict) and "block_content" in item:
                        block_content = item["block_content"]
                        if block_content and block_content.strip():
                            # 如果block_content包含换行符，按行分割
                            if "\n" in block_content:
                                texts.extend([line.strip() for line in block_content.split("\n") if line.strip()])
                            else:
                                texts.append(block_content.strip())
                if texts:
                    logger.info(f"[PaddleOCR OCR] 成功提取 {len(texts)} 个文本片段（从parsing_res_list）")
                    return texts, json_file
            
            logger.warning("[PaddleOCR OCR] JSON文件中未找到rec_texts或parsing_res_list字段")
            return None, json_file

        except Exception as e:
            logger.exception(f"[PaddleOCR OCR] 读取JSON文件失败: {e}")
            return None, json_file

    except subprocess.TimeoutExpired:
        logger.error("[PaddleOCR OCR] 命令执行超时")
        return None, None
    except Exception as e:
        logger.exception(f"[PaddleOCR OCR] 调用失败: {e}")
        return None, None


def call_paddleocr_doc_parser_for_text(image_path: str, save_path: str) -> tuple[Optional[List[str]], Optional[str]]:
    """调用paddleocr doc_parser命令，将markdown转换为纯文本（用于内部调用提取关键词）
    
    Args:
        image_path: 图片路径
        save_path: 保存路径（目录）
        
    Returns:
        (纯文本列表（按行分割）, markdown文件路径)，如果失败返回(None, None)
    """
    try:
        if not os.path.exists(image_path):
            logger.error(f"[PaddleOCR DocParser] 图片文件不存在: {image_path}")
            return None, None
        
        # 生成输出目录和基础文件名
        image_dir = os.path.dirname(image_path)
        image_basename = os.path.splitext(os.path.basename(image_path))[0]
        save_path_base = os.path.join(save_path, image_basename)
        os.makedirs(save_path_base, exist_ok=True)
        
        # 构建paddleocr doc_parser命令
        cmd = [
            "paddleocr", "doc_parser", "-i", image_path,
            "--precision", "fp32",
            "--use_doc_unwarping", "False",
            "--use_doc_orientation_classify", "True",
            "--use_chart_recognition", "True",
            "--save_path", save_path_base
        ]
        
        logger.info(f"[PaddleOCR DocParser] 执行命令: {' '.join(cmd)}")
        
        # 执行命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5分钟超时
            check=False,
        )
        
        if result.returncode != 0:
            logger.error(f"[PaddleOCR DocParser] 命令执行失败，返回码: {result.returncode}")
            logger.error(f"[PaddleOCR DocParser] 错误输出: {result.stderr}")
            return None, None
        
        # 查找保存的Markdown文件
        # PaddleOCR会在save_path下创建目录，文件路径为: {save_path}/{basename}.md
        md_file = os.path.join(save_path_base, f"{image_basename}.md")
        
        # 也可能在子目录中
        if not os.path.exists(md_file):
            md_files = sorted(Path(save_path_base).rglob("*.md"))
            if md_files:
                md_file = str(md_files[0])
                logger.info(f"[PaddleOCR DocParser] 在子目录中找到Markdown文件: {md_file}")
        
        if not os.path.exists(md_file):
            logger.warning(f"[PaddleOCR DocParser] Markdown文件不存在: {md_file}")
            return None, None
        
        # 读取Markdown文件并转换为纯文本
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                markdown_content = f.read()
            
            if not markdown_content.strip():
                logger.warning("[PaddleOCR DocParser] Markdown文件内容为空")
                return [], md_file
            
            # 将Markdown转换为纯文本列表
            plain_text_lines = markdown_to_plain_text(markdown_content)
            logger.info(f"[PaddleOCR DocParser] 成功提取 {len(plain_text_lines)} 行纯文本，Markdown文件: {md_file}")
            return plain_text_lines, md_file
                
        except Exception as e:
            logger.exception(f"[PaddleOCR DocParser] 读取Markdown文件失败: {e}")
            return None, md_file
            
    except subprocess.TimeoutExpired:
        logger.error("[PaddleOCR DocParser] 命令执行超时")
        return None, None
    except Exception as e:
        logger.exception(f"[PaddleOCR DocParser] 调用失败: {e}")
        return None, None


def extract_keywords_from_ocr_texts(ocr_texts: List[str]) -> Dict[str, Any]:
    """从OCR文本列表中提取关键信息
    
    Args:
        ocr_texts: OCR识别的文本列表
        
    Returns:
        包含提取的关键信息的字典
    """
    keywords = {
        "project": "",
        "standardReferences": "",
        "soundLevelMeterMode": "",
        "soundCalibratorMode": "",
        "calibrationValueBefore": "",
        "calibrationValueAfter": "",
        "weather_info": []  # 存储天气相关信息
    }
    
    if not ocr_texts:
        return keywords
    
    # 将所有文本合并，用于匹配
    full_text = " ".join(ocr_texts)
    
    # 提取项目名称
    project_match = re.search(r'项目名称[:：]([^检测依据声级计声校准器检测前检测后气象条件日期]+)', full_text)
    if project_match:
        project = project_match.group(1).strip()
        # 清理可能的后续内容
        project = re.sub(r'检测依据.*$', '', project).strip()
        keywords["project"] = project
        logger.debug(f"[关键词提取] 提取到项目名称: {project}")
    
    # 提取检测依据
    standard_match = re.search(r'检测依据[:：]([^声级计声校准器检测前检测后气象条件日期]+)', full_text)
    if standard_match:
        standard = standard_match.group(1).strip()
        # 提取GB标准
        gb_standards = re.findall(r'GB\s*\d+[-\.]?\d*[-\.]?\d*', standard)
        if gb_standards:
            keywords["standardReferences"] = " ".join(gb_standards)
        else:
            keywords["standardReferences"] = standard.replace("□其他：", "").strip()
        logger.debug(f"[关键词提取] 提取到检测依据: {keywords['standardReferences']}")
    
    # 提取声级计型号/编号
    sound_meter_match = re.search(r'声级计型号[/：:]?(?:编号)?[:：]\s*([A-Z0-9+/]+)', full_text)
    if sound_meter_match:
        keywords["soundLevelMeterMode"] = sound_meter_match.group(1).strip()
        logger.debug(f"[关键词提取] 提取到声级计型号: {keywords['soundLevelMeterMode']}")
    
    # 提取声校准器型号/编号
    calibrator_match = re.search(r'声校准器型号[/：:]?(?:编号)?[:：]\s*([A-Z0-9+/]+)', full_text)
    if calibrator_match:
        keywords["soundCalibratorMode"] = calibrator_match.group(1).strip()
        logger.debug(f"[关键词提取] 提取到声校准器型号: {keywords['soundCalibratorMode']}")
    
    # 提取校准值 - 按照出现顺序：第一个dB(A)是检测前，第二个是检测后
    # 首先尝试通过字段名匹配
    before_cal_found = False
    after_cal_found = False
    
    # 先尝试通过字段名精确匹配
    for i, text in enumerate(ocr_texts):
        if "检测前校准值" in text and not before_cal_found:
            # 在当前文本中查找（可能格式：检测前校准值：93.8 dB（A））
            before_cal_match = re.search(r'检测前校准值[:：]\s*([0-9.]+)\s*dB[（(]?A[）)]?', text)
            if before_cal_match:
                cal_value = before_cal_match.group(1).strip()
                keywords["calibrationValueBefore"] = f"{cal_value} dB(A)"
                logger.debug(f"[关键词提取] 提取到检测前校准值: {keywords['calibrationValueBefore']}")
                before_cal_found = True
                continue
            # 如果当前文本只有字段名（如"检测前校准值："），检查相邻文本片段
            elif re.search(r'检测前校准值[:：]\s*$', text) or (text.strip() == "检测前校准值："):
                # 检查后续3个文本片段，查找包含dB（A）的文本
                for j in range(i + 1, min(i + 4, len(ocr_texts))):
                    next_text = ocr_texts[j]
                    # 查找包含dB（A）的文本（如"93.8dB（A）"）
                    db_match = re.search(r'([0-9.]+)\s*dB[（(]?A[）)]?', next_text)
                    if db_match:
                        cal_value = db_match.group(1).strip()
                        keywords["calibrationValueBefore"] = f"{cal_value} dB(A)"
                        logger.debug(f"[关键词提取] 从相邻文本提取到检测前校准值: {keywords['calibrationValueBefore']}")
                        before_cal_found = True
                        break
                if before_cal_found:
                    continue
        
        if "检测后校准值" in text and not after_cal_found:
            # 在当前文本中查找（可能格式：检测后校准值：93.8 dB（A）或 93.8dB（A）检测后校准值：_93.8dB（A)）
            after_cal_match = re.search(r'检测后校准值[:：]\s*([0-9.]+)\s*dB[（(]?A[）)]?', text)
            if after_cal_match:
                cal_value = after_cal_match.group(1).strip()
                keywords["calibrationValueAfter"] = f"{cal_value} dB(A)"
                logger.debug(f"[关键词提取] 提取到检测后校准值: {keywords['calibrationValueAfter']}")
                after_cal_found = True
                continue
            # 如果当前文本包含"检测后校准值"但值在文本前面（如"93.8dB（A）检测后校准值："）
            elif re.search(r'([0-9.]+)\s*dB[（(]?A[）)]?\s*检测后校准值', text):
                db_match = re.search(r'([0-9.]+)\s*dB[（(]?A[）)]?', text)
                if db_match:
                    cal_value = db_match.group(1).strip()
                    keywords["calibrationValueAfter"] = f"{cal_value} dB(A)"
                    logger.debug(f"[关键词提取] 从同一文本提取到检测后校准值: {keywords['calibrationValueAfter']}")
                    after_cal_found = True
                    continue
            # 如果当前文本只有字段名（如"检测后校准值："），检查相邻文本片段
            elif re.search(r'检测后校准值[:：]\s*$', text) or (text.strip() == "检测后校准值："):
                # 检查后续3个文本片段，查找包含dB（A）的文本
                for j in range(i + 1, min(i + 4, len(ocr_texts))):
                    next_text = ocr_texts[j]
                    # 查找包含dB（A）的文本（如"93.8dB（A）"）
                    db_match = re.search(r'([0-9.]+)\s*dB[（(]?A[）)]?', next_text)
                    if db_match:
                        cal_value = db_match.group(1).strip()
                        keywords["calibrationValueAfter"] = f"{cal_value} dB(A)"
                        logger.debug(f"[关键词提取] 从相邻文本提取到检测后校准值: {keywords['calibrationValueAfter']}")
                        after_cal_found = True
                        break
                if after_cal_found:
                    continue
    
    # 如果通过字段名没有找到，按照出现顺序：第一个dB(A)是检测前，第二个是检测后
    if not before_cal_found or not after_cal_found:
        db_a_matches = []  # 存储所有找到的dB(A)值及其位置
        for i, text in enumerate(ocr_texts):
            # 查找包含dB（A）的文本
            db_matches = re.finditer(r'([0-9.]+)\s*dB[（(]?A[）)]?', text)
            for match in db_matches:
                cal_value = match.group(1).strip()
                db_a_matches.append((i, cal_value, text))
        
        # 如果找到至少一个dB(A)，且还没有检测前校准值，第一个就是检测前
        if db_a_matches and not before_cal_found:
            first_cal_value = db_a_matches[0][1]
            keywords["calibrationValueBefore"] = f"{first_cal_value} dB(A)"
            logger.debug(f"[关键词提取] 按出现顺序提取到检测前校准值（第一个dB(A)）: {keywords['calibrationValueBefore']}")
            before_cal_found = True
        
        # 如果找到至少两个dB(A)，且还没有检测后校准值，第二个就是检测后
        if len(db_a_matches) >= 2 and not after_cal_found:
            second_cal_value = db_a_matches[1][1]
            keywords["calibrationValueAfter"] = f"{second_cal_value} dB(A)"
            logger.debug(f"[关键词提取] 按出现顺序提取到检测后校准值（第二个dB(A)）: {keywords['calibrationValueAfter']}")
            after_cal_found = True
        # 如果只找到一个dB(A)，且还没有检测后校准值，且检测前已经找到，那么这个就是检测后（可能是同一个值）
        elif len(db_a_matches) == 1 and not after_cal_found and before_cal_found:
            # 如果检测前和检测后是同一个值，也设置检测后
            if keywords["calibrationValueBefore"]:
                keywords["calibrationValueAfter"] = keywords["calibrationValueBefore"]
                logger.debug(f"[关键词提取] 检测前和检测后校准值相同: {keywords['calibrationValueAfter']}")
    
    # 提取天气信息（从文本片段中查找包含日期和天气信息的片段）
    # 需要处理文本可能分散在多个片段中的情况
    # 只有当"日期："存在且后续有天气相关信息时才提取
    current_weather_info = None
    weather_start_idx = -1  # 记录天气信息开始的索引
    
    for i, text in enumerate(ocr_texts):
        # 查找包含"日期："的文本，开始新的天气记录
        # 只有当后续文本中有天气相关信息时才创建记录
        date_match = re.search(r'日期[:：]\s*([\d.\-]+)', text)
        if date_match:
            # 检查后续10个文本片段中是否有天气相关信息（天气、温度、湿度、风速、风向等）
            has_weather_info = False
            for j in range(i, min(i + 10, len(ocr_texts))):
                check_text = ocr_texts[j]
                if any(keyword in check_text for keyword in ["天气", "温度", "湿度", "风速", "风向", "℃", "%RH", "m/s"]):
                    has_weather_info = True
                    break
            
            if has_weather_info:
                # 如果之前有未完成的天气记录，先保存
                if current_weather_info and any([current_weather_info["monitorAt"], current_weather_info["weather"], 
                                                 current_weather_info["temp"], current_weather_info["humidity"], 
                                                 current_weather_info["windSpeed"], current_weather_info["windDirection"]]):
                    keywords["weather_info"].append(current_weather_info)
                
                # 创建新的天气记录
                current_weather_info = {
                    "monitorAt": date_match.group(1).strip(),
                    "weather": "",
                    "temp": "",
                    "humidity": "",
                    "windSpeed": "",
                    "windDirection": ""
                }
                weather_start_idx = i
        
        # 如果当前有天气记录，继续提取信息（从当前文本和后续几个文本中）
        if current_weather_info:
            # 只在天气记录开始后的10个文本片段内查找（避免跨太远）
            if weather_start_idx >= 0 and i <= weather_start_idx + 10:
                # 查找天气（在同一文本或后续文本中）
                if not current_weather_info["weather"]:
                    weather_match = re.search(r'天气\s*([^\s温度湿度风速风向]+)', text)
                    if weather_match:
                        weather_value = weather_match.group(1).strip()
                        if weather_value and weather_value != "_" and not re.match(r'^[\d.\-]+$', weather_value):
                            current_weather_info["weather"] = weather_value
                
                # 查找温度（可能格式：温度29.5-35.0 或 温度 29.5-35.0）
                if not current_weather_info["temp"]:
                    temp_match = re.search(r'温度\s*([0-9.\-]+)', text)
                    if temp_match:
                        current_weather_info["temp"] = temp_match.group(1).strip()
                
                # 查找湿度（可能格式：湿度74.0-74.1 或 在"℃ 湿度"之后的文本中）
                if not current_weather_info["humidity"]:
                    # 先检查当前文本是否包含湿度值
                    humidity_match = re.search(r'湿度\s*([0-9.\-]+)', text)
                    if humidity_match:
                        current_weather_info["humidity"] = humidity_match.group(1).strip()
                    # 如果当前文本是"℃ 湿度"或类似格式，湿度值可能在下一行
                    elif "湿度" in text and i + 1 < len(ocr_texts):
                        next_text = ocr_texts[i + 1]
                        if re.match(r'^[0-9.\-]+', next_text):
                            current_weather_info["humidity"] = next_text.strip()
                
                # 查找风速（可能格式：风速0.4-0.5 或 在"%RH 风速"之后的文本中）
                if not current_weather_info["windSpeed"]:
                    # 先检查当前文本是否包含风速值
                    wind_speed_match = re.search(r'风速\s*([0-9.\-]+)', text)
                    if wind_speed_match:
                        current_weather_info["windSpeed"] = wind_speed_match.group(1).strip()
                    # 如果当前文本是"%RH 风速"或类似格式，风速值可能在下一行
                    elif "风速" in text and i + 1 < len(ocr_texts):
                        next_text = ocr_texts[i + 1]
                        if re.match(r'^[0-9.\-]+', next_text):
                            current_weather_info["windSpeed"] = next_text.strip()
                
                # 查找风向（可能格式：风向南风 或 在"m/s风向"之后的文本中，或 "_m/s风向南风" 或 "m/s风向南风"）
                if not current_weather_info["windDirection"]:
                    # 先检查当前文本是否包含风向值（格式：风向南风）
                    # 改进正则表达式，匹配更长的风向值（如"南风"、"东北"、"东偏北"等）
                    # 注意：不要排除"风"字，因为"风速"中包含"风"，会导致"南风"只匹配到"南"
                    wind_dir_match = re.search(r'风向\s*([^\s日期温度湿度]+?)(?=\s|日期|温度|湿度|风速|$)', text)
                    if wind_dir_match:
                        wind_value = wind_dir_match.group(1).strip()
                        # 确保不是"m/s"或数字
                        if wind_value and wind_value != "m/s" and not re.match(r'^[0-9.\-]+$', wind_value):
                            # 如果只匹配到单个方向字（如"南"），检查下一个文本片段是否是"风"
                            if len(wind_value) == 1 and i + 1 < len(ocr_texts):
                                next_text = ocr_texts[i + 1].strip()
                                # 如果下一个文本是"风"，合并为"南风"等
                                if next_text == "风" or next_text.startswith("风"):
                                    wind_value = wind_value + "风"
                                    logger.debug(f"[关键词提取] 合并风向值: {wind_value}")
                            current_weather_info["windDirection"] = wind_value
                    # 如果当前文本是"m/s风向"或"_m/s风向"格式，风向值在同一文本中（如 "_m/s风向南风" 或 "m/s风向南风"）
                    if not current_weather_info["windDirection"]:
                        # 注意：不要排除"风"字，因为"风速"中包含"风"，会导致"南风"只匹配到"南"
                        wind_dir_match = re.search(r'[_\s]*m/s\s*风向\s*([^\s日期温度湿度]+?)(?=\s|日期|温度|湿度|风速|$)', text)
                        if wind_dir_match:
                            wind_value = wind_dir_match.group(1).strip()
                            if wind_value and not re.match(r'^[0-9.\-]+$', wind_value):
                                # 如果只匹配到单个方向字，检查下一个文本片段
                                if len(wind_value) == 1 and i + 1 < len(ocr_texts):
                                    next_text = ocr_texts[i + 1].strip()
                                    if next_text == "风" or next_text.startswith("风"):
                                        wind_value = wind_value + "风"
                                        logger.debug(f"[关键词提取] 合并风向值: {wind_value}")
                                current_weather_info["windDirection"] = wind_value
                    # 如果当前文本是"m/s"或类似格式，风向值可能在下一行
                    if not current_weather_info["windDirection"]:
                        if ("m/s" in text or "风向" in text) and i + 1 < len(ocr_texts):
                            next_text = ocr_texts[i + 1].strip()
                            if next_text and not re.match(r'^[0-9.\-]+', next_text) and "风向" not in next_text:
                                wind_value = next_text
                                # 如果下一个文本是单个方向字，再检查下下个文本是否是"风"
                                if len(wind_value) == 1 and i + 2 < len(ocr_texts):
                                    next_next_text = ocr_texts[i + 2].strip()
                                    if next_next_text == "风" or next_next_text.startswith("风"):
                                        wind_value = wind_value + "风"
                                        logger.debug(f"[关键词提取] 合并风向值: {wind_value}")
                                current_weather_info["windDirection"] = wind_value
    
    # 保存最后一个天气记录
    if current_weather_info and any([current_weather_info["monitorAt"], current_weather_info["weather"], 
                                     current_weather_info["temp"], current_weather_info["humidity"], 
                                     current_weather_info["windSpeed"], current_weather_info["windDirection"]]):
        keywords["weather_info"].append(current_weather_info)
    
    return keywords


def extract_keywords_from_markdown(markdown_content: str) -> Dict[str, Any]:
    """从markdown内容中直接提取关键信息
    
    Args:
        markdown_content: markdown内容字符串
        
    Returns:
        包含提取的关键信息的字典
    """
    keywords = {
        "project": "",
        "standardReferences": "",
        "soundLevelMeterMode": "",
        "soundCalibratorMode": "",
        "calibrationValueBefore": "",
        "calibrationValueAfter": "",
        "weather_info": []  # 存储天气相关信息
    }
    
    if not markdown_content:
        return keywords
    
    # 移除HTML标签，保留文本内容（但保留表格结构信息）
    # 先提取表格中的文本内容
    text_content = markdown_content
    
    # 提取项目名称
    project_match = re.search(r'项目名称[:：]([^检测依据声级计声校准器检测前检测后气象条件日期<>]+)', text_content)
    if project_match:
        project = project_match.group(1).strip()
        # 清理可能的后续内容和HTML标签
        project = re.sub(r'检测依据.*$', '', project).strip()
        project = re.sub(r'<[^>]+>', '', project).strip()
        if project:
            keywords["project"] = project
            logger.debug(f"[Markdown关键词提取] 提取到项目名称: {project}")
    
    # 提取检测依据
    standard_match = re.search(r'检测依据[:：]([^声级计声校准器检测前检测后气象条件日期<>]+)', text_content)
    if standard_match:
        standard = standard_match.group(1).strip()
        # 提取GB标准
        gb_standards = re.findall(r'GB\s*\d+[-\.]?\d*[-\.]?\d*', standard)
        if gb_standards:
            keywords["standardReferences"] = " ".join(gb_standards)
        else:
            keywords["standardReferences"] = re.sub(r'<[^>]+>', '', standard).replace("□其他：", "").strip()
        logger.debug(f"[Markdown关键词提取] 提取到检测依据: {keywords['standardReferences']}")
    
    # 提取声级计型号/编号
    sound_meter_match = re.search(r'声级计型号[/：:]?(?:编号)?[:：]\s*([A-Z0-9+/（）()]+)', text_content)
    if sound_meter_match:
        sound_meter = sound_meter_match.group(1).strip()
        sound_meter = re.sub(r'<[^>]+>', '', sound_meter).strip()
        if sound_meter:
            keywords["soundLevelMeterMode"] = sound_meter
            logger.debug(f"[Markdown关键词提取] 提取到声级计型号: {keywords['soundLevelMeterMode']}")
    
    # 提取声校准器型号/编号
    calibrator_match = re.search(r'声校准器型号[/：:]?(?:编号)?[:：]\s*([A-Z0-9+/（）()]+)', text_content)
    if calibrator_match:
        calibrator = calibrator_match.group(1).strip()
        calibrator = re.sub(r'<[^>]+>', '', calibrator).strip()
        if calibrator:
            keywords["soundCalibratorMode"] = calibrator
            logger.debug(f"[Markdown关键词提取] 提取到声校准器型号: {keywords['soundCalibratorMode']}")
    
    # 提取检测前校准值
    before_cal_match = re.search(r'检测前校准值[:：]\s*([0-9.]+)\s*dB[（(]?A[）)]?', text_content)
    if before_cal_match:
        cal_value = before_cal_match.group(1).strip()
        keywords["calibrationValueBefore"] = f"{cal_value} dB(A)"
        logger.debug(f"[Markdown关键词提取] 提取到检测前校准值: {keywords['calibrationValueBefore']}")
    
    # 提取检测后校准值
    after_cal_match = re.search(r'检测后校准值[:：]\s*([0-9.]+)\s*dB[（(]?A[）)]?', text_content)
    if after_cal_match:
        cal_value = after_cal_match.group(1).strip()
        keywords["calibrationValueAfter"] = f"{cal_value} dB(A)"
        logger.debug(f"[Markdown关键词提取] 提取到检测后校准值: {keywords['calibrationValueAfter']}")
    
    # 提取天气信息
    # 查找所有包含"日期："的行或片段
    date_pattern = r'日期[:：]\s*([\d.\-]+)'
    date_matches = list(re.finditer(date_pattern, text_content))
    
    for date_match in date_matches:
        date_value = date_match.group(1).strip()
        # 获取日期匹配位置后的文本（最多500字符）
        start_pos = date_match.end()
        weather_section = text_content[start_pos:start_pos + 500]
        
        weather_info = {
            "monitorAt": date_value,
            "weather": "",
            "temp": "",
            "humidity": "",
            "windSpeed": "",
            "windDirection": ""
        }
        
        # 提取天气
        weather_match = re.search(r'天气\s*([^\s温度湿度风速风向<>]+)', weather_section)
        if weather_match:
            weather_value = weather_match.group(1).strip()
            weather_value = re.sub(r'<[^>]+>', '', weather_value).strip()
            if weather_value and weather_value != "_" and not re.match(r'^[\d.\-]+$', weather_value):
                weather_info["weather"] = weather_value
        
        # 提取温度
        temp_match = re.search(r'温度[:：]?\s*([0-9.\-]+)', weather_section)
        if temp_match:
            weather_info["temp"] = temp_match.group(1).strip()
        
        # 提取湿度
        humidity_match = re.search(r'湿度[:：]?\s*([0-9.\-]+)', weather_section)
        if humidity_match:
            weather_info["humidity"] = humidity_match.group(1).strip()
        
        # 提取风速
        wind_speed_match = re.search(r'风速[:：]?\s*([0-9.\-]+)', weather_section)
        if wind_speed_match:
            weather_info["windSpeed"] = wind_speed_match.group(1).strip()
        
        # 提取风向
        wind_dir_match = re.search(r'风向[:：]?\s*([^\s日期温度湿度风速<>]+?)(?=\s|日期|温度|湿度|风速|$|<)', weather_section)
        if wind_dir_match:
            wind_value = wind_dir_match.group(1).strip()
            wind_value = re.sub(r'<[^>]+>', '', wind_value).strip()
            if wind_value and wind_value != "m/s" and not re.match(r'^[0-9.\-]+$', wind_value):
                weather_info["windDirection"] = wind_value
        
        # 如果至少有一个字段不为空，则添加这条记录
        if any([weather_info["monitorAt"], weather_info["weather"], weather_info["temp"], 
                weather_info["humidity"], weather_info["windSpeed"], weather_info["windDirection"]]):
            keywords["weather_info"].append(weather_info)
            logger.debug(f"[Markdown关键词提取] 提取到天气记录: {weather_info}")
    
    return keywords


def supplement_missing_fields_from_ocr_json(
    records: List[Dict[str, Any]], 
    ocr_json_path: str,
    field_mapping: Dict[str, str] = None
) -> List[Dict[str, Any]]:
    """从OCR的JSON输出中补充缺失字段
    
    根据文本位置关系来补充缺失字段。例如，如果找到了maxReactivePower的值（如"-2.48"），
    那么minReactivePower的值就在它后面的位置（"-4.75"）。
    
    Args:
        records: 原始解析记录列表（OperationalConditionV2格式）
        ocr_json_path: OCR输出的JSON文件路径
        field_mapping: 字段映射关系，如{"maxReactivePower": "minReactivePower"}，表示maxReactivePower后面是minReactivePower
        
    Returns:
        补充后的记录列表
    """
    if not records or not ocr_json_path or not os.path.exists(ocr_json_path):
        return records
    
    try:
        # 读取OCR JSON文件
        with open(ocr_json_path, 'r', encoding='utf-8') as f:
            ocr_data = json.load(f)
        
        # 提取rec_texts数组
        rec_texts = ocr_data.get("rec_texts", [])
        if not rec_texts:
            logger.warning("[OCR字段补充] JSON中未找到rec_texts字段")
            return records
        
        logger.info(f"[OCR字段补充] 从OCR JSON中提取到 {len(rec_texts)} 个文本片段")
        
        # 默认字段映射：max字段后面是min字段
        if field_mapping is None:
            field_mapping = {
                "maxVoltage": "minVoltage",
                "maxCurrent": "minCurrent",
                "maxActivePower": "minActivePower",
                "maxReactivePower": "minReactivePower"
            }
        
        # 为每条记录补充缺失字段
        for record in records:
            record_name = record.get("name", "")
            logger.debug(f"[OCR字段补充] 处理记录: {record_name}")
            
            # 对于每个max字段，如果对应的min字段为空，尝试从OCR中补充
            for max_field, min_field in field_mapping.items():
                max_value = record.get(max_field, "").strip()
                min_value = record.get(min_field, "").strip()
                
                # 如果max字段有值但min字段为空，尝试从OCR中补充
                if max_value and not min_value:
                    logger.debug(f"[OCR字段补充] 记录 {record_name}: {max_field}={max_value}, {min_field}为空，尝试从OCR补充")
                    
                    # 在rec_texts中查找max_value
                    try:
                        max_value_float = float(max_value)
                        # 查找匹配的文本（允许小的数值差异）
                        found_max = False
                        for i, text in enumerate(rec_texts):
                            # 尝试将文本转换为数值
                            try:
                                text_float = float(text.strip())
                                # 如果数值匹配（允许小的误差）
                                if abs(text_float - max_value_float) < 0.01:
                                    found_max = True
                                    # 检查后续几个文本，找到第一个数值作为min_value
                                    # 在表格中，max和min通常是相邻的，但中间可能有其他文本
                                    for j in range(i + 1, min(i + 5, len(rec_texts))):  # 检查后续最多4个文本
                                        next_text = rec_texts[j].strip()
                                        try:
                                            next_value_float = float(next_text)
                                            # 如果找到数值，且与max_value不同，则作为min_value
                                            if abs(next_value_float - max_value_float) > 0.01:
                                                record[min_field] = next_text
                                                logger.info(f"[OCR字段补充] 从OCR补充 {min_field}: {next_text} (在 {max_field}={max_value} 之后，位置 {j})")
                                                break
                                        except ValueError:
                                            # 不是数值，继续查找
                                            continue
                                    if record.get(min_field):
                                        break
                            except ValueError:
                                # 文本不是数值，继续
                                pass
                        
                        if not found_max:
                            logger.debug(f"[OCR字段补充] 未在OCR中找到 {max_field} 的值 '{max_value}'")
                    except ValueError:
                        # max_value不是数值，跳过
                        logger.debug(f"[OCR字段补充] {max_field}值 '{max_value}' 不是数值，跳过")
                        pass
        
        logger.info("[OCR字段补充] 字段补充完成")
        return records
        
    except Exception as e:
        logger.exception(f"[OCR字段补充] 补充过程出错: {e}")
        return records


def extract_image_from_markdown(markdown_content: str, output_dir: str) -> Optional[str]:
    """从markdown内容中提取第一张图片路径
    
    Args:
        markdown_content: markdown内容
        output_dir: 输出目录
        
    Returns:
        图片路径，如果未找到返回None
    """
    # 查找markdown中的图片引用
    # 格式: ![alt](path) 或 <img src="path">
    image_patterns = [
        r'!\[.*?\]\((.*?)\)',  # markdown图片格式
        r'<img[^>]+src=["\'](.*?)["\']',  # HTML img标签
        r'<img[^>]+src=(.*?)(?:\s|>)',  # HTML img标签（无引号）
    ]
    
    for pattern in image_patterns:
        matches = re.findall(pattern, markdown_content)
        if matches:
            image_path = matches[0]
            # 如果是相对路径，尝试在output_dir中查找
            if not os.path.isabs(image_path):
                # 尝试多个可能的路径
                possible_paths = [
                    os.path.join(output_dir, image_path),
                    os.path.join(output_dir, "images", os.path.basename(image_path)),
                    os.path.join(output_dir, os.path.basename(image_path)),
                ]
                for full_path in possible_paths:
                    if os.path.exists(full_path):
                        return full_path
            elif os.path.exists(image_path):
                return image_path
    
    return None


def fallback_parse_with_paddleocr(
    json_data: Dict[str, Any],
    markdown_content: str,
    output_dir: Optional[str] = None,
    document_type: Optional[str] = None,
    input_file: Optional[str] = None
) -> Optional[str]:
    """当JSON数据缺失时，使用paddleocr进行备用解析
    
    Args:
        json_data: 原始JSON数据
        markdown_content: 原始markdown内容
        output_dir: 输出目录（用于查找图片）
        document_type: 文档类型
        input_file: 原始输入文件路径（PDF或图片），如果未找到图片则从PDF提取第一页
        
    Returns:
        补充后的markdown内容，如果失败返回None
    """
    try:
        # 检查数据完整性
        doc_type = document_type or json_data.get("document_type", "unknown")
        is_complete = check_json_data_completeness(json_data, doc_type)
        
        if is_complete:
            logger.info("[PaddleOCR备用] 数据完整，无需使用备用解析")
            return None
        
        logger.warning("[PaddleOCR备用] 检测到数据缺失，启用PaddleOCR备用解析")
        
        # 检查缺失原因：如果是天气字段缺失，优先使用OCR模式
        use_ocr_mode = False
        if doc_type == "noiseMonitoringRecord":
            data = json_data.get("data", {})
            weather_list = data.get("weather") or []
            if weather_list:
                weather_label_tokens = {"天气", "天气状况", "天气情况"}
                has_label_as_value = any(
                    (item.get("weather") or "").strip() in weather_label_tokens for item in weather_list
                )
                all_wind_direction_missing = all(
                    not (item.get("windDirection") or "").strip() for item in weather_list
                )
                # 检查是否有自动填充的天气标记
                # 注意：JSON数据中的weather是字典，不是对象，所以不能直接用getattr
                # 判断逻辑：如果weather值为"晴"且其他字段（temp/humidity/windSpeed）有值但windDirection为空，
                # 很可能是默认填充的（因为默认填充时windDirection通常为空）
                has_auto_filled_weather = any(
                    (item.get("weather") or "").strip() == "晴" and 
                    any([item.get("temp"), item.get("humidity"), item.get("windSpeed")]) and
                    not (item.get("windDirection") or "").strip()
                    for item in weather_list
                )
                if has_label_as_value or all_wind_direction_missing or has_auto_filled_weather:
                    use_ocr_mode = True
                    logger.info("[PaddleOCR备用] 检测到天气字段缺失，优先使用OCR模式提取文本")
        
        # 尝试从markdown中提取图片路径
        image_path = None
        if output_dir:
            # 首先尝试从markdown中提取
            image_path = extract_image_from_markdown(markdown_content, output_dir)
            if image_path:
                logger.info(f"[PaddleOCR备用] 从markdown中找到图片: {image_path}")
            
            # 如果找不到，尝试在output_dir中查找png文件
            if not image_path and os.path.exists(output_dir):
                # 查找所有png文件
                png_files = list(Path(output_dir).rglob("*.png"))
                if png_files:
                    # 优先查找包含"粘贴"或"image"的文件名
                    for png_file in png_files:
                        if "粘贴" in png_file.name or "image" in png_file.name.lower():
                            image_path = str(png_file)
                            logger.info(f"[PaddleOCR备用] 使用找到的图片: {image_path}")
                            break
                    
                    # 如果没找到特殊名称的，使用第一个
                    if not image_path:
                        image_path = str(png_files[0])
                        logger.info(f"[PaddleOCR备用] 使用找到的图片: {image_path}")
        
        # 如果仍未找到图片，尝试从input_file处理
        if not image_path:
            logger.warning("[PaddleOCR备用] 未找到可用的图片文件，尝试从input_file处理")
            
            if input_file and os.path.exists(input_file):
                # 检测文件实际类型（不依赖扩展名）
                file_type = detect_file_type(input_file)
                
                if file_type == 'pdf':
                    # 文件是PDF，尝试提取第一页
                    pdf_path = input_file
                    logger.info(f"[PaddleOCR备用] 检测到PDF文件（通过内容）: {pdf_path}")
                    image_path = extract_first_page_from_pdf(pdf_path, output_dir)
                    if image_path:
                        logger.info(f"[PaddleOCR备用] 成功从PDF提取第一页图片: {image_path}")
                    else:
                        logger.warning("[PaddleOCR备用] 从PDF提取图片失败（可能是PDF文件损坏或缺少必要的库）")
                elif file_type in ['png', 'jpeg', 'jpg']:
                    # 文件是图片，直接使用
                    image_path = input_file
                    logger.info(f"[PaddleOCR备用] 检测到图片文件（{file_type}）: {image_path}")
                else:
                    # 文件类型未知，尝试按PDF处理（可能是PDF但没有正确识别）
                    logger.debug(f"[PaddleOCR备用] input_file类型未知（{file_type}），尝试按PDF处理: {input_file}")
                    if PDFIUM_AVAILABLE:
                        try:
                            # 尝试打开为PDF
                            pdf_path = input_file
                            image_path = extract_first_page_from_pdf(pdf_path, output_dir)
                            if image_path:
                                logger.info(f"[PaddleOCR备用] 成功将文件作为PDF处理并提取第一页: {image_path}")
                        except Exception as e:
                            logger.debug(f"[PaddleOCR备用] 无法将文件作为PDF处理: {e}")
            
            # 如果input_file处理失败，尝试在output_dir中查找PDF文件
            if not image_path and output_dir:
                pdf_path = find_pdf_file(output_dir)
                if pdf_path:
                    logger.info(f"[PaddleOCR备用] 在输出目录中找到PDF文件: {pdf_path}")
                    image_path = extract_first_page_from_pdf(pdf_path, output_dir)
                    if image_path:
                        logger.info(f"[PaddleOCR备用] 成功从PDF提取第一页图片: {image_path}")
            
            # 如果仍未找到，尝试在input_file的父目录中查找
            if not image_path and input_file:
                parent_dir = os.path.dirname(input_file)
                if parent_dir and os.path.exists(parent_dir):
                    pdf_path = find_pdf_file(parent_dir)
                    if pdf_path:
                        logger.info(f"[PaddleOCR备用] 在input_file父目录中找到PDF文件: {pdf_path}")
                        image_path = extract_first_page_from_pdf(pdf_path, output_dir)
                        if image_path:
                            logger.info(f"[PaddleOCR备用] 成功从PDF提取第一页图片: {image_path}")
            
            if not image_path:
                logger.warning(f"[PaddleOCR备用] 未找到可用的图片或PDF文件（input_file={input_file}, output_dir={output_dir}），无法进行备用解析")
                logger.info("[PaddleOCR备用] 备用解析需要图片文件或PDF文件，如果都没有，将返回原始markdown内容")
        
        if not image_path:
            logger.warning("[PaddleOCR备用] 未找到可用的图片文件，备用解析无法进行，返回None（将使用原始解析结果）")
            return None
        
        # 根据缺失类型选择OCR模式
        paddleocr_markdown = None
        if use_ocr_mode:
            # 天气字段缺失，优先使用OCR模式提取文本
            logger.info("[PaddleOCR备用] 使用OCR模式提取文本（适合补充天气等字段）")
            ocr_save_path = os.path.dirname(image_path) if os.path.dirname(image_path) else output_dir or os.path.dirname(image_path)
            if not ocr_save_path:
                ocr_save_path = os.path.dirname(image_path) or "."
            
            ocr_texts, ocr_json_path = call_paddleocr_ocr(image_path, ocr_save_path)
            if ocr_texts:
                # 从OCR文本中提取关键词
                keywords = extract_keywords_from_ocr_texts(ocr_texts)
                
                # 将关键词信息添加到markdown中（作为注释，供后续解析使用）
                keywords_comment = "\n\n<!-- OCR关键词补充:\n"
                if keywords.get("project"):
                    keywords_comment += f"项目名称：{keywords['project']}\n"
                if keywords.get("standardReferences"):
                    keywords_comment += f"检测依据：{keywords['standardReferences']}\n"
                if keywords.get("soundLevelMeterMode"):
                    keywords_comment += f"声级计型号/编号：{keywords['soundLevelMeterMode']}\n"
                if keywords.get("soundCalibratorMode"):
                    keywords_comment += f"声校准器型号/编号：{keywords['soundCalibratorMode']}\n"
                if keywords.get("calibrationValueBefore"):
                    keywords_comment += f"检测前校准值：{keywords['calibrationValueBefore']}\n"
                if keywords.get("calibrationValueAfter"):
                    keywords_comment += f"检测后校准值：{keywords['calibrationValueAfter']}\n"
                if keywords.get("weather_info"):
                    for weather in keywords["weather_info"]:
                        keywords_comment += f"日期：{weather['monitorAt']} 天气：{weather['weather']} 温度：{weather['temp']} 湿度：{weather['humidity']} 风速：{weather['windSpeed']} 风向：{weather['windDirection']}\n"
                keywords_comment += "-->\n"
                
                # 将关键词信息合并到原始markdown中
                paddleocr_markdown = markdown_content + keywords_comment
                logger.info(f"[PaddleOCR备用] OCR关键词提取完成，补充了天气等字段")
                
                # OCR模式成功，直接返回结果
                return paddleocr_markdown
            else:
                logger.warning("[PaddleOCR备用] OCR模式提取文本失败，尝试使用doc_parser模式")
                use_ocr_mode = False  # 降级到doc_parser模式
        
        # 如果OCR模式未使用或失败，使用doc_parser模式
        if not use_ocr_mode:
            # 其他字段缺失，使用doc_parser模式
            logger.info("[PaddleOCR备用] 使用doc_parser模式解析文档结构")
            paddleocr_result = call_paddleocr(image_path)
            if not paddleocr_result:
                logger.error("[PaddleOCR备用] PaddleOCR解析失败")
                return None
        
        # 检查返回结果格式
        if "markdown_content" in paddleocr_result:
            # 直接从MD文件读取的内容
            paddleocr_markdown = paddleocr_result["markdown_content"]
            logger.info(f"[PaddleOCR备用] 成功从MD文件读取，生成 {len(paddleocr_markdown)} 字符的markdown")
            
            # 从markdown内容中提取关键词来补充数据
            logger.info("[PaddleOCR备用] 从MD文件内容中提取关键词补充数据")
            keywords = extract_keywords_from_markdown(paddleocr_markdown)
            
            # 将关键词信息添加到markdown中（作为注释，供后续解析使用）
            keywords_comment = "\n\n<!-- Markdown关键词补充:\n"
            if keywords["project"]:
                keywords_comment += f"项目名称：{keywords['project']}\n"
            if keywords["standardReferences"]:
                keywords_comment += f"检测依据：{keywords['standardReferences']}\n"
            if keywords["soundLevelMeterMode"]:
                keywords_comment += f"声级计型号/编号：{keywords['soundLevelMeterMode']}\n"
            if keywords["soundCalibratorMode"]:
                keywords_comment += f"声校准器型号/编号：{keywords['soundCalibratorMode']}\n"
            if keywords["calibrationValueBefore"]:
                keywords_comment += f"检测前校准值：{keywords['calibrationValueBefore']}\n"
            if keywords["calibrationValueAfter"]:
                keywords_comment += f"检测后校准值：{keywords['calibrationValueAfter']}\n"
            if keywords["weather_info"]:
                for weather in keywords["weather_info"]:
                    keywords_comment += f"日期：{weather['monitorAt']} 天气：{weather['weather']} 温度：{weather['temp']} 湿度：{weather['humidity']} 风速：{weather['windSpeed']} 风向：{weather['windDirection']}\n"
            keywords_comment += "-->\n"
            
            # 将关键词信息合并到markdown中
            paddleocr_markdown = paddleocr_markdown + keywords_comment
            # 统计补充的字段数量（不包括weather_info列表）
            field_count = sum(1 for k, v in keywords.items() if k != "weather_info" and v) + len(keywords.get("weather_info", []))
            logger.info(f"[PaddleOCR备用] MD文件关键词提取完成，补充了 {field_count} 个字段")
        elif "parsing_res_list" in paddleocr_result:
            # 从JSON或stdout解析的结果，需要转换为markdown
            paddleocr_markdown = paddleocr_to_markdown(paddleocr_result)
            if not paddleocr_markdown:
                logger.warning("[PaddleOCR备用] PaddleOCR未解析出有效内容")
                return None
            logger.info(f"[PaddleOCR备用] 成功解析，生成 {len(paddleocr_markdown)} 字符的markdown")
        else:
            logger.error("[PaddleOCR备用] PaddleOCR返回格式不正确")
            return None
        
        # 调用paddleocr ocr提取关键词来补充数据
        logger.info("[PaddleOCR备用] 调用OCR提取关键词补充数据")
        ocr_save_path = os.path.dirname(image_path)  # 使用图片所在目录作为保存路径
        ocr_texts, _ = call_paddleocr_ocr(image_path, ocr_save_path)
        
        if ocr_texts:
            # 从OCR文本中提取关键词
            keywords = extract_keywords_from_ocr_texts(ocr_texts)
            
            # 将关键词信息添加到markdown中（作为注释，供后续解析使用）
            keywords_comment = "\n\n<!-- OCR关键词补充:\n"
            if keywords["project"]:
                keywords_comment += f"项目名称：{keywords['project']}\n"
            if keywords["standardReferences"]:
                keywords_comment += f"检测依据：{keywords['standardReferences']}\n"
            if keywords["soundLevelMeterMode"]:
                keywords_comment += f"声级计型号/编号：{keywords['soundLevelMeterMode']}\n"
            if keywords["soundCalibratorMode"]:
                keywords_comment += f"声校准器型号/编号：{keywords['soundCalibratorMode']}\n"
            if keywords["calibrationValueBefore"]:
                keywords_comment += f"检测前校准值：{keywords['calibrationValueBefore']}\n"
            if keywords["calibrationValueAfter"]:
                keywords_comment += f"检测后校准值：{keywords['calibrationValueAfter']}\n"
            if keywords["weather_info"]:
                for weather in keywords["weather_info"]:
                    keywords_comment += f"日期：{weather['monitorAt']} 天气：{weather['weather']} 温度：{weather['temp']} 湿度：{weather['humidity']} 风速：{weather['windSpeed']} 风向：{weather['windDirection']}\n"
            keywords_comment += "-->\n"
            
            # 将关键词信息合并到markdown中
            paddleocr_markdown = paddleocr_markdown + keywords_comment
            logger.info(f"[PaddleOCR备用] OCR关键词提取完成，补充了 {len(keywords)} 个字段")

        
        # 合并原始markdown和paddleocr结果
        # 优先使用paddleocr的结果，因为它更完整
        combined_markdown = f"{paddleocr_markdown}\n\n<!-- 原始内容（可能不完整） -->\n{markdown_content}"
        
        return combined_markdown
        
    except Exception as e:
        logger.exception(f"[PaddleOCR备用] 备用解析过程出错: {e}")
        return None


def extract_text_with_paragraphs_from_ocr_json(json_path: str, line_height_threshold: float = 1.5, paragraph_gap_threshold: float = 2.0) -> str:
    """
    从PaddleOCR的JSON输出中提取带段落分割的纯文本
    
    Args:
        json_path: OCR输出的JSON文件路径
        line_height_threshold: 行高倍数阈值，用于判断是否在同一行（默认1.5）
        paragraph_gap_threshold: 段落间距倍数阈值，用于判断是否需要分段（默认2.0）
    
    Returns:
        带段落分割的纯文本字符串
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            ocr_data = json.load(f)
        
        # 提取文本和坐标信息
        rec_texts = ocr_data.get("rec_texts", [])
        dt_polys = ocr_data.get("dt_polys", [])
        
        if not rec_texts or not dt_polys:
            logger.warning("[OCR文本提取] JSON中缺少rec_texts或dt_polys字段")
            return ""
        
        if len(rec_texts) != len(dt_polys):
            logger.warning(f"[OCR文本提取] rec_texts长度({len(rec_texts)})与dt_polys长度({len(dt_polys)})不匹配")
            # 取较小的长度
            min_len = min(len(rec_texts), len(dt_polys))
            rec_texts = rec_texts[:min_len]
            dt_polys = dt_polys[:min_len]
        
        # 计算每个文本块的边界框和中心点
        text_blocks = []
        for i, (text, poly) in enumerate(zip(rec_texts, dt_polys)):
            if not text or not text.strip():
                continue
            
            # 从多边形坐标计算边界框
            # poly格式: [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
            if len(poly) >= 4:
                xs = [point[0] for point in poly]
                ys = [point[1] for point in poly]
                x_min, x_max = min(xs), max(xs)
                y_min, y_max = min(ys), max(ys)
                
                # 计算中心点和高度
                center_x = (x_min + x_max) / 2
                center_y = (y_min + y_max) / 2
                height = y_max - y_min
                width = x_max - x_min
                
                text_blocks.append({
                    'text': text.strip(),
                    'x_min': x_min,
                    'x_max': x_max,
                    'y_min': y_min,
                    'y_max': y_max,
                    'center_x': center_x,
                    'center_y': center_y,
                    'height': height,
                    'width': width,
                    'index': i
                })
        
        if not text_blocks:
            logger.warning("[OCR文本提取] 没有有效的文本块")
            return ""
        
        # 按Y坐标（从上到下）排序
        text_blocks.sort(key=lambda b: (b['y_min'], b['x_min']))
        
        # 计算平均行高（用于判断行间距）
        heights = [b['height'] for b in text_blocks]
        avg_height = sum(heights) / len(heights) if heights else 20
        
        # 将文本块按行分组
        lines = []
        current_line = [text_blocks[0]]
        
        for i in range(1, len(text_blocks)):
            prev_block = text_blocks[i - 1]
            curr_block = text_blocks[i]
            
            # 计算Y坐标重叠度
            y_overlap = min(prev_block['y_max'], curr_block['y_max']) - max(prev_block['y_min'], curr_block['y_min'])
            overlap_ratio = y_overlap / min(prev_block['height'], curr_block['height']) if min(prev_block['height'], curr_block['height']) > 0 else 0
            
            # 计算Y坐标间距
            y_gap = curr_block['y_min'] - prev_block['y_max']
            gap_ratio = y_gap / avg_height if avg_height > 0 else 0
            
            # 判断是否在同一行：有重叠或间距小于行高阈值
            if overlap_ratio > 0.3 or (y_gap >= 0 and gap_ratio < line_height_threshold):
                current_line.append(curr_block)
            else:
                # 新行开始，保存当前行
                lines.append(current_line)
                current_line = [curr_block]
        
        # 添加最后一行
        if current_line:
            lines.append(current_line)
        
        # 对每行内的文本块按X坐标排序（从左到右）
        for line in lines:
            line.sort(key=lambda b: b['x_min'])
        
        # 生成文本，根据行间距判断段落分割
        result_lines = []
        prev_line_y = None
        prev_line_height = None
        
        for line_idx, line in enumerate(lines):
            # 计算当前行的Y坐标和高度
            line_y_min = min(b['y_min'] for b in line)
            line_y_max = max(b['y_max'] for b in line)
            line_height = line_y_max - line_y_min
            line_center_y = (line_y_min + line_y_max) / 2
            
            # 拼接当前行的文本
            # 对于表格数据，使用制表符分隔；对于普通文本，使用空格
            line_text = ""
            prev_x_max = None
            
            # 判断是否是表格行（如果一行中有多个文本块且X坐标分布较均匀）
            is_table_row = len(line) > 2
            
            for block in line:
                if prev_x_max is not None:
                    x_gap = block['x_min'] - prev_x_max
                    # 如果间距较大，添加分隔符
                    if x_gap > avg_height * 0.3:
                        if is_table_row:
                            # 表格使用制表符
                            line_text += "\t"
                        else:
                            # 普通文本使用空格
                            line_text += " "
                line_text += block['text']
                prev_x_max = block['x_max']
            
            # 判断是否需要换段
            if prev_line_y is not None and prev_line_height is not None:
                # 计算行间距
                line_gap = line_y_min - prev_line_y
                gap_ratio = line_gap / prev_line_height if prev_line_height > 0 else 0
                
                # 如果行间距大于段落阈值，添加空行
                if gap_ratio > paragraph_gap_threshold:
                    result_lines.append("")  # 空行表示段落分隔
            
            result_lines.append(line_text)
            prev_line_y = line_y_max
            prev_line_height = line_height
        
        # 合并为最终文本
        result_text = "\n".join(result_lines)
        logger.info(f"[OCR文本提取] 成功提取文本，共 {len(lines)} 行，{len(result_lines)} 行（含段落分隔）")
        
        return result_text
        
    except Exception as e:
        logger.exception(f"[OCR文本提取] 处理失败: {e}")
        return ""

