# PDF转换器模块化结构

## 项目结构

```
pdf_converter/
├── __init__.py              # 包初始化
├── __main__.py              # 模块入口（支持 python -m pdf_converter）
├── main.py                  # CLI主入口
├── config.py                # 配置文件
│
├── models/                   # 数据模型
│   ├── __init__.py
│   └── data_models.py       # 所有数据模型类
│
├── utils/                    # 工具函数
│   ├── __init__.py
│   ├── file_utils.py        # 文件处理工具
│   └── image_utils.py       # 图片处理工具
│
├── ocr/                      # OCR功能模块
│   ├── __init__.py
│   ├── ocr_extractor.py     # OCR文本提取
│   └── ocr_parser.py        # OCR文本解析
│
├── parser/                   # 解析器模块
│   ├── __init__.py
│   ├── document_type.py     # 文档类型检测
│   ├── table_parser.py      # 表格解析
│   ├── noise_parser.py      # 噪声检测记录解析
│   ├── electromagnetic_parser.py  # 电磁检测记录解析
│   └── json_converter.py    # JSON转换主入口
│
├── processor/                # PDF处理器模块
│   ├── __init__.py
│   ├── mineru_processor.py # MinerU PDF处理器
│   └── converter.py         # 主转换函数
│
└── [文档]
    ├── README.md            # 模块说明
    ├── SPLIT_GUIDE.md       # 拆分指南
    └── STRUCTURE.md         # 本文档
```

## 运行方式

### 方式1：使用模块入口（推荐）
```bash
python -m pdf_converter <input_file> [options]
```

### 方式2：使用命令行脚本
```bash
python pdf_convert.py <input_file> [options]
```

### 方式3：直接导入使用
```python
from pdf_converter.processor.converter import convert_to_markdown
result = await convert_to_markdown(...)
```

## 模块说明

### models - 数据模型
定义所有数据结构：
- `WeatherData` - 气象数据
- `NoiseData` - 噪声数据
- `OperationalCondition` - 工况信息
- `NoiseDetectionRecord` - 噪声检测记录
- `ElectromagneticWeatherData` - 电磁检测气象数据
- `ElectromagneticData` - 电磁数据
- `ElectromagneticDetectionRecord` - 电磁检测记录

### utils - 工具函数
- `file_utils`: 文件处理（`safe_stem`, `to_pdf`）
- `image_utils`: 图片处理（`crop_image`, `image_to_base64`, `replace_image_with_base64`）

### ocr - OCR功能
- `ocr_extractor`: 调用外部OCR脚本提取文本
- `ocr_parser`: 解析OCR提取的文本，填充空白字段

### parser - 解析器
- `document_type`: 检测文档类型
- `table_parser`: 表格解析（支持rowspan/colspan）
- `noise_parser`: 噪声检测记录解析
- `electromagnetic_parser`: 电磁检测记录解析（包含平均值计算）
- `json_converter`: JSON转换主入口

### processor - PDF处理器
- `mineru_processor`: MinerU PDF处理器类（异步处理）
- `converter`: 主转换函数，协调所有模块

### main - 主入口
- CLI参数解析
- 参数验证
- 调用转换函数

## 依赖关系

```
main.py
  └─> processor.converter
        ├─> processor.mineru_processor
        ├─> utils.file_utils
        ├─> utils.image_utils
        └─> parser.json_converter
              ├─> parser.noise_parser
              │     ├─> parser.table_parser
              │     ├─> ocr.ocr_extractor
              │     └─> ocr.ocr_parser
              ├─> parser.electromagnetic_parser
              │     └─> parser.table_parser
              └─> parser.document_type
```

## 配置说明

所有配置都在 `config.py` 中：
- OCR路径配置（可通过环境变量覆盖）
- 模型配置
- 图片裁剪配置
- OCR区域配置

## 注意事项

1. 所有相对导入使用 `from ..module import ...` 格式
2. 配置文件中的路径可以通过环境变量覆盖
3. 模块支持异步处理（使用 `asyncio`）
4. 需要确保所有依赖已安装

