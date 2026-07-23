# Changelog

All notable changes to this skill will be documented in this file.

## [2.4.0] - 2026-07-23

### 新增：旧版指令失稳与产出漂移门禁

- 新增 `references/instruction-stability-standards.md`，把“规则写了但仍漏项”拆成约束追踪、验证模态、真实产物阶段、历史回归和多轮 observable 五类可审计关系。
- 新增 `scripts/instruction_stability_gate.py assess`：未知第三方或旧版 Skill 无需执行候选代码，即可识别多维审阅无重复证据、视觉/几何约束无 render/geometry/visual 验证、完成声明无稳定性回执以及“有脚本但无覆盖证明”等结构性风险。
- 新增正式 `verify`：先复算当前候选的 `HARNESS_REVIEW_VERIFIED`，再对至少三轮真实产物重跑 active checker；checker 必须绑定 artifact SHA-256、逐项报告 constraint measurement，并比较合同声明的 exact / set_equal / numeric_tolerance observables。该步骤只生成 `INSTRUCTION_STABILITY_EVIDENCE_READY` 草稿。
- 新增合同、evaluator-signed 候选外硬约束基线和 held-out cases 示例：门禁自动发现 `SKILL.md` 与 `references/**/*.md` 的硬要求信号文件，签名基线必须完整枚举 sources/exclusions，并让显式来源锚点、合同 hard constraints、基线 source refs、隐藏正反例和当前候选哈希完全一致。
- 三轮证据新增 evaluation ID、相同 input/config SHA-256、唯一 execution nonce、独立 run 目录和 evaluator-signed producer log；日志同时绑定当前完整候选、producer ID 与实现清单哈希，阻断跨候选/跨 producer 重放、复用路径、篡改 runner attestation 或把不同输入混作稳定性样本。
- 正负例和真实 run artifact 都先复制到同类随机临时目录及随机文件名再交给 checker；负向 case 限定为单 constraint / 单 checker，并要求结构化 `failed_constraint_ids`、fixture SHA-256 和 measurement 精确命中目标，减少按公开/隐藏/run 类别路径分支和任意非零退出码冒充覆盖。
- evaluator 证据从进程内共享 HMAC 改为离线 Ed25519 签名：候选动态验证只持公钥，私钥不进入 producer/checker 进程树。新增 `verify-receipt`，只有离线签名草稿重新绑定当前候选、policy、外部证据、producer logs 与真实产物后才输出 `INSTRUCTION_STABILITY_VERIFIED`。
- measurement 合同新增值类型、condition 和 expected 阈值；正例/真实 run 必须满足，负例必须实际违反，不再接受任意非空 measurement 字典。
- 新增 38 个历史失效、漂移与逃逸回归测试，覆盖旧版 writing review、旧版 SVG、整份 requirements 文件漏列、合同漏项、签名基线/held-out/producer log 篡改与重放、样本类别路径泄漏、签名工具不可覆盖、最终回执验签、Harness evidence 陈旧、policy override、measurement 阈值、几何模态和阶段错配、负向误命中、三轮伪复用、集合/数值漂移、产物篡改、路径逃逸、原子回执和可信候选确认。
- 新增 `.github/workflows/skill-lint-harness.yml`，在 PR 和 main 变更时自动运行原有 14 项证据门禁与新增 38 项稳定性回归（共 52 项），并检查 Python 编译、JSON 与发布版本同步。

### 改进

- 正式完成语义仍分 `HARNESS_REVIEW_VERIFIED`、`INSTRUCTION_STABILITY_VERIFIED`、`DOMAIN_VERIFIED` 三层；中间态 `INSTRUCTION_STABILITY_EVIDENCE_READY` 明确不得冒充完成。“稳定完成”至少需要前两层，业务正确性声明再要求第三层。
- 候选绑定策略清单纳入指令稳定性标准；策略更新后旧 Harness review snapshot 自动失效。
- 更新审查索引、业务流、工作流、报告规范、质量意见模板和 review profile，把 verification modality、artifact stage、逐约束覆盖和重复运行证据纳入 Hard Fail。
- 固化真实历史失效类别：文字自报关闭、空 active scope、陈旧状态、读集不完整、SVG 几何目检漂移、生产器与文档冲突、负向 canary 和组合契约冲突。

## [2.3.0] - 2026-07-22

### 新增：从格式审查升级为可验证 Harness 预检

