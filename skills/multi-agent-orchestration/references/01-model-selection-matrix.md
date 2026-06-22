# 模型选择与执行模式矩阵

> 本文档为 SKILL.md 的 Level 2 参考文档，提供模型路由和执行模式选择的完整细节。
> 读取时机：规划并行任务、为 Agent 分配模型、选择 Subagent / Agent Teams / tmux 时。

---

## 1. 模型分级（L0 / L1 / L2）

模型路由只服务 worker，不绑定 PM 所在产品。Codex 做 PM 时可以启动 Claude Code 或 OpenCode worker；Claude Code 做 PM 时也可以启动 Codex 或 OpenCode worker。判断顺序是：任务复杂度 → 当前可用额度 → worker backend → 模型/环境变量。

### 1.1 能力定义

| 级别 | 定位 | 典型模型 | 适合任务 |
|------|------|---------|---------|
| **L0 轻量** | 快速、低成本 | Haiku / Flash | 单文件改动、i18n、翻译、配置调整 |
| **L1 标准** | 平衡性价比 | Sonnet | 多文件但边界清晰的功能、bug 修复 |
| **L2 重型** | 深度理解 | Opus | 架构重构、跨模块集成、首次探索陌生代码库 |

### 1.2 任务-模型路由

| 任务特征 | 推荐级别 | 判断关键词 |
|---------|---------|-----------|
| 单文件改动、逻辑简单 | L0 | "添加"、"补充"、"翻译"、"复制" |
| 多文件但边界清晰 | L1 | 默认 |
| 需理解现有架构 | L1→L2 | "修改"、"重构" |
| 跨模块集成 | L2 | "理解"、"分析"、"设计" |
| 架构级重构 | L2 | "拆分"、"重写" |
| 首次探索陌生代码库 | L2 | "探索"、"调研" |

**经验法则**：任务描述包含"理解/分析/重构/设计"→ L2；包含"添加/补充/翻译/复制"→ L0；其余默认 L1。

### 1.3 额度 Profile

| Profile | 目标 | backend | 典型设置 |
|---------|------|---------|----------|
| `claude-provider` | 通过第三方 Anthropic-compatible API 启动 Claude Code | Claude Code | `claude --settings /path/to/provider.settings.json ...` |
| `claude-oauth` | 用户明确要求时才消耗 Claude Code 订阅/OAuth 额度 | Claude Code | `env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_BASE_URL claude ...` |
| `codex-l1` | 消耗 Codex/OpenAI 额度做常规功能 | Codex | `codex exec -m <model> -a never -s danger-full-access -` |
| `opencode-l0` | 消耗 OpenCode 已配置 provider 的轻量额度 | OpenCode | `opencode run --format json --model <provider/model> ...` |
| `opencode-l1` | 消耗 OpenCode 已配置 provider 的常规额度 | OpenCode | `opencode run --format json --model <provider/model> ...` |
| `opencode-acp` | 通过 OpenCode ACP server 接入结构化协议 | OpenCode / ACP | `opencode acp`，需要 PM 侧 ACP client/adapter |
| `hermes-l1` | 利用 Hermes 池化凭证 + fallback chain 做常规功能 | Hermes | `hermes chat -q "$(cat /tmp/prompt.md)" -m <model> --yolo` |
| `hermes-acp` | 通过 Hermes ACP server 接入结构化协议 | Hermes / ACP | `hermes acp`，需要 PM 侧 ACP client/adapter |
| `kimi-l0` | 消耗 Moonshot/Kimi 额度做轻量任务 | Kimi | `kimi --print -c "$(cat /tmp/prompt.md)" -m kimi-latest -y` |
| `kimi-acp` | 通过 Kimi ACP server 接入结构化协议 | Kimi / ACP | `kimi --acp`，需要 PM 侧 ACP client/adapter |
| `gemini-l1` | 消耗 Google AI 额度做常规功能 | Gemini | `gemini -p "$(cat /tmp/prompt.md)" -m gemini-2.5-pro -y` |
| `qoderwork-l0` | 消耗 QoderWork 平台免费额度（Qwen3 Max 等）做轻量任务 | QoderWork | `qoderclicn -p "$(cat /tmp/prompt.md)" -m qmodel_latest` |
| `qoderwork-l1` | 消耗 QoderWork 平台额度 + 利用元典/企查查 MCP 工具链 | QoderWork | `qoderclicn -p "$(cat /tmp/prompt.md)" -m qmodel_latest --mcp-config <mcp.json>` |
| `custom-cli` | 接入其他可一行命令启动的 Agent | custom CLI | `<agent-command> < /tmp/task.prompt.md` |
| `oss-local` | 不消耗云端额度，适合低风险重复任务 | Codex OSS / shell | `codex exec --oss --local-provider lmstudio ...` 或脚本 |

