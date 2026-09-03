---
name: multi-agent-orchestration
description: 本技能应在用户要求并行推进多个任务、开启多个 worker/agent、使用 Orca Run/Task/Dispatch 或 tmux 独立 session、让 PM 通过 UI/会话转录实时巡检并统一调度 Claude Code、Codex、CodeBuddy、QoderWork 等 CLI，或要求防止 PM 直接实现逃逸时使用；用户授权 Wave Autopilot 后，PM 按项目任务源固定策略自动链式推进波次（组波/派单/验收/合并/泊车）。触发词包括“并行推进”“开多个 worker”“Orca 编排”“supervised worker”“PM 总控”“独立 session”“多 agent 并行”“分派任务”“自动推进”“Wave Autopilot”“自动组波/自动推进波次”。不要用于单个短任务、纯任务状态同步，或 Git 分支/提交/PR/merge 规则。
license: MIT
metadata:
  version: "2.14.2"
  homepage: https://github.com/cat-xierluo/legal-skills
  author: 杨卫薪律师（微信ywxlaw）
---

# Multi-Agent Orchestration

以当前主会话作为 PM，拆解、派工、巡检、验收和收口多个本地 Agent。日常 worktree 与 terminal/session 都优先由 Orca Orchestration 管理；Orca 不可用、用户明确要求或需要复现兼容性路径时才使用纯终端 tmux。不要把“开了终端”误写成“建立了受监管任务”。

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
| Orca terminal-managed | 已配置的 CodeBuddy/QoderWork CN、zcode driver，或五种白名单 backend 的非 supervised 路径 | Worktree + terminal + UI + terminal read/send/wait |
| tmux worktree（兼容回退） | Orca 不可用、用户指定 tmux、或需复现非 Orca 路径 | Git worktree + tmux + checkpoint/Sentinel；不作为高频默认路径 |
| tmux lightweight（兼容回退） | 用户明确不要 worktree，或目标不是 Git 仓且 worker 文件夹互不重叠 | 文件夹 + tmux；无 Git 隔离；不作为高频默认路径 |
| 同宿主 subagent | 窄范围、短任务、无需独立进程/分支 | 宿主决定 |
| Claude Agent Teams/view | Claude Code 做 PM 且项目明确采用其原生团队能力 | 按 Claude 官方会话与 worktree 规则 |

同一 worker 只能有一个控制模式。terminal-managed 没有 Task/Dispatch，不得要求 `worker_done`；supervised 必须有 live preamble 与 Task/Dispatch，不得用终端文本或 STATUS 冒充完成。

## 3. 不变量与启动门禁

PM 在业务实现前完成：

1. 读取项目规则和完整任务卡，确定目标、非目标、allowed/forbidden files、验证命令与完成条件。
2. 按根因、依赖链和文件范围分组；只有改动范围正交、验收独立、无共享锁文件/schema/迁移时才并行。
3. 为每个 worker 指定 branch、worktree、session、backend/profile/model、provider slot 和 Session Context。
4. 启动后验证真实 cwd/worktree/branch/session。Orca create 必须局部绑定到已验证的 `PROJECT_DIR` Git top，返回的 repoId 必须与 current worktree repoId 一致；缺失、畸形或错配在 Session Context/terminal 副作用前失败关闭，并只清理可精确证明归属的资源。门禁失败不得由 PM 静默接管业务实现。
5. 发送完整 worker prompt，确认 checkpoint 或 Orca Dispatch 出现，再进入巡检。

硬约束：

- 先执行 Harness 调用层级门禁。Claude Code/Codex PM 可派发五个已配置 backend；CodeBuddy、QoderWork CN PM 只能派发自身。未知、冲突或无法证明的宿主身份失败关闭。
- PM 默认只做拆解、派工、纠偏、review 和收口；用户明确授权或编排层本身需要修复时才直接修改。
- 每个 worker 只修改自己的允许范围。共享文件、锁文件和全局契约按依赖顺序处理。
- 轻量模式下不同 worker 必须占用互不重叠的文件夹；可能写同一目录时回到 worktree 模式。
- Worker 验证命令不是安装授权。缺工具时报告阻塞，除非 PM 传入精确 `--allow-install-command` 和 `--install-authorization-source`。
- Worker 自报、STATUS、UI 卡片、TUI idle、heartbeat 和 timeout 都不能单独证明业务完成。
- supervised spawn 收尾自检 dispatch 绑定（Task-106；旧发布文案曾误用 Task-076）：worker-start 后主动 `dispatch-show --task` 核对；为空时按 runbook #18 自动三步补绑（无 `--inject` 的 dispatch 建绑定 → 从 preamble 提取真实 ctx id → 单行 terminal send 注入 worker_done/ask 命令形式），SPAWN 输出必须含 `SPAWN_WORKER_DISPATCH_BIND: ok|manual-required`；`manual-required` 不阻断 spawn 但属显式告警，PM 须按同三步手动补绑。
- launch 路径 dispatch 绑定自检同权（Task-107；旧发布文案曾误用 Task-077）：Wave receipt 派单漏 `--orca-supervised` 但传了 `--orca-task-id` 时，terminal 启动后由 launch 分支对预建 Task 执行同一自检+补绑并输出同款 `SPAWN_WORKER_DISPATCH_BIND` 行（实现共用 `orchestration_dispatch_bind_selfcheck`，register/launch 两条路径勿各留一份）；缺 `--orca-run-id` 的残缺组合在任何 terminal 副作用前失败关闭；纯 terminal-managed（无 task）不涉及 dispatch，保持零变化。
- worktree 落盘后、任何 terminal/worker-start/任务注入之前，`spawn-worker.sh` 先跑 isolation pre-gate：非 lightweight 且非 dry-run 时机械判定 worktree 目录存在、`branch --show-current == 预期分支` 且 HEAD 可解析。mismatch（实测：PM 请求复用已有 worktree/branch 时，Orca 自动改用 `-2` 后缀分支建新 worktree）打印 `SPAWN_WORKER_ISOLATION_PREGATE_FAILED` 并 exit 2——此时调用日志里没有任何 terminal create/run-create/task-create/worker-start，Session Context 与 authority receipt 尚未落盘，worktree 保留供 PM 精确清理；不存在"worker 已带任务活跑、spawn 却报失败"的 partial dispatch。final `SPAWN_WORKER_GATE` 只保留 launch 后才能观察的 pane cwd 校验。回归：`scripts/test-spawn-worker-orca.sh` 末尾的 Orca `-2` 后缀 E2E。
- 裸调 worker-start 的冷启动心跳窗口（2026-08-30 实测）：绕过 `spawn-worker.sh` 直接 `worker-start --worktree current --agent claude` 一步起终端时，dispatch 有约 60 秒启动确认窗口，Claude Code 冷启动可能超窗 → `last_failure: "timeout"`、Task 被标 failed，并遗留 title=None 的孤儿终端；该窗口为 Orca runtime 内部行为，本机不可调。对策：优先走 `spawn-worker.sh` 预建 terminal（等 TUI ready）再 `worker-start --terminal` 的两步路径；已裸调失败时复位 Task（`task-update --status ready` 或 register 的 `--reset-failed`）+ 改 `--terminal <现存 agent 终端>` 重试，`terminal close` 清理孤儿；worker-start 返回体的 ready/terminal 字段可能为 None（部分生效），以 `dispatch-show --task` 实际状态为准。

