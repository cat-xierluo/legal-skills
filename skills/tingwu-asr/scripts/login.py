#!/usr/bin/env python3
"""保存 Cookie 到 config/cookies.json

由 Agent 通过 MCP Playwright 提取 cookie 后调用:
  python3 scripts/login.py --save-cookies '{"cna":"xxx","login_aliyunid_ticket":"xxx",...}'

也可以直接传入 cookie JSON 文件路径:
  python3 scripts/login.py --cookie-file /path/to/cookies.json
"""

import json
import sys
import time
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
COOKIE_PATH = SKILL_ROOT / "config" / "cookies.json"


def save_cookies(cookie_map):
    """保存 cookie 字典到文件"""
    if isinstance(cookie_map, str):
        cookie_map = json.loads(cookie_map)

    data = {
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cookies": cookie_map,
    }
    COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已保存 {len(cookie_map)} 个 Cookie 到 {COOKIE_PATH}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="通义听悟 Cookie 管理")
    parser.add_argument("--save-cookies", help="直接传入 cookie JSON 字符串")
    parser.add_argument("--cookie-file", help="从文件读取 cookie JSON")
    args = parser.parse_args()

    if args.save_cookies:
        save_cookies(args.save_cookies)
    elif args.cookie_file:
        with open(args.cookie_file, encoding="utf-8") as f:
            save_cookies(json.load(f))
    else:
        print(f"用法: {sys.argv[0]} --save-cookies '<json>' 或 --cookie-file <path>")
        sys.exit(1)


if __name__ == "__main__":
    main()
