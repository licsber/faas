#!/usr/bin/env python3
"""
本地图片性能分析 - 排除网络下载影响
"""

import asyncio
import aiohttp
import time
import statistics
import base64
from pathlib import Path

# 加载本地图片
IMAGE_PATH = Path(__file__).parent / "Kirito.jpg"


def load_image_base64() -> str:
    """加载本地图片为 base64"""
    with open(IMAGE_PATH, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')


async def make_request(session: aiohttp.ClientSession, url: str, image_b64: str) -> float:
    """发起单个请求并返回耗时（毫秒）"""
    start = time.time()
    try:
        async with session.post(
            url,
            json={"image": image_b64},
            headers={"Content-Type": "application/json"}
        ) as resp:
            await resp.read()
            return (time.time() - start) * 1000
    except Exception as e:
        print(f"请求错误: {e}")
        return -1


async def find_max_throughput(server: str, duration: int = 10):
    """寻找最大吞吐量"""
    print(f"\n{'='*70}")
    print(f"寻找最大吞吐量 (测试时长: {duration}秒)")
    print(f"{'='*70}")
    
    image_b64 = load_image_base64()
    print(f"图片大小: {len(image_b64)/1024:.1f} KB")
    
    results_summary = []
    
    for concurrency in [1, 2, 4, 6, 8, 10, 12, 16, 20]:
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=100),
            timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            
            # 预热
            for _ in range(2):
                await make_request(session, server, image_b64)
            
            # 测试
            start = time.time()
            success = 0
            errors = 0
            latencies = []
            
            semaphore = asyncio.Semaphore(concurrency)
            
            async def bounded_call():
                nonlocal success, errors
                async with semaphore:
                    latency = await make_request(session, server, image_b64)
                    if latency > 0:
                        success += 1
                        latencies.append(latency)
                    else:
                        errors += 1
            
            # 持续发送请求
            tasks = []
            while time.time() - start < duration:
                if len(tasks) < concurrency * 2:
                    task = asyncio.create_task(bounded_call())
                    tasks.append(task)
                
                # 清理完成的任务
                tasks = [t for t in tasks if not t.done()]
                await asyncio.sleep(0.001)
            
            # 等待剩余任务
            if tasks:
                await asyncio.gather(*tasks)
            
            elapsed = time.time() - start
            qps = success / elapsed
            
            # 计算延迟统计
            if latencies:
                avg_lat = statistics.mean(latencies)
                med_lat = statistics.median(latencies)
                max_lat = max(latencies)
                p95 = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 20 else max_lat
            else:
                avg_lat = med_lat = max_lat = p95 = 0
            
            results_summary.append({
                'concurrency': concurrency,
                'qps': qps,
                'success': success,
                'errors': errors,
                'avg_lat': avg_lat,
                'p95_lat': p95
            })
            
            print(f"  并发 {concurrency:2d}: {qps:6.2f} QPS | 延迟: {avg_lat:7.1f}ms (P95: {p95:7.1f}ms) | {success} 成功 {errors} 错误")
            await asyncio.sleep(0.3)
    
    # 找出最佳配置
    print(f"\n{'='*70}")
    print("最佳配置分析:")
    print(f"{'='*70}")
    
    best_qps = max(results_summary, key=lambda x: x['qps'])
    print(f"  最高 QPS: 并发 {best_qps['concurrency']} -> {best_qps['qps']:.2f} QPS")
    
    # 找到延迟和 QPS 平衡的点（QPS > 90% 最大值且延迟较低）
    threshold = best_qps['qps'] * 0.9
    balanced = [r for r in results_summary if r['qps'] >= threshold]
    if balanced:
        best_balanced = min(balanced, key=lambda x: x['avg_lat'])
        print(f"  最佳平衡: 并发 {best_balanced['concurrency']} -> {best_balanced['qps']:.2f} QPS, 延迟 {best_balanced['avg_lat']:.1f}ms")


async def stress_test(server: str, concurrency: int, duration: int):
    """压力测试"""
    print(f"\n{'='*70}")
    print(f"压力测试: 并发={concurrency}, 时长={duration}秒")
    print(f"{'='*70}")
    
    image_b64 = load_image_base64()
    
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=100),
        timeout=aiohttp.ClientTimeout(total=30)
    ) as session:
        
        # 预热
        for _ in range(3):
            await make_request(session, server, image_b64)
        
        # 压力测试
        start = time.time()
        latencies = []
        errors = 0
        
        semaphore = asyncio.Semaphore(concurrency)
        
        async def worker():
            nonlocal errors
            while time.time() - start < duration:
                latency = await make_request(session, server, image_b64)
                if latency > 0:
                    latencies.append(latency)
                else:
                    errors += 1
        
        # 启动 workers
        workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
        await asyncio.gather(*workers)
        
        total_time = time.time() - start
        
        # 分析结果
        if latencies:
            latencies.sort()
            print(f"  总请求数: {len(latencies)}")
            print(f"  错误数: {errors}")
            print(f"  总耗时: {total_time:.2f} 秒")
            print(f"  QPS: {len(latencies)/total_time:.2f}")
            print(f"  平均延迟: {statistics.mean(latencies):.2f} ms")
            print(f"  中位数: {statistics.median(latencies):.2f} ms")
            print(f"  P95: {latencies[int(len(latencies)*0.95)]:.2f} ms")
            print(f"  P99: {latencies[int(len(latencies)*0.99)]:.2f} ms")
            print(f"  最大: {max(latencies):.2f} ms")


async def main():
    import sys
    server = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:32768"
    
    print(f"目标服务器: {server}")
    print(f"本地图片: {IMAGE_PATH}")
    
    # 寻找最大吞吐量
    await find_max_throughput(server, duration=10)
    
    # 最佳并发压力测试
    print("\n")
    await stress_test(server, concurrency=8, duration=20)


if __name__ == "__main__":
    asyncio.run(main())
