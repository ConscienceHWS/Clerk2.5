# PDF转换工具 FastAPI 版本

## 概述

这是 PDF 转换工具的 FastAPI 版本，提供 RESTful API 接口用于将 PDF/图片转换为 Markdown 和 JSON 格式。

## 安装依赖

```bash
pip install fastapi uvicorn python-multipart
```

## 启动服务

### 方式1：使用启动脚本
```bash
python pdf_converter/api_server.py
```

### 方式2：使用 uvicorn 直接启动
```bash
uvicorn pdf_converter.api.main:app --host 0.0.0.0 --port 8000
```

### 方式3：指定端口和主机
```bash
uvicorn pdf_converter.api.main:app --host 0.0.0.0 --port 8080 --reload
```

## API 端点

### 1. 根路径 - 获取API信息
```
GET /
```
返回API基本信息和可用端点列表。

### 2. 健康检查
```
GET /health
```
检查服务是否正常运行。

### 3. 转换文件（异步）
```
POST /convert
Content-Type: multipart/form-data
```

**请求参数：**
- `file` (file, required): 上传的PDF或图片文件
- `max_pages` (int, optional, default=10): 最大转换页数
- `formula_enable` (bool, optional, default=True): 启用公式识别
- `table_enable` (bool, optional, default=True): 启用表格识别
- `embed_images` (bool, optional, default=True): 嵌入图片为base64
- `model_name` (str, optional): 模型名称（默认使用配置的模型）
- `gpu_memory_utilization` (float, optional, default=0.9): GPU内存利用率
- `dpi` (int, optional, default=200): PDF转图片的DPI
- `output_json` (bool, optional, default=False): 输出JSON格式
- `use_split` (bool, optional, default=False): 使用图片分割提高精度

**响应示例：**
```json
{
  "task_id": "uuid-string",
  "status": "pending",
  "message": "任务已创建，正在处理中",
  "markdown_file": null,
  "json_file": null,
  "document_type": null
}
```

### 4. 查询任务状态
```
GET /task/{task_id}
```

**响应示例：**
```json
{
  "task_id": "uuid-string",
  "status": "completed",
  "message": "转换成功",
  "progress": 100.0,
  "markdown_file": "/path/to/file.md",
  "json_file": "/path/to/file.json",
  "document_type": "noise_detection",
  "error": null
}
```

**状态值：**
- `pending`: 等待处理
- `processing`: 处理中
- `completed`: 已完成
- `failed`: 失败

### 5. 下载Markdown文件
```
GET /download/{task_id}/markdown
```

返回转换后的Markdown文件。

### 6. 下载JSON文件
```
GET /download/{task_id}/json
```

返回转换后的JSON文件（如果请求时指定了`output_json=True`）。

### 7. 删除任务
```
DELETE /task/{task_id}
```

删除任务及其临时文件。

## 使用示例

### 使用 curl

```bash
# 1. 上传文件并开始转换
curl -X POST "http://localhost:8000/convert" \
  -F "file=@example.pdf" \
  -F "output_json=true" \
  -F "use_split=true"

# 响应
# {"task_id": "abc-123-def", "status": "pending", ...}

# 2. 查询任务状态
curl "http://localhost:8000/task/abc-123-def"

# 3. 下载Markdown文件
curl "http://localhost:8000/download/abc-123-def/markdown" -o output.md

# 4. 下载JSON文件
curl "http://localhost:8000/download/abc-123-def/json" -o output.json
```

### 使用 Python requests

```python
import requests
import time

# 1. 上传文件
with open("example.pdf", "rb") as f:
    files = {"file": f}
    data = {
        "output_json": True,
        "use_split": True,
        "max_pages": 10
    }
    response = requests.post("http://localhost:8000/convert", files=files, data=data)
    result = response.json()
    task_id = result["task_id"]
    print(f"任务ID: {task_id}")

# 2. 轮询任务状态
while True:
    response = requests.get(f"http://localhost:8000/task/{task_id}")
    status = response.json()
    print(f"状态: {status['status']} - {status['message']}")
    
    if status["status"] == "completed":
        break
    elif status["status"] == "failed":
        print(f"错误: {status.get('error')}")
        break
    
    time.sleep(2)  # 等待2秒后再次查询

# 3. 下载文件
if status["status"] == "completed":
    # 下载Markdown
    md_response = requests.get(f"http://localhost:8000/download/{task_id}/markdown")
    with open("output.md", "wb") as f:
        f.write(md_response.content)
    
    # 下载JSON
    if status.get("json_file"):
        json_response = requests.get(f"http://localhost:8000/download/{task_id}/json")
        with open("output.json", "wb") as f:
            f.write(json_response.content)
```

### 使用 JavaScript/Fetch

```javascript
// 1. 上传文件
const formData = new FormData();
formData.append('file', fileInput.files[0]);
formData.append('output_json', 'true');
formData.append('use_split', 'true');

const response = await fetch('http://localhost:8000/convert', {
  method: 'POST',
  body: formData
});

const result = await response.json();
const taskId = result.task_id;

// 2. 轮询任务状态
const checkStatus = async () => {
  const statusResponse = await fetch(`http://localhost:8000/task/${taskId}`);
  const status = await statusResponse.json();
  
  if (status.status === 'completed') {
    // 下载文件
    const mdResponse = await fetch(`http://localhost:8000/download/${taskId}/markdown`);
    const mdBlob = await mdResponse.blob();
    // 处理下载的Markdown文件
  } else if (status.status === 'failed') {
    console.error('转换失败:', status.error);
  } else {
    // 继续轮询
    setTimeout(checkStatus, 2000);
  }
};

checkStatus();
```

## API 文档

启动服务后，可以访问以下地址查看自动生成的API文档：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 注意事项

1. **异步处理**：文件转换是异步处理的，需要轮询任务状态或使用WebSocket获取实时更新
2. **文件清理**：任务完成后，临时文件会保留一段时间。建议完成后调用 DELETE 接口清理
3. **CORS配置**：默认允许所有来源，生产环境应限制为特定域名
4. **文件大小限制**：FastAPI默认文件上传大小限制为100MB，可通过配置修改
5. **并发处理**：FastAPI支持并发请求，但GPU资源有限，可能需要限制并发数

## 配置

可以通过环境变量或修改代码来配置：
- 服务器端口和主机
- CORS允许的来源
- 文件大小限制
- 临时文件保存路径

## 错误处理

API会返回标准的HTTP状态码：
- `200`: 成功
- `400`: 请求参数错误
- `404`: 资源不存在
- `500`: 服务器内部错误

错误响应格式：
```json
{
  "detail": "错误描述信息"
}
```

