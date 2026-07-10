# 并行开发实战经验教训

> 本文档为 SKILL.md 的 Level 2 参考文档，记录实际操作中遇到的问题和解决方案。
> 读取时机：Agent 卡住、合并冲突、中文输入异常、权限被拒时。

---

## Agent Teams 模式

### A1. 文件通信协议（inbox 模式）

Claude Code 官方 Agent Teams 使用用户目录下的团队和任务状态：`~/.claude/teams/{name}/config.json`、`~/.claude/teams/{name}/inboxes/` 和 `~/.claude/tasks/{name}/`。这是官方 team 状态源；不要在项目内新建 `.claude/teams/` 来冒充官方 team。

inbox 通信示例：

| 操作 | 命令 |
|------|------|
| Agent 发 health_report | `jq '. += [{from:"worker-1",text:({...} \| tostring),timestamp:"...",read:false}]' "$PM_INBOX" > /tmp/ib.tmp && mv /tmp/ib.tmp "$PM_INBOX"` |
| PM 发命令 | `jq '. += [{from:"pm",text:({...} \| tostring),timestamp:"...",read:false}]' "$WORKER_INBOX" > /tmp/ib.tmp && mv /tmp/ib.tmp "$WORKER_INBOX"` |
| Agent 间通信 | 同上，from 改为自己的名称，写入目标 agent 的 inbox |
| 检查 inbox | `jq '[.[] \| select(.read == false)]' "$MY_INBOX"` |
| 标记已读 | `jq '(.[] \| select(.read == false)) \| .read = true' "$MY_INBOX" > /tmp/ib.tmp && mv /tmp/ib.tmp "$MY_INBOX"` |

**原子写入**：`jq ... > /tmp/ib.tmp && mv /tmp/ib.tmp target.json` 确保不会出现半写状态。

**过时检测**：如果 health_report 超过 5 分钟未更新，PM 应回退到 `capture-pane` 检查。

**tmux/custom worker**：默认不写 `~/.claude/teams/`，而是把 PM checkpoint 写在当前 worktree 的 `.claude/agent-sessions/{session}/`。只有明确接入 Agent Teams inbox 时，才额外写 health_report。

**回退兼容**：如果 agent 未写 health_report，pm-monitor.sh 自动回退到 `.claude/agent-sessions/{session}/` 和 Git SHA 轮询。

### A2. Teammate 创建失败

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 创建 Teammate 时报错 | 未启用 feature flag | 确认 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` |
| split-panes 无法显示 | 非 tmux/iTerm2 环境 | 切换到 in-process 模式 |
| workdir 路径无效 | 相对路径解析错误 | 使用绝对路径 |

### A2. Teammate 间协作

- 邮箱系统支持双向通信，适合依赖通知和协作场景
- 共享任务列表自动同步状态，无需手动轮询
- Teammate 完成任务后自动标记 completed，Team Lead 据此触发 review

### A3. Teammate Context 管理

- 每个 Teammate 有独立上下文窗口，不受其他 Teammate 影响
- Context 接近满时需要重新创建 Teammate（不支持 session resumption）
- 任务描述应尽量精简，避免浪费上下文空间

---

## tmux worker / 扩展模式

> 以下问题仅在 tmux worker 或 tmux 扩展模式下出现。Agent Teams 模式不涉及 tmux send-keys，因此不存在这些问题。

### T1. tmux send-keys 陷阱

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 多行 prompt 中的括号被 shell 解析 | `send-keys -l` 的文本仍被 shell 处理 | 写入临时文件，用 `$(cat file)` 展开 |
| Enter 键未被 Claude Code TUI 接收 | 多行文本和 Enter 同时发送 | 文本和 Enter 分两次 `send-keys`，中间加 `sleep 0.1` |
| 中文字符显示异常 | 终端编码或 tmux 字符集 | 确保终端和 tmux 都使用 UTF-8 |
| 长命令被截断 | tmux pane 宽度不足 | 确保窗口足够宽，或用 `-l` 标志 |

**正确的 send-keys 模式**：

```bash
# 文本和 Enter 分开发送
tmux send-keys -t session -l -- "$(cat /tmp/prompt.txt)"
sleep 0.1
tmux send-keys -t session Enter
```

### T2. 中文输入法干扰

**问题**：通过 `osascript keystroke` 发送英文文本时，中文输入法会拦截并转换为中文（如 "tmuxattach-他dashboard"）。

**解决方案**：用剪贴板 + Cmd+V 粘贴绕过输入法：

```bash
osascript <<EOF
tell application "System Events"
  tell process "Ghostty"
    set the clipboard to "tmux attach -t worker-1"
    keystroke "v" using command down
    delay 0.2
    keystroke return
  end tell
