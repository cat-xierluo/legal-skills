---
name: multi-agent-orchestration
description: 编排两个以上边界独立的本地 worker，使用 Orca Run/Task/Dispatch、独立 worktree/session 或 tmux 回退，由 PM 负责拆解、派发、巡检、独立验收、PR 收口与临时资源清理；也用于用户明确要求“并行推进”“多个 worker”“PM 总控”“Wave Autopilot”或防止 PM 直接实现逃逸。不要用于单个短任务、纯状态同步，或仅需 Git 分支、提交、PR、merge 规则的工作。
license: MIT
metadata:
  version: "2.16.3"
  homepage: https://github.com/cat-xierluo/legal-skills
  author: 杨卫薪律师（微信ywxlaw）
---

# Multi-Agent Orchestration

以当前主会话作为 PM，拆解、派工、巡检、验收和收口多个本地 Agent。日常 worktree 与 terminal/session 优先由 Orca 管理；Orca 不可用、用户明确要求或需要复现兼容路径时才使用 tmux。不要把“开了终端”误写成“建立了受监管任务”。

## 1. 适用边界与副作用

使用本 Skill：

- 同时推进两个以上边界独立、可分别验收的本地任务。
- 需要独立 worktree、分支、session、额度 lane 或可人工接管的长任务。
- PM 需要读取 worker 进度、纠偏、等待结构化完成事件并统一收口。
- 用户明确要求 Orca、tmux、独立 session、多个 worker、PM/orchestrator 或 Wave Autopilot。

不要使用：

- 单个短任务、一次性问答或无并行价值的单文件修改。
- 纯任务源、负责人和依赖状态同步：遵循项目任务源规则，不在本 Skill 扩展。
- branch/commit/push/PR/merge/冲突规则：使用 `git-workflow`。
- 宿主不能启动或控制本地 Agent CLI 时：使用宿主自己的 subagent 能力。

本 Skill 可能创建 Git/Orca worktree、分支、Session Context、终端、tmux session，以及 supervised Run/Task/Dispatch。它不自动安装依赖，也不自行扩张 push、merge、发布或外部调度授权。真实 provider 配置及备份不得进入 Git、日志或交付物。

交付成功后，`pm-closeout.sh` 默认清理一次性 worker 的远端 head、worktree 与本地分支；长期功能/集成分支及固定 worktree 必须声明 `long-lived` 并保留。事实未知、身份漂移或生命周期未结算时失败关闭。对已经确认合并、但未走标准 closeout 的单一遗留 worker，可使用 `post-merge-cleanup.sh` 做严格 dry-run/execute 清理；它不替代标准 closeout，也不得用于批量扫描。

## 2. 模式选择

| 模式 | 何时选择 | 完成权威 |
|---|---|---|
| Orca supervised | 用户要求监督、等待结果、DAG、ask/reply 或 decision gate；Agent 可被 Orca 识别 | `worker_done → Delivery`，再由 PM 验收与 settlement |
| Orca terminal-managed | 白名单 backend 未采用 supervised，或 CLI 仅能由外部 terminal 管理 | terminal 输出 + checkpoint + 真实产物，PM 验收 |
| tmux worktree | Orca 不可用、用户指定 tmux 或兼容性回归 | checkpoint + Git/测试/产物，PM 验收 |
| tmux lightweight | 用户明确不要 worktree，或非 Git 目标且目录绝不重叠 | checkpoint + 真实产物，PM 验收 |
| 同宿主 subagent | 窄范围、短任务、无需独立进程或分支 | 宿主决定 |

同一 worker 只能有一个控制模式。terminal-managed 没有 Task/Dispatch，不得要求 `worker_done`；supervised 必须有 live Task/Dispatch，不得用 STATUS、UI 卡片、TUI idle、heartbeat 或 timeout 冒充完成。

## 3. 派发前合同与门禁

### 3.1 先完成任务建模

PM 在任何 worker 副作用前完成：

1. 读取项目规则和完整任务卡，确定目标、非目标、allowed/forbidden files、验证命令与完成条件。
2. 按根因、依赖链和文件范围分组；只有范围正交、验收独立、无共享锁文件/schema/迁移时才并行。
3. 为每个 worker 指定 branch、`branch_lifecycle`、integration target/base、worktree、session、角色、backend/profile/model、provider slot 和资源 owner。
4. 普通 worker 默认为 `ephemeral-worker`；只有项目任务合同明确声明的长期功能/集成基线才使用 `--branch-lifecycle long-lived`。源分支生命周期与合并目标是两个字段，不得混同。
5. 默认每波及全局活跃 worker 不超过 3；PM 待验收交付超过 2 个时停止扩波。项目可以收紧，只有用户明确、限期的探索窗口才可放宽。

