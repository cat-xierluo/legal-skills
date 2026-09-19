## MCP 协同工作流（v1.6.0+）

元典已发布官方 MCP（https://open.chineselaw.com/mcp-config），3 个 servers：yuandian-law（法律法规）、yuandian-case（案例文书）、yuandian-company（企业信息）。MCP 只替换数据接入层，不代表统一检索算法：具体工具仍分别对应向量、关键词、结构化筛选和详情接口。本 Skill 的中间层价值是先形成涵摄式研究计划，再将 MCP 返回视为候选池，由 Agent 逐条精选后答复或生成报告。

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

### AI Agent 五步工作流

开始下列数据调用前，先按 [`07-research-middleware.md`](07-research-middleware.md) 形成涵摄矩阵、`propositions` 和 `query_matrix`；机器可读查询计划必须通过 `scripts/validate-research-contract.py --plan research-plan.json`。MCP 工具参数同样受字段归属与一争点一查询规则约束。

```
Step 1: 先完成并校验 research-plan.json
  scripts/validate-research-contract.py --plan research-plan.json
  → 非 0：停止调用；区分法律检索缺口与事实/证据缺口

Step 2: 按 query_matrix 调 MCP 拿候选数据（agent 直接调，不经 yd-run）
  mcp__yuandian_law__yuandian_law_vector_search("违约金", sxx="现行有效")
  → 拿到 API 响应 JSON

Step 3: 喂给 yd-run ingest 归档 + 生成 per-call 底稿
  echo "<上一步的 JSON>" | yd-run ingest \
      --query "违约金 调整" \
      --endpoint "/open/law_vector_search"
  → archive/<ts>_违约金_调整.json + .md（同直接 API 模式）
  → CWD/<ts>_违约金_调整.md 工作副本

Step 4: Agent 逐条复核候选，生成 selected-sources.json
  scripts/validate-research-contract.py \
      --plan research-plan.json \
      --selection selected-sources.json
  → 仅 HIGH/MEDIUM、verified、已映射命题的来源可进入交付

Step 5: 默认在对话中给结论和少量精选依据；用户明确要求正式报告时才 consolidate
  yd-run consolidate --project "case-2024-xxx" \
      --case "..." --strategy "..." --analysis "..." \
      --conclusion "一句话结论：..." \
      --risks "主要风险：..." \
      --next-actions "后续行动：..." \
      --research-plan research-plan.json \
      --selection selected-sources.json \
      --include "违约金"
  → archive/case-2024-xxx/ 项目包 + 7 节精选报告
  → --include 只归档/列示原始调用，不复制原始召回正文
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

`--endpoint` 取值见 INGEST_ROUTING 路由表（36 个 endpoint 全部覆盖，包括元典 MCP 暴露的数据 tools）。`ingest` 只负责归档与格式化候选底稿，不签发“可以进入正式报告”的结论。

### 何时用哪种模式

| 场景 | 推荐模式 |
|---|---|
| agent 调 mcp__yuandian__* | 走 MCP + yd-run ingest；随后由 Agent 精选 |
| 客户端没装 MCP / 单次脚本 | 走 yd-run search/case/... 直接 API（v1.5.x 兼容）|
| 调试 / 看 raw JSON | 走 yd-run raw |

两种数据接入模式产出的 archive 格式和 per-call 元信息一致，可混用；无论来自 MCP 还是直接 API，都必须经过同一 `selected-sources` 门禁，数据来源不能替代法律相关性审查。
