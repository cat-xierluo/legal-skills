---
name: skill-lint
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "2.1.0"
license: MIT
description: Skill 质量验收与格式审查工具，也可称 Skilllint。本技能应在用户需要审查 Claude Code Skill 的目录结构、Frontmatter、引用一致性、发布版本、业务流深度、可评估性和安全风险时使用。不要用于：创建新技能、代码审查、应用功能测试、通用编程任务。
---

# Skill Lint

本技能是后置验收工具，负责审查一个 Claude Code Skill 是否结构合规、文档一致、可发布、可评估、安全风险可控，并判断它是否真实承载了业务流程。

不要用本技能从零创建新 Skill。创建或大改 Skill 时，先完成内容设计，再使用本技能做质量验收。

## 工作原则

- 先看硬性问题，再看优化问题。
- 先做静态审查，再判断业务流深度。
- 先定位审查单元，再审查目标 Skill 目录及明确给出的上下文。
- 不把格式合规等同于任务效果通过。
- 对无法确认的能力标注“未提及/待补充”。

## 输入

审查时至少需要：

- 目标路径或仓库地址：可以是单个 Skill 目录、monorepo 根目录、GitHub 仓库或待改造的提示词集合
- 审查目的：发布前验收、改造评估、他人 Skill 审查、回归检查等

可选输入：

- 用户给出的特殊偏好或项目规则
- 本地审查配置文件，如 `config/review-profile.local.yaml`
- 需要重点关注的问题清单

如需配置个人或项目的发布元数据策略，先复制 `config/review-profile.example.yaml` 为 `config/review-profile.local.yaml`，再填入本地值。个人偏好只作为本地上下文使用，不写入公开文件，不复制到审查报告中，除非用户明确要求公开。

## 审查流程

### 1. 确认范围

先读取 `references/repository-skill-discovery-standards.md`，判断输入目标是哪一类：

- 单个 Skill 目录：目标目录自身包含 `SKILL.md`
- monorepo / Skill 集合：仓库根目录只是容器，内部多个子目录才是最小 Skill 单元
- 松散提示词集合：没有标准 `SKILL.md` 单元，但存在带 `name` / `description` frontmatter 的 Markdown 或 README 索引
- 普通仓库：没有足够证据表明包含 Skill

不要只因为仓库根目录缺少 `SKILL.md` 就判定整个仓库不合格。根目录缺少 `SKILL.md` 只有在用户明确指定根目录就是单个 Skill，或仓库声明自己是一个可加载 Skill 根目录时，才按严重问题处理。

发现候选单元后，先列出：

- 已确认 Skill 单元：目录内有 `SKILL.md`
- 非标准但可迁移的 Skill-like 文档：单个 Markdown 带 `name` / `description` frontmatter，或 README 明确称为 skill
- 仓库级治理文件：README、LICENSE、CHANGELOG、Marketplace、贡献说明

如果候选单元很多，先按用户指定范围审查；用户未指定时，优先审查已确认 Skill 单元，并抽样检查 Skill-like 文档，报告中说明抽样范围。

### 2. 扫描文件

对每个已确认或被选中的候选单元列出文件，并重点检查：

- `SKILL.md`
- `CHANGELOG.md`
- `LICENSE.txt`
- `config/*.example.*`
- `references/*.md`
- `scripts/*`
- `assets/*`
- `templates/*`
- `archive/.gitkeep`

如果在 Skill 单元内出现 `.env`、真实密钥、`__pycache__/`、`docs/`、`test/` 等发布版不应包含的内容，按严重程度记录。仓库根目录的 README、docs、LICENSE、CHANGELOG 可以是 monorepo 治理文件，不按单个 Skill 目录结构误判。

### 3. 模块化规则审查

先读取 `references/skill-standards.md` 作为审查索引，再按问题类型读取对应模块。不要一次性把所有细则混在一份报告逻辑中。

默认模块：

- `repository-skill-discovery-standards.md`：仓库类型、monorepo、最小 Skill 单元和候选文档发现
- `structure-standards.md`：目录结构、文件可达性、references 命名
- `frontmatter-metadata-policy.md`：通用字段与发布字段分层
- `trigger-description-standards.md`：`name` 与 `description` 触发边界
- `configuration-privacy-standards.md`：配置模板、本地配置隔离、公开内容去具体化
- `security-assessment-standards.md`：危险执行、敏感访问、数据外传、凭证、依赖、MCP 和提示词安全
- `publishing-standards.md`：LICENSE、CHANGELOG、version、README / marketplace 同步
- `workflow-output-standards.md`：SKILL.md 正文、依赖、脚本、输出和可编排性
- `business-flow-rubric.md`：业务流深度、Hard Fail 和可评估性基础
- `reporting-standards.md`：问题分级和报告结构

`LICENSE.txt`、`version`、README 和 Marketplace 属于发布治理，不属于普通目录结构硬要求。审查私人或第三方普通 Skill 时，只有在用户给出发布目标或项目规则时才按发布模块判定。

### 4. 安全性评估

读取 `references/security-assessment-standards.md`，对纳入审查的 Skill 单元做安全风险评估。

重点检查：

