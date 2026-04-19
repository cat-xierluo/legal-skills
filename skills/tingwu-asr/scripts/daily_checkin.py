#!/usr/bin/env python3
"""每日签到：检查登录状态，记录剩余额度

Agent 工作流:
  1. 先用 MCP Playwright 访问 tingwu.aliyun.com 触发每日签到
  2. 用 MCP Playwright 提取 cookie，调用 login.py --save-cookies 保存
  3. 运行本脚本检查登录状态和额度

本脚本只做纯 HTTP 部分（步骤 3）。
"""

import json
import sys
import time
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
COOKIE_PATH = SKILL_ROOT / "config" / "cookies.json"
QUOTA_LOG = SKILL_ROOT / "config" / "quota_history.jsonl"


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from tingwu import TingwuClient

    try:
        client = TingwuClient()
    except FileNotFoundError as e:
        print(f"错误: {e}")
        print("请先用 MCP Playwright 登录并保存 Cookie")
        sys.exit(1)

    auth = client.check_auth()
    if not auth["valid"]:
        print(f"登录无效: {auth['error']}")
        print("请先用 MCP Playwright 重新登录")
        sys.exit(1)

    print("登录状态: 有效")
    user = auth.get("user", {})
    name = user.get("aliyunUserName") or user.get("displayName", "")
    if name:
        print(f"用户: {name}")

    try:
        account = client.get_account_info()
        print(f"账户信息: {json.dumps(account, ensure_ascii=False, indent=2)}")
        _log_quota(account)
    except Exception as e:
        print(f"获取额度失败: {e}")

    print("签到完成!")


def _log_quota(account):
    QUOTA_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "account": account,
    }
    with open(QUOTA_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