Issue 分组细则读取 `references/12-issue-grouping.md`；并发与真实踩坑读取 `references/10-parallel-lessons.md`。

### 派发价值、验收背压与资源责任

额度和并发只用于路由已经成立的任务，不能生成任务。每个任务必须声明三种 `value_kind` 之一，并回答消费者合同：

- `value_kind`：`implementation`（改变行为的实现/修复）、`reusable_verification`（可复用的确定性测试/fixture/基准/故障注入资产）、`merge_gate`（针对具名 PR/change + 40 位 head 的零 diff 合并/发布决策）三选一；docs/research/纯调查/文案与格式清理不可派；
- `problem_target`：具体问题、模块或 PR，不接受 "look into it" 式占位；
- `decision_or_gate_changed`：产出会改变什么行为或决策，而不是只描述"形成文档"；
- `engineering_assets` / `doc_assets`：声明的非文档工程资产路径与随行文档；`implementation`/`reusable_verification` 必须至少声明一个非文档资产，`merge_gate` 必须为空并改用 `gate_target.pr` + `gate_target.head_sha`（40-hex）；
- `verification_commands`：确定性验证命令；实现与验证资产必填，merge gate 可省略（其证据即 accept/reject 决策）；
- `worker_pr_policy`：`worker_pr`（独立有价值的 worker PR）、`integration_pr`（并入具名集成 PR/branch，必填非占位 `integration_target`）或 `no_worker_pr`（仅 merge_gate）；实现/验证资产二选一，不把 PR 数当目标；
- `value_identity`：必填的波内去重身份；显式重复判 duplicate，同 `value_kind` + 同 `problem_target` 判 subsumed，均拒绝；
- `consumer`、`consume_by`、`expiry`、`observable_acceptance`、`resource_owner`：命名消费者、消费时限、到期处置、可观察验收与资源责任（无外部进程写 `none`）。

`DRAFT` 默认不可派。文档不是独立价值：docs-only、简单调查与纯文案/格式清理不得获得独立 worker/worktree/PR；文档只随同 implementation / reusable_verification / merge decision 的同一有价值变更交付（经 `doc_assets` 声明并过 postflight 实证），或由既有角色在无派发成本下处理。只有命名实现已具备全部非文档输入、且缺少的合同是唯一阻塞时，才创建一次晋级任务。PM 待验收超过自身可处理能力时停止扩波；默认每波/全局活跃 worker ≤3、research/docs ≤1，项目可以收紧，只有用户显式、限期的探索窗口才可放宽。

额度充足时优先增加确定性测试、fixture、基准、故障注入、真实交互/样本验收工具、生成器和独立前向评测。禁止以 quota-burn、PR 数、文档行数或 worker 忙碌度作为目标。详细查表与反模式读取 `references/15-wave-autopilot.md` §5。

派发前把候选波次写成 `templates/dispatch-value-gate.example.json` 同构 JSON（`schema_version: dispatch-value-gate.v2`），并运行 `python3 scripts/dispatch-value-gate.py <spec.json>`；非零退出不得启动 worker。该门禁机械拒绝非 `READY`、合同字段缺失或占位、docs/research kind、无 `value_kind` 的通用调查、纯文档交付计划、占位资产、重复/被包含的价值身份、收敛模式并发超限、待验收 PR >2，以及启动外部资源却没有 owner 的任务；PR 数、行数、token 与 commit 数都不是价值信号。

派发的 worker 交付在验收/合并前必须再过交付后门禁：用同一 spec 运行 `python3 scripts/worker-value-postflight.py --spec <spec.json> --task-id <ID> (--repo <repo> --base <sha> --head <sha> | --diff <patch> --delivery-head <40-hex>) --evidence <evidence.json>`，非零退出不得接 PR。该门禁用 diff 实证：至少一个声明的非文档工程资产真的变更（实际文档路径即使位于声明的工程目录之下也不算工程命中，只能经 `doc_assets` 作为随行文档）、变更路径不超出声明资产（文档可随行但不得是唯一变更）、`verification_commands` 在 evidence 中有 exit 0 执行记录。head 绑定是硬条件：evidence 必须含 40-hex `verified_head`，且等于 Git 模式解析 `--head` 所得的真实 commit（patch 模式等于显式 `--delivery-head`）；`merge_gate` 还要求该 head 等于 `gate_target.head_sha`，零 diff 仅对声明 `merge_gate`（`no_worker_pr` + 具名 PR + 40-hex head）放行，报告必须给出 accept/reject 决策与决策消费者。大 diff、绿色自测或 worker 活跃度不能挽救未消费/不可验证的任务。

### 角色分离验收门禁（非平凡实现波的强制默认）

非平凡实现波（`implementation`/`reusable_verification` 交付）默认实行角色分离收口：实现 worker 与深度 diff 审查 + 行为验证 worker 必须是两个不同 dispatch/session；PM 拥有方向、价值合同、粗粒度巡检、冲突/风险升级、immutable-head 记账与最终收口，在独立证据一致时不重复逐行审查或补丁实现。接受交付/合并前运行：

```bash
python3 scripts/review-acceptance-gate.py <review-acceptance.json>
```

契约见 `templates/review-acceptance.example.json`（`schema_version: review-acceptance-gate.v1`）。机械接受仅当：实现者与审查者的 `dispatch_id`/`session_id` 均非占位且互不相同；`delivery_head` 与 `reviewed_head` 为同一不可变 40-hex commit；审查结论为字面 `ACCEPT`；`verification_evidence` 为非空的 `{command, exit_code}` 记录且全部 exit 0（纯文字叙述证据无效）；`review_consumer` 与 `review_expiry` 已具名；`blocking_findings` 为空。机械拒绝：自审、身份缺失/占位、head 漂移/非 40-hex、纯文字证据、缺验证或验证失败、占位消费者/到期处置、以及 PM 实现/深度审查例外缺少非空枚举理由 + 授权来源。

