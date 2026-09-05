# 派发、交付与验收合同

> 仅在准备派发、验收交付或处理验收失败时读取。`SKILL.md` 只保留门禁顺序，本文件承载字段与失败语义。

## 1. 派发价值合同（`dispatch-value-gate.v2`）

额度和并发只用于路由已经成立的任务，不能生成任务。每个任务必须声明：

- `value_kind`：`implementation`、`reusable_verification`、`merge_gate` 三选一。
- `problem_target`：具体问题、模块或 PR，不接受占位调查。
- `decision_or_gate_changed`：产出会改变的行为、判断或门禁。
- `engineering_assets` / `doc_assets`：实现与验证资产至少声明一个非文档工程资产；`merge_gate` 改用 `gate_target.pr` + 40 位 `gate_target.head_sha`。
- `verification_commands`：实现与验证资产必填；merge gate 的证据为 accept/reject 决策。
- `worker_pr_policy`：`worker_pr`、`integration_pr` 或 `no_worker_pr`。`integration_pr` 必须具名 `integration_target`；`no_worker_pr` 仅用于 merge gate。
- `value_identity`：波内去重身份；显式重复或同 kind + target 被包含均拒绝。
- `consumer`、`consume_by`、`expiry`、`observable_acceptance`、`resource_owner`：消费者、消费期、到期处置、可观察验收与外部资源责任。

`DRAFT`、docs-only、research、简单调查、纯文案和格式清理不可获得独立 worker/worktree/PR。文档只能作为 implementation、reusable verification 或 merge decision 的随行资产，或由现有角色在无派发成本下处理。

派发前用示例模板形成 JSON：

```bash
python3 scripts/dispatch-value-gate.py <dispatch-spec.json>
```

非零退出不得创建 worker。PR 数、行数、token、commit 数和忙碌度都不是价值信号。

门禁通过后，把同一份合同直接绑定到 spawn，避免人工转抄遗漏或改写验证命令：

```bash
bash scripts/spawn-worker.sh ... \
  --verification-contract <dispatch-spec.json> \
  --verification-task-id <task_id>
```

脚本要求 task_id 恰好匹配一次，并把 `verification_commands` 每项作为完整字符串写入精确 Shell allowlist；`implementation` / `reusable_verification` 解析为空时在派发副作用前拒绝。不要同时传 `--verify-cmd` 制造两个权威来源。

## 2. 交付后价值门

验收或接 PR 前，用派发时同一份 spec 检查真实交付：

```bash
python3 scripts/worker-value-postflight.py \
  --spec <dispatch-spec.json> --task-id <ID> \
  --repo <repo> --base <sha> --head <sha> \
  --evidence <evidence.json>
```

离线 patch 模式改用 `--diff <patch> --delivery-head <40-hex>`。门禁要求：

- 至少一个声明的非文档工程资产真的发生变更；文档路径即使位于工程目录下，也不能冒充工程资产。
- 所有实际路径位于声明资产范围；文档只可经 `doc_assets` 随行。
- evidence 中每条声明验证命令都有 exit 0 记录。
- `verified_head` 是 40 位 commit，并等于真实 Git head 或 patch 模式的 delivery head。
- `merge_gate` 的 head 还必须等于 `gate_target.head_sha`；零 diff 只允许给具名 PR/head 的 merge gate，并必须产出 accept/reject 及消费者。

大 diff、绿色自测或 worker 自报不能挽救越界、无消费或未绑定 head 的交付。

## 3. 角色分离验收（`review-acceptance-gate.v1`）

非平凡 `implementation` / `reusable_verification` 默认由不同 dispatch/session 的 implementer 与 reviewer 收口。PM 负责方向、合同、粗粒度巡检、风险升级、immutable-head 记账与最终收口，不在独立证据一致时重复逐行审查或补丁实现。

```bash
python3 scripts/review-acceptance-gate.py <review-acceptance.json>
```

模板：`templates/review-acceptance.example.json`。接受条件：

