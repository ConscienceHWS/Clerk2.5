# Copyright (c) Opendatalab. All rights reserved.

"""
配置文件 v2
"""

import os

# 设备环境：nvi（NVIDIA GPU）/ npu（华为昇腾 NPU）/ cpu，用于按环境选择 VLLM_PLUGINS、PADDLE_OCR_DEVICE 等
from .utils.device_env import detect_device_kind

DEVICE_KIND = os.getenv("PDF_CONVERTER_DEVICE_KIND") or detect_device_kind()

# 默认模型配置（与 v1 保持一致）
DEFAULT_MODEL_NAME = "OpenDataLab/MinerU2.5-2509-1.2B"
DEFAULT_GPU_MEMORY_UTILIZATION = 0.9
DEFAULT_DPI = 200
DEFAULT_MAX_PAGES = 10

# v2 特有配置（外部API相关）
DEFAULT_API_URL = os.getenv("API_URL", "http://127.0.0.1:5282")
DEFAULT_BACKEND = os.getenv("BACKEND", "vlm-vllm-async-engine")
DEFAULT_PARSE_METHOD = os.getenv("PARSE_METHOD", "auto")
DEFAULT_START_PAGE_ID = int(os.getenv("START_PAGE_ID", "0"))
DEFAULT_END_PAGE_ID = int(os.getenv("END_PAGE_ID", "99999"))
DEFAULT_LANGUAGE = os.getenv("LANGUAGE", "ch")
DEFAULT_RESPONSE_FORMAT_ZIP = os.getenv("RESPONSE_FORMAT_ZIP", "true").lower() == "true"
DEFAULT_RETURN_MIDDLE_JSON = os.getenv("RETURN_MIDDLE_JSON", "false").lower() == "true"
DEFAULT_RETURN_MODEL_OUTPUT = os.getenv("RETURN_MODEL_OUTPUT", "true").lower() == "true"
DEFAULT_RETURN_MD = os.getenv("RETURN_MD", "true").lower() == "true"
DEFAULT_RETURN_IMAGES = os.getenv("RETURN_IMAGES", "false").lower() == "true"
DEFAULT_RETURN_CONTENT_LIST = os.getenv("RETURN_CONTENT_LIST", "false").lower() == "true"
DEFAULT_SERVER_URL = os.getenv("SERVER_URL", "string")

