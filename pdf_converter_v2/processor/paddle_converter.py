"""
PaddleOCR-based converter for v3 workflow.
"""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional, Sequence

import aiofiles

from ..utils.logging_config import get_logger
from ..utils.file_utils import safe_stem

logger = get_logger("pdf_converter_v2.processor.paddle")

PADDLE_EXECUTABLE = os.getenv("PADDLE_DOC_PARSER_CMD", "paddleocr")


async def _run_paddle_doc_parser(cmd: Sequence[str]) -> tuple[int, str, str]:
    """Execute paddleocr doc_parser command asynchronously."""
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
        logger.debug(f"[Paddle] stdout: {stdout[:5000]}")
    if stderr:
        logger.debug(f"[Paddle] stderr: {stderr[:5000]}")
    return process.returncode, stdout, stderr


async def convert_to_markdown(
    input_file: str,
    output_dir: str = "./output",
    max_pages: int = 10,  # 参数保留用于兼容，Paddle端处理完整PDF
    is_ocr: bool = False,
    formula_enable: bool = True,
    table_enable: bool = True,
    language: str = "ch",
    backend: str = "paddle",
    url: str = "",
    embed_images: bool = True,
    output_json: bool = False,
    start_page_id: int = 0,
    end_page_id: int = 99999,
    parse_method: str = "doc_parser",
    server_url: str = "",
    response_format_zip: bool = False,
    return_middle_json: bool = False,
    return_model_output: bool = False,
    return_md: bool = True,
    return_images: bool = True,
    return_content_list: bool = False,
    forced_document_type: Optional[str] = None,
) -> Optional[dict]:
    """
    Convert PDF to Markdown using PaddleOCR doc_parser.
    Parameters kept for compatibility with v2 interface; most are unused.
    """
    if not os.path.exists(input_file):
        logger.error(f"[Paddle] 输入文件不存在: {input_file}")
        return None

    file_name = f'{safe_stem(Path(input_file).stem)}_{time.strftime("%y%m%d_%H%M%S")}'
    os.makedirs(output_dir, exist_ok=True)

    temp_dir = tempfile.mkdtemp(prefix=f"pdf_converter_v3_{file_name}_")
    logger.info(f"[Paddle] 创建临时目录: {temp_dir}")
    save_path_base = os.path.join(temp_dir, Path(input_file).stem)
    os.makedirs(save_path_base, exist_ok=True)

    cmd = [
        PADDLE_EXECUTABLE,
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
            logger.error(f"[Paddle] doc_parser 执行失败，code={return_code}")
            if stderr:
                logger.error(stderr)
            return None

        md_files = sorted(Path(save_path_base).rglob("*.md"))
        if not md_files:
            logger.error(f"[Paddle] 未找到Markdown文件，save_path={save_path_base}")
            return None

        markdown_parts = []
        for md_file in md_files:
            logger.info(f"[Paddle] 读取md: {md_file}")
            async with aiofiles.open(md_file, "r", encoding="utf-8") as f:
                markdown_parts.append(await f.read())

        final_content = "\n\n".join(markdown_parts)
        logger.info(f"[Paddle] 合并后的markdown长度: {len(final_content)}")

        # 输出目录
        local_md_dir = os.path.join(output_dir, file_name, "markdown")
        os.makedirs(local_md_dir, exist_ok=True)

        md_path = os.path.join(local_md_dir, f"{file_name}.md")
        async with aiofiles.open(md_path, "w", encoding="utf-8") as f:
            await f.write(final_content)

        output_md_path = os.path.join(output_dir, f"{file_name}.md")
        async with aiofiles.open(output_md_path, "w", encoding="utf-8") as f:
            await f.write(final_content)

        # 复制图片资源
        if embed_images or return_images:
            local_image_dir = os.path.join(output_dir, file_name, "images")
            os.makedirs(local_image_dir, exist_ok=True)
            image_exts = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
            for asset in Path(save_path_base).rglob("*"):
                if asset.is_file() and asset.suffix.lower() in image_exts:
                    dst = os.path.join(local_image_dir, asset.name)
                    shutil.copy2(asset, dst)
                    logger.debug(f"[Paddle] 复制图片: {asset} -> {dst}")

        json_data = None
        json_path = None
        if output_json:
            try:
                logger.info("[Paddle] 开始转换为JSON")
                from ..parser.json_converter import parse_markdown_to_json

                json_output_dir = os.path.join(output_dir, file_name) if file_name else output_dir
                json_data = parse_markdown_to_json(
                    final_content,
                    first_page_image=None,
                    output_dir=json_output_dir,
                    forced_document_type=forced_document_type,
                    enable_paddleocr_fallback=False,
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
            logger.debug(f"[Paddle] 清理临时目录: {temp_dir}")
        except Exception as exc:
            logger.warning(f"[Paddle] 清理临时目录失败: {exc}")

