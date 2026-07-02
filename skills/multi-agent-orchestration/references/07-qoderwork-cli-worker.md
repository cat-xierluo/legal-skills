# QoderWork CLI (`qoderclicn`) Worker 可行性研究

> 本文档为 SKILL.md 的补充参考文档，记录 QoderWork CLI 作为 worker backend 的可行性研究。
> 研究日期：2026-06-20
> 复测日期：2026-06-21（CN 版 `qoderclicn` + Qwen3.7-Max，书稿 worker 三轮评测场景）

---

## 1. 概述

QoderWork 桌面端内置了 `qoderclicn` CLI 二进制，功能类似 Claude Code / Codex CLI，可以作为 multi-agent orchestration 的 worker backend 使用。核心价值是利用 QoderWork 平台的每日免费模型额度（如 Qwen3 Max）和内置 MCP 工具链（元典法律检索、企查查工商查询等）。

> **⚠️ 2026-06-26 修正（用户澄清）**：QoderWork CLI 接入的 MCP（元典法律检索、企查查等）**不是平台免费连接器，而是用户自己在外部配置的付费 API**（与其它 CLI 共用同一套 key/额度）。"免费"仅指 Qwen 等模型的每日额度；MCP 调用花的是用户付费 API。因此**不需要 MCP 的 worker（如纯正文修订）务必关 MCP**（`--strict-mcp-config` / 不加载 mcp-config），避免误触发付费 API；同 ref 08 §5 / DEC-037。

## 2. 二进制位置与安装

| 属性 | 值 |
|------|-----|
| CN 版二进制路径 | `/Applications/QoderWork CN.app/Contents/Resources/bin/qoderclicn` |
| 国际版二进制路径 | `/Applications/QoderWork.app/Contents/Resources/bin/qodercli` |
| 建议 symlink | `sudo ln -s '/Applications/QoderWork CN.app/Contents/Resources/bin/qoderclicn' /usr/local/bin/qoderclicn` |
| CN 版认证/配置目录 | `~/.qoderworkcn/` 与 `~/Library/Application Support/QoderWork CN/` |
| 国际版认证/配置目录 | `~/.qoderwork/` 与 `~/Library/Application Support/QoderWork/` |

同一机器可能同时安装：

- `/Applications/QoderWork CN.app`
- `/Applications/QoderWork.app`
- `/Applications/Qoder.app`（旧编辑器 CLI，`/usr/local/bin/qoder` 可能指向它，不是 agent CLI）

CN 版与国际版的登录状态、配置目录和 CLI 名称不同。评估 CN 额度时必须显式使用 `qoderclicn`，不要用 `/usr/local/bin/qoder` 代替。

### 2.1 PATH-less 检测（实测盲区）

`which qoderclicn` 在桌面端已装但未建 symlink 时会报 `not found`，导致 PM 误判 worker CLI 不可用。`scripts/check-dependencies.sh --backend qoderwork-cn` 现有多源检测：先查 `PATH`，再查已知 .app bundle 路径（CN 版 `/Applications/QoderWork CN.app/Contents/Resources/bin/qoderclicn` + 国际版 `/Applications/QoderWork.app/Contents/Resources/bin/qodercli`），检测到时给 `DEPENDENCY_WARN` + actionable fix 提示（spawn-worker.sh --command 传绝对路径 / `sudo ln -s`）。

不只 CI/构建环境依赖这段检测，PM 在新机器派 worker 前也应该跑：

```bash
bash scripts/check-dependencies.sh --backend qoderwork-cn --strict
```

## 3. CLI 关键参数

