---
name: multi-agent-orchestration
description: 多 Agent 本地执行编排。本技能应在 2 个以上本地 Agent/会话需要并行推进、worktree 隔离、Agent Teams/tmux 启动、PM 巡检和 PR 收口时使用。不要用于单个短任务、跨平台任务状态管理，或 Git 分支/提交/PR/merge 安全规则。
license: MIT
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.8.2"
---

# Multi-Agent Orchestration

PM 式多 Agent 本地执行编排。它回答一个问题：多个 Agent 如何在同一仓库里用独立 worktree/session 并行干活，并让 PM 会话可巡检、可收口。

## 1. 边界

使用本 Skill：
- 需要 2 个以上本地 Agent / Codex / Claude session 并行工作。
- 任务需要独立 worktree、独立分支、独立 PR。
- PM 会话需要启动、监控、纠偏和收口多个 worker。

不使用本 Skill：
- 单个短任务、单文件修改、一次性问答。
- 任务主状态、负责人、依赖管理：用 `cross-agent-coordination`。
- 分支命名、提交格式、PR merge、push、冲突解决：用 `git-workflow`。
- 外部 Agent 邮件触发：用对应外部协作/邮件 Skill。

## 2. 执行模式

| 模式 | 适用 | 默认隔离 |
|------|------|----------|
| PM 直接处理 | 轻量、低风险、无并行价值 | 当前工作区 |
| Subagent | 窄范围分析、审阅、局部修订 | 通常不新建 worktree |
| Agent Teams | Claude Code 可用、需要团队式协作 | worktree + branch |
| tmux 独立 session | 长上下文、正式写作、需要独立 Codex/Claude 进程 | worktree + branch |

优先级由项目规则决定。若项目明确要求正式章节撰写使用 tmux 独立 session，遵循项目规则。

## 3. 标准流程

1. **读任务源**：优先读取项目配置或项目上下文指定的任务源，用 `cross-agent-coordination` 判断可执行项、依赖和归属。
2. **先分组**：不要默认一个 Issue 一个 worker。文件范围重叠、同一章节/模块、存在依赖链的任务应同组顺序执行。
3. **判定并行安全**：只有文件范围清晰、无共享迁移/锁文件/schema、验收标准独立时才拆成多个 worktree 并行。
4. **命名并创建 worktree**：分支按任务语义命名；worktree 路径按本地执行来源加前缀。
5. **启动 worker**：给每个 worker 明确目标文件、允许修改范围、验证命令、提交和 PR 要求。
6. **PM 巡检**：定期查看 health report、tmux pane、git status、commit/PR 状态。发现偏题、阻塞或范围扩大时介入。
7. **收口**：worker 提交并开 PR 后，PM 做范围检查、触发 review、按 `git-workflow` 合并和清理。

## 4. 命名规则

分支名面向远端协作和 PR，必须体现任务语义，不写执行来源。

```text
docs/ch01-agent-intro
research/issue-13-ch08-materials
fix/agent-session-shell
```

worktree 路径只用于本地隔离，应加执行来源前缀：

```text
.claude/worktrees/tmux-ch01-agent-intro
.claude/worktrees/team-agent-session-shell
.claude/worktrees/subagent-copyedit-ch02
```

不要把 `tmux-`、`subagent-`、`team-`、`agentteam-` 写进分支名。分支类型前缀和提交/PR 格式以 `git-workflow` 为准。

创建示例：

```bash
git worktree add .claude/worktrees/tmux-ch01-agent-intro -b docs/ch01-agent-intro
git worktree add .claude/worktrees/team-agent-shell -b fix/agent-session-shell
```

## 5. Worker Prompt 最小模板

```text
你是并行执行 worker，不是唯一协作者。不要回退或覆盖其他人的改动。

Branch: docs/ch01-agent-intro
Worktree: .claude/worktrees/tmux-ch01-agent-intro
Scope: 只修改 manuscript/认知篇/ch01-从Chatbot到Agent.md
Goal: 完成 ch01 正式初稿。
Inputs: AGENTS.md、docs/STYLE-GUIDE.md、对应大纲卡片、Issue、指定 research/source-material。
Verify: git diff --check main...HEAD
Finish: commit、push、创建 PR；PR 正文列出 Issue、来源材料、验证和风险。
Out of scope: 不更新协作文档，不扩展调研，不改其他章节。
```

