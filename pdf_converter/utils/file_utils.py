# Copyright (c) Opendatalab. All rights reserved.

"""
文件处理工具函数
"""

import os
import re
from pathlib import Path

from mineru.cli.common import read_fn


def safe_stem(file_path):
    """安全地提取文件名（去除不安全字符）"""
    stem = Path(file_path).stem
    return re.sub(r'[^\w.]', '_', stem)


def to_pdf(file_path):
    """将文件转换为PDF格式（如果需要）"""
    if file_path is None or not os.path.exists(file_path):
        return None

    pdf_bytes = read_fn(file_path)
    unique_filename = f'{safe_stem(file_path)}.pdf'
    tmp_file_path = os.path.join(os.path.dirname(file_path), unique_filename)

    with open(tmp_file_path, 'wb') as tmp_pdf_file:
        tmp_pdf_file.write(pdf_bytes)

    return tmp_file_path

