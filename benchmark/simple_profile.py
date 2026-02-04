#!/usr/bin/env python3
"""简单性能分析"""
import asyncio
import aiohttp
import time

async def test_qps(server: str, concurrency: int, duration: int = 10):
    url = "https://picsum.photos/400/300"
    success = 0
    errors = 0
    latencies = []
    
    async with aiohttp.ClientSession() as session:
        # 预热
        for _ in range(3):
            try:
                async with session.post(server, json={"url": url}, timeout=aiohttp.ClientTimeout(total=30)) as r:
                    await r.read()
            except:
                pass
        
        semaphore = asyncio.Semaphore(concurrency)
        
        async def request():
            nonlocal success, errors
            async with semaphore:
                start = time.time()
                try:
                    async with session.post(
                        server, 
                        json={"url": url},
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as resp:
                        await resp.read()
                        if resp.status == 200:
                            success += 1
                            latencies.append((time.time() - start) * 1000)
                        else:
                            errors += 1
                except Exception as e:
                    errors += 1
        
        # 运行测试
        start = time.time()
        tasks = []
        while time.time() - start < duration:
            if len(tasks) < concurrency * 3:
                tasks.append(asyncio.create_task(request()))
            
            # 清理已完成任务
            done = [t for t in tasks if t.done()]
            for d in done:
                tasks.remove(d)
            
            await asyncio.sleep(0.001)
        
        await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start
        
        qps = success / elapsed
        avg_lat = sum(latencies) / len(latencies) if latencies else 0
        
        print(f"并发 {concurrency:2d}: QPS={qps:5.2f}, 成功={success}, 错误={errors}, 平均延迟={avg_lat:.0f}ms")
        return qps

async def main():
    server = "http://localhost:32768"
    print(f"测试服务器: {server}")
    print("="*60)
    
    results = []
    for c in [1, 2, 4, 6, 8, 10, 12, 16, 20]:
        qps = await test_qps(server, c, duration=8)
        results.append((c, qps))
        await asyncio.sleep(1)
    
    print("\n" + "="*60)
    print("最优配置:")
    best = max(results, key=lambda x: x[1])
    print(f"  并发 {best[0]}: QPS = {best[1]:.2f}")

asyncio.run(main())
