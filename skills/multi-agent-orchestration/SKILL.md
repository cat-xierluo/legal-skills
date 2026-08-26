---
name: multi-agent-orchestration
description: 本技能应在用户要求并行推进多个任务、开启多个 worker/agent、使用 Orca Run/Task/Dispatch 或 tmux 独立 session、让 PM 通过 UI/会话转录实时巡检并统一调度 Claude Code、Codex、CodeBuddy、QoderWork 等 CLI，或要求防止 PM 直接实现逃逸时使用；用户授权 Wave Autopilot 后，PM 按项目任务源固定策略自动链式推进波次（组波/派单/验收/合并/泊车）。触发词包括“并行推进”“开多个 worker”“Orca 编排”“supervised worker”“PM 总控”“独立 session”“多 agent 并行”“分派任务”“自动推进”“Wave Autopilot”“自动组波/自动推进波次”。不要用于单个短任务、纯任务状态同步，或 Git 分支/提交/PR/merge 规则。
license: MIT
metadata:
  version: "2.8.0"
  homepage: https://github.com/cat-xierluo/legal-skills
  author: 杨卫薪律师（微信ywxlaw）
---

# Multi-Agent Orchestration

以当前主会话作为 PM，拆解、派工、巡检、验收和收口多个本地 Agent。优先使用 Orca 作为控制平面；Orca 不可用或用户明确要求 tmux 时使用 tmux。不要把“开了终端”误写成“建立了受监管任务”。

## 1. 边界与权限

使用本 Skill：

- 同时推进 2 个以上边界独立的本地任务。
- 需要独立 worktree、分支、session、额度 lane 或可人工接管的长任务。
- PM 需要读取 worker 进度、纠偏、等待结构化完成事件并统一收口。
- 用户明确要求 Orca、tmux、独立 session、多个 worker 或 PM/orchestrator 模式。

不使用本 Skill：

- 单个短任务、一次性问答或无并行价值的单文件修改。
- 任务源、负责人和依赖状态同步：使用 `cross-agent-coordination`。
- branch/commit/push/PR/merge/冲突规则：使用 `git-workflow`。
- 非 CLI harness 内嵌 Agent 无法启动或控制本地 Agent CLI 时，使用宿主自己的 subagent 能力。

本 Skill 会执行以下本地副作用：

- 在用户指定仓库创建 Git/Orca worktree、分支、Session Context、终端或 tmux session。
- 启动用户选择的本地 Agent CLI；supervised 模式还会在 Orca runtime 创建 Run/Task/Dispatch、消息和 UI 状态。
- `clean-worktree.sh` 默认只预览；只有显式 `--execute` 才清理目标会话/worktree，生命周期未知时失败关闭。
- provider settings/registry 可能含 Token。只读取用户明确指定的配置；真实配置及 `*.bak*` 不得入库、不得写入日志，疑似泄露立即轮换。
- 不自动安装依赖，不自动 push、合并或发布。安装必须有精确命令和可审计授权来源。

## 2. 模式选择

| 模式 | 何时选择 | 能力边界 |
|---|---|---|
| Orca supervised | 用户要求监督、等待结果、DAG、ask/reply、decision gate；Agent 可被 Orca 识别 | Worktree + Run/Task/Dispatch + worker transcript + `worker_done` |
| Orca terminal-managed | 已配置的 CodeBuddy/QoderWork CN，或四种白名单 backend 的非 supervised 路径 | Worktree + terminal + UI + terminal read/send/wait |
| tmux worktree | Orca 不可用、用户指定 tmux、或需复现非 Orca 路径 | Git worktree + tmux + checkpoint/Sentinel |
| tmux lightweight | 用户明确不要 worktree，或目标不是 Git 仓且 worker 文件夹互不重叠 | 文件夹 + tmux；无 Git 隔离 |
| 同宿主 subagent | 窄范围、短任务、无需独立进程/分支 | 宿主决定 |
| Claude Agent Teams/view | Claude Code 做 PM 且项目明确采用其原生团队能力 | 按 Claude 官方会话与 worktree 规则 |

同一 worker 只能有一个控制模式。terminal-managed 没有 Task/Dispatch，不得要求 `worker_done`；supervised 必须有 live preamble 与 Task/Dispatch，不得用终端文本或 STATUS 冒充完成。

## 3. 不变量与启动门禁

PM 在业务实现前完成：