Issue 分组读取 `references/12-issue-grouping.md`；并发边界与真实事故读取 `references/10-parallel-lessons.md`。

### 3.2 强制门禁顺序

以下四道门按阶段执行，任一非零退出均不得跳过：

1. **派发价值门**：候选波次采用 `templates/dispatch-value-gate.example.json` 同构合同，运行 `python3 scripts/dispatch-value-gate.py <spec.json>`。只接受 `implementation`、`reusable_verification` 或绑定具名 PR/head 的 `merge_gate`；docs/research/纯调查/纯格式工作不可独立派发。
2. **交付价值后门**：使用同一 spec 运行 `worker-value-postflight.py`，以真实 diff、声明资产、验证命令和 40 位 immutable head 证明交付。
3. **角色分离验收门**：非平凡实现由不同 dispatch/session 的 implementer 与 reviewer 完成，运行 `review-acceptance-gate.py`。自审、head 漂移、纯叙述证据、失败验证或未清 blocker 均拒绝。
4. **失败恢复门**：先用 `acceptance-recovery.py` 分类。`internal_recoverable` 在预算内修复并重新独立审查；`external_dependency`、`safety_unknown` 或预算耗尽才泊车。已具名 PR 的 docs-only 验收修复只能走 `acceptance-repair-gate.py` 的极窄 preflight/postflight 通道。

字段、命令、例外枚举、reviewer 证据预算与恢复语义统一读取 `references/18-dispatch-acceptance-contracts.md`；不要在项目 prompt 或别的脚本另造一套分类表。

### 3.3 运行时安全门

- `spawn-worker.sh` 从完整进程祖先链识别真实 PM harness，并对嵌套层白名单取交集。未知、冲突或不可证明的宿主失败关闭；`--pm-harness` 只做一致性声明，不能提权。
- Claude Code/Codex PM 可派 Claude Code、Codex、CodeBuddy、QoderWork CN；CodeBuddy、QoderWork CN PM 只能派自身。zcode 默认禁用，只有用户明确授权后修改 `config/harness-backend-policy.json` 才可开启。
- worktree 落盘后、任何 terminal/Task/worker-start/任务注入前，必须证明目录、预期分支和 HEAD 一致；Orca repoId 必须与已验证项目一致。失败只清理可精确证明归属的资源，PM 不得借机直接实现业务。
- Worker 只修改 allowed paths。reviewer 默认只可写自身 Session Context；修复被审分支必须显式 `--review-repair-grant <授权来源>`，且任何 `config/*.local.yaml` 都不可写。
- Shell 与安装均 fail-closed。验证命令不等于安装授权；只有精确 `--allow-install-command` 和可审计授权来源才允许安装。内置 `sed` 只放行 `sed -n '<数字或 $>[,<数字或 $>]p' <单文件>`，替换、写入、执行、多文件和其他形式仍需精确 allowlist。
- Node/Make/Python worktree 依赖补偿与默认 verify 注入由 `spawn-worker-deps.sh` 处理；不得让 worker 用安装绕过缺失依赖。具体行为读取 `references/02-runtime-dependencies.md` 与 `references/10-parallel-lessons.md`。

## 4. Orca-first 执行

### 4.1 每个新会话先读取运行时合同

```bash
orca skills get orca-cli
orca skills get orchestration   # supervised / DAG / ask-reply 时
orca status --json
```

以运行中 CLI 的指南和 `--help` 为准。`spawn-worker.sh` 只在当前 `PROJECT_DIR` 可被精确解析为同一 Orca worktree/repo 时进入 Orca；`--no-orca-mode` 显式走 tmux。

### 4.2 Wave 准备屏障

多 worker supervised Wave 必须先一次性写 manifest、创建一个 Run 并预建全部 Task，receipt 成功后才并行启动。不要让并发 spawn 各自创建/重绑 Run，也不要在 `worker-start` 注入任务后再次发送完整 prompt。

