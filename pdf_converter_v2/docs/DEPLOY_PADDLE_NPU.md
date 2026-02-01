# 在 Paddle NPU 容器内部署 pdf_converter_v2

本文档说明如何在 Docker 容器 `paddle-npu-dev`（已安装 PaddlePaddle NPU、PaddleX）内部署并运行 pdf_converter_v2 项目。

---

## 服务器信息（阿里云极客营）

| 项 | 说明 |
|----|------|
| **主机名** | geek.gc |
| **操作系统** | Linux |
| **公网 IP** | 47.101.133.94 |
| **SSH 端口** | 28529 |
| **登录用户** | anyuan |
| **认证** | 已配置公钥（密钥登录） |
| **描述** | 阿里云极客营服务器 |

**SSH 连接示例：**
```bash
ssh anyuan@47.101.133.94 -p 28529
```

**连接安源内网（在极客营服务器上执行）：**
```bash
ssh root@localhost -p 23456
```

**硬件与容器：**
- **架构**：ARM + 华为 910B 显卡 NPU
- **容器名**：`paddle-npu-dev`
- **进入容器**：`docker exec -it paddle-npu-dev bash`

**容器内 Paddle 环境：**
- 验证：`python -c "import paddle; print(paddle.version)"`
- 已安装：`paddle-custom-npu 3.3.0`、`paddlepaddle 3.3.0`、`paddlex 3.4.0`、`paddle2onnx 1.3.1`

---

## 外网访问（端口映射与防火墙）

容器内服务监听 `0.0.0.0:5282` 只对**容器内部**可见，外网要访问需做两步。

### 1. 把容器端口映射到宿主机

容器**启动时**要加上端口映射，例如：

```bash
# 宿主机上启动容器时（示例）
docker run -d --name paddle-npu-dev \
  -p 5282:5282 \
  -p 4214:4214 \
  ... 其他参数 ...  <镜像名>
```

- **5282**：MinerU API（file_parse）
- **4214**：pdf_converter_v2 API（若也在本容器跑）

**若容器已经存在且当时没加 `-p`：**

- **方式 A**：用当前容器重新建一个带端口映射的（推荐）
  ```bash
  # 宿主机
  docker stop paddle-npu-dev
  docker commit paddle-npu-dev paddle-npu-dev:bak
  docker run -d --name paddle-npu-dev-new \
    -p 5282:5282 -p 4214:4214 \
    -v /work:/work \
    paddle-npu-dev:bak
  # 之后用 paddle-npu-dev-new 进入，旧容器可删或保留
  ```
- **方式 B**：查一下当前容器是否已有映射
  ```bash
  docker port paddle-npu-dev
  ```
  若没有 5282，只能重新 `docker run` 一次并加上 `-p 5282:5282`。

### 2. 宿主机 / 云安全组放行端口

在**阿里云控制台**：

1. 打开 **ECS → 安全组**，找到该实例使用的安全组。
2. **入方向** 添加规则：端口 **5282**（及 4214 如需要），来源 `0.0.0.0/0`（或限定 IP），协议 TCP。
3. 保存后，外网即可访问。

若宿主机自己还有防火墙（如 iptables/ufw），也需放行 5282（和 4214）。

### 3. 外网访问地址

- **MinerU API 文档**：`http://47.101.133.94:5282/docs`
- **MinerU file_parse**：`http://47.101.133.94:5282/file_parse`（POST）
- **pdf_converter_v2 健康检查**（若端口 4214 已映射）：`http://47.101.133.94:4214/health`

本地或其它机器测试：

```bash
curl http://47.101.133.94:5282/docs
```

能打开即表示外网访问正常。

### 4. 用 curl 测试 MinerU /file_parse（与代码调用参数一致）

以下命令与 `pdf_converter_v2/processor/converter.py` 中调用 MinerU 的表单参数一致（`convert_to_markdown` 的默认值）。

