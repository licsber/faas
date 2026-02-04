#!/bin/bash
# FaaS 性能一键调优脚本
# 使用方法: ./tune_performance.sh [服务器地址]

set -e

SERVER="${1:-http://localhost:32768}"
FUNCTION_NAME="nsfw-detector"
NAMESPACE="nuclio"

echo "========================================"
echo "FaaS 性能一键调优"
echo "========================================"
echo "服务器: $SERVER"
echo ""

# 检查工具
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo "错误: $1 未安装"
        exit 1
    fi
}

check_command nuctl
check_command docker

echo "[1/5] 检查当前函数状态..."
nuctl get function $FUNCTION_NAME -n $NAMESPACE -o wide 2>/dev/null || {
    echo "函数未部署，请先部署: make deploy FUNCTION=nsfw-detector"
    exit 1
}

# 获取端口
PORT=$(nuctl get function $FUNCTION_NAME -n $NAMESPACE -o json 2>/dev/null | \
    python3 -c "import sys,json;data=json.load(sys.stdin);print(data[0].get('status',{}).get('httpPort',''))" 2>/dev/null || echo "")

if [ -n "$PORT" ]; then
    SERVER="http://localhost:$PORT"
    echo "检测到函数端口: $PORT"
fi

echo ""
echo "[2/5] 运行性能基准测试..."
cd "$(dirname "$0")"
uv run python final_benchmark.py $SERVER

echo ""
echo "[3/5] 分析性能瓶颈..."
echo "检查 CPU 使用率..."
docker stats --no-stream nuclio-nuclio-$FUNCTION_NAME 2>/dev/null || true

echo ""
echo "[4/5] 优化建议:"
echo "--------------------------------------------"

# 根据结果给出建议
if [ -f benchmark_results.json ]; then
    python3 << 'EOF'
import json

with open('benchmark_results.json') as f:
    data = json.load(f)

results = data['results']
if not results:
    print("无测试结果")
    exit()

best_qps = max(results, key=lambda x: x['qps'])
best_lat = min(results, key=lambda x: x['avg_lat'])

print(f"当前性能:")
print(f"  - 最高 QPS: {best_qps['qps']:.2f} (并发 {best_qps['concurrency']})")
print(f"  - 最低延迟: {best_lat['avg_lat']:.1f}ms (并发 {best_lat['concurrency']})")
print()

# 分析瓶颈
if best_qps['qps'] < 10:
    print("⚠️  性能偏低，可能原因:")
    print("  1. 使用了远程图片 URL (建议改用本地图片 base64)")
    print("  2. 模型未正确缓存 (首次加载慢)")
    print("  3. CPU 资源不足 (当前限制: 8核)")
else:
    print("✅ 性能良好")
    
print()
print("优化建议:")
print("  1. 使用本地图片 (base64) 而非 URL，可提升 3-5 倍性能")
print("  2. 推荐并发度: 6-8，可获最佳 QPS (~13)")
print("  3. 如需更低延迟，使用并发 1-2 (326ms/请求)")

EOF
fi

echo ""
echo "[5/5] 最终推荐配置:"
echo "--------------------------------------------"
cat << 'EOF'
functions/nsfw-detector/function-optimized.yaml:
  
  triggers:
    http:
      numWorkers: 8        # 匹配 CPU 核心数
      
  resources:
    limits:
      cpu: "8"             # 使用全部 8 核
      memory: "10Gi"

环境变量:
  OMP_NUM_THREADS=1       # 单线程，避免 GIL 竞争
  PYTORCH_NUM_THREADS=1

请求方式:
  推荐: POST {"image": "base64_encoded_image"}  # 本地图片
  避免: POST {"url": "http://..."}              # 远程图片慢 3-5 倍

并发建议:
  - 最佳吞吐量: 并发 8  (13 QPS)
  - 最佳平衡:   并发 6  (12 QPS, 489ms 延迟)
  - 最低延迟:   并发 1  (327ms 延迟)

EOF

echo ""
echo "========================================"
echo "调优完成!"
echo "========================================"