## 6. 启动方式

### tmux / 独立 Codex session

```bash
tmux new-session -d \
  -s legal-ch01 \
  -c .claude/worktrees/tmux-ch01-agent-intro \
  'codex -a never exec -s danger-full-access - < /tmp/ch01.prompt.md'
```

巡检：

```bash
tmux capture-pane -t legal-ch01 -p | tail -30
git -C .claude/worktrees/tmux-ch01-agent-intro status --short
```

### Agent Teams / Claude Code

Agent Teams 仍使用 worktree 隔离。将 `workdir` 指向带来源前缀的 worktree，分支保持语义名：

```json
{
  "name": "worker-1",
  "workdir": ".claude/worktrees/team-agent-shell",
  "prompt": "Branch: fix/agent-session-shell\nScope: ...\nVerify: ..."
}
```

### Subagent

仅用于轻量、边界窄、输入少的任务。若需要长时间写作、跨大量材料整合、独立提交 PR，升级为 tmux 或 Agent Teams。

## 7. 巡检与介入

PM 巡检信号：
- worktree 是否有文件落盘、commit、PR。
- tmux pane 是否长时间只读材料、等待确认、偏题联网、反复规划不执行。
- worker 是否扩大改动范围或触碰共享文件。
- PR diff 是否只覆盖声明范围。

介入规则：
- 有持续输出或文件在增长时继续等待。
- 长时间无落盘但仍在规划时，发送更窄的“先写目标文件”命令。
- 明确偏题、等待确认、越界修改时中断并纠偏。
- 失败或重启前先保留 worktree，避免丢失已落盘产物。

可选自动 PM 监控脚本（保留 Agent Teams inbox、任务状态、Git SHA、PR 状态和 tmux session 多维巡检能力）：

```bash
bash scripts/pm-monitor.sh \
  --project /path/to/repo \
  --team-dir ~/.claude/teams/team-name \
  --tasks-dir ~/.claude/tasks/tasks-uuid \
  --branch docs/ch01-agent-intro:legal-ch01
```

## 8. 收口

worker 完成后：
1. 检查 `git status --short`、`git diff --check main...HEAD`、PR diff 范围。
2. 需要 review 时交叉审阅，分支作者不审自己的 PR。
3. 合并、push、PR 编号写入 commit、Issue 关闭等动作遵循 `git-workflow`。
4. 合并后清理 worktree/session：

```bash
git worktree remove .claude/worktrees/tmux-ch01-agent-intro
tmux kill-session -t legal-ch01
```

## 9. 依赖

### 系统依赖

| 依赖 | 安装方式 |
|------|----------|
| `git` | 通常随开发环境提供 |
| `tmux` | macOS: `brew install tmux`<br>Linux: `sudo apt-get install tmux` |
| `jq` | macOS: `brew install jq`<br>Linux: `sudo apt-get install jq` |
| `gh` | macOS: `brew install gh`<br>Linux: 参考 GitHub CLI 官方安装方式 |

### 可选终端依赖

`scripts/terminal-split.sh` 只在对应终端场景下需要额外工具：Kitty 需要 `kitty @`，WezTerm 需要 `wezterm cli`，macOS GUI 终端自动化依赖 `osascript`，Warp/Ghostty/Zed/Terminal.app 分屏或新标签能力取决于本机应用和辅助功能授权。

## 10. 参考

只在需要细节时读取：
- `references/model-selection-matrix.md`：模型与执行模式选择。
- `references/parallel-lessons.md`：tmux/Agent Teams 实战坑点。
- `references/legal-domain-templates.md`：法律项目拆解样例。

脚本：
- `scripts/pm-monitor.sh`：自动 PM 巡检脚本，保留 Agent Teams inbox、tasks、Git SHA、PR 状态、tmux session 多维监控。
- `scripts/terminal-split.sh`：多终端分屏/新标签辅助，保留 iTerm2、Kitty、WezTerm、Warp、Ghostty、Zed、Terminal.app 支持。
