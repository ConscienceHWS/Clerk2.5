# API 文档类型说明

## 支持的文档类型

API `/convert` 接口的 `type` 参数支持以下8种文档类型：

### 原有类型（5个）

| type 参数 | 说明 | 内部映射 |
|-----------|------|----------|
| `noiseRec` | 噪声检测记录 | noiseMonitoringRecord |
| `emRec` | 电磁检测记录 | electromagneticTestRecord |
| `opStatus` | 工况信息 | operatingConditionInfo |
| `settlementReport` | 结算报告 | settlementReport |
| `designReview` | 设计评审 | designReview |

### 新增类型（3个）✨

| type 参数 | 说明 | 内部映射 | 特点 |
|-----------|------|----------|------|
| `feasibilityApprovalInvestment` | 可研批复投资估算 | feasibilityApprovalInvestment | 含建设规模字段 |
| `feasibilityReviewInvestment` | 可研评审投资估算 | feasibilityReviewInvestment | 标准格式 |
| `preliminaryApprovalInvestment` | 初设批复概算投资 | preliminaryApprovalInvestment | 含合计行 |

## API 使用示例

### 1. 上传文件并指定类型

```bash
curl -X POST "http://localhost:4214/convert" \
  -F "file=@可研批复.pdf" \
  -F "type=feasibilityApprovalInvestment"
```

**响应：**
```json
{
  "task_id": "abc123...",
  "status": "pending",
  "message": "任务已创建，正在后台处理中，请使用task_id查询状态"
}
```

### 2. 查询任务状态

```bash
curl "http://localhost:4214/task/abc123..."
```

**响应（处理中）：**
```json
{
  "task_id": "abc123...",
  "status": "processing",
  "message": "开始处理文件..."
}
```

**响应（完成）：**
```json
{
  "task_id": "abc123...",
  "status": "completed",
  "message": "转换成功",
  "document_type": "feasibilityApprovalInvestment"
}
```

### 3. 获取JSON数据

```bash
curl "http://localhost:4214/task/abc123.../json"
```

**响应：**
```json
{
  "document_type": "feasibilityApprovalInvestment",
  "data": [
    {
      "No": "四、",
      "name": "输变电工程",
      "Level": "1",
      "constructionScaleOverheadLine": "",
      "constructionScaleBay": "6",
      "constructionScaleSubstation": "",
      "constructionScaleOpticalCable": "",
      "staticInvestment": "12500000",
      "dynamicInvestment": "13000000"
    }
  ]
}
```

## Python 客户端示例

```python
import requests
import time

# 1. 上传文件
with open("可研批复.pdf", "rb") as f:
    response = requests.post(
        "http://localhost:4214/convert",
        files={"file": f},
        data={"type": "feasibilityApprovalInvestment"}
    )
    task_id = response.json()["task_id"]
    print(f"任务ID: {task_id}")

# 2. 轮询状态
while True:
    response = requests.get(f"http://localhost:4214/task/{task_id}")
    status = response.json()["status"]
    print(f"状态: {status}")
    
    if status == "completed":
        break
    elif status == "failed":
        print("处理失败")
        exit(1)
    
    time.sleep(2)  # 等待2秒后再查询

# 3. 获取结果
response = requests.get(f"http://localhost:4214/task/{task_id}/json")
data = response.json()
print(f"文档类型: {data['document_type']}")
print(f"数据条数: {len(data['data'])}")

# 4. 清理任务
requests.delete(f"http://localhost:4214/task/{task_id}")
```

## 投资估算类型的JSON格式

### 可研批复 (feasibilityApprovalInvestment)

**特点：** 包含4个建设规模字段

```json
{
  "document_type": "feasibilityApprovalInvestment",
  "data": [
    {
      "No": "序号",
      "name": "工程或费用名称",
      "Level": "0/1/2/3",
      "constructionScaleOverheadLine": "建设规模-架空线",
      "constructionScaleBay": "建设规模-间隔",
      "constructionScaleSubstation": "建设规模-变电",
      "constructionScaleOpticalCable": "建设规模-光缆",
      "staticInvestment": "静态投资（元）",
      "dynamicInvestment": "动态投资（元）"
    }
  ]
}
```

### 可研评审 (feasibilityReviewInvestment)

**特点：** 标准格式，无建设规模字段

