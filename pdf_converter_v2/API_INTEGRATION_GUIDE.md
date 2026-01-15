# PDF转换API接入文档 - 结算报告与初设评审类型

## 概述

本文档介绍如何使用PDF转换API处理两种新的文档类型：
- **settlementReport**（结算报告）
- **designReview**（初设评审）

这两种类型采用本地表格提取和解析，不依赖外部API，处理速度更快。

---

## API端点

### 1. 上传文件并开始转换

**端点**: `POST /convert`

**请求格式**: `multipart/form-data`

**请求参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `file` | File | 是 | PDF文件（支持多页，无页数限制） |
| `type` | String | 是 | 文档类型：`settlementReport` 或 `designReview` |

**响应格式**:

```json
{
  "task_id": "uuid-string",
  "status": "pending",
  "message": "任务已创建，正在后台处理中，请使用task_id查询状态",
  "markdown_file": null,
  "json_file": null,
  "document_type": null
}
```

**示例请求** (cURL):

```bash
curl -X POST "http://localhost:4214/convert" \
  -F "file=@结算报告.pdf" \
  -F "type=settlementReport"
```

**示例请求** (Python):

```python
import requests

url = "http://localhost:4214/convert"
files = {"file": open("结算报告.pdf", "rb")}
data = {"type": "settlementReport"}

response = requests.post(url, files=files, data=data)
result = response.json()
task_id = result["task_id"]
print(f"任务ID: {task_id}")
```

---

### 2. 查询任务状态

**端点**: `GET /task/{task_id}`

**响应格式**:

```json
{
  "status": "completed",
  "message": "处理成功",
  "progress": 100.0,
  "markdown_file": null,
  "json_file": "/tmp/xxx/output/file.json",
  "json_data": { ... },
  "document_type": "settlementReport",
  "error": null
}
```

**状态值说明**:

- `pending`: 任务已创建，等待处理
- `processing`: 正在处理中
- `completed`: 处理完成
- `failed`: 处理失败

---

### 3. 获取JSON数据

**端点**: `GET /task/{task_id}/json`

**响应格式**: 直接返回JSON数据（见下方数据格式说明）

**示例请求**:

```bash
curl "http://localhost:4214/task/{task_id}/json"
```

---

## 数据格式说明

### settlementReport（结算报告）

**文档类型标识**: `"document_type": "settlementReport"`

**数据结构**: 所有表格数据组织在 `data` 字段中，按表名作为key

**完整响应示例**:

```json
{
  "document_type": "settlementReport",
  "data": {
    "审定结算汇总表": [
      {
        "No": 1,
        "name": "建筑安装工程费",
        "settledVerifiedTaxExclusiveInvestment": 50332168.79,
        "settledVerifiedTaxInclusiveInvestment": 54862064
      },
      {
        "No": 2,
        "name": "建设场地清理费",
        "settledVerifiedTaxExclusiveInvestment": 4241199.82,
        "settledVerifiedTaxInclusiveInvestment": 4267054.85
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
    ],
    "赔偿合同": [
      {
        "No": 1,
        "contractCounterpartyName": "泽州县交通运输局路政管理所",
        "compensationItem": "在公路上增设平面交叉道口1处",
        "contractAmount": 11.49,
        "settlementSubmittedAmount": 11.49,
        "differenceAmount": 0
      }
    ],
    "物资采购合同1": [
      {
        "No": 1,
        "materialName": "铁塔,AC220kV,通用,角钢,Q345,常规塔",
        "contractQuantity": 0,
        "drawingQuantity": 36.08,
        "unitPriceExcludingTax": 7349.37,
        "differenceAmount": -265194.67
      }
    ],
    "物资采购合同2": [
      {
        "No": 1,
        "materialName": "铁塔,AC220kV,通用,角钢,Q345,常规塔",
        "contractAmount": 0,
        "bookedAmount": 265194.67,
        "differenceAmount": -265194.67,
        "remark": ""
      }
    ],
    "其他服务类合同": [
      {
        "No": 1,
        "serviceProvider": "山西顺德土地评估规划咨询有限公司",
        "bidNotice": "SXTYZX-TY20087TP-JC04-QT-38",
        "contractAmount": 44.98,
        "submittedAmount": 44.98,
        "settlementAmount": 44.98
      }
    ]
  }
}
```

**字段说明**:

#### 审定结算汇总表

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `No` | Integer | 序号 |
| `name` | String | 项目名称（审计内容） |
| `settledVerifiedTaxExclusiveInvestment` | Float | 结算审定不含税投资（元，两位小数） |
| `settledVerifiedTaxInclusiveInvestment` | Float | 结算审定含税投资（元，两位小数） |

#### 合同执行情况

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `No` | Integer | 序号 |
| `constructionUnit` | String | 施工单位 |
| `bidNoticeAmount` | Float | 中标通知书金额（元，两位小数） |
| `bidNoticeNo` | String | 中标通知书编号 |
| `contractAmount` | Float | 合同金额（元，两位小数） |
| `settlementSubmittedAmount` | Float | 结算送审金额（元，两位小数） |
| `differenceAmount` | Float | 差额（元，两位小数） |

