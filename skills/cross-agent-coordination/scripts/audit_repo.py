#!/usr/bin/env python3
"""Audit task metadata in a cross-agent-coordination project."""

from __future__ import annotations

import argparse
from pathlib import Path

from collab_lib import iter_task_dirs, load_config, load_task_type_registry, parse_frontmatter, parse_slug


def audit_task(task_dir, registry):
    issues = []
    parsed = parse_slug(task_dir.name)
    readme = task_dir / "README.md"
    fm = parse_frontmatter(readme)

    if not parsed:
        issues.append("目录名不符合 {YYMMDDNNN}-{type}-{title}")
        parsed = {}

    folder_id = parsed.get("id", "")
    folder_type = parsed.get("type", "")
    fm_id = str(fm.get("id", ""))
    fm_slug = str(fm.get("slug", ""))
    fm_type = str(fm.get("type", ""))

    if not readme.exists():
        issues.append("缺少 README.md")
    elif not fm:
        issues.append("README 缺少 frontmatter")

    if folder_id and fm_id and folder_id != fm_id:
        issues.append(f"id 不一致: 目录={folder_id}, frontmatter={fm_id}")
    elif folder_id and not fm_id:
        issues.append("frontmatter 缺少 id")

    if fm_slug and fm_slug != task_dir.name:
        issues.append(f"slug 不一致: 目录={task_dir.name}, frontmatter={fm_slug}")
    elif not fm_slug:
        issues.append("frontmatter 缺少 slug")

    if folder_type:
        try:
            normalized_folder_type = registry.normalize(folder_type)
        except SystemExit:
            normalized_folder_type = folder_type
            issues.append(f"目录分类不在任务类型注册表中: {folder_type}")
    else:
        normalized_folder_type = ""

    if fm_type:
        try:
            normalized_fm_type = registry.normalize(fm_type)
        except SystemExit:
            normalized_fm_type = fm_type
            issues.append(f"frontmatter type 不在任务类型注册表中: {fm_type}")
        if normalized_folder_type and normalized_fm_type != normalized_folder_type:
            issues.append(f"type 不一致: 目录={folder_type}, frontmatter={fm_type}")
    elif folder_type:
        issues.append("frontmatter 缺少 type")

    if "assignee" not in fm:
        issues.append("frontmatter 缺少 assignee")
    if "dependencies" not in fm:
        issues.append("frontmatter 缺少 dependencies")
    if "artifact_paths" not in fm:
        issues.append("frontmatter 缺少 artifact_paths")

    return {
        "path": str(task_dir),
        "id": folder_id or fm_id or "-",
        "folder_type": folder_type or "-",
        "frontmatter_type": fm_type or "-",
        "issues": issues,
    }


def render_markdown(results, show_ok=False):
    filtered = [item for item in results if item["issues"] or show_ok]
    lines = [
        "# Cross-Agent-Coordination 元数据审计",
        "",
        f"- 扫描任务数: {len(results)}",
        f"- 发现问题任务数: {sum(1 for item in results if item['issues'])}",
        "",
        "| Task | ID | 目录分类 | Frontmatter Type | Issues |",
        "|---|---:|---|---|---|",
    ]
    if not filtered:
        lines.append("| - | - | - | - | 未发现问题 |")
    for item in filtered:
        issues = "<br>".join(item["issues"]) if item["issues"] else "OK"
        lines.append(
            f"| `{item['path']}` | `{item['id']}` | `{item['folder_type']}` | "
            f"`{item['frontmatter_type']}` | {issues} |"
        )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="cross-agent-coordination project root")
    parser.add_argument("--show-ok", action="store_true", help="include tasks with no issues")
    args = parser.parse_args()

    root = Path(args.root).expanduser()
    config = load_config(root)
    registry = load_task_type_registry(root, config)
    results = [audit_task(task_dir, registry) for task_dir in iter_task_dirs(root)]
    print(render_markdown(results, show_ok=args.show_ok))


if __name__ == "__main__":
    main()
