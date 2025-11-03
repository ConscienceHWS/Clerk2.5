# Copyright (c) Opendatalab. All rights reserved.

import argparse
import asyncio
import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

import aiofiles
from loguru import logger
from vllm.v1.engine.async_llm import AsyncLLM
from vllm.engine.arg_utils import AsyncEngineArgs
from pdf2image import convert_from_path
from PIL import Image
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


class OperationalCondition:
    """工况信息数据模型"""
    def __init__(self):
        self.monitorAt: str = ""  # 检测时间
        self.project: str = ""  # 项目名称
        self.name: str = ""  # 名称，如1#主变
        self.voltage: str = ""  # 电压范围
        self.current: str = ""  # 电流范围
        self.activePower: str = ""  # 有功功率
        self.reactivePower: str = ""  # 无功功率
    
    def to_dict(self):
        return {
            "monitorAt": self.monitorAt,
            "project": self.project,
            "name": self.name,
            "voltage": self.voltage,
            "current": self.current,
            "activePower": self.activePower,
            "reactivePower": self.reactivePower
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
        self.operationalConditions: List[OperationalCondition] = []
    
    def to_dict(self):
        return {
            "project": self.project,
            "standardReferences": self.standardReferences,
            "soundLevelMeterMode": self.soundLevelMeterMode,
            "soundCalibratorMode": self.soundCalibratorMode,
            "calibrationValueBefore": self.calibrationValueBefore,
            "calibrationValueAfter": self.calibrationValueAfter,
            "weather": [w.to_dict() for w in self.weather],
            "noise": [n.to_dict() for n in self.noise],
            "operationalConditions": [oc.to_dict() for oc in self.operationalConditions]
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


def extract_table_with_rowspan_colspan(markdown_content: str) -> List[List[List[str]]]:
    """提取表格数据，处理rowspan和colspan属性"""
    tables: List[List[List[str]]] = []
    table_matches = re.findall(r'<table>(.*?)</table>', markdown_content, re.DOTALL)
    logger.debug(f"[extract_table_with_rowspan_colspan] 共找到 {len(table_matches)} 个表格")
    
    for table_idx, table_content in enumerate(table_matches):
        tr_matches = re.findall(r'<tr[^>]*>(.*?)</tr>', table_content, re.DOTALL)
        logger.debug(f"[extract_table_with_rowspan_colspan] 表格{table_idx}, 行数: {len(tr_matches)}")
        
        if not tr_matches:
            continue
        
        # 用于存储rowspan的值（跨行的单元格值）
        rowspan_values = {}  # {(row_idx, col_idx): (value, remaining_rows)}
        
        # 先构建一个矩阵来存储所有单元格
        max_cols = 0
        table_matrix = []
        
        for row_idx, tr_content in enumerate(tr_matches):
            # 找到所有td标签，包括属性
            td_pattern = r'<td[^>]*>(.*?)</td>'
            td_matches_with_attrs = re.finditer(td_pattern, tr_content, re.DOTALL)
            
            row = []
            col_idx = 0
            
            for td_match in td_matches_with_attrs:
                full_td = td_match.group(0)
                cell_content = td_match.group(1)
                
                # 提取rowspan和colspan属性
                rowspan_match = re.search(r'rowspan=["\']?(\d+)["\']?', full_td)
                colspan_match = re.search(r'colspan=["\']?(\d+)["\']?', full_td)
                
                rowspan = int(rowspan_match.group(1)) if rowspan_match else 1
                colspan = int(colspan_match.group(1)) if colspan_match else 1
                
                # 解析单元格内容
                cell_text = parse_table_cell(cell_content)
                
                # 跳过被rowspan占用的列
                while (row_idx, col_idx) in rowspan_values:
                    row.append(rowspan_values[(row_idx, col_idx)][0])  # 使用rowspan的值
                    remaining = rowspan_values[(row_idx, col_idx)][1] - 1
                    if remaining > 0:
                        rowspan_values[(row_idx + 1, col_idx)] = (rowspan_values[(row_idx, col_idx)][0], remaining)
                    del rowspan_values[(row_idx, col_idx)]
                    col_idx += 1
                
                # 添加单元格内容
                for c in range(colspan):
                    row.append(cell_text if c == 0 else "")
                    
                    # 如果有rowspan，记录到后续行
                    if rowspan > 1 and c == 0:
                        rowspan_values[(row_idx + 1, col_idx)] = (cell_text, rowspan - 1)
                    
                    col_idx += 1
            
            # 处理剩余的被rowspan占用的列
            while (row_idx, col_idx) in rowspan_values:
                row.append(rowspan_values[(row_idx, col_idx)][0])
                remaining = rowspan_values[(row_idx, col_idx)][1] - 1
                if remaining > 0:
                    rowspan_values[(row_idx + 1, col_idx)] = (rowspan_values[(row_idx, col_idx)][0], remaining)
                del rowspan_values[(row_idx, col_idx)]
                col_idx += 1
            
            if row:
                table_matrix.append(row)
                max_cols = max(max_cols, len(row))
                logger.debug(f"[extract_table_with_rowspan_colspan] 表格{table_idx} 第{row_idx}行, 内容: {row}")
        
        # 统一列数（可选，确保每行列数一致）
        for row in table_matrix:
            while len(row) < max_cols:
                row.append("")
        
        if table_matrix:
            tables.append(table_matrix)
    
    logger.debug(f"[extract_table_with_rowspan_colspan] 总表格: {len(tables)}")
    return tables


def parse_operational_conditions(markdown_content: str) -> List[OperationalCondition]:
    """解析工况信息表格"""
    conditions: List[OperationalCondition] = []
    
    # 查找工况信息相关的表格
    if "附件2 工况信息" not in markdown_content and "工况信息" not in markdown_content:
        logger.debug("[工况信息] 未找到工况信息标识")
        return conditions
    
    # 提取表格数据（支持rowspan和colspan）
    tables = extract_table_with_rowspan_colspan(markdown_content)
    
    if not tables:
        logger.warning("[工况信息] 未能提取出任何表格内容")
        return conditions
    
    # 查找工况信息表格（通常包含"检测时间"、"电压"、"电流"等关键词）
    for table in tables:
        if not table or len(table) < 2:
            continue
        
        # 检查表头是否包含工况信息的关键词
        header_row = table[0]
        has_operational_keywords = any(
            keyword in " ".join(header_row)
            for keyword in ["检测时间", "电压", "电流", "有功功率", "无功功率", "项目"]
        )
        
        if not has_operational_keywords:
            continue
        
        logger.info(f"[工况信息] 找到工况信息表格，行数: {len(table)}")
        
        # 找到表头行的列索引
        header_row = table[0]
        monitor_at_idx = -1
        project_idx = -1
        name_idx = -1
        voltage_idx = -1
        current_idx = -1
        active_power_idx = -1
        reactive_power_idx = -1
        
        for idx, cell in enumerate(header_row):
            cell_lower = cell.lower()
            if "检测时间" in cell or "监测时间" in cell:
                monitor_at_idx = idx
            elif "项目" in cell:
                # 项目列可能有colspan，需要找到实际的列
                if project_idx == -1:
                    project_idx = idx
                # 检查下一列是否是名称列（如果项目列colspan=2，下一列可能是名称）
                if idx + 1 < len(header_row) and name_idx == -1:
                    next_cell = header_row[idx + 1]
                    if not any(k in next_cell.lower() for k in ["电压", "电流", "有功", "无功", "检测"]):
                        name_idx = idx + 1
            elif "电压" in cell or "电压(kv)" in cell_lower:
                voltage_idx = idx
            elif "电流" in cell or "电流(a)" in cell_lower:
                current_idx = idx
            elif "有功功率" in cell or ("有功" in cell and "功率" in cell):
                active_power_idx = idx
            elif "无功功率" in cell or ("无功" in cell and "功率" in cell):
                reactive_power_idx = idx
            elif ("名称" in cell or "主变" in cell) and name_idx == -1:
                name_idx = idx
        
        logger.debug(f"[工况信息] 列索引: 检测时间={monitor_at_idx}, 项目={project_idx}, 名称={name_idx}, "
                    f"电压={voltage_idx}, 电流={current_idx}, 有功功率={active_power_idx}, 无功功率={reactive_power_idx}")
        
        # 处理数据行（从第二行开始，第一行是表头）
        current_monitor_at = ""
        current_project = ""
        
        for row_idx in range(1, len(table)):
            row = table[row_idx]
            if len(row) < 4:  # 至少需要检测时间、项目、名称等基本字段
                continue
            
            # 检测时间
            if monitor_at_idx >= 0 and monitor_at_idx < len(row) and row[monitor_at_idx].strip():
                current_monitor_at = row[monitor_at_idx].strip()
            
            # 项目名称
            if project_idx >= 0 and project_idx < len(row) and row[project_idx].strip():
                current_project = row[project_idx].strip()
            
            # 名称（如1#主变）
            name_value = ""
            if name_idx >= 0 and name_idx < len(row):
                name_value = row[name_idx].strip()
            elif project_idx >= 0 and project_idx + 1 < len(row):
                # 如果名称列在项目列后面
                name_value = row[project_idx + 1].strip()
            
            # 只有当名称存在时才创建工况信息记录（因为有rowspan的情况）
            if name_value and any(k in name_value for k in ["主变", "#"]):
                oc = OperationalCondition()
                oc.monitorAt = current_monitor_at
                oc.project = current_project
                oc.name = name_value
                
                # 电压
                if voltage_idx >= 0 and voltage_idx < len(row):
                    oc.voltage = row[voltage_idx].strip()
                
                # 电流
                if current_idx >= 0 and current_idx < len(row):
                    oc.current = row[current_idx].strip()
                
                # 有功功率
                if active_power_idx >= 0 and active_power_idx < len(row):
                    oc.activePower = row[active_power_idx].strip()
                
                # 无功功率
                if reactive_power_idx >= 0 and reactive_power_idx < len(row):
                    oc.reactivePower = row[reactive_power_idx].strip()
                
                conditions.append(oc)
                logger.debug(f"[工况信息] 解析到: {oc.to_dict()}")
        
        # 只处理第一个匹配的表格
        if conditions:
            break
    
    logger.info(f"[工况信息] 共解析到 {len(conditions)} 条工况信息")
    return conditions


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


# ---------------------------- OCR识别功能 ----------------------------
# OCR工具路径配置
OCR_PYTHON_PATH = "/mnt/win_d/PaddleVL/venv/bin/python"
OCR_SCRIPT_PATH = "/mnt/win_d/PaddleVL/paddleocr_tool.py"
OCR_BASE_DIR = "/mnt/win_d/PaddleVL"  # PaddleVL 基础目录，用于解析相对路径


def ocr_extract_text_from_image(image: Image.Image, output_dir: Optional[str] = None) -> str:
    """使用外部OCR脚本从图片中提取文本"""
    if not os.path.exists(OCR_PYTHON_PATH):
        logger.warning(f"OCR Python路径不存在: {OCR_PYTHON_PATH}")
        return ""
    
    if not os.path.exists(OCR_SCRIPT_PATH):
        logger.warning(f"OCR脚本路径不存在: {OCR_SCRIPT_PATH}")
        return ""
    
    # 保存图片到临时文件
    temp_image_path = None
    temp_output_dir = None
    try:
        # 如果提供了output_dir，使用output_dir下的临时目录；否则使用系统临时目录
        if output_dir:
            temp_output_dir = os.path.join(output_dir, "ocr_temp")
            os.makedirs(temp_output_dir, exist_ok=True)
        else:
            temp_output_dir = tempfile.mkdtemp(prefix="ocr_output_")
        
        # 生成临时图片文件路径
        import uuid
        temp_image_filename = f"ocr_temp_{uuid.uuid4().hex}.png"
        temp_image_path = os.path.join(temp_output_dir, temp_image_filename)
        
        # 保存PIL Image到临时文件
        logger.debug(f"[OCR] 准备保存图片到: {temp_image_path}")
        image.save(temp_image_path, 'PNG')
        
        # 强制刷新文件系统缓存（确保文件写入磁盘）
        try:
            import gc
            gc.collect()
            os.sync() if hasattr(os, 'sync') else None
        except:
            pass
        
        # 等待一下确保文件写入完成
        import time
        time.sleep(0.1)
        
        # 确保文件保存完成
        if not os.path.exists(temp_image_path):
            logger.error(f"[OCR] 临时图片保存失败，文件不存在: {temp_image_path}")
            logger.error(f"[OCR] 临时目录内容: {os.listdir(temp_output_dir) if os.path.exists(temp_output_dir) else '目录不存在'}")
            return ""
        
        # 验证文件大小
        file_size = os.path.getsize(temp_image_path)
        if file_size == 0:
            logger.error(f"[OCR] 临时图片文件大小为0: {temp_image_path}")
            return ""
        
        # 使用绝对路径，避免路径问题
        temp_image_path = os.path.abspath(temp_image_path)
        logger.info(f"[OCR] 保存临时图片成功: {temp_image_path} (大小: {file_size} bytes)")
        logger.debug(f"[OCR] 调用OCR脚本: {OCR_PYTHON_PATH} {OCR_SCRIPT_PATH}")
        
        # 调用外部OCR脚本
        # 使用绝对路径参数，避免相对路径问题
        layout_model_path = os.path.join(OCR_BASE_DIR, 'model/PP-DocLayoutV2')
        vl_model_path = os.path.join(OCR_BASE_DIR, 'model/PaddleOCR-VL')
        
        # 确保模型路径存在
        if not os.path.exists(layout_model_path):
            logger.error(f"[OCR] 布局模型路径不存在: {layout_model_path}")
            return ""
        if not os.path.exists(vl_model_path):
            logger.error(f"[OCR] VL模型路径不存在: {vl_model_path}")
            return ""
        
        cmd = [
            OCR_PYTHON_PATH,
            OCR_SCRIPT_PATH,
            temp_image_path,
            '-o', temp_output_dir,
            '--layout_model', layout_model_path,
            '--vl_model', vl_model_path
        ]
        
        logger.info(f"[OCR] 执行命令: {' '.join(cmd)}")
        logger.info(f"[OCR] 工作目录: {OCR_BASE_DIR}")
        logger.info(f"[OCR] 输入图片: {temp_image_path}")
        logger.info(f"[OCR] 输出目录: {temp_output_dir}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,  # 增加到120秒超时（模型加载需要时间）
            cwd=OCR_BASE_DIR,  # 在 PaddleVL 基础目录运行，这样相对路径也能正常工作
            env=os.environ.copy()  # 复制当前环境变量
        )
        
        # 即使返回码不为0，也可能已经生成了文件（某些警告可能导致返回码非0）
        # 先尝试查找输出的Markdown文件
        image_basename = os.path.splitext(os.path.basename(temp_image_path))[0]
        md_filename = f"{image_basename}_page_1.md"
        md_path = os.path.join(temp_output_dir, md_filename)
        
        # 如果找不到文件，尝试查找所有md文件
        if not os.path.exists(md_path):
            md_files = [f for f in os.listdir(temp_output_dir) if f.endswith('.md')] if os.path.exists(temp_output_dir) else []
            if md_files:
                md_path = os.path.join(temp_output_dir, md_files[0])
                logger.info(f"[OCR] 找到Markdown文件: {md_path}")
            else:
                # 如果找不到文件且返回码非0，才报错
                if result.returncode != 0:
                    logger.error(f"[OCR] 脚本执行失败，返回码: {result.returncode}")
                    logger.error(f"[OCR] 标准输出:\n{result.stdout}")
                    logger.error(f"[OCR] 错误输出:\n{result.stderr}")
                    return ""
                else:
                    logger.warning(f"[OCR] 未找到输出的Markdown文件，输出目录: {temp_output_dir}")
                    logger.info(f"[OCR] 输出目录内容: {os.listdir(temp_output_dir) if os.path.exists(temp_output_dir) else '目录不存在'}")
                    return ""
        
        # 如果能找到文件，即使返回码非0也认为成功（可能是警告导致的）
        if result.returncode != 0:
            logger.warning(f"[OCR] 脚本返回码非0: {result.returncode}，但找到了输出文件，继续处理")
            logger.debug(f"[OCR] 标准输出: {result.stdout}")
            logger.debug(f"[OCR] 错误输出: {result.stderr}")
        else:
            logger.info(f"[OCR] 脚本执行成功")
            logger.debug(f"[OCR] 脚本输出: {result.stdout}")
        
        # 读取Markdown内容并提取纯文本
        with open(md_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        
        # 从Markdown中提取纯文本（移除Markdown格式）
        # 移除Markdown表格、代码块等格式，保留文本内容
        text = markdown_content
        # 移除Markdown表格标记
        text = re.sub(r'\|', ' ', text)
        # 移除多个空格
        text = re.sub(r'\s+', ' ', text)
        # 移除Markdown链接格式 [text](url) -> text
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        # 移除Markdown标题标记
        text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
        # 移除Markdown代码块
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`[^`]+`', '', text)
        
        extracted_text = text.strip()
        logger.debug(f"[OCR] 提取到文本: {extracted_text[:200]}...")
        return extracted_text
        
    except subprocess.TimeoutExpired:
        logger.error("[OCR] OCR脚本执行超时（60秒）")
        return ""
    except Exception as e:
        logger.exception(f"[OCR] OCR识别失败: {e}")
        return ""
    # finally:
        # 清理临时文件
        # try:
        #     if temp_image_path and os.path.exists(temp_image_path):
        #         os.unlink(temp_image_path)
        #     if temp_output_dir and os.path.exists(temp_output_dir):
        #         shutil.rmtree(temp_output_dir)
        # except Exception as e:
        #     logger.debug(f"[OCR] 清理临时文件失败: {e}")


def parse_noise_detection_record_from_ocr(ocr_text: str) -> Dict[str, str]:
    """从OCR文本中解析噪声检测记录的基本字段"""
    result = {
        "project": "",
        "standardReferences": "",
        "soundLevelMeterMode": "",
        "soundCalibratorMode": "",
        "calibrationValueBefore": "",
        "calibrationValueAfter": "",
        "weather": {}
    }
    
    if not ocr_text:
        return result
    
    # 按行分割文本，处理多行情况
    lines = [line.strip() for line in ocr_text.split('\n') if line.strip()]
    full_text = ' '.join(lines)
    
    # 项目名称 - 需要在"项目名称："和下一个字段之间提取
    # 项目名称后面可能是"检测依据"、"声级计"、"日期"等
    project_patterns = [
        r'项目名称[：:]\s*([^检测]+?)(?=(?:检测依据|监测依据|声级计|日期|项目编号|$))',
        r'项目名称[：:]\s*([^：:]+?)(?=(?:检测|声级|日期|项目编号|$))',
        r'项目名称[：:]\s*([^\n]+?)(?=\s*(?:检测依据|监测依据|声级计|日期))',
    ]
    for pattern in project_patterns:
        project_match = re.search(pattern, full_text)
        if project_match:
            result["project"] = project_match.group(1).strip()
            # 移除可能包含的其他字段标识
            result["project"] = re.sub(r'\s*(?:检测依据|监测依据|声级计|日期).*$', '', result["project"]).strip()
            break
    
    # 检测依据/监测依据 - 提取到下一个字段或行尾
    reference_patterns = [
        r'(?:检测依据|监测依据)[：:]\s*([^声级计]+?)(?=(?:声级计|日期|项目编号|气象条件|$))',
        r'(?:检测依据|监测依据)[：:]\s*([^\n]+?)(?=\s*(?:声级计|日期|气象条件))',
        r'(?:检测依据|监测依据)[：:]\s*([^\n]+)',
    ]
    for pattern in reference_patterns:
        reference_match = re.search(pattern, full_text)
        if reference_match:
            ref_text = reference_match.group(1).strip()
            # 移除可能的"声级计型号/编号"等后续内容
            ref_text = re.sub(r'\s*声级计.*$', '', ref_text).strip()
            # 移除可能的日期等后续内容
            ref_text = re.sub(r'\s*日期.*$', '', ref_text).strip()
            result["standardReferences"] = ref_text
            break
    
    # 声级计型号/编号 - 可能在同一行或下一行
    meter_patterns = [
        r'声级计型号[：:/\s]*编号[：:]\s*([^\n]+?)(?=(?:日期|检测|校准|气象条件|$))',
        r'声级计型号[：:]\s*([^\n]+?)(?=(?:日期|检测|校准|气象条件|$))',
        r'声级计[：:/\s]*编号[：:]\s*([^\n]+?)(?=(?:日期|检测|校准|气象条件|$))',
    ]
    for pattern in meter_patterns:
        meter_match = re.search(pattern, full_text)
        if meter_match:
            meter_text = meter_match.group(1).strip()
            # 移除"日期"等后续内容
            meter_text = re.sub(r'\s*日期.*$', '', meter_text).strip()
            if meter_text and meter_text not in ['___', '____', '']:
                result["soundLevelMeterMode"] = meter_text
                break
    
    # 声级计校准器型号
    calibrator_patterns = [
        r'(?:声级计校准器型号|声纹准器型号)[：:]\s*([^\n]+?)(?=(?:日期|检测|校准|气象条件|$))',
        r'校准器型号[：:]\s*([^\n]+?)(?=(?:日期|检测|校准|气象条件|$))',
    ]
    for pattern in calibrator_patterns:
        calibrator_match = re.search(pattern, full_text)
        if calibrator_match:
            calibrator_text = calibrator_match.group(1).strip()
            calibrator_text = re.sub(r'\s*日期.*$', '', calibrator_text).strip()
            if calibrator_text and calibrator_text not in ['___', '____', '']:
                result["soundCalibratorMode"] = calibrator_text
                break
    
    # 检测前校准值
    before_patterns = [
        r'检测前校准值[：:]\s*([^\n]+?)(?=(?:检测后|日期|气象条件|$))',
        r'检测前[：:]\s*校准值[：:]\s*([^\n]+)',
    ]
    for pattern in before_patterns:
        before_match = re.search(pattern, full_text)
        if before_match:
            before_text = before_match.group(1).strip()
            before_text = re.sub(r'\s*检测后.*$', '', before_text).strip()
            if before_text and before_text not in ['___', '____', '']:
                result["calibrationValueBefore"] = before_text
                break
    
    # 检测后校准值
    after_patterns = [
        r'检测后校准值[：:]\s*([^\n]+?)(?=(?:日期|气象条件|$))',
        r'检测后[：:]\s*校准值[：:]\s*([^\n]+)',
    ]
    for pattern in after_patterns:
        after_match = re.search(pattern, full_text)
        if after_match:
            after_text = after_match.group(1).strip()
            after_text = re.sub(r'\s*日期.*$', '', after_text).strip()
            if after_text and after_text not in ['___', '____', '']:
                result["calibrationValueAfter"] = after_text
                break
    
    # 气象条件 - 可能有多条记录
    # 查找所有包含日期、天气等信息的段落
    weather_sections = re.findall(r'(?:日期|天气|温度|湿度|风速|风向)[：:]?.*?(?=(?:日期|天气|温度|湿度|风速|风向)[：:]|$)', full_text, re.IGNORECASE)
    
    # 如果没有找到单独的气象条件段落，尝试从整段文本中提取
    if not weather_sections:
        # 尝试提取第一个日期相关的段落
        date_section = re.search(r'日期[：:]\s*([\d.\-]+).*?(?=(?:项目编号|项目名称|检测依据|$))', full_text, re.DOTALL)
        if date_section:
            weather_sections = [date_section.group(0)]
    
    if weather_sections:
        # 解析第一条气象记录（通常是最新的）
        weather_text = weather_sections[0]
        
        # 解析日期
        date_match = re.search(r'日期[：:]\s*([\d.\-]+)', weather_text)
        if date_match:
            result["weather"]["monitorAt"] = date_match.group(1).strip()
        
        # 解析天气
        weather_val_match = re.search(r'天气\s*([^\s温度湿度风速风向]+)', weather_text)
        if weather_val_match:
            result["weather"]["weather"] = weather_val_match.group(1).strip()
        
        # 解析温度（支持范围）
        temp_match = re.search(r'温度\s*([0-9.\-\s~]+)', weather_text)
        if temp_match:
            result["weather"]["temp"] = temp_match.group(1).strip()
        
        # 解析湿度（支持范围）
        humidity_match = re.search(r'湿度\s*([0-9.\-\s~]+)', weather_text)
        if humidity_match:
            result["weather"]["humidity"] = humidity_match.group(1).strip()
        
        # 解析风速（支持范围）
        wind_speed_match = re.search(r'风速\s*([0-9.\-\s~]+)', weather_text)
        if wind_speed_match:
            result["weather"]["windSpeed"] = wind_speed_match.group(1).strip()
        
        # 解析风向
        wind_dir_match = re.search(r'风向\s*([^\s温度湿度风速日期]+)', weather_text)
        if wind_dir_match:
            result["weather"]["windDirection"] = wind_dir_match.group(1).strip()
    
    logger.debug(f"[OCR解析] 原始文本: {ocr_text[:200]}")
    logger.debug(f"[OCR解析] 解析结果: {result}")
    return result


def parse_noise_detection_record(markdown_content: str, first_page_image: Optional[Image.Image] = None, output_dir: Optional[str] = None) -> NoiseDetectionRecord:
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
    
    # 解析工况信息
    operational_conditions = parse_operational_conditions(markdown_content)
    record.operationalConditions = operational_conditions
    
    # 如果字段为空且提供了首页图片，使用OCR补充识别
    needs_ocr = (
        (not record.project or not record.project.strip()) or
        (not record.standardReferences or not record.standardReferences.strip()) or
        (not record.soundLevelMeterMode or not record.soundLevelMeterMode.strip()) or
        (not record.soundCalibratorMode or not record.soundCalibratorMode.strip()) or
        (not record.calibrationValueBefore or not record.calibrationValueBefore.strip()) or
        (not record.calibrationValueAfter or not record.calibrationValueAfter.strip()) or
        (not record.weather or len(record.weather) == 0)
    )
    
    if needs_ocr and first_page_image:
        logger.info("[噪声检测] 检测到空字段，使用OCR补充识别...")
        
        # 裁剪首页指定区域（-t 255 -b 1155 -l 115 -r 115）
        try:
            ocr_image = crop_image(first_page_image, top=255, bottom=1155, left=115, right=115)
            
            # OCR识别
            ocr_text = ocr_extract_text_from_image(ocr_image, output_dir=output_dir)
            logger.info(ocr_text)

            if ocr_text:
                # 从OCR文本中解析字段
                ocr_result = parse_noise_detection_record_from_ocr(ocr_text)
                logger.info(ocr_result)
                # 填充空字段
                if (not record.project or not record.project.strip()) and ocr_result.get("project"):
                    record.project = ocr_result["project"]
                    logger.info(f"[OCR] 填充项目名称: {record.project}")
                
                if (not record.standardReferences or not record.standardReferences.strip()) and ocr_result.get("standardReferences"):
                    record.standardReferences = ocr_result["standardReferences"]
                    logger.info(f"[OCR] 填充检测依据: {record.standardReferences}")
                
                if (not record.soundLevelMeterMode or not record.soundLevelMeterMode.strip()) and ocr_result.get("soundLevelMeterMode"):
                    record.soundLevelMeterMode = ocr_result["soundLevelMeterMode"]
                    logger.info(f"[OCR] 填充声级计型号: {record.soundLevelMeterMode}")
                
                if (not record.soundCalibratorMode or not record.soundCalibratorMode.strip()) and ocr_result.get("soundCalibratorMode"):
                    record.soundCalibratorMode = ocr_result["soundCalibratorMode"]
                    logger.info(f"[OCR] 填充声级计校准器型号: {record.soundCalibratorMode}")
                
                if (not record.calibrationValueBefore or not record.calibrationValueBefore.strip()) and ocr_result.get("calibrationValueBefore"):
                    record.calibrationValueBefore = ocr_result["calibrationValueBefore"]
                    logger.info(f"[OCR] 填充检测前校准值: {record.calibrationValueBefore}")
                
                if (not record.calibrationValueAfter or not record.calibrationValueAfter.strip()) and ocr_result.get("calibrationValueAfter"):
                    record.calibrationValueAfter = ocr_result["calibrationValueAfter"]
                    logger.info(f"[OCR] 填充检测后校准值: {record.calibrationValueAfter}")
                
                # 填充气象条件
                if (not record.weather or len(record.weather) == 0) and ocr_result.get("weather"):
                    weather = WeatherData()
                    weather_data = ocr_result["weather"]
                    if weather_data.get("monitorAt"):
                        weather.monitorAt = weather_data["monitorAt"]
                    if weather_data.get("weather"):
                        weather.weather = weather_data["weather"]
                    if weather_data.get("temp"):
                        weather.temp = weather_data["temp"]
                    if weather_data.get("humidity"):
                        weather.humidity = weather_data["humidity"]
                    if weather_data.get("windSpeed"):
                        weather.windSpeed = weather_data["windSpeed"]
                    if weather_data.get("windDirection"):
                        weather.windDirection = weather_data["windDirection"]
                    
                    if any([weather.monitorAt, weather.weather, weather.temp, weather.humidity, weather.windSpeed, weather.windDirection]):
                        record.weather.append(weather)
                        logger.info(f"[OCR] 填充气象条件: {weather.to_dict()}")
            else:
                logger.warning("[OCR] 未能从OCR中提取到有效文本")
        except Exception as e:
            logger.exception(f"[OCR] 使用OCR补充识别失败: {e}")
    
    return record


def calculate_average(values: List[str]) -> str:
    """计算平均值，处理空值和无效值"""
    numeric_values = []
    for val in values:
        if val and val.strip():
            # 尝试提取数字（可能包含单位）
            try:
                # 移除可能的单位（如V/m, T等）和空格
                cleaned = re.sub(r'[^\d.\-]', '', val.strip())
                if cleaned:
                    num = float(cleaned)
                    numeric_values.append(num)
            except (ValueError, AttributeError):
                continue
    
    if numeric_values:
        avg = sum(numeric_values) / len(numeric_values)
        # 保留原始格式，如果是整数则返回整数格式
        if avg == int(avg):
            return str(int(avg))
        else:
            # 保留适当的小数位
            return f"{avg:.3f}".rstrip('0').rstrip('.')
    return ""


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
                
                # 电场强度
                if len(row) > 4: em.powerFrequencyEFieldStrength1 = row[4]
                if len(row) > 5: em.powerFrequencyEFieldStrength2 = row[5]
                if len(row) > 6: em.powerFrequencyEFieldStrength3 = row[6]
                if len(row) > 7: em.powerFrequencyEFieldStrength4 = row[7]
                if len(row) > 8: em.powerFrequencyEFieldStrength5 = row[8]
                if len(row) > 9: em.avgPowerFrequencyEFieldStrength = row[9]
                
                # 磁感应强度
                if len(row) > 10: em.powerFrequencyMagneticDensity1 = row[10]
                if len(row) > 11: em.powerFrequencyMagneticDensity2 = row[11]
                if len(row) > 12: em.powerFrequencyMagneticDensity3 = row[12]
                if len(row) > 13: em.powerFrequencyMagneticDensity4 = row[13]
                if len(row) > 14: em.powerFrequencyMagneticDensity5 = row[14]
                if len(row) > 15: em.avgPowerFrequencyMagneticDensity = row[15]
                
                # 如果平均电场强度为空，则计算平均值
                if not em.avgPowerFrequencyEFieldStrength or not em.avgPowerFrequencyEFieldStrength.strip():
                    field_values = [
                        em.powerFrequencyEFieldStrength1,
                        em.powerFrequencyEFieldStrength2,
                        em.powerFrequencyEFieldStrength3,
                        em.powerFrequencyEFieldStrength4,
                        em.powerFrequencyEFieldStrength5
                    ]
                    calculated_avg = calculate_average(field_values)
                    if calculated_avg:
                        em.avgPowerFrequencyEFieldStrength = calculated_avg
                        logger.debug(f"计算平均电场强度: {calculated_avg} (基于前5个值)")
                
                # 如果平均磁感应强度为空，则计算平均值
                if not em.avgPowerFrequencyMagneticDensity or not em.avgPowerFrequencyMagneticDensity.strip():
                    density_values = [
                        em.powerFrequencyMagneticDensity1,
                        em.powerFrequencyMagneticDensity2,
                        em.powerFrequencyMagneticDensity3,
                        em.powerFrequencyMagneticDensity4,
                        em.powerFrequencyMagneticDensity5
                    ]
                    calculated_avg = calculate_average(density_values)
                    if calculated_avg:
                        em.avgPowerFrequencyMagneticDensity = calculated_avg
                        logger.debug(f"计算平均磁感应强度: {calculated_avg} (基于前5个值)")
                
                record.electricMagnetic.append(em)
    
    return record


def parse_markdown_to_json(markdown_content: str, first_page_image: Optional[Image.Image] = None, output_dir: Optional[str] = None) -> Dict[str, Any]:
    """将Markdown内容转换为JSON"""
    doc_type = detect_document_type(markdown_content)
    
    if doc_type == "noise_detection":
        data = parse_noise_detection_record(markdown_content, first_page_image, output_dir).to_dict()
        return {"document_type": doc_type, "data": data}
    
    if doc_type == "electromagnetic_detection":
        data = parse_electromagnetic_detection_record(markdown_content).to_dict()
        return {"document_type": doc_type, "data": data}
    
    return {"document_type": "unknown", "data": {}, "error": "无法识别的文档类型"}


# ---------------------------- 图片裁剪功能 ----------------------------
def crop_image(image: Image.Image, top=0, bottom=0, left=0, right=0) -> Image.Image:
    """
    裁剪图片
    
    Args:
        image: PIL Image对象
        top: 上方裁剪像素数
        bottom: 下方裁剪像素数
        left: 左侧裁剪像素数
        right: 右侧裁剪像素数
    
    Returns:
        裁剪后的PIL Image对象
    """
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    width, height = image.size
    logger.debug(f"原图尺寸: {width} x {height}")
    
    # 计算裁剪区域 (left, top, right, bottom)
    crop_box = (left, top, width - right, height - bottom)
    
    # 验证裁剪参数
    new_width = width - left - right
    new_height = height - top - bottom
    
    if new_width <= 0 or new_height <= 0:
        logger.warning(f"裁剪后的图片尺寸无效: {new_width} x {new_height}，使用原图")
        return image
    
    if left + right >= width or top + bottom >= height:
        logger.warning(f"裁剪区域超出图片范围，使用原图")
        return image
    
    # 执行裁剪
    cropped_img = image.crop(crop_box)
    logger.debug(f"裁剪后尺寸: {cropped_img.size}")
    
    return cropped_img


class MinerUPDFProcessor:
    """使用vllm异步引擎处理PDF的处理器"""
    
    def __init__(self, model_name="OpenDataLab/MinerU2.5-2509-1.2B", gpu_memory_utilization=0.5):
        """初始化vllm异步引擎和MinerUClient"""
        self.async_llm = AsyncLLM.from_engine_args(
            AsyncEngineArgs(
                model=model_name,
                logits_processors=[MinerULogitsProcessor],
                gpu_memory_utilization=gpu_memory_utilization,
                trust_remote_code=True
            )
        )
        self.client = MinerUClient(
            backend="vllm-async-engine",
            vllm_async_llm=self.async_llm
        )
    
    async def shutdown(self):
        """关闭异步LLM引擎"""
        if self.async_llm:
            await self.async_llm.shutdown()
    
    async def process_pdf_pages(self, pdf_path, max_pages=None, dpi=200, use_split=False):
        """
        处理PDF的页面，返回提取的文本块列表（异步版本）
        
        Args:
            pdf_path: PDF文件路径
            max_pages: 最大处理页数
            dpi: 图片DPI
            use_split: 是否使用图片分割提高精度
        
        Returns:
            处理结果列表
        """
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
                
                if use_split:
                    # 使用图片分割提高精度
                    # 1. 先处理标题区域（用于识别类型）
                    # 标题区域：-t 135 -b 1375 -l 540 -r 540
                    logger.info("处理标题区域（用于识别文档类型）...")
                    title_image = crop_image(image, top=135, bottom=1375, left=540, right=540)
                    title_blocks = await self.client.aio_two_step_extract(title_image)
                    title_markdown = self.blocks_to_markdown(title_blocks)
                    
                    # 2. 再处理表体区域（用于提取数据）
                    # 表体区域：-t 255 -b 275 -l 115 -r 115
                    logger.info("处理表体区域（用于提取数据）...")
                    body_image = crop_image(image, top=255, bottom=275, left=115, right=115)
                    body_blocks = await self.client.aio_two_step_extract(body_image)
                    body_markdown = self.blocks_to_markdown(body_blocks)
                    
                    # 合并标题和表体的内容
                    combined_markdown = title_markdown + "\n\n" + body_markdown
                    
                    results.append({
                        "page": i + 1,
                        "extracted_blocks": combined_markdown,
                        "title_markdown": title_markdown,
                        "body_markdown": body_markdown
                    })
                else:
                    # 原有方式：处理整页
                    extracted_blocks = await self.client.aio_two_step_extract(image)
                    results.append({
                        "page": i + 1,
                        "extracted_blocks": extracted_blocks
                    })
            
            return results
        except Exception as e:
            logger.exception(f"PDF处理失败: {e}")
            return None
    
    def blocks_to_markdown(self, extracted_blocks):
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
    output_json=False,
    use_split=False
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

    processor = None
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
        if use_split:
            logger.info("使用图片分割模式提高识别精度")
        results = await processor.process_pdf_pages(pdf_path, max_pages=max_pages, dpi=dpi, use_split=use_split)
        
        if not results:
            logger.error("PDF处理失败")
            return None
        
        # 将所有页面的内容合并为Markdown
        markdown_parts = []
        
        # 获取PDF的图片（用于保存和OCR）
        pdf_images = []
        first_page_image = None
        try:
            if embed_images or output_json:
                # 获取PDF的图片（用于保存和OCR）
                pdf_images = convert_from_path(pdf_path, dpi=dpi)
                if max_pages:
                    pdf_images = pdf_images[:max_pages]
                
                # 保存第一页图片用于OCR（如果是噪声检测表）
                if pdf_images and output_json:
                    first_page_image = pdf_images[0]
        except Exception as e:
            logger.warning(f"无法加载PDF图片: {e}")
            pdf_images = []
        
        for i, result in enumerate(results):
            page_num = result['page']
            
            # 如果使用了图片分割，extracted_blocks已经是markdown字符串
            if use_split and isinstance(result.get('extracted_blocks'), str):
                page_markdown = result['extracted_blocks']
                # 可以单独使用标题和表体的结果
                if 'title_markdown' in result:
                    logger.debug(f"第 {page_num} 页标题区域识别结果: {result['title_markdown'][:100]}...")
                if 'body_markdown' in result:
                    logger.debug(f"第 {page_num} 页表体区域识别结果: {result['body_markdown'][:100]}...")
            else:
                extracted_blocks = result['extracted_blocks']
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
                # 如果是噪声检测表，传递第一页图片用于OCR补充识别
                json_data = parse_markdown_to_json(original_content, first_page_image=first_page_image, output_dir=output_dir)
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
        # 关闭异步LLM引擎
        if processor:
            try:
                await processor.shutdown()
            except Exception as e:
                logger.warning(f"关闭异步LLM引擎失败: {e}")
        
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