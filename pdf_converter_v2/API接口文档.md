# PDF 转换服务 API 接口文档

## 概述

本服务提供 PDF 文档解析功能，支持多种电力工程文档类型的结构化数据提取。

**服务地址**: `http://{host}:14213`

---

## 1. 健康检查

### 请求

```
GET /health
```

### 响应

```json
{
  "status": "healthy",
  "service": "pdf_converter_v2"
}
```

---

## 2. 上传并转换文件

### 请求

```
POST /convert
Content-Type: multipart/form-data
```

**参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| file | File | 是 | PDF 文件 |
| type | String | 是 | 文档类型（见下表） |

**支持的文档类型**:

| type 值 | 说明 | 数据结构 |
|---------|------|----------|
| `fsApproval` | 可研批复投资估算 | 嵌套结构（含建设规模） |
| `fsReview` | 可研评审投资估算 | 嵌套结构 |
| `pdApproval` | 初设批复概算投资 | 嵌套结构 |
| `designReview` | 初设评审概算投资 | 嵌套结构 |
| `settlementReport` | 结算审计报告 | 对象结构（多表） |
| `noiseRec` | 噪声检测记录 | 专用结构 |
| `emRec` | 电磁检测记录 | 专用结构 |
| `opStatus` | 工况信息 | 专用结构 |

### 响应

```json
{
  "task_id": "5367d6e4-5a8c-43db-baa1-d8757cbb5746",
  "status": "processing",
  "message": "任务已创建"
}
```

> **说明**: 文件转换为异步处理，需使用 `task_id` 轮询任务状态。

---

## 3. 查询任务状态

### 请求

```
GET /task/{task_id}
```

### 响应

**处理中**:
```json
{
  "task_id": "5367d6e4-5a8c-43db-baa1-d8757cbb5746",
  "status": "processing"
}
```

**已完成**:
```json
{
  "task_id": "5367d6e4-5a8c-43db-baa1-d8757cbb5746",
  "status": "completed"
}
```

**失败**:
```json
{
  "task_id": "5367d6e4-5a8c-43db-baa1-d8757cbb5746",
  "status": "failed",
  "error": "错误信息"
}
```

---

## 4. 获取转换结果

### 请求

```
GET /task/{task_id}/json
```

### 响应

根据文档类型返回不同结构的 JSON 数据。

---

## 5. 各类型返回数据结构

### 5.1 可研批复投资估算 (fsApproval)

三层嵌套结构，包含建设规模字段。

```json
{
  "document_type": "fsApproval",
  "data": [
    {
      "name": "山西临汾古县220千伏输变电工程",
      "Level": 0,
      "constructionScaleSubstation": "360",
      "constructionScaleBay": "1",
      "constructionScaleOverheadLine": "75.11",
      "constructionScaleOpticalCable": "124.2",
      "staticInvestment": 19850.0,
      "dynamicInvestment": 20222.0,
      "items": [
        {
          "No": 1,
          "name": "变电工程",
          "Level": 1,
          "constructionScaleSubstation": "360",
          "constructionScaleBay": "1",
          "constructionScaleOverheadLine": "",
          "constructionScaleOpticalCable": "",
          "staticInvestment": 10055.0,
          "dynamicInvestment": 10244.0,
          "items": [
            {
              "No": 0,
              "name": "古县220千伏变电站新建工程",
              "Level": 2,
              "constructionScaleSubstation": "360",
              "constructionScaleBay": "",
              "constructionScaleOverheadLine": "",
              "constructionScaleOpticalCable": "",
              "staticInvestment": 9630.0,
              "dynamicInvestment": 9810.0
            }
          ]
        }
      ]
    }
  ]
}
```

**字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| name | String | 工程名称 |
| Level | Integer | 层级（0=顶层大类, 1=二级分类, 2=具体项目） |
| constructionScaleSubstation | String | 建设规模-变电（兆伏安） |
| constructionScaleBay | String | 建设规模-间隔（个） |
| constructionScaleOverheadLine | String | 建设规模-架空线（公里） |
| constructionScaleOpticalCable | String | 建设规模-光缆（公里） |
| staticInvestment | Number | 静态投资（万元） |
| dynamicInvestment | Number | 动态投资（万元） |
| items | Array | 子项目列表 |

---

### 5.2 可研评审投资估算 (fsReview)

两层嵌套结构，不含建设规模字段。

```json
{
  "document_type": "fsReview",
  "data": [
    {
      "name": "变电工程",
      "Level": 0,
      "staticInvestment": 9317.0,
      "dynamicInvestment": 9491.0,
      "items": [
        {
          "No": 1,
          "name": "晋城周村220kV变电站新建工程",
          "Level": 1,
          "staticInvestment": 8889.0,
          "dynamicInvestment": 9055.0,
          "items": []
        }
      ]
    }
  ]
}
```