1. 读取项目规则和完整任务卡，确定目标、非目标、allowed/forbidden files、验证命令与完成条件。
2. 按根因、依赖链和文件范围分组；只有改动范围正交、验收独立、无共享锁文件/schema/迁移时才并行。
3. 为每个 worker 指定 branch、worktree、session、backend/profile/model、provider slot 和 Session Context。
4. 启动后验证真实 cwd/worktree/branch/session；门禁失败不得由 PM 静默接管业务实现。
5. 发送完整 worker prompt，确认 checkpoint 或 Orca Dispatch 出现，再进入巡检。

硬约束：

- 先执行 Harness 调用层级门禁。Claude Code/Codex PM 可派发四个已配置 backend；CodeBuddy、QoderWork CN PM 只能派发自身。未知、冲突或无法证明的宿主身份失败关闭。
- PM 默认只做拆解、派工、纠偏、review 和收口；用户明确授权或编排层本身需要修复时才直接修改。
- 每个 worker 只修改自己的允许范围。共享文件、锁文件和全局契约按依赖顺序处理。
- 轻量模式下不同 worker 必须占用互不重叠的文件夹；可能写同一目录时回到 worktree 模式。
- Worker 验证命令不是安装授权。缺工具时报告阻塞，除非 PM 传入精确 `--allow-install-command` 和 `--install-authorization-source`。
- Worker 自报、STATUS、UI 卡片、TUI idle、heartbeat 和 timeout 都不能单独证明业务完成。

Issue 分组细则读取 `references/11-issue-grouping.md`；并发与真实踩坑读取 `references/09-parallel-lessons.md`。

### 3.1 Harness 调用层级

| PM 宿主 | 允许派发的 worker backend |
|---|---|
| Claude Code | Claude Code、Codex、CodeBuddy、QoderWork CN |
| Codex | Claude Code、Codex、CodeBuddy、QoderWork CN |
| CodeBuddy | CodeBuddy |
| QoderWork CN | QoderWork CN |

`spawn-worker.sh` 从完整进程祖先链的真实可执行程序识别宿主，对每层 Harness 的白名单取交集，使嵌套调用只能降权、不能借强 CLI 恢复权限；在 Orca 能唯一定位当前 worktree 的 working agent 时再交叉校验。同一 worktree 有多个 working agent 时不拿模糊 Orca 信号覆盖进程证据；若进程也无法证明身份则失败关闭。任务文本、已安装 CLI、个人偏好配置和 `--pm-harness` 都不是授权来源。`--pm-harness` 只能声明预期身份，与检测结果不一致时失败，不能向上提权。权威白名单为 `config/harness-backend-policy.json`，默认拒绝；结果写入 `METADATA.runtime.harness_authority`。

声明的 worker backend 还必须与实际启动命令一致。只接受直接启动四种 CLI、受信的 Claude provider wrapper，或由 `render-runtime-profile.sh` 生成的受限 batch shell；任意 backend 标签伪装、命令链和不透明 wrapper 在副作用前拒绝。安装守卫降级不能放宽此身份门禁。

### 3.2 worktree 依赖补偿 + 默认 verify 命令（Task-045/046，G31）

`spawn-worker.sh` source `scripts/spawn-worker-deps.sh`，在 worktree 创建后自动补偿依赖 + 注入默认 verify 命令，让 worker 不靠路径巧合也能自验：

- **依赖补偿**（`ensure_worktree_deps`，项目类型感知，读全局 `PROJECT_DIR`/`WORKTREE`）：
  - **Node**：worktree 不在主仓父链（Orca `~/orca/workspaces/` 是独立路径树）且主仓有 `node_modules` → 软链 `worktree/node_modules → 主仓/node_modules`。tmux worktree 本在主仓子树（`.claude/worktrees/`）靠 npm 向上解析（G28），不软链。
  - **Rust**：`~/.cargo` registry 全局共享、worktree `target/` 独立，不补偿。
  - **Python**：venv 含绝对路径、软链会挂，默认不自动补偿；PM 可显式传 `--python-runtime-symlink <主仓 .runtime>`（v2.7 Task-061，badminton-lab Wave 1/2 两轮验证的模式）共享主仓运行时——fail-closed：worktree 已有 `.runtime` 则保留、源解释器缺失或为 0 字节占位（Wave 1 实际出现）拒绝启动、软链失败退出非零；`clean-worktree.sh` 删除前安全 unlink 该软链。
