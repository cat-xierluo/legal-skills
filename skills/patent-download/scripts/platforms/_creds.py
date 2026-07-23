#!/usr/bin/env python3
"""平台凭证加载 —— 从环境变量读取（公开发布版）。

各平台账号通过环境变量提供：
    PATENT_<PLATFORM>_USERNAME
    PATENT_<PLATFORM>_PASSWORD
例如 uyanip → PATENT_UYANIP_USERNAME / PATENT_UYANIP_PASSWORD

可在 config/.env 文件中配置（本地，不入库），见 config/.env.example；
也可直接 export。环境变量优先于 .env 文件。

无额外依赖：.env 由本模块手动解析。读不到返回空字符串，
由调用方（平台 main 或 cli.py）决定如何提示用户。
"""

import os

ENV_PREFIX = "PATENT_"
_ENV_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "config", ".env",
)

_loaded = False
_env_cache = {}


def _load_dotenv():
    """手动解析 config/.env（若存在），结果缓存。无依赖。"""
    global _loaded, _env_cache
    if _loaded:
        return
    _loaded = True
    try:
        with open(_ENV_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                _env_cache[key.strip()] = val.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass


def _get(key: str):
    """环境变量优先，回退 .env 文件。"""
    _load_dotenv()
    return os.environ.get(key) or _env_cache.get(key)


def load_creds(platform: str) -> dict:
    """读取指定平台的账号；读不到返回空字符串。

    命名：PATENT_<PLATFORM 大写>_USERNAME / _PASSWORD
    """
    prefix = f"{ENV_PREFIX}{platform.upper()}_"
    return {
        "username": _get(prefix + "USERNAME") or "",
        "password": _get(prefix + "PASSWORD") or "",
    }


# 需要账号的平台（google/epub 免登录，不在此列）
LOGIN_PLATFORMS = ("uyanip", "patentstar", "gpic", "pss")


def check_leak() -> bool:
    """防泄露自检：确认 config/.env 未被 git 追踪。

    返回 True 表示安全（.env 未入库或不在 git 仓库内），False 表示有泄露风险。
    用于发布前自检，避免真实账号被误提交。
    """
    import subprocess
    env_file = os.path.normpath(_ENV_PATH)
    # 从 .env 所在目录向上找 git 仓库根，路径更可靠
    start_dir = os.path.dirname(env_file)
    try:
        toplevel = subprocess.run(
            ["git", "-C", start_dir, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
        ).stdout.strip()
    except (FileNotFoundError, OSError):
        return True  # 无 git，跳过检查
    if not toplevel:
        return True  # 非 git 仓库

    rel = os.path.relpath(env_file, toplevel)
    tracked = subprocess.run(
        ["git", "-C", toplevel, "ls-files", "--error-unmatch", rel],
        capture_output=True, text=True,
    )
    if tracked.returncode == 0:
        print(f"🚨 警告：{rel} 已被 git 追踪！真实账号可能已泄露。")
        print("   请立即执行（撤销追踪，不删本地文件）：")
        print(f"     git -C \"{toplevel}\" rm --cached {rel}")
        print("   并确认 .gitignore 含 **/.env 规则。")
        return False
    return True


if __name__ == "__main__":
    # 自检：打印各平台是否配置了账号（不打印密码）
    import sys
    # 先做防泄露自检
    check_leak()
    print()
    key = sys.argv[1] if len(sys.argv) > 1 else None
    if key:
        c = load_creds(key)
        print(f"{key}: username={'有' if c.get('username') else '无'}, password={'有' if c.get('password') else '无'}")
    else:
        print("需要账号的平台：")
        for k in LOGIN_PLATFORMS:
            c = load_creds(k)
            print(f"  {k:15} username={'有' if c.get('username') else '无'}, password={'有' if c.get('password') else '无'}")
        print("\n免登录平台：google, epub（无需配置）")
