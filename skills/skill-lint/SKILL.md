---
name: skill-lint
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "2.4.0"
license: MIT
description: Skill 创建预检、可靠性验收与格式审查工具，也可称 Skilllint。本技能应在用户创建、重大改造或审查 Claude Code Skill，需要识别旧版 Skill 的指令遵循不稳定、产出漂移、验证模态错配、约束漏检，或检查 Harness 契约、候选绑定证据、故障注入、目录结构、业务流和安全风险时使用。不要用于：代替业务领域验证器、代码审查、应用功能测试、通用编程任务。
---

# Skill Lint

本技能负责 Skill 创建前设计预检和创建后质量验收：审查一个 Claude Code Skill 是否结构合规、文档一致、可发布、可评估、安全风险可控，判断它是否真实承载业务流程，并检查“完成”结论是否由候选绑定证据和多轮真实产物支撑。

本技能不代替主要创建者或领域验证器。创建或大改 Skill 时，用它先审查 Harness 设计，再由创建工具实现，完成后回到本技能做候选绑定验收。

## 工作原则

- 先看硬性问题，再看优化问题。
- 先做静态审查，再判断业务流深度。
- 先定位审查单元，再审查目标 Skill 目录及明确给出的上下文。
- 不把格式合规等同于任务效果通过。
- 不采信生产者自报的 PASS；正式验收必须绑定当前候选、当前规则和实际日志。
- 不把“有 checker”当作“覆盖完整”；每条硬约束必须追踪到合适模态、正确产物阶段和回归用例。
- 不比较自然语言输出的整文件哈希；只比较合同声明的关键覆盖集合和可观察不变量。
- 客观缺陷 fail-closed；语义质量保留人工判断，不伪装成万能自动化。
- 对无法确认的能力标注“未提及/待补充”。

## 输入

审查时至少需要：

- 目标路径或仓库地址：可以是单个 Skill 目录、monorepo 根目录、GitHub 仓库或待改造的提示词集合
- 审查目的：创建前设计预检、发布前验收、改造评估、他人 Skill 审查、回归检查等

可选输入：

- 用户给出的特殊偏好或项目规则
- 本地审查配置文件，如 `config/review-profile.local.yaml`
- 需要重点关注的问题清单

如需配置个人或项目的发布元数据策略，先复制 `config/review-profile.example.yaml` 为 `config/review-profile.local.yaml`，再填入本地值。个人偏好只作为本地上下文使用，不写入公开文件，不复制到审查报告中，除非用户明确要求公开。

## 审查流程

### 0. 选择模式

- **创建预检**：目标尚未实现或将重大改造。先读取 `references/harness-reliability-standards.md`，产出七层 Harness 设计、Hard Fail 和至少一个逃逸反例；不要直接扩大提示词。
- **快速审查**：检查第三方 Skill、草稿或局部问题。可以只做静态与语义审查，但结论必须写 `NOT_VERIFIED`，不得称功能已验收。
- **旧版稳定性审查**：检查老版本、多维 review、视觉生产或反复漏项的 Skill。先读取 `references/instruction-stability-standards.md` 并运行静态 `assess`；缺少约束追踪合同或多轮证据时标记 `NOT_VERIFIED`，不得用一次成功执行推断稳定。
- **正式验收**：发布、交付或声称“稳定完成”前，除全部审查模块外，还必须运行候选绑定证据门禁。动态执行只用于用户已确认的自有/可信候选；未知第三方候选默认停在 `NOT_VERIFIED`，除非用户明确授权并使用隔离环境。

创建预检完成后，由用户指定的创建工具或实现者落地；本技能在实现完成后重新进入正式验收。这样既把可靠性理念前移，又不让审查器与生产器混成同一责任。

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
- `harness-reliability-standards.md`：七层 Harness、独立验证、候选绑定证据、故障注入和闭环
- `instruction-stability-standards.md`：约束追踪、验证模态、产物阶段、多轮覆盖和漂移判定
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

### 6. Harness 可靠性审查

创建预检、重大改造和正式验收必须读取 `references/harness-reliability-standards.md`，逐层检查 Contract / Producer / Verifier / Evidence Binding / Fault Injection / Closure / Composition。旧版、多维审阅、视觉生产或用户反馈“反复漏项/产出漂移”时还必须读取 `references/instruction-stability-standards.md`。

