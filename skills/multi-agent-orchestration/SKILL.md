---
name: multi-agent-orchestration
description: 多 Agent 本地执行编排与跨模型额度路由。本技能应在 2 个以上本地 Agent/会话需要并行推进、worktree 隔离、Claude Code/Codex/OpenCode/tmux worker 启动、PM 巡检、模型/额度分流和 PR 收口时使用。当前主会话可以是 Codex、Claude Code、OpenCode 或其他 Agent；PM 是角色，不是固定产品。不要用于单个短任务、跨平台任务状态管理，或 Git 分支/提交/PR/merge 安全规则。
license: MIT
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.9.3"
---

# Multi-Agent Orchestration

PM 式多 Agent 本地执行编排。它回答一个问题：多个 Agent 如何在同一仓库里用独立 worktree/session 并行干活，并让当前主会话作为 PM 可巡检、可收口、可控制额度消耗。

PM 是当前负责拆解、派工、验收和收口的主会话，不绑定具体产品。Codex 可以做 PM 调 Claude Code 或 OpenCode worker；Claude Code 也可以做 PM 调 Codex 或 OpenCode worker。Skill 只规定角色、隔离、启动、状态和收口协议。

## 1. 边界

使用本 Skill：
- 需要 2 个以上本地 Agent / Codex / Claude session 并行工作。
- 任务需要独立 worktree、独立分支、独立 PR。
- PM 会话需要启动、监控、纠偏和收口多个 worker。
- 需要把简单任务路由给 Claude Code、Codex、OpenCode 或其他 CLI worker，以控制主会话 token 和不同模型额度消耗。

不使用本 Skill：
- 单个短任务、单文件修改、一次性问答。
- 任务主状态、负责人、依赖管理：用 `cross-agent-coordination`。
- 分支命名、提交格式、PR merge、push、冲突解决：用 `git-workflow`。
- 外部 Agent 邮件触发：用对应外部协作/邮件 Skill。

## 2. 执行模式

| 模式 | 适用 | 默认隔离 |
|------|------|----------|
| PM 直接处理 | 轻量、低风险、无并行价值 | 当前工作区 |
| 同宿主 Subagent | 窄范围分析、审阅、局部修订 | 通常不新建 worktree |
| Claude Code Agent Teams | Claude Code 做 PM 且需要团队式协作 | worktree + branch |
| tmux 独立 CLI session | 需要跨产品 worker、长上下文、独立额度或独立进程 | worktree + branch |
| Claude Code agent view | 需要使用官方后台会话、peek/reply/attach 和 `claude agents` 总览 | 可用 Claude 官方 `--worktree` / `--tmux`，或手动 worktree |
| ACP adapter | 项目已提供稳定 adapter，且需要结构化事件流 | adapter 决定，仍建议 worktree + branch |

优先级由项目规则决定。若项目明确要求正式章节撰写使用 tmux 独立 session，遵循项目规则。

### 2.1 角色与后端

先分清角色，再选择后端：

| 角色 | 职责 | 可由谁担任 |
|------|------|------------|
| PM | 读取任务源、分组、启动 worker、巡检、验收、合并收口 | 当前 Codex、Claude Code、OpenCode 或其他主会话 |
| Worker | 在指定 worktree/branch 内完成限定任务 | Claude Code、Codex、OpenCode、自定义 CLI、shell 脚本、未来 ACP agent |
| Reviewer | 检查 diff、测试、范围和风险 | PM、另一个 worker、code-review subagent |

PM 代理纪律：
- 如果用户明确要求当前会话做 PM / orchestrator / 多 Agent 编排，PM 默认不直接写业务代码。
- PM 的核心价值是 token efficiency、模型/额度路由、多线程推进、范围控制和验收收口；实现任务优先派给 worktree worker、独立 CLI session、Agent Teams 或 Subagent。
- PM 可以直接改代码的例外：任务极小且无并行价值、用户明确要求 PM 直接做、worker 连续纠偏失败且只剩窄范围收口、或需要立即修复 PM 自己生成的 orchestration 文档/配置。
- PM 如果越过例外直接下场改代码，应在最终汇报说明原因；常规实现应通过 worker 产物、PM 纠偏和 PR review 完成。

