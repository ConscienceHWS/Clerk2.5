#!/usr/bin/env python3
"""
Markdown to PDF converter
使用 markdown 和 weasyprint 将 Markdown 文件转换为 PDF
"""

import sys
import os
from pathlib import Path

try:
    import markdown
    from weasyprint import HTML, CSS
except ImportError as e:
    print(f"缺少必要的库: {e}")
    print("\n请安装所需库:")
    print("  pip install markdown weasyprint")
    sys.exit(1)


def md_to_pdf(md_file, pdf_file=None, css_file=None):
    """
    将 Markdown 文件转换为 PDF
    
    Args:
        md_file: Markdown 文件路径
        pdf_file: 输出 PDF 文件路径（可选，默认为 md_file 同名的 .pdf）
        css_file: 自定义 CSS 文件路径（可选）
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
    
    # 添加基本样式
    css_content = """
    @page {
        size: A4;
        margin: 2cm;
    }
    body {
        font-family: "Microsoft YaHei", "SimSun", "Arial", sans-serif;
        font-size: 12pt;
        line-height: 1.6;
        color: #333;
    }
    h1 {
        font-size: 24pt;
        color: #2c3e50;
        border-bottom: 2px solid #3498db;
        padding-bottom: 10px;
        margin-top: 30px;
    }
    h2 {
        font-size: 20pt;
        color: #34495e;
        margin-top: 25px;
        border-bottom: 1px solid #bdc3c7;
        padding-bottom: 5px;
    }
    h3 {
        font-size: 16pt;
        color: #555;
        margin-top: 20px;
    }
    h4 {
        font-size: 14pt;
        color: #666;
        margin-top: 15px;
    }
    code {
        background-color: #f4f4f4;
        padding: 2px 4px;
        border-radius: 3px;
        font-family: "Consolas", "Monaco", monospace;
        font-size: 11pt;
    }
    pre {
        background-color: #f8f8f8;
        border: 1px solid #ddd;
        border-radius: 4px;
        padding: 10px;
        overflow-x: auto;
        font-size: 10pt;
    }
    pre code {
        background-color: transparent;
        padding: 0;
    }
    table {
        border-collapse: collapse;
        width: 100%;
        margin: 15px 0;
    }
    th, td {
        border: 1px solid #ddd;
        padding: 8px;
        text-align: left;
    }
    th {
        background-color: #3498db;
        color: white;
        font-weight: bold;
    }
    tr:nth-child(even) {
        background-color: #f2f2f2;
    }
    blockquote {
        border-left: 4px solid #3498db;
        margin: 15px 0;
        padding-left: 15px;
        color: #666;
        font-style: italic;
    }
    a {
        color: #3498db;
        text-decoration: none;
    }
    img {
        max-width: 100%;
        height: auto;
    }
    details {
        margin: 10px 0;
    }
    summary {
        cursor: pointer;
        font-weight: bold;
        color: #3498db;
    }
    """
    
    # 如果有自定义 CSS，读取它
    if css_file and Path(css_file).exists():
        with open(css_file, 'r', encoding='utf-8') as f:
            css_content = f.read()
    
    # 构建完整的 HTML 文档
    html_doc = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{md_path.stem}</title>
    </head>
    <body>
        {html}
    </body>
    </html>
    """
    
    # 确定输出文件路径
    if pdf_file is None:
        pdf_file = md_path.with_suffix('.pdf')
    else:
        pdf_file = Path(pdf_file)
    
    try:
        # 转换为 PDF
        print(f"正在转换: {md_path.name} -> {pdf_file.name}")
        HTML(string=html_doc).write_pdf(
            pdf_file,
            stylesheets=[CSS(string=css_content)]
        )
        print(f"✅ 转换成功: {pdf_file}")
        return True
    except Exception as e:
        print(f"❌ 转换失败: {e}")
        return False


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 md_to_pdf.py <markdown_file> [output_pdf]")
        sys.exit(1)
    
    md_file = sys.argv[1]
    pdf_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    md_to_pdf(md_file, pdf_file)

