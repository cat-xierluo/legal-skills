# Agent CLI 完整参考手册

> 本文档为 SKILL.md 的补充参考文档，汇总本机已安装的所有 Agent CLI 的命令规范。
> 更新日期：2026-06-21

---

## 0. 总览

| CLI | 版本 | 二进制路径 | 交互模式 | 批处理模式 | ACP | 额度来源 | 默认 model（个人偏好） |
|-----|------|-----------|----------|-----------|-----|---------|------------------------|
| Claude Code | 2.1.175 | `~/.local/bin/claude` | `claude` | `claude -p` | ✗ | Anthropic API / 第三方 provider / OAuth | `glm-5.2`、`MiniMax-M3`（默认轮换） |
| Codex | 0.142.0-alpha.6 | `~/.local/bin/codex` | `codex` | `codex exec` | ✗ | OpenAI API | （见 `codex_policy.policy`，默认 `explicit_only` 时不主动派） |
| OpenCode | 1.17.6 | `~/.opencode/bin/opencode` | `opencode` | `opencode run` | ✓ `opencode acp` | 多 provider（config.toml） | `opencode:<provider>/<model>`（按 OpenCode profile） |
| Hermes Agent | 0.17.0 | `~/.local/bin/hermes` | `hermes` / `hermes chat` | `hermes chat -q "..."` | ✓ `hermes acp` | 多 provider（pooled auth） | （按 hermes profile） |
| Kimi CLI | 0.39 | `~/.local/bin/kimi` | `kimi` | `kimi --print -c "..."` | ✓ `kimi --acp` | Moonshot API | （按 kimi profile） |
| Gemini CLI | 0.29.0 | `/opt/homebrew/bin/gemini` | `gemini` | `gemini -p "..."` | ✓ `--experimental-acp` | Google AI / Vertex | （按 gemini profile） |
| QoderWork CLI | 1.0.24 | QoderWork CN.app 内 bin | `qoderclicn` | `qoderclicn -p "..."` | ✗ | QoderWork 平台额度 | `qoder-3.7MAX`、`qoder-3.7PLUS` |
| CodeBuddy / WorkBuddy CLI | 2.103.3 | WorkBuddy.app 内 bin | `codebuddy` | `codebuddy --print` | ✓ `--acp` | WorkBuddy 账号额度 / 内置模型 | `deepseek-v4-pro`、`deepseek-v4-flash` |
| Rudder | 0.2.9 | `~/.local/bin/rudder` | `rudder run` | 通过 `agent` 子命令 | ✗ | 自托管 | （按 rudder profile） |

> 默认 model 列来源：`~/.claude/orchestration-personal.json` 的 `main_force.models` 与 `backend_model_routing.<backend>.default_models`（详见 SKILL.md §2.4）；缺省回落本表。Codex 默认行为按 `codex_policy.policy` 决定；个人偏好通常 `explicit_only`——只在用户明确要求时解封。

**未安装 / 不可用**：OpenClaw（symlink 已断）、Reasonix、Aider、Devin。

---

## 1. Claude Code（`claude`）

> SKILL.md 已有详细覆盖。本节仅做参数速查补充。

### 1.1 核心参数速查

```
用法: claude [options] [prompt]

交互模式:     claude
批处理模式:   claude -p "prompt"  或  claude -p < prompt.md
流式输出:     claude -p --output-format stream-json "prompt"
```

| 参数 | 说明 | 编排用途 |
|------|------|---------|
| `-p` / `--print` | 非交互模式，打印后退出 | worker 批处理必选 |
| `--output-format <fmt>` | `text` / `json` / `stream-json` | stream-json 适合 PM 解析 |
| `--settings <file-or-json>` | 加载 settings JSON（provider 配置） | 第三方 provider 路由 |
| `--setting-sources <src>` | `user` / `project` / `local` | 控制加载哪些配置层 |
| `--strict-mcp-config` | 只用 `--mcp-config` 的 MCP server | 隔离 MCP 工具 |
| `--mcp-config <config>` | 加载 MCP 服务器配置 | 注入自定义工具 |
| `--permission-mode <mode>` | `default` / `accept_edits` / `bypass_permissions` / `dont_ask` / `auto` | worker 自动化程度 |
| `--dangerously-skip-permissions` | 跳过所有权限检查 | 沙箱环境专用 |
| `--system-prompt <prompt>` | 自定义系统提示词 | 角色定制 |
| `--append-system-prompt <prompt>` | 追加系统提示词 | 增量指令 |
| `-c` / `--continue` | 继续最近会话 | 断点续跑 |
| `-r` / `--resume [id]` | 恢复指定会话 | 指定 session |
| `--session-id <uuid>` | 使用指定 session ID | 可预测 session |
| `--worktree [name]` | 创建 git worktree | 文件隔离 |
| `--tmux` | 为 worktree 创建 tmux session | 需配合 --worktree |
| `--tools <tools...>` | 限制可用工具集 | 收窄 worker 能力 |
| `--allowed-tools <tools>` | 允许的工具 | 白名单 |
| `--disallowed-tools <tools>` | 禁止的工具 | 黑名单 |
| `--effort <level>` | `low` / `medium` / `high` / `xhigh` / `max` | 控制思考深度 |
| `--model <model>` | 指定模型 | 覆盖默认模型 |
| `--fallback-model <model>` | 主模型不可用时 fallback | 容错 |
| `--max-turns <n>` | 最大交互轮数 | 控制预算 |
| `--add-dir <dirs>` | 添加工作目录 | 跨目录访问 |
| `--bare` | 最小模式：跳过 hooks/LSP/plugins/CLAUDE.md | 减少启动开销 |
| `--safe-mode` | 禁用所有自定义配置 | 排障 |
| `--agent <agent>` | 指定 agent | 自定义角色 |
| `--agents <json>` | JSON 定义自定义 agents | 多角色 |
| `-i` / `--prompt-interactive <text>` | 执行 prompt 并继续交互 | 半自动 |
| `--remote-control [name]` | 启用远程控制 | 外部驱动 |

