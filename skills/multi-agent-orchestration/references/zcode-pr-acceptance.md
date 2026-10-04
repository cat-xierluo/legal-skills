# zcode-pr-acceptance — 远端直发 PR 证据离线验收

> 任务：TASK-2026-10-04-ZGUI-PR-ACCEPTANCE。本工具是**离线判定器**：PM 用自己的通道新鲜读取 GitHub（PR metadata、PR files、同 branch 全状态 PR 列表、精确 head checks、不同 SID 内容审查报告），把读取结果整理为两份 JSON 交给本工具，得到稳定的 `PASS` / `REJECT` / `UNKNOWN` 判定。工具本身**不访问网络、不调用 gh、不做任何 Git 变更、不访问 token、不自动 merge**，仅用 Python 标准库。

## 依赖

开箱即用，仅 Python 3 标准库（≥3.8），无需安装任何包。

## 用法与退出码

```bash
python3 skills/multi-agent-orchestration/scripts/zcode-pr-acceptance.py \
  --expectations expectations.json \
  --evidence evidence.json \
  [--now-iso "2026-10-04T12:00:00Z"] [--out verdict.json]
```

| 退出码 | 含义 |
|--------|------|
| 0 | PASS（全部程序性门通过） |
| 10 | REJECT（证据无效，或证据证明存在违规） |
| 20 | UNKNOWN（证据不足/过期，无法下结论；**不是放行**） |
| 30 | 内部/参数错误 |
| 2 | argparse 用法错误 |

`--now-iso` 仅供测试注入时钟；使用时输出中 `clock.source=argument` 自我声明，消费方可据此降级信任。默认使用系统 UTC 时钟。

## 输入 1：expectations（PM 预期，schema `zcode-pr-acceptance/expectations@1`）

| 字段 | 类型 | 约束 |
|------|------|------|
| `schema` | string | 必须精确等于 `zcode-pr-acceptance/expectations@1` |
| `task_sid` | string | `^[A-Za-z0-9._:-]{1,64}$` |
| `repo` | string | `owner/name`，与证据精确相等（大小写敏感） |
| `expected_base_ref` | string | 目标基线分支 ref（如 `integration/mao-zcode-gui`） |
| `expected_base` | string | 40 位小写 hex（冻结 base commit） |
| `expected_head` | string | 40 位小写 hex（不可变 PR head） |
| `expected_branch` | string | PR 来源分支 ref |
| `allowed_paths` | string[] | 非空、不重复、朴素相对 POSIX 路径（禁 `..`/绝对路径/`~`/反斜杠/控制字符） |
| `author_sid` | string | SID 模式 |
| `reviewer_sid` | string | SID 模式，必须 ≠ `author_sid` |
| `required_checks` | string[] | 非空、不重复的必需 check 名。**为空/缺失时判 UNKNOWN（`REQUIRED_CHECKS_UNSPECIFIED`），绝不以 `all([])` 放行** |
| `evidence_max_age_seconds` | int | 正整数（禁止 bool 冒充 int），证据新鲜度上限 |

## 输入 2：evidence（PM 新鲜读取的 GitHub 快照，schema `zgui-pr-acceptance/evidence@1`）

| 字段 | 类型 | 约束 |
|------|------|------|
| `schema` | string | 必须精确等于 `zgui-pr-acceptance/evidence@1` |
| `collected_at` | string | ISO-8601 UTC（`...Z`，小数秒仅接受 3 或 6 位；日历非法如 `13-45` → REJECT `VALUE_INVALID`）。超出未来容忍 300s → UNKNOWN `EVIDENCE_TIME_INVALID`；超过新鲜度上限 → UNKNOWN `EVIDENCE_STALE` |
| `repo` | string | 同上 |
| `pr` | object | 见下 |
| `pr.number` | int | 正整数，禁 bool |
| `pr.state` | enum | `OPEN`/`CLOSED`/`MERGED`（大写敏感）；非 OPEN → REJECT `PR_NOT_OPEN` |
| `pr.is_draft` | bool | 必须真 bool；true → REJECT `PR_DRAFT` |
| `pr.branch` / `pr.base_ref` | string | ref 模式；与预期不等 → REJECT `BRANCH_MISMATCH`/`BASE_MISMATCH` |
| `pr.head_sha` / `pr.base_sha` | string | 40 hex；不等 → REJECT `HEAD_MISMATCH`/`BASE_MISMATCH` |
| `pr.author_sid` | string | SID；不等 → REJECT `AUTHOR_SID_MISMATCH` |
| `pr.files[]` | list | `{path, status, sha?, previous_path?}`；`status ∈ added/changed/modified/renamed`（`removed` → REJECT `FILE_STATUS_UNSUPPORTED`；`renamed` 的 `previous_path` 也必须在允许集合内）。路径集合与 `allowed_paths` **精确相等**，否则 REJECT `PATHS_MISMATCH` |
| `branch_prs[]` | list | `{number, state, branch, head_sha}`，同 branch 全状态 PR 清单。目标 branch 上出现任何其他 PR（任何状态）→ REJECT `DUPLICATE_BRANCH_PR`；空清单 → UNKNOWN `BRANCH_PR_LIST_EMPTY`；不含目标 PR → UNKNOWN `BRANCH_PR_NOT_LISTED` |
| `head_checks` | object | `{head_sha, checks[]}`；`head_sha` ≠ 预期 head → REJECT `CHECKS_HEAD_MISMATCH`（不得拿别的 head 的 checks 充数）。check `{name, status, conclusion}`，`status ∈ queued/in_progress/completed`，`conclusion ∈ success/failure/neutral/skipped/timed_out/action_required/cancelled/stale/null`。**唯一算成功的组合是 `completed`+`success`；pending/失败/其他一律 `CHECK_NOT_SUCCESS`，不得当 SUCCESS**；必需 check 缺失 → `REQUIRED_CHECK_MISSING`；同名重复 → `CHECK_DUPLICATE` |
| `review` | object | `{reviewer_sid, head_sha, verdict, blockers[]}`。审查 head ≠ 预期 head → REJECT `REVIEW_HEAD_MISMATCH`；`verdict=REJECT` → `REVIEW_VERDICT_REJECT`；`blockers` 非空 → `REVIEW_BLOCKERS`（只回显计数，不回显内容）；审查者 ≠ 指定 reviewer SID → `REVIEWER_SID_MISMATCH`；审查者 = 作者 SID → `REVIEWER_NOT_INDEPENDENT` |

未知多余字段一律**忽略且永不回显**（前向兼容；PR 标题/正文/评论等自由文本不在 schema 内，也不得进入输出）。

## 判定策略

- **REJECT**：任何结构违规（schema 未知、字段缺失、类型不符、bool 冒充 int、路径穿越/重复、枚举非法）或语义违规（head/base/repo/draft/OPEN 偏差、允许文件集合不等、同 SID、审查不通过、同 branch 重复 PR、checks 另 head/缺必需/非 success）。
- **UNKNOWN**：证据不足或过期（`REQUIRED_CHECKS_UNSPECIFIED`、`BRANCH_PR_LIST_EMPTY`、`BRANCH_PR_NOT_LISTED`、`EVIDENCE_STALE`、`EVIDENCE_TIME_INVALID`）。UNKNOWN 永远不是放行。
- 优先级：REJECT > UNKNOWN > PASS；所有原因按固定检查顺序收集并全部输出。
- 结构校验出现 REJECT 级问题时跳过语义比较（缺失字段无法可靠比对），原因仍完整输出。

## 原因枚举总表

`INPUT_MISSING` `INPUT_UNPARSEABLE` `INPUT_NOT_OBJECT` `SCHEMA_UNKNOWN` `SCHEMA_MISSING_FIELD` `TYPE_MISMATCH` `BOOL_AS_INT` `VALUE_INVALID` `PATH_DUPLICATE` `PATH_TRAVERSAL` `PATHS_MISMATCH` `FILE_STATUS_UNSUPPORTED` `REPO_MISMATCH` `BASE_MISMATCH` `HEAD_MISMATCH` `BRANCH_MISMATCH` `PR_NOT_OPEN` `PR_DRAFT` `AUTHOR_SID_MISMATCH` `REVIEWER_SID_MISMATCH` `REVIEWER_NOT_INDEPENDENT` `REVIEW_HEAD_MISMATCH` `REVIEW_VERDICT_REJECT` `REVIEW_BLOCKERS` `BRANCH_PR_LIST_EMPTY` `BRANCH_PR_NOT_LISTED` `BRANCH_PR_LIST_DUPLICATE` `DUPLICATE_BRANCH_PR` `CHECKS_HEAD_MISMATCH` `CHECK_DUPLICATE` `REQUIRED_CHECK_MISSING` `CHECK_NOT_SUCCESS` `REQUIRED_CHECKS_UNSPECIFIED` `EVIDENCE_STALE` `EVIDENCE_TIME_INVALID`

其中 UNKNOWN 级：`BRANCH_PR_LIST_EMPTY` `BRANCH_PR_NOT_LISTED` `REQUIRED_CHECKS_UNSPECIFIED` `EVIDENCE_STALE` `EVIDENCE_TIME_INVALID`；其余均为 REJECT 级。

## 输出（verdict，schema `zgui-pr-acceptance/verdict@1`）

