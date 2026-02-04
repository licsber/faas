# AI 检测平台 - Nuclio FaaS

基于 Nuclio 的**通用 AI 检测 FaaS 平台**，支持快速部署各类 AI 模型服务（图像分类、目标检测、OCR、文本分析等）。

**✨ 设计原则**：一个平台，无限检测能力。添加新检测器就像创建一个新目录一样简单。

---

## ⚠️ 重要：跨平台部署限制

**nuctl 在 macOS ARM64 上运行时，会生成 ARM64 架构的镜像，即使 DOCKER_HOST 指向远程 Linux AMD64 服务器。**

**解决方案**：必须在目标架构的机器上运行 `make deploy`。

---

## 🚀 预构建镜像部署（推荐国内用户使用）

由于 HuggingFace 在国内访问困难，推荐使用 **GitHub Actions 自动构建**包含完整模型的镜像，推送到 Docker Hub 后在国内服务器直接拉取部署。

### 方案对比

| 部署方式 | 构建时间 | 依赖网络 | 适用场景 |
|----------|----------|----------|----------|
| 默认 `make deploy` | 5-10 分钟 | HuggingFace | 海外服务器 |
| **预构建镜像** | 1-2 分钟 | Docker Hub | **国内服务器** |

### 快速开始

#### 1. Fork 并配置 GitHub Actions

1. Fork 本仓库到你的 GitHub 账号
2. 添加 Docker Hub 密钥：
   - `Settings` → `Secrets and variables` → `Actions` → `New repository secret`
   - 添加 `DOCKER_USERNAME` 和 `DOCKER_PASSWORD`

#### 2. 自动构建

每次推送代码到 `main` 分支，或修改 `functions/nsfw-detector/**` 时，GitHub Actions 会自动：
- 构建多架构镜像（linux/amd64, linux/arm64）
- 预下载 HuggingFace 模型到镜像
- 推送到 Docker Hub

#### 3. 国内服务器部署

```bash
# 1. 修改 function-prebuilt.yaml 中的镜像地址
#    image: your-dockerhub-username/faas-nsfw-detector:latest

# 2. 使用预构建镜像部署
make deploy-prebuilt FUNCTION=nsfw-detector
```

### 本地构建镜像（可选）

```bash
# 本地构建并推送到私有仓库
make build-image FUNCTION=nsfw-detector REGISTRY=your-registry.com

# 然后推送
docker push your-registry.com/faas-nsfw-detector:latest
```

---

## 🌐 国内服务器部署须知

由于网络原因，以下镜像在国内服务器可能无法正常拉取，**建议提前通过镜像代理或其他方式准备好**：

| 镜像 | 用途 | 触发时机 |
|------|------|----------|
| `gcr.io/iguazio/uhttpc:0.0.3-amd64` | Nuclio 构建时内部使用 | 执行 `make deploy` 时自动拉取 |
| `quay.io/nuclio/dashboard:stable-amd64` | Nuclio Dashboard | 执行 `make dashboard` 时拉取 |
| `python:3.12-slim` | CPU 版本基础镜像 | 部署 CPU 函数时拉取 |
| `nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04` | GPU 版本基础镜像 | 部署 GPU 函数时拉取 |

### 手动拉取示例（需配置代理或使用镜像站）

```bash
# 方法 1：通过代理拉取后重新打标签
docker pull gcr.io/iguazio/uhttpc:0.0.3-amd64
docker pull quay.io/nuclio/dashboard:stable-amd64
docker pull python:3.12-slim
docker pull nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

# 方法 2：使用国内镜像站（如果可用）
# 例如阿里云、 DaoCloud 等提供的镜像代理服务
```

如果拉取失败，部署时会报错：`Error response from daemon: Get "https://gcr.io/v2/": net/http: request canceled while waiting for connection`

---

## 🚀 快速开始

### 方式一：在目标服务器上部署（推荐）

```bash
# SSH 到 Linux AMD64 服务器
ssh user@your-server

# 克隆项目
git clone <your-repo>
cd faas

# 启动 Dashboard
make dashboard

# 部署所有检测器
make deploy
```

### 方式二：本地 macOS 测试（仅适合单机开发）

```bash
# 1. 安装 colima 或 Docker Desktop（支持 x86_64 模拟）
brew install colima
colima start --arch x86_64

# 2. 部署
make dashboard
make deploy
```

---

## 📁 项目结构

```
faas/
├── functions/              # 检测器函数目录
│   └── nsfw-detector/     # 示例：NSFW 图像检测
│       ├── main.py
│       ├── function.yaml      # CPU 配置
│       └── function-gpu.yaml  # GPU 配置
├── templates/             # 新建检测器模板
│   └── python-detector/   # Python 检测器模板
├── Makefile               # 统一管理命令
└── README.md
```

---

## 🛠️ Makefile 命令

| 命令 | 说明 |
|------|------|
| `make help` | 查看所有命令 |
| `make dashboard` | 启动 Dashboard |
| `make deploy` | **部署所有检测器**（必须在目标架构机器上运行） |
| `make deploy CUDA=true` | **部署所有检测器**（GPU 版本） |
| `make deploy FUNCTION=xxx` | 部署指定检测器 |
| `make deploy FUNCTION=xxx CUDA=true` | 部署指定检测器（GPU 版本） |
| `make list` | 列出本地可用检测器 |
| `make status` | 查看所有检测器状态 |
| `make status FUNCTION=xxx` | 查看指定检测器状态 |
| `make clean` | 删除所有检测器 |

---

## 🏗️ 添加新检测器

### 快速添加

