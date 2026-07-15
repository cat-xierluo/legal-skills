---
name: legal-case-analysis
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.3.2"
license: CC-BY-NC
description: 本技能应在用户需要基于案件材料、咨询材料、合同资料、证据材料或检索结果进行法律分析、案件研判、风险评估、诉讼策略、刑事案件研判与审查起诉分析、非诉风险判断、客户说明或法律分析报告时使用。它是法律任务的前置分析引擎，不要求每次都生成正式报告。不要用于：单纯 OCR、单纯法条案例检索、单纯 Word 排版转换、仅需包装服务方案且无需新增法律分析的文档生成。
---

# legal-case-analysis

通用法律分析 Skill。用于把零散案件材料整理成可验证、可检索、可论证、可复用的法律分析结果。

本技能首先是法律分析引擎，其次才按需要生成报告、咨询答复、客户说明或检索任务清单。法律分析可以作为其他 Skill 的前置步骤使用。

本技能不绑定具体案由。具体领域规则通过案件材料、法律检索结果和用户目标动态补足。

## 核心原则

1. 先整理事实，再适用法律。
2. 先区分证据与陈述，再形成判断。
3. 先用 `yuandian-law-search` 完成基础法律检索，再基于检索结果进行法律分析。
4. 先提出检索问题，再引用法律依据。
5. 诉讼场景优先使用要件式分析：请求权基础、构成要件、事实、证据、证明责任和抗辩逐项对应。
6. 每个重要结论都应对应事实来源、证据来源或检索依据。
7. 材料未提及的信息，标注“未提及”或“待补充”，不得自行补全。
8. 对争议材料同时评价真实性、关联性、合法性和证明目的。
9. 对涉及时效、期间、新旧法、司法解释变化的问题，必须单独校验。

## 输入

可接受以下一种或多种输入：

- 案件概述、咨询记录、委托人陈述。
- 合同、函件、付款凭证、登记资料、裁判文书、执行材料。
- 证据目录、聊天记录、录音转写、会议纪要。
- 法条检索结果、案例检索结果、法律研究报告。
- 用户指定的分析目标，例如“评估是否起诉”“生成法律分析报告”“形成客户说明”。

如果材料是 PDF、图片或扫描件，先使用 MinerU OCR、PaddleOCR 或其他文档转换工具转为 Markdown 后再分析。

## 输出

默认输出 Markdown。是否生成正式报告取决于用户目标；很多场景只需要分析底稿、咨询答复或供其他 Skill 使用的分析结论。

根据使用场景选择输出：

- 分析底稿：面向后续写作、方案生成、诉讼准备或内部讨论，突出事实、要件、证据、检索和风险。
- 简版咨询答复：面向事实较少、目标单一的日常法律咨询，突出结论、主要理由、风险和下一步。
- 内部分析报告：面向律师团队，重事实、证据、法理、风险和策略。
- 客户说明版：面向非法律专业客户，表达更通俗，突出结论和行动建议。
- 检索任务清单：面向 `yuandian-law-search` 或 `zhihe-legal-research`。

## 工作方法

分析过程和工作方法放在 `references/` 中，按任务需要读取：

- `references/iteration-context.md`：长期迭代上下文，包括定位、边界、资源分层和后续演进方向。
- `references/analysis-engine-boundary.md`：法律分析引擎定位，以及与 `legal-proposal-generator` 等 Skill 的协作边界。
- `references/workflow.md`：完整工作流，包括目标识别、案件阶段、材料处理、检索、论证和交付检查。
- `references/report-depth-control.md`：按案件复杂度选择简版咨询、标准分析或复杂案件分阶段报告。
- `references/element-litigation-nine-step.md`：要件式诉讼分析九步法，用于**民事/民商事**诉讼和争议解决场景的分析支架。
- `references/criminal-case-analysis.md`：刑事案件分析法（四要件为主干，审查起诉骨架 + 辩护对抗检验），用于刑事案件研判、审查起诉/审查逮捕底稿、定性与量刑分析；违法/责任阻却事由用三阶层（该当性→违法性→有责性）在分析内逐层审查。
- `references/fact-evidence-extraction.md`：事实与证据抽取规则。
- `references/civil-commercial-analysis-workflow.md`：复杂民商事案件法律分析步骤。
- `references/issue-spotting.md`：法律问题识别和问题树拆解规则。
- `references/legal-research-bridge.md`：法律检索衔接规则。
- `references/argument-risk-assessment.md`：论证和风险评估规则。

## 输出模板

最终交付模板放在 `templates/` 中：

- `templates/simple-consultation-answer.md`：简版咨询答复模板。
- `templates/legal-analysis-report.md`：通用法律分析报告模板。
- `templates/legal-research-query-list.md`：法律检索任务清单模板。
- `templates/client-summary.md`：客户说明模板。