### 1.2 Worker 启动模式

**Provider registry（推荐）**：
```bash
eval "$(bash scripts/render-runtime-profile.sh \
  --backend claude-code \
  --provider-registry config/claude-providers.local.json \
  --api-provider deepseek \
  --model v4flash \
  --mode batch \
  --prompt-file /tmp/task.prompt.md)"

bash -lc "$WORKER_COMMAND"
```

registry 里每个 provider 有自己的 `base_url`、`auth_token_env` / `api_key_env`、`auth_type` 和 `models`。`render-runtime-profile.sh` 会把模型别名解析成 provider 真实模型名，再交给 `claude --model`。

**Settings 文件（兼容旧路径）**：
```bash
bash scripts/claude-provider-env.sh \
  --settings /path/to/provider.settings.json \
  --model provider-model \
  -- \
  claude --settings /path/to/provider.settings.json \
    --model provider-model \
    -p --output-format stream-json \
    --permission-mode acceptEdits \
  < /tmp/task.prompt.md
```

**tmux 交互式（可纠偏/可接管）**：
```bash
tmux new-session -d -s worker-claude -c /path/to/worktree \
  'bash scripts/claude-provider-env.sh --settings /path/to/provider.settings.json --model provider-model -- claude --settings /path/to/provider.settings.json --model provider-model --permission-mode auto'
```

第三方 provider 不要裸跑 `claude --settings ...`。标准路径是先用 `render-runtime-profile.sh` 生成命令；该命令默认包 `scripts/claude-provider-env.sh`。wrapper 会清理继承的 `ANTHROPIC_*` provider 路由变量、从 registry 或 settings 导入 env、补齐 `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_API_KEY`、设置 `CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST=1`，并给 `claude` 注入 `--setting-sources project,local`。这样用户级 `~/.claude/settings.json` 里的 MiniMax/其他 provider 不会覆盖本次 worker。

**Claude 官方 worktree + tmux**：
```bash
claude --worktree feature-x --tmux
```

### 1.3 已知坑点

- `< redirect` 在 tmux 内必须用 `bash -lc` 包裹
- `-p` + `--output-format stream-json` + tmux detached 组合可能导致启动即死
- 大 prompt（> 5KB）+ 大 codebase 会触发 autocompact thrash
- `--bare` 模式适合 worker 减少启动 token 消耗

---

## 2. Codex（`codex`）

### 2.1 核心参数速查

```
用法: codex [OPTIONS] [PROMPT]          # 交互模式
      codex exec [OPTIONS] [PROMPT]     # 批处理模式
```

| 参数 | 说明 | 编排用途 |
|------|------|---------|
| `exec` | 非交互执行子命令 | worker 批处理入口 |
| `-m` / `--model <MODEL>` | 指定模型（如 `o3`, `o4-mini`） | 模型路由 |
| `-s` / `--sandbox <MODE>` | `read-only` / `workspace-write` / `danger-full-access` | 安全控制 |
| `--dangerously-bypass-approvals-and-sandbox` | 跳过所有审批和沙箱 | 沙箱环境专用 |
| `-c` / `--config <key=value>` | 覆盖 config.toml 配置 | 运行时调参 |
| `-p` / `--profile <NAME>` | 加载 `$CODEX_HOME/<name>.config.toml` | 多 profile 路由 |
| `--oss` | 使用开源模型 | 本地/低成本任务 |
| `--local-provider <PROVIDER>` | `lmstudio` / `ollama` | 本地推理 |
| `-i` / `--image <FILE>` | 附加图片 | 多模态任务 |
| `--enable <FEATURE>` | 启用 feature flag | 实验功能 |
| `--disable <FEATURE>` | 禁用 feature flag | 稳定性控制 |
| `--strict-config` | config.toml 字段不识别时报错 | 配置校验 |