**NPU 容器内必须使用 `backend=pipeline`**：vLLM 未安装且面向 GPU，使用 `vlm-vllm-async-engine` 会报错 `Please install vllm to use the vllm-async-engine backend`。GPU 环境可改用 `backend=vlm-vllm-async-engine`。

**同一台机子测试（MinerU 在本机 5282）：**

```bash
# 将图片路径换成你的文件；NPU 下使用 backend=pipeline
curl -X POST "http://127.0.0.1:5282/file_parse" \
  -F "files=@./4Qqasa3JZL3a1W7jSD4vlQe0820d98a3a85b058d371be99fe2ce07.jpg" \
  -F "return_middle_json=false" \
  -F "return_model_output=true" \
  -F "return_md=true" \
  -F "return_images=true" \
  -F "end_page_id=99999" \
  -F "parse_method=auto" \
  -F "start_page_id=0" \
  -F "lang_list=ch" \
  -F "output_dir=./output" \
  -F "server_url=string" \
  -F "return_content_list=false" \
  -F "backend=pipeline" \
  -F "table_enable=true" \
  -F "response_format_zip=true" \
  -F "formula_enable=true" \
  -o result.zip
```

- **返回 zip**：`response_format_zip=true` 时响应为 zip，用 `-o result.zip` 保存。
- **返回 JSON**：若想直接看 JSON，可改为 `-F "response_format_zip=false"` 并 `-o result.json`。
- **外网访问**：把 `127.0.0.1:5282` 换成公网地址（如 `47.101.133.94:5282`），并确保端口已映射与安全组放行。

---

## 环境要求

- 已进入容器：`docker exec -it paddle-npu-dev bash`
- 已安装：`paddle-custom-npu`、`paddlepaddle`、`paddlex`、`paddle2onnx`
- 验证 Paddle：`python -c "import paddle; print(paddle.version)"`

## 部署方式概览

pdf_converter_v2 有两种运行方式：

1. **仅部署 API 服务**：在容器内只跑本项目的 FastAPI（/convert 等），OCR 仍调用外部 `file_parse` 接口（可指向宿主机或其他容器）。
2. **API + 本机 OCR**：若同一容器内还部署了提供 `file_parse` 的 OCR 服务（如 MinerU 等），可将 `API_URL` 指向本机，实现闭环。

以下步骤以「仅部署 API 服务」为例，OCR 地址通过环境变量配置。

---

## 步骤 1：进入容器并准备代码

```bash
# 宿主机执行
docker exec -it paddle-npu-dev bash
```

在容器内，将项目放到统一目录（例如 `/workspace`），二选一：

**方式 A：挂载宿主机目录（推荐）**

```bash
# 宿主机启动容器时挂载，例如：
# docker run ... -v /path/to/Clerk2.5:/workspace/Clerk2.5 ...
# 则容器内路径为：
cd /workspace/Clerk2.5/pdf_converter_v2
```

**方式 B：在容器内克隆**

```bash
cd /workspace
git clone <your-repo-url> Clerk2.5
cd Clerk2.5/pdf_converter_v2
```

**方式 C：本地传递（无法使用 git 时）**

在**宿主机**（有项目代码的机器）上操作：

1. 打包项目（三选一）：

   **只传 pdf_converter_v2（推荐，会排除无关文件）：**
   ```bash
   cd /path/to/Clerk2.5/pdf_converter_v2
   bash scripts/package_for_transfer.sh
   ```
   会在上一级目录生成 `pdf_converter_v2.tar.gz`。

   **同时传 MinerU + pdf_converter_v2（需在容器内跑 MinerU 时）：**
   ```bash
   cd /path/to/Clerk2.5/pdf_converter_v2
   bash scripts/package_clerk_for_transfer.sh
   ```
   会在上一级目录生成 `Clerk2.5.tar.gz`（含 `mineru/` 与 `pdf_converter_v2/`）。

   **或手动打包：**
   ```bash
   cd /path/to
   tar czvf pdf_converter_v2.tar.gz Clerk2.5/pdf_converter_v2
   # 或整仓：tar czvf Clerk2.5.tar.gz Clerk2.5
   ```

