# Tasks

## 待办

- [ ] severity 边界(❌ Hard Fail vs ⚠️ 警告)更明确:agent-eval-lab r7 自迭代时,"业务流浅"被判 Hard Fail,判据示例可更稳。
- [ ] 报告加"给非技术用户的结论摘要"段(像 agent-eval-lab 的"给你的结论"),不只技术指标表。
- [ ] 静态预筛层:继续把 frontmatter 和目录规范脚本化；候选/规则绑定及动态 checker 重跑已在 v2.3.0 落地。
- [ ] Hard Fail 完备性:知识堆砌(agent-eval-lab r8 验证 ✓);补"纯 prompt 堆砌 / 纯 few-shot 无流程 / 纯外链无内文"等反 skill 本质形态。
- [ ] 用跨场景、不同任务脆弱性的 golden mini-skill 样本校准 Hard Fail 与语义警告边界。
- [ ] 增加 Windows 环境的路径、runtime 与命令兼容性验证。
- [ ] 评估把历史 finding 自动转为故障用例骨架的可行性。
- [ ] 为多 Skill 组合契约定义可选的机器可读 schema。

## 已完成

- [x] Task-014：识别旧版 Skill 的指令遵循不稳定和产出漂移
  - 来源：用户要求 `skill-lint` 能识别旧版 `writing-reviewer`、`svg-book-illustrator` 及类似 Skill 中“任务反复强调但实际漏做、产出随轮次漂移、修改未真实落地”的问题。
  - 完成日期：2026-07-23
  - 结果：新增显式约束锚点 + evaluator-signed 候选外基线 + 约束追踪合同的完整性差异审计；门禁自动发现 `SKILL.md` 与 references 中含硬要求信号的文件，禁止静默漏掉整份规范。正式验证固定用当前受信 `skill-lint` 复算 Harness evidence，再核验至少三轮同输入/配置、唯一 nonce、独立路径和签名 producer log 的真实产物；日志绑定 evaluation、当前候选及 producer 实现清单，公开/隐藏/run artifacts 使用同类随机路径。证据改用候选执行环境之外的 Ed25519 私钥签名，动态门禁只生成 `EVIDENCE_READY` 草稿，最终须由公钥 `verify-receipt` 复验后才输出 `INSTRUCTION_STABILITY_VERIFIED`。新增 38 个专项回归，与原有 14 项证据门禁共 52 项接入 PR/main CI；缺合同、签名基线/held-out、Harness evidence、合格多轮证据或最终签名回执时保持 `NOT_VERIFIED`。
  - 历史校准：以 writing-reviewer v0.13/v0.14 的文字关闭、空 active scope、陈旧状态和读集缺口，以及 svg-book-illustrator v1.8.4/v1.8.8 的几何目检漂移、生产器/文档冲突为 failure family，不复制真实书稿或敏感材料。

- [x] Task-013：建立可验证 Harness 创建预检与正式验收门禁
  - 来源：用户希望把书籍项目中“规则反复强调但仍遗漏、修改不到位”的治理经验融入 `skill-lint`，用于创建或审查其他 Skill。
  - 完成日期：2026-07-22
  - 结果：新增七层 Harness 模型、候选/策略绑定、可信候选确认、最小环境、实时 checker 重跑、故障注入与完成语义分层；正式门禁不采信自填退出码或 PASS，未知第三方候选默认 `NOT_VERIFIED`。

- [x] Task-012：增加 Skill 安全性评估模块
  - 来源：用户提出既然可以评测 Skill，也应增加一轮安全性评估，并参考 `skills/skill-manager` 中 GitHub 安装后的安全检查能力。
  - 完成日期：2026-06-12
  - 结果：新增 `references/security-assessment-standards.md`；更新 `SKILL.md`、审查索引、报告规范、质量意见报告模板和配置示例，将危险执行、敏感文件访问、数据外传、硬编码凭证、提示词安全、依赖风险、安装钩子、MCP 风险和 Git 历史敏感泄露纳入独立安全评估。
- [x] Task-011：增加仓库 / monorepo 的最小 Skill 单元发现机制
  - 来源：用户指出给出一个仓库时，仓库可能是 monorepo，不能只看根目录是否存在 `SKILL.md` 或 Markdown 文件，而应检测 repo 中哪个才是 Skill 的最小单元。
  - 完成日期：2026-06-12
  - 结果：新增 `references/repository-skill-discovery-standards.md`；更新 `SKILL.md`、审查索引、结构规范、报告规范和质量意见报告模板，要求仓库审查先定位单 Skill、monorepo、Skill-like 文档或普通仓库，再按最小单元审查。
- [x] Task-010：增加内部 archive 归档机制
  - 来源：用户提出 `skill-lint` 内部也要增加 archive 机制。
  - 完成日期：2026-06-12
  - 结果：新增 `archive/.gitkeep` 和 `references/archive-standards.md`；更新 `SKILL.md`、结构规范、报告规范和质量意见报告模板，规定正式报告可归档到 `archive/YYYYMMDD_HHMMSS_<target-slug>/`，真实归档内容不提交到 Git。