PM 例外仅在四种枚举情形（`role_exception.reason_code`）允许：`worker_failure`、`conflicting_verdicts`、`security_or_high_risk_evidence`、`control_plane_recovery`，且必须声明 `kind`（`pm_implementation`/`pm_deep_review`）、非空 `reason` 与 `authorized_by`；带例外通过的收口在输出中标记 `ordinary_delivery: false`，永远不得计为常规交付。边界：本门禁验证契约的内部一致性（身份、head、结论、证据、例外文书），让角色分离可执行、可审计，但不声称能 policing 所有行为——身份与例外申报是否真实发生，仍依赖角色纪律与事后审计。

**Reviewer 写范围纪律（v2.14.0）**：reviewer dispatch 默认可写范围只有自身 Session Context（`<worktree>/.claude/agent-sessions/<session>/**`）；需要修复被审分支时，必须由任务合同显式授予——spawn 用 `--role reviewer --review-repair-grant <授权来源>`，无授权却传 `--allow-paths` 直接 fail-closed 拒绝 spawn（不静默收窄）。无论是否授予修复权，`config/*.local.yaml`（安装 Skill 的本地运行配置）对 reviewer 永远不可写。 Enforcement 分两层：`spawn-worker.sh` 在任何副作用前注入 `SCOPE_GUARD_ROLE/SCOPE_GUARD_SESSION_ROOT/SCOPE_GUARD_REVIEW_REPAIR_GRANT` 并把角色写入 METADATA `runtime.role`；`scope-guard.py` 对 reviewer 无授权时只放行 Session Context 前缀，`config/*.local.yaml` 硬拒绝。回归：`scripts/test-reviewer-scope-guard.sh`。

**Reviewer 证据预算（evidence budget）**：reviewer 的证据收集有量纲，不是越多越好。优先级固定为 exact HEAD + diff + 受影响文件——已经拿到被审 commit 的 diff 后，不得再整份重读大型 canonical 文档（只按需读 diff 触及的小节）；外部 CI 查询只在 verdict（accept/reject）依赖该结果时才做。环境/时序类失败最多做一次归因复跑：归因后修复环境再跑属于新验证，不算复跑；仍失败必须具名 `NOT_VERIFIED`（无法验证）或 `REJECT`（证据指向缺陷），不得第三次盲试、不得以推测替代证据。PM 可随时发送 budget stop 截断证据收集，reviewer 收到后按已有证据收敛结论并显式标注未验证部分。该预算只约束证据获取的量，不改变验收语义：与 `--role reviewer` 写范围纪律、独立验收（实现者≠审查者）和 fail-closed 不冲突——预算耗尽不产出"放宽的通过"，只产出具名的 `NOT_VERIFIED`/`REJECT`。

### 验收失败恢复分类（单一机械合同，v2.14.0）

验收失败不得再硬编码「any gate failure => park」。唯一分类权威是 `scripts/acceptance-recovery.py`（`acceptance-recovery.v1`）：`internal_recoverable`（本项目自有资产可修复：PR checks 确定性失败、交付越界、验证证据缺失、review blockers、docs-only 验收修复）、`external_dependency`（配额耗尽、上游不可用、缺用户资产/授权）、`safety_unknown`（事实歧义、身份/head 漂移不可证、安全高风险、runtime 损坏）。表外信号一律 fail-closed 归 `safety_unknown`。决策：internal_recoverable 且修复预算未耗尽时动作必须是 `repair`（首次）或 `re_review`（之后），默认预算 2 次，耗尽才 `park`；external_dependency 与 safety_unknown 立即 `park`。预算按「失败 episode」计数（进入 repair_acceptance 记一次，同一 episode 内重复 reconcile 不重复计数）。autopilot runtime 与 codex-heartbeat-cycle 都从该模块导入同一张表，禁止在别处再写分类分支；回归 `scripts/test-acceptance-recovery.py`。

机器行为（v2.14.0 起）：`autopilot_runtime` 对 `checks == "fail"` 不再无条件 `hard_park`——预算内规划内部动作 `repair_acceptance`（state 保持 RUNNING 不泊车，PM 按 §6 派发修复/独立 re-review），预算耗尽才 `hard_park`（`internal_recoverable` 类）；`checks == "unknown"` 维持 `hard_park`（safety_unknown）。`codex-heartbeat-cycle` 把 `repair_acceptance` 映射为 `decision=review` 且心跳继续；`decision=park`（建议停止心跳）只属于 hard_park（安全不明/外部依赖/预算耗尽）。

### acceptance repair 极窄通道（`acceptance-repair.v1`，docs-only）

dispatch-value-gate.v2 拒绝 docs-only 派发仍然成立；唯一例外是「已具名 PR 的验收只差文档修复」：合同模板 `templates/acceptance-repair.example.json`，派发前 `python3 scripts/acceptance-repair-gate.py preflight --spec <spec.json> --registry <ledger.json>`、交付后 `postflight`（同 spec/registry + evidence + diff 源），非零退出不得派发/接受。合同必须：钉扎既有 `target`（pr + branch + 40-hex head_sha）；`integration_target` 等于 `target.branch`（只能集成回既有 PR 分支，不存在独立文档 PR 的表达字段）；`blockers` 为结构化 `{id, source, detail}` 且 ID 唯一；`file_scope` 全部为文档路径（复用 `is_document_path` 单一语义表），非文档变更属 implementation 价值必须走 v2；具名 `consumer`、时区感知未过期 `expiry`、非空 `verification_commands`、`repair_owner` + registry 台账实现序列化 owner（同 PR 只允许一个活跃 owner，同 (pr, head_sha) 或活跃 blocker 重叠 = 重复修复，机械拒绝）；`re_review` 声明修复 worker 与独立 reviewer 互异身份；`repair_attempts_used` ≥ 2 时拒绝派发（必须按分类合同泊车）。postflight 额外机械拒绝：head 漂移（git 模式要求 delivery head 是 pinned head 的后代且 evidence `verified_head` 一致；patch 模式无法证明谱系，一律拒绝）、范围外/非文档修改、零 diff、blocker 未全部解决或解决声明超出合同、验证命令未 exit 0、owner 不一致。回归：`scripts/test-acceptance-repair-gate.sh`。

### 3.1 Harness 调用层级

| PM 宿主 | 允许派发的 worker backend |
|---|---|
| Claude Code | Claude Code、Codex、CodeBuddy、QoderWork CN |
| Codex | Claude Code、Codex、CodeBuddy、QoderWork CN |
| CodeBuddy | CodeBuddy |
| QoderWork CN | QoderWork CN |

