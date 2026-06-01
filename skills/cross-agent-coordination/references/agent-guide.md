# Agent Collaboration Guide

Use this guide when an agent starts, resumes, hands off, or finishes work in a cross-agent-coordination project.

## Repository Shape

```
/
  config/
    collab.yaml
    task-types.yaml
  templates/
    tasks/
      default.md
      写作.md
  project-tasks.md
  260517001-研究-法律AI产品生态调查/
    README.md
```

The project task source is configured by `project.issue_file` or project context. Task folders stay flat at the repository root only when a workstream needs a material package, artifact package, or durable handoff notes. Project-specific task files, task types, and templates live in the project, not inside the Skill source.

## Start A Work Session

1. Pull the latest default branch.
2. Read `config/collab.yaml` and the configured task source.
3. For executable work, run `python3 scripts/find_task.py . --available --agent <agent-id>`.
4. If the user gives a topic, run `python3 scripts/find_task.py . --topic "<topic>"` before creating any task folder.
5. Create an agent branch named `agent/{agent-id}/{slug}` or `agent/{agent-id}/issue-{n}-{slug}` before committing.

Default `claim_policy` is `assigned_only`; only work on Issues or task folders whose responsible field matches your Agent ID. Projects may set `claim_policy: claim_pool` to allow unassigned todo tasks to be claimed.

## Create A Task

Create or edit the configured task source first. Only create a task folder when the workstream needs a durable material package:

```bash
python3 scripts/task_scaffold.py create --root . --type 研究 --topic "LegalSkill架构设计" --assignee codex
```

The script allocates the next `YYMMDDNNN` ID, creates `{id}-{type}-{title}`, and writes README frontmatter using the project template. Use `--field key=value` to add project-specific metadata:

```bash
python3 scripts/task_scaffold.py create --root . --type 写作 --topic "ch01 Agent发展阶段" --field chapter=ch01 --field target_words=15000
```

Before creating, the script searches existing tasks and stops when it finds likely duplicates. Integrate new findings into the existing task README instead of creating another folder. Use `--dry-run` to inspect the generated ID and slug without writing files. Use `--force-new` only after confirming the topic is not a duplicate.

## Update A Task README

Keep the configured task source as the status source. Keep the task README useful for the next agent when a task folder exists. Include:

- Objective and acceptance criteria
- Current progress
- Source files, links, or evidence already reviewed
- Decisions and rationale
- Blockers and open questions
- Next concrete step

Do not rely on chat history alone. The README is the durable handoff record.

## Commit And PR

Use an agent-specific branch and let scripts set the Git author:

```bash
python3 scripts/gh_git.py branch --dest . --agent codex --name agent/codex/260517001-研究-法律AI产品生态调查
python3 scripts/gh_git.py commit --dest . --agent codex --message "docs: update task handoff"
python3 scripts/gh_git.py push --dest . --agent codex
python3 scripts/gh_git.py pr --dest . --agent codex --title "docs: Codex handoff update"
```

Prefer an agent-specific token environment variable, such as `CODEX_GITHUB_TOKEN`, when the PR opener should appear as that agent's GitHub account or app. The `pr` subcommand writes Agent ID, Git author, and expected GitHub actor into the PR body. If a token is stored in `config/collab.yaml`, first confirm that file is ignored and never stage it.

## Trigger External Agents By Email

When an external agent supports inbound email, compose a trigger draft:

```bash
python3 scripts/email_trigger.py . --agent manus --task-id 260517001 --topic "法律AI产品生态调查"
```

Prefer binding to an existing Issue in the configured task source:

```bash
python3 scripts/email_trigger.py . --agent manus --issue 9
```

Use this only after binding the work to an existing Issue/task or confirming the email instructs the recipient to run duplicate search first. See `references/email-trigger.md`.

## Route To External Adapters

Before sending work to an external Agent, check `config/collab.yaml`:

1. Match the task need against `agents.<id>.capabilities`.
2. Prefer `--issue N` so the adapter receives the project task-source context.
3. Include acceptance criteria and handoff requirements in the trigger.
4. Require branch + PR output when the result changes repository files.
5. Keep local execution sessions in `multi-agent-orchestration`; do not use email adapters to manage tmux or worktree state.

## Finish A Work Session

1. Update the configured task source status and notes.
2. If a task folder exists, update README `progress`, `updated`, `assignee`, and add a short handoff note with next steps.
3. Run `python3 scripts/find_task.py . --topic "<topic>"` before uploading newly researched material.
4. Run `python3 scripts/audit_repo.py .` when touching legacy or externally created tasks.
5. Commit README and artifact changes.
6. Open or update the PR.

## Merge Duplicate Tasks

When two folders cover the same workstream:

1. Choose the richest task folder as the target unless the user chooses differently.
2. Copy useful material into the target.
3. Record source task IDs in the target README.
4. Add merge notices to source READMEs.
5. Move source folders to `archive/` only after preserving their README frontmatter.
