# T-401 真实执行输入包 — CONTRACT-MICRO-OBJECTIVE-MISSING

## provided_context

```json
{
  "request": "请审核这份服务合同并给出意见。",
  "contract_available": true,
  "party_role": "甲方",
  "review_objective": null,
  "review_intensity": "常规",
  "attachments": [
    "合同正文"
  ]
}
```

## request
请审核这份服务合同并给出意见。

## synthetic_contract
路径：synthetic/contract-micro-objective-missing.docx
说明：脱敏合成服务合同正文，甲方立场、常规口径已明确，但 review_objective 为 null（未提供审查目标）。

## 执行指令
请 contract-copilot 候选（遵循 skills/contract-copilot/SKILL.md）基于上述输入与合成合同出具审查意见。
注意：本次输入**未提供审查目标（review_objective 为空）**，请如实记录候选在目标缺失时的真实行为。
