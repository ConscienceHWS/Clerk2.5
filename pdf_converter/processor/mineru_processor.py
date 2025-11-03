# Copyright (c) Opendatalab. All rights reserved.

"""MinerU PDF处理器模块"""

import os
from pdf2image import convert_from_path
from vllm.v1.engine.async_llm import AsyncLLM
from vllm.engine.arg_utils import AsyncEngineArgs
from mineru_vl_utils import MinerUClient, MinerULogitsProcessor

from ..utils.image_utils import crop_image
from ..utils.logging_config import get_logger
from ..config import (
    TITLE_CROP_TOP, TITLE_CROP_BOTTOM, TITLE_CROP_LEFT, TITLE_CROP_RIGHT,
    BODY_CROP_TOP, BODY_CROP_BOTTOM, BODY_CROP_LEFT, BODY_CROP_RIGHT
)

logger = get_logger("pdf_converter.processor.mineru")

class MinerUPDFProcessor:
    """使用vllm异步引擎处理PDF的处理器"""
    
    def __init__(self, model_name="OpenDataLab/MinerU2.5-2509-1.2B", gpu_memory_utilization=0.5):
        """
        初始化vllm异步引擎和MinerUClient
        
        注意：这个初始化过程是同步阻塞的，会启动子进程加载模型
        如果要避免阻塞，应该在后台线程中初始化
        """
        logger.info(f"初始化MinerU处理器，模型: {model_name}")
        
        # 在初始化前确保CUDA环境干净
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()  # 等待所有CUDA操作完成
        except:
            pass
        
        try:
            logger.info(f"创建AsyncLLM引擎实例（模型: {model_name}）...")
            # 注意：AsyncLLM.from_engine_args 是同步阻塞的
            # 它会启动子进程并加载模型，这个过程可能需要几秒到几十秒
            self.async_llm = AsyncLLM.from_engine_args(
                AsyncEngineArgs(
                    model=model_name,
                    logits_processors=[MinerULogitsProcessor],
                    gpu_memory_utilization=gpu_memory_utilization,
                    trust_remote_code=True,
                    dtype=torch.float32
                )
            )
            logger.info(f"MinerU处理器初始化成功，模型: {model_name}")
        except Exception as e:
            logger.error(f"MinerU处理器初始化失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
        
        self.client = MinerUClient(
            backend="vllm-async-engine",
            vllm_async_llm=self.async_llm
        )
        self._shutdown = False
    
    async def shutdown(self):
        """关闭异步LLM引擎"""
        if self._shutdown:
            logger.debug("MinerU处理器已经关闭，跳过重复关闭")
            return
        
        if self.async_llm:
            try:
                logger.info("正在关闭MinerU异步引擎...")
                await self.async_llm.shutdown()
                self._shutdown = True
                
                # 清理资源并等待一段时间，确保引擎进程完全退出
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        torch.cuda.synchronize()  # 等待CUDA操作完成
                except:
                    pass
                
                # 等待一段时间，确保vllm引擎进程完全退出
                import asyncio
                await asyncio.sleep(1.0)  # 等待1秒，确保进程完全退出
                
                logger.info("MinerU异步引擎已关闭并清理完成")
            except Exception as e:
                logger.warning(f"关闭MinerU异步引擎时出错: {e}")
                self._shutdown = True  # 标记为已关闭，避免重复尝试
    
    async def process_pdf_pages(self, pdf_path, max_pages=None, dpi=200, use_split=False, output_dir=None):
        """
        处理PDF的页面，返回提取的文本块列表（异步版本）
        
        Args:
            pdf_path: PDF文件路径
            max_pages: 最大处理页数
            dpi: 图片DPI
            use_split: 是否使用图片分割提高精度
            output_dir: 输出目录，用于保存切割后的图片（可选）
        
        Returns:
            处理结果列表
        """
        try:
            # 如果使用图片分割且提供了输出目录，创建切割图片保存目录
            split_image_dir = None
            if use_split and output_dir:
                split_image_dir = os.path.join(output_dir, "split_images")
                os.makedirs(split_image_dir, exist_ok=True)
                logger.info(f"切割后的图片将保存到: {split_image_dir}")
            
            # 转换PDF为图片
            all_images = convert_from_path(pdf_path, dpi=dpi)
            total_pages = len(all_images)
            
            # 限制处理的页数
            if max_pages and max_pages > 0:
                images = all_images[:max_pages]
                logger.info(f"将处理前 {max_pages} 页（共 {total_pages} 页）")
            else:
                images = all_images
                logger.info(f"将处理全部 {total_pages} 页")
            
            results = []
            import time
            
            for i, image in enumerate(images):
                page_num = i + 1
                page_start_time = time.time()
                logger.info(f"========== 处理第 {page_num}/{len(images)} 页 ==========")
                logger.info(f"原图尺寸: {image.size[0]} x {image.size[1]} 像素")
                
                if use_split:
                    # 使用图片分割提高精度
                    # 1. 先处理标题区域（用于识别类型）
                    # 标题区域：-t 135 -b 1375 -l 540 -r 540
                    logger.info(f"[第 {page_num} 页] 开始处理标题区域（用于识别文档类型）...")
                    title_start_time = time.time()
                    title_image = crop_image(image, top=TITLE_CROP_TOP, bottom=TITLE_CROP_BOTTOM, left=TITLE_CROP_LEFT, right=TITLE_CROP_RIGHT)
                    logger.info(f"[第 {page_num} 页] 标题区域裁剪完成，尺寸: {title_image.size[0]} x {title_image.size[1]} 像素")
                    
                    # 保存切割后的标题图片（如果指定了输出目录）
                    if split_image_dir:
                        title_image_path = os.path.join(split_image_dir, f"page_{page_num}_title.png")
                        try:
                            title_image.save(title_image_path)
                            logger.info(f"[第 {page_num} 页] 标题区域图片已保存: {title_image_path}")
                        except Exception as e:
                            logger.warning(f"[第 {page_num} 页] 保存标题区域图片失败: {e}")
                    
                    logger.info(f"[第 {page_num} 页] 标题区域开始识别...")
                    title_blocks = await self.client.aio_two_step_extract(title_image)
                    title_markdown = self.blocks_to_markdown(title_blocks)
                    title_time = time.time() - title_start_time
                    title_text_len = len(title_markdown.strip())
                    logger.info(f"[第 {page_num} 页] 标题区域识别完成，耗时: {title_time:.2f}秒，提取文本长度: {title_text_len} 字符")
                    if title_text_len > 0:
                        logger.debug(f"[第 {page_num} 页] 标题区域内容预览: {title_markdown[:100]}...")
                    
                    # 2. 再处理表体区域（用于提取数据）
                    # 表体区域：-t 255 -b 275 -l 115 -r 115
                    logger.info(f"[第 {page_num} 页] 开始处理表体区域（用于提取数据）...")
                    body_start_time = time.time()
                    body_image = crop_image(image, top=BODY_CROP_TOP, bottom=BODY_CROP_BOTTOM, left=BODY_CROP_LEFT, right=BODY_CROP_RIGHT)
                    logger.info(f"[第 {page_num} 页] 表体区域裁剪完成，尺寸: {body_image.size[0]} x {body_image.size[1]} 像素")
                    
                    # 保存切割后的表体图片（如果指定了输出目录）
                    if split_image_dir:
                        body_image_path = os.path.join(split_image_dir, f"page_{page_num}_body.png")
                        try:
                            body_image.save(body_image_path)
                            logger.info(f"[第 {page_num} 页] 表体区域图片已保存: {body_image_path}")
                        except Exception as e:
                            logger.warning(f"[第 {page_num} 页] 保存表体区域图片失败: {e}")
                    
                    logger.info(f"[第 {page_num} 页] 表体区域开始识别...")
                    body_blocks = await self.client.aio_two_step_extract(body_image)
                    body_markdown = self.blocks_to_markdown(body_blocks)
                    body_time = time.time() - body_start_time
                    body_text_len = len(body_markdown.strip())
                    logger.info(f"[第 {page_num} 页] 表体区域识别完成，耗时: {body_time:.2f}秒，提取文本长度: {body_text_len} 字符")
                    if body_text_len > 0:
                        logger.debug(f"[第 {page_num} 页] 表体区域内容预览: {body_markdown[:100]}...")
                    
                    # 合并标题和表体的内容
                    combined_markdown = title_markdown + "\n\n" + body_markdown
                    total_text_len = len(combined_markdown.strip())
                    page_time = time.time() - page_start_time
                    logger.info(f"[第 {page_num} 页] 处理完成，总耗时: {page_time:.2f}秒，合并后文本长度: {total_text_len} 字符")
                    logger.info(f"[第 {page_num} 页] 处理详情 - 标题区域: {title_time:.2f}秒 ({title_text_len} 字符), 表体区域: {body_time:.2f}秒 ({body_text_len} 字符)")
                    
                    results.append({
                        "page": page_num,
                        "extracted_blocks": combined_markdown,
                        "title_markdown": title_markdown,
                        "body_markdown": body_markdown
                    })
                else:
                    # 原有方式：处理整页
                    logger.info(f"[第 {page_num} 页] 开始识别整页内容...")
                    extracted_blocks = await self.client.aio_two_step_extract(image)
                    page_markdown = self.blocks_to_markdown(extracted_blocks)
                    page_time = time.time() - page_start_time
                    page_text_len = len(page_markdown.strip())
                    logger.info(f"[第 {page_num} 页] 识别完成，耗时: {page_time:.2f}秒，提取文本长度: {page_text_len} 字符")
                    
                    results.append({
                        "page": page_num,
                        "extracted_blocks": extracted_blocks
                    })
            
            return results
        except Exception as e:
            logger.exception(f"PDF处理失败: {e}")
            return None
    
    def blocks_to_markdown(self, extracted_blocks):
        """将提取的文本块转换为Markdown格式"""
        if not extracted_blocks:
            return ""
        
        # 如果extracted_blocks已经是字符串（Markdown格式），直接返回
        if isinstance(extracted_blocks, str):
            return extracted_blocks
        
        # 如果是列表，遍历处理
        if isinstance(extracted_blocks, list):
            markdown_content = ""
            for block in extracted_blocks:
                # 如果block是字符串，直接添加
                if isinstance(block, str):
                    markdown_content += block + "\n\n"
                # 如果是字典，按类型处理
                elif isinstance(block, dict):
                    block_type = block.get("type", "")
                    content = block.get("content", "")
                    
                    if block_type == "title" or block_type == "heading":
                        level = block.get("level", 1)
                        markdown_content += f"{'#' * level} {content}\n\n"
                    elif block_type == "paragraph" or block_type == "text":
                        markdown_content += f"{content}\n\n"
                    elif block_type == "list" or block_type == "unordered_list":
                        items = block.get("items", [])
                        for item in items:
                            markdown_content += f"- {item}\n"
                        markdown_content += "\n"
                    elif block_type == "ordered_list":
                        items = block.get("items", [])
                        for i, item in enumerate(items, 1):
                            markdown_content += f"{i}. {item}\n"
                        markdown_content += "\n"
                    elif block_type == "table":
                        table_content = block.get("content", "")
                        if isinstance(table_content, str):
                            markdown_content += f"{table_content}\n\n"
                        else:
                            # 尝试格式化表格
                            markdown_content += f"{table_content}\n\n"
                    elif block_type == "formula" or block_type == "math":
                        formula = block.get("content", "")
                        markdown_content += f"$$\n{formula}\n$$\n\n"
                    elif block_type == "image" or block_type == "figure":
                        image_path = block.get("path", "") or block.get("src", "")
                        alt_text = block.get("alt", "") or image_path
                        if image_path:
                            markdown_content += f"![{alt_text}]({image_path})\n\n"
                    else:
                        # 默认处理：如果有content字段就使用
                        if content:
                            markdown_content += f"{content}\n\n"
                        # 否则尝试转换为字符串
                        elif block:
                            markdown_content += f"{str(block)}\n\n"
            
            return markdown_content
        
        # 其他情况，尝试转换为字符串
        return str(extracted_blocks)

