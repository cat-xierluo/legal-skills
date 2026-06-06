---
name: multi-agent-orchestration
description: 当用户要求你并行推进多个任务、一次性开多个 worker/agent 同时工作、用 tmux 启动多个独立 session、防止 PM 直接实现逃逸、或者你作为 PM 需要拆解并派发任务给多个独立 worker 时使用。触发词包括"并行推进""开多个""同时推进""派 worker""多 agent 并行""开 worker""tmux 启动""独立 session""防逃逸""分派任务""一起做"。不要用于单个短任务、跨平台任务状态管理、或 Git 分支/提交/PR/merge 安全规则。
license: MIT
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.16.1"
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

优先级由项目规则决定。若用户或项目明确要求使用 tmux / 独立 session / 开 worker，进入防逃逸门禁。

### 2.1 防逃逸门禁

强制 session 触发条件：
- 用户明确说 `tmux`、`独立 session`、`开 worker`、`多 Agent 并行`、`你做 PM / orchestrator`、`不要你直接写`，或项目规则要求 tmux / 独立 session。
- 任务需要独立额度、长上下文、后台持续运行、人工可接管，或同时推进 2 个以上本地 worker。

触发后，PM 在任何业务实现前必须完成启动门禁：
1. 创建或确认隔离 worktree、语义分支和 Session Context 路径。
2. 启动 tmux session；Claude 官方 `--worktree --tmux` 可作为 Claude 专用等价入口。
3. 用 `tmux has-session` / `tmux list-sessions` / `claude agents --json` 验证 session 存活，并确认 pane cwd 或 agent cwd 指向目标 worktree。
4. 给 worker 发送 Bootstrap-only prompt 或 Full worker prompt，prompt 必须包含 Branch、Worktree、Session Context、Runtime Profile、Allowed files、Forbidden files 和验证命令。
5. 在 1-2 分钟内确认 `STATUS.json` 出现；若未出现，只能发送 checkpoint-only 纠偏或重启 worker，不得直接接管业务实现。

降级规则：
- 显式要求 tmux 时，Agent Teams、Subagent、PM 直接处理都不是等价替代；除非用户明确同意降级。
- 显式要求独立 session 但未指定 tmux 时，默认使用 tmux；Claude 官方 `--worktree --tmux` 可用。Agent view / Agent Teams 只有在能证明独立后台会话、独立 cwd/worktree 和可巡检状态时才可替代。
- 门禁失败时，PM 必须报告阻塞和失败点；允许直接修改的仅限 worker prompt、Skill 文档、监控脚本或本地协作配置等编排层文件。
- 若 PM 触发例外直接处理业务代码，最终汇报必须写明例外原因、未使用 session 的具体门禁失败点和用户是否批准降级。

### 2.2 角色与后端

先分清角色，再选择后端：

| 角色 | 职责 | 可由谁担任 |
|------|------|------------|
| PM | 读取任务源、分组、启动 worker、巡检、验收、合并收口 | 当前 Codex、Claude Code、OpenCode 或其他主会话 |
| Worker | 在指定 worktree/branch 内完成限定任务 | Claude Code、Codex、OpenCode、自定义 CLI、shell 脚本、未来 ACP agent |
| Reviewer | 检查 diff、测试、范围和风险 | PM、另一个 worker、code-review subagent |

PM 代理纪律：
- 如果用户明确要求当前会话做 PM / orchestrator / 多 Agent 编排，PM 默认不直接写业务代码；若同时触发 §2.1，必须先通过启动门禁。
- PM 的核心价值是 token efficiency、模型/额度路由、多线程推进、范围控制和验收收口；实现任务优先派给 worktree worker、独立 CLI session、Agent Teams 或 Subagent。
- PM 可以直接改代码的例外：任务极小且无并行价值、用户明确要求 PM 直接做、worker 连续纠偏失败且只剩窄范围收口、或需要立即修复 PM 自己生成的 orchestration 文档/配置。显式 tmux / 独立 session 要求下，这些例外必须先取得用户确认或记录门禁失败。
- PM 如果越过例外直接下场改代码，应在最终汇报说明原因；常规实现应通过 worker 产物、PM 纠偏和 PR review 完成。

后端选择规则：
- 当前主会话是什么不重要；默认“谁启动编排，谁就是 PM”。
- 需要通过第三方 Anthropic-compatible API 启动 Claude Code 时，worker backend 选 Claude Code；这是 Claude Code worker 的默认额度模式。
- 只有用户明确要走 Claude 订阅/OAuth 时，才使用 `claude-oauth-*` profile，并清理第三方 provider 环境变量。
- 需要消耗 Codex / OpenAI 额度或使用 Codex 配置时，worker backend 选 Codex。
- 需要消耗 OpenCode 已配置的 provider/model，或要使用 OpenCode 的 `opencode run` / `opencode acp` 能力时，worker backend 选 OpenCode。
- 其他 Agent 只要能用一行命令启动，并能在指定 cwd 读写文件，也可作为 custom CLI worker。
- 需要稳定进程生命周期和人工接管时，优先 `tmux + worktree`；触发 §2.1 时，`tmux + worktree` 是默认执行层，不是可静默跳过的建议。
- ACP 只在 adapter 已稳定、能输出结构化状态时启用；没有 adapter 时不要为了协议增加不确定性。

