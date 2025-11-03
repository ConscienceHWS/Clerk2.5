# 代码拆分指南

## 拆分状态

- ✅ models/ - 已完成
- ✅ utils/ - 已完成
- ✅ config.py - 已完成
- ✅ ocr/ - 基本完成（可能需要调整导入）
- ⏳ parser/ - 待创建
- ⏳ processor/ - 待创建
- ⏳ main.py - 待创建

## 下一步工作

由于代码文件较大（1911行），建议手动创建剩余模块或使用自动化脚本。关键文件位置：

1. **parser模块**（原文件207-1363行）：
   - `detect_document_type`
   - `extract_table_with_rowspan_colspan`
   - `parse_operational_conditions`
   - `parse_table_cell`
   - `extract_table_data`
   - `parse_noise_detection_record`
   - `calculate_average`
   - `parse_electromagnetic_detection_record`
   - `parse_markdown_to_json`

2. **processor模块**（原文件1407-1797行）：
   - `MinerUPDFProcessor` 类
   - `convert_to_markdown` 函数

3. **main.py**（原文件1799-1911行）：
   - `main` 函数
   - CLI参数解析
   - 入口点

## 导入依赖关系

```
main.py
  ├─> processor.converter (convert_to_markdown)
  │     ├─> processor.mineru_processor (MinerUPDFProcessor)
  │     ├─> utils.file_utils
  │     ├─> utils.image_utils
  │     └─> parser.json_converter (parse_markdown_to_json)
  │           ├─> parser.noise_parser
  │           ├─> parser.electromagnetic_parser
  │           ├─> ocr.ocr_extractor
  │           └─> models.data_models
```

