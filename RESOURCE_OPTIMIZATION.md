# CPU/内存 资源优化报告

## 测试结论

### 资源使用现状

| 指标 | 原始配置 | 实际使用 | 利用率 | 优化后 |
|------|---------|---------|--------|--------|
| **CPU** | 8核 | 8核 (100%) | ✅ 充分利用 | 8核 |
| **内存** | 10GB | 1.6-2.1GB | ❌ 20% 浪费 | **3GB** |

### 关键发现

1. **内存严重过剩**
   - 配置 10GB，实际仅用 1.6-2.1GB
   - 浪费约 **80%** 内存资源
   - 优化至 3GB 可节省 **70%** 内存

2. **CPU 是性能瓶颈**
   - 8核满载时达到最大 QPS (~13)
   - 减少 CPU 会降低 QPS 线性下降
   - 4核配置 QPS 约 11.5 (损失 12%)

3. **最佳 CPU/内存 比例**
   - **8核 : 4GB = 1 : 0.5** (推荐，留有余量)
   - 或 **4核 : 2GB = 1 : 0.5** (性价比更高)

---

## 推荐配置

### 方案 A: 性能优先 (推荐)
追求最高吞吐量和最低延迟

```yaml
resources:
  requests:
    cpu: "2"
    memory: "2Gi"
  limits:
    cpu: "8"      # 使用全部 CPU
    memory: "3Gi" # 保留 50% 余量

triggers:
  http:
    numWorkers: 8  # 匹配 CPU 核心数
```

**性能指标:**
- QPS: **~13** (本地图片 base64)
- 单请求延迟: **~327ms**
- 内存使用: **~2GB / 4GB (50%)**，有余量应对大图片

---

### 方案 B: 性价比优先
节省资源，性能损失较小

```yaml
resources:
  requests:
    cpu: "1"
    memory: "1Gi"
  limits:
    cpu: "4"      # 使用 50% CPU
    memory: "2Gi" # 足够使用

triggers:
  http:
    numWorkers: 4  # 匹配 CPU 核心数
```

**性能指标:**
- QPS: **~11.5** (损失 12%)
- 单请求延迟: **~350ms**
- 内存使用: **~1.7GB / 2GB (85%)**
- **资源节省: 50% CPU, 33% 内存**

---

### 方案 C: 极简配置
最低资源需求，适合开发测试

```yaml
resources:
  requests:
    cpu: "0.5"
    memory: "1Gi"
  limits:
    cpu: "2"
    memory: "2Gi"

triggers:
  http:
    numWorkers: 2
```

**性能指标:**
- QPS: **~6**
- 单请求延迟: **~330ms**
- **资源节省: 75% CPU, 80% 内存**

---

## 场景推荐

| 场景 | 推荐方案 | 配置 | 预估 QPS |
|------|---------|------|---------|
| **生产环境 (高并发)** | 方案 A | 8C3G | 13 |
| **生产环境 (平衡)** | 方案 B | 4C2G | 11.5 |
| **开发测试** | 方案 C | 2C2G | 6 |
| **边缘计算/低成本** | 方案 C | 2C2G | 6 |

---

## 部署命令

### 方案 A (性能优先)
```bash
# 已更新到 function.yaml，直接部署
make deploy FUNCTION=nsfw-detector
```

### 方案 B (性价比优先)
```bash
# 使用优化配置
cat > /tmp/function-b.yaml << 'EOF'
metadata:
  name: nsfw-detector
  namespace: nuclio
spec:
  runtime: python:3.12
  handler: main:handler
  resources:
    limits:
      cpu: "4"
      memory: "2Gi"
  # ... 其他配置相同
  triggers:
    http:
      numWorkers: 4
EOF

nuctl deploy nsfw-detector --file /tmp/function-b.yaml \
  --path functions/nsfw-detector --namespace nuclio
```

---

## 成本对比 (以云服务器为例)

假设价格:
- CPU: ¥100/核/月
- 内存: ¥30/GB/月

| 方案 | CPU | 内存 | 月成本 | 节省 |
|------|-----|------|--------|------|
| 原始 (8C10G) | 8核 | 10GB | ¥1,100 | - |
| 方案 A (8C3G) | 8核 | 3GB | **¥890** | **¥210 (19%)** |
| 方案 B (4C2G) | 4核 | 2GB | **¥460** | **¥640 (58%)** |
| 方案 C (2C2G) | 2核 | 2GB | **¥260** | **¥840 (76%)** |

---

## 监控建议

### 内存使用监控
```bash
# 查看实际内存使用
docker stats --no-stream nuclio-nuclio-nsfw-detector

# 预期输出:
# MEM USAGE / LIMIT    MEM%
# 1.8GiB / 3GiB        60%
```

### 性能监控
```bash
# 运行基准测试
cd benchmark
uv run python final_benchmark.py http://localhost:32768
```

### 告警阈值
| 指标 | 警告 | 严重 |
|------|------|------|
| 内存使用率 | > 85% | > 95% |
| CPU 使用率 | > 90% | > 95% |
| P95 延迟 | > 800ms | > 1200ms |

---

## 总结

1. **内存从 10GB 优化到 4GB，节省 60%**
2. **保持 8核 CPU 不变，性能不受影响**
3. **CPU/内存 最佳比例: 1 : 0.375**
4. **如需进一步节省，可降至 4C2G，仅损失 12% 性能**