- **默认 verify 命令**（`inject_default_verify_commands`，`write_install_authorization` 前调用）：PM 未传 `--verify-cmd` 时，按 `package.json` scripts 注入 `npm run typecheck/lint/test/test:e2e/build` 到 `VERIFY_COMMANDS` → 进 `allowed_shell` 白名单。`test:e2e` 是 verification-gate 的功能完成线（编译过 ≠ 功能可用，FaroPDF 2026-08-05 QA-02 教训），项目有该 script 就默认注入；无则自动跳过。npm 未注入任何命令时**兜底扫 Makefile**（v2.7 Task-057，badminton-lab Wave 2 事故根因：Make 驱动的 Python 项目零注入，worker 全部 `make` 门禁被 `SHELL_COMMAND_NOT_ALLOWLISTED` 拦截）：解析 `^target:` 目标名，只注入白名单动词 `test / test-* / check / ci / lint` 为 `make <target>`，`.PHONY`/变量赋值/文件目标不匹配；其他门禁目标（如 `security-scan`）PM 显式传 `--verify-cmd`。PM 显式 `--verify-cmd` 优先，不覆盖。

依赖补偿必须失败关闭：目标处已有真实目录就保留，断裂 symlink 或创建 symlink 失败则 `spawn-worker.sh` 退出非零，不能留下一个看似已启动、实际无法验证的 worker。用 `scripts/test-spawn-worker-deps.sh` 覆盖路径类型、默认/显式 verify 和双 worker 并发。

`clean-worktree.sh` 删 worktree 前安全 unlink 该软链（`[ -L ] && rm -f` 无尾斜杠，绝不跟随删主仓 `node_modules`）。install-guard 仍 `deny_by_default` 拦 `npm install/ci/add`，worker 不会误改主仓 `node_modules`。详见 `references/09-parallel-lessons.md` G28/G31。

### 3.3 PM spawn 操作纪律（Task-041~044，Wave-2 实战）

spawn 一个 worker 后，PM 的操作纪律（Wave-2 实战撞坑固化）：

1. **不主动 send 完整 task prompt**（Task-042）：`--orca-supervised` 的 worker 由 `worker-start` 注入 live preamble + TASK（唯一任务注入器，见 §4.4/4.5）。PM spawn 后再 send 完整 prompt 是重复投递，会让 worker 混淆/双重执行。长 prompt 写 `WORKER_PROMPT.md`（Session Context），terminal 只发短 Read 指令触发。
2. **Wave 先建完整控制面，再并行启动**（Task-043/050）：用 `orca-wave-prepare.sh` 一次创建/绑定 Run，并在任何 worker 启动前串行创建全部独立 Task；receipt 固化 `run_id`、`coordinator_handle` 和各 `task_id`。不要重试 `run-create`，也不要让并发 spawn 各自 `run-use/task-create`，否则会触发 consumer fencing 或重复 Task。
3. **supervised worker 不用 pm-monitor/sentinel 判完成**（Task-041）：supervised 完成唯一权威是 `worker_done → Delivery`（`pm-orchestrate show/wait` 读 dispatch + Delivery）。`pm-monitor`（STATUS/commit-stale）和 `sentinel`（tui-idle/timeout）的信号不是 supervised 完成权威——`STATUS=done` ≠ Delivery、tui-idle 只表示可交互不表示完成。supervised 的 PM 只用 `pm-orchestrate show/wait`；pm-monitor/sentinel 是 tmux/terminal-managed 回退路径的辅助观察器，套到 supervised 会误判。
4. **只并行无依赖步骤**（Task-044/050）：spawn 前的独立探查和 receipt 完成后的多个 worker 启动/核验可并行；Run 和全部 Task 的创建属于 Wave 准备屏障，必须先串行完成。依赖链（Task 预建→worker-start、spawn→核验、verify→commit）保持串行。

### 3.4 `spawn-worker.sh` 模块边界（Task-048）

`spawn-worker.sh` 保留启动顺序、全局默认值和跨模块编排；下列 sourced 模块只承载单一职责，不得绕过入口门禁独立执行生产副作用：

- `spawn-worker-flags.sh`：usage 与参数解析。
- `spawn-worker-orca.sh`：Orca runtime 检测、worktree 创建和 terminal 注入。
- `spawn-worker-metadata.sh`：Session Context `METADATA.json` 合同。
- `spawn-worker-provider-lease.sh`：provider lease acquire/finalize/provisional cleanup。
- `spawn-worker-launch.sh`：tmux/Orca 共用启动边界与 supervised 注册。

这些模块继续使用入口已初始化的全局变量，以保持现有 CLI 和生命周期语义；行为变更应另立任务，不得借结构重构顺带修改。每个模块都有同名 `test-spawn-worker-*.sh` 直接合同测试，仍需配合完整 smoke 验证真实入口。

## 4. Orca-first 控制平面

### 4.1 先读取版本匹配指南

每个新会话先运行：

```bash
orca skills get orca-cli
orca skills get orchestration   # 仅 supervised / DAG / ask-reply 场景
orca status --json
```

以运行中二进制返回的指南和 `--help` 为准，不从本 Skill 猜未来参数。脚本（包括 Harness 权限检测）通过 `scripts/orca-runtime.sh` 统一 CLI：`ORCA_CLI_COMMAND` → dev `orca-dev` → Linux 外部 shell `orca-ide` → `orca`。

### 4.2 检测真实运行时

`spawn-worker.sh` 在 `PROJECT_DIR` 的 Git toplevel 调用 `orca worktree current --json`，只有返回的 `.result.worktree.path` 与项目一致才进入 Orca。不要依赖 `TERM_PROGRAM` 或 `ORCA_WORKTREE_ID`；它们在真实 Orca session 中可能不存在。

显式 `--no-orca-mode` 使用 tmux。`--no-worktree` 与 Orca worktree 模式互斥。Orca 路径本身不要求 tmux。

### 4.3 Terminal-managed

适用于 CodeBuddy、QoderWork CN，以及四种白名单 backend 中不采用 supervised 的交互式 CLI：

```bash
bash scripts/spawn-worker.sh \
  --project "$PROJECT" --branch feat/worker-a --session worker-a \
  --pm-harness codex --worker-backend codebuddy --command "$WORKER_COMMAND"
```

PM 可在 Orca UI 查看 worktree、branch、terminal，用统一入口控制：

```bash
bash scripts/pm-orchestrate.sh peek --worktree "$WT" --session worker-a
bash scripts/pm-orchestrate.sh read --worktree "$WT" --session worker-a --lines 5000 --cursor 0
bash scripts/pm-orchestrate.sh send --worktree "$WT" --session worker-a --text "只修测试失败"
bash scripts/pm-orchestrate.sh wait --worktree "$WT" --session worker-a --timeout 300
```

CodeBuddy/Qoder 的 trust/permission dialog 由 `spawn-worker.sh` 通过 Orca terminal read/send 或 tmux capture/send 处理。CLI 未被 Orca 识别时仍保留 terminal-managed，不伪造 Dispatch。

当前两阶段启动显式使用 `worktree create --setup inherit → 写入 Session Context/权限与 scope hook → terminal create --command`。不要直接改成 `worktree create --agent`：其原子启动会早于本 Skill 写入机械门禁。只有 Orca 提供预置文件或延迟 Agent 启动合同后，才切换 agent-first；自定义 provider/wrapper 始终保留 external terminal 路径。

`terminal wait --for tui-idle` 只表示 TUI 可交互或暂时空闲，不表示任务完成。Qoder 等 alternate-screen TUI 应从 `--cursor 0` 开始保存返回的 `nextCursor` 做增量读取；最终仍以 STATUS/RESULT、真实 diff/tests/artifacts 和 PM 验收为准。

### 4.4 Supervised：一个 Wave 共用一个 Run

当用户明确要求监督、等待结果或协调 DAG 时，先写 Wave manifest，并在任何 worker 启动前预建一个 Run 和全部 Task：

```bash
cat > /tmp/wave.json <<'JSON'
{"objective":"Wave 1 objective","tasks":[
  {"key":"worker-a","title":"worker-a","spec":"完整任务、范围、验证和完成协议"},
  {"key":"worker-b","title":"worker-b","spec":"完整任务、范围、验证和完成协议"}
]}
JSON
bash scripts/orca-wave-prepare.sh --manifest /tmp/wave.json --receipt /tmp/wave-receipt.json
```

receipt 成功后，才并行启动 worker；每个 worker 复用同一 `run_id/coordinator_handle` 与自己的 `task_id`：

```bash
bash scripts/spawn-worker.sh \
  --project "$PROJECT" --branch feat/worker-a --session worker-a \
  --worker-backend claude-code --command "$AGENT_COMMAND" \
  --orca-supervised --orca-run-id "$RUN_ID" \
  --orca-coordinator-handle "$COORDINATOR_HANDLE" \
  --orca-task-id "$TASK_A_ID"
```

