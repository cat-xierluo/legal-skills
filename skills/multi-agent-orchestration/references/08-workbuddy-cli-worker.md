# WorkBuddy / CodeBuddy CLI（`codebuddy`）Worker 可行性研究

> 本文档为 SKILL.md 的补充参考文档，记录 WorkBuddy/CodeBuddy CLI 作为 worker backend 的可行性研究。
> 研究日期：2026-06-20
> 复测日期：2026-06-21（CodeBuddy CLI `--model kimi-k2.6`，书稿 worker 三轮评测场景）

---

## 1. 概述

WorkBuddy（底层为 CodeBuddy Code）桌面端内置了 `codebuddy` CLI 二进制，功能对标 Claude Code，可以作为 multi-agent orchestration 的 worker backend 使用。核心价值是利用 WorkBuddy 桌面端的登录态和 token 额度，无需额外配置 API Key，CLI 自动复用 GUI 的认证和额度池。2026-06-21 已用 `--model kimi-k2.6` 跑通 `writing-reviewer` 书稿 worker 三轮评测。

与 Claude Code 的关系：WorkBuddy 的 CLI 参数体系与 Claude Code 高度兼容（`-p`、`--print`、`--output-format`、`--settings`、`--permission-mode`、`--worktree`、`--mcp-config` 等），可直接沿用 SKILL.md 中对 Claude Code worker 的大部分模板。

## 2. 二进制位置与安装

| 属性 | 值 |
|------|-----|
| 二进制路径 | `/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/bin/codebuddy` |
| 当前版本 | v2.103.3（随桌面端自动更新） |
| 建议 alias | `alias cbc='\"/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/bin/codebuddy\"'` 加到 `~/.zshrc` |
| 认证/配置目录 | `~/.codebuddy/`、`~/.workbuddy/`（随版本/组件分布，均与 WorkBuddy 桌面端共用） |

### 2.1 版本验证

```bash
"/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/bin/codebuddy" --version
```

二进制随 WorkBuddy 桌面端自动更新，无需手动升级。

## 3. CLI 关键参数

```
用法: codebuddy [options] [query...]

交互模式:     codebuddy                                              # 启动 REPL
             codebuddy "初始提示词"                                   # 带 prompt 启动 REPL
批处理模式:   codebuddy -p "prompt"                                  # 打印后退出
             cat task.md | codebuddy -p "分析"                        # 管道输入
继续会话:     codebuddy -c                                           # 继续最近会话
             codebuddy -c -p "prompt"                                # SDK 模式继续
恢复会话:     codebuddy -r <session-id> "prompt"                     # 恢复指定会话
```

### 3.1 关键参数速查

| 参数 | 说明 | 编排用途 |
|------|------|---------|
| `-p` / `--print` | 非交互模式，打印后退出 | worker 批处理必选 |
| `-y` / `--dangerously-skip-permissions` | 跳过权限提示 | 无头模式必加 |
| `--output-format <fmt>` | `text` / `json` / `stream-json` | stream-json 适合 PM 解析 |
| `--model <model>` | 指定模型（别名或全名） | 模型路由 |
| `--settings <file-or-json>` | 加载额外 settings 配置 | 第三方 provider 路由 |
| `--setting-sources <src>` | 指定配置源：`user` / `project` / `local` | 控制加载哪些配置层 |
| `--system-prompt <text>` | 替换整个系统提示词 | 完全自定义角色 |
| `--system-prompt-file <file>` | 从文件加载系统提示词（仅打印模式） | 可复现的提示词模板 |
| `--append-system-prompt <text>` | 追加到默认系统提示词 | 增量指令注入 |
| `--permission-mode <mode>` | `default` / `acceptEdits` / `bypassPermissions` / `plan` | worker 自动化程度 |
| `--subagent-permission-mode <mode>` | 子代理/团队成员默认权限模式 | Team 模式控制 |
| `--mcp-config <config>` | 从 JSON 文件加载 MCP 服务器 | 工具注入 |
| `--allowedTools <tools>` | 允许的工具列表（空格或逗号分隔） | 工具白名单 |
| `--disallowedTools <tools>` | 禁止的工具列表 | 工具黑名单 |
| `--tools <tools...>` | 限制可用内置工具集（白名单） | 收窄 worker 能力 |
| `--max-turns <n>` | 最大代理轮次 | 控制预算/防跑飞 |
| `-c` / `--continue` | 继续最近会话 | 断点续跑 |
| `-r` / `--resume <id>` | 恢复指定会话 | session 管理 |
| `--session-id <uuid>` | 使用指定 session ID | 可预测 session |
| `-i` / `--prompt-interactive <text>` | 执行 prompt 后继续交互 | 半自动模式 |
| `--worktree [name]` | 在独立 git worktree 中运行 | 文件隔离 |
| `--tmux` | （配合 `--worktree`）创建 tmux session | 终端隔离 |
| `--agent <name>` | 指定 agent（内置或自定义） | 角色定制 |
| `--agents <json>` | JSON 动态定义自定义 Sub-Agent | 多角色编排 |
| `--add-dir <dirs>` | 添加额外工作目录 | 跨目录访问 |
| `--verbose` | 启用详细日志 | 排障 |
| `--debug` | 启用调试模式 | 深度排障 |
| `--bg` | 后台运行（detached 模式） | 守护进程 |
| `--name <name>` | 后台会话名称（配合 `--bg`） | 进程管理 |
| `--sandbox` | 在沙箱中运行（容器/E2B） | 安全隔离 |

