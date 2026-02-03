# -*- coding: utf-8 -*-
"""
PDF 按页切割工具
将大 PDF 按固定页数切分为多个小 PDF，用于分段转换以降低单次请求内存。
"""

import tempfile
from pathlib import Path
from typing import List

from .logging_config import get_logger

logger = get_logger("pdf_converter_v2.utils.pdf_splitter")

try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False

PDF2_REQUIRED_MSG = "PyPDF2 未安装，无法进行 PDF 切割与页数检测。请安装: pip install PyPDF2"


def _require_pypdf2() -> None:
    if not PYPDF2_AVAILABLE:
        raise RuntimeError(PDF2_REQUIRED_MSG)


def get_pdf_page_count(pdf_path: str) -> int:
    """获取 PDF 页数。若无法读取则返回 0。未安装 PyPDF2 时抛出 RuntimeError。"""
    _require_pypdf2()
    try:
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            return len(reader.pages)
    except Exception as e:
        logger.warning(f"[PDF切割] 获取页数失败 {pdf_path}: {e}")
        return 0


def split_pdf_by_pages(
    input_pdf: str,
    output_dir: str,
    chunk_size: int = 50,
) -> List[str]:
    """
    将 PDF 按 chunk_size 页一段切分为多个临时 PDF 文件。

    :param input_pdf: 输入 PDF 路径
    :param output_dir: 存放切分后 PDF 的目录（一般为临时目录）
    :param chunk_size: 每段页数，默认 50
    :return: 切分后的 PDF 文件路径列表，按页码顺序；失败返回空列表。未安装 PyPDF2 时抛出 RuntimeError。
    """
    _require_pypdf2()

    input_path = Path(input_pdf)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    try:
        with open(input_pdf, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            total = len(reader.pages)
    except Exception as e:
        logger.error(f"[PDF切割] 读取 PDF 失败 {input_pdf}: {e}")
        return []

    if total <= 0:
        return []

    if total <= chunk_size:
        return [input_pdf]

    chunk_paths: List[str] = []
    start = 0
    idx = 0
    while start < total:
        end = min(start + chunk_size, total)
        chunk_pdf = out_path / f"chunk_{idx}_{input_path.stem}.pdf"
        try:
            writer = PyPDF2.PdfWriter()
            for i in range(start, end):
                writer.add_page(reader.pages[i])
            with open(chunk_pdf, "wb") as w:
                writer.write(w)
            chunk_paths.append(str(chunk_pdf))
            logger.info(f"[PDF切割] 段 {idx + 1}: 页 {start + 1}-{end}/{total} -> {chunk_pdf.name}")
        except Exception as e:
            logger.exception(f"[PDF切割] 写入段 {idx} 失败: {e}")
            for p in chunk_paths:
                try:
                    Path(p).unlink(missing_ok=True)
                except Exception:
                    pass
            return []
        start = end
        idx += 1

    return chunk_paths
