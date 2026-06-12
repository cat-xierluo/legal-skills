# Decisions

## D-2026-06-12-10 安全评估独立成模块

- 背景：用户提出既然 `skill-lint` 可以评测 Skill，也应增加一轮安全性评估，并可参考 `skills/skill-manager` 中 GitHub 安装后的安全检查能力。
- 决策：新增 `references/security-assessment-standards.md`，把安全性评估作为独立审查模块接入默认流程，覆盖危险执行、下载并执行、权限提升、文件删除、敏感文件访问、数据外传、硬编码凭证、动态导入与混淆、安装钩子、MCP、依赖风险、提示词安全和 Git 历史敏感泄露。
- 理由：安全评估和“公开内容去具体化”不是同一层问题。前者判断 Skill 是否可能造成系统、凭证、数据或提示词安全风险；后者判断示例和文档是否包含真实人名、客户、案件或配置值。拆成独立模块后，报告可以分别给出质量结论、安全级别和整改方式。
- 实施：参考 `skill-manager/scripts/security.py` 的分类，但不把安装脚本变成 `skill-lint` 的运行依赖；在 `SKILL.md`、审查索引、报告规范、质量意见报告模板和 `config/review-profile.example.yaml` 中加入安全评估入口、检查项、Hard Fail 和风险分级。

## D-2026-06-12-09 仓库审查先发现最小 Skill 单元

- 背景：用户指出，当输入是 GitHub 仓库时，该仓库可能是 monorepo 或 Skill 集合；直接检查根目录是否存在 `SKILL.md` 会误判，应该先识别 repo 中哪个目录或文件才是 Skill 的最小单元。
- 决策：新增 `references/repository-skill-discovery-standards.md`，把仓库审查拆成“单元发现”和“单元审查”两个阶段。根目录缺少 `SKILL.md` 不再默认是严重问题；只有用户指定的 Skill 单元、发布索引声明的 Skill 单元，或声明为单 Skill 仓库的根目录缺少 `SKILL.md`，才按严重问题处理。
- 理由：monorepo 根目录通常承担治理、索引和发布配置功能，不等同于 Skill 根目录。先定位最小单元，可以避免把仓库级问题、Skill 单元问题和迁移候选文档混在一起。
- 实施：更新 `SKILL.md`、`skill-standards.md`、`structure-standards.md`、`reporting-standards.md` 和质量意见报告模板，报告中必须列出已确认 Skill、Skill-like 文档、README 索引项及本次纳入范围。

## D-2026-06-12-08 增加内部 archive 归档机制

- 背景：用户提出 `skill-lint` 内部也需要增加 archive 机制，用于保存正式审查报告和质量意见。
- 决策：新增 `archive/.gitkeep` 和 `references/archive-standards.md`；正式质量意见报告可归档到 `archive/YYYYMMDD_HHMMSS_<target-slug>/`，包含 `quality-opinion-report.md`、`review-metadata.json`、`evidence-index.md` 三类文件。
- 理由：质量意见报告需要可追溯、可复查，但真实审查报告可能包含外部项目路径、提交摘要、用户配置或敏感材料。用 `archive/` 保存运行产物，并依赖根目录 `.gitignore` 忽略真实归档内容，可以兼顾追溯和公开发布安全。
- 边界：Git 只保留 `archive/.gitkeep` 和规则文件；真实归档内容不提交。归档前必须脱敏，不能复制客户、案件、联系方式、密钥或外部仓库的大段原文。

## D-2026-06-12-07 增加最终质量意见报告模板

- 背景：用户提出审查一个 Skill 后，最终可能需要出具一份 Skill 质量意见报告，明确指出问题以及修正方式。
- 决策：新增 `templates/skill-quality-opinion-report.md`，作为正式审查交付模板；更新 `SKILL.md`、`reporting-standards.md` 和结构规范，要求正式质量意见报告写明问题、影响、修正方式和复查标准。
- 理由：reference 适合定义审查规则，template 适合承载最终交付格式。把最终报告模板放入 `templates/`，可以让审查输出更稳定，也方便个人 Skill 审查和发布前验收复用。

## D-2026-06-12-06 Reference 按审查功能解耦

- 背景：用户指出 `skill-standards.md` 中“推荐结构”混入 LICENSE 等发布要求，整个 reference 可以进一步按 `skill-lint` 当前功能规范解耦，以便个人 Skill 创建和审查时更清楚地加载规则。
- 决策：将 `skill-standards.md` 改为审查索引，只保留模块路由、默认顺序、Hard Fail 汇总和 License 定位；新增结构、触发描述、配置隐私、发布治理、工作流输出、报告分级六个细则文件。
- 理由：目录结构、发布许可证、触发描述、配置隐私和业务流质量是不同判断层。拆开后，审查第三方普通 Skill 时不会把本仓库发布规则误当作通用硬要求；审查个人 Skill 时也可以按本地配置只加载需要的模块。
- 取舍：保留 `frontmatter-metadata-policy.md` 和 `business-flow-rubric.md` 作为既有独立模块，不重复搬运；`publishing-standards.md` 专门承接 LICENSE、CHANGELOG、version、README 和 Marketplace。

