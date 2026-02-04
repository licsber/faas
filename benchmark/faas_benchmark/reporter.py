"""测试结果报告."""

import json

from .models import BenchmarkResult


def print_results(result: BenchmarkResult):
    """打印文本格式结果."""
    print(f"\n{'=' * 60}")
    print("测试结果")
    print(f"{'=' * 60}")
    print(f"总请求数:        {result.total_requests}")
    print(f"成功请求:        {result.successful_requests} ({result.success_rate:.2f}%)")
    print(f"失败请求:        {result.failed_requests}")
    print(f"总耗时:          {result.total_time_seconds:.2f} 秒")
    print(f"QPS:             {result.qps:.2f}")
    print(f"{'=' * 60}")
    print("延迟统计 (毫秒)")
    print(f"{'=' * 60}")
    print(f"最小值:          {result.min_latency_ms:.2f} ms")
    print(f"平均值:          {result.mean_latency_ms:.2f} ms")
    print(f"中位数:          {result.median_latency_ms:.2f} ms")
    print(f"P95:             {result.p95_latency_ms:.2f} ms")
    print(f"P99:             {result.p99_latency_ms:.2f} ms")
    print(f"最大值:          {result.max_latency_ms:.2f} ms")

    if result.errors:
        print(f"{'=' * 60}")
        print("错误统计")
        print(f"{'=' * 60}")
        for error, count in sorted(result.errors.items(), key=lambda x: -x[1]):
            print(f"  {error}: {count}")

    print(f"{'=' * 60}\n")


def print_results_json(result: BenchmarkResult):
    """打印 JSON 格式结果."""
    output = {
        "config": {
            "server": result.config.server,
            "function": result.config.function,
            "concurrency": result.config.concurrency,
            "mode": result.config.mode,
        },
        "summary": {
            "total_requests": result.total_requests,
            "successful_requests": result.successful_requests,
            "failed_requests": result.failed_requests,
            "success_rate_percent": round(result.success_rate, 2),
            "total_time_seconds": round(result.total_time_seconds, 2),
            "qps": round(result.qps, 2),
        },
        "latency": {
            "min_ms": round(result.min_latency_ms, 2),
            "mean_ms": round(result.mean_latency_ms, 2),
            "median_ms": round(result.median_latency_ms, 2),
            "p95_ms": round(result.p95_latency_ms, 2),
            "p99_ms": round(result.p99_latency_ms, 2),
            "max_ms": round(result.max_latency_ms, 2),
        },
        "errors": result.errors,
        "timestamp": result.end_time.isoformat(),
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


def report(result: BenchmarkResult, output_format: str = "text"):
    """根据格式输出结果."""
    match output_format:
        case "json":
            print_results_json(result)
        case _:
            print_results(result)
