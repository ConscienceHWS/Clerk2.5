# Copyright (c) Opendatalab. All rights reserved.

import argparse
import asyncio
import base64
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

from loguru import logger
from vllm import LLM
from pdf2image import convert_from_path
from mineru_vl_utils import MinerUClient
from mineru_vl_utils import MinerULogitsProcessor
from mineru.cli.common import prepare_env, read_fn, pdf_suffixes, image_suffixes


# ---------------------------- JSON转换数据模型 ----------------------------
class WeatherData:
    def __init__(self):
        self.monitorAt: str = ""
        self.weather: str = ""
        self.temp: str = ""
        self.humidity: str = ""
        self.windSpeed: str = ""
        self.windDirection: str = ""
    
    def to_dict(self):
        return {
            "monitorAt": self.monitorAt,
            "weather": self.weather,
            "temp": self.temp,
            "humidity": self.humidity,
            "windSpeed": self.windSpeed,
            "windDirection": self.windDirection
        }


class NoiseData:
    def __init__(self):
        self.code: str = ""
        self.address: str = ""
        self.source: str = ""
        self.dayMonitorAt: str = ""
        self.dayMonitorValue: str = ""
        self.dayMonitorBackgroundValue: str = ""
        self.nightMonitorAt: str = ""
        self.nightMonitorValue: str = ""
        self.nightMonitorBackgroundValue: str = ""
        self.remark: str = ""
    
    def to_dict(self):
        return {
            "code": self.code,
            "address": self.address,
            "source": self.source,
            "dayMonitorAt": self.dayMonitorAt,
            "dayMonitorValue": self.dayMonitorValue,
            "dayMonitorBackgroundValue": self.dayMonitorBackgroundValue,
            "nightMonitorAt": self.nightMonitorAt,
            "nightMonitorValue": self.nightMonitorValue,
            "nightMonitorBackgroundValue": self.nightMonitorBackgroundValue,
            "remark": self.remark
        }


class NoiseDetectionRecord:
    def __init__(self):
        self.project: str = ""
        self.standardReferences: str = ""
        self.soundLevelMeterMode: str = ""
        self.soundCalibratorMode: str = ""
        self.calibrationValueBefore: str = ""
        self.calibrationValueAfter: str = ""
        self.weather: List[WeatherData] = []
        self.noise: List[NoiseData] = []
    
    def to_dict(self):
        return {
            "project": self.project,
            "standardReferences": self.standardReferences,
            "soundLevelMeterMode": self.soundLevelMeterMode,
            "soundCalibratorMode": self.soundCalibratorMode,
            "calibrationValueBefore": self.calibrationValueBefore,
            "calibrationValueAfter": self.calibrationValueAfter,
            "weather": [w.to_dict() for w in self.weather],
            "noise": [n.to_dict() for n in self.noise]
        }


class ElectromagneticWeatherData:
    def __init__(self):
        self.weather: str = ""
        self.temp: str = ""
        self.humidity: str = ""
        self.windSpeed: str = ""
    
    def to_dict(self):
        return {
            "weather": self.weather,
            "temp": self.temp,
            "humidity": self.humidity,
            "windSpeed": self.windSpeed
        }