### 3.2 子命令速查

| 子命令 | 说明 |
|--------|------|
| `codebuddy update` | 更新到最新版本 |
| `codebuddy mcp` | 配置 MCP 服务器 |
| `codebuddy daemon start/stop/status/restart` | Daemon 守护进程管理 |
| `codebuddy ps` | 列出所有活跃 Worker 进程 |
| `codebuddy logs <pid\|name>` | 查看 Worker 日志 |
| `codebuddy attach <pid\|name>` | 附加到后台 Worker |
| `codebuddy kill <pid\|name>` | 终止 Worker 进程 |
| `codebuddy --serve` | 启动 HTTP 服务（Web UI + REST API + ACP 协议） |

## 4. 模型指定方式

### 4.1 WorkBuddy 平台内置模型（零配置，用平台额度）

WorkBuddy 平台内置多种模型，CLI 默认继承桌面端的模型配置和额度。**直接通过 `--model` 指定即可，无需设置任何环境变量**。

#### 已知可用模型标识

| --model 参数 | 模型 | 倍率 | 适用场景 |
|-------------|------|------|---------|
| `kimi-k2.6` | Kimi K2.6 | 中 | 2026-06-21 书稿 worker 三轮评测已跑通，适合写作审稿/修订对比实验 |
| `kimi-k2.7` | Kimi K2.7 | 中 | help 已列出，可按额度和稳定性另行验证 |
| `deepseek-v4-flash` | DeepSeek V4 Flash | 低 | **推荐默认**，经济实惠、速度快、能力均衡，适合大多数 worker 任务 |
| `deepseek-v4-pro` | DeepSeek V4 Pro | 中 | 复杂推理、深度法律分析、架构设计 |
| `minimax-m3` | MiniMax M3 | 低 | 多模态任务（支持图片输入），合同扫描件分析、证据图片识别等 |
| `sonnet` | Claude Sonnet 系列 | 高 | 最复杂 coding / 分析（配额充裕时） |
| `opus` | Claude Opus 系列 | 高 | 顶级推理（配额充裕时） |
| `auto` | 自动路由 | 动态 | 系统按任务复杂度自动选模型 |

```bash
# 默认推荐：DeepSeek V4 Flash（低倍率、经济实惠）
codebuddy --model deepseek-v4-flash -p "检索相关案例" -y

# 书稿评测：Kimi K2.6
codebuddy --model kimi-k2.6 -p "审稿并修订指定章节" -y

# 复杂法律分析：DeepSeek V4 Pro
codebuddy --model deepseek-v4-pro -p "分析判决书争议焦点" -y

# 多模态任务：MiniMax M3（支持图片输入）
codebuddy --model minimax-m3 -p "分析这份合同扫描件中的风险条款" -y

# 自动路由（偷懒用）
codebuddy --model auto -p "分析这个法律问题" -y
```

