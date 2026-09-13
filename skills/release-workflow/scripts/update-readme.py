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


def rewrite_readme(path: Path, repo: str, url_map: dict[str, str]) -> tuple[int, list[str]]:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"https://github\.com/"
        + re.escape(repo)
        + r"/releases/(?:latest/download|download/[^/\s]+)/([A-Za-z0-9.\-]+\.zip)"
    )
    replaced = 0
    unmatched: list[str] = []

    def replace(match: re.Match[str]) -> str:
        nonlocal replaced
        filename = match.group(1)
        parsed = ASSET_RE.fullmatch(filename)
        if not parsed:
            unmatched.append(filename)
            return match.group(0)
        slug = parsed.group(1)
        target = url_map.get(slug)
        if target is None:
            unmatched.append(filename)
            return match.group(0)
        if target != match.group(0):
            replaced += 1
            return target
        return match.group(0)

    updated = pattern.sub(replace, text)
    if updated != text:
        path.write_text(updated, encoding="utf-8")
    return replaced, unmatched


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
    all_unmatched: list[str] = []
    for readme in readmes:
        replaced, unmatched = rewrite_readme(readme, repo, urls)
        total += replaced
        all_unmatched.extend(unmatched)
        print(f"{readme}: 更新 {replaced} 个下载链接")

    if all_unmatched:
        unique = sorted(set(all_unmatched))
        print(f"未匹配资产 ({len(unique)}): {unique[:10]}", file=sys.stderr)
    print(f"完成: {len(readmes)} 个 README，共更新 {total} 个下载链接")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