```json
{"business_semantics_proven":false,"clock":{"now_utc":"...","source":"system"},
 "decision":"PASS","expected_base":"...","expected_head":"...","evidence_age_seconds":42,
 "generated_at_utc":"...","inputs":{"evidence_sha256":"...","expectations_sha256":"..."},
 "pr_number":7,"reason_details":{},"reasons":[],"repo":"owner/name",
 "schema":"zgui-pr-acceptance/verdict@1","task_sid":"...","tool_version":"1.0.0"}
```

- `inputs.*_sha256`：对两份输入**原始字节**的 SHA256 绑定。消费方核验：内容不同 → hash 必不同；同输入 + `--now-iso` 注入时钟 → 输出**字节级一致**（含 `generated_at_utc`）；默认系统时钟下两次运行仅 `generated_at_utc` 不同，其余字段（含 reasons 顺序）完全一致。`expected_head` 回显固定 head，消费方据此钉死被验收的 commit。
- `business_semantics_proven` 恒为 `false`：**CI success ≠ 业务语义证明**。语义结论只能来自不同 SID 的内容审查（`review` 节）；PASS 仅表示程序性门（结构/路径/身份/checks/新鲜度）全部通过。
- 输出只含枚举、sha、计数、时间戳等结构化字段；不输出环境变量、token、或任何输入自由文本。

## 安全属性与边界

- 离线纯标准库：源码不 import 网络/subprocess；不做任何 Git 操作；不读环境变量。
- 输入不可信自由文本（标题/正文/评论/blockers 内容）不回显；秘密类字段即使存在也被忽略。
- 工具无法离线验证 GitHub 侧真实性——**信任锚是 PM 的新鲜读取**（collected_at + 新鲜度上限 + 输入 SHA256 绑定）。`clock.source=argument` 时新鲜度结论按注入时钟计算并自我声明。
- 历史快照负例：一个如今已 MERGED 的真实 PR 快照会因 `PR_NOT_OPEN` 被拒；draft 期快照因 `PR_DRAFT` 被拒。合成正例只证明接口行为；真实新 PR 的端到端消费由 PM 之后执行。
- 口径备注（经安全审查确认 fail-closed，均可接受）：容器字段（`pr`/`head_checks`/`review`/`files`/`branch_prs`/`checks`/`blockers`）缺失与类型不符统一按 `TYPE_MISMATCH` 拒绝；JSON 重复键不检测（按解析器取最后值）；同一枚举多次出现时 `reason_details` 仅回显首条明细（判定不受影响）；路径首尾空白/控制字符按 `PATH_TRAVERSAL` 归类（同为 REJECT 级）；`REF_RE`/`REPO_RE` 允许 `..` 字面段（仅做等值比较、无文件系统用途）。

## 纯合成样例（仅示例，sha 均为虚构）

expectations.json：

```json
{"schema":"zgui-pr-acceptance/expectations@1","task_sid":"TASK-2026-10-04-ZGUI-PR-ACCEPTANCE",
 "repo":"example-owner/example-repo","expected_base_ref":"integration/example-line",
 "expected_base":"1111111111111111111111111111111111111111",
 "expected_head":"2222222222222222222222222222222222222222",
 "expected_branch":"feat/example-branch",
 "allowed_paths":["skills/example/scripts/tool.py","skills/example/scripts/test_tool.py"],
 "author_sid":"SID-AUTHOR","reviewer_sid":"SID-REVIEWER",
 "required_checks":["ci"],"evidence_max_age_seconds":900}
```

evidence.json：

```json
{"schema":"zgui-pr-acceptance/evidence@1","collected_at":"2026-10-04T12:00:00Z",
 "repo":"example-owner/example-repo",
 "pr":{"number":7,"state":"OPEN","is_draft":false,"branch":"feat/example-branch",
       "head_sha":"2222222222222222222222222222222222222222",
       "base_ref":"integration/example-line",
       "base_sha":"1111111111111111111111111111111111111111",
       "author_sid":"SID-AUTHOR",
       "files":[{"path":"skills/example/scripts/tool.py","status":"added"},
                {"path":"skills/example/scripts/test_tool.py","status":"added"}]},
 "branch_prs":[{"number":7,"state":"OPEN","branch":"feat/example-branch",
                "head_sha":"2222222222222222222222222222222222222222"}],
 "head_checks":{"head_sha":"2222222222222222222222222222222222222222",
                "checks":[{"name":"ci","status":"completed","conclusion":"success"}]},
 "review":{"reviewer_sid":"SID-REVIEWER","head_sha":"2222222222222222222222222222222222222222",
           "verdict":"APPROVE","blockers":[]}}
```

以 `--now-iso 2026-10-04T12:05:00Z` 运行 → `decision=PASS`、退出码 0（仅证明接口，不代表任何真实 PR）。
