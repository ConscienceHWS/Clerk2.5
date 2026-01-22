# PDF 转换服务 API 接口文档

## 概述

本服务提供 PDF 文档解析功能，支持多种电力工程文档类型的结构化数据提取。

**服务地址**: `http://{host}:14213`

---

## 文档类型与模板数据源对照表

| type | 说明 | 模板数据源文件 |
|------|------|----------------|
| fsApproval | 可研批复投资估算 | `2-（可研批复）晋电发展〔2017〕831号+国网山西省电力公司关于临汾古县、晋城周村220kV输变电等工程可行性研究报告的批复.pdf` |
| fsReview | 可研评审投资估算 | `1-（可研评审）晋电经研规划〔2017〕187号(盖章)国网山西经研院关于山西晋城周村220kV输变电工程可行性研究报告的评审意见.pdf` |
| pdApproval | 初设批复概算投资 | `5-（初设批复）晋电建设〔2019〕566号　国网山西省电力公司关于晋城周村220kV输变电工程初步设计的批复.pdf` |
| designReview | 初设评审概算投资 | `4-（初设评审）中电联电力建设技术经济咨询中心技经〔2019〕201号关于山西周村220kV输变电工程初步设计的评审意见.pdf` |
| settlementReport | 结算审计报告 | `9-（结算报告）山西晋城周村220kV输变电工程结算审计报告.pdf` |
| finalAccount | 竣工决算审核报告 | `10-（决算报告）盖章页-山西晋城周村220kV输变电工程竣工决算审核报告（中瑞诚鉴字（2021）第002040号）.pdf` |

### 文档标题特征识别规则

| type | 标题关键词 | 返回结构 |
|------|-----------|----------|
| fsApproval | 含"可研批复" | 三层嵌套 + 建设规模 |
| fsReview | 含"可研评审" | 两层嵌套 |
| pdApproval | 含"初设批复" | 两层嵌套 |
| designReview | 含"初设评审" | 两层嵌套 |
| settlementReport | 含"结算报告"或"审计报告" | 多表对象 |
| finalAccount | 含"竣工决算"或"决算审核" | 两层嵌套（按项目分组） |

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
| `finalAccount` | 竣工决算审核报告 | 嵌套结构（按项目分组） |
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

对象结构，包含三种表格类型（与 settlementReport 结构类似）：
1. **初设评审的概算投资**（表头含：序号、工程名称、建设规模、静态投资、动态投资）- 两层嵌套结构
2. **初设评审的概算投资明细**（表头含：序号、工程或费用名称、建筑工程费、设备购置费、安装工程费、其他费用、合计）- 三层嵌套结构，按工程名称分组
3. **初设评审的概算投资费用**（表头含：序号、工程或费用名称、费用金额、各项占静态投资%、单位投资）- 三层嵌套结构，按工程名称分组

**返回格式**:

```json
{
  "document_type": "designReview",
  "data": {
    "初设评审的概算投资": [
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
    ],
    "初设评审的概算投资明细": [
      {
        "name": "周村220kV变电站新建工程",
        "items": [
          {
            "No": 1,
            "Level": 1,
            "projectOrExpenseName": "主辅生产工程",
            "constructionProjectCost": 1537.0,
            "equipmentPurchaseCost": 4309.0,
            "installationProjectCost": 1417.0,
            "otherExpenses": 0.0,
            "items": [
              {
                "No": 1,
                "Level": 2,
                "projectOrExpenseName": "主要生产工程",
                "constructionProjectCost": 1188.0,
                "equipmentPurchaseCost": 4294.0,
                "installationProjectCost": 1417.0,
                "otherExpenses": 0.0
              }
            ]
          },
          {
            "No": 4,
            "Level": 1,
            "projectOrExpenseName": "其他费用",
            "constructionProjectCost": 0.0,
            "equipmentPurchaseCost": 0.0,
            "installationProjectCost": 0.0,
            "otherExpenses": 1229.0,
            "items": [
              {
                "No": 8,
                "Level": 2,
                "projectOrExpenseName": "建设场地征用及清理费",
                "constructionProjectCost": 0.0,
                "equipmentPurchaseCost": 0.0,
                "installationProjectCost": 0.0,
                "otherExpenses": 326.0
              }
            ]
          }
        ]
      }
    ],
    "初设评审的概算投资费用": [
      {
        "name": "凤城—金鼎π入周村变220kV线路工程",
        "items": [
          {
            "No": 1,
            "Level": 1,
            "projectOrExpenseName": "输电线路本体工程",
            "cost": 2265.0,
            "items": []
          },
          {
            "No": 4,
            "Level": 1,
            "projectOrExpenseName": "其他费用",
            "cost": 415.0,
            "items": [
              {
                "No": 6,
                "Level": 2,
                "projectOrExpenseName": "建设场地征用及清理费",
                "cost": 174.0
              }
            ]
          }
        ]
      }
    ]
  }
}
```

**初设评审的概算投资 字段说明**（两层嵌套）:

| 字段 | 类型 | 说明 |
|------|------|------|
| name | String | 工程大类名称（如"变电工程"、"线路工程"） |
| Level | Integer | 层级（0=大类, 1=子项） |
| staticInvestment | Number | 静态投资（万元） |
| dynamicInvestment | Number | 动态投资（万元） |
| items | Array | 子项目列表 |

