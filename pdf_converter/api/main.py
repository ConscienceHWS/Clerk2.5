# Copyright (c) Opendatalab. All rights reserved.

"""
PDF转换工具 FastAPI 版本
"""

import asyncio
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
import json
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing_extensions import Annotated

from ..processor.converter import convert_to_markdown
from ..config import DEFAULT_MODEL_NAME, DEFAULT_GPU_MEMORY_UTILIZATION, DEFAULT_DPI, DEFAULT_MAX_PAGES
from ..utils.logging_config import get_logger, init_logging

# 初始化日志系统
init_logging(
    log_dir=os.getenv("PDF_CONVERTER_LOG_DIR", "./logs"),
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    log_to_file=True,
    log_to_console=True
)

# 获取日志记录器
logger = get_logger("pdf_converter.api")

app = FastAPI(
    title="PDF转换工具API",
    description="将PDF/图片转换为Markdown和JSON格式",
    version="1.0.0"
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
    """转换请求模型"""
    max_pages: Optional[int] = DEFAULT_MAX_PAGES
    formula_enable: bool = True
    table_enable: bool = True
    embed_images: bool = True
    model_name: str = DEFAULT_MODEL_NAME
    gpu_memory_utilization: float = DEFAULT_GPU_MEMORY_UTILIZATION
    dpi: int = DEFAULT_DPI
    output_json: bool = False
    use_split: bool = False


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


@app.get("/")
async def root():
    """API根路径"""
    return {
        "name": "PDF转换工具API",
        "version": "1.0.0",
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
    return {"status": "healthy", "service": "pdf_converter"}


async def process_conversion_task(
    task_id: str,
    file_path: str,
    output_dir: str,
    request: ConversionRequest
):
    """
    后台处理转换任务
    
    注意：这个函数在响应返回给客户端之后才会执行
    所有耗时操作（包括模型初始化）都在这里进行，不会阻塞请求响应
    """
    try:
        logger.info(f"[任务 {task_id}] 后台任务开始执行（模型初始化即将开始）...")
        task_status[task_id]["status"] = "processing"
        task_status[task_id]["message"] = "开始处理文件..."
        
        logger.info(f"[任务 {task_id}] 开始处理: {file_path}")
        
        # 设置环境变量
        os.environ['MINERU_VLM_FORMULA_ENABLE'] = str(request.formula_enable)
        os.environ['MINERU_VLM_TABLE_ENABLE'] = str(request.table_enable)
        
        # 执行转换
        # 注意：convert_to_markdown 是异步函数，但内部会调用 MinerUPDFProcessor.__init__
        # 而 AsyncLLM.from_engine_args 是同步阻塞的，会阻塞事件循环
        # 虽然我们在后台任务中执行，但如果事件循环被阻塞，响应也可能延迟返回
        # 为了解决这个问题，我们需要将同步阻塞操作放到线程池中
        result = await convert_to_markdown(
            input_file=file_path,
            output_dir=output_dir,
            max_pages=request.max_pages,
            is_ocr=False,
            formula_enable=request.formula_enable,
            table_enable=request.table_enable,
            language="ch",
            backend="vllm-engine",
            url=None,
            embed_images=request.embed_images,
            model_name=request.model_name,
            gpu_memory_utilization=request.gpu_memory_utilization,
            dpi=request.dpi,
            output_json=request.output_json,
            use_split=request.use_split
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
    finally:
        # 清理临时文件
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.warning(f"[任务 {task_id}] 清理临时文件失败: {e}")


@app.post("/convert", response_model=ConversionResponse)
async def convert_file(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(description="上传的PDF或图片文件")],
    max_pages: Annotated[Optional[int], Form()] = DEFAULT_MAX_PAGES,
    formula_enable: Annotated[bool, Form()] = True,
    table_enable: Annotated[bool, Form()] = True,
    embed_images: Annotated[bool, Form()] = True,
    model_name: Annotated[str, Form()] = DEFAULT_MODEL_NAME,
    gpu_memory_utilization: Annotated[float, Form()] = DEFAULT_GPU_MEMORY_UTILIZATION,
    dpi: Annotated[int, Form()] = DEFAULT_DPI,
    output_json: Annotated[bool, Form()] = False,
    use_split: Annotated[bool, Form()] = True,
):
    """
    转换PDF/图片文件（异步处理）
    
    工作流程：
    1. 接收文件并生成task_id
    2. 立即返回task_id（不等待任何处理）
    3. 后台异步执行转换任务
    4. 客户端使用task_id轮询状态或直接获取结果
    
    - **file**: 上传的文件（PDF或图片）
    - **max_pages**: 最大转换页数（默认10）
    - **formula_enable**: 启用公式识别（默认True）
    - **table_enable**: 启用表格识别（默认True）
    - **embed_images**: 嵌入图片为base64（默认True）
    - **model_name**: 模型名称
    - **gpu_memory_utilization**: GPU内存利用率（默认0.9）
    - **dpi**: PDF转图片的DPI（默认200）
    - **output_json**: 输出JSON格式（默认False）
    - **use_split**: 使用图片分割提高精度（默认False）
    """
    # 生成任务ID
    task_id = str(uuid.uuid4())
    
    # 创建临时目录和输出目录
    temp_dir = tempfile.mkdtemp(prefix=f"pdf_converter_{task_id}_")
    output_dir = os.path.join(temp_dir, "output")
    os.makedirs(output_dir, exist_ok=True)
    
    # 保存上传的文件
    file_path = os.path.join(temp_dir, file.filename or "uploaded_file")
    try:
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        logger.info(f"[任务 {task_id}] 文件已保存: {file_path} ({len(content)} bytes)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存文件失败: {str(e)}")
    
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
        "output_dir": output_dir
    }
    
    # 创建请求对象
    request = ConversionRequest(
        max_pages=max_pages,
        formula_enable=formula_enable,
        table_enable=table_enable,
        embed_images=embed_images,
        model_name=model_name,
        gpu_memory_utilization=gpu_memory_utilization,
        dpi=dpi,
        output_json=output_json,
        use_split=use_split
    )
    
    # 使用 asyncio.create_task 创建后台任务，确保立即返回
    # 注意：模型初始化是同步阻塞的，但在后台任务中执行，不会阻塞响应返回
    # convert_to_markdown 内部会调用 MinerUPDFProcessor.__init__，这个初始化会阻塞
    # 但由于它在后台任务中，响应会立即返回给客户端
    task = asyncio.create_task(
        process_conversion_task(
            task_id,
            file_path,
            output_dir,
            request
        )
    )
    
    # 立即返回task_id，不等待任何处理
    # 模型初始化等耗时操作会在后台任务中执行，不会阻塞这里的返回
    # 即使 AsyncLLM.from_engine_args 是同步阻塞的，也不会影响响应返回
    logger.info(f"[任务 {task_id}] 任务已创建并添加到后台，立即返回task_id（模型初始化将在后台执行，不阻塞响应）")
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


# 启动时的初始化
@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化"""
    logger.info("PDF转换工具API服务启动")
    logger.info("可用端点: POST /convert, GET /task/{task_id}, GET /download/{task_id}/*")


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
    logger.info("PDF转换工具API服务关闭")