`orca-wave-prepare.sh` 给每个 Task spec 前置不可省略的 `worker_done` 协议提醒；spec 内的 branch 名一律用**连字符形式**（Orca worktree `--name` 与 spawn 的 `safe_branch` 都会把 `/` 规范成 `-`，spec 写斜杠名会让 worker 隔离门禁误判 blocked——Wave 1 教训，manifest 含 `branch: x/y` 会被 `orca-wave-prepare.sh` fail-closed 拒绝）。`orca-supervised-register.sh` 直接复用 receipt，对 `worker-start` 显式传 `--from`，避免并发 rebinding；被 `task_not_startable` 拒绝时带 `--reset-failed` 可把前任 worker 提问/中止翻成 failed 的 Task 复位 ready 重试一次（Task-060）。单 worker 可不传 receipt，由 helper 创建 Run/Task。`worker-start` 是唯一任务注入器；supervised 路径不得再发送普通 prompt。注册失败保留 receipt 与 terminal 供精确恢复，但整个 spawn 返回非零。**并行 worker 会同时写共享文档时（CHANGELOG/DECISIONS/TASKS），PM 在各 spec 中预分配互不冲突的编号与槽位**（如 DEC-044/045 分派到不同 worker），合并冲突留给 PM 收口按既定模式解。

### 4.5 Supervised 生命周期

固定顺序：

```text
PM create/bind Run
  → 在任何 worker 启动前创建全部 Task
  → worker-start 注入 live preamble + TASK（各 worker 可并行）
  → worker 工作；必要时 ask/heartbeat
  → worker 从自己的 terminal 精确发送一次 worker_done
  → PM check --wait 收到完整 Delivery
  → PM 处理每条消息并验收真实 diff/tests/artifacts
  → 每个 settled terminal 选择 reuse / release / retain
  → PM ack Delivery
```

PM 常用命令：

```bash
bash scripts/pm-orchestrate.sh read --worktree "$WT" --session worker-a --lines 80
bash scripts/pm-orchestrate.sh show --worktree "$WT" --session worker-a
bash scripts/pm-orchestrate.sh wait --worktree "$WT" --session worker-a --timeout 900
bash scripts/pm-orchestrate.sh reply --worktree "$WT" --session worker-a --message-id "$MID" --text "按方案 A"
bash scripts/pm-orchestrate.sh release --worktree "$WT" --session worker-a
bash scripts/pm-orchestrate.sh ack --worktree "$WT" --session worker-a --delivery-id "$DID"
```

授权快照运行时刷新（Task-058，Wave 2 事故链路固化）——worker 被 `SHELL_COMMAND_NOT_ALLOWLISTED` 拦住验证命令且根因是 spawn 授权不含它时：

```bash
bash scripts/pm-orchestrate.sh reauthorize --worktree "$WT" --session worker-a \
  --allow-cmd "make test" --allow-cmd "make ci" \
  --resume-text "终端已重启，授权已刷新；你的未提交进度保留在 worktree，从断点继续"
```

一条命令完成：授权文件合并 → launch.sh B64 重写（guard 读内联快照，改文件对运行中进程无效）→ Task 复位 → 同 worktree 新终端 + Task 重注册（worker-start 重注入）→ METADATA 改路由 → 关旧终端。未提交工作区改动全部保留。

每次 supervised 的 send/wait/reply/release/retain/ack/settle 都先由脚本对当前 PM terminal 执行 `run-use`，并把新 coordinator handle 写回 METADATA；`check` 随后消费已绑定 Run，不携带陈旧 `--run` 路由。`wait` 不自动 ack。timeout/count=0 只是滚动巡检窗口结束，不是失败。Sentinel 不得因 STATUS、idle、heartbeat、question、escalation 或 timeout 执行 stop/release/terminal close。完整契约读取 `references/12-orca-cli-worker.md` 和 `references/13-pm-orchestrate.md`。

由 `spawn-worker.sh` 预先创建、再交给 `worker-start --terminal` 的 provider terminal 属于 external resource。settled 后 `worker-release` 可能正确返回 retained；清理脚本只有在 worker/Dispatch 已结算、ownership/reason 明确为 `external/external_terminal` 且 Orca resource handle 与 METADATA 完全一致时，才由创建者关闭这个精确句柄，其他状态一律失败关闭。