## D-2026-06-12-05 增加可复制审查配置模板

- 背景：用户指出仅有 `frontmatter-metadata-policy.md` 示范意义不足，审查个人 Skill 时应提供可直接复制使用的 config/example。
- 决策：新增 `config/review-profile.example.yaml`，用于配置普通必需字段、项目发布字段、第三方审查策略、公开内容去具体化、严重程度和报告暴露策略。
- 理由：policy 适合解释规则，config example 适合复用落地。使用 `*.example.yaml` 入仓、`*.local.yaml` 本地填写，可以让用户配置个人默认值，同时避免真实个人信息进入公开仓库。

## D-2026-06-12-04 Frontmatter 元数据分层

- 背景：用户指出个人 `homepage`、`author`、`version`、`license` 等配置不应混入普通 Skill 的基础规范；普通 Skill 实际只需要 `name` 和 `description`。
- 决策：将 frontmatter 元数据分为“通用加载字段”和“项目/平台发布字段”。通用必需字段仅为 `name`、`description`；`version`、`license`、`author`、`homepage`、`source` 只在项目规则或发布平台需要时检查。
- 理由：`description` 是技能路由指纹，`name` 是技能身份；其他字段服务于发布、索引、许可证和项目治理。把个人默认值写进通用模板会导致第三方 Skill 被误判，也会放大个人配置泄露和模板污染风险。
- 实施：新增 `references/frontmatter-metadata-policy.md`，并调整格式检查清单中的 frontmatter 字段要求。

## D-2026-06-12-03 示例配置与公开内容必须去具体化

- 背景：用户指出设置文件中不应出现非常具体的信息、人名或按真实案件项目填写的内容，这类问题不能只靠固定关键词，需要智能判断。
- 决策：将“示例配置与公开内容去具体化”纳入 `skill-lint` 审查规则。`config/*.example.*`、SKILL.md、references、CHANGELOG、TASKS、DECISIONS 等公开文件不得包含真实人名、客户名、案件项目、案号、联系方式、地址、账号或可反查组合信息。
- 理由：Skill 是公开复用单元，示例文件和文档一旦混入真实业务信息，会造成隐私、合规和可发布风险；使用占位符和泛化案例能保留结构说明，同时降低泄露风险。
- 判定方式：结合关键词、字段语义和上下文智能判断。无法确认是否真实时标为疑似具体信息；明显真实或可识别时按严重问题处理。

## D-2026-06-12-02 重定位为专门的 skill-lint 验收工具

- 背景：用户反馈原 `skill-architect` “创建 + 审查一体化”后显得泥沙俱下，不利于作为后置质量验收工具独立判断一个 Skill 的质量。
- 决策：将公开入口从 `skill-architect` 重定位为 `skill-lint`，目录迁移到 `skills/skill-lint/`，frontmatter `name` 改为 `skill-lint`；主文档去掉创建模式，聚焦格式审查、发布一致性、业务流深度和可评估性。
- 理由：创建和验收是两个不同阶段。创建阶段需要发散和设计，验收阶段需要收敛、判错和给出可执行修复建议。拆回 `skill-lint` 后，触发边界更清楚，也便于前端或第三方调用做质量判断。
- 实施取舍：业务流深度判则采用中等严格度，Hard Fail 作为硬指标，五层评估对象作为软指标；个人偏好文件保持本地隔离，不作为公开配置模板发布。

## D-2026-06-12-01 统一 references 文件名为小写

- 背景：`skill-architect` 的 `references/` 中同时存在大写规范文档文件名和小写检查清单文件名，引用风格不统一，也不利于后续改造成专门的 lint/验收工具。
- 决策：将参考文档文件名统一为小写 kebab-case，保留语义清晰的名称：`skill-dev-guide.md`、`skill-orchestration-guide.md`、`skill-standards.md`。
- 理由：小写文件名减少跨平台大小写差异带来的引用风险；kebab-case 与 skill 目录命名风格一致，后续新增 `business-flow-rubric.md` 等判则文件时也有统一规则。

## D-2026-06-07-01 整合 skill-lint 到 skill-architect

- 背景：`skill-architect` 已包含创建、编辑和格式审查流程，`skill-lint` 只提供独立审查入口；两者的 `references/skill-standards.md` 内容完全一致，继续维护两个技能会造成触发与规则维护重复。
- 决策：保留 `skill-architect` 作为唯一公开 Skill，将 `skill-lint` 作为旧称兼容到审查模式；从 README、Marketplace 和发布配置示例中移除 `skill-lint` 独立入口，并删除 `skills/skill-lint/` 目录。
- 理由：`skill-architect` 是更完整的上位技能，已覆盖审查模式；合并后只需维护一套规范、一份触发描述和一条发布记录。
- 许可证：合并后的 `skill-architect` 使用 MIT，避免将原 MIT 的审查能力整合后变为更受限的许可证，并符合通用工具类 Skill 的许可证规范。
