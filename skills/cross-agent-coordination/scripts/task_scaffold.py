#!/usr/bin/env python3
"""Create task folders for cross-agent-coordination projects."""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from collab_lib import (
    get_agent_identity,
    get_current_agent,
    get_next_task_id,
    get_token,
    load_config,
    load_task_type_registry,
    merge_frontmatter,
    parse_field,
    project_config,
    render_template,
    resolve_project_path,
    sanitize_slug_part,
    find_similar_tasks,
    skill_root,
    today,
)


def run(cmd, cwd=None):
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def capture(cmd, cwd=None):
    return subprocess.check_output(cmd, cwd=str(cwd) if cwd else None).decode("utf-8").strip()


def configure_git_identity(root, identity):
    run(["git", "config", "user.name", identity["git_name"]], cwd=root)
    run(["git", "config", "user.email", identity["git_email"]], cwd=root)


def git_auth_args(token):
    raw = f"x-access-token:{token}".encode("utf-8")
    encoded = base64.b64encode(raw).decode("ascii")
    return ["-c", f"http.extraHeader=Authorization: Basic {encoded}"]


def git_with_token(token, git_args, cwd=None):
    run(["git", *git_auth_args(token), *git_args], cwd=cwd)


def parse_repo(repo_url):
    match = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)", repo_url)
    if not match:
        raise SystemExit(f"无法解析 GitHub 仓库地址: {repo_url}")
    return match.group("owner"), match.group("repo")


def clean_repo_url(repo_url):
    owner, repo = parse_repo(repo_url)
    return f"https://github.com/{owner}/{repo}.git"


