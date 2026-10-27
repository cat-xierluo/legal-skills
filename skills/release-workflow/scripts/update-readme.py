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
import html
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ASSET_RE = re.compile(r"^(.+)-(\d+\.\d+\.\d+)\.zip$")
VERSION_RE = re.compile(r"^## \[?v?(\d+\.\d+\.\d+)\]?", re.MULTILINE)
PENDING_RE = re.compile(r"源码 v\d+\.\d+\.\d+ 待发布[；;。]?\s*")


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
            slug = match.group(1)
            previous = ASSET_RE.fullmatch(result.get(slug, "").rsplit("/", 1)[-1])
            if not previous or version_tuple(match.group(2)) > version_tuple(previous.group(2)):
                result[slug] = url
    return result


def version_tuple(version: str) -> tuple[int, ...]:
    return tuple(map(int, version.split(".")))


def source_dir(readme: Path, category: str, name: str) -> Path | None:
    """Find source beside the README, including expert-suite member references."""
    for root in readme.resolve().parents:
        directory = root / category / name
        if (directory / "CHANGELOG.md").is_file():
            return directory
    return None


def source_version(directory: Path | None) -> str | None:
    if directory is None:
        return None
    match = VERSION_RE.search((directory / "CHANGELOG.md").read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"CHANGELOG 缺少 SemVer: {directory.name}")
    return match.group(1)


def asset_version(url: str | None) -> str | None:
    match = ASSET_RE.fullmatch((url or "").rsplit("/", 1)[-1])
    return match.group(2) if match else None


def discover_readmes(root: Path) -> list[Path]:
    readmes = [root / "README.md"]
    suite_root = root / "expert-suites"
    if suite_root.is_dir():
        readmes.extend(sorted(suite_root.glob("*/README.md")))
    return readmes


