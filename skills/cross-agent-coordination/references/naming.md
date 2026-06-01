# Naming And Archive Rules

Use the project-configured task source as the task status source across all agents. Task folders are optional context packages for heavy workstreams.

## Issue Record

Default issue heading format:

```markdown
### ✅ Issue #9: 触发 Manus 调研任务
```

Recommended fields:

- `类型` / `Type`: task type, optionally with delegation text such as `研究（委托 Manus）`.
- `负责人` / `Lead Author` / `assignee`: human or Agent responsible for execution.
- `依赖`: dependency text. `Issue #N` references are parsed as dependencies.
- `目标`: objective.
- `素材来源` / `来源材料`: source material.
- `验收标准`: acceptance criteria section.

Default status mapping:

| Marker | Status |
|---|---|
| `⬜` | `pending_confirmation` |
| `✅` | `ready` |
| `🟢` | `created` |
| `[ ]` | `todo` |
| `[x]` | `done` |

Projects may override mappings through `project.status_map`, `available_statuses`, and `dependency_done_statuses` in `config/collab.yaml`.

## Task Folder ID

Format: `YYMMDDNNN`

- `YYMMDD`: task creation date.
- `NNN`: three-digit sequence for that date, starting from `001`.
- The ID never changes after creation, even if the task is renamed, merged, or archived.

## Folder Slug

Format: `{id}-{type}-{title}`

Examples:

- `260305001-法律-CodingPlan数据条款综合`
- `260305002-研究-LegalSkill架构设计`
- `260305003-整合-多来源资料合并`

Rules:

- `id` must be the stable task ID.
- `type` must exist in the task type registry. Projects extend it through `config/task-types.yaml`.
- Scripts accept aliases from the registry and normalize them to the canonical type.
- `title` may use Chinese or English, but must not contain path separators or shell-sensitive characters.
- Keep titles concise enough to scan in GitHub branch and PR lists.

## Branch Name

Format: `agent/{agent-id}/{slug}`

Examples:

- `agent/codex/260305001-法律-CodingPlan数据条款综合`
- `agent/manus/260305002-研究-LegalSkill架构设计`

## README Frontmatter

README frontmatter belongs to the task folder context package. It must not override the configured task source status.

Each task folder must contain `README.md` with frontmatter:

```yaml
---
id: 260305001
slug: 260305001-法律-CodingPlan数据条款综合
title: CodingPlan 数据条款综合研究
type: 法律
status: doing
assignee: codex
dependencies: []
artifact_paths: []
progress: 30
created: 2026-03-05
updated: 2026-03-05
---
```

`agent` may appear in legacy tasks, but new tasks use `assignee`.

## Status

| Status | Meaning |
|---|---|
| `todo` | 待开始 |
| `doing` | 进行中 |
| `done` | 已完成 |
| `blocked` | 阻塞中 |
| `archived` | 已归档 |
| `deprecated` | 已废弃 |

Dependencies are considered satisfied when referenced tasks are `done`, `resolved`, or `closed`.

## Merge And Archive

When merging similar tasks:

1. Compare task folders and choose the richest folder as the main task, unless the user chooses a different target.
2. Keep every original task ID in the main README under a merge history section.
3. Add a merge notice to each source README that points to the target task.
4. Move merged source folders under `archive/` only after preserving their README frontmatter.