#### 赔偿合同

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `No` | Integer | 序号 |
| `contractCounterpartyName` | String | 合同对方名称 |
| `compensationItem` | String | 赔偿事项 |
| `contractAmount` | Float | 合同金额（元，两位小数） |
| `settlementSubmittedAmount` | Float | 结算送审金额（元，两位小数） |
| `differenceAmount` | Float | 差额（元，两位小数） |

#### 物资采购合同1

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `No` | Integer | 序号 |
| `materialName` | String | 物料名称 |
| `contractQuantity` | Float | 合同数量 |
| `drawingQuantity` | Float | 施工图数量 |
| `unitPriceExcludingTax` | Float | 单价（不含税）（元，两位小数） |
| `differenceAmount` | Float | 差额（元，两位小数） |

#### 物资采购合同2

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `No` | Integer | 序号 |
| `materialName` | String | 物料名称 |
| `contractAmount` | Float | 合同金额（元，两位小数） |
| `bookedAmount` | Float | 入账金额（元，两位小数） |
| `differenceAmount` | Float | 差额（元，两位小数） |
| `remark` | String | 备注 |

#### 其他服务类合同

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `No` | Integer | 序号 |
| `serviceProvider` | String | 服务商 |
| `bidNotice` | String | 中标通知书 |
| `contractAmount` | Float | 合同金额（元，两位小数） |
| `submittedAmount` | Float | 送审金额（元，两位小数） |
| `settlementAmount` | Float | 结算金额（元，两位小数） |

---

### designReview（初设评审）

**文档类型标识**: `"document_type": "designReview"`

**数据结构**: 层级结构，大类包含子项数组

**完整响应示例**:

```json
{
  "document_type": "designReview",
  "data": [
    {
      "name": "变电工程",
      "Level": 0,
      "staticInvestment": 9728,
      "dynamicInvestment": 9910,
      "items": [
        {
          "No": 1,
          "name": "周村220kV变电站新建工程",
          "Level": 1,
          "staticInvestment": 9278,
          "dynamicInvestment": 9452
        },
        {
          "No": 2,
          "name": "凤城220kV变电站周村间隔扩建工程",
          "Level": 1,
          "staticInvestment": 450,
          "dynamicInvestment": 458
        }
      ]
    },
    {
      "name": "线路工程",
      "Level": 0,
      "staticInvestment": 4678,
      "dynamicInvestment": 4765,
      "items": [
        {
          "No": 1,
          "name": "凤城—金鼎π入周村变220kV线路工程",
          "Level": 1,
          "staticInvestment": 2960,
          "dynamicInvestment": 3015
        },
        {
          "No": 2,
          "name": "凤城—周村220kV线路工程",
          "Level": 1,
          "staticInvestment": 1718,
          "dynamicInvestment": 1750
        }
      ]
    }
  ]
}
```

**字段说明**:

#### 大类（Level=0）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `name` | String | 大类名称（如"变电工程"、"线路工程"） |
| `Level` | Integer | 层级标识，固定为 `0`（表示大类） |
| `staticInvestment` | Float | 静态投资总计（单位：万元） |
| `dynamicInvestment` | Float | 动态投资总计（单位：万元） |
| `items` | Array | 子项列表 |

#### 子项（Level=1）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `No` | Integer | 序号 |
| `name` | String | 工程名称 |
| `Level` | Integer | 层级标识，固定为 `1`（表示子项） |
| `staticInvestment` | Float | 静态投资（单位：万元） |
| `dynamicInvestment` | Float | 动态投资（单位：万元） |

**识别规则**:

- 大类：序号为中文数字，如"一"、"二"、"三"（不含括号）
- 子项：序号为带括号的中文数字，如"（一）"、"（二）"、"（三）"

---

## 完整接入示例

### Python示例

```python
import requests
import time
import json

def convert_pdf(file_path, doc_type, api_base_url="http://localhost:4214"):
    """
    转换PDF文件并获取JSON数据
    
    Args:
        file_path: PDF文件路径
        doc_type: 文档类型 ("settlementReport" 或 "designReview")
        api_base_url: API服务地址
    
    Returns:
        dict: JSON数据
    """
    # 1. 上传文件
    upload_url = f"{api_base_url}/convert"
    with open(file_path, "rb") as f:
        files = {"file": f}
        data = {"type": doc_type}
        response = requests.post(upload_url, files=files, data=data)
        response.raise_for_status()
        result = response.json()
        task_id = result["task_id"]
        print(f"任务已创建，task_id: {task_id}")
    
    # 2. 轮询任务状态
    status_url = f"{api_base_url}/task/{task_id}"
    max_wait_time = 300  # 最大等待5分钟
    start_time = time.time()
    
    while True:
        response = requests.get(status_url)
        response.raise_for_status()
        status = response.json()
        
        if status["status"] == "completed":
            print("处理完成")
            break
        elif status["status"] == "failed":
            raise Exception(f"处理失败: {status.get('error', '未知错误')}")
        
        # 检查超时
        if time.time() - start_time > max_wait_time:
            raise Exception("处理超时")
        
        print(f"处理中... ({status.get('progress', 0)}%)")
        time.sleep(2)  # 等待2秒后再次查询
    
    # 3. 获取JSON数据
    json_url = f"{api_base_url}/task/{task_id}/json"
    response = requests.get(json_url)
    response.raise_for_status()
    json_data = response.json()
    
    return json_data

# 使用示例
if __name__ == "__main__":
    # 处理结算报告
    settlement_data = convert_pdf("结算报告.pdf", "settlementReport")
    print(json.dumps(settlement_data, ensure_ascii=False, indent=2))
    
    # 处理初设评审
    design_data = convert_pdf("初设评审.pdf", "designReview")
    print(json.dumps(design_data, ensure_ascii=False, indent=2))
```

