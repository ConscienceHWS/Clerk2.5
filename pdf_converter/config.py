# Copyright (c) Opendatalab. All rights reserved.

"""
配置文件
"""

import os

# OCR工具路径配置
OCR_PYTHON_PATH = os.getenv("OCR_PYTHON_PATH", "/mnt/win_d/PaddleVL/venv/bin/python")
OCR_SCRIPT_PATH = os.getenv("OCR_SCRIPT_PATH", "/mnt/win_d/PaddleVL/paddleocr_tool.py")
OCR_BASE_DIR = os.getenv("OCR_BASE_DIR", "/mnt/win_d/PaddleVL")

# 默认模型配置
DEFAULT_MODEL_NAME = "OpenDataLab/MinerU2.5-2509-1.2B"
DEFAULT_GPU_MEMORY_UTILIZATION = 0.9
DEFAULT_DPI = 200
DEFAULT_MAX_PAGES = 10

# 图片分割配置（用于提高识别精度）
# 标题区域：用于识别文档类型
TITLE_CROP_TOP = 135
TITLE_CROP_BOTTOM = 1375
TITLE_CROP_LEFT = 540
TITLE_CROP_RIGHT = 540

# 表体区域：用于提取数据
BODY_CROP_TOP = 255
BODY_CROP_BOTTOM = 240
BODY_CROP_LEFT = 115
BODY_CROP_RIGHT = 115

# OCR区域配置（噪声检测表）
# 第一页OCR区域（用于填充空白字段）
OCR_REGION_1_TOP = 255
OCR_REGION_1_BOTTOM = 1155
OCR_REGION_1_LEFT = 115
OCR_REGION_1_RIGHT = 115

# 第二页OCR区域（用于补充识别声级计、校准值等）
OCR_REGION_2_TOP = 350
OCR_REGION_2_BOTTOM = 1245
OCR_REGION_2_LEFT = 115
OCR_REGION_2_RIGHT = 115

