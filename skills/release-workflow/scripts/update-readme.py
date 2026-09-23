#!/usr/bin/env python3
"""Refresh root and expert-suite README download URLs from release assets.

Usage:
  python3 update-readme.py [<owner>/<repo>] [README ...]
  python3 update-readme.py --assets-json fixture.json <owner>/<repo> [README ...]

When no README path is supplied, the script updates README.md and every
expert-suites/*/README.md. Only links that point to the selected repository
are eligible; independent-repository download links are left untouched.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ASSET_RE = re.compile(r"^(.+)-(\d+\.\d+\.\d+)\.zip$")


def detect_repo() -> str:
    """Infer owner/repo from git remote origin."""
    try:
        out = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        match = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", out)
        if match:
            return match.group(1)
    except (OSError, subprocess.SubprocessError):
        pass
    return os.environ.get("GH_REPO", "")


def fetch_release(repo: str) -> dict[str, object]:
    owner, name = repo.split("/", 1)
    api = f"https://api.github.com/repos/{owner}/{name}/releases/latest"
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    request = urllib.request.Request(
        api,
        headers={"Authorization": f"token {token}"} if token else {},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def asset_url_map(release: dict[str, object]) -> dict[str, str]:
    """Map '<slug>-<semver>.zip' assets to slug, including suite-* assets."""
    result: dict[str, str] = {}
    assets = release.get("assets", [])
    if not isinstance(assets, list):
        raise ValueError("release assets 不是列表")
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = asset.get("name")
        url = asset.get("browser_download_url")
        if not isinstance(name, str) or not isinstance(url, str):
            continue
        match = ASSET_RE.fullmatch(name)
        if match:
            result[match.group(1)] = url
    return result


def discover_readmes(root: Path) -> list[Path]:
    readmes = [root / "README.md"]
    suite_root = root / "expert-suites"
    if suite_root.is_dir():
        readmes.extend(sorted(suite_root.glob("*/README.md")))
    return readmes


def rewrite_readme(path: Path, repo: str, url_map: dict[str, str]) -> dict[str, object]:
    """刷新一个 README:下载链接按「行内声明的技能名」重映射,版本列同步对齐。

    三层处理,彼此幂等:
    1. 根 README 的 HTML 表行(<tr> 块):按行内 href="skills/<name>/" 的技能名
       重映射下载链接(根治改名残留死链——链接里的旧 slug 不再决定去向),
       并把紧邻下载 td 的版本列对齐到 zip 实际版本(含 vA.B.C→vX.Y.Z 区间写法)。
       行内没有指向本仓库的链接时(如独立仓库下载行)整行不动。
    2. 套件 README 的 Markdown 表行:按行内 ](../skills/<name>/) 成员名重映射链接。
    3. 表行之外的散链(正文引用、blockquote 整套链接):按链接自身 slug 映射。

    返回 {"links": 变更链接数, "versions": 对齐版本列数, "unmatched": [...]},
    仅当内容变化时写回。
    """
    text = path.read_text(encoding="utf-8")
    stats: dict[str, object] = {"links": 0, "versions": 0, "unmatched": []}
    repo_link = re.compile(
        r"https://github\.com/"
        + re.escape(repo)
        + r"/releases/(?:latest/download|download/[^/\s]+)/([A-Za-z0-9.\-]+\.zip)"
    )

    def _rewrite_html_row(row_match: re.Match[str]) -> str:
        tr = row_match.group(0)
        name_match = re.search(r'href="skills/([a-z0-9-]+)/"', tr)
        if not name_match:
            return tr
        name = name_match.group(1)
        target = url_map.get(name)
        links = repo_link.findall(tr)
        if not links:
            return tr  # 独立仓库下载行或无下载链接:整行不动
        if target is None:
            stats["unmatched"].append(f"{name}(行)")
            return tr

        changed = 0

        def swap(match: re.Match[str]) -> str:
            nonlocal changed
            if match.group(0) != target:
                changed += 1
            return target

        new_tr = repo_link.sub(swap, tr)

        # 版本列对齐:锚定「版本 td + 本仓库下载 td」结构。链接可能已是最新
        # (幂等重跑或链接先于版本列被修过),版本列仍需独立检查对齐
        target_ver = ASSET_RE.fullmatch(target.rsplit("/", 1)[-1])
        if target_ver:
            version_cell = re.compile(
                r"(<td[^>]*>)v[\d.]+[^<]*(</td>\s*<td[^>]*><a href=\""
                + re.escape(target)
                + r"\")"
            )
            new_tr, hits = version_cell.subn(
                rf"\g<1>v{target_ver.group(2)}\g<2>", new_tr, count=1
            )
            stats["versions"] = int(stats["versions"]) + hits
        if new_tr == tr:
            return tr
        stats["links"] = int(stats["links"]) + changed
        return new_tr

    def _rewrite_md_row(line_match: re.Match[str]) -> str:
        line = line_match.group(0)
        member = re.search(r"\]\([^)]*?/skills/([a-z0-9-]+)/\)", line)
        if not member:
            return line
        target = url_map.get(member.group(1))
        if not target or not repo_link.search(line):
            return line
        changed = 0

        def swap(match: re.Match[str]) -> str:
            nonlocal changed
            if match.group(0) != target:
                changed += 1
            return target

        new_line = repo_link.sub(swap, line)
        stats["links"] = int(stats["links"]) + changed
        return new_line

    text = re.sub(r"<tr>.*?</tr>", _rewrite_html_row, text, flags=re.DOTALL)
    text = re.sub(r"^\|.*\|$", _rewrite_md_row, text, flags=re.MULTILINE)

    # 表行之外的散链:按链接自身 slug 映射
    def _replace_loose(match: re.Match[str]) -> str:
        parsed = ASSET_RE.fullmatch(match.group(1))
        if not parsed:
            stats["unmatched"].append(match.group(1))
            return match.group(0)
        target = url_map.get(parsed.group(1))
        if target is None:
            stats["unmatched"].append(match.group(1))
            return match.group(0)
        if target != match.group(0):
            stats["links"] = int(stats["links"]) + 1
            return target
        return match.group(0)

    text = repo_link.sub(_replace_loose, text)

    original = path.read_text(encoding="utf-8")
    if text != original:
        path.write_text(text, encoding="utf-8")
    return stats


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--assets-json",
        type=Path,
        help="从本地 GitHub release JSON 读取 assets，供离线测试或复验",
    )
    parser.add_argument("repo", nargs="?", help="owner/repo；默认从 origin 推断")
    parser.add_argument("readmes", nargs="*", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo = args.repo or detect_repo()
    if not repo or repo.count("/") != 1:
        print(f"ERROR: 未能推断 owner/repo（可作为参数传入）: {repo!r}", file=sys.stderr)
        return 1

    try:
        if args.assets_json:
            release = json.loads(args.assets_json.read_text(encoding="utf-8"))
        else:
            release = fetch_release(repo)
        urls = asset_url_map(release)
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
        print(f"ERROR: 获取或解析 GitHub Release 失败: {exc}", file=sys.stderr)
        return 1

    if not urls:
        print("ERROR: 最新 Release 没有可识别的 SemVer ZIP 资产", file=sys.stderr)
        return 1
    print(f"latest release assets: {len(urls)} 个")

    readmes = args.readmes or discover_readmes(Path.cwd())
    missing = [path for path in readmes if not path.is_file()]
    if missing:
        print(f"ERROR: README 不存在: {', '.join(map(str, missing))}", file=sys.stderr)
        return 1

    total = 0
    total_versions = 0
    all_unmatched: list[str] = []
    for readme in readmes:
        stats = rewrite_readme(readme, repo, urls)
        total += int(stats["links"])
        total_versions += int(stats["versions"])
        all_unmatched.extend(stats["unmatched"])  # type: ignore[arg-type]
        print(
            f"{readme}: 更新 {stats['links']} 个下载链接, "
            f"对齐 {stats['versions']} 个版本列"
        )

    if all_unmatched:
        unique = sorted(set(all_unmatched))
        print(f"未匹配资产 ({len(unique)}): {unique[:10]}", file=sys.stderr)
    print(
        f"完成: {len(readmes)} 个 README，共更新 {total} 个下载链接、"
        f"{total_versions} 个版本列"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