- implementer 与 reviewer 的 `dispatch_id`、`session_id` 均非占位且互不相同。
- `delivery_head` 与 `reviewed_head` 是同一个 40 位 commit。
- verdict 为字面 `ACCEPT`，`blocking_findings` 为空。
- `verification_evidence` 是非空 `{command, exit_code}` 数组且全部 exit 0；纯文字叙述无效。
- `review_consumer` 与 `review_expiry` 已具名。

PM 例外只允许四种 `reason_code`：`worker_failure`、`conflicting_verdicts`、`security_or_high_risk_evidence`、`control_plane_recovery`。必须同时声明 `kind`（`pm_implementation` / `pm_deep_review`）、非空 `reason` 与 `authorized_by`；通过后标记 `ordinary_delivery: false`，不得计为常规交付。

### Reviewer 写范围与证据预算

- reviewer 派发必须使用 `--role reviewer`；默认只写自身 Session Context。
- 需要修复被审分支时，任务合同必须显式授予 `--review-repair-grant <授权来源>`；无授权却传 `--allow-paths` 在任何副作用前拒绝。
- `config/*.local.yaml` 永远不可写，授权也不例外。
- 证据优先级固定为 exact HEAD → diff → 受影响文件。拿到 diff 后不整份重读大型 canonical 文档，只按触及小节读取。
- 外部 CI 只在 verdict 依赖时查询；环境/时序失败最多一次归因复跑。仍失败输出 `NOT_VERIFIED` 或 `REJECT`，不得第三次盲试。
- PM 可发 budget stop；预算耗尽不会放宽通过条件。

## 4. 验收失败分类（`acceptance-recovery.v1`）

唯一分类权威是 `scripts/acceptance-recovery.py`：

| 分类 | 典型情形 | 动作 |
|---|---|---|
| `internal_recoverable` | PR checks 确定性失败、交付越界、缺验证证据、review blocker、合法 docs-only 验收修复 | 预算内 `repair`，随后 `re_review`；默认最多 2 个失败 episode |
| `external_dependency` | 配额耗尽、上游不可用、缺用户资产或授权 | 立即 `park` |
| `safety_unknown` | 事实歧义、身份/head 不可证、安全高风险、runtime 损坏 | 立即 `park` |

表外信号一律归 `safety_unknown`。同一 episode 内重复 reconcile 不重复计数；预算耗尽才把 internal failure 泊车。Autopilot runtime 和 heartbeat adapter 必须导入这一张表，禁止另写 `any gate failure => park` 分支。

## 5. docs-only 验收修复窄通道（`acceptance-repair.v1`）

该通道只服务“既有具名 PR 的验收只差文档修复”，不是通用 docs-only 后门。模板：`templates/acceptance-repair.example.json`。

```bash
python3 scripts/acceptance-repair-gate.py preflight \
  --spec <spec.json> --registry <ledger.json>

python3 scripts/acceptance-repair-gate.py postflight \
  --spec <spec.json> --registry <ledger.json> \
  --evidence <evidence.json> <diff-source-arguments>
```

合同必须钉扎既有 PR、branch 与 40 位 head；`integration_target` 必须等于 target branch；blocker 是 ID 唯一的结构化对象；`file_scope` 全为文档路径；具名 consumer、expiry、verification commands、repair owner 和独立 re-review 身份。registry 保证同 PR 只有一个活跃 owner，并拒绝同 head 或 blocker 的重复修复。`repair_attempts_used >= 2` 时拒绝派发。

postflight 额外拒绝 head 漂移、范围外或非文档修改、零 diff、blocker 未全部解决、验证失败与 owner 不一致。patch 模式无法证明 head 谱系，一律拒绝。

## 6. 最小回归

```bash
bash scripts/test-dispatch-value-gate.sh
bash scripts/test-worker-value-postflight.sh
bash scripts/test-review-acceptance-gate.sh
bash scripts/test-blocker-recovery.sh
```

修改任一门禁或模板后，再按 `references/19-maintainer-validation.md` 执行完整回归。
