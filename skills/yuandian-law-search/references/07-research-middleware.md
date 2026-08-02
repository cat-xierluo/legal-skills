# 检索机制感知型法律研究中间层（执行合同）

> 本 reference 落地 [DEC-006]：把 Skill 从"元典 API/MCP 包装 + 归档 + 报告"升级为"检索机制感知型法律研究中间层"。
> 案件检索（综合检索 / 类案对标 / 已有报告复盘）**默认走本主流程**；简单法条或案号检索（`detail` / `case-detail`）不启动本流程。
> 评测定位见 [DEC-007]：本文定义的是**第 1 层「检索方案评测」**的产物——可在不调用元典接口时完整产出。

## 1. 与既有约定的关系

- v1.6.1+ 已有的「5 字段争点识别表」（见 [`02-typical-workflows.md`](02-typical-workflows.md) 场景 4：行为主体 / 角色定位 / 行为模式 / 抗辩点 / 用户已明确的论点）是本流程 `research_brief` 的**子集**，不重复执行。
- 本流程把争点识别扩展为：`research_brief`（检索简报）→ `propositions`（检索命题）→ `query_matrix`（查询矩阵）→ 对位复核。
- 关键词扩展三原则（[`01-keyword-expansion.md`](01-keyword-expansion.md)）仍适用，但降级为查询矩阵**内部**的一条改写手段，不再是案件检索的默认主路径（[DEC-006] pt 5）。

## 2. 执行合同（调用任何检索接口前必须完成）

案件检索必须按以下顺序推进；任一步信息不足时按 §6 前置门禁处理，不得跳步直接调用接口。

```
① 轻量案件研判 ─► research_brief
② 由 brief 派生 ─► propositions（正向支持 + 反向排除）
③ 由 propositions 派生 ─► query_matrix（一争点一查询，单一接口）
④ 小样本试检（1-2 条命题先验证接口与表达是否有效）
⑤ 对位复核（HIGH / MEDIUM / LOW / MISMATCH）─► 策略修正
⑥ 正式检索 ─► 结论—依据—查询可追溯报告
```

