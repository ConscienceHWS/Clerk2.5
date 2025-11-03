# Copyright (c) Opendatalab. All rights reserved.

"""
文件处理工具函数
"""

import os
import re
from pathlib import Path


def safe_stem(file_path):
    """安全地提取文件名（去除不安全字符）"""
    stem = Path(file_path).stem
    return re.sub(r'[^\w.]', '_', stem)