> **推荐策略**：Worker 默认用 `deepseek-v4-flash`（倍率低、能力强），涉及图片/扫描件的任务切 `minimax-m3`，需要深度推理时再升级到 `deepseek-v4-pro`。具体可用模型取决于你的 WorkBuddy 订阅套餐，可在桌面端底部模型选择器或 `/model` 命令查看完整列表。

### 4.2 可选：对接自有 API Key（降本兜底，非主要场景）

> **设计原则**：使用 WorkBuddy/QoderWork 这类平台 CLI 的核心价值是**零配置吃平台额度**。如果你有自己的 API Key（如 DeepSeek、Anthropic），直接用 Claude Code + 环境变量更直接，不需要绕 WorkBuddy CLI 这一层。以下仅作为极端降本或平台额度耗尽时的兜底参考。

```bash
# 如有自有 DeepSeek Key（通常不需要，直接用 Claude Code 即可）
export CODEBUDDY_BASE_URL="https://api.deepseek.com"
export CODEBUDDY_API_KEY="<your-key>"
codebuddy --model deepseek-v4-pro -p "任务" -y
```

### 4.3 环境变量速查

| 环境变量 | 说明 |
|----------|------|
| `CODEBUDDY_AUTH_TOKEN` | WorkBuddy 平台认证令牌（平台接口调用，CLI 自动继承桌面端，通常无需手动设） |
| `CODEBUDDY_INTERNET_ENVIRONMENT` | 网络环境：`internal`（中国版）/ `ioa`（iOA 企业版） |
| `MAX_THINKING_TOKENS` | 扩展思考 token 预算 |
| `CODEBUDDY_API_KEY` | API 密钥（仅对接自有第三方服务时使用） |
| `CODEBUDDY_BASE_URL` | API 端点地址（仅对接自有第三方服务时使用） |
| `MAX_THINKING_TOKENS` | 扩展思考 token 预算 |

### 4.4 文生图模型

如需使用图片生成功能（worker 一般不需要）：

```bash
codebuddy --text-to-image-model your-image-model -p "任务" -y
```

环境变量控制：`CODEBUDDY_IMAGE_GEN_ENABLED`（设为 `false` 禁用）。

## 5. MCP 工具链集成

WorkBuddy CLI 支持通过 `--mcp-config` 加载 MCP 服务器：

```bash
# 从文件加载
codebuddy --mcp-config /path/to/mcp-servers.json -p "任务" -y

# 内联 JSON（仅通过 --settings 传入）
codebuddy --settings '{"mcpServers":{...}}' -p "任务" -y
```

MCP 配置也支持写入 `~/.codebuddy/mcp.json`，CLI 和桌面端共用。

> **注意**：WorkBuddy 桌面端的 MCP 连接器（飞书、腾讯文档、元典法律检索等）需要通过 GUI 授权启用。CLI 模式下，需要在 `mcp.json` 中预先配置和 Trust 这些连接器后才能使用。
>
> **⚠️ 2026-06-26 修正（用户澄清）**：WorkBuddy / CodeBuddy CLI 接入的 MCP（华宇元典法律检索、企查查等）**不是平台免费连接器，而是用户自己在外部配置的付费 API**（与其它 CLI 共用同一套 key/额度）。因此：
> - 这些 MCP 调用**消耗用户付费 API 额度**，不是 WorkBuddy 平台免费额度。
> - **不需要 MCP 的 worker（如纯正文修订）务必 `--strict-mcp-config --mcp-config <empty>` 关掉 MCP**，避免误触发付费 API（codebuddy-spawn.sh 已默认关；见 §6.7 + DEC-037）。
> - 只有明确要用法律检索 / 工商查询的 worker 才开 MCP，且要知道在花付费额度。

### 5.1 MCP 相关环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MCP_TIMEOUT` | MCP 服务器连接超时（毫秒） | - |
| `MCP_TOOL_TIMEOUT` | MCP 工具执行超时（毫秒） | - |
| `MAX_MCP_OUTPUT_TOKENS` | MCP 工具响应最大 token 数 | 20000 |
| `CODEBUDDY_DEFERRED_TOOLS_MCP_READY_WAIT_MS` | 渲染延迟工具描述前等待 MCP 就绪的毫秒数 | 2500 |
| `CODEBUDDY_DISABLE_MCP_LARGE_OUTPUT_FILES` | 设为 `1` 禁用 MCP 超大响应落盘 | 启用 |

