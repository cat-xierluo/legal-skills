#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "httpx>=0.27.0",
# ]
# ///

"""配置与连通性自检。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import get_runtime_config, parse_document  # noqa: E402

DEFAULT_TEST_URL = (
    "https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/"
    "pp_structure_v3_demo.png"
)


def masked_token(token: str) -> str:
    if len(token) <= 12:
        return "***"
    return f"{token[:8]}...{token[-4:]}"


def main() -> int:
    parser = argparse.ArgumentParser(description="PaddleOCR skill 自检")
    parser.add_argument("--skip-api-test", action="store_true", help="只检查配置，不发请求")
    parser.add_argument("--test-url", help="覆盖默认测试文档 URL")
    args = parser.parse_args()

    print("=" * 60)
    print("PaddleOCR Skill Smoke Test")
    print("=" * 60)

    try:
        runtime = get_runtime_config()
    except ValueError as error:
        print(f"配置错误：{error}")
        print("请先编辑 paddle-ocr/config/.env")
        return 1

    print("配置检查通过")
    print(f"API URL: {runtime['api_url']}")
    print(f"Token: {masked_token(runtime['access_token'])}")
    print(f"Timeout: {runtime['timeout_seconds']} 秒")
    print(f"Batch pages: {runtime['batch_pages']}")

    if args.skip_api_test:
        print("已跳过 API 连通性测试")
        return 0

    test_url = args.test_url or DEFAULT_TEST_URL
    print(f"测试文档: {test_url}")
    result = parse_document(file_url=test_url)
    if not result.get("ok"):
        error = result.get("error") or {}
        print(f"API 测试失败：{error.get('message', '未知错误')}")
        return 1

    preview = result.get("text", "").replace("\n", " ")[:200]
    if preview:
        print(f"文本预览: {preview}...")
    print("API 测试通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
