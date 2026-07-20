#!/usr/bin/env python3
"""update-readme.py — 把 README 表格里的占位 URL 替换为最新 release 的真实下载链接

用法:
  python3 update-readme.py [<owner>/<repo>] [<readme_path>]

默认从环境变量读取:
  GH_REPO        — owner/repo(默认从 git remote origin 推断)
  README_PATH    — README 路径(默认 ./README.md)

行为:
  1. 调 GitHub API 拿最新 release 的 assets
  2. 解析每个 <skill>-<semver>.zip 文件名,提取 skill 名
  3. 用真实 browser_download_url 替换 README 中形如
     `https://github.com/<owner>/<repo>/releases/latest/download/<skill>-<semver>.zip`
     的占位 URL
  4. 不匹配 skill 名(比如该 skill 没出现在 release 中)的占位保持原样
  5. 不修改非占位的 URL(release 真实的 release/download/<tag>/<file> 不动)

返回码:
  0  替换成功(可能替换 0 个——README 已最新)
  1  错误(GitHub API 调用失败 / 解析失败)
"""
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


def detect_repo() -> str:
    """从 git remote origin 推断 owner/repo"""
    try:
        out = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
        # 处理 ssh (git@github.com:owner/repo.git) 和 https (https://github.com/owner/repo.git) 两种
        m = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", out)
        if m:
            return m.group(1)
    except Exception:
        pass
    return os.environ.get("GH_REPO", "")


def main() -> int:
    repo = sys.argv[1] if len(sys.argv) > 1 else detect_repo()
    if not repo or "/" not in repo:
        print(f"ERROR: 未能推断 owner/repo(可作为参数传入):{repo!r}", file=sys.stderr)
        return 1

    owner, _, name = repo.partition("/")
    readme_path = Path(
        sys.argv[2] if len(sys.argv) > 2 else os.environ.get("README_PATH", "README.md")
    )
    if not readme_path.is_file():
        print(f"ERROR: README 不存在:{readme_path}", file=sys.stderr)
        return 1

    # 拉最新 release 的 assets
    api = f"https://api.github.com/repos/{owner}/{name}/releases/latest"
    try:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
        req = urllib.request.Request(
            api,
            headers={"Authorization": f"token {token}"} if token else {},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"ERROR: GitHub API 返回 {e.code}:{e.reason}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: GitHub API 调用失败:{e}", file=sys.stderr)
        return 1

    # 解析 zip 文件名 → skill 名映射
    url_map: dict[str, str] = {}
    for a in data.get("assets", []):
        asset_name = a.get("name", "")
        if not asset_name.endswith(".zip"):
            continue
        base = asset_name[:-4]
        skill = base.rsplit("-", 1)[0]
        url_map[skill] = a["browser_download_url"]
    print(f"latest release assets:{len(url_map)} 个")

    # 替换 README 占位
    readme = readme_path.read_text()
    pattern = re.compile(
        r"https://github\.com/" + re.escape(f"{owner}/{name}") +
        r"/releases/latest/download/([a-z0-9.\-]+)\.zip"
    )

    replaced = 0
    unmatched: list[str] = []

    def repl(m: re.Match) -> str:
        nonlocal replaced
        full = m.group(1)
        skill = full.rsplit("-", 1)[0]
        if skill in url_map:
            replaced += 1
            return url_map[skill]
        unmatched.append(full)
        return m.group(0)

    new = pattern.sub(repl, readme)

    if replaced > 0:
        readme_path.write_text(new)
        print(f"README 已更新 {replaced} 个下载链接")
    else:
        print("README 无可替换链接(可能已最新或没占位)")

    if unmatched:
        print(f"未匹配 skill({len(unmatched)}):{unmatched[:5]}", file=sys.stderr)
        # 不返回错误——README 可能本来就不含这些 skill

    return 0


if __name__ == "__main__":
    sys.exit(main())