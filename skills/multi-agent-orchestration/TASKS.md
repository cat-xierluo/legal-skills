# Multi-Agent Orchestration Tasks

本文件是本 Skill 的当前维护队列。历史实现细节以 Git、PR 和 `CHANGELOG.md` 为准；不要把已失效的本机绝对路径、terminal、Run、Task、Dispatch 或临时 capability 当作可恢复上下文。

## 状态与领取规则

| 状态 | 含义 | Agent 动作 |
|---|---|---|
| `READY` | 依赖与范围齐全，可领取 | 从最新 `origin/main` 新建短分支和独立 Worktree |
| `IN_PROGRESS` | 已有唯一 owner、候选分支和冻结起点 | 只由当前 owner 推进；其他 Agent 只读观察或独立 review |
| `RESTART_REQUIRED` | 目标仍有效，但旧候选/Worktree/证据已失效 | 先重建合同与基线，不复用旧运行身份 |
| `BLOCKED` | 前置任务未完成 | 不实施，只维护依赖事实 |
| `PARKED` | 等用户授权、外部 owner 或设计决定 | 不自动恢复 |
| `OBSERVE` | 只收集证据，尚未达到立项阈值 | 不修改生产规则 |
| `COMPLETE` | 已由合并提交或其他不可变证据关闭 | 不重复实现 |

领取 `READY` 任务前必须：`git fetch origin`；确认任务未被其他 PR/会话占用；记录 owner、分支、Worktree、base ref 与 immutable start SHA；只修改卡片允许范围；完成后写回 PR、测试和剩余 `NOT_VERIFIED`。任务未明确允许时，不编辑其他 Skill、个人配置或其他会话 Worktree。

## 当前执行顺序与波次

1. 通信能力波次：`ORCA-CROSS-PM-HANDOFF` 从最新 `origin/main` 重建合同并交付。
2. `ORCA-PEER-COMMS` → `ORCA-COMMS-E2E`；两项保持依赖阻塞，不提前实现。

Hermes 专项和 ZCode 专项不插入上述顺序；只有卡片状态转为 `READY` 且 owner 明确后才进入执行队列。

## TASK-2026-09-28-ORCA-SETTLEMENT-READBACK — 对齐真实 Orca 回读与外部终端结算

- 状态：`READY`；优先级：`P1`；类型：`runtime-compatibility`；Owner：未领取。来源：Eval Harness 的 P014 主线接入检查；这是该任务短生命周期验证的直接前置，不变更通信波次排序。
- 已复现事实：现行 `scripts/runtime_settlement.py` SHA-256 `6ca9c93e3394f0013a6bae627eba3d5573de19a8e4299d6daf39dae8d7fab08d` 对已保全真实 `worker-show` 回执报 `IDENTITY_MISMATCH: dispatch.run_id`；原始响应为 `runId` / `processIncarnation` / `runtimeEpoch` 等 camelCase。另一个独立资源谓词检查中，真实 `exited + exactWorker`、无 residual 的 `external/not_requested` 终端仍不能结算，因为当前规则只接受 Orca-owned `released`。
- 私有证据入口：由 P014 PM 保管的 `eval-harness/evals/ehcg-p014-integration-260928/`。原始退出响应完整哈希 `f79199c81126509135a22cf556086ad72589be3f3d384d857ee210c4aa06ffe6`；不向公开仓复制真实工作树、任务身份、capability 或课程数据。当前复现是历史原件只读重放，不是新 runtime 观察，不补签旧 attempt。
- 目标：让真实新旧 Orca 响应形状被严格消费，并按实际 owner 证明外部终端已关闭且完成结算；保留 `released` 与 `external closed/accounted` 的区别，不改写上游原始状态、不按 missing/失联推断退出。
- 允许范围：本 Skill 的 `scripts/runtime_settlement.py`、必要的 `scripts/provider-lease.py` 结算消费者、对应 runtime/provider 测试和短脱敏 fixtures、`references/23-runtime-settlement.md` 及随行版本文档；实现前现查基线并冻结确切文件。禁止改历史证据、私有 provider 配置、通用权限策略、用户全局 settings 或其他 Skill。
- 可观察验收：真实结构最小脱敏回放可被读取；snake_case/camelCase 双字段出现时必须同值，矛盾、缺项或错绑 Run/Task/Dispatch/runtime/incarnation/terminal 均拒绝。外部终端的正向退出必须与精确 owner、关闭后态、无残留、lease 与 Delivery 证据组合；仅 retained、terminal missing、退出自报或重复旧回执不得完成结算。旧 owned-release、terminal-loss、lease/ack 顺序及递归哈希回归保持。
- 执行与停止：先用私有原件只读复现，再在隔离短分支实现和独立复验；代码通过后才允许一次新鲜 MiniMax 短 live，经 MAO/Orca 且在首个业务文件前冻结 prepare。首个确定性阻塞即保全，不自动追加长课或重复 claim。P014 本地代码接入不等于本卡完成，本卡也不等于课程质量通过。
## TASK-2026-09-29-REMOTE-NODE-M0-E2E — 远程节点派发真机端到端验收