2. 把压缩包拷进容器（`paddle-npu-dev` 换成你的容器名或 ID）：
   ```bash
   docker cp pdf_converter_v2.tar.gz paddle-npu-dev:/tmp/
   # 若打包的是 Clerk2.5.tar.gz：
   # docker cp Clerk2.5.tar.gz paddle-npu-dev:/tmp/
   ```

3. 进入容器并解压到目标目录：
   ```bash
   docker exec -it paddle-npu-dev bash
   mkdir -p /workspace
   cd /workspace
   tar xzvf /tmp/pdf_converter_v2.tar.gz
   rm /tmp/pdf_converter_v2.tar.gz
   cd pdf_converter_v2
   ```
   若解压的是 `Clerk2.5.tar.gz`，则：
   ```bash
   tar xzvf /tmp/Clerk2.5.tar.gz
   rm /tmp/Clerk2.5.tar.gz
   cd Clerk2.5/pdf_converter_v2   # 只跑 pdf_converter_v2 时
   # 或先装 MinerU 再跑 pdf_converter_v2，见下方「MinerU 安装与启动」
   ```

**若需同时部署 MinerU（提供 file_parse 接口）与 pdf_converter_v2**，建议打包整个 `Clerk2.5`（含 `mineru/` 和 `pdf_converter_v2/`），传入容器后解压到 `/workspace/Clerk2.5`，再按下方「MinerU 安装与启动」和「步骤 2」分别安装并启动。

---

## MinerU 安装与启动（可选，提供 file_parse 接口）

pdf_converter_v2 的 OCR 依赖外部 `file_parse` 接口；若希望在本容器内同时跑 MinerU（提供该接口），按以下步骤操作。**前提**：代码已传入容器且位于 `/workspace/Clerk2.5`（即存在 `/workspace/Clerk2.5/mineru/`）。

### 1. 传入 MinerU 代码

若尚未传入，在**宿主机**打包整个 Clerk2.5（含 mineru 与 pdf_converter_v2）并拷入容器：

```bash
# 宿主机
cd /path/to
tar czvf Clerk2.5.tar.gz Clerk2.5

docker cp Clerk2.5.tar.gz paddle-npu-dev:/tmp/
docker exec -it paddle-npu-dev bash -c 'mkdir -p /workspace && cd /workspace && tar xzvf /tmp/Clerk2.5.tar.gz && rm /tmp/Clerk2.5.tar.gz'
```

容器内路径：`/workspace/Clerk2.5/mineru`、`/workspace/Clerk2.5/pdf_converter_v2`。

### 2. 安装 MinerU 依赖

在容器内执行（已进入容器且位于 Clerk2.5 下）：

```bash
cd /workspace/Clerk2.5
pip3 install -r mineru/requirements-paddle-npu.txt
```

若后端（vlm/pipeline）报缺包，再按需安装；容器内已有 Paddle，可不重复安装。

### 3. 启动 MinerU API（file_parse）

在 **Clerk2.5 目录**下设置 `PYTHONPATH` 并启动（端口可改，此处用 5282）：

```bash
cd /workspace/Clerk2.5
export PYTHONPATH=/workspace/Clerk2.5
# 使用 NPU 推理（layout/mfd/mfr 等 PyTorch 模型跑在 NPU 上）；不设则可能回退到 CPU
export MINERU_DEVICE_MODE=npu
python3 -m uvicorn mineru.cli.fast_api:app --host 0.0.0.0 --port 5282
```

若启动或首次调用 `/file_parse` 时报错 **cannot allocate memory in static TLS block**（与 simsimd/libgomp 相关），请先设置 `LD_PRELOAD` 再启动，见本文档末尾「常见问题」中对应条目。

