# PDF Converter v2

PDF转换工具 v2版本 - 使用新的API接口进行PDF转换

## 主要特性

v2版本通过调用新的API接口（`http://192.168.2.3:8000/file_parse`）进行PDF转换，API返回zip文件，然后从zip中提取md文件进行原有的json解析逻辑。

## 主要改进

1. **API简化**: 大幅简化API参数，只需指定文件类型即可
2. **格式支持**: 支持PDF和图片格式（PNG、JPG、JPEG、BMP、TIFF、WEBP等）
3. **智能限制**: 自动检测页数，超过20页自动拒绝处理
4. **类型指定**: 支持指定文档类型（噪声记录、电磁记录、工况信息）
5. **独立解析**: 工况信息支持单独解析返回
6. **部署优化**: 支持命令行参数和systemd服务部署
7. **性能优化**: 使用外部API接口，转换速度更快
8. **保持兼容**: 复用v1的json解析逻辑，保持输出格式一致

## 使用方法

### 命令行使用

```bash
# 基本使用
python -m pdf_converter_v2 input.pdf

# 指定输出目录
python -m pdf_converter_v2 input.pdf -o ./output

# 同时输出JSON格式
python -m pdf_converter_v2 input.pdf --output-json

# 自定义API服务器地址
python -m pdf_converter_v2 input.pdf --url http://192.168.2.3:8000

# 更多选项
python -m pdf_converter_v2 input.pdf --help
```

### Python代码使用

```python
import asyncio
from pdf_converter_v2.processor.converter import convert_to_markdown

async def main():
    result = await convert_to_markdown(
        input_file="input.pdf",
        output_dir="./output",
        output_json=True,
        url="http://192.168.2.3:8000"
    )
    print(f"Markdown文件: {result['markdown_file']}")
    if result.get('json_file'):
        print(f"JSON文件: {result['json_file']}")

asyncio.run(main())
```

## API接口说明

### FastAPI服务接口

**启动服务：**
```bash
# 使用默认配置
python pdf_converter_v2/api_server.py

# 指定端口和主机
python pdf_converter_v2/api_server.py --host 0.0.0.0 --port 4214

# 查看帮助
python pdf_converter_v2/api_server.py --help
```

**主要端点：**
- `POST /convert`: 转换文件（异步处理）
  - 参数：
    - `file` (required): PDF或图片文件
    - `type` (optional): 文档类型 (`noiseRec` | `emRec` | `opStatus`)
- `GET /task/{task_id}`: 查询任务状态
- `GET /task/{task_id}/json`: 直接获取JSON数据
- `GET /download/{task_id}/markdown`: 下载Markdown文件
- `GET /download/{task_id}/json`: 下载JSON文件
- `DELETE /task/{task_id}`: 删除任务

**示例调用：**
```bash
# 上传文件并指定类型
curl -X POST "http://localhost:4214/convert" \
  -F "file=@example.pdf" \
  -F "type=noiseRec"

# 查询任务状态
curl "http://localhost:4214/task/{task_id}"

# 获取JSON数据
curl "http://localhost:4214/task/{task_id}/json"
```

### 外部API接口

v2版本内部调用的外部API接口：

- **URL**: `http://192.168.2.3:8000/file_parse`
- **方法**: POST
- **Content-Type**: multipart/form-data
- **返回格式**: zip文件

### 文档类型说明

| 参数值 | 中文名称 | 正式全称（代码内） |
|--------|---------|------------------|
| `noiseRec` | 噪声原始记录 | `noiseMonitoringRecord` |
| `emRec` | 电磁原始记录 | `electromagneticTestRecord` |
| `opStatus` | 工况信息 | `operatingConditionInfo` |

## 文件结构

```
pdf_converter_v2/
├── __init__.py
├── __main__.py
├── main.py                 # 命令行入口
├── processor/
│   ├── __init__.py
│   └── converter.py       # 核心转换逻辑
├── parser/
│   ├── __init__.py
│   └── json_converter.py  # JSON解析（复用v1逻辑）
└── utils/
    ├── __init__.py
    ├── file_utils.py      # 文件工具函数
    └── logging_config.py # 日志配置
```

## 安装依赖

### 确定使用的Python环境

在安装依赖之前，需要确定服务使用的Python环境：

**方法1：使用检查脚本（推荐）**
```bash
cd /home/hws/workspace/GitLab/Clerk2.5/pdf_converter_v2
bash check_python_env.sh
```