- 新增 `references/harness-reliability-standards.md`，用 Contract / Producer / Verifier / Evidence Binding / Fault Injection / Closure / Composition 七层模型审查 Skill 的真实可靠性。
- 新增创建预检模式：创建或重大改造 Skill 前先定义结果属性、生产者/验证者、Hard Fail、失败回炉和逃逸反例；实现完成后再进入正式验收。
- 新增 `scripts/harness_evidence_gate.py`，用完整候选清单、策略读集和 SHA-256 绑定审查证据，并在 `verify` 时亲自重跑候选内 checker；不读取 JSON 自填的退出码、PASS 或日志结论。
- 新增 14 个故障注入回归测试，覆盖候选漂移、范围漏项、空清单、策略漂移、自报结果、反例未阻断、未知层/runtime/checker、checker 篡改候选、证据覆盖、可信候选确认、敏感环境隔离和不适用理由不足。

### 改进

- 将“执行器自报完成”“只有正常样例”“空范围或检查异常 fail-open”“跨 Skill 无契约”等纳入 Hard Fail。
- 审查报告新增 Harness 七层、成熟度和证据等级，强制区分 `HARNESS_REVIEW_VERIFIED`、`DOMAIN_VERIFIED` 与 `NOT_VERIFIED`。
- 更新 review profile、模块路由、业务流与工作流规则，使客观缺陷走硬门禁，语义质量保留人工判断。
- 更新 `skill-dev-guide.md`，把七层预检前移到创建前，并要求实现后由实时 checker 正式验收。
- 动态 checker 仅允许用户显式确认的自有/可信候选，默认使用最小环境白名单和临时 HOME；未知第三方候选保持 `NOT_VERIFIED`，门禁不冒充代码沙箱。

## [2.2.0] - 2026-06-25

### 新增:Skill 本质审查 + 报告教学化升级(基于 skill-lint 自迭代 golden 测试)

- **business-flow-rubric 新增 §0「Skill 的本质」**:明确 skill = 渐进式披露 + 可执行处理流程 / 工作规范;知识库型(原始文本 / 知识堆砌、无抽象规范、无可执行流程)违反本质,判 Hard Fail。沉淀知识必须抽成抽象规范,不是塞原文。审查**不做"类型分类"**,所有 skill 按本质统一审。
- **Hard Fail 新增「知识堆砌」**:把原始文本 / 知识 / 语料 / 法条 / 书稿成堆塞进 skill,未抽成可执行抽象规范(知识库型典型问题)——skill 不是知识仓库。
- **去掉"工具类降低要求"的分类措辞**:改为"按任务脆弱性调严格度,不按 skill 类型分类"(统一本质审)。
- **报告教学化升级**:finding 的"设计理念"(一句话)升级为「为什么错(原理)」+「最优设计(该怎么设计才对,给范例)」两段——使用者不仅知道改什么,还学到为什么这么设计才对。`reporting-standards.md` + 质量意见报告模板同步。
- 来源:agent-eval-lab 自迭代 r7 用 5 个 golden mini-skill 样本测试 skill-lint,发现"不分类型判太重 + 报告不够教学"两点,据此 patch;retest sample-03 验证有效。

## [2.1.0] - 2026-06-19

### 新增

- 报告新增「设计理念」教学层：严重问题和警告问题的 finding 增加「设计理念」字段，对承载设计原理的结构性建议（拆解披露、触发边界、上下文聚焦、自由度匹配、可机判验收等）一句话点透背后 skill 写作原理，使审查报告同时具备教学价值，让手动阅读报告的人能学到 skill 写作理念。

### 改进

- 7 个 standards 文件（structure / trigger-description / frontmatter-metadata-policy / workflow-output / security-assessment / configuration-privacy / business-flow-rubric）各新增「设计理念」小节，整理该维度背后的写作原理和可直接引用的报告话术。
- 更新 `SKILL.md`、`skill-standards.md`、`reporting-standards.md`、质量意见报告模板，要求结构性建议带理念、纯事实问题可省。

## [2.0.8] - 2026-06-12

### 新增

- 新增 `references/security-assessment-standards.md`，将危险执行、敏感文件访问、数据外传、硬编码凭证、提示词安全、依赖风险、安装钩子、MCP 风险和 Git 历史敏感泄露纳入独立安全评估模块。

### 改进

