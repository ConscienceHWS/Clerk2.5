# Copyright (c) Opendatalab. All rights reserved.

"""JSON转换模块 v2 - 复用v1的解析逻辑"""

from typing import Dict, Any, Optional
from PIL import Image
import sys
from pathlib import Path

# 添加v1的路径以便导入
v1_path = Path(__file__).parent.parent.parent / "pdf_converter"
if str(v1_path) not in sys.path:
    sys.path.insert(0, str(v1_path.parent))

from ..utils.logging_config import get_logger

logger = get_logger("pdf_converter_v2.parser.json")

# 导入v1的解析逻辑
# 注意：v2版本复用v1的JSON解析逻辑，但v1的模块可能依赖MinerU和PaddleOCR
# 只要不传递first_page_image（设为None），OCR相关代码不会被执行
try:
    # 方法1: 尝试直接导入（如果v1模块在路径中）
    from pdf_converter.parser.document_type import detect_document_type
    from pdf_converter.parser.noise_parser import parse_noise_detection_record
    from pdf_converter.parser.electromagnetic_parser import parse_electromagnetic_detection_record
except (ImportError, ModuleNotFoundError) as e:
    # 方法2: 尝试通过动态导入，将v1的父目录添加到sys.path
    try:
        v1_parent = Path(__file__).parent.parent.parent
        if str(v1_parent) not in sys.path:
            sys.path.insert(0, str(v1_parent))
        
        # 再次尝试导入
        from pdf_converter.parser.document_type import detect_document_type
        from pdf_converter.parser.noise_parser import parse_noise_detection_record
        from pdf_converter.parser.electromagnetic_parser import parse_electromagnetic_detection_record
    except (ImportError, ModuleNotFoundError) as e2:
        # 如果仍然失败，可能是缺少某些依赖（如mineru），但不影响JSON解析
        # 只要不调用OCR相关代码即可
        logger.warning(f"导入v1模块时出现警告（可能缺少某些可选依赖）: {e2}")
        logger.warning("将尝试继续，但可能需要安装完整依赖")
        # 尝试再次导入，如果失败则抛出异常
        try:
            from pdf_converter.parser.document_type import detect_document_type
            from pdf_converter.parser.noise_parser import parse_noise_detection_record
            from pdf_converter.parser.electromagnetic_parser import parse_electromagnetic_detection_record
        except Exception as e3:
            logger.error(f"无法导入v1的解析模块: {e3}")
            raise ImportError(f"无法导入v1的解析模块，请确保pdf_converter模块可用: {e3}")

def parse_markdown_to_json(markdown_content: str, first_page_image: Optional[Image.Image] = None, output_dir: Optional[str] = None) -> Dict[str, Any]:
    """将Markdown内容转换为JSON - 复用v1的解析逻辑"""
    doc_type = detect_document_type(markdown_content)
    
    if doc_type == "noise_detection":
        data = parse_noise_detection_record(markdown_content, first_page_image, output_dir).to_dict()
        return {"document_type": doc_type, "data": data}
    
    if doc_type == "electromagnetic_detection":
        data = parse_electromagnetic_detection_record(markdown_content).to_dict()
        return {"document_type": doc_type, "data": data}
    
    return {"document_type": "unknown", "data": {}, "error": "无法识别的文档类型"}