```
Usage: qoderclicn [options] [command] [query...]

关键参数：
  -p, --print                    非交互模式，打印响应后退出（适合 worker 批处理）
  -m, --model <model>            指定模型（默认和新模型用名称；自定义用 modelID）
  -w, --cwd <dir>                设置工作目录
  --system-prompt <text>         自定义系统提示词
  --append-system-prompt <text>  追加系统提示词
  --mcp-config <config>          加载 MCP 服务器配置（JSON 文件或 inline JSON）
  --permission-mode <mode>       权限模式：default / accept_edits / bypass_permissions / dont_ask / auto
  --dangerously-skip-permissions 跳过所有权限检查（慎用）
  --allowed-tools <tool>         允许的工具列表
  --disallowed-tools <tool>      禁止的工具列表
  --attachment <file>            附加文件到初始 prompt
  --max-output-tokens <size>     最大输出 token 数
  -c, --continue                 继续最近一次会话
  -r, --resume [id]              恢复指定会话
  -n, --name <name>              设置会话显示名
  --session-id <id>              使用指定会话 ID
  --reasoning-effort <level>     推理努力程度
  --context-window <size>        显式设置上下文窗口
  --list-models                  列出当前用户可用模型
  --agent <name>                 指定 agent
  --agents <json>                JSON 定义自定义 agents
  --output-format <format>       输出格式
  --input-format <format>        输入格式
```

## 4. 可用模型

| 模型 key | 对应模型 | 备注 |
|----------|---------|------|
| `qmodel_latest` | Qwen3.7-Max | 每日有免费额度 |
| `qmodel` | Qwen3.7-Plus | |
| `q36fmodel` | Qwen3.6-Flash | |
| `dmodel` | DeepSeek-V4-Pro | |
| `dfmodel` | DeepSeek-V4-Flash | |
| `gm51model` | GLM-5.1 | |
| `kmodel` | Kimi-K2.6 | |
| `mmodel` | MiniMax-M2.7 | |

注意：具体可用模型和额度随 QoderWork 平台策略变化，以 `--list-models` 实际输出为准。

## 5. 关键限制与注意事项

### 5.0 登录与信任目录

CN 版登录检查：

```bash
env -u QODER_AGENT_SDK_ENTRYPOINT \
    -u QODER_AGENT_SDK_VERSION \
    -u QODER_WORK_INTEGRATION_MODE \
    -u QODERWORK_SOURCE_CHAT_ID \
    -u QODERWORK_AWARENESS_SINK \
    -u QODERWORK_AWARENESS_SINK_MEMORY \
    '/Applications/QoderWork CN.app/Contents/Resources/bin/qoderclicn' --list-models
```

未登录时会提示：

```text
Not logged in. Run `qoderclicn login` to authenticate.
```

登录命令：

```bash
env -u QODER_AGENT_SDK_ENTRYPOINT \
    -u QODER_AGENT_SDK_VERSION \
    -u QODER_WORK_INTEGRATION_MODE \
    -u QODERWORK_SOURCE_CHAT_ID \
    -u QODERWORK_AWARENESS_SINK \
    -u QODERWORK_AWARENESS_SINK_MEMORY \
    '/Applications/QoderWork CN.app/Contents/Resources/bin/qoderclicn' login
```

登录会打开 `qoder.com.cn` 的浏览器授权页。授权完成后，CLI 显示 `Login successful`，交互式界面显示 `Signed in Browser Login`。

每个新 worktree 首次启动时，CLI 会询问是否信任目录。PM 只选择 `Trust folder`，不要信任整个 `.claude/worktrees/**` 父目录，避免后续 worker 误读其他 worktree。

### 5.1 SDK 环境变量冲突（重要）

**`qoderclicn` 不能从 QoderWork 桌面端内部 session 启动。** 桌面端运行时会注入以下环境变量：

- `QODER_AGENT_SDK_ENTRYPOINT=sdk-ts`
- `QODER_AGENT_SDK_VERSION=0.1.0`
- `QODER_WORK_INTEGRATION_MODE=1`
- `QODERWORK_SOURCE_CHAT_ID=...`
- 等等

当这些变量存在时，`qoderclicn` 会尝试走 SDK 模式而非 CLI 模式，导致报错：

```
Error: sdk_invalid_args: Agent SDK entrypoint env is set but required flags are missing.
Expected --print --input-format stream-json --output-format stream-json
```

**解决方案**：必须在干净的终端/tmux session 中运行，或显式清除这些环境变量：