**使用 NPU 推理**：MinerU pipeline 的 layout、MFD、MFR 等 PyTorch 模型通过 `get_device()` 选择设备；设置 **`MINERU_DEVICE_MODE=npu`**（或 `npu:0`）可强制使用 NPU。脚本 `pdf_converter_v2/scripts/start_mineru_in_container.sh` 已默认设置 `MINERU_DEVICE_MODE=npu`，用该脚本启动即可走 NPU。

**PaddleOCR 使用 NPU**：若使用 **PaddleOCR**（`paddleocr ocr` / `doc_parser`，含 pdf_converter_v2 的 PaddleOCR 备用或工况附件转换），需设置 **`PADDLE_OCR_DEVICE=npu:0`**，否则 PaddleOCR 默认在 CPU 上推理，在 NPU 容器内易触发段错误（`phi::ConvKernel<float, phi::CPUContext>`）。本项目在调用 PaddleOCR 子进程时会读取该环境变量并自动加上 `--device npu:0`。

如需后台运行，可用 `nohup` 或 screen/tmux。**容器内无 systemd**：请使用 `pdf_converter_v2/scripts/start_mineru_in_container.sh`，例如在 Clerk2.5 下执行 `bash pdf_converter_v2/scripts/start_mineru_in_container.sh`（脚本内已含 `LD_PRELOAD` 与 `MINERU_DEVICE_MODE=npu`）。宿主机若以 systemd 为 init，可用 `scripts/mineru-api.service` 托管，并在其中添加 `Environment=MINERU_DEVICE_MODE=npu`。

验证：

```bash
curl http://127.0.0.1:5282/docs
```

### 4. 再启动 pdf_converter_v2 并指向本机 MinerU

NPU 下必须使用 pipeline 后端（容器内未安装 vLLM），通过环境变量 `BACKEND=pipeline` 传给 pdf_converter_v2：

```bash
export API_URL="http://127.0.0.1:5282"
export BACKEND=pipeline
cd /workspace/Clerk2.5/pdf_converter_v2
python3 api_server.py --host 0.0.0.0 --port 4214
```

这样 pdf_converter_v2 会调用本容器内的 MinerU 做 OCR，且请求 `/file_parse` 时使用 `backend=pipeline`。

### 5. 常见问题：huggingface.co 超时、模型无法下载

首次调用 `/file_parse` 时，MinerU 的 pipeline 会从 Hugging Face 拉取模型（`opendatalab/PDF-Extract-Kit-1.0`）。若出现 **Connection to huggingface.co timed out** 或 **LocalEntryNotFoundError**，说明当前环境访问不了 huggingface.co，可按下面三种方式之一处理。

#### 方式 A：使用 Hugging Face 国内镜像（优先尝试）

在**启动 MinerU 之前**设置环境变量，让 `huggingface_hub` 走国内镜像：

```bash
export HF_ENDPOINT=https://hf-mirror.com
cd /workspace/Clerk2.5
export PYTHONPATH=/workspace/Clerk2.5
python3 -m uvicorn mineru.cli.fast_api:app --host 0.0.0.0 --port 5282
```

若容器/服务器能访问 `hf-mirror.com`，模型会自动从镜像下载。

#### 方式 B：使用 ModelScope 源（国内可访问）

MinerU 支持从 ModelScope 拉取同一套模型，国内网络通常可访问：

1. 安装 ModelScope：`pip3 install modelscope`
2. 指定使用 ModelScope，再启动 MinerU：

```bash
export MINERU_MODEL_SOURCE=modelscope
cd /workspace/Clerk2.5
export PYTHONPATH=/workspace/Clerk2.5
python3 -m uvicorn mineru.cli.fast_api:app --host 0.0.0.0 --port 5282
```

pipeline 会使用 `OpenDataLab/PDF-Extract-Kit-1.0` 从 ModelScope 下载。

#### 方式 C：使用本地已下载的模型

在有外网的机器上先下载好模型，再把目录拷进容器，并配置 MinerU 使用本地路径：