### 2.2 子命令

| 子命令 | 说明 |
|--------|------|
| `exec` | 非交互执行（worker 用） |
| `review` | 代码审查 |
| `resume` | 恢复之前会话 |
| `login` / `logout` | 认证管理 |
| `mcp` | MCP 服务器管理 |
| `plugin` | 插件管理 |
| `apply` | 应用最新 diff（`git apply`） |
| `doctor` | 诊断安装/配置/运行时健康 |
| `cloud` | 浏览 Codex Cloud 任务 |
| `features` | 查看 feature flags |

### 2.3 Worker 启动模式

**批处理**：
```bash
codex exec -m o4-mini -s danger-full-access - < /tmp/task.prompt.md
```

**tmux 交互式**：
```bash
tmux new-session -d -s worker-codex -c /path/to/worktree \
  'codex -m o4-mini -s workspace-write'
```

**tmux 批处理**：
```bash
tmux new-session -d -s worker-codex -c /path/to/worktree \
  "bash -lc 'codex exec -m o4-mini -s danger-full-access - < /tmp/task.prompt.md'"
```

**本地开源模型**：
```bash
codex exec --oss --local-provider ollama -m qwen2.5-coder -s workspace-write - < /tmp/task.prompt.md
```

### 2.4 Profile 路由

Codex 的 profile 机制通过 `-p` / `--profile` 加载 `$CODEX_HOME/<name>.config.toml`：

```bash
# 使用自定义 profile
codex exec -p legal-worker -m o4-mini -s danger-full-access - < /tmp/task.prompt.md

# 覆盖配置项
codex exec -c 'model="o3"' -c 'shell_environment_policy.inherit=all' - < /tmp/task.prompt.md
```

### 2.5 与 Skill 集成要点

- Codex 的 `exec` 是 worker 的标准入口，不支持 `< redirect` 时同样需要 `bash -lc` 包裹
- `-s danger-full-access` 是 worker 自动化的常用选项，但需确保 worktree 隔离
- Codex 没有内建的 `--system-prompt` 参数，系统提示需在 prompt 文件或 config.toml 中设定
- `codex apply` 可在 worker 完成后单独应用 diff，作为 PM 收口的替代路径

---

## 3. OpenCode（`opencode`）

### 3.1 核心参数速查

```
用法: opencode [project]                # 交互 TUI
      opencode run [message..]          # 批处理
      opencode acp                      # ACP 服务器
```

| 参数 | 说明 | 编排用途 |
|------|------|---------|
| `run [message..]` | 非交互执行 | worker 批处理入口 |
| `-m` / `--model <provider/model>` | 指定模型（格式 `provider/model`） | 模型路由 |
| `-c` / `--continue` | 继续最近会话 | 断点续跑 |
| `-s` / `--session <id>` | 恢复指定会话 | session 管理 |
| `--fork` | fork 当前会话 | 分支实验 |
| `--prompt <text>` | 设置 prompt | 批处理 |
| `--agent <name>` | 指定 agent | 角色定制 |
| `--pure` | 不加载外部插件 | 减少干扰 |
| `--format <fmt>` | 输出格式（`json` 等） | PM 解析 |

### 3.2 子命令

| 子命令 | 说明 |
|--------|------|
| `run` | 非交互执行（worker 用） |
| `acp` | ACP 服务器模式 |
| `mcp` | MCP 服务器管理 |
| `providers` / `auth` | Provider 和凭证管理 |
| `models [provider]` | 列出可用模型 |
| `agent` | Agent 管理 |
| `session` | Session 管理 |
| `stats` | Token 用量和成本统计 |
| `export` / `import` | Session 数据导入导出 |
| `serve` | 无头服务器 |
| `web` | 启动 Web 界面 |
| `plugin` | 插件管理 |
| `github` | GitHub agent 管理 |
| `pr <number>` | 拉取 PR 分支并运行 |

### 3.3 Worker 启动模式

**批处理**：
```bash
opencode run --model anthropic/claude-sonnet-4-20250514 "$(cat /tmp/task.prompt.md)"
```

**tmux 交互式**：
```bash
tmux new-session -d -s worker-opencode -c /path/to/worktree \
  'opencode --model anthropic/claude-sonnet-4-20250514'
```

**ACP 服务器**：
```bash
tmux new-session -d -s worker-opencode-acp -c /path/to/worktree \
  'opencode acp'
```

**Web 界面**：
```bash
opencode web --port 8080
```

### 3.4 Provider 管理

OpenCode 的 provider 通过 `opencode providers` 管理，支持多 provider 配置：

```bash
opencode providers          # 查看已配置 provider
opencode models             # 列出所有可用模型
opencode models anthropic   # 列出 Anthropic provider 下的模型
opencode stats              # 查看 token 用量
```