**字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| name | String | 工程名称 |
| Level | Integer | 层级（0=大类, 1=子项） |
| staticInvestment | Number | 静态投资（万元） |
| dynamicInvestment | Number | 动态投资（万元） |
| items | Array | 子项目列表 |

---

### 5.3 初设批复概算投资 (pdApproval)

两层嵌套结构，与 fsReview 结构一致。

```json
{
  "document_type": "pdApproval",
  "data": [
    {
      "name": "变电工程",
      "Level": 0,
      "staticInvestment": 9728.0,
      "dynamicInvestment": 9910.0,
      "items": [
        {
          "No": 1,
          "name": "周村220kV变电站新建工程",
          "Level": 1,
          "staticInvestment": 9278.0,
          "dynamicInvestment": 9452.0
        }
      ]
    }
  ]
}
```

---

### 5.4 初设评审概算投资 (designReview)

两层嵌套结构，与 pdApproval 结构完全一致。

```json
{
  "document_type": "designReview",
  "data": [
    {
      "name": "变电工程",
      "Level": 0,
      "staticInvestment": 9728.0,
      "dynamicInvestment": 9910.0,
      "items": [
        {
          "No": 1,
          "name": "周村220kV变电站新建工程",
          "Level": 1,
          "staticInvestment": 9278.0,
          "dynamicInvestment": 9452.0
        }
      ]
    }
  ]
}
```

---

### 5.5 结算审计报告 (settlementReport)

对象结构，包含多个表格数据。

```json
{
  "document_type": "settlementReport",
  "data": {
    "审定结算汇总表": [
      {
        "No": 1,
        "name": "建筑安装工程费",
        "settledVerifiedTaxExclusiveInvestment": 50332168.79,
        "settledVerifiedTaxInclusiveInvestment": 54862064.0
      }
    ],
    "合同执行情况": [
      {
        "No": 1,
        "constructionUnit": "晋城市巨能电网工程有限公司(变电安装)",
        "bidNoticeAmount": 738.98,
        "bidNoticeNo": "国网晋招建设施工字（2019-0925）-04",
        "contractAmount": 738.98,
        "settlementSubmittedAmount": 697.94,
        "differenceAmount": 41.04
      }
    ]
  }
}
```

**审定结算汇总表字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| No | Integer | 序号 |
| name | String | 费用名称 |
| settledVerifiedTaxExclusiveInvestment | Number | 结算审定投资（不含税，元） |
| settledVerifiedTaxInclusiveInvestment | Number | 结算审定投资（含税，元） |

**合同执行情况字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| No | Integer | 序号 |
| constructionUnit | String | 施工单位 |
| bidNoticeAmount | Number | 中标通知书金额（万元） |
| bidNoticeNo | String | 中标通知书编号 |
| contractAmount | Number | 合同金额（万元） |
| settlementSubmittedAmount | Number | 结算送审金额（万元） |
| differenceAmount | Number | 差额（万元） |

---

## 6. 调用示例

### 6.1 上传文件

```bash
curl -X POST "http://{host}:14213/convert" \
  -F "file=@/path/to/document.pdf" \
  -F "type=fsApproval"
```

### 6.2 查询状态

```bash
curl -X GET "http://{host}:14213/task/{task_id}"
```

### 6.3 获取结果

```bash
curl -X GET "http://{host}:14213/task/{task_id}/json"
```

---

## 7. 错误处理

当解析失败或文档类型无法识别时，返回：

```json
{
  "document_type": "unknown",
  "data": {},
  "error": "无法识别的文档类型"
}
```

---

## 8. 注意事项

1. **异步处理**: 文件上传后立即返回 `task_id`，需轮询状态直到 `completed`
2. **轮询间隔**: 建议 3-5 秒轮询一次
3. **超时时间**: 大文件处理可能需要 30 秒以上，建议设置 5 分钟超时
4. **文件大小**: 支持最大 50MB 的 PDF 文件
5. **类型指定**: `type` 参数必须与文档内容匹配，否则解析结果可能为空

---

## 9. 文档类型对照表

| type | 文档标题特征 | 返回结构 |
|------|-------------|----------|
| fsApproval | 可研批复 | 三层嵌套 + 建设规模 |
| fsReview | 可研评审 | 两层嵌套 |
| pdApproval | 初设批复 | 两层嵌套 |
| designReview | 初设评审 | 两层嵌套 |
| settlementReport | 结算报告/审计报告 | 多表对象 |
