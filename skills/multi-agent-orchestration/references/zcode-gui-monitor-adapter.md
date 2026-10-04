# zcode-gui-monitor-adapter：只读证据 → PM 监控状态适配器

## 定位

- **问题**：只读会话证据（PR250 采集器 schemaVersion 1 的 metadata JSON）缺少可直接消费的 PM 监控状态和完成待审门。
- **行为**：`zcode-gui-monitor-adapter.py` 单次读取证据文件 raw bytes（上限 1 MiB）→ 计算 SHA-256 → 严格校验（UTF-8 / JSON / schema / 类型 / 绑定 / 摘要 / 期待 provider+model）→ 固定状态机映射 → 输出固定 JSON。
- **边界**：Python 3.9+ 标准库；零网络、零 daemon、零 Orca 调用、不读 DB、不导入未发布模块。不投递、不监督、不判定真实活性——三个 flags 恒为 `false`。

## 用法

```bash
# 必填：--evidence / --session-id / --input-id
python3 skills/multi-agent-orchestration/scripts/zcode-gui-monitor-adapter.py \
  --evidence /path/to/collector-metadata.json \
  --session-id sess_xxx --input-id queue_xxx

# 可选期待值（证据摘要 / 采集环境身份），任一不匹配即固定错误退出
python3 skills/multi-agent-orchestration/scripts/zcode-gui-monitor-adapter.py \
  --evidence /path/to/collector-metadata.json \
  --session-id sess_xxx --input-id queue_xxx \
  --expected-evidence-sha256 <64位hex> \
  --expected-provider account:bigmodel-start-plan \
  --expected-model GLM-5.3-Flash
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--evidence FILE` | 是 | 采集器 metadata JSON 路径；只读，绝不创建/写入；>1 MiB 拒绝 |
| `--session-id SID` | 是 | 必须与 metadata `sessionId` 完全一致，否则 `BINDING_MISMATCH` |
| `--input-id INPUT` | 是 | 必须与 metadata `inputId` 完全一致，否则 `BINDING_MISMATCH` |
| `--expected-evidence-sha256 HEX` | 否 | 64 位 hex；与文件 raw bytes 摘要不符 → `EVIDENCE_DIGEST_MISMATCH` |
| `--expected-provider PROVIDER` | 否 | 与 `finalAssistant.providerId` 不符 → `PROVIDER_MISMATCH` |
| `--expected-model MODEL` | 否 | 与 `finalAssistant.modelId` 不符 → `MODEL_MISMATCH` |

离线自测：`python3 skills/multi-agent-orchestration/scripts/test-zcode-gui-monitor-adapter.py`（真实 CLI 驱动，零网络零副作用；默认不绑定任何远端路径）。真实消费者回归由环境变量显式注入：

```bash
ZCODE_GUI_MONITOR_REAL_EVIDENCE=/path/to/real-metadata.json \
ZCODE_GUI_MONITOR_REAL_SESSION=sess_xxx \
ZCODE_GUI_MONITOR_REAL_INPUT=queue_xxx \
# 可选：ZCODE_GUI_MONITOR_REAL_SHA256 / _REAL_PROVIDER / _REAL_MODEL
python3 skills/multi-agent-orchestration/scripts/test-zcode-gui-monitor-adapter.py
```

三要素缺失或文件不存在时该块明确打印 `SKIP`，不影响其余用例。

## 采集器合法 nullable 约定（schemaVersion 1）

采集器无 turn 时固定输出 `turn = {"found": false, "turnId": null, "status": null}`。适配器据此把**标量字段的 `null` 视同"缺失/未观测"**（`input.status`、`turn.found/status/turnId`、`finalAssistant.*` 布尔与 `providerId/modelId`、`completionEvidence.*`），仅接受"非 null 且类型错误"才判 `EVIDENCE_TYPE_INVALID`。例如 `input.status=null` + 无 turn → `INPUT_ACCEPTED`；`turn.status=null` + `found=false` → `TURN_UNKNOWN`。非 unknown 缺值绝不补全为成功。

## 状态机（固定词表，冲突检测先行）

先做冲突检测（见下节）；无冲突后按序映射：

| 观察 | 状态 |
|------|------|
| `input.status == "admitted"`（无 concrete turn/final） | `INPUT_ACCEPTED` |
| `input.status == "failed"`（无 concrete turn/final） | `INPUT_FAILED` |
| `input.status` 缺失 / null / 未知值（无论 turn/final 观测如何） | `TURN_UNKNOWN` |
| input promoted 但无 turn（`turn.found` 非 true） | `TURN_UNKNOWN` |
| `turn.status == "running"` / `"error"` / `"cancelled"` | `TURN_RUNNING` / `TURN_ERROR` / `TURN_CANCELLED` |
| `turn.status` 为其他未知值（含 null 且 found=true） | `TURN_UNKNOWN`（保留 UNKNOWN） |
| turn completed，`finalAssistant.errorFree` 明确 false | `DELIVERY_ERROR` |
| turn completed，最终 assistant 或 `complete=true` 任一不齐 | `DELIVERY_PENDING` |
| promoted 输入 + turn completed + finalAssistant 四项布尔 true + `completionEvidence.complete` 显式 true | `READY_FOR_PM_REVIEW` |
| 证据内部矛盾 | `EVIDENCE_CONFLICT`（先行短路） |

