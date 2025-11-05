# PDF转换工具 v1 到 v2 迁移指南

本文档帮助您从 v1 版本迁移到 v2 版本。

## 快速对比

| 项目 | v1 | v2 |
|------|----|----|
| 默认端口 | 4213 | 4214 |
| API参数 | 10+ 个 | 2 个 |
| 文件格式 | 仅PDF | PDF + 图片 |
| 页数限制 | 可配置 | 自动限制（≤20页） |

## 1. API调用变更

### v1 版本调用示例

```bash
curl -X POST "http://localhost:4213/convert" \
  -F "file=@example.pdf" \
  -F "max_pages=10" \
  -F "formula_enable=true" \
  -F "table_enable=true" \
  -F "embed_images=true" \
  -F "output_json=true" \
  -F "use_split=false"
```

### v2 版本调用示例

```bash
# 基本调用（自动检测类型）
curl -X POST "http://localhost:4214/convert" \
  -F "file=@example.pdf"

# 指定文档类型
curl -X POST "http://localhost:4214/convert" \
  -F "file=@example.pdf" \
  -F "type=noiseRec"
```

### 参数映射

**已移除的参数（v2 不再需要）：**
- ❌ `max_pages` - 自动处理，超过20页会拒绝
- ❌ `formula_enable` - 内部固定启用
- ❌ `table_enable` - 内部固定启用
- ❌ `embed_images` - 内部固定为 False
- ❌ `dpi` - 不再需要
- ❌ `use_split` - 不再需要
- ❌ `output_json` - 默认启用
- ❌ `model_name` - 使用默认值
- ❌ `gpu_memory_utilization` - 使用默认值

**新增的参数：**
- ✅ `type` - 文档类型（可选）
  - `noiseRec`: 噪声原始记录
  - `emRec`: 电磁原始记录
  - `opStatus`: 工况信息

## 2. 服务部署变更

### v1 版本部署

```bash
# 使用 start_api.py
python start_api.py
```

### v2 版本部署

**方式1：直接运行（开发/测试）**
```bash
# 使用默认配置
python pdf_converter_v2/api_server.py

# 指定参数
python pdf_converter_v2/api_server.py --host 0.0.0.0 --port 4214 --log-level info
```

**方式2：systemd 服务（生产环境）**
```bash
# 1. 复制服务文件
sudo cp pdf-converter-v2.service /etc/systemd/system/

# 2. 修改配置（根据实际情况）
sudo nano /etc/systemd/system/pdf-converter-v2.service

# 3. 启动服务
sudo systemctl daemon-reload
sudo systemctl start pdf-converter-v2
sudo systemctl enable pdf-converter-v2
```

## 3. 环境变量配置

### v1 版本环境变量

```bash
API_HOST=0.0.0.0
API_PORT=4213
LOG_LEVEL=INFO
```

### v2 版本环境变量

```bash
# API服务配置
API_HOST=0.0.0.0
API_PORT=4214
LOG_LEVEL=INFO

# 外部API配置（v2新增）
API_URL=http://192.168.2.3:8000
BACKEND=vlm-vllm-async-engine
PARSE_METHOD=auto
LANGUAGE=ch

# 日志配置
PDF_CONVERTER_LOG_DIR=/path/to/logs
```

## 4. 代码调用变更

### Python 代码示例

**v1 版本：**
```python
import requests

files = {"file": open("example.pdf", "rb")}
data = {
    "max_pages": 10,
    "formula_enable": True,
    "table_enable": True,
    "output_json": True
}
response = requests.post("http://localhost:4213/convert", files=files, data=data)
```

**v2 版本：**
```python
import requests

files = {"file": open("example.pdf", "rb")}
data = {
    "type": "noiseRec"  # 可选
}
response = requests.post("http://localhost:4214/convert", files=files, data=data)
```

## 5. 响应格式

响应格式保持不变，但需要注意：

1. **默认返回JSON**：v2 版本默认启用 JSON 输出
2. **文档类型字段**：`document_type` 字段使用正式全称
   - v1: `"noise_detection"`
   - v2: `"noiseMonitoringRecord"`

## 6. 新功能使用

### 支持图片格式

```bash
# 上传图片文件
curl -X POST "http://localhost:4214/convert" \
  -F "file=@image.png" \
  -F "type=noiseRec"
```

### 单独解析工况信息

```bash
# 只解析工况信息
curl -X POST "http://localhost:4214/convert" \
  -F "file=@operating_condition.pdf" \
  -F "type=opStatus"
```

## 7. 常见问题

### Q: v1 和 v2 可以同时运行吗？

A: 可以，它们使用不同的端口（v1: 4213, v2: 4214），不会冲突。

### Q: 如何回退到 v1？

A: 继续使用 v1 的服务即可，两个版本可以共存。

### Q: v2 的 JSON 格式和 v1 一样吗？

A: 基本一致，但 `document_type` 字段使用正式全称。

### Q: 超过20页的文件怎么处理？

A: v2 会自动拒绝超过20页的文件，返回400错误。如需处理大文件，请使用 v1 版本。

## 8. 迁移检查清单

- [ ] 更新API端点地址（端口从 4213 改为 4214）
- [ ] 移除所有配置参数，只保留 `file` 和可选的 `type`
- [ ] 更新环境变量配置
- [ ] 测试文件上传和转换功能
- [ ] 验证JSON输出格式
- [ ] 更新服务部署配置（如使用systemd）
- [ ] 更新客户端代码（如使用SDK）

## 9. 获取帮助

如有问题，请参考：
- [CHANGELOG.md](./CHANGELOG.md) - 详细更新说明
- [pdf_converter_v2/README.md](./pdf_converter_v2/README.md) - v2 版本文档
- API文档：启动服务后访问 `http://localhost:4214/docs`

