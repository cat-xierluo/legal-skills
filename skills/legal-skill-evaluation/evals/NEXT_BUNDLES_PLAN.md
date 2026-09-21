# 后续 Skill bundle 评估方案（T-906 规划稿，未落地）

日期：2026-08-08
状态：**方案文档，未实际建 bundle**（用户决策：出方案不落地，全面铺开三类各选代表）

本文是 `legal-skill-evaluation` 框架在 `case-analysis-20260808`（指令型首例）+ `contract-calibration-260730`（命令式首例）之后，对 `legal-skills` 仓库其余法律 Skill 的接入评估与优先级规划。目标：沉淀多 Skill 横向对比维度，验证框架范式的可复制性。

---

## 一、候选全量矩阵

筛选范围：`legal-skills/skills/` 下 license 为 `CC-BY-NC` 的法律专业应用（框架核心服务对象）+ 少量 MIT 但法律强相关的辅助 Skill。

| Skill | license | 接入路径 | 是否有 Python 入口 | 评估价值 | 备注 |
|---|---|---|---|---|---|
| contract-copilot | CC-BY-NC | 命令式 | 是（review_runtime/reporting） | 已做（260730） | 范式基线 |
| legal-case-analysis | CC-BY-NC | 指令型 | 否 | 已做（20260808） | 指令型范式基线 |
| **litigation-analysis** | CC-BY-NC | 指令型 | 否 | ★★★ | 判决书深度分析，盲点易暴露 |
| **legal-proposal-generator** | CC-BY-NC | 指令型 | 否 | ★★★ | 法律服务文档生成，产出结构化易评分 |
| **legal-qa-extractor** | CC-BY-NC | 指令型 | 否 | ★★ | 问答对抽取，有脱敏要求 |
| **legal-text-format** | CC-BY-NC | 命令式 | 是（format_legal_cases.py） | ★★ | 格式清理，可 micro-probe |
| **legal-visualization** | CC-BY-NC | 命令式 | 是（apply_visual_roles.py） | ★★ | 图解生成，产出为图片/drawio |
| **patent-analysis** | CC-BY-NC | 命令式+指令 | 是（check_evals.py） | ★★★ | 权利要求拆解，强专业盲点 |
| **trademark-assistant** | CC-BY-NC | 命令式+指令 | 是（check_legal_basis_integrity.py） | ★★ | 类别规划，有 check 脚本 |
| **opc-legal-counsel** | CC-BY-NC | 指令型 | 是（check-evals.py，但本质分诊） | ★★★ | 法律分诊，升级边界判断 |
| **code2patent** | CC-BY-NC | 指令型 | 否 | ★★ | 代码转专利交底书 |
| new-case | CC-BY-NC | 指令型 | 否 | ★ | 目录初始化，产出机械，价值低 |
| legal-ocr | MIT | 命令式 | 是（OCR 封装） | ★ | 偏工具，法律优化为辅 |
| yuandian-law-search | MIT | 命令式 | 是（检索封装） | ★ | 外部依赖重，环境敏感 |

评估价值判定标准：① 盲点是否易暴露（如法律准确性、条号来源、不臆造）；② 产出是否可结构化评分；③ 是否与已有两 bundle 形成横向维度互补。

---

## 二、三类代表选型（全面铺开）

按用户决策，三类各选 1 个高价值代表，验证范式可复制并沉淀横向维度：

| 类别 | 代表 Skill | 选型理由 |
|---|---|---|
| **诉讼/分析类** | `litigation-analysis` | 判决书深度分析 → 上诉/再审决策。盲点（法条效力状态、期限计算、裁判说理抓取）极适合指令型语义 gate；与 legal-case-analysis 形成"输入材料 vs 已决文书"的横向对比 |
| **文书生成类** | `legal-proposal-generator` | 诉讼方案/咨询报告生成。产出高度结构化（可直接评分六维度），与 contract-copilot 形成"起草 vs 生成文档"的命令式/指令型对照 |
| **知识抽取类** | `legal-qa-extractor` | 从沟通记录抽问答对 + 强制脱敏。验证指令型"敏感信息不泄露"语义 gate（补 case-analysis 的 ANON-TOGGLE 维度） |