`spawn-worker.sh` 从完整进程祖先链的真实可执行程序识别宿主，对每层 Harness 的白名单取交集，使嵌套调用只能降权、不能借强 CLI 恢复权限；在 Orca 能唯一定位当前 worktree 的 working agent 时再交叉校验。同一 worktree 有多个 working agent 时不拿模糊 Orca 信号覆盖进程证据；若进程也无法证明身份则失败关闭。任务文本、已安装 CLI、个人偏好配置和 `--pm-harness` 都不是授权来源。`--pm-harness` 只能声明预期身份，与检测结果不一致时失败，不能向上提权。权威白名单为 `config/harness-backend-policy.json`，默认拒绝；结果写入 `METADATA.runtime.harness_authority`。

**zcode 默认不在 Claude Code/Codex 的 backend 白名单（v2.11.0 P0-④）**：zcode 的额度 lane 独立、发放规则在服务端，与 Claude/Codex 订阅额度语义不同，默认一律拒绝派发。唯一启用通道是用户明确授权后显式编辑 `config/harness-backend-policy.json` 把 `zcode` 加回对应 host（git diff 可审计）；canonical 映射保留，策略文件是唯一开关，不存在命令行 flag 直通。

声明的 worker backend 还必须与实际启动命令一致。只接受直接启动五种 CLI、受信的 Claude provider wrapper、受信的 zcode worker driver（`zcode-worker-driver.py`，唯一放行的 python 形态），或由 `render-runtime-profile.sh` 生成的受限 batch shell；任意 backend 标签伪装、命令链和不透明 wrapper 在副作用前拒绝。安装守卫降级不能放宽此身份门禁。

### 3.2 worktree 依赖补偿 + 默认 verify 命令（Task-045/046，G31）

`spawn-worker.sh` source `scripts/spawn-worker-deps.sh`，在 worktree 创建后自动补偿依赖 + 注入默认 verify 命令，让 worker 不靠路径巧合也能自验：

- **依赖补偿**（`ensure_worktree_deps`，项目类型感知，读全局 `PROJECT_DIR`/`WORKTREE`）：
  - **Node**：worktree 不在主仓父链（Orca `~/orca/workspaces/` 是独立路径树）且主仓有 `node_modules` → 软链 `worktree/node_modules → 主仓/node_modules`。tmux worktree 本在主仓子树（`.claude/worktrees/`）靠 npm 向上解析（G28），不软链。
  - **Rust**：`~/.cargo` registry 全局共享、worktree `target/` 独立，不补偿。
  - **Python**：venv 含绝对路径、软链会挂，默认不自动补偿；PM 可显式传 `--python-runtime-symlink <主仓 .runtime>`（v2.7 Task-061，badminton-lab Wave 1/2 两轮验证的模式）共享主仓运行时——fail-closed：worktree 已有 `.runtime` 则保留、源解释器缺失或为 0 字节占位（Wave 1 实际出现）拒绝启动、软链失败退出非零；`clean-worktree.sh` 删除前安全 unlink 该软链。
- **默认 verify 命令**（`inject_default_verify_commands`，`write_install_authorization` 前调用）：PM 未传 `--verify-cmd` 时，按 `package.json` scripts 注入 `npm run typecheck/lint/test/test:e2e/build` 到 `VERIFY_COMMANDS` → 进 `allowed_shell` 白名单。`test:e2e` 是 verification-gate 的功能完成线（编译过 ≠ 功能可用，FaroPDF 2026-08-05 QA-02 教训），项目有该 script 就默认注入；无则自动跳过。npm 未注入任何命令时**兜底扫 Makefile**（v2.7 Task-057，badminton-lab Wave 2 事故根因：Make 驱动的 Python 项目零注入，worker 全部 `make` 门禁被 `SHELL_COMMAND_NOT_ALLOWLISTED` 拦截）：解析 `^target:` 目标名，只注入白名单动词 `test / test-* / check / ci / lint` 为 `make <target>`，`.PHONY`/变量赋值/文件目标不匹配；其他门禁目标（如 `security-scan`）PM 显式传 `--verify-cmd`。PM 显式 `--verify-cmd` 优先，不覆盖。

依赖补偿必须失败关闭：目标处已有真实目录就保留，断裂 symlink 或创建 symlink 失败则 `spawn-worker.sh` 退出非零，不能留下一个看似已启动、实际无法验证的 worker。用 `scripts/test-spawn-worker-deps.sh` 覆盖路径类型、默认/显式 verify 和双 worker 并发。

`clean-worktree.sh` 删 worktree 前安全 unlink 该软链（`[ -L ] && rm -f` 无尾斜杠，绝不跟随删主仓 `node_modules`）。install-guard 仍 `deny_by_default` 拦 `npm install/ci/add`，worker 不会误改主仓 `node_modules`。详见 `references/10-parallel-lessons.md` G28/G31。

### 3.3 PM spawn 操作纪律（Task-041~044，Wave-2 实战）

spawn 一个 worker 后，PM 的操作纪律（Wave-2 实战撞坑固化）：

1. **不主动 send 完整 task prompt**（Task-042）：`--orca-supervised` 的 worker 由 `worker-start` 注入 live preamble + TASK（唯一任务注入器，见 §4.4/4.5）。PM spawn 后再 send 完整 prompt 是重复投递，会让 worker 混淆/双重执行。长 prompt 写 `WORKER_PROMPT.md`（Session Context），terminal 只发短 Read 指令触发。
2. **Wave 先建完整控制面，再并行启动**（Task-043/050）：用 `orca-wave-prepare.sh` 一次创建/绑定 Run，并在任何 worker 启动前串行创建全部独立 Task；receipt 固化 `run_id`、`coordinator_handle` 和各 `task_id`。不要重试 `run-create`，也不要让并发 spawn 各自 `run-use/task-create`，否则会触发 consumer fencing 或重复 Task。
3. **supervised worker 不用 pm-monitor/sentinel 判完成**（Task-041）：supervised 完成唯一权威是 `worker_done → Delivery`（`pm-orchestrate show/wait` 读 dispatch + Delivery）。`pm-monitor`（STATUS/commit-stale）和 `sentinel`（tui-idle/timeout）的信号不是 supervised 完成权威——`STATUS=done` ≠ Delivery、tui-idle 只表示可交互不表示完成。supervised 的 PM 只用 `pm-orchestrate show/wait`；pm-monitor/sentinel 是 tmux/terminal-managed 回退路径的辅助观察器，套到 supervised 会误判。
4. **只并行无依赖步骤**（Task-044/050）：spawn 前的独立探查和 receipt 完成后的多个 worker 启动/核验可并行；Run 和全部 Task 的创建属于 Wave 准备屏障，必须先串行完成。依赖链（Task 预建→worker-start、spawn→核验、verify→commit）保持串行。
5. **DEC 编号预分配纪律（2026-08-29 三波撞号教训）**：wave manifest 的每个任务 spec 必须显式其一——「新增 DEC 用预分配号 DEC-XXX」或「禁止新增 DEC（实现类默认，只引用既有合同号）」。合同类按 wave 顺序预分配；实现类漏写会导致 worker 自选号撞车（2026-08-28 三 worker 同选 DEC-066，收口重编号三次+一次误伤）。

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

