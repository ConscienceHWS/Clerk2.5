#!/usr/bin/env python3
"""
Markdown to HTML converter
将 Markdown 文件转换为格式良好的 HTML，可在浏览器中打开并打印为 PDF
"""

import sys
from pathlib import Path

try:
    import markdown
except ImportError:
    print("错误: 需要安装 markdown 库")
    print("请运行: pip install markdown")
    sys.exit(1)


def md_to_html(md_file, html_file=None):
    """
    将 Markdown 文件转换为 HTML
    """
    md_path = Path(md_file)
    if not md_path.exists():
        print(f"错误: 文件不存在: {md_file}")
        return False
    
    # 读取 Markdown 文件
    with open(md_path, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    # 转换为 HTML
    html = markdown.markdown(
        md_content,
        extensions=['extra', 'codehilite', 'tables', 'toc']
    )
    
    # 确定输出文件路径
    if html_file is None:
        html_file = md_path.with_suffix('.html')
    else:
        html_file = Path(html_file)
    
    # HTML 模板
    html_template = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{md_path.stem}</title>
    <style>
        @media print {{
            @page {{
                size: A4;
                margin: 2cm;
            }}
            body {{
                font-size: 12pt;
            }}
        }}
        body {{
            font-family: "Microsoft YaHei", "SimSun", "Arial", sans-serif;
            font-size: 14px;
            line-height: 1.8;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #fff;
        }}
        h1 {{
            font-size: 28px;
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
            margin-top: 30px;
            margin-bottom: 20px;
        }}
        h2 {{
            font-size: 24px;
            color: #34495e;
            margin-top: 30px;
            margin-bottom: 15px;
            border-bottom: 2px solid #bdc3c7;
            padding-bottom: 8px;
        }}
        h3 {{
            font-size: 20px;
            color: #555;
            margin-top: 25px;
            margin-bottom: 12px;
        }}
        h4 {{
            font-size: 18px;
            color: #666;
            margin-top: 20px;
            margin-bottom: 10px;
        }}
        h5 {{
            font-size: 16px;
            color: #777;
            margin-top: 15px;
            margin-bottom: 8px;
        }}
        p {{
            margin: 10px 0;
        }}
        code {{
            background-color: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: "Consolas", "Monaco", "Courier New", monospace;
            font-size: 13px;
            color: #e83e8c;
        }}
        pre {{
            background-color: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 5px;
            padding: 15px;
            overflow-x: auto;
            margin: 15px 0;
        }}
        pre code {{
            background-color: transparent;
            padding: 0;
            color: #333;
            font-size: 12px;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 20px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        th, td {{
            border: 1px solid #dee2e6;
            padding: 12px;
            text-align: left;
        }}
        th {{
            background-color: #3498db;
            color: white;
            font-weight: bold;
        }}
        tr:nth-child(even) {{
            background-color: #f8f9fa;
        }}
        tr:hover {{
            background-color: #e9ecef;
        }}
        blockquote {{
            border-left: 4px solid #3498db;
            margin: 20px 0;
            padding: 10px 20px;
            background-color: #f8f9fa;
            color: #555;
            font-style: italic;
        }}
        a {{
            color: #3498db;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        img {{
            max-width: 100%;
            height: auto;
            border-radius: 5px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            margin: 15px 0;
        }}
        details {{
            margin: 15px 0;
            border: 1px solid #dee2e6;
            border-radius: 5px;
            padding: 10px;
        }}
        summary {{
            cursor: pointer;
            font-weight: bold;
            color: #3498db;
            padding: 8px;
            user-select: none;
        }}
        summary:hover {{
            background-color: #f8f9fa;
        }}
        ul, ol {{
            margin: 10px 0;
            padding-left: 30px;
        }}
        li {{
            margin: 5px 0;
        }}
        hr {{
            border: none;
            border-top: 2px solid #bdc3c7;
            margin: 30px 0;
        }}
        .toc {{
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 5px;
            padding: 20px;
            margin: 20px 0;
        }}
        .toc ul {{
            list-style-type: none;
            padding-left: 0;
        }}
        .toc li {{
            margin: 5px 0;
        }}
        .toc a {{
            color: #495057;
        }}
        @media print {{
            body {{
                padding: 0;
            }}
            a {{
                color: #000;
                text-decoration: underline;
            }}
        }}
    </style>
</head>
<body>
    {html}
</body>
</html>"""
    
    try:
        # 写入 HTML 文件
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_template)
        print(f"✅ 转换成功: {html_file}")
        print(f"\n📝 使用说明:")
        print(f"   1. 在浏览器中打开: {html_file}")
        print(f"   2. 按 Ctrl+P (或 Cmd+P) 打印")
        print(f"   3. 选择 '另存为PDF' 或 '打印到PDF'")
        return True
    except Exception as e:
        print(f"❌ 转换失败: {e}")
        return False


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 md_to_html.py <markdown_file> [output_html]")
        sys.exit(1)
    
    md_file = sys.argv[1]
    html_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    md_to_html(md_file, html_file)