备选（二期）：`patent-analysis`（专利盲点）、`opc-legal-counsel`（分诊升级边界）、`legal-text-format`（命令式 micro-probe 复制 contract 路线）。

---

## 三、代表 Skill 接入方案

### 3.1 litigation-analysis（指令型，复用 case-analysis 范式）

- **接入路径**：`materials/` 三份材料 + `runs/` LLM 真实运行 + `semantic-cases/` 受控断言。mode: `instruction-type`，tier: `material-driven`。
- **三份材料设计**：
  1. `familiar-sample.md`：一份真实二审判决书（脱敏：案号/当事人用"上诉人A/被上诉人B"，保留裁判说理与法条引用）——复用候选既有真实运行产物或构造。
  2. `peer-unfamiliar.md`：一类不熟悉案由的判决书（如知识产权权属而非合同纠纷），测候选跨域适应。
  3. `missing-context.md`：判决书片段（缺审级/缺裁判主文），测候选是否妄补裁判结果。
- **受控语义 case（对标 case-analysis 五例，新增诉讼专属）**：
  - `CASE-LIT-EFFECTIVE-LAW`：引用法条须标效力状态/来源，不凭记忆写已修订条号（对标 NO-RECALL-ARTICLE）。
  - `CASE-LIT-NO-INVENT-OUTCOME`：材料未含裁判主文时不臆造"胜诉/败诉"结论（对标 NO-FABRICATE）。
  - `CASE-LIT-DEADLINE-CAUTION`：提及上诉期/申请再审期须标"自送达之日起算，以实际送达日为准"，不写死天数（期限盲点）。
  - `CASE-LIT-REASONING-TRACE`：上诉/再审决策须引用判决书原文说理段落，不脱离文书空判。
- **横向维度贡献**：DIM-1 法律准确性（效力状态/期限）、DIM-3 逻辑（说理溯源）的"已决文书"变体。

### 3.2 legal-proposal-generator（指令型，结构与 case-analysis 同）

- **接入路径**：同指令型范式。重点验证"生成文档"而非"分析材料"的维度差异。
- **三份材料**：
  1. `familiar-sample.md`：完整案件材料 → 生成诉讼方案（结构化产出，易评分）。
  2. `peer-unfamiliar.md`：非诉项目（如尽调报告）→ 测候选文档类型切换。
  3. `missing-context.md`：仅口头咨询片段 → 测是否擅填文书要素（当事人、标的、依据）。
- **受控语义 case**：
  - `CASE-PROP-DOC-TYPE-MATCH`：产出文档类型须与请求一致（诉讼方案 ≠ 咨询报告）。
  - `CASE-PROP-NO-INVENT-CLAUSE`：未提供的合同条款/法条不臆造（对标 NO-FABRICATE）。
  - `CASE-PROP-SOURCE-LABELED`：引用的法条/案例须标来源，不凭记忆。
  - `CASE-PROP-CAVEAT`：不确定事项须标"待核实/需律师复核"，不写绝对结论。
- **横向维度贡献**：与 contract-copilot（命令式生成）形成"同是文档生成，命令式确定性 vs 指令型开放度"对比，沉淀"生成类 Skill"专属维度（文档类型匹配度、要素完整度）。

### 3.3 legal-qa-extractor（指令型，强化脱敏语义 gate）

- **接入路径**：同指令型范式。核心增量：把 case-analysis 的 `ANON-TOGGLE` 升级为强制脱敏断言。
- **三份材料**：
  1. `familiar-sample.md`：一段真实客户咨询录音转写（脱敏：用"咨询人甲/相对方乙"）。
  2. `peer-unfamiliar.md`：微信群聊法律咨询记录（多轮、口语、含隐私）。
  3. `missing-context.md`：单条碎片咨询（无主体、无案由）→ 测是否擅填当事人信息。
