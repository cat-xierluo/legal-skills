# Benchmark 样本说明

本目录不存放真实客户材料，只存放脱敏样本设计说明，用于回归测试 `legal-qa-extractor` 的输出稳定性。

## 样本列表

- `01-single-issue.md`：单问题咨询
- `02-multi-issue-switching.md`：多问题跳转
- `03-same-issue-repeated.md`：同题多次重提
- `04-follow-up-questions.md`：多轮追问
- `05-proactive-risk-reminder.md`：律师主动风险提醒
- `06-admin-heavy.md`：行政沟通占比高
- `07-incomplete-answer.md`：回答不完整
- `08-batch-mixed-directory.md`：目录批处理混合场景

## 使用方式

- 每次调整 `SKILL.md`、输出模板或规则文档后，至少按上述 8 类场景做一次纸面回归。
- 若有真实脱敏咨询记录，可将其映射到最接近的样本类型，复核输出是否满足 `references/benchmark-rubric.md`。
