# Copyright (c) Opendatalab. All rights reserved.
"""
日志配置模块
复用v1的日志配置逻辑
"""

import sys
from pathlib import Path

# 添加v1的路径以便导入
v1_path = Path(__file__).parent.parent.parent / "pdf_converter"
if str(v1_path) not in sys.path:
    sys.path.insert(0, str(v1_path.parent))

try:
    from pdf_converter.utils.logging_config import get_logger
except ImportError:
    # 如果无法导入，使用loguru作为后备
    from loguru import logger as _logger
    
    def get_logger(name=None):
        """获取日志记录器"""
        if name:
            return _logger.bind(name=name)
        return _logger