class ElectromagneticData:
    def __init__(self):
        self.code: str = ""
        self.address: str = ""
        self.height: str = ""
        self.monitorAt: str = ""
        self.powerFrequencyEFieldStrength1: str = ""
        self.powerFrequencyEFieldStrength2: str = ""
        self.powerFrequencyEFieldStrength3: str = ""
        self.powerFrequencyEFieldStrength4: str = ""
        self.powerFrequencyEFieldStrength5: str = ""
        self.avgPowerFrequencyEFieldStrength: str = ""
        self.powerFrequencyMagneticDensity1: str = ""
        self.powerFrequencyMagneticDensity2: str = ""
        self.powerFrequencyMagneticDensity3: str = ""
        self.powerFrequencyMagneticDensity4: str = ""
        self.powerFrequencyMagneticDensity5: str = ""
        self.avgPowerFrequencyMagneticDensity: str = ""
    
    def to_dict(self):
        return {
            "code": self.code,
            "address": self.address,
            "height": self.height,
            "monitorAt": self.monitorAt,
            "powerFrequencyEFieldStrength1": self.powerFrequencyEFieldStrength1,
            "powerFrequencyEFieldStrength2": self.powerFrequencyEFieldStrength2,
            "powerFrequencyEFieldStrength3": self.powerFrequencyEFieldStrength3,
            "powerFrequencyEFieldStrength4": self.powerFrequencyEFieldStrength4,
            "powerFrequencyEFieldStrength5": self.powerFrequencyEFieldStrength5,
            "avgPowerFrequencyEFieldStrength": self.avgPowerFrequencyEFieldStrength,
            "powerFrequencyMagneticDensity1": self.powerFrequencyMagneticDensity1,
            "powerFrequencyMagneticDensity2": self.powerFrequencyMagneticDensity2,
            "powerFrequencyMagneticDensity3": self.powerFrequencyMagneticDensity3,
            "powerFrequencyMagneticDensity4": self.powerFrequencyMagneticDensity4,
            "powerFrequencyMagneticDensity5": self.powerFrequencyMagneticDensity5,
            "avgPowerFrequencyMagneticDensity": self.avgPowerFrequencyMagneticDensity
        }


class ElectromagneticDetectionRecord:
    def __init__(self):
        self.project: str = ""
        self.standardReferences: str = ""
        self.deviceName: str = ""
        self.deviceMode: str = ""
        self.deviceCode: str = ""
        self.monitorHeight: str = ""
        self.weather: ElectromagneticWeatherData = ElectromagneticWeatherData()
        self.electricMagnetic: List[ElectromagneticData] = []
    
    def to_dict(self):
        return {
            "project": self.project,
            "standardReferences": self.standardReferences,
            "deviceName": self.deviceName,
            "deviceMode": self.deviceMode,
            "deviceCode": self.deviceCode,
            "monitorHeight": self.monitorHeight,
            "weather": self.weather.to_dict(),
            "electricMagnetic": [em.to_dict() for em in self.electricMagnetic]
        }


# ---------------------------- JSON转换工具函数 ----------------------------
def detect_document_type(markdown_content: str) -> str:
    """检测文档类型"""
    if "污染源噪声检测原始记录表" in markdown_content:
        return "noise_detection"
    if "工频电场/磁场环境检测原始记录表" in markdown_content:
        return "electromagnetic_detection"
    return "unknown"


def parse_table_cell(cell_content: str) -> str:
    """解析表格单元格内容"""
    if not cell_content:
        return ""
    cell_content = re.sub(r'<[^>]+>', '', cell_content)
    cell_content = re.sub(r'\s+', ' ', cell_content).strip()
    return cell_content


def extract_table_data(markdown_content: str) -> List[List[List[str]]]:
    """从Markdown内容中提取表格数据"""
    tables: List[List[List[str]]] = []
    table_matches = re.findall(r'<table>(.*?)</table>', markdown_content, re.DOTALL)
    logger.debug(f"[extract_table_data] 共找到 {len(table_matches)} 个表格")
    
    for table_idx, table_content in enumerate(table_matches):
        table_rows: List[List[str]] = []
        tr_matches = re.findall(r'<tr[^>]*>(.*?)</tr>', table_content, re.DOTALL)
        logger.debug(f"[extract_table_data] 表格{table_idx}, 行数: {len(tr_matches)}")
        
        for row_idx, tr_content in enumerate(tr_matches):
            td_matches = re.findall(r'<td[^>]*>(.*?)</td>', tr_content)
            row: List[str] = [parse_table_cell(td) for td in td_matches]
            if row:
                table_rows.append(row)
        
        if table_rows:
            tables.append(table_rows)
    
    logger.debug(f"[extract_table_data] 总表格: {len(tables)}")
    return tables


