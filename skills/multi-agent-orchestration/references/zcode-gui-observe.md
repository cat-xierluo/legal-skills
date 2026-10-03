# zcode-gui-observe — 一次性 GUI 会话观察 CLI

`zcode-gui-observe.py` 将既有的证据采集器（collector）与状态适配器（adapter）串联为**一次性的只读观察**：对给定的 `(--db, --session-id, --input-id)` 绑定执行一次采集、一次状态映射，并在 stdout 输出**恰好一个固定 schema 的 JSON**。无轮询、无后台、无 watch、无网络、无自动投递，不调用模型或 Orca。

> **READY 只意味着"待 PM 审查"**：本工具不交付、不派发、不接受任何任务；输出中的三个 flags（`pmAccepted` / `orcaSupervised` / `livenessAuthoritative`）恒为 `false`。

## 依赖声明（重要：尚未开箱可用）

本 CLI 依赖以下两个脚本，**二者对应的 PR 尚未合并进本分支**，因此 base 提交中同目录的缺省兄弟脚本不存在，**不能保证开箱可用**。在 PR 合并前，必须显式指定冻结副本路径（`--collector`/`--adapter` 参数或环境变量）：

| 依赖 | PR | 冻结 head | 冻结副本 SHA-256 |
|------|-----|-----------|------------------|
| collector `zcode-session-evidence.py` | PR250（未合并） | `554a60c1ea27155ad03ec0e2b558d70a8fbb7c1f` | `469020be3d53e9708d50e04b629c791582f80fb8dca6c8298c22ee5edf8cca8b` |
| adapter `zcode-gui-monitor-adapter.py` | PR253（未合并） | `9f77ef0d51cd7b240f512da5c7bfc8257490f98b` | `e596a5add9ee86198c651ef5e7a431d41c4e66bca7d3ebf49318e22021325489` |

- 标准库实现，Python 3.9+，无第三方依赖，无需安装任何包。
- 依赖以当前 Python 解释器的子进程方式运行（无 `shell=True`），每个子进程超时有界（默认 10 秒，最小 1 秒，最大 60 秒）。
- **退出码门（R1-B1）**：先校验依赖子进程 `returncode == 0` 再解释其 stdout；任何依赖非零退出（即使 stdout 是合法 ok/READY 载荷）一律映射为失败，绝不产生 `OK`/`READY_FOR_PM_REVIEW`。
- 可用 `--collector-sha256` / `--adapter-sha256` 固定期望的依赖脚本 SHA-256（不匹配则报 `OBS_DEP_SHA_MISMATCH`），用于消费冻结副本时的完整性核验。

## 用法

```bash
python3 skills/multi-agent-orchestration/scripts/zcode-gui-observe.py \
  --db /path/to/zcode-sessions.db \
  --session-id <sessionId> \
  --input-id <inputId> \
  [--collector /path/to/zcode-session-evidence.py] \
  [--adapter /path/to/zcode-gui-monitor-adapter.py] \
  [--expect-provider <providerId>] [--expect-model <modelId>] \
  [--collector-sha256 <hex>] [--adapter-sha256 <hex>] \
  [--timeout 10]
```

依赖解析优先级：显式参数 > 环境变量 `ZCODE_GUI_COLLECTOR` / `ZCODE_GUI_ADAPTER` > 同目录兄弟脚本（当前分支上通常不存在，会报 `OBS_DEP_MISSING`）。

退出码：`0` = 观察完成（`state` 存在）；`1` = 观察失败（stdout 仍有固定 JSON，`error.code` 给出固定错误码）；`2` = 命令行用法错误（argparse，信息走 stderr）。

## 输出 schema（固定，单行 JSON）

成功（`status=OK`）：

```json
{
  "observer": "zcode-gui-observe",
  "schemaVersion": 1,
  "status": "OK",
  "sessionId": "<请求的 sessionId>",
  "inputId": "<请求的 inputId>",
  "state": "<adapter 固定状态>",
  "summary": {
    "provider": "...", "model": "...", "turnId": "..." | null,
    "evidenceSha256": "<64位hex，包装器对 collector 原始输出的摘要>",
    "inputStatus": "...", "turnStatus": "..." | null,
    "finalAssistantFound": false
  },
  "flags": {"pmAccepted": false, "orcaSupervised": false, "livenessAuthoritative": false},
  "error": null
}
```

失败（`status=ERROR`）：`state` 与 `summary` 为 `null`，`error.code` 为固定错误码，flags 仍恒 `false`。

`state` 词汇与 adapter（PR253）一致：`INPUT_ACCEPTED`、`INPUT_FAILED`、`TURN_UNKNOWN`、`TURN_RUNNING`、`TURN_ERROR`、`TURN_CANCELLED`、`DELIVERY_PENDING`、`DELIVERY_ERROR`、`READY_FOR_PM_REVIEW`、`EVIDENCE_CONFLICT`。

## 错误码

包装器固定错误码：

