"""命令行接口."""

import argparse

from .config import create_config
from .models import BenchmarkConfig


def parse_args() -> argparse.Namespace:
    """解析命令行参数."""
    parser = argparse.ArgumentParser(
        description="FaaS 性能测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基础测试（默认参数）
  uv run python -m faas_benchmark --server http://localhost:8080

  # 高并发测试
  uv run python -m faas_benchmark --server http://localhost:8080 -c 50 -n 1000

  # 压测 60 秒
  uv run python -m faas_benchmark --server http://localhost:8080 -c 20 -d 60

  # 使用本地图片
  uv run python -m faas_benchmark --server http://localhost:8080 \\
      --mode image --image-path ./test.jpg
        """,
    )

    # 服务器配置
    parser.add_argument(
        "--server",
        "-s",
        required=True,
        help="服务器地址，例如: http://localhost:8080 或 http://192.168.1.100:49152",
    )

    parser.add_argument(
        "--function",
        "-f",
        default="nsfw-detector",
        help="函数名称 (默认: nsfw-detector)",
    )

    # 测试配置
    parser.add_argument(
        "--concurrency",
        "-c",
        type=int,
        default=10,
        help="并发数 (默认: 10)",
    )

    parser.add_argument(
        "--requests",
        "-n",
        type=int,
        default=100,
        help="总请求数 (默认: 100)，与 --duration 互斥",
    )

    parser.add_argument(
        "--duration",
        "-d",
        type=int,
        help="测试时长（秒），优先级高于 --requests",
    )

    # 测试模式
    parser.add_argument(
        "--mode",
        "-m",
        choices=["url", "image", "health"],
        default="url",
        help="测试模式: url=使用图片URL, image=使用本地图片, health=健康检查 (默认: url)",
    )

    parser.add_argument(
        "--image-url",
        default="https://picsum.photos/400/300",
        help="测试图片 URL (默认: https://picsum.photos/400/300)",
    )

    parser.add_argument(
        "--image-path",
        help="本地测试图片路径 (mode=image 时使用)",
    )

    # 其他选项
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="请求超时时间（秒）(默认: 30)",
    )

    parser.add_argument(
        "--warmup",
        type=int,
        default=5,
        help="预热请求数 (默认: 5)",
    )

    parser.add_argument(
        "--output",
        "-o",
        choices=["text", "json"],
        default="text",
        help="输出格式 (默认: text)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="显示详细进度",
    )

    return parser.parse_args()


def config_from_args(args: argparse.Namespace) -> BenchmarkConfig:
    """从参数创建配置."""
    return create_config(
        server=args.server,
        function=args.function,
        concurrency=args.concurrency,
        requests=args.requests,
        duration=args.duration,
        mode=args.mode,
        image_url=args.image_url,
        image_path=args.image_path,
        timeout=args.timeout,
        warmup=args.warmup,
        output=args.output,
        verbose=args.verbose,
    )
