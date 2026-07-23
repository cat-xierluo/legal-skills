# Decisions

## D-2026-07-23-01 指令稳定性采用“逐约束合同 + 多轮真实产物重检”

- 背景：v2.3.0 已能证明候选/策略清单未漂移并实时重跑已选择的 checker，但仍不能证明“所有要求都被选择”“验证方式适合目标属性”“检查的是最终产物”或“下一轮不会漏掉另一项”。旧版 writing-reviewer 和 svg-book-illustrator 均出现过文字规则存在、局部检查通过、真实修订或渲染结果仍漏项的情况。
- 决策：
  1. 新增机器可读约束追踪合同；门禁自动发现 `SKILL.md` 与 references 中含硬要求信号的文件，要求 evaluator-signed 候选外基线完整枚举 sources/exclusions；显式 constraint 锚点、全部纳入的规范行、合同 hard constraints 与基线必须双向一致并绑定当前完整候选，防止合同自身或整份规范文件被漏列。
  2. 没有合同时，静态 `assess` 只给 `NOT_VERIFIED` 和结构性 finding，不执行未知第三方候选。
  3. 声称稳定前必须先复算当前候选的 Harness review evidence，再在同一输入/配置基线上保留至少三轮真实产物；每轮绑定 evaluation ID、唯一 nonce、独立路径和 evaluator-signed producer log，日志还绑定当前候选及 producer 实现清单。`verify` 把 run/public/held-out artifacts 复制到同类随机目录和随机文件名后逐轮运行 checker，checker 必须绑定 artifact SHA-256 并精确报告全部 constraint id、合同化 measurement 和 observable。
  4. 漂移只比较合同声明的关键 observable，不比较整份自然语言输出哈希；支持 exact、set equality 和有界 numeric tolerance。
  5. 完成语义分三层：Harness 证据完整、指令覆盖稳定、领域业务正确，三者不能互相替代；动态 `verify` 只产生 `EVIDENCE_READY` 草稿，只有离线签名并由 `verify-receipt` 重新绑定全部证据后才能输出稳定性 VERIFIED。
  6. 原有证据门禁和新增稳定性门禁进入仓库 CI；以后修改策略、checker、合同或发布版本时自动复跑，避免本地一次性通过后静默退化。
- 独立性边界：evaluator Ed25519 私钥只存在于不执行候选代码的独立 reviewer/CI 离线签名边界；动态验证、producer 和 checker 只接触候选外公钥。签名用于基线、held-out manifest、producer log 和最终 receipt，证明对应私钥持有者签发且证据未被篡改，不证明签发者陈述必然真实；私钥若与候选共享可读主机/工作区则不构成独立性，高风险场景继续要求受控 runner 和外部审计日志。
- 验证模态：geometry/appearance/interaction/state 等约束只接受相应强度的 checker；text/source 检查不能替代 render/visual/final/state。内容审阅中的主观质量保留人工判断，但“是否覆盖全部审阅维度、是否落到真实 source/final/state”必须尽量转为 schema/coverage/state 不变量。
- 安全边界：静态 `assess` 不执行候选；动态 `verify` 仅运行用户确认的自有/可信候选，使用 `shell=False`、最小环境和临时 HOME，但明确不冒充沙箱。回执位于候选和运行产物目录之外，以排他方式原子新建，拒绝已有文件和目标/父目录符号链接。
- 历史校准：writing-reviewer v0.13/v0.14 暴露文字关闭、空 active scope、陈旧 status 和 checker 读集不完整；svg-book-illustrator v1.8.4/v1.8.8 暴露几何目检不可重复、生产器与文档契约冲突。将其抽象为去具体化 failure family 和测试，不把书稿正文写入 Skill。
- 替代方案：未采用“再加一轮 LLM checklist”，因为它仍会出现同类注意力漂移；未强制输出完全相同，因为开放性写作的正常措辞差异不应被误判；未让 `skill-lint` 自动生成领域 checker，因为审查器不能代替领域生产和验证责任。

## D-2026-07-22-01 可靠性审查采用“语义评议 + 实时重跑门禁”双层结构

- 背景：仅靠 SKILL.md 中反复强调任务，仍会出现表面执行、遗漏修改、自报完成和旧证据复用。格式审查无法判断这些结果是否真实落地。
- 决策：`skill-lint` 在创建预检和正式验收中使用七层 Harness 模型。语义判断由审查者完成；正式门禁绑定候选和策略读集，并在 `verify` 时亲自运行候选内已绑定的 checker 和故障用例，不读取生产器自填的退出码或 PASS。
- 严重度边界：可客观判断的缺失、漂移、空范围、未知 checker、执行异常和反例未阻断按 Hard Fail；语义标准宽泛、例外过大等先按警告并保留人工复核。
- 完成语义：`HARNESS_REVIEW_VERIFIED` 证明当前候选的审查器、正例与反例刚刚通过，不冒充业务正确性；目标 Skill 声称完成业务任务时仍需自己的 `DOMAIN_VERIFIED`。
- 安全边界：门禁不使用 shell 字符串，只执行候选清单内、后缀与受支持 runtime 匹配的 checker，并只传递运行所需的最小环境白名单。动态 verify 仅限用户显式确认的自有/可信候选；这不是沙箱，未知第三方候选默认保持 `NOT_VERIFIED`，除非进入用户授权的隔离环境。
- 替代方案：未采用纯清单或自填日志方案，因为仍可被 Agent 文字自报绕过；未采用通用业务验证器，因为不同领域无法由一个静态脚本可靠判定。

