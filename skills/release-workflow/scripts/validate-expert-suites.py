#!/usr/bin/env python3
"""Validate expert-suite directories without introducing a suite manifest."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


SUITE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
VERSION_RE = re.compile(r"^##\s+\[?v?(\d+\.\d+\.\d+)\]?", re.MULTILINE)
SKILL_NAME_RE = re.compile(r"^name:\s*[\"']?([^\"'\s]+)", re.MULTILINE)
SOURCE_LINK_RE = re.compile(
    r"\[([a-z0-9]+(?:-[a-z0-9]+)*)\]"
    r"\(\.\./\.\./skills/\1/\)"
)
RELEASE_BASE_RE = (
    r"https://github\.com/cat-xierluo/legal-skills/releases/"
    r"(?:latest/download|download/[^/\s]+)"
)


@dataclass(frozen=True)
class SuiteSummary:
    suite_id: str
    version: str
    members: tuple[str, ...]


class ValidationError(Exception):
    """A user-actionable expert-suite contract violation."""


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValidationError(f"无法读取 {path}: {exc}") from exc


def _version_from_changelog(path: Path) -> str:
    match = VERSION_RE.search(_read(path))
    if not match:
        raise ValidationError(f"{path} 缺少可解析的首个 SemVer 版本标题")
    return match.group(1)


def _frontmatter_name(path: Path) -> str:
    text = _read(path)
    if not text.startswith("---\n"):
        raise ValidationError(f"{path} 缺少 frontmatter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValidationError(f"{path} frontmatter 未闭合")
    match = SKILL_NAME_RE.search(text[4:end])
    if not match:
        raise ValidationError(f"{path} frontmatter 缺少 name")
    return match.group(1)


def _has_release_asset(text: str, asset_name: str) -> bool:
    return bool(re.search(rf"{RELEASE_BASE_RE}/{re.escape(asset_name)}", text))


def _tracked(repo_root: Path, path: Path) -> bool:
    relative = path.relative_to(repo_root)
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative.as_posix()],
        cwd=repo_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _members_from_readme(readme: Path) -> tuple[str, ...]:
    text = _read(readme)
    marker = "## 包含的 Skills"
    start = text.find(marker)
    if start == -1:
        raise ValidationError(f"{readme} 缺少“{marker}”章节")
    section = text[start + len(marker) :]
    next_heading = re.search(r"^##\s+", section, re.MULTILINE)
    if next_heading:
        section = section[: next_heading.start()]
    members = tuple(SOURCE_LINK_RE.findall(section))
    if not members:
        raise ValidationError(f"{readme} 的成员表没有标准 Skill 源码链接")
    duplicates = sorted({item for item in members if members.count(item) > 1})
    if duplicates:
        raise ValidationError(f"{readme} 的成员表存在重复项: {', '.join(duplicates)}")
    return members


def validate_suite(
    repo_root: Path,
    suite_dir: Path,
    *,
    check_git: bool = True,
) -> SuiteSummary:
    suite_id = suite_dir.name
    if not SUITE_ID_RE.fullmatch(suite_id):
        raise ValidationError(f"非法套件目录名: {suite_id}")

    required_files = ("README.md", "CHANGELOG.md", "LICENSE.txt")
    for name in required_files:
        path = suite_dir / name
        if not path.is_file() or path.is_symlink():
            raise ValidationError(f"{suite_id} 缺少真实文件 {name}")

    members_dir = suite_dir / "skills"
    if not members_dir.is_dir() or members_dir.is_symlink():
        raise ValidationError(f"{suite_id} 缺少真实目录 skills/")

    version = _version_from_changelog(suite_dir / "CHANGELOG.md")
    readme = suite_dir / "README.md"
    readme_text = _read(readme)
    expected_suite_asset = f"suite-{suite_id}-{version}.zip"
    if not _has_release_asset(readme_text, expected_suite_asset):
        raise ValidationError(
            f"{readme} 缺少与 CHANGELOG 对齐的整套下载链接 {expected_suite_asset}"
        )

    link_members: list[str] = []
    for child in sorted(members_dir.iterdir(), key=lambda path: path.name):
        if not child.is_symlink():
            raise ValidationError(f"{suite_id}/skills/{child.name} 必须是符号链接")
        skill_id = child.name
        if not SUITE_ID_RE.fullmatch(skill_id):
            raise ValidationError(f"{suite_id} 含非法 Skill 链接名: {skill_id}")
        expected_link = f"../../../skills/{skill_id}"
        actual_link = child.readlink().as_posix()
        if actual_link != expected_link:
            raise ValidationError(
                f"{suite_id}/skills/{skill_id} 应指向 {expected_link}，实际为 {actual_link}"
            )

        target = child.resolve(strict=False)
        expected_target = repo_root / "skills" / skill_id
        if target != expected_target.resolve(strict=False):
            raise ValidationError(f"{suite_id}/skills/{skill_id} 发生目录逃逸")
        if not expected_target.is_dir() or expected_target.is_symlink():
            raise ValidationError(f"目标 Skill 不存在或不是公开真实目录: skills/{skill_id}")

        for required in ("SKILL.md", "CHANGELOG.md", "LICENSE.txt"):
            target_file = expected_target / required
            if not target_file.is_file():
                raise ValidationError(f"skills/{skill_id} 缺少 {required}")
            if check_git and not _tracked(repo_root, target_file):
                raise ValidationError(f"skills/{skill_id}/{required} 未被 Git 跟踪")

        declared_name = _frontmatter_name(expected_target / "SKILL.md")
        if declared_name != skill_id:
            raise ValidationError(
                f"skills/{skill_id}/SKILL.md 声明 name={declared_name}，与目录名不一致"
            )
        if check_git and not _tracked(repo_root, child):
            raise ValidationError(f"{suite_id}/skills/{skill_id} 符号链接未被 Git 跟踪")
        link_members.append(skill_id)

    if not link_members:
        raise ValidationError(f"{suite_id} 至少需要一个成员 Skill")

    readme_members = _members_from_readme(readme)
    if set(readme_members) != set(link_members):
        missing = sorted(set(link_members) - set(readme_members))
        extra = sorted(set(readme_members) - set(link_members))
        raise ValidationError(
            f"{suite_id} README 与符号链接不一致；"
            f"README 缺少={missing or '无'}，README 多写={extra or '无'}"
        )

    for skill_id in link_members:
        member_version = _version_from_changelog(
            repo_root / "skills" / skill_id / "CHANGELOG.md"
        )
        expected_asset = f"{skill_id}-{member_version}.zip"
        if not _has_release_asset(readme_text, expected_asset):
            raise ValidationError(
                f"{readme} 缺少 {skill_id} 当前版本的单独下载链接 {expected_asset}"
            )

    return SuiteSummary(suite_id, version, tuple(sorted(link_members)))


def validate_repository(
    repo_root: Path,
    suite_root: Path | None = None,
    *,
    check_git: bool = True,
) -> list[SuiteSummary]:
    repo_root = repo_root.resolve()
    suite_root = (suite_root or repo_root / "expert-suites").resolve()
    if not suite_root.is_dir():
        raise ValidationError(f"专家套件根目录不存在: {suite_root}")
    suite_dirs = sorted(
        (path for path in suite_root.iterdir() if path.is_dir()),
        key=lambda path: path.name,
    )
    if not suite_dirs:
        raise ValidationError(f"专家套件根目录为空: {suite_root}")
    return [
        validate_suite(repo_root, suite_dir, check_git=check_git)
        for suite_dir in suite_dirs
    ]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path(__file__).resolve().parents[3]
    parser.add_argument("--repo-root", type=Path, default=default_root)
    parser.add_argument("--suite-root", type=Path)
    parser.add_argument(
        "--skip-git-check",
        action="store_true",
        help="仅供隔离 fixture 测试；正式校验不得使用",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        summaries = validate_repository(
            args.repo_root,
            args.suite_root,
            check_git=not args.skip_git_check,
        )
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    total_members = sum(len(item.members) for item in summaries)
    unique_members = len({member for item in summaries for member in item.members})
    for item in summaries:
        print(
            f"OK {item.suite_id} v{item.version}: "
            f"{len(item.members)} members ({', '.join(item.members)})"
        )
    print(
        f"PASS: {len(summaries)} suites, {total_members} memberships, "
        f"{unique_members} unique skills"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