默认 Claude Code worker 使用 `claude-provider`。每个第三方 provider 使用一个本地 settings JSON，参考 `config/claude-provider-settings.example.json`；真实 token 文件应放在项目或用户目录的忽略路径中。settings 是完整环境变量组，包含 Haiku/Sonnet/Opus 默认模型、timeout、thinking tokens 和行为开关，所以启动命令不要额外指定 `--model sonnet`。只有用户明确要走订阅/OAuth 时，才使用 `claude-oauth` 并清理 `ANTHROPIC_API_KEY`、`ANTHROPIC_AUTH_TOKEN` 和第三方 `ANTHROPIC_BASE_URL`。

### 1.4 各执行模式下指定模型

**Claude Code Agent Teams 模式**：如果要走第三方 API，先让该 session 加载 provider settings。模型映射由 settings 里的 `ANTHROPIC_DEFAULT_*_MODEL` 变量提供。

**Claude Code tmux worker（默认第三方 API settings）**：tmux 启动的是一个后台独立终端 session，可 attach 或 capture。默认启动交互式 Claude Code，使用 `--settings` 加载整份 provider profile。模板见 `config/claude-provider-settings.example.json`。

```bash
tmux new-session -d \
  -s worker-claude-provider \
  -c .claude/worktrees/tmux-feature \
  'claude --settings /path/to/provider.settings.json --permission-mode auto'
```

批处理执行 prompt 时，再使用 Claude Code 的 `-p` 非交互模式：

```bash
tmux new-session -d \
  -s worker-claude-provider \
  -c .claude/worktrees/tmux-feature \
  'claude --settings /path/to/provider.settings.json -p --permission-mode auto --output-format stream-json < /tmp/task.prompt.md'
```

**Claude Code tmux worker（可选订阅/OAuth）**：只在用户明确要求使用 Claude 订阅/OAuth 时启用，启动命令里清掉第三方 provider 环境，避免误走 API key 或代理服务。

```bash
tmux new-session -d \
  -s worker-claude-oauth \
  -c .claude/worktrees/tmux-feature \
  'env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_BASE_URL claude --permission-mode auto'
```

**Codex tmux worker**：用 `-m` 或 profile 指定模型。

```bash
tmux new-session -d \
  -s worker-codex-l1 \
  -c .claude/worktrees/tmux-feature \
  'codex exec -m <codex-model> -a never -s danger-full-access - < /tmp/task.prompt.md'
```

**OpenCode tmux worker**：模型格式通常是 `provider/model`，先用 `opencode models` 查看可用项。

```bash
tmux new-session -d \
  -s worker-opencode-l1 \
  -c .claude/worktrees/tmux-feature \
  'opencode run --format json --model <provider/model> "$(cat /tmp/task.prompt.md)"'
```

**OpenCode ACP server**：仅在 PM 侧已有 ACP client/adapter 时使用。

```bash
tmux new-session -d \
  -s worker-opencode-acp \
  -c .claude/worktrees/tmux-feature \
  'opencode acp'
```

**自定义 CLI worker**：用于其他一行命令 Agent。把模型、provider、profile、权限参数放进命令；PM 只要求它在指定 worktree 内执行，并产出 checkpoint 三件套，或至少可由 Git 状态巡检。

```bash
tmux new-session -d \
  -s worker-custom \
  -c .claude/worktrees/tmux-feature \
  '<agent-command> < /tmp/task.prompt.md'
```

**Hermes Agent tmux worker**：Hermes 原生支持 `--worktree`，pooled auth 支持多 provider 自动 fallback。

```bash
tmux new-session -d \
  -s worker-hermes \
  -c .claude/worktrees/tmux-feature \
  'hermes --yolo -m gpt-4o'
```

或使用 Hermes 原生 worktree：

```bash
tmux new-session -d \
  -s worker-hermes \
  'hermes --worktree tmux-feature --yolo -m gpt-4o'
```

**Kimi CLI tmux worker**：原生 `stream-json` 输出，适合 PM 解析。

