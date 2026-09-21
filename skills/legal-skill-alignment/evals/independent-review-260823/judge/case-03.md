# 评分回执：case-03

> 评分者：judge-case03 agent（全新上下文，与 worker 无共享会话；只见 SKILL.md + constraints-tracker + 素材 + Brief 产物）
> 评分日期：2026-08-23

被评产物：`worker-outputs/case-03-brief.md`
判定依据：SKILL.md（同目录）+ constraints-tracker.md + 素材 `worker-inputs/case-03.md`。以下行号均指 Brief 文件行号。

## 约束核查表（C-01~C-14 逐条）

| ID | 判定 | 证据 |
|----|------|------|
| C-01 | PASS | L37 Brief 顶部 blockquote：「遵循 legal-skill-brief/v1 规范（question-set/v1 五问）」，位于 Brief 本体（L35 `# Skill 编译请求`）首行引用块 |
| C-02 | PASS | 同 L37 含 `question-set/v1`；L52 段标题「二、五问要素（question-set/v1）」再次标注 |
| C-03 | PASS | L43 `skill_family：app-data-compliance-scan`，匹配 `^[a-z0-9]+(-[a-z0-9]+)+$`，无下划线 |
| C-04 | PASS（附规范矛盾备注） | L45 `stage: post_launch` 为标准 snake_case，命中正则。`doc_type: compliance-report`（L49）为 kebab-case，但该值与 SKILL.md 引用的 standard-prompt-output.md L60 模板示例**逐字一致**（规范自身示例违反自家 snake_case 规则）；operator 等三角色字段为「中文描述+推断标注」形态，同样与规范完整模板 `{角色}` 自由填写一致。属规范内部矛盾而非产出缺陷，不记 FAIL，建议修规范 |
| C-05 | PASS | 二.1（L54-69 必要/可选输入+信息来源含待确认标注）、二.2（L71-87 产出/格式/质量标准/形态 mixed）、二.3（L89-108 主流程 8 步+决策点+异常路径，L94「待补」）、二.4（L110-122）、二.5（L124-141）五问全部非空 |
| C-06 | PASS | L112 operator（律所合规团队律师/合规专员，推断+待确认）、L114 represented_party（被评估 App 运营公司）、L116 output_audience（客户数据合规负责人），三字段均非空 |
| C-07 | PASS | L132-135 四行法源 effective_date 均为 `unverified`，非空且**零编造施行日**（未凭名称填 2021-11-01 之类），完全符合 v1.0.6 降级规则 |
| C-08 | PASS | 全表无任何行标 `verified`（L132-135 verification_status 均 unverified），无「仅名称反推却升 verified」情形，约束平凡满足 |
| C-09 | PASS | 阈值配置 2 行（L149-150）source 分别为「SOP 输出规范 + sample-001 反推（待团队确认）」「SOP 提及输出项；标准 unverified」；判断标准 6 行（L156-161）source 均「sample-001 反推」，无空 source |
| C-10 | PASS | 素材溯源表（L167-170）三项实际素材 quality 均 `silver`（含理由）；authorities 行数量 0、quality 写「—（缺失，构成 blocker）」——0 份素材无可评对象且已注明，规范示例对该情形写「unrated（无素材）」，属措辞级瑕疵非缺口 |
| C-11 | PASS | 五段三部分齐：敏感材料处理（L177-179）、外传策略（L181-184：否/否/本地一次性）、高风险结论复核（L186-188：涉具体法律建议+必须律师复核） |
| C-12 | PASS | L199「### 阻塞交接缺口（blocker）」与 L203「### 可带警告交接缺口（warning）」两类分组齐，且每条尾缀 `— type: blocker/warning` |
| C-13 | PASS | L194「structurally_complete: true（五问齐全，缺口已如实标注）」，布尔值明确；顶部 L39 亦同步标注 |
| C-14 | PASS | 独立重算 handoff_ready = true && (blocker=0) = **false**，与 L196 自标一致；blocker 数、warning 数重算比对见下节，四项全部吻合 |

## 状态重算过程

**第 1 步：五问字段面（structurally_complete 前提）**
- 二.1 有答案（含信息来源待确认标注）；二.2 有答案；二.3 有答案（含两处「待补」：L94 权限判断基准、L108 异常场景为补全建议）；二.4 三子项+触发场景+语气基调齐；二.5 法源表+范本来源+风险清单+风格偏好齐。五问无空白且缺口均显式标注 → 满足。

**第 2 步：法源三列与素材原文判定**
- 法源表 L132-135 四行均带 jurisdiction（CN）/ effective_date（unverified）/ verification_status（unverified）三列 → 满足。
- 素材侧：素材 1 L69 仅「《个人信息保护法》第 6/7/13…条；《数据安全法》第 21/27/30 条；《网络安全法》第 41/42/43 条；《App 违法违规收集使用个人信息行为认定方法》」——**只有名称与条号，无任何 URL、无原文文本、无本地文件路径**。素材 2 亦仅引用《个保法》第 17 条条号。素材未提供任何 source_url/source_file 级别的法源原文，Brief 的认定（L29「法源原文（authorities）｜缺失｜0 份」）属实。