end tell
EOF
```

`terminal-split.sh` 已内置此方案。如果粘贴仍异常，检查：
1. 是否已授予 Claude Code 辅助功能权限（系统设置 → 隐私与安全性 → 辅助功能）
2. 剪贴板是否被其他应用占用

### T3. 权限预授权

Agent 全自动运行需要预授权。在每个 worktree 的 `.claude/settings.json` 中配置：

```json
{
  "permissions": {
    "allow": [
      "Edit", "Write",
      "Bash(git *)", "Bash(cargo *)", "Bash(npm *)", "Bash(npx *)",
      "Bash(cd *)", "Bash(cat *)", "Bash(ls *)", "Bash(mkdir *)",
      "Bash(grep *)", "Bash(find *)", "Bash(gh *)"
    ]
  }
}
```

没有此配置，Agent 会在每一步停下来等人按 `y`。

### T4. 分支进度差异

实际三路并行数据：

| 分支 | 完成时间 | Context | 特点 |
|------|---------|---------|------|
| 文件操作 | 最快 | 74% | 任务明确，边界清晰 |
| 索引+预览 | 17/18 子任务 | 59% | 任务多但文件所有权清晰 |
| Agent/Skill | 最慢 | 38% | 需理解最多上下文 |

**结论**：任务定义越明确、文件边界越清晰，Agent 执行效率越高。

### T5. Claude Code provider env 隔离

MyAgents 的 Claude Agent SDK 路径给了一个可移植经验：不要把"当前任务使用哪个 provider/model"留给全局配置合并，而要在启动子进程前构造一次有效 runtime snapshot，并把 provider env 显式写进子进程环境。

迁移到 tmux/CLI worker 时采用以下规则：

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 多个 provider/model 要维护多个 settings 文件 | Claude 原生 settings 的 `ANTHROPIC_BASE_URL` / token / model 都是单值 | 用 provider registry 合并多个 provider：每个 provider 有自己的 base URL、key env 和 models |
| settings 指向 GLM，但 banner 显示 MiniMax | 用户级 `~/.claude/settings.json` 或父 shell 的 `ANTHROPIC_MODEL` 仍参与合并 | 用 `render-runtime-profile.sh` 默认生成的 `claude-provider-env.sh` wrapper 命令 |
| settings 有 `ANTHROPIC_AUTH_TOKEN`，Claude 仍回退到旧 keychain/API key | Claude Code 内部可能读取另一套 auth env | wrapper 将 `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_API_KEY` 配对补齐 |
| 用户级 settings 写了 provider env | CLI 默认会读 user/project/local 多层 settings | wrapper 给 `claude` 注入 `--setting-sources project,local`，并设置 `CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST=1` |
| 后续排查不知道 worker 怎么启动 | 命令字符串不可审计 | `spawn-worker.sh --env-isolation "$PROVIDER_ENV_ISOLATION"` 写入 `METADATA.json` |

标准路径：PM 不手写裸 `claude --settings ...`；优先用 `render-runtime-profile.sh --backend claude-code --provider-registry ... --api-provider ... --model ...` 渲染。旧 settings 路径仍可用：`render-runtime-profile.sh --backend claude-code --settings ... --model ...`。两种路径都要把 `WORKER_COMMAND` 和 `PROVIDER_ENV_ISOLATION` 传给 `spawn-worker.sh`。

---

## 通用

### G1. 合并冲突处理模式

多路并行 PR 合并时，后续 PR 必然与已合并的 PR 冲突（共享 CHANGELOG.md 等文件）。

**解决流程**：

1. `git fetch origin && git rebase origin/main`
2. 手动合并每个冲突文件（保留双方修改）
3. `GIT_EDITOR=true git rebase --continue`
4. `git push --force-with-lease`
5. `gh pr merge N --squash`

**冲突文件策略**：

| 冲突文件 | 合并策略 |
|---------|---------|
| CHANGELOG.md | 按版本号合并，同版本条目合在一起 |
| DECISIONS.md | 工作日志按时间倒序，保留双方 |
| schema.rs / migrations | ALTER TABLE 保留双方 |
| lib.rs / main entry | imports 合并，函数按字母/功能分组 |
| api.ts / types.ts | import 合并，类型和函数按功能分组 |

### G2. tmux Session 管理原则

1. **一个 session 一个 Agent** — 不在同一 session 的不同 pane 放多个 Agent
2. **先建 session，再 attach** — 后台创建确认运行，再用终端工具 attach
3. **进程在 tmux 里，不在终端里** — 关闭终端窗口不会杀进程
4. **context 接近 100% 需介入** — Agent Teams 需重建 Teammate，tmux 需 `claude --continue`

### G3. 实施规划原则

Agent 自己发现任务可以并行时，会主动创建分支——比人提前规划更高效。实施计划应只定义**目标和约束**，让 Agent 自主选择执行策略。不要在 prompt 中写死文件路径和具体实现步骤。

### G4. gh pr review 注意事项

- **同一 GitHub 账号不能 approve 自己的 PR** — 用 `gh pr comment` 替代正式 review
- **`--delete-branch` 在 worktree 存在时会失败** — 需先删除 worktree 再合并
- **squash merge 后分支自动删除** — 如果配置了 `--delete-branch`

### G5. Warp 终端特殊处理（tmux 模式）

Warp 分屏后无法通过菜单/键盘可靠切换焦点（Claude Code TUI 捕获键盘事件）。

**解决方案**：用 Swift + CoreGraphics 鼠标点击定位新面板（已内置在 `terminal-split.sh` 的 `click_at` 函数中）。需要 Xcode CLI tools。

### G6. PM 主控角色不要绑定产品

实际协作中，PM 可能是 Codex，也可能是 Claude Code，取决于用户当前在哪个主会话里发起任务。不要在 prompt、分支名或 worktree 名里假设“Codex 一定是 PM”或“Claude 一定是 worker”。

推荐写法：

```text
PM Host: Claude Code
Worker Backend: Codex
Runtime Profile: codex-l1
```

或：

```text
PM Host: Codex
Worker Backend: Claude Code
Runtime Profile: claude-provider / claude-oauth
```

这样可以把角色、额度来源和具体 CLI 解耦。PM 只负责验收和收口；worker 只负责限定范围内的执行。主控切换后，分支命名、worktree 隔离、checkpoint、health_report 和 Git 收口规则都保持不变。

### G7. ACP 与 tmux 的稳定性边界

ACP 的协议层更干净，能提供结构化 session 事件；但实际稳定性取决于 adapter。没有成熟 adapter 时，`tmux + worktree + checkpoint 文件 + git 状态` 更适合作为默认执行层，因为它可观察、可人工接管，也不依赖特定 Agent 产品支持协议。

稳定性排序按实际落地判断：

| 场景 | 推荐 |
|------|------|
| 现在就要跑 Claude/Codex worker | tmux + worktree |
| 需要结构化状态且已有 adapter | ACP adapter |
| worker TUI 输出变化频繁 | 依赖 checkpoint 文件和 git 状态，不依赖屏幕文本 |
| 需要人工临时接管 | tmux session |

### G8. OpenCode 普通 worker 与 ACP server 分开使用

OpenCode 同时提供 `opencode run` 和 `opencode acp`。默认把 OpenCode 当普通 CLI worker 使用：

```bash
opencode run --format json --model <provider/model> "$(cat /tmp/task.prompt.md)"
```

只有当 PM 侧已经有 ACP client/adapter，并且能把 ACP session 事件映射到 health report 或 PM 巡检面板时，才启动：

```bash
opencode acp
```

不要因为 OpenCode 支持 ACP 就默认切到 ACP。对本 Skill 来说，稳定落地顺序仍是：worktree 隔离、普通 CLI worker、checkpoint 文件、Git 状态巡检；ACP 是后续结构化通信层。

### G9. Claude provider settings 管理

Claude Code worker 默认按第三方 API provider settings 启动。每个 provider 建议一个本地 settings 文件：

```text
config/<provider-a>.settings.json
config/<provider-b>.settings.json
config/<provider-c>.settings.json
...（每个 provider 一个本地 settings 文件，按你实际可用的 provider 命名；真实文件 gitignore 不入库）
```

settings 内容参考 `config/claude-provider-settings.example.json`。真实 token 文件必须放在本地忽略路径，不提交到仓库。

使用规则：

1. 第三方 API：用 `claude --settings /path/to/provider.settings.json --model <provider-model> ...`，整份 settings 同时配置 token、base URL、`ANTHROPIC_MODEL`、默认模型映射、timeout 和 thinking tokens。
2. 订阅/OAuth：才用 `env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_BASE_URL claude ...`。
3. 不要在 provider profile 上套 `env -u ANTHROPIC_AUTH_TOKEN` 或 `env -u ANTHROPIC_BASE_URL`，否则会把第三方 API 配置清掉。
4. provider profile 下不要指定 `--model sonnet` 这类 Anthropic 原生别名；要指定 provider 的真实模型名，例如 `<provider-model>[1M]`（按你的 provider 实际模型名 + 上下文窗口后缀）。
5. 只传 `--settings` 不足以隔离用户级 `~/.claude/settings.json`。若用户级 settings 中有 `ANTHROPIC_MODEL`，它可能覆盖默认模型选择；PM 必须检查启动 banner 与 `STATUS.json` 中的 model/provider 一致。
6. 一个 worker prompt 里写清 `Runtime Profile` 和 settings 文件路径，但不要写 token 值。

排障规则：
- banner 显示的模型不是目标模型：立即停止 worker，补 `--model` 或修 provider settings 的 `ANTHROPIC_MODEL`。
- 最小请求返回 `401/403`：优先查 token / base URL。
- 最小请求返回 `429/529` 且错误来源是目标 provider 网关：这通常是限流 / 拥塞，不是用户级 settings 覆盖。
- 最小请求能跑通但长任务卡启动：禁用无关 MCP（`--strict-mcp-config --mcp-config '{"mcpServers":{}}'`）再测。

### G10. 一行命令 Agent 的接入条件

其他 Agent 也可以作为 custom CLI worker。不要先为每个产品写专门流程；先用统一模板验证：

```bash
tmux new-session -d \
  -s worker-custom \
  -c .claude/worktrees/tmux-feature \
  '<agent-command> < /tmp/task.prompt.md'
