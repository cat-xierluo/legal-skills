# T-401 真实执行输入包 — CONTRACT-MICRO-ATTACHMENT-MISSING

## provided_context

```json
{
  "request": "请审核这份技术服务合同并给出意见。",
  "contract_available": true,
  "party_role": "甲方",
  "review_objective": "签约前把关",
  "review_intensity": "常规",
  "attachments": [
    "合同正文"
  ]
}
```

## request
请审核这份技术服务合同并给出意见。

## synthetic_contract
路径：synthetic/contract-micro-attachment-missing.docx
说明：脱敏合成技术服务合同正文。正文第二至六条反复引用《附件一：服务清单与交付物说明》《附件二：费用与里程碑表》《附件三：知识产权与数据处理附录》《附件四：验收与运维服务规范》，但本次审查**未随附任何附件文本**，且正文与附件冲突时以附件为准。

## 执行指令
请 contract-copilot 候选（遵循 skills/contract-copilot/SKILL.md）基于上述输入与合成合同出具审查意见。
注意：本次输入**未提供合同正文所引用的任何附件**，请如实记录候选在附件缺失时的真实行为——尤其是它是否明确附件缺失对服务范围、验收标准与价款判断的限制，并将附件到位列为签署前先决条件。
