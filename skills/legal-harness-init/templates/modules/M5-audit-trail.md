# M5 回溯契约片段库 ⭐

agent 在用户卡壳时主动调出本片段库参考。本文件是 M5 模块的**核心片段库**。

## 使用场景

用户卡在以下问题时参考：

- "哪些动作必须留痕？"
- "写到什么文件？"
- "什么格式？"

## 按项目类型的回溯触发场景

### 诉讼

```markdown
### 必须回溯的动作

- 案号/管辖/对方当事人变更 → docs/DECISIONS.md
- 新增证据材料 → CHANGELOG.md
- 策略调整 → docs/DECISIONS.md
- 对外发送文书 → 双重人工确认 + docs/DECISIONS.md
- 开庭日期/举证期限/上诉期变更 → TASKS.md
```

### 非诉合同

```markdown
### 必须回溯的动作

- 合同版本切换 → CHANGELOG.md
- 关键条款决策（管辖/责任/担保/价款）→ docs/DECISIONS.md
- 里程碑事件（签约/交割）→ docs/DECISIONS.md
- 客户对条款的实质修改 → docs/DECISIONS.md
- 待办事项（签约前/交割前）→ TASKS.md
```

### 知产

```markdown
### 必须回溯的动作

- 申请号/阶段变更 → CHANGELOG.md
- 驳回/复审/无效决策 → docs/DECISIONS.md
- 续展/年费节点 → TASKS.md
- 客户对申请文件的实质修改 → docs/DECISIONS.md（含改前/改后）
- 答复策略调整 → docs/DECISIONS.md
```

### 企业法务

```markdown
### 必须回溯的动作

- 合规审查结论 → docs/DECISIONS.md
- 模板修订 → CHANGELOG.md
- 风险事件 → docs/DECISIONS.md（含风险等级、应对方案）
- 待办事项 → TASKS.md
- 内部规则修订 → CHANGELOG.md
```

### 法律研究/学者

```markdown
### 必须回溯的动作

- 研究思路与取舍 → docs/DECISIONS.md
- 检索结果/案例汇编节点 → CHANGELOG.md
- 文献引用增减 → CHANGELOG.md
- 结论性表述调整 → docs/DECISIONS.md
- 待办（检索/撰写/评审）→ TASKS.md
```

## 三个留痕目的地（基础片段）

```markdown
### 回溯位置

- 重要决策 → docs/DECISIONS.md
- 用户可见变更 → CHANGELOG.md
- 进行中/待办 → TASKS.md（或 status/TASKS.md，按项目约定）
```

## 写入原则（通用）

```markdown
### 回溯原则

- 每次写入必须含日期（YYYY-MM-DD）、上下文、动作、影响
- 不替我下"实质性结论"，但要把达成结论的过程完整留痕
- 不删除已有记录，只追加或标记作废
- 写入前先检查目标文件是否存在、是否已记录同类内容，避免重复
```

## 三个文件的字段模板

### DECISIONS.md 字段模板

```markdown
# DEC-{编号}：{决策标题}

- 日期：YYYY-MM-DD
- 背景：...
- 选项：A. ...；B. ...；C. ...
- 决定：X. ...
- 影响：...
- 复核：{姓名}
```

### CHANGELOG.md 字段模板

```markdown
# CHANGELOG

## YYYY-MM-DD

- {变更描述}
  - 文件：{路径}
  - 来源：{来源}
  - 影响范围：{范围}

## YYYY-MM-DD

- {变更描述}
  - ...
```

### TASKS.md 字段模板

```markdown
# TASKS

## 进行中

- [ ] {任务描述}
  - 案号/申请号：{编号}
  - 截止：YYYY-MM-DD
  - 负责人：{姓名}

## 已完成

- [x] {任务描述}（YYYY-MM-DD 完成）
```

## 完整用户级 M5 段（推荐）

```markdown
## 回溯契约（Audit Trail Contract）

我是法律工作者，AI 在协助我工作时，必须把以下"关键动作"按以下规则留痕：

### 必须回溯的动作

（按当前项目类型自动填入，见本文件 §"按项目类型的回溯触发场景"）

### 回溯位置

- 重要决策 → docs/DECISIONS.md
- 用户可见变更 → CHANGELOG.md
- 进行中/待办 → TASKS.md（或 status/TASKS.md，按项目约定）

### 回溯原则

- 每次写入必须含日期（YYYY-MM-DD）、上下文、动作、影响
- 不替我下"实质性结论"，但要把达成结论的过程完整留痕
- 不删除已有记录，只追加或标记作废
- 写入前先检查目标文件是否存在、是否已记录同类内容，避免重复
```

## 项目级 M5 细化片段

### 诉讼项目级细化

```markdown
## 项目级回溯补充

### 关键时点（针对本案）

- 开庭日期：YYYY-MM-DD → TASKS.md
- 举证期限：YYYY-MM-DD → TASKS.md
- 上诉期：YYYY-MM-DD → TASKS.md

### 项目特定触发

- 对方当事人变更 → DECISIONS.md
- 证据材料目录结构变更 → CHANGELOG.md
- 策略调整 → DECISIONS.md
```

### 知产项目级细化

```markdown
## 项目级回溯补充

- 商标局发文 → CHANGELOG.md（含发文日期、文书类型）
- 驳回/复审/无效决策 → DECISIONS.md
- 续展节点前 60 天 → TASKS.md
- 客户对申请文件的实质修改 → DECISIONS.md（含改前/改后）
- 答复策略调整 → DECISIONS.md（含调整理由）
```

### 非诉项目级细化

```markdown
## 项目级回溯补充

- DD 重大发现 → DECISIONS.md
- 合同版本切换（v1→v2→v3）→ CHANGELOG.md（含变更条款、变更理由）
- 签约/交割里程碑 → DECISIONS.md
- 客户对条款的实质修改 → DECISIONS.md
```

### 企业法务项目级细化

```markdown
## 项目级回溯补充

- 合同重大修改（金额/管辖/责任）→ DECISIONS.md
- 风险事件 → DECISIONS.md（含风险等级、应对方案）
- 模板修订 → CHANGELOG.md
- 内部审批流程变更 → DECISIONS.md
```

### 法律研究项目级细化

```markdown
## 项目级回溯补充

- 研究思路调整（章节增删、立场变化）→ DECISIONS.md
- 文献/案例新增 → CHANGELOG.md（含引用信息）
- 引用格式变更 → DECISIONS.md
- 交付物版本切换 → CHANGELOG.md
- 评审/审稿意见 → DECISIONS.md（含意见摘要 + 回应）
```

## 关闭回溯契约的情况（不推荐）

```markdown
## 回溯契约

⚠️ 回溯契约已关闭（仅适用于个人练习 / 学习项目 / 完全私密使用）

- 法律工作强烈不建议关闭
```

## 后续动作

agent 拿到用户回答后：

1. 询问项目类型（决定触发场景清单）
2. 取最贴近的片段
3. 拼装到 AGENTS.md 的 M5 段

**用户级 M5** = 触发场景清单 + 回溯位置 + 回溯原则
**项目级 M5 细化** = 在用户级基础上叠加项目特定触发