"""
GPU监控工具模块
用于获取和计算GPU使用情况
"""

import subprocess
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def get_gpu_info() -> Optional[Dict[str, Any]]:
    """
    获取GPU信息（使用nvidia-smi）
    
    Returns:
        GPU信息字典，包含：
        - gpu_index: GPU索引
        - gpu_memory_used: 已使用显存（字节）
        - gpu_utilization: GPU利用率（%）
        - gpu_memory_total: 总显存（字节）
        - gpu_name: GPU名称
        如果获取失败返回None
    """
    try:
        # 执行nvidia-smi命令
        cmd = [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits"
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )
        
        if result.returncode != 0:
            logger.debug(f"nvidia-smi命令执行失败: {result.stderr}")
            return None
        
        # 解析输出（取第一个GPU）
        lines = result.stdout.strip().split('\n')
        if not lines or not lines[0]:
            logger.debug("nvidia-smi未返回GPU信息")
            return None
        
        parts = [p.strip() for p in lines[0].split(',')]
        if len(parts) < 5:
            logger.debug(f"GPU信息格式不正确: {lines[0]}")
            return None
        
        gpu_index = int(parts[0])
        gpu_name = parts[1]
        memory_total_mb = int(parts[2])
        memory_used_mb = int(parts[3])
        utilization = float(parts[4])
        
        return {
            "gpu_index": gpu_index,
            "gpu_name": gpu_name,
            "gpu_memory_total": memory_total_mb * 1024 * 1024,  # 转换为字节
            "gpu_memory_used": memory_used_mb * 1024 * 1024,  # 转换为字节
            "gpu_utilization": utilization
        }
    except Exception as e:
        logger.debug(f"获取GPU信息失败: {e}")
        return None


def get_gpu_info_delta(start_gpu_info: Optional[Dict], end_gpu_info: Optional[Dict]) -> Optional[Dict[str, Any]]:
    """
    计算GPU使用增量（OCR任务期间的GPU使用）
    
    Args:
        start_gpu_info: 开始时的GPU信息
        end_gpu_info: 结束时的GPU信息
    
    Returns:
        GPU增量信息，包含：
        - gpu_index: GPU索引
        - gpu_memory_used: 显存增量（字节），OCR任务期间增加的显存使用
        - gpu_utilization: GPU利用率（%），结束时的利用率
        - gpu_memory_total: 总显存（字节）
        - gpu_name: GPU名称
        如果无法计算返回None
    """
    if not end_gpu_info:
        return None
    
    result = {
        "gpu_index": end_gpu_info.get("gpu_index"),
        "gpu_name": end_gpu_info.get("gpu_name"),
        "gpu_memory_total": end_gpu_info.get("gpu_memory_total"),
        "gpu_utilization": end_gpu_info.get("gpu_utilization")
    }
    
    # 计算显存增量
    if start_gpu_info and end_gpu_info:
        start_memory = start_gpu_info.get("gpu_memory_used", 0)
        end_memory = end_gpu_info.get("gpu_memory_used", 0)
        memory_delta = max(0, end_memory - start_memory)  # 确保非负
        result["gpu_memory_used"] = memory_delta
    else:
        # 如果没有开始信息，使用结束时的绝对显存（不推荐，但作为后备）
        # 注意：这种情况下无法准确计算增量，但至少能知道GPU使用情况
        result["gpu_memory_used"] = end_gpu_info.get("gpu_memory_used", 0)
    
    return result