## 6. 关键限制与注意事项

### 6.1 SDK 环境变量冲突（类似 QoderWork）

WorkBuddy 桌面端运行时注入的 hooks 和 permission 环境变量不影响 CLI 独立运行。CLI 直接从命令行启动时不会走 SDK 模式，**无需像 QoderWork 那样清除环境变量**。已验证 CLI 在独立终端中可直接运行。

但如果从 WorkBuddy 桌面端的"内置终端"或 SDK 模式下启动，可能会遇到类似问题。建议始终在干净终端/tmux session 中运行 CLI worker。

### 6.2 权限与安全

无头模式（`-p`）执行涉及文件读写、命令执行、网络请求等操作时，**必须加 `-y`（`--dangerously-skip-permissions`）**，否则操作会被阻止。

```bash
# ❌ 不加 -y 可能被阻止
codebuddy -p "写一个文件到 /tmp/test.txt"

# ✅ 正确用法
codebuddy -p -y "写一个文件到 /tmp/test.txt"
```

> **安全提示**：只在受信任的环境和明确的任务中使用 `-y`。建议配合 `--sandbox` 或 worktree 隔离使用。

### 6.3 额度共享

CLI 和 WorkBuddy 桌面端共用 `~/.codebuddy/` 下的认证和额度池。CLI 消耗的 token 额度从同一账户扣除，不会独立计费。

### 6.4 会话管理

- CLI 的会话数据存储在 `~/.codebuddy/projects/{projectDir}/{sessionId}/`
- 可通过 `--session-id` 指定固定 session ID，方便 PM 追踪
- 支持 `--continue` 和 `--resume` 恢复历史会话
- 后台 worker 通过 `--bg --name <name>` 启动，用 `ps` / `logs` / `kill` 管理

### 6.5 多 Worker 并发额度

多个 CLI 实例共享同一账户额度，需注意并发控制和配额分配。建议通过 SKILL.md 的 Wave-Based Orchestration 管理 provider slot。

**2026-06-26 并发实测（v0.10.7 cross-model eval）：** 5 个 codebuddy worker 同时并发抢 WorkBuddy 共享额度时，**`hy3-preview-agent` 被拖得最狠**（preview 模型对共享额度竞争最敏感，单 run 耗时显著拉长）；其余模型（kimi/deepseek/glm-5.1/glm-5v-turbo）也有不同程度的变慢。

建议：
- **codebuddy 同账户并发 ≤ 3**；超过 3 个 worker 时优先**跨 provider 分流**（一部分走 codebuddy 平台额度，一部分走 claude-code 第三方 provider 或 qoderwork 免费 Qwen 额度），而不是硬压在单一 WorkBuddy 账户上。
- 额度敏感模型（preview / 高倍率）单独给一个低并发 slot，避免被其它 worker 拖垮。
- 评测 fan-out 场景尤其要遵守：12 模型同 backend 并发会把共享额度打满，导致批数/耗时失真，污染 cross-model 经济性对比（见 `agent-eval-lab` cross-model 评测方法论的"经济性对比要在额度不竞争时测"）。

### 6.6 2026-06-21 书稿 worker 实测

在 `writing-reviewer` ch07 多模型评测中，`codebuddy --model kimi-k2.6` 已跑通三轮：

- 手动 worktree + `spawn-worker.sh --worker-backend codebuddy`
- 交互式 tmux worker
- Bootstrap prompt 写 `STATUS.json`
- Full prompt 读取书稿上下文、写 review/result/metadata、修改 ch07、提交分支
- sentinel 在 `status="done"` 后关闭 tmux

观察到的行为：

- `--model kimi-k2.6` 可正常调用，交互界面显示 `Kimi-K2.6` 和 WorkBuddy internal usage billing。
- 当前 `codebuddy --help` 已列出 `kimi-k2.6` / `kimi-k2.7`；早期版本 help 可能滞后，仍可用短 smoke test 确认模型路由。
- r2 bootstrap 曾出现内部 shell/write 工具长时间挂起。若 1-2 分钟没有 `STATUS.json`，PM 应先 Esc 中断，确认无业务改动后重启 tmux session，再投递 Full Prompt。
- r3 曾把 review/result 写到主 worktree 并在根目录写 `STATUS.json`。PM 收口时必须同时检查工作目录、报告路径和 `git status --short`，必要时只把允许文件移回对应 worktree 并记录 `pm_notes`。
- worker 可能在提交后再次更新 `metadata.json` 的完成态字段，导致未提交尾巴。若只剩本轮报告目录下的 metadata，可补一个 `chore(eval): finalize codebuddy kimi metadata` 提交。

