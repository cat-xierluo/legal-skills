# ZCode 会话证据采集器（zcode-session-evidence.py）

只读采集单个 ZCode 会话的用户输入（session_input）→ turn → 最终 assistant 完成证据，输出稳定 JSON，供 GUI 任务监控方向复用。本采集器**不实现 Orca 监督**，也**不是实时活性权威**。

## 用途与边界

- 用于：以精确绑定方式核查"某个会话输入是否已完成、最终 assistant 是否完成且含文本"，把冷 SQLite 快照当作可回溯证据。
- 不用于：
  - 实时活性判断——冷快照缺项绝不推导 idle 或完成；
  - 计费优惠、token 成本或任何 PM 验收结论；
  - 扫描或输出其他会话的正文、reasoning、tool 输入/输出或认证信息。

## 依赖

无。Python 3.9+ 标准库（`sqlite3`、`json`、`argparse`），开箱即用，无需安装。

## 用法

```bash
python3 scripts/zcode-session-evidence.py \
  --db <ZCode原生SQLite路径> \
  --session-id <精确session id> \
  --input-id <精确session_input id> \
  [--include-final-text]
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `--db` | 是 | 既有 ZCode SQLite 数据库路径；只读打开，不存在时直接报错且**绝不创建** |
| `--session-id` | 是 | 精确 session id，与 input 联合绑定 |
| `--input-id` | 是 | 精确 session_input id |
| `--include-final-text` | 否 | 默认关闭；关闭时仅输出元数据与最终文本长度，开启才携带最终 assistant 文本 |

## 绑定与判定语义

1. 以 `mode=ro` URI + `PRAGMA query_only` + 单个 deferred 读事务打开既有 DB，全程一致读快照；任何路径都不会创建或写原生 DB。
2. 精确绑定 `session_input.id + session_id`；无匹配或多余匹配均报错（`INPUT_NOT_FOUND` / `INPUT_AMBIGUOUS`），绝不猜测。
3. 由 `session_input.promoted_message_id` 关联 `turn_usage.user_message_id`；多条匹配报 `TURN_AMBIGUOUS`，零条报 turn 缺失。
4. 最终 assistant = 本会话内 `role=assistant` 且原生 `data.parentID == promoted_message_id` 的 **sequence 最新一条**；只判它，不从较早成功 assistant 拾取去覆盖最新 error/未完成/无 text。
5. 完成证据（`completionEvidence.complete`）同时要求：turn 原生 `status=completed`、该 assistant `time.completed` 非空、无 `error`、含非空 text part。
6. `providerId`/`modelId`/`mode` 只取自该 assistant 原生 message data；缺项显式 `unknown`，不回落其他会话或默认套餐。
7. turn 状态只用 `turn_usage.status` 原生值归类（`running/completed/error/cancelled`）；缺失或未知值输出 `unknown`，绝不由其他字段推导。

## 成功输出（稳定 JSON，键排序）

```json
{
  "ok": true,
  "schemaVersion": 1,
  "sessionId": "...", "inputId": "...",
  "input": {"status": "admitted|promoted|failed|unknown", "statusReason": null, "promotedMessageId": "..."},
  "turn": {"found": true, "turnId": "...", "status": "running|completed|error|cancelled|unknown"},
  "finalAssistant": {"found": true, "messageId": "...", "completed": true, "errorFree": true,
                     "textAvailable": true, "textLength": 123,
                     "providerId": "...", "modelId": "...", "mode": "..."},
  "completionEvidence": {"turnCompleted": true, "finalAssistantCompleted": true,
                         "finalAssistantErrorFree": true, "finalTextAvailable": true, "complete": true},
  "liveness": {"authoritative": false, "note": "..."}
}
```

`--include-final-text` 时 `finalAssistant` 才增加 `text` 字段（无可用文本时为 `null`）。

## 错误输出

失败一律输出 `{"ok": false, "error": {"code": ..., "message": ...}}` 且进程退出码非零；不抛含路径或会话数据的 traceback。

| 错误码 | 含义 |
|---|---|
| `DB_NOT_FOUND` | 数据库不存在或不是常规文件（不创建） |
| `DB_OPEN_FAILED` | 无法以只读模式打开或准备快照 |
| `DB_SCHEMA_INVALID` | 缺少必需表或列 |
| `INPUT_NOT_FOUND` | (session_id, input_id) 绑定无匹配 |
| `INPUT_AMBIGUOUS` | 绑定多匹配，拒绝歧义 |
| `TURN_AMBIGUOUS` | 同一 promoted message 关联多条 turn_usage，拒绝歧义 |
| `JSON_MALFORMED` | message/part 的 data 列不是合法 JSON |
| `READ_ERROR` | 读库失败 |
| `INTERNAL_ERROR` | 未预期内部错误（细节隐去） |

## 脱敏保证（任何模式）

绝不输出：reasoning、tool 输入/输出、`session_input.payload`、认证参数、完整 DB 路径、其他会话数据。错误信息也不含 DB 路径。合成与真实库均应满足；回归见 `scripts/test-zcode-session-evidence.py`。

## 回归测试

```bash
python3 skills/multi-agent-orchestration/scripts/test-zcode-session-evidence.py
```

覆盖：两身份错绑、同 input 多 turn 拒歧义、admitted/failed/缺 turn、completed/最后 assistant error/未完成/无 text（含"较早成功不得覆盖最新"）、provider 缺项、schema/JSON 错误、text 显式开关、敏感内容不泄露、缺 DB 不创建、原 DB 字节不变。
