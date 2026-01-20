# Copyright (c) Opendatalab. All rights reserved.

"""
MinerU 服务管理模块

负责：
1. 自动启动/停止 mineru-api.service 以释放 GPU 显存
2. 检测 OCR 任务状态
3. 定时检查空闲并停止服务
"""

import asyncio
import os
import socket
import subprocess
import time
import threading
from typing import Optional
from datetime import datetime

from .logging_config import get_logger

logger = get_logger("pdf_converter_v2.mineru_manager")

# 服务名称
MINERU_SERVICE_NAME = "mineru-api.service"

# MinerU API 地址和端口（用于健康检查）
MINERU_API_HOST = os.getenv("MINERU_API_HOST", "192.168.2.3")
MINERU_API_PORT = int(os.getenv("MINERU_API_PORT", "8000"))

# 空闲超时时间（秒），超过此时间无任务则停止服务
IDLE_TIMEOUT_SECONDS = int(os.getenv("MINERU_IDLE_TIMEOUT", "60"))  # 默认 1 分钟

# 检查间隔（秒）
CHECK_INTERVAL_SECONDS = int(os.getenv("MINERU_CHECK_INTERVAL", "60"))  # 默认 1 分钟

# 服务启动等待超时（秒）
SERVICE_START_TIMEOUT = int(os.getenv("MINERU_START_TIMEOUT", "120"))  # 默认 2 分钟


