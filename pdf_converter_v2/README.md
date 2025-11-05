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

## 依赖要求

- aiohttp: 异步HTTP客户端
- aiofiles: 异步文件操作
- pdf2image: PDF转图片
- PIL/Pillow: 图片处理
- loguru或happy-python: 日志记录

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

## 更新说明

详细更新内容请参考项目根目录的 [CHANGELOG.md](../CHANGELOG.md)

