#!/usr/bin/env python3
"""
快速性能测试和调优脚本
"""

import subprocess
import json
import time
import sys
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class TestConfig:
    name: str
    workers: int
    cpu_limit: int
    memory: str
    concurrency: int
    duration: int = 30

@dataclass
class TestResult:
    config: TestConfig
    qps: float
    avg_latency: float
    p95_latency: float
    p99_latency: float
    success_rate: float
    
    def __str__(self):
        return (f"{self.config.name:20s} | QPS: {self.qps:6.2f} | "
                f"Avg: {self.avg_latency:8.2f}ms | P95: {self.p95_latency:8.2f}ms | "
                f"P99: {self.p99_latency:8.2f}ms")


def get_function_port() -> Optional[str]:
    """获取函数端口"""
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
            return str(port) if port else None
    except Exception as e:
        print(f"获取端口失败: {e}")
    return None


def deploy_function(workers: int, cpu_limit: int, memory: str) -> bool:
    """部署函数"""
    print(f"\n[部署] workers={workers}, cpu={cpu_limit}, mem={memory}")
    
    # 读取当前配置并修改
    with open("functions/nsfw-detector/function.yaml", "r") as f:
        config = f.read()
    
    # 修改 workers
    config = config.replace(f"numWorkers: ", f"numWorkers: {workers}  # ")
    # 恢复正确的 workers
    import re
    config = re.sub(r'numWorkers: \d+ # ', f'numWorkers: {workers}', config)
    
    # 修改 CPU 限制
    config = re.sub(r'cpu: "\d+"\s*$', f'cpu: "{cpu_limit}"', config, flags=re.MULTILINE)
    
    # 修改内存限制
    config = re.sub(r'memory: "\d+Gi"', f'memory: "{memory}"', config)
    
    # 保存临时配置
    with open("/tmp/function-test.yaml", "w") as f:
        f.write(config)
    
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
         "--path", "functions/nsfw-detector",
         "--namespace", "nuclio",
         "--project-name", "default",
         "--no-pull"],
        capture_output=True, text=True, timeout=300
    )
    
    if result.returncode != 0:
        print(f"部署失败: {result.stderr}")
        return False
    
    print("部署成功，等待就绪...")
    time.sleep(15)
    return True


def run_benchmark(server: str, concurrency: int, duration: int) -> Optional[TestResult]:
    """运行基准测试"""
    cmd = [
        "uv", "run", "python", "-m", "faas_benchmark",
        "--server", server,
        "--concurrency", str(concurrency),
        "--duration", str(duration),
        "--warmup", "3",
        "--output", "json"
    ]
    
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, 
            timeout=duration + 60, cwd="benchmark"
        )
        
        if result.returncode != 0:
            print(f"测试失败: {result.stderr}")
            return None
        
        # 解析 JSON
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if line and line[0] == '{':
                data = json.loads(line)
                return data
        return None
        
    except Exception as e:
        print(f"测试错误: {e}")
        return None


def print_results(results: List[TestResult]):
    """打印结果汇总"""
    if not results:
        print("无测试结果")
        return
    
    print("\n" + "="*90)
    print("性能测试汇总 (按 QPS 排序)")
    print("="*90)
    print(f"{'排名':<4} {'配置':<20} {'QPS':<8} {'平均延迟':<10} {'P95':<10} {'P99':<10}")
    print("-" * 90)
    
    sorted_results = sorted(results, key=lambda x: x.qps, reverse=True)
    for i, r in enumerate(sorted_results[:10], 1):
        print(f"{i:<4} {r.config.name:<20} {r.qps:<8.2f} {r.avg_latency:<10.2f} "
              f"{r.p95_latency:<10.2f} {r.p99_latency:<10.2f}")
    
    best = sorted_results[0]
    print("\n" + "="*90)
    print(f"🏆 最佳配置: {best.config.name}")
    print(f"   QPS: {best.qps:.2f} | 平均延迟: {best.avg_latency:.2f}ms | P95: {best.p95_latency:.2f}ms")
    print("="*90)


def main():
    print("="*60)
    print("FaaS 性能快速调优")
    print("="*60)
    
    results = []
    
    # 测试配置矩阵
    configs = [
        TestConfig("w4-c10", 4, 8, "8Gi", 10, 20),
        TestConfig("w4-c20", 4, 8, "8Gi", 20, 20),
        TestConfig("w6-c10", 6, 8, "8Gi", 10, 20),
        TestConfig("w6-c20", 6, 8, "8Gi", 20, 20),
        TestConfig("w8-c10", 8, 8, "8Gi", 10, 20),
        TestConfig("w8-c20", 8, 8, "8Gi", 20, 20),
        TestConfig("w8-c40", 8, 8, "8Gi", 40, 20),
        TestConfig("w10-c20", 10, 8, "8Gi", 20, 20),
    ]
    
    for cfg in configs:
        print(f"\n{'='*60}")
        print(f"测试: {cfg.name}")
        print(f"{'='*60}")
        
        if not deploy_function(cfg.workers, cfg.cpu_limit, cfg.memory):
            continue
        
        port = get_function_port()
        if not port:
            print("无法获取端口")
            continue
        
        server = f"http://localhost:{port}"
        data = run_benchmark(server, cfg.concurrency, cfg.duration)
        
        if data:
            result = TestResult(
                config=cfg,
                qps=data.get('qps', 0),
                avg_latency=data.get('avg_latency_ms', 0),
                p95_latency=data.get('p95_latency_ms', 0),
                p99_latency=data.get('p99_latency_ms', 0),
                success_rate=data.get('success_rate', 0) * 100
            )
            results.append(result)
            print(result)
        
        time.sleep(3)
    
    print_results(results)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n测试被中断")