- 状态：`READY`；优先级：`P1`；类型：`verification`；Owner：待领取；来源：DEC-2026-09-29-REMOTE-NODE-DISPATCH（v2.30.0 代码已合，mock 全绿，真机链路未测）。
- 前置：v2.30.0 已进 origin/main；节点侧 `git pull origin main` 使副本版本门放行；节点 ssh 免密 + rsync + gh 可用。
- 目标：在真实节点跑通 checklist：probe ok 全字段 → 容量拒绝真机复现（临时调低 load_threshold → rc=4）→ 不可达 rc=65 → 基线门 rc=3（PM 未 push 时）→ receipt 生成/consume/重放拒/过期拒 → ssh 直调节点 spawn-worker.sh 无 receipt 仍 fail-closed → 完整 E2E（spawn-worker-remote spawn → 节点起真实 claude-code worker 读节点自己的 key、METADATA remote_dispatch.key_source_node 留痕、node- 前缀分支 push + PR、PM gh 可见、PR-fingerprint 验收合并、status 拿到 STATUS 演进、cleanup 后节点 lease/worktree/terminal 清干净）→ 降级演练（节点断开 → 65 → 回落本机路径人工走通）。
- 允许范围：本 Skill references/25 的验收记录、personal config（gitignored）节点参数微调、临时 receipt/probe 参数。禁止：为过门禁改弱 policy。
- 完成标准：checklist 逐项记录证据（命令 + 输出摘要）；不通过项登记为独立卡。
- 结案证据（2026-09-29 深夜，v2.30.4）：**派发管道全链真机验证通过**——probe 全门（ok/容量4/不可达65/基线3/版本门）；receipt 签发→Air 消费→重放拒绝；fail-closed 不变量；两次完整 spawn（Air 本机 lease acquire/finalize + ORCA worktree `~/orca/workspaces/legal-skills/` + `--trust-worktree` 预置生效 + worker 以借用 key 真实运行并修改 README）；PM 监督面（status 软账回写 + `orca terminal read --environment Air` 实读 + 双机 ORCA 终端列表同步）；失败恢复两轮全净（terminal close → lease release `--orca-cli` 显式 → worktree/branch/软账清零）。
- **未完成腿：worker 端到端交付 PR**。两次失败根因：①untrusted worktree（已由 v2.30.4 `--trust-worktree` 解决）；②worker 任务设计与 provider 稳定性——shell 白名单不含 `echo >>` 追加导致 worker 用多步 Edit 绕行，且 GLM（借用 key）当晚限流窗口直接终止会话（无 result 记录）。跟进要求：worker prompt 改用 Edit 工具而非 shell 追加；provider 稳定窗口重试。本腿转记到下方 AUTODISCOVER/调度 epic 前置，不单独阻塞 M0 结案。

## TASK-2026-09-29-REMOTE-NODE-PROMPT-DELIVERY — 远程 worker 任务投递与终端可见性

- 状态：`COMPLETE`（v2.30.5 交付）；优先级：`P1`；类型：`fix`；来源：用户 2026-09-29 观察"派发远程 worker 后对应终端没有真实推进"。
- 根因：v2.30.0-2.30.4 E2E 用 `claude -p` 内嵌任务——`-p` 模式缓冲全部输出到进程结束，终端只见 preamble；worker 实际在干活（transcript 有完整操作）但双机 Orca UI 均不可见；同时绕开 terminal-managed 的 checkpoint 契约（STATUS.json 无人写）。
- 交付：`spawn --prompt-file`（节点 METADATA 取 terminal_handle + `orca terminal send --environment` 跨机投递 + 失败重试 + 软账 prompt 段）；节点段新增可选 `orca_environment`；任务书规范（Edit 工具 + STATUS 契约）入 references/25。
- 真机验证：`NOT_VERIFIED`（等 provider 稳定窗口按新流程重跑完整 E2E 交付腿，与 SMART-SCHEDULING 开局一并做）。

