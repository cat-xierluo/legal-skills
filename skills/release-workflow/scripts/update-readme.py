#!/usr/bin/env python3
"""update-readme.py — 把 README 表格里的下载 URL 统一改写为最新 release 的真实链接

用法:
  python3 update-readme.py [<owner>/<repo>] [<readme_path>]

默认从环境变量读取:
  GH_REPO        — owner/repo(默认从 git remote origin 推断)
  README_PATH    — README 路径(默认 ./README.md)

行为:
  1. 调 GitHub API 拿最新 release 的 assets
  2. 解析每个 <skill>-<semver>.zip 文件名,建立 skill 名 → 真实 browser_download_url 映射
  3. 扫描 README 中指向本仓库的两种下载链接形式,全部改写为最新 release 的真实链接:
     - 占位形式:`.../releases/latest/download/<skill>-<semver>.zip`
     - 显式 tag 形式:`.../releases/download/<任意 tag>/<skill>-<semver>.zip`
     (本项目 README 实际使用显式 tag 形式,因此必须覆盖,否则只会刷新恰好已是新 tag 的链接)
  4. 按文件名解析 <skill>,在最新 release 资产中匹配;匹配成功则改写为该资产真实 URL
     (URL 内含最新 tag,无需后续手动再改)
  5. 不匹配的链接(如该 skill 已不在最新 release 中、或属于其他仓库)保持原样
  6. 不修改其他仓库(owner/repo 不一致)的链接,如独立仓库 trademark-assistant.skill

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

    # 替换 README 中所有指向本仓库的下载链接(占位形式 + 显式 tag 形式)
    readme = readme_path.read_text()
    # 匹配两类 URL,捕获其中的文件名(<skill>-<semver>.zip):
    #   releases/latest/download/<file>.zip
    #   releases/download/<任意 tag>/<file>.zip
    pattern = re.compile(
        r"https://github\.com/" + re.escape(f"{owner}/{name}") +
        r"/releases/(?:latest/|download/[^/\s]+/)([A-Za-z0-9.\-]+\.zip)"
    )

    replaced = 0
    unmatched: list[str] = []

    def repl(m: re.Match) -> str:
        nonlocal replaced
        file_name = m.group(1)
        if not file_name.endswith(".zip"):
            return m.group(0)
        skill = file_name[:-4].rsplit("-", 1)[0]
        if skill in url_map:
            target = url_map[skill]
            # 仅当 URL 实际变化时才计数 + 改写(保证幂等:已最新则不计)
            if target != m.group(0):
                replaced += 1
                return target
            return m.group(0)
        unmatched.append(file_name)
        return m.group(0)

    new = pattern.sub(repl, readme)

    if replaced > 0:
        readme_path.write_text(new)
        print(f"README 已更新 {replaced} 个下载链接")
    else:
        print("README 已是最新(无需更新下载链接)")

    if unmatched:
        print(f"未匹配 skill({len(unmatched)}):{unmatched[:5]}", file=sys.stderr)
        # 不返回错误——README 可能本来就不含这些 skill

    return 0


if __name__ == "__main__":
    sys.exit(main())