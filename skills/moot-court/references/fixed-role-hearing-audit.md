# WorkBuddy 固定角色庭审被动验收

此工具只读取已保存的原生 trace、书记员事件和演练材料，核对可见调用与逐字绑定。它不发起子代理、不阻断读取、不判断实体观点或保密转述，也不证明隐藏调用、强隔离、Teams、法律正确性或无人干预稳定性。输出不包含正文和 prompt，必须在 hearing 目录之外以 0600 新建，禁止覆盖已有路径（包括符号链接和硬链接）。

```bash
python3 -B scripts/audit_fixed_role_hearing.py \
  --hearing /absolute/hearing --trace /absolute/part1.jsonl \
  --trace /absolute/part2.jsonl \
  --expected-root-session /independently-observed-root-id \
  --output /absolute/new-report.json
```

`--trace` 按实际发生顺序重复提供，`trace_index` 从 1 开始，`trace_line` 是该文件中 Agent function span **起始**行的 1 基行号。同一文件内容不得重复输入，同一原生 traceId 的重叠归档也不得混入。每个文件须有完整成功边界及已完成 span；中断、错误边界、截断或无法归属时结果为 `NOT_VERIFIED`。`--expected-root-session` 须由归档之外独立取得并与每个 Agent descriptor 逐项比对；缺失或不一致只记`NOT_VERIFIED`。中断运行不能通过拼接或补写旧日志伪装为完整证据。

## 输入约定

`hearing/run/events/` 是书记员事件，调用 `clerk.load_events/replay` 并要求 civil、无 active、最终正常 close。`hearing/calls/role-sessions.json` 的 `run_id` 与事件一致，`role_sessions` 数组恰含 `judge`、`plaintiff`、`defendant`，每项有 `role` 和 `native_session_id`；`support_sessions` 数组显式登记其他会话（每项 `native_session_id`，没有则 `[]`）。每个登记会话必须可见，所有调用必须登记；首次调用无 resume，以后调用的 resume、返回 sessionId 与 descriptor sessionId 一致。支持会话不计为诉讼角色；不支持嵌套 Agent。

`hearing/review-receipts/index.json` 采用以下结构（路径相对于 hearing；禁止越出 hearing）：

```json
{
  "schema": "fixed-role-hearing-audit-v1",
  "run_id": "run-id",
  "drafts": [
    {"turn_id":"T-0001", "role":"plaintiff", "draft_path":"role-drafts/T-0001.json", "trace_index":1, "trace_line":42}
  ],
  "reviews": [
    {"turn_id":"T-0001", "role":"plaintiff", "draft_path":"role-drafts/T-0001.json", "draft_sha256":"64 lowercase hexadecimal characters", "judge_session_id":"agent-judge", "verdict":"ACCEPT", "receipt_path":"review-receipts/T-0001.md", "trace_index":1, "trace_line":55}
  ],
  "auxiliary_calls": [
    {"trace_index":1, "trace_line":18, "session_id":"agent-judge", "purpose":"庭前准备"}
  ]
}
```

每个正式 speech 在 `drafts` 中恰有一项，位置指向生成该稿的角色 Agent 调用；原生返回允许整体包在唯一 JSON 代码围栏中，审计仅去除该外围栏，其余不得规范化。原生完整 JSON、draft JSON 和 speech payload 必须作为 JSON 对象完全相等，字符串及 citations 保持原样。每个双方稿的每次审查均登记到 `reviews`，包括 RETURN；draft 路径指向送审时的原始 JSON 文件，SHA-256 为该文件原始字节的完整小写摘要。审核调用必须发生在角色产出同一 JSON 之后；法官的原生最终返回可为裸 JSON 或唯一 JSON 围栏，解析后须为含 `"verdict":"ACCEPT"` 或 `"RETURN"` 的对象，与索引一致，其完整原生文本须逐字包含于回执文件。法官 prompt 必须逐字包含紧凑 JSON 对象 `{"review_request":{"turn_id":"…","role":"…","draft_sha256":"…"},"body":"…","citations":["…"]}`；该对象由送审 draft 原字段序列化而来，因此同时绑定完整正文、citations 顺序与内容。原生 trace 中带该标记的调用必须与索引一一对应，漏登记即拒绝。归档中每一条观察到的 Agent 调用都必须归入正式稿、审查或 `auxiliary_calls` 三者之一，未归类调用一律拒绝；`auxiliary_calls` 记录庭前准备、续接验证与支持任务等非发言调用，其 purpose 为自述标签，审计只证明覆盖完整，不证明标签诚实。每个双方正式发言必须恰有一个 ACCEPT，且其原稿、文件摘要与正式 draft 一致；法官发言无需递归审查。索引不得包含示例结构以外的未知字段。回执属于调用证据，不是正式事件。

退出码：0 `OBSERVED_PASS`；1 `VIOLATION`（如摘要送审、字符差异、错绑、缺少接受记录）；2 `INPUT_ERROR`（输入格式、路径或输出不可用）；3 `NOT_VERIFIED`（如边界错误、截断、缺失 trace 定位或历史索引）。证据来自归档文件本身，摘要不是签名，不证明其来源可信。旧运行缺少新索引时保留原件，不补造索引来改写历史结论。