def github_api(method, url, token, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            detail = json.loads(body)
        except json.JSONDecodeError:
            detail = {"message": body}
        return exc.code, detail


def render_matches(matches):
    lines = ["发现可能重复的既有任务："]
    for item in matches:
        lines.append(
            f"- {item['slug']} (score={item['score']:.2f}, id={item['id']}, "
            f"status={item['status']}, type={item['type']})"
        )
    lines.append("")
    lines.append("请优先打开上述任务 README，把新材料整合进去；如确认不是重复主题，再添加 --force-new。")
    return "\n".join(lines)


def template_candidates(root, config, task_type):
    project = project_config(config)
    template_dir = resolve_project_path(root, str(project.get("template_dir", "")), "templates/tasks")
    candidates = [
        template_dir / f"{task_type}.md",
        template_dir / "default.md",
        skill_root() / "templates" / "tasks" / f"{task_type}.md",
        skill_root() / "templates" / "tasks" / "default.md",
    ]
    return candidates


def load_template(root, config, task_type):
    for path in template_candidates(root, config, task_type):
        if path.exists():
            return path.read_text(encoding="utf-8")
    return """---
id: {{ id }}
slug: {{ slug }}
title: {{ title }}
type: {{ type }}
status: todo
assignee: {{ assignee }}
dependencies: []
artifact_paths: []
progress: 0
created: {{ created }}
updated: {{ updated }}
---

# {{ title }}

## 目标

## 验收标准

## 来源材料

## 交接记录
"""


def build_readme(root, config, task_type, fields):
    content = render_template(load_template(root, config, task_type), fields)
    return merge_frontmatter(content, fields)


def parse_extra_fields(raw_fields):
    fields = {}
    for raw in raw_fields:
        key, value = parse_field(raw)
        fields[key] = value
    return fields


def get_origin(root):
    try:
        return capture(["git", "remote", "get-url", "origin"], cwd=root)
    except subprocess.CalledProcessError:
        return ""


def cmd_create(args):
    root = Path(args.root).expanduser()
    config = load_config(root)
    registry = load_task_type_registry(root, config)
    agent = get_current_agent(config, args.agent)
    identity = get_agent_identity(config, agent)
    task_type = registry.normalize(args.type)

    matches = find_similar_tasks(root, registry, args.topic, task_type, args.match_threshold, limit=5, config=config)
    if matches and not args.force_new:
        if args.dry_run:
            print(render_matches(matches))
            return
        raise SystemExit(render_matches(matches))

    task_id = get_next_task_id(root)
    topic_slug = sanitize_slug_part(args.topic)
    slug = sanitize_slug_part(args.slug or f"{task_id}-{task_type}-{topic_slug}")
    if not re.match(r"^\d{9}-", slug):
        slug = f"{task_id}-{slug}"
    dest = root / slug
    if dest.exists() and not args.reuse:
        raise SystemExit(f"任务目录已存在: {dest}；如需复用请添加 --reuse")

    extra_fields = parse_extra_fields(args.field)
    fields = {
        "id": task_id,
        "slug": slug,
        "title": args.topic,
        "type": task_type,
        "status": "todo",
        "assignee": args.assignee or agent,
        "dependencies": [],
        "artifact_paths": [],
        "progress": 0,
        "created": today(),
        "updated": today(),
    }
    fields.update(extra_fields)

    if args.dry_run:
        print(f"DRY_RUN_TASK_ID:{task_id}")
        print(f"DRY_RUN_SLUG:{slug}")
        print(f"DRY_RUN_TYPE:{task_type}")
        print(f"DRY_RUN_ASSIGNEE:{fields['assignee']}")
        return

    dest.mkdir(parents=True, exist_ok=True)
    readme = dest / "README.md"
    if not readme.exists():
        readme.write_text(build_readme(root, config, task_type, fields), encoding="utf-8")

    print(f"✅ 创建任务: {slug} (ID: {task_id})")

    if args.auto_commit:
        branch = f"agent/{agent}/{slug}"
        configure_git_identity(root, identity)
        run(["git", "checkout", "-B", branch], cwd=root)
        run(["git", "add", "-A"], cwd=root)
        commit_msg = f"feat: 创建任务 {args.topic} ({slug})"
        run(["git", "commit", "-m", commit_msg], cwd=root)
        print(f"📝 提交: {commit_msg}")

        token = get_token(config, agent)
        origin = get_origin(root)
        if not origin:
            print("⚠️ 当前仓库没有 Git remote，已保留本地提交，跳过 push/PR")
            return
        if not token:
            print("⚠️ 未找到 GITHUB_TOKEN 或 agent token，无法推送")
            return

        clean_origin = clean_repo_url(origin)
        run(["git", "remote", "set-url", "origin", clean_origin], cwd=root)
        git_with_token(token, ["push", "-u", "origin", branch], cwd=root)
        print(f"✅ 已推送分支: {branch}")

        owner, repo = parse_repo(clean_origin)
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        data = {
            "title": f"feat: {args.topic}",
            "body": f"""## Agent Attribution

- Agent ID: {agent}
- Git Author: {identity['git_name']} <{identity['git_email']}>
- Expected GitHub Actor: {identity['github_user'] or '取决于实际执行 PR 的账号'}

## 任务信息

- ID: {task_id}
- 类型: {task_type}
- Assignee: {fields['assignee']}
- slug: {slug}

## 描述

创建任务「{args.topic}」""",
            "head": branch,
            "base": "main",
        }
        status, body = github_api("POST", url, token, data)
        if status == 201:
            pr_url = body["html_url"]
            pr_number = body["number"]
            print(f"✅ 已创建 PR: {pr_url}")
            if args.auto_merge:
                merge_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/merge"
                merge_status, merge_body = github_api(
                    "PUT",
                    merge_url,
                    token,
                    {"merge_method": "squash", "commit_title": f"Merge: {args.topic}"},
                )
                if merge_status == 200:
                    print(f"✅ 已自动合并 PR #{pr_number}")
                    git_with_token(token, ["push", "origin", "--delete", branch], cwd=root)
                    print(f"✅ 已删除远程分支 {branch}")
                else:
                    print(f"⚠️ 自动合并失败: {merge_status}")
                    print(f"   {merge_body}")
        else:
            print(f"❌ 创建 PR 失败: {body}")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    create = sub.add_parser("create")
    create.add_argument("--root", required=True)
    create.add_argument("--type", required=True, help="任务类型，可由 config/task-types.yaml 扩展")
    create.add_argument("--topic", required=True)
    create.add_argument("--slug", default="")
    create.add_argument("--agent", default="")
    create.add_argument("--assignee", default="", help="任务负责人，默认使用当前 agent")
    create.add_argument("--field", action="append", default=[], help="追加 frontmatter 字段，格式 key=value")
    create.add_argument("--reuse", action="store_true", help="复用已存在的同名任务目录")
    create.add_argument("--force-new", action="store_true", help="即使命中相似主题也强制新建任务")
    create.add_argument("--match-threshold", type=float, default=0.58, help="主题查重阈值，默认 0.58")
    create.add_argument("--dry-run", action="store_true", help="只输出将要创建的任务 ID 和 slug")
    create.add_argument("--auto-commit", action="store_true", help="自动提交并推送")
    create.add_argument("--auto-merge", action="store_true", help="自动合并 PR")
    create.set_defaults(func=cmd_create)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
