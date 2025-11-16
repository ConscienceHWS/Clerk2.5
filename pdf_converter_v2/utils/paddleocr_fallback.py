# Copyright (c) Opendatalab. All rights reserved.

"""PaddleOCR备用解析模块 - 当MinerU解析结果缺失时使用"""

import json
import os
import subprocess
import tempfile
import time
import random
from pathlib import Path
from typing import Dict, Any, Optional
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
        # 检查噪声检测记录的关键字段
        required_fields = ["project", "standardReferences", "soundLevelMeterMode", "soundCalibratorMode"]
        missing_count = sum(1 for field in required_fields if not data.get(field))
        
        # 检查噪声数据
        noise_list = data.get("noise", [])
        if len(noise_list) == 0:
            logger.warning("[数据完整性检查] 噪声数据列表为空")
            return False
        
        # 如果超过一半的关键字段缺失，或者噪声数据为空，认为数据缺失
        if missing_count >= len(required_fields) / 2:
            logger.warning(f"[数据完整性检查] 关键字段缺失过多: {missing_count}/{len(required_fields)}")
            return False
        
        # 检查噪声数据是否完整
        for noise_item in noise_list:
            if not noise_item.get("code") or not noise_item.get("address"):
                logger.warning("[数据完整性检查] 噪声数据项不完整")
                return False
        
        return True
    
    elif document_type == "electromagneticTestRecord":
        # 检查电磁检测记录的关键字段
        required_fields = ["project", "standardReferences", "deviceName", "deviceMode"]
        missing_count = sum(1 for field in required_fields if not data.get(field))
        
        # 检查电磁数据
        em_list = data.get("electricMagnetic", [])
        if len(em_list) == 0:
            logger.warning("[数据完整性检查] 电磁数据列表为空")
            return False
        
        if missing_count >= len(required_fields) / 2:
            logger.warning(f"[数据完整性检查] 关键字段缺失过多: {missing_count}/{len(required_fields)}")
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
        
        # 构建paddleocr命令，添加save_path参数
        cmd = ["paddleocr", "doc_parser", "-i", image_path, "--save_path", save_path_base]
        
        # 设置环境变量，限制GPU内存使用
        env = os.environ.copy()
        # 设置PaddlePaddle的GPU内存分配策略，使用更保守的内存分配
        env["FLAGS_fraction_of_gpu_memory_to_use"] = "0.3"  # 只使用30%的GPU内存
        env["FLAGS_allocator_strategy"] = "auto_growth"  # 使用自动增长策略，避免一次性分配过多内存
        
        logger.info(f"[PaddleOCR] 执行命令: {' '.join(cmd)} (使用GPU，限制内存使用)")
        
        # 执行命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5分钟超时
            check=False,
            env=env  # 使用修改后的环境变量
        )
        
        if result.returncode != 0:
            logger.error(f"[PaddleOCR] 命令执行失败，返回码: {result.returncode}")
            logger.error(f"[PaddleOCR] 错误输出: {result.stderr}")
            return None
        
        # 尝试从保存的JSON文件中读取结果
        json_file = f"{save_path_base}_res.json"
        if os.path.exists(json_file):
            logger.info(f"[PaddleOCR] 从JSON文件读取结果: {json_file}")
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                    # 转换为标准格式
                    if isinstance(json_data, dict):
                        # 如果JSON文件直接包含parsing_res_list，直接返回
                        if "parsing_res_list" in json_data:
                            parsed_result = {"parsing_res_list": json_data["parsing_res_list"]}
                        # 如果包含res键，提取其中的parsing_res_list
                        elif "res" in json_data and "parsing_res_list" in json_data.get("res", {}):
                            parsed_result = {"parsing_res_list": json_data["res"]["parsing_res_list"]}
                        else:
                            # 尝试解析整个JSON结构
                            parsed_result = parse_paddleocr_output(json.dumps(json_data))
                    else:
                        parsed_result = parse_paddleocr_output(json.dumps(json_data))
                    
                    logger.info(f"[PaddleOCR] 从JSON文件解析成功，获得 {len(parsed_result.get('parsing_res_list', []))} 个区块")
                    return parsed_result
            except Exception as e:
                logger.warning(f"[PaddleOCR] 读取JSON文件失败: {e}，尝试从stdout解析")
        
        # 如果JSON文件不存在或读取失败，尝试从stdout解析
        output_text = result.stdout.strip()
        if output_text:
            logger.info("[PaddleOCR] 从stdout解析输出")
            parsed_result = parse_paddleocr_output(output_text)
            logger.info(f"[PaddleOCR] 解析成功，获得 {len(parsed_result.get('parsing_res_list', []))} 个区块")
            return parsed_result
        else:
            logger.warning("[PaddleOCR] stdout输出为空，且未找到JSON文件")
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
        
        # 如果仍未找到图片，尝试从PDF提取第一页
        if not image_path:
            logger.warning("[PaddleOCR备用] 未找到可用的图片文件，尝试从PDF提取第一页")
            
            # 首先尝试使用提供的input_file
            pdf_path = None
            if input_file and os.path.exists(input_file) and input_file.lower().endswith('.pdf'):
                pdf_path = input_file
                logger.info(f"[PaddleOCR备用] 使用提供的PDF文件: {pdf_path}")
            elif output_dir:
                # 在output_dir中查找PDF文件
                pdf_path = find_pdf_file(output_dir)
                if pdf_path:
                    logger.info(f"[PaddleOCR备用] 在输出目录中找到PDF文件: {pdf_path}")
            
            if pdf_path:
                # 从PDF提取第一页
                image_path = extract_first_page_from_pdf(pdf_path, output_dir)
                if image_path:
                    logger.info(f"[PaddleOCR备用] 成功从PDF提取第一页图片: {image_path}")
                else:
                    logger.error("[PaddleOCR备用] 从PDF提取图片失败")
            else:
                logger.error("[PaddleOCR备用] 未找到PDF文件，无法提取图片")
        
        if not image_path:
            logger.error("[PaddleOCR备用] 未找到可用的图片文件，备用解析失败")
            return None
        
        # 调用paddleocr
        paddleocr_result = call_paddleocr(image_path)
        if not paddleocr_result:
            logger.error("[PaddleOCR备用] PaddleOCR解析失败")
            return None
        
        # 转换为markdown
        paddleocr_markdown = paddleocr_to_markdown(paddleocr_result)
        
        if not paddleocr_markdown:
            logger.warning("[PaddleOCR备用] PaddleOCR未解析出有效内容")
            return None
        
        logger.info(f"[PaddleOCR备用] 成功解析，生成 {len(paddleocr_markdown)} 字符的markdown")
        
        # 合并原始markdown和paddleocr结果
        # 优先使用paddleocr的结果，因为它更完整
        combined_markdown = f"{paddleocr_markdown}\n\n<!-- 原始内容（可能不完整） -->\n{markdown_content}"
        
        return combined_markdown
        
    except Exception as e:
        logger.exception(f"[PaddleOCR备用] 备用解析过程出错: {e}")
        return None