**方法2：手动检查**
```bash
# 检查systemd服务使用的Python
cat /etc/systemd/system/pdf-converter-v2.service | grep ExecStart

# 检查运行中的进程
ps aux | grep pdf-converter-v2 | grep python

# 检查项目使用的Python（查看api_server.py第一行）
head -1 api_server.py

# 检查默认Python
which python3
python3 --version
```

**方法3：通过Python代码检查**
```bash
# 在Python中检查
python3 -c "import sys; print('Python路径:', sys.executable); print('Python版本:', sys.version)"
```

### 快速安装（推荐）

确定Python环境后，使用对应的pip安装：

```bash
# 如果使用 python3，使用 pip3
pip3 install -r requirements.txt

# 如果使用 python，使用 pip
pip install -r requirements.txt

# 如果不确定，使用 python -m pip（推荐）
python3 -m pip install -r requirements.txt
```

### 手动安装

**必需依赖：**
```bash
# 根据你的Python环境选择对应的pip命令
pip3 install aiohttp aiofiles Pillow
# 或
python3 -m pip install aiohttp aiofiles Pillow
```

**PDF处理库（至少安装一个）：**
```bash
# 方案1：安装 pypdfium2（推荐，文件更小）
pip3 install pypdfium2
# 或
python3 -m pip install pypdfium2

# 方案2：安装 pdf2image（备用方案，需要系统安装 poppler）
# Ubuntu/Debian: sudo apt-get install poppler-utils
# CentOS/RHEL: sudo yum install poppler-utils
# macOS: brew install poppler
pip3 install pdf2image
# 或
python3 -m pip install pdf2image
```

**如果使用API服务：**
```bash
pip3 install fastapi uvicorn[standard] pydantic typing-extensions
# 或
python3 -m pip install fastapi uvicorn[standard] pydantic typing-extensions
```

**日志库（至少安装一个）：**
```bash
pip3 install loguru
# 或
python3 -m pip install loguru
# 或使用 happy-python
pip3 install happy-python
```

### 系统依赖

如果使用 `pdf2image`，需要安装系统级的 `poppler` 工具：

- **Ubuntu/Debian:**
  ```bash
  sudo apt-get update
  sudo apt-get install poppler-utils
  ```

- **CentOS/RHEL:**
  ```bash
  sudo yum install poppler-utils
  ```

- **macOS:**
  ```bash
  brew install poppler
  ```

## 依赖要求

- **aiohttp**: 异步HTTP客户端
- **aiofiles**: 异步文件操作
- **Pillow**: 图片处理（必需）
- **pypdfium2** 或 **pdf2image**: PDF转图片（至少安装一个，推荐 pypdfium2）
- **loguru** 或 **happy-python**: 日志记录（至少安装一个）
- **fastapi, uvicorn, pydantic**: Web框架（仅在使用API服务时需要）

## 与v1版本的区别

| 特性 | v1版本 | v2版本 |
|------|--------|--------|
| PDF处理方式 | 本地MinerU处理 | API接口处理 |
| 返回格式 | 直接markdown | zip文件（包含md） |
| 性能 | 本地处理 | 服务器端处理（更快） |
| JSON解析 | 直接解析 | 复用v1逻辑 |

## 服务部署

### 使用 systemd 服务

1. **安装服务文件：**
```bash
sudo cp pdf-converter-v2.service /etc/systemd/system/
sudo systemctl daemon-reload
```

2. **修改配置：**
编辑 `/etc/systemd/system/pdf-converter-v2.service`，根据实际情况修改：
- `WorkingDirectory`: 工作目录路径
- `ExecStart`: Python路径和脚本路径
- 环境变量配置

3. **启动服务：**
```bash
sudo systemctl start pdf-converter-v2
sudo systemctl enable pdf-converter-v2  # 开机自启
sudo systemctl status pdf-converter-v2  # 查看状态
```

4. **查看日志：**
```bash
sudo journalctl -u pdf-converter-v2 -f
```

### 环境变量配置

主要环境变量：
- `API_URL`: 外部API地址（默认: http://192.168.2.3:8000）
- `API_HOST`: 服务监听地址（默认: 0.0.0.0）
- `API_PORT`: 服务监听端口（默认: 4214）
- `LOG_LEVEL`: 日志级别（默认: info）
- `PDF_CONVERTER_LOG_DIR`: 日志目录（默认: ./logs）

## 注意事项

1. **API服务器**: 确保外部API服务器（`http://192.168.2.3:8000`）正常运行
2. **网络连接**: v2版本需要网络连接以访问外部API
3. **页数限制**: 文件页数不能超过20页，超过会自动拒绝
4. **文件格式**: 支持PDF和常见图片格式（PNG、JPG、JPEG、BMP、TIFF、WEBP）
5. **输出格式**: JSON输出格式与v1版本保持一致
6. **工况信息**: 工况信息可以单独解析（`type=opStatus`），也可以包含在噪声记录中