适用于 CodeBuddy、QoderWork CN、zcode（经 driver 渲染），以及五种白名单 backend 中不采用 supervised 的路径：

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

`orca-wave-prepare.sh` 给每个 Task spec 前置不可省略的 `worker_done` 协议提醒；spec 内的 branch 名一律用**连字符形式**（Orca worktree `--name` 与 spawn 的 `safe_branch` 都会把 `/` 规范成 `-`，spec 写斜杠名会让 worker 隔离门禁误判 blocked——Wave 1 教训，manifest 含 `branch: x/y` 会被 `orca-wave-prepare.sh` fail-closed 拒绝）。`orca-supervised-register.sh` 直接复用 receipt，对 `worker-start` 显式传 `--from`，避免并发 rebinding；被 `task_not_startable` 拒绝时带 `--reset-failed` 可把前任 worker 提问/中止翻成 failed 的 Task 复位 ready 重试一次（Task-060）。单 worker 可不传 receipt，由 helper 创建 Run/Task。`worker-start` 是唯一任务注入器；supervised 路径不得再发送普通 prompt。注册失败保留 receipt 与 terminal 供精确恢复，但整个 spawn 返回非零。`CHANGELOG/DECISIONS/TASKS/AGENTS/ROADMAP` 等 shared context 默认由 PM/维护者单写：worker 只提交任务专属产物与结构化 writeback proposal，PM 验收后串行写回。DEC/Task 编号预分配只分配标识，不授权并行修改共享文档；历史冲突按 `references/16-autopilot-durability.md` 的 fail-closed 恢复边界处理。

手动恢复/重注册时，`orca-supervised-register.sh` 会按精确 worktree/terminal/session 身份自动补写完整 `session.orca.supervised` 路由合同，并输出 `ORCAREG_METADATA_BIND=ok|manual-required`。`manual-required` 表示 worker 已启动但脚本不能唯一证明 METADATA 目标；PM 不得重试启动或把消息误发到 terminal，应按 `references/14-pm-orchestrate.md` 的恢复步骤核对身份并补写。

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

每次 supervised 的 send/wait/reply/release/retain/ack/settle 都先由脚本对当前 PM terminal 执行 `run-use`，并把新 coordinator handle 写回 METADATA；`check` 随后消费已绑定 Run，不携带陈旧 `--run` 路由。`wait` 不自动 ack。timeout/count=0 只是滚动巡检窗口结束，不是失败。Sentinel 不得因 STATUS、idle、heartbeat、question、escalation 或 timeout 执行 stop/release/terminal close。完整契约读取 `references/13-orca-cli-worker.md` 和 `references/14-pm-orchestrate.md`。

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

用户显式授权后，PM 按项目任务源中固定的组波/泊车策略自动链式推进波次：收口后自动写回任务源、查表组下一波并派发，直到泊车条件。**授权与策略权威都在项目上下文**（本 skill 不承载项目授权）；查表查不到合法组合即泊车，这是 Autopilot fail-closed 的根本。验收路径不因自动化放宽：最终树复跑门禁、safe-push、唯一 PR，再按 main 保护规则分流为本地集成或 GitHub merge。每波收口发摘要但不等确认，泊车必须完整报告后停止。

Autopilot 活跃期间**必须挂 recurring cron 看门狗**，并与 Orca 推送、Dispatch 状态轮询三通道并用——推送唤醒实测会丢（worker_done 可延迟数小时不唤醒 PM）；完成判定的权威是 `worker-show` 的 dispatch/worker 状态，不是队列里有没有消息。看门狗每跳清单、验收期确定性缺陷的 fix-worker 派发模式与实测反模式读取 `references/15-wave-autopilot.md`。已由同一 watcher 明确观察到额度受限时，才可用 `scripts/night-watch.sh --terminal <PM终端handle> --model <当前模型> --settings <provider/account 配置权威文件>` 守夜；自动唤醒拒绝可变 setting-sources，并冻结 settings 内容指纹。首次探测即成功、配置/认证/网络/未知错误、超时或 terminal 失败都不会唤醒。真实 PM 终端的 `quota → available → send → PM 被唤醒` 仍标记 `NOT_VERIFIED`，流程见 `references/15-wave-autopilot.md` §8。**守夜/夜间模式（用户触发词："守夜模式/首页模式/过夜模式/晚上继续/N 小时后启动"，2026-08-28 固化）**：用户说出任一触发词时，PM 按双通道方案布防——①**定时形态（用户已知恢复时间，如"3 小时后启动"）**：`nohup caffeinate -dis` 包裹一次性定时器（sleep N 后 `orca terminal send` 注入唤醒文本）脱离 PM/Orca 进程树直接运行；会话侧可选挂一次性 cron 兜底。**零探测零死窗消耗，最经济**。②**探测形态（恢复时间未知）**：保留 session recurring cron 看门狗不删（每跳 turn 活动兼防冻心跳+兜底唤醒，死窗积压跳 token=保险费）+ `nohup caffeinate -dis` 脱离进程树的 night-watch 武装探测。铁律：任何守夜装置不得只活在 Orca/Electron 进程树内（App Nap 屏灭冻结整树，与合盖无关，2026-08-28 实证）；night-watch 在额度仍可用时启动会 exit 11（要求从耗尽态武装），需 exit-11 重试监督循环或确认耗尽后再启动。完整复盘见 references 对应节与 Task-078。

守夜 v2 使用 `scripts/night-revive-timer.sh`；布防参数、双通道自测、双读/游标核活、硬额度与瞬发拥塞分流、`task-list` 完成权威及 `SPAWN_WORKER_DISPATCH_BIND` 巡检全部读取 `references/15-wave-autopilot.md` §4.1，不在入口重复维护。

