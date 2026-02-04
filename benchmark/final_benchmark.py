#!/usr/bin/env python3
"""
最终性能基准测试 - 测试所有优化配置
"""

import asyncio
import aiohttp
import time
import statistics
import base64
from pathlib import Path
import json

IMAGE_PATH = Path(__file__).parent / "Kirito.jpg"


def load_image_base64() -> str:
    with open(IMAGE_PATH, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')


async def test_configuration(server: str, config_name: str, concurrency: int, 
                             duration: int = 20) -> dict:
    """测试特定配置"""
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
                req_start = time.time()
                try:
                    async with session.post(server, json={"image": image_b64},
                                           headers={"Content-Type": "application/json"}) as resp:
                        await resp.read()
                        latency = (time.time() - req_start) * 1000
                        latencies.append(latency)
                except:
                    errors += 1
        
        workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
        await asyncio.gather(*workers)
        
        total_time = time.time() - start
        
        if latencies:
            latencies.sort()
            return {
                'config': config_name,
                'concurrency': concurrency,
                'qps': len(latencies) / total_time,
                'success': len(latencies),
                'errors': errors,
                'avg_lat': statistics.mean(latencies),
                'p50_lat': latencies[int(len(latencies)*0.5)],
                'p95_lat': latencies[int(len(latencies)*0.95)],
                'p99_lat': latencies[int(len(latencies)*0.99)],
                'max_lat': max(latencies)
            }
        return None


async def main():
    import sys
    server = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:32768"
    
    print("="*80)
    print("FaaS 最终性能基准测试")
    print("="*80)
    print(f"目标服务器: {server}")
    print(f"测试图片: {IMAGE_PATH} ({IMAGE_PATH.stat().st_size/1024:.1f} KB)")
    print()
    
    results = []
    
    # 测试不同并发配置
    test_configs = [
        ("最优延迟", 1),
        ("低并发", 2),
        ("中并发", 4),
        ("推荐并发", 6),
        ("高并发", 8),
        ("极限并发", 12),
        ("超并发", 16),
    ]
    
    for name, concurrency in test_configs:
        print(f"测试 {name} (并发={concurrency})...", end=" ", flush=True)
        result = await test_configuration(server, name, concurrency, duration=15)
        if result:
            results.append(result)
            print(f"QPS: {result['qps']:.2f}, 延迟: {result['avg_lat']:.1f}ms")
        else:
            print("失败")
    
    # 打印汇总表
    print()
    print("="*80)
    print("性能测试结果汇总")
    print("="*80)
    print(f"{'配置':<12} {'并发':<6} {'QPS':<8} {'平均延迟':<10} {'P95延迟':<10} {'P99延迟':<10}")
    print("-"*80)
    
    for r in results:
        print(f"{r['config']:<12} {r['concurrency']:<6} {r['qps']:<8.2f} "
              f"{r['avg_lat']:<10.1f} {r['p95_lat']:<10.1f} {r['p99_lat']:<10.1f}")
    
    # 找出最佳配置
    best_qps = max(results, key=lambda x: x['qps'])
    best_lat = min(results, key=lambda x: x['avg_lat'])
    
    # 找到最佳平衡点 (QPS > 90% 最大 && 延迟较低)
    threshold = best_qps['qps'] * 0.9
    balanced_candidates = [r for r in results if r['qps'] >= threshold]
    best_balanced = min(balanced_candidates, key=lambda x: x['avg_lat']) if balanced_candidates else best_qps
    
    print()
    print("="*80)
    print("推荐配置:")
    print("="*80)
    print(f"  🏆 最高吞吐量: 并发 {best_qps['concurrency']} -> {best_qps['qps']:.2f} QPS")
    print(f"  ⚡ 最低延迟:   并发 {best_lat['concurrency']} -> {best_lat['avg_lat']:.1f} ms")
    print(f"  ⚖️  最佳平衡: 并发 {best_balanced['concurrency']} -> "
          f"{best_balanced['qps']:.2f} QPS, {best_balanced['avg_lat']:.1f} ms 延迟")
    print("="*80)
    
    # 保存结果
    result_file = Path("benchmark_results.json")
    with open(result_file, 'w') as f:
        json.dump({
            'server': server,
            'image': str(IMAGE_PATH),
            'results': results,
            'recommendation': {
                'best_qps': best_qps,
                'best_latency': best_lat,
                'best_balanced': best_balanced
            }
        }, f, indent=2, default=str)
    print(f"\n结果已保存到: {result_file}")


if __name__ == "__main__":
    asyncio.run(main())
