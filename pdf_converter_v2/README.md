# PDF Converter v2

PDF转换工具 v2版本 - 使用新的API接口进行PDF转换

## 主要特性

v2版本通过调用新的API接口（`http://192.168.2.3:8000/file_parse`）进行PDF转换，API返回zip文件，然后从zip中提取md文件进行原有的json解析逻辑。

## 主要改进

1. **性能优化**: 使用新的API接口，转换速度更快
2. **统一接口**: 通过统一的API接口处理PDF转换
3. **保持兼容**: 复用v1的json解析逻辑，保持输出格式一致

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

v2版本调用的API接口：

- **URL**: `http://192.168.2.3:8000/file_parse`
- **方法**: POST
- **Content-Type**: multipart/form-data
- **返回格式**: zip文件

### 主要参数

- `files`: PDF文件（multipart/form-data）
- `return_md`: 返回markdown格式
- `response_format_zip`: 返回zip格式
- `formula_enable`: 启用公式识别
- `table_enable`: 启用表格识别
- `backend`: 后端引擎（默认: vlm-vllm-async-engine）

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

## 注意事项

1. 确保API服务器（`http://192.168.2.3:8000`）正常运行
2. v2版本需要网络连接以访问API
3. 输出的JSON格式与v1版本保持一致

