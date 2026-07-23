# Reporting Standards

本文件定义问题分级和审查报告结构。

## 问题分级

| 级别 | 说明 | 处理 |
|------|------|------|
| 严重 | 阻塞加载、发布、使用安全或质量验收 | 必须修复 |
| 警告 | 影响维护、复用、审查可信度或可评估性 | 建议修复 |
| 信息 | 风格、清晰度或后续改进建议 | 可选处理 |

Hard Fail 一律按严重问题处理。

## 报告原则

- 问题先行，摘要后置。
- 仓库审查先说明发现了哪些最小 Skill 单元，再报告问题。
- 每个问题都要写明位置、模块、影响和建议。
- 最终质量意见报告必须写明问题、修正方式和复查标准。
- 不把“项目发布规则”误写成“所有 Skill 通用规则”。
- 不把 monorepo 根目录缺少 `SKILL.md` 误写成子 Skill 的严重问题。
- 安全问题必须写明风险类别、安全级别、证据位置和复查标准。
- 对无法确认的能力标注“未提及/待补充”。
- 使用本地配置审查时，不暴露配置值，除非用户明确要求。
- 正式质量意见报告生成后，按 `archive-standards.md` 判断是否归档。
- 正式验收必须区分 `HARNESS_REVIEW_VERIFIED`、`INSTRUCTION_STABILITY_EVIDENCE_READY`、`INSTRUCTION_STABILITY_VERIFIED`、`DOMAIN_VERIFIED` 和 `NOT_VERIFIED`；`EVIDENCE_READY` 只是待签草稿，不得用静态审查或未验签草稿冒充功能通过。
- Harness 七层采用短板判断；任一必需层触发 Hard Fail 时，总体不得通过。
- 稳定性 finding 必须写明具体 constraint id、checker modality、artifact stage、case 或 run；不得只写“模型遵循不稳定”。
- 动态证据必须写明候选信任来源和执行环境；未知第三方候选在非隔离环境中只能标记 `NOT_VERIFIED`。
- 对承载设计原理的结构性建议（拆解披露、触发边界、上下文聚焦、自由度匹配、可机判验收、渐进式披露 + 可执行流程等），finding 必须含两段教学:**为什么错(原理)**——这个问题违反了哪条 skill 写作 / 技术原理;**最优设计**——根据原理该怎么设计才对(给具体范例)。这使审查报告同时是 skill 写作教学:使用者不仅知道改什么,还学到"为什么这么设计才对"。纯事实问题(文件缺失、引用断裂、命名)可省。各模块 standards 文件含「设计理念」小节可供引用。

## 模板选择

| 场景 | 使用模板 |
|------|----------|
| 快速审查反馈 | 使用本文件内的简版报告结构 |
| 创建前 Harness 预检 | 使用本文件内的简版报告结构，并单列七层设计与反例计划 |
| 发布前验收 | 使用 `templates/skill-quality-opinion-report.md` |
| 第三方 Skill 正式评估 | 使用 `templates/skill-quality-opinion-report.md` |
| 用户要求“质量意见”“最终报告”“整改建议” | 使用 `templates/skill-quality-opinion-report.md` |

`templates/skill-quality-opinion-report.md` 是最终交付模板，适合形成可归档的质量意见。填写时保留有依据的问题，不要为了填满章节而编造风险。

## 归档要求

需要归档时，将最终报告保存为：

```text
archive/YYYYMMDD_HHMMSS_<target-slug>/quality-opinion-report.md
```

同时生成 `review-metadata.json` 和 `evidence-index.md`。归档文件只保留脱敏摘要、相对路径、提交摘要和检查结论，不复制真实敏感材料或大段外部内容。

## 报告模板

