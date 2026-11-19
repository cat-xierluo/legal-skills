#!/usr/bin/env python3
"""对 legal-material-organizer 发布候选执行确定性静态检查。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


ALLOWED_ARCHIVE_FILES = {".gitignore", ".gitkeep"}
BANNED_DIRECTORIES = {"docs", "evals", "__pycache__"}
BANNED_FILENAMES = {".DS_Store"}
PRIVATE_PATH_PATTERNS = (
    re.compile("/" + r"Users/[^/\s]+/"),
    re.compile("/" + r"home/[^/\s]+/"),
    re.compile(r"[A-Za-z]:\\" + r"Users\\[^\\\s]+\\"),
    re.compile("~/" + "Documents/"),
)
PRIVACY_PATTERNS = (
    ("PRIVACY_EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("PRIVACY_PHONE", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("PRIVACY_LANDLINE", re.compile(r"(?<!\d)0\d{2,3}-?\d{7,8}(?!\d)")),
    ("PRIVACY_ID_NUMBER", re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)")),
    ("PRIVACY_LEGACY_ID_NUMBER", re.compile(r"(?<!\d)\d{15}(?!\d)")),
    ("PRIVACY_CASE_NUMBER", re.compile(r"[（(]20\d{2}[）)][\u4e00-\u9fa5A-Za-z0-9]+第?\d+号")),
    ("PRIVACY_WECHAT_ID", re.compile(r"\bwxid_\w+")),
    ("PRIVACY_QQ_ACCOUNT", re.compile(r"\b(?:QQ|qq)[:：]\s?\d{5,11}\b")),
    (
        "PRIVACY_ORGANIZATION",
        re.compile(r"[\u4e00-\u9fa5A-Za-z0-9（）()]{2,24}(?:有限公司|股份有限公司|律师事务所|事务所|研究院|大学|学院)"),
    ),
    (
        "PRIVACY_COURT_OR_AUTHORITY",
        re.compile(r"[\u4e00-\u9fa5]{2,12}(?:人民法院|中级人民法院|人民检察院|公证处|仲裁委员会|监督管理局|税务局|公安局|派出所)"),
    ),
    ("PRIVACY_INTERNAL_ID", re.compile(r"\b(?:DEC|TASK|CASE|RUN|SUITE|PR|ISSUE)-\d+\b")),
)
PRIVACY_SKIPPED_FILES = {"TASKS.md", "DECISIONS.md", "LICENSE.txt"}
PRIVACY_SKIPPED_RELATIVE_PATHS = {
    Path("scripts") / "validate_release.py",
    Path("scripts") / "test_validate_release.py",
}
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _read_frontmatter(skill_path: Path) -> dict[str, object]:
    lines = skill_path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}
    values: dict[str, object] = {}
    current_mapping: dict[str, str] | None = None
    for line in lines[1:end]:
        child_match = re.match(r"^\s{2}([a-zA-Z0-9_-]+):\s*(.*)$", line)
        if child_match and current_mapping is not None:
            current_mapping[child_match.group(1)] = child_match.group(2).strip().strip('"\'')
            continue
        match = re.match(r"^([a-zA-Z0-9_-]+):\s*(.*)$", line)
        if match:
            key = match.group(1)
            value = match.group(2).strip().strip('"\'')
            if value:
                values[key] = value
                current_mapping = None
            else:
                current_mapping = {}
                values[key] = current_mapping
    return values


def _iter_public_text_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or "archive" in path.relative_to(root).parts:
            continue
        if path.suffix.lower() in {
            ".md", ".py", ".json", ".yaml", ".yml", ".txt", ".url",
            ".csv", ".html", ".htm", ".js", ".ts", ".css", ".sh",
            ".ini", ".cfg", ".toml", ".xml",
        }:
            yield path


def _is_git_ignored(root: Path, path: Path) -> bool:
    """仅把 Git 明确忽略的系统文件视为不会进入仓库发布物。"""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "--quiet", "--", str(path)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    return result.returncode == 0


def _privacy_text(path: Path) -> str:
    """发布元数据豁免：作者与许可联系方式不进入内容隐私扫描。"""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if path.name == "SKILL.md" and lines and lines[0].strip() == "---":
        try:
            end = lines.index("---", 1)
        except ValueError:
            return "\n".join(lines)
        return "\n".join(lines[end + 1 :])
    return "\n".join(lines)


def validate_candidate(root: Path) -> list[dict[str, str]]:
    root = root.resolve()
    findings: list[dict[str, str]] = []

    def add(rule: str, path: Path, message: str) -> None:
        findings.append({"rule": rule, "path": str(path.relative_to(root)), "message": message})

    for required in (
        "SKILL.md",
        "CHANGELOG.md",
        "LICENSE.txt",
        "config/instruction-stability-contract.json",
    ):
        path = root / required
        if not path.is_file():
            add("REQUIRED_FILE", path, "缺少项目要求的技能级文件")

    for path in root.rglob("*"):
        relative_parts = path.relative_to(root).parts
        if path.is_dir() and path.name in BANNED_DIRECTORIES:
            add("BANNED_DIRECTORY", path, "发布候选不应包含开发计划、评测材料或缓存目录")
        if path.is_file() and path.name in BANNED_FILENAMES and not _is_git_ignored(root, path):
            add("BANNED_FILE", path, "发布候选不应包含系统缓存文件")
        if "archive" in relative_parts and path.is_file() and path.name not in ALLOWED_ARCHIVE_FILES:
            add("ARCHIVE_PAYLOAD", path, "Skill 内 archive 只能保留 .gitignore 与 .gitkeep")

    skill_path = root / "SKILL.md"
    if skill_path.is_file():
        frontmatter = _read_frontmatter(skill_path)
        if frontmatter.get("name") != root.name:
            add("FRONTMATTER_NAME", skill_path, "frontmatter name 必须与目录名一致")
        metadata = frontmatter.get("metadata")
        skill_version = metadata.get("version") if isinstance(metadata, dict) else None
        changelog_path = root / "CHANGELOG.md"
        changelog_version = None
        if changelog_path.is_file():
            match = re.search(r"^## \[([^\]]+)\] - \d{4}-\d{2}-\d{2}", changelog_path.read_text(encoding="utf-8"), re.MULTILINE)
            changelog_version = match.group(1) if match else None
        if not skill_version or skill_version != changelog_version:
            add("VERSION_SYNC", skill_path, "frontmatter metadata.version 必须与 CHANGELOG 最新版本一致")
        if frontmatter.get("license") != "CC-BY-NC":
            add("LICENSE_ID", skill_path, "法律专业应用 Skill 的 license 必须为 CC-BY-NC")
        if len(skill_path.read_text(encoding="utf-8").splitlines()) > 500:
            add("SKILL_LENGTH", skill_path, "SKILL.md 不得超过 500 行")

    license_path = root / "LICENSE.txt"
    if license_path.is_file():
        license_text = license_path.read_text(encoding="utf-8")
        for required_text in (
            "Creative Commons Attribution-NonCommercial 4.0 International",
            "Copyright (c) 2025 杨卫薪律师（微信ywxlaw）",
            "Email: secretxierluo@gmail.com",
            "WeChat: ywxlaw (微信)",
        ):
            if required_text not in license_text:
                add("LICENSE_TEXT", license_path, f"许可证缺少规定文本: {required_text}")

    for path in _iter_public_text_files(root):
        if path.name in PRIVACY_SKIPPED_FILES or path.relative_to(root) in PRIVACY_SKIPPED_RELATIVE_PATHS:
            continue
        text = _privacy_text(path)
        for pattern in PRIVATE_PATH_PATTERNS:
            if pattern.search(text):
                add("PRIVATE_PATH", path, "公开文件包含本机绝对路径或个人目录")
                break
        for rule, pattern in PRIVACY_PATTERNS:
            if pattern.search(text):
                add(rule, path, "公开文件疑似包含未登记的个人、机构或内部记录锚点")
        if path.suffix.lower() == ".md":
            for raw_target in MARKDOWN_LINK_RE.findall(text):
                target = raw_target.split("#", 1)[0].strip().strip("<>")
                if not target or "://" in target or target.startswith(("#", "mailto:")):
                    continue
                if not (path.parent / target).resolve().exists():
                    add("BROKEN_LINK", path, f"引用不可达: {raw_target}")

    scan_path = root / "scripts" / "scan_materials.py"
    if scan_path.is_file():
        scan_text = scan_path.read_text(encoding="utf-8")
        if 'SKILL_DIR / "archive"' in scan_text or 'self.archive_dir / "processed"' in scan_text:
            add("SKILL_ARCHIVE_WRITE", scan_path, "运行时真实材料不得写入 Skill archive")

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 legal-material-organizer 是否满足发布静态门槛")
    parser.add_argument("candidate", nargs="?", default=str(Path(__file__).resolve().parent.parent))
    args = parser.parse_args()
    root = Path(args.candidate)
    findings = validate_candidate(root)
    result = {
        "candidate": str(root.resolve()),
        "status": "PASS" if not findings else "FAIL",
        "finding_count": len(findings),
        "findings": findings,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