def parse_noise_detection_record(markdown_content: str) -> NoiseDetectionRecord:
    """解析噪声检测记录"""
    record = NoiseDetectionRecord()
    tables = extract_table_data(markdown_content)
    
    if not tables:
        logger.warning(f"[噪声检测] 未能提取出任何表格内容")
        return record

    first_table = tables[0]
    for row in first_table:
        logger.debug(f"[噪声检测][ROW] len={len(row)}, content={row}")
        if len(row) >= 2:
            if "项目名称" in row[0]:
                for i, cell in enumerate(row):
                    if "项目名称" in cell and i + 1 < len(row):
                        record.project = row[i + 1]
                        if not record.project.strip():
                            logger.error(f"[噪声检测] 项目名称 为空，行数据: {row}")
                        break
            if any(k in row[0] for k in ["检测依据", "监测依据"]):
                for i, cell in enumerate(row):
                    if any(k in cell for k in ["检测依据", "监测依据"]) and i + 1 < len(row):
                        record.standardReferences = row[i + 1]
                        if not record.standardReferences.strip():
                            logger.error(f"[噪声检测] 检测/监测依据 为空，行数据: {row}")
                        break
            if any(k in row[0] for k in ["声纹计型号", "声级计型号"]):
                for i, cell in enumerate(row):
                    if any(k in cell for k in ["声纹计型号", "声级计型号"]) and i + 1 < len(row):
                        record.soundLevelMeterMode = row[i + 1]
                        if not record.soundLevelMeterMode.strip():
                            logger.error(f"[噪声检测] 声级计型号 为空，行数据: {row}")
                        break
            if any(k in row[0] for k in ["声纹准器型号", "声级计校准器型号"]):
                for i, cell in enumerate(row):
                    if any(k in cell for k in ["声纹准器型号", "声级计校准器型号"]) and i + 1 < len(row):
                        record.soundCalibratorMode = row[i + 1]
                        if not record.soundCalibratorMode.strip():
                            logger.error(f"[噪声检测] 声级计校准器型号 为空，行数据: {row}")
                        break
            if "检测前校准值" in row[0]:
                for i, cell in enumerate(row):
                    if "检测前校准值" in cell and i + 1 < len(row):
                        record.calibrationValueBefore = row[i + 1]
                        if not record.calibrationValueBefore.strip():
                            logger.error(f"[噪声检测] 检测前校准值 为空，行数据: {row}")
                        break
            if "检测后校准值" in row[0]:
                for i, cell in enumerate(row):
                    if "检测后校准值" in cell and i + 1 < len(row):
                        record.calibrationValueAfter = row[i + 1]
                        if not record.calibrationValueAfter.strip():
                            logger.error(f"[噪声检测] 检测后校准值 为空，行数据: {row}")
                        break

    weather = WeatherData()
    for row in first_table:
        if len(row) >= 2 and "气象条件" in row[0]:
            text = " ".join(row[1:])
            m = re.search(r'日期[:：]\s*([\d.\-]+)', text)
            if m: weather.monitorAt = m.group(1)
            m = re.search(r'天气[:：]\s*([^\s]+)', text)
            if m: weather.weather = m.group(1)
            m = re.search(r'温度[:：]?\s*([0-9.\-]+)', text)
            if m: weather.temp = m.group(1)
            m = re.search(r'湿度[:：]?\s*([0-9.\-]+)', text)
            if m: weather.humidity = m.group(1)
            m = re.search(r'风速[:：]?\s*([0-9.\-]+)', text)
            if m: weather.windSpeed = m.group(1)
            m = re.search(r'风向[:：]?\s*([^\s]+)', text)
            if m: weather.windDirection = m.group(1)
            record.weather.append(weather)
            break

    for table in tables:
        for row in table:
            if len(row) >= 8 and row[0] and row[0] not in ["编号", "备注"]:
                logger.info(row)
                nd = NoiseData()
                nd.code = row[0]
                nd.address = row[1] if len(row) > 1 else ""
                nd.source = row[2] if len(row) > 2 else ""
                nd.dayMonitorAt = row[3] if len(row) > 3 else ""
                nd.dayMonitorValue = row[4] if len(row) > 4 else ""
                nd.dayMonitorBackgroundValue = row[5] if len(row) > 5 else ""
                nd.nightMonitorAt = row[6] if len(row) > 6 else ""
                nd.nightMonitorValue = row[7] if len(row) > 7 else ""
                nd.nightMonitorBackgroundValue = row[8] if len(row) > 8 else ""
                nd.remark = row[9] if len(row) > 9 else ""
                record.noise.append(nd)
    
    return record


