# 评分回执：case-01 R2

> 评分者：judge-case01-R2 agent（全新上下文，与 worker 无共享会话；只见 SKILL.md + constraints-tracker + 素材 + Brief 产物）
> 评分日期：2026-08-23

## case-01 R2 Brief 独立评分报告

依据：SKILL.md v1.0.6（判定权威）+ constraints-tracker.md C-01~C-14 + references/standard-prompt-output.md（格式权威）。行号均指 worker-outputs/case-01-R2-brief.md。

## 约束核查表（C-01~C-14）

| ID | 判定 | 证据 |
|----|------|------|
| C-01 | PASS | Brief（代码块内）首个 blockquote L47："遵循 legal-skill-brief/v1 规范" |
| C-02 | PASS | 同 L47："方法论 question-set/v1（五问）" |
| C-03 | PASS | L56 `skill_family：supplier-service-contract-review`，匹配 `^[a-z0-9]+(-[a-z0-9]+)+$` |
| C-04 | FAIL（warning 级） | stage `pre_contract`（L58）、represented_party `buyer`（L59）合规；但 output_audience `client-legal`（L60）、doc_type `contract-review`（L61）为 kebab-case，operator `lawyer + paralegal`（L59）含空格加号，均不匹配 tracker 正则 `^[a-z]+(_[a-z]+)*$`。**重要减轻情节**：源规范自相矛盾——standard-prompt-output.md 命名约定表（L40）规定文书类型用 snake_case（例 `demand_letter`），但同文件元数据示例（L57-60：`compliance-officer`/`opposing-counsel`/`internal-team`/`demand-letter`）及"模板填充示例"（L367-373：operator `buyer-counsel`、output_audience `buyer-internal-team`、doc_type `contract-review`）全部用 kebab-case。R2 的取值几乎逐字镜像了规范自己的合同审查示例，属"按示例做但违反规则条文"。按 tracker 声明的验证方法（正则）判 FAIL，但根因一半在源规范，建议评汇总时降权或记为规范缺陷回填项 |
| C-05 | PASS | 二.1（L66-79 必要/可选输入+信息来源）、二.2（L81-96）、二.3（L98-126 主流程10步+决策点+异常路径）、二.4（L128-136）、二.5（L138-153）五问均实质非空 |
| C-06 | PASS | L130-132 三子项齐全：operator（所内律师+助理，用户明示）、represented_party（电商企业采购方+推断依据）、output_audience（客户公司法务部+推断依据） |
| C-07 | PASS | L144-149 每行 effective_date 均填 `unverified`——素材无法源原文时 v1.0.6 明文要求此填法，且无一行凭名称编造施行日（L148 明写"施行日不得凭名称填写"） |
| C-08 | PASS | 四行全部 `verification_status: unverified`，无任何行升级为 verified，证据门槛不被触发；且证据四列按规范预填 `unverified`（规范 L314 明示 unverified 行此填法） |
| C-09 | PASS（warning 级） | L159-163 阈值配置 3 行 source 全非空（SOP/所内审查清单），L167-173 判断标准 5 行 source 全非空；额外加分：L161 主动标注 SOP 阈值与样本 A 实际触发（约4倍 vs 5倍线）的口径不一致并挂 W2 |
| C-10 | PASS（warning 级） | L177-182 每行 quality 非空：sample=silver（注明摘要版未经复核）、sop=gold、rules=gold、qa/revisions/tools-data/authorities=unrated（注明无此类素材） |
| C-11 | PASS | L186-189 敏感材料处理（识别企业名/金额+部分脱敏状态+脱敏责任）、L191-194 外传策略（检索否/上传否/留存）、L196-198 高风险结论复核，三部分齐 |
| C-12 | PASS（warning 级） | L208"阻塞交接缺口（blocker…）"与 L212"可带警告交接缺口（warning）"两类分组齐，每项带 `— type:` 标注 |
| C-13 | PASS | L203 `structurally_complete: true` 布尔值明确 |
| C-14 | PASS | 独立重算与自标注完全一致（见下节）；L204 还显式写出公式 `handoff_ready: false（= structurally_complete && blocker 数 = 0，未满足）` |

## 状态重算过程

