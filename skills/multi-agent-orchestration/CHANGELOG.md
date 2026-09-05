Warning: truncated output (original token count: 47635)
Total output lines: 1554

# Changelog

## [2.16.4] - 2026-09-05

### 改进

- 移除 `multi-agent-orchestration` 主文档、法律场景 reference 和历史记录中对其他任务协调 Skill 的名称与职责跳转；任务来源只表述为“由项目既有任务源确定”，本 Skill 独立聚焦本地 Worker 执行编排。

## [2.16.3] - 2026-09-05

### 改进

- **主文档按运行阶段收敛**：`SKILL.md` 从候选版 579 行压缩为 208 行，只保留触发边界、模式选择、门禁顺序、最短执行闭环与 Hard Fail；详细派发/交付/review/修复合同迁入 `references/18-dispatch-acceptance-contracts.md`，维护者模块边界与完整回归迁入 `references/19-maintainer-validation.md`。
- **按需加载地图**：将 Orca、Autopilot、backend、验收合同和维护测试映射到明确 reference，避免一个会话默认加载全部历史事故、操作参数和测试矩阵；现有脚本合同、门禁顺序与安全语义不变。

### 技术优化

- `test-dependency-install-guard.sh` 使用临时的禁用额度路由配置，隔离开发者本地 `orchestration-personal.json` 与过期 quota summary，确保 spawn 集成断言检验安装/Shell 门禁本身，而不是被更早的个人配额预检污染。

### 文档完善

- 同步指向 `git-workflow` 的分支生命周期权威文档，明确编排层只负责触发 delivery-bound 清理，Git 层负责一次性/长期分支判定、批量 stale 审计和长期功能线关闭。

### 验证

- 两个 Skill 的 quick validation 与 Git `diff --check` 通过；安全扫描为 0 critical / 0 high；cleanup 37/37、closeout 120/120、dependency guard 67/67、spawn flags 30/30、metadata 21/21 通过。
- Harness Failure Audit 继续保留 5 个既有 hard finding（受精确交付证据约束的远端分支删除通用命中 1 个、旧测试退出码模式 4 个）；Instruction Stability 因缺正式约束追踪合同与签名多轮证据保持 `NOT_VERIFIED`。真实 GitHub/Orca 外部链路继续沿用 v2.16.1 的 `NOT_VERIFIED` 边界，不因文档重构扩大结论。

## [2.16.2] - 2026-09-05

### 修复

- **长期分支误清理保护**：派发新增 `--branch-lifecycle ephemeral-worker|long-lived`，并把生命周期与 `base_ref` 持久化到 Session `METADATA.json`。清理优先读取元数据，调用方不得把 `long-lived` 降级为一次性分支；长期源分支固定保留远端 ref、本地 ref 与 Worktree。
- **合并目标与 Worker head 分离**：`pm-cleanup-worker.sh` 新增 `--integration-target`，要求 GitHub PR `baseRefName` 精确匹配。短 Worker 合入长期功能/集成分支时只删除 Worker head，integration target 永不成为本次清理对象；本地集成交付证明也改查实际远端目标，不再写死 `origin/main`。

### 技术优化

- `test-pm-cleanup-worker.sh` 从 23 扩至 37 项，新增 PR base 错配、保护性升级、长期目标保留、长期源分支三类 Git 资源全保留及生命周期防降级回归；spawn flags 30/30、metadata 21/21、pm-closeout 120/120 全绿。

### 待办事项

- 真实 GitHub 仓库中“短 Worker PR → 长期集成分支 → 自动清理 Worker head”的外部链路仍为 `NOT_VERIFIED`；当前证据来自 fake-gh 与真实临时 Git 仓。
- Skill Lint 安全扫描为 0 critical / 0 high；Harness 静态审查仍因受精确交付证据约束的 `git push --delete` 报通用 `HFA-011`，并命中 4 个本轮未改旧测试的 `HRA-001`，因此不声明全 Skill Harness 已验证，也不以命令变形规避扫描。候选缺少正式约束追踪合同与签名多轮证据，Instruction Stability 继续为 `NOT_VERIFIED`。

## [2.16.1] - 2026-09-05

### 新增

- **验收后自动清理**：新增 `pm-cleanup-worker.sh`，`pm-closeout.sh` 的 `remote-pr` / `local-after-pr` 成功路径默认以冻结 PR/head/tip、delivery commit、worktree 和 Session identity 调用执行；`--keep-branch` 作为显式保留例外。
- **资源终态合同**：统一输出 `CLEANED`、`RETAINED_WITH_REASON`、`CLEANUP_PENDING`。交付 commit 与清理债务分开记账，清理失败不盲重试 merge/push，但不能被静默隐藏为“完全完成”。

### 修复

- **只读 `sed` 被误拦**：Shell fail-closed 门禁补入受限数字范围读取 `sed -n '<range>p' <单文件>`；写入 `w`、执行 `e`、替换、多文件及其他形式仍需精确 allowlist。该报错属于 spawn 授权策略遗漏，不是系统文件权限不足。
- **squash 分支可删性**：远端分支先核 exact tip 与 PR/delivery 事实；worktree 安全移除后，本地分支以 expected tip 为 old-value 精确删 ref，不依赖 `git branch -d` 的可达性，也不使用无条件 `git branch -D`。

### 技术优化

- 新增 `test-pm-cleanup-worker.sh` 23 项，覆盖 dirty/非法 metadata/远端查询失败/PR-head mismatch/未知 PR 状态/dry-run/merged 全清理/open PR 保留远端等路径；dependency guard 67/67 覆盖受限 `sed` 正负例；`test-pm-closeout.sh` 120/120，含默认 cleanup 参数与回执集成断言。

### 待办事项

- 真实 GitHub 仓库的 delivery → 远端分支 → Orca lifecycle/worktree → 本地 ref 全链自动清理仍为 `NOT_VERIFIED`；本次结论只覆盖 throwaway Git 与 fake-gh 确定性证据。
- 全量回归未形成全绿回执：既有 `codex → zcode` policy 与“zcode 默认禁用”的正文/测试冲突；真实 Orca smoke 在 terminal send 失败（其创建的两个精确 terminal 已关闭）。Instruction Stability 仍为 `NOT_VERIFIED`；Skill Lint 对本功能受 exact tip/PR/delivery 约束的远端删除仍给出通用 `HFA-011`，未用命令变形规避扫描。

## [2.16.0] - 2026-09-05

### 新增（post-merge cleanup gate，合并后即时清理）

- **职责单一的 `scripts/post-merge-cleanup.sh`**：PR 确认合并后当场回收一个 worker 分支的 worktree/本地/远端短分支。删除资格真值来自 git-workflow 分支清理规则，全部门禁机械判定、fail-closed：① 分支不是 `main/master/develop`、`--base` 或 `--protected-branch`（名称或 glob，长期集成分支）匹配项；② 存在唯一 `state == MERGED` 的 PR 且其 `headRefOid` 与本地分支 tip 精确一致——squash/rebase merge 的唯一权威证据，head 漂移视为身份不明；③ 无开放 stacked child PR 以该分支为 base（gh 查询失败也拒绝）；④ worktree 无未提交改动；⑤ session 生命周期可证结算——tmux 存活且无 supervised dispatch、terminal accounting 为 active/reclaimable/release_pending/release_unknown/unknown 一律拒绝；⑥ 远端状态必须 `ls-remote` 可验证。门禁不过输出 `POST_MERGE_CLEANUP_DEFERRED: reason=...`（exit 2）保留现场。
- **生命周期顺序执行**：execute 时先经 `clean-worktree.sh --execute --delete-branch`（worker-release → 关 terminal/lease → 删 worktree → 删本地分支），再 `git push origin --delete` 远端短分支（push 报错但 follow-up `ls-remote` 证明远端已删时按并发竞态幂等放行），最后机械零残留验证（本地 ref、worktree 注册与目录、tmux session、远端 ref）；远端删除失败或任一残留以 exit 9 报告，绝不把部分成功冒充完成。执行前复核分支 tip 未移动（TOCTOU）。默认 dry-run 零副作用；即时清理是「已合并且无消费者」对 <24h 规则的显式例外，只处理显式传入的单个分支，不批量扫描。
- **`clean-worktree.sh` 新增 `--force-delete-branch`**：squash/rebase merge 后分支 tip 不可达 main，安全 `git branch -d` 必拒；该开关允许在 `-d` 拒绝后升级 `-D`，仅供持有独立 MERGED+head 证据的调用方（即 post-merge-cleanup.sh 门禁通过后）使用，不带开关时行为不变（拒绝并 exit 2，不再依赖 set -e 的裸失败）。
- **文档同步**：SKILL.md §8 新增 post-merge-cleanup 段并纳入验收测试清单与 `gh` 依赖说明；`references/14-pm-orchestrate.md` §4.4 的「自动清理属于 Task-103」占位替换为实际工具指引。版本 2.15.1 → 2.16.0。

## [2.15.1] - 2026-09-04

### 修复（reauthorize 已结算 task 的 TASK_REUSED 误判，Task-113）

- **有界区分真单活与结算残留**：worker_done outcome=failed 正常结算（task 翻成 failed、Dispatch settled、Delivery release+ack）后跑 `pm-orchestrate reauthorize`，预检打印 task state=failed，但新 terminal 注册返回 `TASK_REUSED`；旧实现（Task-081）把 TASK_REUSED 固定解释为「task 仍 dispatched（单活 fencing）」，回滚新终端并指引 PM「先 settle 再重跑」——task 早已结算，恢复链死循环。现注册返回 TASK_REUSED 时按 Step 0 预检状态三分：`failed/settled`（结算残留）先复核一次 task-list，确认仍是 failed/settled 才 `task-update ready` 并只重试一次注册，成功后照常改路由/关旧终端；`dispatched` 维持原单活 fencing 回滚 + runbook #18 指引零变化；`unknown`/其他状态与「预检 failed/settled → 复核翻回 dispatched」的漂移一律回滚新终端 fail-closed 不复位。身份、coordinator 绑定、terminal ownership、Delivery/settlement、provider lease 与 scope guard 全部未放宽；新终端建立后任何中间失败仍先关新终端、保留旧终端（重复调用不累积终端）。
- **回归门禁扩容**：`test-pm-reauthorize.sh` 9 案例 71 断言 → 14 案例 95 断言。新增 J（failed+settled+TASK_REUSED 复核一致 → 复位重试恢复、零终端泄漏）、J2（settled 状态字串同链路）、K（复位后重试仍 TASK_REUSED → 有界单次重试 + 回滚）、L（预检 failed → 复核翻回 dispatched 漂移 → fail-closed 不复位）、M（unknown + TASK_REUSED → 不猜测不复位）、N（结算恢复链重复调用不累积终端）。fake CLI 新增 `task_reused_once` 模式（仅当 task-update 复位后才放行重试，保证验证「复位 → 重试」因果链）与 `task-status-next` 一次性状态轮换（漂移注入）。红→绿实测：修复前 71 通过 / 24 失败（全部落在 J/J2/K/L/N），修复后 95/95 全绿；`test-pm-orchestrate-handoff.sh` 31/31、`bash -n pm-orchestrate.sh` 通过。
- **文档同步**：`SKILL.md` §4.5 reauthorize 段新增结算残留语义说明。版本 2.15.0 → 2.15.1。

## [2.15.0] - 2026-09-04

### 新增

- **PR 唯一性审计 `pr-audit.v1`**：新增 `scripts/pr-audit.py` 与 `pm-orchestrate.sh pr-audit`。按 canonical repo/Git common dir、base/head ref 与 OID、head repository、真实 diff 指纹相等以及独立 `Task:`/`Agent:` trailer，把 open PR 分为 exact、suspected、unrelated；同 head 错 SHA、元数据相同但 diff 不同、同内容异分支、fork、事实未知和候选截断均失败关闭，stdout 保持单 JSON。
- **PR-first 三态收口**：`pm-closeout.sh` 新增 `local-after-pr`（默认）、`remote-pr`、`validate-only`，以及两阶段显式授权：第一阶段绑定 repo/PR/head/SHA/operation，main mutation 前第二阶段再绑定最终 base/candidate/tree。只读预审发生在任何 push/create 之前，唯一 worker 自建 PR 可直接接管，zero 才允许授权式 push/create；调用方 body 中保留 `Task:`/`Agent:` trailer 会在 mutation 前被拒。

### 修复

- **本地 main 事务边界**：候选改为在 fresh main 隔离 clone 中对冻结 worker patch 做三方应用，不再整文件覆盖 main；从隔离 main 候选 safe-push，远端确认后才快进真实 clean main。scope 冲突、safe-push 失败、错误/dirty/进行中 Git 操作的 main worktree 均保持 main 不变。
- **保护规则与漂移失败关闭**：改读 GitHub branch metadata 的类型化 `.protected` 布尔值，同时覆盖 classic branch protection 与 rulesets；只有明确 `false` 才允许本地 main push，并在最终 push 前再次确认，403/404/畸形/中途翻转都降为非成功 `VALIDATE_ONLY`。最终 main push/GitHub merge 前重跑唯一 PR 审计并复核 base/head/diff/checks/review；远端 mutation 前另拒绝原生 merge queue（留给 Task-070），合并用 `--match-head-commit`，成功还需验证三字段、merge commit 已进入 main、第一父提交等于已审 base 且 tree 等于候选 tree。
- **分布式 commit point 状态**：普通失败（exit 2–8）保持 main 零 mutation；create/merge/push/close 调用开始后若服务端可能已提交但回执、tree 或本地同步不确定，统一 exit 9 输出 `OUTCOME_UNKNOWN`、`REVIEW_REQUIRED` 或 `LOCAL_PENDING`，保留精确 PR/commit 供恢复，禁止把部分成功伪报成普通失败或盲重试。

### 技术优化

- `test-pr-audit.sh` 新增 18 项分类、GHE/凭证脱敏、diff mismatch、101 条截断和稳定错误合同测试；`test-pm-closeout.sh` 扩至 118 项，覆盖原 36 项及 validate-only 零写入、自建 PR 接管、create/same-content race、同文件三方合并/冲突、classic/ruleset/merge-queue 保护分流、保护中途翻转、base TOCTOU、candidate-bound 重授权、post-commit outcome-unknown/local-pending、Git/PR diff 凭证脱敏、scope/pathspec、safe-push 失败、错误 main worktree、可靠 Git operation marker（active rebase 目录拒绝、stale `REBASE_HEAD` 忽略）与最终 PR 集合漂移。

### 待办事项

- 真实 GitHub 非保护仓的 `PR → 隔离 main push → 本地 main 快进 → PR close`，以及保护仓的 `PR → 本地候选 → GitHub merge` 尚未在本次本地环境执行，标记 `NOT_VERIFIED`；确定性 fake-gh/throwaway Git 证据不得替代真实外部验收。

## [2.14.2] - 2026-09-03

### 修复（pm-monitor tmux 判活三态，Task-113）

- **判活误报根因修复**：`pm-monitor.sh` 的 `check_tmux_session` 原来把三种失败折叠进同一个 `! tmux has-session` → dead 分支——① tmux 命令不在 PATH（rc=127，Monitor/受限环境常见）、② tmux 可用但控制面查询失败（socket 不可达 / Permission denied 等）、③ 目标 session 确实不存在。真实事故：Badminton Lab 本轮 `pm-monitor` 把可由 `tmux capture-pane` / `tmux has-session` 证明仍存活的 `bl112-glm53flash`、`bl113-glm53flash` 报为 `SESSION_GONE`。现新增 `tmux_session_state` 分类函数输出三态：`alive`（控制面确认存在）、`absent`（查询成功且明确无此 session：`can't find session` / `no server running`，唯一允许发 `SESSION_GONE` 的状态）、`unknown`（命令缺失或查询失败，存活不可判定）。
- **unknown 不再冒充 dead**：控制面查询异常时输出可机器识别的 `SESSION_UNKNOWN: <session> (branch <branch>) reason=<单行原因>` + `AGENT_NEEDS_INPUT`，PM 据此知道是观察器自身故障而非 worker 死亡；同状态跨轮去重（状态机只在翻转时发事件）；从 absent/unknown 恢复存活补发 `SESSION_RECOVERED` 供撤销告警。`check_commit_staleness` 改为复用同一分类，只对确认 alive 的 session 追提交停滞告警，不用不确定的判活去骚扰可能仍存活的 worker。
- **新增确定性回归门禁 `scripts/test-pm-monitor.sh`**：PATH shim fake tmux（模式/序列驱动，POSIX sh）+ 临时 Git 仓库，7 案例 23 断言覆盖 alive 不误报、可靠 absent 才 SESSION_GONE、socket 查询错误报 UNKNOWN、tmux 命令缺失报 UNKNOWN、同状态 3 轮去重、恢复事件；Case 4/5/6 对旧折叠实现必红（红 13 通过/10 失败 → 修复后 23/23 全绿），零外部依赖、零常驻进程。
- **文档同步**：`SKILL.md` §7 新增 pm-monitor 判活三态说明。版本 2.14.1 → 2.14.2。

## [2.14.1] - 2026-09-03