def rewrite_readme(path: Path, repo: str, url_map: dict[str, str]) -> dict[str, object]:
    """Refresh asset links while preserving current source versions and row order.

    Source CHANGELOG wins over ZIP versions. With no local source (a standalone
    README), retain legacy asset-version alignment. Missing assets keep existing
    published links, so a partial hotfix never erases another component's link.
    """
    text = path.read_text(encoding="utf-8")
    stats: dict[str, object] = {"links": 0, "versions": 0, "unmatched": []}
    repo_link = re.compile(
        r"https://github\.com/"
        + re.escape(repo)
        + r"/releases/(?:latest/download|download/[^/\s]+)/([A-Za-z0-9.\-]+\.zip)"
        + r"(?=$|[\s<>\"')])"
    )

    def target_for(slug: str, cell: str) -> str | None:
        old = repo_link.search(cell)
        # An unobserved latest/download URL may only be a future placeholder.
        historical = old.group(0) if old and "/releases/download/" in old.group(0) else None
        if "待发布" in cell or "待首次发布" in cell:
            historical = None
        target = url_map.get(slug)
        if historical and target and version_tuple(asset_version(historical)) > version_tuple(asset_version(target)):
            return historical
        return target or historical

    def download(target: str, markdown: bool = False) -> str:
        label = f"已发布 v{asset_version(target)}"
        return f"[{label}]({target})" if markdown else f'<a href="{html.escape(target, quote=True)}">{label}</a>'

    def pending(body: str, current: str | None, published: str | None) -> str:
        body = PENDING_RE.sub("", body).strip("；; ")
        if current and current != published:
            return f"{body}；源码 v{current} 待发布" if body else f"源码 v{current} 待发布"
        return body

    def _rewrite_html_row(row_match: re.Match[str]) -> str:
        tr = row_match.group(0)
        name_match = re.search(r'href="skills/([a-z0-9-]+)/"', tr)
        if not name_match:
            return tr
        name = name_match.group(1)
        cells = list(re.finditer(r"(<td\b[^>]*>)(.*?)(</td>)", tr, re.DOTALL))
        version_index = next(
            (i for i, cell in enumerate(cells) if re.fullmatch(r"\s*v[\d.]+[^<]*", cell[2])),
            None,
        )
        if version_index is None or version_index + 1 >= len(cells):
            return tr
        download_index = version_index + 1
        old_download = cells[download_index][2]
        if re.search(r"https?://", old_download) and not repo_link.search(old_download):
            return tr  # Independent-repository downloads remain untouched.
        target = target_for(name, old_download)
        current = source_version(source_dir(path, "skills", name))
        if target is None:
            stats["unmatched"].append(f"{name}(尚无公开资产)")
        published = asset_version(target)
        replacements = {download_index: download(target) if target else "尚无公开 ZIP"}
        current = current or published
        if current and cells[version_index][2] != f"v{current}":
            replacements[version_index] = f"v{current}"
            stats["versions"] = int(stats["versions"]) + 1
        if download_index + 1 < len(cells):
            notes = cells[download_index + 1][2]
            if "内容版本待核" in old_download and "内容版本待核" not in notes:
                notes = f"历史 ZIP 内容版本待核；{notes}"
            notes = re.sub(r"下载为已发布 v[\d.]+[；;。]?\s*", "", notes)
            notes = re.sub(r"(?:源码待发布|下载(?:链接)?仍为上一已发布包)[；;。]?\s*", "", notes)
            replacements[download_index + 1] = pending(notes, current, published)
        previous = repo_link.search(old_download)
        if target and (not previous or previous.group(0) != target):
            stats["links"] = int(stats["links"]) + 1
        new_tr = tr
        for index, content in sorted(replacements.items(), reverse=True):
            cell = cells[index]
            new_tr = new_tr[:cell.start(2)] + content + new_tr[cell.end(2):]
        return new_tr

    def _rewrite_md_row(line_match: re.Match[str]) -> str:
        line = line_match.group(0)
        suite = re.search(r"\]\(expert-suites/([a-z0-9-]+)/\)", line)
        if suite:
            name = suite.group(1)
            cells = line.split("|")
            if len(cells) != 7:
                return line
            directory = source_dir(path, "expert-suites", name)
            current = source_version(directory)
            if current:
                if cells[4].strip() != f"v{current}":
                    stats["versions"] = int(stats["versions"]) + 1
                cells[4] = f" v{current} "
            if directory and (directory / "skills").is_dir():
                cells[3] = f" {sum(p.is_symlink() for p in (directory / 'skills').iterdir())} "
            target = target_for(f"suite-{name}", cells[5])
            previous = repo_link.search(cells[5])
            if target and (not previous or previous.group(0) != target):
                stats["links"] = int(stats["links"]) + 1
            cells[5] = f" {download(target, markdown=True)} " if target else " 尚无公开 ZIP "
            return "|".join(cells)
        member = re.search(r"\]\([^)]*?/skills/([a-z0-9-]+)/\)", line)
        if not member:
            return line
        cells = line.split("|")
        if len(cells) != 5:
            return line
        if re.search(r"https?://", cells[3]) and not repo_link.search(cells[3]):
            return line
        name = member.group(1)
        current = source_version(source_dir(path, "skills", name))
        target = target_for(name, cells[3])
        previous = repo_link.search(cells[3])
        if target and (not previous or previous.group(0) != target):
            stats["links"] = int(stats["links"]) + 1
        cells[2] = f" {pending(cells[2].strip(), current, asset_version(target))} "
        cells[3] = f" {download(target, markdown=True)} " if target else " 尚无公开下载 "
        return "|".join(cells)

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
        if version_tuple(parsed.group(2)) > version_tuple(asset_version(target)):
            return match.group(0)
        if target != match.group(0):
            stats["links"] = int(stats["links"]) + 1
            return target
        return match.group(0)

    text = repo_link.sub(_replace_loose, text)

    # Keep suite headers honest when only some assets have been hotfixed.
    if path.parent.parent.name == "expert-suites" and "## 包含的 Skills" in text:
        header, rest = text.split("## 包含的 Skills", 1)
        current = source_version(path.parent)
        own_link = next(
            (m.group(0) for m in repo_link.finditer(header)
             if ASSET_RE.fullmatch(m.group(1)).group(1) == f"suite-{path.parent.name}"),
            None,
        )
        target = target_for(f"suite-{path.parent.name}", own_link or "")
        header = re.sub(r"^> 整套源码 v[\d.]+ 待[^\n]*\n?", "", header, flags=re.MULTILINE)
        published = asset_version(target)
        if not target and own_link:
            header = re.sub(r"^> \[[^\n]+\]\(" + re.escape(own_link) + r"\)[ \t]*\n?", "",
                            header, flags=re.MULTILINE)
        if target:
            line = f"> {download(target, markdown=True)}"
            header = re.sub(
                r"^> \[[^\n]+\]\(" + re.escape(own_link or "") + r"\)[ \t]*$",
                lambda _: line,
                header, flags=re.MULTILINE,
            ) if own_link else re.sub(
                r"^(# [^\n]+\n)\n*", lambda m: m[1] + "\n" + line + "\n\n", header, count=1
            )
        if current != published:
            marker = "待发布" if target else "待首次发布（尚无公开下载）"
            marker = f"> 整套源码 v{current} {marker}"
            if target:
                header = header.replace(line + "\n", line + "\n" + marker + "\n", 1)
            else:
                header = re.sub(
                    r"^(# [^\n]+\n)\n*", lambda m: m[1] + "\n" + marker + "\n\n", header, count=1
                )
        else:
            header = header.replace("> 上方旧包内容不随源码变化。\n", "")
        text = header.rstrip() + "\n\n## 包含的 Skills" + rest

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
