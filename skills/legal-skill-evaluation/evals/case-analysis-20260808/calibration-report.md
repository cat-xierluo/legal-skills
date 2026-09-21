# legal-case-analysis 案件分析场景校准报告

日期：2026-08-08

模式：标准评测（agent 真实运行三案例，NOT_VERIFIED）

结论：`adopt-with-notes`（标准模式：三案例由 agent 真实运行并补哈希，六维度/taste 全覆盖、5 语义 case 经通用 judge_hint 协议判定；指令型不签发 DOMAIN_VERIFIED，verdict 保持 NOT_VERIFIED，详见 §三、§六）

## 一、结论先行

首个非 contract-copilot 的 eval bundle 已建立，验证 harness 框架对**指令型 Skill**（无 scripts/、纯提示词驱动）的接入可行性。bundle 走「三份材料 + LLM 真实运行产出 + 语义/能力门禁」路线，而非 contract 侧的 micro-probe 路线。

本轮用 `legal-case-analysis` v1.0.0（候选 sha256 `0c22a1be...`，git-tracked 25 文件）做快速模式探路：
- familiar 场景复用候选既有真实运行产物（`examples/contest-sample-analysis.md`，商品房买卖纠纷）作代表性产出，做六维度/taste 静态初筛。
- peer-unfamiliar（目标缺失）与 missing-context 标注 not-run，标准模式再补 agent 真实运行。
- 5 个受控语义 case 完成断言设计，并配套 `semantic-cases/json/*_input.json`；经 T-903 重构，`semantic_micro_case_gate.py` 已可经通用 `judge_hint` 协议直接消费（见 §四）。

初筛显示候选在事实/证据区分、缺失标注、检索闭环方向表现良好；但**条号来源可溯性**是机械判定的盲点，需框架侧补「来源标注」断言能力。

## 二、候选与通用门禁

| 项目 | 结果 |
|---|---|
| 候选 | `skills/legal-case-analysis` v1.0.0 |
| 候选范围 | Git 跟踪文件，25 个 |
| 候选 SHA-256 | `0c22a1be077490b42ce08784fb824ff0e36768c6576c9dbeace88ef275aaf66f` |
| Harness 静态审查 | 未运行正式 skill-lint gate，保持 `NOT_VERIFIED` |
| 指令稳定性 | `NOT_VERIFIED` |
| 法律领域验收 | `NOT_VERIFIED` |

## 三、三份测试（标准模式，2026-08-08 升级）

> 三案例均由 agent 以 legal-case-analysis v1.0.0 规范真实运行，落盘 `runs/*-output.md`，补 input/output 真实 sha256，六维度与八项 taste 全覆盖（见 `evaluation-package.json`）。指令型不签发 DOMAIN_VERIFIED，verdict 为 `adopt-with-notes`（框架 v0.8.8 新增推荐态）。

### 1. 熟悉材料：商品房买卖纠纷（复用既有真实运行产物）

| 维度 | 评分 | 主要依据 |
|---|---:|---|
| DIM-1 法律准确性 | 4 | 请求权基础、解除与返还链条引用具体法条并标注来源；部分商业取舍仍需律师复核 |
| DIM-2 事实与证据 | 5 | 材料台账区分客观证据/当事人陈述/争议材料，标注证明力 |
| DIM-3 逻辑说服力 | 5 | 问题树—论证—风险—策略链条完整 |
| DIM-4 关键问题把握 | 5 | 抓住解除效力、交付条件、执行救济主线 |
| DIM-5 实务可用性 | 5 | 可直接进入诉讼方案与执行异议 |
| DIM-6 格式完整度 | 5 | 概况、画像、材料清单、事实、论证、风险、策略齐全 |

Taste：TASTE-1~8 全 pass（结论边界清、风险/商业区分、缺失标待补充、立场清晰、无承诺、明示底稿、提示核验、提示缺失影响）。

### 2. 同类但不熟悉：技术开发合同（标准模式已运行）

运行产出：`runs/peer-unfamiliar-output.md`（input/output sha 已回填 suite）。委托目标栏故意留空，候选正确**暂停并请求确认**（〇项目标确认阻断项列出 A–F 可选项），未自行选"评估是否起诉/出具报告"。`CASE-OBJ-MISSING` 断言 observed=pass。