模型格式为 `provider/model`，例如 `anthropic/claude-sonnet-4-20250514`、`openai/gpt-4o`、`google/gemini-2.5-pro`。

### 3.5 与 Skill 集成要点

- `opencode run` 支持直接传 message 参数（不需要 stdin redirect），比 Claude Code / Codex 更方便
- `opencode acp` 可直接作为 ACP 服务器，适合已有 ACP client/adapter 的项目
- `opencode pr <number>` 可自动拉取 PR 分支并启动，适合 PR review worker
- `opencode stats` 提供内置成本统计，PM 可直接查询 worker 消耗

---

## 4. Hermes Agent（`hermes`）

### 4.1 核心参数速查

```
用法: hermes                    # 交互模式（默认 TUI）
      hermes chat -q "prompt"   # 单次查询
      hermes --cli              # 强制经典 REPL
```

| 参数 | 说明 | 编排用途 |
|------|------|---------|
| `-z` / `PROMPT` | 单次查询 prompt | 批处理 |
| `-m` / `--model <MODEL>` | 指定模型 | 模型路由 |
| `--provider <PROVIDER>` | 指定 provider | provider 路由 |
| `-t` / `--toolsets <TOOLSETS>` | 启用工具集 | 收窄/扩展能力 |
| `--resume <SESSION>` | 恢复指定会话 | session 管理 |
| `--continue [NAME]` | 继续最近/指定会话 | 断点续跑 |
| `--worktree` | 启动时创建 git worktree | 文件隔离 |
| `--accept-hooks` | 自动接受 hooks | 减少人工干预 |
| `--skills <SKILLS>` | 指定技能集 | 定制能力 |
| `--yolo` | 自动批准所有操作 | 沙箱自动化 |
| `--pass-session-id` | 输出 session ID | PM 追踪 |
| `--ignore-user-config` | 忽略用户配置 | 隔离环境 |
| `--ignore-rules` | 忽略规则文件 | 测试/排障 |
| `--safe-mode` | 安全模式 | 排障 |
| `--tui` | 使用现代 TUI | 可视化 |
| `--cli` | 强制经典 REPL | 脚本兼容 |

### 4.2 关键子命令

| 子命令 | 说明 |
|--------|------|
| `chat` | 交互对话（默认） |
| `model` | 选择默认模型 |
| `fallback` | 管理 fallback provider 链 |
| `auth` | 池化凭证管理（add/list/remove/reset） |
| `setup` | 交互式设置向导 |
| `acp` | ACP 服务器模式 |
| `mcp` | MCP 服务器管理 |
| `sessions` | 会话管理（list/rename/export/prune） |
| `kanban` | 多 profile 协作看板 |
| `cron` | 定时任务管理 |
| `gateway` | 消息网关（WhatsApp/Slack 等） |
| `dashboard` | Web UI 仪表盘 |
| `skills` / `bundles` / `plugins` | 技能/插件管理 |
| `doctor` | 诊断检查 |
| `profile` | 多 profile 隔离管理 |
| `computer-use` | macOS Computer Use 后端 |

### 4.3 Worker 启动模式

**单次查询**：
```bash
hermes chat -q "$(cat /tmp/task.prompt.md)" -m gpt-4o --yolo
```

**tmux 交互式**：
```bash
tmux new-session -d -s worker-hermes -c /path/to/worktree \
  'hermes --worktree --yolo -m gpt-4o'
```

**tmux + worktree 隔离**（Hermes 原生支持 `--worktree`）：
```bash
tmux new-session -d -s worker-hermes \
  'hermes --worktree feature-x --yolo -m gpt-4o'
```

**ACP 服务器**：
```bash
tmux new-session -d -s worker-hermes-acp -c /path/to/worktree \
  'hermes acp'
```

### 4.4 Pooled Auth 机制

Hermes 独特的池化凭证系统，适合多 provider 路由：

```bash
hermes auth add <provider>     # 添加凭证到池
hermes auth list               # 列出池内凭证
hermes auth remove <p> <t>     # 移除凭证
hermes auth reset <provider>   # 重置耗尽状态
hermes fallback add            # 添加 fallback provider
hermes fallback list           # 查看 fallback 链
```

### 4.5 与 Skill 集成要点

- Hermes 的 `--worktree` 是内建的，比 Claude Code 的 `--worktree` 更早支持
- Pooled auth + fallback chain 机制让 Hermes 天然适合多 provider 路由场景
- `--pass-session-id` 可让 PM 精确追踪 worker session
- `--yolo` 等同于 Claude Code 的 `--dangerously-skip-permissions`
- Hermes 有丰富的子命令生态（kanban、cron、gateway），可作为编排层的补充工具
- `hermes profile` 支持多 profile 隔离，类似 Claude Code 的多 settings 文件