class MinerUServiceManager:
    """MinerU 服务管理器（单例模式）"""
    
    _instance: Optional["MinerUServiceManager"] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> "MinerUServiceManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        # 当前活跃的 OCR 任务计数
        self._active_tasks = 0
        self._tasks_lock = threading.Lock()
        
        # 最后一次任务完成时间（或管理器启动时间，用于计算空闲）
        self._last_task_end_time: Optional[datetime] = None
        
        # 管理器初始化时间（用于首次空闲检测）
        self._init_time: datetime = datetime.now()
        
        # 定时检查线程
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitor = threading.Event()
        
        # 服务启动锁，避免并发启动
        self._start_lock = asyncio.Lock()
        
        logger.info(f"[MinerU管理器] 初始化完成，空闲超时: {IDLE_TIMEOUT_SECONDS}s, 检查间隔: {CHECK_INTERVAL_SECONDS}s")
    
    def _run_systemctl(self, action: str) -> tuple[bool, str]:
        """
        执行 systemctl 命令
        
        Args:
            action: start, stop, status, is-active
        
        Returns:
            (success, output)
        """
        cmd = ["systemctl", action, MINERU_SERVICE_NAME]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            output = result.stdout.strip() or result.stderr.strip()
            success = result.returncode == 0
            return success, output
        except subprocess.TimeoutExpired:
            logger.error(f"[MinerU管理器] systemctl {action} 超时")
            return False, "timeout"
        except Exception as e:
            logger.error(f"[MinerU管理器] systemctl {action} 失败: {e}")
            return False, str(e)
    
    def is_service_active(self) -> bool:
        """检查服务是否正在运行（systemd 状态）"""
        success, output = self._run_systemctl("is-active")
        is_active = success and output == "active"
        logger.debug(f"[MinerU管理器] 服务状态: {output} (active={is_active})")
        return is_active
    
    def is_port_available(self, host: str = None, port: int = None, timeout: float = 2.0) -> bool:
        """
        检查 MinerU API 端口是否可连接
        
        Args:
            host: 主机地址，默认使用 MINERU_API_HOST
            port: 端口号，默认使用 MINERU_API_PORT
            timeout: 连接超时时间（秒）
        
        Returns:
            True 如果端口可连接
        """
        host = host or MINERU_API_HOST
        port = port or MINERU_API_PORT
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            is_available = result == 0
            logger.debug(f"[MinerU管理器] 端口检测 {host}:{port} -> {'可用' if is_available else '不可用'}")
            return is_available
        except Exception as e:
            logger.debug(f"[MinerU管理器] 端口检测失败: {e}")
            return False
    
    def is_service_ready(self) -> bool:
        """
        检查服务是否完全就绪（systemd active 且端口可连接）
        """
        return self.is_service_active() and self.is_port_available()
    
    def start_service_sync(self) -> bool:
        """同步启动服务，等待端口可用"""
        # 如果服务已完全就绪，无需启动
        if self.is_service_ready():
            logger.debug("[MinerU管理器] 服务已就绪，无需启动")
            return True
        
        # 如果 systemd 状态是 active 但端口不可用，等待端口
        if self.is_service_active():
            logger.info("[MinerU管理器] 服务已启动，等待端口就绪...")
        else:
            logger.info("[MinerU管理器] 正在启动 MinerU 服务...")
            success, output = self._run_systemctl("start")
            if not success:
                logger.error(f"[MinerU管理器] 服务启动失败: {output}")
                return False
        
        # 等待服务完全启动（systemd active 且端口可连接）
        start_time = time.time()
        check_interval = 2  # 每 2 秒检查一次
        
        while time.time() - start_time < SERVICE_START_TIMEOUT:
            if self.is_service_ready():
                elapsed = time.time() - start_time
                logger.info(f"[MinerU管理器] 服务启动成功，端口已就绪（等待 {elapsed:.1f}s）")
                return True
            
            # 检查服务是否意外停止
            if not self.is_service_active():
                logger.error("[MinerU管理器] 服务启动后意外停止")
                return False
            
            elapsed = time.time() - start_time
            logger.debug(f"[MinerU管理器] 等待端口就绪... ({elapsed:.0f}s/{SERVICE_START_TIMEOUT}s)")
            time.sleep(check_interval)
        
        logger.warning(f"[MinerU管理器] 服务启动超时（{SERVICE_START_TIMEOUT}s），端口仍不可用")
        return False
    
    async def start_service(self) -> bool:
        """异步启动服务"""
        async with self._start_lock:
            # 在线程池中执行同步操作
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.start_service_sync)
    
    def stop_service_sync(self) -> bool:
        """同步停止服务"""
        if not self.is_service_active():
            logger.debug("[MinerU管理器] 服务未运行，无需停止")
            return True
        
        # 检查是否有活跃任务
        with self._tasks_lock:
            if self._active_tasks > 0:
                logger.warning(f"[MinerU管理器] 当前有 {self._active_tasks} 个活跃任务，不能停止服务")
                return False
        
        logger.info("[MinerU管理器] 正在停止 MinerU 服务以释放 GPU 显存...")
        success, output = self._run_systemctl("stop")
        
        if success:
            logger.info("[MinerU管理器] 服务已停止，GPU 显存已释放")
            return True
        else:
            logger.error(f"[MinerU管理器] 服务停止失败: {output}")
            return False
    
    async def stop_service(self) -> bool:
        """异步停止服务"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.stop_service_sync)
    
    def task_started(self):
        """标记一个 OCR 任务开始"""
        with self._tasks_lock:
            self._active_tasks += 1
            logger.info(f"[MinerU管理器] 任务开始，当前活跃任务数: {self._active_tasks}")
    
    def task_ended(self):
        """标记一个 OCR 任务结束"""
        with self._tasks_lock:
            self._active_tasks = max(0, self._active_tasks - 1)
            self._last_task_end_time = datetime.now()
            logger.info(f"[MinerU管理器] 任务结束，当前活跃任务数: {self._active_tasks}")
    
    def get_active_task_count(self) -> int:
        """获取当前活跃任务数"""
        with self._tasks_lock:
            return self._active_tasks
    
    def _monitor_loop(self):
        """定时监控循环（在单独线程中运行）"""
        logger.info("[MinerU管理器] 定时监控线程已启动")
        
        while not self._stop_monitor.is_set():
            try:
                # 检查是否需要停止服务
                self._check_and_stop_if_idle()
            except Exception as e:
                logger.exception(f"[MinerU管理器] 监控检查异常: {e}")
            
            # 等待下一次检查
            self._stop_monitor.wait(CHECK_INTERVAL_SECONDS)
        
        logger.info("[MinerU管理器] 定时监控线程已停止")
    
    def _check_and_stop_if_idle(self):
        """检查是否空闲，如果空闲则停止服务"""
        with self._tasks_lock:
            active_tasks = self._active_tasks
            last_end_time = self._last_task_end_time
        
        # 如果有活跃任务，不停止
        if active_tasks > 0:
            logger.debug(f"[MinerU管理器] 当前有 {active_tasks} 个活跃任务，保持服务运行")
            return
        
        # 如果服务未运行，无需处理
        if not self.is_service_active():
            logger.debug("[MinerU管理器] 服务未运行，跳过检查")
            return
        
        # 检查空闲时间
        # 如果从未有任务完成，使用管理器初始化时间作为参考
        reference_time = last_end_time if last_end_time is not None else self._init_time
        idle_seconds = (datetime.now() - reference_time).total_seconds()
        
        if idle_seconds >= IDLE_TIMEOUT_SECONDS:
            if last_end_time is None:
                logger.info(f"[MinerU管理器] 服务启动后无任务，已空闲 {idle_seconds:.0f}s，超过阈值 {IDLE_TIMEOUT_SECONDS}s，准备停止")
            else:
                logger.info(f"[MinerU管理器] 服务已空闲 {idle_seconds:.0f}s，超过阈值 {IDLE_TIMEOUT_SECONDS}s，准备停止")
            self.stop_service_sync()
        else:
            remaining = IDLE_TIMEOUT_SECONDS - idle_seconds
            logger.debug(f"[MinerU管理器] 服务空闲 {idle_seconds:.0f}s，还需 {remaining:.0f}s 达到停止阈值")
    
    def start_monitor(self):
        """启动定时监控线程"""
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            logger.debug("[MinerU管理器] 监控线程已在运行")
            return
        
        self._stop_monitor.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name="MinerUMonitor",
            daemon=True
        )
        self._monitor_thread.start()
        logger.info("[MinerU管理器] 定时监控已启动")
    
    def stop_monitor(self):
        """停止定时监控线程"""
        if self._monitor_thread is None:
            return
        
        self._stop_monitor.set()
        self._monitor_thread.join(timeout=5)
        self._monitor_thread = None
        logger.info("[MinerU管理器] 定时监控已停止")
    
    def get_status(self) -> dict:
        """获取管理器状态"""
        with self._tasks_lock:
            active_tasks = self._active_tasks
            last_end_time = self._last_task_end_time
        
        idle_seconds = None
        if last_end_time is not None:
            idle_seconds = (datetime.now() - last_end_time).total_seconds()
        
        service_active = self.is_service_active()
        port_available = self.is_port_available() if service_active else False
        
        return {
            "service_name": MINERU_SERVICE_NAME,
            "service_active": service_active,
            "port_available": port_available,
            "service_ready": service_active and port_available,
            "api_endpoint": f"http://{MINERU_API_HOST}:{MINERU_API_PORT}",
            "active_tasks": active_tasks,
            "last_task_end_time": last_end_time.isoformat() if last_end_time else None,
            "idle_seconds": idle_seconds,
            "idle_timeout_seconds": IDLE_TIMEOUT_SECONDS,
            "check_interval_seconds": CHECK_INTERVAL_SECONDS,
            "service_start_timeout": SERVICE_START_TIMEOUT,
            "monitor_running": self._monitor_thread is not None and self._monitor_thread.is_alive()
        }


# 全局单例
_manager: Optional[MinerUServiceManager] = None


def get_mineru_manager() -> MinerUServiceManager:
    """获取 MinerU 服务管理器单例"""
    global _manager
    if _manager is None:
        _manager = MinerUServiceManager()
    return _manager


async def ensure_mineru_service_running() -> bool:
    """
    确保 MinerU 服务正在运行
    
    在调用 OCR API 前调用此函数
    """
    manager = get_mineru_manager()
    return await manager.start_service()
