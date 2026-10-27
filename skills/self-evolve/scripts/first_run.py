#!/usr/bin/env python3
"""首次引导：增量扫描与 HTML，当前 Agent 接手分析；不调用独立模型。"""
from __future__ import annotations
import sys
from public_workflow import main as public_main


def main() -> int:
    # Old --no-panel remains harmless: the public entry produces standalone HTML.
    sys.argv = [sys.argv[0], 'scan', *[a for a in sys.argv[1:] if a != '--no-panel']]
    return public_main()


if __name__ == '__main__':
    raise SystemExit(main())