- [x] Task-009：增加最终 Skill 质量意见报告模板
  - 来源：用户提出审查 Skill 后可能要出具最终质量意见报告，指出问题及修正方式。
  - 完成日期：2026-06-12
  - 结果：新增 `templates/skill-quality-opinion-report.md`；更新 `SKILL.md`、`reporting-standards.md` 和结构规范，要求最终报告包含结论、问题、影响、修正方式和复查标准。
- [x] Task-008：按审查功能解耦 references
  - 来源：用户提出 `skill-standards.md` 中“推荐结构”混入 LICENSE 等发布要求，整个 reference 应按当前 `skill-lint` 功能规范进一步解耦。
  - 完成日期：2026-06-12
  - 结果：将 `skill-standards.md` 改为审查索引，新增 `structure-standards.md`、`trigger-description-standards.md`、`configuration-privacy-standards.md`、`publishing-standards.md`、`workflow-output-standards.md`、`reporting-standards.md`；明确 LICENSE 属于发布治理，不是普通结构硬要求。
- [x] Task-007：补充可复制的个人/项目审查配置模板
  - 来源：用户提出仅有 metadata policy 示范意义不够，应增加普通 config 或 config example，方便审查个人 Skill 时使用。
  - 完成日期：2026-06-12
  - 结果：新增 `config/review-profile.example.yaml`，覆盖通用 frontmatter 必需字段、发布字段策略、第三方审查策略、公开内容去具体化、严重程度和报告暴露策略；本地实际配置使用 `config/review-profile.local.yaml` 并保持不入仓。
- [x] Task-006：抽离个人/项目发布元数据规则
  - 来源：用户提出“个人 homepage / author / version / license 配置应专门抽取，普通 skill 只需要 name 和 description”。
  - 完成日期：2026-06-12
  - 结果：新增 `references/frontmatter-metadata-policy.md`，明确普通 Skill 只硬性要求 `name` 和 `description`；`homepage`、`author`、`version`、`license`、`source` 改为项目/平台发布字段，按项目规则审查。
- [x] Task-005：补充示例配置与公开内容去具体化审查规则
  - 来源：用户提出“设置文件当中都不应该出现非常具体的信息、人名、案件项目，需要智能判断”。
  - 完成日期：2026-06-12
  - 结果：在格式规范和业务流判则中加入真实人名、客户名、案件项目、案号、联系方式、可反查组合信息的审查规则，并明确不只依赖关键词黑名单。