```bash
bash scripts/orca-wave-prepare.sh --manifest /tmp/wave.json --receipt /tmp/wave-receipt.json

bash scripts/spawn-worker.sh \
  --project "$PROJECT" --branch feat/worker-a --session worker-a \
  --branch-lifecycle ephemeral-worker --worker-backend claude-code \
  --command "$AGENT_COMMAND" --orca-supervised \
  --orca-run-id "$RUN_ID" --orca-coordinator-handle "$COORDINATOR_HANDLE" \
  --orca-task-id "$TASK_A_ID"
```

完整 manifest、Terminal-managed、Dispatch 自检、cold-start 恢复、settle 与 metadata 合同读取 `references/13-orca-cli-worker.md`。PM 的 read/show/send/wait/reply/release/ack/settle/pr-audit/closeout 命令读取 `references/14-pm-orchestrate.md`。

### 4.3 Worker Prompt 与 Session Context

使用 `templates/worker-prompt.md`，至少写明：任务卡、范围、禁止项、验证命令、完成协议、branch lifecycle、integration target、资源 owner、安装授权和 Git identity。supervised 的 `worker-start` 是唯一任务注入器；长 prompt 可落到 `WORKER_PROMPT.md`，terminal 只发送短 Read 指令。

```text
<worktree>/.claude/agent-sessions/<session>/
├── METADATA.json
├── STATUS.json
├── RESULT.md
├── PATCH_SUMMARY.md
└── WORKER_PROMPT.md
```

字段与 checkpoint 读取 `references/03-checkpoint-files.md`。supervised 中 STATUS 只辅助观察，完成权威仍是 `worker_done → Delivery`。

## 5. 巡检、介入与持续推进

按证据优先级巡检：

1. supervised：Delivery、`worker-show`、`worker-read`。
2. terminal-managed：terminal read + checkpoint。
3. tmux：checkpoint、Git status/log、bounded capture-pane。
4. 所有模式最终检查真实 diff、测试、产物与 PR 状态。

发现偏题、阻塞、越界或验证失败时，优先给原 worker 发送窄纠偏；需要独立审阅时另派 reviewer。运行时活性与业务进展必须分开判断：输出/cursor/CPU 前进只证明活性，文件、commit、测试和产物才证明业务进展。观察不确定时不得自动 Esc、Ctrl+C、stop、release 或按进程名批量 kill。

Wave Autopilot 只有用户明确授权并在项目任务源固定策略后才启用。L1 当前会话推进读取 `references/15-wave-autopilot.md`；跨会话 L2 controller 与尚未实现的 L3 scheduler 边界读取 `references/16-autopilot-durability.md`。不要把 session cron、Markdown 任务源或 provider lease 单独描述成持久控制器。

## 6. 验收、Git 交付与资源收口

PM 依次完成：

1. 读取完整 Delivery、实际 diff 和 worker 证据；运行与产物类型匹配的验证。GUI/Web/桌面变化必须启动真实入口做代表性交互。
2. 核对 allowed files、敏感文件、安装授权、Git identity、commit/head、PR 范围，以及任务启动的服务/端口/子进程已按 owner 收口。
3. supervised worker 先 reuse/release/retain，再 ack；仍存活但漏发完成时先结构化提醒，确认已死才使用 `settle`。
4. 用户或项目已授权 Git 外部写入时，使用 `pm-closeout.sh` 的 PR-first 流程。PR 唯一性、冻结 head/diff/check/review、两阶段 mutation receipt、Monorepo integration path 与结果不确定恢复统一以 `references/14-pm-orchestrate.md` 为准。
5. 交付确认后立即取得资源终态；不得把清理留给 PM 记忆。

```bash
bash scripts/pm-cleanup-worker.sh \
  --project "$PROJECT" --worktree "$WT" --branch feat/worker-a --session worker-a \
  --branch-lifecycle ephemeral-worker --integration-target integration/feature-a \
  --pr "$PR" --expected-tip "$WORKER_TIP" \
  --delivery-mode remote-pr --delivery-commit "$MERGE_COMMIT"
# 手工接管时先预览，再以同一精确参数加 --execute；pm-closeout 成功路径默认自动执行。
```

清理必须区分源分支生命周期与合并目标：

