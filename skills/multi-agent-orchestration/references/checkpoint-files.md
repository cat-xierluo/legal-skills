# Worker Checkpoint Files

> 读取时机：启动 worker、写 worker prompt、PM 巡检或收口时。

Worker 必须把进度压缩到 `.claude/agent-sessions/<session-id>/`，避免 PM 为了巡检频繁读取完整日志。这里的 checkpoint 是 PM 巡检文件协议，不等同于 Claude Code 自身用于回退会话的 checkpointing 功能。

新 worker 不再创建 `.agent-context/`。旧 worker 或历史 PR 已经写入 `.agent-context/` 时，PM 可以兼容读取，但后续纠偏应要求迁移到 `.claude/agent-sessions/<session-id>/`。

## 1. 文件清单

| 文件 | 写入时机 | PM 用途 |
|------|----------|---------|
| `.claude/agent-sessions/<session-id>/STATUS.json` | 启动后立即创建，每 10-15 分钟或阶段变化时更新 | 判断运行状态、阻塞、测试进度、最近提交 |
| `.claude/agent-sessions/<session-id>/RESULT.md` | 完成、失败或主动停止时写入 | 快速了解结果、验证、风险和下一步 |
| `.claude/agent-sessions/<session-id>/PATCH_SUMMARY.md` | 有代码或文件 diff 时写入 | 不读完整日志也能理解改动范围和意图 |

旧 worker 可继续写 `.agent-context/health.json` 和 `handoff.md`；PM 监控脚本兼容读取旧目录，但新 worker 必须使用上述三件套。

## 2. STATUS.json

```json
{
  "status": "running",
  "phase": "implementing",
  "progress": "2/5",
  "updated_at": "2026-06-02T12:00:00Z",
  "branch": "feat/example",
  "worktree": ".claude/worktrees/tmux-example",
  "session_id": "tmux-example",
  "session_context": ".claude/agent-sessions/tmux-example",
  "runtime_profile": "claude-provider",
  "last_commit_sha": "",
  "files_touched": [
    "src/example.ts"
  ],
  "tests": [
    {
      "command": "npm test",
      "status": "pending",
      "summary": ""
    }
  ],
  "needs_input": false,
  "issues": []
}
```

`status` 取值：

| 值 | 含义 |
|----|------|
| `running` | 正在执行 |
| `blocked` | 需要 PM 或用户输入 |
| `done` | 完成，已写 RESULT/PATCH_SUMMARY |
| `failed` | 失败，RESULT 中说明原因 |
| `stopped` | PM 或用户要求停止 |

## 3. RESULT.md

```markdown
# Result

## Status
done

## Summary
- 完成了什么。
- 没有完成什么。

## Validation
- `npm test`: passed
- `npm run typecheck`: passed

## Files Changed
- `src/example.ts`: 改动目的。

## Risks
- 剩余风险或未覆盖测试。

## Next Steps
- 后续建议。
```

## 4. PATCH_SUMMARY.md

```markdown
# Patch Summary

## Intent
这次 diff 要解决的问题。

## Scope
- 允许范围内的文件。
- 没有触碰的共享文件。

## Behavioral Changes
- 用户可见或系统行为变化。

## Tests
- 已运行测试。
- 未运行测试及原因。

## Review Notes
- PM review 时应重点看的地方。
```

## 5. PM 读取规则

PM 巡检优先顺序：

1. `STATUS.json`
2. `RESULT.md`
3. `PATCH_SUMMARY.md`
4. `git status --short` 和 `git diff --stat`
5. tmux pane、agent view logs 或完整 stream-json 日志

只有 checkpoint 缺失、过期、互相矛盾或报告阻塞时，才读取完整日志。
