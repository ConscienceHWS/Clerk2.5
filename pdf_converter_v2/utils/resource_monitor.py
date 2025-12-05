"""
资源监控采集器模块
在OCR任务期间，后台线程定期采集GPU和系统负载数据
"""
import threading
import time
import subprocess
import logging
import os
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class ResourceMonitor:
    """资源监控采集器，在后台线程中定期采集GPU和系统负载数据"""
    
    def __init__(self, interval: float = 0.5):
        """
        初始化资源监控采集器
        
        Args:
            interval: 采集间隔（秒），默认0.5秒
        """
        self.interval = interval
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.samples: List[Dict[str, Any]] = []
        self.lock = threading.Lock()
    
    def start(self):
        """启动监控采集"""
        if self.monitoring:
            logger.warning("资源监控已在运行中")
            return
        
        self.monitoring = True
        self.samples.clear()
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info(f"资源监控采集器已启动，采集间隔: {self.interval}秒")
    
    def stop(self):
        """停止监控采集"""
        if not self.monitoring:
            logger.warning("资源监控未在运行")
            return
        
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)
        logger.info(f"资源监控采集器已停止，共采集 {len(self.samples)} 个样本")
    
    def _monitor_loop(self):
        """监控循环，定期采集数据"""
        while self.monitoring:
            try:
                sample = self._collect_sample()
                if sample:
                    with self.lock:
                        self.samples.append(sample)
            except Exception as e:
                logger.warning(f"采集资源数据时出错: {e}")
            
            time.sleep(self.interval)
    
    def _collect_sample(self) -> Optional[Dict[str, Any]]:
        """
        采集一次资源数据样本
        
        Returns:
            包含GPU和系统负载信息的字典，如果采集失败返回None
        """
        sample = {
            "timestamp": time.time(),
            "gpu_info": self._get_gpu_info(),
            "system_load": self._get_system_load()
        }
        return sample
    
    def _get_gpu_info(self) -> Optional[Dict[str, Any]]:
        """获取GPU信息"""
        try:
            cmd = [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.used,utilization.gpu",
                "--format=csv,noheader,nounits"
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=2,
                check=False
            )
            
            if result.returncode != 0:
                return None
            
            lines = result.stdout.strip().split('\n')
            if not lines or not lines[0]:
                return None
            
            parts = [p.strip() for p in lines[0].split(',')]
            if len(parts) < 5:
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
    
    def _get_system_load(self) -> Optional[Dict[str, float]]:
        """获取系统负载"""
        try:
            # Linux系统使用os.getloadavg()
            if hasattr(os, 'getloadavg'):
                load_avg = os.getloadavg()
                return {
                    "load_1min": load_avg[0],
                    "load_5min": load_avg[1],
                    "load_15min": load_avg[2]
                }
        except Exception as e:
            logger.debug(f"获取系统负载失败: {e}")
        return None
    
    def get_statistics(self) -> Optional[Dict[str, Any]]:
        """
        对采集的数据进行统计分析
        
        Returns:
            统计结果，包含：
            - gpu_index: GPU索引
            - gpu_name: GPU名称
            - gpu_memory_total: 总显存（字节）
            - gpu_memory_used: 期间最大显存使用量（字节），任务期间采集到的最大显存使用
            - gpu_memory_used_avg: 平均显存使用（字节）
            - gpu_memory_used_max: 最大显存使用（字节）
            - gpu_utilization_avg: 平均GPU利用率（%）
            - gpu_utilization_max: 最大GPU利用率（%）
            - system_load_avg_1min: 平均1分钟系统负载
            - system_load_max_1min: 最大1分钟系统负载
            - sample_count: 采集的样本数量
            - duration: 监控持续时间（秒）
        """
        with self.lock:
            if not self.samples:
                logger.warning("没有采集到任何数据样本")
                return None
            
            # 提取GPU信息
            gpu_samples = [s["gpu_info"] for s in self.samples if s.get("gpu_info")]
            if not gpu_samples:
                logger.warning("没有采集到GPU数据")
                return None
            
            # 提取系统负载信息
            load_samples = [s["system_load"] for s in self.samples if s.get("system_load")]
            
            # 计算GPU统计信息
            first_gpu = gpu_samples[0]
            last_gpu = gpu_samples[-1]
            
            # 计算平均值和最大值（用于统计）
            memory_values = [g.get("gpu_memory_used", 0) for g in gpu_samples]
            utilization_values = [g.get("gpu_utilization", 0) for g in gpu_samples]
            
            memory_avg = sum(memory_values) / len(memory_values) if memory_values else 0
            memory_max = max(memory_values) if memory_values else 0
            utilization_avg = sum(utilization_values) / len(utilization_values) if utilization_values else 0
            utilization_max = max(utilization_values) if utilization_values else 0
            
            # 使用期间最大显存值（不再计算增量）
            # 注意：这是采集期间的最大显存使用量，不是增量
            gpu_memory_used = int(memory_max)
            
            # 计算系统负载统计
            load_1min_values = [l.get("load_1min", 0) for l in load_samples if l]
            load_1min_avg = sum(load_1min_values) / len(load_1min_values) if load_1min_values else None
            load_1min_max = max(load_1min_values) if load_1min_values else None
            
            # 计算持续时间
            duration = self.samples[-1]["timestamp"] - self.samples[0]["timestamp"] if len(self.samples) > 1 else 0
            
            result = {
                "gpu_index": first_gpu.get("gpu_index"),
                "gpu_name": first_gpu.get("gpu_name"),
                "gpu_memory_total": first_gpu.get("gpu_memory_total"),
                "gpu_memory_used": gpu_memory_used,  # 期间最大显存使用量（不是增量）
                "gpu_memory_used_avg": int(memory_avg),
                "gpu_memory_used_max": int(memory_max),
                "gpu_utilization": utilization_avg,  # 平均利用率
                "gpu_utilization_avg": utilization_avg,
                "gpu_utilization_max": utilization_max,
                "system_load_avg_1min": load_1min_avg,
                "system_load_max_1min": load_1min_max,
                "sample_count": len(self.samples),
                "duration": duration
            }
            
            logger.info(f"资源统计计算完成 - 样本数: {len(self.samples)}, 持续时间: {duration:.2f}秒, "
                       f"最大显存使用: {gpu_memory_used / 1024 / 1024:.2f}MB (平均: {memory_avg / 1024 / 1024:.2f}MB), "
                       f"平均GPU利用率: {utilization_avg:.2f}%, 最大GPU利用率: {utilization_max:.2f}%")
            
            return result

