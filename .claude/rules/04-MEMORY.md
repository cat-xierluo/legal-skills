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

- **律师短视频自动化（🎬内容）**：口播 mp4 → 字幕 + 强调缩放 + 文字可视化的全自动成片链路。粗剪/字幕链路已跑通（lawyer-video-cut v1.1.1、lawyer-video-production v1.1.0，PR#24/#25 已合并，端到端验证 FragmentVideo 120.5s→96.4s）。下游三条渲染路径（A=FFmpeg烧字幕、B=op7418花字、C=Remotion可视化）由 idle-task-runner 凌晨自动推进。项目入口 `private-skills/` 的 `LAWYER-VIDEO-ROADMAP.md`（总览）+ 律师短视频 IDLE_HANDOFF（接力）。注意后续会话已把项目重构为"律师IP全链"（见 handoffs/🎬内容-律师IP全链.md）。
- **idle-handoff skill**：把会话成果/下一步记进 idle-task-runner 凌晨自动推进体系。任意工作区可调用，自动探测 IDLE_TASK_RUNNER_ROOT。2026-07-10 起源于 legal-skills/.claude/commands/ 的一个 command（注意：`.claude/commands/` 被 .gitignore，command 文件不入库、易丢），2026-07-14 已升级为独立 skill `private-skills/任务自动化/idle-handoff/`（v0.1.0，含路径解耦）。
- **douyin-content-manager 定时任务 (2026-07-15)**：抖音视频「下载→压缩→转录(FunASR)→纠错(DeepSeek)」每日凌晨一条龙。cron `2fe76c31`，03:20 Asia/Shanghai（实测触发偏晚~1h，引擎 bug）。详见 `memory/topics/douyin-content-manager.md`。

## Durable Lessons

- **command → skill 的演进路径（2026-07-10 律师短视频首例验证）**：临时能力先在工作区 `.claude/commands/` 跑通，稳定后升级为独立 skill。但 `.claude/commands/` 在本工作区被 `.gitignore`（第13行），command 文件不入 git、易随清理丢失——所以 command 阶段就要在记忆/日志留痕，升级成 skill 才有持久落点。
- **private-skills 是 symlink 独立仓库**（见 ~/.claude memory `project_private_skills_symlink_repo`）：legal-skills/private-skills 指向 maoscripts/private-skills 真仓库；提交去那边；工作区混多会话改动不能 `git add -A`；开 PR 分支基于 origin/main 避免带别人未推送提交；commit 前查全仓库 staged 防混入。
- **MyAgents cron 的三个坑（2026-07-13 douyin 任务验证）**：① `cron update --prompt-file` 静默失败（报 ✓ 但 prompt 没写回）——改 prompt 必须删了 `cron add --prompt-file` 重建，建完立即 `cron list --json` 验内容；② 裸 cron 表达式被当 UTC 解释（差 8h），必须 `--schedule '{"kind":"cron","expr":"...","tz":"Asia/Shanghai"}'`；③ 即使带 tz，实测触发仍偏晚 ~40min-1h（引擎层 bug，无法外部修，只能接受）。详见 `memory/topics/douyin-content-manager.md`。