def parse_electromagnetic_detection_record(markdown_content: str) -> ElectromagneticDetectionRecord:
    """解析电磁检测记录"""
    record = ElectromagneticDetectionRecord()
    tables = extract_table_data(markdown_content)
    
    if not tables:
        logger.warning(f"[电磁检测] 未能提取出任何表格内容")
        return record

    first_table = tables[0]
    for row in first_table:
        logger.debug(f"[电磁检测][ROW] len={len(row)}, content={row}")
        i = 0
        while i < len(row):
            cell = row[i]
            if i+1 >= len(row):
                break
            value = row[i+1]
            if "项目名称" in cell:
                record.project = value
                if not record.project.strip():
                    logger.error(f"[电磁检测] 项目名称 为空，行数据: {row}")
                i += 2
                continue
            if "监测依据" in cell:
                record.standardReferences = value
                if not record.standardReferences.strip():
                    logger.error(f"[电磁检测] 监测依据 为空，行数据: {row}")
                i += 2
                continue
            if "仪器名称" in cell:
                record.deviceName = value
                if not record.deviceName.strip():
                    logger.error(f"[电磁检测] 仪器名称 为空，行数据: {row}")
                i += 2
                continue
            if "仪器型号" in cell:
                record.deviceMode = value
                if not record.deviceMode.strip():
                    logger.error(f"[电磁检测] 仪器型号 为空，行数据: {row}")
                i += 2
                continue
            if "仪器编号" in cell:
                record.deviceCode = value
                if not record.deviceCode.strip():
                    logger.error(f"[电磁检测] 仪器编号 为空，行数据: {row}")
                i += 2
                continue
            if any(k in cell for k in ["测量高度", "检测高度"]):
                record.monitorHeight = value
                if not record.monitorHeight.strip():
                    logger.error(f"[电磁检测] 检测/测量高度 为空，行数据: {row}")
                i += 2
                continue
            if "检测环境条件" in cell:
                text = value
                m = re.search(r'([0-9.\-]+)\s*℃', text)
                if m: record.weather.temp = m.group(1)
                m = re.search(r'([0-9.\-]+)\s*%RH', text)
                if m: record.weather.humidity = m.group(1)
                m = re.search(r'([0-9.\-]+)\s*m/s', text)
                if m: record.weather.windSpeed = m.group(1)
                m = re.search(r'天气[：:]*\s*([^\s]+)', text)
                if m: record.weather.weather = m.group(1)
                i += 2
                continue
            i += 1

    for table in tables:
        for row in table:
            if len(row) >= 8 and row[0] and row[0] not in ["编号", "备注"] and row[0].startswith("EB"):
                logger.info(row)
                em = ElectromagneticData()
                em.code = row[0]
                em.address = row[1] if len(row) > 1 else ""
                em.height = row[2] if len(row) > 2 else ""
                em.monitorAt = row[3] if len(row) > 3 else ""
                if len(row) > 4: em.powerFrequencyEFieldStrength1 = row[4]
                if len(row) > 5: em.powerFrequencyEFieldStrength2 = row[5]
                if len(row) > 6: em.powerFrequencyEFieldStrength3 = row[6]
                if len(row) > 7: em.powerFrequencyEFieldStrength4 = row[7]
                if len(row) > 8: em.powerFrequencyEFieldStrength5 = row[8]
                if len(row) > 9: em.avgPowerFrequencyEFieldStrength = row[9]
                if len(row) > 10: em.powerFrequencyMagneticDensity1 = row[10]
                if len(row) > 11: em.powerFrequencyMagneticDensity2 = row[11]
                if len(row) > 12: em.powerFrequencyMagneticDensity3 = row[12]
                if len(row) > 13: em.powerFrequencyMagneticDensity4 = row[13]
                if len(row) > 14: em.powerFrequencyMagneticDensity5 = row[14]
                if len(row) > 15: em.avgPowerFrequencyMagneticDensity = row[15]
                record.electricMagnetic.append(em)
    
    return record


