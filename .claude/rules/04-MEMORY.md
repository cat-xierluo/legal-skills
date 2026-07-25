---
summary: "Curated long-term memory"
read_when:
  - Main session only
---
# MEMORY.md - Long-Term Memory

This file is the agent's compact long-term memory. It should hold durable working principles, project indexes, and stable shared context.

Do not use this file as a transcript. Detailed project history belongs in topic files; daily raw notes belong in dated logs.

## Memory Architecture

| Layer | Path | Purpose |
|---|---|---|
| Core memory | `.claude/rules/04-MEMORY.md` | Compact principles, current project index, durable decisions |
| User context | `.claude/rules/03-USER.md` | Stable user preferences and context |
| Topic memory | `memory/topics/<name>.md` | Detailed project or theme history |
| Daily notes | `memory/YYYY-MM-DD.md` | Raw chronological notes from recent work |

Information should flow from raw notes to topic files, then into this file only when it becomes broadly useful.

## Rules

- Store each fact in one place. Link or point to detail instead of duplicating it.
- Prefer dated, concrete memories over vague impressions.
- Remove or demote stale context during maintenance.
- Keep this file short enough to remain useful when automatically loaded.
- When the memory structure changes, update the relevant instructions and templates together.

## Current Context

Add the current state of important projects here as short pointers. Put detailed timelines in `memory/topics/`.

## Durable Lessons

Add cross-project lessons and working principles here when they have repeated value.
