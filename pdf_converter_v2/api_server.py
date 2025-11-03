#!/usr/bin/env python3
# Copyright (c) Opendatalab. All rights reserved.

"""
FastAPI服务器启动脚本 v2
可以通过 python api_server.py 来启动API服务
"""

import os
import sys
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

if __name__ == '__main__':
    # 可以通过环境变量配置端口和主机
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "4214"))  # v2 使用不同的默认端口
    
    print(f"启动PDF转换工具API v2 服务...")
    print(f"访问地址: http://{host}:{port}")
    print(f"API文档: http://{host}:{port}/docs")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )

