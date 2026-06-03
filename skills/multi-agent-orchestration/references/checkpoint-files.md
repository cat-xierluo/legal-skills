# Worker Checkpoint Files

> 读取时机：启动 worker、写 worker prompt、PM 巡检或收口时。

Worker 必须把进度压缩到 `.claude/agent-sessions/<session-id>/`，避免 PM 为了巡检频繁读取完整日志。这里的 checkpoint 是 PM 巡检文件协议，不等同于 Claude Code 自身用于回退会话的 checkpointing 功能。

## 1. 文件清单

| 文件 | 写入时机 | PM 用途 |
|------|----------|---------|
| `.claude/agent-sessions/<session-id>/STATUS.json` | 启动后立即创建，每 10-15 分钟或阶段变化时更新 | 判断运行状态、阻塞、测试进度、最近提交 |
| `.claude/agent-sessions/<session-id>/RESULT.md` | 完成、失败或主动停止时写入 | 快速了解结果、验证、风险和下一步 |
| `.claude/agent-sessions/<session-id>/PATCH_SUMMARY.md` | 有代码或文件 diff 时写入 | 不读完整日志也能理解改动范围和意图 |

## 2. STATUS.json

复制 `templates/checkpoint-status.json` 到 `Session Context/STATUS.json` 后替换占位符。该 JSON 模板必须保持可被 `jq` 解析；不要在 JSON 文件内写注释。

`status` 取值：

| 值 | 含义 |
|----|------|
| `running` | 正在执行 |
| `blocked` | 需要 PM 或用户输入 |
| `done` | 完成，已写 RESULT/PATCH_SUMMARY |
| `failed` | 失败，RESULT 中说明原因 |
| `stopped` | PM 或用户要求停止 |

字段经济性规则：

| 字段组 | 必要性 | PM 自动监控 |
|--------|--------|-------------|
| `status`、`phase`、`progress`、`updated_at`、`heartbeat_interval_seconds` | 判断 worker 是否健康、是否过期 | 是 |
| `task_source`、`branch`、`worktree`、`session_id`、`session_context` | 把事件映射回任务、分支和 worktree | 是 |
| `current_action`、`next_action` | 避免 PM 读取完整日志也能判断是否偏题 | 是 |
| `needs_input`、`pm_action_required`、`blocker`、`issues` | 触发 PM 介入 | 是 |
| `tests`、`git.pr_url`、`git.last_commit_sha` | 判断是否进入 review/收口 | 是 |
| `runtime`、`scope`、`files_touched`、`risks`、`last_pm_correction` | PM 手动 review 时快速定位风险 | 部分 |

不要把完整日志、长推理、完整环境变量或 token 写入 `STATUS.json`。`runtime` 只记录工具路径、版本和 profile 名，不记录密钥、认证头、完整 settings JSON 或完整 shell env。

## 3. RESULT.md

复制 `templates/checkpoint-result.md`，在完成、失败或主动停止时写入 `Session Context/RESULT.md`。RESULT 负责给 PM 快速理解结果，不要重复完整日志。

## 4. PATCH_SUMMARY.md

复制 `templates/checkpoint-patch-summary.md`，在有代码或文件 diff 时写入 `Session Context/PATCH_SUMMARY.md`。PATCH_SUMMARY 负责说明 diff 意图、范围、行为变化、测试和 review 重点。

## 5. PM 读取规则

PM 巡检优先顺序：

1. `STATUS.json`
2. `RESULT.md`
3. `PATCH_SUMMARY.md`
4. `git status --short` 和 `git diff --stat`
5. tmux pane、agent view logs 或完整 stream-json 日志

只有 checkpoint 缺失、过期、互相矛盾或报告阻塞时，才读取完整日志。
