# 精选法律检索报告

只有用户要求报告／落盘时，才将实际查询和精选依据整理成两个输入文件。普通对话无需 JSON。报告不是完整召回的汇编，`consolidate` 只消费通过校验的精选清单。

## 轻量报告：focused 记录

单争点及普通检索报告使用 `schema_version=1.1, mode=focused`，不要求要件矩阵、反向命题或预先计划文件。可以在检索后如实记录；不得把没执行过的建议查询记成已执行。

```json
{
  "schema_version": "1.1",
  "mode": "focused",
  "case_id": "example-guarantee-period",
  "research_brief": {
    "research_goal": "核对保证期间条文",
    "dispute_focus": ["民法典第692条的具体内容"]
  },
  "propositions": [
    {"id": "P1", "statement": "核对保证期间及未约定期间的规则", "importance": "decisive"}
  ],
  "queries": [
    {
      "id": "Q1",
      "proposition_id": "P1",
      "interface": "detail",
      "query_expression": "中华人民共和国民法典",
      "filters": {"--ft-name": "第六百九十二条"}
    }
  ]
}
```

这是结构示例，不是已执行证据。记录真实接口的 CLI 等价名及字段；MCP 原始工具名／参数可另记扩展字段，不得把 CLI 参数直接用作 MCP 入参。未设置的筛选记 `{}`，不补造改写、地区或时间参数。

另一份 `selected-sources.json` 沿用 [精选来源合同](08-selected-sources-delivery.md) 的 schema 1.0，只放拟采用的少量来源。两份文件的 schema 版本不必相同。每项须说明支持哪一命题、适用理由、来源、核验范围；案例与规范分开。

focused 报告输出四节：结论与适用前提、分析、精选依据、未解决问题。查询轨迹折叠置后，不重复展示完整矩阵、依据速查表和程序门禁表。

## 深度报告：保留兼容

确需完整涵摄矩阵和多争点记录时使用 [深度研究](07-research-middleware.md) 的 schema 1.0。原七节报告仍受支持；不要只因要落盘就升级深度。

## 校验与生成

```bash
scripts/validate-research-contract.py \
  --plan /absolute/path/research-plan.json \
  --selection /absolute/path/selected-sources.json

scripts/yd-run consolidate \
  --title "案件主题" --project "case-project" \
  --case "最少必要案情与假设" \
  --strategy "实际查询及追加原因" \
  --analysis "结合精选来源的分析" \
  --conclusion "附条件结论" \
  --risks "未确认事实与核验边界" \
  --next-actions "必要后续动作；没有则说明无" \
  --research-plan /absolute/path/research-plan.json \
  --selection /absolute/path/selected-sources.json \
  --output /absolute/path/法律检索报告.md
```

非零校验退出码阻断报告。校验器只验证结构、映射和核验声明，不证明法律适用判断正确，也不保证 source_url／archive_ref 实际可达；Agent 仍须实际复核。现有历史法源 core 限制见精选合同，不能为过门禁伪造现行状态。

规范先按核心／补充，再按类型排序；典型案例不进入法律依据组。最多12条是上限，不是目标。已排除候选只显示统计，不把无关标题再带进正文。

## 留存与原始轨迹

报告、两份输入保存到所选归档目录的项目子目录。默认 `archive/<project>/`；也可用 `--archive-dir` 或 `YD_ARCHIVE_DIR`。正式报告本身是明确的写入操作，不用 `--no-archive` 代替取消报告生成。

`--include` 可选，仅从工作目录匹配 `<时间戳>_<查询>.md`，将底稿归档并列出链接；不决定报告正文来源。**不必为了生成报告补齐每次调用的 Markdown。**

- `--no-report` 跑过的检索没有 Markdown，但原始 JSON 仍可作为来源追溯。
- 缓存命中不会补写 Markdown，也不重复扣积分。
- 缺少底稿时直接省略 `--include`，在精选来源中引用已有 JSON／来源链接即可。不为补底稿重跑收费请求。
- 确需重建 Markdown 时，从已有 JSON 离线格式化或 `ingest --input`；不人工重抄全文。
- “附带底稿文件数”不是“实际 API 调用数”，更不是费用账单。

案件目录只放正式报告及用户要求的交接材料；原始响应、临时文件和客户敏感材料不提交公开仓库。

## 验收

- 正文仅使用已核验且对位的精选来源；无原始召回全文。
- 规范与案例分组，来源去重，适用时间明确。
- 决定性命题有支持来源或明确列入未解决问题。
- 缺少精选、LOW/MISMATCH、待核验、错误映射等不能通过换 focused 模式绕过门禁。