1. **在有网络的机器上下载**（二选一）：
   - Hugging Face：`pip install huggingface_hub && python -c "from huggingface_hub import snapshot_download; snapshot_download('opendatalab/PDF-Extract-Kit-1.0', local_dir='./PDF-Extract-Kit-1.0')"`
   - ModelScope：`pip install modelscope && modelscope download --model OpenDataLab/PDF-Extract-Kit-1.0 --local_dir ./PDF-Extract-Kit-1.0`
2. 将整个 `PDF-Extract-Kit-1.0` 目录拷入容器（例如放到 `/work/models/PDF-Extract-Kit-1.0`）。
3. 在容器内创建配置文件 `~/mineru.json`（或 `$MINERU_TOOLS_CONFIG_JSON` 指定的路径），内容示例：

```json
{
  "models-dir": {
    "pipeline": "/work/models/PDF-Extract-Kit-1.0",
    "vlm": "/work/models/MinerU2.5-2509-1.2B"
  }
}
```

若只使用 pipeline 后端，只写 `pipeline` 即可；vlm 后端需要对应 vlm 模型路径。
4. 启动时指定使用本地模型：

```bash
export MINERU_MODEL_SOURCE=local
cd /workspace/Clerk2.5
export PYTHONPATH=/workspace/Clerk2.5
python3 -m uvicorn mineru.cli.fast_api:app --host 0.0.0.0 --port 5282
```

建议先试 **方式 A**，不行再用 **方式 B**，无法联网时用 **方式 C**。

---

## 步骤 2：安装项目依赖

容器内已有 Paddle 相关包，只需安装本项目所需的其他依赖（不重复安装 paddle）：

```bash
cd /workspace/Clerk2.5/pdf_converter_v2   # 或你的实际路径

# 使用项目提供的容器内依赖列表（不包含 paddle）
pip3 install -r requirements-paddle-npu.txt
```

若未使用 `requirements-paddle-npu.txt`，可手动安装核心依赖：

```bash
pip3 install aiohttp aiofiles Pillow pypdfium2 pdf2image pdfplumber \
  fastapi uvicorn pydantic typing-extensions loguru
```

如遇 `pypdfium2` 或 `pdf2image` 安装失败，可先跳过，部分功能（如纯图片 OCR）仍可用。

---

## 步骤 3：配置环境变量

按实际拓扑设置「PDF/图片转 Markdown」所调用的 OCR 服务地址，**并在 NPU 容器内指定使用 pipeline 后端**（否则会报错「Please install vllm to use the vllm-async-engine backend」）：

```bash
# 外部 file_parse 服务地址（必配）
# 例如：宿主机或其他容器上的 MinerU/file_parse 服务
export API_URL="http://192.168.2.3:5282"

# NPU 容器内必设：调用 MinerU /file_parse 时使用 pipeline 后端（容器内无 vLLM）
export BACKEND=pipeline

# 可选：本服务监听端口
export API_PORT=4214
```

若 `file_parse` 就在本容器内、且监听 5282：

```bash
export API_URL="http://127.0.0.1:5282"
export BACKEND=pipeline
```

---

## 步骤 4：启动 API 服务

在项目根目录下启动（确保当前目录为 `pdf_converter_v2`，以便模块和路径正确）。**NPU 容器内请先设置 `BACKEND=pipeline`**（见步骤 3）：

```bash
cd /workspace/Clerk2.5/pdf_converter_v2
# 若未在步骤 3 设置：export BACKEND=pipeline
python3 api_server.py --host 0.0.0.0 --port ${API_PORT:-4214}
```

如需对外访问，需在 `docker run` 时映射端口，例如：

```bash
# 宿主机
docker run ... -p 4214:4214 ...
```

---

## 步骤 5：验证

在容器内或宿主机上：

```bash
# 健康检查
curl http://localhost:4214/health

# 若端口已映射到宿主机
curl http://<宿主机IP>:4214/health
```

