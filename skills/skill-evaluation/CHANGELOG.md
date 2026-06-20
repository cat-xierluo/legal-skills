# CHANGELOG

## [v0.1.0] - 2026-06-20

### 新增
- 首版法律 Skill 场景化评测 skill（来源：法律AI书 ch07 第六节 #91 / #119，游初《二轮对焦》）。
- **核心定位**：不构建通用六维度基准，按法律场景（合同 / 诉讼 / 合规）分维度评测**产出物质量**；与 `skill-lint` 划界（规整性层 vs 输出合理性层）。
- **三场景维度清单**：`contract` / `litigation` / `compliance`，各含 taste 项（经验律师一眼觉得不对的东西显式化）。
- 评测目的：定位"要回 SKILL.md 补哪句话"，而非给 Skill 打总分。

### ⚠️ 开放难题（作者 2026-06-20 明确）
验证法律 Skill 产出物质量、不同文书不同标准、taste 结构化是**开放难题，非一次创建可定**。v0.1.0 为**起点**，待 **#123 / DR-5**（skill eval 前沿调研，在法律AI书仓库 `research/deep-research-prompts/DR-5-skill-eval.md`）回传后迭代维度集。详见 TASKS.md。