- `SKILL.md` 和 references 是否含提示注入、绕过安全限制、隐藏执行、敏感数据收集或欺骗性描述
- scripts 是否含危险命令执行、下载并执行、权限提升、无边界删除、敏感文件访问、数据外传、动态导入或混淆
- config/example 是否含真实凭证、真实 endpoint、真实 webhook 或本地敏感路径
- 依赖、安装钩子、MCP、网络请求和外部工具权限是否有用途说明、范围限制和用户确认
- GitHub 仓库审查时，提交历史是否出现过敏感信息泄露、异常删除重加或与 Skill 行为不一致的提交

安全评估不等同于完整渗透测试。对命中项要结合上下文判断误报；但涉及凭证泄露、下载并执行、权限提升、持久化、无确认数据外传、隐藏提示词指令等问题时，默认按严重问题处理。

### 5. 业务流深度审查

使用 `references/business-flow-rubric.md` 检查：

- Trigger：是否清楚说明何时触发、何时不触发
- Intake：是否识别输入缺口并规定追问方式
- Reasoning：是否区分事实、归纳、判断和依据
- Output：是否定义输出结构、验收标准和后续动作
- Safety：是否控制隐私、过度承诺和高风险场景

默认采用中等严格度：Hard Fail 是硬指标，五层评估对象是软指标。

### 6. 可评估性审查

确认 Skill 是否具备后续 eval 的基础：

- 是否声明评估范围
- 是否声明 Hard Fail
- 是否提供 benchmark case 或样例
- 是否提供输出验收标准
- 是否区分静态检查与动态评估

缺少这些内容不一定阻塞发布，但应作为质量风险记录。

### 7. 生成审查报告

审查报告应优先列出问题，再给摘要。严重问题必须具体到文件和位置。

如用户需要最终交付件、发布前意见或正式质量结论，使用 `templates/skill-quality-opinion-report.md` 生成“Skill 质量意见报告”，报告中必须写明问题、影响、修正方式和复查标准。

对承载设计原理的结构性建议（拆解披露、触发边界、上下文聚焦、自由度匹配、可机判验收等），在 finding 的「设计理念」字段一句话讲清背后写作原理，可回查对应 standards 文件的「设计理念」小节，使报告同时具备 skill 写作教学价值；纯事实问题（文件缺失、引用断裂、命名大小写）可省。

生成正式质量意见报告后，按 `references/archive-standards.md` 判断是否归档。需要归档时，在本技能 `archive/YYYYMMDD_HHMMSS_<target-slug>/` 下保存报告、元数据和证据索引；真实归档内容不提交到 Git。

## 问题分级

| 级别 | 说明 | 处理 |
|------|------|------|
| ❌ 严重 | 阻塞加载、发布、使用安全或质量验收 | 必须修复 |
| ⚠️ 警告 | 影响维护、复用、审查可信度或可评估性 | 建议修复 |
| ℹ️ 信息 | 风格、清晰度或后续改进建议 | 可选处理 |

Hard Fail 一律按严重问题处理。

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
   - 依据: 违反的规则
   - 影响: 为什么阻塞
   - 建议: 具体修复方式
   - 设计理念: 结构性建议必填，一句话点透背后写作原理；纯事实问题可省

## ⚠️ 警告问题

1. **[问题标题]**
   - 位置: `文件路径`
   - 影响: 维护 / 发布 / 可评估性风险
   - 建议: 具体优化方式
   - 设计理念: 结构性建议必填，一句话点透背后写作原理；纯事实问题可省

## 安全评估

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 凭证与敏感配置 | ✅/⚠️/❌ | ... |
| 危险执行与文件操作 | ✅/⚠️/❌ | ... |
| 网络外联与数据外传 | ✅/⚠️/❌ | ... |
| 依赖、安装钩子与 MCP | ✅/⚠️/❌ | ... |
| 提示词安全 | ✅/⚠️/❌ | ... |

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

## 建议操作

1. ...
2. ...
```

## 参考规则

- `references/skill-standards.md`：审查索引和模块路由
- `references/repository-skill-discovery-standards.md`：仓库类型识别、monorepo 单元发现和候选文档分级
- `references/structure-standards.md`：目录结构、文件可达性和 references 命名
- `references/frontmatter-metadata-policy.md`：Frontmatter 通用字段与项目发布字段分层策略
- `references/trigger-description-standards.md`：`name` 与 `description` 触发边界
- `references/configuration-privacy-standards.md`：配置模板、本地配置隔离和公开内容去具体化
- `references/security-assessment-standards.md`：危险执行、敏感访问、数据外传、凭证、依赖、MCP 和提示词安全
- `references/publishing-standards.md`：LICENSE、CHANGELOG、version 与发布索引
- `references/workflow-output-standards.md`：正文工作流、依赖、脚本、输出和可编排性
- `references/business-flow-rubric.md`：业务流深度和可评估性判则
- `references/reporting-standards.md`：问题分级和审查报告模板
- `references/archive-standards.md`：正式审查报告的内部归档机制
- `references/skill-dev-guide.md`：Skill 开发规范参考
- `references/skill-orchestration-guide.md`：复杂编排规范参考
- `config/review-profile.example.yaml`：个人/项目审查配置模板
- `templates/skill-quality-opinion-report.md`：最终 Skill 质量意见报告模板
