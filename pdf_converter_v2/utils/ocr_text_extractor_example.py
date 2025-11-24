#!/usr/bin/env python3
"""
OCR文本提取示例 - 从PaddleOCR JSON输出中提取带段落分割的纯文本
"""

from pdf_converter_v2.utils.paddleocr_fallback import extract_text_with_paragraphs_from_ocr_json
import sys

def main():
    if len(sys.argv) < 2:
        print("用法: python ocr_text_extractor_example.py <json_file_path>")
        print("示例: python ocr_text_extractor_example.py out/工况信息_res.json")
        sys.exit(1)
    
    json_path = sys.argv[1]
    
    # 提取文本（可以自定义参数）
    # line_height_threshold: 行高倍数阈值，用于判断是否在同一行（默认1.5）
    # paragraph_gap_threshold: 段落间距倍数阈值，用于判断是否需要分段（默认2.0）
    result = extract_text_with_paragraphs_from_ocr_json(
        json_path,
        line_height_threshold=1.5,
        paragraph_gap_threshold=2.0
    )
    
    if result:
        print("=" * 80)
        print("提取的文本（带段落分割）:")
        print("=" * 80)
        print(result)
        print("=" * 80)
        print(f"\n文本长度: {len(result)} 字符")
        print(f"行数: {len(result.split(chr(10)))} 行")
    else:
        print("未能提取文本，请检查JSON文件格式")

if __name__ == "__main__":
    main()