**Dispatch 死锁兜底 `settle`（Task-047R）**：若 worker 进程已死但未发 `worker_done`，用 `pm-orchestrate settle --worktree <WT> --session <S> --reason "..." [--force] [--destroy]`：
1. **身份与审计门禁**：METADATA.project 与 worker 必须属于同一 Git common dir；先在 `<git-common-dir>/orchestration/settle-audit.ndjson` 持久化 reason，审计不可写则不做 mutation。
2. **严格 liveness gate**：只有 `observation.status=exited|missing` 与 `worker.state=succeeded|failed|stopped` 的已知死亡组合通过；缺字段、active 和未来未知值全部 REFUSED exit 2，除非 PM 明确 `--force`。
3. **原子结算**：先用当前 Orca 的 `worker-stop` 对精确 Dispatch 原子 fence+stop。失败时只尝试一次非破坏性的 `worker-abandon` 兜底，记录审计并返回 2；无论 abandon 是否成功，都不得进入 `--destroy`。
4. **默认安全**：成功 stop 后仍不删 worktree/lease/symlink/Session Context。PM 可先保存输出，再跑 `clean-worktree.sh --execute --force-remove-dirty`。
5. **显式 `--destroy`**：仅在 stop 成功后释放 provider lease、由 Orca 删除精确 worktree、再对完全匹配的 Git worktree 做 fallback；路径仍存在则失败。审计位于 common dir，删除 Session Context 后仍可追溯。
- `--reason` 强制。`--force` 只覆盖 liveness 不确定性，不覆盖身份、审计、stop、lease 或删除失败。
- 这是 supervised 正式 lifecycle（worker_done→Delivery→release→ack）的例外兜底，不是常规收尾——优先让 worker 正常发 `worker_done`。
- 验证：`test-settle-liveness.sh` 覆盖响应字段矩阵；`test-settle-command.sh` 覆盖 mutation 顺序、失败保留、精确删除与持久审计。

### 4.6 Wave Autopilot（用户授权的常设自动推进）

用户显式授权后，PM 按项目任务源中固定的组波/泊车策略自动链式推进波次：收口后自动写回任务源、查表组下一波并派发，直到泊车条件。**授权与策略权威都在项目上下文**（本 skill 不承载项目授权）；查表查不到合法组合即泊车，这是 Autopilot fail-closed 的根本。验收路径不因自动化放宽（门禁在最终树复跑 + safe-push + PR squash 强制），每波收口发摘要但不等确认，泊车必须完整报告后停止。

Autopilot 活跃期间**必须挂 recurring cron 看门狗**，并与 Orca 推送、Dispatch 状态轮询三通道并用——推送唤醒实测会丢（worker_done 可延迟数小时不唤醒 PM）；完成判定的权威是 `worker-show` 的 dispatch/worker 状态，不是队列里有没有消息。看门狗每跳清单、验收期确定性缺陷的 fix-worker 派发模式与实测反模式读取 `references/14-wave-autopilot.md`。

## 5. tmux 回退

先按 backend 生成命令，再 spawn：

```bash
bash scripts/render-runtime-profile.sh \
  --backend claude-code --runtime-profile default \
  --api-provider provider-a --model model-a --output command

bash scripts/spawn-worker.sh \
  --project "$PROJECT" --branch feat/worker-a --session worker-a \
  --base-ref main --command "$WORKER_COMMAND" \
  --worker-backend claude-code --with-sentinel --no-orca-mode
```

spawn 后立即验证：

```bash
tmux has-session -t worker-a
tmux display-message -p -t worker-a '#{pane_current_path}'
test -f "$WT/.claude/agent-sessions/worker-a/METADATA.json"
```

不要 `tmux attach` 阻塞 PM 主循环，也不要无 timeout 等 STATUS。长 prompt 写入 Session Context 的 `WORKER_PROMPT.md`，只向 terminal 发送短 Read 指令。详见 `templates/pm-spawn-postflight.md`。

## 6. Worker Prompt 与 Session Context

使用 `templates/worker-prompt.md`。至少填写：

- Background、Mission、Allowed files、Forbidden files、Non-goals。
- Branch、Worktree、Session Context、Runtime Profile、provider/model。
- Project Skills 的已验证路径；不要让独立 cwd 中的 worker 猜 sibling Skill 位置。
- Verification commands、Execution Authority、安装授权来源。
- STATUS/RESULT/PATCH_SUMMARY 的路径和更新节奏。
- supervised 时由 live preamble 提供 task/dispatch ID；worker 不得猜 ID，完成后只发一次 `worker_done` 并停止新工作。

