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

## TASK-2026-09-24-CLAUDE-AUTO-SHELL — 恢复 Claude Code 原生 auto 的普通命令权限

- 状态：`IN_PROGRESS`（候选分支待集成）；优先级：`P1`；类型：`security-policy/usability`；Owner：Codex `/root`；来源：用户反馈 Claude Code auto Worker 的定向 unittest 被编排层 `SHELL_COMMAND_NOT_ALLOWLISTED` 拦截。
- 候选合同：分支 `fix/claude-auto-worker-shell`；Worktree `mao-claude-auto-shell/legal-skills`；integration base `origin/main`；immutable start `f36f7c0cc28e0bbafac08e90f995b6391390d85d`。
- 目标：仅对显式 auto 且 hook 生效的 Claude Code Worker，让普通 Bash 由原生 auto/settings 决定；保留安装、Orca 协议、tracked 删除和受保护 Git 操作的编排边界。其他 backend 与非 auto 模式保持精确白名单。
- 允许范围：本 Skill 的 `dependency-install-guard.py`、spawn/metadata/provider 包装、定向测试、`SKILL.md`、worker prompt、运行时参考、`DECISIONS.md`、`CHANGELOG.md`、`TASKS.md`，以及根 README 对本 Skill 的版本索引。
- 验收：原报错命令在 Claude auto 策略下不再由 hook 拒绝；安装、强推、主干 push、`gh pr merge`、tracked 删除与其他 backend 拒绝仍有效；spawn snapshot/METADATA/receipt 策略一致；运行定向门禁与 Skill 审查。真实 Claude auto 分类器是否最终批准该命令须在线实测，未测标 `NOT_VERIFIED`。
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
