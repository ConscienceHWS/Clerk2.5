# FastAPI服务启动指南

## 推荐启动方式

### 方式1：在项目根目录使用启动脚本（推荐）
```bash
# 在 /mnt/win_d/Clerk2.5 目录下
python start_api.py
```

### 方式2：使用uvicorn命令（推荐）
```bash
# 在 /mnt/win_d/Clerk2.5 目录下
uvicorn pdf_converter.api.main:app --host 0.0.0.0 --port 8000
```

### 方式3：使用模块方式
```bash
# 在 /mnt/win_d/Clerk2.5 目录下
python -m uvicorn pdf_converter.api.main:app --host 0.0.0.0 --port 8000
```

### 方式4：使用pdf_converter目录内的脚本
```bash
# 在 /mnt/win_d/Clerk2.5/pdf_converter 目录下
python api_server.py
```
注意：此方式需要正确配置Python路径。

## 环境变量配置

可以通过环境变量配置服务：

```bash
# 设置端口
export API_PORT=8080

# 设置主机
export API_HOST=127.0.0.1

# 启动服务
python start_api.py
```

## 测试服务

服务启动后，访问以下地址：

- API文档（Swagger UI）: http://localhost:8000/docs
- API文档（ReDoc）: http://localhost:8000/redoc
- 健康检查: http://localhost:8000/health

## 常见问题

### 问题1: ModuleNotFoundError: No module named 'pdf_converter'

**解决方案**：
- 确保在项目根目录（包含 `pdf_converter` 目录的目录）下运行
- 或使用 `uvicorn` 命令启动（推荐）

### 问题2: 端口已被占用

**解决方案**：
```bash
# 指定其他端口
uvicorn pdf_converter.api.main:app --host 0.0.0.0 --port 8080

# 或使用环境变量
export API_PORT=8080
python start_api.py
```

### 问题3: 导入错误

**解决方案**：
确保已安装所有依赖：
```bash
pip install fastapi uvicorn python-multipart
```

## 生产环境部署

### 使用Gunicorn（推荐）
```bash
pip install gunicorn
gunicorn pdf_converter.api.main:app \
    -w 4 \
    -k uvicorn.workers.UvicornWorker \
    -b 0.0.0.0:8000 \
    --timeout 120
```

### 使用systemd服务（示例）

创建 `/etc/systemd/system/pdf-converter-api.service`:
```ini
[Unit]
Description=PDF Converter API Service
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/mnt/win_d/Clerk2.5
Environment="PATH=/mnt/win_d/Clerk2.5/venv/bin"
ExecStart=/mnt/win_d/Clerk2.5/venv/bin/uvicorn pdf_converter.api.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl enable pdf-converter-api
sudo systemctl start pdf-converter-api
sudo systemctl status pdf-converter-api
```