```bash
tmux new-session -d \
  -s worker-kimi \
  -c .claude/worktrees/tmux-feature \
  'kimi --print --output-format stream-json -y -m kimi-latest -c "$(cat /tmp/task.prompt.md)"'
```

**Gemini CLI tmux worker**：`--approval-mode` 提供 4 级审批控制。

```bash
tmux new-session -d \
  -s worker-gemini \
  -c .claude/worktrees/tmux-feature \
  'gemini -y --approval-mode auto_edit -m gemini-2.5-pro'
```

批处理模式：

```bash
tmux new-session -d \
  -s worker-gemini \
  -c .claude/worktrees/tmux-feature \
  "bash -lc 'gemini -p \"\$(cat /tmp/task.prompt.md)\" -m gemini-2.5-pro -y'"
```

**QoderWork CLI tmux worker**：消耗 QoderWork 平台额度，可利用元典/企查查 MCP 工具链。**必须在干净终端启动**（不能从 QoderWork 桌面端内部 session 启动）。

```bash
tmux new-session -d \
  -s worker-qoderwork \
  -c .claude/worktrees/tmux-feature \
  'qoderclicn -m qmodel_latest --permission-mode auto'
```

批处理模式：

```bash
tmux new-session -d \
  -s worker-qoderwork \
  -c .claude/worktrees/tmux-feature \
  "bash -lc 'qoderclicn -p \"\$(cat /tmp/task.prompt.md)\" -m qmodel_latest'"
```

**交互式 tmux session**：只在需要人工接管时用 `/model` 或 CLI 内部菜单切换模型。

```bash
# 启动 Claude Code 后切换模型
tmux send-keys -t session-name "/model" Enter
sleep 1
# 用 Up/Down 导航到目标模型（次数取决于菜单排序）
for i in 1 2 3; do tmux send-keys -t session-name Down; sleep 0.05; done
tmux send-keys -t session-name Enter
```

或在 prompt 文件开头声明模型偏好：

```
[模型建议: 这是 i18n 任务，适合轻量模型。请先 /model 切换。]
```

### 1.5 运行时升降级

**升级（→ L2）**：Agent 反复失败 >2 次、任务复杂度超预期

**降级（→ L0）**：架构设计完成进入实现、剩余为重复性工作

Agent Teams 模式下模型在创建时指定，升降级需重新创建 Teammate。

tmux 交互模式下：

```bash
# 中断 Agent 并切换模型
tmux send-keys -t session-name C-c
sleep 0.5
tmux send-keys -t session-name "/model" Enter
# 导航到目标模型后继续
tmux send-keys -t session-name -l -- "模型已升级，继续刚才的任务。"
tmux send-keys -t session-name Enter
```

Claude Code `-p` 批处理模式下，推荐停止旧 worker，保留 worktree，按更高 profile 重启，并在 prompt 中说明“接续当前 worktree 已有改动，不要回退”。

### 1.6 批量调度模板

```bash
# tasks.conf 格式: name  backend  worktree路径  profile  prompt文件
worker-1  claude    .claude/worktrees/i18n-fixes      claude-provider  /tmp/task-i18n.txt
worker-2  codex     .claude/worktrees/file-ops        codex-l1         /tmp/task-fileops.txt
worker-3  opencode  .claude/worktrees/ui-copy         opencode-l0      /tmp/task-copy.txt
worker-4  claude    .claude/worktrees/refactor-core   claude-provider  /tmp/task-refactor.txt
worker-5  hermes    .claude/worktrees/api-integration hermes-l1        /tmp/task-api.txt
worker-6  kimi      .claude/worktrees/translation     kimi-l0          /tmp/task-trans.txt
worker-7  gemini    .claude/worktrees/docs-update     gemini-l1        /tmp/task-docs.txt
worker-8  qoderwork .claude/worktrees/legal-research  qoderwork-l1     /tmp/task-legal.txt
worker-9  custom    .claude/worktrees/custom-agent    custom-cli       /tmp/task-custom.txt
```

---

## 2. 执行模式选择

### 2.1 三档 Claude Code worker

| 档位 | 命令形态 | 适合任务 | PM 巡检 |
|------|----------|----------|---------|
| 批处理 | `claude -p --output-format stream-json --max-turns 20 ...` | 独立、边界清楚、能一次完成的任务 | checkpoint + stream-json + final diff |
| tmux 可接管终端 | `tmux new-session -d ... 'claude --settings ...'` | 长上下文、需要随时 attach/capture/send-keys | checkpoint + git + tmux pane |
| 官方 agent view | `claude agents` / `claude --worktree --tmux` / 版本支持时 `claude --bg` 或 `/bg` | 需要 Claude 官方后台会话、peek/reply/attach | checkpoint + `claude agents --json` + agent view |

