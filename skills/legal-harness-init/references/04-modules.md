# 04 - 8 模块全览

## 一句话结论

**不预设 5 类律师配 5 套模板**——法律工作的多样性远超模板能覆盖。本 skill 用 8 个模块作为骨架，agent 按模块顺序引导你回答，最后拼装成 AGENTS.md。

## 模块列表

| # | 模块 | 用户级/项目级 | 答什么 | 详细讲解 |
|---|---|---|---|---|
| M1 | **角色身份** | 用户级 | 你的角色、业务方向、执业地域 | [references/07-module-role.md](07-module-role.md) |
| M2 | **工作流与产出** | 用户级 | 你常做的几类工作、产出文档 | [references/08-module-workflow.md](08-module-workflow.md) |
| M3 | **协作偏好** | 用户级 | 详尽 vs 简洁、批注 vs 修订、中英文 | [references/09-module-collab-style.md](09-module-collab-style.md) |
| M4 | **工具链与禁区** | 用户级 | 允许/禁止的工具、红线 | [references/10-module-toolchain-redlines.md](10-module-toolchain-redlines.md) |
| **M5** | **回溯契约** ⭐ | 用户级 + 项目级细化 | 哪些动作必须留痕、写到哪里 | [references/06-audit-trail-contract.md](06-audit-trail-contract.md) + [references/11-module-audit-trail.md](11-module-audit-trail.md) |
| M6 | **项目上下文** | 项目级 | 项目类型、编号、委托人、阶段 | [references/12-module-project-context.md](12-module-project-context.md) |
| M7 | **案件/项目关键事实** | 项目级 | 按所选项目类型动态问 | [references/13-module-case-facts.md](13-module-case-facts.md) |
| M8 | **文件结构约定** | 项目级 | 用什么目录模板、命名约定、gitignore | [references/14-module-file-structure.md](14-module-file-structure.md) |

## 为什么不预设

预设方案的问题：

- **覆盖盲区**：律师/法务/学者/培训师/法律科技 PM……预设不能穷举
- **思维惰性**：让人倾向"按模板填"，而不是"想清楚自己的独特需求"
- **维护成本**：5 预设 × 2 层 = 10 份范本，新增一类工作要改 10 个文件
- **教学反向**：与其教"诉讼律师就该这样配"，不如教"AGENTS.md 应该包含哪些维度"——后者才是真正可迁移的能力

**模块化方案的哲学**：教用户"想清楚自己的维度"，让他们和 agent 一起拼装出真正贴合自己的配置。

## 用户级流程（M1-M5）

```
M1 角色身份：你的角色？主要业务方向？执业地域？
M2 工作流与产出：你最常做的几类工作？产出什么文档？
M3 协作偏好：详尽还是简洁？批注还是修订？中英文？
M4 工具链与禁区：允许/禁止的工具？必须人工复核的动作？红线？
M5 回溯契约：是否开启（默认开）→ 勾选通用触发场景
→ 直接生成并写入（按检测到的平台写所有位置的 AGENTS.md）
```

预计 **5-10 个问答**，由 M1-M5 拼接出用户级 AGENTS.md。

## 项目级流程（M6-M8 + M5 细化）

```
M6 项目上下文：什么类型（诉讼/非诉/知产/法务/研究）？编号？委托人？当前阶段？
M7 案件/项目关键事实：按所选项目类型动态问
M8 文件结构约定：用什么目录模板？命名约定？哪些文件不进版本？
M5 项目级细化：本项目有没有特殊的回溯要求？
→ 与 project-init 协作 → 写入并展示 diff
```

预计 **8-15 个问答**，由 M6-M8 + M5 细化拼接出项目级 AGENTS.md。

## 模块拼装规则

按模块顺序收集答案 → 每个模块取"用户回答 + 最贴近的片段库片段" → 按固定模板拼装：

```
# {M1 角色摘要}

## 工作流与产出
{M2 内容}

## 协作偏好
{M3 内容}

## 工具链与禁区
{M4 内容}

## 回溯契约
{M5 内容}

---

# 项目：{M6 项目类型 + 编号}

## 上下文
{M6 内容}

## 关键事实
{M7 内容}

## 文件结构
{M8 内容}

## 项目级回溯补充
{M5 项目级细化内容}
```

详见 [references/05-write-an-agents-md.md](05-write-an-agents-md.md)。

## 5 套参考范例

放在 `references/17-examples/`，作为"完整长什么样"的展示：

- `full-example-litigation.md` — 诉讼律师
- `full-example-transactional.md` — 非诉合同律师
- `full-example-ip.md` — 知产律师
- `full-example-in-house.md` — 企业法务
- `full-example-research.md` — 法律研究

**不直接套用**，仅在用户某模块卡壳时作参考。

## 接下来读什么

- 写作原则（顺序、详略、风格）→ [references/05-write-an-agents-md.md](05-write-an-agents-md.md)
- ⭐ 法律人专属回溯契约 → [references/06-audit-trail-contract.md](06-audit-trail-contract.md)
- M1-M8 任一模块 → 详见上表"详细讲解"列