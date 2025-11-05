#!/usr/bin/env python3
# Copyright (c) Opendatalab. All rights reserved.

"""
FastAPI服务器启动脚本 v2
可以通过 python api_server.py 来启动API服务
支持命令行参数配置
"""

import os
import sys
import argparse
from pathlib import Path

# 添加项目根目录到Python路径
current_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(current_dir))

import uvicorn

# 支持相对导入和绝对导入
try:
    from pdf_converter_v2.api.main import app
except ImportError:
    # 如果绝对导入失败，尝试相对导入
    sys.path.insert(0, str(current_dir.parent))
    from pdf_converter_v2.api.main import app


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="PDF转换工具API v2 服务器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认配置启动
  python api_server.py
  
  # 指定主机和端口
  python api_server.py --host 0.0.0.0 --port 4214
  
  # 指定日志级别
  python api_server.py --log-level debug
  
  # 使用workers模式（生产环境）
  python api_server.py --workers 4
        """
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default=os.getenv("API_HOST", "0.0.0.0"),
        help="服务器监听地址 (默认: 0.0.0.0，可通过环境变量 API_HOST 设置)"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("API_PORT", "4214")),
        help="服务器监听端口 (默认: 4214，可通过环境变量 API_PORT 设置)"
    )
    
    parser.add_argument(
        "--log-level",
        type=str,
        default=os.getenv("LOG_LEVEL", "info"),
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        help="日志级别 (默认: info，可通过环境变量 LOG_LEVEL 设置)"
    )
    
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="工作进程数 (默认: 1，生产环境建议使用多个workers)"
    )
    
    parser.add_argument(
        "--reload",
        action="store_true",
        help="启用自动重载（开发模式，不建议在生产环境使用）"
    )
    
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    
    print(f"启动PDF转换工具API v2 服务...")
    print(f"监听地址: {args.host}:{args.port}")
    print(f"访问地址: http://{args.host}:{args.port}")
    print(f"API文档: http://{args.host}:{args.port}/docs")
    print(f"日志级别: {args.log_level}")
    if args.workers:
        print(f"工作进程数: {args.workers}")
    if args.reload:
        print(f"自动重载: 已启用（开发模式）")
    print()
    
    uvicorn_config = {
        "app": app,
        "host": args.host,
        "port": args.port,
        "log_level": args.log_level,
    }
    
    if args.workers:
        uvicorn_config["workers"] = args.workers
    
    if args.reload:
        uvicorn_config["reload"] = True
    
    uvicorn.run(**uvicorn_config)