Session Context 默认：

```text
<worktree>/.claude/agent-sessions/<session>/
├── METADATA.json
├── STATUS.json
├── RESULT.md
├── PATCH_SUMMARY.md
└── WORKER_PROMPT.md
```

字段与 checkpoint 语义读取 `references/03-checkpoint-files.md`。`STATUS.status` 使用 `running|done|failed|blocked|stopped`，成功只写字面 `done`。

supervised 模式下 STATUS 是**辅助观察信号**（阶段/心跳），完成权威是 `worker_done → Delivery`；PM 的 wave spec 不要把『周期性 STATUS 更新』当作完成判据或巡检依据（Wave 2 实测三个 supervised worker 均未写 STATUS，Delivery 流转完全正常）——supervised 巡检用 `check --wait`/`pm-orchestrate wait`，STATUS 轮询只适用于 tmux/terminal-managed 回退路径。

## 7. 巡检与介入

按证据优先级巡检：

1. supervised：Delivery、`worker-show`、`worker-read`。
2. terminal-managed：terminal read + STATUS/RESULT。
3. tmux：STATUS/RESULT、git status/log、bounded capture-pane。
4. 所有模式最终检查真实 diff、测试、产物和 PR 状态。

辅助脚本：

```bash
bash scripts/worktree-status.sh --project "$PROJECT" --branch feat/worker-a --session worker-a
bash scripts/pm-monitor.sh --project "$PROJECT" --branch feat/worker-a:worker-a --once
bash scripts/sentinel.sh --status-file "$CTX/STATUS.json" --tmux-session worker-a
```

Sentinel 是唤醒/观察器，不是 supervised lifecycle authority。发现偏题、阻塞、越界或验证失败时优先给原 worker 发窄纠偏；需要独立审阅时另派 reviewer。Sentinel 设计读取 `references/04-sentinel-design.md`。

worker TUI 被限流或中断后停在 idle 时，`pm-orchestrate send`（supervised 走 Dispatch inbox）叫不醒它——用 `orca terminal send --terminal <handle> --text "..." --enter` 直接键盘注入；判活看 `peek` transcript 时间戳距当前的差值（G39）。

## 8. 收口

PM 必须：

1. 读取 worker 交付、完整 Delivery 和实际 diff，不采信单句“完成”。`worker-show/dispatch-show` 与 diff/tests 可以证明业务状态，但只读检查不能替代 `worker_done` 或 `settle` 的生命周期结算。
2. 运行与产物类型匹配的验证；GUI/Web/桌面行为要启动真实入口做代表性交互。
3. 核对 allowed files、敏感文件、安装授权、Git identity、commit 和 PR 范围。
4. supervised worker 先 reuse/release/retain，再 ack；不得因为只读检查“看起来完成”而跳过 settlement。worker 仍存活且漏发 `worker_done` 时先结构化提醒；确认已死才走 `settle`。terminal-managed/tmux 按用户意图保留或关闭。
5. 用 `git-workflow` 完成 rebase/push/PR/merge；本 Skill 不替代 Git 安全规则。
6. 清理前先 dry-run：

```bash
bash scripts/clean-worktree.sh --project "$PROJECT" --branch feat/worker-a --session worker-a
# 确认目标、dirty 状态和 Orca terminal accounting 后才加 --execute
```

active、release_pending、release_unknown 或生命周期不明的 supervised worker 一律拒绝删除 worktree。

## 9. Backend 与配置

默认优先与 PM 同宿主，只有额度、模型能力或用户明确要求时跨工具；跨工具仍不得越过 §3.1 的 Harness 白名单。个人偏好写入 ignored 的 `config/orchestration-personal.json`，模板为 `.example.json`；项目 trunk、任务源、验证命令和 provider slots 可写入 `.claude/orchestration.config.json`。个人配置只能选择白名单以内的 backend，不能扩张宿主权限。

`concurrency.per_backend[backend]` 优先于 `concurrency.max_per_provider`。配置有效正整数时，`spawn-worker.sh` 在任何 branch/worktree 副作用前获取原子 provider 租约，启动后绑定实际 tmux session 或 Orca terminal；Sentinel、`pm-orchestrate release` 和 `clean-worktree` 只在资源已结算或关闭时释放。无配置时输出 advisory，不假装机械限额。

不得复制 `.env`、真实 settings、Token、cookie、证书或账号凭证到 worktree/提交。Claude provider 隔离、CodeBuddy、QoderWork CN、Codex 参数分别读取：

