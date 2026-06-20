# Skill Standards 审查索引

本文件只负责审查路由和总顺序，不承载全部细则。执行审查时先读本文件，再按目标 Skill 的问题类型打开对应 reference。

## 设计原则

- 结构、元数据、配置、发布、工作流、报告各自独立。
- 审查仓库时先定位最小 Skill 单元，再判断结构问题。
- 普通 Skill 基础验收不绑定项目发布要求。
- 安全评估独立于隐私去具体化；前者判断危险执行和外联风险，后者判断公开内容是否具体化。
- `LICENSE.txt`、`version`、README、Marketplace 属于发布治理，不属于目录结构硬要求。
- 审查第三方 Skill 时，先按通用规则判断；只有用户提供项目规则或发布目标时，才套用发布规则。

## 审查模块

| 模块 | 文件 | 何时读取 | 核心判断 |
|------|------|----------|----------|
| 仓库单元发现 | `repository-skill-discovery-standards.md` | 目标是仓库、GitHub URL、monorepo 或不确定路径 | 哪些目录或文档才是最小审查单元 |
| 物理结构 | `structure-standards.md` | 检查目录、文件、引用、references 命名 | Skill 是否能被正确加载和维护 |
| 元数据分层 | `frontmatter-metadata-policy.md` | 检查 frontmatter 字段归属 | 普通字段与发布字段是否混淆 |
| 触发描述 | `trigger-description-standards.md` | 检查 `name`、`description` | 触发边界是否清楚 |
| 配置与隐私 | `configuration-privacy-standards.md` | 检查 config、example、公开内容 | 是否泄露真实信息或本地配置 |
| 安全评估 | `security-assessment-standards.md` | 检查外部 Skill、脚本、MCP、网络、依赖或提示词风险 | 是否存在危险执行、敏感访问、数据外传或提示词安全问题 |
| 发布治理 | `publishing-standards.md` | 检查 LICENSE、CHANGELOG、version、索引 | 是否符合发布目标 |
| 工作流与输出 | `workflow-output-standards.md` | 检查 SKILL.md 正文、依赖、脚本、输出 | 是否可执行、可维护 |
| 业务流深度 | `business-flow-rubric.md` | 判断 Skill 是否承载真实业务流程 | Trigger / Intake / Reasoning / Output / Safety |
| 报告与分级 | `reporting-standards.md` | 生成审查报告 | 问题分级、修正建议和报告结构是否一致 |
| 归档机制 | `archive-standards.md` | 归档正式质量意见报告 | 归档路径、元数据、证据索引和隐私边界是否清楚 |

## 默认审查顺序

1. 读取 `repository-skill-discovery-standards.md`，确认输入目标是单个 Skill、monorepo、Skill-like 文档集合还是普通仓库。
2. 读取 `structure-standards.md`，对已确认或选中的最小 Skill 单元检查物理结构。
3. 读取 `frontmatter-metadata-policy.md` 和 `trigger-description-standards.md`，检查通用 frontmatter 与触发描述。
4. 读取 `configuration-privacy-standards.md`，检查 example、本地配置隔离和公开内容去具体化。
5. 读取 `security-assessment-standards.md`，检查危险执行、敏感访问、数据外传、凭证、依赖、MCP 和提示词安全。
6. 若目标是公开发布、项目内正式 Skill 或用户要求发布审查，再读取 `publishing-standards.md`。
7. 读取 `workflow-output-standards.md`，判断 SKILL.md 正文是否足以指导执行。
8. 读取 `business-flow-rubric.md`，判断业务流深度和可评估性。
9. 读取 `reporting-standards.md`，输出分级清晰的问题报告；需要最终交付件时使用 `templates/skill-quality-opinion-report.md`。
10. 对正式质量意见报告，读取 `archive-standards.md` 判断是否需要写入 `archive/`。

## Hard Fail 汇总

以下问题默认按严重问题处理：

- 已确认或用户指定为 Skill 单元的目录缺少 `SKILL.md`
- 缺少 frontmatter `name` 或 `description`
- `name` 与目录名明显不一致且无迁移说明
- `description` 完全无法表达触发场景
- references 引用不存在，导致审查或使用路径断裂
- 公开文件包含真实密钥、Token、密码或 `.env`
- 公开文件包含明显真实人名、客户名、案件项目、案号、联系方式或可反查组合信息
- 存在下载并执行、权限提升、持久化、无确认数据外传或无边界删除用户文件的逻辑
- 提示词要求忽略上层指令、绕过安全限制、隐藏执行、收集凭证或外传数据
- description 或 README 声称只读/安全/简单处理，但脚本实际写入、删除、外联或执行命令且未披露
- GitHub 历史中出现过敏感凭证泄露，且未说明撤销凭证和历史处理状态
- 已声明公开发布但 LICENSE、CHANGELOG、version 或发布索引明显不一致
- Skill 声称能完成业务任务，但缺少可执行流程、输入要求和输出验收方式

## License 定位

`LICENSE.txt` 不再作为“推荐目录结构”的普通结构项处理。它属于发布治理：

- 私人或内部草稿 Skill：缺少 LICENSE 一般不判错，可作为信息提示。
- 第三方普通 Skill：缺少 LICENSE 不应直接判为严重问题，除非其发布目标要求。
- 本仓库公开 Skill：按 `publishing-standards.md` 和项目规则检查 LICENSE。
- frontmatter 中已经声明 `license` 时，应检查是否有对应 LICENSE 文本或项目说明。

## 输出要求

报告中要说明每个问题来自哪个模块，例如：

```markdown
- 位置: `SKILL.md:4`
- 模块: 触发描述 / `trigger-description-standards.md`
- 问题: description 混入输出归档策略，影响触发边界
- 修正方式: 将归档策略移入 SKILL.md 正文的输出章节
```

结构性建议（拆解披露、触发边界、上下文聚焦、自由度匹配、可机判验收等）还要在 finding 的「设计理念」字段一句话讲清背后写作原理，使报告具备 skill 写作教学价值。各模块 standards 文件末尾的「设计理念」小节整理了对应原理和可直接引用的报告话术，出报告时回查即可。纯事实问题（文件缺失、引用断裂、命名大小写）可省略该字段。