---

## 5. Kimi CLI（`kimi`）

### 5.1 核心参数速查

```
用法: kimi                        # 交互模式
      kimi --print -c "prompt"    # 批处理模式
      kimi --acp                  # ACP 服务器
```

| 参数 | 说明 | 编排用途 |
|------|------|---------|
| `-c` / `-q` / `--command` / `--query <TEXT>` | 用户查询 | 批处理入口 |
| `-m` / `--model <TEXT>` | 指定模型 | 模型路由 |
| `-w` / `--work-dir <DIR>` | 工作目录 | 目录指定 |
| `-C` / `--continue` | 继续上次会话 | 断点续跑 |
| `--print` | 非交互打印模式 | worker 批处理 |
| `--acp` | ACP 服务器模式 | 协议集成 |
| `--ui [shell\|print\|acp]` | UI 模式选择 | 控制交互方式 |
| `--input-format [text\|stream-json]` | 输入格式 | PM 输入管道 |
| `--output-format [text\|stream-json]` | 输出格式 | PM 解析 |
| `--mcp-config-file <FILE>` | MCP 配置文件 | 工具注入 |
| `--mcp-config <TEXT>` | MCP 配置 JSON | 内联工具注入 |
| `-y` / `--yolo` / `--yes` / `--auto-approve` | 自动批准 | 沙箱自动化 |
| `--agent-file <FILE>` | 自定义 agent 规范文件 | 角色定制 |

### 5.2 Worker 启动模式

**批处理**：
```bash
kimi --print -c "$(cat /tmp/task.prompt.md)" -m kimi-latest -y
```

**tmux 交互式**：
```bash
tmux new-session -d -s worker-kimi -c /path/to/worktree \
  'kimi -y -m kimi-latest'
```

**ACP 服务器**：
```bash
tmux new-session -d -s worker-kimi-acp -c /path/to/worktree \
  'kimi --acp'
```

**流式输出**：
```bash
kimi --print --output-format stream-json -c "$(cat /tmp/task.prompt.md)"
```

### 5.3 与 Skill 集成要点

- Kimi CLI 的参数风格接近 Claude Code（`--print`、`--mcp-config`、`--yolo`）
- `-w` / `--work-dir` 可直接指定工作目录，不需要 `cd` 再启动
- `--agent-file` 支持自定义 agent 规范，适合给 worker 注入特定角色行为
- 原生支持 `stream-json` 输出格式，PM 可直接解析
- `kimi` 和 `kimi-cli` 是同一个二进制（两个入口）

---

## 5A. CodeBuddy / WorkBuddy CLI（`codebuddy`）

> 2026-06-21 实测：WorkBuddy 桌面端内置 CodeBuddy CLI，可作为 custom CLI worker 使用；它不同于 Moonshot 官方 `kimi` CLI。

### 5A.1 安装与版本

| 属性 | 值 |
|------|-----|
| 二进制路径 | `/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/bin/codebuddy` |
| 版本 | `2.103.3` |
| 配置目录 | `~/.workbuddy/` |
| 自定义模型配置 | `~/.workbuddy/models.json` |

`codebuddy --help` 的模型列表可能滞后。2026-06-21 实测中，help 只列出 `kimi-k2.5`，但 `--model kimi-k2.6` 能正常调用，交互界面显示 `Kimi-K2.6 · internal Usage Billing`。

### 5A.2 核心参数速查

```
用法: codebuddy [options] [prompt]

交互模式:     codebuddy
批处理模式:   codebuddy --print "prompt"
```

| 参数 | 说明 | 编排用途 |
|------|------|---------|
| `-p` / `--print` | 非交互输出后退出 | smoke test / 小任务 |
| `--model <model>` | 指定模型 ID，如 `kimi-k2.6` | 模型路由 |
| `--permission-mode <mode>` | `acceptEdits` / `bypassPermissions` / `default` / `plan` | 自动化控制 |
| `-y` / `--dangerously-skip-permissions` | 跳过权限检查 | 沙箱 worktree 中可用 |
| `--tools <value>` | 限制内置工具，空字符串表示禁用工具 | smoke test |
| `--output-format <fmt>` | `text` / `json` / `stream-json` | PM 解析 |
| `--worktree [name]` | 创建 git worktree | 不建议替代 PM 手动 worktree |
| `--tmux` | 配合 `--worktree` 创建 tmux | 不建议替代 PM 手动 tmux |
| `--session-id <uuid>` | 指定 CLI 会话 ID | 可追踪会话 |
| `--system-prompt` / `--append-system-prompt` | 系统提示 | 角色定制 |
| `--mcp-config` / `--strict-mcp-config` | MCP 配置 | 工具注入 |
| `--acp` | ACP 模式 | 协议集成 |

### 5A.3 tmux Worker 启动模式