## TASK-2026-09-29-REMOTE-NODE-AUTODISCOVER — ORCA 配对设备自动发现并登记 remote_nodes

- 状态：`READY`；优先级：`P2`；类型：`feature`；来源：用户 2026-09-29——用户说"派发远程 worker"时，检测本机 ORCA 是否配置了远程设备/服务器（`orca environment list` / `orca host list` 即现成清单），有则登记进 personal config `remote_nodes` 供后续直接复用。
- 目标：`spawn-worker-remote.sh discover [--write]`——列出 ORCA 已配对 environment（区分 local/ssh/environment 三类 host），对每个候选探测 ssh 可达性 + bash/git/python3 三道门 + 猜测 remote_root（该设备上本仓库 clone 的常见位置），打印登记建议；`--write` 时把确认项写入 gitignored personal config（占位字段留待用户补阈值），绝不覆盖已有条目。
- 允许范围：spawn-worker-remote.sh 新子命令、remote-node-probe.py 复用、example 文档；不自动 clone、不自动装依赖（那是 provision 的职责且需显式触发）。
- 验收：mock environment list 单测 + 真机对 Air 跑一次 discover 输出正确建议；已存在条目时幂等跳过。

## TASK-2026-09-29-SMART-SCHEDULING — 双账号×双机智能调度层

- 状态：`BLOCKED`（前置：REMOTE-NODE-M0-E2E）；优先级：`P1`；类型：`feature`；来源：用户 2026-09-29 定稿——两 GLM 账号（数据源=用户 fork 的 cat-xierluo/zcode-cli 项目，可读双账号额度 + 5h/周刷新卡；~/bin/zcode-quota 旧脚本已弃用）× 两机器（probe 容量）→ 动态分流：避开账号并发限制、避开单机终端过载、刷新卡临期优先消耗（token 效率最优）。用户已授权该 epic 开发期额度放心派发，且要求本 epic 本身用 worker 并发推进（M0 远程派发的首战）。
- 目标：在 spawn 决策前增加调度层——输入任务流，状态=账号侧（以 cat-xierluo/zcode-cli fork 的账号/额度/刷新卡读取为准，评估替换或扩展 quota_summary_zcode 生产方/references/21）× 机器侧（remote-node-probe + 本机 mem budget）× 在途（lease + remote-dispatches 软账），输出=backend×provider×机器 的派发建议；刷新卡临期（5h 窗口）优先吃、账号并发各自限流、机器终端数各自限流。
- 允许范围：route_suggest.py/quota_preflight.py 扩展、新调度脚本、personal config schema 演进、references 新页；不得绕过现有门禁。
- 验收：设计卡先行（数据源矩阵 + 调度判据 + 降级矩阵）；实现后 mock 调度单测 + 真机双账号双机实测各一轮。

## TASK-2026-09-29-DROP-CODEBUDDY-QODERWORK — 下线 CodeBuddy 与 QoderWork backend

- 状态：`READY`；优先级：`P2`；类型：`removal`；来源：用户 2026-09-29 指示「QoderWork 这部分不需要了，包括 CodeBuddy，直接通过 PR 删掉」。
- 目标：独立 PR 从 origin/main 删除两个 backend 全链：harness-backend-policy.json hosts 与候选签名策略位、spawn-worker.sh backend case、render-runtime-profile.sh 分支、qoderclicn-interactive-spawn.sh、config/codebuddy-auth-first-run.sh、references/07/08、example 配置段、SKILL.md 提及、相关测试同步、CHANGELOG。保持 receipt/远程派发等 v2.30.0 新能力不受影响。
- 注意：与 v2.30.0 同文件（policy/spawn），必须在 v2.30.0 PR 合并后基于新 main 开分支，避免冲突。

## TASK-2026-09-24-CLAUDE-AUTO-SHELL — 恢复 Claude Code 原生 auto 的普通命令权限