- 更新 `SKILL.md`、`skill-standards.md`、`reporting-standards.md`、质量意见报告模板和审查配置示例，要求正式审查报告包含“安全评估”维度，并区分安全级别与普通质量问题分级。
- 参考 `skill-manager` 的安全检查分类，但保持 `skill-lint` 作为质量意见工具，不直接依赖安装流程或运行时拦截。

## [2.0.7] - 2026-06-12

### 新增

- 新增 `references/repository-skill-discovery-standards.md`，要求审查 GitHub 仓库或 monorepo 时先发现最小 Skill 单元，再进入结构、frontmatter 和业务流审查。

### 改进

- 更新 `SKILL.md`、`skill-standards.md`、`structure-standards.md`、`reporting-standards.md` 和质量意见报告模板，明确仓库根目录缺少 `SKILL.md` 不等于 monorepo 不合格；只有用户指定或发布声明的 Skill 单元缺少 `SKILL.md` 时才判严重问题。
- 报告模板新增“审查单元发现”部分，用于列出已确认 Skill、Skill-like 文档、README 索引项和未纳入范围。
- 将归档元数据示例中的 `skill_lint_version` 改为占位符，避免示例版本号随发布漂移。

## [2.0.6] - 2026-06-12

### 新增

- 新增 `archive/.gitkeep`，为正式质量意见报告提供技能内部归档目录。
- 新增 `references/archive-standards.md`，定义归档触发场景、目录命名、归档文件、Git 忽略规则、隐私安全和复查关系。

### 改进

- 更新 `SKILL.md`、`reporting-standards.md`、`structure-standards.md` 和质量意见报告模板，要求正式报告按需写入 `archive/YYYYMMDD_HHMMSS_<target-slug>/`，且真实归档内容不提交到 Git。

## [2.0.5] - 2026-06-12

### 新增

- 新增 `templates/skill-quality-opinion-report.md`，作为审查 Skill 后出具最终质量意见报告的模板。

### 改进

- 更新 `SKILL.md` 和 `reporting-standards.md`，要求最终质量意见报告明确问题、影响、修正方式和复查标准。
- 将 `templates/` 纳入结构规范的可选资源目录，用于放置可复用文本模板。

## [2.0.4] - 2026-06-12

### 改进

- 将 `references/skill-standards.md` 从巨型检查清单重构为审查索引，只负责模块路由和默认审查顺序。
- 新增模块化 reference：`structure-standards.md`、`trigger-description-standards.md`、`configuration-privacy-standards.md`、`publishing-standards.md`、`workflow-output-standards.md`、`reporting-standards.md`。
- 将 `LICENSE.txt`、`version`、README、Marketplace 等规则明确归入发布治理，避免普通 Skill 结构审查误判。

### 文档完善

- 更新 `SKILL.md` 审查流程和参考规则列表，说明先读审查索引，再按问题类型读取对应模块。

## [2.0.3] - 2026-06-12

### 新增

- 新增 `config/review-profile.example.yaml`，提供可复制的个人/项目审查配置模板，用于配置发布字段策略、隐私去具体化规则、严重程度和报告暴露策略。

### 改进

- 在 `SKILL.md` 和 frontmatter 元数据策略中说明：本地配置应复制为 `config/review-profile.local.yaml` 使用，不提交到仓库。

## [2.0.2] - 2026-06-12

### 新增

- 新增 `references/frontmatter-metadata-policy.md`，明确普通 Skill 的通用 frontmatter 只硬性要求 `name` 和 `description`。
- 将 `homepage`、`author`、`version`、`license`、`source` 明确划入项目/平台发布字段，不再作为普通 Skill 的通用必填或默认推荐项。

### 改进

- 更新 frontmatter 检查清单，区分“通用必需字段”和“发布字段分层”，避免将个人作者、个人主页、许可证默认值硬编码进通用 Skill 模板。

## [2.0.1] - 2026-06-12

### 新增

- 新增示例配置与公开内容去具体化规则：`config/*.example.*`、SKILL.md、references、CHANGELOG、TASKS、DECISIONS 中不应出现真实人名、客户名、案件项目、案号、联系方式或可反查组合信息。
- 在审查规则中明确“智能判断”要求：不只依赖关键词黑名单，应识别疑似真实业务材料、具名人员、客户简称、法院 + 案由 + 时间组合等具体信息。

## [2.0.0] - 2026-06-12

### 重大变更

