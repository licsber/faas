#!/usr/bin/env python3
"""
测试不同 CPU/内存 比例下的性能
找到资源使用与性能的最佳平衡点
"""

import asyncio
import aiohttp
import time
import statistics
import base64
import json
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional

IMAGE_PATH = Path(__file__).parent / "Kirito.jpg"


@dataclass
class ResourceConfig:
    name: str
    cpu_limit: int
    memory: str      # 如 "2Gi", "3Gi"
    workers: int


@dataclass
class TestResult:
    config: ResourceConfig
    qps: float
    avg_latency: float
    p95_latency: float
    success_rate: float
    memory_usage: Optional[str] = None
    cpu_usage: Optional[str] = None


def load_image_base64() -> str:
    with open(IMAGE_PATH, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')


def generate_config(cpu: int, memory: str, workers: int) -> str:
    """生成 function.yaml 配置"""
    return f"""# NSFW 检测器 - 资源优化测试
metadata:
  name: nsfw-detector
  namespace: nuclio
  labels:
    app: nsfw-detector
    version: "test"

spec:
  runtime: python:3.12
  handler: main:handler
  description: "NSFW 检测 - 资源测试"
  
  resources:
    requests:
      cpu: "1"
      memory: "1Gi"
    limits:
      cpu: "{cpu}"
      memory: "{memory}"
  
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
    path: /root/faas/functions/nsfw-detector
    baseImage: python:3.12-slim
    commands:
      - apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 wget git && rm -rf /var/lib/apt/lists/*
      - pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
      - pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn
      - pip install --no-cache-dir torch torchvision transformers Pillow numpy requests
      - mkdir -p /opt/huggingface/models
      - export HF_HOME=/opt/huggingface && export TRANSFORMERS_CACHE=/opt/huggingface/models
      - python3 -c "from transformers import AutoModelForImageClassification, AutoImageProcessor; m='Falconsai/nsfw_image_detection'; AutoImageProcessor.from_pretrained(m, cache_dir='/opt/huggingface/models'); AutoModelForImageClassification.from_pretrained(m, cache_dir='/opt/huggingface/models'); print('Model downloaded')"
  
  triggers:
    http:
      kind: http
      numWorkers: {workers}
      workerAvailabilityTimeoutMilliseconds: 30000
      attributes:
        maxRequestBodySize: 33554432
  
  minReplicas: 1
  maxReplicas: 1
  
  loggerSinks:
    - level: warning
      sink: ""
"""


def deploy_config(config: ResourceConfig) -> bool:
    """部署特定配置"""
    print(f"\n部署: {config.name} (CPU={config.cpu_limit}, MEM={config.memory}, Workers={config.workers})")
    
    yaml_content = generate_config(config.cpu_limit, config.memory, config.workers)
    
    with open("/tmp/function-test.yaml", "w") as f:
        f.write(yaml_content)
    
    # 删除旧函数
    subprocess.run(
        ["nuctl", "delete", "function", "nsfw-detector", "-n", "nuclio"],
        capture_output=True, timeout=60
    )
    time.sleep(2)
    
    # 部署
    result = subprocess.run(
        ["nuctl", "deploy", "nsfw-detector",
         "--file", "/tmp/function-test.yaml",
         "--path", "/root/faas/functions/nsfw-detector",
         "--namespace", "nuclio",
         "--project-name", "default",
         "--no-pull"],
        capture_output=True, text=True, timeout=300
    )
    
    if result.returncode != 0:
        print(f"部署失败: {result.stderr[-500:]}")
        return False
    
    print("部署成功，等待预热...")
    time.sleep(15)
    return True


def get_server_url() -> str:
    """获取服务地址"""
    try:
        result = subprocess.run(
            ["nuctl", "get", "function", "nsfw-detector", "-n", "nuclio", "-o", "json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if isinstance(data, list) and len(data) > 0:
                data = data[0]
            port = data.get('status', {}).get('httpPort', '')
            if port:
                return f"http://localhost:{port}"
    except:
        pass
    return "http://localhost:32768"


def get_container_stats() -> tuple:
    """获取容器资源使用情况"""
    try:
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "nuclio-nuclio-nsfw-detector"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if len(lines) >= 2:
                parts = lines[1].split()
                # 格式: CONTAINER CPU% MEM_USAGE/LIMIT MEM% ...
                if len(parts) >= 4:
                    cpu = parts[1]
                    mem = parts[2] + ' ' + parts[3]
                    return cpu, mem
    except:
        pass
    return None, None


async def run_benchmark(server: str, concurrency: int = 8, duration: int = 15) -> Optional[dict]:
    """运行基准测试"""
    image_b64 = load_image_base64()
    
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=100),
        timeout=aiohttp.ClientTimeout(total=30)
    ) as session:
        
        # 预热
        for _ in range(3):
            async with session.post(server, json={"image": image_b64},
                                   headers={"Content-Type": "application/json"}) as resp:
                await resp.read()
        
        # 测试
        start = time.time()
        latencies = []
        errors = 0
        
        semaphore = asyncio.Semaphore(concurrency)
        
        async def worker():
            nonlocal errors
            while time.time() - start < duration:
                try:
                    async with session.post(server, json={"image": image_b64},
                                           headers={"Content-Type": "application/json"}) as resp:
                        if resp.status == 200:
                            latencies.append(1)  # 只计数
                        else:
                            errors += 1
                except:
                    errors += 1
        
        workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
        await asyncio.gather(*workers)
        
        total_time = time.time() - start
        total = len(latencies) + errors
        
        # 获取资源使用
        cpu_usage, mem_usage = get_container_stats()
        
        return {
            'qps': len(latencies) / total_time,
            'success': len(latencies),
            'errors': errors,
            'success_rate': len(latencies) / total if total > 0 else 0,
            'cpu_usage': cpu_usage,
            'mem_usage': mem_usage
        }


def calculate_efficiency(result: TestResult) -> float:
    """计算资源效率得分 = QPS / (CPU * Memory_GB)"""
    mem_gb = float(result.config.memory.replace('Gi', '').replace('G', ''))
    cpu = result.config.cpu_limit
    # 效率 = QPS / (CPU * MEM) - 越高越好
    return result.qps / (cpu * mem_gb) if cpu > 0 and mem_gb > 0 else 0


async def main():
    print("="*80)
    print("CPU/内存 比例优化测试")
    print("="*80)
    
    # 测试不同配置
    # 原则: workers 应该 <= cpu_limit
    configs = [
        # CPU=4 配置
        ResourceConfig("4C-2G-4W", 4, "2Gi", 4),
        ResourceConfig("4C-3G-4W", 4, "3Gi", 4),
        ResourceConfig("4C-4G-4W", 4, "4Gi", 4),
        
        # CPU=6 配置
        ResourceConfig("6C-2G-6W", 6, "2Gi", 6),
        ResourceConfig("6C-3G-6W", 6, "3Gi", 6),
        ResourceConfig("6C-4G-6W", 6, "4Gi", 6),
        
        # CPU=8 配置
        ResourceConfig("8C-2G-8W", 8, "2Gi", 8),
        ResourceConfig("8C-3G-8W", 8, "3Gi", 8),
        ResourceConfig("8C-4G-8W", 8, "4Gi", 8),
        
        # 当前配置（对比）
        ResourceConfig("8C-10G-8W", 8, "10Gi", 8),
    ]
    
    results = []
    
    for config in configs:
        if not deploy_config(config):
            continue
        
        server = get_server_url()
        print(f"测试 {config.name}...", end=" ", flush=True)
        
        data = await run_benchmark(server, concurrency=8, duration=15)
        if data:
            result = TestResult(
                config=config,
                qps=data['qps'],
                avg_latency=0,  # 简化测试
                p95_latency=0,
                success_rate=data['success_rate'],
                memory_usage=data.get('mem_usage'),
                cpu_usage=data.get('cpu_usage')
            )
            results.append(result)
            eff = calculate_efficiency(result)
            print(f"QPS: {result.qps:.2f}, 效率: {eff:.3f}, CPU: {result.cpu_usage}, MEM: {result.memory_usage}")
        else:
            print("失败")
        
        time.sleep(2)
    
    # 打印结果汇总
    print("\n" + "="*100)
    print("测试结果汇总 (按效率排序)")
    print("="*100)
    print(f"{'配置':<15} {'CPU':<4} {'内存':<6} {'Workers':<8} {'QPS':<8} {'成功率':<8} {'内存使用':<15} {'效率':<8}")
    print("-"*100)
    
    sorted_results = sorted(results, key=calculate_efficiency, reverse=True)
    
    for r in sorted_results:
        eff = calculate_efficiency(r)
        print(f"{r.config.name:<15} {r.config.cpu_limit:<4} {r.config.memory:<6} "
              f"{r.config.workers:<8} {r.qps:<8.2f} {r.success_rate*100:<8.1f} "
              f"{r.memory_usage or 'N/A':<15} {eff:<8.3f}")
    
    # 推荐配置
    if sorted_results:
        best_eff = sorted_results[0]
        best_qps = max(results, key=lambda x: x.qps)
        
        print("\n" + "="*100)
        print("推荐配置:")
        print("="*100)
        print(f"  🏆 最高效率: {best_eff.config.name}")
        print(f"     CPU={best_eff.config.cpu_limit}, MEM={best_eff.config.memory}, Workers={best_eff.config.workers}")
        print(f"     QPS={best_eff.qps:.2f}, 效率={calculate_efficiency(best_eff):.3f}")
        print()
        print(f"  ⚡ 最高性能: {best_qps.config.name}")
        print(f"     CPU={best_qps.config.cpu_limit}, MEM={best_qps.config.memory}, Workers={best_qps.config.workers}")
        print(f"     QPS={best_qps.qps:.2f}")
        
        # 性价比分析
        print("\n  💰 性价比分析 (每GB内存的QPS):")
        for r in sorted_results[:5]:
            mem_gb = float(r.config.memory.replace('Gi', ''))
            qps_per_gb = r.qps / mem_gb
            print(f"     {r.config.name}: {qps_per_gb:.2f} QPS/GB")
    
    print("="*100)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n测试被中断")