> 简单检索（用户给出明确法条名+条号、或明确案号、或问"XX 法怎么规定"且无案件事实）走 [`SKILL.md` 接口速查](../SKILL.md#接口速查)即可，**不启动本流程**。判定边界见 §7。

## 3. research_brief（检索简报）schema

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `research_goal` | string | 是 | 本次研究要回答的法律问题（用户真正要求裁判/判断的命题，不是案由复述） |
| `party_stance` | object | 是 | 当事人立场：`role`（原告/被告/被申请人/代理人…）+ `claim_or_defense`（核心诉求或抗辩） |
| `procedure_stage` | string | 否 | 程序阶段（一审/二审/再审/仲裁/执行/诉前） |
| `dispute_focus` | string[] | 是 | 争议焦点：用户原话里已明确的核心论点（来自 5 字段表的"用户已明确论点"） |
| `claim_or_defense_path` | string[] | 是 | 请求权/抗辩路径——由本案事实推导，用于区分主题相近但请求权基础不同的近邻案型（不预设特定法律领域） |
| `legal_elements` | object[] | 是 | 法律要件：`element`（要件名）+ `source`（法源线索，待检索验证）+ `covered`（brief 是否已覆盖该要件的事实）。`covered` **不是装饰字段**：`covered=false` 的要件必须落入 `facts_to_supplement` 并标注是否阻断路径，驱动补问/假设继续——若全员 `covered=true` 却仍要检索，说明要件拆解流于形式 |
| `decisive_facts` | string[] | 是 | 决定性事实（must_match）：检索简报和查询表达必须覆盖的事实 |
| `background_facts` | string[] | 否 | 背景事实（影响裁判尺度但不决定争点定性） |
| `facts_to_supplement` | object[] | 否 | 待补事实：`fact` + `blocks_path`（是否改变检索路径）+ `action`（补问/标注假设继续） |
| `must_exclude_neighbor_types` | string[] | 是 | 必须排除的近邻案型（must_not_match），见 §8 |
| `key_decisive_facts` | string[] | 否（建议） | `decisive_facts` 的**置顶短摘要**（3-5 条精简版），放在 brief 顶部便于人/judge 快速复核，不得与 `decisive_facts` 矛盾 |
| `key_exclusions` | string[] | 否（建议） | `must_exclude_neighbor_types` 的**置顶短摘要**，同上 |
| `role_comparison_matrix` | object | 否（仅同主题多角色场景） | 多主体角色对比矩阵，见 §3.1 |
| `prior_report_sources` | object | 否 | 已有法律分析报告（见 §3.2），无则留空 |

**硬约束**：`dispute_focus`、`decisive_facts`、`must_exclude_neighbor_types` 三项不得为空；任一为空说明案件研判未完成，退回 §6 前置门禁。

### 3.1 scan-friendly 摘要与多角色对比矩阵

- **置顶摘要**：`key_decisive_facts` 与 `key_exclusions` 是 `decisive_facts` / `must_exclude_neighbor_types` 的精简镜像，放在 brief 顶部，让复核者（人或自动 judge）无需翻查嵌套字段即可定位关键事实与近邻排除。底层详细字段仍是权威来源；摘要不得与之矛盾，也不得只写摘要而省略底层字段。目的：避免 dense 结构化输出被快速浏览时漏看关键排除项。
- **多角色对比矩阵**：当一个案件含 2+ 主体角色且请求权基础不同，除为每个角色产出独立的 propositions/queries 外，还应输出 `role_comparison_matrix` 汇总差异：

  ```json
  {
    "axes": ["主体角色", "请求权基础/规范", "决定性事实", "必须排除的近邻"],
    "rows": [
      {"role": "主体角色 A", "claim_basis": "（该角色的请求权基础/规范，由本案推导）", "decisive_facts": ["..."], "exclusions": ["..."]},
      {"role": "主体角色 B", "claim_basis": "（与 A 不同的请求权基础/规范）", "decisive_facts": ["..."], "exclusions": ["..."]}
    ]
  }
  ```
  矩阵是汇总视图，**不替代**各角色的独立 query_matrix（一争点一查询仍按角色分别落）。

### 3.2 已有法律分析报告（`prior_report_sources`）

输入含既有法律分析报告时，`prior_report_sources` 必须拆成**三栏**，把"事实/结论/假设"分层（反 inflation 关键防线）：

| 子字段 | 含义 | 处置 |
|---|---|---|
| `report_facts` | string[] | 报告**援引的、可定位来源的客观事实**（报告中有出处、可回查的事实陈述）。可作检索线索直接使用 |
| `report_conclusions` | string[] | 报告的**法律结论/定性**（报告作者的主观判断）。**必须降级为待验证假设**，不得当已证事实写入 `decisive_facts` |
| `hypotheses_to_verify` | object[] | 由结论转化的、必须独立检索验证的判断：`hypothesis` + `verifies_conclusion`（关联 report_conclusions）+ `proposition_id`（对应验证命题） |

**法源 vs 法律判断的区分**（易错点）：

- 报告**援引的法源**（具体法条名称+条号，属客观引用）→ 可直接作 `queries[].filters`（`--yyft`）或法条检索线索，**无需降级**。
- 报告**作者的法律评价/定性**（对要件是否成立、是否构成某行为的判断）→ 属主观判断，**必须降级为 `hypotheses_to_verify`**，配独立验证命题。

**硬约束**：不得因报告存在而跳过 §2 轻量研判；每条 `report_conclusions` 都应有对应 `hypotheses_to_verify` 条目；报告结论不得直接出现在 `decisive_facts`（那是 must_match 事实位）。

## 4. propositions（检索命题）schema

每个命题只验证**一项**可被法条或案例支持/否定的判断。

| 字段 | 取值 |
|---|---|
| `id` | `P-NN` |
| `statement` | 单一判断陈述（"……构成/不构成……""……要件需要/不需要……"） |
| `type` | `normative`（规范命题：法条如何规定）/ `fact-structure`（事实结构命题：此类事实是否落入该规范）/ `adjudication-rule`（裁判规则命题：裁判者如何认定）/ `reverse`（反向命题：对方抗辩或不利类案的裁判路径） |
| `direction` | `support`（支持我方立场）/ `oppose`（对方抗辩、不利类案、否定要件） |
| `importance` | `decisive`（决定争点定性）/ `supportive`（影响尺度或佐证） |
| `parent_element` | 关联的 `legal_elements[].element` 或 `dispute_focus` |

**正反向必生成**：每个 decisive 争点至少生成 1 条 `support` + 1 条 `reverse` 命题（[DEC-006] pt 3）。反向命题是"近邻陷阱"的主要防线——它显式表达"什么情况下我方命题不成立"，对应到查询就是排除条件。

## 5. query_matrix（查询矩阵）schema

| 字段 | 说明 |
|---|---|
| `id` | `Q-NN` |
| `proposition_id` | 承载的单一命题（`P-NN`） |
| `interface` | `search` / `keyword` / `detail` / `case` / `case-semantic` / `regulation` / `case-detail` |
| `routing_rationale` | 为何选此接口（基于接口的真实匹配机制，见 §9） |
| `query_field` | 主查询字段（自然语言问题 / 关键词组合 / 结构化字段） |
| `query_expression` | 实际查询表达 |
| `filters` | 筛选条件（`--sxx`/`--effect1`/`--province`/`--jarq-*`/`--ay`/`--yyft` 等） |
| `allow_rewrite` | 是否允许后端改写（向量接口默认 true；关键词接口不适用） |
| `expected_hit` | 预期命中类型（法源/类案/裁判规则） |
| `exclusion_criteria` | 排除标准（来自 `must_exclude_neighbor_types`，对应反向命题） |
| `fallback_path` | 零命中或低对位时的降级路径（换接口 / 缩短关键词 / 切 OR / 换语义） |

**一争点多小查询**（[DEC-006] pt 4，硬约束）：

- 每个 `query` 只承载**一个争点 + 一组决定性事实**。
- `case` / `keyword` 接口的后端只支持**全局 AND/OR**，**不得**把多个争点或一长串事实压成嵌套布尔串。
- 一个争点通常对应 2-4 条 query（不同接口、不同方向、正反各一），而不是 1 条巨查询。
- `--expand` 全局 OR 仅作为单条 query **内部**的改写手段保留兼容，不再作为案件检索主路径。

## 6. 检索前门禁（pre-door gate）

信息不足时按"最小必要"处理，不得空跑查询，也不得一次性追问十几个问题：

| 情形 | 处理 |
|---|---|
| 事实不足但**不影响查询方向**（如赔偿具体数额未定） | 在 brief 标注假设继续，不影响命题与查询生成 |
| 主体 / 行为链条 / 待解决问题缺失到**会改变检索路径** | 只补问会改变检索路径的最关键问题（**最多 3 个核心**，通常含"合同/法律关系类型+违约形态"或"当事人角色"），其余标注假设继续 |
| 完全无法判断争点（用户只说"帮我查相关案例"） | 触发最小补问：合同/法律关系类型 + 诉求方向；不补问不生成 query_matrix |
| 明确法条名+条号 / 明确案号 / 纯概念问答 | **不启动本流程**，直接走接口速查 |

补问结果回填 brief 后再继续；补问不超过 **1 轮**——**1 轮 = 1 次交互回合**（不限制该回合内问几个，但单回合最多 3 个会改变检索路径的核心问题），**不得套用 5 字段争点识别表的全字段逐一追问**（那是案件研判输入表，不是补问清单）；仍不足则按假设推进并标注 `待补充`。

## 7. 何时不启动本流程（边界）

- 用户给出明确法条名 + 条号 → `detail`。
- 用户给出明确案号 → `case-detail --ah`。
- 用户问"XX 法怎么规定的"且无案件事实 → `search`。
- 用户问"关于 XX 的法律条文" → `keyword`。
- 以上属"简单检索"，直接走 [`SKILL.md` 接口速查](../SKILL.md#接口速查)，不产出 research_brief。

只要用户描述了事实结构、争议焦点、诉讼立场，或问"类似案件怎么判""能不能主张 XX""对方抗辩怎么办"——即触发本流程。

## 8. 近邻案型排除（must_not_match）

近邻陷阱 = 主题、案由或行业相近，但**主体角色、行为链条或决定性事实**不同，混入会污染主要依据。brief 必须在查询前显式写出 `must_exclude_neighbor_types`（由本案事实推导，**不预设特定法律领域的清单**），并映射到对应 query 的 `exclusion_criteria`。

识别方向（非穷举，按本案事实判断，不列举具体案型）：

- **请求权基础不同**：主题相近但落入不同规范路径（主体身份 / 客体 / 行为要件不同），各路径要件不能互替。
- **主体角色不同**：同一主题下行为主体身份不同，导致责任路径或注意义务标准不同。
- **行为链条/决定性事实不同**：主题或行业相近，但关键事实缺失或不同，不能直接类推。

**`must_exclude_neighbor_types` 写法**：每项写**一个独立近邻案型**（不合并多项），并表述具体到"为什么排除"（缺哪个要件 / 主体 / 事实），便于复核；`key_exclusions` 置顶摘要同样逐项独立。

对位复核时，命中近邻案型应标 `LOW` 或 `MISMATCH`，不得纳入主要依据。

## 9. 接口路由规则（按机制，不按"统一搜索"抽象）

基于已知后端能力（完整审计见 Task-002，本节为当前已知能力的路由）：

| 检索目标 | 首选接口 | 理由 |
|---|---|---|
| 规范发现（"XX 的法律规定"） | `search`（法条向量） | 语义匹配，广覆盖概念关联 |
| 精确核法（已知法条名+条号） | `detail` | 直接定位，无歧义 |
| 关键词精确 + 效力/日期筛选 | `keyword` | 字面 AND/OR + 结构化过滤 |
| 事实结构类案（"类似案件怎么判"） | `case-semantic`（案例向量） | 长事实结构语义匹配，关键词会丢事实 |
| 裁判用语 / 援引法条 / 案由复检 | `case`（结构化字段） | `--ay`/`--fxgc`/`--yyft`/`--jbdw` 精确过滤 |
| 标杆案例对标 | 先 `case-semantic`（事实骨架），再 `case` 结构化复检 | 见 [`02-typical-workflows.md`](02-typical-workflows.md) 场景 5 |

**硬约束**：

- `case` 关键词默认放 4-6 个高信息密度词，不构造后端无法表达的长 AND（[DEC-002]、[DEC-006] pt 4）。
- `case` 一轮零命中 ≠ "无类案"：立即切 `case-semantic` 或缩短关键词换 OR 复检（[DEC-002]）。
- 后端 `score`/`_score` 只在**同一接口同一查询内部**作排序信号，不跨查询、不跨接口、不替代法律对位度。

### 9.1 字段归属接口速查表（防 filter 误挂）

filter 必须挂在**真正支持它**的接口上，否则会被忽略或报错（实测 worker 易把案例语义字段误挂到案例关键词）。下表以 `scripts/yd_search.py` 源码为权威（`case` 子命令定义见源码 `add_parser("case")`，`case-semantic` 见 `add_parser("case-semantic")`）：

| filter | `case` 关键词 | `case-semantic` | `search`/`keyword` 法条 |
|---|:---:|:---:|:---:|
| `--ay`/`--fxgc`/`--yyft`/`--jbdw`/`--ah`/`--ajlb`/`--title` | ✓ | ✗ | ✗ |
| `--wenshu-type`/`--fayuan` | ✗ | ✓ | ✗ |
| `--wszl` | ✓ | ✓ | ✗ |
| `--cj`（法院层级） | ✗ | ✓ | ✗ |
| `--jarq-start`/`--jarq-end`（结案日期） | ✓ | ✓ | ✗ |
| `--sxx`/`--effect1`/`--fgmc`（法条时效/效力/法规名称） | ✗ | ✗ | ✓ |
| `--province`/`--xzqh-p` | ✓ | ✓ | ✗ |
| `--authority-only` | ✓ | ✓ | ✗ |

易错点提醒：

- **`--wenshu-type`（案件类型，如民事案件）属于 `case-semantic`**，不要挂到 `case` 关键词（`case` 用 `--ajlb` 表达案件类别，无 `--wenshu-type`）。
- **`--ay`/`--fxgc`/`--yyft`（案由/分析过程/援引法条）属于 `case` 关键词**，`case-semantic` 不支持——想用这些结构化字段精确复检就切到 `case`。
- **`--jarq-start/end` 两个案例接口都支持**（源码确认），可放心用于日期范围。
- 法条接口（`search`/`keyword`）的 `--sxx`/`--effect1` 不得挪到案例接口。

**硬校验**：用 `scripts/validate-query-filters.py <research-plan.json>` 自动校验 filter×interface 合法性（退出码 0 合法 / 1 有违规，可接 CI 或 pre-commit hook）。单条 query 可用 `--query '{"interface":"case","filters":{...}}'`。字段表与本节一致，以 `yd_search.py` 各 subparser 为权威。

## 10. 策略与法律检索解耦（[DEC-006] pt 6）

`economical` / `balanced` / `aggressive` 只控制**调用预算与深度**（试几条 query、是否自动跑语义+关键词双检索、是否自动拉 case-detail），**不得**改变：

- 争点识别与要件拆解；
- 接口路由与字段适配；
- 对位度门槛（HIGH/MEDIUM/LOW/MISMATCH）；
- 反向检索与近邻排除。

## 11. 对位度标签（结果复核）

| 标签 | 含义 |
|---|---|
| `HIGH` | 法律问题相同，主体关系、行为链条、决定性事实基本覆盖，可作主要类案/主要法源 |
| `MEDIUM` | 法律问题相同，但缺一项决定性事实或程序背景不同，仅作辅助 |
| `LOW` | 仅主题/行业/案由相近，不能直接支撑核心结论 |
| `MISMATCH` | 争点、主体角色、行为模式或裁判命题不同，应排除 |

首轮结果按此标签复核；只有诊断出偏差原因（接口误选 / 表达不适配 / 近邻混入）后，才允许扩展查询或换接口。

## 12. 机器可读导出骨架（Task-004 预留）

为支持 Agent Eval Lab 与人工复盘，案件检索建议导出以下结构（字段稳定，不绑定特定评测平台格式）：

```json
{
  "research_brief": { /* §3 字段 */ },
  "propositions": [ /* §4 */ ],
  "queries": [ /* §5 */ ],
  "results": [
    { "result_id": "", "backend_score": null, "relevance_label": "HIGH|MEDIUM|LOW|MISMATCH",
      "include": true, "reason": "" }
  ],
  "conclusion_links": [
    { "conclusion": "", "proposition_id": "", "query_id": "", "result_ids": [] }
  ],
  "run_meta": { "skill_version": "", "strategy_version": "", "model": "", "live": false, "credits": 0 }
}
```

脱敏要求：导出对象不得包含未脱敏案件全文、API Key 或 live 响应原文；冻结响应的版本策略见 Task-004。