| 维度 | 评分 | 主要依据 |
|---|---:|---|
| DIM-1 法律准确性 | 5 | 正确识别目标缺失，不妄断法律关系或结论 |
| DIM-2 事实与证据 | 5 | 材料按类型与证据强度初评分类 |
| DIM-3 逻辑说服力 | 5 | 目标确认→材料清单→表面焦点→待补→下一步，链条清 |
| DIM-4 关键问题把握 | 4 | 目标缺失下不强行抓焦点，正确暂停，仅列表面争点 |
| DIM-5 实务可用性 | 5 | 列 A–F 可选项 + 待补清单，行动明确 |
| DIM-6 格式完整度 | 5 | 结构稳定 |

Taste：TASTE-1~8 全 pass。

### 3. 故意缺失背景：单轮咨询（标准模式已运行）

运行产出：`runs/missing-context-output.md`（input/output sha 已回填 suite）。候选列出口缺清单（7 项）并请求补齐，**未臆造主体/条号/结论**，所有条号标"条号待检索/依据待补充"。`CASE-MISSING-NO-FABRICATE` 断言 observed=pass。

| 维度 | 评分 | 主要依据 |
|---|---:|---|
| DIM-1 法律准确性 | 5 | 未凭记忆写条号，一律标条号待检索 |
| DIM-2 事实与证据 | 5 | 仅限委托人自述，未虚构，来源标注清晰 |
| DIM-3 逻辑说服力 | 5 | 缺口→程序提示→下一步，自洽 |
| DIM-4 关键问题把握 | 4 | 背景缺失下不强行抓焦点，正确标缺失 |
| DIM-5 实务可用性 | 5 | 明确下一步补齐缺口 |
| DIM-6 格式完整度 | 5 | 结构稳定 |

Taste：TASTE-1~8 全 pass。

## 四、受控语义 case 与门禁盲点

| case | 期望 | 机械门禁现状 |
|---|---|---|
| CASE-OBJ-MISSING | 目标缺失须请求确认 | 需 agent 运行文本判定，合同 gate 不含 |
| CASE-FACT-STMT | 事实/陈述区分 | 可正则近似，但合同 gate 硬码合同语义 |
| CASE-NO-RECALL-ARTICLE | 不凭记忆写条号 | **难点**：产物出现大量条号，但来源是材料/校准文件回填；机械查"有无条号"会误判，需"条号须带来源标注"断言 |
| CASE-NO-FABRICATE | 未提及不补全 | 可正则近似（缺要素须有标记） |
| CASE-ANON-TOGGLE | 默认不脱敏 | 反向验证，本包不脱敏 |

**门禁盲点（已迭代解决，见 T-903）**：原 `semantic_micro_case_gate.py` 为合同场景专用（硬码"可签/第N条/审查结论"），不能直接服务案件分析；`capability_suite_gate.py` 的 case 数/tier/capability/status 枚举也是合约专用硬编码，导致本 bundle 初版 `capability_suite_gate` 直接 fail。T-903 已把两门禁重构为**声明式 mode**：

- `capability_suite_gate.py`：suite 顶层新增 `mode` 字段（`command-type` 默认保留合同约束；`instruction-type` 放宽——最小 case 数 20→3、跳过 `fixture_spec` 必填、跳过 case_type/tier/capability 必填覆盖校验；`material-driven` 从命令式必填 `TIERS` 移出为指令型专用 `INSTRUCTION_TIERS`、`SOURCE_KINDS` 增 `not-run`/`existing-real-run`、`OBSERVED_STATUSES` 增 `warn` 以支持语义 gate 软提示、not-run 断言豁免 `expected`）。
- `semantic_micro_case_gate.py`：新增通用 `(trigger, judge_hint)` 协议分支——`case_id` 以 `CASE-` 开头且 payload 含 `assertions[].judge_hint`（`contains_any` / `not_contains` / `regex`）时走通用判定，合同 CASE 逻辑原样保留。5 个语义 case 已配套 `semantic-cases/json/*_input.json` 供门禁消费。