**第 3 步：是否产出具体法律建议**
- 是。二.2（L77、L82）明确输出含「整改建议（含优先级与期限）」，二.3 第 8 步输出「整改建议+整改期限」，判断标准表含「→ 不合规（高）」级合规性判定。整改建议属 SKILL.md「关键法源缺失的唯一判定」明列的类型（「需据法源作出的合规整改建议」）→ **法源原文缺失必须登记 blocker，法域已知（CN）不能降级**。

**第 4 步：blocker 独立清点**
- 逐条核对 handoff_ready=false 三个触发条件：(a) operator 有推断依据（用户自述「我在律所的合规团队」）且仅 warning 级待补 → 不算 blocker，处理正确；(b) 五问无空白 → 不触发；(c) 具体法律建议+法源原文缺失 → 触发 1 项。待确认清单 L201 恰好仅此 1 项 blocker（「关键法源原文缺失」）。**独立清点 blocker = 1 → handoff_ready = false**。

**第 5 步：warning 独立清点**
- L205-214 逐条数：operator 推断 / represented_party 推断 / output_audience 推断 / 风险等级规则 / 整改期限标准 / 事实采集方式 / 单样本节选 / 法源时效 / 适用范围边界 / 法源覆盖度 = **10 条**。

**与自标注比对表**

| 字段 | Brief 自标 | 独立重算 | 一致？ |
|------|-----------|---------|--------|
| structurally_complete | true（L194） | true（五条件全满足） | 一致 |
| handoff_ready | false（L196） | false（blocker=1） | 一致 |
| blocker 数 | 1（L197） | 1 | 一致 |
| warning 数 | 10（L198） | 10 | 一致 |

附加核对：状态转换规则要求「含 blocker 不建议下游直接编译」须在顶部显式标注——L39 顶部 blockquote「**交接状态：structurally_complete = true，handoff_ready = false（含 1 项 blocker），不建议下游直接编译**」满足；失败条件三条均未触发（律师复核已声明于 L104、L188）。**C-14 判定：PASS。**

## 三项特别核查

**1. 法源降级**
- 证据：L128 二.5 法律依据表首行占位：「**法源原文缺失：以下条目均 unverified，待用户补充权威出处后升级。** 素材仅提供法规名称与条号引用，无法源原文、施行日期或链接，不得据此编写确定性法律结论」——与 v1.0.6 强制话术实质逐字对应。effective_date 列 L132-135 四行一律 `unverified`，无一行凭名称填写具体日期（含最容易编造的《网安法》施行/修订日，该行 L134 还额外标注「须确认所引为最新施行版本」）。
- 结论：**合规**。

**2. 空壳行**
- 三部法律行（L132-134）：名称+具体条号（个保法 12 条、数安法 3 条、网安法 3 条）+CN+三列 → 属「可定位的具体法源」，是正式法源行，非空壳。
- 《App 违法违规收集使用个人信息行为认定方法》行（L135）：仅文件全称、无条号。按基础规则属应仅在占位行转录的线索；**但** SKILL.md 例外条款明文「若素材已点名法域且名称足以定位法源范围（如 case-03 明确 CN + 四部法规名称），可转录名称行」，且该行满足例外全部附加条件：三列 unverified、说明列注明「仅文件名称；待补发文字号、全文与现行有效性」、全 Brief 未据此编写任何具体法律结论（L128 明示禁止）。四部法规的名称待补缺口另在 warning L214（法源覆盖度）与 blocker 补充方式中列明。
- 结论：**合规（依 SKILL.md 为 case-03 明文设置的例外条款）**，无「三列凑空」行。
- 附注瑕疵（不计 FAIL）：Brief 三处（L21、L201、L220）写「四部法规 + 《认定方法》」，实际素材共 4 份文书（三部法律+一个认定方法），该措辞把它数成 5 份；法源表本身 4 行正确，属行文计数口误。

**3. 防错核对**
- 防错核对行：L122 位于二.4 末尾，含 (a)(b)(c) 三项逐一确认 + 交叉印证说明，符合 v1.0.4 强制格式。
- represented_party 陷阱：本案陷阱是把读者类角色「数据合规负责人」填进 represented_party。Brief 的 represented_party = 被评估 App 运营公司（L114，当事人立场），「数据合规负责人」正确落在 output_audience（L116），且防错核对行明文点破「数据合规负责人属 output_audience」——**陷阱未踩中**。
- operator 与 output_audience：operator=律所合规团队（用 Skill 的人，L112），output_audience=客户方（收报告的人，L116），分属委托两侧，未混淆，核对行 (c) 亦显式确认。
- 结论：**合规**。

## 总判定

- **blocker 级 FAIL 数：0**
- **warning 级 FAIL 数：0**
- 一句话结论：该 Brief 14 项约束全过、状态四项自标注与独立重算完全一致，三项强制特别规则（法源降级/例外条款下的名称行转录/防错核对）均正确执行且精准避开了「合规负责人误填 represented_party」陷阱，是一份可按「含 1 blocker、暂不可交接」正确流转的高质量产出；仅存三处不计 FAIL 的瑕疵（「四部法规+《认定方法》」计数口误、authorities 0 份行 quality 未用 unrated 字样、以及规范自身 doc_type 示例与 C-04 snake_case 正则矛盾——最后一项建议修规范而非改产出）。