def parse_markdown_to_json(markdown_content: str) -> Dict[str, Any]:
    """将Markdown内容转换为JSON"""
    doc_type = detect_document_type(markdown_content)
    
    if doc_type == "noise_detection":
        data = parse_noise_detection_record(markdown_content).to_dict()
        return {"document_type": doc_type, "data": data}
    
    if doc_type == "electromagnetic_detection":
        data = parse_electromagnetic_detection_record(markdown_content).to_dict()
        return {"document_type": doc_type, "data": data}
    
    return {"document_type": "unknown", "data": {}, "error": "无法识别的文档类型"}


class MinerUPDFProcessor:
    """使用vllm引擎处理PDF的处理器"""
    
    def __init__(self, model_name="OpenDataLab/MinerU2.5-2509-1.2B", gpu_memory_utilization=0.5):
        """初始化vllm引擎和MinerUClient"""
        self.llm = LLM(
            model=model_name,
            logits_processors=[MinerULogitsProcessor],
            gpu_memory_utilization=gpu_memory_utilization,
            trust_remote_code=True
        )
        self.client = MinerUClient(
            backend="vllm-engine",
            vllm_llm=self.llm
        )
    
    def process_pdf_pages(self, pdf_path, max_pages=None, dpi=200):
        """处理PDF的页面，返回提取的文本块列表"""
        try:
            # 转换PDF为图片
            all_images = convert_from_path(pdf_path, dpi=dpi)
            total_pages = len(all_images)
            
            # 限制处理的页数
            if max_pages and max_pages > 0:
                images = all_images[:max_pages]
                logger.info(f"将处理前 {max_pages} 页（共 {total_pages} 页）")
            else:
                images = all_images
                logger.info(f"将处理全部 {total_pages} 页")
            
            results = []
            for i, image in enumerate(images):
                logger.info(f"处理第 {i + 1}/{len(images)} 页...")
                
                # 提取文本块
                extracted_blocks = self.client.two_step_extract(image)
                results.append({
                    "page": i + 1,
                    "extracted_blocks": extracted_blocks
                })
            
            return results
        except Exception as e:
            logger.exception(f"PDF处理失败: {e}")
            return None
    
    def blocks_to_markdown(self, extracted_blocks):
        logger.info(extracted_blocks)
        """将提取的文本块转换为Markdown格式"""
        if not extracted_blocks:
            return ""
        
        # 如果extracted_blocks已经是字符串（Markdown格式），直接返回
        if isinstance(extracted_blocks, str):
            return extracted_blocks
        
        # 如果是列表，遍历处理
        if isinstance(extracted_blocks, list):
            markdown_content = ""
            for block in extracted_blocks:
                # 如果block是字符串，直接添加
                if isinstance(block, str):
                    markdown_content += block + "\n\n"
                # 如果是字典，按类型处理
                elif isinstance(block, dict):
                    block_type = block.get("type", "")
                    content = block.get("content", "")
                    
                    if block_type == "title" or block_type == "heading":
                        level = block.get("level", 1)
                        markdown_content += f"{'#' * level} {content}\n\n"
                    elif block_type == "paragraph" or block_type == "text":
                        markdown_content += f"{content}\n\n"
                    elif block_type == "list" or block_type == "unordered_list":
                        items = block.get("items", [])
                        for item in items:
                            markdown_content += f"- {item}\n"
                        markdown_content += "\n"
                    elif block_type == "ordered_list":
                        items = block.get("items", [])
                        for i, item in enumerate(items, 1):
                            markdown_content += f"{i}. {item}\n"
                        markdown_content += "\n"
                    elif block_type == "table":
                        table_content = block.get("content", "")
                        if isinstance(table_content, str):
                            markdown_content += f"{table_content}\n\n"
                        else:
                            # 尝试格式化表格
                            markdown_content += f"{table_content}\n\n"
                    elif block_type == "formula" or block_type == "math":
                        formula = block.get("content", "")
                        markdown_content += f"$$\n{formula}\n$$\n\n"
                    elif block_type == "image" or block_type == "figure":
                        image_path = block.get("path", "") or block.get("src", "")
                        alt_text = block.get("alt", "") or image_path
                        if image_path:
                            markdown_content += f"![{alt_text}]({image_path})\n\n"
                    else:
                        # 默认处理：如果有content字段就使用
                        if content:
                            markdown_content += f"{content}\n\n"
                        # 否则尝试转换为字符串
                        elif block:
                            markdown_content += f"{str(block)}\n\n"
            
            return markdown_content
        
        # 其他情况，尝试转换为字符串
        return str(extracted_blocks)