**初设评审的概算投资明细 字段说明**（三层嵌套）:

第一层（按工程名称分组）:

| 字段 | 类型 | 说明 |
|------|------|------|
| name | String | 单项工程名称（如"周村220kV变电站新建工程"） |
| items | Array | 该工程下的费用项目列表 |

第二层（费用大类，Level=1）:

| 字段 | 类型 | 说明 |
|------|------|------|
| No | Integer | 序号 |
| Level | Integer | 1（大类） |
| projectOrExpenseName | String | 工程或费用名称 |
| constructionProjectCost | Number | 建筑工程费（万元） |
| equipmentPurchaseCost | Number | 设备购置费（万元） |
| installationProjectCost | Number | 安装工程费（万元） |
| otherExpenses | Number | 其他费用（万元） |
| items | Array | 子项列表 |

第三层（费用子项，Level=2）:

| 字段 | 类型 | 说明 |
|------|------|------|
| No | Integer | 序号 |
| Level | Integer | 2（子项） |
| projectOrExpenseName | String | 工程或费用名称（已去除"其中："前缀） |
| constructionProjectCost | Number | 建筑工程费（万元） |
| equipmentPurchaseCost | Number | 设备购置费（万元） |
| installationProjectCost | Number | 安装工程费（万元） |
| otherExpenses | Number | 其他费用（万元） |

**初设评审的概算投资费用 字段说明**（三层嵌套）:

第一层（按工程名称分组）:

| 字段 | 类型 | 说明 |
|------|------|------|
| name | String | 单项工程名称（如"凤城—金鼎π入周村变220kV线路工程"） |
| items | Array | 该工程下的费用项目列表 |

第二层（费用大类，Level=1）:

| 字段 | 类型 | 说明 |
|------|------|------|
| No | Integer | 序号 |
| Level | Integer | 1（大类） |
| projectOrExpenseName | String | 工程或费用名称 |
| cost | Number | 费用金额（万元） |
| items | Array | 子项列表 |

第三层（费用子项，Level=2）:

| 字段 | 类型 | 说明 |
|------|------|------|
| No | Integer | 序号 |
| Level | Integer | 2（子项） |
| projectOrExpenseName | String | 工程或费用名称（已去除"其中："前缀） |
| cost | Number | 费用金额（万元） |

**Level 判断规则**:

| 序号格式 | Level | 说明 |
|---------|-------|------|
| 一、二、三 | 1 | 大类（中文数字） |
| 1、2、3 | 1 | 大类（阿拉伯数字） |
| (1)、（一）、（二） | 2 | 子项（带括号） |
| 以"其中："开头 | 2 | 子项（特殊标识，输出时去除前缀） |
| "可抵扣固定资产增值税额" | 1 | 特殊处理为大类 |

> **说明**: 明细表和费用表会从 PDF 中提取多个表格（如"周村220kV变电站新建工程总概算表"、"凤城220kV变电站周村间隔扩建工程总概算表"），每个表格按工程名称分组，Level 2 的子项嵌套在对应的 Level 1 父项下。

---

### 5.5 竣工决算审核报告 (finalAccount)

按项目分组的两层嵌套结构，提取单项工程投资完成情况。

```json
{
  "document_type": "finalAccount",
  "data": [
    {
      "No": 1,
      "name": "周村220kV输变电工程变电站新建工程",
      "items": [
        {
          "feeName": "建筑安装工程",
          "estimatedCost": "35880000.00",
          "approvedFinalAccountExcludingVat": "25251424.77",
          "vatAmount": "2272628.23",
          "costVariance": "8355947.00",
          "varianceRate": "23.29%"
        },
        {
          "feeName": "设备购置",
          "estimatedCost": "43090000.00",
          "approvedFinalAccountExcludingVat": "48823212.30",
          "vatAmount": "6347015.53",
          "costVariance": "-12080227.83",
          "varianceRate": "-28.03%"
        },
        {
          "feeName": "其他费用",
          "estimatedCost": "15550000.00",
          "approvedFinalAccountExcludingVat": "11728700.03",
          "vatAmount": "418272.16",
          "costVariance": "3403027.81",
          "varianceRate": "21.88%"
        }
      ]
    },
    {
      "No": 2,
      "name": "周村间隔扩建工程",
      "items": [...]
    }
  ]
}
```

**第一层（项目）字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| No | Integer | 项目序号（如1、2、3、4） |
| name | String | 项目名称（审计内容） |
| items | Array | 费用明细列表 |

**第二层（费用明细）字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| feeName | String | 费用项目（建筑安装工程、设备购置、其他费用） |
| estimatedCost | String | 概算金额（元） |
| approvedFinalAccountExcludingVat | String | 决算金额审定不含税（元） |
| vatAmount | String | 增值税额（元） |
| costVariance | String | 超节支金额（元），正数表示节支，负数表示超支 |
| varianceRate | String | 超节支率（如"23.29%"或"-28.03%"） |

> **说明**: 该文档为扫描件，通过 OCR 识别后提取"单项工程的投资完成情况"章节中的各项目投资表格数据。

---

### 5.6 结算审计报告 (settlementReport)

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
4. **文件大小**: 支持最大 50MB 的 PDF 文件
5. **类型指定**: `type` 参数必须与文档内容匹配，否则解析结果可能为空

