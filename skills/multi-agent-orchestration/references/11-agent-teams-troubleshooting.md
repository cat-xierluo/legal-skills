# Agent Teams Troubleshooting

> 读取时机：Claude Code Agent Teams / agent view / `--worktree --tmux` 后端启动、巡检或收口异常时。

## 1. 快速分流

先判断问题在哪一层：

| 现象 | 优先检查 | 处理 |
| --- | --- | --- |
| 看不到 agent / teammate | `claude agents --json`、Claude Code 版本、feature 支持 | 确认当前 Claude Code 支持 agent view / teams；不支持时降级为 `tmux + worktree` |
| agent 在错误目录工作 | agent cwd、worktree 路径、`git branch --show-current` | 立刻停止实现，写 blocked STATUS，重启到正确 worktree |
| 官方 worktree 存在但 PM 找不到状态 | 官方 worktree 路径、`.claude/agent-sessions/<session>` 是否存在 | PM 补写或映射 `METADATA.json`，再发送 bootstrap-only prompt 让 worker 写 `STATUS.json` |
| inbox / tasks 没有更新 | `~/.claude/teams/<team>/`、`~/.claude/tasks/<team>/`、权限 | 不在项目内自造 `.claude/teams/`；必要时只读官方状态源并用 Session Context 兜底 |
| worker 长时间无心跳 | `STATUS.json.updated_at`、tmux/agent pane、git commit 数、文件 mtime | 先发 checkpoint-only 纠偏；5 分钟无变化再重启或降级 |
| PR 已开但 PM 继续等待 | PR mergeable、base drift、`STATUS.json.git.pr_url` | 进入收口流程；不要把“PR 已开”当作 worker 仍在执行 |

## 2. 官方状态源与本 Skill 状态源

Claude 官方 Agent Teams / agent view 可能有自己的状态源：

- `claude agents --json`
- `~/.claude/teams/<team-name>/`
- `~/.claude/tasks/<team-name>/`
- Claude 官方 `--worktree` 创建的 worktree

本 Skill 的 PM 状态源仍是目标 worktree 内：

- `.claude/agent-sessions/<session-id>/METADATA.json`
- `.claude/agent-sessions/<session-id>/STATUS.json`
- `.claude/agent-sessions/<session-id>/RESULT.md`
- `.claude/agent-sessions/<session-id>/PATCH_SUMMARY.md`

不要在项目里创建 `.claude/teams/` 冒充官方 team。官方状态源用于发现和观察；Session Context 用于 PM checkpoint、Wave、provider slot 和收口。

## 3. `--worktree --tmux` 兼容规则

Claude Code 原生 `--worktree --tmux` 与本 Skill 的 `tmux + worktree` 隔离模型兼容。PM 可以把它作为 Claude worker backend，但必须补齐三件事：

1. 验证官方 worktree 路径、branch 和 session cwd。
2. 在该 worktree 的 `.claude/agent-sessions/<session-id>/` 写入或补写 `METADATA.json`。
3. 给 worker 发送 bootstrap-only prompt，让它写 `STATUS.json`，之后再发送完整任务 prompt。

如果 PM 不能稳定读取官方 agent 状态，降级为本 Skill 的 `scripts/spawn-worker.sh`。

## 4. 常见纠偏 Prompt

checkpoint 缺失：

```text
PM correction: stop implementation now. First create/update .claude/agent-sessions/<session-id>/STATUS.json with cwd, branch, worktree, runtime profile, provider/model, current_action and next_action. Do not continue implementation until the checkpoint is written.
```

错误目录：

```text
PM correction: you are in the wrong cwd or branch. Set STATUS.json status=blocked with the mismatch details and stop. Do not modify files in this workspace.
```

范围扩大：

```text
PM correction: stop all unrelated changes. Return to <task-id>. Allowed files remain <allowed-files>. Forbidden files remain <forbidden-files>. Next action: commit or revert only within allowed scope, then rerun <verification>.
```

PR 收口：

```text
PM correction: PR is open. Update STATUS.json status=done, fill git.pr_url, write RESULT.md and PATCH_SUMMARY.md, then stop. Do not start another task.
```

## 5. 停止而不是继续纠偏的情况

- agent 继续在错误目录或错误分支实现。
- agent 尝试 reset、checkout、删除未授权文件或改 forbidden files。
- agent 泄露 token、settings、完整环境变量或敏感材料。
- 两次纠偏后仍无 `STATUS.json`、无 commit、无文件进展。
- PR/base/CI 状态不明，继续下一 Wave 会扩大冲突。
