# ⭐ 回溯契约通用片段

> 这是回溯契约（M5 模块）的**通用片段**，可被各预设范本 include。完整原理讲解见 [references/06-audit-trail-contract.md](../references/06-audit-trail-contract.md)。

## 通用片段（直接粘贴到 AGENTS.md 的 M5 段）

```markdown
## 回溯契约（Audit Trail Contract）

我是法律工作者，AI 在协助我工作时，必须把以下"关键动作"按以下规则留痕：

### 必须回溯的动作

（按当前项目类型自动填入——见 references/06-audit-trail-contract.md §"按项目类型的回溯触发场景"）

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

## 按项目类型的触发场景清单

> 复制以下对应清单替换上方 "必须回溯的动作" 段：

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

## 三种文件的字段模板

### DECISIONS.md

```markdown
# DEC-{编号}：{决策标题}

- 日期：YYYY-MM-DD
- 背景：...
- 选项：A. ...；B. ...；C. ...
- 决定：X. ...
- 影响：...
- 复核：{姓名}
```

### CHANGELOG.md

```markdown
# CHANGELOG

## YYYY-MM-DD

- {变更描述}
  - 文件：{路径}
  - 来源：{来源}
  - 影响范围：{范围}
```

### TASKS.md

```markdown
# TASKS

## 进行中

- [ ] {任务描述}
  - 案号/申请号：{编号}
  - 截止：YYYY-MM-DD
  - 负责人：{姓名}
```

## 注意事项

- 回溯契约默认开启（法律人强烈建议）
- 写入前 AI 必须检查目标文件是否存在
- 不删除已有记录，只追加或标记作废
- 不替用户下"实质性结论"——但要把达成结论的过程完整留痕