# 派发、交付与验收合同

> 仅在准备派发、验收交付或处理验收失败时读取。`SKILL.md` 只保留门禁顺序，本文件承载字段与失败语义。

## 1. 派发价值合同（`dispatch-value-gate.v2`）

额度和并发只用于路由已经成立的任务，不能生成任务。每个任务必须声明：

- `value_kind`：`implementation`、`reusable_verification`、`merge_gate`、`business_artifact` 四选一。
- `problem_target`：具体问题、模块或 PR，不接受占位调查。
- `decision_or_gate_changed`：产出会改变的行为、判断或门禁。
- `engineering_assets` / `doc_assets`：实现与验证资产至少声明一个非文档工程资产；`merge_gate` 改用 `gate_target.pr` + 40 位 `gate_target.head_sha`。
- `verification_commands`：实现与验证资产必填；merge gate 的证据为 accept/reject 决策。
- `worker_pr_policy`：`worker_pr`、`integration_pr` 或 `no_worker_pr`。`integration_pr` 必须具名 `integration_target`；`no_worker_pr` 可用于 merge gate 或不需要 Git PR 的业务产物。
- `value_identity`：波内去重身份；显式重复或同 kind + target 被包含均拒绝。
- `consumer`、`consume_by`、`expiry`、`observable_acceptance`、`resource_owner`：消费者、消费期、到期处置、可观察验收与外部资源责任。

`DRAFT`、没有明确消费者的占位调查、维护文档和纯格式清理不可获得独立 worker/worktree/PR。用户委托的研究、设计、文书与报告使用下述业务合同，不因文件是文档而被拒绝；工程任务的随行文档仍使用 `doc_assets`。

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

### 并发计数与项目收紧

用 `python3 scripts/dispatch-value-gate.py --describe-policy` 只读查看同一代码常量的默认值。它不读取运行库存、不创建资源，也不是派发成功回执。

v2 的可选 `capacity` 块包含 `active_workers`（现有活跃数，不含本波）、`worker_limit`（项目上限，只可收紧当前模式默认值，0 表示暂停新派）、具名 `scope` 与库存证据 `inventory_ref`。提供时四项须完整，布尔、负数、非整数或扩大上限均拒绝；门以 `active_workers + len(tasks)` 核总量。未提供时旧合同仍只核 `len(tasks)`，输出 `candidate_only`，不能当成全机可用性证明。快照的真实性和跨 PM 协调由原 owner 核实；合同回放不重新声明当前库存，内存 slots 和 provider lease 仍分别检查。

### 业务产物合同

显式选择 `value_kind: business_artifact`，仍须满足 READY、波次去重、消费期限及资源归属。`business_artifact` 块声明：

- `purpose_type`：`research_report`、`design_document`、`legal_document` 或 `business_report`；同时具名 `purpose` 与原请求 `request_ref`。
- `sources`：唯一 `source_id` 与可回查 `reference`；这些是待独审核对的来源声明，脚本不会联网或替代事实核查。
- `artifacts`：每项精确相对 `path`、`modality`、`media_type`；不得通配、路径穿越或使用符号链接，不再同时声明 `engineering_assets/doc_assets`。
- `acceptance_criteria`：唯一 `criterion_id`、具体 `standard`、对应 `artifact_paths/source_ids`，须覆盖全部产物与来源。
- `acceptance_mode`：`content_review` 使用显式空 `verification_commands`；`verifier` 使用非空真实命令及退出码。两种模式都须内容独审，不能编造测试命令凑数。

`content_review` 绑定到 spawn 后不回退项目自动测试发现，也不能同时要求 `--require-verification`。文件所有权、真实权限、内存与 backend 门禁继续独立生效。

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

### 业务交付与独审证据

先只读观察实际文件：

```bash
python3 scripts/business_artifact_contract.py \
  --spec <dispatch-spec.json> --task-id <ID> \
  --artifact-root <canonical-absolute-directory>
```

输出 `observed_draft` 和 `accepted: false`，仅生成 `delivery`，不得当作独审或完成回执。当前支持 UTF-8 文本/Markdown/HTML、PDF、PNG、JPEG、DOCX/PPTX/XLSX 及通用二进制。文件逐块读取；上限为单文件 64 MiB、32 个产物、128 个来源及 128 条标准，观察 CLI 的 spec 上限 1 MiB。PDF/图片/Office 仅核基础文件签名；Office 的 ZIP 签名不证明文件可打开，独审仍须按业务标准验证渲染和内容。

业务后门用 `--artifact-root <canonical-absolute-directory>` 替代 Git/patch 参数；Git 与非 Git 目录均读取实际交付文件，不要求伪造提交或代码变更。`delivery` 清单绑定原 task 合同、来源、根目录、每个文件 SHA-256 与字节数，交付身份为 `artifact-sha256:…`。文件变化须重新观察并重新独审。

`evidence` 包含 `delivery`、具名 `implementation`、`content_review` 和 `executed`。独审记录须绑定同一 `delivery_identity/sources_sha256`，逐条标准提供 `PASS`、具体依据及原 artifact/source IDs，并逐来源提供 `source_checks`。作者与审查者的 `dispatch_id/session_id/author_id` 均须不同；宿主子代理使用真实宿主会话身份，不能伪造 Orca Dispatch。

业务 `review-acceptance-gate.v1` 显式填写 `value_kind`、原 `business_task`、`business_evidence`、`artifact_root`、相同的 `delivery_identity/reviewed_identity` 及角色身份、`ACCEPT`、空 blocker、消费者和期限。门再次读取真实文件；不要求工程专用的 40 位 Git head 或虚构命令。机械检查只证明文件、合同、角色和证据绑定，语义质量仍由独审负责。

## 3. 角色分离验收（`review-acceptance-gate.v1`）

非平凡 `implementation` / `reusable_verification` / `business_artifact` 默认由不同 dispatch/session 的 implementer 与 reviewer 收口。PM 负责方向、合同、粗粒度巡检、风险升级、immutable-head 记账与最终收口，不在独立证据一致时重复逐行审查或补丁实现。

```bash
python3 scripts/review-acceptance-gate.py <review-acceptance.json>
```

工程模板：`templates/review-acceptance.example.json`。工程接受条件如下；业务字段与文件读回按上一节执行，角色分离、ACCEPT、无 blocker、消费者与期限对两者均适用：

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
python3 scripts/test_business_artifact.py
bash scripts/test-blocker-recovery.sh
```

修改任一门禁或模板后，再按 `references/19-maintainer-validation.md` 执行完整回归。
