# Legacy Migration Guide

Use this guide when an existing collaboration project contains older task metadata.

## What Changed In v0.4.0

- Skill path is `.claude/skills/cross-agent-coordination/`.
- Project config is `config/collab.yaml`.
- Task types are read from `config/task-types.yaml`, then the Skill default registry.
- New task README frontmatter uses `assignee`; `agent` is only read as a legacy fallback.
- Dashboard and Obsidian sync helpers were removed from this Skill.

The scripts intentionally do not read old `github-monorepo-collab` or `config/monorepo.yaml` paths.

## Low-Risk Migration Order

1. Copy old local configuration into `config/collab.yaml`.
2. Add `config/task-types.yaml` for project-specific task categories.
3. Add `templates/tasks/default.md` and type-specific templates if needed.
4. Run `python3 scripts/audit_repo.py .`.
5. Fix only the task README files that block current work.
6. For new tasks, use `task_scaffold.py` so metadata is written in the v0.4.0 format.

## Common Fixes

- Rename `agent` to `assignee` when touching an active task.
- Add `dependencies: []` and `artifact_paths: []` if missing.
- Replace old script references with `task_scaffold.py` and `audit_repo.py`.
- Remove any workflow that invokes a removed dashboard generator.