后端选择规则：
- 当前主会话是什么不重要；默认“谁启动编排，谁就是 PM”。
- 需要通过第三方 Anthropic-compatible API 启动 Claude Code 时，worker backend 选 Claude Code；这是 Claude Code worker 的默认额度模式。
- 只有用户明确要走 Claude 订阅/OAuth 时，才使用 `claude-oauth-*` profile，并清理第三方 provider 环境变量。
- 需要消耗 Codex / OpenAI 额度或使用 Codex 配置时，worker backend 选 Codex。
- 需要消耗 OpenCode 已配置的 provider/model，或要使用 OpenCode 的 `opencode run` / `opencode acp` 能力时，worker backend 选 OpenCode。
- 其他 Agent 只要能用一行命令启动，并能在指定 cwd 读写文件，也可作为 custom CLI worker。
- 需要稳定进程生命周期和人工接管时，优先 `tmux + worktree`。
- ACP 只在 adapter 已稳定、能输出结构化状态时启用；没有 adapter 时不要为了协议增加不确定性。

环境/profile 纪律：
- PM 启动 worker 时必须显式写 `Runtime Profile`、settings/profile 路径、模型来源和关键环境变量处理方式，不假定 Claude Code、Codex、OpenCode 共享同一套 shell 环境。
- Claude Code 第三方 API provider profile 要保留 `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / 默认模型映射；不要套用 OAuth 的清理命令。
- Claude Code 订阅/OAuth profile 才清理第三方 provider 环境变量，避免误走外部 API。
- Codex / OpenAI worker、OpenCode worker 和 custom CLI worker 使用各自 profile；不要把 Anthropic provider 环境变量当作通用 worker 环境。
- Worker bootstrap 必须把 `which claude/codex/opencode`、版本号、cwd、关键 profile 名和 `node/npm/python/cargo` 等运行信息写入 `STATUS.json`，便于 PM 判断“环境不一样”是否影响任务。

## 3. 标准流程

1. **读任务源**：优先读取项目配置或项目上下文指定的任务源，用 `cross-agent-coordination` 判断可执行项、依赖和归属。
2. **先分组**：不要默认一个 Issue 一个 worker。文件范围重叠、同一章节/模块、存在依赖链的任务应同组顺序执行。
3. **判定并行安全**：只有文件范围清晰、无共享迁移/锁文件/schema、验收标准独立时才拆成多个 worktree 并行。
4. **选择 worker backend 和 runtime profile**：按任务复杂度、当前额度、模型偏好和是否需要独立进程，选择 Claude Code / Codex / OpenCode / custom CLI / shell / ACP。
5. **PM 创建隔离环境**：默认由 PM 创建 worktree、分支和 session context 目录，再把路径交给 worker；只有 Claude Code 官方 Agent Teams / agent view 明确使用自身 `--worktree` 能力时，才允许由 Claude Code 创建，但 PM 仍要验收分支、路径和隔离状态。
6. **启动 worker**：给每个 worker 明确目标文件、允许修改范围、验证命令、session context 目录、提交和 PR 要求。
7. **PM 巡检**：优先查看 `.claude/agent-sessions/<session-id>/STATUS.json`、`RESULT.md`、`PATCH_SUMMARY.md`、git status、commit/PR 状态；Claude 官方 Agent Teams 则优先读取 `~/.claude/teams/<team>/` 和 `~/.claude/tasks/<team>/`，`claude agents --json`、tmux pane 或 agent view 作为兜底观察。发现偏题、阻塞或范围扩大时介入。
8. **PM 验收而非代写**：PM 对 worker 结果做范围检查、测试复核和 review；发现问题优先发纠偏指令或派给 reviewer/另一个 worker，不默认自己改业务代码。
9. **收口**：worker 提交并开 PR 后，PM 做范围检查、触发 review、按 `git-workflow` 合并和清理。

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

### 4.1 Session Context 目录

Worker 的本地状态统一写到当前 worktree 的 `.claude/agent-sessions/<session-id>/`（下文简称 **Session Context**），复用项目既有 `.claude/` 协作空间，与 Claude Code 官方 Agent Teams 状态源明确区分。

```text
.claude/agent-sessions/legal-ch01/STATUS.json
.claude/agent-sessions/legal-ch01/RESULT.md
.claude/agent-sessions/legal-ch01/PATCH_SUMMARY.md
```

Claude Code 官方 Agent Teams 是另一套机制：团队配置在用户目录 `~/.claude/teams/<team-name>/config.json`，任务状态在 `~/.claude/tasks/<team-name>/`，inbox 在 `~/.claude/teams/<team-name>/inboxes/`。使用官方 Agent Teams 时优先读写这些官方状态源；不要在项目里自造 `.claude/teams/` 来冒充官方 team。

`.claude/agent-sessions/` 是 PM 巡检状态，不属于业务 diff。PM 和 worker 都必须确认它不进入 commit / push / PR；需要时由 PM 在对应 worktree 的本地 exclude 中忽略。

## 5. Worker Prompt 模板

Worker prompt 应像启动 subagent 一样给足上下文：任务来源、验收标准、允许文件、禁止文件、验证命令、checkpoint 协议和 PM 纠偏协议都要写清。不要只给一句“实现某功能”，否则 worker 容易把环境、依赖或相关技术债扩展成自己的任务。

模板放在 `templates/worker-prompt.md`，包含两个可复制段落：
- Bootstrap-only prompt：只创建 `STATUS.json`，适合高延迟 provider 或 high-effort 模型的第一条消息。
- Full worker prompt：按 Context / Background / Mission / Scope / Deliverables / Process / Verification / Autonomy / Out of Scope / PM Correction 组织，接近派发 subagent 时的写法。

对高延迟 provider 或 high-effort 模型，优先用两段式启动：第一条消息使用 Bootstrap-only prompt 创建 `Session Context/STATUS.json` 并回报 runtime；PM 确认 checkpoint 后，再发送 Full worker prompt。这样能避免 worker 在长思考前没有可观测状态。

## 6. 启动方式

### tmux / 独立 Claude Code worker

适合把简单或中等任务路由到 Claude Code。默认使用第三方 API provider settings；订阅/OAuth 只在用户明确要求时使用。

第三方 API settings 示例：

```bash
tmux new-session -d \
  -s legal-ch01 \
  -c .claude/worktrees/tmux-ch01-agent-intro \
  'claude --settings config/minimax.settings.json --permission-mode auto'
