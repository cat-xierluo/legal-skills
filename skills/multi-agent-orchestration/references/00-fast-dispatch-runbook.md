# 快速派发 Runbook（Claude Code + GLM/MiniMax + Orca 标准通道）

> 2026-09-23 实战固化（badminton-lab BL-215/216 波，zcode PM 宿主端到端验证）。
> 适用：常规实现/修复/审查 worker。supervised 波次仪式（Run/Task/Dispatch/
> `orca-wave-prepare.sh`）只在需要 ask/decision gate/DAG/多 worker 共享 Run 时用；
> 常规单/双 worker 直接走本页，不需要 PM_TERMINAL。

## 前置（一次性确认）

- Orca 在跑：`orca status --json` 里 `runtime.state == "ready"` 即可；spawn 会自动
  接管 Orca 终端与 worktree（落 `~/orca/workspaces/<repo>/<branch>`）。
- `claude --version` 可解析（spawn 内部会做 PATH 注入）。
- 模型路由已由 `config/orchestration-personal.json` 的 `quota_aware_routing`
  （enabled=true）提供：**不传 profile 时 route_suggest 按 lane 额度自动选**
  （glm-5.3=深度 / glm-5.3-flash=跑腿 / minimax-M3=L0 批量）。只想锁定模型时才传
  `--runtime-profile glm-5.3|minimax-M3|glm-5.3-flash`；PM 宿主白名单见
  `config/harness-backend-policy.json`（zcode→claude-code/codex 本来就放行）。

## 三步

### 1. spec + 价值门（§3.2 门 1，必须先过）

写 `dispatch-value-gate.v2` spec（模板 `templates/dispatch-value-gate.example.json`；
`verification_commands` 写定向/scoped 命令，全量套件归 PM 收口），然后：

```bash
python3 scripts/dispatch-value-gate.py spec-blXXX.json   # 期望 {"ok": true}
```

### 2. spawn（一条命令）

```bash
bash scripts/spawn-worker.sh \
  --project "$PROJ" \
  --branch feat/blXXX-short-slug \
  --session blXXX-wN \
  --worker-backend claude-code \
  --runtime-profile glm-5.3 \
  --branch-lifecycle ephemeral-worker \
  --base-ref main \
  --verification-contract "$SPEC_DIR/spec-blXXX.json" --verification-task-id BL-XXX \
  --git-expected-name <git-name> --git-expected-email <git-email> \
  --git-integration-base main --git-push-remote origin \
  --command 'claude --permission-mode auto "Read /tmp/<wave>/blXXX-WORKER-PROMPT.md and execute the task it describes. Reply in Chinese."'
```

自动完成：harness 白名单校验 → 验证合同 preflight → quota/mem 预算 → provider
lease（claude-code 并发上限见 personal config）→ Orca 终端 + worktree + Session
Context 脚手架 + authority receipt。成功标志是结尾打印 `SPAWN_WORKER_NEXT:
send worker prompt, then wait for .../STATUS.json`。

### 3. 巡检

- 进度：`<orca-worktree>/.claude/agent-sessions/<session>/STATUS.json`、
  `git -C <orca-worktree> log --oneline`、远端分支、`gh pr list`。
- 完成权威（terminal-managed 模式）= terminal 输出 + checkpoint 文件 + 真实
  diff/测试/PR，不认自报。

## 已知坑（均为实付学费）

1. **不要 `--bare`**：v2.11.0 起与 PreToolUse hook 强制互斥，spawn 直接 fail-closed
   （`--bare auto-degrade removed`）。`--permission-mode auto` 就够。
2. **zcode 是合法 PM 宿主**（policy `zcode → [claude-code, codex]`）：不要想当然认
   为会被挡、先去读 spawn 源码找备选路径——脚本本来就 fail-closed，直接跑，第一行
   输出就会打印 `SPAWN_WORKER_HARNESS_POLICY: pm=... allowed=...`。
3. `--base-ref` 只收引用名（`main`/`origin/main`），裸 sha 会被
   `SPAWN_WORKER_BASE_REF_MUST_BE_REF` 拒绝。
4. 默认命令（不传 `--command`）= 空 claude 会话，不会自动领任务；常规派发必须传
   带 Read 指向任务书的 `--command`。长 prompt 放 /tmp 文件，命令里只留一句 Read。
5. 项目侧前置（badminton-lab）：BL/DEC 取号必须先 registry+TASKS 进 main 再
   spawn；TASKS `next_transition` ≤200 字；registry 状态词只能用
   已分配/已兑现/已交付待验收/已交付但验收否决（`check_task_source_consistency.py` 强制）。