**持久性边界**：recurring cron 只属于当前 PM 会话的低延迟 fast path。v2.10.0 起，`scripts/autopilot-controller.py` + `scripts/autopilot-facts.py` 提供 `L2 / CROSS_SESSION_RECOVERABLE` controller core：版本化 ledger/WAL、PM lease/fencing、可信只读 facts、幂等 reconcile 与单 mutation tick；项目必须提供固定 manifest 和受信 mutation adapter。真实 Orca/GitHub mutation 端到端与真实断电仍为 `NOT_VERIFIED`。没有外部 durable scheduler 时继续报告 `AUTOPILOT_L3_SCHEDULER_NOT_IMPLEMENTED`；用户要求跨会话接管、无人值守恢复或 soft park 自动恢复时读取 `references/16-autopilot-durability.md`，不得把 L2 controller 包装成 L3。

**外部调度器适配器 `codex-heartbeat-cycle`（v2.13.0）**：Codex App heartbeat 可充当上述外部 durable scheduler，适配器 `scripts/codex-heartbeat-cycle.py` 保证「一次唤醒 = 一次有界循环」——读显式 JSON 请求（钉扎 controller/适配器 path+sha256、repo/project/policy 身份、owner/fencing token），经 `autopilot-controller` CLI（argv 数组、shell=False、有界超时）执行一次 status → reconcile，仅当通过 tick 前闸门（动作 allowlist、待验收反压阈值、配额拒绝、fencing/租约身份一致）时执行至多一次 tick，输出机器 JSON（`decision=wait/review/dispatch/park/complete`、receipt、`future_heartbeat_needed`）。硬边界：不循环、不 sleep、不派生后台进程、不注入 raw 终端输入、不改 TASKS、不按 token 丰度挑任务；不确定的 tick 按不确定上报且绝不重试，tick 后不再发起任何控制器调用；COMPLETE/硬泊车/重复拒绝建议停止心跳。v2.14.0 起适配器不硬编码「任何门禁失败 => park」：控制器的 `repair_acceptance` 内部动作（验收失败经 `acceptance-recovery` 分类为 internal_recoverable 且预算未耗尽）映射为 `decision=review` 且心跳继续；`park` 只属于 hard_park（安全不明/外部依赖/修复预算耗尽）。请求模板 `templates/codex-heartbeat-cycle.example.json`，契约测试 `scripts/test-codex-heartbeat-cycle.py`。
## 5. tmux 兼容回退

先用 `render-runtime-profile.sh` 生成 backend 命令，再由 `spawn-worker.sh` 加 `--no-orca-mode` 启动。spawn 后立即核对 `tmux has-session`、pane cwd 与 Session Context 的 `METADATA.json`；任一不一致都停止派单。

不要 `tmux attach` 阻塞 PM 主循环，也不要无 timeout 等 STATUS。长 prompt 写入 Session Context 的 `WORKER_PROMPT.md`，只向 terminal 发送短 Read 指令。完整后检清单见 `templates/pm-spawn-postflight.md`，已知 tmux 陷阱见 `references/10-parallel-lessons.md`“tmux worker / 扩展模式”。

## 6. Worker Prompt 与 Session Context

使用 `templates/worker-prompt.md`。至少填写：

- Background、Mission、Allowed files、Forbidden files、Non-goals。
- Branch、Worktree、Session Context、Runtime Profile、provider/model。
- Project Skills 的已验证路径；不要让独立 cwd 中的 worker 猜 sibling Skill 位置。
- Verification commands、Execution Authority、安装授权来源。
- STATUS/RESULT/PATCH_SUMMARY 的路径和更新节奏。
- supervised 时由 live preamble 提供 task/dispatch ID；worker 不得猜 ID，完成后只发一次 `worker_done` 并停止新工作。

Worker prompt 必须携带两条共享上下文硬条款（2026-08-30 Wave 1-6 实战：两次合并
覆盖 + 一次误删弹药后固化；`templates/worker-prompt.md` 已同步）：

- 禁止修改共享上下文文档（`docs/TASKS.md`/README/CHANGELOG/DECISIONS 等项目
  共享真值）——交付状态由 PM 验收后统一写回；worker 在分支里写，合并时会覆盖
  PM 真值。需要写回的内容写 Session Context 的 `WRITEBACK_PROPOSAL.md`。
- 禁止删除任何既有 fixture/他人交付物——即使看似与你的任务重叠；疑似重叠时在
  RESULT 里提出，由 PM 裁决。

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

pm-monitor 对 tmux session 的判活是三态，不是二值：`alive` 保持静默；只有控制面查询成功且明确无此 session（`can't find session` / `no server running`）才算可靠 absent、发 `SESSION_GONE`；tmux 命令不在 PATH 或 socket/查询失败一律发 `SESSION_UNKNOWN` + `AGENT_NEEDS_INPUT`（存活不可判定，禁止冒充 dead——Badminton Lab bl112/bl113 存活被误报事故），恢复存活补发 `SESSION_RECOVERED`。同一状态跨轮去重；`check_commit_staleness` 只对确认 alive 的 session 追告警。状态机回归门禁：`bash scripts/test-pm-monitor.sh`（live/absent/查询错误/命令缺失/去重/恢复 7 案例 23 断言，旧折叠实现必红）。

把运行时活性与业务进展分开判断：`worker-read --source auto`/terminal cursor 前进只证明有输出，文件、提交和测试证据才证明业务进展；cursor、CPU 或时间戳静止都不能单独证明假死。来源改变、截断、PID 身份不可证明、quiet 测试、网络等待和 ask/dialog 时降级为 `unknown`。探测默认只读，不自动 Esc/Ctrl+C/stop/release；确认终端停在 idle 且工作未完时，PM 才可显式用 `orca terminal send --terminal <handle> --text "..." --enter` 注入一次短唤醒，并复读 screen/Dispatch 状态。
## 8. 收口

PM 必须：

1. 读取 worker 交付、完整 Delivery 和实际 diff，不采信单句“完成”。`worker-show/dispatch-show` 与 diff/tests 可以证明业务状态，但只读检查不能替代 `worker_done` 或 `settle` 的生命周期结算。
2. 运行与产物类型匹配的验证；GUI/Web/桌面行为要启动真实入口做代表性交互。
3. 核对 allowed files、敏感文件、安装授权、Git identity、commit 和 PR 范围。
4. supervised worker 先 reuse/release/retain，再 ack；不得因为只读检查“看起来完成”而跳过 settlement。worker 仍存活且漏发 `worker_done` 时先结构化提醒；确认已死才走 `settle`。terminal-managed/tmux 按用户意图保留或关闭。
5. 用户或项目已授权 Git 外部写入时，默认按 **PR 先行** 收口：先 safe-push 并创建或接管唯一匹配的 PR，冻结其 base/head/diff/checks 作为审阅边界；PM 验收后再在最新 main 上建立本地集成候选并复跑门禁。Monorepo 不得直接 `git merge` feature 分支，按 `git-workflow` 使用目录级或 squash 集成；main 有保护规则时，本地候选只用于验收，最终仍由 GitHub PR merge。该顺序不自动授予 push/merge/close 权限；Task-097 完成前，现有 `pm-closeout.sh` 仍会在 create 后直接 GitHub merge，选择本地集成时不得调用该一体化路径。详细分流见 `references/14-pm-orchestrate.md` §4。
6. 合并 worker 分支后必须 diff 校验共享文档真值：worker 违规写入 `docs/TASKS.md`
   等共享文档的改动会随合并带回，`git diff <base>...HEAD -- docs/TASKS.md`（及
   CHANGELOG/DECISIONS）逐处核对；发现 worker 版本覆盖 PM 真值时以 main 版本
   为准重写（2026-08-30 Wave 1-6 两次合并覆盖教训）。
