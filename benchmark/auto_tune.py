#!/usr/bin/env python3
"""
FaaS 性能自动调优脚本
自动调整配置并测试，找出最佳性能参数
"""

import subprocess
import json
import time
import sys
import re
from dataclasses import dataclass
from typing import List, Optional
import statistics

@dataclass
class TestResult:
    config_name: str
    qps: float
    avg_latency: float
    p95_latency: float
    p99_latency: float
    success_rate: float
    
    def __str__(self):
        return (f"{self.config_name:20s} | QPS: {self.qps:6.2f} | "
                f"Avg: {self.avg_latency:8.2f}ms | P95: {self.p95_latency:8.2f}ms | "
                f"P99: {self.p99_latency:8.2f}ms | Success: {self.success_rate:.1f}%")


class PerformanceTuner:
    def __init__(self, server: str = "http://localhost:32768"):
        self.server = server
        self.results: List[TestResult] = []
        
    def get_function_port(self) -> Optional[str]:
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
    
    def deploy_function(self, workers: int, cpu_limit: int, memory: str, 
                       batch_size: int = 1, use_onnx: bool = False) -> bool:
        """部署函数并返回是否成功"""
        print(f"\n{'='*60}")
        print(f"部署配置: workers={workers}, cpu={cpu_limit}, mem={memory}, batch={batch_size}")
        print(f"{'='*60}")
        
        # 先生成配置文件
        config = self._generate_config(workers, cpu_limit, memory, batch_size, use_onnx)
        config_path = "/tmp/function-tuned.yaml"
        with open(config_path, 'w') as f:
            f.write(config)
        
        # 删除旧函数
        subprocess.run(
            ["nuctl", "delete", "function", "nsfw-detector", "-n", "nuclio"],
            capture_output=True, timeout=60
        )
        time.sleep(2)
        
        # 部署新配置
        result = subprocess.run(
            ["nuctl", "deploy", "nsfw-detector", 
             "--file", config_path,
             "--path", "functions/nsfw-detector",
             "--namespace", "nuclio",
             "--project-name", "default",
             "--no-pull"],
            capture_output=True, text=True, timeout=300
        )
        
        if result.returncode != 0:
            print(f"部署失败: {result.stderr}")
            return False
        
        print("部署成功，等待服务就绪...")
        time.sleep(10)  # 等待服务启动
        
        # 获取新端口
        port = self.get_function_port()
        if port:
            self.server = f"http://localhost:{port}"
            print(f"服务地址: {self.server}")
        return True
    
    def _generate_config(self, workers: int, cpu_limit: int, memory: str, 
                        batch_size: int, use_onnx: bool) -> str:
        """生成 function.yaml 配置"""
        # 设置线程数 - 让每个 worker 可以使用更多线程来加速单请求
        threads_per_worker = max(1, cpu_limit // workers)
        
        config = f"""# NSFW 检测器 - 性能优化版本
metadata:
  name: nsfw-detector
  namespace: nuclio
  labels:
    app: nsfw-detector
    version: "tuned"

spec:
  runtime: python:3.12
  handler: main:handler
  description: "NSFW 检测 - 性能优化"
  
  resources:
    requests:
      cpu: "500m"
      memory: "3Gi"
    limits:
      cpu: "{cpu_limit}"
      memory: "{memory}"
  
  env:
    - name: NSFW_MODEL_NAME
      value: "Falconsai/nsfw_image_detection"
    - name: DEVICE
      value: "cpu"
    - name: PYTHONUNBUFFERED
      value: "1"
    - name: BATCH_SIZE
      value: "{batch_size}"
    - name: USE_ONNX
      value: "{'true' if use_onnx else 'false'}"
    # 调整线程数以优化性能 - 每个 worker 使用更多线程
    - name: OMP_NUM_THREADS
      value: "{threads_per_worker}"
    - name: MKL_NUM_THREADS
      value: "{threads_per_worker}"
    - name: OPENBLAS_NUM_THREADS
      value: "{threads_per_worker}"
    - name: VECLIB_MAXIMUM_THREADS
      value: "{threads_per_worker}"
    - name: NUMEXPR_NUM_THREADS
      value: "{threads_per_worker}"
    - name: PYTORCH_NUM_THREADS
      value: "{threads_per_worker}"
  
  build:
    path: ./functions/nsfw-detector
    baseImage: python:3.12-slim
    commands:
      - apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 wget git && rm -rf /var/lib/apt/lists/*
      - pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
      - pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn
      - pip install --no-cache-dir torch torchvision transformers Pillow numpy requests
      - pip install --no-cache-dir onnxruntime 2>/dev/null || true
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
  
  platform:
    attributes:
      restartPolicy:
        name: always
        maximumRetryCount: 3
  
  loggerSinks:
    - level: warning
      sink: ""
"""
        return config
    
    def run_benchmark(self, concurrency: int = 20, duration: int = 30, 
                     test_name: str = "") -> Optional[TestResult]:
        """运行基准测试"""
        print(f"\n运行测试: {test_name} (并发={concurrency}, 时长={duration}s)")
        print("-" * 60)
        
        cmd = [
            "uv", "run", "python", "-m", "faas_benchmark",
            "--server", self.server,
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
            
            # 解析 JSON 输出
            # 找到 JSON 部分
            lines = result.stdout.strip().split('\n')
            json_line = None
            for line in lines:
                line = line.strip()
                if line and line[0] == '{':
                    json_line = line
                    break
            
            if json_line:
                data = json.loads(json_line)
                r = TestResult(
                    config_name=test_name,
                    qps=data.get('qps', 0),
                    avg_latency=data.get('avg_latency_ms', 0),
                    p95_latency=data.get('p95_latency_ms', 0),
                    p99_latency=data.get('p99_latency_ms', 0),
                    success_rate=data.get('success_rate', 0) * 100
                )
                print(r)
                return r
            else:
                print("无法解析输出")
                return None
                
        except subprocess.TimeoutExpired:
            print("测试超时")
            return None
        except Exception as e:
            print(f"测试错误: {e}")
            return None
    
    def test_worker_configs(self):
        """测试不同 worker 数量配置"""
        print("\n" + "="*60)
        print("阶段 1: 测试 Worker 数量配置")
        print("="*60)
        
        # 8 核 CPU，测试不同 worker 数量
        configs = [
            (4, 8, "8Gi"),   # 少 worker，每个 worker 更多 CPU
            (6, 8, "8Gi"),
            (8, 8, "8Gi"),   # 1:1 匹配
            (10, 8, "8Gi"),
            (12, 8, "8Gi"),
        ]
        
        for workers, cpu, mem in configs:
            if self.deploy_function(workers, cpu, mem):
                # 测试不同并发度
                for conc in [10, 20, 40]:
                    result = self.run_benchmark(
                        concurrency=conc, 
                        duration=20,
                        test_name=f"w{workers}-c{conc}"
                    )
                    if result:
                        self.results.append(result)
            time.sleep(3)
    
    def test_batch_inference(self):
        """测试批处理推理"""
        print("\n" + "="*60)
        print("阶段 2: 测试批处理推理")
        print("="*60)
        
        # 使用最优的 worker 配置，添加批处理
        best_workers = 8
        
        for batch_size in [1, 2, 4]:
            if self.deploy_function(best_workers, 8, "8Gi", batch_size=batch_size):
                for conc in [10, 20, 40]:
                    result = self.run_benchmark(
                        concurrency=conc,
                        duration=20,
                        test_name=f"batch{batch_size}-c{conc}"
                    )
                    if result:
                        self.results.append(result)
            time.sleep(3)
    
    def test_resource_limits(self):
        """测试不同资源限制"""
        print("\n" + "="*60)
        print("阶段 3: 测试资源限制")
        print("="*60)
        
        configs = [
            (8, 8, "6Gi"),
            (8, 8, "10Gi"),
            (8, 10, "10Gi"),
        ]
        
        for workers, cpu, mem in configs:
            if self.deploy_function(workers, cpu, mem):
                for conc in [10, 20, 40]:
                    result = self.run_benchmark(
                        concurrency=conc,
                        duration=20,
                        test_name=f"cpu{cpu}-mem{mem}-c{conc}"
                    )
                    if result:
                        self.results.append(result)
            time.sleep(3)
    
    def print_summary(self):
        """打印测试结果汇总"""
        print("\n" + "="*80)
        print("性能测试汇总")
        print("="*80)
        
        if not self.results:
            print("没有测试结果")
            return
        
        # 按 QPS 排序
        sorted_results = sorted(self.results, key=lambda x: x.qps, reverse=True)
        
        print(f"{'排名':<4} {'配置':<20} {'QPS':<8} {'平均延迟':<10} {'P95延迟':<10} {'成功率':<8}")
        print("-" * 80)
        
        for i, r in enumerate(sorted_results[:15], 1):
            print(f"{i:<4} {r.config_name:<20} {r.qps:<8.2f} {r.avg_latency:<10.2f} "
                  f"{r.p95_latency:<10.2f} {r.success_rate:<8.1f}%")
        
        # 最佳配置
        best = sorted_results[0]
        print("\n" + "="*80)
        print(f"最佳配置: {best.config_name}")
        print(f"  QPS: {best.qps:.2f}")
        print(f"  平均延迟: {best.avg_latency:.2f} ms")
        print(f"  P95延迟: {best.p95_latency:.2f} ms")
        print("="*80)
    
    def run(self):
        """运行完整测试流程"""
        print("FaaS 性能自动调优开始")
        print(f"目标服务器: {self.server}")
        
        # 检查 nuctl 是否可用
        result = subprocess.run(["which", "nuctl"], capture_output=True)
        if result.returncode != 0:
            print("错误: nuctl 未安装，请先安装 nuctl")
            sys.exit(1)
        
        try:
            # 阶段 1: Worker 配置
            self.test_worker_configs()
            
            # 阶段 2: 资源限制
            self.test_resource_limits()
            
            # 打印汇总
            self.print_summary()
            
        except KeyboardInterrupt:
            print("\n测试被中断")
            self.print_summary()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="FaaS 性能自动调优")
    parser.add_argument("--server", "-s", default="http://localhost:32768", help="服务器地址")
    parser.add_argument("--quick", "-q", action="store_true", help="快速测试模式")
    args = parser.parse_args()
    
    tuner = PerformanceTuner(server=args.server)
    tuner.run()
