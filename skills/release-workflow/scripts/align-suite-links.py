#!/usr/bin/env python3
"""align-suite-links.py — 把专家套件 README 的成员下载链接对齐到各 Skill 的 CHANGELOG 当前版本

背景:validate-expert-suites.py 按 skills/<name>/CHANGELOG.md 的当前 semver 校验套件
README 的成员下载链接。main 上任何 Skill 升版本(如 legal-ocr 1.5.0→1.6.0)后,
长期 PR merge main 时会把过时的成员链接带进分支,validate 因此拦截(这是设计行为)。
本脚本按 CHANGELOG 当前版本批量改写成员链接,用于 validate 拦截后的一键对齐。

用法:
  python3 align-suite-links.py [--suites-root expert-suites] [--skills-root skills] [--dry-run]

行为:
  - 对每个套件 README,把 releases/(latest/download/|download/<tag>/)<skill>-<semver>.zip
    中的版本号改写为该 skill 的 CHANGELOG 当前 semver
  - 链接版本超前于发布时(新版本尚未打 zip)属预期:latest/download 占位在下次发版后生效
  - --dry-run 只打印将变更的行,不写回

退出码: 0 正常(含无变更); 1 目录缺失
"""
import argparse
import re
import sys
from pathlib import Path


def current_semver(changelog: Path) -> str | None:
    m = re.search(r"## \[?v?([0-9]+\.[0-9]+\.[0-9]+)\]?", changelog.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suites-root", type=Path, default=Path("expert-suites"))
    parser.add_argument("--skills-root", type=Path, default=Path("skills"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.suites_root.is_dir():
        print(f"ERROR: 套件目录不存在: {args.suites_root}", file=sys.stderr)
        return 1

    versions: dict[str, str] = {}
    for d in sorted(args.skills_root.iterdir()):
        changelog = d / "CHANGELOG.md"
        if d.is_dir() and changelog.is_file():
            ver = current_semver(changelog)
            if ver:
                versions[d.name] = ver

    total = 0
    for readme in sorted(args.suites_root.glob("*/README.md")):
        text = readme.read_text(encoding="utf-8")
        new = text
        for skill, ver in versions.items():
            new = re.sub(
                rf"(releases/(?:latest/download/|download/[^/\s]+/)"
                rf"{re.escape(skill)}-)\d+\.\d+\.\d+(\.zip)",
                rf"\g<1>{ver}\g<2>",
                new,
            )
        if new != text:
            changed = sum(
                1 for a, b in zip(text.splitlines(), new.splitlines()) if a != b
            )
            print(f"{'[dry-run] ' if args.dry_run else ''}已对齐 "
                  f"{readme.parent.name}: {changed} 处链接")
            total += changed
            if not args.dry_run:
                readme.write_text(new, encoding="utf-8")

    if total == 0:
        print("套件成员链接均已对齐(无变更)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