```markdown
# [skill-name] Skill 审查报告

**审查时间**: YYYY-MM-DD HH:MM
**技能路径**: /path/to/skill
**审查范围**: 发布前验收 / 改造评估 / 第三方审查 / 回归检查

## 审查单元发现

| 单元 | 类型 | 是否纳入 | 说明 |
|------|------|----------|------|
| `path/to/skill` | 已确认 Skill / Skill-like 文档 / README 索引项 | 是 / 否 | ... |

## 结论

- 总体状态: ✅ 通过 / ⚠️ 需改进 / ❌ 不通过
- 严重问题: N
- 警告问题: N
- 信息提示: N

## ❌ 严重问题

1. **[问题标题]**
   - 位置: `文件路径:行号`
   - 模块: `reference-file.md`
   - 依据: 违反的规则
   - 影响: 为什么阻塞
   - 建议: 具体修复方式
   - 设计理念: 结构性建议必填，一句话点透背后写作原理（可引用对应 standards 的「设计理念」小节）；纯事实问题可省

## ⚠️ 警告问题

1. **[问题标题]**
   - 位置: `文件路径`
   - 模块: `reference-file.md`
   - 影响: 维护 / 发布 / 可评估性风险
   - 建议: 具体优化方式
   - 设计理念: 结构性建议必填，一句话点透背后写作原理（可引用对应 standards 的「设计理念」小节）；纯事实问题可省

## ℹ️ 信息提示

- [提示信息]

## 安全评估

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 凭证与敏感配置 | ✅/⚠️/❌ | ... |
| 危险执行与文件操作 | ✅/⚠️/❌ | ... |
| 网络外联与数据外传 | ✅/⚠️/❌ | ... |
| 依赖、安装钩子与 MCP | ✅/⚠️/❌ | ... |
| 提示词安全 | ✅/⚠️/❌ | ... |

安全问题条目应补充：

- 风险类别：命令执行 / 数据外传 / 硬编码凭证 / 提示词安全 / 依赖风险等
- 安全级别：Critical / High / Medium / Low / None
- 复查标准：如何确认风险已删除、降级或有明确用户确认和范围限制

## 业务流深度

| 层级 | 状态 | 说明 |
|------|------|------|
| Trigger | ✅/⚠️/❌ | ... |
| Intake | ✅/⚠️/❌ | ... |
| Reasoning | ✅/⚠️/❌ | ... |
| Output | ✅/⚠️/❌ | ... |
| Safety | ✅/⚠️/❌ | ... |

## 可评估性

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 评估范围 | ✅/⚠️/❌ | ... |
| Hard Fail | ✅/⚠️/❌ | ... |
| benchmark / 样例 | ✅/⚠️/❌ | ... |
| 输出验收标准 | ✅/⚠️/❌ | ... |
| 静态检查与动态评估区分 | ✅/⚠️/❌ | ... |

## Harness 可靠性

| 层 | 状态 | 证据 |
|----|------|------|
| Contract | ✅/⚠️/❌ | ... |
| Producer | ✅/⚠️/❌ | ... |
| Verifier | ✅/⚠️/❌ | ... |
| Evidence Binding | ✅/⚠️/❌ | ... |
| Fault Injection | ✅/⚠️/❌ | ... |
| Closure | ✅/⚠️/❌/不适用 | ... |
| Composition | ✅/⚠️/❌/不适用 | ... |

- 审查证据：`HARNESS_REVIEW_VERIFIED` / `NOT_VERIFIED`
- 指令稳定性：`INSTRUCTION_STABILITY_VERIFIED` / `INSTRUCTION_STABILITY_EVIDENCE_READY（不得作完成结论）` / `NOT_VERIFIED`
- 业务验证：`DOMAIN_VERIFIED` / `NOT_VERIFIED` / 不适用
- 候选聚合哈希：`<sha256 或未生成>`
- 稳定性合同/evaluator Ed25519-signed 外部硬约束基线与 held-out/Harness evidence/签名运行证据/签名回执与公钥 ID：`<sha256、key id 或未生成>`
- 候选信任与执行环境：`<自有/已审查可信/第三方未知；普通工作区/隔离环境>`
- 故障注入：`<checker、参数、预期非零退出码与本次实际退出码>`
- 多轮覆盖：`<run 数、相同 input/config 哈希、唯一 nonce/签名 producer log、hidden cases、hard constraint ids、measurement 类型/阈值与 observable 比较结果>`
- 总体成熟度：L0 / L1 / L2 / L3 / L4

## 建议操作

1. ...
2. ...
```