### 修复

- **Orca worktree 分支错配在任务注入前失败关闭**：`spawn-worker.sh` 在 worktree 落盘后、任何 terminal、Session Context、authority receipt、Task 或 `worker-start` 副作用之前执行 isolation pre-gate，机械核对目录、实际分支与 HEAD。Orca 因同名分支自动创建 `-2` 后缀分支时立即输出 `SPAWN_WORKER_ISOLATION_PREGATE_FAILED` 并退出，保留 worktree 供 PM 精确处置，不再形成“spawn 报失败但 worker 已收到任务”的 partial dispatch。
- **收窄最终门禁职责**：launch 后的 `SPAWN_WORKER_GATE` 只保留必须等 terminal 创建后才能观察的 pane cwd 校验；branch 与 HEAD 身份由前置门禁独占，避免同一不变量在副作用前后产生不一致结论。

### 技术优化

- **新增真实入口回归**：`test-spawn-worker-orca.sh` 用 fake Orca CLI 实际创建 `-2` 后缀 worktree，负例断言零 terminal/run/task/worker-start 调用、零 Session Context 落盘且 worktree 保留；正例断言 worker-start 注入与 supervised METADATA 合同完整。
- **Reviewer 证据预算**：固定 exact HEAD、diff 与受影响文件优先，外部 CI 仅在 verdict 必需时查询；环境或时序失败最多一次归因复跑，之后必须具名 `NOT_VERIFIED` 或 `REJECT`，PM 可发送 budget stop 收敛审查范围。

### 文档完善

- `SKILL.md` 增加 isolation pre-gate 硬约束与 Reviewer 证据预算；`references/10-parallel-lessons.md` 新增 G40 partial dispatch 复盘和 G41 evidence budget 经验。

## [2.14.0] - 2026-09-02

### 修复（验收失败恢复：internal_recoverable 不再被直接泊车）

