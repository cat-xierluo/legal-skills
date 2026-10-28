# WorkBuddy 原生子会话与访问审计

用于复查已归档的 WorkBuddy 冷启动运行，回答“实际调用了哪个子代理、哪份稿件由它生成、观察到它读了哪些文件”。主控的自述、角色标签或输出文件本身不能证明这些事实。

这是可选的事后工具，不接入书记员写入路径，不阻止已经发生的读取。它只支持本机实测的 span JSONL 和 `moot-court call index v1`；当前支持每次调用创建独立实例的归档，不接受同一 session 多次调用或 Teams 嵌套，不能用来验收新版固定会话流程。固定会话另核原生 `resume` 参数、返回 ID 和跨回合响应，见 Runtime 验证。

## 输入与边界

- `--trace`：WorkBuddy 原生 `span_start/span_end` JSONL。
- `--calls-index`：原始 `calls/index.json`，相对 packet／submission 路径从该文件所在目录的上级定位。
- `--policy`：由主控根据原派工边界制定的逐会话工具／精确读取路径白名单。不能用观察到的访问自动反推“这些访问都已获准”。
- `--output`：新报告路径；拒绝覆盖、链接覆盖和既有文件。报告权限为 `0600`，不包含 prompt、稿件正文或命令原文。

示例 policy：

```json
{
  "schema": "workbuddy-audit-policy-v1",
  "expected_root_session_id": "runtime-root-session-id",
  "sessions": {
    "agent-inline": {"tools": [], "read_paths": []},
    "agent-file": {
      "tools": ["Read"],
      "read_paths": ["/path/to/run/calls/T-0008-packet.json"]
    }
  }
}
```

根会话 ID 必须来自已核的运行元数据；只检查 UUID 字符串格式不算身份核验。白名单逐一列出实际 session，包括首稿、补正、准备与复核；只允许 `Read` 或无工具，不接受目录前缀和隐式别名。准备会话与复核者分别配置，不能把复核者可读全量材料的权限赋给参演角色。这是旧归档审计器的工具白名单，不能用来限制生产演练中的法律检索。

```bash
python3 -B scripts/audit_workbuddy_trace.py \
  --trace /path/to/native-trace.jsonl \
  --calls-index /path/to/run/calls/index.json \
  --policy /path/to/access-policy.json \
  --output /path/to/new-audit.json
python3 -B scripts/test_audit_workbuddy_trace.py
```

审计合并 start/end，核对实际父工具调用与参数、Agent span、原生子会话描述符、所属 agent 的 generation、packet 与原稿。报告绑定 trace、索引、policy、packet 和 submission 摘要及回查行号。`mcp_tools` 的 custom span 不算工具调用；模型 completion ID 不能当子会话 ID。`agent_id_first_draft` 同样计入实例，不能因未成为正式稿便漏记。

| 退出码 | 含义 |
|---|---|
| 0 | `OBSERVED_PASS`：支持结构下，已观察调用、稿件对应和访问符合所给 policy |
| 1 | 观察到未批准工具／读取、稿件不一致或调用参数不一致 |
| 2 | 输入结构、事件冲突、路径或报告写入错误 |
| 3 | `NOT_VERIFIED`：缺失／未完成调用、关系不足、嵌套或当前不支持的证据 |

## 结论不能越过观察范围

本地 trace 可编辑、可能截断，摘要不证明签名真实性或历史完整。当前文件路径与符号链接状态也不能重建读取时的目标或权限。未观察到 `events/` 读取只说明这份支持格式的 trace 未记录该访问，不能追认强制隔离、隐藏调用不存在、稿件法律语义正确或 Agent Teams 已验证。

源码中的审计器、回归与本文属于开发验收资料；生产候选包继续按显式允许集排除，不把旧 trace、策略或评测资产送给庭审角色。