## 容器/NPU 环境额外依赖与常见错误

在 **Docker 或 NPU 容器** 内运行 pdf_converter_v2 API 时，若出现以下错误，按下面步骤处理。

### 1. 去水印失败：`pdfinfo` 未找到（poppler）

**现象**：`PDFInfoNotInstalledError: Unable to get page count. Is poppler installed and in PATH?`

**原因**：`pdf2image` 依赖系统提供的 `pdfinfo`（poppler-utils），容器内未安装。

**解决**：在运行 **pdf_converter_v2 API** 的容器内安装 poppler：

```bash
# Debian/Ubuntu
apt-get update && apt-get install -y poppler-utils

# CentOS/RHEL
yum install -y poppler-utils
```

### 2. 附件页切割失败：缺少 `pdfplumber`

**现象**：`No module named 'pdfplumber'`

**原因**：API 进程所在 Python 环境未安装 `pdfplumber`。

**解决**：在 **pdf_converter_v2 API** 所在环境安装依赖：

```bash
pip install pdfplumber
# 或安装 NPU 环境完整依赖
pip install -r pdf_converter_v2/requirements-paddle-npu.txt
```

### 3. MinerU 报错：`operator torchvision::nms does not exist`

**现象**：调用 MinerU API（`/file_parse`）返回 500，日志中 `RuntimeError: operator torchvision::nms does not exist`。

**原因**：MinerU 使用的 `torch` 与 `torchvision` 版本不匹配（常见于 ARM/aarch64 或 NPU 自定义 PyTorch 构建）。

**解决**：在 **运行 MinerU API** 的容器/环境中，安装版本匹配的 PyTorch 与 torchvision（参见项目根目录 [MINERU_DEPLOYMENT.md](../MINERU_DEPLOYMENT.md) 中「常见问题：torchvision::nms」）。简要步骤：

- 使用同一来源、同一版本的 `torch` 和 `torchvision`（如官方 wheel 或 NPU 厂商提供的配对版本）。
- 若曾单独升级/降级过 PyTorch，需同时重装匹配的 torchvision，或先卸载两者再一起安装。

### 4. MinerU 报错：No module named 'tbe' / ACL 500001（NPU）

**现象**：调用 MinerU API 返回 500，日志中 `ModuleNotFoundError: No module named 'tbe'` 或 `SetPrecisionMode ... error code is 500001`、`GEInitialize failed`。

**原因**：启动 MinerU 前未加载华为昇腾 CANN 环境，NPU 运行时无法找到 `tbe` 等模块。

**解决**：在 **启动 MinerU API** 前加载 CANN 的 `set_env.sh`，或改用 CPU：

- **加载 CANN**：`source /usr/local/Ascend/ascend-toolkit/set_env.sh`（路径以实际安装为准），再启动 MinerU。
- **使用启动脚本**：设置 `export ASCEND_ENV=/usr/local/Ascend/ascend-toolkit/set_env.sh` 后执行 `start_mineru_in_container.sh`，脚本会自动 source。
- **临时用 CPU**：`export MINERU_DEVICE_MODE=cpu` 后再启动 MinerU，可先跑通流程（速度较慢）。

详见项目根目录 [MINERU_DEPLOYMENT.md](../MINERU_DEPLOYMENT.md) 中「常见问题：No module named 'tbe' / ACL 500001」。

### 5. MinerU 报错：Hugging Face 无法连接 / 模型下载失败

**现象**：调用 MinerU API 返回 500，日志中 `Network is unreachable`、`LocalEntryNotFoundError`、`opendatalab/PDF-Extract-Kit-1.0` 等，无法从 Hugging Face 下载模型。

**原因**：MinerU 默认从 `huggingface.co` 拉取模型，内网或无法访问外网时会失败。

**解决**：使用 **ModelScope** 作为模型来源（国内可访问）：

- **启动前设置**：`export MINERU_MODEL_SOURCE=modelscope`，再启动 MinerU。
- **使用启动脚本**：`start_mineru_in_container.sh` 已默认使用 `MINERU_MODEL_SOURCE=modelscope`；若需用 Hugging Face，可设置 `export MINERU_MODEL_SOURCE=huggingface` 后执行脚本。
- **首次使用 ModelScope**：需安装 `pip install modelscope`，模型会下载到 ModelScope 默认缓存目录。

## 更新说明

详细更新内容请参考项目根目录的 [CHANGELOG.md](../CHANGELOG.md)

