# Copyright (c) Opendatalab. All rights reserved.

"""工具函数模块"""

from .device_env import (
    DeviceKind,
    detect_device_kind,
    is_nvidia,
    is_npu,
    is_cpu_only,
)

__all__ = [
    "DeviceKind",
    "detect_device_kind",
    "is_nvidia",
    "is_npu",
    "is_cpu_only",
]
