#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "httpx>=0.27.0",
#   "pypdfium2>=4.30.0",
# ]
# ///

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import httpx  # noqa: F401
    import pypdfium2  # noqa: F401
except ImportError as error:
    missing = getattr(error, "name", str(error))
    print(f"[FAIL] 缺少依赖: {missing}")
    print("请使用: uv run scripts/smoke_test.py --skip-api-test")
    print("或安装: pip install httpx pypdfium2")
    raise SystemExit(1) from error

from mineru_ocr import MinerUBackend  # noqa: E402
from paddle_ocr import PaddleOCRBackend  # noqa: E402
from common import get_config_path, get_skill_root, has_paddle_config, load_env, resolve_mineru_token  # noqa: E402


def check_path(path: Path, label: str) -> bool:
    if path.exists():
        print(f"[OK] {label}: {path}")
        return True
    print(f"[FAIL] {label}: {path}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="legal-ocr 配置与结构自检")
    parser.add_argument("--skip-api-test", action="store_true", help="跳过外部 API 连通性检查")
    args = parser.parse_args()

    root = get_skill_root()
    checks = [
        check_path(root / "SKILL.md", "SKILL.md"),
        check_path(root / "config" / ".env.example", ".env.example"),
        check_path(root / "references" / "output_schema.md", "output_schema.md"),
        check_path(root / "archive" / ".gitkeep", "archive/.gitkeep"),
        check_path(root / "scripts" / "convert.py", "convert.py"),
        check_path(root / "scripts" / "paddle_ocr.py", "paddle backend"),
        check_path(root / "scripts" / "mineru_ocr.py", "mineru backend"),
    ]

    env = load_env()
    print("")
    print("配置状态")
    print("===============================================")
    print(f"配置文件: {get_config_path()} ({'存在' if get_config_path().exists() else '未创建，可从 .env.example 复制'})")
    print(f"PaddleOCR: {'已配置' if has_paddle_config(env) else '未配置'}")
    print(f"MinerU Token: {'已检测到' if resolve_mineru_token(env) else '未检测到，将使用轻量模式'}")
    print(f"法律术语优化: {env.get('LEGAL_OCR_LEGAL_TERMS') or 'auto'}")

    if not args.skip_api_test:
        print("")
        print("API 自检")
        print("===============================================")
        try:
            print(f"MinerU: {MinerUBackend(env).verify_token()}")
        except Exception as error:  # noqa: BLE001
            print(f"MinerU: {error}")
        try:
            PaddleOCRBackend(env)
            print("PaddleOCR: 配置字段可读取。")
        except Exception as error:  # noqa: BLE001
            print(f"PaddleOCR: {error}")

    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
