# Copyright (c) Opendatalab. All rights reserved.

"""
PDF转换工具 FastAPI 版本 v2 - 使用外部API接口
"""

import asyncio
import os
import shutil
import tempfile
import uuid
import base64
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
import json
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing_extensions import Annotated, Literal

from ..processor.converter import convert_to_markdown
from ..utils.logging_config import get_logger

# 尝试导入配置，如果不存在则使用默认值
try:
    from ..config import (
        DEFAULT_MODEL_NAME, DEFAULT_GPU_MEMORY_UTILIZATION, DEFAULT_DPI, DEFAULT_MAX_PAGES,
        DEFAULT_API_URL, DEFAULT_BACKEND, DEFAULT_PARSE_METHOD, DEFAULT_START_PAGE_ID,
        DEFAULT_END_PAGE_ID, DEFAULT_LANGUAGE, DEFAULT_RESPONSE_FORMAT_ZIP,
        DEFAULT_RETURN_MIDDLE_JSON, DEFAULT_RETURN_MODEL_OUTPUT, DEFAULT_RETURN_MD,
        DEFAULT_RETURN_IMAGES, DEFAULT_RETURN_CONTENT_LIST, DEFAULT_SERVER_URL
    )
except ImportError:
    # 如果配置不存在，使用默认值
    DEFAULT_MODEL_NAME = "OpenDataLab/MinerU2.5-2509-1.2B"
    DEFAULT_GPU_MEMORY_UTILIZATION = 0.9
    DEFAULT_DPI = 200
    DEFAULT_MAX_PAGES = 10
    DEFAULT_API_URL = os.getenv("API_URL", "http://192.168.2.3:8000")
    DEFAULT_BACKEND = os.getenv("BACKEND", "vlm-vllm-async-engine")
    DEFAULT_PARSE_METHOD = os.getenv("PARSE_METHOD", "auto")
    DEFAULT_START_PAGE_ID = int(os.getenv("START_PAGE_ID", "0"))
    DEFAULT_END_PAGE_ID = int(os.getenv("END_PAGE_ID", "99999"))
    DEFAULT_LANGUAGE = os.getenv("LANGUAGE", "ch")
    DEFAULT_RESPONSE_FORMAT_ZIP = os.getenv("RESPONSE_FORMAT_ZIP", "true").lower() == "true"
    DEFAULT_RETURN_MIDDLE_JSON = os.getenv("RETURN_MIDDLE_JSON", "false").lower() == "true"
    DEFAULT_RETURN_MODEL_OUTPUT = os.getenv("RETURN_MODEL_OUTPUT", "true").lower() == "true"
    DEFAULT_RETURN_MD = os.getenv("RETURN_MD", "true").lower() == "true"
    DEFAULT_RETURN_IMAGES = os.getenv("RETURN_IMAGES", "true").lower() == "true"  # 默认启用，以便PaddleOCR备用解析可以使用
    DEFAULT_RETURN_CONTENT_LIST = os.getenv("RETURN_CONTENT_LIST", "false").lower() == "true"
    DEFAULT_SERVER_URL = os.getenv("SERVER_URL", "string")

