# Copyright (c) Opendatalab. All rights reserved.

"""
设备环境识别：区分本地是 NVIDIA GPU (nvi) 还是华为昇腾 NPU (npu)。
用于在代码中按环境设置 VLLM_PLUGINS、LD_PRELOAD、PADDLE_OCR_DEVICE 等。
"""

import os
import subprocess
from typing import Literal

DeviceKind = Literal["nvi", "npu", "cpu"]

# 环境变量显式指定时优先使用（nvi / npu / cpu）
ENV_DEVICE_KIND = "PDF_CONVERTER_DEVICE_KIND"


def _nvidia_available() -> bool:
    """检测是否有可用 NVIDIA 环境（CUDA / nvidia-smi）。"""
    if os.getenv("CUDA_VISIBLE_DEVICES") is not None:
        # 若显式设为空字符串表示隐藏 GPU，不视为 nvi
        if os.getenv("CUDA_VISIBLE_DEVICES", "").strip() == "":
            return False
        return True
    try:
        r = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _npu_available() -> bool:
    """检测是否有华为昇腾 NPU 环境。"""
    if os.getenv("ASCEND_HOME"):
        return True
    if os.getenv("ASCEND_RT_VISIBLE_DEVICES") is not None:
        return True
    if os.getenv("MINERU_DEVICE_MODE", "").lower().startswith("npu"):
        return True
    try:
        r = subprocess.run(
            ["npu-smi", "info"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False


def detect_device_kind() -> DeviceKind:
    """
    识别当前运行环境为 nvi（NVIDIA GPU）、npu（华为昇腾 NPU）或 cpu。

    优先级：
    1. 环境变量 PDF_CONVERTER_DEVICE_KIND（nvi / npu / cpu）
    2. NPU 相关环境或 npu-smi 可用 -> npu
    3. NVIDIA 相关环境或 nvidia-smi 可用 -> nvi
    4. 否则 -> cpu

    Returns:
        "nvi" | "npu" | "cpu"
    """
    raw = os.getenv(ENV_DEVICE_KIND, "").strip().lower()
    if raw in ("nvi", "npu", "cpu"):
        return raw  # type: ignore[return-value]

    if _npu_available():
        return "npu"
    if _nvidia_available():
        return "nvi"
    return "cpu"


def is_nvidia() -> bool:
    """当前是否为 NVIDIA GPU 环境。"""
    return detect_device_kind() == "nvi"


def is_npu() -> bool:
    """当前是否为华为昇腾 NPU 环境。"""
    return detect_device_kind() == "npu"


def is_cpu_only() -> bool:
    """当前是否仅为 CPU 环境（无 nvi/npu）。"""
    return detect_device_kind() == "cpu"
