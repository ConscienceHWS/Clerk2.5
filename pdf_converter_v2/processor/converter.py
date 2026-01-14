# Copyright (c) Opendatalab. All rights reserved.

"""PDF转换主函数模块 v2 - 使用新的API接口"""

import asyncio
import json
import os
import time
import zipfile
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Sequence

import aiohttp
import aiofiles
from PIL import Image

from ..utils.logging_config import get_logger
from ..utils.file_utils import safe_stem

logger = get_logger("pdf_converter_v2.processor")
PADDLE_CMD = os.getenv("PADDLE_DOC_PARSER_CMD", "paddleocr")


async def _run_paddle_doc_parser(cmd: Sequence[str]) -> tuple[int, str, str]:
    """异步执行 paddleocr doc_parser 命令"""
    logger.info(f"[Paddle] 执行命令: {' '.join(cmd)}")
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await process.communicate()
    stdout = stdout_bytes.decode("utf-8", errors="ignore")
    stderr = stderr_bytes.decode("utf-8", errors="ignore")
    if stdout:
        logger.debug(f"[Paddle] stdout: {stdout[:2000]}")
    if stderr:
        logger.debug(f"[Paddle] stderr: {stderr[:2000]}")
    return process.returncode, stdout, stderr


async def _convert_with_paddle(
    input_file: str,
    output_dir: str,
    embed_images: bool,
    output_json: bool,
    forced_document_type: Optional[str],
):
    """针对工况附件使用 PaddleOCR doc_parser 直接转换"""
    if not os.path.exists(input_file):
        logger.error(f"[Paddle] 输入文件不存在: {input_file}")
        return None
    
    file_name = f'{safe_stem(Path(input_file).stem)}_{time.strftime("%y%m%d_%H%M%S")}'
    os.makedirs(output_dir, exist_ok=True)
    
    temp_dir = tempfile.mkdtemp(prefix=f"pdf_converter_paddle_{file_name}_")
    logger.info(f"[Paddle] 创建临时目录: {temp_dir}")
    save_path_base = os.path.join(temp_dir, Path(input_file).stem)
    os.makedirs(save_path_base, exist_ok=True)
    
    cmd = [
        PADDLE_CMD,
        "doc_parser",
        "-i",
        input_file,
        "--precision",
        "fp32",
        "--use_doc_unwarping",
        "False",
        "--use_doc_orientation_classify",
        "True",
        "--use_chart_recognition",
        "True",
        "--save_path",
        save_path_base,
    ]
    
    try:
        return_code, _, stderr = await _run_paddle_doc_parser(cmd)
        if return_code != 0:
            logger.error(f"[Paddle] doc_parser 执行失败 code={return_code}")
            if stderr:
                logger.error(stderr)
            return None
        
        md_files = sorted(Path(save_path_base).rglob("*.md"))
        if not md_files:
            logger.error("[Paddle] 未找到Markdown文件")
            return None
        
        markdown_parts = []
        for md_file in md_files:
            async with aiofiles.open(md_file, "r", encoding="utf-8") as f:
                markdown_parts.append(await f.read())
        final_content = "\n\n".join(markdown_parts)
        logger.info(f"[Paddle] 合并后的markdown长度: {len(final_content)}")
        
        local_md_dir = os.path.join(output_dir, file_name, "markdown")
        os.makedirs(local_md_dir, exist_ok=True)
        md_path = os.path.join(local_md_dir, f"{file_name}.md")
        async with aiofiles.open(md_path, "w", encoding="utf-8") as f:
            await f.write(final_content)
        
        output_md_path = os.path.join(output_dir, f"{file_name}.md")
        async with aiofiles.open(output_md_path, "w", encoding="utf-8") as f:
            await f.write(final_content)
        
        if embed_images:
            local_image_dir = os.path.join(output_dir, file_name, "images")
            os.makedirs(local_image_dir, exist_ok=True)
            for asset in Path(save_path_base).rglob("*"):
                if asset.is_file() and asset.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}:
                    shutil.copy2(asset, os.path.join(local_image_dir, asset.name))
        
        json_data = None
        json_path = None
        if output_json:
            try:
                from ..parser.json_converter import parse_markdown_to_json
                json_output_dir = os.path.join(output_dir, file_name)
                json_data = parse_markdown_to_json(
                    final_content,
                    first_page_image=None,
                    output_dir=json_output_dir,
                    forced_document_type=forced_document_type,
                    enable_paddleocr_fallback=True,
                    input_file=input_file,
                )
                json_path = os.path.join(output_dir, f"{file_name}.json")
                async with aiofiles.open(json_path, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(json_data, ensure_ascii=False, indent=2))
            except Exception as exc:
                logger.exception(f"[Paddle] JSON转换失败: {exc}")
        
        return {
            "markdown_file": output_md_path,
            "json_file": json_path,
            "json_data": json_data,
            "content": final_content,
        }
    finally:
        try:
            shutil.rmtree(temp_dir)
        except Exception as exc:
            logger.warning(f"[Paddle] 清理临时目录失败: {exc}")

