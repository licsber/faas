"""配置管理."""

from .models import BenchmarkConfig


def create_config(
    server: str,
    function: str = "nsfw-detector",
    concurrency: int = 10,
    requests: int = 100,
    duration: int | None = None,
    mode: str = "url",
    image_url: str | None = "https://picsum.photos/400/300",
    image_path: str | None = None,
    timeout: int = 30,
    warmup: int = 5,
    output: str = "text",
    verbose: bool = False,
) -> BenchmarkConfig:
    """创建测试配置."""
    return BenchmarkConfig(
        server=server.rstrip("/"),
        function=function,
        concurrency=concurrency,
        total_requests=requests,
        duration=duration,
        mode=mode,
        image_url=image_url,
        image_path=image_path,
        timeout=timeout,
        warmup=warmup,
        output_format=output,
        verbose=verbose,
    )
