# Copyright (c) Opendatalab. All rights reserved.

"""PDF转换工具主入口 v2"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from .utils.logging_config import get_logger

logger = get_logger("pdf_converter_v2.main")

# 支持在包内和包外两种运行方式
try:
    # 尝试相对导入（包内运行）
    from .processor.converter import convert_to_markdown
except ImportError:
    # 如果相对导入失败，使用绝对导入（包外运行）
    from pdf_converter_v2.processor.converter import convert_to_markdown

def main():
    """命令行主函数"""
    parser = argparse.ArgumentParser(description='将PDF/图片转换为Markdown格式 v2（使用新的API接口）')
    
    # 必需参数
    parser.add_argument('input_file', help='输入文件路径（PDF）')
    
    # 输出选项
    parser.add_argument('-o', '--output-dir', default='./output', help='输出目录（默认: ./output）')
    parser.add_argument('--max-pages', type=int, default=10, help='最大转换页数（默认: 10，通过end_page_id控制）')
    
    # API选项
    parser.add_argument('--url', default='http://192.168.2.3:8000', help='API服务器URL（默认: http://192.168.2.3:8000）')
    parser.add_argument('--backend', default='vlm-vllm-async-engine', help='处理后端（默认: vlm-vllm-async-engine）')
    parser.add_argument('--parse-method', default='auto', help='解析方法（默认: auto）')
    parser.add_argument('--start-page-id', type=int, default=0, help='起始页ID（默认: 0）')
    parser.add_argument('--end-page-id', type=int, default=99999, help='结束页ID（默认: 99999）')
    
    # 处理选项
    parser.add_argument('--no-formula', action='store_true', help='禁用公式识别')
    parser.add_argument('--no-table', action='store_true', help='禁用表格识别')
    parser.add_argument('--language', default='ch', help='识别语言（默认: ch）')
    
    # 输出格式选项
    parser.add_argument('--no-embed-images', action='store_true', help='不嵌入图片（使用相对路径）')
    parser.add_argument('--output-json', action='store_true', help='同时输出JSON格式（自动识别文档类型）')
    
    # 日志选项
    parser.add_argument('-v', '--verbose', action='store_true', help='详细日志输出')
    
    args = parser.parse_args()
    
    # 配置日志
    log_level = "DEBUG" if args.verbose else "INFO"
    logger.remove()
    logger.add(sys.stderr, level=log_level)
    
    # 验证输入文件
    if not os.path.exists(args.input_file):
        logger.error(f"输入文件不存在: {args.input_file}")
        sys.exit(1)
    
    # 验证文件类型
    file_ext = Path(args.input_file).suffix.lower()
    if file_ext != '.pdf':
        logger.warning(f"输入文件类型为 {file_ext}，v2版本主要支持PDF文件")
    
    # 准备参数
    formula_enable = not args.no_formula
    table_enable = not args.no_table
    embed_images = not args.no_embed_images
    
    logger.info(f"开始转换: {args.input_file}")
    logger.info(f"使用API: {args.url}")
    logger.info(f"处理后端: {args.backend}")
    logger.info(f"公式识别: {'启用' if formula_enable else '禁用'}")
    logger.info(f"表格识别: {'启用' if table_enable else '禁用'}")
    
    # 执行转换
    try:
        result = asyncio.run(convert_to_markdown(
            input_file=args.input_file,
            output_dir=args.output_dir,
            max_pages=args.max_pages,
            is_ocr=False,
            formula_enable=formula_enable,
            table_enable=table_enable,
            language=args.language,
            backend=args.backend,
            url=args.url,
            embed_images=embed_images,
            output_json=args.output_json,
            start_page_id=args.start_page_id,
            end_page_id=args.end_page_id,
            parse_method=args.parse_method,
            response_format_zip=True
        ))
        
        if result:
            logger.info("转换成功完成！")
            logger.info(f"Markdown文件: {result['markdown_file']}")
            if result.get('json_file'):
                logger.info(f"JSON文件: {result['json_file']}")
                if result.get('json_data'):
                    doc_type = result['json_data'].get('document_type', 'unknown')
                    logger.info(f"文档类型: {doc_type}")
        else:
            logger.error("转换失败")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("用户中断操作")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"转换过程中发生错误: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