- **验收失败单一机械分类合同（`acceptance-recovery.v1`）**：新增 `scripts/acceptance-recovery.py`。修复前编排合同把「任何门禁失败」直接映射为泊车——`autopilot_runtime` 对 `checks == "fail"` 无条件 `hard_park`，`codex-heartbeat-cycle` 对 `hard_park` 一律 `decision=park` 且建议停止心跳，内部可恢复的验收失败（本项目自有资产即可修复）因此被错误泊车、波次无谓中断。现唯一分类权威是 `acceptance-recovery.py`：`internal_recoverable`（PR checks 确定性失败/交付越界/验证证据缺失/review blockers/docs-only 验收修复）在修复预算未耗尽时动作必须是 `repair`（首次）或 `re_review`（之后），默认预算 **2 次**，耗尽才 `park`；`external_dependency`（配额/上游/缺用户资产或授权）与 `safety_unknown`（事实歧义/身份或 head 漂移不可证/安全高风险/runtime 损坏）立即 `park`，表外信号 fail-closed 归 `safety_unknown`。修复预算按「失败 episode」计数：进入 repair_acceptance 记一次，同一 episode 内重复 reconcile 不重复计数（修复在途 ≠ 新失败）。`autopilot_runtime` 与 `codex-heartbeat-cycle` 都从该模块导入同一张表，禁止在别处再写分类分支。
- **autopilot runtime 集成**：`checks == "fail"` 经分类后预算内规划新的内部动作 `repair_acceptance`（`INTERNAL_ACTIONS` 新增；state 保持 `RUNNING` 不泊车，item 记 `repair_attempts`，`RUNTIME_ITEM_KEYS` 同步扩键，向后兼容旧状态文件）；预算耗尽才 `hard_park`，且 `_fail_action` 携带 `failure_class`（默认 `safety_unknown`）。`checks == "unknown"` 维持 `hard_park`（safety_unknown）。
- **codex-heartbeat 集成**：适配器 `classify_internal` 新增 `repair_acceptance` → `decision=review` 且 `future_heartbeat_needed=true`（不泊车、心跳继续）；`decision=park`（停止心跳）从此只属于 hard_park（安全不明/外部依赖/修复预算耗尽）。回归测试新增 2 用例（repair_acceptance 两个 episode 均不泊车零 tick；预算耗尽 hard_park 仍泊车停心跳），套件 31→33 用例。
- **docs-only acceptance repair 极窄通道（`acceptance-repair.v1`）**：新增 `scripts/acceptance-repair-gate.py`（preflight/postflight 双门禁）+ `templates/acceptance-repair.example.json`，服务「已具名 PR 的验收只差文档修复」场景，dispatch-value-gate.v2 拒绝 docs-only 的规则不变。机械拒绝清单：缺字段/占位、`target.head_sha` 非 40-hex、`integration_target` ≠ `target.branch`（只能集成回既有 PR 分支，合同不存在独立文档 PR 的表达字段）、blocker 缺失/重复、`file_scope` 含非文档或 traversal 路径、过期、`repair_attempts_used` ≥ 2（必须按分类合同泊车）、re_review 自审、registry 重复修复（同 pr+head_sha 或活跃 blocker 重叠）、owner 串行冲突（同 PR 单活跃 owner）；postflight 另拒 head 漂移（git 模式要求 delivery head 是 pinned head 后代且 evidence `verified_head` 一致，patch 模式无法证明谱系一律拒绝）、范围外/非文档修改、零 diff、blocker 未全部解决或解决声明超出合同、验证命令未 exit 0、owner 不一致。
- **reviewer 写范围纪律（角色分离验收波强制默认）**：`spawn-worker.sh` 新增 `--role implementer|reviewer` 与 `--review-repair-grant <授权来源>`。reviewer 默认可写范围只有自身 Session Context；无授权却传 `--allow-paths` 在任何副作用前 fail-closed 拒绝 spawn（不静默收窄）；`config/*.local.yaml`（安装 Skill 的本地运行配置）对 reviewer 永远不可写，授权也不例外。enforcement 分两层：spawn 在副作用前注入 `SCOPE_GUARD_ROLE/SCOPE_GUARD_SESSION_ROOT/SCOPE_GUARD_REVIEW_REPAIR_GRANT` 并写 METADATA `runtime.role`；`scope-guard.py` 新增 reviewer 层（无授权只放行 Session Context 前缀；config/*.local.yaml 硬拒绝）。非 reviewer 角色行为完全不变（向后兼容）。
- **文档同步**：`SKILL.md` §3 新增「Reviewer 写范围纪律」「验收失败恢复分类」「acceptance repair 极窄通道」三节、§4.6 heartbeat 语义更新、§12 Hard Fail 新增 #13/#14；`references/15-wave-autopilot.md` §6 重写为先分类再处置 + 修复通道 + §6.1 reviewer 写范围，§7 反模式新增两条。版本 2.13.0 → 2.14.0。
- **测试**：新增 `scripts/test-blocker-recovery.sh`（恢复合同统一回归入口）= `test-acceptance-recovery.py`（51 断言：三类分类表、预算语义、表外 fail-closed、module/CLI 同表）+ `test-acceptance-repair-gate.sh`（33 断言：真实临时 Git 仓，preflight 19 + postflight 14 正反例）+ `test-reviewer-scope-guard.sh`（19 断言：hook 层 session-context/配置硬拒绝/授权与向后兼容 + spawn 角色门 fail-closed）。已验证：test-blocker-recovery.sh 全绿（103 断言）、test-codex-heartbeat-cycle.py 33/33、test-dispatch-value-gate.sh 31/31、test-worker-value-postflight.sh 27/27。NOT_VERIFIED（待独立 reviewer 新会话补跑后裁决）：`test-autopilot-controller.py`、`test-spawn-worker-metadata.sh`、`test-spawn-worker-flags.sh`——本 dispatch 的命令授权快照不含这三条，改动对应的运行时回归（`case_v2_acceptance_failure_repairs_before_park` 等）已写入测试文件但未在本会话执行。

## [2.13.0] - 2026-09-02

### 新增

- **Codex 心跳有界循环适配器（`codex-heartbeat-cycle`）**：新增 `scripts/codex-heartbeat-cycle.py`，让 Codex App heartbeat 充当外部调度器驱动既有 L2 autopilot-controller，而不把 L2 包装成常驻 L3——每次心跳被唤醒只执行一次有限循环：读取显式常规文件 JSON 请求（钉扎 controller/适配器 path+sha256、repo/project/policy 身份、owner/fencing token、有界超时），经既有 `autopilot-controller` CLI（argv 数组、shell=False、有界超时、stdin=/dev/null）执行一次 status → reconcile，仅当 reconcile 给出 ready 的外部变更意图且通过 tick 前闸门（动作 allowlist、声明与机械验收反压阈值>2、配额拒绝、待定意图 planned/ready/token 一致、租约身份一致）时执行至多一次 tick，随后输出机器 JSON（`decision=wait/review/dispatch/park/complete`、精确 receipt、`future_heartbeat_needed`、fail-closed 原因）。硬边界：不循环、不 sleep、不派生后台进程、不注入 raw 终端输入、不改 TASKS、不按 token 丰度挑选价值任务；不确定的 tick（超时/非零退出/输出畸形）一律按结果不确定上报且绝不重试，tick 之后不再发起任何控制器调用；COMPLETE/硬泊车/重复拒绝时建议停止心跳。配确定性契约测试 `scripts/test-codex-heartbeat-cycle.py`（31 用例：argv 安全、每次调用至多一次 tick、每个拒绝场景零 tick、有界超时、畸形输出 fail-closed、不确定后零重试零追加调用、示例模板驱动完整循环；零网络零真实 Orca/GitHub 变更）与请求模板 `templates/codex-heartbeat-cycle.example.json`。`SKILL.md` §4.6 同步适配器边界。
- **角色分离验收门禁（`review-acceptance-gate.v1`，fail-closed）**：新增 `scripts/review-acceptance-gate.py`，把 MAO-PM-ROLE-SEPARATION 的角色分工从文字约定变成可执行验收契约——实现 worker 负责非平凡实现，独立 reviewer worker 负责深度 diff 审查与行为验证，PM 只拥有方向、价值合同、粗粒度巡检、冲突/风险升级、immutable-head 记账与最终收口。机械接受仅当：实现者与审查者具备互不相同、非占位的 `dispatch_id`/`session_id` 身份；`delivery_head` 与 `reviewed_head` 为同一不可变 40-hex commit；审查结论为字面 `ACCEPT`；`verification_evidence` 为非空 `{command, exit_code}` 记录且全部 exit 0（纯文字叙述证据拒绝）；`review_consumer`/`review_expiry` 已具名；`blocking_findings` 为空。自审、身份缺失/占位、head 漂移/非 40-hex、纯文字证据、缺验证/验证失败、占位消费者/到期处置一律拒绝。PM 实现/深度审查例外仅在 `worker_failure`、`conflicting_verdicts`、`security_or_high_risk_evidence`、`control_plane_recovery` 四种枚举 `reason_code` 下允许，必须附非空 `reason` 与 `authorized_by`；带例外通过的收口输出 `ordinary_delivery: false`，永远不得计为常规交付。配确定性契约测试 `scripts/test-review-acceptance-gate.sh`（27 用例：正例、例外标记非常规交付、自审/同 dispatch/同 session、head 漂移、verdict 大小写、纯文字证据、失败验证、占位消费/到期、blocking findings、例外文书四反例、schema fail-closed、示例模板自洽断言，成败退出码与机器可读输出均断言）与示例 `templates/review-acceptance.example.json`（过自身门禁）。`SKILL.md` §3 新增「角色分离验收门禁」节（强制默认 + 不声称能 policing 所有行为的边界声明）、§12 Hard Fail #12 与验收命令清单同步。既有 `dispatch-value-gate.py`/`worker-value-postflight.py` 未改动。

## [2.12.2] - 2026-09-01

### 修复（验收纠偏 r3：堵住 docs-only 目录误报）

- **postflight 先分类文档路径再匹配资产**：2.12.1 及之前，`_postflight` 先按声明资产匹配实际变更路径，宽声明（如 `engineering_assets: ["skills/foo"]`）会把其下 docs-only diff（`skills/foo/README.md`）算作工程资产命中而放行，违反"文档不得是唯一变更"的核心规则。现实际文档路径永远无法满足 `matched_engineering_assets`——即使位于声明的工程目录之下，也只能经 `doc_assets` 声明作为随行文档；未在 `doc_assets` 声明的实际文档路径保持 outside-contract。
- **文档路径语义单一来源**：preflight 的 `_is_document_path` 升为公共 `is_document_path`（扩展名 + `docs/` 目录同一张表），postflight 通过加载 gate 模块复用同一 helper，不再各自维护扩展名清单，防止两门禁语义漂移。
- 新增 3 条确定性回归（宽工程目录 + README-only diff 拒绝；宽目录 + 真实源码 + 已声明随行 README 通过且命中工程目录；未声明的实际文档路径保持 outside-contract），postflight 矩阵 23→27，preflight 31 用例不变，全绿。

## [2.12.1] - 2026-09-01

### 修复（验收纠偏 r2）

- **`value_identity` 改为机械必填**：2.12.0 文档声明去重身份但代码允许缺失；现缺失/占位一律拒绝，新增缺失与占位两条回归。
- **postflight head 绑定（真 Git revision binding，测试实证）**：2.12.0 的 CHANGELOG 曾写"`verified_head` 与 `gate_target.head_sha` 漂移拒绝"，属超前表述——该版 evidence 缺 `verified_head` 仍可通过，且 merge gate 正例比较的是 `BASE..BASE`。本版起：每个被接受的 postflight 都必须含 40-hex `verified_head`；Git 模式用 `git rev-parse --verify <head>^{commit}` 解析 `--head` 并要求 evidence 一致；patch 模式新增显式 `--delivery-head <40-hex>`（缺失/非 40-hex 拒绝）作为投递修订绑定；`merge_gate` 额外要求解析/evidence head 等于 `gate_target.head_sha`，正例改为 pinned target 自比（`HEAD..HEAD`）。新增缺失 head、stale evidence head、git head ≠ merge target、缺 `--delivery-head`、非 40-hex delivery head 五条负回归。
- **新增 `integration_pr` 派发政策**：2.12.0 强制所有实现/验证资产走独立 `worker_pr`，助长 PR 数膨胀。现实现/可复用验证资产可选 `worker_pr` 或 `integration_pr`，选后者必填非占位 `integration_target`（具名集成 PR/branch）；merge_gate 仍仅 `no_worker_pr`。示例模板的实现任务改为 `integration_pr` + `integration_target` 演示具名集成消费。
- **移除 SKILL.md docs-only 矛盾表述**：原文先说 docs/research 不可派、随后又允许 docs-only 换取状态迁移，现统一为：文档只随同 implementation / reusable_verification / merge decision 的同一有价值变更交付（`doc_assets` 声明 + postflight 实证），docs-only/简单调查/纯文案清理不得获得独立 worker/worktree/PR。
- 测试矩阵：preflight 31 用例、postflight 23 场景（临时真实 Git 仓）全绿，成败退出码与机器可读输出均断言。

## [2.12.0] - 2026-09-01

### 新增

- **派发价值合同 v2（`dispatch-value-gate.v2`，fail-closed preflight）**：`dispatch-value-gate.py` 现要求每个任务机械声明三种 `value_kind` 之一——`implementation`（改变行为的实现/修复）、`reusable_verification`（可复用确定性测试/fixture/基准/故障注入资产）、`merge_gate`（具名 PR/change + 40-hex head 的零 diff 合并决策）——并补齐 `problem_target`、`engineering_assets`/`doc_assets`、`verification_commands`、`worker_pr_policy`（仅 merge_gate 允许 `no_worker_pr`）、`gate_target`（`pr` + 40-hex `head_sha`）与波内去重身份 `value_identity`（显式重复判 duplicate，同 `value_kind`+同 `problem_target` 判 subsumed）。docs/research kind、无 `value_kind` 的通用调查、纯文档交付计划、占位资产一律拒绝；六字段消费者合同（consumer/decision_or_gate_changed/consume_by/expiry/observable_acceptance/resource_owner）与 explore/backpressure 门禁保留。行数、token、commit/PR 数不构成价值信号。示例模板改为双任务示例（实现 + merge gate），合同测试重写为 26 用例（含模板自洽性断言）。
- **交付后价值门禁 `worker-value-postflight.py`（新）**：读同一 spec，对 `--repo/--base/--head` 或 `--diff` patch 实证交付——至少一个声明的非文档工程资产真实变更、变更路径不超出声明资产（文档可随行但不得是唯一变更）、`verification_commands` 在 evidence JSON 中有 exit 0 执行记录；零 diff 仅对声明 `merge_gate` 放行，报告输出 accept/reject 决策与决策消费者。（head/revision 绑定合同由 2.12.1 修正补齐，见该条目。）大 diff、绿色自测或 worker 活跃度不能挽救未消费/不可验证的任务。新增确定性契约测试 `test-worker-value-postflight.sh`（临时真实 Git 仓库，成功/失败退出码与机器可读输出均断言）。`SKILL.md` §3 派发价值节同步两段门禁工作流，§12 验收清单新增 postflight 测试并扩展 Hard Fail #10；`references/15-wave-autopilot.md` §5 六字段文本审查表仍有效，机械合同以本版本与 `templates/dispatch-value-gate.example.json` 为准。

## [2.11.0] - 2026-09-01

### 修复（P0：配额与恢复门禁强化）

- **spawn-worker 配额预检门（P0-①）**：新增 `scripts/quota_preflight.py`（fail-closed 门禁，exit 3=拒绝），`spawn-worker.sh` 对自动补选与显式 `--api-provider` 的 provider 一律在**任何 worktree/terminal/lease/dispatch 副作用之前**预检：summary 缺失/不可读/过期/lane 低于判停线（闭界）/lane 不健康/provider-lane 不匹配/claude-code 未解析出 provider 全部拒绝。绕过通道只有新增显式 flag `--quota-preflight-override <非空授权来源>`（写入 METADATA `runtime.quota_preflight` 与 authority receipt，状态 `override:<原拒绝原因>`）；撤销了默认人工锁定直通。19 用例契约测试 `scripts/test-quota-preflight.py` 全绿。
- **删除 claude-code `--bare` 自动降级（P0-②）**：撤销 v1.20.2 Task-019 的 `CLAUDE_CODE_BARE_AUTO_DEGRADE`——hook 不可证明（`--bare`/`--safe-mode`/`--setting-sources` 排除 local/`CLAUDE_CODE_SIMPLE=1`/缺 claude token）时默认 fail-closed exit 64，不再静默降级 prompt-only（静默放弃机械安装门禁）。唯一降级通道是既有显式可审计的 `--allow-prompt-only-install-guard <授权来源>`（codex/zcode 无 hook backend 的既有要求不变）。`--no-claude-code-bare-auto-degrade` flag 随之移除。
- **修复 renderer hook 契约（P0-② 集成断点收尾）**：P0-② 落地后 `render-runtime-profile.sh` 仍对 claude-code provider env isolation 默认追加 `--bare`，标准 render → spawn 路径被 install-guard fail-closed 拒绝，逼 PM 手工删字符串。现改为：settings/registry 两路默认渲染 hook-capable 命令（无 `--bare`），wrapper、`--setting-sources project,local`、可选 `--no-mcp` 契约不变（GLM 同配置实测无 `--bare` 可正常运行）。bare 能力保留为显式 opt-in renderer flag `--claude-bare`（仅 claude-code provider isolation 路径合法，错用 exit 64），输出上下文 isolation 标签追加 `+bare(degraded/unhooked)` 标记；spawn-worker 仍要求显式 `--allow-prompt-only-install-guard`，不恢复自动降级。新增确定性契约测试 `scripts/test-render-runtime-profile.sh`（33 断言：两路默认无 `--bare`、`--no-mcp` 保留、opt-in degraded/unhooked 标记、错用 fail-closed、标准 render 输出机械提取 spawn-worker `claude_hook_disable_reason` 检查直通、bare opt-in 反向仍被拦截）。
- **pm-orchestrate 新增 `quota-park`（P0-③）**：配额停滞恢复交接命令。固定顺序：liveness gate（active/不确定仅 `--force` 可过）→ `worker-stop` 精确 fence+stop 旧 dispatch → 释放 METADATA 记录的 provider lease（`--resource-settled`，依赖 Orca terminal liveness 证明）→ METADATA `.recovery.quota_park` marker。worktree/session/checkpoint 全程保留；任何失败路径不释放 lease、不写 marker，绝不双活。park 后同 worktree 重启需新 session id（receipt 每会话唯一），切 provider 允许，两者仍受 quota preflight 约束。新增 `scripts/test-pm-orchestrate-handoff.sh`：正向/active 反向/stop 故障/lease 释放故障注入/`--force`/缺 `--reason`/tmux 模式反向/park 后换 session 交接 8 场景 31 断言全绿。
- **zcode 默认不在 Claude Code/Codex backend 白名单（P0-④）**：`config/harness-backend-policy.json` 的 `hosts.claude-code`/`hosts.codex` 移除 `zcode`（额度 lane 独立、语义与订阅额度不同）。唯一启用通道 = 用户明确授权后显式编辑策略文件加回（git diff 可审计）；canonical 映射与命令身份门禁保留。`scripts/test-harness-backend-policy.sh` 同步断言 deny。

## [2.10.3] - 2026-09-02

### 修复

- **Orca 仓库未注册自动收口（Task-111，2026-09-01 custom-skills 实测事故）**：仓库是有效 Git 仓、Orca runtime 健康但 repo 未注册时，`orca worktree current --json` 只返回 `{ok:false,error:{code:"selector_not_found"}}`，Orca 模式被静默降级为 tmux；手工 `orca repo add` 后立即恢复。`scripts/orca-runtime.sh` 的 `orca_runtime_current_project` 现在把失败原因暴露为 `ORCA_WORKTREE_CURRENT_ERROR`（`selector_not_found` / `path_mismatch` / 空=runtime 不可达·非 Git·不可解析），并新增 `orca_runtime_register_current_project`：仅在错误码精确等于 `selector_not_found`、canonical Git toplevel 可解析、`orca status --json` 可达时执行一次 `orca repo add --path <toplevel> --json`，复验 `worktree current` 精确返回该 toplevel + repo 身份才算成功。`scripts/spawn-worker-orca.sh` 的 `detect_orca_mode` 接线：注册失败、合同非 ok 或复验不匹配一律打印诊断后回退既有 tmux 路径（fail-closed，早于 branch/worktree/provider 副作用）；`--dry-run` 只打印 `ORCA_RUN` 计划不执行 mutation。已注册仓库、`--no-orca-mode`、非 Git、runtime 不可达、其他错误码一律不注册；mutation/授权边界（只注册当前这一个 Git 仓库，不触碰其他 Orca 项目）固化到 `references/13-orca-cli-worker.md` §3。

### 技术优化

- 新增 `scripts/test-orca-auto-register.sh`：41 用例确定性 mock 回归（fake orca CLI 经 `ORCA_CLI_COMMAND` 注入，不依赖也不改动真实 Orca 状态），覆盖 success（含 CLI 非零退出仍带错误合同）、already registered、runtime down（无 JSON / status 不可达）、non-Git、wrong error code、repo add failure、post-add path mismatch，以及 `--no-orca-mode` / DRY_RUN / path_mismatch 永不注册。

## [2.10.2] - 2026-08-31

### 改进

- **裸调 worker-start 冷启动窗口坑沉淀（实测 2026-08-30）**：绕过 `spawn-worker.sh` 直接 `worker-start --worktree current --agent claude` 存在约 60 秒启动确认窗口，Claude Code 冷启动超窗 → dispatch timeout、Task failed 并遗留孤儿终端（本机不可调，疑 Orca 对慢冷启动 agent 的兼容问题，可上游反馈）。SKILL.md supervised 经验清单与 `references/13-orca-cli-worker.md` 失败与恢复节新增完整恢复序列（清孤儿 → 复位 Task → `--terminal` 复用重试 → 以 dispatch-show 判读部分生效的返回体），并明确两步路径（spawn-worker.sh 预建 terminal 等 TUI ready 再注册）是该场景的正确入口。

## [2.10.1] - 2026-08-30

### 改进

- **Orca 高频主路径纠偏（Task-110 / DEC-135）**：明确日常 worktree 与 terminal/session 统一优先由 Orca Orchestration 管理；纯终端 tmux 降为 Orca 不可用、用户明确要求或兼容性回归时的回退，不再作为当前优先 spike。
- **PR 先行、本地集成分流**：PM 收口先创建或接管唯一匹配 PR，冻结精确 base/head SHA、diff、checks 与 review，再在最新 main 上建立本地候选并复跑门禁；无保护且获授权时本地集成推入 main，有 branch protection/required checks 时本地只验收、最终仍走 GitHub merge。PR-first 只改变顺序，不扩张 push/merge/close 权限；现有 `pm-closeout.sh` 行为未改，Task-097 完成前选择本地集成必须走手工分段流程。

### 文档完善

- `references/14-pm-orchestrate.md` 新增重复 PR 审计、`LOCAL_INTEGRATE / REMOTE_PR_MERGE / VALIDATE_ONLY` 三态和 Monorepo 禁止直接 feature merge 的边界；明确 Task-097 自动门禁落地前仍需手工审计，不把文档合同误报成脚本能力。
- `references/15-wave-autopilot.md` 同步 PR-first 本地/远端分流并承接守夜 v2 细节；`references/10-parallel-lessons.md` 将早期 tmux 默认结论标为历史阶段，避免旧 reference 反向覆盖 Orca-first 当前规则。`SKILL.md` 入口由 515 行收敛至 490 行。
- Task-097 由 `DRAFT` 升为 `READY` 并补齐范围、非目标、确定性/真实验收；Task-003 降为按需 `DRAFT`，Task-064 保留环境实证轨道。

### 技术优化

- 清除发布目录中的忽略态 `scripts/.DS_Store`；`test-pm-reauthorize.sh` 不再用 `|| true` 吞掉 fake terminal 清单过滤的真实错误，只把 `grep=1`（过滤后为空）作为合法结果，其他退出码保持失败。

## [2.10.0] - 2026-08-30

### 新增

- **Wave Autopilot L2 持久 runtime core（Task-066）**：新增零第三方依赖的 `autopilot-controller.py` / `autopilot_runtime.py`，在 Git common dir 保存版本化 state、write-ahead event、PM lease 与递增 fencing token；提供 `init/acquire/renew/status/reconcile/tick`，每次 tick 最多执行一个通过精确 target、digest、token 和 receipt 绑定的外部 mutation。`status` 保持只读，event→state 与 lease→state 单步崩溃间隙可审计恢复，未来 schema、身份漂移、脏/重复/unknown 事实均失败关闭。
- **可信 facts collector**：新增 `autopilot-facts.py`，将 immutable manifest 与 runtime request 分离；固定可执行文件/配置/证据 digest，只读采集 Orca、Git、GitHub、project 与 provider 事实。Dispatch/PR 动态 ID 只能由 ledger 提供或按 task、branch/base/head 唯一发现，歧义、陈旧 verification/writeback、check/review/head 漂移不得进入 mutation。

### 修复

- **Task-093 正式收口**：PM closeout 冻结 worker base/tip，把 worker 多提交的 Makefile 净补丁精确重放到每一轮最新 `origin/main` 整文件；拒绝 mode/stage/fuzz/三方或语义冲突。main 在验证期间前移会重新合并并重跑同一 argv 门禁，三轮仍移动或验证改变 Git 状态时停止，不进入 push/PR。
- **Autopilot 幂等与接管加固**：已记录 receipt/started intent 在外部事实精确收敛前不会被暂态 observe/hard-park 覆盖；planned intent 接管后重新 fencing/revalidate，facts deadline 过期时先持久化 `ready=false` 并以零 adapter 调用拒绝 tick，必须 fresh reconcile。merge 强制绑定当前 head 的 verification、gate/evidence digest、required checks/approvals，幂等键不包含会波动的实际审批数；mutation adapter 在首个可执行 intent 才按 canonical path + digest 永久封印。
- **恢复探针非法 JSON 失败关闭（Task-109）**：`recover-unconfigured-worker.sh` 不再把 `dispatch-show` / `terminal read` 的命令失败、损坏 JSON 或非法结构折叠成空事实；现在会在 terminal send/worker-start 前输出稳定 `RECOVER_REASON` 与 manual-required。合法无 Dispatch 和空 tail 保持原语义，恢复矩阵 56/56。

### 技术优化

- `test-autopilot-controller.py` 24/24 覆盖双 PM、接管、WAL/lease 崩溃间隙、进程锁、过期计划零调用、七类 mutation 收敛、lost receipt/timeout、adapter 封印、敏感字段拒绝和损坏/漂移失败关闭；`test-autopilot-facts.py` 21/21 覆盖动态 Dispatch/PR 生命周期、多任务子集、只读命令、digest、freshness、歧义与进程组超时；`test-pm-closeout.sh` 36/36 覆盖真实 throwaway Git 冲突与 main 移动。
- 能力边界仍为 `L2 / CROSS_SESSION_RECOVERABLE` controller core。真实 Orca/GitHub mutation adapter 端到端、真实断电后的 fsync/rename 行为继续标记 `NOT_VERIFIED`；Task-067 外部 scheduler 未实现，继续报告 `AUTOPILOT_L3_SCHEDULER_NOT_IMPLEMENTED`。

## [2.9.7] - 2026-08-30

### 修复

- **reauthorize 支持 dispatched 等待态 worker（Wave 10 T3，Task-081）**：原实现只适用 task 已 failed/blocked 的 worker——escalation 等待中（task 仍 dispatched）执行 reauthorize 被 `TASK_REUSED` 拒绝且泄漏 2 个 terminal（2026-08-30 实测）。现新增 Step 0 预检：dispatched 且有未消费 escalation/question 消息时先 reply 消费等待（resume 文本即 reply body）再走既有重授权链；terminal 生命周期防泄漏——新终端建立后任何中间失败（复位/重注册/METADATA 改路由失败）先关新终端保留旧终端，幂等重复调用零累积；TASK_REUSED 硬限制场景输出 runbook #18 manual-recovery 指引 + settle 后重跑选项而非裸拒绝。新增 `test-pm-reauthorize.sh` 55 用例矩阵（dispatched±消息/failed/blocked/completed/幂等/新终端失败回滚），lifecycle 回归 10 用例全绿。

- **route_suggest stale fail-closed（Wave 10 T1）**：额度快照超过 freshness 窗口或缺失 `generated_at` 时不再基于过期 fuel 余量推荐 lane——输出降级 `stale_degraded/degraded` 且 `lane/provider` 为空，新增 `refresh_hint` 指示先刷新 `summary_path` 快照再派单；reservoir lane 保留推荐但 evidence 注明快照过期。spawn-worker route 兜底消费点同步适配非 ok 状态。测试矩阵覆盖 fresh/stale/missing generated_at/no-lanes 四态（22 单测 + 27 shell 测试，PM 合并树复跑通过）。触发事故：2026-08-29 FaroPDF 派单读到 3 小时陈旧快照，报 83% 实际 9%。

### 新增

- **spawn-worker `--deps-mode` 依赖模式选择（Wave 10 T4，G31）**：新增 `auto|symlink|local` 三态（默认 auto 与既有行为完全兼容）。`local`：不软链主仓 node_modules，打印 `SPAWN_WORKER_DEPS_LOCAL` 提示（worker 首验前本地 install，授权走既有 install-guard 通道）；`auto` 智能升级：本次 spawn 显式传 `--allow-install-command`（任务会改依赖）时自动选 local 并打印推断理由。断链 fail-closed 与 Python runtime-symlink 语义零变化。测试 18+27 全绿（PM 合并树复跑，含「显式 symlink 优先于 install 授权推断」用例）。触发事故：2026-08-30 FaroPDF 三连坑——软链拒 pnpm add / vite server.fs.allow 拒软链路径 / vitest 全挂，PM 每次 spawn 后被迫手工重建。
- **`recover-unconfigured-worker.sh` 自动恢复（Wave 10b T5）**：spawn 后 terminal 里 agent 未起（`agent_unconfigured` / no recognized agent 家族，实测约 20% 概率）时，一条命令完成原 PM 手工三步——读 Session Context `METADATA.runtime.command` 重注入启动命令 → TUI 就绪 → 按 Task-092 基建 `register --reset-failed` 重绑 task；全程幂等（重复调用零新 terminal、零重复 register），不可恢复场景（terminal 已死/状态不明）显式 `manual-required` 指引而非静默重试。测试 30 用例四态矩阵（正常/幂等/terminal 死/manual-required）+ lifecycle 回归 10 用例全绿。触发事故：2026-08-30 五个 worker 中两度手工恢复，每次约 10 分钟。

## [2.9.6] - 2026-08-30

### 改进

- **额度转可消费资产（Task-102/108，DEC-133）**：新增派发消费者合同（消费者、改变的决策/门禁、消费期、过期条件、可观察验收、资源 owner）；`DRAFT` 不再自动派 docs-only，额度只在已成立任务之间路由，`urgency=high` 不再允许扩张任务源或制造 quota-burn 工作。
- **验收背压与合理并发**：默认全局/每波 worker ≤3、research/docs ≤1；PM 验收积压时停止扩波，探索窗口必须显式且限期。Autopilot 复盘改报消费者兑现、状态迁移、验收债务和进程净增量，不再用 PR 数或 value/filler 自评分证明价值。
- **外部进程生命周期**：worker prompt 与收口 Hard Fail 增加服务/PID/进程组/端口 owner、端口关闭和零净增量证据；身份不明时失败关闭，禁止按进程名批量 kill 或误清用户既有服务。
- **派发价值机器门禁**：新增零依赖 `dispatch-value-gate.py`、示例 spec 与确定性测试；机械拒绝非 READY、消费者六字段缺失、无状态迁移 docs/research、收敛并发/验收背压超限，以及启动外部资源却无 owner 的派单。worker prompt 将 `consume_by`、`expiry` 和 `observable_acceptance` 拆为独立字段。

## [2.9.5] - 2026-08-30

### 修复

- **手工 register 自动恢复 supervised 路由（Task-092）**：`orca-supervised-register.sh` 在 worker/Dispatch 建立后，按精确 worktree id/path、terminal handle 与唯一 Session Context 自动补写完整 `.session.orca.supervised` 合同；无法唯一证明目标时输出 `ORCAREG_METADATA_BIND=manual-required`，保留活跃 worker 且不重试启动。`smoke-orca-control-plane.sh` 新增完整字段断言，reference 14 固化人工恢复和临时 terminal 活性证据边界。
- **Autopilot 与引用单一权威**：删除互相矛盾的旧 Wave Autopilot 副本，固定 reference 15 为 L1、reference 16 为 L2/L3 durability、reference 17 为模型能力档案；同步修复模板 `references/12-issue-grouping.md` 断链和 SKILL frontmatter 版本漂移。
- **任务/决策编号纠偏**：当前 Task-076/077 分别保留多层并行与 zcode，历史 Dispatch 自动补绑规范号改为 Task-106/107并保留可追溯别名；重复的 settle `DEC-034` 改为唯一 `DEC-130`，新增 DEC-131 固定控制面权威。

### 技术优化

- **Task-093 阶段性交付**：`pm-closeout.sh` 移除 `eval`，门禁改为 argv 执行；safe-push 路径和 Git identity 显式化；PR create/merge/view 错误不再吞掉，临时 body 只创建/传递一次。冲突 resolver 只处理 Git 确认 unmerged 的声明文档并主动 stage，字面冲突标记不再误报；Makefile 行级并集被明确拒绝。`test-pm-closeout.sh` 在 throwaway Git 仓覆盖 20 项错误、成功与真实冲突路径，并纳入 SKILL 验收清单。Makefile 专用「基线整文件 + worker patch 重放」仍未实现，任务保持 `IN_PROGRESS`。

### 文档完善

- 将文末 29 个非规范 `TODO` 状态分诊为 `DRAFT/IN_PROGRESS/DONE`，Task-066 在 durability schema、fencing/mutation 边界和故障注入合同齐备后晋级 `READY`；移除 TASKS 尾部孤立残段。

## [2.9.4] - 2026-08-29

### 修复

- **route_suggest 自动补选不注入 provider env（实测抓出）**：补选只填 API_PROVIDER（lease 计数 + METADATA），worker 仍是裸 `claude` 继承用户全局默认 provider——与 lease 计数的 lane 不一致，且实测 MiniMax 后端对继承配置报 400 modelCode 不存在。现在补选成功且命令为 backend 默认值（用户未显式 `--command`）时，`route_suggest_wrap_command` 用 `claude-provider-env.sh` 自动包装：注入 `config/<provider>.settings.json` 的 env + `--model`（取 settings 的 `env.ANTHROPIC_MODEL`）+ `--permission-mode auto`；settings 缺失/model 解析失败保持裸命令（fail-open 不阻断 spawn）。新增 stderr 标记行 `ROUTE_SUGGEST_ENV`。端到端实测：L0 补选 minimax-M3 → worker 以 MiniMax-M3[1M] 真实完成文件创建任务。
- 测试 16→23 断言（wrap 四场景：注入/显式命令不包装/settings 缺失保持裸命令/非 claude-code 跳过 + 接线顺序断言）；修复 helper 内 `$model（`全角标点在 set -u 下 unbound 的经典坑（memory 已有先例）。


## [2.9.3] - 2026-08-29

### 新增

- **额度感知路由（quota-aware routing）**：PM 派单前按各模型 lane 的余量/窗口倒计时/健康常态评分推荐 provider，替代"任务卡写死 provider"的静态路由。`scripts/route_suggest.py`（python3 零依赖纯决策器）：中立契约 schema `quota-aware-routing.summary.v1`（产出方不限：定时探针/网关/手写均可）、`--tier/--scene/--task-card-path/--config` 参数、退出码约定（ok/locked_by_card/not_configured=0，degraded/all_lanes_stopped=1 供调用方降级）。评分语义：fuel 型 lane 按余量为主分 + 临期（resets_at 倒计时 < urgency_window 且余量高于判停线）加 0-50 分临期权重（urgency=high 提示 PM 扩大该 tier 本波任务量）；reservoir 型（免费/积分、并发敏感）仅 `--scene` 匹配 reservoir_scenes 时入链且并发 cap=1；`resets_at` 早于当前时刻标 pending_refresh 退静态序兜底；燃料 lane 全判停落 tier_policy.default。12 个单测覆盖降级/信号/评分全路径。
- **spawn-worker 集成兜底**：新增 sourced helper `scripts/spawn-worker-route-suggest.sh`（函数 route_suggest_autofill_provider，接线锚点在 provider lease 消费 API_PROVIDER 之前）；`--api-provider` 缺省 + 个人配置 `quota_aware_routing.enabled` 且 backend 为 claude-code 时按 `ROUTE_SUGGEST_TIER`（缺省 L1）自动补选，stderr 输出 `ROUTE_SUGGEST_AUTO` 行；route_suggest 任何失败（not_configured/degraded/崩溃）不改道不 fail，走既有默认链路；显式 `--api-provider` 永远优先（人工锁定 > 动态路由）。16 断言集成测试 + 现有 spawn-worker 系列 6/6 回归通过。
- **个人配置模板 `quota_aware_routing` 段**（`config/orchestration-personal.example.json`）：enabled 默认 false（不配即无感）、summary_path 指向中立 schema v1 余量 JSON、lanes（fuel/reservoir + providers + concurrency_cap）、tier_policy（各 tier 候选链 + default 保底）、reservoir_scenes。模型池快照全在 gitignored 个人配置，skill 代码与文档零具体模型名。
- **`references/17-model-capability-profile.md` 模型能力×任务匹配档案**（2.9.5 统一编号；公开知识层）：六大家族（GLM/MiniMax/DeepSeek/Kimi/Qwen/豆包）画像（档位/强项/弱项/典型任务正反例/部署形态中性描述/当期版本快照+"以你实际可用版本为准"）；fuel/reservoir 两类 lane 派单哲学；填 tier_policy 的五步指引；程序永不读取（纯知识文档，改它对运行时零风险）。
- **SKILL.md §9.1 额度感知路由小节**：派单清单固化 route_suggest 必跑步骤、urgency=high 扩量语义、人工锁定优先、降级路径、能力档案指引。

## [2.9.2.1] - 2026-08-29

- **守夜 v2 实战协议固化**(Task-080):新模板 `scripts/night-revive-timer.sh`(7 参数 fail-closed+`--repeat/--until` 打摆复活+`nohup caffeinate -dis` 脱链)与 `templates/workers.tsv.example`;SKILL.md §4.6 增四铁律(通道自测/双读核活法含游标推进法/硬死vs拥塞诊断树/task-list 完成权威)。
- **§3.3 增第 5 条**:DEC 编号预分配纪律(wave manifest 必须显式预分配号或禁止新增;2026-08-28 三波撞号教训)。

## [2.9.2] - 2026-08-28

### 修复

- **Task-076 自动补绑覆盖正常 spawn 派单路径（Task-077）**：2.9.1 的 dispatch-show 自检+三步自动补绑实现在 `orca-supervised-register.sh`，但 `orca-wave-prepare` receipt 的 launch_contract 只要求传 `--orca-run-id/--orca-task-id/--orca-coordinator-handle` 三件套、未提主旗标 `--orca-supervised`——PM 按此派单时三件套被 spawn 侧静默忽略（仅 `ORCA_SUPERVISED=1` 时消费），worker 走 terminal-managed 启动，Task 停 [ready]、dispatch-show 为空、`SPAWN_WORKER_DISPATCH_BIND` 行不打印，PM 只能手动三步补绑（2026-08-28 Wave 20 双 worker 实测形态）。现在 launch 路径在 terminal 启动完成后，对已传入的 `--orca-task-id` 执行与 register 路径完全相同的自检+补绑并输出同款 DISPATCH_BIND 行；缺 `--orca-run-id` 的残缺组合在任何 terminal 副作用前失败关闭（exit 64）；纯 terminal-managed（无 task）保持零变化。

### 同步

- 自检+三步补绑实现抽为公共函数 `orchestration_dispatch_bind_selfcheck`（`orca-supervised-protocol.sh`），register 路径（`orca-supervised-register.sh`）与 launch 路径（`spawn-worker-launch.sh`）共用同一份，输出合同（ORCAREG_ 前缀 stderr 日志 + KV）不变，杜绝双份漂移。
- launch 补绑成功后向 METADATA 写入与 supervised 分支同款的 `session.orca.supervised` 块（run/task/coordinator/dispatch/bind），并输出 `SPAWN_WORKER_ORCA_PRECREATED_TASK_BOUND` 行；空 dispatch_id 下 pm-orchestrate 仍自动按 terminal-managed 路由，`--with-sentinel` 的 dispatch-id 传递复用 `ORCA_SUPERVISED_DISPATCH_ID`。
- `test-spawn-worker-launch.sh` 新增 5 个 Task-077 用例：健康路径不触发 mutation、dispatch-show 为空自动补绑 ok（含无 `--inject` 与单行注入与 METADATA 契约断言）、补绑失败 manual-required 不阻断、残缺组合副作用前 exit 64、纯 terminal-managed 零 dispatch 调用回归保护。
- SKILL.md §3 硬约束补 launch 路径自检同权一行；frontmatter version 修正为 2.9.2（2.9.0/2.9.1 时漏更）。

## [2.9.1] - 2026-08-27

### 修复

- **spawn 后 Dispatch 绑定静默缺失的自动检测与补绑（Task-076）**：2026-08-27 三波实战（badminton-lab Wave17 bl-011-resume / Wave18 bl-012-contract / Wave19 双 worker）中，`orca-supervised-register.sh` 的 worker-start 成功拉起 TUI 并注入任务，但 Orca 不识别终端内 agent（`agent_unconfigured` / no recognized agent 家族）导致 Dispatch 未绑——Task 停 [ready]、`dispatch-show --task` 为空、worker_done 无通道，此前只能靠 PM 人肉发现并按 runbook #18 三步补绑。现在 worker-start 后主动 `dispatch-show --task` 核对；receipt 与 dispatch-show 均为空时自动执行补绑三步（无 `--inject` 的 dispatch 建绑定 → 从响应/preamble 提取真实 ctx id，多 id 歧义宁拒不猜 → 单行 terminal send 注入 worker_done/ask 精确命令形式，多行文本会在 TUI 提前回车），并以 `ORCAREG_DISPATCH_BIND=ok|manual-required` 汇报；`manual-required` 不再以 exit 1 阻断 spawn（terminal/任务注入已生效），改为显式告警 + WARN 打印手动三步。
- `spawn-worker-launch.sh` 消费绑定结果：SPAWN 输出新增 `SPAWN_WORKER_DISPATCH_BIND: ok|manual-required` 行；METADATA `session.orca.supervised` 新增 `dispatch_bind` 字段，`manual-required` 时仍写入 run/task/coordinator（PM 手动补绑的输入），空 `dispatch_id` 下 pm-orchestrate 自动按 terminal-managed 路由。

### 同步

- SKILL.md §3 硬约束与 §4.6 看门狗各补一行（DISPATCH_BIND 行纳入 spawn receipt/每跳巡检）；`references/13` §10 METADATA 契约示例补 `dispatch_bind` 字段。
- `test-spawn-worker-orca.sh` 新增 4 个 Task-076 用例（`ORCA_CLI_COMMAND` fake CLI 子进程跑 register）：健康路径不触发补绑、dispatch-show 空自动补绑 ok（含无 `--inject` 与单行注入断言）、补绑失败 manual-required 不阻断、绑定成功但注入失败仍 manual-required；`test-spawn-worker-launch.sh` 断言 METADATA 新契约并新增 manual-required 不阻断 + run/task 保留用例。

## [2.9.0] - 2026-08-27

### 新增

- **zcode 成为第五个 worker backend（Task-077 转正，DEC-129）**：ZCode 桌面端内嵌的官方 CLI（GLM 官方 Harness）可作为 worker 派发，消耗 BigModel Coding Plan 额度（与 GUI 同端点同凭证，官方活动期内享渠道加成）。因 zcode 无独立 TUI（`@zcode/tui` 未随桌面端打包），采用 **driver 模式**：新脚本 `scripts/zcode-worker-driver.py` 长驻 `zcode app-server` 子进程（stdio 私有协议，自动应答每 turn 的 `session/requestRuntimePreferences`——15s 窗口超时即 `prompt_failed`），PM `send` 的文本经 `session/send` 进程内注入（零重启纠偏），事件流渲染为可读行供 tmux/Orca 巡检；本地命令 `/status /stop /compact /quit`。
- **身份门禁扩展**：`canonical_harness_backend` 加 `zcode`；`validate-worker-command.py` 新增 trusted-driver 通道（`--trusted-zcode-driver`，唯一放行的 python 形态，realpath 锁定 skill 内脚本）；`harness-backend-policy.json` 的 claude-code/codex 派发集加 zcode（zcode 不做 PM host）。install-guard 走 prompt-only（同 codex，需 `--allow-prompt-only-install-guard`）。
- **render/check-dependencies 支持**：`render-runtime-profile.sh --backend zcode`（interactive=driver、batch=headless `--mode yolo`）；`check-dependencies.sh --backend zcode` 三层检测（PATH/bundle/`~/.zcode/cli/config.json` model+provider，缺失给修复指引）+ `--print-bundle-path zcode`。
- **新测试 `test-zcode-driver.sh`**（8 用例，stub app-server，CI 无需 ZCode.app）：config fail-fast ×2、偏好自动应答、create 派发、stdin→session/send 转发、sessionId 捕获（真实嵌套结构 `result.session.sessionId`）、事件渲染；策略矩阵补 zcode allow/deny（含 codebuddy/qoder PM 派 zcode 拒绝、evil-driver 拒绝）。
- 新文档 `references/09-zcode-cli-worker.md`（协议/凭证链路/限制/实战坑，真机验证记录）；`references/06` 速查表/对比矩阵/tmux 模板补 zcode；SKILL.md 四→五 backend 同步。

### 修复

- driver 时序缺陷（真机端到端暴露）：create 完成前到达的 PM 消息由 queue+drain 缓冲不丢弃；`/quit` 等待 backlog flush（上限 10s）。

### 边界澄清

- **G24 辨析**：G24 及 SKILL §1「ZCode 类非 CLI harness 不做 PM」约束的是 **ZCode GUI 会话扮演 PM**；zcode **CLI 作为 worker backend** 是正交能力，两者并存不矛盾（DEC-129 记录）。


## [2.8.1] - 2026-08-27

### 新增

- 新增 `pm-quota-stall.sh` 与加固后的 `night-watch.sh`（Task-064）：用可移植的有界探针区分 quota、配置、认证、网络、timeout 与未知错误；只有同一 watcher 明确观察到 `quota → available` 才向调用方提供且 show 回执为同一可写 handle 的 terminal 注入一次唤醒。模型与 provider/account settings 权威文件必须显式提供，settings 内容指纹冻结且自动唤醒拒绝可变 setting-sources；首次即 available、所有非额度失败和 terminal show/send 失败均 fail-closed。
- 新增两组确定性回归，覆盖武装状态机、混合错误文本优先级、精确且可写 terminal 身份、settings 内容指纹、探针副作用约束、原子锁、时限与输入门禁。

### 修复

- 修复从符号链接 Skill 目录调用 spawn 时，`orca worktree create` 可能按脚本物理 cwd 绑定到错误仓库的问题（Task-073）：create 现在 scoped 到已验证的 `PROJECT_DIR` Git top，并在任何 Session Context/terminal 副作用前核对 repoId；畸形或错配只精确回滚可证明归属的 worktree/branch，无法证明时保留现场并明确报错。
- 修正 Autopilot 判活合同：运行时活性与业务进展分维度观察；cursor/CPU/时间戳静止不再单独等同假死，探测默认只读且不自动 interrupt/stop/release。

### 技术优化

- Wave manifest、quota JSON 和 Orca create 响应解析全部改为显式 fail-closed，Skill Harness failure audit 降至 0 finding；Harness 回归在“进程身份与同 worktree 另一 working agent 冲突”时验证正确失败关闭，不再把合法冲突环境误报成测试失败；公开参考与 Orca fixture 中的本机绝对用户路径替换为可移植示例路径。

### 验证

- `test-pm-quota-stall.sh` 39/39、`test-night-watch.sh` 31/31、`test-spawn-worker-orca.sh` 41/41 通过；Skill Harness failure audit 0 finding。真实 provider 429、真实 PM terminal 端到端唤醒，以及真实 Orca 中故意制造的破坏性跨仓 create 均未执行并标记 `NOT_VERIFIED`。
## [2.8.0] - 2026-08-26

### 新增

- Wave Autopilot 模式（Task-062，`DEC-125`）：`references/15-wave-autopilot.md` + SKILL.md §4.6。用户显式授权后，PM 按项目任务源固定策略自动链式推进波次直到泊车。核心机制：监控**三通道并用**（Orca 推送 + recurring cron 看门狗 + Dispatch 状态轮询；完成权威是 `worker-show` 的 dispatch/worker 状态而非队列消息——实测 worker_done 推送可延迟 6.6h 不唤醒 PM）；授权与组波/泊车策略权威留在项目上下文，skill 只定义机制与不变量；验收路径不因自动化放宽（最终树门禁复跑 + safe-push + PR squash）；泊车 fail-closed、每波摘要不阻断。含验收期确定性缺陷的 fix-worker 派发模式（新分支名 + `--base-ref origin/<原分支>` 避 worktree 撞车）与 8 条实测反模式清单。来源：badminton-lab Wave 4/5（PR #21—#25）完整生命周期实战。
## [2.7.1] - 2026-08-26

### 改进

- 内部上下文同步：`references/10-parallel-lessons.md` 新增 G39（badminton-lab Wave 4）——同账号多 claude-code worker 的 5 小时限流同时触发；429 打断 turn 后 TUI 停在 idle，`pm-orchestrate send` 投递 Dispatch inbox 叫不醒（`ok:true` ≠ 被消费），须用 `orca terminal send --text ... --enter` 键盘注入唤醒；判活看 `peek` transcript 时间戳与当前的差值而非 tail 文本。SKILL.md §7 增补对应唤醒指引一句。纯文档变更，无脚本改动，全部脚本 `bash -n` 通过。
## [2.7.0] - 2026-08-25

### 新增

- `pm-orchestrate reauthorize` 子命令（Task-058）：spawn 授权快照的运行时刷新一条命令化——合并 `--allow-cmd` 进授权文件、重写 `launch.s…17635 tokens truncated…

### Reason
- 来源：用户明确「Workbody 这个 Agent 的 CLI 只选用 Deepseek V4 Pro 和 Deepseek V4 Flash 两个模型」，并补充「qoderwork-cn 也只调用 Deepseek V4 Pro / Deepseek V4 Flash / Qwen3.7-Max / Qwen3.7-Plus，其中后两个更推荐在晚上 10 点到早上 8 点之间调用，因为会打二折」，「除非我明确要求，尽量不要调用 CodeX」。落地为个人偏好 `backend_model_routing.codebuddy` + `backend_model_routing.qoderwork-cn` + `codex_policy`，并通过 `discount_window` 把折扣时段、`trigger_phrases` 把 CodeX 解封条件显式标注，让 PM 派 worker 时能直接看到「此时段是否用 Qwen 两档最划算」与「CodeX 默认锁死、必须看到原话才解封」。

## [1.17.6] - 2026-07-05

### Added
- **`--add-dir` 透传（codebuddy 跨目录访问）**：`render-runtime-profile.sh` 新增 `--add-dir <dir>` 参数（可重复），codebuddy backend 追加到 `cb_parts`。`spawn-worker.sh` 同步新增 `--add-dir <dir>` 参数，写入 `METADATA.json` 的 `add_dirs` 字段。用途：PM 派 worker 时若任务文件/素材在 worktree 外，`spawn-worker.sh --add-dir /tmp --add-dir ../shared-assets`。
- **`permission_auto()` 兜底 runtime "Do you want to proceed" prompt**：`spawn-worker.sh` 新增 `permission_auto()` 函数，启动 tmux 后轮询 pane 内容（最长 60s，2s 间隔），匹配「Do you want to proceed」文本后自动选 option 2「Yes, and don't ask again for session」（Down+Enter=session-allow）。与 `trust_auto` 共用 `--no-trust-auto` opt-out。只自动选 session-allow，不选 bypass（安全：session-allow 仍记录，且只对当前 session）。

### Fixed
- **runtime "Do you want to proceed" prompt 无自动处理**：上一轮（v1.17.5）的 `trust_auto` 只处理了首启 trust folder dialog，但 codebuddy 读取 worktree 外文件时的「跨目录安全门」是另一层 prompt。PM 派 headless worker 时若任务文件在 worktree 外（如 `/tmp`），worker 会卡在 "Do you want to proceed?" 弹窗。新增 `permission_auto()` 兜底此场景。

### Reason
- 来源：2026-07-05 PM 用 codebuddy worker 实战，即使带了 `-y`，读取 `/tmp` 任务文件时仍弹 "Do you want to proceed" 弹窗。`-y`/`--dangerously-skip-permissions` 跳工具权限，但不覆盖 codebuddy 的「跨目录访问」安全门。官方文档的解是 `--add-dir`（settings 或 CLI flag），而 permission_auto 作为兜底自动选 session-allow。

## [1.17.5] - 2026-07-05

### Fixed
- **codebuddy/qoder 交互式 worker 缺 -y / --dangerously-skip-permissions**（问题 2 运行时部分）：`render-runtime-profile.sh` 的 codebuddy case `-y` 逻辑从「batch 恒加 / 交互式仅显式 --dangerously-skip-permissions」改为「交互式也默认加，仅 --no-skip-permissions opt-out」。qoderwork-cn case 同改为默认加 --dangerously-skip-permissions。理由：spawn-worker.sh 派 tmux session 本质 headless（无人在终端应答 runtime permission prompt），DEC-040 F1/F3 只修了 batch 模式，交互式 gap 还在。
- **codebuddy 首启 trust folder dialog 无自动处理**（问题 1）：`spawn-worker.sh` 新增 trust-auto：启动 tmux 后轮询 pane 内容，匹配 codebuddy trust dialog 文本（Trust folder / Trust folder and all subdirectories），自动选 option 3（Down×3+Enter），避免子目录二次 prompt。提供 `--no-trust-auto` opt-out。
- **codebuddy PATH 检测假阴性**（问题 3 补充）：`check-dependencies.sh` 新增 `--print-bundle-path codebuddy|qoderwork-cn`，直接输出 .app bundle 二进制绝对路径。`spawn-worker.sh --help` 加 Troubleshooting 段，提示用 check-dependencies 多源检测或取绝对路径传给 --command/--bin。

### Reason
- 来源：2026-07-05 PM 用 `spawn-worker.sh --backend codebuddy` 派 worker，连续撞 3 个手动 prompt：首启 trust folder dialog → 子目录访问 dialog → which codebuddy 找不到。CHANGELOG v1.16.6/1.17.1/1.17.2 历史上修过 batch 模式 flag 和 PATH-less 检测，但交互式 headless worker 的自动 -y + trust-auto 两个 gap 一直没补。

## [1.17.4] - 2026-07-03

### Added
- **`scripts/qoderclicn-interactive-spawn.sh`**：长任务（10+ tool call）专用 helper。`qoderclicn` 在 batch `-p` 模式下走 SDK/bare 模式 → GUI 主进程 (pid 65090) 的 HeadlessSession → 1-2s 内 `gemini.exitHeadlessMode` 主动 idle-exit（实测日志 `~/.qoderworkcn/logs/runs/...-p65090/process.exiting ... uptime_ms=1176`）。DEC-042 决策：长任务改走 interactive 模式 + tmux `send-keys` 投递 prompt（**无 `-p`**），实测 5 个 tool call（pwd/date/echo/uname/ls）全跑通 + worker 仍在 `>` ready。Helper 自带：
  - argv-form tmux `new-session` 触发（路径空格不丢）
  - trust-folder 自动 `1 + Enter` 接受（可关：`--no-trust-auto`）
  - TUI ready 检测（看 `Type your message` 或 `>`）
  - prompt 12KB/16KB 分段（`send-keys` / `paste-buffer`）
  - thinking/tool_use 出现确认（60s）

- **references/07 §8 新增「长任务专用 helper」指引**：PM 用法 + helper 适用场景 + 与 batch `-p` 对照。

### Reason
- 来源：2026-07-03 doc-curator-iter Wave 1 W2 中途死的根因诊断。investigator 14 行 A/B 测试定位 F1+F3 (DEC-040) 解决了 batch flag + model key，但 worker 仍 1-2s exit 不进 agent loop；进一步排查确认是 SDK/bare 模式的 HeadlessSession 设计问题，**不是 flag 错**。Reference §6.2 已写明 batch 仅限短任务，但 PM 派 W2 时 10+ tool call 仍走 batch 故踩坑。
- 决策：保留 batch `-p` 作为「短任务兜底」（≤3 tool call），新增 interactive helper 作「长任务 canonical」。`spawn-worker.sh` 后续加 `--mode interactive` 集成（本次仅 helper + 文档）。

## [1.17.3] - 2026-07-03

### Security
- **凭证卫生审查（skill-lint 验收触发）**：`config/*.settings.json`（deepseek / glm / minimax）含真实 API key，虽已被 `.gitignore` 的 `**/config/*.json` 拦住不进 git 追踪（Hard Fail #5 未触发），但真实 live key 明文躺在工作区仍是外带风险。**这三把 key 需在各 provider 后台轮换**（DeepSeek / BigModel-GLM / MiniMax），并确认打包与 ClawHub 同步都尊重 `**/config/*.json` 排除。长期方案：真实 token 只放环境变量，settings 文件留占位。

### Fixed
- **`.gitignore` 补 `**/.claude/agent-sessions/`**：SKILL.md §4.1 要求 agent-sessions 巡检产物不进 commit，但仓库 `.gitignore` 此前无对应规则，`git add -A` 会误提交（含本地绝对路径的 `SENTINEL_OUT.log`）。补规则并删除遗留样例 `.claude/agent-sessions/orch-pref/`。
- **personal.json「不入库」表述统一**：`config/orchestration-personal.json` 与 `.example.json` 的 `_comment`/`_path_user` 原写「随 skill 走，在仓库内」，与 §2.4「gitignore 不入库」矛盾（实际行为是 gitignored）。统一为「在 skill config/ 目录内，但被 .gitignore 排除、不入库」。
- **personal.json 路径一致性**：§3.3 用户级 vs 项目级叠加表原写 `~/.claude/orchestration-personal.json`（旧 home 路径），与 §2.4 现行 `config/orchestration-personal.json` 不一致，已统一为 config/ 路径。
- **§2.4 TODO stale 字段**：`main_force.models` → `main_force.task_routing`（schema 已重命名），`coddex` 拼写 → `codex`。
- **registry example 反混淆注释**：`claude-provider-registry.example.json` 的 `_comment` 原直接给出真实 endpoint 对照（open.bigmodel.cn / api.deepseek.com / api.minimaxi.com），使别名脱敏形同虚设，已删除改为占位说明。
- 清理 `.DS_Store`。

### Reason
- 触发：对本 skill 做 skill-lint 发布前验收，命中 1 个凭证暴露风险 + 4 个文档/元数据一致性问题。凭证按「默认按严重处理」，其余为发布一致性修复。

## [1.17.2] - 2026-07-03

### Fixed
- **codebuddy / qoderclicn batch mode 启动参数（CLI flag 误用导致 Wave 1 worker 出货失败）**：派 Wave 1（`doc-curator-iter-2026-07-03`）实测两个 worker 都立即退出 / 卡住，investigator worker 14 行 A/B 测试定位到 render-runtime-profile.sh 生成命令时 2 个 flag 错配 + 个人配置 1 个 model key 错误：
  - **F1**：codebuddy batch 默认 `--permission-mode acceptEdits` 与 `-y` 冲突，CLI 自己报错要求 `codebuddy -p -y "<prompt>"` 或 `--permission-mode bypassPermissions`。改为 batch 默认 `bypassPermissions`（交互式不动）。
  - **F3**：qoderclicn batch 模式必须显式 `--dangerously-skip-permissions`（`--permission-mode auto` 在 headless 不 bypass）。自动加在 `MODE=batch` 路径里（`SKIP_PERMISSIONS=1` 已存在的语义不变）。
  - **F2**：`config/orchestration-personal.json` `backend_model_routing.qoderclicn.default_models` 把 `qoder-3.7MAX` / `qoder-3.7PLUS`（CLI 不接受）换成 `[qmodel_latest, qmodel]`（CLI 1.0.34 实证可用 key 之一）。`tier_note` 同步标注实际对应 `Qwen3.7-Max` / `Qwen3.7-Plus`。
- **诊断先于修复**（meta 流程）：用 investigator worker 14 行 A/B 测试（A/B 改 1-2 个 flag 看哪个 fix pass）+ `/tmp/cli-diagnostic-report.md` 沉淀证据 + CLI 实测拒绝消息。最小 3 行改 + 单 commit，不直接凭印象 patch。

### Reason
- 触发：本次 Wave 1 派发失败时 PM 一度怀疑 GUI 登录态 / trust folder / path 转义。Diagnoser 14 行 A/B 实验逐一排除（GUI app 全部运行中、登录态齐备、空目录 trust folder 也通过、ARG_MAX 1MB ≫ 提示词 6KB、shell 转义正确）。定位到 F1+F3 是 render-profile 默认值错，F2 是 personal.json model 名字错。
- 决策：source 修默认值而非文档「PM 用对 flag」。理由：默认值下 CLI 默认跑通是「先入坑后纠错」的逆向发现，文档「PM 用 -p -y」很多用户不知道；与其让每个 PM 犯错不如让 render-profile 默认发对命令。

## [1.17.1] - 2026-07-03

### Fixed
- **codebuddy / qoderclicn 假阴性检测（PATH-less 已知 .app bundle 多源检测）**：先前 `check-dependencies.sh --backend codebuddy` / `--backend qoderwork-cn` 只跑 `command -v codebuddy` + `command -v qoderclicn`，desktop 端已装但未建 symlink 时（如 `/usr/local/bin/codebuddy`）会假阴性报 MISSING/WARN 但不给出 actionable fix，PM 误判 worker CLI 不可用。新增 `check_app_bundle_binary()` 多源检测：先查 `PATH`，再依次查已知 .app bundle 绝对路径（codebuddy: `/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/bin/codebuddy`; qoderclicn: CN 版 `/Applications/QoderWork CN.app/Contents/Resources/bin/qoderclicn` + 国际版 `/Applications/QoderWork.app/Contents/Resources/bin/qodercli`），找到 bundle 时给 `DEPENDENCY_WARN` + actionable fix（`spawn-worker.sh --command` 直接传绝对路径 / `sudo ln -s` 永久 symlink），都找不到时显式提示装桌面端。两条 backend case 同步加进 usage() 帮助文本。
- **references/07-qoderwork-cli-worker.md §2.1**：新增「PATH-less 检测」一节，指引 PM 在新机器派 worker 前跑 `check-dependencies.sh --backend qoderwork-cn --strict`；附 spawn-worker 传绝对路径 / `sudo ln -s` 两条 fix。
- **references/08-workbuddy-cli-worker.md §2.2**：同 §2.1 形态，codebuddy 版本。
- **新 `--backend` 选项启用**：usage 文本加 `codebuddy | qoderwork-cn`。

### Reason
- 触发：用户 2026-07-03 派 Wave 1 时实测——`which codebuddy` + `which qoderclicn` 都报 `not found`，PM 一度以为 desktop 端没装；后续 ls 发现 `.app bundle` 内二进制其实在，是 symlink 没建。规则：「binary 实际在 app bundle」也算 worker 可用（spawn 传绝对路径即可），不应被漏报。
- 决策：不自动 `sudo ln -s` 创建 symlink（高风险操作、PM/用户应显式确认），改为报告 + 给两条 fix 让 PM 选；`check_app_bundle_binary()` 设计为静默存在性检查（前置于它的 `check_optional_cmd` 已决定 OK/WARN），避免重复 report。

## [1.17.0] - 2026-07-03

### Added
- **cron + sentinel 标准组合监测模式（§7.3）**：sentinel（§7.2）是主监测，但有 3 个盲区——(a) worker 硬卡死不写 STATUS 时 sentinel 轮询到 `--max-wait` 超时（exit 124）；(b) worker 用非标准 STATUS 文件名（如 `issue-XXX-status.json`）时 sentinel 监听 `STATUS.json` 轮询空文件到超时；(c) sentinel 自身被 SIGKILL/SIGTERM 或 harness 未 re-invoke 时静默消失。新增 §7.3 把"sentinel（秒级抓 done）+ cron（兜底：漏合入 + 硬卡死双信号检测 + sentinel 失效）"写成**标准两层组合**，而非二选一。PM 派 worker 后必挂两层。
- **cron 兜底频次硬推荐**：短任务 ~22min、**长流水线 10-15min**，避开 `:00`/`:30` 整点（API 拥堵 + 速率限制）。给出错峰 cron 表达式（`3,13,23,33,43,53 * * * *` 每 10 分钟 / `7,29,51 * * * *` 每 22 分钟）。不低于 10 分钟（过频抵消 token efficiency）。
- **双信号卡死检测**：判 worker 卡死必须 STATUS.updated_at + 文件 mtime 都超阈值（长流水线 20min）**且** pane 尾部有死循环证据，缺一不可；避免把正常 long thinking 误判为死循环。只满足时间信号时发 `tmux send-keys` 心跳探针，下一轮再判。
- **`templates/cron-monitor-prompt.md`**：可复用 cron prompt 模板（worker session + STATUS 路径 + git 分支 + sentinel id + stale 阈值 + 收尾自删 + 无动作一句话汇报），含占位符表 + cron 表达式建议表 + 收尾纪律。

### Reason
- 来源：用户 2026-07-03 反馈"cron 兜底频次 30 分钟太低，起码 10 分钟"，并提议改进 skill 兜底频次。排查发现 SKILL.md §7 原本没有 cron 兜底频次的硬性数字（30 分钟是 PM 按 cache 经济性自设，偏稀疏），但 skill 内部 TASKS #69/#70 早已登记"把 cron+sentinel 标准组合 + 10-15min 频次写进 §7 + 建 cron 模板"两条待办，本次一并实施。
- 决策：sentinel 事件驱动零 idle token 是主监测不可废；cron 兜底抓 sentinel 三个盲区 + 卡死双信号检测，是 graceful 降级而非替代。频次按任务粒度（长流水线 10-15min）平衡 catch-up 速度与 re-invoke token 成本。详见 DEC-038。

## [1.16.7] - 2026-07-02

### Added
- **个人 backend 路由偏好配置机制**（用户级，可被任何人自定义）：
  - 新增 `config/orchestration-personal.example.json` 模板，字段：`main_force`（主力 host + model 轮换）、`codex_policy`（`explicit_only` / `allowed`）、`backend_model_routing`（`qoderclicn` / `codebuddy` 的默认 model 列表）、`notes`。任何用户可复制为 `~/.claude/orchestration-personal.json` 后按个人可用 provider / model / 平台额度修改。
  - SKILL.md §2.4 新增「个人路由偏好」小节：PM 派 worker 前先读 `~/.claude/orchestration-personal.json`（缺失回落 example）；字段定义 + 缺省回落表；与 §2.2 / §2.3 / §3.3 的优先级关系。
  - SKILL.md §2.2 加「Backend → 默认模型速查表」：Claude Code 默认 `glm-5.2` / `MiniMax-M3` 轮换；`qoderclicn` 默认 `qoder-3.7MAX` / `qoder-3.7PLUS`；`codebuddy` 默认 `deepseek-v4-pro` / `deepseek-v4-flash`；Codex 默认 `explicit_only`（仅用户明确要求时启用）。
  - SKILL.md §3.3 增「用户级 vs 项目级」叠加表，明确 `~/.claude/orchestration-personal.json` 与 `.claude/orchestration.config.json` 不冲突，字段命名刻意不重叠。
  - `references/06-agent-cli-reference.md` §0 总览表加「默认 model（个人偏好）」列。

### Known Limitations
- **`render-runtime-profile.sh` 暂未自动读 personal config**：本次只做配置 + 文档 + PM 手动遵循。后续增强（解析 `main_force.models` → 默认 `--model`、`codex_policy.policy` → Codex backend gate、`backend_model_routing.<backend>.default_models` → 跨工具 default）需要开新 worker 单独做，避免无人监督下改脚本引入新不确定性。

### Reason
- 来源：用户确认主力 = Claude Code host + GLM-5.2 / MiniMax-M3 轮换；Codex 智能高但额度贵，仅在用户明确要求时启用；`qoderclicn` / `codebuddy` 跨工具 backend 在主力不够或用户明确指定时才派；每个 backend 的默认 model 也是个人偏好（不是 skill 级硬编码）。
- 决策：把"个人偏好"做成跟个人 dotfile 一样不进仓库（`~/.claude/orchestration-personal.json`），skill 内只留 example 模板 + 文档；机制可被其他用户复制和修改。Codex `explicit_only` 作为软推荐（个人偏好层面），不强写进 skill 硬规则。

## [1.16.6] - 2026-06-26

### Added
- **ref 08 §6.7 复测更新（codebuddy 多模型 eval）**：writing-reviewer v0.10.7 cross-model eval 中，codebuddy backend 并发跑 kimi-k2.6 / deepseek-v4-flash / deepseek-v4-pro（同 ch08 baseline 71 hard FAIL），三个 worker pass-1 全部 71→51，backend 在多模型 fan-out 下端到端可用。
- **snapshot-copy-into-worktree pattern（backend 无关关键修复）**：eval skill 快照在主仓库 untracked → fresh worktree 看不到；codebuddy trust-folder 又禁止跨目录读。修复：spawn 时把冻结 snapshot 拷进 worktree，worker 用 worktree-local 相对路径读，同时消除跨目录访问 / trust 限制 / path 漂移三类问题。详见 DEC-037。
- **`codebuddy-spawn.sh` helper**：`research/verification/writing-reviewer-skill-version-eval-260622/codebuddy-spawn.sh`，一条命令完成 worktree add + snapshot 拷贝 + session context + tmux（codebuddy 交互 + MCP off）。codebuddy/qoder spawn 暂用此手动 helper。
- **codebuddy MCP-off 标准flag**：正文修订任务用 `--strict-mcp-config --mcp-config /tmp/empty-mcp.json`（`{"mcpServers":{}}`）关 MCP，减前言 + 避免 WorkBuddy MCP 连接器 GUI 授权弹窗。
- **`render-runtime-profile.sh --no-mcp` 开关**：Claude Code worker 传 `--no-mcp` 自动注入 `--strict-mcp-config --mcp-config '{"mcpServers":{}}'`，跳过 "new MCP servers found" 审批弹窗（实测有效）。
- **eval worker 权限约定（worktree 隔离 → 最高权限）**：eval/test worker 都在独立 worktree 里跑、安全隔离，统一用最高权限免任何手动点击——Claude Code `--permission-mode bypassPermissions`（或 `--dangerously-skip-permissions`，经 render-runtime-profile 的 `--permission-mode` 传入）、codebuddy `-y`（`--dangerously-skip-permissions`）、qoderclicn `--dangerously-skip-permissions`。配合 `--no-mcp`，spawn 后直达 REPL，零点击。

### Known Limitations
- **`render-runtime-profile.sh` 仍不支持 codebuddy / qoderclicn backend**：只支持 claude-code（registry/settings）/ codex / opencode。codebuddy/qoder worker 暂走手动 helper 或原生 `--worktree --tmux`。TODO：把这两个 backend 加进 render-runtime-profile，统一 spawn 路径。

## [1.16.5] - 2026-06-23

### Added
- **Claude provider/model registry 模式**：新增 `config/claude-provider-registry.example.json`，按 MyAgents 的 provider intent 思路，把多个 provider 的 `base_url`、`auth_token_env` / `api_key_env`、`auth_type` 和 `models` 放入一个本地 registry。真实 registry 仍放 ignored local 文件，真实 key 优先用环境变量承载。
- **`claude-provider-env.sh` 支持 registry**：新增 `--provider-registry PATH --api-provider ID --model MODEL_ALIAS`，启动时解析 provider base URL、auth token 和模型别名，构造本次 worker 的有效 env。
- **`render-runtime-profile.sh` 支持 registry**：新增 `--provider-registry`，在渲染阶段把 model alias 解析成真实 provider model，并传给 `claude --model`；旧 `--settings` 路径保留兼容。

### Changed
- **文档改为 registry-first**：`SKILL.md`、`references/01-model-selection-matrix.md`、`references/06-agent-cli-reference.md`、`references/10-parallel-lessons.md` 改为推荐 registry + provider id + model alias，旧的每模型一个 settings 文件标为兼容路径。

### Reason
- 来源：用户确认不同模型来源有不同 Base URL、API key 和模型清单，希望参照 MyAgents 运行时动态选择 provider/model 的方式，减少为每个模型维护独立 settings JSON。
- 决策：保留两种模式。registry 模式作为默认推荐，settings 模式作为已有流程和排障兼容。这样 Agent 后续只需要指定 `api_provider` 与 `model alias`，由 wrapper 动态生成 Claude Code worker 环境。

## [1.16.4] - 2026-06-23

### Added
- **Claude Code provider env isolation wrapper**：新增 `scripts/claude-provider-env.sh`，借鉴 MyAgents 的 runtime snapshot/env 构造思路，在启动第三方 provider worker 前清理继承的 Claude/Anthropic provider 路由变量，从目标 settings JSON 导入 env，补齐 `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_API_KEY`，设置 `CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST=1`，并给 `claude` 注入 `--setting-sources project,local`。
- **runtime metadata env isolation 字段**：`spawn-worker.sh` 新增 `--env-isolation`，写入 `METADATA.json` 的 `runtime.env_isolation`，方便 PM 复盘某个 worker 是否走了 wrapper、OAuth 清理或继承环境。

### Changed
- **`render-runtime-profile.sh` 默认包 wrapper**：`claude-code + --settings + --model` 现在默认生成 `bash scripts/claude-provider-env.sh ... -- claude ...` 命令；排障时可显式 `--no-provider-env-isolation` 绕过。
- **batch render 自动 shell-wrap**：`render-runtime-profile.sh --mode batch` 生成的 Claude/Codex/OpenCode 命令会自动包 `bash -lc`，避免 `<` 重定向或 `$(cat prompt)` 在 `spawn-worker.sh` 的 tmux command 中不展开。
- **Provider smoke 与文档同步**：`smoke-provider-settings.sh` 改为走 wrapper；`SKILL.md`、`references/01-model-selection-matrix.md`、`references/06-agent-cli-reference.md`、`references/10-parallel-lessons.md` 更新为 settings + `--model` + wrapper 三件套口径。
- **Provider settings 模板补全**：example settings 增加 `ANTHROPIC_API_KEY` 和 haiku/opus/sonnet `_MODEL_NAME` 字段；真实 settings 仍保持本地 ignored。

### Reason
- 来源：用户指出另一个项目 MyAgents 在运行时可以动态选择 provider/model，并且可能屏蔽了用户级 Claude settings。对照 MyAgents 发现关键不是 SDK 本身，而是一次会话启动前的有效配置快照、settings-sourced provider env 屏蔽和子进程 env 显式构造。
- 本次把该模式移植到 Claude Code CLI worker 层，解决用户级 `~/.claude/settings.json` 指向 MiniMax 时，任务指定 GLM/DeepSeek/MiniMax 等 provider 仍可能被全局配置污染的问题。

## [1.16.3] - 2026-06-23

### Fixed
- **Claude Code 第三方 provider 启动命令强制显式模型**：`render-runtime-profile.sh` 在 `claude-code + --settings` 但缺少 `--model` 时直接报错，避免用户级 `~/.claude/settings.json` 或继承环境中的 `ANTHROPIC_MODEL` 覆盖 provider profile。
- **Provider settings 模板补全当前模型字段**：`config/claude-provider-settings.example.json` 新增 `ANTHROPIC_MODEL`、`ANTHROPIC_MODEL_NAME`、`ANTHROPIC_DEFAULT_FABLE_MODEL` 和 `ANTHROPIC_DEFAULT_FABLE_MODEL_NAME`，与现有 haiku/opus/sonnet 映射共同描述 provider 模型。
- **启动文档修正**：`SKILL.md`、`references/06-agent-cli-reference.md`、`references/10-parallel-lessons.md` 不再建议只用 `claude --settings <settings>`；第三方 provider worker 标准命令改为 `claude --settings <settings> --model <provider-model> ...`，并要求 PM 核对启动 banner。
- **Provider settings 排障口径**：补充 401/403、429/529、banner 模型错位、MCP 卡启动的判断规则。

### Reason
- 来源：法律 AI 书 `writing-reviewer` skill-version eval 中，PM 以 GLM 5.2 settings 启动 worker，交互界面仍显示 `MiniMax-M3[1m]`。诊断发现用户级 `~/.claude/settings.json` 配置了 `ANTHROPIC_MODEL=MiniMax-M3[1m]`，而本地 provider settings 只配置 base URL、token 和默认模型映射，没有配置当前会话模型。
- 实测结果：只传 `--settings glm-5.2.settings.json` 时 banner 显示 MiniMax；补 `--model glm-5.2[1M]` 后 banner 显示 GLM；在 settings 内补 `ANTHROPIC_MODEL` 后，即使漏传 `--model`，banner 也不再被用户级 MiniMax 默认覆盖。
- 同轮诊断还确认 GLM 5.1 / 5.2 最小请求均返回 `open.bigmodel.cn` 的 529，MiniMax 最小请求正常。这说明 GLM 当时的失败是目标 provider 网关拥塞 / 限流，不是 Claude Code 本地 settings 解析失败或余额不足。

## [1.16.2] - 2026-06-15

### Fixed (文档层)
- **`SKILL.md §6 启动方式`** 加 2 段醒目警示，来源 FaroPDF v0.2 Wave 1 spawn ISS-071 worker 实战（[DEC-033]）：
  - **`<` redirect 必须用 `bash -lc` 包**：`spawn-worker.sh:305` `tmux new-session -d -s "$SESSION" -c "$WORKTREE" "$COMMAND"` 直接 exec command 不通过 shell，shell metacharacter 不展开。错误：`--command 'claude -p < /tmp/x.md'`；正确：`--command "bash -lc 'claude -p < /tmp/x.md'"`。
  - **claude `-p` batch 模式 autocompact thrash 风险**：大 prompt（> 5KB）+ 大 codebase context 会触发 claude 内部 `Autocompact is thrashing` 3 次后自动终止，worker 永远不到达终态。规避：拆小 prompt < 3KB / 用交互式 claude + tmux send-keys / 窄 scope worker。

### Reason
- 2026-06-15 FaroPDF v0.2 推进期间，PM 按 §3.1 启动 Wave 1（3 worker ISS-071/067/070 并行）。spawn ISS-071 一个验证链路，遇到 2 个 skill 层 bug：
  1. `--command 'claude -p < /tmp/iss-071-prompt.md'` 启动后 worker 立即退出，sentinel 等 7211s 后 SENTINEL_TIMEOUT。
  2. 修复 Bug 1 后 worker 真启动 + 写 STATUS.json bootstrap，4 分钟后 claude 进程 autocompact thrash 自动停止，sentinel 持续轮询。
- PM 决策取消 Wave 1，改单 session 直推 ISS-071。详见项目侧 `FaroPDF/docs/DECISIONS.md` DEC-104 + skill 侧 [DEC-033]。
- 本次只改文档警示，不动 `spawn-worker.sh` 脚本（自动检测 shell metachar 留 follow-up，避免覆盖用户的非 bash shell 选择）。

### Follow-up (TASKS 已登记)
- `spawn-worker.sh` opt-in `--shell-wrap` flag 自动包 `bash -lc`（待证据足够时升级）
- `templates/worker-prompt.md` 加专门小节说明 claude -p 模式限制 + 替代方案
- memory `project-multi-agent-state` 补 Wave 1 / Bug A&B 经验

---

## [1.16.1] - 2026-06-05

### Fixed
- **`scripts/sentinel.sh` synonym 兜底**：case 分支接受 worker 实际写的 synonym 终态。成功终态 `done|completed|finished|complete` → exit 0；失败终态 `failed|blocked|stopped|aborted|cancelled` → exit 2。`SENTINEL_UNKNOWN_STATUS` 仍保留 `*)` 诊断 log，但不再让 worker 写 synonym 时死锁轮询到 `--max-wait`。

### Changed
- **`templates/worker-prompt.md` Process §9**：新增"Canonical terminal status (mandatory)"步骤，明确 worker 终态必须用 `status="done"` **exactly**；defensively sentinel 也认 `completed` / `finished` / `complete`，但 worker 不得依赖 synonym。引用项目侧 DEC-060 / skill 侧 [DEC-032]。

### Reason
- 来源：v1.16.0 sentinel bash 模式首次在 FaroPDF Wave 6 真用（2 worker 并行），两位 worker 写 `status="completed"` / `status="finished"` 逃过 sentinel case 分支的 `done` 严格判断，sentinel 持续空转，PM 收不到 harness task-notification，直到用户手动问"进度"才暴露。Spike 阶段只测了 `done` / `failed` 严格用法，没覆盖 LLM 写 synonym 的漂移。
- 验证：Wave 6 实战触发，PM 收口时 kill 2 sentinel（exit 143）+ 写双侧 patch 后已修复。Wave 7+ 工人按 worker-prompt.md §9 写 `status="done"`，sentinel 事件驱动链路恢复。
- 项目侧对应：FaroPDF 仓 `docs/DECISIONS.md` DEC-060（PR #48 / 2026-06-05）记录了实战触发 + 修复方案；本条 CHANGELOG 是 skill 侧 [DEC-032] 的实际交付记录。

## [1.16.0] - 2026-06-05

### Added
- **Sentinel bash 模式**（Task #9）：每个 worker 配一个 `scripts/sentinel.sh` 进程，PM 用 `run_in_background=true` 启，harness 在 sentinel exit 时通过 task-notification 自动 re-invoke PM，实现事件驱动 PM 唤醒，零 idle token 消耗。
- **`scripts/sentinel.sh`**：轮询 `STATUS.json` 终态（`done | failed | blocked | stopped`），命中后 capture tmux pane tail、`tmux kill-session`、`exit`。退出码 0/2/64/124 与 `wait-worker.sh` 对齐。复用 `redact_sensitive_stream` 内联（不抽公共库）。
- **`templates/pm-sentinel-response.md`**：PM 收到 sentinel task-notification 后的标准动作清单，按 exit code 分支（0=done, 2=failed/blocked/stopped, 124=timeout, 64=usage error），含范围检查、graceful 降级到 `pm-monitor.sh` 路径。
- **`references/04-sentinel-design.md`**：设计文档，复述 2026-06-05 3 phase spike 结果，解释为什么 Sentinel 模式与 DEC-030 假设不同（数量线性 / 单进程单 STATUS / 进程语义清晰 / graceful 降级）。
- **`scripts/smoke-sentinel.sh`**：端到端 smoke test，覆盖 done 路径（sentinel exit 0 + tmux killed + pane tail captured + redaction 工作）和 timeout 路径（sentinel exit 124 + max-wait 触发）。

### Changed
- **`scripts/spawn-worker.sh`**：新增 `--with-sentinel`、`--sentinel-poll-interval`、`--sentinel-max-wait`、`--keep-tmux-on-terminal` 标志。`--with-sentinel` 启用时输出 `SPAWN_WORKER_SENTINEL_CMD: ...` 和 `SPAWN_WORKER_RECOMMENDED_NEXT: ...` 提示 PM 在下一次 Bash 调用里 `run_in_background=true` 启 sentinel。**不在 spawn-worker 内部启 sentinel**（职责分离 + 避免 auto mode 拒多 background）。
- **`scripts/lint-wait-script.sh`**：默认 lint 集合加入 `sentinel.sh`，复用现有 `bash -n` + substring expansion 检查。
- **`SKILL.md` §6 工具面**：列出 `sentinel.sh`；§7.1 增加脚注指向 §7.2（"§7.2 是本规则的限定条件下可工作变体"）；新增 §7.2 Sentinel bash 模式章节，描述 PM 端两次 Bash 调用模式、事件命名空间、降级路径、调优建议。
- **`SKILL.md` frontmatter**：version bump `1.15.1` → `1.16.0`。
- **`DECISIONS.md`**：新增 `[DEC-031] - 2026-06-05 - Sentinel bash 模式 (Task #9 实施)`，**限定条件下 supersede DEC-030**，明确 sentinel 数 = 未完结 worker 数（线性而非 N×N）、单进程单 STATUS、graceful 降级是默认行为。DEC-030 文本保留（历史判断）。

### Reason
- 来源：Wave 4/5 实际痛点——PM 用 `pm-monitor.sh --log-file` 巡检是 polling-based，事件驱动不闭环，PM 必须靠用户输入或低频轮询才能感知 worker 终态。Wave 5 收口时把 Task #9 标"designed, not implemented"。
- 验证：2026-06-05 30 分钟 Spike 在 Claude Code 实测 `run_in_background=true` Bash 任务，3 phases 全部通过——harness 不区分 exit code（0/1/124 都 re-invoke），多次并发 notification 同 turn 批处理，单 background 拒率 spike 实测 1/6，graceful 降级是默认行为。
- 结论：在限定条件下（sentinel 数线性、单进程单 STATUS、graceful 降级），`run_in_background=true` Bash 任务可以作为可靠的 PM 唤醒机制。Wave 6 启动时启用。

### Out of Scope（避免在本次 PR 蔓延）
- Codex / OpenCode worker 的 sentinel 集成：暂未实测，Codex 走 `templates/codex-heartbeat-wait.md`
- 多 sentinel 对单 worker 去重：PM 行为层处理
- 重写 `pm-monitor.sh`（Task #6 单独 PR）

## [1.15.1] - 2026-06-05

### Changed
- **Claude Code background wait caveat**：修正 `run-in-background` 描述，明确 background Bash 只负责后台运行等待器，不保证把 worker 终态消息推回 PM / agent session。
- **multi-worker monitoring**：多 worker / Wave 默认使用 `pm-monitor.sh --log-file` + 显式低频巡检，不再建议为每个 worker 启 background wait 并期待宿主自动回调。

### Reason
- 来源：用户在 Claude Code 中实测发现，background Bash 没有可靠触发 agent session；开启多个独立 worker 时可能没有任何消息返回。
- 结论：完成通知必须回到结构化 checkpoint、事件日志和显式巡检；background job 只能作为日志写入器或人工可查看后台进程。

## [1.15.0] - 2026-06-05

### Added
- **optional project config template**：新增 `templates/project-config.json`，声明 trunk、任务源、worktree/session 默认路径、按 worker type 拆分的验证命令、provider slot、非敏感配置复制清单和 hook 边界。

### Changed
- **SKILL.md config discipline**：标准流程增加项目配置读取规则，明确配置只提供默认值，不替代 PM 判断。
- **Goal/worker templates**：增加 project config 字段，要求 PM 写明采用了哪些配置字段、忽略了哪些字段以及安全检查结果。

### Reason
- 来源：TASKS 中仍有“评估项目级配置文件”待办，且用户关注脚本是否过度设计。
- 结论：采用轻量模板，不新增脚本、不自动读取、不自动复制配置、不自动执行 hook；`.env`、真实 settings、token/key/cert 等继续默认禁止。

## [1.14.1] - 2026-06-05

### Changed
- **script surface governance**：明确默认工具面只包含 dependency check、runtime profile render、spawn worker 和 PM monitor；status/clean/wait/test/terminal split 均按场景使用，避免 PM 被脚本数量牵引。
- **provider slot planning**：超过 4 个 worker 时，改为显式声明 `backend + settings/profile path + provider + model + max concurrency`，而不是脚本自动猜测用哪个 settings.json。
- **templates**：worker prompt、checkpoint、Goal Contract 和 Wave Summary 增加 settings/profile path，让每个 worker 的额度来源可审计但不暴露 settings 内容。

### Reason
- 来源：用户担心脚本数量过多、出现过度设计，并追问超过 4 个 worker 时到底如何分配 settings.json。
- 结论：不新增自动 scheduler。现阶段应把 provider pool 做成 PM 可审计的显式 slot 表；如果只有一个可用 settings/profile，则并发 cap 降到 3-4，剩余任务进入下一 Wave。

## [1.14.0] - 2026-06-05

### Added
- **runtime dependency matrix**：新增 `references/02-runtime-dependencies.md`，按 core、tmux/worktree、PR/GitHub、worker backend、Codex heartbeat、terminal split 和验证工具拆分依赖。
- **dependency checker**：新增 `scripts/check-dependencies.sh`，可检查核心依赖、backend CLI、`gh` 和终端分屏工具；脚本只报告状态，不安装软件、不启动 worker。

### Changed
- **SKILL.md dependency section**：将依赖说明从单张系统依赖表升级为分层依赖说明，明确 `claude`、`codex`、`opencode`、`gh` 不是所有模式的硬依赖。
- **smoke test**：`smoke-tmux-worker.sh` 纳入 dependency checker 基础回归。

### Reason
- 来源：用户指出使用本 Skill 可能还有常规依赖需要安装，当前文档没有写清楚。
- 结论：依赖应按执行模式拆分，避免把所有可选 backend 都误解为必装，同时给 PM 一个启动前的本地检查入口。

## [1.13.0] - 2026-06-05

### Added
- **runtime profile command helper**：新增 `scripts/render-runtime-profile.sh`，按 `claude-code`、`claude-oauth`、`codex`、`opencode`、`custom` backend 生成 worker command、prompt context 和 spawn metadata，减少 PM 手写 provider/profile 命令。
- **Agent Teams troubleshooting**：新增 `references/11-agent-teams-troubleshooting.md`，覆盖 agent/team 不可见、错误 cwd、官方 worktree 状态映射、checkpoint 缺失、PR 收口和必须停止的场景。

### Changed
- **spawn flow**：SKILL.md 启动示例改为先用 `render-runtime-profile.sh` 生成 runtime 字段，再传给 `spawn-worker.sh`，保持启动命令生成与 worktree/session gate 分离。
- **smoke test**：`smoke-tmux-worker.sh` 覆盖 runtime profile helper 的 custom、Claude Code 和 Codex 输出。

### Reason
- 来源：用户要求继续推进 TASKS 中可落地的优化项。
- 结论：Agent Teams 排障指南和 runtime profile helper 都能本地落地并提升稳定性；Agent Teams feature flag、真实 Claude 原生 `--worktree --tmux` 后端和跨 PM/worker smoke 仍需要真实宿主环境验证。

## [1.12.0] - 2026-06-05

### Added
- **Goal-Driven Multi-Wave Loop**：SKILL.md 新增 PM 级 Orchestration Goal Loop，支持在成功条件满足前自动收口当前 Wave、读取任务源、选择下一批安全任务并启动下一 Wave。
- **Goal Contract 模板**：新增 `templates/orchestration-goal.md`，要求 PM 在连续推进前写清任务源、成功条件、自主级别、并发/预算上限、继续条件和停止条件。
- **Goal Loop 状态映射**：`checkpoint-status.json` 增加 `orchestration_goal` 字段；`worker-prompt.md` 增加 Goal ID / Loop Iteration，并明确 worker 不得自行领取其他任务。

### Changed
- **Wave summary**：新增 Goal ID、loop iteration、continue/stop decision、remaining tasks 和 next Wave 字段，让每轮自动继续都有可审计记录。
- **Skill 路由**：明确 Claude Code / Codex `/goal` 可作为 PM loop 的宿主续跑能力，但不替代 worktree、tmux、checkpoint、review 和 merge 门禁。

### Reason
- 来源：用户希望多 Agent 编排不止“一次运行一个 Wave”，而是在 PR 验收、验证和任务源状态正常时，能自动继续下一 Wave，直到目标范围内任务耗尽或触发停机条件。
- 结论：连续推进应放在 PM 层，不放给 worker；worker 保持窄任务边界，PM 负责任务池、Wave 收口、继续/停止判断和合并门禁。

## [1.11.0] - 2026-06-04

### Added
- **Wave-Based Orchestration**：SKILL.md 新增 Wave 一等调度概念，要求 PM 在每轮启动前记录 `wave_id`、worker 清单、base ref、共享风险、provider/model/slot、收口顺序和下一轮进入条件。
- **跨 provider 并发池**：明确超过 3-4 个 worker 时不应压在单一 API provider 上，应跨 runtime profile/API 来源分流，并在 Wave 收口时评估模型/provider 表现。
- **worker 类型与验证底线**：worker prompt 新增 `ui-wiring`、`contract-extension`、`tauri-command`、`docs/research` 等类型，明确 Tauri/Rust worker 的 `cargo check --offline` 验证底线和 skipped verification 记录要求。
- **Wave checkpoint 字段与 summary 模板**：`checkpoint-status.json` 新增 `wave`、`worker_class`、provider/model/slot 和 `model_evaluation` 字段；新增 `templates/wave-summary.md`。
- **多信号进展巡检**：`pm-monitor.sh` 新增 `--wave-id`、`--progress-stale-threshold`、`WORKER_SILENT_PROGRESS`、`WORKER_NO_PROGRESS` 和 `WORKER_FINISHED_NO_PHASE_DONE`，结合 STATUS、commit、file mtime 和 dirty state 判断 worker 是否真有进展。
- **wait script lint**：新增 `scripts/lint-wait-script.sh`，用于检查 wait/monitor/custom wait 脚本的 `bash -n` 和 `${VAR:0:N}` substring 闭合错误。
- **worktree metadata**：`spawn-worker.sh` 在 Session Context 写入 `METADATA.json`，记录 base、session、runtime profile、provider slot、验证命令和 PR 占位；`worktree-status.sh` / `clean-worktree.sh` 会展示该摘要。

### Changed
- **worker prompt**：加入 Wave 信息、provider slot、Decision ID race 规则、worker type rules 和验证底线。
- **spawn gate**：`spawn-worker.sh`、`worktree-status.sh` 和 `clean-worktree.sh` 使用物理路径解析，避免 macOS `/var` / `/private/var` 别名导致 cwd gate 误失败。
- **worktree-status.sh**：单 worker 只读总览增加 wave/provider/model/type 输出。
- **smoke test**：`smoke-tmux-worker.sh` 通过 `spawn-worker.sh` 创建 worker，覆盖 metadata 写入、总览展示和清理前摘要。
- **parallel-lessons.md**：补充 Wave worker 类型、Vitest/Vite 二进制资源兼容、DEC 编号 race 和 provider 并发池实战记录。

### Reason
- 来源：用户要求评估 TASKS 中多个优化/升级建议，并把合理项升级为 `multi-agent-orchestration` 的正式机制。
- 结论：Wave、provider 并发池、多信号巡检、worker 类型、验证底线和 DEC race 属于高复用执行协议；Agent Teams 发布状态、终端 split-panes、底层 adapter、Snap mode 等仍留作后续研究。

## [1.10.0] - 2026-06-04

### Added
- **worker 生命周期脚本**：新增 `spawn-worker.sh`、`worktree-status.sh`、`clean-worktree.sh` 和 `smoke-tmux-worker.sh`，把 worktree/session 创建、单 worker 状态总览、安全清理和端到端 smoke test 固化为可执行入口。
- **commit stale 事件**：`pm-monitor.sh` 新增 `--commit-stale-threshold` 和 `WORKER_STALE_NO_COMMIT`，用于提示 session 存活但分支长时间没有阶段性提交的 worker。
- **Codex heartbeat 模板**：新增 `templates/codex-heartbeat-wait.md`，明确 Codex App 用 `wait-worker.sh --once` 做轻量唤醒，创建/修改 automation 时必须使用 `automation_update` 工具。
- **Worker commit cadence**：worker prompt 要求长任务每 30-60 分钟或阶段完成后生成可 review commit，并刷新 `STATUS.json` 的 Git 字段。

### Changed
- **wait-worker.sh 输出脱敏**：tmux pane tail 和 RESULT tail 默认过滤 token/key/secret/auth/password 等敏感行，并替换常见 secret token 片段。
- **SKILL.md 压缩启动章节**：将长启动示例收束为 `spawn-worker.sh` + 常用 command 索引，保留防逃逸门禁和最小验证规则。
- **checkpoint Git 字段**：`templates/checkpoint-status.json` 增加 `git.last_commit_at` 和 `git.commits_since_base`，`pm-monitor.sh` / `worktree-status.sh` 同步显示。
- **脚本 shebang**：核心脚本统一使用 `/usr/bin/env bash`；`pm-monitor.sh` 增加 bash 4+ 版本门禁，避免 macOS 系统 `/bin/bash` 3.2 运行关联数组失败。
- **UTC 时间解析**：`pm-monitor.sh` 和 `wait-worker.sh` 在 macOS 上按 UTC 解析 `updated_at` 的 `Z` 后缀，避免刚写入的 checkpoint 被误报 stale。

### Reason
- 来源：用户希望把 “tmux 独立 session 防逃逸” 做成可执行、可验证、可 smoke 的完整协议，并适配 Codex 的后台等待/heartbeat 方式。
- 目标：让 PM 不再依赖手写命令和主观自律；启动、等待、监控、状态、清理和回归验证都有明确脚本入口。

## [1.9.9] - 2026-06-03

### Added
- **wait-worker.sh tmux 诊断尾部输出**：新增 `--tmux-session`、`--pane-tail-lines`、`--include-pane-on` 和 `--stale-threshold`。默认只在 checkpoint 缺失、过期或终态时读取 tmux pane tail。
- **状态源分层规则**：SKILL.md §7.1 明确 `STATUS.json` / `RESULT.md` / `PATCH_SUMMARY.md` 是主协议，`tmux capture-pane` 只作诊断窗口，不作为完成标准。

### Reason
- 来源：用户提出既然 background Bash 在运行，是否可以直接读取 tmux worker 输出。
- 结论：可以读，但要作为诊断兜底而非主状态源，避免屏幕输出截断、清屏、敏感信息和上下文膨胀影响 PM 判断。

## [1.9.8] - 2026-06-03

### Added
- **scripts/wait-worker.sh**：新增单 worker 等待器，可持续等待或 `--once` 快速检查 `.claude/agent-sessions/<session>/STATUS.json`，在 `done` / `failed` / `blocked` / `stopped` 时输出 RESULT/PATCH_SUMMARY 路径并退出。
- **§7.1 主动等待与宿主唤醒**：明确 `wait-worker.sh` 不替代 `pm-monitor.sh`；Claude Code 可接 Bash background/run-in-background，Codex App 则用当前 thread 的 heartbeat automation 调用 `wait-worker.sh --once` 实现主动唤醒。

### Reason
- 来源：用户希望 Claude Code 的 Bash `run_in_background` 等待体验也能适配 Codex。
- 结论：Codex CLI 没有同名自动通知机制；Codex 适配应通过“通用等待脚本 + Codex heartbeat/thread wakeup”完成，避免把核心 monitor 绑定到单一宿主。

## [1.9.7] - 2026-06-03

### Added
- **防逃逸门禁**：当用户或项目明确要求 tmux / 独立 session / 开 worker 时，PM 在业务实现前必须创建 worktree/branch、启动 session、验证 cwd/branch、派发 worker prompt 并确认 `STATUS.json`，否则报告阻塞，不得静默降级为 PM 直接实现或普通 Subagent。
- **Worker Isolation Gate**：`templates/worker-prompt.md` 要求 worker 在读任务或实现前确认 cwd、branch 和 worktree；不匹配时写 blocked `STATUS.json` 并停止。
- **STATUS orchestration_gate 字段**：`templates/checkpoint-status.json` 新增 session/cwd/branch/worktree/degraded/escape 结构化门禁字段，`pm-monitor.sh` 会输出 `ORCHESTRATION_GATE_FAILED`。

### Fixed
- **pm-monitor.sh 本地未 push 分支误退出**：远端分支不存在时先查 merged PR；若本地分支仍存在，输出 `BRANCH_NOT_PUSHED` 并保持 monitor 运行。
- **SESSION_GONE 去重**：tmux session 消失事件只在状态变化时输出，避免低频巡检日志重复刷屏。

### Reason
- 来源：用户反馈其他模型在 Claude Code 中反复没有按 tmux 独立 session 推进，需要把“不要逃逸”从建议性描述升级成可检查门禁。
- 目标：让 PM、worker 和 monitor 三层都能暴露逃逸：PM 不能绕过启动门禁，worker 不能在错误目录继续实现，monitor 能报告 gate 失败和本地分支未 push。

## [1.9.6] - 2026-06-03

### Changed
- **SKILL.md §6 tmux / Claude Code worker 例子**：去掉 `--max-turns 20` 的限制示例，加注"不要设 `--max-turns`；PM 重点是检测 worker 真在运转而不是限制 turn 数"。
- **scripts/pm-monitor.sh BRANCH 状态区分**：远端 branch 不存在时，区分两种情况：
  - 本地 branch HEAD == main HEAD → `BRANCH_NOT_PUSHED: $branch (waiting for worker to commit and push)`（**新事件**）
  - 本地 branch HEAD != main HEAD → `BRANCH_MERGED: $branch`（保留原行为）
  - 解决"branch 还没 push 被误判为 merged"导致 monitor 立刻退出的问题。

### Reason
- 来源：FaroPDF v0.1 Wave 2 启 worker 后 PM 监控失灵的根因分析。
- 主要根因：
  1. worker prompt 没强调"启动后立即写 STATUS.json 心跳"，导致 max-turns 触发时没 STATUS.json，PM 无从判断 worker 真在运转。
  2. SKILL 自带 pm-monitor.sh 的 BRANCH_MERGED 判断只看 `origin/$branch` 是否存在，忽略了"branch 还没 push"的常见 case，导致 monitor 立刻退出。
  3. SKILL 例子给的 `--max-turns 20` 让我误以为应该设上限，实际应让 worker 跑自然结束。

## [1.9.5] - 2026-06-03

### Added
- **§8.0 PM 在 Worker 提 PR 后的持续同步**（精简版）：
  1. 提 PR 之后立即跑 `gh pr view <N> --json mergeable,mergeStateStatus,baseRefName`；冲突走 `git-workflow` 决策表。
  2. PM 在主目录 commit docs / DEC 之后**立即** `git push origin main`，避免本地与 origin/main drift（squash merge 引入的"内容相同但 history 不同"会让 git 误判冲突）。

### Reason
- 来源：FaroPDF v0.1 Wave 1 真实合并 PR #18 / #19 前的根因复盘。
- 主要根因：PM 没在 worker 提 PR 后立即跑 mergeable 检查；PM 本地 main commit DEC 后没立即 push。

## [1.9.4] - 2026-06-03

### Added
- `parallel-lessons.md` 新增 G17：任务编号从 `ISS-NNN` 改为 `Task-NNN`（与 project-init v1.1.1 对齐）。说明新约定、迁移规则，以及历史 lesson（如 G15 的 `FaroPDF ISS-018`）和 commit history 保持原样不改写。

## [1.9.3] - 2026-06-03

### Changed
- 将 checkpoint 可复制模板从 `references/03-checkpoint-files.md` 移到 `templates/`，包括 `checkpoint-status.json`、`checkpoint-result.md` 和 `checkpoint-patch-summary.md`。
- 新增 `templates/worker-prompt.md`，将 worker prompt 拆成 Bootstrap-only 和 Full worker 两段，并按 Context / Background / Mission / Scope / Deliverables / Process / Verification / Autonomy / Out of Scope / PM Correction 组织。
- 精简 `SKILL.md` 与 `references/03-checkpoint-files.md`：正文只保留规则、字段经济性和模板路径，避免 Skill 主体继续膨胀。

## [1.9.2] - 2026-06-03

### Changed
- 将 `STATUS.json` 升级为 v2 schema，补充 `task_source`、`current_action`、`next_action`、`scope`、`runtime`、`git`、`pm_action_required`、`blocker`、`risks` 和 `last_pm_correction` 等 PM 决策字段。
- 明确 `STATUS.json` 的经济性边界：只记录 PM 自动监控和 review 决策必需的结构化信号，不记录 token、完整环境变量、settings 内容或长日志。
- 增强 `pm-monitor.sh`：新增 `--once`、`--interval`、`--stale-threshold`、`--log-file`，支持一次性巡检、低频后台巡检和事件日志落盘。
- `pm-monitor.sh` 现在会从 checkpoint 输出 `CHECKPOINT_STALE`、`AGENT_NEEDS_INPUT`、`CHECKPOINT_TEST_FAILURE`、`CHECKPOINT_PR` 等事件，减少 PM 前台轮询需求。
- 补充经济型巡检规则：脚本负责事件输出和日志，是否自动唤起 PM 取决于宿主环境；无唤醒能力时用 `--once` 或低频读取 log tail。

## [1.9.1] - 2026-06-03

### Changed
- 将新 worker 的 checkpoint 目录从 `.agent-context/` 调整为 `.claude/agent-sessions/<session-id>/`，复用项目既有 `.claude/` 协作空间；`pm-monitor.sh` 仍兼容读取旧 `.agent-context/`。
- 明确 Claude Code 官方 Agent Teams 的状态源在 `~/.claude/teams/<team>/` 与 `~/.claude/tasks/<team>/`，不要在项目内自造 `.claude/teams/` 冒充官方 team。
- 明确 worktree、分支和 session context 默认由 PM 创建；只有 Claude Code 官方 Agent Teams / agent view 明确使用自身 `--worktree` 能力时，才允许 worker 侧创建隔离环境，PM 仍需验收。
- 将 PM review correction 固化为收口流程：PM review 失败时优先把具体修正发回原 worker，worker 追加修复 commit、更新验证和 PR，PM 再复核。
- 补充环境差异规则：Claude Code provider settings、Claude OAuth/订阅、Codex/OpenAI 和 OpenCode profile 必须分开声明，不默认清理或继承环境变量。

## [1.9.0] - 2026-06-02

### Changed
- 将 PM 从具体产品中解耦：当前 Codex、Claude Code 或其他主会话都可以担任 PM。
- 将 worker backend 抽象为 Claude Code、Codex、OpenCode、shell 和可选 ACP adapter，支持从 Claude Code 启动 Codex/OpenCode worker，或从 Codex 启动 Claude Code/OpenCode worker。
- 补充 runtime profile / 额度路由规则，明确 Claude Code worker 默认走第三方 API provider settings，订阅/OAuth 只作为显式例外。
- 补充 Claude Code 第三方 API provider settings 模式：通过 `--settings /path/to/provider.settings.json` 加载 `ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN` 和默认模型环境变量。
- 将 Claude Code worker 默认额度模式调整为第三方 API provider settings，并新增 `references/claude-provider-settings.example.json` 模板。
- 将 Claude Code tmux worker 默认启动方式调整为交互式后台终端 session；`-p` 仅作为批处理 prompt 的可选模式。
- 将 provider settings 示例调整为 Minimax Anthropic-compatible API 结构，保持 token、base URL、三类默认模型、timeout、thinking tokens 和行为开关一并配置。
- 增加结构化 checkpoint 三件套：`.agent-context/STATUS.json`、`RESULT.md`、`PATCH_SUMMARY.md`，并新增模板参考文档。
- 更新 `pm-monitor.sh`，支持从分支自动定位 worktree、监听 checkpoint 文件变化，并可选通过 `--claude-agents-cwd` 读取 Claude 官方后台 session 状态。
- 补充 Claude Code 官方 agent view / background session 入口：`claude agents`、`claude agents --json`、`--worktree`、`--tmux`，以及版本支持时的 `claude --bg` 和 `/bg`，作为 tmux 之外的 Claude 专用后台会话模式。
- 补充 OpenCode worker 支持：默认用 `opencode run --format json --model <provider/model>`，并将 `opencode acp` 记录为可选 ACP server 候选。
- 补充 custom CLI worker 模板，支持其他可一行命令启动、可在指定 worktree 中运行的 Agent。
- 将 ACP 定位为可选后端：协议层结构化，但默认仍以 `tmux + worktree + checkpoint 文件 + git 状态` 作为稳定执行层。
- 更新 Worker Prompt 模板，加入 PM Host、Worker Backend、Runtime Profile 和 `.agent-context/STATUS.json` / `RESULT.md` / `PATCH_SUMMARY.md` checkpoint 协议。
- 明确用户指定当前会话担任 PM agent 时，PM 默认不直接写业务代码；实现优先委派给 worktree worker、独立 session、Agent Teams 或 Subagent，PM 负责巡检、纠偏、review 和收口。
- 基于 FaroPDF ISS-018 实战补充流程约束：高延迟 provider 可两段式 bootstrap；`.agent-context/` 只作本地 checkpoint，不进入 Git/PR；worker 不应等待 PM 下一步；STATUS 每次写入必须刷新 `updated_at`；窄范围实现默认 low/medium effort。

## [1.8.2] - 2026-06-01

### Changed
- 收口发布包参考文档，只保留模型/执行模式矩阵、实战坑点和法律项目拆解样例。
- 精简法律场景参考，移除未落地的未来模板路径和外部 catalog 设想，明确其只作为本地执行层拆分样例。

### Removed
- 移除已落地或过时的历史平台调研、Agent Teams 优化积压和 Auto PM 蓝图文档，避免与当前 SKILL.md 实现机制重复或冲突。

## [1.8.1] - 2026-05-20

### Changed
- 同步任务协调层边界说明和参考文档命名。

## [1.8.0] - 2026-05-20

### Changed
- 重命名 Skill：`multi-agent-workflow` → `multi-agent-orchestration`，标题改为 Multi-Agent Orchestration，以突出“本地多 Agent 执行编排”而非普通流程说明。
- 同步更新 SKILL.md description 和开篇说明，统一使用“执行编排”表述。
- 同步更新相关边界引用。

## [1.7.0] - 2026-05-20

### Changed
- 重命名 Skill：`parallel-agent-workflow` → `multi-agent-workflow`，标题改为 Multi-Agent Workflow，以匹配当前“多 Agent 本地执行编排”的职责边界。
- 优化 SKILL.md frontmatter description，补充正向触发场景和负向边界。
- 补充脚本依赖说明，明确 `pm-monitor.sh` 与 `terminal-split.sh` 的系统依赖和可选终端依赖。
- 同步更新相关边界引用。

## [1.6.0] - 2026-05-19

### Changed
- 精简 `SKILL.md` 为执行入口、命名规则、启动方式、巡检和收口规则；复杂细节转交 `references/` 和 `scripts/`。
- 明确任务源由项目配置或项目上下文决定，不在 Skill 中写死固定文件路径。
- 保留 `pm-monitor.sh` 的自动 PM 巡检能力，包括 Agent Teams inbox、tasks、Git SHA、PR 状态和 tmux session 多维监控。
- 保留 `terminal-split.sh` 的多终端分屏能力，包括 iTerm2、Kitty、WezTerm、Warp、Ghostty、Zed 和 Terminal.app。

## [1.5.0] - 2026-05-17

### Added
- 新增从项目任务源形成本地执行计划的通用规则：提取 Issue ID、状态、推进建议、文件/组件、依赖和验收标准。
- 新增 待办事项分组策略：按文件/组件重叠、依赖链、并行安全度和 PR 审查边界决定多个 Issue 是否放入同一 worktree/session。
- 新增 L1/L2/L3 路由说明，明确不是一个 Issue 必然对应一个 session。

### Changed
- `multi-agent-orchestration` 继续只拥有本地执行层；分组计划只服务本轮执行，不成为新的任务状态源。

## [1.4.0] - 2026-05-17

### Changed
- 明确本 Skill 只负责本地 Agent 会话、并行执行、PM 巡检和 worktree 隔离，不拥有任务主状态。
- 标准流程改为从项目既有任务源接收已经确认可执行的任务。
- 将 `git-task-orchestrator` 定位改为历史蓝图，不再作为当前协作入口，也不迁入其旧 worktree/session 方案。

## [1.3.0] - 2026-05-09

### Added
- **任务列表管理**：复用 Agent Teams 的 tasks 目录结构（JSON 任务项 + .lock 文件锁 + .highwatermark 增量读取）
- **文件锁机制**：agent 认领任务时用 `flock()` 防止并发冲突
- **高水位标记**：agent 增量读取任务列表，已完成任务自动删除并更新 highwatermark
- **pm-monitor.sh v4.1**：新增 `--tasks-dir` 参数、`check_task_states()` 函数、TASK_STATUS/TASK_COMPLETED 事件
- **权限继承自动化**：启动时自动从主仓库复制 `.claude/settings.json` 到每个 worktree
- **Context 恢复**：团队协议持久化到 worktree 的 `CLAUDE.md`，`claude --continue` 后协议不丢失

### Changed
- §6.1 创建 Worktree 增加权限自动复制步骤
- §6.2 初始化增加共享任务列表创建
- §6.3 启动 Agent 增加 CLAUDE.md 持久化步骤
- §6.6 清理增加 tasks 目录清理
- pm-monitor.sh 支持 `--tasks-dir` 参数

## [1.2.0] - 2026-05-09

### Changed
- **[重大] tmux 模式统一使用 Agent Teams 文件通信协议**：tmux 仅作为进程管理层，通信层复用 `~/.claude/teams/` 的 inbox + tasks 机制
- tmux 模式从"降级模式"重命名为"扩展模式"，体现架构对等性
- pm-monitor.sh v4：新增 `--team-dir` 参数，支持 inbox health_report 轮询（6 个新事件类型），保留 git SHA 轮询作为第二维度
- 运行时干预改为 inbox 命令消息 + 短 send-keys 提醒（替代长文本 send-keys）
- 监控巡检改为读取 PM inbox health_report（首选），capture-pane 降为回退方案

### Added
- Agent Teams 通信协议 prompt 模板（health_report 发送、命令检查、agent 间 inbox 通信）
- 团队目录初始化步骤（config.json + inbox 文件创建）
- health_report 消息类型（status/phase/progress/last_commit_sha/context_pct/issues）
- inbox 命令协议（continue/stop/check_review_feedback/rebase/commit_and_push）
- pm-monitor.sh 过时检测（5 分钟无 health_report 自动告警）
- 自动 PM 蓝图中的 tmux 扩展模式通信架构
- parallel-lessons.md 文件通信协议操作手册

## [1.1.0] - 2026-05-08

### Changed
- **[重大] 默认使用 Agent Teams（Teammate 模式）**：在 Claude Code 环境下，重任务优先使用官方 Agent Teams，tmux 降级为非 Claude Code 环境的备选方案
- 任务规模路由从二元（Subagent / tmux）升级为三元（Subagent / Agent Teams / tmux）
- 执行模式对比从二元表扩展为三元表（Subagent / Agent Teams / tmux Session）
- 监控方式从 tmux capture-pane 扩展为 Agent Teams 共享任务列表 + 邮箱系统
- 通信通道增加 Agent Teams 邮箱系统（双向通信，替代单向 send-keys）
- 新增环境检测逻辑（自动选择 Agent Teams 或 tmux 降级）
- 实战经验文档按 Agent Teams / tmux 降级 / 通用三类重组

### Added
- SKILL.md §3 前置条件拆分为 Agent Teams 和 tmux 两组
- SKILL.md §4 环境检测与模式选择
- SKILL.md §5 Agent Teams 标准流程（规划/Worktree/启动 Teammates/监控/干预/审查/合并）
- SKILL.md §6 tmux 降级模式（保留完整流程）
- Agent Teams 详细技术调研

## [1.0.0] - 2026-05-07

### 新增
- SKILL.md 核心技能定义，覆盖并行 Agent 完整生命周期
- terminal-split.sh 跨终端分屏脚本（支持 iTerm2/Kitty/WezTerm/Warp/Ghostty/Zed/Terminal.app）
- pm-monitor.sh 参数化 PM Monitor（基于 git SHA 变化，自动停止）
- 模型选择矩阵（L0/L1/L2 路由 + 运行时升降级）
- 执行模式选择（Subagent vs tmux + 混合模式）
- PM 巡检循环蓝图（健康/任务/PR 三维巡检）
- 实战经验教训文档（tmux 陷阱、合并冲突、IME 干扰）
- 与 git-task-orchestrator 的边界定义和协作路由
- 法律实务任务拆解模板（诉讼/非诉/尽调/合同审查）作为扩展参考
- 多 Agent 平台技术调研（Claude Code/OpenClaw/Codex/Hermes 对比 + Skills 生态评测）作为扩展参考
