"""负载测试核心逻辑."""

import asyncio
import time
from collections import deque
from datetime import datetime

import aiohttp

from .models import BenchmarkConfig, BenchmarkResult, RequestResult
from .payload import PayloadBuilder


class LoadTester:
    """负载测试器."""

    def __init__(self, config: BenchmarkConfig):
        self.config = config
        self.results: deque = deque(maxlen=100000)
        self._stop_event = asyncio.Event()
        self._request_count = 0
        self._lock = asyncio.Lock()
        self._payload_builder = PayloadBuilder(config.mode, config.image_url, config.image_path)

    async def _make_request(self, session: aiohttp.ClientSession) -> RequestResult:
        """执行单个请求."""
        payload = self._payload_builder.build()

        start_time = time.perf_counter()
        try:
            async with session.post(
                self.config.server,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
            ) as response:
                await response.text()
                latency_ms = (time.perf_counter() - start_time) * 1000

                if response.status == 200:
                    return RequestResult(
                        success=True, latency_ms=latency_ms, status_code=response.status
                    )
                else:
                    return RequestResult(
                        success=False,
                        latency_ms=latency_ms,
                        status_code=response.status,
                        error=f"HTTP {response.status}",
                    )

        except asyncio.TimeoutError:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return RequestResult(success=False, latency_ms=latency_ms, error="Timeout")
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return RequestResult(success=False, latency_ms=latency_ms, error=str(type(e).__name__))

    async def _worker(self, session: aiohttp.ClientSession, worker_id: int):
        """工作协程."""
        while not self._stop_event.is_set():
            result = await self._make_request(session)

            async with self._lock:
                self.results.append(result)
                self._request_count += 1

                # 检查是否达到请求数限制
                if (
                    self.config.duration is None
                    and self._request_count >= self.config.total_requests
                ):
                    self._stop_event.set()
                    break

    async def _progress_reporter(self):
        """进度报告协程."""
        if not self.config.verbose:
            return

        start_time = time.time()
        while not self._stop_event.is_set():
            await asyncio.sleep(1)
            async with self._lock:
                count = self._request_count

            elapsed = time.time() - start_time
            current_qps = count / elapsed if elapsed > 0 else 0

            if self.config.duration:
                print(
                    f"\r  进度: {count} 请求, {elapsed:.1f}s / {self.config.duration}s, "
                    f"当前 QPS: {current_qps:.1f}",
                    end="",
                    flush=True,
                )
            else:
                progress = count / self.config.total_requests * 100
                print(
                    f"\r  进度: {count}/{self.config.total_requests} ({progress:.1f}%), "
                    f"当前 QPS: {current_qps:.1f}",
                    end="",
                    flush=True,
                )
        print()

    async def _duration_controller(self):
        """时长控制器."""
        if self.config.duration:
            await asyncio.sleep(self.config.duration)
            self._stop_event.set()

    async def run(self) -> BenchmarkResult:
        """执行测试."""
        self._print_header()

        # 预热
        if self.config.warmup > 0:
            print(f"预热中... ({self.config.warmup} 请求)")
            async with aiohttp.ClientSession() as session:
                for _ in range(self.config.warmup):
                    await self._make_request(session)
            print("预热完成\n")

        # 正式测试
        print("开始测试...")
        start_time = datetime.now()
        self._stop_event.clear()

        async with aiohttp.ClientSession() as session:
            tasks = []

            # 启动工作协程
            for i in range(self.config.concurrency):
                task = asyncio.create_task(self._worker(session, i))
                tasks.append(task)

            # 启动进度报告
            progress_task = asyncio.create_task(self._progress_reporter())

            # 启动时长控制（如果指定了时长）
            if self.config.duration:
                duration_task = asyncio.create_task(self._duration_controller())
                tasks.append(duration_task)

            # 等待所有任务完成
            await self._stop_event.wait()

            # 取消所有工作协程
            for task in tasks:
                task.cancel()
            progress_task.cancel()

            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except asyncio.CancelledError:
                pass

        end_time = datetime.now()

        # 汇总结果
        return self._summarize_results(start_time, end_time)

    def _print_header(self):
        """打印测试头信息."""
        print("\n" + "=" * 60)
        print("FaaS 性能测试")
        print("=" * 60)
        print(f"服务器: {self.config.server}")
        print(f"并发数: {self.config.concurrency}")
        if self.config.duration:
            print(f"测试时长: {self.config.duration} 秒")
        else:
            print(f"请求总数: {self.config.total_requests}")
        print(f"测试模式: {self.config.mode}")
        print("=" * 60 + "\n")

    def _summarize_results(self, start_time: datetime, end_time: datetime) -> BenchmarkResult:
        """汇总测试结果."""
        results_list = list(self.results)
        latencies = [r.latency_ms for r in results_list]
        successful = sum(1 for r in results_list if r.success)
        failed = len(results_list) - successful

        # 统计错误类型
        errors = {}
        for r in results_list:
            if not r.success and r.error:
                errors[r.error] = errors.get(r.error, 0) + 1

        # 计算 QPS
        total_time = (end_time - start_time).total_seconds()
        qps = len(results_list) / total_time if total_time > 0 else 0

        return BenchmarkResult(
            config=self.config,
            start_time=start_time,
            end_time=end_time,
            total_requests=len(results_list),
            successful_requests=successful,
            failed_requests=failed,
            latencies_ms=latencies,
            errors=errors,
            qps=qps,
        )