- 状态：`COMPLETE`；优先级：`P1`；类型：`security-policy/usability`；Owner：Codex `/root`；来源：用户反馈 Claude Code auto Worker 的定向 unittest 被编排层 `SHELL_COMMAND_NOT_ALLOWLISTED` 拦截。
- 候选合同：分支 `fix/claude-auto-worker-shell`；Worktree `mao-claude-auto-shell/legal-skills`；integration base `origin/main`；immutable start `f36f7c0cc28e0bbafac08e90f995b6391390d85d`。
- 目标：仅对显式 auto 且 hook 生效的 Claude Code Worker，让普通 Bash 由原生 auto/settings 决定；保留安装、Orca 协议、tracked 删除和受保护 Git 操作的编排边界。其他 backend 与非 auto 模式保持精确白名单。
- 允许范围：本 Skill 的 `dependency-install-guard.py`、spawn/metadata/provider 包装、定向测试、`SKILL.md`、worker prompt、运行时参考、`DECISIONS.md`、`CHANGELOG.md`、`TASKS.md`，以及根 README 对本 Skill 的版本索引。
- 验收：原报错命令在 Claude auto 策略下不再由 hook 拒绝；安装、强推、主干 push、`gh pr merge`、tracked 删除与其他 backend 拒绝仍有效；spawn snapshot/METADATA/receipt 策略一致；运行定向门禁与 Skill 审查。真实 Claude auto 分类器是否最终批准该命令须在线实测，未测标 `NOT_VERIFIED`。
- 交付记录：PR #192；review 发现并修复无关文案与受保护命令解析缺口；GitHub `harness-regression` 和 `runtime-settlement` 检查均通过。
- 本地证据（2026-09-24）：`test-dependency-install-guard.sh` 190/190；`test-spawn-worker-metadata.sh` 31/31；`test_worker_delivery_prompt.py` 9/9；provider 路由回归 29/29；Python 编译与 Bash 语法通过；`git diff --check` 通过；skill-lint Harness Failure Audit 0 finding，Security Scan 0 critical / 0 high（其他命中主要为既有测试 fixture 与受控脚本能力）。真实 Claude Code auto 分类器对该命令的最终决策、真实 Orca/provider 生命周期为 `NOT_VERIFIED`。审查时移除无关的 subagent 通道选择文案，并修复 auto 门禁对重定向、赋值前缀和复合语法的误放行。候选分支独立于原工作树；原工作树其他 Skill 的既存修改未纳入本候选。

独立维护池另有 `HERMES-BASH-VERSION-GATE` 可领取；它只增加入口版本诊断，不得顺带处理首次 trust/MCP 交互或 GitHub merge 恢复。

## TASK-2026-09-14-GIT-RM-AUTHORITY — 明确 tracked 文件删除权限

- 状态：`COMPLETE`；优先级：`P1`；类型：`security-policy`；Owner：Codex `/root`。
- 候选合同：分支 `codex/mao-git-rm-authority`；Worktree `/private/tmp/legal-skills-mao-git-rm-authority`；integration base `origin/main`；immutable start `67a5b6c35d76f2002806af781f876e1730599877`。
- 交付证据：PR #180；实现 commit `957d545700c4c23499b946bdf1f60155a4e95198`；独立 adversarial review `APPROVE`。依赖门禁在 Homebrew Bash 与 macOS Bash 3.2 各 170/170，metadata 各 31/31，worker prompt 9/9；完整维护矩阵主体通过，`smoke-orca-worker.sh` 因本机 Orca 缺少 `terminal.multiplex.v1` 按设计 SKIP(77)，fake control-plane smoke 通过；Skill quick validate 与 harness audit 通过，security audit 为 0 critical / 0 high。真实 Orca/provider supervised 全生命周期仍为 `NOT_VERIFIED`。
- 来源修正：原卡名为 `MINIMAX-LANE-ALLOWLIST`，但复核证明 provider 并非根因。合同中的 `node <script>` 和 `gh pr create` 已可执行；失败来自 Worker 改写精确命令，以及 `git rm <tracked>` 尚无授权分类。
- 目标：为 tracked 文件删除建立窄且可审计的合同；同时让 Worker prompt 明确验证命令必须与 authority receipt 完全一致，不得自行加 `export`、`cd`、命令替换或多行 body。
- 已冻结设计：内置分类器只允许单段命令 `git rm -- <一个 repo-relative tracked file>`；必须命中启动时冻结并进入 authority snapshot 的 `allowed_write_paths`。高风险分类先于精确 `allowed_shell_commands`，因此 `--allow-cmd` 不能覆盖 `-r`、`-f`、`--cached`、多路径、目录/submodule、pathspec、Shell 展开或范围外拒绝。
- 允许范围：`scripts/dependency-install-guard.py`、冻结 `allowed_write_paths` 所需的 spawn/authority 生产链及其测试、`templates/worker-prompt.md`、`scripts/orca-supervised-protocol.sh`、`scripts/test_worker_delivery_prompt.py`、`references/02-runtime-dependencies.md`、`references/14-pm-orchestrate.md`、必要的版本与任务同步。
- 验收：最小 tracked fixture 正例；untracked、范围外、`..`、glob、`-r`、`-f`、远端删除混淆和复合命令反例；拒绝时索引与工作树不变。
- 定向验证：`bash scripts/test-dependency-install-guard.sh`、`bash scripts/test-spawn-worker-metadata.sh`、`python3 scripts/test_worker_delivery_prompt.py`，随后执行完整维护矩阵。
- 非目标：不开放任意 Shell，不把 verification contract 变成通用命令授权。