推荐 PM 先用 `spawn-worker.sh` 创建 worktree，再在该 worktree 内启动交互式 CodeBuddy：

```bash
tmux new-session -d \
  -s wr-ch07-codebuddy-kimi-k26-r1 \
  -c /path/to/worktree \
  'bash -lc '\''exec "/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/bin/codebuddy" \
    --model kimi-k2.6 \
    --permission-mode bypassPermissions \
    --session-id wr-ch07-codebuddy-kimi-k26-r1'\'''
```

短 smoke test 可用：

```bash
"/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/bin/codebuddy" \
  --print \
  --model kimi-k2.6 \
  --permission-mode default \
  --tools '' \
  --output-format text \
  '只回复 OK，不要做任何文件操作。'
```

### 5A.4 实测注意事项

- 每个新 worktree 首次启动会询问信任目录。PM 只选择 `Trust folder only`，不要信任 `worktrees/**` 父目录。
- `--model kimi-k2.6` 虽不一定出现在 help 列表中，但可通过短提示词和交互界面的 `Kimi-K2.6` 标识确认。
- 书稿评测 r1 已完整跑通：review、正文修订、self-check、result、metadata、commit、sentinel done。
- worker 可能在提交后更新 `metadata.json` 的 `commit_sha` / `status` 字段，导致一个未提交尾巴。PM 收口时要检查 `git status --short`，若只剩 metadata 完成态字段，可补一个 `chore(eval): finalize codebuddy kimi metadata` 提交。
- 交互式 r2 bootstrap 曾出现 CodeBuddy 内部 shell/write 工具长时间挂起。若 1-2 分钟没有 `STATUS.json`，PM 应先 Esc 中断，检查无业务改动后重启 tmux session；必要时由 PM 仅在 Session Context 中写入“重启中”状态，再投递 Full Prompt。业务正文和报告仍应由 worker 完成。
- 对长任务优先交互式 tmux，不建议一发 `--print` 跑完整书稿 worker；交互式模式便于处理信任目录、权限、工具挂起和 prompt 纠偏。

---

## 6. Gemini CLI（`gemini`）

### 6.1 核心参数速查

```
用法: gemini [query..]            # 交互模式
      gemini -p "prompt"          # 非交互（headless）模式
```

| 参数 | 说明 | 编排用途 |
|------|------|---------|
| `-p` / `--prompt <TEXT>` | 非交互模式 + prompt | worker 批处理 |
| `-m` / `--model <MODEL>` | 指定模型 | 模型路由 |
| `-i` / `--prompt-interactive <TEXT>` | 执行 prompt 后继续交互 | 半自动 |
| `-s` / `--sandbox` | 沙箱模式 | 安全控制 |
| `-y` / `--yolo` | 自动批准所有操作 | 沙箱自动化 |
| `--approval-mode <MODE>` | `default` / `auto_edit` / `yolo` / `plan` | 精细审批控制 |
| `--experimental-acp` | ACP 模式 | 协议集成 |
| `--allowed-mcp-server-names` | 允许的 MCP server | 工具白名单 |
| `--allowed-tools` | 不需确认即可运行的工具 | 工具白名单 |
| `-e` / `--extensions` | 使用的扩展列表 | 能力控制 |
| `-l` / `--list-extensions` | 列出可用扩展 | 能力探索 |
| `-r` / `--resume <id>` | 恢复会话（`latest` 或 index） | session 管理 |
| `--list-sessions` | 列出可用会话 | session 探索 |
| `--delete-session <id>` | 删除会话 | session 清理 |
| `--include-directories <dirs>` | 额外工作目录 | 跨目录访问 |
| `-o` / `--output-format <fmt>` | `text` / `json` / `stream-json` | PM 解析 |
| `--raw-output` | 不消毒模型输出 | 调试（有安全风险） |

### 6.2 子命令

| 子命令 | 说明 |
|--------|------|
| `mcp` | MCP 服务器管理 |
| `extensions` | 扩展管理 |
| `skills` | 技能管理 |
| `hooks` | Hook 管理 |

### 6.3 Worker 启动模式

**批处理**：
```bash
gemini -p "$(cat /tmp/task.prompt.md)" -m gemini-2.5-pro -y
```

**tmux 交互式**：
```bash
tmux new-session -d -s worker-gemini -c /path/to/worktree \
  'gemini -y --approval-mode auto_edit -m gemini-2.5-pro'
```

**审批模式分级**：
```bash
# plan 模式（只读，不执行）
gemini --approval-mode plan -p "分析这个代码库的架构"

# auto_edit 模式（自动批准编辑，但执行命令仍需确认）
gemini --approval-mode auto_edit -p "修复这个 bug"

# yolo 模式（全自动）
gemini --approval-mode yolo -p "重构这个模块"
```

### 6.4 与 Skill 集成要点

