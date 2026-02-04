# FaaS 性能优化指南

> 本文档记录 NSFW 检测器的性能优化过程和最佳实践

## 性能测试结果

### 硬件配置
- **CPU**: Intel Xeon Platinum 8369B @ 2.70GHz (8核)
- **内存**: 14GB
- **模型**: Falconsai/nsfw_image_detection (ViT 基础模型)

### 优化后性能

| 并发数 | QPS | 平均延迟 | P95 延迟 | 适用场景 |
|--------|-----|---------|---------|----------|
| 1 | 3.06 | 327ms | 331ms | 最低延迟 |
| 2 | 6.12 | 327ms | 335ms | 低延迟 |
| 4 | 11.52 | 344ms | 370ms | 平衡 |
| **6** | **12.19** | **489ms** | **604ms** | **推荐** |
| **8** | **13.13** | **607ms** | **639ms** | **最高吞吐** |
| 12 | 13.04 | 904ms | 1173ms | 高并发 |
| 16 | 13.09 | 1192ms | 1253ms | 极限并发 |

**关键发现**:
- 单请求推理耗时: **~327ms** (本地图片)
- 最高 QPS: **~13** (并发 8)
- 超过 8 并发后 QPS 不再增长（CPU 瓶颈）

### 图片加载方式对比

| 方式 | 延迟 | 说明 |
|------|------|------|
| 本地图片 (base64) | 327ms | ✅ 推荐 |
| 远程 URL | 1600ms+ | ❌ 慢 5 倍，主要耗时在网络下载 |

## 优化配置

### 1. function.yaml 优化

```yaml
# triggers 配置
triggers:
  http:
    kind: http
    numWorkers: 8                    # 匹配 CPU 核心数
    workerAvailabilityTimeoutMilliseconds: 30000
    attributes:
      maxRequestBodySize: 33554432

# 资源配置
resources:
  requests:
    cpu: "2"
    memory: "4Gi"
  limits:
    cpu: "8"                         # 使用全部 CPU
    memory: "10Gi"

# 环境变量
env:
  # 单线程配置 - 多 worker 比多线程更有效
  - name: OMP_NUM_THREADS
    value: "1"
  - name: MKL_NUM_THREADS
    value: "1"
  - name: OPENBLAS_NUM_THREADS
    value: "1"
  - name: PYTORCH_NUM_THREADS
    value: "1"
```

### 2. 关键优化点

| 优化项 | 配置 | 效果 |
|--------|------|------|
| Worker 数量 | 8 (匹配 CPU 核数) | 充分利用多核 |
| 线程限制 | 全部设为 1 | 避免 GIL 竞争 |
| 日志级别 | warning | 减少日志开销 |
| 图片传输 | base64 本地图片 | 避免网络延迟 |
| 资源限制 | CPU 8核, 内存 10GB | 充足资源 |

### 3. 不推荐的优化

| 优化 | 结果 | 原因 |
|------|------|------|
| 增加线程数 (OMP_NUM_THREADS > 1) | 性能下降 | Python GIL 限制 |
| 批处理 (batch size > 1) | 性能下降 | 同步开销 > 批处理收益 |
| 更多 workers (> 8) | 无提升 | CPU 已满载 |

## 使用建议

### 客户端调用

**推荐方式 - 本地图片 base64:**
```python
import base64
import requests

with open("image.jpg", "rb") as f:
    image_b64 = base64.b64encode(f.read()).decode()

response = requests.post(
    "http://localhost:32768",
    json={"image": image_b64},
    headers={"Content-Type": "application/json"}
)
```

**避免方式 - 远程 URL:**
```python
# 慢 3-5 倍！主要耗时在网络下载
requests.post(
    "http://localhost:32768",
    json={"url": "https://example.com/image.jpg"}
)
```

### 并发建议

| 场景 | 推荐并发 | 预期 QPS | 延迟 |
|------|---------|---------|------|
| 最低延迟优先 | 1-2 | 3-6 | 327ms |
| 平衡性能 | 4-6 | 11-12 | 344-489ms |
| 最大吞吐 | 8 | 13 | 607ms |
| 高并发容忍 | >8 | 13 (上限) | >900ms |

## 性能监控

### 检查 CPU 使用率
```bash
docker stats nuclio-nuclio-nsfw-detector
```

### 运行基准测试
```bash
cd benchmark
uv run python final_benchmark.py http://localhost:32768
```

### 一键调优
```bash
cd benchmark
./tune_performance.sh
```

## 进一步优化方向

如果当前性能仍不满足需求，可考虑：

1. **模型量化/蒸馏**
   - 使用更小的模型 (如 MobileNet 版本)
   - 量化到 INT8

2. **ONNX Runtime**
   - 转换模型到 ONNX 格式
   - 使用 ONNX Runtime 推理

3. **GPU 加速**
   - 使用 function-gpu.yaml 部署
   - 单 GPU 可处理 50+ QPS

4. **多实例部署**
   - 部署多个函数实例
   - 使用负载均衡分发请求

## 总结

当前配置已达到 CPU 性能上限 (~13 QPS)，主要瓶颈在模型推理本身。
如需更高性能，需要:
1. 使用更轻量级模型
2. 使用 GPU 加速
3. 水平扩展多实例