```

provider settings 可从 `config/claude-provider-settings.example.json` 复制后填写，内容是一整组环境变量：token、base URL、Haiku/Sonnet/Opus 默认模型、timeout、thinking tokens 和 Claude Code 行为开关。模板按 Minimax Anthropic-compatible API 的结构编写；其他 provider 只替换 token、base URL 和模型名。真实 settings 放在用户已忽略的本地路径，不要提交 token。

tmux session 是一个后台独立终端，可用 `tmux attach`、`capture-pane` 和 `send-keys` 管理。默认启动交互式 Claude Code，方便 PM 随时接管。若只是批处理执行 prompt，可改用 Claude Code 的 `-p` 模式：

```bash
tmux new-session -d \
  -s legal-ch01 \
  -c .claude/worktrees/tmux-ch01-agent-intro \
  'claude --settings config/minimax.settings.json -p --output-format stream-json --max-turns 20 --permission-mode acceptEdits < /tmp/ch01.prompt.md'
```

订阅/OAuth 示例：

```bash
tmux new-session -d \
  -s legal-ch01 \
  -c .claude/worktrees/tmux-ch01-agent-intro \
  'env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_BASE_URL claude --permission-mode auto'
```

### tmux / 独立 Codex worker

适合 Claude Code 做 PM 时，把部分任务交给 Codex worker 消耗 OpenAI/Codex 配额。

```bash
tmux new-session -d \
  -s legal-ch01 \
  -c .claude/worktrees/tmux-ch01-agent-intro \
  'codex exec -a never -s danger-full-access - < /tmp/ch01.prompt.md'
```

巡检：

```bash
tmux capture-pane -t legal-ch01 -p | tail -30
git -C .claude/worktrees/tmux-ch01-agent-intro status --short
```

### Claude Code agent view / 官方后台会话

Claude Code 提供 agent view，可用 `claude agents` 管理后台会话。它适合 Claude Code 做主要 worker 池时使用：官方会话可在 agent view 里 peek、reply、attach；shell 可用 `claude agents --json` 给 PM 脚本读取 live sessions。

```bash
claude agents --settings config/minimax.settings.json --permission-mode acceptEdits
```

脚本巡检：

```bash
claude agents --cwd "$(pwd)" --json
```

本机 Claude Code 2.1.149 已支持 `--worktree` 和 `--tmux`，可用官方 worktree/tmux 入口创建可接管 session：

```bash
claude --settings config/minimax.settings.json \
  --worktree legal-ch01 \
  --tmux \
  --name "legal-ch01" \
  --permission-mode acceptEdits \
  "Read TASK.md and implement it. Keep .claude/agent-sessions/legal-ch01/STATUS.json current. Write RESULT.md and PATCH_SUMMARY.md."
```

如果当前版本帮助明确列出 `--bg`，也可从 shell 直接启动后台会话：

```bash
claude --settings config/minimax.settings.json \
  --bg --name "legal-ch01" \
  --permission-mode acceptEdits \
  "Read TASK.md and implement it. Keep .claude/agent-sessions/legal-ch01/STATUS.json current. Write RESULT.md and PATCH_SUMMARY.md."