## TASK-2026-09-13-ORCA-CROSS-PM-HANDOFF — 跨 PM 基线通知与任务交接

- 状态：`RESTART_REQUIRED`；优先级：`P1`；类型：`implementation`；Owner：未领取。
- 前置：`ORCA-COMMS-CONTRACT`（PR #153）与 `ORCA-WORKER-ASK-REPLY`（PR #154）已完成。
- 状态修正：旧卡记录的本地分支/Worktree 已不可用，冻结基线停留在 `9fec934c`；不得继续标记 `IN_PROGRESS`，也不得复用旧 Run/Task/Dispatch 或临时回执冒充当前候选证据。
- 下一动作：从最新 `origin/main` 重建一页 Harness/消息合同，重新核对当前 Orca CLI/runtime，再新建短分支和独立 Worktree。旧双 Run shell 试验只能作为设计输入。
- 目标：在两个独立 PM session 之间完成 `offer → accept/reject → immutable handoff receipt`，绑定 source/target task、repo、base ref、immutable head、影响范围、已验门禁、未验证项、唯一下一动作和失效条件。
- 必须覆盖：错误/关闭 sender、recipient 不存在、runtime/repo/main/head 漂移、重复交接、接收方沉默、幂等恢复，以及 Codex App task 与 Orca Run 的边界。
- 权限边界：交接消息不转移文件、Shell、安装、Git/merge 或 lifecycle 权限；接收方必须显式接受，过期后重新交接。
- 非目标：不建立跨平台全局总线，不自动合并 PR，不用广播代替 ownership ledger。

## TASK-2026-09-13-ORCA-PEER-COMMS — 受限同 Run Worker/Reviewer 协作

- 状态：`BLOCKED`；阻塞于：`ORCA-CROSS-PM-HANDOFF`；优先级：`P1`（作为 P1 通信 E2E 的必要前置）；Owner：未领取。
- 目标：允许同 Run 内的只读事实请求、blocker、具名依赖就绪通知和 review 证据引用；默认由 PM 中转，只有身份和审计归属可证明时才评估 direct-peer。
- 禁止：通过 peer 消息修改任务范围、owner、allowed paths、安装/Git 权限、完成 verdict 或资源清理决策；禁止自由群聊和无业务价值广播。
- 解锁条件：Cross-PM Handoff 合并后，先复用其身份、correlation、幂等和失效合同，再冻结本任务 allowed paths 与验证矩阵。

## TASK-2026-09-13-ORCA-COMMS-E2E — 跨 Session 通信真实验收矩阵

- 状态：`BLOCKED`；阻塞于：`ORCA-CROSS-PM-HANDOFF`、`ORCA-PEER-COMMS`；优先级：`P1`；类型：`reusable_verification`。
- 目标：分别证明 `durably_enqueued → delivered_visible → consumed → replied → action_started → business_completed`，并覆盖重启、timeout、Delivery 重放、consumer fencing、handle/runtime 替换和资源结算。
- 验收：离线 fake CLI 故障注入与至少一个真实 Orca 多 session 场景；只有真实启动受支持 Agent 并观察 `worker_done → Delivery → PM 验收 → settlement → ack`，才能标记对应 backend E2E 已验证。
- 非目标：不把 shell session 消息测试扩大为 provider 全生命周期结论。

## TASK-2026-09-20-HERMES-BASH-VERSION-GATE — 入口 Bash 版本诊断

