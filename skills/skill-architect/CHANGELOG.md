# Changelog

All notable changes to this skill will be documented in this file.

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

- 同步 `references/SKILL-DEV-GUIDE.md` 至 v2.4.0。
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
- 同步 SKILL-DEV-GUIDE.md 至 v2.3.0

### 修改

- SKILL.md 精简至 419 行（原 510 行）
- 审查模式精简：移除重复检查清单，引用 Step 5
- 审查报告模板更新：新增行数和目录层级检查项
- 章节编号调整：5.3→SKILL.md 行数，5.4→目录层级，5.5-5.9 顺延

## [1.1.0] - 2026-02-28

### 新增

- **模块化设计检查**（§2）：独立功能解耦、跨 skill 协调规范
- **安全审计检查**（§12）：禁止危险删除命令、API keys 硬编码检查
- 同步 SKILL-DEV-GUIDE.md 至 v2.2.0
- 同步 SKILL-ORCHESTRATION-GUIDE.md 至 v2.0.0

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
- 参考/SKILL-DEV-GUIDE.md - 开发规范参考
- 参考/SKILL-ORCHESTRATION-GUIDE.md - 编排规范参考
