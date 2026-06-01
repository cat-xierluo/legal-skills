#!/usr/bin/env python3
"""Compose email trigger drafts for external agents."""

from __future__ import annotations

import argparse
import re
from email.message import EmailMessage
from pathlib import Path

from collab_lib import (
    find_task_by_ref,
    get_agent_info,
    load_config,
    load_task_type_registry,
    sanitize_slug_part,
)


SECTION_ALIASES = {
    "目标": ["目标", "任务目标", "Objective"],
    "验收标准": ["验收标准", "Acceptance Criteria", "检查清单"],
    "来源材料": ["来源材料", "素材来源", "Sources", "Source Materials"],
    "交接要求": ["交接要求", "交接记录", "Handoff", "Handoff Requirements"],
}


def find_task(root, registry, config, task_id="", slug="", issue=""):
    ref = issue or task_id or slug
    if not ref:
        return {}
    summary = find_task_by_ref(root, registry, ref, config)
    if not summary:
        return {}
    if summary.get("source") == "task_folder":
        readme = Path(summary["path"]) / "README.md"
        summary["readme"] = readme
    return summary


def agent_info(config, agent):
    info = get_agent_info(config, agent)
    return {
        "id": agent,
        "name": info.get("name") or info.get("git_name") or agent,
        "email": info.get("email") or info.get("git_email") or f"{agent}@agents.local",
        "from_alias": info.get("from_alias", ""),
        "github_user": info.get("github_user", ""),
        "token_env": info.get("token_env", ""),
        "trigger_email": info.get("trigger_email", ""),
        "reply_to": info.get("reply_to", ""),
    }


def compose_subject(agent, task, topic):
    marker = f"Issue #{task['id']}" if task and task.get("source") == "issue" else (task["id"] if task else "NEW")
    title = task.get("title") if task else topic
    return f"[Cross-Agent-Coordination][{marker}][{agent['id']}] {title}"


def extract_sections(readme):
    if not readme or not readme.exists():
        return ""
    lines = readme.read_text(encoding="utf-8", errors="ignore").splitlines()
    sections = {}
    current = ""
    buffer = []
    for line in lines:
        heading = re.match(r"^(#{2,4})\s+(.+?)\s*$", line)
        if heading:
            if current:
                sections[current] = buffer
            current = heading.group(2).strip()
            buffer = []
        elif current:
            buffer.append(line)
    if current:
        sections[current] = buffer

    output = []
    for label, names in SECTION_ALIASES.items():
        selected = []
        for name in names:
            if name in sections:
                selected = sections[name]
                break
        cleaned = "\n".join(selected).strip()
        if cleaned:
            output.append(f"### {label}\n\n{cleaned}")
    if not output:
        return ""
    return "## Task Context From README\n\n" + "\n\n".join(output)


def extract_issue_context(task):
    if not task or task.get("source") != "issue":
        return ""
    task_source = task.get("issue_file") or "configured task source"
    output = []
    if task.get("objective"):
        output.append(f"### 目标\n\n{task['objective']}")
    if task.get("source_material"):
        output.append(f"### 来源材料\n\n{task['source_material']}")

    sections = task.get("sections", {})
    preferred = [
        "大纲要点",
        "调研任务",
        "需确定事项",
        "审阅维度",
        "验收标准",
        "触发方式",
        "交接要求",
    ]
    for name in preferred:
        value = sections.get(name, "").strip()
        if value:
            output.append(f"### {name}\n\n{value}")
    if not output:
        return ""
    return f"## Task Context From {task_source}\n\n" + "\n\n".join(output)


def task_source_label(config, task):
    if task and task.get("source") == "issue":
        return task.get("issue_file") or "configured task source"
    project = config.get("project", {})
    if isinstance(project, dict):
        return str(project.get("issue_file") or project.get("task_source_file") or "configured task source")
    return "configured task source"