- [x] Task-003：重定位 `skill-architect` → `skill-lint`，打造专门的 Skill 质量验收工具
  - 来源：用户提出"skill 有点泥沙俱下"问题，希望将本技能从"创建 + 审查一体化"重新定位为"专门的后置验收/审查工具"。
  - 立项日期：2026-06-11
  - 完成日期：2026-06-12
  - 状态：**已完成**
  - 结果：新增业务流深度判则，重写主入口为专门的 Skill Lint 审查工具，目录迁移到 `skills/skill-lint/`，并同步 README、Marketplace、ClawHub 示例配置、项目初始化配置和开发/评估指南。

  ### 1. 目标定位

  - 从"创建+审查混合"改为"**专门做 Skill Lint**"：以审查、验收、发现质量问题为核心场景
  - 同时支持审查"自己的 skill"和"他人的 skill"；前端调用也保留为合法使用方式
  - 整体倾向"在后的验收、发现问题"，让其他人能借此判断一个 skill 的质量
  - 与 v1.5.0 整合的方向回转需要单独解释（见 §6 风险与连锁）

  ### 2. 已对齐的共识（2026-06-11）

  | 项 | 决定 | 备注 |
  |---|---|---|
  | 新名字 | `skill-lint`（kebab-case） | 对齐项目多数 skill 命名（`legal-text-format` / `transcription-corrector` / `patent-analysis`） |
  | frontmatter `name` 字段 | `name: skill-lint` | 2026-06-11 用户确认 |
  | 目录路径 | `skills/skill-lint/` | 与 `name` 字段保持一致 |
  | 用户口语展示名 | "Skilllint" 可在 description 中保留 | 触发匹配用,非 name 字段 |
  | 个人 vs 通用分层范式 | 沿用 `*.example.*` 模式 | 参见 `docs/SKILL-DEV-GUIDE.md` §4.3 |
  | 通用规则文件 | `*.example.yaml` 入仓 | 审查"他人"时默认使用 |
  | 个人偏好文件 | `*.local.yaml`（或 `*.personal.yaml`） | 被 `.gitignore` 忽略；审查"自己"时挂载 |
  | 业务流深度判则载体 | 独立 `references/business-flow-rubric.md` | 判则来源见 §3 |

  ### 3. 审查维度设计（v1.6.1 → v2.0.0 改造点）

  #### 3.1 结构维度（与 v1.6.1 Step 5 部分重叠，需要瘦身聚焦）

  - frontmatter 合规
  - SKILL.md 长度
  - 脚本规范
  - 文件夹内部是否整洁、命名是否统一

  #### 3.2 内容维度（**新增，重点设计**）

  - 这个 skill 是否**真实承载了一个业务流程**（业务流深度）
  - 是否声明评估范围 / Hard Fail / benchmark / 验收标准（`SKILL-EVALUATION-GUIDE.md` §10.2 已埋点）
  - 如果只是简单规范罗列、缺少可执行流程，应当判定为质量不足
  - 判则来源：综合自 `docs/SKILL-EVALUATION-GUIDE.md`
    - §5 五层评估对象（Trigger / Intake / Reasoning / Output / Safety）
    - §6.2 Hard Fail 条件
    - §10.2 评估基础设施检查

  ### 4. 实施分阶段计划（独立可决策）

  | 阶段 | 内容 | 阻塞/依赖 | 建议优先级 |
  |------|------|----------|----------|
  | 阶段 A | 写 `references/business-flow-rubric.md` 业务流深度判则 | 无 | ★★★ 高（不动其他文件） |
  | 阶段 B | 重写 `SKILL.md` 正文：去掉"创建模式"，聚焦"Lint 工作流" | 依赖 A 落定 | ★★★ 高 |
  | 阶段 C | 改名 + 目录迁移：`skill-architect/` → `skill-lint/` | 依赖 B 完稿 | ★★ 中 |
  | 阶段 D | 同步引用：`marketplace.json` / `README.md` / 其他 skill 引用 | 依赖 C 完成 | ★★ 中 |
  | 阶段 E | 在 `DECISIONS.md` 追加 D-2026-06-11-01 解释方向回转 | 依赖 C 完成 | ★ 低（最后归档） |
  | 阶段 F | 第一次 v2.0.0 release：补 `CHANGELOG.md` + 验证 git ls-files | 依赖 D、E 完成 | ★ 低 |

  ### 5. 最终取舍

  - 业务流深度判则采用中等严格度：五层评估对象作为软指标，Hard Fail 作为硬指标。
  - 审查"他人"时不暴露个人偏好：本地偏好只作为上下文使用，不提供公开 personal example。
  - 阶段 B 采用重写方案：`SKILL.md` 只保留审查、验收和报告相关内容。
  - 改名路径采用一次到位：`skills/skill-architect/` 迁移为 `skills/skill-lint/`。
  - 版本号升为 v2.0.0：目录与公开入口发生破坏性变更。

  ### 6. 风险与连锁影响

  - **方向回转说明**：v1.5.0 (2026-06-07) 刚把 `skill-lint` 合并进 `skill-architect`,本次又拆分出来是合理的新定位（从"创建+审查混合"改为"专门审查工具"），已在 `DECISIONS.md` 追加 D-2026-06-12-02 解释"为什么方向又变了"
  - **引用盘点**：`marketplace.json` / `README.md` / 任何在其他 skill 文档中提到 `skill-architect` 的地方,改名后全部要同步
  - **历史 CHANGELOG 完整性**：v1.5.0 / v1.6.0 / v1.6.1 段落里"整合"相关表述,改名后是否需要加注释指明"该方向在 v2.0.0 撤回"
  - **git 历史**：重命名 + 后续修改会让 `git log --follow` 行为复杂;考虑是否用 `git mv` 保留可追溯性

  ### 7. 迭代空间

  - 业务流深度判则允许"边写边迭代",第一版不必追求覆盖全部 §5/§6.2/§10.2
  - 个人偏好文件的具体字段（哪些偏好值得配置）也是开放点,可以从最简版开始
  - 前端使用场景的实际调用接口（输入参数、输出结构）暂未设计,等主体稳定后再补

- [x] Task-004：统一 `references/` 文件名为小写
  - 来源：用户要求 "Reference 里面的这个文件名称全都改成小写，做个统一"
  - 完成日期：2026-06-12
  - 结果：将开发指南、编排指南重命名为 `skill-dev-guide.md`、`skill-orchestration-guide.md`，并补充 `references/` 文件名小写规则。
- [x] Task-001：整合 `skill-architect` 与 `skill-lint`
  - 来源：用户要求 "`skill-architect`、`skill-lint` 这两个 skill 应该整合成一个"
  - 完成日期：2026-06-07
  - 结果：保留 `skill-architect` 为唯一入口，合并审查触发说明，下线 `skill-lint` 独立发布项和目录。
- [x] Task-002：补充 README 归档/合并说明
  - 来源：用户要求 "readme里面的归档说明里面要更新"
  - 完成日期：2026-06-07
  - 结果：在 README 已归档/已合并技能表中补充 `skill-lint` 已合并到 `skill-architect` v1.5.0。