- 将公开入口从 `skill-architect` 重定位为 `skill-lint`，目录迁移到 `skills/skill-lint/`，frontmatter `name` 改为 `skill-lint`。
- 移除“创建 + 审查一体化”定位，主入口改为专门的后置质量验收、格式审查和审计报告工具。

### 新增

- 新增 `references/business-flow-rubric.md`，用于审查业务流深度、Hard Fail、五层评估对象和可评估性基础设施。
- 审查报告模板新增“业务流深度”和“可评估性”两部分。

### 改进

- 重写 `SKILL.md`，聚焦目录结构、Frontmatter、引用一致性、发布版本、业务流深度和可评估性审查。
- 同步 README、Marketplace、ClawHub 示例配置、项目初始化配置和根目录开发/评估指南中的入口名称。

## [1.6.2] - 2026-06-12

### 改进

- 统一 `references/` 内参考文档文件名为小写：`skill-dev-guide.md`、`skill-orchestration-guide.md`、`skill-standards.md`。
- 在命名检查中补充 `references/` 文件名全小写、多个词用连字符（kebab-case）的规则，并同步内部引用。

## [1.6.1] - 2026-06-08

### 新增

- **5.17 description 内容边界（只写三件事）**：description 仅含"功能 / 触发 / 不触发"三件事；不含归档 / 输出位置 / 写入策略 / 内部步骤 / 开关状态 / 默认行为 / 产物结构 / 副作用 / 双写策略。附"三件事内容定义表 + 反例表 + 判定命令 + 反例案例"。来源：用户在 transcription-corrector v1.0.7 描述优化中明确"description 只需写功能 / 怎么触发 / 不被什么触发，归档和运作方式不该写在里面"。

## [1.6.0] - 2026-06-08

### 新增

