# Copyright (c) Opendatalab. All rights reserved.

"""PDF转换工具主入口"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from .utils.logging_config import get_logger

logger = get_logger("pdf_converter.main")
from mineru.cli.common import pdf_suffixes, image_suffixes

# 支持在包内和包外两种运行方式
try:
    # 尝试相对导入（包内运行）
    from .processor.converter import convert_to_markdown
except ImportError:
    # 如果相对导入失败，使用绝对导入（包外运行）
    from pdf_converter.processor.converter import convert_to_markdown

def main():
    """命令行主函数"""
    parser = argparse.ArgumentParser(description='将PDF/图片转换为Markdown格式（使用vllm引擎）')
    
    # 必需参数
    parser.add_argument('input_file', help='输入文件路径（PDF或图片）')
    
    # 输出选项
    parser.add_argument('-o', '--output-dir', default='./output', help='输出目录（默认: ./output）')
    parser.add_argument('--max-pages', type=int, default=10, help='最大转换页数（默认: 10）')
    
    # 处理选项
    parser.add_argument('--ocr', action='store_true', help='强制启用OCR（暂不支持）')
    parser.add_argument('--no-formula', action='store_true', help='禁用公式识别')
    parser.add_argument('--no-table', action='store_true', help='禁用表格识别')
    parser.add_argument('--language', default='ch', help='识别语言（默认: ch）')
    
    # 模型选项
    parser.add_argument('--model', default='OpenDataLab/MinerU2.5-2509-1.2B', 
                       help='模型名称（默认: OpenDataLab/MinerU2.5-2509-1.2B）')
    parser.add_argument('--gpu-memory', type=float, default=0.9, 
                       help='GPU内存利用率（默认: 0.9）')
    parser.add_argument('--dpi', type=int, default=200, 
                       help='PDF转图片的DPI（默认: 200）')
    
    # 后端选项（兼容老版接口，但实际使用vllm-engine）
    parser.add_argument('--backend', default='vllm-engine', 
                       choices=['vllm-engine'], 
                       help='处理后端（默认: vllm-engine）')
    parser.add_argument('--url', help='服务器URL（暂不支持）')
    
    # 输出格式选项
    parser.add_argument('--no-embed-images', action='store_true', help='不嵌入图片（使用相对路径）')
    parser.add_argument('--output-json', action='store_true', help='同时输出JSON格式（自动识别文档类型）')
    parser.add_argument('--use-split', action='store_true', help='使用图片分割提高识别精度（标题区域识别类型，表体区域提取数据）')
    
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
    supported_suffixes = pdf_suffixes + image_suffixes
    if file_ext not in supported_suffixes:
        logger.error(f"不支持的文件类型: {file_ext}，支持的类型: {supported_suffixes}")
        sys.exit(1)
    
    # 准备参数
    formula_enable = not args.no_formula
    table_enable = not args.no_table
    embed_images = not args.no_embed_images
    
    # 设置环境变量（用于后续处理）
    os.environ['MINERU_VLM_FORMULA_ENABLE'] = str(formula_enable)
    os.environ['MINERU_VLM_TABLE_ENABLE'] = str(table_enable)
    
    logger.info(f"开始转换: {args.input_file}")
    logger.info(f"使用模型: {args.model}")
    logger.info(f"公式识别: {'启用' if formula_enable else '禁用'}")
    logger.info(f"表格识别: {'启用' if table_enable else '禁用'}")
    
    # 执行转换
    try:
        result = asyncio.run(convert_to_markdown(
            input_file=args.input_file,
            output_dir=args.output_dir,
            max_pages=args.max_pages,
            is_ocr=args.ocr,
            formula_enable=formula_enable,
            table_enable=table_enable,
            language=args.language,
            backend=args.backend,
            url=args.url,
            embed_images=embed_images,
            model_name=args.model,
            gpu_memory_utilization=args.gpu_memory,
            dpi=args.dpi,
            output_json=args.output_json,
            use_split=args.use_split
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
