#!/bin/bash
# 根据资源限制部署函数
# 用法: ./deploy_with_resources.sh [a|b|c|custom]
#   a - 方案A: 8核4GB (性能优先, 默认)
#   b - 方案B: 4核2GB (性价比优先)
#   c - 方案C: 2核2GB (极简配置)
#   custom - 自定义 (交互式)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SCHEME="${1:-a}"

echo "========================================"
echo "FaaS 资源优化部署"
echo "========================================"
echo ""

cd "$PROJECT_ROOT"

# 检查 nuctl
if ! command -v nuctl &> /dev/null; then
    echo "错误: nuctl 未安装"
    exit 1
fi

# 选择方案
case "$SCHEME" in
    a|A|performance)
        CPU_LIMIT=8
        MEM_LIMIT="4Gi"
        WORKERS=8
        SCHEME_NAME="方案 A (性能优先 - 8核4GB)"
        ;;
    b|B|balanced)
        CPU_LIMIT=4
        MEM_LIMIT="2Gi"
        WORKERS=4
        SCHEME_NAME="方案 B (性价比优先)"
        ;;
    c|C|minimal)
        CPU_LIMIT=2
        MEM_LIMIT="2Gi"
        WORKERS=2
        SCHEME_NAME="方案 C (极简配置)"
        ;;
    custom)
        echo "自定义配置:"
        read -p "CPU 限制 (核): " CPU_LIMIT
        read -p "内存限制 (如 3Gi): " MEM_LIMIT
        read -p "Worker 数量: " WORKERS
        SCHEME_NAME="自定义配置"
        ;;
    *)
        echo "用法: $0 [a|b|c|custom]"
        echo ""
        echo "可选方案:"
        echo "  a - 8核4GB (性能优先, QPS~13, 留有余量)"
        echo "  b - 4核2GB (性价比优先, QPS~11.5)"
        echo "  c - 2核2GB (极简配置, QPS~6)"
        echo "  custom - 自定义配置"
        exit 1
        ;;
esac

echo "部署: $SCHEME_NAME"
echo "  CPU: ${CPU_LIMIT}核"
echo "  内存: $MEM_LIMIT"
echo "  Workers: $WORKERS"
echo ""

# 生成配置
cat > /tmp/function-resource.yaml << EOF
# NSFW 检测器 - $SCHEME_NAME
metadata:
  name: nsfw-detector
  namespace: nuclio
  labels:
    app: nsfw-detector
    version: "optimized"

spec:
  runtime: python:3.12
  handler: main:handler
  description: "NSFW 检测 - $SCHEME_NAME"
  
  resources:
    requests:
      cpu: "1"
      memory: "1Gi"
    limits:
      cpu: "${CPU_LIMIT}"
      memory: "${MEM_LIMIT}"
  
  env:
    - name: NSFW_MODEL_NAME
      value: "Falconsai/nsfw_image_detection"
    - name: DEVICE
      value: "cpu"
    - name: PYTHONUNBUFFERED
      value: "1"
    - name: OMP_NUM_THREADS
      value: "1"
    - name: MKL_NUM_THREADS
      value: "1"
    - name: OPENBLAS_NUM_THREADS
      value: "1"
    - name: PYTORCH_NUM_THREADS
      value: "1"
  
  build:
    path: ${PROJECT_ROOT}/functions/nsfw-detector
    baseImage: python:3.12-slim
    commands:
      - apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 wget git && rm -rf /var/lib/apt/lists/*
      - pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
      - pip install --no-cache-dir torch torchvision transformers Pillow numpy requests
      - mkdir -p /opt/huggingface/models
      - export HF_HOME=/opt/huggingface && export TRANSFORMERS_CACHE=/opt/huggingface/models
      - python3 -c "from transformers import AutoModelForImageClassification, AutoImageProcessor; m='Falconsai/nsfw_image_detection'; AutoImageProcessor.from_pretrained(m, cache_dir='/opt/huggingface/models'); AutoModelForImageClassification.from_pretrained(m, cache_dir='/opt/huggingface/models'); print('Model downloaded')"
  
  triggers:
    http:
      kind: http
      numWorkers: ${WORKERS}
      workerAvailabilityTimeoutMilliseconds: 30000
      attributes:
        maxRequestBodySize: 33554432
  
  minReplicas: 1
  maxReplicas: 1
  
  loggerSinks:
    - level: warning
      sink: ""
EOF

echo "[1/3] 删除旧函数..."
nuctl delete function nsfw-detector -n nuclio 2>/dev/null || true
sleep 2

echo "[2/3] 部署新配置..."
nuctl deploy nsfw-detector \
    --file /tmp/function-resource.yaml \
    --path "${PROJECT_ROOT}/functions/nsfw-detector" \
    --namespace nuclio \
    --project-name default \
    --no-pull

echo ""
echo "[3/3] 等待服务就绪..."
sleep 10

# 获取端口
PORT=$(nuctl get function nsfw-detector -n nuclio -o json 2>/dev/null | \
    python3 -c "import sys,json;data=json.load(sys.stdin);print(data[0].get('status',{}).get('httpPort',''))" 2>/dev/null || echo "")

if [ -n "$PORT" ]; then
    echo ""
    echo "========================================"
    echo "部署完成!"
    echo "========================================"
    echo "服务器地址: http://localhost:$PORT"
    echo ""
    echo "快速测试:"
    echo "  cd benchmark && uv run python -m faas_benchmark -s http://localhost:$PORT -c $WORKERS -d 10 --mode image --image-path ./Kirito.jpg"
    echo ""
    
    # 询问是否立即测试
    read -p "是否立即运行性能测试? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cd "$SCRIPT_DIR"
        uv run python -m faas_benchmark \
            --server "http://localhost:$PORT" \
            --concurrency "$WORKERS" \
            --duration 15 \
            --mode image \
            --image-path ./Kirito.jpg
    fi
else
    echo "获取端口失败，请手动检查"
    nuctl get function nsfw-detector -n nuclio
fi