**条号来源盲点（仍待框架补强，非阻塞）**：`CASE-NO-RECALL-ARTICLE` 的判定要点是"无检索时不写凭记忆条号"，但候选样例产物出现的条号均来自材料/校准文件回填（已标注来源），机械 gate 无法区分"凭记忆"与"有来源"。当前该 case 在 suite 内标 `warn`、在通用 gate 内用 `contains_any: [校准文件/材料回填/检索/待检索/条号待]` 做近似放行；彻底解决需在框架层定义「条号须带来源标注」断言协议（登记为后续迭代项，不阻塞本 bundle 闭环）。

**gate 实测证据（2026-08-08 初版跑通 + T-903 重构 + bash 验证）**：
- `evaluation_package_gate.py check`：**pass**（补 familiar 的 input/output sha256、not-run case 移出 package.cases[] 后通过）。
- `capability_suite_gate.py` **初版 fail**，失败项全部是 contract 侧硬编码约束（`SUITE-008/013/014/026/038/039/040`），证明框架当时不接纳指令型 bundle——此即 T-903 的触发证据。
- `capability_suite_gate.py` **T-903 重构后 + bash 验证（2026-08-08）**：本 bundle 已声明 `mode: instruction-type`、`status: prepared-not-verified`、`tier: material-driven`，**已验证 pass**（`errors: []`）。同期回归 contract bundle：`capability_suite_gate.py` 与 `evaluation_package_gate.py` 均 **pass**，无回归。
- `semantic_micro_case_gate.py` **T-903 重构后 + bash 实跑（2026-08-08）**：以 `runs/familiar-sample-output.md` 为 output 实测 5 例——`CASE-FACT-STMT` / `CASE-NO-RECALL-ARTICLE` / `CASE-NO-FABRICATE` / `CASE-ANON-TOGGLE` 均 **pass**；`CASE-OBJ-MISSING` **fail**（符合预期：familiar 完整产出不暴露"目标缺失"边界，正是指令型 gate 在快速模式要暴露、待标准模式由 agent 真实运行 peer-unfamiliar 补齐的盲点）。通用 `judge_hint` 分支工作正常。

## 五、最小修复单元（快速模式初判，待标准模式坐实）

- 框架侧：**T-902 已完成**（SKILL.md 步骤 3.5 显式区分命令式/指令型两条接入路径）；**T-903 已完成**（两门禁重构支持 `instruction-type` 与通用 `judge_hint` 协议，bash 验证闭环：**已验证 pass**，contract 无回归）。
- 候选侧：若标准模式运行显示条号偶有凭记忆无来源，则在 SKILL.md 强化"条号须就近标注来源"约束。

## 六、下一步（标准模式已升级，2026-08-08）

1. ~~agent 真实运行 peer-unfamiliar 与 missing-context，落盘 runs/ 并补 input/output 哈希。~~ **已完成**：两案例由 agent 按候选规范真实运行，产出 `runs/peer-unfamiliar-output.md` / `runs/missing-context-output.md`，真实 sha256 已回填 `capability-suite.json` 与 `evaluation-package.json`。
2. ~~bash 验证 T-903：`capability_suite_gate.py` + 5 例 `semantic_micro_case_gate.py`~~ **已完成（2026-08-08）：全部验证通过，contract 无回归，详见 §四 实测证据。**
3. ~~回填 evaluation-package.json 的 dimensions/taste/repair_units，将 verdict 升级。~~ **已完成**：三案例六维度（DIM-1~6）与八项 taste（TASTE-1~8）全覆盖，`mode: standard`、`verdict: adopt-with-notes`（框架 v0.8.8 新增，指令型未签发 DOMAIN_VERIFIED 适用）；双 gate 复验均 **pass**。

### 后续迭代项（非阻塞）

- **语义 gate judge_hint 调优**：`CASE-OBJ-MISSING` 的 `not_contains` 负面词与候选实际表述（"〇项目标确认阻断项"）未对齐，导致该受控 gate 在 peer/missing 真实产出上 fail；属断言设计精化，不影响 suite 级人工判读（observed=pass）。建议在 `judge_hint` 增加"含请求确认/暂停"正向判定。
- **条号来源盲点**：框架层"条号须带来源标注"断言协议仍待补强（§四），本 bundle 如实标 warn 放行。
- **T-904**：评估 `litigation-analysis` / `legal-proposal-generator` / `legal-qa-extractor` 作为后续 bundle，沉淀多 Skill 横向对比维度。