7. 在 main/trunk 复跑验证前先刷新依赖与构建（Node 项目 `pnpm install` +
   `pnpm build` 或项目等价命令）：旧 `dist/`/`node_modules` 滞后新 lockfile 会
   造成假失败，把 worker 交付误判为回归。
8. 核对任务声明的 `resource_owner`：对本任务启动的服务/监听端口/子进程验证已退出，项目提供 PID/端口基线时必须证明零净增量。身份不明或仍在监听时停止收口，不得按进程名批量 kill；用户原有服务不属于 worker 清理范围。
9. 清理前先 dry-run：

```bash
bash scripts/clean-worktree.sh --project "$PROJECT" --branch feat/worker-a --session worker-a
# 确认目标、dirty 状态和 Orca terminal accounting 后才加 --execute
```

active、release_pending、release_unknown 或生命周期不明的 supervised worker 一律拒绝删除 worktree。

## 9. Backend 与配置

默认优先与 PM 同宿主，只有额度、模型能力或用户明确要求时跨工具；跨工具仍不得越过 §3.1 的 Harness 白名单。个人偏好写入 ignored 的 `config/orchestration-personal.json`，模板为 `.example.json`；项目 trunk、任务源、验证命令和 provider slots 可写入 `.claude/orchestration.config.json`。个人配置只能选择白名单以内的 backend，不能扩张宿主权限。

`concurrency.per_backend[backend]` 优先于 `concurrency.max_per_provider`。配置有效正整数时，`spawn-worker.sh` 在任何 branch/worktree 副作用前获取原子 provider 租约，启动后绑定实际 tmux session 或 Orca terminal；Sentinel、`pm-orchestrate release` 和 `clean-worktree` 只在资源已结算或关闭时释放。无配置时输出 advisory，不假装机械限额。

不得复制 `.env`、真实 settings、Token、cookie、证书或账号凭证到 worktree/提交。Claude provider 隔离、CodeBuddy、QoderWork CN、zcode、Codex 参数分别读取：

- `references/01-model-selection-matrix.md`
- `references/06-agent-cli-reference.md`
- `references/07-qoderwork-cli-worker.md`
- `references/08-codebuddy-cli-worker.md`
- `references/09-zcode-cli-worker.md`：zcode CLI worker 接入（无 TUI，driver 模式；协议/凭证/额度）

### 9.1 额度感知路由（可选，个人配置启用）

个人配置 `quota_aware_routing.enabled=true` 时，PM 组卡/派单前必跑：

```bash
python3 scripts/route_suggest.py --tier L0|L1|L2|multimodal [--scene ...] [--task-card-path ...]
```

- 输出 JSON 的 `provider` 填入任务卡 / `--api-provider`；`urgency=high` 只表示
  某 lane 窗口临期且余量充足，PM 可从已经通过消费者合同与验收背压的任务中调整路由，不能据此扩张任务源或现场生成 quota-burn 工作。
- 任务卡显式 `provider` 字段永远优先（人工锁定 > 动态路由）。
- `spawn-worker.sh` 在 `--api-provider` 缺省且配置启用时自动兜底调用
  （`ROUTE_SUGGEST_TIER` 传入 tier，缺省 L1）。
- 未配置 / summary 读不到 → `not_configured` / `degraded`，走静态
  `main_force.task_routing`，不 fail、不静默改道。
- 模型能力 × 任务匹配的判断方法见 `references/17-model-capability-profile.md`；
  lanes/tier_policy 在个人配置维护，本 skill 不承载任何具体模型选择。

**额度数据时效规范（派单前硬校验，2026-08-30 实战固化）**：route_suggest 只读
`summary_path` 指向的落盘快照（quota-aware-routing.summary.v1），不会自动刷新；
拿陈旧快照组卡/派单，余量读数会严重失真。PM 操作规程：

1. 派单前必读 route-summary.json 的 `generated_at`：距今超过 `freshness_minutes`
   （默认 30）必须先手动跑 `dump_quota_summary.py`（私有侧产出方脚本）刷新快照，
   再采信 route_suggest 输出；不确定时就先刷一次。
2. route_suggest 输出的 `stale=true` 是硬信号不是装饰：stale 期间禁止据其输出
   组卡/派单，先刷新快照再重新路由。
3. 任一 lane 余量低于 `stop_line_percent`（默认 15）即视为停用：禁止向该 lane
   派新 worker（脚本层该 lane 已判 `available=false`，PM 也不得手工指定 provider
   绕过）。（实战：83% 报 9%，险些向 9% lane 派 2 worker——陈旧快照的余量读数
   不可直接采信）

**spawn-worker 配额预检门（v2.11.0 P0-①，fail-closed）**：启用
`quota_aware_routing` 时，`spawn-worker.sh` 对自动补选与显式 `--api-provider`
的 provider 一律在**任何 worktree/terminal/lease/dispatch 副作用之前**跑
`scripts/quota_preflight.py`：summary 缺失/不可读/过期（超过 `freshness_minutes`）/
lane 低于判停线（判停线为闭界，恰好等于也拒）/lane 不健康/provider 不在配置
lane 内/claude-code 未解析出 provider，全部 exit 3 拒绝，不产生任何副作用。
被拒后确要放行，只有一条显式通道：`--quota-preflight-override <非空授权来源>`
（授权来源写入 METADATA 与 authority receipt 供审计，状态记为
`override:<原拒绝原因>`）；**默认不存在人工锁定直通**。预检结论同时写入
`METADATA.runtime.quota_preflight`。配 `scripts/test-quota-preflight.py`
（19 用例门禁契约）。

**配额停滞恢复交接（v2.11.0 P0-③，quota-park）**：worker 撞判停线/冻结后的
标准恢复入口：

```bash
bash scripts/pm-orchestrate.sh quota-park --worktree <WT> --session <SESSION> \
  --reason "配额停滞，人工确认" [--force]
```