async def convert_to_markdown(
    input_file: str,
    output_dir: str = "./output",
    max_pages: int = 10,
    is_ocr: bool = False,
    formula_enable: bool = True,
    table_enable: bool = True,
    language: str = "ch",
    backend: str = "vlm-vllm-async-engine",
    url: str = "http://192.168.2.3:8000",
    embed_images: bool = True,
    output_json: bool = False,
    start_page_id: int = 0,
    end_page_id: int = 99999,
    parse_method: str = "auto",
    server_url: str = "string",
    response_format_zip: bool = True,
    return_middle_json: bool = False,
    return_model_output: bool = True,
    return_md: bool = True,
    return_images: bool = True,  # 默认启用，以便PaddleOCR备用解析可以使用
    return_content_list: bool = False,
    forced_document_type: Optional[str] = None
):
    """将PDF/图片转换为Markdown的主要函数（使用新的API接口）"""
    
    if not os.path.exists(input_file):
        logger.error(f"输入文件不存在: {input_file}")
        return None

    # 生成文件名
    file_name = f'{safe_stem(Path(input_file).stem)}_{time.strftime("%y%m%d_%H%M%S")}'
    
    try:
        os.makedirs(output_dir, exist_ok=True)
        
        # 构建API请求URL
        api_url = f"{url}/file_parse"
        logger.info(f"调用API接口: {api_url}")
        
        # 创建临时目录用于解压zip文件
        temp_dir = tempfile.mkdtemp(prefix=f"pdf_converter_v2_{file_name}_")
        logger.info(f"创建临时目录: {temp_dir}")
        
        try:
            # 准备表单数据
            form_data = aiohttp.FormData()
            form_data.add_field('return_middle_json', str(return_middle_json).lower())
            form_data.add_field('return_model_output', str(return_model_output).lower())
            form_data.add_field('return_md', str(return_md).lower())
            form_data.add_field('return_images', str(return_images).lower())
            form_data.add_field('end_page_id', str(end_page_id))
            form_data.add_field('parse_method', parse_method)
            form_data.add_field('start_page_id', str(start_page_id))
            form_data.add_field('lang_list', language)
            form_data.add_field('output_dir', './output')
            form_data.add_field('server_url', server_url)
            form_data.add_field('return_content_list', str(return_content_list).lower())
            form_data.add_field('backend', backend)
            form_data.add_field('table_enable', str(table_enable).lower())
            form_data.add_field('response_format_zip', str(response_format_zip).lower())
            form_data.add_field('formula_enable', str(formula_enable).lower())
            
            # 打开文件并添加到表单数据（文件会在请求发送时读取）
            file_obj = open(input_file, 'rb')
            try:
                # 根据扩展名设置内容类型，默认使用application/octet-stream
                ext = (Path(input_file).suffix or "").lower()
                content_type = 'application/octet-stream'
                if ext == '.pdf':
                    content_type = 'application/pdf'
                elif ext in {'.png'}:
                    content_type = 'image/png'
                elif ext in {'.jpg', '.jpeg'}:
                    content_type = 'image/jpeg'
                elif ext in {'.bmp'}:
                    content_type = 'image/bmp'
                elif ext in {'.tif', '.tiff'}:
                    content_type = 'image/tiff'
                elif ext in {'.webp'}:
                    content_type = 'image/webp'

                # 将上传文件名截断为更短的安全文件名，避免对端服务在构造输出路径时触发 “File name too long”
                # 使用更短的阈值（80字符），因为外部API可能会在路径中拼接其他部分
                original_name = os.path.basename(input_file)
                max_name_len = 80  # 降低到80字符，留出更多安全余量
                if len(original_name) > max_name_len:
                    stem = Path(original_name).stem
                    suffix = Path(original_name).suffix
                    max_stem_len = max_name_len - len(suffix)
                    # 如果截断后太短，使用简化命名：保留前几个字符 + 哈希后缀
                    if max_stem_len < 10:
                        import hashlib
                        hash_suffix = hashlib.md5(original_name.encode('utf-8')).hexdigest()[:8]
                        upload_name = f"file_{hash_suffix}{suffix}"
                    else:
                        safe_stem_name = stem[:max_stem_len]
                        upload_name = f"{safe_stem_name}{suffix}"
                else:
                    upload_name = original_name

                form_data.add_field(
                    'files',
                    file_obj,
                    filename=upload_name,
                    content_type=content_type
                )
                
                # 发送API请求
                async with aiohttp.ClientSession() as session:
                    logger.info(f"开始上传文件: {input_file}")
                    async with session.post(api_url, data=form_data) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            logger.error(f"API请求失败，状态码: {response.status}, 错误: {error_text}")
                            return None
                        
                        # 检查Content-Type是否为zip
                        content_type = response.headers.get('Content-Type', '')
                        if 'zip' not in content_type and 'application/zip' not in content_type:
                            # 如果不是zip，尝试检查响应内容
                            content_disposition = response.headers.get('Content-Disposition', '')
                            if 'zip' not in content_disposition.lower():
                                logger.warning(f"响应Content-Type可能不是zip: {content_type}")
                        
                        # 保存zip文件
                        zip_path = os.path.join(temp_dir, f"{file_name}.zip")
                        async with aiofiles.open(zip_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                await f.write(chunk)
                        
                        logger.info(f"Zip文件已保存: {zip_path}")
            finally:
                # 关闭文件对象
                file_obj.close()
            
            # 解压zip文件
            logger.info("开始解压zip文件...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # 查找md文件
            md_files = list(Path(temp_dir).rglob("*.md"))
            if not md_files:
                logger.error("在zip文件中未找到md文件")
                return None
            
            logger.info(f"找到 {len(md_files)} 个md文件")
            
            # 读取所有md文件并合并
            markdown_parts = []
            for md_file in sorted(md_files):
                logger.info(f"读取md文件: {md_file}")
                async with aiofiles.open(md_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    markdown_parts.append(content)
            
            # 合并所有页面内容
            original_content = "\n\n".join(markdown_parts)
            logger.info(f"合并后的markdown长度: {len(original_content)} 字符")
            
            # 准备输出目录
            local_md_dir = os.path.join(output_dir, file_name, "markdown")
            os.makedirs(local_md_dir, exist_ok=True)
            
            # 处理图片嵌入（如果需要）
            final_content = original_content
            if embed_images:
                # 查找图片文件
                image_files = list(Path(temp_dir).rglob("*.png")) + list(Path(temp_dir).rglob("*.jpg")) + list(Path(temp_dir).rglob("*.jpeg"))
                if image_files:
                    local_image_dir = os.path.join(output_dir, file_name, "images")
                    os.makedirs(local_image_dir, exist_ok=True)
                    
                    # 复制图片到输出目录
                    for img_file in image_files:
                        dst_path = os.path.join(local_image_dir, img_file.name)
                        shutil.copy2(img_file, dst_path)
                        logger.debug(f"复制图片: {img_file} -> {dst_path}")
            
            # 保存Markdown文件
            md_path = os.path.join(local_md_dir, f"{file_name}.md")
            async with aiofiles.open(md_path, 'w', encoding='utf-8') as f:
                await f.write(final_content)
            logger.info(f"Markdown文件已保存: {md_path}")
            
            # 生成输出文件路径（在output_dir根目录下也保存一份）
            output_md_path = os.path.join(output_dir, f"{file_name}.md")
            async with aiofiles.open(output_md_path, 'w', encoding='utf-8') as f:
                await f.write(final_content)
            
            logger.info(f"转换完成: {output_md_path}")
            
            # JSON转换（如果需要）
            json_data = None
            json_path = None
            if output_json:
                try:
                    logger.info("开始转换为JSON格式...")
                    # 复用v1的json解析逻辑
                    # 注意：v2版本不涉及MinerU和PaddleOCR的具体调用，只进行JSON解析
                    # first_page_image设为None，因为v2版本不处理PDF图片
                    from ..parser.json_converter import parse_markdown_to_json
                    # 构建完整的输出目录路径，包含文件名的子目录
                    json_output_dir = os.path.join(output_dir, file_name) if file_name else output_dir
                    json_data = parse_markdown_to_json(
                        original_content,
                        first_page_image=None,
                        output_dir=json_output_dir,
                        forced_document_type=forced_document_type,
                        enable_paddleocr_fallback=True,
                        input_file=input_file,
                    )
                    json_path = os.path.join(output_dir, f"{file_name}.json")
                    async with aiofiles.open(json_path, 'w', encoding='utf-8') as f:
                        await f.write(json.dumps(json_data, ensure_ascii=False, indent=2))
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
            
        finally:
            # 清理临时目录
            try:
                shutil.rmtree(temp_dir)
                logger.debug(f"已清理临时目录: {temp_dir}")
            except Exception as e:
                logger.warning(f"清理临时目录失败: {e}")
    
    except Exception as e:
        logger.exception(f"转换过程出错: {e}")
        return None

