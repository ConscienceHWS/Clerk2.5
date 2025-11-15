# MinerU 部署指南

根据实际部署经验总结的 MinerU 部署步骤。

## 环境要求

- Python 3.11
- GPU 支持（NVIDIA）
- 足够的磁盘空间（模型文件较大）

## 部署步骤

### 1. 创建虚拟环境

```bash
cd /mnt/win_d/Clerk2.5  # 或您的项目目录

# 创建虚拟环境
python3.11 -m venv venv

# 激活虚拟环境
source venv/bin/activate
```

### 2. 安装依赖

#### 安装 mineru-vl-utils（推荐）

```bash
# 设置临时目录和缓存目录（避免占用系统盘）
export TMPDIR=/mnt/win_d/Clerk2.5/tmp
export PIP_CACHE_DIR=/mnt/win_d/Clerk2.5/tmp/pip_cache
mkdir -p $TMPDIR $PIP_CACHE_DIR

# 安装 mineru-vl-utils（包含 vllm 支持）
pip install "mineru-vl-utils[vllm]"

# 如果需要完整功能
pip install "mineru-vl-utils[all]"
```

#### 安装MinerU库


```bash
# 安装或升级到 dev 分支
pip install -U git+https://gitee.com/myhloli/MinerU.git@dev

# 验证安装
python -c "import mineru; print(getattr(mineru, '__version__', 'installed'))"
which mineru-api
mineru-api --help
```


### 3. 下载模型

#### 使用 modelscope 下载（推荐）

```bash
# 安装 modelscope（如果还没安装）
pip install modelscope

# 下载 MinerU 2.5 模型（新版）
modelscope download --model OpenDataLab/MinerU2.5-2509-1.2B

# 模型会下载到默认位置：
# ~/.cache/modelscope/hub/models/OpenDataLab/MinerU2.5-2509-1.2B/
```

### 4. 配置环境变量

创建配置文件或设置环境变量：

```bash
# 模型源配置（如果使用本地模型）
export MINERU_MODEL_SOURCE=local 
```

### 5. 启动服务

#### 方式一：命令行启动

```bash
# 启动 Gradio 界面
mineru-gradio --server-name 0.0.0.0 --server-port 7860

# 启动 API 服务
mineru-api --host 0.0.0.0 --port 8000

# 带更多参数的启动
mineru-gradio \
  --enable-vllm-engine true \
  --server-name 0.0.0.0 \
  --enable-api true \
  --max-convert-pages 20 \
  --latex-delimiters-type b \
  --gpu-memory-utilization 0.9
```

#### 方式二：使用 systemd 服务（生产环境）

创建服务文件 `/etc/systemd/system/mineru-api.service`:

```ini
[Unit]
Description=MinerU API Service
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root

# 工作目录
WorkingDirectory=/mnt/win_d/Clerk2.5

# 环境变量
Environment="MINERU_MODEL_SOURCE=local"
Environment="HF_ENDPOINT=https://hf-mirror.com"
Environment="TMPDIR=/mnt/win_d/Clerk2.5/tmp"

# 启动命令（如果使用 mineru-vl-utils 安装）
ExecStart=/mnt/win_d/Clerk2.5/venv/bin/mineru-api --host 0.0.0.0 --port 8000

# 重启策略
Restart=always
RestartSec=10
StartLimitInterval=300
StartLimitBurst=5

# 日志配置
StandardOutput=journal
StandardError=journal
SyslogIdentifier=mineru-api

[Install]
WantedBy=multi-user.target
```

启动和管理服务：

```bash
# 重新加载 systemd 配置
sudo systemctl daemon-reload

# 启动服务
sudo systemctl start mineru-api

# 设置开机自启
sudo systemctl enable mineru-api

# 查看服务状态
sudo systemctl status mineru-api

# 查看日志
sudo journalctl -u mineru-api -f

# 重启服务
sudo systemctl restart mineru-api
```

---

## PDF转换工具 v2 API 部署

v2 API 是调用 MinerU API 的封装服务，提供简化的接口和文档类型解析功能。

### 前置要求

- ✅ MinerU API 服务已部署并运行（默认端口 8000）
- ✅ Python 3.11 虚拟环境已创建
- ✅ 项目代码已克隆到 `/mnt/win_d/Clerk2.5`

### 1. 安装 v2 API 依赖

在已激活的虚拟环境中安装依赖：

```bash
cd /mnt/win_d/Clerk2.5
source venv/bin/activate

# 安装 FastAPI 和相关依赖
pip install fastapi uvicorn python-multipart aiohttp aiofiles

# 安装其他依赖（如果项目有 requirements 文件）
# pip install -r requirements.txt
```

### 2. 配置环境变量

v2 API 需要配置外部 MinerU API 地址：

