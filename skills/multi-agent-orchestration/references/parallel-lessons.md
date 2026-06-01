# 并行开发实战经验教训

> 本文档为 SKILL.md 的 Level 2 参考文档，记录实际操作中遇到的问题和解决方案。
> 读取时机：Agent 卡住、合并冲突、中文输入异常、权限被拒时。

---

## Agent Teams 模式

### A1. 文件通信协议（inbox 模式）

两种模式（Agent Teams / tmux 扩展）统一使用 `~/.claude/teams/{name}/inboxes/` 邮箱通信：

| 操作 | 命令 |
|------|------|
| Agent 发 health_report | `jq '. += [{from:"worker-1",text:({...} \| tostring),timestamp:"...",read:false}]' "$PM_INBOX" > /tmp/ib.tmp && mv /tmp/ib.tmp "$PM_INBOX"` |
| PM 发命令 | `jq '. += [{from:"pm",text:({...} \| tostring),timestamp:"...",read:false}]' "$WORKER_INBOX" > /tmp/ib.tmp && mv /tmp/ib.tmp "$WORKER_INBOX"` |
| Agent 间通信 | 同上，from 改为自己的名称，写入目标 agent 的 inbox |
| 检查 inbox | `jq '[.[] \| select(.read == false)]' "$MY_INBOX"` |
| 标记已读 | `jq '(.[] \| select(.read == false)) \| .read = true' "$MY_INBOX" > /tmp/ib.tmp && mv /tmp/ib.tmp "$MY_INBOX"` |

**原子写入**：`jq ... > /tmp/ib.tmp && mv /tmp/ib.tmp target.json` 确保不会出现半写状态。

**过时检测**：如果 health_report 超过 5 分钟未更新，PM 应回退到 `capture-pane` 检查。

**回退兼容**：如果 agent 未写 health_report（旧 agent / 非 Claude Code CLI），pm-monitor.sh 自动回退到纯 git SHA 轮询。

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

## tmux 降级模式

> 以下问题仅在 tmux 降级模式下出现。Agent Teams 模式不涉及 tmux send-keys，因此不存在这些问题。

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

---

## 通用（两种模式共有）

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