环境/profile 纪律：
- PM 启动 worker 时必须显式写 `Runtime Profile`、settings/profile 路径、模型来源和关键环境变量处理方式，不假定 Claude Code、Codex、OpenCode 共享同一套 shell 环境。
- Claude Code 第三方 API provider profile 要保留 `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / 默认模型映射；不要套用 OAuth 的清理命令。
- Claude Code 订阅/OAuth profile 才清理第三方 provider 环境变量，避免误走外部 API。
- Codex / OpenAI worker、OpenCode worker 和 custom CLI worker 使用各自 profile；不要把 Anthropic provider 环境变量当作通用 worker 环境。
- Worker bootstrap 必须把 `which claude/codex/opencode`、版本号、cwd、关键 profile 名和 `node/npm/python/cargo` 等运行信息写入 `STATUS.json`，便于 PM 判断“环境不一样”是否影响任务。

## 3. 标准流程

1. **读任务源与项目配置**：若项目提供 `.claude/orchestration.config.json` 或等价配置，先读取 trunk、任务源、验证命令、可复制配置和 hook 边界；再用 `cross-agent-coordination` 判断可执行项、依赖和归属。
2. **先分组**：不要默认一个 Issue 一个 worker。文件范围重叠、同一章节/模块、存在依赖链的任务应同组顺序执行。
3. **判定并行安全**：只有文件范围清晰、无共享迁移/锁文件/schema、验收标准独立时才拆成多个 worktree 并行。
4. **判定是否触发防逃逸门禁**：只要用户或项目明确要求 tmux / 独立 session / 开 worker，按 §2.1 执行；门禁未通过前不写业务代码。
5. **选择 worker backend 和 runtime profile**：按任务复杂度、当前额度、模型偏好和是否需要独立进程，选择 Claude Code / Codex / OpenCode / custom CLI / shell / ACP。
6. **PM 创建隔离环境**：默认由 PM 创建 worktree、分支和 session context 目录，再把路径交给 worker；只有 Claude Code 官方 Agent Teams / agent view 明确使用自身 `--worktree` 能力时，才允许由 Claude Code 创建，但 PM 仍要验收分支、路径和隔离状态。
7. **启动 worker 并验证门禁**：给每个 worker 明确目标文件、允许修改范围、验证命令、session context 目录、提交和 PR 要求；确认 session 存活、cwd/branch 正确、`STATUS.json` 出现或已发送 bootstrap correction。
8. **PM 巡检**：优先查看 `.claude/agent-sessions/<session-id>/STATUS.json`、`RESULT.md`、`PATCH_SUMMARY.md`、git status、commit/PR 状态；Claude 官方 Agent Teams 则优先读取 `~/.claude/teams/<team>/` 和 `~/.claude/tasks/<team>/`，`claude agents --json`、tmux pane 或 agent view 作为兜底观察。发现偏题、阻塞、范围扩大或无阶段性提交时介入。
9. **PM 验收而非代写**：PM 对 worker 结果做范围检查、测试复核和 review；发现问题优先发纠偏指令或派给 reviewer/另一个 worker，不默认自己改业务代码。
10. **收口**：worker 提交并开 PR 后，PM 做范围检查、触发 review、按 `git-workflow` 合并和清理。

### 3.1 Wave-Based Orchestration

Wave 是在同一 base ref、同一批冲突假设下启动的一组并行 worker。它用来记录“本项目已经并行推进过几轮”、控制并发风险，并让 PM 在每轮结束后复盘 provider/model 表现。

Wave 启动前，PM 必须写清：
- `wave_id`、base ref、目标、worker 清单、每个 worker 的分支/worktree/session。
- 每个 worker 的类型：`ui-wiring`（低风险 UI 接线）、`contract-extension`（共享契约/依赖变更）、`tauri-command`（Rust/Tauri/本机依赖）、`docs/research`、`custom`。
- runtime profile / provider / model / settings/profile 路径 / 额度来源 / 并发槽位。超过 3-4 个 worker 时，不要压在单一 API provider 或同一个 settings 文件上；应跨 Claude provider、Codex/OpenAI、OpenCode、local/OSS 等 profile 分流。
- 共享风险：`package.json`、锁文件、`src-tauri/`、`src/shared/`、全局布局、DEC 编号或同一模块入口。
- 预期 PR 数、收口顺序、下一 Wave 进入条件。

并发数量不是固定 3 个。文件范围独立、验证命令独立、无共享契约冲突时，默认目标可提高到 4-6 个 worker；纯文档、翻译、i18n、互不重叠 UI 接线可以更多。涉及共享依赖、锁文件、Tauri command、全局布局、DEC race 或同一模块入口时，降到 1-3 个并按依赖顺序推进。

Provider slot 分配是 PM 的显式规划，不是脚本自动猜测：
- 一个 slot 表示一条可并发额度 lane：`backend + settings/profile path + provider + model + max_concurrency`。
- Claude Code 第三方 provider 用具体 settings 文件区分，例如 `config/minimax.settings.json`、`config/glm.settings.json`；真实 settings 文件保持本地 ignored，不提交。
- Codex 用 Codex profile / model 区分；OpenCode 用 `provider/model` profile 区分；custom worker 写明实际命令来源。
- 默认同一 provider/settings 文件最多放 3 个 worker；只有低风险任务且上一 Wave 表现稳定时才放到 4 个。需要 5-6 个 worker 时，优先拆到第二 provider 或 Codex/OpenCode/local profile。
- 高风险任务（共享契约、Tauri/Rust、本机依赖、锁文件）优先给上一 Wave 指令遵循和验证表现最好的 profile，且每个高风险共享域通常只开 1 个 worker。
- 如果本机只有一个可用 settings/profile，不要为了凑人数启动 5-6 个 worker；把并发 cap 降到 3-4，剩余任务进入下一 Wave。

6-worker 示例：

| Worker | 任务风险 | Backend | Settings/Profile | Slot |
|--------|----------|---------|------------------|------|
| W1 | 高 | Claude Code | `config/minimax.settings.json` | `minimax-1` |
| W2 | 中 | Claude Code | `config/minimax.settings.json` | `minimax-2` |
| W3 | 低 | Claude Code | `config/glm.settings.json` | `glm-1` |
| W4 | 低 | Claude Code | `config/glm.settings.json` | `glm-2` |
| W5 | 文档/研究 | Codex | `codex:<profile>` | `codex-1` |
| W6 | 重复性低风险 | OpenCode/custom | `<provider/model or command label>` | `opencode-1` |

Wave 收口时，PM 记录每个 worker 的 `merged` / `done-unmerged` / `blocked` / `deferred` / `restarted`，并评估模型/provider 表现：Isolation Gate、STATUS 心跳、commit 节奏、范围遵循、验证通过率、review 修复次数、diff 质量、阻塞/幻觉/环境误判。下一 Wave 根据该评估调整任务分配：高风险任务给指令遵循和工程可靠性更好的 profile，低风险重复任务给成本或吞吐更优的 profile。

### 3.2 Goal-Driven Multi-Wave Loop

Orchestration Goal 是 PM 层目标循环，用来让多轮 Wave 在条件满足前持续推进。它不把所有任务交给单个 worker；PM 仍按 Wave 从任务源取下一批安全可并行项，worker 仍只执行自己的窄范围任务。

启动 Goal Loop 前，PM 必须写清 Goal Contract，模板见 `templates/orchestration-goal.md`：
- 任务源：如 `docs/TASKS.md`、GitHub Issues、项目配置中的 issue file。
- 成功条件：例如目标范围内没有可执行 pending task、所有已启动 worker 都进入 `merged` / `done-unmerged` / `blocked` / `deferred`，主干验证通过，文档已同步。
- 自主级别：`plan-only`（只规划下一 Wave）、`auto-launch`（可自动开下一 Wave）、`auto-review`（可自动复核 worker 结果）、`auto-merge`（在项目规则允许时按 `git-workflow` 合并）。
- 上限：最大 wave 数、每轮最大 worker、总 worker、预算/时间、provider 并发槽位。
- 继续条件和停止条件。

PM 可在支持的宿主中使用 Claude Code / Codex 的 `/goal` 来包住 PM loop，但 `/goal` 只负责让 PM 持续执行循环，不替代本 Skill 的 worktree、tmux、checkpoint、review 和 merge 门禁。Goal prompt 必须写明“PM 不直接实现业务代码；实现仍由 worker 完成”。

每轮 Wave 收口后，PM 按以下顺序决定是否自动继续：
1. 读取任务源，关闭已完成项，识别可执行 pending task、依赖、文件范围和共享风险。
2. 确认当前 Wave 没有未处理的 failed/blocked worker、未验收 PR、base drift、冲突、主干验证失败或敏感/破坏性操作。
3. 根据上一 Wave 的 provider/model 评估调整并发：干净通过可维持或小幅增加，出现冲突、范围越界、验证失败或限流则降并发。
4. 若仍有可安全并行的任务，创建下一 Wave；若只剩高冲突/高风险任务，降为 1-2 个 worker 或停下请求用户确认。
5. 若成功条件满足，写 final goal summary 并停止。

自动继续条件：
- 上一 Wave 的 worker 均为 `merged`、`done-unmerged`、`deferred` 或明确 `blocked` 且不会影响下一 Wave。
- 所有合并动作已按 `git-workflow` 处理，base ref、本地主干和远端主干一致或已明确记录差异。
- 必需验证通过；跳过的验证有清楚原因且不影响下一 Wave。
- 下一批任务的 allowed/forbidden files 清晰，且没有共享锁文件、schema、全局布局或 DEC 编号 race 未解决。
- provider 并发槽位足够，且没有连续限流、长延迟或 worker 指令遵循退化。

必须停止并汇报的条件：
- 任一 worker `failed`、`blocked` 且影响下一 Wave，或连续两次纠偏无效。
- PR 冲突、base drift、主干验证失败、测试不稳定、merge 权限不足或 GitHub/CI 状态不明。
- 下一批任务需要用户产品判断、破坏性文件操作、联网敏感处理、密钥/隐私处理或项目规则未授权的自动合并。
- 任务源含糊、依赖未满足、文件范围高度重叠，或只剩共享契约/锁文件/Tauri command 等高风险任务。
- 达到 Goal Contract 的 wave、worker、时间、预算或 provider 上限。

### 3.3 Optional Project Config

项目可放置 `.claude/orchestration.config.json`，模板见 `templates/project-config.json`。该配置只声明项目默认值，不替代 PM 判断，也不允许静默执行破坏性动作。

配置可声明：
- trunk/base ref、任务源、默认 worktree/session context 路径。
- 按 worker type 拆分的验证命令。
- provider slot 默认计划，供 Goal/Wave 启动清单引用。
- 可复制到 worktree 的非敏感配置文件，例如 `.npmrc.example` 或只读模板。
- post-create / pre-merge hook 命令。

配置安全规则：
- 永远不要默认复制 `.env`、真实 settings、token、key、cookie、证书或账号凭证。
- `allowed_config_copy` 只允许非敏感文件；`forbidden_config_copy` 命中时必须停止并报告。
- hook 默认只是声明。PM 只有在项目规则或用户明确授权时才运行；运行前应展示命令，必要时先 dry-run。
- `spawn-worker.sh` 不自动读取项目配置、不自动复制配置、不自动执行 hook，避免把可选约定升级成隐式副作用。
- 若配置缺失或字段不清楚，PM 回到 Skill 默认值：trunk=`main`、不复制配置、不跑 hook、只使用 worker prompt 明确列出的验证命令。

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
.claude/agent-sessions/legal-ch01/METADATA.json
.claude/agent-sessions/legal-ch01/STATUS.json
.claude/agent-sessions/legal-ch01/RESULT.md
.claude/agent-sessions/legal-ch01/PATCH_SUMMARY.md
```

Claude Code 官方 Agent Teams 是另一套机制：团队配置在用户目录 `~/.claude/teams/<team-name>/config.json`，任务状态在 `~/.claude/tasks/<team-name>/`，inbox 在 `~/.claude/teams/<team-name>/inboxes/`。使用官方 Agent Teams 时优先读写这些官方状态源；不要在项目里自造 `.claude/teams/` 来冒充官方 team。

`.claude/agent-sessions/` 是 PM 巡检状态，不属于业务 diff。PM 和 worker 都必须确认它不进入 commit / push / PR；需要时由 PM 在对应 worktree 的本地 exclude 中忽略。

## 5. Worker Prompt 模板

Worker prompt 应像启动 subagent 一样给足上下文：任务来源、验收标准、允许文件、禁止文件、验证命令、checkpoint 协议、隔离自检和 PM 纠偏协议都要写清。不要只给一句“实现某功能”，否则 worker 容易把环境、依赖或相关技术债扩展成自己的任务。

模板放在 `templates/worker-prompt.md`，包含两个可复制段落：
- Bootstrap-only prompt：只创建 `STATUS.json`，适合高延迟 provider 或 high-effort 模型的第一条消息。
- Full worker prompt：按 Context / Background / Mission / Scope / Deliverables / Process / Verification / Autonomy / Out of Scope / PM Correction 组织，接近派发 subagent 时的写法。

对高延迟 provider 或 high-effort 模型，优先用两段式启动：第一条消息使用 Bootstrap-only prompt 创建 `Session Context/STATUS.json` 并回报 runtime；PM 确认 checkpoint 后，再发送 Full worker prompt。这样能避免 worker 在长思考前没有可观测状态。

## 6. 启动方式

默认工具面保持收敛：
- `check-dependencies.sh`：新机器或启动 Wave 前做一次 preflight。
- `render-runtime-profile.sh`：为每个 worker 渲染 backend/settings/profile/model/slot 和启动命令。
- `spawn-worker.sh`：创建 worktree、Session Context 和 tmux session。
- `sentinel.sh`：每个 worker 一个，PM 用 `run_in_background=true` 启，worker 终态时唤起 PM（见 §7.2）。
- `pm-monitor.sh`：多 worker/Wave 巡检；单 worker 或宿主唤醒才用 `wait-worker.sh`。

项目配置模板见 `templates/project-config.json`。PM 可以把其中的 trunk、验证命令和 provider slot 复制到本轮 Goal/Wave 计划，但脚本不会自动套用该配置。

其余脚本只在对应场景使用：`worktree-status.sh` 做只读总览，`clean-worktree.sh` 做 dry-run 清理，`smoke-tmux-worker.sh` / `lint-wait-script.sh` 只做 Skill 自测，`terminal-split.sh` 只是可选可视化辅助，不属于默认启动路径。

默认用 `scripts/spawn-worker.sh` 创建 worktree、Session Context 和 tmux session；它只负责隔离和启动，PM 仍必须发送 `templates/worker-prompt.md` 并确认 `STATUS.json`。不同 backend/profile 的启动命令可先用 `scripts/render-runtime-profile.sh` 生成，减少手写环境差异。

```bash
eval "$(bash scripts/render-runtime-profile.sh \
  --backend claude-code \
  --runtime-profile minimax \
  --api-provider minimax \
  --model claude-sonnet-4-5 \
  --provider-slot minimax-1 \
  --settings config/minimax.settings.json)"

bash scripts/spawn-worker.sh \
  --project /path/to/repo \
  --branch docs/ch01-agent-intro \
  --session legal-ch01 \
  --worker-backend "$WORKER_BACKEND" \
  --runtime-profile "$RUNTIME_PROFILE" \
  --api-provider "$API_PROVIDER" \
  --model "$MODEL" \
  --provider-slot "$PROVIDER_SLOT" \
  --verify-cmd 'npm run typecheck' \
  --command "$WORKER_COMMAND"
```

启动后必须通过最小门禁：`tmux has-session` 存活、pane cwd 指向 worktree、`git branch --show-current` 等于目标分支、`Session Context/METADATA.json` 已记录 base/runtime/verification、`Session Context/STATUS.json` 在 1-2 分钟内出现。失败时停止 session 或发送 bootstrap correction，不要在 PM 主目录继续实现。

常用 worker command：
- Claude Code 第三方 provider：`claude --settings <local-provider.settings.json> --permission-mode auto`。真实 settings 不提交；模板见 `config/claude-provider-settings.example.json`。
- Claude Code 订阅/OAuth：`env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_BASE_URL claude --permission-mode auto`。
- Claude Code 批处理：`claude --settings <settings> -p --output-format stream-json --permission-mode acceptEdits < /tmp/task.prompt.md`。
- Codex：`codex exec -a never -s danger-full-access - < /tmp/task.prompt.md`。
- OpenCode：`opencode run --format json --model <provider/model> "$(cat /tmp/task.prompt.md)"`，或交互式 `opencode --model <provider/model>`。
- 自定义 CLI：任何能在指定 cwd 运行、接收 prompt、落盘 checkpoint 的命令。

**不要设 `--max-turns`**：PM 重点是检测 worker 是否真在推进，而不是限制 turn 数。长任务通过 `STATUS.json.updated_at`、阶段性 commit、`pm-monitor.sh` stale 事件和 PM 纠偏控制。

Claude Code agent view / 官方后台会话可作为 Claude 专用后端：`claude agents`、`claude agents --json`、版本支持时的 `--worktree --tmux`、`--bg` 或 `/bg`。使用前以本机 `claude --help` / `claude agents --help` 为准；只有能证明独立 cwd/worktree、可巡检状态和可接管会话时，才可替代 tmux。

Agent Teams 适合 Claude Code 团队式协作；仍要使用 worktree 隔离并把 `workdir` 指向带来源前缀的 worktree。ACP 只在 adapter 已稳定、能输出结构化状态时启用。Subagent 仅用于轻量、边界窄、输入少的任务；需要长时间写作、独立提交 PR 或跨大量材料整合时升级为 tmux / agent view / Agent Teams。

## 7. 巡检与介入

PM 巡检信号：
- worktree 是否有文件落盘、commit、PR。
- `.claude/agent-sessions/<session-id>/METADATA.json` 是否记录 base ref、runtime profile、provider slot、验证命令和 PR 占位。
- `.claude/agent-sessions/<session-id>/STATUS.json` 是否更新，是否报告 blocked / needs_input / done。
- `.claude/agent-sessions/<session-id>/RESULT.md` 和 `PATCH_SUMMARY.md` 是否存在，摘要是否足够 PM 不读完整日志也能验收。
- tmux pane 是否长时间只读材料、等待确认、偏题联网、反复规划不执行。
- worker 是否扩大改动范围或触碰共享文件。
- PR diff 是否只覆盖声明范围。

介入规则：
- 有持续输出、checkpoint 更新或文件在增长时继续等待。
- 启动后 1-2 分钟仍没有 `Session Context/STATUS.json` 时，先发送 checkpoint-only 纠偏；仍无响应时中断当前思考并重发 bootstrap 指令，不直接接管实现。
- 长时间无落盘但仍在规划时，先发送更窄的“先写目标文件”命令。
- worker 跳过 10-15 分钟 STATUS 心跳或 30-60 分钟阶段性 commit 时，PM 主动发送纠偏，要求立刻更新 STATUS 或提交当前已验证阶段；5 分钟内仍无 STATUS/commit/文件进展变化时，升级为重启 worker、派 reviewer 或 PM 窄范围收口。
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

完整字段见 `references/checkpoint-files.md`，可复制模板见 `templates/checkpoint-status.json`、`templates/checkpoint-result.md` 和 `templates/checkpoint-patch-summary.md`。PM 默认只读这些 checkpoint 和最终 diff，不定时拉完整日志。

可选自动 PM 监控脚本（保留 Agent Teams inbox、任务状态、Git SHA、PR 状态和 tmux session 多维巡检能力）：

```bash
bash scripts/pm-monitor.sh \
  --project /path/to/repo \
  --team-dir ~/.claude/teams/team-name \
  --tasks-dir ~/.claude/tasks/tasks-uuid \
  --claude-agents-cwd /path/to/repo \
  --wave-id wave-5 \
  --commit-stale-threshold 1800 \
  --progress-stale-threshold 1800 \
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
- 单个 worker 的只读总览用 `scripts/worktree-status.sh`；清理用 `scripts/clean-worktree.sh`，默认 dry-run，真正删除必须显式 `--execute`。

### 7.1 主动等待与宿主唤醒

`scripts/wait-worker.sh` 是单 worker 等待器，不替代 `pm-monitor.sh`。它主读一个 `STATUS.json`，在 `done`、`failed`、`blocked` 或 `stopped` 时退出并输出 `RESULT.md` / `PATCH_SUMMARY.md` 路径。适合把“worker 完成时通知 PM”接到不同宿主。

状态源分层：
- `METADATA.json` 是 PM 启动时写入的静态上下文，记录 base/runtime/provider/verification，不作为完成判定。
- `STATUS.json` / `RESULT.md` / `PATCH_SUMMARY.md` 是完成、阻塞、验证和收口的主协议。
- `tmux capture-pane` 是诊断窗口，只在 checkpoint 缺失、过期、终态或显式要求时读取尾部输出。
- 不用 tmux pane 文本判断任务完成；完成标准仍是 checkpoint、git diff、验证和 PR 状态。

Claude Code PM：
- Bash background/run-in-background 只能让等待器在后台运行，不保证触发或唤醒当前 PM / agent session；多 worker 同时等待时尤其可能没有任何完成消息返回。
- 不要把 background Bash 当作可靠完成通知机制。它最多作为日志写入器或人工可查看的后台 job；PM 仍必须靠 `STATUS.json`、`pm-monitor.sh --log-file`、`wait-worker.sh --once`、tmux/agent view 显式巡检来收口。
- 单 worker 可临时用 background Bash 跑 `wait-worker.sh`，但启动时必须同时记录 log 文件或保留可查询命令；多 worker / Wave 默认使用 `pm-monitor.sh --log-file`，不要为每个 worker 启一个 background wait 并期待宿主逐个回调。
- **限定条件例外**：§7.2 描述的 Sentinel 模式是本规则的"限定条件下可工作变体"——单 worker 单 sentinel、`run_in_background=true` 启、harness 100% re-invoke 实测验证（2026-06-05 spike）。Wave 6 启用 sentinel 之前仍按上述保守判断走。

  ```bash
  bash scripts/wait-worker.sh \
    --worktree .claude/worktrees/tmux-ch01-agent-intro \
    --session legal-ch01 \
    --tmux-session legal-ch01 \
    --interval 30
  ```

Codex PM：
- Codex CLI 的后台 shell 不会自动把完成事件推回当前对话；不要假定它等价于 Claude Code `run_in_background`。
- 在 Codex App 中，优先把 `wait-worker.sh --once` 接到当前 thread 的 heartbeat automation；完整 prompt 见 `templates/codex-heartbeat-wait.md`。创建、修改或删除 automation 时必须先查找并使用 `automation_update` 工具，不手写 raw RRULE。
- 没有 heartbeat/automation 能力时，Codex PM 使用 `pm-monitor.sh --once` 或 `wait-worker.sh --once` 低频手动巡检；长任务仍用 `pm-monitor.sh --log-file` 持续记录事件。

`wait-worker.sh` 的职责是等一个 worker 到终态；它输出终态，不负责唤醒宿主。多 worker、PR 状态、git SHA、gate 和 stale 事件仍由 `pm-monitor.sh` 负责。

### 7.2 Sentinel bash 模式（事件驱动 PM 唤醒）

> 适用：Wave 6 之后，每个 worker 配套启一个 sentinel，PM 由 harness task-notification
> 事件驱动地唤醒，零 idle token 消耗，保留多轮纠偏能力。设计依据见
> `references/sentinel-design.md`；DEC-031 supersede DEC-030 的限定条件判断。

**模式**：每个 worker 配一个 `scripts/sentinel.sh` 进程。Sentinel 轮询 `STATUS.json`，
读到 `done | failed | blocked | stopped` 时 capture tmux pane tail、`tmux kill-session`、
`exit`。Sentinel 由 PM 用 `run_in_background=true` 启，exit 触发 harness
task-notification → PM 被 re-invoke。

**PM 端调用模式**：每 worker 两次 Bash 调用：

```bash
# 1) Foreground: 创建 worktree + 启动 worker + 拿 gate 验证
bash scripts/spawn-worker.sh \
  --project /path/to/repo \
  --branch docs/ch01-agent-intro \
  --session legal-ch01 \
  --with-sentinel \  # 仅打印 SPAWN_WORKER_SENTINEL_CMD，不在内部启
  --command "$WORKER_COMMAND"

# 2) Background: sentinel 事件驱动 wake
# 从 spawn-worker.sh 输出里复制 SPAWN_WORKER_SENTINEL_CMD 那行
bash scripts/sentinel.sh \
  --status-file .claude/worktrees/tmux-docs-ch01-agent-intro/.claude/agent-sessions/legal-ch01/STATUS.json \
  --tmux-session legal-ch01 \
  --poll-interval 5 \
  --max-wait 7200
# ↑ 用 Bash run_in_background=true 启
```

**为什么不在 spawn-worker.sh 内部启 sentinel**：
- `spawn-worker.sh` 是 fg 工具，sentinel 是 bg 工具，职责分离
- 避免单 Bash 调用内 fork 多个 background（auto mode 拒率更高）
- PM 显式 opt-in 收 sentinel 通知（`run_in_background=true`）是 harness re-invoke 的前提

**Sentinel 事件命名空间**（独立于 `WAIT_WORKER_*`）：

| 事件 | 触发 |
|------|------|
| `SENTINEL_START` | 启动时 |
| `SENTINEL_PENDING` | STATUS.json 缺失 |
| `SENTINEL_PANE_TAIL` | capture pane 前（best-effort）|
| `SENTINEL_TERMINAL` | 检测到 `done` / `failed` / `blocked` / `stopped` |
| `SENTINEL_TMUX_KILLED` / `SENTINEL_TMUX_GONE` | kill tmux 之后 |
| `SENTINEL_TIMEOUT` | `--max-wait` 到了还没看到终态 |

**PM 收到 notification 后的标准动作**见 `templates/pm-sentinel-response.md`：
- Exit 0 = done：读 RESULT/PATCH_SUMMARY，跑 verify，review，merge
- Exit 2 = failed/blocked/stopped：读 STATUS.issues 决定 restart / block / defer
- Exit 124 = timeout：检查 worker tmux + STATUS 状态，纠偏或重启
- Exit 64 = usage error：检查 `--status-file` / `--tmux-session` 与 spawn-worker 一致性

**降级路径**：如果 sentinel 没启起来（auto mode 拒 / SIGKILL / 参数错），PM 回到 §7.1
行为：单 worker 用 `wait-worker.sh --once`，多 worker 用 `pm-monitor.sh --log-file`。
降级是 graceful 的，不是失败。

**调优建议**：
- `--poll-interval`：默认 5s。worker 单次 thinking 短时降到 1s，长时保持 5s
- `--max-wait`：默认 7200s（2h）。长 worker 拆 sub-task，每个 sub-task 自己的 max-wait
- `--keep-tmux-on-terminal`：review 阶段不杀 tmux，便于 PM tmux capture-pane 看 worker 收尾
- `--pane-tail-lines 0`：不需要 pane 快照时关掉，少 1 个 tmux capture-pane 调用

**已知不覆盖**：
- 多 sentinel 对单 worker 去重：PM 行为层保证 1:1
- Codex / OpenCode 路径：暂未实测，Codex 走 `templates/codex-heartbeat-wait.md`
- 高频 polling 风暴：worker 集群大、polling 间隔 < 2s 时单 worker CPU 可能略高，按需调

## 8. 收口

### 8.0 PM 在 Worker 提 PR 后的持续同步

worker 提 PR 不是 PM 收口完成的信号。从提 PR 到合并之间，PM 必须做两件事避免外部抢跑：

1. **提 PR 之后立即跑 mergeable 检查**：

   ```bash
   gh pr view <N> --json state,mergeable,mergeStateStatus,baseRefName,headRefName
   ```

   - `mergeable=CONFLICTING` / `mergeStateStatus=DIRTY` / `baseRefName` 落后：base 已被 doc-curator 或其他 PR 抢跑。立即按 `git-workflow` 的「base 落后 / 冲突处理」决策表（update branch vs rebase vs close-and-reopen）处理。
   - `mergeable=MERGEABLE` 且 base 是最新：进入 review 流程。

2. **PM 本地 main 立即 push**：
   - PM 在主目录 commit docs / DEC 之后**立即** `git push origin main`，避免本地与 origin/main drift。
   - drift 后 push 报 non-fast-forward，squash merge 引入的"内容相同但 history 不同"会让 git 误判冲突，恢复成本高。
   - 看到 origin/main 领先本地时，先 `git fetch origin` + `git switch -C main origin/main`（不是 `git pull`，squash commit 不会自动 ff），再继续 PM 工作。

worker backend 选择（subagent / tmux / Agent Teams）见 §2.1。

### 8.1 收口标准步骤

worker 完成后：
1. 检查 `git status --short`、`git diff --check main...HEAD`、PR diff 范围。
2. 需要 review 时交叉审阅，分支作者不审自己的 PR。
3. 合并、push、PR 编号写入 commit、Issue 关闭等动作遵循 `git-workflow`。
4. 若 PM review 发现问题，优先通过 tmux / agent view / inbox 给原 worker 发送 review correction；worker 应追加修复 commit、重新运行验证并更新 PR，不由 PM 默认代写。
5. PM 复核 correction commit、验证结果和 PR diff 后，再决定是否进入 merge。
6. 合并后清理 worktree/session，先 dry-run 再显式执行：

```bash
bash scripts/clean-worktree.sh --project /path/to/repo --branch docs/ch01-agent-intro --session legal-ch01
bash scripts/clean-worktree.sh --project /path/to/repo --branch docs/ch01-agent-intro --session legal-ch01 --execute
```

## 9. 依赖

依赖按模式分层；只读文档不需要安装任何工具。首次在新机器上启动 worker 前，先运行：

```bash
bash scripts/check-dependencies.sh
bash scripts/check-dependencies.sh --backend claude-code --backend codex --check-gh
```

### 最小本地执行依赖

| 依赖 | 安装方式 |
|------|----------|
| `git` | 通常随开发环境提供 |
| `bash` | 常规脚本需要 bash；`pm-monitor.sh` 需要 bash 4+ |
| `jq` | macOS: `brew install jq`<br>Linux: `sudo apt-get install jq` |
| `tmux` | macOS: `brew install tmux`<br>Linux: `sudo apt-get install tmux` |

常见 Unix 工具如 `awk`、`sed`、`grep`、`find`、`stat`、`date`、`mktemp` 通常由系统提供；日期解析已兼容 macOS/Linux。

### 按模式启用的依赖

| 模式 | 依赖 |
|------|------|
| PR / mergeability 巡检 | `gh`，且需要已登录 |
| Claude Code worker | `claude`；第三方 provider 需要本地 settings 文件 |
| Codex worker | `codex` |
| OpenCode worker | `opencode` |
| Codex heartbeat | Codex App automation 能力；创建/修改 automation 必须使用 `automation_update` |
| Claude 官方 agent view / `--worktree --tmux` | `claude`，必要时还需要 `tmux` |

### 可选终端依赖

`scripts/terminal-split.sh` 只在对应终端场景下需要额外工具：Kitty 需要 `kitty @`，WezTerm 需要 `wezterm cli`，macOS GUI 终端自动化依赖 `osascript`，Warp/Ghostty/Zed/Terminal.app 分屏或新标签能力取决于本机应用和辅助功能授权。

完整依赖矩阵见 `references/runtime-dependencies.md`。依赖检查脚本只报告状态，不安装软件、不启动 worker、不改配置。

## 10. 参考

只在需要细节时读取：
- `references/model-selection-matrix.md`：模型与执行模式选择。
- `config/claude-provider-settings.example.json`：Claude Code 第三方 API provider settings 模板。
- `references/runtime-dependencies.md`：按模式拆分的本地依赖矩阵和安装建议。
- `references/checkpoint-files.md`：`STATUS.json`、`RESULT.md`、`PATCH_SUMMARY.md` 的字段和模板。
- `references/parallel-lessons.md`：tmux/Agent Teams 实战坑点。
- `references/agent-teams-troubleshooting.md`：Agent Teams / agent view / Claude 原生 `--worktree --tmux` 后端排障。
- `references/legal-domain-templates.md`：法律项目拆解样例。

官方文档：
- Claude Code agent view: `https://code.claude.com/docs/en/agent-view`
- Claude Code worktrees: `https://code.claude.com/docs/en/worktrees`
- Claude Code CLI usage: `https://code.claude.com/docs/en/cli-usage`
- Claude Code checkpointing: `https://code.claude.com/docs/en/checkpointing`