固定顺序：liveness gate（复用 settle 真字段检查；active/不确定时仅 `--force`
可继续，表示 PM 已人工确认配额卡死）→ `worker-stop` 精确 fence+stop 旧
dispatch → 释放 METADATA 记录的 provider lease → METADATA
`.recovery.quota_park` 落 marker。worktree/session/checkpoint 全程保留
（与 settle 的区别：绝不删文件）。任何一步失败立即中止：不释放 lease、不写
marker——**lease 释放永远在 worker-stop 成功之后，任何失败路径都不会出现
"worker 活着 + 额度已放"的双活窗口**。park 完成后同 worktree 重启必须用新
session id（authority receipt 每会话唯一，fail-closed），切 provider 也允许；
两条路都仍要过 spawn-worker 配额预检。配 `scripts/test-pm-orchestrate-handoff.sh`
（正向/反向/故障注入/交接 8 场景）。

## 10. 依赖

### 系统依赖

| 依赖 | 安装方式 |
|---|---|
| `bash` 4+ | macOS: `brew install bash`；Linux: 包管理器安装 |
| `git` | macOS: `xcode-select --install` 或 `brew install git` |
| `jq` | macOS: `brew install jq`；Linux: `sudo apt-get install jq` |
| `gh` | 仅 `pm-closeout.sh` 的 PR 创建/合并需要；macOS: `brew install gh`；Linux: 按 GitHub CLI 官方包安装 |
| `tmux` | 仅 tmux 路径需要；macOS: `brew install tmux` |
| `python3` | 安装门禁和 scope guard 需要 |

Orca 路径需要运行中的 Orca runtime 与版本匹配 CLI，不自动安装。按 backend 还需对应 `claude`、`codex`、`codebuddy`、`qoderclicn` 或 `zcode`（含 `~/.zcode/cli/config.json` 凭证，见 ref 09 §2）。

```bash
bash scripts/check-dependencies.sh --backend claude-code --backend codex --check-gh
```

## 11. 按需 references

- `references/02-runtime-dependencies.md`：运行时依赖与配置复制边界。
- `references/03-checkpoint-files.md`：METADATA/STATUS/RESULT/PATCH_SUMMARY。
- `references/04-sentinel-design.md`：事件驱动唤醒和 timeout 语义。
- `references/05-legal-domain-patterns.md`：法律任务常见拆分。
- `references/10-parallel-lessons.md`：并发、dialog、provider 和历史故障。
- `references/11-agent-teams-troubleshooting.md`：Claude 原生团队/会话排障。
- `references/12-issue-grouping.md`：Issue 分组、依赖链和 PR 粒度。
- `references/13-orca-cli-worker.md`：Orca 双层模型、runtime、Run/Task/Dispatch 和恢复。
- `references/14-pm-orchestrate.md`：PM 三模式统一控制入口。
- `references/15-wave-autopilot.md`：Wave Autopilot 自动推进、三通道监控、看门狗清单与泊车语义。
- `references/16-autopilot-durability.md`：跨会话 L2/L3 控制面、租约/fencing、幂等对账与故障注入合同。
- `references/17-model-capability-profile.md`：额度 lane 的模型能力与任务匹配档案。
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
10. 以额度余额、PR 数或 worker 忙碌度为理由派发没有 `value_kind`、命名消费者/消费时限/可观察验收的任务；或未过 `dispatch-value-gate.py` 派发、未过 `worker-value-postflight.py` 就接受交付/PR。
11. worker/测试启动了服务或监听器，却没有资源 owner、清理证据和 PID/端口零净增量核对；或为清理而按进程名批量 kill。
12. 非平凡实现波未过 `review-acceptance-gate.py` 就接受交付/合并；或 PM 实现/深度审查例外缺枚举 `reason_code`、非空 `reason` 或 `authorized_by`，或把 `ordinary_delivery: false` 的收口计为常规交付。
13. 验收失败未过 `acceptance-recovery.py` 分类就泊车（internal_recoverable 修复预算未耗尽即 park），或在 runtime/heartbeat/文档之外另写「gate failure => park」分类分支。
14. reviewer dispatch 未按 `--role reviewer` 纪律约束写范围：无 `--review-repair-grant` 授权却写自身 Session Context 之外，或写任何 `config/*.local.yaml`；或 docs-only acceptance repair 未过 `acceptance-repair-gate.py` preflight/postflight（缺字段、head 漂移、范围外/非文档修改、未解决 blocker、重复修复、owner 串行冲突任一即拒绝）。

修改本 Skill 后至少运行：

```bash
find scripts -type f -name '*.sh' -print0 | xargs -0 -n1 bash -n
bash scripts/test-spawn-worker-flags.sh
bash scripts/test-spawn-worker-orca.sh
bash scripts/test-pm-quota-stall.sh
python3 scripts/test-quota-preflight.py
bash scripts/test-pm-orchestrate-handoff.sh
bash scripts/test-night-watch.sh
bash scripts/test-spawn-worker-metadata.sh
bash scripts/test-spawn-worker-provider-lease.sh
bash scripts/test-spawn-worker-launch.sh
bash scripts/lint-wait-script.sh
bash scripts/test-dependency-install-guard.sh
bash scripts/test-harness-backend-policy.sh
bash scripts/test-render-runtime-profile.sh
bash scripts/test-worker-command-policy.sh
bash scripts/test-zcode-driver.sh
bash scripts/test-provider-lease.sh
bash scripts/test-spawn-worker-deps.sh
bash scripts/test-dispatch-value-gate.sh
bash scripts/test-worker-value-postflight.sh
bash scripts/test-review-acceptance-gate.sh
bash scripts/test-blocker-recovery.sh
bash scripts/test-orca-wave-lifecycle.sh
bash scripts/test-settle-liveness.sh
bash scripts/test-settle-command.sh
bash scripts/test-recover-unconfigured.sh
bash scripts/test-pm-closeout.sh
python3 scripts/test-autopilot-controller.py
python3 scripts/test-autopilot-facts.py
bash scripts/smoke-sentinel.sh
bash scripts/smoke-tmux-worker.sh
bash scripts/smoke-orca-worker.sh
bash scripts/smoke-orca-control-plane.sh
```

`smoke-orca-worker.sh` 验证真实 runtime 检测但不启动 Agent；`smoke-orca-control-plane.sh` 用 fake CLI 验证命令路由、cursor 与 external terminal accounting。只有实际启动 Orca 支持的 Agent 并观察 `worker_done → Delivery → release/精确外部终端结算 → ack`，才能把该 backend 的 supervised 路径标记已验证；其他 backend 不得类推。
