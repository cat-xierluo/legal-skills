# CHANGELOG

## [v0.1.0] - 2026-06-20

### 新增
- 首版多模型去 AI 化横评 skill（来源：法律AI书 TASKS #114）。
- **流程**：N 个候选模型并行生成 → 裁判模型（跨家族、不在候选内）按 BOOK-TONE-REVIEW 七类门禁 + de-ai-polish 打五维加权分 → 排名选优 → 最优模型跑定稿。
- **评价标准对接既有规范**（口吻干净度 / 句式自然度 / 词汇准确度 / 信息密度 / 法律边界感），不另造检测逻辑。
- 阈值规则：≥4.5 直接定稿；前两名分差 ≤0.5 做 tiebreak。
- references：`judge-prompt`（裁判模板）/ `scoring-rubric` / `model-selection-log`。
