#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF Converter v2 测试脚本
测试API接口调用、zip文件处理和JSON转换功能
"""

import asyncio
import os
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pdf_converter_v2.processor.converter import convert_to_markdown
from pdf_converter_v2.parser.json_converter import parse_markdown_to_json
from pdf_converter_v2.utils.logging_config import get_logger

logger = get_logger("pdf_converter_v2.test")

async def test_api_conversion(input_file: str, output_dir: str = "./test_output"):
    """测试API转换功能"""
    print(f"\n{'='*60}")
    print(f"测试API转换功能")
    print(f"{'='*60}")
    print(f"输入文件: {input_file}")
    print(f"输出目录: {output_dir}")
    
    if not os.path.exists(input_file):
        print(f"❌ 错误: 输入文件不存在: {input_file}")
        return False
    
    try:
        result = await convert_to_markdown(
            input_file=input_file,
            output_dir=output_dir,
            max_pages=10,
            formula_enable=True,
            table_enable=True,
            language="ch",
            backend="vlm-vllm-async-engine",
            url="http://127.0.0.1:5282",
            embed_images=True,
            output_json=True,  # 启用JSON转换
            start_page_id=0,
            end_page_id=99999,
            parse_method="auto",
            response_format_zip=True
        )
        
        if result:
            print(f"\n✅ 转换成功!")
            print(f"   Markdown文件: {result.get('markdown_file')}")
            if result.get('json_file'):
                print(f"   JSON文件: {result.get('json_file')}")
            if result.get('json_data'):
                doc_type = result['json_data'].get('document_type', 'unknown')
                print(f"   文档类型: {doc_type}")
                if doc_type != 'unknown' and result['json_data'].get('data'):
                    data = result['json_data']['data']
                    if doc_type == 'noise_detection':
                        print(f"   项目名称: {data.get('project', '未找到')}")
                        print(f"   噪声数据条数: {len(data.get('noise', []))}")
                    elif doc_type == 'electromagnetic_detection':
                        print(f"   项目名称: {data.get('project', '未找到')}")
                        print(f"   电磁数据条数: {len(data.get('electricMagnetic', []))}")
            return True
        else:
            print(f"\n❌ 转换失败")
            return False
            
    except Exception as e:
        print(f"\n❌ 转换过程出错: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_json_conversion_from_existing_md(md_file: str):
    """测试从现有md文件进行JSON转换"""
    print(f"\n{'='*60}")
    print(f"测试JSON转换功能（使用现有md文件）")
    print(f"{'='*60}")
    print(f"MD文件: {md_file}")
    
    if not os.path.exists(md_file):
        print(f"❌ 错误: MD文件不存在: {md_file}")
        return False
    
    try:
        # 读取md文件
        with open(md_file, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        
        print(f"   MD内容长度: {len(markdown_content)} 字符")
        
        # 转换为JSON
        json_data = parse_markdown_to_json(
            markdown_content,
            first_page_image=None,
            output_dir=None
        )
        
        if json_data:
            doc_type = json_data.get('document_type', 'unknown')
            print(f"\n✅ JSON转换成功!")
            print(f"   文档类型: {doc_type}")
            
            if doc_type != 'unknown' and json_data.get('data'):
                data = json_data['data']
                if doc_type == 'noise_detection':
                    print(f"   项目名称: {data.get('project', '未找到')}")
                    print(f"   检测依据: {data.get('standardReferences', '未找到')}")
                    print(f"   声级计型号: {data.get('soundLevelMeterMode', '未找到')}")
                    print(f"   噪声数据条数: {len(data.get('noise', []))}")
                    if data.get('noise'):
                        print(f"   第一条数据: {data['noise'][0]}")
                elif doc_type == 'electromagnetic_detection':
                    print(f"   项目名称: {data.get('project', '未找到')}")
                    print(f"   监测依据: {data.get('standardReferences', '未找到')}")
                    print(f"   电磁数据条数: {len(data.get('electricMagnetic', []))}")
                    if data.get('electricMagnetic'):
                        print(f"   第一条数据: {data['electricMagnetic'][0]}")
            else:
                print(f"   ⚠️  未识别到文档类型或数据为空")
            
            return True
        else:
            print(f"\n❌ JSON转换失败")
            return False
            
    except Exception as e:
        print(f"\n❌ JSON转换过程出错: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_from_output_dir():
    """测试从output目录中的md文件进行JSON转换"""
    print(f"\n{'='*60}")
    print(f"测试从output目录中的md文件")
    print(f"{'='*60}")
    
    output_dir = Path(__file__).parent / "out"
    if not output_dir.exists():
        print(f"❌ 错误: output目录不存在: {output_dir}")
        return False
    
    md_files = list(output_dir.glob("*.md"))
    if not md_files:
        print(f"❌ 错误: 在output目录中未找到md文件")
        return False
    
    success_count = 0
    for md_file in md_files:
        print(f"\n处理文件: {md_file.name}")
        if await test_json_conversion_from_existing_md(str(md_file)):
            success_count += 1
    
    print(f"\n{'='*60}")
    print(f"总计: {success_count}/{len(md_files)} 个文件转换成功")
    print(f"{'='*60}")
    
    return success_count == len(md_files)


async def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("PDF Converter v2 测试脚本")
    print("="*60)
    
    # 解析命令行参数
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        output_dir = sys.argv[2] if len(sys.argv) > 2 else "./test_output"
        
        # 测试1: API转换测试
        print("\n【测试1】API接口转换测试")
        result = await test_api_conversion(input_file, output_dir)
        if result:
            print("\n✅ 所有测试通过!")
        else:
            print("\n❌ 测试失败!")
            sys.exit(1)
    else:
        # 如果没有提供输入文件，则测试从output目录中的md文件
        print("\n【测试】从output目录中的md文件进行JSON转换测试")
        print("提示: 如果要测试API转换，请提供PDF文件路径:")
        print("      python test_converter.py <pdf_file> [output_dir]")
        
        # 测试2: 从output目录测试
        result = await test_from_output_dir()
        if result:
            print("\n✅ 所有测试通过!")
        else:
            print("\n⚠️  部分测试失败!")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

