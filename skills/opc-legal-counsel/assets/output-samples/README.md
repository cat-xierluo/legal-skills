# 标准输出样稿

本目录用于存放 `opc-legal-counsel` 的标准输出样稿。

这些文件不是法条笔记，也不是知识库摘要，而是给技能直接复用的“输出骨架 + 示例答案”。

## 使用原则

- 先按 `SKILL.md` 的输入协议补关键事实
- 再根据问题类型选最接近的一份样稿
- 样稿只提供结构和表达方式，不要整段照抄
- 需要条款、清单或速查信息时，和其他资产组合使用

## 文件说明

| 文件 | 适用场景 | 建议组合 |
|------|----------|----------|
| `ai-launch-report.md` | AI 产品 / AI 功能上线前核查 | `risk-checklist.md` + `compliance-quick-ref.md` |
| `opc-separation-report.md` | 一人公司公私混用、股东借款、历史补救 | `risk-checklist.md` |
| `contract-review-report.md` | 合同审查、改条款、谈判优先级输出 | `contract-clauses.md` |

## 后续扩展方向

- 将样稿与 `evals/evals.json` 中的重点场景建立映射
- 为每份样稿补一版“极简输出”和“一般输出”
- 视使用频率增加“劳动用工分诊”“侵权投诉应对”“监管问询应对”等样稿