- 状态：`READY`；优先级：`P2`；类型：`diagnostics`；Owner：未领取。
- 已关闭前因：v2.27.4 已修复中文全角括号邻接变量导致的 `set -u` 崩溃；该问题在 Bash 5.3.3 同样复现，不能归因于 macOS Bash 3.2。
- 目标：对确实使用 Bash 4+ 语法/能力的生产入口增加统一、早期、可操作的版本诊断，明确 macOS 默认 Bash 3.2 的升级路径；不把普通语法错误、环境缺失或 runtime 失败误报成版本问题。
- 允许范围：先盘点实际入口与最低版本；保留 `pm-monitor.sh`、`check-dependencies.sh` 和 `references/02-runtime-dependencies.md` 已有诊断，只给遗漏的真实 Bash 4+ 生产入口补统一机器码与安装提示；不得批量改写全部脚本 shebang。
- 验收：Bash 3.2 fixture/替身得到稳定机器码与安装提示；受支持版本继续原行为；诊断发生在 worktree/provider/terminal/Orca mutation 前；完整维护矩阵通过。
- 非目标：不处理 Claude 首次 trust/MCP/import 交互，不改变 permission mode，不处理 GitHub merge 失败恢复。

## TASK-2026-09-20-HERMES-FIRST-RUN-AUTH-DESIGN — 首次交互的安全接管合同

- 状态：`PARKED`；原因码：`NEEDS_SAFE_DESIGN`；优先级：`P2`；Owner：未领取。
- 问题：Claude CLI 首次 trust、MCP/import 或相似交互可能阻塞无人值守 Worker；现有证据不足以安全自动回答。
- 解锁条件：先提交设计候选，列出每类真实交互的可识别证据、显式用户授权、隔离配置目录、超时/人工接管和清理合同，并给出零真实凭证的 fixture。
- 禁止方案：默认 `--dangerously-skip-permissions`、预写用户全局 trust、修改真实凭证、按模糊 pane 文本自动按键，或把首次交互成功扩大为 provider 生命周期已验证。

## TASK-2026-09-20-HERMES-GITHUB-MERGE-RECOVERY — GitHub 失败恢复合同

- 状态：`PARKED`；原因码：`NEEDS_SAFE_DESIGN`；优先级：`P2`；Owner：未领取。
- 问题：merge API 的 403/404/TLS/回执丢失可能分别代表权限、路径、网络或结果不确定；当前不能用同一 fallback 处理。
- 解锁条件：基于 `git-workflow` 冻结错误分类、PR diff/checks/review 证据、远端状态复验、幂等恢复和结果不确定状态；每类必须有零 mutation 反例与已发生 mutation 的 reconciliation 用例。
- 禁止方案：把 raw push main 设为静默默认 fallback、在 merge 结果未知时重复 mutation，或绕过分支保护和用户既定的 PR-first 顺序。

## TASK-2026-09-16-HERMES-PM-REVIEW-BATCH2 — 第二批纪律观察

- 状态：`OBSERVE`；优先级：`P2`；可计数证据：`0/10`。
- 规则：累计至少 10 条带 PR、提交或事件记录指针且按共同根因去重的证据后，再决定是否进入正文或脚本；在此之前不逐点 patch。
- 既有五个主题（stale base、派发后监测、宿主 subagent 边界、PM 收口例外、GitHub 通道降级）因任务源中没有可复查指针，仅作为线索保留，不计入阈值。任何新增观察必须附不可变证据和它与现有任务不重复的理由。

## TASK-2026-09-13-ZCODE-RUNTIME-ADAPTER — ZCode 真实宿主接入

- 状态：`PARKED`；原因：独立 ZCode owner/会话；优先级：`P1`。
- 已完成基础：PR #147 已合并，driver safety 的 27 个 Shell 断言和 59 个 Python 断言构成安全底座。
- 剩余：真实 CLI 配置入口、RuntimeAdapter、模型/套餐读回、双实例隔离和真实 provider 生命周期。旧卡中“PR #147 仍为 draft/未合并”的状态已作废。
- 恢复条件：用户或既有 ZCode owner 明确恢复；从最新 `origin/main` 新建候选，不读取或改写其他会话 Worktree，不把 stub 测试冒充真实 provider 验证。

## TASK-2026-09-05-ZCODE-QUOTA-PHASE2 — ZCode 额度消费链第二期

- 状态：`PARKED`；恢复要求：`REBASE_REQUIRED`；优先级：`P2`；原因：旧候选基于 v2.24.0，且曾发生未授权 Orca Setup 安装。
- 已解除前置：PR #151 已把 Orca Setup 固定为 `--setup skip`，但不使旧候选自动有效。
- 恢复条件：独立 ZCode owner 基于最新 `origin/main` 重建合同，重新确认个人 Coding Plan 5h 观测的身份边界、离线 fixture 与允许文件；真实请求、套餐切换、安装、远控和自动用卡仍需单独授权。