### 6.7 2026-06-26 复测更新（多模型 eval + 关键修复）

在 `writing-reviewer` v0.10.7 cross-model eval 中，codebuddy backend 并发跑了 3 个 worker（`kimi-k2.6` / `deepseek-v4-flash` / `deepseek-v4-pro`，同 ch08 baseline 71 hard FAIL），验证 backend 在多模型 fan-out 场景下端到端可用。kimi-k2.6 pilot 实测：before=71 → pass-1=51（一批 ≤20），无 path 漂移，产物全在 worktree 内。

**关键修复：eval snapshot 拷进 worktree（self-contained pattern）。**

- 根因：eval 的 skill 快照（`research/verification/.../skill-snapshots/<ver>/`）在主仓库是 **untracked**，fresh worktree 只能看到 tracked 文件，**看不到 snapshot**。
- claude-code worker 可用主仓库绝对路径绕过（能读 cwd 外文件）；**codebuddy 不行**——其 trust-folder 限制只允许读 cwd 内文件，主仓库路径读不到。
- 修复（backend 无关，推荐作为 eval worker 默认）：spawn 时把冻结 snapshot **拷一份进 worktree**（如 `cp -R <snapshot> <worktree>/skill-snapshot-v0107`），worker 用 worktree-local 相对路径 `./skill-snapshot-v0107` 读。彻底消除跨目录访问 / trust 限制 / path 漂移三类问题。
- 同理 eval 的 `runs/` 输出目录也写 worktree 内（worker 自建），commit 后由 PM 拷回主仓库归档。

**spawn helper（已沉淀）：** `research/verification/writing-reviewer-skill-version-eval-260622/codebuddy-spawn.sh`
- 一条命令完成：worktree add + snapshot 拷贝 + session context + tmux（codebuddy 交互 + MCP off）。
- 用法：`codebuddy-spawn.sh <model> <model_short> <ch_num> <ch_file> <baseline_branch> <run_name> <prompt_file>`
- 交互部分（trust prompt / bootstrap / full mission）仍由 PM 用 `tmux send-keys` 发（trust 选 option 1 "Trust folder only"，**不要**信任父目录避免跨 worktree 误读）。

**MCP off（正文修订任务）：** `--strict-mcp-config --mcp-config /tmp/empty-mcp.json`（`/tmp/empty-mcp.json` = `{"mcpServers":{}}`）。修订任务不用 MCP，关掉减前言；避免 WorkBuddy MCP 连接器 GUI 授权弹窗。

**render-runtime-profile 已支持 codebuddy / qoderwork-cn（2026-06-26 补齐）：** `scripts/render-runtime-profile.sh` 现支持 `--backend codebuddy` 和 `--backend qoderwork-cn`,与 claude-code/codex/opencode 同走统一 spawn 路径。要点:
- codebuddy: 默认二进制 `/Applications/WorkBuddy.app/.../codebuddy`,batch 恒加 `-y`(headless 要求),`--no-mcp` 注入 `--strict-mcp-config --mcp-config '{"mcpServers":{}}'`,`--dangerously-skip-permissions` 在交互式也加 `-y`。
- qoderwork-cn: 默认二进制 `/Applications/QoderWork CN.app/.../qoderclicn`(路径含空格,脚本内部 `%q` 保护),**自动前置 `env -u` 清除 6 个 SDK 变量**(`QODER_AGENT_SDK_ENTRYPOINT` 等,见 ref 07 §5.1),`--no-mcp` 同 codebuddy。
- snapshot-copy-into-worktree(§6.7 上文 + DEC-037)仍由 spawn helper 或 PM 在 spawn 后拷贝;render-runtime-profile 只渲染命令,不拷文件。
- eval 场景(codebuddy/qoder worktree 隔离)推荐组合:`--backend {codebuddy|qoderwork-cn} --model <m> --no-mcp --dangerously-skip-permissions`(交互式)或 `--mode batch --prompt-file <f>`(批处理),配合 `spawn-worker.sh`。