def compose_body(config, registry, agent, task, topic, task_type, instruction):
    repo_url = config.get("github", {}).get("repo_url", "<repo_url>")
    task_source = task_source_label(config, task)
    if task and task.get("source") == "issue":
        issue_ref = f"Issue #{task['id']}"
        branch_slug = sanitize_slug_part(f"issue-{task['id']}-{task['title']}")
        branch = f"agent/{agent['id']}/{branch_slug}"
        topic = topic or task["title"]
        deps = ", ".join(f"Issue #{dep}" for dep in task.get("dependencies", [])) or "-"
        task_block = f"""## Bound Issue

- Issue: {issue_ref}
- Title: {task['title']}
- Type: {task['type']}
- Status: {task['status']}
- Assignee: {task.get('assignee') or '-'}
- Dependencies: {deps}
- Source: `{task_source}`
"""
        context_block = extract_issue_context(task)
    elif task:
        slug = task["slug"]
        task_id = task["id"]
        branch = f"agent/{agent['id']}/{slug}"
        task_block = f"""## Bound Task

- Task ID: {task_id}
- Slug: {slug}
- Title: {task['title']}
- Type: {task['type']}
- Status: {task['status']}
- Assignee: {task.get('assignee') or '-'}
- README: `{slug}/README.md`
"""
        context_block = extract_sections(task.get("readme"))
    else:
        normalized_type = registry.normalize(task_type) if task_type else "<任务类型>"
        branch = f"agent/{agent['id']}/<task-slug>"
        task_block = f"""## New Task Request

- Topic: {topic}
- Type: {normalized_type}
- First run duplicate search. Create a new task only if no existing workstream matches.
"""
        context_block = ""

    instruction = instruction or "请完成该任务的下一步研究/整理，并提交到协作仓库。"
    context_block = f"\n\n{context_block}" if context_block else ""
    return f"""请作为 {agent['name']} 处理以下 Cross-Agent-Coordination 任务。

## Repository

- Repo: {repo_url}

{task_block}
{context_block}

## Assignment

{instruction}

## Required Workflow

1. Clone or pull the latest repository.
2. Run duplicate search before adding new work:
   `python3 scripts/find_task.py . --topic "{topic}"`
3. If a related task exists, integrate new findings into that task instead of creating a duplicate folder.
4. Use branch:
   `{branch}`
5. Commit as this agent:
   `python3 scripts/gh_git.py commit --dest . --agent {agent['id']} --message "docs: update handoff"`
6. Push and create PR:
   `python3 scripts/gh_git.py push --dest . --agent {agent['id']}`
   `python3 scripts/gh_git.py pr --dest . --agent {agent['id']} --title "docs: {agent['name']} handoff update"`

## Attribution

- Agent ID: {agent['id']}
- Git Author: {agent['name']} <{agent['email']}>
- Expected GitHub Actor: {agent['github_user'] or '取决于实际执行 PR 的账号'}

## Handoff Requirements

- Update the configured task source (`{task_source}`) when this project uses one. If a task folder exists, update its README as handoff context only.
- Add sources reviewed, decisions made, blockers, and next step.
- Open a PR. Do not push directly to `main`.
"""


def write_eml(path, to_addr, subject, body, reply_to="", from_alias=""):
    msg = EmailMessage()
    msg["To"] = to_addr
    if from_alias:
        msg["From"] = from_alias
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Subject"] = subject
    msg.set_content(body)
    Path(path).write_text(msg.as_string(), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="cross-agent-coordination project root")
    parser.add_argument("--agent", required=True, help="target agent id")
    parser.add_argument("--topic", default="", help="task topic or assignment topic")
    parser.add_argument("--type", default="", help="task type/category for new task requests")
    parser.add_argument("--issue", default="", help="bind email to an Issue number in the configured task source")
    parser.add_argument("--task-id", default="", help="bind email to an existing task id")
    parser.add_argument("--slug", default="", help="bind email to an existing task slug")
    parser.add_argument("--to", default="", help="override target email address")
    parser.add_argument("--reply-to", default="", help="override Reply-To address")
    parser.add_argument("--from-alias", default="", help="optional From header for .eml drafts")
    parser.add_argument("--instruction", default="", help="extra assignment instructions")
    parser.add_argument("--output", default="", help="write .eml draft to this path")
    args = parser.parse_args()

    root = Path(args.root).expanduser()
    config = load_config(root)
    registry = load_task_type_registry(root, config)
    agent = agent_info(config, args.agent)
    task = find_task(root, registry, config, args.task_id, args.slug, args.issue)
    to_addr = args.to or agent["trigger_email"]
    if not to_addr:
        raise SystemExit(f"缺少触发邮箱：请在 agents.{args.agent}.trigger_email 中配置，或传入 --to")
    reply_to = args.reply_to or agent["reply_to"]
    from_alias = args.from_alias or agent["from_alias"]

    topic = args.topic or (task.get("title") if task else "")
    if not topic:
        raise SystemExit("缺少任务主题：请传入 --topic，或使用 --issue/--task-id/--slug 绑定已有任务")
    subject = compose_subject(agent, task, topic)
    body = compose_body(config, registry, agent, task, topic, args.type, args.instruction)
    if args.output:
        write_eml(args.output, to_addr, subject, body, reply_to, from_alias)
        print(f"EMAIL_DRAFT:{args.output}")
    else:
        print(f"To: {to_addr}")
        if from_alias:
            print(f"From: {from_alias}")
        if reply_to:
            print(f"Reply-To: {reply_to}")
        print(f"Subject: {subject}")
        print()
        print(body)


if __name__ == "__main__":
    main()