- `ephemeral-worker`：只有 exact PR head/base、expected tip、delivery commit、干净 worktree 和 settled lifecycle 全部一致时才清理。
- `long-lived`，或源分支等于 integration target：保留远端 ref、本地 ref 与固定 worktree，输出 `RETAINED_WITH_REASON reason=long-lived-branch`。
- 调用参数不得把 metadata 的 `long-lived` 降级；短 Worker 合入长期分支时只清理 Worker head，绝不清理 integration target。
- 结果只允许 `CLEANED`、`RETAINED_WITH_REASON`、`CLEANUP_PENDING`。交付已确认后，清理失败作为独立债务继续处理，不重跑 push/merge；隐去 `CLEANUP_PENDING` 后声称完全闭环属于 Hard Fail。

Git 生命周期与批量 stale 分支清理由 `git-workflow` Skill 的“分支清理”入口负责；该 Skill 会按需加载自己的清理 reference。

## 7. Backend、额度与依赖

默认优先与 PM 同宿主，只有额度、模型能力或用户明确要求时跨工具。个人偏好写入 ignored 的 `config/orchestration-personal.json`，项目策略写入 `.claude/orchestration.config.json`；个人配置只能在 harness 白名单内选择 backend。

启用 `quota_aware_routing` 时，派单前必须用新鲜 summary 运行 `route_suggest.py`；summary 缺失、过期、lane 低于判停线、provider 不健康或未映射时，`quota_preflight.py` 在任何副作用前拒绝。显式 override 必须携带授权来源并写入 receipt。额度只为已经通过价值门的任务选路，不能生成 quota-burn 工作。模型与 lane 判断读取 `references/01-model-selection-matrix.md` 和 `references/17-model-capability-profile.md`。

系统依赖：Bash 4+、Git、jq、Python 3；PR 审计/收口需要 `gh`；tmux 仅回退路径需要；Orca 路径需要运行中的 Orca runtime 与版本匹配 CLI。按 backend 还需对应本地 CLI。检查命令：

```bash
bash scripts/check-dependencies.sh --backend claude-code --backend codex --check-gh
```

## 8. 按需读取地图

| 当前问题 | 读取 |
|---|---|
| 模型、provider、执行模式 | `references/01-model-selection-matrix.md`、`references/17-model-capability-profile.md` |
| 依赖、checkpoint、Sentinel | `references/02-runtime-dependencies.md`、`03-checkpoint-files.md`、`04-sentinel-design.md` |
| 法律任务拆分、Issue 分组、并发事故 | `references/05-legal-domain-patterns.md`、`10-parallel-lessons.md`、`12-issue-grouping.md` |
| Agent Teams 排障、CLI backend | `references/06-agent-cli-reference.md`—`11-agent-teams-troubleshooting.md` 中对应 backend |
| Orca worker 与 PM 操作 | `references/13-orca-cli-worker.md`、`14-pm-orchestrate.md` |
| Autopilot | `references/15-wave-autopilot.md`、`16-autopilot-durability.md` |
| 派发、交付、review 与修复合同 | `references/18-dispatch-acceptance-contracts.md` |
| 修改本 Skill 后的验证 | `references/19-maintainer-validation.md` |

不要一次加载全部 references；只读取当前阶段与 backend 所需的文件。

## 9. Hard Fail

出现以下任一情形，停止派发、接受、合并或清理，并保留可复查证据：

- 用户要求 PM/worker 编排，启动门禁未过而 PM 直接写业务代码。
- worker cwd/worktree/branch/repo/head 与目标不一致，或宿主/backend 身份不可证明。
- 真实 provider settings、Token、备份或其他敏感信息进入 Git、日志或打包件。
- 未授权安装、全局环境写入、raw push、范围外修改，或把 verify 当安装授权。
- supervised worker 无 live Task/Dispatch，或用 STATUS/Sentinel/idle/timeout 代替 `worker_done` 与 settlement。
- 只凭 worker 自报、静态 lint、单次 UI 状态或未绑定 head 的证据声称业务完成。
- 未过派发价值、交付后、角色分离或失败恢复门禁；无授权 reviewer 越界写入，或把 PM 例外交付计为常规交付。
- PR create/push/merge 前未通过唯一性与冻结事实审计，或结果不确定时盲重试 mutation。
- worker 启动的服务/监听器没有 owner 与零净增量证据，或按进程名批量 kill。
- 清理 active/unknown/release pending worker；误删长期分支或 integration target；交付后没有记录三种资源终态之一。

修改本 Skill 后，按 `references/19-maintainer-validation.md` 运行受影响测试和完整回归。只有真实启动受支持 Agent 并观察 `worker_done → Delivery → release/精确外部终端结算 → ack`，才能把该 backend 的 supervised 路径标记为已验证；其他 backend 不得类推。
