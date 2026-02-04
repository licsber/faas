# AI 检测平台 - Nuclio FaaS

基于 Nuclio 的**通用 AI 检测 FaaS 平台**，支持快速部署各类 AI 模型服务。

## 快速开始

```bash
# 1. 部署检测器
make deploy FUNCTION=nsfw-detector

# 2. 获取端口并测试
PORT=$(nuctl get function nsfw-detector -n nuclio -o json | \
  python3 -c "import sys,json;print(json.load(sys.stdin)[0].get('status',{}).get('httpPort',''))")

curl -X POST http://localhost:$PORT \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/image.jpg"}'
```

---

## 构建并推送镜像

```bash
# 构建镜像
docker build -f Dockerfile.nsfw-detector -t licsber/nsfw-detector:latest .

# 推送到 Docker Hub
docker push licsber/nsfw-detector:latest
```

---

## 性能测试

```bash
cd benchmark

# 基础测试
uv run python runner.py -s http://localhost:$PORT

# 高并发测试
uv run python runner.py -s http://localhost:$PORT -c 20 -n 500

# 使用本地图片（推荐，避免下载延迟）
uv run python runner.py -s http://localhost:$PORT --mode image --image-path ./Kirito.jpg
```

### 性能指标

**测试环境**: Intel Xeon 8369B @ 2.70GHz (8核), 14GB 内存

| 并发 | QPS | 平均延迟 | 说明 |
|------|-----|---------|------|
| 1 | 3.0 | 327ms | 单请求延迟 |
| 4 | 11.5 | 344ms | 推荐平衡 |
| **8** | **13.0** | **607ms** | **最高吞吐** |

**资源优化配置** (CPU:内存 = 1:0.5):
```yaml
resources:
  limits:
    cpu: "8"      # 8核
    memory: "4Gi" # 4GB（实际使用1.6-2GB，留有余量应对大图片）

triggers:
  http:
    numWorkers: 8  # 与CPU核心数1:1
```

---

## Makefile 命令

| 命令 | 说明 |
|------|------|
| `make deploy` | 部署所有检测器 |
| `make deploy FUNCTION=xxx` | 部署指定检测器 |
| `make deploy CUDA=true` | GPU版本部署 |
| `make list` | 列出可用检测器 |
| `make status` | 查看状态 |
| `make clean` | 删除所有检测器 |

---

## 项目结构

```
faas/
├── functions/
│   └── nsfw-detector/
│       ├── main.py           # 检测逻辑
│       ├── function.yaml     # CPU配置
│       └── function-gpu.yaml # GPU配置
├── benchmark/                # 性能测试工具
│   ├── faas_benchmark/       # 测试库
│   ├── Kirito.jpg           # 测试图片
│   └── runner.py            # 测试入口
├── templates/               # 新建检测器模板
├── Dockerfile.nsfw-detector # Docker构建文件
├── Makefile                 # 部署命令
└── README.md                # 本文档
```

---

## 调用示例

```bash
# URL检测
curl -X POST http://localhost:$PORT \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/image.jpg"}'

# base64图片检测
curl -X POST http://localhost:$PORT \
  -H "Content-Type: application/json" \
  -d '{"image": "base64_encoded_data"}'
```

响应格式：
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

## ⚠️ 注意事项

**跨平台部署**: nuctl 构建的镜像与运行机器架构绑定，必须在目标架构机器上运行 `make deploy`。

**国内网络**: 部分基础镜像(`gcr.io`, `quay.io`)可能无法直接拉取，需提前准备。

**GitHub Actions 安全**: PR 时只构建不推送镜像，防止恶意代码替换生产镜像。

---

## 技术栈

- **FaaS平台**: Nuclio
- **运行时**: Python 3.12
- **深度学习**: PyTorch + Transformers
- **模型**: Falconsai/nsfw_image_detection
