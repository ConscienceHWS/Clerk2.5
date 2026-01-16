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
import json
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
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


class GpuInfo(BaseModel):
    """GPU监控信息（基于采集数据计算得出）"""
    gpu_index: Optional[int] = None
    gpu_memory_used: Optional[int] = None  # 字节，任务期间的最大显存使用量
    gpu_utilization: Optional[float] = None  # 百分比，平均GPU利用率
    gpu_memory_total: Optional[int] = None  # 总显存（字节）
    gpu_name: Optional[str] = None
    # 以下为可选统计字段
    gpu_memory_used_avg: Optional[int] = None  # 平均显存使用（字节）
    gpu_memory_used_max: Optional[int] = None  # 最大显存使用（字节）
    gpu_utilization_max: Optional[float] = None  # 最大GPU利用率（%）
    system_load_avg_1min: Optional[float] = None  # 平均1分钟系统负载
    system_load_max_1min: Optional[float] = None  # 最大1分钟系统负载
    system_load_avg_5min: Optional[float] = None  # 平均5分钟系统负载
    system_load_max_5min: Optional[float] = None  # 最大5分钟系统负载
    system_load_avg_15min: Optional[float] = None  # 平均15分钟系统负载
    system_load_max_15min: Optional[float] = None  # 最大15分钟系统负载
    sample_count: Optional[int] = None  # 采集的样本数量
    duration: Optional[float] = None  # 监控持续时间（秒）


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
    gpu_info: Optional[GpuInfo] = None  # GPU监控信息


class OCRRequest(BaseModel):
    """OCR识别请求模型"""
    image_base64: str  # base64编码的图片数据
    image_format: Optional[str] = "png"  # 图片格式：png, jpg, jpeg