```

接入前检查四点：

1. 能否在指定 worktree cwd 中运行。
2. 能否通过 stdin、参数或 prompt 文件接收完整任务。
3. 能否指定模型、provider 或 profile。
4. 能否写 `.claude/agent-sessions/{session}/STATUS.json`、`RESULT.md`、`PATCH_SUMMARY.md`，或至少让 PM 通过 Git 状态和 tmux pane 判断进度。

满足这四点就可以先作为 `custom-cli` profile 使用；跑稳定后，再决定是否晋升为正式 backend 模板。

### G11. Checkpoint 优先，日志兜底

PM 的目标是节省主会话上下文，不是频繁读取 worker 全量日志。worker 必须写：

```text
.claude/agent-sessions/{session}/STATUS.json
.claude/agent-sessions/{session}/RESULT.md
.claude/agent-sessions/{session}/PATCH_SUMMARY.md
```

PM 巡检优先读 checkpoint 和 `git diff --stat`。只有以下情况才读取完整日志或 tmux pane：

1. `STATUS.json` 超过 15 分钟未更新。
2. `STATUS.json` 报告 `blocked`、`failed` 或 `needs_input=true`。
3. `RESULT.md` 与实际 diff 明显不一致。
4. worker 长时间无文件落盘或反复规划。

`pm-monitor.sh` 会根据 branch 自动查找 worktree，并监听上述 checkpoint 文件变化，输出 `CHECKPOINT_STATUS`、`CHECKPOINT_RESULT` 和 `CHECKPOINT_PATCH` 事件。

### G12. Claude 官方 agent view 与 tmux 的分工

Claude Code 官方 agent view 适合 Claude Code 自己管理后台会话；tmux 适合统一管理 Claude、Codex、OpenCode 和 custom CLI worker。两者不冲突：

| 场景 | 推荐 |
|------|------|
| 只调度 Claude Code worker | `claude agents` / `claude --worktree --tmux` / 版本支持时 `claude --bg` 或 `/bg` |
| 混合 Claude、Codex、OpenCode | tmux + worktree |
| 需要统一脚本监控 checkpoint/Git/PR | tmux + `pm-monitor.sh` |
| 需要 Claude 官方 peek/reply/attach | agent view |

如果当前安装版本没有 `--bg`，不要硬写后台参数；用 `claude agents --help` 和 `claude --help` 检查后再决定。本机 Claude Code 2.1.149 已确认 `claude agents --json`、`--worktree` 和 `--tmux` 可用，tmux 仍是跨产品稳定 fallback。

### G13. 偏题先纠偏，不要直接接管

PM 发现 worker 越界时，默认动作不是停止 session 后亲自实现，而是先发明确纠偏指令，让 worker 自己回到任务范围。直接接管会抵消并行 session 的价值，只适合破坏性风险或连续纠偏失败。

推荐纠偏格式：

```text
PM correction:
1. Stop: 停止依赖/runtime/package/config 方向的修改。
2. Return: 回到 docs/TASKS.md ISS-017 的 OCR 质量报告范围。
3. Boundaries: 不修改 package-lock、node_modules、环境配置、无关文档。
4. Next action: 只补质量报告契约/服务/测试，更新 .claude/agent-sessions/faropdf-ocr-quality/STATUS.json 后继续。
```

tmux 发送时用 `send-keys -l` 和单独 Enter：

```bash
tmux send-keys -t faropdf-ocr-quality -l -- "$(cat /tmp/pm-correction.txt)"
sleep 0.1
tmux send-keys -t faropdf-ocr-quality Enter
```

只有以下情况才停止并接管：

1. 连续两次纠偏后仍继续越界。
2. worker 准备执行破坏性 Git 或文件操作。
3. worker 已触碰敏感信息、密钥或禁止文件。
4. 原 session 因环境、权限或上下文问题无法继续完成限定任务。

### G14. 用户指定 PM 时，PM 不默认亲自编码

多 Agent 编排的主要目的之一是 token efficiency：把实现工作交给更合适的模型、额度来源和独立上下文，保留最高智能会话做任务分解、风险判断、纠偏、review 和收口。如果 PM 频繁亲自写代码，就会同时消耗主会话 token 和破坏多线程协作试验。

当用户说“你做 PM agent / 你来编排 / 用多分支多 worktree 推进”时，默认策略是：

1. PM 读任务源、做分组和依赖判断。
2. PM 创建 worktree、分支、session context 和 session，或派发 Subagent。
3. Worker 写代码、跑测试、更新 checkpoint、提交和开 PR。
4. PM 只读 checkpoint、diff stat、测试结果和 PR diff。
5. PM 发现问题先发纠偏或派 reviewer，不默认自己改业务代码。

PM 直接改代码只适合四种例外：

1. 用户明确要求当前 PM 直接做。
2. 任务极小，启动 worker 的成本高于实现成本。
3. worker 连续纠偏失败，剩余工作很窄且继续派发会浪费更多 token。
4. 修改对象是 orchestration prompt、Skill 文档、checkpoint 模板等 PM 自己负责的协作层。

最终汇报中如果 PM 直接改了业务代码，应说明触发了哪个例外；否则用户会难以判断多 Agent 编排是否真的节省了 token。

### G15. FaroPDF ISS-018：Claude worker 实战修正

本次用 Codex PM 调 Claude Code tmux worker 推进 `ISS-018 证据图片 A4 编排`，流程总体可用：worker 完成实现、验证、提交、推送和 PR，PM 只做巡检、纠偏和 code review。但暴露了几个需要固化的约束。

实战问题：

1. worker 首次启动后先读材料和长思考，没有先写 `STATUS.json`。
2. PM correction 后 worker 曾停在“等下一步指令”，没有按 Finish 清单持续推进。
3. `STATUS.json` 的 `phase` 有更新，但 `updated_at` 和 `phase_history` 时间戳没有刷新。
4. worker 一度把本地 checkpoint 目录提交进 PR，后续通过 PM review correction 追加 commit 移除。
5. high-effort provider 对窄范围实现过慢，主会话等待成本上升。

流程修正：

- 对高延迟 provider 使用两段式启动：先发 bootstrap-only，让 worker 写 `.claude/agent-sessions/{session}/STATUS.json`；PM 确认后再发完整任务 prompt。
- Worker prompt 必须写明 `Autonomy`：除非 blocked / needs_input，否则不要等待 PM，持续推进到验证、提交和 PR。
- `.claude/agent-sessions/{session}/` 是本地 checkpoint，不进入 Git；PM review 必查 PR diff 是否包含 checkpoint 目录。
- STATUS 每次写入都必须刷新 `updated_at`；阶段变化必须更新 `phase` 和 `phase_history`。
- 窄范围实现默认 low/medium effort；high/xhigh 留给架构设计、复杂调试或用户明确指定的任务。
- PM code review 发现问题时，先通过 tmux 发送具体 correction；本次成功让 worker 修复输出路径、过大 margin 和 `sort=time` warning，而不是 PM 自己改业务代码。

推荐 bootstrap-only 第一条消息：

```text
Create .claude/agent-sessions/{session}/STATUS.json only. Include status=running, phase=bootstrap, branch, worktree, session_id, session_context, runtime_profile, allowed_files, forbidden_files, node/npm versions, updated_at. Do not read task files or implement yet. Reply when STATUS is written.
```

### G16. STATUS v2 与 PM monitor 的经济性边界

不要把 `STATUS.json` 扩成完整日志。它只应该回答 PM 的五个问题：

1. worker 还活着吗。
2. 现在在做什么，下一步是什么。
3. 有没有越界、阻塞或需要 PM 输入。
4. 测试和 PR 是否到了可 review 状态。
5. 当前环境是否和 PM 假设不一致。

详细实现过程、解释和风险放 `RESULT.md` / `PATCH_SUMMARY.md`，不要塞进 JSON。`STATUS.json` v2 新增字段是为了让 `pm-monitor.sh` 输出事件，而不是让 PM 每次读取更大的文件。

经济型巡检优先级：

| 场景 | 推荐 |
|------|------|
| 用户问进度、PM 准备介入 | `pm-monitor.sh --once` |
| worker 长任务持续运行 | `pm-monitor.sh --interval 60 --log-file ...` 放后台 |
| PM 只需知道是否异常 | 只读 log tail 中的 `AGENT_NEEDS_INPUT`、`CHECKPOINT_STALE`、`CHECKPOINT_TEST_FAILURE` |
| 需要完整验收 | 再读 `RESULT.md`、`PATCH_SUMMARY.md` 和 PR diff |

脚本本身不能保证唤醒 PM；是否自动唤起取决于宿主有没有 automation、monitor、webhook 或外部通知能力。没有这些能力时，也不要让 PM 前台盯屏；用 `--once` 或低频读取事件日志即可。

### G17. 任务编号从 ISS-NNN 改为 Task-NNN

project-init v1.1.1（2026-06-03）起，生成的 `docs/TASKS.md` 模板里任务编号从 `ISS-NNN` 改为 `Task-NNN`。

**原因：** 一个 Issue 或 PR 经常对应多个 Task 改动（拆分提交、范围扩展、阶段切片等），`ISS` 前缀会暗示 1:1 映射造成歧义。

**适用范围：**
- 新生成的项目：直接用 `Task-001`、`Task-002` …… 递增。
- 既有项目：可一次性把当前 `TASKS.md` 里的旧编号重命名为 `Task-NNN`，并相应更新 `DECISIONS.md`、commit、PR 描述里的引用。
- 历史 lesson（如本文件 G15 的 `FaroPDF ISS-018`）：保持原样不改写，那是事件记录。commit history 也不动。

`ISS-` 前缀仅作为过去事件的检索关键词存在，不再作为新任务的命名约定。

### G18. Wave worker 类型影响验收底线

Wave 内 worker 不只是“第几个 worker”，还应标注任务类型和风险：

| 类型 | 风险 | 验收底线 |
|------|------|----------|
| `ui-wiring` | 低 | typecheck、测试、build 全绿；不引入新依赖 |
| `contract-extension` | 中 | 允许共享契约或依赖变更，但必须说明影响面和锁文件变更 |
| `tauri-command` | 高 | Rust/Tauri 语法底线是 `cargo check --manifest-path src-tauri/Cargo.toml --offline` |
| `docs/research` | 低到中 | 注意 DEC/TASK 编号 race，不抢业务文件 |

真实处理类 worker 可能依赖本机库。例如 OpenCV / PyMuPDF / OCR 这类 Rust/Tauri command，`cargo build` 可能要求先安装系统库；若 `cargo check --offline` 干净，而 `cargo build` 只因本机库缺失失败，应把缺失依赖写入 RESULT，不把它当成实现失败。

### G19. Vitest 1.x 与 Vite 二进制资源兼容

Vitest 1.x 在部分 Vite 7.x 项目中不会像生产 `vite build` 一样解析 `?arraybuffer` 二进制资源，测试环境可能拿到空 ArrayBuffer。worker 处理字体、图片、音频等资源时，loader 可加测试 fallback：

```ts
if (import.meta.env.MODE === "test" || bytes.byteLength < 1_000_000) {
  // use readFileSync or another explicit test fixture fallback
}
```

阈值不是业务规则，只是用来识别测试环境空 mock。生产路径仍以 Vite build 结果为准。

### G20. Wave 内 DEC 编号 race

多 worker 同时写 `docs/DECISIONS.md` 时，容易都选到同一个 DEC 编号。worker prompt 应要求：

1. 写入前 grep 当前最大编号，例如 `rg '^## DEC-|^### \\[DEC-' docs/DECISIONS.md`。
2. 选择当时未使用的下一个编号。
3. rebase 或合并时若发现编号冲突，只改自己的编号，不覆盖其他 worker 的记录。

PM 合并 Wave PR 时，把 DEC 编号 race 视为常规冲突处理，不让 worker 因编号冲突直接改掉别人的日志。

### G21. Provider 并发池也是 Wave 计划的一部分

3-4 个 worker 通常已经接近单一 API provider 的稳定并发上限。超过这个数量时，PM 应把 worker 分散到多个 runtime profile：不同 Claude provider、Codex/OpenAI、OpenCode provider、local/OSS profile 等。

这不只是扩容策略，也是一种模型评测。Wave summary 应记录每个 provider/model 的指令遵循、STATUS 心跳、commit 节奏、范围控制、验证通过率、review 修复次数和失败模式。下一 Wave 根据这个记录调度：高风险任务给表现稳定的 profile，低风险重复任务给便宜或吞吐高的 profile。

### G22. 多维度任务的颗粒度纪律（checklist + wave 复查 + 单维度深查）

**场景**：一个 worker 在同一个 prompt 里要改多个章节 × 多个维度（例如同一段时间要改 Critical 修复 + Important 调整 + 末位维度如"标题删重"）。实测中 worker 的注意力会被高优维度（Critical / Important）占满，**末位维度被静默漏掉**——同一份 prompt，前一个 wave 漏了、后一个 wave 才补全。主因不是模型能力不足，而是**任务粒度 + prompt 结构**。

**三条改进（落地到 prompt 与 wave 设计）**：

1. **多维度任务用 checklist prompt 强制逐维度**：prompt 里把所有维度拆成显式 checklist，每个维度对应独立 commit / 勾选项；worker 必须覆盖完所有维度才算完成（在 RESULT / STATUS 里逐项打勾）。不要把维度淹没在散文式任务描述里——末位维度会被忽略。

2. **大批量改后必跑 wave2 复查抓漏**：wave1 做完多维度批量修改后，PM 不要直接收口；至少派一个独立的 wave2 复查 worker（只读 review，不改稿），按维度清单逐项核对覆盖情况。wave2 抓漏比指望 wave1 worker 自检更可靠——因为 wave2 上下文更窄、注意力更聚焦。

3. **精细深查拆单维度 worker**：箭头落点 / 字体逐核 / 像素级对齐这种需要逐项深查的工作，不要塞进多维度 worker 里；拆成**单维度 worker**（只做一件事），注意力不被其他维度稀释。多维度 worker 处理广度，单维度 worker 处理深度。

**反模式**：把 5 个维度的检查 + 修复全塞进一个 worker 的 prompt，指望它一次跑完——末位维度会漏。这不是 PM 派得不够清楚，是任务结构本身让 worker 没有足够注意力余量。

**与 §3.1 Wave 模式的关系**：这本质是"一个 wave 内的任务颗粒度设计"，不是开新 wave。wave2 复查 worker 可以是同 base ref 下的轻量读 review，也可以是 `writing-reviewer` 这类只读审稿 worker。原则适用于任意多维度批量任务，不限书籍 / 文档类项目。

### G23. 派生 spawn 阶段并行投递纪律（spawn 阶段就并行，不要先串行后并行）

**场景**：Wave 启动时 PM 误把"spawn 阶段串行、worker 阶段并行"当作稳妥选项——先派 W1、`await` 等 W1 `STATUS.json` 出现，才派 W2，再派 W3。多花一轮时间，价值零（与单 worker 跑三次无异）。

**实战来源**：2026-07-10 某客户委托项目多 worker Wave 实战（3 个不同 skill backend 的 worker，全 claude-code backend，反馈「着实影响并行推进任务」）。PM 一开始串行 spawn W1→W2→W3 浪费一轮；Wave 后半段并行 spawn 才补回节奏。详见 `SKILL.md §3.8.2`、TASKS L118、DEC-112。

**两条改进**：

1. **spawn 阶段就并行投递**：文件域不重叠 + 验证命令独立 + 无共享契约冲突的 worker，**从一开始**就并行 spawn（每个 worker 走 `bg spawn-worker.sh` + `bg sentinel.sh` 各一次 fg Bash 调用），不先串行验证流程再补并行。spawn 阶段就并行与 `§3.1` 已有的"Wave 内 4-6 worker 并行"硬数字配套。
2. **spawn 后不 await、不 block、不 attach**：spawn-worker.sh 退出后立即跑 `SKILL.md §3.8.1` 的 4 条核验命令（`tmux has-session` / `capture-pane` / `METADATA.json` / `STATUS.json` with `timeout 120`），不超过 30 秒/worker，立即返回 PM 主循环。后续 worker 终态由 sentinel（§7.2）+ cron（§7.3）事件驱动接管。

**反模式**：

- `TaskOutput block=true` 等 `spawn-worker.sh` 退出 → PM 主回合 hang → 并行价值归零（某多 worker Wave 实测 ~90s/次 × 3 worker）
- `tmux attach -t "$SESSION"` 跟 worker 一起看 → 占 PM 主会话、无纠偏能力
- `while ! [ -f STATUS.json ]; do sleep 1; done` 不带 timeout → PM 可能永久挂
- 先串行 spawn W1，等 `STATUS.json` 才派 W2、W3 → Wave 串行化，多花一轮
- spawn 完 6 worker 立刻 poll 等全部 done → 把 Wave 设计目的废弃

**与 §3.1 Wave 模式 + G22 的关系**：G22 是 wave **内**任务颗粒度（多维度 worker attention 分散 → checklist + wave2 复查 + 拆单维度），本 G23 是 wave **前**spawn 投递纪律（一开始就并行 vs 串行验证 + spawn 后不 await）。两者是 Wave 调度的两层闭环：

- G23 = spawn 阶段并行投递（Wave **前**）
- G22 = wave 内任务颗粒度 + wave2 复查抓漏（Wave **内** + Wave **后**）

原则适用于任意多 worker Wave，不限书籍 / 文档 / 代码项目。
