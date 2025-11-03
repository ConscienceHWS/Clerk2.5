# PDF Converter API Linux Service 安装指南

本文档说明如何在 Linux 系统上安装和配置 PDF Converter API 作为 systemd 服务。

## 前置要求

1. Python 3.8+ 已安装
2. 虚拟环境已创建并安装了所有依赖
3. systemd 系统（大多数现代 Linux 发行版）

## 安装步骤

### 1. 检查文件路径

首先，确认以下路径是否正确：

- **项目根目录**: `/mnt/win_d/Clerk2.5`
- **Python 虚拟环境**: `/mnt/win_d/Clerk2.5/venv/bin/python`
- **启动脚本**: `/mnt/win_d/Clerk2.5/start_api.py`
- **日志目录**: `/mnt/win_d/Clerk2.5/logs`（需要确保目录存在）

### 2. 创建必要的目录

```bash
# 创建日志目录
mkdir -p /mnt/win_d/Clerk2.5/logs

# 创建输出目录（如果不存在）
mkdir -p /mnt/win_d/Clerk2.5/output

# 创建临时目录（如果不存在）
mkdir -p /mnt/win_d/Clerk2.5/tmp
```

### 3. 复制 service 文件

将 `pdf-converter.service` 文件复制到 systemd 目录：

```bash
# 复制到 systemd 用户服务目录（推荐，不需要 root）
mkdir -p ~/.config/systemd/user/
cp pdf-converter.service ~/.config/systemd/user/

# 或者复制到系统服务目录（需要 root 权限）
sudo cp pdf-converter.service /etc/systemd/system/
```

### 4. 编辑 service 文件（如果需要）

根据实际情况修改 service 文件中的路径：

```bash
# 如果是用户服务
nano ~/.config/systemd/user/pdf-converter.service

# 如果是系统服务
sudo nano /etc/systemd/system/pdf-converter.service
```

主要需要检查的配置：
- `User`: 运行服务的用户
- `WorkingDirectory`: 项目根目录路径
- `Environment="PATH"`: Python 虚拟环境路径
- `ExecStart`: 启动脚本路径

### 5. 重载 systemd 配置

```bash
# 如果是用户服务
systemctl --user daemon-reload

# 如果是系统服务
sudo systemctl daemon-reload
```

### 6. 启用并启动服务

```bash
# 如果是用户服务
systemctl --user enable pdf-converter.service
systemctl --user start pdf-converter.service

# 如果是系统服务
sudo systemctl enable pdf-converter.service
sudo systemctl start pdf-converter.service
```

### 7. 检查服务状态

```bash
# 如果是用户服务
systemctl --user status pdf-converter.service

# 如果是系统服务
sudo systemctl status pdf-converter.service
```

## 常用命令

### 查看服务状态

```bash
# 用户服务
systemctl --user status pdf-converter.service

# 系统服务
sudo systemctl status pdf-converter.service
```

### 查看服务日志

```bash
# 使用 journalctl 查看日志
journalctl -u pdf-converter.service -f

# 查看最近 100 行日志
journalctl -u pdf-converter.service -n 100

# 查看今天的日志
journalctl -u pdf-converter.service --since today
```

### 重启服务

```bash
# 用户服务
systemctl --user restart pdf-converter.service

# 系统服务
sudo systemctl restart pdf-converter.service
```

### 停止服务

```bash
# 用户服务
systemctl --user stop pdf-converter.service

# 系统服务
sudo systemctl stop pdf-converter.service
```

### 禁用服务（开机不自启）

```bash
# 用户服务
systemctl --user disable pdf-converter.service

# 系统服务
sudo systemctl disable pdf-converter.service
```

## 验证服务

服务启动后，可以通过以下方式验证：

### 1. 检查服务状态

```bash
systemctl --user status pdf-converter.service
# 或
sudo systemctl status pdf-converter.service
```

应该看到状态为 `active (running)`。

### 2. 测试健康检查端点

