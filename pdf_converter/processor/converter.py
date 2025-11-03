# Copyright (c) Opendatalab. All rights reserved.

"""PDF转换主函数模块"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional
from PIL import Image

import aiofiles
from pdf2image import convert_from_path
from mineru.cli.common import prepare_env, pdf_suffixes, image_suffixes

from .mineru_processor import MinerUPDFProcessor
from ..utils.file_utils import safe_stem, to_pdf
from ..utils.image_utils import replace_image_with_base64
from ..parser.json_converter import parse_markdown_to_json
from ..utils.logging_config import get_logger

logger = get_logger("pdf_converter.processor")

async def convert_to_markdown(
    input_file,
    output_dir="./output",
    max_pages=10,
    is_ocr=False,
    formula_enable=True,
    table_enable=True,
    language="ch",
    backend="vllm-engine",
    url=None,
    embed_images=True,
    model_name="OpenDataLab/MinerU2.5-2509-1.2B",
    gpu_memory_utilization=0.9,
    dpi=200,
    output_json=False,
    use_split=False
):
    """将PDF/图片转换为Markdown的主要函数（使用vllm引擎）"""
    
    if not os.path.exists(input_file):
        logger.error(f"输入文件不存在: {input_file}")
        return None

    # 转换为PDF格式（如果需要）
    pdf_path = to_pdf(input_file)
    if not pdf_path:
        logger.error("文件转换失败")
        return None

    processor = None
    try:
        os.makedirs(output_dir, exist_ok=True)
        
        # 生成文件名
        file_name = f'{safe_stem(Path(input_file).stem)}_{time.strftime("%y%m%d_%H%M%S")}'
        parse_method = 'vllm-engine'
        
        # 准备输出目录
        local_image_dir, local_md_dir = prepare_env(output_dir, file_name, parse_method)
        
        # 初始化处理器（每次请求都创建新实例，确保模型正确加载）
        # 注意：AsyncLLM.from_engine_args 是同步阻塞的，会阻塞当前线程
        # 在异步环境中，这可能会阻塞事件循环，导致响应延迟
        # 但因为我们已经在后台任务中执行，所以不会阻塞HTTP响应返回
        logger.info(f"初始化MinerU处理器（模型: {model_name}）...")
        # 将同步阻塞的初始化操作放到线程池中执行，避免阻塞事件循环
        loop = asyncio.get_event_loop()
        processor = await loop.run_in_executor(
            None,  # 使用默认线程池
            lambda: MinerUPDFProcessor(model_name=model_name, gpu_memory_utilization=gpu_memory_utilization)
        )
        logger.info("MinerU处理器初始化完成")
        
        # 处理PDF页面
        logger.info(f"开始处理PDF: {pdf_path}")
        if use_split:
            logger.info("使用图片分割模式提高识别精度")
        results = await processor.process_pdf_pages(pdf_path, max_pages=max_pages, dpi=dpi, use_split=use_split, output_dir=output_dir)
        
        if not results:
            logger.error("PDF处理失败")
            return None
        
        # 将所有页面的内容合并为Markdown
        markdown_parts = []
        
        # 获取PDF的图片（用于保存和OCR）
        pdf_images = []
        first_page_image = None
        try:
            if embed_images or output_json:
                # 获取PDF的图片（用于保存和OCR）
                pdf_images = convert_from_path(pdf_path, dpi=dpi)
                if max_pages:
                    pdf_images = pdf_images[:max_pages]
                
                # 保存第一页图片用于OCR（如果是噪声检测表）
                if pdf_images and output_json:
                    first_page_image = pdf_images[0]
        except Exception as e:
            logger.warning(f"无法加载PDF图片: {e}")
            pdf_images = []
        
        for i, result in enumerate(results):
            page_num = result['page']
            
            # 如果使用了图片分割，extracted_blocks已经是markdown字符串
            if use_split and isinstance(result.get('extracted_blocks'), str):
                page_markdown = result['extracted_blocks']
                # 可以单独使用标题和表体的结果
                if 'title_markdown' in result:
                    logger.debug(f"第 {page_num} 页标题区域识别结果: {result['title_markdown'][:100]}...")
                if 'body_markdown' in result:
                    logger.debug(f"第 {page_num} 页表体区域识别结果: {result['body_markdown'][:100]}...")
            else:
                extracted_blocks = result['extracted_blocks']
                # 转换为Markdown
                page_markdown = processor.blocks_to_markdown(extracted_blocks)
            
            # 如果需要保存页面图片，将图片链接添加到Markdown中
            if i < len(pdf_images) and embed_images:
                image_filename = f"page_{page_num}.png"
                image_path = os.path.join(local_image_dir, image_filename)
                try:
                    pdf_images[i].save(image_path)
                    # 在页面内容前添加图片引用（可选）
                    # page_markdown = f"![第 {page_num} 页](images/{image_filename})\n\n" + page_markdown
                except Exception as e:
                    logger.warning(f"保存页面图片失败: {e}")
            
            markdown_parts.append(page_markdown)
        
        # 合并所有页面内容
        original_content = "\n\n".join(markdown_parts)
        
        # 在处理完PDF后，如果需要进行OCR，则关闭MinerU以释放显存
        # 注意：在API环境中，如果不进行OCR，可以选择不关闭处理器以提高性能
        # 关闭处理器会导致下次请求时需要重新加载模型
        if processor and output_json:
            # 只有在需要OCR时才关闭处理器释放显存（OCR是CPU模式，但关闭可能有助于稳定性）
            try:
                logger.info("关闭MinerU处理器以释放GPU显存（用于后续OCR处理）...")
                await processor.shutdown()
                processor = None
                # 清理CUDA缓存
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        logger.info("已清理CUDA缓存")
                except ImportError:
                    pass
                except Exception as e:
                    logger.debug(f"清理CUDA缓存失败: {e}")
            except Exception as e:
                logger.warning(f"关闭MinerU处理器失败: {e}")
        elif processor:
            # 如果不进行OCR，保持处理器运行状态（可以在finally中关闭，或者不关闭以便复用）
            logger.debug("保持MinerU处理器运行状态（未进行OCR，无需释放显存）")
            # 注意：这里不关闭processor，让finally块处理
        
        logger.info(original_content)


        # 处理图片嵌入
        if embed_images:
            final_content = replace_image_with_base64(original_content, local_image_dir)
        else:
            final_content = original_content
        
        logger.info(final_content)
        # 保存Markdown文件
        md_path = os.path.join(local_md_dir, f"{file_name}.md")
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(final_content)
        logger.info(f"Markdown文件已保存: {md_path}")
        
        # 生成输出文件路径（在output_dir根目录下也保存一份）
        output_md_path = os.path.join(output_dir, f"{file_name}.md")
        with open(output_md_path, 'w', encoding='utf-8') as f:
            f.write(final_content)
        
        logger.info(f"转换完成: {output_md_path}")
        
        # JSON转换（如果需要）
        json_data = None
        json_path = None
        if output_json:
            try:
                logger.info("开始转换为JSON格式...")
                # 如果是噪声检测表，传递第一页图片用于OCR补充识别
                json_data = parse_markdown_to_json(original_content, first_page_image=first_page_image, output_dir=output_dir)
                json_path = os.path.join(output_dir, f"{file_name}.json")
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=2)
                logger.info(f"JSON文件已保存: {json_path}")
                logger.info(f"文档类型: {json_data.get('document_type', 'unknown')}")
            except Exception as e:
                logger.exception(f"JSON转换失败: {e}")
                json_data = None
        
        return {
            'markdown_file': output_md_path,
            'json_file': json_path,
            'json_data': json_data,
            'content': final_content,
            'original_content': original_content
        }

    except Exception as e:
        logger.exception(f"转换过程出错: {e}")
        return None
    finally:
        # 关闭异步LLM引擎（如果还没有关闭）
        # 注意：如果已经关闭（为了OCR），这里会安全地处理
        if processor:
            try:
                logger.debug("清理MinerU处理器...")
                await processor.shutdown()
                processor = None
                # 确保清理CUDA缓存
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        torch.cuda.synchronize()  # 等待CUDA操作完成
                except:
                    pass
            except Exception as e:
                logger.warning(f"关闭异步LLM引擎失败: {e}")
        
        # 清理临时PDF文件
        if pdf_path and pdf_path != input_file and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except:
                pass

