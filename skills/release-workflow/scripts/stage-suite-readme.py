#!/usr/bin/env python3
"""Render release URLs only inside staging, checking the local release assets."""
from pathlib import Path
import argparse
import re
import zipfile


VERSION = re.compile(r"^##\s+\[?v?(\d+\.\d+\.\d+)\]?", re.M)
BASE = "https://github.com/cat-xierluo/legal-skills/releases/"


def version(path):
    match = VERSION.search(path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"Missing version: {path}")
    return match[1]


def render(suite, tag, assets):
    if not re.fullmatch(r"[A-Za-z0-9._-]+", tag):
        raise ValueError("Invalid release tag")
    if suite.is_symlink() or any(p.is_symlink() for p in suite.rglob("*")):
        raise ValueError("Staging must contain real files, not source member symlinks")
    text = (suite / "README.md").read_text(encoding="utf-8")
    headings = list(re.finditer(r"^## 包含的 Skills[ \t]*$", text, re.M))
    if len(headings) != 1:
        raise ValueError("Expected exactly one member section")
    start = headings[0].end()
    following = re.search(r"^##\s+", text[start:], re.M)
    end = start + following.start() if following else len(text)
    prefix, member_text, suffix = text[:start], text[start:end], text[end:]
    suite_asset = f"suite-{suite.name}-{version(suite / 'CHANGELOG.md')}.zip"
    # These links are prospective release contents, never source-tree claims.
    prefix = re.sub(re.escape(BASE) + r"(?:latest/download|download/[^/\s]+)/suite-" + re.escape(suite.name) + r"-\d+\.\d+\.\d+\.zip(?:[?#][^\s)]+)?", BASE + f"download/{tag}/{suite_asset}", prefix)
    prefix = re.sub(r"整套源码 v\d+\.\d+\.\d+ 待首次发布（尚无公开下载）", f"[本次发布整套下载]({BASE}download/{tag}/{suite_asset})", prefix)
    prefix = re.sub(r"(?m)^> 整套源码 v\d+\.\d+\.\d+ 待发布\n?", "", prefix)
    for member in sorted((suite / "skills").iterdir()):
        current = version(member / "CHANGELOG.md")
        asset = f"{member.name}-{current}.zip"
        path = assets / asset
        if not path.is_file():
            raise ValueError(f"Missing current release asset: {asset}")
        with zipfile.ZipFile(path) as archive:
            if any((info.external_attr >> 16) & 0o170000 == 0o120000 for info in archive.infolist()):
                raise ValueError(f"Release asset contains a symlink: {asset}")
            names = [info.filename for info in archive.infolist() if not info.is_dir()]
            expected = {f"{member.name}/{p.relative_to(member).as_posix()}": p
                        for p in member.rglob("*") if p.is_file()}
            if len(names) != len(set(names)) or set(names) != set(expected):
                raise ValueError(f"Asset membership does not match staged candidate: {asset}")
            for name, source in expected.items():
                if archive.read(name) != source.read_bytes():
                    raise ValueError(f"Asset content does not match staged candidate: {asset}/{name}")
        lines = member_text.splitlines()
        for index, line in enumerate(lines):
            if f"[{member.name}](../../skills/{member.name}/)" not in line:
                continue
            cells = line.split("|")
            cells[2] = re.sub(r"；\s*源码 v\d+\.\d+\.\d+ 待发布", "", cells[2])
            cells[3] = f" [本次发布 v{current}]({BASE}download/{tag}/{asset}) "
            lines[index] = "|".join(cells)
        member_text = "\n".join(lines) + "\n"
    (suite / "README.md").write_text(prefix + member_text + suffix, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--assets", required=True, type=Path)
    args = parser.parse_args()
    render(args.suite, args.tag, args.assets)