## TASK-2026-09-19-INSTRUCTION-STABILITY-CONTRACT — 建立机器可读约束追踪

- 状态：`PARKED`；优先级：`P2`；类型：`quality-infrastructure`。
- 问题：当前 `skill-lint instruction_stability_gate.py assess` 因缺少 `config/instruction-stability-contract.json` 只能给出 `INSTRUCTION_STABILITY_NOT_VERIFIED`；这不等于已发现具体业务错误。
- 恢复条件：先选择少量真正 hard 的跨会话/权限/完成约束，为每条建立稳定 ID、active checker、正确 artifact stage、最小违规反例和合法近似正例；正式稳定性声明还需要候选外 evaluator-signed baseline/held-out 与至少三轮真实产物。
- 非目标：不为消除扫描告警而给全部自然语言机械加锚点，不用静态 grep 冒充 runtime/state 验证。

## 已完成

| 任务 | 状态 | 不可变证据 |
|---|---|---|
| tracked 文件删除权限 | `COMPLETE` | PR #180；实现 commit `957d545700c4c23499b946bdf1f60155a4e95198`；独立 adversarial review `APPROVE`；两套 Bash 门禁各 170/170，security audit 0 critical / 0 high；真实 online lifecycle 仍为 `NOT_VERIFIED` |
| WorkerList 精确分页清理 | `COMPLETE` | PR #178；实现 commit `83488cdddc6606e9b772007452420cc1dd81734e`；独立 review `APPROVE`；维护矩阵 143 命令通过，Bash 5.3 / 3.2 专项各 211/211；真实 online lifecycle 仍为 `NOT_VERIFIED` |
| Completion Authority 收口 | `COMPLETE` | PR #145，merge `c7501e99` |
| ZCode driver safety 基础 | `COMPLETE` | PR #147，merge `f763d3dc`；RuntimeAdapter 另卡保留 |
| Orca Setup 安装策略 | `COMPLETE` | PR #151，merge `b368d62d` |
| Orca 通信合同 | `COMPLETE` | PR #153，merge `49f55385` |
| Worker ask/reply | `COMPLETE` | PR #154，merge `9fec934c` |
| Hermes PM 宿主识别 | `COMPLETE` | PR #155，merge `ffb47a8a` |
| Hermes 全 backend 授权 | `COMPLETE` | PR #156，merge `6645c0e8` |
| base-ref 引用合同 | `COMPLETE` | PR #165 / #173，merge `a2df4a5f` / `41072b9e` |
| `NON-ZCODE-CLOSEOUT` | `COMPLETE` | 其中曾停放的 PR #145 已于后续修复后合并 |
| `EXISTING-BRANCH-RECONCILE` | `COMPLETE` | PR #145/#147 均已合并；旧本地候选不得继续作为活动分支 |

## Agent 接手模板

领取任务时在 PR 正文或任务卡更新中填写：

```text
task_id:
owner/session:
status: READY -> IN_PROGRESS
branch_lifecycle: ephemeral-worker
branch/worktree:
integration_base_ref: origin/main
immutable_start_sha:
allowed_paths:
forbidden_paths:
verification_commands:
external_side_effects_authorized:
evidence_boundary:
blocker_and_recovery:
```

交付时补充 immutable head、PR URL、review verdict、真实测试结果、仍为 `NOT_VERIFIED` 的层、资源终态，并把任务改为 `COMPLETE`、`PARKED` 或 `RESTART_REQUIRED`。不要仅写“已完成”或保留失效 Worktree 路径。

## 2026-09-30 独立复核补充

仅登记修复与验收任务，未修改实现；原有执行顺序和其他任务状态保持。测试限隔离合成夹具，真实 SSH/provider/Orca 全链未验。

### TASK-2026-09-30-REMOTE-RECEIPT-ATOMIC-CONSUME — 修复一次性回执并发重复消费