**完成待审门要求已证 promoted 输入**：`READY_FOR_PM_REVIEW` 仅当 `input.status` 显式为 `"promoted"` 时可达；input 缺失/未知值即使 turn/final 观测全 true 也只给 `TURN_UNKNOWN`。READY 另需 `completionEvidence.complete` 显式 `true` 且与观测一致——缺项保持未知不补全（落入 `DELIVERY_PENDING`）。

## EVIDENCE_CONFLICT 触发条件（双向一致合同）

存在且可知（非 null）的两侧布尔必须**任一方向**一致；缺失/null 键保持未知、绝不构成冲突。以下任一成立即 `EVIDENCE_CONFLICT`（exit 0）：

1. `completionEvidence.complete`（显式 bool）≠ 观测 complete（turn completed 且 final 四项全 true）——既拒绝伪造 complete=true，也拒绝欠声明 complete=false；
2. `completionEvidence.turnCompleted` ≠ 观测 turn completed；
3. `completionEvidence.finalAssistantCompleted / finalAssistantErrorFree / finalTextAvailable`（显式 bool）≠ 对应 `finalAssistant` 布尔为 true 的观测；
4. `finalAssistant.found == false` 但 `completed / errorFree / textAvailable` 任一为 true（未 found 却声明具体布尔）；
5. `turn.found == false` 但 `turn.status` 是 running/completed/error/cancelled 之一（turn 自身矛盾）；
6. `input.status ∈ {admitted, failed}`（已证非 promoted）但 `turn.found == true` 或 `finalAssistant.found == true`（concrete turn/final 矛盾）。

正常进行中快照不误拒：running turn + 全 false 的 completionEvidence 一致，照常 `TURN_RUNNING`；pending 快照（final 不全 + 显式 false 的 ce）照常 `DELIVERY_PENDING`。旧成功不被掩盖：`failed` 输入短路，turn `error` 优先于残留成功 finalAssistant（前者若带 concrete turn 则先行冲突）。

## 错误契约（固定 JSON + exit 2）

缺文件 / 超 1 MiB / 坏 UTF-8 / 坏 JSON / schema 非 1 / 类型错误 / 绑定不一致 / 摘要不匹配 / 期待 provider 或 model 不一致 → 输出单一固定 JSON 并以 exit 2 退出。错误输出**不含路径、不含输入原文、不含 traceback**，仅有：

```json
{"adapter": "zcode-gui-monitor-adapter", "schemaVersion": 1, "error": "<错误码>", "flags": {"pmAccepted": false, "orcaSupervised": false, "livenessAuthoritative": false}}
```

错误码：`EVIDENCE_UNREADABLE`、`EVIDENCE_TOO_LARGE`、`EVIDENCE_NOT_UTF8`、`EVIDENCE_NOT_JSON`、`EVIDENCE_SCHEMA_UNSUPPORTED`、`EVIDENCE_TYPE_INVALID`、`EVIDENCE_DIGEST_MISMATCH`、`BINDING_MISMATCH`、`PROVIDER_MISMATCH`、`MODEL_MISMATCH`。

## 输出契约

成功输出（exit 0）只含绑定 IDs、摘要、固定状态与 flags，未知字段一律丢弃：

```json
{
  "adapter": "zcode-gui-monitor-adapter",
  "schemaVersion": 1,
  "sessionId": "sess_...",
  "inputId": "queue_...",
  "turnId": "turn_... | null",
  "evidenceSha256": "<64位hex>",
  "state": "<固定状态>",
  "provider": "<providerId 或 unknown>",
  "model": "<modelId 或 unknown>",
  "flags": {"pmAccepted": false, "orcaSupervised": false, "livenessAuthoritative": false}
}
```

- `pmAccepted=false`：适配器无权代表 PM 接受任何交付；
- `orcaSupervised=false`：适配器不参与、不声称任何真实 Orca 监督；
- `livenessAuthoritative=false`：适配器不做活性判定，缺失字段绝不推断为 idle/completed；
- `provider`/`model` 缺失时输出 `unknown`，绝不由期待值回落填充。

## cold 快照边界

- **单次读取、时点快照**：证据只反映采集时刻，适配器输出只对该时点负责；同一文件重跑 `evidenceSha256` 一致，文件内容与目录条目不变。
- **不推断**：metadata 中缺失或 null 的字段一律按"未知"处理并落入 fail-closed 状态（`TURN_UNKNOWN`/`DELIVERY_PENDING`），绝不补全为成功。
- **不可作为投递依据**：任何状态（含 `READY_FOR_PM_REVIEW`）都不能触发自动 GUI 投递或监督动作；真实 Dispatch 必须走原生通道，由 PM 人工复核后另行发起。
- **不泄露**：reasoning、tool 载荷、正文文本、凭证等未消费字段永远不出现在输出中。