返回 `{"status":"healthy",...}` 即表示 API 部署成功。随后可用 `/convert` 上传 PDF/图片进行转换。

---

## 可选：使用启动脚本

项目内提供了容器内一键安装并启动的脚本（需先 `cd` 到 `pdf_converter_v2` 目录）：

```bash
cd /workspace/Clerk2.5/pdf_converter_v2
bash scripts/run_in_paddle_npu.sh
```

脚本会检查 Python、安装 `requirements-paddle-npu.txt`、读取 `API_URL` 和 `BACKEND`（NPU 下默认 `pipeline`）并启动 `api_server.py`。可根据需要修改脚本中的默认 `API_URL` 和端口。

---

## 若 MinerU 也需要用 LLM

MinerU 的 VLM 推理支持多种后端；是否能用 LLM/vLLM 取决于运行环境。

### 1. GPU 环境（进程内 vLLM）

在 MinerU 所在环境安装 vLLM 后，可直接用 vLLM 做 VLM 推理：

- 安装：`pip install vllm`
- 调用 MinerU 时使用：`backend=vlm-vllm-async-engine`（异步）或 `backend=vlm-vllm-engine`（同步）
- pdf_converter_v2：设置 `export BACKEND=vlm-vllm-async-engine` 后启动 API，或 curl/调用时传 `backend=vlm-vllm-async-engine`

MinerU 会在进程内加载 vLLM 和 VLM 模型，无需单独起 VLM 服务。

### 2. NPU 环境（当前容器）

当前 NPU 容器内**未安装** vLLM（vLLM 主要面向 GPU/CUDA），因此：

- **推荐**：继续使用 **pipeline** 后端（Paddle pipeline 做 VLM），设置 `BACKEND=pipeline`。无需 LLM 进程。
- **可选**：通过 **vlm-http-client** 连接**外部** VLM 服务：
  - MinerU 支持 `backend=vlm-http-client`，并需传入 `server_url`（例如 `http://host:30000`）。
  - 该 URL 需指向**与 MinerUClient 协议兼容**的 VLM 服务（如 MinerU 自带的 vLLM 服务默认端口 30000）。
  - 文档中 PaddleOCR 的 **genai_server**（端口 8118）是 PaddleOCR-VL 的接口，与 MinerU 的 vlm-http-client 协议**不一定兼容**；若要用 8118，需确认协议或存在适配层。
  - 使用方式：
    - 先在一台 GPU 机器上启动 MinerU 的 vLLM 服务（端口如 30000），或其它兼容 MinerUClient 的 VLM 服务。
    - 调用 MinerU 的 `file_parse` 时传：`backend=vlm-http-client`、`server_url=http://gpu-host:30000`。
    - pdf_converter_v2：设置 `export BACKEND=vlm-http-client`、`export SERVER_URL=http://gpu-host:30000` 后启动；API 会把 `SERVER_URL` 传给 MinerU。

### 3. 使用 vlm-http-client 时 pdf_converter_v2 的配置

| 环境变量     | 说明 |
|--------------|------|
| `BACKEND`    | 设为 `vlm-http-client` |
| `SERVER_URL` | VLM 服务地址，例如 `http://127.0.0.1:30000` 或 `http://gpu-server:30000` |

curl 测试示例（MinerU 在本机 5282，VLM 服务在 30000）：

```bash
curl -X POST "http://127.0.0.1:5282/file_parse" \
  -F "files=@./your.pdf" \
  -F "backend=vlm-http-client" \
  -F "server_url=http://127.0.0.1:30000" \
  -F "return_md=true" \
  -F "response_format_zip=true" \
  # ... 其他参数同前 ...
  -o result.zip
```

---

## 常见问题

