#!/usr/bin/env python3
"""
便捷入口脚本 - 等同于 `python -m faas_benchmark`

使用方法:
    uv run python runner.py --server http://localhost:8080
"""

from faas_benchmark.__main__ import main

if __name__ == "__main__":
    main()