- `references/01-model-selection-matrix.md`
- `references/06-agent-cli-reference.md`
- `references/07-qoderwork-cli-worker.md`
- `references/08-codebuddy-cli-worker.md`

## 10. 依赖

### 系统依赖

| 依赖 | 安装方式 |
|---|---|
| `bash` 4+ | macOS: `brew install bash`；Linux: 包管理器安装 |
| `git` | macOS: `xcode-select --install` 或 `brew install git` |
| `jq` | macOS: `brew install jq`；Linux: `sudo apt-get install jq` |
| `tmux` | 仅 tmux 路径需要；macOS: `brew install tmux` |
| `python3` | 安装门禁和 scope guard 需要 |

Orca 路径需要运行中的 Orca runtime 与版本匹配 CLI，不自动安装。按 backend 还需对应 `claude`、`codex`、`codebuddy` 或 `qoderclicn`。

```bash
bash scripts/check-dependencies.sh --backend claude-code --backend codex --check-gh
```

## 11. 按需 references

- `references/02-runtime-dependencies.md`：运行时依赖与配置复制边界。
- `references/03-checkpoint-files.md`：METADATA/STATUS/RESULT/PATCH_SUMMARY。
- `references/04-sentinel-design.md`：事件驱动唤醒和 timeout 语义。
- `references/05-legal-domain-patterns.md`：法律任务常见拆分。
- `references/09-parallel-lessons.md`：并发、dialog、provider 和历史故障。
- `references/10-agent-teams-troubleshooting.md`：Claude 原生团队/会话排障。
- `references/11-issue-grouping.md`：Issue 分组、依赖链和 PR 粒度。
- `references/12-orca-cli-worker.md`：Orca 双层模型、runtime、Run/Task/Dispatch 和恢复。
- `references/13-pm-orchestrate.md`：PM 三模式统一控制入口。
- `references/14-wave-autopilot.md`：Wave Autopilot 自动推进、三通道监控、看门狗清单与泊车语义。

不要一次加载全部 references；按当前 backend、控制模式和故障类型读取。

## 12. 验收门禁

Hard Fail：

1. 用户要求 PM/worker 编排，启动门禁未过而 PM 直接写业务代码。
2. worker cwd/worktree/branch 与目标不一致。
3. 真实 provider settings 或备份进入 Git/打包件。
4. 未授权安装、全局环境写入、raw push 或范围外修改。
5. supervised worker 无 live Task/Dispatch，或用 STATUS/Sentinel 代替 `worker_done`。
6. PM 未处理完整 Delivery、未结算 settled terminal 就 ack/结束。
7. 清理 active/unknown/release_pending/release_unknown supervised worker。
8. 只凭 worker 自报、静态 lint 或单次 UI 状态声称业务完成。
9. CodeBuddy/QoderWork CN 或未知宿主向上/跨宿主派发，或用 `--pm-harness`、个人配置伪造宿主身份。

修改本 Skill 后至少运行：

```bash
find scripts -type f -name '*.sh' -print0 | xargs -0 -n1 bash -n
bash scripts/test-spawn-worker-flags.sh
bash scripts/test-spawn-worker-orca.sh
bash scripts/test-spawn-worker-metadata.sh
bash scripts/test-spawn-worker-provider-lease.sh
bash scripts/test-spawn-worker-launch.sh
bash scripts/lint-wait-script.sh
bash scripts/test-dependency-install-guard.sh
bash scripts/test-harness-backend-policy.sh
bash scripts/test-worker-command-policy.sh
bash scripts/test-provider-lease.sh
bash scripts/test-spawn-worker-deps.sh
bash scripts/test-orca-wave-lifecycle.sh
bash scripts/test-settle-liveness.sh
bash scripts/test-settle-command.sh
bash scripts/smoke-sentinel.sh
bash scripts/smoke-tmux-worker.sh
bash scripts/smoke-orca-worker.sh
bash scripts/smoke-orca-control-plane.sh
```

`smoke-orca-worker.sh` 验证真实 runtime 检测但不启动 Agent；`smoke-orca-control-plane.sh` 用 fake CLI 验证命令路由、cursor 与 external terminal accounting。只有实际启动 Orca 支持的 Agent 并观察 `worker_done → Delivery → release/精确外部终端结算 → ack`，才能把该 backend 的 supervised 路径标记已验证；其他 backend 不得类推。
