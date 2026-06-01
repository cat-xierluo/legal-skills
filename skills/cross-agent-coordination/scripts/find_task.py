#!/usr/bin/env python3
"""Find existing cross-agent-coordination tasks."""

from __future__ import annotations

import argparse
from pathlib import Path

from collab_lib import (
    find_similar_tasks,
    get_current_agent,
    is_available_task,
    load_config,
    load_task_type_registry,
    project_config,
)


def render(matches):
    lines = [
        "# 相似任务检索",
        "",
        "| Score | Source | Slug | ID | Type | Status | Assignee | Title |",
        "|---:|---|---|---:|---|---|---|---|",
    ]
    if not matches:
        lines.append("| - | - | - | - | - | - | - | 未找到相似任务 |")
    for item in matches:
        score = item.get("score")
        score_text = f"{score:.2f}" if isinstance(score, float) else "-"
        lines.append(
            f"| {score_text} | `{item.get('source', '-')}` | `{item['slug']}` | `{item['id']}` | `{item['type']}` | "
            f"`{item['status']}` | `{item.get('assignee', '') or '-'}` | {item['title']} |"
        )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="cross-agent-coordination project root")
    parser.add_argument("--topic", default="", help="topic to search before creating new work")
    parser.add_argument("--type", default="", help="optional task type/category")
    parser.add_argument("--threshold", type=float, default=0.45)
    parser.add_argument("--available", action="store_true", help="only show executable todo tasks")
    parser.add_argument("--agent", default="", help="current agent id for --available filtering")
    args = parser.parse_args()

    root = Path(args.root).expanduser()
    config = load_config(root)
    registry = load_task_type_registry(root, config)
    task_type = registry.normalize(args.type) if args.type else ""
    matches = find_similar_tasks(root, registry, args.topic, task_type, args.threshold, config=config)

    if args.available:
        agent = get_current_agent(config, args.agent)
        claim_policy = str(project_config(config).get("claim_policy", "assigned_only"))
        matches = [
            item
            for item in matches
            if is_available_task(root, item, registry, agent, claim_policy, config)
        ]

    print(render(matches))


if __name__ == "__main__":
    main()
