#!/usr/bin/env python3
# Copyright (c) Opendatalab. All rights reserved.

"""
FastAPI服务器启动脚本（项目根目录版本）
可以通过 python start_api.py 来启动API服务
"""

import os
import sys
from pathlib import Path

# 确保当前目录在Python路径中
current_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(current_dir))

import uvicorn
from pdf_converter.api.main import app

if __name__ == '__main__':
    # 可以通过环境变量配置端口和主机
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "4213"))
    
    print(f"启动PDF转换工具API服务...")
    print(f"访问地址: http://{host}:{port}")
    print(f"API文档: http://{host}:{port}/docs")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )

