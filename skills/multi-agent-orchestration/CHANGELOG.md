# Changelog

## [1.9.1] - 2026-06-03

### Changed
- 将新 worker 的 checkpoint 目录从 `.agent-context/` 调整为 `.claude/agent-sessions/<session-id>/`，复用项目既有 `.claude/` 协作空间；`pm-monitor.sh` 仍兼容读取旧 `.agent-context/`。
- 明确 Claude Code 官方 Agent Teams 的状态源在 `~/.claude/teams/<team>/` 与 `~/.claude/tasks/<team>/`，不要在项目内自造 `.claude/teams/` 冒充官方 team。
- 明确 worktree、分支和 session context 默认由 PM 创建；只有 Claude Code 官方 Agent Teams / agent view 明确使用自身 `--worktree` 能力时，才允许 worker 侧创建隔离环境，PM 仍需验收。
- 将 PM review correction 固化为收口流程：PM review 失败时优先把具体修正发回原 worker，worker 追加修复 commit、更新验证和 PR，PM 再复核。
- 补充环境差异规则：Claude Code provider settings、Claude OAuth/订阅、Codex/OpenAI 和 OpenCode profile 必须分开声明，不默认清理或继承环境变量。

## [1.9.0] - 2026-06-02

### Changed
- 将 PM 从具体产品中解耦：当前 Codex、Claude Code 或其他主会话都可以担任 PM。
- 将 worker backend 抽象为 Claude Code、Codex、OpenCode、shell 和可选 ACP adapter，支持从 Claude Code 启动 Codex/OpenCode worker，或从 Codex 启动 Claude Code/OpenCode worker。
- 补充 runtime profile / 额度路由规则，明确 Claude Code worker 默认走第三方 API provider settings，订阅/OAuth 只作为显式例外。
- 补充 Claude Code 第三方 API provider settings 模式：通过 `--settings /path/to/provider.settings.json` 加载 `ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN` 和默认模型环境变量。
- 将 Claude Code worker 默认额度模式调整为第三方 API provider settings，并新增 `references/claude-provider-settings.example.json` 模板。
- 将 Claude Code tmux worker 默认启动方式调整为交互式后台终端 session；`-p` 仅作为批处理 prompt 的可选模式。
- 将 provider settings 示例调整为 Minimax Anthropic-compatible API 结构，保持 token、base URL、三类默认模型、timeout、thinking tokens 和行为开关一并配置。
- 增加结构化 checkpoint 三件套：`.agent-context/STATUS.json`、`RESULT.md`、`PATCH_SUMMARY.md`，并新增模板参考文档。
- 更新 `pm-monitor.sh`，支持从分支自动定位 worktree、监听 checkpoint 文件变化，并可选通过 `--claude-agents-cwd` 读取 Claude 官方后台 session 状态。
- 补充 Claude Code 官方 agent view / background session 入口：`claude agents`、`claude agents --json`、`--worktree`、`--tmux`，以及版本支持时的 `claude --bg` 和 `/bg`，作为 tmux 之外的 Claude 专用后台会话模式。
- 补充 OpenCode worker 支持：默认用 `opencode run --format json --model <provider/model>`，并将 `opencode acp` 记录为可选 ACP server 候选。
- 补充 custom CLI worker 模板，支持其他可一行命令启动、可在指定 worktree 中运行的 Agent。
- 将 ACP 定位为可选后端：协议层结构化，但默认仍以 `tmux + worktree + checkpoint 文件 + git 状态` 作为稳定执行层。
- 更新 Worker Prompt 模板，加入 PM Host、Worker Backend、Runtime Profile 和 `.agent-context/STATUS.json` / `RESULT.md` / `PATCH_SUMMARY.md` checkpoint 协议。
- 明确用户指定当前会话担任 PM agent 时，PM 默认不直接写业务代码；实现优先委派给 worktree worker、独立 session、Agent Teams 或 Subagent，PM 负责巡检、纠偏、review 和收口。
- 基于 FaroPDF ISS-018 实战补充流程约束：高延迟 provider 可两段式 bootstrap；`.agent-context/` 只作本地 checkpoint，不进入 Git/PR；worker 不应等待 PM 下一步；STATUS 每次写入必须刷新 `updated_at`；窄范围实现默认 low/medium effort。

## [1.8.2] - 2026-06-01

### Changed
- 收口发布包参考文档，只保留模型/执行模式矩阵、实战坑点和法律项目拆解样例。
- 精简法律场景参考，移除未落地的未来模板路径和外部 catalog 设想，明确其只作为本地执行层拆分样例。

### Removed
- 移除已落地或过时的历史平台调研、Agent Teams 优化积压和 Auto PM 蓝图文档，避免与当前 SKILL.md 实现机制重复或冲突。

## [1.8.1] - 2026-05-20

### Changed
- 同步相关 Skill 引用：`cross-agent-collab` 更名为 `cross-agent-coordination` 后，更新任务协调层边界说明和参考文档。

## [1.8.0] - 2026-05-20

### Changed
- 重命名 Skill：`multi-agent-workflow` → `multi-agent-orchestration`，标题改为 Multi-Agent Orchestration，以突出“本地多 Agent 执行编排”而非普通流程说明。
- 同步更新 SKILL.md description 和开篇说明，统一使用“执行编排”表述。
- 同步更新 `cross-agent-coordination` 中对本 Skill 的边界引用。

## [1.7.0] - 2026-05-20

### Changed
- 重命名 Skill：`parallel-agent-workflow` → `multi-agent-workflow`，标题改为 Multi-Agent Workflow，以匹配当前“多 Agent 本地执行编排”的职责边界。
- 优化 SKILL.md frontmatter description，补充正向触发场景和负向边界。
- 补充脚本依赖说明，明确 `pm-monitor.sh` 与 `terminal-split.sh` 的系统依赖和可选终端依赖。
- 同步更新 `cross-agent-coordination` 中对本 Skill 的边界引用。

## [1.6.0] - 2026-05-19

### Changed
- 精简 `SKILL.md` 为执行入口、命名规则、启动方式、巡检和收口规则；复杂细节转交 `references/` 和 `scripts/`。
- 明确任务源由项目配置或项目上下文决定，不在 Skill 中写死固定文件路径。
- 保留 `pm-monitor.sh` 的自动 PM 巡检能力，包括 Agent Teams inbox、tasks、Git SHA、PR 状态和 tmux session 多维监控。
- 保留 `terminal-split.sh` 的多终端分屏能力，包括 iTerm2、Kitty、WezTerm、Warp、Ghostty、Zed 和 Terminal.app。

## [1.5.0] - 2026-05-17

### Added
- 新增从项目任务源形成本地执行计划的通用规则：提取 Issue ID、状态、推进建议、文件/组件、依赖和验收标准。
- 新增 待办事项分组策略：按文件/组件重叠、依赖链、并行安全度和 PR 审查边界决定多个 Issue 是否放入同一 worktree/session。
- 新增 L1/L2/L3 路由说明，明确不是一个 Issue 必然对应一个 session。

### Changed
- `multi-agent-orchestration` 继续只拥有本地执行层；分组计划只服务本轮执行，不成为新的任务状态源。

## [1.4.0] - 2026-05-17

### Changed
- 明确本 Skill 只负责本地 Agent 会话、并行执行、PM 巡检和 worktree 隔离，不拥有任务主状态。
- 标准流程改为从项目任务源接任务；任务读取、外部 Agent 邮件触发和跨平台归属交给 `cross-agent-coordination`。
- 将 `git-task-orchestrator` 定位改为历史蓝图，不再作为当前协作入口，也不迁入其旧 worktree/session 方案。

## [1.3.0] - 2026-05-09

### Added
- **任务列表管理**：复用 Agent Teams 的 tasks 目录结构（JSON 任务项 + .lock 文件锁 + .highwatermark 增量读取）
- **文件锁机制**：agent 认领任务时用 `flock()` 防止并发冲突
- **高水位标记**：agent 增量读取任务列表，已完成任务自动删除并更新 highwatermark
- **pm-monitor.sh v4.1**：新增 `--tasks-dir` 参数、`check_task_states()` 函数、TASK_STATUS/TASK_COMPLETED 事件
- **权限继承自动化**：启动时自动从主仓库复制 `.claude/settings.json` 到每个 worktree
- **Context 恢复**：团队协议持久化到 worktree 的 `CLAUDE.md`，`claude --continue` 后协议不丢失

### Changed
- §6.1 创建 Worktree 增加权限自动复制步骤
- §6.2 初始化增加共享任务列表创建
- §6.3 启动 Agent 增加 CLAUDE.md 持久化步骤
- §6.6 清理增加 tasks 目录清理
- pm-monitor.sh 支持 `--tasks-dir` 参数

## [1.2.0] - 2026-05-09

### Changed
- **[重大] tmux 模式统一使用 Agent Teams 文件通信协议**：tmux 仅作为进程管理层，通信层复用 `~/.claude/teams/` 的 inbox + tasks 机制
- tmux 模式从"降级模式"重命名为"扩展模式"，体现架构对等性
- pm-monitor.sh v4：新增 `--team-dir` 参数，支持 inbox health_report 轮询（6 个新事件类型），保留 git SHA 轮询作为第二维度
- 运行时干预改为 inbox 命令消息 + 短 send-keys 提醒（替代长文本 send-keys）
- 监控巡检改为读取 PM inbox health_report（首选），capture-pane 降为回退方案

### Added
- Agent Teams 通信协议 prompt 模板（health_report 发送、命令检查、agent 间 inbox 通信）
- 团队目录初始化步骤（config.json + inbox 文件创建）
- health_report 消息类型（status/phase/progress/last_commit_sha/context_pct/issues）
- inbox 命令协议（continue/stop/check_review_feedback/rebase/commit_and_push）
- pm-monitor.sh 过时检测（5 分钟无 health_report 自动告警）
- 自动 PM 蓝图中的 tmux 扩展模式通信架构
- parallel-lessons.md 文件通信协议操作手册

## [1.1.0] - 2026-05-08

### Changed
- **[重大] 默认使用 Agent Teams（Teammate 模式）**：在 Claude Code 环境下，重任务优先使用官方 Agent Teams，tmux 降级为非 Claude Code 环境的备选方案
- 任务规模路由从二元（Subagent / tmux）升级为三元（Subagent / Agent Teams / tmux）
- 执行模式对比从二元表扩展为三元表（Subagent / Agent Teams / tmux Session）
- 监控方式从 tmux capture-pane 扩展为 Agent Teams 共享任务列表 + 邮箱系统
- 通信通道增加 Agent Teams 邮箱系统（双向通信，替代单向 send-keys）
- 新增环境检测逻辑（自动选择 Agent Teams 或 tmux 降级）
- 实战经验文档按 Agent Teams / tmux 降级 / 通用三类重组

### Added
- SKILL.md §3 前置条件拆分为 Agent Teams 和 tmux 两组
- SKILL.md §4 环境检测与模式选择
- SKILL.md §5 Agent Teams 标准流程（规划/Worktree/启动 Teammates/监控/干预/审查/合并）
- SKILL.md §6 tmux 降级模式（保留完整流程）
- Agent Teams 详细技术调研

## [1.0.0] - 2026-05-07

### 新增
- SKILL.md 核心技能定义，覆盖并行 Agent 完整生命周期
- terminal-split.sh 跨终端分屏脚本（支持 iTerm2/Kitty/WezTerm/Warp/Ghostty/Zed/Terminal.app）
- pm-monitor.sh 参数化 PM Monitor（基于 git SHA 变化，自动停止）
- 模型选择矩阵（L0/L1/L2 路由 + 运行时升降级）
- 执行模式选择（Subagent vs tmux + 混合模式）
- PM 巡检循环蓝图（健康/任务/PR 三维巡检）
- 实战经验教训文档（tmux 陷阱、合并冲突、IME 干扰）
- 与 git-task-orchestrator 的边界定义和协作路由
- 法律实务任务拆解模板（诉讼/非诉/尽调/合同审查）作为扩展参考
- 多 Agent 平台技术调研（Claude Code/OpenClaw/Codex/Hermes 对比 + Skills 生态评测）作为扩展参考
