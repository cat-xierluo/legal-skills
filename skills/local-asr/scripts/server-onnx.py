#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""
FunASR ONNX 加速服务入口。

默认行为：
1. 将默认模型切到 `paraformer-onnx`
2. 打开 ONNX INT8 量化
3. 其余参数复用 server.py
"""

import os

os.environ.setdefault("FUNASR_SERVER_DEFAULT_MODEL", "paraformer-onnx")
os.environ.setdefault("FUNASR_SERVER_DEFAULT_QUANTIZE", "1")

from server import main


if __name__ == "__main__":
    main()
