# Copyright (c) Opendatalab. All rights reserved.

"""JSON转换模块 v2 - 独立版本，不依赖v1"""

from typing import Dict, Any, Optional
import re
from PIL import Image

from ..utils.logging_config import get_logger
from .document_type import detect_document_type
from .noise_parser import parse_noise_detection_record
from .electromagnetic_parser import parse_electromagnetic_detection_record
from .table_parser import parse_operational_conditions, parse_operational_conditions_v2, parse_operational_conditions_opstatus

logger = get_logger("pdf_converter_v2.parser.json")

def parse_markdown_to_json(markdown_content: str, first_page_image: Optional[Image.Image] = None, output_dir: Optional[str] = None, forced_document_type: Optional[str] = None) -> Dict[str, Any]:
    """将Markdown内容转换为JSON - v2独立版本，不依赖v1和OCR
    如果提供 forced_document_type（正式全称），则优先按指定类型解析。
    支持映射：
      - noiseMonitoringRecord -> 使用噪声解析
      - electromagneticTestRecord -> 使用电磁解析
      - 其他类型：返回空数据占位
    """
    if forced_document_type:
        if forced_document_type == "noiseMonitoringRecord":
            data = parse_noise_detection_record(markdown_content, first_page_image=None, output_dir=output_dir).to_dict()
            return {"document_type": forced_document_type, "data": data}
        if forced_document_type == "electromagneticTestRecord":
            data = parse_electromagnetic_detection_record(markdown_content).to_dict()
            return {"document_type": forced_document_type, "data": data}
        if forced_document_type == "operatingConditionInfo":
            # 仅解析工况信息
            # 优先级：表1检测工况格式 > opStatus格式 > 旧格式
            # 1. 检查是否为"表1检测工况"格式（使用正则表达式，允许中间有空格）
            # 支持：表1检测工况、表 1 检测工况、表 1检测工况、表1 检测工况 等变体
            pattern = r'表\s*1\s*检测工况'
            if re.search(pattern, markdown_content):
                logger.info("[JSON转换] 检测到'表1检测工况'标识（包括空格变体），使用新格式解析")
                op_list = parse_operational_conditions_v2(markdown_content)
                serialized = [oc.to_dict() if hasattr(oc, "to_dict") else oc for oc in (op_list or [])]
                return {"document_type": forced_document_type, "data": {"operationalConditions": serialized}}
            
            # 2. 检查是否为opStatus格式（附件 工况及工程信息，且不包含"表1检测工况"）
            if "附件" in markdown_content and "工况" in markdown_content:
                logger.info("[JSON转换] 检测到'附件 工况及工程信息'格式，使用opStatus格式解析")
                op_list = parse_operational_conditions_opstatus(markdown_content)
                serialized = [oc.to_dict() if hasattr(oc, "to_dict") else oc for oc in (op_list or [])]
                return {"document_type": forced_document_type, "data": serialized}
            
            # 3. 使用旧格式解析（先尝试有标题模式，如果失败则尝试无标题模式）
            logger.info("[JSON转换] 未检测到特殊格式标识，使用旧格式解析")
            op_list = parse_operational_conditions(markdown_content, require_title=True)
            # 如果没有找到结果，尝试无标题模式（仅根据表格结构判断）
            if not op_list:
                logger.info("[JSON转换] 有标题模式未找到结果，尝试无标题模式解析")
                op_list = parse_operational_conditions(markdown_content, require_title=False)
            serialized = [oc.to_dict() if hasattr(oc, "to_dict") else oc for oc in (op_list or [])]
            return {"document_type": forced_document_type, "data": {"operationalConditions": serialized}}
        return {"document_type": forced_document_type, "data": {}}

    doc_type = detect_document_type(markdown_content)
    
    if doc_type == "noise_detection":
        # v2版本不依赖OCR，first_page_image参数会被忽略
        data = parse_noise_detection_record(markdown_content, first_page_image=None, output_dir=output_dir).to_dict()
        return {"document_type": doc_type, "data": data}
    
    if doc_type == "electromagnetic_detection":
        data = parse_electromagnetic_detection_record(markdown_content).to_dict()
        return {"document_type": doc_type, "data": data}
    
    return {"document_type": "unknown", "data": {}, "error": "无法识别的文档类型"}