- 状态：`READY`；优先级：`P1`；类型：`security-policy/concurrency`；Owner：未领取；来源：2026-09-30 当前主干只读审计。
- 基线证据：`8c529516db1a5ad80c525593a0e162ef7a5751ad`，`scripts/remote-dispatch-receipt.sh:214-255`；两个消费者打开同一 receipt 后等待原 inode flock，首次消费以 os.replace 换 inode，第二个仍读旧未消费值。隔离夹具两者均返回0并接受同一 nonce/hash；未启动真实 Worker。
- 目标：同一 receipt/nonce 并发竞争最多一个消费者成功；后续消费者必须拒绝，不依赖下游 branch/lease 偶然拦截。
- 允许范围：`scripts/remote-dispatch-receipt.sh`、对应回执测试、必要的 `references/25-remote-node-dispatch.md` 与随行文档；禁止改弱 PM/backend 交集、TTL、字段绑定或覆盖其他会话资源。
- 可观察验收：固定“两个进程已打开同一原件”的同步屏障反例，断言恰好一个rc0、另一个非0；顺序重放、过期、字段错绑、损坏JSON、崩溃/中断恢复保持fail-closed；锁方案须在原子替换后仍共享同一锁身份。保留原始失败日志，不能仅跑顺序重放。
- 验证边界：当前证明限回执消费函数；真实SSH/Orca/provider生命周期为`NOT_VERIFIED`。领取时从最新origin/main另开短分支冻结新基线。

### TASK-2026-09-30-REMOTE-CLEANUP-CLI-CONTRACT — 对齐远程收口与真实清理合同

- 状态：`READY`；优先级：`P1`；类型：`integration/resource-settlement`；Owner：未领取；来源：2026-09-30 当前主干只读审计；关联：REMOTE-NODE-M0-E2E、SMART-SCHEDULING。
- 基线证据：`8c529516db1a5ad80c525593a0e162ef7a5751ad`，`scripts/spawn-worker-remote.sh:567-587` 传 `--project <root> <session>`；`scripts/pm-cleanup-worker.sh:24-78` 不接受位置session且要求完整delivery-bound字段。原样callee解析即rc64；现有mock在匹配脚本名后直接CLEANUP_OK，未验证接口。
- 目标：远程正常交付与失败回收分别走现有合法合同；资源清理可重入，软账仅在节点精确终态证明后移除。
- 允许范围：`scripts/spawn-worker-remote.sh`、必要的metadata/ledger字段与对应测试、`references/25-remote-node-dispatch.md`；若需改callee，先冻结明确最小范围。禁止通过移除expected-tip/PR/delivery/lifecycle校验绕过失败；禁止用STATUS自报代替交付权威。
- 可观察验收：mock SSH传输层后实际执行生产callee参数解析和必要验证；正向包含project/session/worktree/branch/pr/expected-tip/delivery-mode/delivery-commit，dry-run与execute均被核验；错绑、dirty、active、long-lived、PR查询失败保留资源及软账。gh事实查询绑定local-project对应canonical repo，显式覆盖closed/merged状态；从其他cwd调用不串仓。失败后的安全重试不得重放merge/push。
- 验证边界：当前已复现CLI必败，未执行真实清理。保留既有M0人工恢复证据，不把人工清理成功改写为wrapper E2E通过；SMART-SCHEDULING开局先核此卡与未完成交付腿。

### TASK-2026-09-30-REMOTE-HOST-PATH-BOUNDARY — 分离PM与节点的路径事实

- 状态：`READY`；优先级：`P2`；类型：`runtime-compatibility`；Owner：未领取；来源：2026-09-30 当前主干只读审计。
- 基线证据：`8c529516db1a5ad80c525593a0e162ef7a5751ad`，`scripts/spawn-worker-remote.sh:258-264` 用PM本地-x复验node bash_path；`:33,299-312` 将PM HOME派生的Orca路径写入node trust配置。实际cmd_spawn在mock probe OK且node-only路径时rc64；原样TRUST_PY在隔离node HOME写出PM路径。
- 目标：节点可执行文件和HOME/Orca工作区以节点事实或实际创建后METADATA为准，PM不据本地同路径猜测。
- 允许范围：`scripts/spawn-worker-remote.sh`、必要的`scripts/remote-node-probe.py`字段、对应测试及远程使用文档；不扩大默认trust授权范围。
- 可观察验收：PM不存在但节点可执行的bash≥4路径能派发；节点不存在/非绝对/版本不足仍拒绝；PM与node用户名和HOME不同的fixture，只信任节点实际工作区，PM路径不写入node配置；无--trust-worktree不写配置。测试调用真实cmd_spawn参数与分支逻辑，不能只字符串断言。
- 验证边界：当前为隔离fixture与生产片段，未跑真实跨机；真实双主机路径差异验收仍`NOT_VERIFIED`。