### JavaScript/Node.js示例

```javascript
const FormData = require('form-data');
const fs = require('fs');
const axios = require('axios');

async function convertPdf(filePath, docType, apiBaseUrl = 'http://localhost:4214') {
  // 1. 上传文件
  const form = new FormData();
  form.append('file', fs.createReadStream(filePath));
  form.append('type', docType);
  
  const uploadResponse = await axios.post(`${apiBaseUrl}/convert`, form, {
    headers: form.getHeaders()
  });
  
  const taskId = uploadResponse.data.task_id;
  console.log(`任务已创建，task_id: ${taskId}`);
  
  // 2. 轮询任务状态
  const maxWaitTime = 300000; // 5分钟
  const startTime = Date.now();
  
  while (true) {
    const statusResponse = await axios.get(`${apiBaseUrl}/task/${taskId}`);
    const status = statusResponse.data;
    
    if (status.status === 'completed') {
      console.log('处理完成');
      break;
    } else if (status.status === 'failed') {
      throw new Error(`处理失败: ${status.error || '未知错误'}`);
    }
    
    if (Date.now() - startTime > maxWaitTime) {
      throw new Error('处理超时');
    }
    
    console.log(`处理中... (${status.progress || 0}%)`);
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  
  // 3. 获取JSON数据
  const jsonResponse = await axios.get(`${apiBaseUrl}/task/${taskId}/json`);
  return jsonResponse.data;
}

// 使用示例
(async () => {
  try {
    const settlementData = await convertPdf('结算报告.pdf', 'settlementReport');
    console.log(JSON.stringify(settlementData, null, 2));
    
    const designData = await convertPdf('初设评审.pdf', 'designReview');
    console.log(JSON.stringify(designData, null, 2));
  } catch (error) {
    console.error('错误:', error.message);
  }
})();
```

---

## 注意事项

### 1. 文件要求

- **格式**: 仅支持PDF格式
- **页数**: 无限制（与 `noiseRec`、`emRec`、`opStatus` 类型的20页限制不同）
- **文件大小**: 建议不超过50MB

### 2. 处理特点

- **本地处理**: 不依赖外部API，处理速度更快
- **表格提取**: 自动提取PDF中的表格数据
- **智能识别**: 自动识别表格类型并解析为结构化数据

### 3. 数据准确性

- 所有金额字段保留两位小数
- 序号字段为整数
- 文本字段已清理换行符和多余空格

### 4. 错误处理

如果处理失败，响应中的 `status` 字段为 `"failed"`，`error` 字段包含错误信息：

```json
{
  "status": "failed",
  "error": "表格提取失败: ...",
  "message": "处理失败"
}
```

### 5. 任务管理

- 任务完成后，JSON数据会保留在内存中，可通过 `GET /task/{task_id}/json` 获取
- 建议在处理完成后及时获取数据，避免任务被清理
- 可通过 `DELETE /task/{task_id}` 主动删除任务

---

## 常见问题

### Q1: 如果PDF中没有找到预期的表格怎么办？

A: 系统会返回空的数组。例如，如果PDF中没有"审定结算汇总表"，则 `data["审定结算汇总表"]` 为空数组 `[]`。

### Q2: 如何处理多个相同类型的表格？

A: 系统会自动合并相同类型的表格。例如，如果PDF中有多个"合同执行情况"表格，它们会被合并为一个数组。

### Q3: 序号格式识别失败怎么办？

A: 对于 `designReview` 类型，如果序号格式无法识别（既不是中文数字，也不是带括号的中文数字），该行会被当作子项处理。如果当前没有大类，则作为独立项输出。

### Q4: 金额单位是什么？

A: 
- `settlementReport`: 所有金额单位为**元**（人民币）
- `designReview`: 所有金额单位为**万元**

### Q5: 如何处理跨页表格？

A: 系统会自动识别并合并跨页的表格，无需特殊处理。

---

## 技术支持

如有问题，请联系开发团队或查看项目文档。

**API服务地址**: `http://localhost:4214`（默认）

**API文档**: `http://localhost:4214/docs`（Swagger UI）
