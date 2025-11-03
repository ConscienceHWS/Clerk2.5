# PDF转换器模块化结构说明

## 模块结构

```
pdf_converter/
├── __init__.py              # 包初始化
├── config.py                # 配置文件（已完成）
├── main.py                   # 主入口和CLI（待创建）
│
├── models/                   # 数据模型
│   ├── __init__.py          # 导出所有模型类（已完成）
│   └── data_models.py       # 所有数据模型定义（已完成）
│
├── utils/                    # 工具函数
│   ├── __init__.py          # 导出工具函数（已完成）
│   ├── file_utils.py        # 文件处理工具（已完成）
│   └── image_utils.py       # 图片处理工具（已完成）
│
├── ocr/                      # OCR功能模块
│   ├── __init__.py          # 导出OCR函数（已完成）
│   ├── ocr_extractor.py     # OCR文本提取（已完成）
│   └── ocr_parser.py        # OCR文本解析（已完成）
│
├── parser/                   # 解析器模块（待创建）
│   ├── __init__.py
│   ├── document_type.py     # 文档类型检测
│   ├── table_parser.py      # 表格解析
│   ├── noise_parser.py      # 噪声检测记录解析
│   ├── electromagnetic_parser.py  # 电磁检测记录解析
│   └── json_converter.py    # JSON转换主入口
│
├── processor/                # PDF处理器模块（待创建）
│   ├── __init__.py
│   ├── mineru_processor.py # MinerU PDF处理器
│   └── converter.py         # 主转换函数
│
└── README.md                # 本文档

```

## 已完成模块

### 1. models/data_models.py
包含所有数据模型类：
- WeatherData
- NoiseData
- OperationalCondition
- NoiseDetectionRecord
- ElectromagneticWeatherData
- ElectromagneticData
- ElectromagneticDetectionRecord

### 2. utils/
- file_utils.py: `safe_stem`, `to_pdf`
- image_utils.py: `crop_image`, `image_to_base64`, `replace_image_with_base64`

### 3. config.py
所有配置常量，包括OCR路径、模型配置、图片裁剪配置等

### 4. ocr/
- ocr_extractor.py: `ocr_extract_text_from_image`
- ocr_parser.py: `parse_noise_detection_record_from_ocr`

## 待创建模块

### 1. parser/
需要从 `demo_pdf_cut.py` 的以下部分提取：
- 第207-464行：JSON转换工具函数
  - `detect_document_type`
  - `extract_table_with_rowspan_colspan`
  - `parse_operational_conditions`
  - `parse_table_cell`
  - `extract_table_data`
- 第976-1348行：解析函数
  - `parse_noise_detection_record`
  - `calculate_average`
  - `parse_electromagnetic_detection_record`
  - `parse_markdown_to_json`

### 2. processor/
需要从 `demo_pdf_cut.py` 的以下部分提取：
- 第1407-1561行：`MinerUPDFProcessor` 类
- 第1608-1797行：`convert_to_markdown` 函数

### 3. main.py
需要从 `demo_pdf_cut.py` 的以下部分提取：
- 第1799-1911行：`main` 函数和 `if __name__ == '__main__'` 部分

## 创建脚本

可以使用以下Python脚本自动完成拆分：

```python
# split_code.py
# 从 demo_pdf_cut.py 提取代码并创建模块文件
```

## 注意事项

1. 所有模块需要使用相对导入（如 `from ..models import ...`）
2. 需要确保所有导入路径正确
3. 主入口 `main.py` 需要放在 `pdf_converter/` 目录下，而不是子目录
4. 测试时需要确保所有依赖都已安装