```bash
# 外部 MinerU API 地址（根据实际情况修改）
export API_URL=http://192.168.2.3:8000

# v2 API 服务配置
export API_HOST=0.0.0.0
export API_PORT=4214

# 日志配置
export PDF_CONVERTER_LOG_DIR=/mnt/win_d/Clerk2.5/logs
export LOG_LEVEL=INFO

# 其他配置（可选）
export BACKEND=vlm-vllm-async-engine
export PARSE_METHOD=auto
export LANGUAGE=ch
```

### 3. 启动 v2 API 服务

#### 方式一：命令行启动（开发/测试）

```bash
# 基本启动
python pdf_converter_v2/api_server.py

# 指定端口和主机
python pdf_converter_v2/api_server.py --host 0.0.0.0 --port 4214

# 开发模式（自动重载）
python pdf_converter_v2/api_server.py --reload --log-level debug

# 生产模式（多进程）
python pdf_converter_v2/api_server.py --workers 4 --log-level info

# 查看帮助
python pdf_converter_v2/api_server.py --help
```

#### 方式二：使用 systemd 服务（生产环境）

创建服务文件 `/etc/systemd/system/pdf-converter-v2.service`:

```ini
[Unit]
Description=PDF Converter API Service v2
Documentation=https://github.com/your-repo/pdf-converter
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root

# 工作目录
WorkingDirectory=/mnt/win_d/Clerk2.5

# Python 路径
Environment="PYTHONPATH=/mnt/win_d/Clerk2.5"

# API 服务配置
Environment="API_HOST=0.0.0.0"
Environment="API_PORT=4214"

# 日志配置
Environment="PDF_CONVERTER_LOG_DIR=/mnt/win_d/Clerk2.5/logs"
Environment="LOG_LEVEL=INFO"

# 外部API配置（v2版本使用外部MinerU API）
Environment="API_URL=http://192.168.2.3:8000"
Environment="BACKEND=vlm-vllm-async-engine"
Environment="PARSE_METHOD=auto"
Environment="LANGUAGE=ch"

# 启动命令（使用虚拟环境中的 Python）
ExecStart=/mnt/win_d/Clerk2.5/venv/bin/python /mnt/win_d/Clerk2.5/pdf_converter_v2/api_server.py --host 0.0.0.0 --port 4214 --log-level info

# 重启策略
Restart=always
RestartSec=10
StartLimitInterval=300
StartLimitBurst=5

# 日志配置
StandardOutput=journal
StandardError=journal
SyslogIdentifier=pdf-converter-v2

[Install]
WantedBy=multi-user.target
```

启动和管理服务：

```bash
# 复制服务文件
sudo cp pdf-converter-v2.service /etc/systemd/system/

# 重新加载 systemd 配置
sudo systemctl daemon-reload

# 启动服务
sudo systemctl start pdf-converter-v2

# 设置开机自启
sudo systemctl enable pdf-converter-v2

# 查看服务状态
sudo systemctl status pdf-converter-v2

# 查看日志
sudo journalctl -u pdf-converter-v2 -f

# 重启服务
sudo systemctl restart pdf-converter-v2
```

### 4. 验证部署

#### 测试 API 服务

```bash
# 健康检查
curl http://localhost:4214/health

# 查看 API 文档
# 浏览器访问: http://localhost:4214/docs

# 测试文件上传
curl -X POST "http://localhost:4214/convert" \
  -F "file=@example.pdf" \
  -F "type=noiseRec"
```

#### 测试完整流程

```bash
# 1. 上传文件，获取 task_id
curl -X POST "http://localhost:4214/convert" \
  -F "file=@test.pdf" \
  -F "type=noiseRec"

# 2. 查询任务状态
curl "http://localhost:4214/task/{task_id}"

# 3. 获取 JSON 结果
curl "http://localhost:4214/task/{task_id}/json"
```

### 5. 服务架构

```
┌─────────────────┐
│  客户端请求      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐      HTTP请求      ┌─────────────────┐
│  v2 API 服务    │ ────────────────>  │  MinerU API     │
│  (端口 4214)    │                    │  (端口 8000)    │
│                 │ <────────────────  │                 │
│ - 文件上传       │     返回 ZIP       │ - PDF转换       │
│ - 类型解析       │                    │ - Markdown生成  │
│ - JSON转换       │                    │                 │
└─────────────────┘                    └─────────────────┘
```

### 6. 端口说明

- **MinerU API**: 端口 `8000`（必需，v2 API 依赖）
- **v2 API**: 端口 `4214`（可通过参数修改）
- **v1 API**: 端口 `4213`（可选，与 v2 可共存）

### 7. 常见问题

#### v2 API 无法连接到 MinerU API

**问题**：v2 API 启动失败，提示无法连接 MinerU API

**解决方案**：
```bash
# 1. 检查 MinerU API 是否运行
curl http://192.168.2.3:8000/health

# 2. 检查环境变量配置
echo $API_URL

# 3. 修改 service 文件中的 API_URL
sudo vim /etc/systemd/system/pdf-converter-v2.service
sudo systemctl daemon-reload
sudo systemctl restart pdf-converter-v2
```

#### 端口冲突

**问题**：端口 4214 已被占用