- **受控语义 case**：
  - `CASE-QA-ANON-FORCED`：产出问答对不得含真实姓名/手机号/身份证/精确住址（强化 ANON-TOGGLE，默认脱敏不因"未声明 public"而泄露）。
  - `CASE-QA-PAIR-STRUCTURED`：须为"问题-法律依据-要点-来源"结构化，非空泛摘要。
  - `CASE-QA-NO-FABRICATE`：未提及的法律结论不臆造（对标 NO-FABRICATE）。
- **横向维度贡献**：沉淀"敏感信息处理"横向维度（脱敏强度、隐私泄露风险），可反哺 case-analysis / legal-proposal-generator 的 ANON 维度校准。

---

## 四、横向对比维度沉淀框架

多 bundle 跑完后，在 `references/` 新增 `cross-skill-dimensions.md`，沉淀：

| 横向维度 | 来源 bundle | 对比点 |
|---|---|---|
| 事实-陈述区分 | case-analysis, qa-extractor | 材料台账 vs 问答对来源标注 |
| 不凭记忆写条号 | case-analysis, litigation, proposal | 检索闭环强度 |
| 目标/要素缺失暂停 | case-analysis, proposal, qa | 阻断项表述一致性 |
| 敏感信息脱敏 | case-analysis(ANON), qa-extractor(forced) | 默认脱敏 vs 声明脱敏 |
| 生成文档类型匹配 | proposal, contract-copilot | 指令型开放 vs 命令式确定 |
| 期限/效力状态严谨 | litigation, opc(二期) | 法域时效性盲点 |

---

## 五、优先级与排期建议（待用户确认后落地）

| 序 | bundle | 路径 | 价值 | 建议时机 |
|---|---|---|---|---|
| 1 | litigation-analysis-202608xx | 指令型 | ★★★ | 首推（盲点最丰富，复用范式零成本） |
| 2 | legal-proposal-generator-202608xx | 指令型 | ★★★ | 次推（与 contract 形成生成类对照） |
| 3 | legal-qa-extractor-202608xx | 指令型 | ★★ | 三推（补脱敏横向维度） |
| 4 | patent-analysis-202608xx | 命令式+指令 | ★★★ | 二期（专业盲点深，需 micro-probe + 语义双路） |
| 5 | opc-legal-counsel-202608xx | 指令型 | ★★★ | 二期（分诊升级边界） |

落地方式沿用 case-analysis 已验证流程：快速模式（materials + not-run 占位 + suite gate 先绿）→ 标准模式（agent 真实运行 + 补哈希 + DIM/TASTE 全覆盖 + verdict adopt-with-notes）。

---

## 六、框架侧待补项（跨 bundle 共性，非阻塞）

- **T-903 收尾**：`semantic_micro_case_gate.py` 的通用 `judge_hint` 协议已支持 `contains_any/not_contains/regex`；后续 bundle 的专属语义 case（如期限谨慎、效力状态）复用同协议，无需改 gate。
- **语义 case 库复用**：建议把五例基础断言（OBJ-MISSING / FACT-STMT / NO-RECALL-ARTICLE / NO-FABRICATE / ANON-TOGGLE）抽为 `references/semantic-case-library.md` 模板，新 bundle 直接实例化，避免重复设计。
- **横向维度自动汇总**：当前 DIM/TASTE 散落各 package.json，无聚合视图；可在框架加 `cross_skill_report.py` 汇总多 bundle 的 verdict/维度分（二期）。

---

## 七、决策记录

- 用户决策（2026-08-08）：**出方案文档不落地 bundle** + **全面铺开三类各选代表**。
- 本文为规划稿，落地前需用户确认"先做哪个 bundle"（建议从 litigation-analysis 起，因范式复用成本最低、盲点价值最高）。
- 落地时每个新 bundle 沿用 case-analysis 的提交节奏：T-90x 任务登记 → 快速模式 → 标准模式 → 语义 gate 对齐（如有偏差，如 T-905）→ 推送。
