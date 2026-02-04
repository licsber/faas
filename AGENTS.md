# AGENTS.md - AI Agent Guide

> 本文件为 AI 编程助手提供项目背景信息。人类开发者请优先阅读 README.md。

---

## 项目概述

本项目是一个基于 **Nuclio** 的**通用 AI 检测 FaaS 平台**，用于部署各类 AI 模型服务（图像分类、目标检测、OCR、文本分析等）。

**设计理念**：
- 一个平台，无限检测能力
- 每个检测功能是一个独立的 FaaS 函数
- 统一的管理接口（Makefile）
- 开箱即用的示例（NSFW 检测）

### 内置示例

- **nsfw-detector**：图像内容安全检测（不适宜内容识别）

### 技术栈

| 组件 | 版本/类型 |
|------|----------|
| FaaS 平台 | Nuclio |
| 运行时 | Python 3.12 |
| 深度学习框架 | PyTorch + Transformers（可选） |
| 部署工具 | nuctl CLI + Makefile |

---

## 项目结构

```
faas/
├── functions/                 # FaaS 函数目录（各种检测器）
│   ├── nsfw-detector/        # 示例：NSFW 检测器
│   │   ├── main.py           # 主处理逻辑（Nuclio 函数入口）
│   │   ├── function.yaml     # CPU 部署配置
│   │   └── function-gpu.yaml # GPU 部署配置（可选）
│   └── your-detector/        # 添加你的检测器...
├── templates/                # 函数模板目录
│   ├── python-detector/      # Python 检测器模板
│   │   ├── main.py
│   │   ├── function.yaml
│   │   └── function-gpu.yaml
│   └── README.md             # 如何添加新检测器
├── Makefile                  # 统一的部署管理接口
├── README.md                 # 人类开发者文档
└── AGENTS.md                 # 本文件
```

### 关键文件说明

- `functions/*/main.py`：Nuclio 函数入口，必须包含 `init_context()` 和 `handler()` 函数
- `functions/*/function.yaml`：CPU 部署配置（Nuclio Function 配置）
- `functions/*/function-gpu.yaml`：GPU 部署配置（可选）
- `Makefile`：统一的部署管理接口，对所有函数通用

---

## 开发规范

### 函数开发规范

1. **入口函数**：每个检测器必须包含两个标准入口：
   ```python
   def init_context(context):
       """容器启动时调用一次，用于初始化模型等"""
       pass
   
   def handler(context, event):
       """每个请求调用，处理业务逻辑"""
       return context.Response(body=..., headers=..., status_code=...)
   ```

2. **全局变量**：模型等重量级资源应在 `init_context()` 中加载，存入全局变量实现复用

3. **依赖管理**：Python 依赖在 `function.yaml` 的 `build.commands` 中通过 `pip install` 安装，**不使用** requirements.txt

4. **镜像源**：已配置清华 PyPI 镜像加速下载
   ```yaml
   - pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
   ```

5. **返回格式**：建议统一返回 JSON 格式，包含 `success` 和 `data` 字段
   ```json
   {
       "success": true,
       "data": { ... }
   }
   ```

### 配置规范

#### CPU 配置 (`function.yaml`)
- 基础镜像：`python:3.12-slim`
- 资源：CPU 0.5-2 核，内存 1-4 Gi
- 工作进程：4 个

#### GPU 配置 (`function-gpu.yaml`)
- 基础镜像：`nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04`
- 资源：CPU 1-4 核，内存 4-8 Gi，1 个 GPU
- 工作进程：2 个
- 需配置 `nodeSelector` 和 `tolerations` 以调度到 GPU 节点

---

## 构建与部署

### 前置要求

- Docker 运行中
- nuctl CLI 已安装（`brew install nuctl` 或从 GitHub 下载）
- **重要**：必须在目标架构机器上运行部署命令（nuctl 会生成本机架构的镜像）

### 常用命令

```bash
# 查看所有可用命令
make help

# 启动 Nuclio Dashboard（本地调试使用）
make dashboard

# 部署所有函数（CPU 版本）
make deploy

# 部署所有函数（GPU 版本）
make deploy CUDA=true

# 部署指定函数
make deploy FUNCTION=nsfw-detector

# 查看函数状态
make status
make status FUNCTION=nsfw-detector

# 列出本地可用函数
make list

# 删除所有函数
make clean

# DRYRUN 模式（只打印命令，不执行）
make deploy DRYRUN=true
```

### 部署限制

⚠️ **跨平台部署限制**：nuctl 在 macOS ARM64 上运行时，会生成 ARM64 架构的镜像，即使 DOCKER_HOST 指向远程 Linux AMD64 服务器。

**解决方案**：
1. 直接在目标 Linux AMD64 服务器上运行 `make deploy`
2. 或在本地使用 x86_64 模拟（如 Colima）：`colima start --arch x86_64`

---

## 添加新检测器

平台设计为易于扩展，添加新检测器的步骤：

```bash
# 1. 使用模板创建新检测器
make new-function NAME=face-detector

# 或手动创建
mkdir functions/face-detector
cp templates/python-detector/* functions/face-detector/

# 2. 修改配置
# - function.yaml: 修改 metadata.name 和 spec.description
# - function-gpu.yaml: 同上

# 3. 实现检测逻辑（main.py）
# - 在 init_context() 中加载模型
# - 在 handler() 中处理请求

# 4. 部署测试
make deploy FUNCTION=face-detector
```

详见 `templates/README.md`

---

## API 接口示例

以 NSFW 检测器为例，部署后通过 HTTP 触发器暴露服务：

```bash
# 获取函数端口
PORT=$(nuctl get function nsfw-detector -n nuclio -o json | \
  python3 -c "import sys,json;print(json.load(sys.stdin).get('status',{}).get('httpPort',''))")

# 调用
curl -X POST http://localhost:$PORT \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/image.jpg"}'
```

每个检测器可定义自己的请求/响应格式。

---

## 故障排查

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| `exec format error` | 架构不匹配（如 ARM64 镜像在 AMD64 运行） | 在目标架构机器上运行 `make deploy` |
| 构建慢 | PyTorch 等大型依赖下载慢 | 已配置清华源，首次构建仍较慢，请耐心等待 |
| 端口冲突 | 手动指定端口可能冲突 | 配置中已移除固定端口，使用 Nuclio 自动分配 |
| GPU 不可用 | CUDA 版本不匹配或 GPU 节点未就绪 | 检查 `nvidia/cuda` 镜像版本与宿主机的兼容性 |
| `gcr.io` 拉取失败 | 国内网络无法访问 GCR | 提前手动拉取 `gcr.io/iguazio/uhttpc:0.0.3-amd64` 镜像 |

### 国内服务器注意事项

国内服务器可能无法正常拉取以下镜像，建议提前准备：

| 镜像 | 用途 |
|------|------|
| `gcr.io/iguazio/uhttpc:0.0.3-amd64` | Nuclio 构建时内部使用 |
| `quay.io/nuclio/dashboard:stable-amd64` | Nuclio Dashboard |
| `python:3.12-slim` | CPU 版本基础镜像 |
| `nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04` | GPU 版本基础镜像 |

详细说明参见 README.md「国内服务器部署须知」章节。

---

## 扩展阅读

- [Nuclio 官方文档](https://nuclio.io/docs/latest/)
- [nuctl CLI 参考](https://nuclio.io/docs/latest/reference/nuctl/nuctl/)
- [Transformers 文档](https://huggingface.co/docs/transformers/)

---

## 目录导航

- 新检测器模板：`templates/python-detector/`
- 示例实现：`functions/nsfw-detector/`