```json
{
  "document_type": "feasibilityReviewInvestment",
  "data": [
    {
      "No": "序号",
      "name": "工程或费用名称",
      "Level": "0/1/2/3",
      "staticInvestment": "静态投资（元）",
      "dynamicInvestment": "动态投资（元）"
    }
  ]
}
```

### 初设批复 (preliminaryApprovalInvestment)

**特点：** 包含合计行（Level=0）

```json
{
  "document_type": "preliminaryApprovalInvestment",
  "data": [
    {
      "No": "1",
      "name": "输变电工程",
      "Level": "2",
      "staticInvestment": "12000000",
      "dynamicInvestment": "12500000"
    },
    {
      "No": "",
      "name": "合计",
      "Level": "0",
      "staticInvestment": "12000000",
      "dynamicInvestment": "12500000"
    }
  ]
}
```

## Level 等级说明

| Level | 含义 | 示例 |
|-------|------|------|
| 0 | 合计行 | "合计" |
| 1 | 一级项目 | "一、", "四、" |
| 2 | 二级项目 | "1、", "2、" |
| 3 | 三级项目 | "(1)", "（2）" |

## 自动类型检测

如果不指定 `type` 参数，系统会自动检测文档类型：

```bash
# 不指定type，自动检测
curl -X POST "http://localhost:4214/convert" \
  -F "file=@可研批复.pdf"
```

系统会根据文档内容自动识别为 `feasibilityApprovalInvestment`。

## 错误处理

### 无效的type参数

```bash
curl -X POST "http://localhost:4214/convert" \
  -F "file=@test.pdf" \
  -F "type=invalidType"
```

**响应：**
```json
{
  "detail": "无效的type参数"
}
```

### 任务失败

```bash
curl "http://localhost:4214/task/abc123..."
```

**响应：**
```json
{
  "task_id": "abc123...",
  "status": "failed",
  "message": "处理出错: ...",
  "error": "详细错误信息"
}
```

## API 端点总览

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/convert` | 上传文件并创建任务 |
| GET | `/task/{task_id}` | 查询任务状态 |
| GET | `/task/{task_id}/json` | 获取JSON数据 |
| GET | `/download/{task_id}/markdown` | 下载Markdown文件 |
| GET | `/download/{task_id}/json` | 下载JSON文件 |
| DELETE | `/task/{task_id}` | 删除任务 |
| GET | `/health` | 健康检查 |
| GET | `/` | API信息 |

## 启动服务

```bash
# 默认配置（端口4214）
python api_server.py

# 自定义端口
python api_server.py --port 8080

# 生产环境（多进程）
python api_server.py --workers 4
```

## 访问文档

启动服务后，访问以下地址查看交互式API文档：

- Swagger UI: `http://localhost:4214/docs`
- ReDoc: `http://localhost:4214/redoc`

## 注意事项

1. **文件大小限制**: 建议单个文件不超过20页
2. **任务清理**: 处理完成后建议调用 DELETE 接口清理临时文件
3. **轮询间隔**: 建议每2-5秒查询一次任务状态
4. **类型映射**: API 参数使用简短名称，内部自动映射到完整类型名

## 完整工作流程

```
客户端                    API服务器                  处理引擎
  |                          |                          |
  |--POST /convert---------->|                          |
  |  (file + type)           |                          |
  |                          |--创建任务--------------->|
  |<--返回task_id------------|                          |
  |                          |                          |
  |--GET /task/{id}--------->|                          |
  |<--status: processing-----|                          |
  |                          |                          |
  |  (等待2秒)               |                          |
  |                          |                          |
  |--GET /task/{id}--------->|                          |
  |<--status: completed------|<--处理完成---------------|
  |                          |                          |
  |--GET /task/{id}/json---->|                          |
  |<--返回JSON数据-----------|                          |
  |                          |                          |
  |--DELETE /task/{id}------>|                          |
  |<--确认删除---------------|--清理临时文件----------->|
```

## 更新日志

### v2.1.0 (2026-01-15)

- ✨ 新增3个投资估算文档类型
  - `feasibilityApprovalInvestment` - 可研批复
  - `feasibilityReviewInvestment` - 可研评审
  - `preliminaryApprovalInvestment` - 初设批复
- 🔧 更新 API 类型定义和文档
- 📝 完善类型说明和示例