def image_to_base64(image_path):
    """将图片转换为base64编码"""
    with open(image_path, 'rb') as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def replace_image_with_base64(markdown_text, image_dir_path):
    """将Markdown中的图片链接替换为base64编码"""
    pattern = r'\!\[(?:[^\]]*)\]\(([^)]+)\)'

    def replace(match):
        relative_path = match.group(1)
        full_path = os.path.join(image_dir_path, relative_path)
        if os.path.exists(full_path):
            base64_image = image_to_base64(full_path)
            # 判断图片格式
            ext = Path(full_path).suffix.lower()
            mime_type = "image/jpeg" if ext in ['.jpg', '.jpeg'] else f"image/{ext[1:]}" if ext else "image/png"
            return f'![{relative_path}](data:{mime_type};base64,{base64_image})'
        return match.group(0)

    return re.sub(pattern, replace, markdown_text)


def safe_stem(file_path):
    """安全地提取文件名（去除不安全字符）"""
    stem = Path(file_path).stem
    return re.sub(r'[^\w.]', '_', stem)


def to_pdf(file_path):
    """将文件转换为PDF格式（如果需要）"""
    if file_path is None or not os.path.exists(file_path):
        return None

    pdf_bytes = read_fn(file_path)
    unique_filename = f'{safe_stem(file_path)}.pdf'
    tmp_file_path = os.path.join(os.path.dirname(file_path), unique_filename)

    with open(tmp_file_path, 'wb') as tmp_pdf_file:
        tmp_pdf_file.write(pdf_bytes)

    return tmp_file_path