1. **ImportError: Please install vllm to use the vllm-async-engine backend**  
   在 NPU 容器内未安装 vLLM，且 vLLM 面向 GPU。解决：调用 MinerU 时使用 **pipeline** 后端。  
   - 直接 curl 测试：`-F "backend=pipeline"`。  
   - 通过 pdf_converter_v2 调用：启动前设置 `export BACKEND=pipeline`，或使用 `scripts/run_in_paddle_npu.sh`（脚本已默认 `BACKEND=pipeline`）。

2. **simsimd / sklearn / libgomp: cannot allocate memory in static TLS block**  
   使用 pipeline 后端时，**simsimd**（经 albumentations → albucore）和 **scikit-learn**（经 transformers → sklearn）会各自加载自带的 `libgomp`，若加载时机过晚会触发 glibc 的静态 TLS 不足。解决：在**启动 MinerU（uvicorn）之前**同时预加载两处的 libgomp，再启动服务。  
   - **方式 A**：同时预加载 simsimd 与 scikit-learn 自带的 libgomp（路径以你容器内为准，用冒号分隔）：  
     ```bash
     export LD_PRELOAD="/usr/local/lib/python3.10/dist-packages/simsimd.libs/libgomp-a49a47f9.so.1.0.0:/usr/local/lib/python3.10/dist-packages/scikit_learn.libs/libgomp-d22c30c5.so.1.0.0"
     cd /workspace/Clerk2.5
     export PYTHONPATH=/workspace/Clerk2.5
     python3 -m uvicorn mineru.cli.fast_api:app --host 0.0.0.0 --port 5282
     ```  
     若路径不同，可在容器内分别执行 `ls .../simsimd.libs/` 与 `ls .../scikit_learn.libs/`，将两个 `libgomp*.so*` 的绝对路径用冒号拼成 `LD_PRELOAD`。  
   - **方式 B**：使用系统 libgomp（若已安装，如 `libgomp1`），有时可同时满足两处依赖：  
     ```bash
     export LD_PRELOAD=libgomp.so.1
     # 然后同上启动 uvicorn
     ```  
   设置好后无需每次改代码，只需在启动 MinerU 的 shell 里保留 `export LD_PRELOAD=...` 即可。

3. **ImportError: cannot import name 'VisionEncoderDecoderModel' from 'transformers'**  
   MinerU pipeline 依赖 `VisionEncoderDecoderModel`；较新版本的 transformers 可能不再在顶层包导出该类。本项目已在 MinerU 中改为从子模块直接导入（`transformers.models.vision_encoder_decoder.modeling_vision_encoder_decoder`）。若仍报错，可在容器内固定 transformers 版本，例如：`pip3 install "transformers>=4.40,<4.46"`（以 MinerU 兼容的版本为准）。

4. **AttributeError: module 'numpy' has no attribute 'complex'**  
   NumPy 1.24+ 与 2.x 移除了 `np.complex` 别名，而 pipeline 依赖链中的 **librosa**（经 transformers 引入）仍在使用。MinerU 已在启动时对 numpy 做兼容补丁（在 `mineru/cli/fast_api.py` 中），一般无需再改。若仍报错，可尝试将 numpy 固定到 1.20～<1.24：`pip3 install "numpy>=1.20,<1.24"`。

5. **ModuleNotFoundError: No module named 'pdf_converter_v2'**  
   确保在「项目父目录」的上一级执行，或已将 `pdf_converter_v2` 所在目录加入 `PYTHONPATH`。推荐始终在 `pdf_converter_v2` 目录下执行：  
   `python3 api_server.py ...`

6. **调用 /convert 时报错连接不上 file_parse**  
   检查容器内能否访问 `API_URL`：  
   `curl -I $API_URL`  
   若 `file_parse` 在宿主机，需使用宿主机对容器的 IP（如 172.17.0.1）或宿主机真实 IP，并保证端口已映射或防火墙放行。

7. **ModuleNotFoundError: No module named 'soxr'** / **Could not import module 'LayoutLMv3ForTokenClassification'**  
   pipeline 在排序块时会加载 LayoutLMv3（layoutreader），transformers 的依赖链会导入 `audio_utils` 并依赖 **soxr**。解决：安装 soxr，例如 `pip3 install soxr`；或使用更新后的 `mineru/requirements-paddle-npu.txt`（已含 soxr）重新安装 MinerU 依赖。

