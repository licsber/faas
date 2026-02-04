"""数据模型定义."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class BenchmarkConfig:
    """测试配置."""

    server: str
    function: str
    concurrency: int
    total_requests: int
    duration: Optional[int]
    mode: str
    image_url: Optional[str]
    image_path: Optional[str]
    timeout: int
    warmup: int
    output_format: str
    verbose: bool


@dataclass
class RequestResult:
    """单个请求结果."""

    success: bool
    latency_ms: float
    status_code: Optional[int] = None
    error: Optional[str] = None
    timestamp: float = field(default_factory=datetime.now().timestamp)


@dataclass
class BenchmarkResult:
    """测试结果汇总."""

    config: BenchmarkConfig
    start_time: datetime
    end_time: datetime
    total_requests: int
    successful_requests: int
    failed_requests: int
    latencies_ms: List[float]
    errors: Dict[str, int]
    qps: float

    @property
    def total_time_seconds(self) -> float:
        return (self.end_time - self.start_time).total_seconds()

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests * 100

    @property
    def min_latency_ms(self) -> float:
        return min(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def max_latency_ms(self) -> float:
        return max(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def mean_latency_ms(self) -> float:
        import statistics

        return statistics.mean(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def median_latency_ms(self) -> float:
        import statistics

        return statistics.median(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def p95_latency_ms(self) -> float:
        return self._percentile(0.95)

    @property
    def p99_latency_ms(self) -> float:
        return self._percentile(0.99)

    def _percentile(self, p: float) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_latencies = sorted(self.latencies_ms)
        idx = int(len(sorted_latencies) * p)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]
