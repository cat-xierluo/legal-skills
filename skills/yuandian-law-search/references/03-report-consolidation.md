## 法律检索报告（consolidate）

`consolidate` 只在用户明确要求正式报告或落盘时使用。它不再把 per-call 报告汇总为正文，而是从已经通过校验的 `research-plan.json` 与 `selected-sources.json` 生成交付物。完整精选合同见 [`08-selected-sources-delivery.md`](08-selected-sources-delivery.md)。

## 交付数据流

```text
案件事实
  → 涵摄式 research plan
  → API/MCP 候选召回
  → Agent 逐条复核
  → selected sources
  → consolidate 正式报告

per-call .md/.json 与完整响应
  → archive/<project>/（数据底稿）
  ↛ 第六节正文
```

报告生成前必须执行：

```bash
scripts/validate-research-contract.py \
  --plan research-plan.json \
  --selection selected-sources.json
```

任一非零退出码都停止报告生成。该门禁验证结构、映射和可追溯声明，不替代律师对实体法律相关性的复核。

## 7 节结论先行结构

1. **案情简介**：与检索争点有关的最少必要事实。
2. **检索目的与问题**：对应 research plan 的争点。
3. **检索结论**：一句话定性、核心依据速查、风险和后续行动。
4. **分析与判断**：先展示涵摄矩阵摘要，再给综合法律分析。
5. **检索思路与方法**：展示命题—缺口—查询轨迹和交付门禁。
6. **精选法律依据与案例**：只渲染 `selected_sources`；规范性法源与案例分开。
7. **未解决问题、排除统计与原始轨迹**：披露未解决命题、排除数量和 per-call 链接，不复制原始正文。

第六节不是“召回结果区”。它是经过法律对位审查后的精选依据区。案例不得混入规范性法律依据；规范性材料先按核心／补充，再按法律位阶排列。

## 调用方式

```bash
scripts/yd-run consolidate \
  --title "案件主题" \
  --project "case-project" \
  --case "案情：..." \
  --strategy "涵摄缺口、查询路由和复检过程：..." \
  --analysis "结合精选依据完成的分析：..." \
  --conclusion "附条件的一句话结论：..." \
  --risks "主要风险：..." \
  --next-actions "后续行动：..." \
  --research-plan research-plan.json \
  --selection selected-sources.json \
  --include "可选：仅归档的原始查询子串"
```

- `--research-plan` 必填：涵摄式研究计划，包含争点、要件矩阵、法律检索缺口、正反命题和查询。
- `--selection` 必填：Agent 逐条复核后的精选来源清单。
- `--case` / `--strategy` / `--analysis` / `--conclusion` 必填：正式报告不得保留待补写占位符。
- `--include` 可选：匹配 CWD 中 `<时间戳>_<查询>.md`，仅把原始 per-call 文件归档到项目包并在第七节列出调用轨迹；不再控制正文来源。
- `--output` 可选：指定额外报告路径；不传时在 CWD 写工作副本。

## 项目包

```text
archive/<project>/
  research-plan.json
  selected-sources.json
  <timestamp>_<query>.json       # 可选，原始响应
  <timestamp>_<query>.md         # 可选，per-call 底稿
  <timestamp>_法律检索报告.md     # 正式报告
```

`research-plan.json` 和 `selected-sources.json` 是正式报告的两份直接输入。原始响应用于回查候选池和调用过程；不能因为位于同一项目包，就被视为已经纳入法律分析。

## 目标目录归档规范

用户的案件目录只放：

1. 正式法律检索报告；
2. 用户提供的外部素材；
3. 明确需要交接时的精选研究包；
4. 基于报告生成的下游文件。

不得把 per-call 检索记录、完整 MCP/API 响应或临时文件复制到案件目录。原始材料保留在 Skill 的 `archive/`，且该目录不提交 Git。

## 失败关闭条件

- 缺少 research plan 或 selected sources。
- 精选清单为空、重复、包含 `LOW/MISMATCH`、来源未核验或没有命题映射。
- 决定性命题既无精选来源，也未标记 `unresolved`。
- 使用旧 `--include` 试图把整份 per-call 报告写入正文。
- 规范性法源和案例混排，或历史法源被标为核心依据。

## 验证清单

- [ ] 正文中的每条依据均来自 `selected-sources.json`。
- [ ] 第六节没有原始召回正文、无关法条标题或完整候选列表。
- [ ] 规范性法源按位阶排列，案例单独分组。
- [ ] 每条精选来源都有命题、适用理由、核验说明和溯源信息。
- [ ] 未解决命题和排除数量已披露，但排除候选标题没有污染正文。
- [ ] per-call 文件只在 `archive/` 项目包中作为底稿存在。