```bash
curl http://localhost:4213/health
```

应该返回：
```json
{"status":"healthy","service":"pdf_converter"}
```

### 3. 查看 API 文档

在浏览器中打开：
```
http://localhost:4213/docs
```

## 故障排除

### 服务无法启动

1. **检查日志**：
   ```bash
   journalctl -u pdf-converter.service -n 50
   ```

2. **检查路径是否正确**：
   ```bash
   # 检查 Python 虚拟环境是否存在
   ls -l /mnt/win_d/Clerk2.5/venv/bin/python
   
   # 检查启动脚本是否存在
   ls -l /mnt/win_d/Clerk2.5/start_api.py
   ```

3. **手动测试启动**：
   ```bash
   cd /mnt/win_d/Clerk2.5
   /mnt/win_d/Clerk2.5/venv/bin/python start_api.py
   ```

### 端口被占用

如果端口 4213 被占用，可以修改 service 文件中的端口：

```bash
# 编辑 service 文件，修改
Environment="API_PORT=4213"
# 为其他端口，如
Environment="API_PORT=8080"
```

然后重启服务。

### 权限问题

确保服务用户有权限访问：
- 项目目录
- 日志目录
- 输出目录
- 临时目录

```bash
# 检查目录权限
ls -la /mnt/win_d/Clerk2.5/

# 如果需要，修改权限
chmod -R 755 /mnt/win_d/Clerk2.5/
```

## 用户服务 vs 系统服务

### 用户服务（推荐）

- 优点：
  - 不需要 root 权限
  - 更安全
  - 用户登录时自动启动
  
- 缺点：
  - 用户登出后可能停止（除非启用了 linger）
  - 只能由创建服务的用户管理

启用 linger（用户登出后服务继续运行）：
```bash
loginctl enable-linger $USER
```

### 系统服务

- 优点：
  - 系统启动时自动启动
  - 不依赖用户登录状态
  
- 缺点：
  - 需要 root 权限
  - 需要更谨慎的安全配置

## 环境变量配置

可以通过修改 service 文件中的 `Environment` 行来配置环境变量：

```ini
Environment="API_HOST=0.0.0.0"
Environment="API_PORT=4213"
Environment="LOG_LEVEL=INFO"
Environment="MINERU_MODEL_SOURCE=modelscope"
```

修改后需要重载并重启服务：
```bash
systemctl --user daemon-reload
systemctl --user restart pdf-converter.service
```

## 自动重启配置

service 文件已配置自动重启：

```ini
Restart=always
RestartSec=10
StartLimitInterval=300
StartLimitBurst=5
```

这意味着：
- 服务异常退出时会自动重启
- 重启前等待 10 秒
- 如果在 300 秒内重启超过 5 次，则停止尝试重启

## 日志管理

服务日志可以通过 journalctl 查看：

```bash
# 实时查看日志
journalctl -u pdf-converter.service -f

# 查看特定时间的日志
journalctl -u pdf-converter.service --since "2024-01-01 00:00:00"

# 查看错误日志
journalctl -u pdf-converter.service -p err
```

应用自身的日志文件保存在：
```
/mnt/win_d/Clerk2.5/logs/
```

## 安全建议

1. **不要使用 root 运行**（除非必须）：
   ```ini
   User=your-username
   Group=your-groupname
   ```

2. **启用安全选项**（在 service 文件中取消注释）：
   ```ini
   NoNewPrivileges=true
   PrivateTmp=true
   ProtectSystem=strict
   ProtectHome=true
   ```

3. **限制文件访问**：
   ```ini
   ReadWritePaths=/mnt/win_d/Clerk2.5/tmp /mnt/win_d/Clerk2.5/logs
   ```

4. **配置防火墙**：
   只允许必要的端口对外开放。

## 支持

如有问题，请查看：
- 服务日志：`journalctl -u pdf-converter.service`
- 应用日志：`/mnt/win_d/Clerk2.5/logs/`
- 启动脚本输出

