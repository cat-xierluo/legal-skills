## MCP 协同工作流（v1.6.0+）

元典已发布官方 MCP（https://open.chineselaw.com/mcp-config），3 个 servers：yuandian-law（法律法规）、yuandian-case（案例文书）、yuandian-company（企业信息）。本 skill 的价值现在转向"**归档 + 法律检索报告生成**"——数据接入由 MCP 负责，本 skill 负责沉淀。

### 接入元典 MCP

模板在 `scripts/.mcp.json.example`（与 `scripts/.env.example` 同目录）。把它复制为客户端能识别位置的 `.mcp.json`：

```json
{
  "mcpServers": {
    "yuandian-law":    { "url": "https://open.chineselaw.com/mcp/law/stream",    "headers": {"Authorization": "Bearer ${YD_API_KEY}"} },
    "yuandian-case":   { "url": "https://open.chineselaw.com/mcp/case/stream",   "headers": {"Authorization": "Bearer ${YD_API_KEY}"} },
    "yuandian-company":{ "url": "https://open.chineselaw.com/mcp/company/stream","headers": {"Authorization": "Bearer ${YD_API_KEY}"} }
  }
}
```

设置环境变量后重启客户端，agent 即可自动获得 `mcp__yuandian_law__*`、`mcp__yuandian_case__*`、`mcp__yuandian_company__*` 工具。

### AI Agent 三步工作流

```
Step 1: 调 MCP 拿数据（agent 直接调，不经 yd-run）
  mcp__yuandian_law__yuandian_law_vector_search("违约金", sxx="现行有效")
  → 拿到 API 响应 JSON

Step 2: 喂给 yd-run ingest 归档 + 生成 .md
  echo "<上一步的 JSON>" | yd-run ingest \
      --query "违约金 调整" \
      --endpoint "/open/law_vector_search"
  → archive/<ts>_违约金_调整.json + .md（同直接 API 模式）
  → CWD/<ts>_违约金_调整.md 工作副本

Step 3: 多次 ingest 后，调 yd-run consolidate 生成法律检索报告
  yd-run consolidate --project "case-2024-xxx" \
      --case "..." --strategy "..." --analysis "..." \
      --conclusion "一句话结论：..." \
      --risks "主要风险：..." \
      --next-actions "后续行动：..." \
      --include "违约金"
  → archive/case-2024-xxx/ 项目包 + 7 节结论先行报告（详见 templates/legal-research-report.md）
```

### ingest 子命令详细

```bash
# 方式 1: 文件输入
yd-run ingest --query "<Q>" --endpoint "/open/<E>" --input <file.json>

# 方式 2: stdin pipe（agent 友好）
cat result.json | yd-run ingest --query "<Q>" --endpoint "/open/<E>"

# 必填
#   --query:     用于生成文件名 + 元信息
#   --endpoint:  对应 API 路径，用于 routing 到 formatter（见 INGEST_ROUTING）
# 可选
#   --cost:        成本标签（默认 "10 积分"）
#   --no-report:   跳过 .md 报告生成
#   --no-cwd-report: 跳过 CWD 副本
```

`--endpoint` 取值见 INGEST_ROUTING 路由表（36 个 endpoint 全部覆盖，包括元典 MCP 暴露的全部 24 个数据 tools）。

### 何时用哪种模式

| 场景 | 推荐模式 |
|---|---|
| agent 调 mcp__yuandian__* | 走 MCP + yd-run ingest（v1.6.0 推荐）|
| 客户端没装 MCP / 单次脚本 | 走 yd-run search/case/... 直接 API（v1.5.x 兼容）|
| 调试 / 看 raw JSON | 走 yd-run raw |

两种模式产出完全一致（archive/ 格式、.md 元信息、consolidate 路由），可混用。
