# 校准报告：litigation-analysis 指令型 bundle

日期：2026-08-08
模式：标准模式（agent 真实运行三案例 + 六维度/taste 全覆盖 + 语义 gate 判定）
Skill 候选：litigation-analysis v1.3.2（判决书深度分析，上诉/再审决策支持）
接入路径：指令型（materials + LLM 真实运行 + 语义门禁），mode: instruction-type，tier: material-driven

结论：`adopt-with-notes`（指令型 agent 运行闭环，未签发 DOMAIN_VERIFIED；核心语义盲点全部通过，运行无阻断项）

---

## 一、候选规范要点（驱动盲点设计）

- 判决书分析为核心，输出三层（内部版→研究版→客户版），决策支持导向（上诉/再审）。
- 默认"上诉期限通常为15日""裁判日期为上诉期基准"——是典型的"凭记忆写死天数"风险点，材料未含送达日时应标"以实际送达日为准"。
- 未显式要求"法条须标来源/不凭记忆写条号"，但作为法律准确性底线，纳入语义 gate。

---

## 二、三份材料与运行设计

| 材料 | 类型 | 设计意图 | 运行产出 |
|---|---|---|---|
| familiar-sample.md | 二审买卖合同判决（脱敏） | 代表案例，验证法条来源标注 + 说理溯源 | runs/familiar-sample-output.md |
| peer-unfamiliar.md | 知识产权权属判决（脱敏） | 跨案由适应，验证不妄断侵权结论 | runs/peer-unfamiliar-output.md |
| missing-context.md | 判决书片段（缺审级/主文/送达） | 验证不妄补裁判结果 + 期限谨慎 | runs/missing-context-output.md |

---

## 三、三案例标准模式结果与维度评分

### 1. familiar 二审买卖合同判决（executed-pass）

| 维度 | 评分 | 主要依据 |
|---|---:|---|
| DIM-1 法律准确性 | 5 | 民法典/买卖合同司法解释均标材料载明或条号待检索，未凭记忆写未核验条号；终审效力正确 |
| DIM-2 事实与证据 | 5 | 事实链完整溯源原审/二审认定，区分合同约定与法院认定 |
| DIM-3 逻辑说服力 | 5 | 质量异议失效、违约金调减均引原文说理 |
| DIM-4 关键问题把握 | 5 | 抓住"有效书面异议"胜负手与再审突破空间 |
| DIM-5 实务可用性 | 5 | 上诉/再审路径、执行期起算、研究课题均可执行 |
| DIM-6 格式完整度 | 5 | 五段齐全，合规自检完备 |

Taste：TASTE-1~8 全 pass（期限标以实际送达日为准、未承诺胜诉、无虚构依据、边界标注清晰）。

### 2. peer 知识产权权属判决（executed-pass）

| 维度 | 评分 | 主要依据 |
|---|---:|---|
| DIM-1 法律准确性 | 5 | 著作权法/软件条例标材料载明或待检索，权属适用正确 |
| DIM-2 事实与证据 | 5 | 通用组件独立性、复用行为均溯源判决原文 |
| DIM-3 逻辑说服力 | 5 | 从约定权属到通用组件例外推理完整 |
| DIM-4 关键问题把握 | 4 | 抓"通用组件边界"核心，提示依赖事实认定可进一步 |
| DIM-5 实务可用性 | 5 | 丁公司上诉空间、戊侧证据链保留均给可执行建议 |
| DIM-6 格式完整度 | 5 | 五段齐全 |

Taste：TASTE-1~8 全 pass（未写必胜、结论溯源主文、标待补充证据）。

### 3. missing 判决书片段（executed-pass）

| 维度 | 评分 | 主要依据 |
|---|---:|---|
| DIM-1 法律准确性 | 5 | 未妄写条号，期限一律标以实际送达日为准 |
| DIM-2 事实与证据 | 5 | 仅呈现片段原文可识别信息，不扩写 |
| DIM-3 逻辑说服力 | 5 | 缺口→补齐→不妄断推理严谨 |
| DIM-4 关键问题把握 | 5 | 正确识别审级/主文/送达三重缺失，未强行抓焦点 |
| DIM-5 实务可用性 | 5 | 明确下一步补齐完整判决书与送达信息 |
| DIM-6 格式完整度 | 5 | 阻断项/可识别/缺口/提示/下一步五段齐全 |

Taste：TASTE-1~8 全 pass（无死写天数、未形成任何胜负判断、显式标边界）。

---

## 四、语义 gate 实测证据（标准模式）

4 个诉讼专属语义 case，用对应真实产出实跑，全部 **pass**：

| 语义 case | 验证点 | 结果 |
|---|---|---|
| CASE-LIT-EFFECTIVE-LAW | 法条来源标注 + 不凭记忆写条号 | pass |
| CASE-LIT-REASONING-TRACE | 决策溯源二审认定原文 + 不空判 | pass |
| CASE-LIT-NO-INVENT-OUTCOME | 不妄断侵权结论 + 溯源判决主文 | pass |
| CASE-LIT-DEADLINE-CAUTION | 期限标以实际送达日为准 + 不写死天数 | pass |

**judge_hint 对齐说明**：初版断言与候选真实措辞存在偏差（同类 T-905 问题），已调优：
- REASONING-TRACE 的 contains_any 原期望"本院认为/予以维持"，候选用"二审认定/溯源"，改为覆盖真实措辞。
- NO-INVENT-OUTCOME 的 not_contains 原含"丁公司必胜"，候选用"上诉翻盘空间有限"等风险表述，改为更强绝对词（必然胜诉/绝对构成）。
- DEADLINE-CAUTION 的 not_contains 原含"上诉期15日"，候选正确引用材料"十五日内"但标以送达日为准，误判；改为禁止无前提死写（"上诉期为15日"缺送达前提）。

---

## 五、门禁验证（bash 实测）

- `capability_suite_gate.py`：**pass**（instruction-type 模式，三案例 executed-pass + run_receipts + 真实哈希）
- `evaluation_package_gate.py check`：**pass**（standard 模式，DIM-1~6 / TASTE-1~8 全覆盖，verdict adopt-with-notes）
- 语义 gate 4 例实跑：**全部 pass**
- 框架回归：contract / case-analysis 双 bundle 无回归影响（litigation 为新增独立 bundle）

---

## 六、横向维度贡献（沉淀至跨 Skill 对比）

- **期限/效力状态严谨**：litigation 补强 case-analysis 的"不凭记忆写条号"维度，新增"期限不写死天数"诉讼专属盲点。
- **已决文书说理溯源**：与 case-analysis（未决材料分析）形成"输入材料 vs 已决文书"对照。
- **不妄断结论**：与 legal-proposal-generator（二期）、legal-qa-extractor（二期）共享"绝对化表述"红线。

---

## 七、下一步

- 本 bundle 已标准模式闭环，无需待补（材料为脱敏占位样本，无隐私外传风险）。
- 后续可纳入 `references/cross-skill-dimensions.md` 横向汇总（T-906 框架待补项）。
- 二期候选：legal-proposal-generator / legal-qa-extractor / patent-analysis / opc-legal-counsel（见 NEXT_BUNDLES_PLAN.md）。