| 错误码 | 含义 |
|--------|------|
| `OBS_INVALID_ARGS` | `--timeout` 超出 1–60 秒 |
| `OBS_DEP_MISSING` | 依赖脚本缺失/不可执行（不回显路径） |
| `OBS_DEP_SHA_MISMATCH` | 依赖脚本 SHA-256 与期望不符（不回显实际摘要） |
| `OBS_DEP_TIMEOUT` | 依赖子进程超时（已被终止） |
| `OBS_COLLECTOR_BAD_OUTPUT` | collector stdout 不是合法的 collector JSON 或绑定回显不符 |
| `OBS_COLLECTOR_FAILED` | collector 业务错误但错误码不是固定词汇 |
| `OBS_ADAPTER_BAD_OUTPUT` | adapter stdout 非法、flags 被篡改等 |
| `OBS_ADAPTER_FAILED` | adapter 失败但错误码不是固定词汇 |
| `OBS_BINDING_MISMATCH` | adapter 返回的绑定与请求不符（包装器侧核验） |
| `OBS_INTERNAL_ERROR` | 未预期内部错误（不回显 traceback） |

依赖自身的**已发布固定错误码**按 allowlist 核验后原样透出（便于区分"错 SID/input"、"非法 DB"等情形）：

- collector 白名单：`DB_NOT_FOUND`、`DB_OPEN_FAILED`、`DB_SCHEMA_INVALID`、`READ_ERROR`、`JSON_MALFORMED`、`INPUT_NOT_FOUND`、`INPUT_AMBIGUOUS`、`TURN_AMBIGUOUS`、`ASSISTANT_AMBIGUOUS`、`INTERNAL_ERROR`；
- adapter 白名单：`EVIDENCE_UNREADABLE`、`EVIDENCE_TOO_LARGE`、`EVIDENCE_NOT_UTF8`、`EVIDENCE_NOT_JSON`、`EVIDENCE_SCHEMA_UNSUPPORTED`、`EVIDENCE_TYPE_INVALID`、`EVIDENCE_DIGEST_MISMATCH`、`BINDING_MISMATCH`、`PROVIDER_MISMATCH`、`MODEL_MISMATCH`。

白名单之外的任意文本（R1-B2，如合成标记 `SYNTHETIC_PRIVATE_CANARY_123`）一律映射为 `OBS_COLLECTOR_FAILED` / `OBS_ADAPTER_FAILED`，**不回显**。依赖的 stdout/stderr 全文、路径与 traceback **任何情况下都不回显**。`summary` 中的自由字符串回显字段（provider/model/turnId/inputStatus/turnStatus）限可打印且 ≤256 字符，越界值折叠为 `"unknown"`/`null` 哨兵。

## 安全与只读保证

- 原生 DB 只读：包装器自身**从不打开**数据库；仅 collector 以 SQLite URI `mode=ro` + `PRAGMA query_only` 只读快照访问。
- 中间 metadata 以 `0600` 私有临时文件传递给 adapter（`--evidence`），并附带包装器计算的 SHA-256（`--expected-evidence-sha256`）钉死内容；该临时文件在 `finally` 中必定删除（超时/异常路径同样清理）。
- 输出仅含固定 JSON（状态、绑定、摘要、flags）；不含依赖 stdout/stderr、路径、traceback、会话正文。即使依赖在未知字段夹带敏感载荷，包装器只提取已知字段，不会透传。

## 测试

```bash
# 注入冻结副本后运行全部 29 个用例（含真实依赖组）
ZCODE_GUI_COLLECTOR=/path/to/zcode-session-evidence.py \
ZCODE_GUI_ADAPTER=/path/to/zcode-gui-monitor-adapter.py \
python3 skills/multi-agent-orchestration/scripts/test-zcode-gui-observe.py

# 缺省（无环境变量且兄弟脚本缺失）时，真实依赖组会显式 SKIP，仅运行 stub 故障组
python3 skills/multi-agent-orchestration/scripts/test-zcode-gui-observe.py
```

覆盖面：真实合成 DB 走冻结 collector+adapter（READY/无 turn/running/error/cancelled/DELIVERY_ERROR/DELIVERY_PENDING、错 SID/input、非法 DB、缺 DB、provider 期望不符、SHA 校验、敏感载荷不泄露、DB 哈希不变、临时文件净增量 0）；包装故障以小型 stub 实测（异常 stdout、业务错误码透传与清洗、**依赖非零退出但输出合法载荷（exit 9/7）必须失败**、**任意合成大写错误码不回显**、**白名单码仍可诊断**、超时、绑定不符、flags 篡改、timeout 边界、**summary 回显越界折叠**）。测试临时目录可用 `ZCODE_GUI_OBSERVE_SCRATCH` 指定。

## 边界

- 冷快照不构成活性权威：`READY_FOR_PM_REVIEW` 仅表示证据齐备、待 PM 人工审查。
- 不修复、不投递、不监督；与 PM 审查后的后续流程无关。
- PR250/PR253 合并后，兄弟脚本缺省解析才会生效；届时仍建议对高敏感场景显式传 `--collector-sha256`/`--adapter-sha256`。