- Gemini CLI 的 `--approval-mode` 提供最细粒度的审批控制（4 级）
- `-p` 是 headless 模式的标准入口，支持 stdin pipe
- 原生支持 `stream-json` 输出格式
- `--experimental-acp` 标记为实验性，ACP 稳定性待验证
- Gemini CLI 的子命令生态（extensions/skills/hooks）与 Claude Code 结构类似
- `--sandbox` 是布尔开关（不像 Codex 有多级 sandbox mode）

---

## 7. QoderWork CLI（`qoderclicn` / `qodercli`）

> 详细研究见 `references/07-qoderwork-cli-worker.md`。本节为速查补充。

### 7.1 核心参数速查

```
用法: qoderclicn [options] [query...]

交互模式:     qoderclicn
批处理模式:   qoderclicn -p "prompt"
```

| 参数 | 说明 | 编排用途 |
|------|------|---------|
| `-p` / `--print` | 非交互模式 | worker 批处理 |
| `-m` / `--model <model>` | 指定模型 key | 模型路由 |
| `-w` / `--cwd <dir>` | 工作目录 | 目录指定 |
| `--permission-mode <mode>` | `default` / `accept_edits` / `bypass_permissions` / `dont_ask` / `auto` | 自动化控制 |
| `--dangerously-skip-permissions` | 跳过所有权限 | 沙箱专用 |
| `--system-prompt <text>` | 自定义系统提示词 | 角色定制 |
| `--append-system-prompt <text>` | 追加系统提示词 | 增量指令 |
| `--mcp-config <config>` | MCP 服务器配置 | 工具注入 |
| `--strict-mcp-config` | 只用 mcp-config 的 server | 工具隔离 |
| `--tools <tools...>` | 限制内置工具 | 能力收窄 |
| `--allowed-tools` / `--disallowed-tools` | 工具白/黑名单 | 精细控制 |
| `--attachment <file>` | 附加文件 | 上下文注入 |
| `--max-output-tokens <size>` | 最大输出 token | 预算控制 |
| `--reasoning-effort <level>` | 推理努力程度 | 质量/成本平衡 |
| `--context-window <size>` | 显式上下文窗口 | 适配任务 |
| `-c` / `--continue` | 继续最近会话 | 断点续跑 |
| `-r` / `--resume [id]` | 恢复指定会话 | session 管理 |
| `--worktree [name]` | 创建 git worktree | 建议仍由 PM 手动创建 worktree |
| `--agent <name>` / `--agents <json>` | Agent 管理 | 角色定制 |
| `--setting-sources <source>` | 配置源 | 环境控制 |
| `--settings <json>` | 额外 settings | 运行时配置 |

### 7.2 可用模型

| Key | 模型 |
|-----|------|
| `qmodel_latest` | Qwen3.7-Max |
| `qmodel` | Qwen3.7-Plus |
| `q36fmodel` | Qwen3.6-Flash |
| `dmodel` | DeepSeek-V4-Pro |
| `dfmodel` | DeepSeek-V4-Flash |
| `gm51model` | GLM-5.1 |
| `kmodel` | Kimi-K2.6 |
| `mmodel` | MiniMax-M2.7 |

### 7.3 关键限制

- **不能从 QoderWork 桌面端内部启动**（SDK 环境变量干扰），必须在干净终端运行
- 认证和额度与桌面端共用 `~/.qoderworkcn/`
- CN 版与国际版是两个 CLI：CN 版为 `/Applications/QoderWork CN.app/Contents/Resources/bin/qoderclicn`，国际版为 `/Applications/QoderWork.app/Contents/Resources/bin/qodercli`
- `/usr/local/bin/qoder` 可能指向旧 Qoder 编辑器 CLI，不是 QoderWork agent CLI
- 有 `--worktree` 参数，但多 Agent 编排建议仍由 PM 用 `spawn-worker.sh` 手动创建 worktree / 分支 / Session Context，再用 `tmux -c <worktree>` 启动 CLI
- 新 worktree 首次启动会询问信任目录，只选择当前 folder
- 书稿评测中 `qmodel_latest` 已确认显示为 `Qwen3.7-Max Model`，可跑 `writing-reviewer` 单章 worker

---

## 8. Rudder（`rudder`）

> Rudder 更偏项目管理/编排工具而非纯 coding agent，但其 `agent` 子命令可作为 worker。

### 8.1 核心参数速查

```
用法: rudder [options] [command]

启动:       rudder run            # 引导启动 + 运行
诊断:       rudder doctor         # 健康检查
```

| 参数/子命令 | 说明 |
|-------------|------|
| `start` | 启动 Rudder Desktop |
| `run` | 引导启动并运行 |
| `onboard` | 首次设置向导 |
| `doctor` | 诊断检查 |
| `agent` | Agent 操作 |
| `issue` | Issue 操作 |
| `worktree` | Worktree 管理 |
| `worktree:make <name>` | 创建隔离 worktree 实例 |
| `worktree:cleanup <name>` | 清理 worktree |
| `plugin` | 插件管理 |
| `auth` | 认证管理 |
| `context` | CLI 上下文 profile |