```bash
env -u QODER_AGENT_SDK_ENTRYPOINT \
    -u QODER_AGENT_SDK_VERSION \
    -u QODER_WORK_INTEGRATION_MODE \
    -u QODERWORK_SOURCE_CHAT_ID \
    qoderclicn -p "your prompt here"
```

### 5.2 额度共享

CLI 和桌面端共用 `~/.qoderworkcn/` 下的认证和额度池。CLI 消耗的额度会从同一账户扣除，不会独立计费。

### 5.3 MCP 工具链

`qoderclicn` 可通过 `--mcp-config` 加载 MCP 服务器配置，这意味着 worker 可以访问元典法律检索、企查查工商查询等 QoderWork 生态的 MCP 工具。这是相比 Claude Code / Codex worker 的独特优势——法律实务场景下可以直接查法条、查企业信息。

### 5.4 2026-06-21 书稿 worker 实测

在 `writing-reviewer` 书稿评测中，CN 版 `qoderclicn -m qmodel_latest` 已跑通：

- 手动 worktree + `spawn-worker.sh --worker-backend qoderwork-cn`
- 交互式 tmux worker
- Bootstrap prompt 写 `STATUS.json`
- Full prompt 读取书稿上下文、写 review/result/metadata、修改 ch07、提交分支
- sentinel 在 `status="done"` 后关闭 tmux

观察到的行为：

- `qoderclicn -p` 短提示能调用 Qwen3.7-Max，但可能不严格遵循“只回复 OK”这类极短约束；长任务优先使用交互式 tmux，方便 PM 纠偏。
- `qoderclicn` 会显示模型名 `Qwen3.7-Max Model`，可作为模型路由确认。
- worker 可能在提交后再次更新 `metadata.json` 的 `commit_sha` 字段，造成一个未提交尾巴。PM 收口时要检查 `git status --short`，若只剩 metadata 完成态字段，可补一个 `chore(eval): finalize qoder qwen metadata` 收口提交。
- `STATUS.json` 字段可能使用 `status="done"` 但 `phase="completed"`，sentinel 只看 `status` 字面值即可；prompt 仍应强制 terminal status 使用 `done`。

## 6. tmux Worker 启动示例

### 6.1 非交互批处理模式

```bash
# 建议在干净终端中运行（非 QoderWork 内部 session）
tmux new-session -d \
  -s worker-qoderwork \
  -c /path/to/worktree \
  'qoderclicn -m qmodel_latest \
   --permission-mode auto \
   -p "$(cat /tmp/task.prompt.md)"'
```

### 6.2 交互式模式（可人工接管）

```bash
tmux new-session -d \
  -s worker-qoderwork \
  -c /path/to/worktree \
  'env -u QODER_AGENT_SDK_ENTRYPOINT \
       -u QODER_AGENT_SDK_VERSION \
       -u QODER_WORK_INTEGRATION_MODE \
       -u QODERWORK_SOURCE_CHAT_ID \
       -u QODERWORK_AWARENESS_SINK \
       -u QODERWORK_AWARENESS_SINK_MEMORY \
   "/Applications/QoderWork CN.app/Contents/Resources/bin/qoderclicn" \
   -m qmodel_latest \
   --permission-mode auto'
```

> **2026-06-26 复测（writing-reviewer v0.10.7 cross-model eval）**：`qoderclicn -m Qwen3.7-Max` 交互式 tmux worker 已跑通。要点：
> - **路径必须引用**（§6.2 已示范）：`/Applications/QoderWork CN.app/...` 含空格，在 tmux 命令串里若用未加引号的 `$VAR` 展开，会在空格处被 `env` 截断，报 `env: /Applications/QoderWork: No such file or directory` 并秒退、pane 全空（**易误判为"交互式起不来"**）。必须用字面引号路径 `'/Applications/QoderWork CN.app/...'` 或正确转义。
> - **清全部 SDK 变量**（§5.1）：`QODER_AGENT_SDK_ENTRYPOINT` / `_VERSION` / `QODER_WORK_INTEGRATION_MODE` / `QODERWORK_SOURCE_CHAT_ID` / `_AWARENESS_SINK` / `_AWARENESS_SINK_MEMORY` 全清，否则走 SDK 模式报 `sdk_invalid_args`。
> - **eval worker 同样用 snapshot-copy-into-worktree**（DEC-037）：冻结 skill 快照拷进 worktree，worker 用 `./skill-snapshot-v0107` 相对路径读，避免跨目录 / trust 限制 / path 漂移。
> - **最高权限**：`--dangerously-skip-permissions`（worktree 隔离，安全），配合 trust folder（选 "Trust folder"，勿信父目录）。
> - **batch -p 也可用**（`qoderclicn -m Qwen3.7-Max -p "<prompt>"`），但长任务优先交互式（可 PM 纠偏）；batch 仅在交互式真不可作时兜底。