```

如果已在交互式 Claude Code 会话中，且 slash command 可用，可用 `/bg` 把当前会话移入后台。注意：CLI 版本可能对 `--bg`、`/bg`、`attach`、`logs`、`stop` 支持有差异；使用前以 `claude --help`、`claude agents --help` 和当前安装版本为准。

### tmux / 独立 OpenCode worker

适合把任务路由到 OpenCode 已配置的 provider/model。模型格式通常是 `provider/model`；可先用 `opencode models` 查看本机可用模型。

```bash
tmux new-session -d \
  -s legal-ch01-opencode \
  -c .claude/worktrees/tmux-ch01-agent-intro \
  'opencode run --format json --model <provider/model> "$(cat /tmp/ch01.prompt.md)"'
```

如确认该 worktree 是受控隔离环境，且需要减少权限等待，可按项目规则追加 `--dangerously-skip-permissions`；不要在未隔离目录默认使用。

若需要人工接管或继续会话，可改用交互式 OpenCode：

```bash
tmux new-session -d \
  -s legal-ch01-opencode \
  -c .claude/worktrees/tmux-ch01-agent-intro \
  'opencode --model <provider/model>'
```

### tmux / 自定义 CLI worker

适合接入其他能一行命令启动的 Agent。要求：能在 `tmux -c <worktree>` 指定目录运行；能通过 stdin、参数或 prompt 文件接收任务；最好支持模型/profile 参数和机器可读输出。

```bash
tmux new-session -d \
  -s legal-ch01-custom \
  -c .claude/worktrees/tmux-ch01-agent-intro \
  '<agent-command> < /tmp/ch01.prompt.md'
```

自定义 worker 仍必须遵守同一套 Branch、Worktree、Scope、Status、Verify 和 Finish 规则。

### Agent Teams / Claude Code

Claude Code 做 PM 且 Agent Teams 可用时，仍使用 worktree 隔离。将 `workdir` 指向带来源前缀的 worktree，分支保持语义名：

```json
{
  "name": "worker-1",
  "workdir": ".claude/worktrees/team-agent-shell",
  "model": "sonnet",
  "prompt": "Branch: fix/agent-session-shell\nScope: ...\nVerify: ..."
}
```

### ACP adapter

ACP 是可选后端，不是默认后端。只有当项目已有可启动的 ACP agent adapter，并能把 `session/update` 事件映射到 PM 可读状态时，才用 ACP。OpenCode 已提供 `opencode acp` 入口时，可以作为 ACP server 候选；但 PM 侧仍需要可用 ACP client/adapter。ACP worker 仍应遵循同一套 Branch、Worktree、Scope、Verify 和 checkpoint 规则。

### Subagent

仅用于轻量、边界窄、输入少的任务。若需要长时间写作、跨大量材料整合、独立提交 PR，升级为 tmux 或 Agent Teams。

## 7. 巡检与介入

PM 巡检信号：
- worktree 是否有文件落盘、commit、PR。
- `.claude/agent-sessions/<session-id>/STATUS.json` 是否更新，是否报告 blocked / needs_input / done。
- `.claude/agent-sessions/<session-id>/RESULT.md` 和 `PATCH_SUMMARY.md` 是否存在，摘要是否足够 PM 不读完整日志也能验收。
- tmux pane 是否长时间只读材料、等待确认、偏题联网、反复规划不执行。
- worker 是否扩大改动范围或触碰共享文件。
- PR diff 是否只覆盖声明范围。

介入规则：
- 有持续输出、checkpoint 更新或文件在增长时继续等待。
- 启动后 1-2 分钟仍没有 `Session Context/STATUS.json` 时，先发送 checkpoint-only 纠偏；仍无响应时中断当前思考并重发 bootstrap 指令，不直接接管实现。
- 长时间无落盘但仍在规划时，先发送更窄的“先写目标文件”命令。
- 发现轻度偏题、范围扩大、开始修环境/依赖、等待确认或验证方式偏离时，优先通过 tmux / agent view / inbox 发送纠偏指令，让 worker 自己回到范围内执行。
- 只有连续两次纠偏无效、worker 继续触碰禁止范围、准备执行破坏性 Git/文件操作、泄露敏感信息、或已无法在原 session 内恢复时，才停止 session 并由 PM 接管。
- 失败、重启或停止前先保留 worktree 和 `Session Context`，避免丢失已落盘产物。

tmux 纠偏示例：

```bash
tmux send-keys -t legal-ch01 -l -- "PM correction: stop dependency/runtime changes now. Return to ISS-017 only. Do not modify package files or environment config. Update .claude/agent-sessions/legal-ch01/STATUS.json with needs_input=false and continue with the OCR quality report scope."
sleep 0.1
tmux send-keys -t legal-ch01 Enter
```

纠偏 prompt 应包含四件事：停止什么、回到哪个任务、哪些文件/动作仍然禁止、下一步最小可执行动作。不要只写“你偏题了”。

推荐 checkpoint 文件：

```json
{
  "status": "running",
  "phase": "implementing",
  "progress": "2/5",
  "last_commit_sha": "",
  "tests": [],
  "needs_input": false,
  "issues": [],
  "updated_at": "2026-06-02T12:00:00Z"
}
```

完整字段和 Markdown 模板见 `references/checkpoint-files.md`。PM 默认只读这些 checkpoint 和最终 diff，不定时拉完整日志。

可选自动 PM 监控脚本（保留 Agent Teams inbox、任务状态、Git SHA、PR 状态和 tmux session 多维巡检能力）：

```bash
bash scripts/pm-monitor.sh \
  --project /path/to/repo \
  --team-dir ~/.claude/teams/team-name \
  --tasks-dir ~/.claude/tasks/tasks-uuid \
  --claude-agents-cwd /path/to/repo \
  --interval 60 \
  --log-file .claude/agent-sessions/pm-monitor/events.log \
  --branch docs/ch01-agent-intro:legal-ch01
