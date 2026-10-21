# legal-skills 项目 AGENTS 历史

仅在追溯规则变更时读取。本文件保留 v1.11.0 及以前的原始记录，不作为现行操作指令；执行以根 AGENTS.md 和对应 Skill 当前合同为准。

| 版本   | 日期       | 更新内容                                                                                                                              |
| :----- | :--------- | :------------------------------------------------------------------------------------------------------------------------------------ |
| v1.11.0 | 2026-10-16 | 明确共享规则按本轮任务绑定角色与动作权限，隔离临时审计限制，补PR合并裁定、唯一执行者与合并后接续 |
| v1.10.0 | 2026-10-16 | 新增连续推进与阶段交接默认：明确 PM/Worker/审计者职责、主动送审、局部等待与真实停止条件；优先程序观察，修正任务选择和CLAUDE导入语法，并提示旧会话规则重载边界 |
| v1.9.4 | 2026-10-13 | 许可证示例技能名随 `litigation-analysis` 更名为 `judgment-analysis` 同步更新（v2.0.0） |
| v1.9.3 | 2026-10-06 | 所有 Agent 开发改用独立 worktree；主目录固定 main、具名串行采用；删除主目录 checkout/pull 及整目录覆盖示例 |
| v1.9.2 | 2026-09-23 | Skill 开发规范唯一维护源改为 skill-lint（细则在其 references/），删除 docs/ 下已内化的 8 份开发/协作指南文档 |
| v1.9.1 | 2026-09-23 | 将通用工具及协作技能示例由旧名 funasr-transcribe 更新为 local-asr |
| v1.9.0 | 2026-08-09 | 停用 Cloud Plugin Marketplace，删除 `.claude-plugin/marketplace.json` 与 `plugin.json` 及对应配置规范；公开 Skill 以 `skills/` 为交付源，发布索引由 README 与实际启用渠道维护 |
| v1.8.1 | 2026-05-20 | 修正 Skill 开发指南链接，明确后续 Skill 规范以 docs/SKILL-DEV-GUIDE.md 为准 |
| v1.8.0 | 2026-05-17 | 新增 README 最近更新区维护规范：要求新增、正式发布或更新公开 Skill 时同步维护根 README 动态 |
| v1.7.4 | 2026-05-15 | 新增通用 Monorepo 合并规范：禁止 git merge 直接合并，改用目录级 checkout |
| v1.7.3 | 2026-05-14 | 统一私有 Skill 与 Customer Skill 的私有仓库和忽略规则说明 |
| v1.7.2 | 2026-05-14 | 明确 custom-skills 与 private-skills 一样为独立私有 Git 仓库，不公开 |
| v1.7.1 | 2026-05-14 | 精简 custom-skills 本地目录说明：与 private-skills 合并说明，移除业务服务场景表述 |
| v1.7.0 | 2026-05-14 | 新增 custom-skills 本地目录规范：按二级项目文件夹组织，项目 Skill 放入项目内 skills/ |
| v1.6.0 | 2026-04-11 | 强化依赖管理规范：新增"脚本依赖防护要求"（硬依赖 try/except + 安装提示、可选依赖降级标志）、"SKILL.md 依赖声明要求"（区分开箱即用/需安装功能、安装位置就近原则） |
| v1.5.5 | 2026-03-24 | 新增 CC BY-NC 商用许可联系方式规范，统一联系方式 |
| v1.5.4 | 2026-03-21 | 精简 SKILL.md frontmatter：删除 23 个技能的 source 字段，只保留 homepage（符合 ClawHub 规范：source/homepage 二选一）                 |
| v1.5.3 | 2026-03-21 | 重构 ClawHub 同步指南：删除 CLAWHUB.md，创建 clawhub-sync skill 替代，提供交互式批量同步能力                                           |
| v1.5.2 | 2026-03-21 | 完善 SKILL.md frontmatter 和 CHANGELOG 格式：为 5 个技能添加 license 字段，修复 3 个技能的 CHANGELOG 版本格式（douyin-batch-download、de-ai-polish、svg-article-illustrator） |
| v1.5.1 | 2026-03-20 | 精简 ClawHub 发布适配章节：区分必填字段（name、description）与推荐字段（version、homepage），移除已删除脚本引用                                         |
| v1.5.0 | 2026-03-20 | 新增 ClawHub 发布适配章节：定义 frontmatter 字段要求                                         |
| v1.4.0 | 2026-02-18 | 新增敏感信息安全规范：定义敏感文件类型、Skill 开发安全检查清单、.gitignore 维护要求和泄露应急响应流程                                       |
| v1.3.5 | 2026-02-13 | 新增"技能级文档"原则：明确 CHANGELOG.md 等文档为技能级别（位于各技能目录下），不创建项目级别文档；用户要求"更新文档"时默认指当前技能的文档 |
| v1.3.4 | 2026-02-08 | 新增版权信息规范：统一所有自研技能 LICENSE.txt 的版权信息为"杨卫薪律师（微信ywxlaw）"，并更新 4 个技能的 LICENSE.txt 文件 |
| v1.3.3 | 2026-02-08 | 更新许可证管理规范：将法律专业应用技能的许可证从 Apache-2.0-NC 更改为 CC BY-NC（署名-非商业性使用-相同方式共享），更新相关文档和模板 |
| v1.3.2 | 2026-02-08 | 新增许可证管理规范：定义技能许可证分类（法律专业应用使用 Apache-2.0-NC、通用工具使用 MIT）、SKILL.md frontmatter 许可证字段、LICENSE.txt 文件要求和 README.md 许可证列 |
| v1.3.1 | 2026-02-07 | 新增迁移类 Skill 版本历史保留规范：要求从 Command 或提示词迁移的 Skill 在 CHANGELOG 中保留原始版本历史，确保功能演进可追溯 |
| v1.3.0 | 2026-01-30 | 重构文档结构:将 Skill 开发相关内容分离到独立的 SKILL-GUIDE.md 文件,AGENTS.md 聚焦项目协作规范;通过引用链接两个文档 |
| v1.2.0 | 2026-01-30 | 重新设计 Progressive Disclosure 层级:基于官方加载机制,将三级系统扩展为四级(Level 0: Frontmatter, Level 1: 核心文档, Level 2: 支持性文档, Level 3: 可执行资源);新增"文档编写最佳实践"章节;修正技能目录位置说明(`skills/` 目录);优化依赖管理说明,删除反向约束 |
| v1.1.6 | 2026-01-23 | 新增 AGENTS.md 更新规范：要求每次修改 AGENTS.md 时必须同步更新底部的"变更历史"章节；定义版本号递增规则和自动更新要求                   |
| v1.1.5 | 2026-01-23 | 新增 Skill 文档规范：基于官方 Claude Code skills 格式，定义 SKILL.md frontmatter 元数据、description 写作规范、依赖说明格式和 Progressive Disclosure 设计原则 |
| v1.1.4 | 2026-01-22 | 简化依赖管理规范：依赖说明直接写在 SKILL.md 中 |
| v1.1.3 | 2026-01-21 | 强化中文回复要求：将"中文优先"提升为核心原则首位，明确为强制要求而非可选项                                               |
| v1.1.2 | 2026-01-07 | 新增 `CHANGELOG.md` 格式规范：定义版本号规则（测试版 0.x.x、正式版 1.x.x）、版本记录格式、分类标签和内容要求           |
| v1.1.1 | 2026-01-07 | 将 `config/` 纳入按需目录，支持需要配置文件的技能（如 API Token）；配置 archive/ 目录的 git 策略（忽略内容但保留目录） |
| v1.1.0 | 2026-01-07 | 精简文档结构：删除冗余的 `ROADMAP.md` 和 `JOURNAL.md`，保留核心文档 `DECISIONS.md`、`TASKS.md`、`CHANGELOG.md` |
| v1.0.0 | 2026-01-07 | 初始版本，定义法律技能项目的核心协作规范：技能导向、文档即上下文、透明变更、目录约定、标准作业流程及安全合规要求         |
