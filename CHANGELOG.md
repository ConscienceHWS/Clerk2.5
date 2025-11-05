# PDF转换工具更新说明

## 版本历史

### v2.0.0 (最新版本)

#### 🎉 重大更新

**1. API接口简化**
- ✅ 移除了多个配置参数，简化API调用
  - 移除 `max_pages` 参数，改为自动处理：小于20页根据页数动态处理，大于20页直接返回错误
  - 移除 `formula_enable`、`table_enable` 参数（内部固定启用）
  - 移除 `embed_images` 参数（内部固定为 False）
  - 移除 `dpi`、`use_split` 参数
  - 移除 `output_json`、`model_name`、`gpu_memory_utilization` 参数（使用默认值）

**2. 新增文档类型参数**
- ✅ 添加 `type` 参数，支持指定文档类型进行解析
  - `noiseRec` → 噪声原始记录 (`noiseMonitoringRecord`)
  - `emRec` → 电磁原始记录 (`electromagneticTestRecord`)
  - `opStatus` → 工况信息 (`operatingConditionInfo`)

**3. 文件格式支持扩展**
- ✅ 支持上传图片格式文件（PNG、JPG、JPEG、BMP、TIFF、WEBP等）
- ✅ 自动识别文件类型并设置正确的 Content-Type

**4. 工况信息独立解析**
- ✅ 工况信息支持单独解析返回（通过 `type=opStatus`）
- ✅ 噪声检测记录支持无工况信息的情况（向后兼容）

**5. 服务部署优化**
- ✅ API服务器支持命令行参数配置
  - `--host`: 服务器监听地址
  - `--port`: 服务器监听端口
  - `--log-level`: 日志级别
  - `--workers`: 工作进程数（生产环境）
  - `--reload`: 自动重载（开发模式）
- ✅ 提供 systemd service 文件 (`pdf-converter-v2.service`)
- ✅ 支持环境变量和命令行参数双重配置

#### 📝 API变更详情

**POST /convert 接口变更：**

**v1 版本参数：**
```bash
POST /convert
- file (required)
- max_pages (optional, default=10)
- formula_enable (optional, default=True)
- table_enable (optional, default=True)
- embed_images (optional, default=True)
- model_name (optional)
- gpu_memory_utilization (optional, default=0.9)
- dpi (optional, default=200)
- output_json (optional, default=False)
- use_split (optional, default=False)
```

**v2 版本参数：**
```bash
POST /convert
- file (required): PDF或图片文件
- type (optional): 文档类型 (noiseRec | emRec | opStatus)
```

**示例调用：**
```bash
# v1 版本
curl -X POST "http://localhost:4213/convert" \
  -F "file=@example.pdf" \
  -F "max_pages=10" \
  -F "formula_enable=true" \
  -F "table_enable=true" \
  -F "output_json=true"

# v2 版本（简化）
curl -X POST "http://localhost:4214/convert" \
  -F "file=@example.pdf" \
  -F "type=noiseRec"
```

#### 🔧 技术改进

1. **页数限制机制**
   - 自动检测PDF页数（通过字节模式匹配）
   - 图片文件按1页处理
   - 超过20页直接返回400错误

2. **文档类型映射**
   - 短名称（API参数）→ 正式全称（代码内部）
   - `noiseRec` → `noiseMonitoringRecord`
   - `emRec` → `electromagneticTestRecord`
   - `opStatus` → `operatingConditionInfo`

3. **JSON序列化优化**
   - 修复工况信息对象的JSON序列化问题
   - 确保所有数据模型正确转换为字典格式

#### 📦 部署说明

**安装 systemd 服务：**
```bash
# 1. 复制 service 文件
sudo cp pdf-converter-v2.service /etc/systemd/system/

# 2. 修改 service 文件中的路径配置（根据实际情况）
# - WorkingDirectory
# - ExecStart 中的 Python 路径
# - 环境变量配置

# 3. 重新加载 systemd
sudo systemctl daemon-reload

# 4. 启动服务
sudo systemctl start pdf-converter-v2

# 5. 设置开机自启
sudo systemctl enable pdf-converter-v2

# 6. 查看服务状态
sudo systemctl status pdf-converter-v2
```

**直接运行（开发/测试）：**
```bash
# 使用默认配置
python pdf_converter_v2/api_server.py

# 指定端口和主机
python pdf_converter_v2/api_server.py --host 0.0.0.0 --port 4214

# 开发模式（自动重载）
python pdf_converter_v2/api_server.py --reload --log-level debug

# 生产模式（多进程）
python pdf_converter_v2/api_server.py --workers 4 --log-level info
```

#### ⚠️ 迁移指南

**从 v1 迁移到 v2：**

1. **更新API端点**
   - v1 默认端口: `4213`
   - v2 默认端口: `4214`

2. **简化请求参数**
   - 移除所有配置参数，只保留 `file` 和 `type`
   - `type` 参数可选，不传则自动检测文档类型

3. **更新服务配置**
   - 使用新的 service 文件 `pdf-converter-v2.service`
   - 更新启动脚本路径

4. **环境变量配置**
   - v2 版本通过环境变量配置外部API地址等参数
   - 主要环境变量：
     - `API_URL`: 外部API地址（默认: http://192.168.2.3:8000）
     - `API_HOST`: 服务监听地址（默认: 0.0.0.0）
     - `API_PORT`: 服务监听端口（默认: 4214）
     - `LOG_LEVEL`: 日志级别（默认: info）

#### 🐛 问题修复

1. 修复工况信息对象JSON序列化错误
2. 修复图片文件上传时的Content-Type设置
3. 优化页数检测逻辑，提高准确性

---

### v1.x.x

#### 主要特性

1. **本地PDF处理**
   - 使用 MinerU 进行本地PDF转换
   - 支持OCR文本提取和解析
   - 支持图片裁剪和base64嵌入

2. **完整的API参数**
   - 支持细粒度的配置参数
   - 可配置模型、GPU、DPI等参数

3. **文档类型**
   - 噪声检测记录 (`noise_detection`)
   - 电磁检测记录 (`electromagnetic_detection`)

#### API端点

- `POST /convert`: 转换文件（同步/异步）
- `GET /task/{task_id}`: 查询任务状态
- `GET /download/{task_id}/markdown`: 下载Markdown文件
- `GET /download/{task_id}/json`: 下载JSON文件
- `DELETE /task/{task_id}`: 删除任务

---

## 版本对比

| 特性 | v1 | v2 |
|------|----|----|
| PDF处理方式 | 本地MinerU处理 | 外部API接口处理 |
| 图片格式支持 | 仅PDF | PDF + 图片格式 |
| API参数数量 | 10+ 个参数 | 2 个参数（file + type） |
| 页数限制 | 可配置 | 自动限制（≤20页） |
| 文档类型 | 自动检测 | 支持指定类型 |
| 工况信息 | 包含在噪声记录中 | 支持独立解析 |
| 服务部署 | 基础支持 | 命令行参数 + systemd |
| 默认端口 | 4213 | 4214 |

---

## 更新日志格式说明

- ✅ 新增功能
- 🔧 技术改进
- 🐛 问题修复
- ⚠️ 破坏性变更
- 📝 文档更新
- 📦 部署相关

---

## 反馈与支持

如有问题或建议，请提交 Issue 或联系开发团队。