class OCRResponse(BaseModel):
    """OCR识别响应模型"""
    code: int  # 状态码：0表示成功，-1或其他表示错误
    message: str  # 消息
    data: Optional[dict] = None  # 数据，包含texts和full_text
    gpu_info: Optional[GpuInfo] = None  # GPU监控信息


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
    # 资源监控：启动后台采集线程（每0.5秒采集一次）
    from ..utils.resource_monitor import ResourceMonitor
    monitor = ResourceMonitor(interval=0.5)
    monitor.start()
    
    try:
        logger.info(f"[任务 {task_id}] 后台任务开始执行...")
        task_status[task_id]["status"] = "processing"
        task_status[task_id]["message"] = "开始处理文件..."
        
        logger.info(f"[任务 {task_id}] 开始处理: {file_path}")
        
        result = None
        tables_info = None
        
        # 针对投资估算类型，需要先切割附件页
        if request.doc_type in ("feasibilityApprovalInvestment", "feasibilityReviewInvestment", "preliminaryApprovalInvestment"):
            logger.info(f"[任务 {task_id}] 文档类型 {request.doc_type}，需要先切割附件页")
            
            # 导入附件页切割函数
            import sys
            from pathlib import Path as PathLib
            sys.path.insert(0, str(PathLib(__file__).parent.parent))
            
            try:
                from test_no import split_attachment_pages
                
                # 创建附件页输出目录
                attachment_dir = PathLib(output_dir) / "attachments"
                
                # 切割附件页
                logger.info(f"[任务 {task_id}] 开始切割附件页...")
                await asyncio.to_thread(
                    split_attachment_pages,
                    file_path,
                    attachment_dir,
                    use_ocr=True,
                    debug=False
                )
                
                # 查找切割后的附件页PDF
                attachment_pdfs = list(attachment_dir.glob("*_附件页_*.pdf"))
                if attachment_pdfs:
                    # 使用第一个附件页PDF作为输入
                    file_path = str(attachment_pdfs[0])
                    logger.info(f"[任务 {task_id}] 附件页切割完成，使用文件: {file_path}")
                else:
                    logger.warning(f"[任务 {task_id}] 未找到附件页，使用原始文件")
                    logger.info(f"[任务 {task_id}] 提示: 如果PDF是扫描件，请确保安装了Tesseract OCR以启用文本识别")
            except Exception as e:
                logger.error(f"[任务 {task_id}] 附件页切割失败: {e}")
                logger.warning(f"[任务 {task_id}] 将使用原始文件继续处理")
        
        # 针对结算报告 / 初设评审类文档，直接执行表格提取，不调用外部 API
        if request.doc_type in ("settlementReport", "designReview"):
            logger.info(f"[任务 {task_id}] 文档类型 {request.doc_type}，跳过外部 API，直接执行表格提取")
            # 延迟导入，避免启动时因 pandas/numpy 版本冲突导致服务无法启动
            from ..utils.table_extractor import extract_and_filter_tables_for_pdf
            
            # 在线程池中执行表格提取（因为它是同步函数，使用 to_thread 避免阻塞事件循环）
            def run_table_extraction_sync():
                try:
                    logger.info(f"[任务 {task_id}] 开始执行表格提取函数...")
                    logger.info(f"[任务 {task_id}] 参数: pdf_path={file_path}, output_dir={output_dir}, doc_type={request.doc_type}")
                    result = extract_and_filter_tables_for_pdf(
                        pdf_path=file_path,
                        base_output_dir=output_dir,
                        doc_type=request.doc_type,  # type: ignore[arg-type]
                    )
                    logger.info(f"[任务 {task_id}] 表格提取函数执行完成，返回结果: {result is not None}")
                    return result
                except Exception as e:
                    logger.exception(f"[任务 {task_id}] 表格提取/筛选失败: {e}")
                    return None
            
            # 执行表格提取
            tables_info = await asyncio.to_thread(run_table_extraction_sync)
            
            # 构造一个简单的 result，包含必要的字段
            if tables_info:
                # 将表格信息挂到任务状态，方便后续调试或扩展
                task_status[task_id]["tables"] = tables_info
                logger.info(
                    f"[任务 {task_id}] 表格提取完成，筛选目录: {tables_info.get('filtered_dir')}"
                )
                
                # 构造 result，包含解析后的 JSON 数据
                result = {
                    "markdown_file": None,  # 这两个类型不需要 markdown
                    "json_file": None,  # JSON 数据直接放在 json_data 中
                    "json_data": {
                        "document_type": request.doc_type,
                        "data": tables_info.get("parsed_data", {}),
                    }
                }
        else:
            # 其他类型：执行转换（v2 使用外部API）
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
        
        # 停止监控并获取统计结果（基于采集的数据计算）
        monitor.stop()
        stats = monitor.get_statistics()
        if stats:
            task_status[task_id]["gpu_info"] = stats
        
        if result:
            task_status[task_id]["status"] = "completed"
            task_status[task_id]["message"] = "转换成功"
            task_status[task_id]["markdown_file"] = result.get("markdown_file")
            task_status[task_id]["json_file"] = result.get("json_file")
            # 保存JSON数据内容，以便直接返回
            if result.get("json_data"):
                json_data = result["json_data"].copy()
                task_status[task_id]["json_data"] = json_data
                task_status[task_id]["document_type"] = json_data.get("document_type")
            logger.info(f"[任务 {task_id}] 处理成功")
        else:
            task_status[task_id]["status"] = "failed"
            task_status[task_id]["message"] = "转换失败"
            task_status[task_id]["error"] = "转换返回None"
            logger.error(f"[任务 {task_id}] 转换失败")
            
    except Exception as e:
        # 停止监控并获取统计结果（即使异常也记录）
        monitor.stop()
        stats = monitor.get_statistics()
        if stats:
            task_status[task_id]["gpu_info"] = stats
        
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
    # 新增：类型参数（英文传参） noiseRec | emRec | opStatus | settlementReport | designReview | feasibilityApprovalInvestment | feasibilityReviewInvestment | preliminaryApprovalInvestment
    type: Annotated[
        Optional[Literal["noiseRec", "emRec", "opStatus", "settlementReport", "designReview", "feasibilityApprovalInvestment", "feasibilityReviewInvestment", "preliminaryApprovalInvestment"]],
        Form(description="文档类型：noiseRec | emRec | opStatus | settlementReport | designReview | feasibilityApprovalInvestment | feasibilityReviewInvestment | preliminaryApprovalInvestment")
    ] = None,
):
    """
    转换PDF/图片文件（异步处理）
    
    工作流程：
    1. 接收文件并生成task_id
    2. 立即返回task_id（不等待任何处理）
    3. 后台异步执行转换任务（调用外部API）
    4. 客户端使用task_id轮询状态或直接获取结果
    
    - **file**: 上传的文件（PDF或图片）
    - **type**: 文档类型
      * noiseRec - 噪声检测
      * emRec - 电磁检测
      * opStatus - 工况信息
      * settlementReport - 结算报告
      * designReview - 设计评审
      * feasibilityApprovalInvestment - 可研批复投资估算
      * feasibilityReviewInvestment - 可研评审投资估算
      * preliminaryApprovalInvestment - 初设批复概算投资
    
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
    # 不使用原始文件名，直接使用简单的固定命名，避免文件名过长问题
    # 先尝试从Content-Type推断扩展名
    content_type = file.content_type or ""
    extension_map = {
        "application/pdf": ".pdf",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
    }
    ext = extension_map.get(content_type, "")
    
    # 如果没有从Content-Type获取到，尝试从原始文件名获取扩展名
    if not ext and file.filename:
        ext = Path(file.filename).suffix
    
    # 如果还是没有，使用默认扩展名
    if not ext:
        ext = ".pdf"  # 默认假设是PDF
    
    # 使用简单的固定文件名
    file_path = os.path.join(temp_dir, f"file{ext}")
    
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
                    new_file_path = os.path.join(temp_dir, f"file{ext}")
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
        # 结算报告类
        "settlementReport": "settlementReport",
        # 初设评审类
        "designReview": "designReview",
        # 投资估算类（新增）
        "feasibilityApprovalInvestment": "feasibilityApprovalInvestment",
        "feasibilityReviewInvestment": "feasibilityReviewInvestment",
        "preliminaryApprovalInvestment": "preliminaryApprovalInvestment",
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
    
    # 处理GPU信息
    gpu_info_model = None
    if "gpu_info" in status_info and status_info["gpu_info"]:
        gpu_info_model = GpuInfo(**status_info["gpu_info"])
    
    return TaskStatus(
        task_id=task_id,
        status=status_info["status"],
        message=status_info["message"],
        progress=status_info.get("progress"),
        markdown_file=status_info.get("markdown_file"),
        json_file=status_info.get("json_file"),
        document_type=status_info.get("document_type"),
        error=status_info.get("error"),
        gpu_info=gpu_info_model
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
    
    返回识别出的文本列表和GPU监控信息
    """
    temp_dir = None
    image_path = None
    
    # 资源监控：启动后台采集线程（每0.5秒采集一次）
    from ..utils.resource_monitor import ResourceMonitor
    monitor = ResourceMonitor(interval=0.5)
    monitor.start()
    
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
            # 停止监控并获取统计结果
            monitor.stop()
            stats = monitor.get_statistics()
            gpu_info_model = GpuInfo(**stats) if stats else None
            return OCRResponse(
                code=-1,
                message="无法解码base64图片数据",
                data=None,
                gpu_info=gpu_info_model
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
        
        # 调用PaddleOCR进行识别（监控线程在此期间持续采集数据）
        from ..utils.paddleocr_fallback import call_paddleocr_ocr
        
        # 创建保存OCR结果的目录
        ocr_save_path = os.path.join(temp_dir, "ocr_output")
        os.makedirs(ocr_save_path, exist_ok=True)
        
        logger.info(f"[OCR] 开始调用PaddleOCR识别: {image_path}")
        texts, md_file_path = call_paddleocr_ocr(image_path, ocr_save_path)
        
        # 停止监控并获取统计结果（基于采集的数据计算）
        monitor.stop()
        stats = monitor.get_statistics()
        gpu_info_model = GpuInfo(**stats) if stats else None
        
        if texts is None:
            logger.warning("[OCR] PaddleOCR识别失败或未返回结果")
            return OCRResponse(
                code=-1,
                message="PaddleOCR未能识别出文本内容",
                data=None,
                gpu_info=gpu_info_model  # 即使失败也返回GPU信息
            )
        
        # 返回所有文本（已按Y坐标排序并合并，保持正确顺序）
        if not texts:
            texts = []
        
        # 直接使用texts数组，按行用\n连接生成完整文本
        # texts已经是按Y坐标排序并合并的，顺序正确
        full_text = "\n".join(texts) if texts else ""
        
        # 记录文件位置
        logger.info(f"[OCR] 识别成功，共识别出 {len(texts)} 个文本片段，完整文本长度: {len(full_text)} 字符")
        logger.info(f"[OCR] 上传的图片已保存: {image_path}")
        if md_file_path:
            logger.info(f"[OCR] 生成的Markdown文件已保存: {md_file_path}")
        logger.info(f"[OCR] 所有文件保存在目录: {temp_dir}")
        
        return OCRResponse(
            code=0,
            message=f"成功识别出 {len(texts)} 个文本片段",
            data={
                "texts": texts,
                "full_text": full_text
            },
            gpu_info=gpu_info_model  # 返回GPU监控信息
        )
        
    except Exception as e:
        # 停止监控并获取统计结果（即使异常也记录）
        monitor.stop()
        stats = monitor.get_statistics()
        gpu_info_model = GpuInfo(**stats) if stats else None
        
        logger.exception(f"[OCR] 处理失败: {e}")
        return OCRResponse(
            code=-1,
            message=f"OCR处理过程中发生错误: {str(e)}",
            data=None,
            gpu_info=gpu_info_model
        )
    # 注意：不再删除临时文件，保留上传的图片和生成的markdown文件


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