先静态识别：

```bash
python3 scripts/instruction_stability_gate.py assess \
  --candidate-root /path/to/skill
```

缺少 `config/instruction-stability-contract.json` 时，`assess` 返回退出码 2 和 `INSTRUCTION_STABILITY_NOT_VERIFIED`，并按实际内容标出视觉模态缺失、多维审阅无重复证据、完成声明未绑定回执等问题。此模式不执行候选代码，适合旧版和未知第三方 Skill。

声称“指令遵循稳定”“多轮不漏项”前，目标 Skill 必须提供约束追踪合同。每条 hard constraint 在权威来源中使用唯一 `<!-- skill-lint:constraint CONSTRAINT-ID -->` 锚点；候选外 evaluator-signed 基线必须与全部锚点、规范行、合同和当前候选哈希一致。先取得当前候选可复算的 Harness 审查证据，再用相同输入/配置至少独立执行三轮；每轮保留唯一 execution nonce、evaluator-signed producer log 和独立目录内的真实产物。每条硬约束还必须有候选外 evaluator-signed held-out 正反例。完成静态安全审查、披露 checker 且用户确认候选为自有/可信代码后，运行：

```bash
python3 scripts/instruction_stability_gate.py verify \
  --candidate-root /path/to/skill \
  --evaluator-public-key /path/to/review/evaluator-public.pem \
  --requirements-baseline /path/to/review/requirements-baseline.json \
  --harness-evidence /path/to/review/harness-review.json \
  --held-out-cases /path/to/review/held-out-cases.json \
  --held-out-root /path/to/review/held-out \
  --run-evidence /path/to/review/runs.json \
  --runs-root /path/to/review/runs \
  --receipt /path/to/review/instruction-stability-receipt-draft.json \
  --confirm-trusted-candidate
```

该门禁固定使用当前受信 `skill-lint` 复算 `HARNESS_REVIEW_VERIFIED`，再逐轮重跑 active checker。它要求每条硬约束精确映射到显式来源锚点、自动发现并签名枚举的 requirements sources/exclusions、checker、正确验证模态、正确产物阶段、带类型/条件/阈值的 measurement、签名 hidden 正反例和已知历史回归；合同漏列规范行、签名无效、三轮复用路径、旧候选/旧 producer 日志重放、负向用例因其他约束失败、少报一个 constraint id、checker 修改产物或关键 observable 漂移都会阻塞。公开、隐藏和真实运行产物统一使用同类随机暂存路径，避免 checker 按样本类别分支。

`verify` 只生成 `INSTRUCTION_STABILITY_EVIDENCE_READY` 草稿。evaluator 必须在不执行候选代码的隔离环境用 Ed25519 私钥运行 `sign-evidence --private-key ...`，再用只持有候选外公钥的 `verify-receipt` 复验全部绑定；只有后一步输出 `INSTRUCTION_STABILITY_VERIFIED` 才能声明稳定。私钥不得出现在 producer/checker 的进程树、环境或可读工作区，完整命令见 `references/instruction-stability-standards.md`。

客观 Hard Fail 一律阻塞。正式验收应先用 `scripts/harness_evidence_gate.py snapshot` 固化候选与规则读集，填写候选内 checker、参数、超时和故障用例的预期失败码。完成静态安全审查并取得用户对自有/可信候选的确认后，再用 `verify --confirm-trusted-candidate` 亲自重跑。JSON 中不得填写或采信自报退出码、PASS 和日志。只有退出码为 0 且出现 `HARNESS_REVIEW_VERIFIED`，才能说“当前候选的 Harness 审查证据已验证”。该标记不替代目标 Skill 自己的 `DOMAIN_VERIFIED`，门禁也不是第三方代码沙箱。

完成标记不可互相替代：

- `HARNESS_REVIEW_VERIFIED`：当前候选、规则、checker 和故障用例证据有效。
- `INSTRUCTION_STABILITY_EVIDENCE_READY`：动态复算已完成，但草稿尚未离线签名与验签，不能作为完成标记。
- `INSTRUCTION_STABILITY_VERIFIED`：evaluator Ed25519 签名回执已复验，外部硬约束基线/held-out、当前 Harness evidence、候选/producer 绑定和至少三轮真实产物逐约束通过，measurement/observable 未漂移。
- `DOMAIN_VERIFIED`：领域验证器确认具体业务产物正确。

