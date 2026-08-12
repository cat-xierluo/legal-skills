# Orca-first Worker Backend

> 配合 `SKILL.md` §6.5 阅读。版本：v2.3.0（2026-08-12）。

## 目录

1. 先加载版本匹配指南
2. 双层能力模型
3. Runtime 与 CLI 检测
4. 启动与共享 Run
5. Supervised 生命周期
6. PM 实时感知
7. UI 与状态来源
8. CodeBuddy/Qoder/custom CLI
9. 失败与恢复
10. METADATA 契约

## 1. 先加载版本匹配指南

Orca CLI 与 orchestration contract 会随 runtime 更新。每个新会话先运行：

```bash
orca skills get orca-cli
orca skills get orchestration   # 仅监督/等待/DAG/ask-reply 场景
orca status --json
```

若 `ORCA_CLI_COMMAND` 已设置就使用其值；开发版用 `orca-dev`；Linux 的非 Orca terminal 用 `orca-ide`；其他平台用 `orca`。脚本通过 `scripts/orca-runtime.sh` 固化这一选择。

## 2. 双层能力模型

| 层 | 可用 CLI | Orca UI / Worktree | 会话读取 | Task/Dispatch | 完成权威 |
|---|---|---|---|---|---|
| terminal-managed | 任意交互式 CLI | 有 | `terminal read` | 无 | STATUS + 真实产物，PM 验收 |
| supervised | Orca 能识别并注入的 Agent | 有 | `worker-read`，可证明时读 Agent transcript | 有 | worker 自己发送的 `worker_done` |

不要把 terminal-managed 描述成 supervised。`terminal create` 成功只证明终端存在；`task-list` + `dispatch-show` 才证明编排来源。

## 3. Runtime 与 CLI 检测

旧版用 `TERM_PROGRAM=Orca` + `ORCA_WORKTREE_ID` 判断，会在真实 Orca 会话未注入这些变量时误回落，甚至在 `set -u` 下崩溃。v2.3 改为：

1. 从 `PROJECT_DIR` 求 git toplevel。
2. 在该目录执行 `orca worktree current --json`。
3. 比较 `.result.worktree.path` 与项目 toplevel。
4. 验证 `status` 含 `terminal.multiplex.v1`；supervised 另验 `orchestration.contract.v1`。

`--no-orca-mode` 显式改走 tmux；跨 repo 不误触发 Orca；Orca 模式不把 tmux 当硬依赖。

## 4. 启动与共享 Run

先把同一 Wave 的目标绑定为一个 Run：

```bash
bash scripts/pm-orchestrate.sh run-create --objective "完成 Wave 1 的三个独立任务"
# 从 JSON 读取 .result.run.id
```

再为每个 supervised worker 传同一个 Run ID：

```bash
bash scripts/spawn-worker.sh \
  --project "$PROJECT" \
  --branch feat/worker-a \
  --session worker-a \
  --command "$AGENT_COMMAND" \
  --worker-backend claude-code \
  --orca-supervised \
  --orca-run-id "$RUN_ID" \
  --task-title "worker-a" \
  --task-spec "完整任务、范围、验证与完成协议"
```

`spawn-worker.sh` 先创建 worktree/terminal并等待 TUI ready，再让 `orca-supervised-register.sh` 执行 `task-create → worker-start --terminal`。supervised 路径不发送普通占位 prompt，避免同一任务被执行两次。

Run receipt 中的 coordinator handle 是 consumer fencing 身份，不等同于 Run ID。helper 必须把它作为 `--from` 同时传给 `task-create` 和 `worker-start`；缺失时立即失败并保留 terminal，不能靠当前焦点猜 coordinator。

若不传 `--orca-run-id`，helper 为单 worker 新建 Run，适合独立监督；多 worker Wave 不应各建一个 Run。

## 5. Supervised 生命周期

固定顺序：

```text
PM create/bind Run
  → task-create
  → worker-start（注入 live preamble + TASK）
  → worker 工作；必要时 ask/heartbeat
  → worker 从自己的 terminal 发送且只发送一次 worker_done
  → PM check --wait 收到完整 Delivery
  → PM 处理每条消息并决定 reuse / release / retain
  → PM ack Delivery
```

硬边界：

- Worker 必须使用 preamble 注入的 task/dispatch ID；不得猜 ID。
- `STATUS.json=done` 只唤醒 PM，不结算 Task/Dispatch。
- Sentinel 不得因 STATUS、timeout、idle、heartbeat、question 或 escalation 执行 `worker-stop` / `worker-release` / `terminal close`。
- PM 只对 accepted、settled 的 worker 执行 release；要保留排障就显式 retain；有立即后续任务可复用同一 terminal。
- `check --wait` 返回一个 Delivery；处理全部消息再 ack，并继续等到全部预期 Dispatch settle。

## 6. PM 实时感知

统一用 `pm-orchestrate.sh`：