```bash
# 1. 创建新检测器目录
cp -r templates/python-detector functions/my-detector

# 2. 修改配置中的 name 和 description
vi functions/my-detector/function.yaml
vi functions/my-detector/function-gpu.yaml

# 3. 实现检测逻辑
vi functions/my-detector/main.py

# 4. 部署测试
make deploy FUNCTION=my-detector
```

### 检测器模板结构

```python
# main.py 示例结构
def init_context(context):
    """初始化模型（只执行一次）"""
    global model
    # 加载你的模型
    model = load_your_model()

def handler(context, event):
    """处理每个请求"""
    # 解析输入
    data = json.loads(event.body)
    
    # 执行检测
    result = model.detect(data['input'])
    
    # 返回结果
    return context.Response(
        body=json.dumps({"success": True, "data": result}),
        headers={"Content-Type": "application/json"},
        status_code=200
    )
```

详见 `templates/README.md`

---

## 📡 调用检测器

### 获取检测器端口

```bash
PORT=$(nuctl get function nsfw-detector -n nuclio -o json | \
  python3 -c "import sys,json;print(json.load(sys.stdin).get('status',{}).get('httpPort',''))")
```

### 调用示例（以 NSFW 检测器为例）

```bash
# 通过 URL 检测
curl -X POST http://localhost:$PORT \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/image.jpg"}'

# 通过 base64 检测
curl -X POST http://localhost:$PORT \
  -H "Content-Type: application/json" \
  -d '{"image": "base64_encoded_image_data"}'
```

响应格式（各检测器可能不同）：
```json
{
    "success": true,
    "data": {
        "is_nsfw": false,
        "predicted_class": "normal",
        "confidence": 0.9876,
        "scores": {"normal": 0.9876, "nsfw": 0.0124}
    }
}
```

---

## ⚙️ 配置说明

| 配置 | CPU | GPU |
|------|-----|-----|
| runtime | `python:3.12` | `python:3.12` |
| baseImage | `python:3.12-slim` | `nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04` |

已配置清华 PyPI 源加速下载。

---

## 🐛 故障排查

### `exec format error`

**原因**：在 macOS ARM64 上构建的镜像无法在 Linux AMD64 上运行。

**解决**：必须在目标架构的机器上运行 `make deploy`。

### 基础镜像无法拉取

**原因**：国内网络可能无法访问 `gcr.io` 等镜像仓库。

**解决**：提前在可访问的机器上准备镜像：

```bash
# 本地拉取并保存
docker pull gcr.io/iguazio/uhttpc:0.0.3-amd64
docker save gcr.io/iguazio/uhttpc:0.0.3-amd64 > uhttpc.tar

# 传输到服务器并加载
rsync -P uhttpc.tar user@server:~
ssh user@server 'cat uhttpc.tar | docker load'
```

### 端口冲突

**解决**：已删除固定端口，Nuclio 自动分配。

### 构建慢

**解决**：已配置清华源，首次下载 PyTorch 较慢。

---

## 🔥 性能测试

项目提供了 `benchmark/` 性能测试工具，支持并发压力测试。

### 安装依赖（使用 uv）

```bash
# 进入 benchmark 目录
cd benchmark

# 使用 uv 安装依赖
uv sync
```

> 如果没有安装 uv，请参考 [uv 官方文档](https://docs.astral.sh/uv/getting-started/installation/) 安装。

### 快速测试

```bash
cd benchmark

# 基础测试（默认参数：10并发，100请求）
uv run python runner.py --server http://localhost:8080

# 指定并发数和请求数
uv run python runner.py --server http://localhost:8080 -c 20 -n 500

# 压测指定时长（60秒）
uv run python runner.py --server http://localhost:8080 -c 50 -d 60

# 使用本地图片测试
uv run python runner.py --server http://localhost:8080 --mode image --image-path ./test.jpg

# JSON 格式输出
uv run python runner.py --server http://localhost:8080 -o json
```

### 常用参数

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--server` | `-s` | **服务器地址（必填）** | - |
| `--concurrency` | `-c` | 并发数 | 10 |
| `--requests` | `-n` | 总请求数 | 100 |
| `--duration` | `-d` | 测试时长（秒），优先级高于 -n | - |
| `--mode` | `-m` | 测试模式: url/image/health | url |
| `--image-url` | - | 测试图片 URL | https://picsum.photos/400/300 |
| `--image-path` | - | 本地测试图片路径 | - |
| `--output` | `-o` | 输出格式: text/json | text |
| `--verbose` | `-v` | 显示详细进度 | - |

### 测试示例

```bash
# 1. 先获取函数端口
PORT=$(nuctl get function nsfw-detector -n nuclio -o json | \
  python3 -c "import sys,json;print(json.load(sys.stdin).get('status',{}).get('httpPort',''))")

# 2. 运行性能测试
uv run python runner.py --server http://localhost:$PORT -c 10 -n 100 -v

# 输出示例：
# ============================================================
# 测试结果
# ============================================================
# 总请求数:        100
# 成功请求:        100 (100.00%)
# 失败请求:        0
# 总耗时:          15.23 秒
# QPS:             6.57
# ============================================================
# 延迟统计 (毫秒)
# ============================================================
# 最小值:          120.45 ms
# 平均值:          1520.34 ms
# 中位数:          1480.56 ms
# P95:             2100.12 ms
# P99:             2450.78 ms
# 最大值:          2800.23 ms
# ============================================================
```

---

## 📝 内置检测器

| 检测器 | 功能 | 模型 |
|--------|------|------|
| `nsfw-detector` | 图像内容安全检测 | Falconsai/nsfw_image_detection |

欢迎贡献更多检测器！