只要 Skill 声称“稳定完成”，就必须同时满足前两项；若还声称业务结果正确，再加第三项。未运行的层一律写 `NOT_VERIFIED`。

### 7. 可评估性审查

确认 Skill 是否具备后续 eval 的基础：

- 是否声明评估范围
- 是否声明 Hard Fail
- 是否提供 benchmark case 或样例
- 是否提供输出验收标准
- 是否区分静态检查与动态评估
- 是否有逐约束追踪合同、验证模态和产物阶段
- 是否用至少三轮固定输入检查关键覆盖集合与历史回归

缺少这些内容不一定阻塞发布，但应作为质量风险记录。

### 8. 生成审查报告

审查报告应优先列出问题，再给摘要。严重问题必须具体到文件和位置。

如用户需要最终交付件、发布前意见或正式质量结论，使用 `templates/skill-quality-opinion-report.md` 生成“Skill 质量意见报告”，报告中必须写明问题、影响、修正方式和复查标准。

对承载设计原理的结构性建议（拆解披露、触发边界、上下文聚焦、自由度匹配、可机判验收等），在 finding 的「设计理念」字段一句话讲清背后写作原理，可回查对应 standards 文件的「设计理念」小节，使报告同时具备 skill 写作教学价值；纯事实问题（文件缺失、引用断裂、命名大小写）可省。稳定性 finding 必须具体指出漏的是哪条 constraint、验证模态、产物阶段、case 或 run，不使用“遵循不稳定”这类无法复查的泛称。

生成正式质量意见报告后，按 `references/archive-standards.md` 判断是否归档。需要归档时，在本技能 `archive/YYYYMMDD_HHMMSS_<target-slug>/` 下保存报告、元数据和证据索引；真实归档内容不提交到 Git。

## 问题分级

| 级别 | 说明 | 处理 |
|------|------|------|
| ❌ 严重 | 阻塞加载、发布、使用安全或质量验收 | 必须修复 |
| ⚠️ 警告 | 影响维护、复用、审查可信度或可评估性 | 建议修复 |
| ℹ️ 信息 | 风格、清晰度或后续改进建议 | 可选处理 |

Hard Fail 一律按严重问题处理。

## 报告模板

正式质量意见报告模板见 `templates/skill-quality-opinion-report.md`。报告除原有结构、安全、业务流和可评估性外，必须单列 Harness 七层结论、证据等级和完成标记。

模板的设计理念要点（结构性建议必填「设计理念」字段，纯事实问题可省）：

- **严重问题**：位置 + 依据 + 影响 + 修正方式 + 设计理念 + 最优设计 + 复查标准
- **警告问题**：位置 + 影响 + 建议修正 + 设计理念 + 最优设计 + 优先级
- **安全评估**：风险类别 + 安全级别 + 上下文（避免纯关键词误报）
- **复查清单**：严重问题已关闭 + 警告问题处理或登记 + 文件引用可达 + 隐私脱敏 + 安全覆盖 + 发布治理同步

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
- `references/harness-reliability-standards.md`：Harness 七层可靠性、Hard Fail、创建预检和候选绑定证据门禁
- `references/instruction-stability-standards.md`：旧版识别、约束追踪、模态/阶段匹配、多轮执行和产出漂移门禁
- `references/reporting-standards.md`：问题分级和审查报告模板
- `references/archive-standards.md`：正式审查报告的内部归档机制
- `references/skill-dev-guide.md`：Skill 开发规范参考
- `references/skill-orchestration-guide.md`：复杂编排规范参考
- `config/review-profile.example.yaml`：个人/项目审查配置模板
- `config/instruction-stability-contract.example.json`：目标 Skill 的约束追踪合同示例
- `config/instruction-stability-requirements-baseline.example.json`：候选外独立硬约束基线格式示例
- `config/instruction-stability-held-out-cases.example.json`：evaluator-signed 候选外隐藏正反例清单格式
- `scripts/harness_evidence_gate.py`：生成和复算候选绑定的 Harness 审查证据
- `scripts/instruction_stability_gate.py`：静态识别旧版结构风险，并验证多轮真实产物的逐约束覆盖稳定性
- `templates/skill-quality-opinion-report.md`：最终 Skill 质量意见报告模板