`--max-turns`、`--worktree`、`--tmux`、`--bg` 的可用性随 Claude Code 版本变化；使用前以当前 `claude --help`、`claude agents --help` 为准。无论使用哪一档，worker 都必须写 `.claude/agent-sessions/{session}/STATUS.json`、`RESULT.md`、`PATCH_SUMMARY.md`。

### 2.2 执行后端对比：Subagent / Agent Teams / tmux Session / ACP

| 维度 | Subagent（Agent tool） | Agent Teams（Teammate） | tmux Session | ACP adapter |
|------|----------------------|----------------------|-------------|-------------|
| **上下文** | 共享父会话（受窗口大小影响） | 独立完整上下文 | 独立完整上下文 | adapter 决定 |
| **可见性** | 后台运行 | 独立终端窗格（split-panes） | 独立终端 pane | 结构化事件流 |
| **通信** | 单向汇报 | 双向邮箱 + 共享任务列表 | checkpoint 文件 + git + capture-pane 兜底 | JSON-RPC 事件 |
| **生命周期** | 随父会话结束 | 随团队结束 | 独立存活 | adapter 决定 |
| **模型** | 继承父会话 | 创建时独立指定 | 启动命令/profile 指定，支持 Claude Code / Codex / OpenCode / Hermes / Kimi / Gemini / QoderWork | adapter 决定 |
| **文件隔离** | 在当前目录操作 | worktree + 分支 | worktree + 分支 | 仍建议 worktree + 分支 |
| **任务管理** | 无 | 共享任务列表（pending/in-progress/completed） | 外部脚本 + 状态文件 | adapter 事件 + 状态文件 |
| **Agent 间协作** | 不支持 | 支持邮箱通信 | 通过 PM 转发 | 取决于 adapter |
| **启动开销** | 几乎为零 | 低 | 中等 | 中到高 |
| **适合时长** | ≤15 分钟 | 小时级 | 小时级 | 小时级 |
| **并发上限** | 受上下文/API 限制 | 团队规模 | tmux session 数量 | adapter 资源 |
| **可靠性** | 高（内置） | 高（官方内置） | 高（进程/文件），中（屏幕抓取） | 协议高，adapter 成熟度决定实际稳定性 |
| **环境要求** | 通用 | Claude Code + feature flag | tmux + 对应 CLI | 可启动 ACP adapter |

### 2.3 路由矩阵

| 任务特征 | 推荐模式 | 理由 |
|---------|---------|------|
| Code review 一个 PR | Subagent | 明确、短、无需隔离 |
| 研究技术问题 | Subagent | 纯信息收集 |
| 快速修复 bug（单分支） | Subagent | 改动小 |
| 新增完整功能模块 | **Agent Teams**（或 tmux） | 需独立上下文、长时间 |
| 并行 2+ 个独立功能 | **Agent Teams**（或 tmux） | 需文件隔离 |
| 大规模重构 | **Agent Teams**（或 tmux） | 需完整上下文理解 |
| 批量重复操作（i18n） | Subagent × N | 并发效率高 |
| 需要 Agent 间协作 | **Agent Teams** | 唯一支持双向通信 |

**路由决策树**：

```
任务时长 ≤15 分钟？
├─ 是 → Subagent
└─ 否 → 需独立 git 分支？
    ├─ 否 → Subagent
    └─ 是 → 当前 PM 是 Claude Code 且 Agent Teams 已启用？
        ├─ 是 → Agent Teams（split-panes）
        └─ 否 → 需要跨产品或额度路由？
            ├─ 是 → tmux worker（Claude/Codex/OpenCode）
            └─ 否 → tmux worker
```

### 2.4 混合模式

```
PM（Team Lead）
├── Subagent A: review PR #1              ← 分钟级，共享上下文
├── Subagent B: 研究 X 接入方案            ← 分钟级，共享上下文
├── Teammate 1: feat/i18n                 ← 小时级，L0，独立上下文
└── Teammate 2: feat/refactor             ← 小时级，L2，独立上下文
```

PM 在等待 Teammate 期间用 Subagent 处理短任务，不空闲。

tmux worker 模式下，将 Teammate 替换为独立 CLI session 即可。