### 8.2 与 Skill 集成要点

- Rudder 的 `worktree:make` / `worktree:cleanup` 可作为 worktree 生命周期管理的替代工具
- `rudder agent` 可操作 agent，但具体能力取决于 Rudder 实例配置
- 更适合作为编排层的补充（issue 追踪、worktree 管理），而非纯 coding worker
- 与 SKILL.md 的 spawn-worker.sh 思路类似，但走 Rudder 自己的基础设施

---

## 9. 跨 CLI 对比矩阵

### 9.1 Worker 能力对比

| 能力 | Claude Code | Codex | OpenCode | Hermes | Kimi | Gemini | QoderWork |
|------|-------------|-------|----------|--------|------|--------|-----------|
| 批处理模式 | `claude -p` | `codex exec` | `opencode run` | `hermes chat -q` | `kimi --print -c` | `gemini -p` | `qoderclicn -p` |
| stream-json | ✓ | ✗ | `--format json` | ✗ | ✓ | ✓ | ✓ |
| ACP 服务器 | ✗ | ✗ | ✓ `acp` | ✓ `acp` | ✓ `--acp` | ✓ `--experimental-acp` | ✗ |
| 原生 worktree | ✓ `--worktree` | ✗ | ✗ | ✓ `--worktree` | ✗ | ✗ | ✓ `--worktree` |
| 自定义系统提示 | ✓ | ✗（需 config） | ✗（需 config） | ✗（需 config） | ✓ `--agent-file` | ✗ | ✓ |
| MCP 工具注入 | ✓ `--mcp-config` | ✓ `mcp` | ✓ `mcp` | ✓ `mcp` | ✓ `--mcp-config` | ✓ `mcp` | ✓ `--mcp-config` |
| 工具白/黑名单 | ✓ | ✗ | ✗ | ✓ `--toolsets` | ✗ | ✓ `--allowed-tools` | ✓ |
| 权限分级 | 5 级 | 3 级 sandbox | ✗ | `--yolo` | `--yolo` | 4 级 approval | 5 级 |
| 会话管理 | ✓ | ✓ `resume` | ✓ `session` | ✓ `sessions` | ✓ `--continue` | ✓ `--resume` | ✓ |
| 多 provider | settings 文件 | config.toml + profile | config.toml | pooled auth | 单 provider | 单 provider | 平台统一 |

### 9.2 tmux Worker 启动模板对比

```bash
# === Claude Code ===
tmux new-session -d -s W -c WT "$WORKER_COMMAND"  # WORKER_COMMAND from render-runtime-profile.sh

# === Codex ===
tmux new-session -d -s W -c WT 'codex -m o4-mini -s workspace-write'

# === OpenCode ===
tmux new-session -d -s W -c WT 'opencode --model anthropic/claude-sonnet-4-20250514'

# === Hermes ===
tmux new-session -d -s W -c WT 'hermes --yolo -m gpt-4o'

# === Kimi ===
tmux new-session -d -s W -c WT 'kimi -y -m kimi-latest'

# === Gemini ===
tmux new-session -d -s W -c WT 'gemini -y --approval-mode auto_edit -m gemini-2.5-pro'

# === QoderWork ===
tmux new-session -d -s W -c WT 'qoderclicn -m qmodel_latest --permission-mode auto'

# === CodeBuddy / WorkBuddy ===
tmux new-session -d -s W -c WT 'codebuddy --model kimi-k2.6 --permission-mode bypassPermissions'
```

其中 `W` = session name, `WT` = worktree path。Claude Code 实际派发时优先用 `render-runtime-profile.sh` 生成 `WORKER_COMMAND`，避免漏掉 registry/settings wrapper 参数。

---

## 10. 选用建议

| 场景 | 推荐 CLI | 理由 |
|------|---------|------|
| 主力 coding worker | Claude Code | 最成熟的 tool use + 最丰富的参数控制 |
| OpenAI 模型路由 | Codex | 直接消耗 OpenAI 额度，sandbox 分级 |
| 多 provider 灵活切换 | OpenCode / Hermes | 内置多 provider 管理 |
| 法律检索 MCP 任务 | QoderWork | 元典/企查查 MCP 工具链 |
| 需要 ACP 协议 | OpenCode / Hermes / Kimi | 原生 ACP 服务器 |
| Google 模型路由 | Gemini | 直接消耗 Google AI 额度 |
| 轻量级/Kimi 模型 | Kimi | 参数简洁，原生 stream-json |
| 项目管理/编排辅助 | Rudder | issue/worktree/agent 管理 |
| 本地开源模型 | Codex `--oss` | lmstudio/ollama 集成 |
