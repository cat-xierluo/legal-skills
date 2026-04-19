#!/usr/bin/env python3
"""检查登录状态和账户信息（纯 HTTP，无需浏览器）"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tingwu import TingwuClient


def main():
    try:
        client = TingwuClient()
    except FileNotFoundError as e:
        print(f"错误: {e}")
        sys.exit(1)

    auth = client.check_auth()
    if not auth["valid"]:
        print(f"登录状态: 无效 — {auth['error']}")
        print("请运行: python3 scripts/login.py 或让 Agent 用 MCP Playwright 登录")
        sys.exit(1)

    print("登录状态: 有效")
    user = auth.get("user", {})
    if isinstance(user, dict):
        print(f"用户信息: {json.dumps(user, ensure_ascii=False, indent=2)}")

    try:
        account = client.get_account_info()
        print(f"\n账户信息: {json.dumps(account, ensure_ascii=False, indent=2)}")
    except Exception as e:
        print(f"获取账户信息失败: {e}")


if __name__ == "__main__":
    main()
