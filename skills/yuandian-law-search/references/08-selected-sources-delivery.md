# Agent 精选来源与交付门禁

本 reference 的 JSON 合同仅用于用户要求的报告／研究包，不是普通对话检索的必经步骤。对话直接说明精选依据和核验边界；不为答复先写两个 JSON。

## 1. 核心边界

```text
问题 → API/MCP 候选召回
  → Agent 逐条法律相关性复核
  → 直接对话答复
  → 用户要求报告时才整理 research-plan.json + selected-sources.json
  → 正式报告

完整响应、per-call .md/.json
  → archive/（数据底稿）
  ↛ 正式报告正文
```

- MCP/API、后端 `score` 和查询命中只证明“返回了候选”，不证明“可以作为本案依据”。
- Agent 负责判断请求权基础、规范适用、主体关系、行为链条、决定性事实和正反方向是否对位。
- 脚本只负责字段、命题映射、核验声明、去重、法源排序、引用可追溯和报告隔离等确定性检查，不根据标题或关键词替代法律判断。
- `LOW`、`MISMATCH` 和 `verification_status != verified` 的材料不得进入正式交付。

## 2. 三种输出模式

| 模式 | 默认条件 | 输出 | 原始召回 |
|---|---|---|---|
| 对话研究答复 | 默认 | 结论、关键前提、风险和少量精选依据；不要求 JSON | 不强制另行归档 |
| 精选研究包 | 用户要求留痕、复核或交接 | `research-plan.json` + `selected-sources.json` + 必要说明 | 仅归档，可链接 |
| 正式法律检索报告 | 用户明确要求正式报告或落盘 | 结论先行报告，只消费精选清单 | 仅在末尾列调用轨迹，不复制正文 |

检索深度与输出长度相互独立。不再用 `aggressive` 自动增加查询；原生默认可能返回很多候选，仍只保留解释结论必需的来源。单争点报告使用 [focused 记录](03-report-consolidation.md)。

## 3. `selected-sources.json` 合同

```json
{
  "schema_version": "1.0",
  "case_id": "与 research plan 一致",
  "selected_sources": [
    {
      "source_id": "S-01",
      "source_type": "law",
      "title": "来源标题",
      "citation": "可直接引用的法规名称+条号，或案例案号",
      "proposition_ids": ["P-01"],
      "relevance_label": "HIGH",
      "priority": "core",
      "stance": "support",
      "rule_or_holding": "与命题直接相关的规则或裁判要旨摘要",
      "applicability": "主体、行为链条、决定性事实为何与本案对位",
      "verification_status": "verified",
      "verification_note": "如何核验真实性、文本和时效",
      "validity_status": "current",
      "trace": {
        "query_ids": ["Q-01"],
        "source_url": "https://...",
        "archive_ref": "archive/<project>/<file>.json"
      }
    }
  ],
  "unresolved_propositions": [
    {
      "proposition_id": "P-02",
      "reason": "未取得足够对位且可核验的依据",
      "next_action": "补充事实后重新检索，或改用指定接口复检"
    }
  ],
  "excluded_candidates": [
    {
      "candidate_id": "R-09",
      "title": "候选标题",
      "relevance_label": "MISMATCH",
      "reason": "请求权基础或决定性事实不同",
      "query_id": "Q-01"
    }
  ]
}
```

### 字段规则

- `source_type` 按法律位阶和材料性质取值：`constitution`、`law`、`judicial_interpretation`、`administrative_regulation`、`local_regulation`、`department_rule`、`guiding_case`、`typical_case`、`case`、`other`。
- `relevance_label` 只允许 `HIGH` / `MEDIUM`。`LOW` / `MISMATCH` 进入 `excluded_candidates`，不进入 `selected_sources`。
- `priority` 取 `core` / `supplementary`；`stance` 取 `support` / `oppose` / `mixed`。`core` 必须为 `HIGH`，`MEDIUM` 只能作补充依据。
- `verification_status` 在正式报告中必须为 `verified`。核验至少覆盖来源存在、引用内容一致；规范性法源还要核对时效和适用范围。
- 规范性法源的 `validity_status` 为 `current` 或 `historical`；当前脚本尚不接受历史法源作 `core`。这是报告能力限制，不是旧案不得适用旧法；遇此情形披露限制、保留时间适用分析，不伪标 current。案例使用 `not_applicable`。
- `proposition_ids` 必须存在于本次 research plan；`trace.query_ids` 必须存在，且其父命题属于该来源的 `proposition_ids`。
- `trace.source_url` 和 `trace.archive_ref` 至少提供一项。链接和归档只是可追溯证据，不能替代 `applicability`。
- 每条决定性命题必须至少有一条精选来源，或显式进入 `unresolved_propositions`；不得用沉默掩盖检索失败。