### 6.3 从 QoderWork 内部 session 启动（需清除环境变量）

```bash
tmux new-session -d \
  -s worker-qoderwork \
  -c /path/to/worktree \
  'env -u QODER_AGENT_SDK_ENTRYPOINT \
       -u QODER_AGENT_SDK_VERSION \
       -u QODER_WORK_INTEGRATION_MODE \
       -u QODERWORK_SOURCE_CHAT_ID \
       -u QODERWORK_AWARENESS_SINK \
       -u QODERWORK_AWARENESS_SINK_MEMORY \
   qoderclicn -m qmodel_latest \
   --permission-mode auto \
   -p "$(cat /tmp/task.prompt.md)"'
```

### 6.4 与 spawn-worker.sh 集成

理论上可以作为 `custom CLI` worker 通过 `spawn-worker.sh` 启动：

```bash
bash scripts/spawn-worker.sh \
  --project /path/to/repo \
  --branch feature/legal-research \
  --session qw-legal-research \
  --worker-backend qoderwork-cn \
  --runtime-profile qoder-cn-qwen37max \
  --api-provider qoderwork-cn \
  --model 'qmodel_latest/Qwen3.7-Max' \
  --provider-slot qoder-cn-qwen37max-1 \
  --verify-cmd 'your-verify-command' \
  --command "bash -lc 'exec env -u QODER_AGENT_SDK_ENTRYPOINT -u QODER_AGENT_SDK_VERSION -u QODER_WORK_INTEGRATION_MODE -u QODERWORK_SOURCE_CHAT_ID -u QODERWORK_AWARENESS_SINK -u QODERWORK_AWARENESS_SINK_MEMORY \"/Applications/QoderWork CN.app/Contents/Resources/bin/qoderclicn\" -m qmodel_latest --permission-mode auto -n qw-legal-research'"
```

## 7. 适用场景

| 场景 | 推荐度 | 理由 |
|------|--------|------|
| 法律条文/案例检索任务 | 高 | 可直接利用元典 MCP 工具链 |
| 企业工商/财产调查任务 | 高 | 可直接利用企查查 MCP 工具链 |
| 利用免费额度的低风险任务 | 高 | Qwen3 Max 免费额度适合 i18n/翻译/文档整理 |
| 需要长上下文深度推理 | 中 | 取决于具体模型能力 |
| 代码重构/架构级任务 | 低 | Claude Code / Codex 更成熟 |

## 8. 与现有 Skill 框架的集成建议

- **backend 标识**：建议按区域区分，例如 `qoderwork-cn`；profile 可写 `qoder-cn-qwen37max`
- **spawn 集成**：走 `custom CLI` worker 路径，通过 `spawn-worker.sh --worker-backend custom` 启动
- **checkpoint 兼容**：`qoderclicn` 本身不产生 `STATUS.json`，需要在 worker prompt 中明确要求 worker 自行写入 checkpoint 三件套，或靠 git status + tmux capture-pane 兜底巡检
- **额度监控**：目前没有 CLI 方式查询剩余额度，需要在 QoderWork 桌面端查看
- **worktree 隔离**：虽然 CLI 暴露 `--worktree`，多 Agent 编排仍建议由 PM 先用 `spawn-worker.sh` 创建 worktree，再用 `tmux -c <worktree>` 启动 CLI，保证分支名、Session Context 和 sentinel 路径可控
