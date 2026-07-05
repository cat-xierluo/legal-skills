# scope-guard fix — 实测报告

## 测试环境
- CLI: codebuddy v2.103.3 (WorkBuddy 桌面端)
- 模型: deepseek-v4-flash
- 权限模式: bypassPermissions (-y)
- SCOPE_GUARD_ALLOW: "scope-test/**"

## 测试结果

### 1. PreToolUse hook unbypassable 验证
**结论: codebuddy 的 PreToolUse hook 在 -y/bypassPermissions 下是 unbypassable 的。**

- 退出码 0 + JSON `{"hookSpecificOutput":{"permissionDecision":"deny",...}}` → **成功硬拦**
- 越界文件 `outside/outer.txt` 被 hook deny，文件内容未被修改
- 白名单内文件 `scope-test/inner.txt` 正常写入
- Read 工具不受影响（只检查 Edit/Write/NotebookEdit）

### 2. 关键格式要求
- JSON 必须只包含 `permissionDecision` + `permissionDecisionReason` 两个字段
- 不要加 `hookEventName` 字段（会导致被当成 warning 而非 deny）
- 退出码必须是 0（非 0 会被当成 error warning 放行）

### 3. 路径匹配
- codebuddy 传给 hook 的 file_path 是绝对路径（如 `/private/tmp/scope-guard-test/outside/outer.txt`）
- scope-guard.py 做了 worktree root 前缀剥离，支持相对 glob 匹配

## 与 qoder 对比
- qoder 官方文档明确 PreToolUse hook unbypassable（ref 07 §9.3）
- codebuddy 实测确认同样 unbypassable（退出码 0 + 正确 JSON 格式）
- 两者 stdin/stdout JSON 格式一致 → scope-guard.py 同时适用

## 文件变更清单
- `skills/multi-agent-orchestration/scripts/scope-guard.py` (新增)
- `skills/multi-agent-orchestration/scripts/spawn-worker.sh` (加 --allow-paths)
- `skills/multi-agent-orchestration/CHANGELOG.md` (v1.17.7)