```

经济型巡检规则：
- 不要让 PM 主会话每隔几分钟手动读取 worker 日志；那会抵消多 Agent 的 token efficiency。
- 轻量检查用 `pm-monitor.sh --once`，由 PM 在需要判断是否介入时运行一次，只读取事件行。
- 长任务用独立 shell/tmux/background job 运行 `pm-monitor.sh --log-file ...`，脚本持续写事件日志；PM 只在状态变化、用户询问、PR 收口或日志出现 `AGENT_NEEDS_INPUT` / `CHECKPOINT_STALE` / `CHECKPOINT_TEST_FAILURE` 时读取少量日志。
- 当前脚本只负责输出事件和写日志；是否自动唤起 PM 取决于宿主环境是否提供 automation / monitor / webhook。没有宿主唤醒能力时，默认用 `--once` 或低频读取 log tail，仍比前台反复巡检节省上下文。
- `STATUS.json` 只记录 PM 决策必需的结构化信号，详细实现说明继续写 `RESULT.md` 和 `PATCH_SUMMARY.md`。

## 8. 收口

worker 完成后：
1. 检查 `git status --short`、`git diff --check main...HEAD`、PR diff 范围。
2. 需要 review 时交叉审阅，分支作者不审自己的 PR。
3. 合并、push、PR 编号写入 commit、Issue 关闭等动作遵循 `git-workflow`。
4. 若 PM review 发现问题，优先通过 tmux / agent view / inbox 给原 worker 发送 review correction；worker 应追加修复 commit、重新运行验证并更新 PR，不由 PM 默认代写。
5. PM 复核 correction commit、验证结果和 PR diff 后，再决定是否进入 merge。
6. 合并后清理 worktree/session：

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
- `config/claude-provider-settings.example.json`：Claude Code 第三方 API provider settings 模板。
- `references/checkpoint-files.md`：`STATUS.json`、`RESULT.md`、`PATCH_SUMMARY.md` 的字段和模板。
- `references/parallel-lessons.md`：tmux/Agent Teams 实战坑点。
- `references/legal-domain-templates.md`：法律项目拆解样例。

官方文档：
- Claude Code agent view: `https://code.claude.com/docs/en/agent-view`
- Claude Code worktrees: `https://code.claude.com/docs/en/worktrees`
- Claude Code CLI usage: `https://code.claude.com/docs/en/cli-usage`
- Claude Code checkpointing: `https://code.claude.com/docs/en/checkpointing`

脚本：
- `scripts/pm-monitor.sh`：自动 PM 巡检脚本，保留 checkpoint 文件、Agent Teams inbox、tasks、Git SHA、PR 状态、tmux session 多维监控。
- `scripts/terminal-split.sh`：多终端分屏/新标签辅助，保留 iTerm2、Kitty、WezTerm、Warp、Ghostty、Zed、Terminal.app 支持。

模板：
- `templates/worker-prompt.md`：worker bootstrap 和完整派发 prompt 模板。
- `templates/checkpoint-status.json`：`STATUS.json` 模板。
- `templates/checkpoint-result.md`：完成/失败结果摘要模板。
- `templates/checkpoint-patch-summary.md`：PR review 用 diff 摘要模板。
