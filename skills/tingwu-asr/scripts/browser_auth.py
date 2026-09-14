#!/usr/bin/env python3
"""
通义听悟转录（浏览器认证版）
- API 调用通过 playwright MCP fetch 自动带 cookie
- OSS 上传仍走 Python（不需要 cookie）

使用: 在 MCP playwright 浏览器已登录 tingwu 的前提下调用
      Python 端只负责 OSS 上传 + syncPutLink + 轮询
      浏览器端负责 generatePutLink / startTrans / getResult
"""
import json
import sys
import time
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

# 这个模块被 MCP playwright 通过 run_code_unsafe 调用
# Python 端只暴露 OSS 上传 + syncPutLink
import requests

BASE_URL = "https://tingwu.aliyun.com/api"


def oss_upload(sts, local_path):
    """通过 STS 凭证上传到 OSS（不依赖 tingwu cookie）"""
    try:
        import oss2
    except ImportError:
        raise RuntimeError("需要 oss2: pip3 install oss2")

    auth = oss2.StsAuth(
        sts["accessKeyId"],
        sts["accessKeySecret"],
        sts["securityToken"],
    )
    bucket = oss2.Bucket(auth, sts["endpoint"], sts["bucket"])
    print(f"  正在上传到 OSS: {local_path} -> {sts['fileKey']}")
    oss2.resumable_upload(
        bucket, sts["fileKey"], local_path,
        progress_callback=lambda c, t: print(f"\r  进度: {c/t*100:.1f}%", end=""),
        num_threads=4,
    )
    print("\n  上传完成")
    return True