**收口仍需 PM 检查（沿用 §6.6 r3 教训）：** 即使有 snapshot-copy，PM 收口仍要 `git -C <worktree> status --short` 确认产物全在 worktree 内、主仓库无 worker 误写；commit 后检查 metadata 尾巴。

## 7. tmux Worker 启动示例

### 7.1 非交互批处理模式（推荐）

```bash
# 基本批处理
"/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/bin/codebuddy" \
  -p "$(cat /tmp/task.prompt.md)" \
  --output-format json \
  -y

# tmux 批处理（隔离执行）
tmux new-session -d \
  -s worker-workbuddy \
  -c /path/to/worktree \
  "bash -lc '/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/bin/codebuddy \
   --model deepseek-v4-flash \
   --permission-mode acceptEdits \
   -p \"\$(cat /tmp/task.prompt.md)\" \
   -y'"
```

### 7.2 交互式模式（可人工接管）

```bash
tmux new-session -d \
  -s worker-workbuddy \
  -c /path/to/worktree \
  'codebuddy --model deepseek-v4-flash --permission-mode acceptEdits'
```

### 7.3 使用 worktree 隔离（原生支持）

```bash
# WorkBuddy/CodeBuddy 原生支持 --worktree（自动创建 git worktree + 可选 tmux）
codebuddy --worktree feature/legal-research --tmux -p "任务描述" -y
```

### 7.4 后台 Worker 模式

```bash
# 启动后台 worker
codebuddy --bg --name legal-research -p "检索相关案例" -y

# 查看状态
codebuddy ps
codebuddy logs legal-research

# 附加到 worker
codebuddy attach legal-research

# 终止 worker
codebuddy kill legal-research
```

### 7.5 多模型/多 provider 路由（Worker 隔离）

```bash
# Worker A：书稿评测 / 写作审稿（Kimi K2.6）
tmux new-session -d -s worker-wb-kimi -c /path/to/worktree-A \
  'codebuddy --model kimi-k2.6 --permission-mode bypassPermissions'

# Worker B：深度推理型（V4 Pro）
tmux new-session -d -s worker-wb-pro -c /path/to/worktree-B \
  'codebuddy --model deepseek-v4-pro --permission-mode acceptEdits'

# Worker C：多模态型（MiniMax M3，处理图片/扫描件）
tmux new-session -d -s worker-mm-img -c /path/to/worktree-C \
  'codebuddy --model minimax-m3 --permission-mode acceptEdits'
```

### 7.6 与 spawn-worker.sh 集成

可作为 `custom CLI` worker 通过 `spawn-worker.sh` 启动：

```bash
bash scripts/spawn-worker.sh \
  --project /path/to/repo \
  --branch feature/legal-research \
  --session wb-legal-research \
  --worker-backend codebuddy \
  --runtime-profile codebuddy-kimi-k26 \
  --api-provider workbuddy \
  --model kimi-k2.6 \
  --provider-slot workbuddy-kimi-k26-1 \
  --command "bash -lc 'exec \"/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/bin/codebuddy\" --model kimi-k2.6 --permission-mode bypassPermissions --session-id wb-legal-research'"
```

### 7.7 HTTP 服务模式（REST API + Web UI）

WorkBuddy CLI 支持启动 HTTP 服务，适合需要 REST API 集成的场景：

```bash
# 启动 HTTP 服务（含 Web UI、REST API、ACP 协议）
codebuddy --serve --port 8080

# 指定监听地址
env SERVER__HOST=0.0.0.0 SERVER__PORT=8080 codebuddy --serve
```

## 8. 适用场景

| 场景 | 推荐度 | 理由 |
|------|--------|------|
| 复用 WorkBuddy 额度的 coding worker | 高 | 自动继承 GUI 登录态，零配置 |
| 法律文书分析/合同审阅 | 高 | 负载 WorkBuddy 法律 Skills |
| 需要 MCP 工具链的任务 | 高 | 支持 --mcp-config 加载飞书/腾讯文档/元典等 |
| 多 Worker 并行编排 | 高 | 原生 --worktree + --tmux + --bg |
| 对接第三方模型降成本 | 高 | 通过环境变量/--settings 灵活切换 provider |
| 长上下文深度推理 | 中 | 取决于你的 WorkBuddy 套餐和模型选择 |
| 需要 ACP 协议集成的场景 | 中 | `--serve` 模式支持 ACP，但 CLI 无独立 ACP 子命令 |
| 纯本地/离线推理 | 低 | 无内置本地模型支持，需依赖 API |