- **5.11 references/ 子文件 frontmatter 限制**：references/*.md 不应携带 frontmatter，元数据唯一来源 = SKILL.md frontmatter；附 bash 扫描命令。来源：审查 transcription-corrector v1.0.6 时发现 `references/skill_overview.md` 携带冗余 frontmatter。v1.0.7 已删除该文件并拆分为 `scope.md` / `config-decoupling.md`（新建时即不带 frontmatter）。
- **5.12 references/ 命名与 SKILL.md 的概念边界**：文件名应反映"具体职责"（first_use / correction_patterns / boundaries）而非通用词（overview / guide）；避免与 SKILL.md 概念重叠的命名（skill_overview / skill_intro）。
- **5.13 公开内容清洁度**：SKILL.md / references/ / CHANGELOG.md / config/*.example.* / DECISIONS.md / TASKS.md 不应出现其他 skill 名 / 私有工作流项目名 / 自家平台名；涉及上下游协作时用通用描述。附反例 + grep 命令。
- **5.14 Git 跟踪状态**：skill 已注册到 marketplace.json / README 时必须 `git ls-files` 验证入仓；整个 skill 目录若 `git status` 显示 `??` 视为严重问题。附三条判定命令。来源：审查 transcription-corrector v1.0.6 时发现整个 skill 目录未跟踪但已注册到 marketplace.json。
- **5.15 CHANGELOG 历史一致性**：v1.0.0 段落应仅描述"v1.0.0 当下"能力；后续版本能力增量在对应版本段落补写，不得"穿越"。来源：审查 transcription-corrector v1.0.0 段落描述了 v1.0.6 才完整的能力。
- **5.16 archive/ 内部一致性**：archive/ 子目录数 ≥ 5 时 STABLE.md / DECISIONS.md 应记录保留策略；STABLE.md 中 `[DEC-XXX]` 引用须与 DECISIONS.md 一致；STABLE.md 内数据自洽。

### 改进

- **5.2 Frontmatter description 长度收紧**：保留 ≤ 1024 字符硬约束，新增"最佳 ≤ 250 字符"建议项（信息密度 vs 长描述的反例）。
- **5.2 references/ 子文件无 frontmatter**：明确为强制项（✅/❌），与 5.11 互为引用。

## [1.5.0] - 2026-06-07

### 新增

- 整合原 `skill-lint` 的独立审查入口：用户提到 `skill-lint` 时，统一按 `skill-architect` 的审查模式处理。
- 新增技能级 `TASKS.md` 与 `DECISIONS.md`，记录本次整合任务、取舍和完成状态。

### 改进

- 更新 `SKILL.md` frontmatter 与正文，将创建、编辑、打包、格式审查、版本同步和审计报告统一为一个技能入口。
- 将许可证调整为 MIT，避免整合后收窄原 `skill-lint` 审查能力的使用权限，并对齐通用工具类 Skill 的许可证规范。
- 同步公开索引和 Marketplace 元数据，将 `skill-lint` 从独立发布项下线。

### 文档完善

- 更新开发指南中的格式合规检查入口，将 `skill-lint` 改为 `skill-architect` 审查模式。
- 更新 README 的已归档/已合并技能说明，补充 `skill-lint` 合并去向。
- 保留历史版本中对 `skill-lint` 的引用，作为当时版本演进记录。

## [1.4.0] - 2026-05-20

### 改进

- 创建流程的 Frontmatter 模板改用新版发布规范，默认包含 `version`、`license`、`author`、`homepage` 推荐字段。
- 将 `version` 从禁止字段调整为公开发布推荐字段，并要求与 `CHANGELOG.md` 最新版本一致。
- 审查清单同步 README 与 marketplace 版本一致性检查，避免发布索引与技能版本漂移。

### 文档完善

- 同步 `references/skill-dev-guide.md` 至 v2.4.0。
- 同步 `references/skill-standards.md` 与 skill-lint v1.4.0 规则。

## [1.3.0] - 2026-03-01

### 新增

- **skill-standards.md 与 skill-lint/checklist.md 统一**：两个文件现在完全一致，方便维护

### 修改

- references/skill-standards.md 重构为混合格式（检查项 + 状态 + 说明）
- 新增 §4 目录层级检查（扁平结构要求）
- 新增 §16 审查报告模板
- 审查摘要新增 SKILL.md 行数、目录层级检查项

## [1.2.0] - 2026-03-01

### 新增

- **负向触发条件**：description 中添加"不要用于"说明
- **SKILL.md 行数检查**（5.3）：限制 ≤ 500 行
- **目录层级检查**（5.4）：references/scripts/assets 扁平结构
- **description 长度检查**：≤ 1024 字符
- 同步 skill-dev-guide.md 至 v2.3.0

### 修改

- SKILL.md 精简至 419 行（原 510 行）
- 审查模式精简：移除重复检查清单，引用 Step 5
- 审查报告模板更新：新增行数和目录层级检查项
- 章节编号调整：5.3→SKILL.md 行数，5.4→目录层级，5.5-5.9 顺延

## [1.1.0] - 2026-02-28

### 新增

- **模块化设计检查**（§2）：独立功能解耦、跨 skill 协调规范
- **安全审计检查**（§12）：禁止危险删除命令、API keys 硬编码检查
- 同步 skill-dev-guide.md 至 v2.2.0
- 同步 skill-orchestration-guide.md 至 v2.0.0

### 修改

- 合规检查清单新增 5.6 模块化设计、5.7 安全审计
- 审查模式检查清单新增 10. 模块化设计检查、11. 安全审计检查
- skill-standards.md 章节编号调整（§2→模块化设计，§12→安全审计）

## [1.0.1] - 2026-02-28

### 新增

- 审查模式：支持审查现有技能的合规性
- 生成结构化审查报告
- 两种使用模式：

  1. **创建模式** - 创建新技能时遵循规范
  2. **审查模式** - 审查现有技能并生成报告

## [1.0.0] - 2026-02-28

### 新增

- 初始版本发布
- 基于官方 skill-creator 理念的自定义创建流程（5 步）
- 内置 12 类合规检查规则：

  1. 目录结构规范
  2. Frontmatter 规范
  3. description 写作规范
  4. 文档一致性规范
  5. 配置文件规范
  6. 技能协作规范（松耦合）
  7. 输出模式规范（模板 + 示例）
  8. 工作流模式规范（顺序 + 条件）
  9. CHANGELOG 规范
  10. 版本号管理规范
  11. 可编排性设计规范
  12. 问题严重程度定义

### 包含文件
- SKILL.md - 主文档（创建流程 + 合规检查 + 审查流程）
- LICENSE.txt - CC BY-NC-SA 4.0 非商用许可证
- CHANGELOG.md - 版本变更记录
- references/skill-standards.md - 技能规范标准（详细检查清单）
- 参考/skill-dev-guide.md - 开发规范参考
- 参考/skill-orchestration-guide.md - 编排规范参考
