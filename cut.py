#!/usr/bin/env python3
"""
PNG图片剪切脚本
支持通过命令行参数指定上下左右四个方向的剪切像素
"""

import argparse
import sys
from PIL import Image
import os

def crop_image(input_path, output_path, top=0, bottom=0, left=0, right=0):
    """
    剪切PNG图片
    
    Args:
        input_path: 输入图片路径
        output_path: 输出图片路径
        top: 上方剪切像素数
        bottom: 下方剪切像素数
        left: 左侧剪切像素数
        right: 右侧剪切像素数
    """
    try:
        # 打开图片
        with Image.open(input_path) as img:
            # 转换为RGB模式（确保兼容性）
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            width, height = img.size
            print(f"原图尺寸: {width} x {height}")
            
            # 计算剪切后的尺寸
            new_width = width - left - right
            new_height = height - top - bottom
            
            # 验证剪切参数是否有效
            if new_width <= 0 or new_height <= 0:
                raise ValueError("剪切后的图片尺寸无效，请检查剪切参数")
            
            if left + right >= width or top + bottom >= height:
                raise ValueError("剪切区域超出图片范围")
            
            # 计算剪切区域 (left, top, right, bottom)
            crop_box = (left, top, width - right, height - bottom)
            
            # 执行剪切
            cropped_img = img.crop(crop_box)
            
            # 保存图片
            cropped_img.save(output_path, 'PNG')
            
            print(f"剪切后尺寸: {new_width} x {new_height}")
            print(f"图片已保存至: {output_path}")
            
    except FileNotFoundError:
        print(f"错误: 找不到输入文件 '{input_path}'")
        sys.exit(1)
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="PNG图片剪切工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 从上方剪切10像素，下方20像素，左侧5像素，右侧15像素
  python png_crop.py input.png output.png -t 10 -b 20 -l 5 -r 15
  
  # 只剪切左右各50像素
  python png_crop.py input.png output.png -l 50 -r 50
  
  # 只剪切上方100像素
  python png_crop.py input.png output.png -t 100
        """
    )
    
    # 必需参数
    parser.add_argument('input', help='输入PNG文件路径')
    parser.add_argument('output', help='输出PNG文件路径')
    
    # 剪切参数
    parser.add_argument('-t', '--top', type=int, default=0, 
                       help='从上方剪切的像素数 (默认: 0)')
    parser.add_argument('-b', '--bottom', type=int, default=0, 
                       help='从下方剪切的像素数 (默认: 0)')
    parser.add_argument('-l', '--left', type=int, default=0, 
                       help='从左侧剪切的像素数 (默认: 0)')
    parser.add_argument('-r', '--right', type=int, default=0, 
                       help='从右侧剪切的像素数 (默认: 0)')
    
    # 可选参数
    parser.add_argument('--overwrite', action='store_true',
                       help='覆盖已存在的输出文件')
    
    args = parser.parse_args()
    
    # 检查输入文件是否存在
    if not os.path.exists(args.input):
        print(f"错误: 输入文件 '{args.input}' 不存在")
        sys.exit(1)
    
    # 检查输入文件是否为PNG
    if not args.input.lower().endswith('.png'):
        print("警告: 输入文件可能不是PNG格式，但脚本会尝试处理")
    
    # 检查输出文件是否已存在
    if os.path.exists(args.output) and not args.overwrite:
        response = input(f"输出文件 '{args.output}' 已存在，是否覆盖? (y/N): ")
        if response.lower() not in ['y', 'yes']:
            print("操作已取消")
            sys.exit(0)
    
    # 检查剪切参数是否为非负数
    for param_name, param_value in [('上边', args.top), ('下边', args.bottom), 
                                   ('左边', args.left), ('右边', args.right)]:
        if param_value < 0:
            print(f"错误: {param_name}剪切像素数不能为负数")
            sys.exit(1)
    
    # 执行剪切操作
    crop_image(args.input, args.output, args.top, args.bottom, args.left, args.right)

if __name__ == "__main__":
    main()