8. **已安装 Paddle，但希望用本机 PaddleOCR 做备用**  
   本项目当前主流程通过 `API_URL` 调用外部接口；容器内若已安装 PaddleOCR，可在同一容器内另行部署提供 `file_parse` 的服务，并将 `API_URL` 指到该服务即可。

9. **PaddleOCR 段错误：`paddleocr ocr` / `doc_parser` 崩溃、`phi::ConvKernel<float, phi::CPUContext>`**  
   表现：运行 **`paddleocr ocr`** 或 **`paddleocr doc_parser`**（或 pdf_converter_v2 触发 PaddleOCR 备用）时，在「Processing N items」或推理阶段崩溃，C++ 栈里有 `AnalysisPredictor::ZeroCopyRun`、`ConvKernel`/`Im2ColFunctor`、`CPUContext`。  
   说明：PaddleOCR 未指定设备时**默认在 CPU 上推理**，在部分环境（如 ARM）上 CPU Conv 会触发段错误。NPU 已加载（日志中有 CustomDevice: npu）但推理仍走 CPU。  
   **解决**：让 PaddleOCR 推理走 NPU：  
   - **命令行直接测试**：环境变量 `PADDLE_OCR_DEVICE` **不会被** `paddleocr` 命令行读取，必须在命令中**显式加上** `--device npu:0`：  
     ```bash
     paddleocr ocr -i /path/to/image.png --save_path /path/to/output --device npu:0
     ```  
   - **通过 pdf_converter_v2 调用**：本项目在调用 `paddleocr ocr` / `doc_parser` 时**未设置环境变量时默认使用 `npu:0`**，因此直接 `python3 api_server.py` 启动也会传 `--device npu:0`。若需用 GPU 或 CPU，可设置 `export PADDLE_OCR_DEVICE=gpu:0` 或 `PADDLE_OCR_DEVICE=cpu`；设为空则不添加 `--device`。  
   - **多卡**：若需指定其他卡，可设 `PADDLE_OCR_DEVICE=npu:1` 等。  
   本项目**默认**在未设置 `PADDLE_OCR_DEVICE` 时使用 `npu:0`，故 NPU 容器内直接启动 API 即可走 NPU；若显式设为空则不加 `--device`，PaddleOCR 用默认设备（易在 NPU 容器内段错误）。  
   **若已加 `--device npu:0` 仍崩溃且栈里仍是 CPUContext**：可能是 PaddleOCR/PaddleX 中部分模型或算子仍在 CPU 上执行（无 NPU 内核或回退到 CPU），属上游问题，可查阅 PaddleOCR 华为 NPU 文档或提 issue。

---

## 小结

| 步骤       | 说明 |
|------------|------|
| 1. 进入容器 | `docker exec -it paddle-npu-dev bash` |
| 2. 进入项目 | `cd /workspace/Clerk2.5/pdf_converter_v2`（或你的路径） |
| 3. 安装依赖 | `pip3 install -r requirements-paddle-npu.txt` |
| 4. 配置 API | `export API_URL=...`，NPU 下加 `export BACKEND=pipeline` |
| 5. MinerU 用 NPU | 启动 MinerU 前设 `export MINERU_DEVICE_MODE=npu`，或使用 `scripts/start_mineru_in_container.sh` |
| 6. PaddleOCR 用 NPU | 若使用 PaddleOCR 备用/工况附件：设 `export PADDLE_OCR_DEVICE=npu:0`，避免 CPU 段错误 |
| 7. 启动服务 | `python3 api_server.py --host 0.0.0.0 --port 4214` |
| 8. 验证     | `curl http://localhost:4214/health` |

按上述步骤即可在 Paddle NPU 容器内完成项目部署。