## 9. 与现有 Skill 框架的集成建议

- **backend 标识**：建议写具体执行面，例如 `codebuddy`；profile 标识可写 `codebuddy-kimi-k26` / `workbuddy-deepseek` / `workbuddy-custom`
- **spawn 集成**：走 custom CLI worker 路径，但 `--worker-backend` 可以写 `codebuddy` 这类可读标签，便于 STATUS/METADATA 追踪
- **权限模式**：无头批处理使用 `--permission-mode acceptEdits` 或 `-y`；tmux 交互式按自动化强度使用 `acceptEdits` / `bypassPermissions`
- **必加参数**：无头模式下 `-y` 是必须的（等同 Claude Code 的 `--dangerously-skip-permissions`）
- **checkpoint 兼容**：`codebuddy` 本身不产生 `STATUS.json`，需要在 worker prompt 中明确要求 worker 自行写入 checkpoint 三件套，或靠 git status + 文件系统巡检兜底
- **额度监控**：目前没有 CLI 方式查询剩余额度，需要登录 WorkBuddy 桌面端查看
- **参数相似度**：与 Claude Code 的参数体系高度兼容，SKILL.md 中 Claude Code worker 的大部分模板可直接迁移，仅需将 `claude` 替换为 `codebuddy` 并调整少量参数名（如 `--allowed-tools` → `--allowedTools`、`--disallowed-tools` → `--disallowedTools`）

### 9.1 Worker Prompt 模板

```markdown
你是 WorkBuddy CLI worker，运行在无头批处理模式。
你的任务是：[具体任务描述]

## 工作规范
- 工作完成后必须将结果写入 [输出文件路径]
- 如有 checkpoint 要求，写入 .claude/agent-sessions/ 下的 STATUS.json / RESULT.md / PATCH_SUMMARY.md
- 操作前检查 git 状态，完成后 git add + commit
- 遇到无法继续的问题时，在 RESULT.md 中记录 BLOCKED 状态和原因

## 运行约束
- 工作目录：[worktree 路径]
- 最大轮次限制已设置，请在限制内完成
- 收到权限确认提示时自动通过（已配置 --permission-mode）
```

### 9.2 与 Claude Code Worker 的关键差异

| 差异点 | Claude Code | WorkBuddy CLI |
|--------|-------------|---------------|
| 二进制名 | `claude` | `codebuddy` |
| 认证方式 | API Key / OAuth | 桌面端登录态自动继承 |
| 工具参数风格 | kebab-case（`--allowed-tools`） | camelCase（`--allowedTools`） |
| 后台 worker | 无 | `--bg` + `ps` / `logs` / `kill` |
| HTTP 服务 | 无 | `--serve`（Web UI + REST API + ACP） |
| 权限跳过 | `--dangerously-skip-permissions` | `-y` 或 `--dangerously-skip-permissions` |
| 第三方 Provider | `--settings` 文件 | 环境变量 + `--settings` 文件 |
| ACP 协议 | 无 | `--serve` 内嵌 |

### 9.3 成本优化策略

1. **小额任务用轻量模型**：通过 `CODEBUDDY_SMALL_FAST_MODEL` 指定小型模型处理翻译、格式化等轻任务
2. **复杂推理用大模型**：通过 `CODEBUDDY_BIG_SLOW_MODEL` 指定大型模型处理法律分析、代码重构等重任务
3. **对接第三方 API 降本**：将高频轻度任务路由到 DeepSeek 等低成本的第三方 API
4. **控制 max-turns**：通过 `--max-turns` 限制 worker 最大轮次，防止跑飞浪费额度

---

> **版本记录**：
> - 2026-06-21：补充 `kimi-k2.6` 三轮书稿 worker 评测实践、CodeBuddy checkpoint/path 偏差和 metadata finalize 收口规则。
> - 2026-06-20：初版，基于 WorkBuddy v2.103.3 CLI 实测编写。
