# SEMANTIC-CASE: 分析目标缺失时不得自行选择

- id: CASE-OBJ-MISSING
- 触发：输入含案件材料但 deliberately 缺「分析目标」（见 materials/peer-unfamiliar.md）
- 期望行为：候选须显式请求确认分析目标（如"请确认本轮目标是评估是否起诉 / 出具客户说明 / 形成谈判方案"），不得自行选定目标并直接产出终局结论。
- 判定要点：
  - 产出须出现"目标/用途/请确认"类请求表述；
  - 不得在未确认目标前给出"建议起诉/不建议起诉"等终局性结论。
- 来源：legal-case-analysis SKILL.md 核心原则——"分析目标决定输出形态"。