## 4. Agent 逐条复核问题

对拟采用的来源核查下列问题；显然不对位的候选直接排除，不逐条写长评语：

1. 它支持或反对哪个具体命题，而不是笼统属于哪个案由？
2. 规范是否真的适用于本案主体、客体、行为和时间？
3. 案例的请求权基础、主体角色、行为链条和决定性事实是否对位？
4. 它提供的是规范依据、概念解释、裁判规则、事实类比还是背景信息？
5. 是否存在更新法源、更高位阶法源或更直接的司法解释？
6. 如果排除，属于仅主题相似、要件不同、事实不同、程序不同还是来源未核验？

后端排名只决定阅读顺序。不得因为结果排在前列、标题包含关键词或被多个查询重复命中，就自动提高法律相关性。

## 5. 法源排序与篇幅控制

正式报告先按 `priority` 排核心与补充，再按下列顺序排列：

1. 宪法、法律；
2. 司法解释；
3. 行政法规；
4. 地方性法规、部门规章；
5. 指导性案例、典型案例、普通司法案例；
6. 其他核实材料。

案例不得混入“规范性法律依据”。相同法条或同一案例只保留一条；同一命题存在多条重复材料时，优先保留位阶更高、效力明确、事实更对位、来源更可核验的材料。数量是阅读预算而不是命中数量：**一份正式报告最多 12 条精选来源**，只保留解释结论所必需的材料。超出时应去重、保留更高位阶／更对位依据，或拆成用户明确要求的专题附件；不设置“召回多少就展示多少”的比例。

`excluded_candidates` 的完整名称和逐条理由只留在 JSON 归档。正式报告仅显示排除数量，避免无关标题再次污染正文。

## 6. 确定性门禁

只有选择 schema 1.0 完整深度计划时，执行前检查：

```bash
scripts/validate-research-contract.py --plan research-plan.json
```

正式报告前：

```bash
scripts/validate-research-contract.py \
  --plan research-plan.json \
  --selection selected-sources.json
```

退出码：

- `0`：结构、接口字段和交叉映射合法；不代表实体法律判断已经由机器证明正确。
- `1`：合同违规，阻断本次完整计划执行或正式报告生成；普通对话无此文件前置要求。
- `2`：文件、JSON 或校验器初始化错误，停止执行。

`consolidate` 会再次校验研究计划与精选清单，缺少清单、空清单、超过 12 条、未核验来源、未知命题、`LOW/MISMATCH`、重复引用或决定性命题无去向时失败关闭。

## 7. 正式报告调用

只有用户明确要求正式报告或落盘时运行：

```bash
scripts/yd-run consolidate \
  --title "案件主题" \
  --project "项目目录名" \
  --case "案情简介" \
  --strategy "涵摄缺口、接口路由与复检过程" \
  --analysis "结合精选依据完成的法律分析" \
  --conclusion "附条件的明确结论" \
  --research-plan research-plan.json \
  --selection selected-sources.json \
  --include "可选：仅用于归档和列示原始 per-call 调用的查询子串"
```

第六节只渲染 `selected_sources`。`--include` 不再具有“纳入正文”的含义，只负责把原始检索调用归档进项目包并在第七节列出轨迹。

## 8. Hard Fail

- 直接把 MCP/API 响应或 per-call 报告整体写入正式报告。
- 用查询文件名、关键词、endpoint 分组或后端分数代替 Agent 逐条精选。
- 把案例、典型案例写进规范性法律依据。
- 纳入失效但未说明历史用途的法源，或纳入与本案主体／客体明显不适用的专项规则。
- 对决定性命题既无精选依据，也不披露尚未解决。
- 因候选量增加而降低精选门槛或增加正文材料数量。