## D-2026-06-25-01 Skill 本质审查 + 报告教学化(不做类型分类)

- 背景:agent-eval-lab 自迭代 r7 用 5 个 golden mini-skill 测 skill-lint,发现:(1) 不分 skill 类型,极简测试样本被按"真实业务 skill"判 Hard Fail(过严);(2) 报告"设计理念"是一句话,不够教学。用户明确:不搞类型分类,skill 本质 = 渐进式披露 + 可执行流程;知识库型(知识堆砌)违反本质 = 不合格;报告要教"为什么错 + 最优设计"。
- 决策:
  1. business-flow-rubric 新增 §0「Skill 的本质」(渐进式披露 + 可执行流程;知识堆砌违反);Hard Fail 加「知识堆砌」;去掉"工具类降低要求"分类措辞,改为"按任务脆弱性调严格度,不按类型分类"。
  2. 报告 finding 的"设计理念"(一句话)升级为「为什么错(原理)」+「最优设计(带范例)」两段;reporting-standards + 质量意见报告模板同步。
- 理由:skill 的价值在可执行流程 / 工作规范(渐进式披露),不在知识堆砌;知识库型塞原文违反本质,该判 Hard Fail(不是"另一类标准")。报告教学化让使用者学到原理 + 最优设计,不只"改什么"。不做类型分类避免"用业务型尺子量知识库型"的误判,统一按本质审。
- 效果:retest sample-03(业务流浅)验证——candidate finding 含"为什么错(skill 本质 = 渐进式披露 + 可执行流程)"+ "最优设计(补 Input / 流程 / Output 范例)",优于 control(一句话设计理念)。

## D-2026-06-19-01 报告增加「设计理念」教学层

- 背景：用户希望 skill-lint 出具的审查报告不只告诉读者"怎么改"，还能说明"为什么这样改是对的"——背后的 skill 写作理念（例如拆解 SKILL.md 到 references 是为了渐进式披露、防止无关上下文污染、让模型更聚焦）。目的是让手动翻看报告的人能从每条建议里学到 skill 写作理念，使报告兼具教材价值。
- 决策：
  1. 在 7 个 standards 文件各新增「设计理念（为什么这样要求）」小节，按维度整理写作原理和可直接引用的报告话术，共约 14 条理念，分布在 structure / trigger-description / frontmatter-metadata-policy / workflow-output / security-assessment / configuration-privacy / business-flow-rubric。
  2. 严重问题和警告问题的 finding 增加「设计理念」字段，结构性建议必填、纯事实问题（文件缺失、引用断裂、命名大小写）可省。
  3. 同步更新 SKILL.md 第 7 步、skill-standards.md 索引、reporting-standards.md 报告原则、质量意见报告模板三处模板；version 升至 2.1.0，CHANGELOG 记录。
- 理由：理念就近驻留在各 standards 文件（而非新建集中文件），本身就是渐进式披露——审查到哪个维度读到哪个文件，理念自然可见。finding 内联一句话理念（而非末尾附录），让读者看具体建议时同步学到原理，最贴合"手动看报告学写作"的诉求。
- 实施与效果样例：以下取 archive 里已审过的 conference-planner 报告 3 条警告，用新范式重写，演示「设计理念」如何把"怎么改"升华为"为什么这样是对的"。

### 效果样例（conference-planner，新范式重写）

#### 警告 1 触发描述缺少负向边界
- 位置：`SKILL.md:3` description 字段
- 所属模块：`trigger-description-standards.md`
- 问题说明：描述给出 6+ 个正向触发词，但没有说明不适用场景。
- 影响：模糊场景下会被错触发，浪费上下文。
- 建议修正：在 description 末尾追加"不要用于：会议纪要、会议室预订、内部例会排程、纯文案润色等场景。"
- 设计理念：description 是模型从上百个 Skill 里"选不选你"的唯一依据，过宽的触发面会让本 Skill 在无关任务上被错误加载、白白吞掉上下文。写明"不要用于 X（改用 Y）"是在收窄触发面——本质是保护每条会话稀缺的注意力预算。详见 trigger-description-standards.md「负向边界」。
- 优先级：高

#### 警告 8 Step 5 质量检查报告缺对应输出模板
- 位置：`SKILL.md:163-179` Step 5
- 所属模块：`workflow-output-standards.md`
- 问题说明：步骤说"输出质量检查报告"，但没有对应的 `templates/quality-check-report.md`，其他 5 份输出都有模板。
- 影响：用户每次自己设计报告格式，质量参差。
- 建议修正：增加 `templates/quality-check-report.md`，按 4 级 emoji 分类的报告骨架。
- 设计理念：为输出提供模板能锁死结果结构、减少逐次格式漂移——本步骤要求"生成报告"却无模板，等于把结构稳定性的责任甩给每次会话。详见 workflow-output-standards.md「计划-验证-执行 + 工作流清单」。
- 优先级：高

#### 警告 6 缺 benchmark / 样例输入输出
- 位置：整个 Skill 目录
- 所属模块：`business-flow-rubric.md`（可评估性）
- 问题说明：没有任何示例输入和预期输出。
- 影响：无法做回归测试和 prompt 迭代评估。
- 建议修正：在 `archive/samples/` 下放 1-2 份完整示例。
- 设计理念：先在没有 Skill 的状态下跑代表性任务、记录真实失败，据此定义评估场景，再写最小指令去通过——没有样例，"成功"就永远停留在主观判断。详见 business-flow-rubric.md「评估驱动 / Hard Fail 可机判」。
- 优先级：中

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
