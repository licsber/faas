"""入口点."""

import asyncio
import sys

from .cli import config_from_args, parse_args
from .reporter import report
from .tester import LoadTester


def main():
    """主函数."""
    args = parse_args()
    config = config_from_args(args)

    try:
        tester = LoadTester(config)
        result = asyncio.run(tester.run())
        report(result, config.output_format)
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
