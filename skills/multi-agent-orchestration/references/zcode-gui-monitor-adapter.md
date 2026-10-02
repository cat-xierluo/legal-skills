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

离线自测：`python3 skills/multi-agent-orchestration/scripts/test-zcode-gui-monitor-adapter.py`（真实 CLI 驱动，零网络零副作用）。

## 状态机（固定词表，按序判定）

| 观察 | 状态 |
|------|------|
| `input.status == "admitted"` | `INPUT_ACCEPTED` |
| `input.status == "failed"` | `INPUT_FAILED` |
| promoted 但无 turn（或 `turn.found` 非 true） | `TURN_UNKNOWN` |
| `turn.status == "running"` | `TURN_RUNNING` |
| `turn.status == "error"` | `TURN_ERROR` |
| `turn.status == "cancelled"` | `TURN_CANCELLED` |
| `turn.status` 为其他未知值 | `TURN_UNKNOWN`（保留 UNKNOWN） |
| turn completed，最终 assistant 信息不全（缺失/未 found） | `DELIVERY_PENDING` |
| turn completed，`finalAssistant.errorFree` 明确为 false | `DELIVERY_ERROR` |
| turn completed 且 finalAssistant `found`/`completed`/`errorFree`/`textAvailable` 均布尔 true | `READY_FOR_PM_REVIEW` |
| 证据内部矛盾（见下） | `EVIDENCE_CONFLICT` |

`READY_FOR_PM_REVIEW` 是**完成待审门**：仅表示"证据齐备、可交 PM 复核"，不是交付完成，更不是验收通过。

## EVIDENCE_CONFLICT 触发条件（过度声明检测）

以下任一成立即输出 `EVIDENCE_CONFLICT`（exit 0，flags 恒 false；缺失字段绝不构成冲突）：

1. `completionEvidence.complete == true` 但 turn 未 completed 或最终 assistant 四项布尔不全（伪造 complete）；
2. `completionEvidence.turnCompleted == true` 但 turn 实际未 completed；
3. `completionEvidence.finalAssistantCompleted / finalAssistantErrorFree / finalTextAvailable == true` 但对应 `finalAssistant` 字段非 true；
4. `finalAssistant.found == true` 但 turn 缺失或 `turn.found` 非 true（无 turn 却有最终 assistant）；
5. `turn.found == false` 但 `turn.status` 是 running/completed/error/cancelled 之一（turn 自身矛盾）。

旧成功不会被掩盖：`input.status == "failed"` 短路为 `INPUT_FAILED`；turn `error` 优先于残留的成功 finalAssistant。

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
- **不推断**：metadata 中缺失的字段（如 textAvailable、finalAssistant）一律按"未知"处理并落入 fail-closed 状态（`TURN_UNKNOWN`/`DELIVERY_PENDING`），绝不补全。
- **不可作为投递依据**：任何状态（含 `READY_FOR_PM_REVIEW`）都不能触发自动 GUI 投递或监督动作；真实 Dispatch 必须走原生通道，由 PM 人工复核后另行发起。
- **不泄露**：reasoning、tool 载荷、正文文本、凭证等未消费字段永远不出现在输出中。