1. **五问字段面**：五问均有实质答案（证据见 C-05 行），无空白问。✓
2. **法源三列与素材核验**：法源表带 jurisdiction/effective_date/verification_status 三列且全填。素材侧核验：素材 1 仅"《民法典》第 577/563 条"、素材 2 仅"《网络安全法》第 21/42 条；《个人信息保护法》第 13 条"的**名称+条号引用**（case-01.md L45、L65），无任何 source_url/source_file/条文原文。素材溯源表（Brief L182）亦如实记 authorities 数量 0。
3. **是否产出具体法律建议**：是。Brief 明确 Skill 产出"合同审查意见书"，每条含"风险描述 → 法条依据 → 修改建议"（L86），Brief 自己也承认"审查意见属具体法律建议（非定稿文书）"（L197）。对照 SKILL.md"关键法源缺失的唯一判定"所列类型，"合同定稿或**审查结论**"明文在列 → 法源原文缺失**必须**登记 blocker。值得肯定：standard-prompt-output.md 的模板示例自己写"是否涉及最终法律结论：否"（L465），与 SKILL.md 权威规则冲突，R2 正确采信了 SKILL.md（判"是"+blocker）而非规范的松弛示例。
4. **blocker 独立计数**：L208-210 blocker 段恰好 1 条 `- [ ]`（关键法源原文）。→ handoff_ready = (true && 1=0) = **false**。
5. **warning 独立计数**：L214-222 共 9 条（W1-W9），逐条点数为 9。
6. **失败条件反向核验**（是否会强制 structurally_complete=false）：五问无空白；已声明需执业律师复核（L198）；敏感信息（真实形态企业名+金额）已声明脱敏状态并提示确认（L186-189、安全预检段 L16-21）——三条均不触发。
7. **顶部标注义务**（v1.0.2 状态转换规则）：L50-51 Brief 顶部 blockquote 显式标注"handoff_ready = false（含 1 项 blocker…）含 blocker，不建议下游直接编译"。✓

| 项 | 独立重算 | Brief 自标注（L203-206） | 一致？ |
|----|---------|------------------------|-------|
| structurally_complete | true | true | ✓ |
| handoff_ready | false | false | ✓ |
| blocker 数 | 1 | 1 | ✓ |
| warning 数 | 9 | 9 | ✓ |

**C-14：一致，PASS。**

## 三项特别核查

**1. 法源降级**：素材确无法源原文（仅名称+条号）→ 降级规则触发。二.5 法律依据表首行占位存在（L142）："法源原文缺失：以下条目均 `unverified`，待用户补充权威出处（如国家法律法规数据库 URL 或所内法条库路径）后升级"，措辞与 SKILL.md 要求一致。四行 effective_date 一律 `unverified`，无一行凭名称填施行日。**结论：合规。**

**2. 空壳行**：四行分别为《民法典》577 条、《民法典》563 条、《网络安全法》21+42 条、《个人信息保护法》13 条——每行均具备 jurisdiction(CN) + 法规名称 + **条号** + 三列 + 诚实说明（"素材仅含条号引用，未附原文；不得作为确定性依据"）。按"有名称+条号的行属合法转录"口径，无一行是"仅名称、无条号、三列凑空"的空壳行。**结论：无空壳行，合规。**

**3. 防错核对**：二.4 段末存在防错核对行（L136），且 (a)(b)(c) 三项逐一确认。represented_party = 采购方电商企业，未误填任何读者类角色；法务部被正确归入 output_audience 并在 (b) 中显式说明。operator（所内律师/助理）与 output_audience（客户法务部）分立无混淆。推断性质（represented_party 反推）未静默，挂 W1。**结论：合规。**

## 总判定

- **blocker 级 FAIL：0 / 14**（C-01/02/03/05/06/07/08/11/13/14 全过）
- **warning 级 FAIL：1**（C-04 命名格式，且半数根因是源规范示例与规则条文自相矛盾，建议同时登记为规范回填项）
- **一句话结论**：R2 Brief 实质达标——状态自标注（true/false/1/9）与独立重算完全吻合，法源降级、空壳行、防错核对三项强制规则全部合规，blocker（关键法源原文缺失）的定级正确援引了 SKILL.md 对"合同审查结论"的权威判定；唯一瑕疵是 warning 级的 metadata 命名格式，不阻塞交接判定。
