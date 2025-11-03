# Copyright (c) Opendatalab. All rights reserved.

"""OCR文本提取模块"""

from typing import Optional
from PIL import Image
from ..utils.logging_config import get_logger

logger = get_logger("pdf_converter.ocr.extractor")
import os
import re
import subprocess
import tempfile
import time
import uuid

from ..config import OCR_PYTHON_PATH, OCR_SCRIPT_PATH, OCR_BASE_DIR


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
        
        # 使用绝对路径的输出目录
        temp_output_dir_abs = os.path.abspath(temp_output_dir)
        
        cmd = [
            OCR_PYTHON_PATH,
            OCR_SCRIPT_PATH,
            temp_image_path,
            '-o', temp_output_dir_abs,  # 使用绝对路径
            '--layout_model', layout_model_path,
            '--vl_model', vl_model_path
        ]
        
        logger.info(f"[OCR] 执行命令: {' '.join(cmd)}")
        logger.info(f"[OCR] 工作目录: {OCR_BASE_DIR}")
        logger.info(f"[OCR] 输入图片: {temp_image_path}")
        logger.info(f"[OCR] 输出目录: {temp_output_dir_abs}")
        
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
        # 使用绝对路径确保正确查找
        temp_output_dir_abs = os.path.abspath(temp_output_dir)
        
        image_basename = os.path.splitext(os.path.basename(temp_image_path))[0]
        md_filename = f"{image_basename}_page_1.md"
        md_path = os.path.join(temp_output_dir_abs, md_filename)
        
        # 如果找不到文件，尝试查找所有md文件
        if not os.path.exists(md_path):
            if os.path.exists(temp_output_dir_abs):
                # 查找所有md文件
                md_files = [f for f in os.listdir(temp_output_dir_abs) if f.endswith('.md')]
                if md_files:
                    # 优先查找包含图片basename的文件
                    matching_files = [f for f in md_files if image_basename in f]
                    if matching_files:
                        md_path = os.path.join(temp_output_dir_abs, matching_files[0])
                    else:
                        md_path = os.path.join(temp_output_dir_abs, md_files[0])
                    logger.info(f"[OCR] 找到Markdown文件: {md_path}")
                else:
                    # 如果找不到md文件，检查输出目录内容
                    logger.warning(f"[OCR] 输出目录中未找到.md文件")
                    logger.info(f"[OCR] 输出目录内容: {os.listdir(temp_output_dir_abs)}")
                    # 检查是否返回码非0
                    if result.returncode != 0:
                        logger.error(f"[OCR] 脚本执行失败，返回码: {result.returncode}")
                        logger.error(f"[OCR] 标准输出:\n{result.stdout}")
                        logger.error(f"[OCR] 错误输出:\n{result.stderr}")
                        return ""
                    else:
                        logger.warning(f"[OCR] 未找到输出的Markdown文件，输出目录: {temp_output_dir_abs}")
                        return ""
            else:
                logger.error(f"[OCR] 输出目录不存在: {temp_output_dir_abs}")
                if result.returncode != 0:
                    logger.error(f"[OCR] 脚本执行失败，返回码: {result.returncode}")
                    logger.error(f"[OCR] 标准输出:\n{result.stdout}")
                    logger.error(f"[OCR] 错误输出:\n{result.stderr}")
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
        
        # 从Markdown中提取纯文本
        # 如果包含HTML表格，保留HTML格式（用于更精确的解析）
        if '<table' in markdown_content or '<td' in markdown_content:
            # 保留HTML格式，后续在解析函数中处理
            extracted_text = markdown_content
            logger.debug(f"[OCR] 提取到HTML表格文本: {extracted_text[:200]}...")
        else:
            # 从Markdown中提取纯文本（移除Markdown格式）
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