```bash
# 精确会话读取：优先 Agent transcript，无法证明时 Orca 返回 terminal fallbackReason
bash scripts/pm-orchestrate.sh read --worktree "$WT" --session worker-a --lines 80

# alternate-screen TUI 首读完整历史，之后保存返回的 nextCursor 增量读取
bash scripts/pm-orchestrate.sh read --worktree "$WT" --session worker-a \
  --lines 5000 --cursor 0

# Dispatch/Task/terminal 状态
bash scripts/pm-orchestrate.sh show --worktree "$WT" --session worker-a

# 结构化纠偏，不向 TUI 重复注入任务
bash scripts/pm-orchestrate.sh send --worktree "$WT" --session worker-a --text "只修复测试失败，不扩大范围"

# 等 worker_done / escalation / question；timeout 只是 checkpoint
bash scripts/pm-orchestrate.sh wait --worktree "$WT" --session worker-a --timeout 900

# 回答问题
bash scripts/pm-orchestrate.sh reply --worktree "$WT" --session worker-a \
  --message-id "$MESSAGE_ID" --text "按方案 A"

# 结算 terminal 后再 ack Delivery
bash scripts/pm-orchestrate.sh release --worktree "$WT" --session worker-a
bash scripts/pm-orchestrate.sh ack --worktree "$WT" --session worker-a --delivery-id "$DELIVERY_ID"
```

这比轮询 tmux pane 更适合 PM：`worker-read` 可读取 Orca hook 证明的 Agent transcript，`check --wait` 只在结构化事件到来时唤醒，UI 同时展示 worktree/branch/terminal。

terminal-managed 的 `terminal wait --for tui-idle` 只是 liveness/readiness 信号。实测 CodeBuddy 在界面仍显示等待模型时也可返回 idle；Qoder 的默认 tail 只见 spinner，而 `--cursor 0` 能读到完整历史。因此不得用 idle 或空 tail 判断完成。

## 7. UI 与状态来源

| 来源 | 说明 | 能否证明完成 |
|---|---|---|
| Orca worktree/card | 人类在 UI 看 worker、branch、comment | 否 |
| `worktree ps` agent state | working/idle 等进程信号 | 否 |
| `STATUS.json` | Worker checkpoint、阶段、验证摘要 | 否（supervised） |
| `worker-show` | Task/Dispatch/terminal resource 状态 | 是，需 accepted settlement |
| Delivery `worker_done` | Worker 生命周期报告 | 是，仍需 PM 验收真实产物 |
| Git diff/tests/artifacts | 实际交付证据 | 决定业务验收 |

supervised 的 STATUS done 只把 workspace 标为 `in-review`；PM 验收并结算后再把 UI 状态改为 completed。

## 8. CodeBuddy/Qoder/custom CLI

Orca terminal 对 `--command` 是开放的，因此 CodeBuddy、QoderWork、Claude 第三方 provider wrapper、Codex custom argv 都可由 Orca 启动并出现在 worktree/terminal UI 中。

原生 orchestration 的 `worker-start --terminal` 只接受 Orca 能证明的 Agent session。若某 CLI 未被识别：

1. 保留 terminal-managed 模式，不回落到 tmux。
2. PM 仍可 `terminal read/send/wait`，并在 UI 看 worktree/branch。
3. 不创建虚假的 Dispatch，不要求 worker 发送 `worker_done`。
4. 若用户必须要原生 Task/Dispatch，改用 Orca 支持的 Agent launcher，或等待 Orca 增加该 Agent 识别。

实测边界：CodeBuddy 可以在 terminal read 中看到完整响应；Qoder 可启动、通过 cursor history 读取，但当前 Orca 1.4.180 未把它识别为 agent；OpenCode 若默认 provider 已禁用会出现 TUI 存活但无有效响应，必须先用 `check-opencode-config.sh --model provider/model` 预检。

## 9. 失败与恢复

- `worker-start` 非零：保留其完整 receipt，检查 `stage/effects/residualResources/recovery`；不要固定 sleep 后盲目 retry。
- mutation outcome unknown：只按 receipt 的 `--retry-request` 精确恢复，或用 `dispatch-show --task` 做只读核对。
- terminal handle stale：按 worktree 重新 `terminal list`，后续只用新 handle，禁止双发。
- `check --wait` timeout / count=0：这是 rolling wait checkpoint，不是 worker failed。
- active/unknown Dispatch 的文件清理：`clean-worktree.sh --execute` fail-closed；先人工决定 `worker-stop` 或 `worker-abandon`，不要用 worktree rm 代替生命周期处理。
- provider/custom argv 由 `spawn-worker.sh` 预创建的 terminal 会被 Orca 标记为 external。settled 后 `worker-release` 返回 `retained/external_terminal` 是所有权结果，不是失败；只有 METADATA 与 worker resource 的句柄精确一致时，创建者才可关闭。任何 active/unknown/mismatch 都拒绝清理。

## 10. METADATA 契约

```json
{
  "session": {
    "orca": {
      "mode": "auto",
      "worktree_id": "<repoId>::<path>",
      "worktree_path": "/abs/path",
      "terminal_handle": "term_xxx",
      "app_version": "1.4.180",
      "capabilities": ["terminal.multiplex.v1", "orchestration.contract.v1"],
      "supervised": {
        "run_id": "run_xxx",
        "coordinator_handle": "term_pm_xxx",
        "task_id": "task_xxx",
        "dispatch_id": "ctx_xxx",
        "contract": "orca.orchestration.contract.v1",
        "completion_authority": "worker_done",
        "terminal_ownership": "external"
      }
    }
  }
}
```

无 `supervised` 子块就只能按 terminal-managed 处理。Handle 是 runtime-scoped；Run/Task/Dispatch 是结构化协调身份，不要互相替代。