async def convert_to_markdown(
    input_file,
    output_dir="./output",
    max_pages=10,
    is_ocr=False,
    formula_enable=True,
    table_enable=True,
    language="ch",
    backend="vllm-engine",
    url=None,
    embed_images=True,
    model_name="OpenDataLab/MinerU2.5-2509-1.2B",
    gpu_memory_utilization=0.9,
    dpi=200,
    output_json=False
):
    """将PDF/图片转换为Markdown的主要函数（使用vllm引擎）"""
    
    if not os.path.exists(input_file):
        logger.error(f"输入文件不存在: {input_file}")
        return None

    # 转换为PDF格式（如果需要）
    pdf_path = to_pdf(input_file)
    if not pdf_path:
        logger.error("文件转换失败")
        return None

    try:
        os.makedirs(output_dir, exist_ok=True)
        
        # 生成文件名
        file_name = f'{safe_stem(Path(input_file).stem)}_{time.strftime("%y%m%d_%H%M%S")}'
        parse_method = 'vllm-engine'
        
        # 准备输出目录
        local_image_dir, local_md_dir = prepare_env(output_dir, file_name, parse_method)
        
        # 初始化处理器
        processor = MinerUPDFProcessor(model_name=model_name, gpu_memory_utilization=gpu_memory_utilization)
        
        # 处理PDF页面
        logger.info(f"开始处理PDF: {pdf_path}")
        results = processor.process_pdf_pages(pdf_path, max_pages=max_pages, dpi=dpi)
        
        if not results:
            logger.error("PDF处理失败")
            return None
        
        # 将所有页面的内容合并为Markdown
        markdown_parts = []
        
        # 如果需要保存页面图片，获取PDF的图片
        pdf_images = []
        try:
            if embed_images:
                # 获取PDF的图片（用于保存）
                pdf_images = convert_from_path(pdf_path, dpi=dpi)
                if max_pages:
                    pdf_images = pdf_images[:max_pages]
        except Exception as e:
            logger.warning(f"无法加载PDF图片用于保存: {e}")
            pdf_images = []
        
        for i, result in enumerate(results):
            page_num = result['page']
            extracted_blocks = result['extracted_blocks']
            
            # 添加页面分隔符（可选）
            # markdown_parts.append(f"\n\n## 第 {page_num} 页\n\n")
            
            # 转换为Markdown
            page_markdown = processor.blocks_to_markdown(extracted_blocks)
            
            # 如果需要保存页面图片，将图片链接添加到Markdown中
            if i < len(pdf_images) and embed_images:
                image_filename = f"page_{page_num}.png"
                image_path = os.path.join(local_image_dir, image_filename)
                try:
                    pdf_images[i].save(image_path)
                    # 在页面内容前添加图片引用（可选）
                    # page_markdown = f"![第 {page_num} 页](images/{image_filename})\n\n" + page_markdown
                except Exception as e:
                    logger.warning(f"保存页面图片失败: {e}")
            
            markdown_parts.append(page_markdown)
        
        # 合并所有页面内容
        original_content = "\n\n".join(markdown_parts)
        
        # 处理图片嵌入
        if embed_images:
            final_content = replace_image_with_base64(original_content, local_image_dir)
        else:
            final_content = original_content
        
        logger.info(final_content)
        # 保存Markdown文件
        md_path = os.path.join(local_md_dir, f"{file_name}.md")
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(final_content)
        logger.info(f"Markdown文件已保存: {md_path}")
        
        # 生成输出文件路径（在output_dir根目录下也保存一份）
        output_md_path = os.path.join(output_dir, f"{file_name}.md")
        with open(output_md_path, 'w', encoding='utf-8') as f:
            f.write(final_content)
        
        logger.info(f"转换完成: {output_md_path}")
        
        # JSON转换（如果需要）
        json_data = None
        json_path = None
        if output_json:
            try:
                logger.info("开始转换为JSON格式...")
                json_data = parse_markdown_to_json(original_content)
                json_path = os.path.join(output_dir, f"{file_name}.json")
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=2)
                logger.info(f"JSON文件已保存: {json_path}")
                logger.info(f"文档类型: {json_data.get('document_type', 'unknown')}")
            except Exception as e:
                logger.exception(f"JSON转换失败: {e}")
                json_data = None
        
        return {
            'markdown_file': output_md_path,
            'json_file': json_path,
            'json_data': json_data,
            'content': final_content,
            'original_content': original_content
        }

    except Exception as e:
        logger.exception(f"转换过程出错: {e}")
        return None
    finally:
        # 清理临时PDF文件
        if pdf_path and pdf_path != input_file and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except:
                pass


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
            output_json=args.output_json
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