# 初始化日志
# v2 使用简化的日志配置，从 v1 复用或使用 loguru
try:
    # 尝试导入 v1 的日志初始化函数
    import sys
    from pathlib import Path
    v1_path = Path(__file__).parent.parent.parent / "pdf_converter"
    if str(v1_path.parent) not in sys.path:
        sys.path.insert(0, str(v1_path.parent))
    from pdf_converter.utils.logging_config import init_logging
    init_logging(
        log_dir=os.getenv("PDF_CONVERTER_LOG_DIR", "./logs"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_to_file=True,
        log_to_console=True
    )
except Exception:
    # 如果无法导入，直接使用 get_logger（会使用 loguru 后备）
    pass

# 获取日志记录器
logger = get_logger("pdf_converter_v2.api")

app = FastAPI(
    title="PDF转换工具API v2",
    description="将PDF转换为Markdown和JSON格式（使用外部API）",
    version="2.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制为特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 存储任务状态
task_status = {}


class ConversionRequest(BaseModel):
    """转换请求模型（v2 精简版）"""
    # 新增：强制文档类型（正式全称）
    doc_type: Optional[str] = None


class ConversionResponse(BaseModel):
    """转换响应模型"""
    task_id: str
    status: str
    message: str
    markdown_file: Optional[str] = None
    json_file: Optional[str] = None
    document_type: Optional[str] = None


class TaskStatus(BaseModel):
    """任务状态模型"""
    task_id: str
    status: str  # pending, processing, completed, failed
    message: str
    progress: Optional[float] = None
    markdown_file: Optional[str] = None
    json_file: Optional[str] = None
    document_type: Optional[str] = None
    error: Optional[str] = None


class OCRRequest(BaseModel):
    """OCR识别请求模型"""
    image_base64: str  # base64编码的图片数据
    image_format: Optional[str] = "png"  # 图片格式：png, jpg, jpeg


class OCRResponse(BaseModel):
    """OCR识别响应模型"""
    success: bool
    texts: Optional[List[str]] = None  # 识别出的文本列表
    full_text: Optional[str] = None  # 完整的段落文本（带段落分割）
    message: Optional[str] = None
    error: Optional[str] = None


@app.get("/")
async def root():
    """API根路径"""
    return {
        "name": "PDF转换工具API",
        "version": "2.0.0",
        "description": "将PDF/图片转换为Markdown和JSON格式（使用外部API）",
        "workflow": {
            "step1": "POST /convert - 上传文件，立即返回 task_id（不等待处理）",
            "step2": "GET /task/{task_id} - 轮询查询任务状态",
            "step3a": "GET /task/{task_id}/json - 任务完成后直接获取JSON数据（推荐）",
            "step3b": "GET /download/{task_id}/json - 任务完成后下载JSON文件",
            "step4": "DELETE /task/{task_id} - (可选) 删除任务清理临时文件"
        },
        "endpoints": {
            "POST /convert": "转换PDF/图片文件（异步，立即返回task_id）",
            "GET /task/{task_id}": "查询任务状态（轮询接口）",
            "GET /task/{task_id}/json": "直接获取JSON数据（返回JSON对象，不下载文件）",
            "GET /download/{task_id}/markdown": "下载Markdown文件",
            "GET /download/{task_id}/json": "下载JSON文件",
            "DELETE /task/{task_id}": "删除任务及其临时文件",
            "GET /health": "健康检查"
        }
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "service": "pdf_converter_v2"}


async def process_conversion_task(
    task_id: str,
    file_path: str,
    output_dir: str,
    request: ConversionRequest
):
    """
    后台处理转换任务
    
    注意：这个函数在响应返回给客户端之后才会执行
    """
    try:
        logger.info(f"[任务 {task_id}] 后台任务开始执行...")
        task_status[task_id]["status"] = "processing"
        task_status[task_id]["message"] = "开始处理文件..."
        
        logger.info(f"[任务 {task_id}] 开始处理: {file_path}")
        
        # 执行转换（v2 使用外部API）
        # v2 特有的参数通过配置或环境变量获取
        result = await convert_to_markdown(
            input_file=file_path,
            output_dir=output_dir,
            # v2: 去除max_pages、公式/表格等前端可调参数
            is_ocr=False,
            formula_enable=True,
            table_enable=True,
            language=DEFAULT_LANGUAGE,
            backend=DEFAULT_BACKEND,
            url=DEFAULT_API_URL,
            # v2: 固定为 False
            embed_images=False,
            output_json=True,
            start_page_id=DEFAULT_START_PAGE_ID,
            end_page_id=DEFAULT_END_PAGE_ID,
            parse_method=DEFAULT_PARSE_METHOD,
            server_url=DEFAULT_SERVER_URL,
            response_format_zip=DEFAULT_RESPONSE_FORMAT_ZIP,
            return_middle_json=DEFAULT_RETURN_MIDDLE_JSON,
            return_model_output=DEFAULT_RETURN_MODEL_OUTPUT,
            return_md=DEFAULT_RETURN_MD,
            return_images=DEFAULT_RETURN_IMAGES,
            return_content_list=DEFAULT_RETURN_CONTENT_LIST,
            forced_document_type=request.doc_type
        )
        
        if result:
            task_status[task_id]["status"] = "completed"
            task_status[task_id]["message"] = "转换成功"
            task_status[task_id]["markdown_file"] = result.get("markdown_file")
            task_status[task_id]["json_file"] = result.get("json_file")
            # 保存JSON数据内容，以便直接返回
            if result.get("json_data"):
                task_status[task_id]["json_data"] = result["json_data"]
                task_status[task_id]["document_type"] = result["json_data"].get("document_type")
            logger.info(f"[任务 {task_id}] 转换成功")
        else:
            task_status[task_id]["status"] = "failed"
            task_status[task_id]["message"] = "转换失败"
            task_status[task_id]["error"] = "转换返回None"
            logger.error(f"[任务 {task_id}] 转换失败")
            
    except Exception as e:
        task_status[task_id]["status"] = "failed"
        task_status[task_id]["message"] = f"处理出错: {str(e)}"
        task_status[task_id]["error"] = str(e)
        logger.exception(f"[任务 {task_id}] 处理失败: {e}")
    # 注意：不再在转换完成后立即删除上传的文件
    # 文件将保留在临时目录中，直到用户调用 DELETE /task/{task_id} 接口时才清理
    # 这样可以方便用户查看上传的文件内容


@app.post("/convert", response_model=ConversionResponse)
async def convert_file(
    file: Annotated[UploadFile, File(description="上传的PDF或图片文件")],
    # 新增：类型参数（英文传参） noiseRec | emRec | equipLog | opStatus
    type: Annotated[Optional[Literal["noiseRec", "emRec", "opStatus"]], Form(description="文档类型：noiseRec | emRec | opStatus")] = None,
):
    """
    转换PDF/图片文件（异步处理）
    
    工作流程：
    1. 接收文件并生成task_id
    2. 立即返回task_id（不等待任何处理）
    3. 后台异步执行转换任务（调用外部API）
    4. 客户端使用task_id轮询状态或直接获取结果
    
    - **file**: 上传的文件（PDF或图片）
    - **type**: 文档类型（noiseRec | emRec | opStatus）
    
    注意：v2 版本内部使用外部API进行转换，v2特有的配置参数（如API URL、backend等）
    通过环境变量或配置文件设置，不通过API参数传入。
    """
    # 生成任务ID
    task_id = str(uuid.uuid4())
    
    # 创建临时目录和输出目录
    temp_dir = tempfile.mkdtemp(prefix=f"pdf_converter_v2_{task_id}_")
    output_dir = os.path.join(temp_dir, "output")
    os.makedirs(output_dir, exist_ok=True)
    
    # 保存上传的文件
    # 获取原始文件名，如果没有则使用默认名称
    original_filename = file.filename or "uploaded_file"
    
    # 如果文件名没有扩展名，尝试从Content-Type推断
    file_path = os.path.join(temp_dir, original_filename)
    if not Path(original_filename).suffix:
        # 尝试从Content-Type获取扩展名
        content_type = file.content_type or ""
        extension_map = {
            "application/pdf": ".pdf",
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
        }
        ext = extension_map.get(content_type)
        if ext:
            file_path = os.path.join(temp_dir, f"{original_filename}{ext}")
            logger.info(f"[任务 {task_id}] 从Content-Type推断扩展名: {ext}")
    
    try:
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        logger.info(f"[任务 {task_id}] 文件已保存: {file_path} ({len(content)} bytes)")
        
        # 如果保存后文件名仍然没有扩展名，尝试通过文件内容检测并重命名
        if not Path(file_path).suffix:
            from ..utils.paddleocr_fallback import detect_file_type
            detected_type = detect_file_type(file_path)
            if detected_type:
                ext_map = {
                    "pdf": ".pdf",
                    "png": ".png",
                    "jpeg": ".jpg",
                }
                ext = ext_map.get(detected_type)
                if ext:
                    new_file_path = file_path + ext
                    os.rename(file_path, new_file_path)
                    file_path = new_file_path
                    logger.info(f"[任务 {task_id}] 通过文件内容检测到类型 {detected_type}，重命名为: {file_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存文件失败: {str(e)}")
    
    # 计算页数并限制：>20页直接报错；图片按1页处理
    try:
        suffix = (Path(file_path).suffix or "").lower()
        pages = 1
        if suffix == ".pdf":
            # 粗略统计：基于PDF标记
            with open(file_path, "rb") as pf:
                pdf_bytes = pf.read()
                try:
                    pages = pdf_bytes.count(b"/Type /Page")
                    if pages <= 0:
                        pages = 1
                except Exception:
                    pages = 1
        else:
            # 常见图片格式视为单页
            pages = 1
        if pages > 20:
            # 清理临时目录后报错
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
            raise HTTPException(status_code=400, detail="文件页数超过20页，拒绝处理")
        logger.info(f"[任务 {task_id}] 页数评估: {pages}")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[任务 {task_id}] 页数评估失败，按1页处理: {e}")
    
    # 初始化任务状态
    task_status[task_id] = {
        "status": "pending",
        "message": "任务已创建",
        "progress": 0.0,
        "markdown_file": None,
        "json_file": None,
        "json_data": None,  # 存储JSON数据内容
        "document_type": None,
        "error": None,
        "temp_dir": temp_dir,
        "output_dir": output_dir,
        "file_path": file_path  # 保存上传文件的路径，方便查看
    }
    
    # 处理类型参数映射
    type_map = {
        "noiseRec": "noiseMonitoringRecord",
        "emRec": "electromagneticTestRecord",
        "opStatus": "operatingConditionInfo",
    }
    doc_type = None
    if type:
        if type not in type_map:
            # 清理临时目录后报错
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
            raise HTTPException(status_code=400, detail="无效的type参数")
        doc_type = type_map[type]

    # 创建请求对象（v2 精简）
    request = ConversionRequest(
        doc_type=doc_type,
    )
    
    # 使用 asyncio.create_task 创建后台任务，确保立即返回
    task = asyncio.create_task(
        process_conversion_task(
            task_id,
            file_path,
            output_dir,
            request
        )
    )
    
    # 立即返回task_id，不等待任何处理
    logger.info(f"[任务 {task_id}] 任务已创建并添加到后台，立即返回task_id")
    return ConversionResponse(
        task_id=task_id,
        status="pending",
        message="任务已创建，正在后台处理中，请使用task_id查询状态",
        markdown_file=None,
        json_file=None,
        document_type=None
    )


@app.get("/task/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """
    查询任务状态（轮询接口）
    
    客户端应定期调用此接口查询任务状态，直到状态变为 "completed" 或 "failed"
    
    - **task_id**: 任务ID（从 /convert 接口返回）
    
    状态说明：
    - **pending**: 等待处理
    - **processing**: 正在处理中
    - **completed**: 处理完成，可以使用 /task/{task_id}/json 获取JSON数据
    - **failed**: 处理失败，查看 error 字段获取错误信息
    """
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    status_info = task_status[task_id]
    return TaskStatus(
        task_id=task_id,
        status=status_info["status"],
        message=status_info["message"],
        progress=status_info.get("progress"),
        markdown_file=status_info.get("markdown_file"),
        json_file=status_info.get("json_file"),
        document_type=status_info.get("document_type"),
        error=status_info.get("error")
    )


@app.get("/download/{task_id}/markdown")
async def download_markdown(task_id: str):
    """
    下载Markdown文件
    
    - **task_id**: 任务ID
    """
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    status_info = task_status[task_id]
    if status_info["status"] != "completed":
        raise HTTPException(status_code=400, detail="任务尚未完成")
    
    markdown_file = status_info.get("markdown_file")
    if not markdown_file or not os.path.exists(markdown_file):
        raise HTTPException(status_code=404, detail="Markdown文件不存在")
    
    return FileResponse(
        markdown_file,
        media_type="text/markdown",
        filename=os.path.basename(markdown_file)
    )


@app.get("/task/{task_id}/json")
async def get_json(task_id: str):
    """
    直接获取JSON数据（返回JSON内容，不下载文件）
    
    - **task_id**: 任务ID
    
    返回：JSON格式的数据对象，包含解析后的文档内容
    """
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    status_info = task_status[task_id]
    
    if status_info["status"] == "pending" or status_info["status"] == "processing":
        raise HTTPException(status_code=400, detail="任务尚未完成，请稍后再试")
    
    if status_info["status"] == "failed":
        raise HTTPException(status_code=400, detail=f"任务失败: {status_info.get('error', '未知错误')}")
    
    json_data = status_info.get("json_data")
    if not json_data:
        # 如果没有保存JSON数据，尝试从文件读取
        json_file = status_info.get("json_file")
        if json_file and os.path.exists(json_file):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
            except Exception as e:
                logger.error(f"[任务 {task_id}] 读取JSON文件失败: {e}")
                raise HTTPException(status_code=500, detail="读取JSON文件失败")
        else:
            raise HTTPException(status_code=404, detail="JSON数据不存在（任务可能没有生成JSON数据）")
    
    return JSONResponse(content=json_data)


@app.get("/download/{task_id}/json")
async def download_json(task_id: str):
    """
    下载JSON文件（返回文件下载）
    
    - **task_id**: 任务ID
    """
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    status_info = task_status[task_id]
    if status_info["status"] != "completed":
        raise HTTPException(status_code=400, detail="任务尚未完成")
    
    json_file = status_info.get("json_file")
    if not json_file or not os.path.exists(json_file):
        raise HTTPException(status_code=404, detail="JSON文件不存在")
    
    return FileResponse(
        json_file,
        media_type="application/json",
        filename=os.path.basename(json_file)
    )


@app.delete("/task/{task_id}")
async def delete_task(task_id: str):
    """
    删除任务及其临时文件
    
    - **task_id**: 任务ID
    """
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    status_info = task_status[task_id]
    temp_dir = status_info.get("temp_dir")
    
    # 清理临时目录
    if temp_dir and os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
            logger.info(f"[任务 {task_id}] 临时目录已清理: {temp_dir}")
        except Exception as e:
            logger.warning(f"[任务 {task_id}] 清理临时目录失败: {e}")
    
    # 删除任务状态
    del task_status[task_id]
    
    return {"message": "任务已删除"}


@app.post("/ocr", response_model=OCRResponse)
async def ocr_image(request: OCRRequest):
    """
    对base64编码的图片进行OCR识别
    
    - **image_base64**: base64编码的图片数据（可以包含data:image/xxx;base64,前缀）
    - **image_format**: 图片格式（png, jpg, jpeg），默认为png
    
    返回识别出的文本列表
    """
    temp_dir = None
    image_path = None
    
    try:
        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix=f"pdf_converter_ocr_{uuid.uuid4()}_")
        logger.info(f"[OCR] 创建临时目录: {temp_dir}")
        
        # 解码base64数据
        image_base64 = request.image_base64.strip()
        
        # 移除可能的数据URI前缀（如 data:image/png;base64,）
        if "," in image_base64:
            image_base64 = image_base64.split(",")[-1]
        
        try:
            image_bytes = base64.b64decode(image_base64)
            logger.info(f"[OCR] Base64解码成功，图片大小: {len(image_bytes)} bytes")
        except Exception as e:
            logger.error(f"[OCR] Base64解码失败: {e}")
            return OCRResponse(
                success=False,
                error=f"Base64解码失败: {str(e)}",
                message="无法解码base64图片数据"
            )
        
        # 确定图片格式和扩展名
        image_format = request.image_format.lower() if request.image_format else "png"
        if image_format not in ["png", "jpg", "jpeg"]:
            image_format = "png"
        
        ext_map = {
            "png": ".png",
            "jpg": ".jpg",
            "jpeg": ".jpg"
        }
        ext = ext_map.get(image_format, ".png")
        
        # 保存图片文件
        image_filename = f"ocr_image_{uuid.uuid4().hex[:8]}{ext}"
        image_path = os.path.join(temp_dir, image_filename)
        
        with open(image_path, "wb") as f:
            f.write(image_bytes)
        logger.info(f"[OCR] 图片已保存: {image_path}")
        
        # 调用PaddleOCR进行识别
        from ..utils.paddleocr_fallback import call_paddleocr_ocr
        
        # 创建保存OCR结果的目录
        ocr_save_path = os.path.join(temp_dir, "ocr_output")
        os.makedirs(ocr_save_path, exist_ok=True)
        
        logger.info(f"[OCR] 开始调用PaddleOCR识别: {image_path}")
        texts = call_paddleocr_ocr(image_path, ocr_save_path)
        
        if texts is None:
            logger.warning("[OCR] PaddleOCR识别失败或未返回结果")
            return OCRResponse(
                success=False,
                error="OCR识别失败",
                message="PaddleOCR未能识别出文本内容"
            )
        
        # 返回所有文本（包括空文本，保持原始顺序）
        if not texts:
            texts = []
        
        # 默认使用所有文本片段拼接作为完整文本
        full_text = "\n".join(texts) if texts else ""
        
        # 尝试提取带段落分割的完整文本
        try:
            # 查找OCR生成的JSON文件
            image_basename = os.path.splitext(os.path.basename(image_path))[0]
            json_file = os.path.join(ocr_save_path, f"{image_basename}_res.json")
            
            if os.path.exists(json_file):
                from ..utils.paddleocr_fallback import extract_text_with_paragraphs_from_ocr_json
                extracted_text = extract_text_with_paragraphs_from_ocr_json(json_file)
                if extracted_text and extracted_text.strip():
                    full_text = extracted_text
                    logger.info(f"[OCR] 成功提取完整段落文本，长度: {len(full_text)} 字符")
                else:
                    logger.debug(f"[OCR] 段落文本提取结果为空，使用文本片段拼接")
            else:
                logger.debug(f"[OCR] JSON文件不存在，使用文本片段拼接")
        except Exception as e:
            logger.warning(f"[OCR] 提取完整段落文本失败: {e}，使用文本片段拼接")
        
        # 确保full_text不为None或空（至少是空字符串）
        if not full_text:
            full_text = "\n".join(texts) if texts else ""
        
        logger.info(f"[OCR] 识别成功，共识别出 {len(texts)} 个文本片段，完整文本长度: {len(full_text)} 字符")
        return OCRResponse(
            success=True,
            texts=texts,
            full_text=full_text,
            message=f"成功识别出 {len(texts)} 个文本片段"
        )
        
    except Exception as e:
        logger.exception(f"[OCR] 处理失败: {e}")
        return OCRResponse(
            success=False,
            error=str(e),
            message="OCR处理过程中发生错误"
        )
    finally:
        # 清理临时文件
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.debug(f"[OCR] 临时目录已清理: {temp_dir}")
            except Exception as e:
                logger.warning(f"[OCR] 清理临时目录失败: {e}")


# 启动时的初始化
@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化"""
    logger.info("PDF转换工具API v2 服务启动")
    logger.info("可用端点: POST /convert, GET /task/{task_id}, GET /download/{task_id}/*, POST /ocr")


# 关闭时的清理
@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时的清理"""
    logger.info("清理临时文件和任务状态...")
    # 清理所有临时目录
    for task_id, status_info in list(task_status.items()):
        temp_dir = status_info.get("temp_dir")
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"清理任务 {task_id} 的临时目录失败: {e}")
    task_status.clear()
    logger.info("PDF转换工具API v2 服务关闭")

