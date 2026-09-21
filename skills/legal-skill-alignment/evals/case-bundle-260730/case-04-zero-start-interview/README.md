# Case 04: 零起点访谈案例（T-004 / T-011）

> **状态**：[骨架 - 待实测]
>
> **目的**：验证无素材路径（苏格拉底式访谈）的端到端可用性。用户只说"我想做一个 XX skill"，没有任何素材。
>
> **访谈脚本**：遵循 [`references/interview-guide.md`](../../../references/interview-guide.md) 的"零起点开题脚本"段。

---

## case-04a：劳动仲裁答辩经验

### 场景设定

**用户角色**：执业律师，劳动法方向
**用户原话**：
```text
我是做劳动法的律师，我想把仲裁答辩的经验做成一个 skill，但我手上没什么整理好的材料，
就是脑子里有很多案子积累下来的经验。不知道怎么开始。
```

### 预期访谈流程（按 interview-guide 零起点脚本）

| 问 | 引导话术 | 预期用户回答（模拟） | 产物 |
|----|---------|---------------------|------|
| 开场 | "你是律师、法务还是其他角色？想做哪个方向？" | "我是律师，做劳动法的，想做仲裁答辩" | operator 初判 = lawyer |
| 第 1 问 | "你做仲裁答辩，一开始手上拿到的是什么？" | "仲裁申请书、证据材料、客户的劳动合同" | 输入：仲裁申请书 + 证据 + 劳动合同 |
| 第 2 问 | "做完交出去的是什么？" | "一份答辩状，还有庭审提纲" | 输出：答辩状 + 庭审提纲 |
| 第 3 问 | "从拿到东西到交出去，脑子里走哪几步？" | "先看仲裁请求，再找抗辩点，然后组织事实理由，最后补法条" | workflow 主流程 |
| 4a | "这个 skill 谁来用？" | "我自己用，或者带助理一起用" | operator = lawyer / paralegal |
| 4b | "是帮谁说话？" | "帮被告，就是用人单位" | represented_party = employer（被告方） |
| 4c | "最后交出去给谁看？" | "给仲裁员看" | output_audience = arbitrator |
| 第 5 问 | "你靠什么法律依据？" | "劳动法、劳动合同法、劳动争议调解仲裁法" | 法源（effective_date 待确认→标 unverified） |

### 预期 Brief 关键字段（模拟产出）

- **skill_family**：`labor-arbitration-defense`（待用户确认）
- **operator**：`lawyer`（或 `employer-counsel`）
- **represented_party**：`employer`（用人单位/被告方）
- **output_audience**：`arbitrator`（仲裁员）
- **doc_type**：`answer`（答辩状）
- **stage**：`arbitration`（劳动仲裁中）

### 预期待确认清单（模拟）

**blocker**：
- （预期为空，访谈应补齐所有关键字段）

**warning**：
- 法源 effective_date 未确认 → 标 unverified
- 单样本/无样本，决策分支覆盖不足
- 庭审提纲格式未明确

### 预期状态判定

- `structurally_complete`: true（五问齐全）
- `handoff_ready`: true（blocker = 0）

---

## case-04b：合同用印审批流程（可选）

### 场景设定

**用户角色**：公司法务
**用户原话**：
```text
我是公司里的法务，每次合同用印都要我审一遍，这个流程我想做成 skill，
让业务部门自己先跑一遍筛查。但我没写过 SOP，就是平时怎么审的就怎么做。
```

### 预期访谈关键点

- **第 3 问陷阱**：用户说"就平时怎么审的"→ 追问"最近一次具体怎么审的，从头说到尾"
- **第 4 问灰度**：operator 可能是"业务部门"（自查）+ "法务"（终审），须明确主操作者
- **doc_type**：可能是 `checklist`（检查清单）而非传统文书——非文书型任务

### 预期 Brief 关键字段（模拟）

- **skill_family**：`contract-seal-approval-precheck`（待确认）
- **operator**：`business-dept`（业务部门自查）+ `legal-counsel`（终审）
- **represented_party**：`company`（公司）
- **output_audience**：`business-dept`（业务部门）+ `legal-counsel`
- **doc_type**：`checklist`（非文书型）
- **stage**：`in_contract`（履约中/签约中）

---

## 实测验收标准（T-004）

- [ ] 找一个真实的"零起点"用户（律师/法务），跑完完整访谈
- [ ] 产出一份 `structurally_complete = true` 的 v1 Brief
- [ ] 第 4 问三角色无混淆（尤其 represented_party vs output_audience）
- [ ] 第 5 问法源至少标出 unverified（不允许完全空白）
- [ ] Brief 可作为下游 skill-creator 的输入（即便 handoff_ready = false 也可交接）

## 待回填的实测记录

```text
访谈日期：—
访谈对象：—（角色：—）
访谈轮次：—
产出的 Brief 路径：—
访谈耗时：—
遇到的问题：—
```
