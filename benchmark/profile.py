#!/usr/bin/env python3
"""
性能分析工具 - 分析各环节耗时
"""

import asyncio
import aiohttp
import time
import statistics
from dataclasses import dataclass
from typing import List

@dataclass
class RequestMetrics:
    total_time: float
    start_time: float
    end_time: float

async def make_request(session: aiohttp.ClientSession, url: str, image_url: str) -> RequestMetrics:
    """发起单个请求并记录时间"""
    start = time.time()
    try:
        async with session.post(
            url,
            json={"url": image_url},
            headers={"Content-Type": "application/json"}
        ) as resp:
            await resp.read()
    except Exception as e:
        print(f"请求错误: {e}")
    end = time.time()
    return RequestMetrics(total_time=end-start, start_time=start, end_time=end)


async def profile_concurrent(server: str, concurrency: int, total_requests: int):
    """分析并发性能"""
    print(f"\n性能分析: 并发={concurrency}, 总请求={total_requests}")
    print("="*60)
    
    image_url = "https://picsum.photos/400/300"
    
    async with aiohttp.ClientSession() as session:
        # 预热
        print("预热中...")
        for _ in range(3):
            await make_request(session, server, image_url)
        
        # 测试
        print(f"开始测试...")
        start_time = time.time()
        
        # 创建请求队列
        semaphore = asyncio.Semaphore(concurrency)
        
        async def bounded_request():
            async with semaphore:
                return await make_request(session, server, image_url)
        
        tasks = [bounded_request() for _ in range(total_requests)]
        results = await asyncio.gather(*tasks)
        
        total_time = time.time() - start_time
        
        # 分析结果
        latencies = [r.total_time * 1000 for r in results if r.total_time > 0]  # ms
        
        if latencies:
            print(f"\n结果汇总:")
            print(f"  总耗时: {total_time:.2f} 秒")
            print(f"  理论 QPS: {total_requests / total_time:.2f}")
            print(f"  平均延迟: {statistics.mean(latencies):.2f} ms")
            print(f"  中位数: {statistics.median(latencies):.2f} ms")
            print(f"  最小: {min(latencies):.2f} ms")
            print(f"  最大: {max(latencies):.2f} ms")
            if len(latencies) > 1:
                print(f"  标准差: {statistics.stdev(latencies):.2f} ms")
            
            # 延迟分布
            sorted_lat = sorted(latencies)
            p50 = sorted_lat[int(len(sorted_lat) * 0.5)]
            p90 = sorted_lat[int(len(sorted_lat) * 0.9)]
            p95 = sorted_lat[int(len(sorted_lat) * 0.95)]
            p99 = sorted_lat[int(len(sorted_lat) * 0.99)]
            
            print(f"\n延迟分布:")
            print(f"  P50: {p50:.2f} ms")
            print(f"  P90: {p90:.2f} ms")
            print(f"  P95: {p95:.2f} ms")
            print(f"  P99: {p99:.2f} ms")
            
            # 计算实际吞吐量
            print(f"\n实际吞吐:")
            print(f"  每请求平均耗时: {statistics.mean(latencies)/1000:.3f} 秒")
            print(f"  理论最大 QPS ({concurrency} 并发): {concurrency / (statistics.mean(latencies)/1000):.2f}")


async def profile_single(server: str):
    """分析单请求各环节耗时"""
    print("\n单请求详细分析")
    print("="*60)
    
    image_url = "https://picsum.photos/400/300"
    
    # 首先测试图片下载速度
    print("\n1. 测试图片下载速度...")
    async with aiohttp.ClientSession() as session:
        dl_times = []
        for _ in range(5):
            start = time.time()
            async with session.get(image_url) as resp:
                await resp.read()
            dl_times.append((time.time() - start) * 1000)
        print(f"   图片下载平均耗时: {statistics.mean(dl_times):.2f} ms")
    
    # 测试端到端推理
    print("\n2. 测试端到端推理...")
    async with aiohttp.ClientSession() as session:
        times = []
        for _ in range(10):
            start = time.time()
            async with session.post(
                server,
                json={"url": image_url},
                headers={"Content-Type": "application/json"}
            ) as resp:
                data = await resp.json()
            elapsed = (time.time() - start) * 1000
            times.append(elapsed)
            await asyncio.sleep(0.1)  # 避免太快
        
        print(f"   推理平均耗时: {statistics.mean(times):.2f} ms")
        print(f"   理论单 worker QPS: {1000/statistics.mean(times):.2f}")


async def find_max_throughput(server: str):
    """寻找最大吞吐量"""
    print("\n寻找最大吞吐量")
    print("="*60)
    
    image_url = "https://picsum.photos/400/300"
    
    for concurrency in [1, 2, 4, 6, 8, 10, 12]:
        async with aiohttp.ClientSession() as session:
            # 预热
            for _ in range(2):
                await make_request(session, server, image_url)
            
            # 测试 5 秒
            start = time.time()
            count = 0
            errors = 0
            
            semaphore = asyncio.Semaphore(concurrency)
            
            async def bounded_call():
                nonlocal errors
                async with semaphore:
                    try:
                        async with session.post(
                            server,
                            json={"url": image_url},
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as resp:
                            if resp.status == 200:
                                return True
                            else:
                                errors += 1
                                return False
                    except:
                        errors += 1
                        return False
            
            # 持续发送请求 5 秒
            tasks = set()
            while time.time() - start < 5:
                if len(tasks) < concurrency * 2:
                    task = asyncio.create_task(bounded_call())
                    tasks.add(task)
                    task.add_done_callback(lambda t: tasks.discard(t))
                
                # 检查完成的任务
                done = [t for t in tasks if t.done()]
                for t in done:
                    if t.result():
                        count += 1
                    tasks.discard(t)
                
                await asyncio.sleep(0.001)
            
            # 等待剩余任务
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                count += sum(1 for r in results if r is True)
            
            elapsed = time.time() - start
            qps = count / elapsed
            
            print(f"  并发 {concurrency:2d}: {qps:5.2f} QPS ({count} 成功, {errors} 错误)")
            await asyncio.sleep(0.5)


async def main():
    import sys
    server = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:32768"
    
    print(f"目标服务器: {server}")
    
    # 单请求分析
    await profile_single(server)
    
    # 不同并发度测试
    await find_max_throughput(server)
    
    # 详细分析
    print("\n")
    await profile_concurrent(server, concurrency=8, total_requests=50)


if __name__ == "__main__":
    asyncio.run(main())