**解决方案**：
```bash
# 查看占用端口的进程
lsof -i:4214

# 杀死占用进程
kill -9 <PID>

# 或使用其他端口启动
python pdf_converter_v2/api_server.py --port 4215
```

---

## 完整部署流程总结

### 1. 部署 MinerU API（基础服务）

```bash
# 1. 创建虚拟环境
cd /mnt/win_d/Clerk2.5
python3.11 -m venv venv
source venv/bin/activate

# 2. 安装 MinerU
pip install "mineru-vl-utils[vllm]"
pip install -U git+https://gitee.com/myhloli/MinerU.git@dev

# 3. 下载模型
pip install modelscope
modelscope download --model OpenDataLab/MinerU2.5-2509-1.2B

# 4. 启动 MinerU API（或配置 systemd 服务）
export MINERU_MODEL_SOURCE=local
mineru-api --host 0.0.0.0 --port 8000
```

### 2. 部署 v2 API（封装服务）

```bash
# 1. 安装 v2 API 依赖（在同一个虚拟环境）
pip install fastapi uvicorn python-multipart aiohttp aiofiles

# 2. 配置环境变量
export API_URL=http://192.168.2.3:8000
export API_PORT=4214

# 3. 启动 v2 API（或配置 systemd 服务）
python pdf_converter_v2/api_server.py --host 0.0.0.0 --port 4214
```

### 3. 验证两个服务

```bash
# 验证 MinerU API
curl http://localhost:8000/health

# 验证 v2 API
curl http://localhost:4214/health

# 查看 v2 API 文档
浏览器访问: http://localhost:4214/docs
```

## 参考

- MinerU GitHub: https://github.com/opendatalab/MinerU
- ModelScope: https://www.modelscope.cn/models/OpenDataLab/MinerU2.5-2509-1.2B
- v2 API 文档: 项目根目录 `pdf_converter_v2/README.md`
- 更新说明: 项目根目录 `CHANGELOG.md`

1  vim .ssh/authorized_keys 
    1  vim .ssh/authorized_keys 
    2  ll
    3  exit
    4  ls
    5  cd auto_install/
    6  ls
    7  cd 
    8  ls
    9  nvidia-smi 
   10  ls
   11  df -h
   12  ls
   13  mkdir workspace
   14  ls
   15  cd workspace/
   16  ls
   17  mkdir Clerk2.5
   18  ls
   19  cd Clerk2.5/
   20  ls
   21  pwd
   22  cd ..
   23  ls
   24  git
   25  git clone git@github.com:ConscienceHWS/Clerk2.5.git
   26  git clone https://github.com/ConscienceHWS/Clerk2.5.git
   27  ls
   28  cd Clerk2.5/
   29  ls
   30  python3.12 -m venv venv
   31  ls -a
   32  source venv/bin/activate
   33  which python
   34  which pip
   35  pip install modelscope
   36  modelscope download --model OpenDataLab/MinerU2.5-2509-1.2B
   37  clear
   38  pip install "mineru-vl-utils[all]"
   39  pip install -U git+https://gitee.com/myhloli/MinerU.git@dev
   40  python -c "import mineru; print(getattr(mineru, '__version__', 'installed'))"
   41  which mineru-api
   42  mineru-api --help
   43  pip install uvicorn
   44  mineru-api --help
   45  pip install fastapi
   46  mineru-api --help
   47  pip install python-multipart
   48  mineru-api --help
   49  export MINERU_MODEL_SOURCE=local 
   50  mineru-gradio --server-name 0.0.0.0 --server-port 7860
   51  pip install gradio
   52  mineru-gradio --server-name 0.0.0.0 --server-port 7860
   53  pip install gradio_pdf
   54  mineru-gradio --server-name 0.0.0.0 --server-port 7860
   55  mineru-api --host 0.0.0.0 --port 8000
   56  vim /etc/systemd/system/mineru-api.service
   57  sudo systemctl daemon-reload
   58  sudo systemctl start mineru-api && sudo journalctl -u mineru-api -f
   59  mkdir -p /root/workspace/Clerk2.5/tmp
   60  ls /root/workspace/Clerk2.5/tmp
   61  sudo systemctl restart mineru-api
   62  ls
   63  pip install fastapi uvicorn python-multipart aiohttp aiofiles
   64  vim /etc/systemd/system/pdf-converter.service
   65  mkdir -p /root/workspace/Clerk2.5/logs
   66  sudo systemctl daemon-reload
   67  sudo systemctl start pdf-converter-v2 && sudo journalctl -u pdf-converter-v2 -f
   68  sudo systemctl start pdf-converter && sudo journalctl -u pdf-converter -f
   69  history 
   70  sudo journalctl -u pdf-converter -f
   71  pip install vllm
   72  sudo journalctl -u pdf-converter -f
   73  pip list
   74  pip uninstall mineru -y
   75  pip install mineru==2.6.3
   76  sudo journalctl -u pdf-converter -f
   77  history 