脚本：
- `scripts/check-dependencies.sh`：检查核心依赖、backend CLI、GitHub CLI 和终端分屏工具。
- `scripts/render-runtime-profile.sh`：按 backend/profile 生成 worker command、prompt context 和 spawn metadata。
- `scripts/spawn-worker.sh`：创建隔离 worktree、Session Context 和 tmux session，并输出启动 gate。
- `scripts/pm-monitor.sh`：自动 PM 巡检脚本，保留 checkpoint 文件、Agent Teams inbox、tasks、Git SHA、PR 状态、tmux session、Wave 和多信号进展监控。
- `scripts/wait-worker.sh`：单 worker 等待器，可接 Claude Code background Bash 或 Codex heartbeat automation。
- `scripts/worktree-status.sh`：单 worker 只读总览，展示 metadata、checkpoint、tmux 和 git 状态。
- `scripts/clean-worktree.sh`：worker session/worktree 安全清理，默认 dry-run，清理前展示 metadata 摘要。
- `scripts/smoke-tmux-worker.sh`：临时 repo 端到端 smoke test；只在修改 Skill 脚本后运行。
- `scripts/lint-wait-script.sh`：wait/monitor/custom wait 脚本 lint；只在修改 wait/monitor 脚本后运行。
- `scripts/terminal-split.sh`：可选可视化辅助，保留 iTerm2、Kitty、WezTerm、Warp、Ghostty、Zed、Terminal.app 支持；默认编排不依赖它。

模板：
- `templates/worker-prompt.md`：worker bootstrap 和完整派发 prompt 模板。
- `templates/orchestration-goal.md`：PM 级连续多 Wave Goal Contract 模板。
- `templates/project-config.json`：可选项目级编排配置模板，声明 trunk、任务源、验证命令、provider slot、非敏感配置复制和 hook 边界。
- `templates/codex-heartbeat-wait.md`：Codex App heartbeat 巡检 prompt。
- `templates/wave-summary.md`：每轮 Wave 收口和 provider/model 评估模板。
- `templates/checkpoint-status.json`：`STATUS.json` 模板。
- `templates/checkpoint-result.md`：完成/失败结果摘要模板。
- `templates/checkpoint-patch-summary.md`：PR review 用 diff 摘要模板。
