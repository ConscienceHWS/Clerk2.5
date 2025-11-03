# Copyright (c) Opendatalab. All rights reserved.
"""
日志配置模块
使用 happy-python 0.9.0 配置日志系统
"""

import os
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    from happy_python import HappyLoggingConfig, HappyLogger
    HAPPY_PYTHON_AVAILABLE = True
except ImportError:
    HAPPY_PYTHON_AVAILABLE = False
    # 如果 happy-python 不可用，使用 loguru 作为后备
    from loguru import logger as _logger


def setup_logging(
    log_dir: Optional[str] = None,
    log_level: str = "INFO",
    log_to_file: bool = True,
    log_to_console: bool = True,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 10
):
    """
    配置日志系统
    
    Args:
        log_dir: 日志文件目录，如果为None则使用默认目录
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: 是否输出到文件
        log_to_console: 是否输出到控制台
        max_bytes: 日志文件最大大小（字节）
        backup_count: 保留的日志文件备份数量
    """
    if not log_dir:
        # 默认日志目录：项目根目录下的 logs 文件夹
        project_root = Path(__file__).parent.parent.parent
        log_dir = project_root / "logs"
    
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    if HAPPY_PYTHON_AVAILABLE:
        # 使用 happy-python 配置日志
        return _setup_happy_logging(
            log_dir=log_dir,
            log_level=log_level,
            log_to_file=log_to_file,
            log_to_console=log_to_console,
            max_bytes=max_bytes,
            backup_count=backup_count
        )
    else:
        # 使用 loguru 作为后备
        return _setup_loguru_logging(
            log_dir=log_dir,
            log_level=log_level,
            log_to_file=log_to_file,
            log_to_console=log_to_console,
            max_bytes=max_bytes,
            backup_count=backup_count
        )


def _setup_happy_logging(
    log_dir: Path,
    log_level: str,
    log_to_file: bool,
    log_to_console: bool,
    max_bytes: int,
    backup_count: int
):
    """使用 happy-python 配置日志"""
    # 日志文件名格式：pdf_converter_YYYY-MM-DD.log
    log_file = log_dir / "pdf_converter.log"
    error_log_file = log_dir / "pdf_converter_error.log"
    
    try:
        # 配置 happy-python 日志
        # 注意：happy-python 0.9.0 的 API 可能需要调整
        logging_config = HappyLoggingConfig(
            log_file=str(log_file),
            error_log_file=str(error_log_file),
            level=log_level,
            console=log_to_console,
            file=log_to_file,
            max_bytes=max_bytes,
            backup_count=backup_count,
            format_string="%(asctime)s [%(levelname)8s] [%(name)s:%(lineno)d] %(message)s",
            date_format="%Y-%m-%d %H:%M:%S"
        )
        
        # 创建 logger
        logger = HappyLogger("pdf_converter", logging_config)
        
        return logger
    except Exception as e:
        # 如果 happy-python 配置失败，使用 loguru 作为后备
        import warnings
        warnings.warn(f"happy-python 配置失败，使用 loguru 作为后备: {e}")
        return _setup_loguru_logging(
            log_dir, log_level, log_to_file, log_to_console, max_bytes, backup_count
        )


def _setup_loguru_logging(
    log_dir: Path,
    log_level: str,
    log_to_file: bool,
    log_to_console: bool,
    max_bytes: int,
    backup_count: int
):
    """使用 loguru 配置日志（后备方案）"""
    from loguru import logger
    
    # 移除默认的 handler
    logger.remove()
    
    # 日志格式
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    
    # 控制台输出
    if log_to_console:
        logger.add(
            lambda msg: print(msg, end=""),
            format=log_format,
            level=log_level,
            colorize=True
        )
    
    # 文件输出
    if log_to_file:
        # 普通日志文件
        log_file = log_dir / f"pdf_converter_{datetime.now().strftime('%Y-%m-%d')}.log"
        logger.add(
            str(log_file),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            level=log_level,
            rotation="10 MB",
            retention=f"{backup_count} days",
            compression="zip",
            encoding="utf-8"
        )
        
        # 错误日志文件
        error_log_file = log_dir / f"pdf_converter_error_{datetime.now().strftime('%Y-%m-%d')}.log"
        logger.add(
            str(error_log_file),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            level="ERROR",
            rotation="10 MB",
            retention=f"{backup_count} days",
            compression="zip",
            encoding="utf-8"
        )
    
    return logger


def get_logger(name: Optional[str] = None):
    """
    获取日志记录器
    
    Args:
        name: 日志记录器名称，如果为None则返回默认的logger
    """
    if HAPPY_PYTHON_AVAILABLE:
        try:
            from happy_python import HappyLogger
            if name:
                return HappyLogger(name)
            else:
                return HappyLogger("pdf_converter")
        except:
            pass
    
    # 后备方案：使用 loguru
    from loguru import logger
    if name:
        return logger.bind(name=name)
    return logger


# 默认初始化日志系统
_default_log_dir = None
_logger_initialized = False


def init_logging(log_dir: Optional[str] = None, **kwargs):
    """
    初始化日志系统（仅初始化一次）
    
    Args:
        log_dir: 日志文件目录
        **kwargs: 其他日志配置参数
    """
    global _default_log_dir, _logger_initialized
    
    if _logger_initialized:
        return
    
    if log_dir:
        _default_log_dir = log_dir
    
    setup_logging(log_dir=log_dir or _default_log_dir, **kwargs)
    _logger_initialized = True


# 如果环境变量中设置了日志目录，自动初始化
if os.getenv("PDF_CONVERTER_LOG_DIR"):
    init_logging(log_dir=os.getenv("PDF_CONVERTER_LOG_DIR"))

