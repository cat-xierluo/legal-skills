# Changelog

All notable changes to this project will be documented in this file.

## [v1.2.4] - 2026-07-30

### 改进
- 明确 `TASKS.md` 是流动的当前任务入口：任务完成并同步相应职责文档后，从活跃区移除。

### 修复
- 删除任务模板中的“归档索引”，禁止为 TASKS 创建快照、`before` 副本或专用历史文件；用户可见变化进入 `CHANGELOG.md`，重要取舍进入 `DECISIONS.md`。

## [v1.2.3] - 2026-07-30

### 新增
- 在 `templates/user-agents-backup-template.md` 保存用户级 `AGENTS.md` v4.0 的原样备份，便于追溯与人工复用。

### 文档完善
- 备份模板不接入 `SKILL.md` 工作流，不参与项目初始化的读取、生成或复制。

## [v1.2.2] - 2026-07-30

### 技术优化
- 将全部文档模板统一命名为 `*-template.md`，使模板名称明确区别于生成目标，并降低被宿主项目 Git 忽略规则误排除的风险。
- 同步更新 `SKILL.md` 的模板入口，保持模板命名、使用方式和发布内容一致。

### 修复
- 修正根 README 中 `project-init` 技能列表版本仍停留在 v1.2.0 的同步遗漏。

## [v1.2.1] - 2026-07-30

### 技术优化
- 按消费方式重构资源目录：需要读取后适配的文档骨架统一迁入 `templates/`，逐字复制的配置、规则和忽略模板统一迁入 `assets/`。
- 更新 `SKILL.md` 和 `scripts/init.sh` 的全部生成路径，使 Agent 生成与脚本复制遵循同一目录语义。

### 修复
- 解决 `DECISIONS.md`、`TASKS.md` 模板因全局忽略规则无法进入发布包的问题。
- 删除文档模板对不存在示例文件的引用，并修正 CHANGELOG 模板继续使用 `Unreleased` 的过期规则。

### 文档完善
- 为 ROADMAP、DECISIONS、TASKS、ARCHITECTURE、DESIGN、CHANGELOG 分别声明模板入口，要求生成真实内容且不得保留空壳或占位符。

## [v1.2.0] - 2026-07-30

### 新增
- 为文件化任务源增加 `Lite`、`Standard`、`Strict` 三档任务配置，按任务风险与复杂度选择，而不是绑定执行主体或调度方式。
- 增加完整状态机、`READY` 门禁、任务卡骨架、状态回退与取消规则，以及严格任务的风险扩展项。

### 改进
- 项目初始化计划必须说明任务文件位置、配置选择理由、首批真实任务和已有文件处理策略。
- 明确 TASKS 只承载活跃任务入口，路线、决策和版本历史分别留在对应文档，避免任务文件持续膨胀。

### 文档完善
- 将原 9 行任务表格说明升级为可按项目裁剪的生成指南，并禁止把项目特定角色、会话或调度机制写入通用模板。
- 将原本会被全局忽略规则排除的 `references/TASKS.md` 迁移为可跟踪、可分发的 `references/task-template.md`。

## [v1.1.2] - 2026-06-12

### Changed
- **Skill 开发项目：** 将默认验收工具从 `skill-architect` 更新为 `skill-lint`，同步 skill 项目 profile 与触发边界说明。

## [v1.1.1] - 2026-06-03

### Changed
- **TASKS.md 模板：** 任务编号从 `#` 改为显式的 `Task-NNN` 格式（`Task-001`、`Task-002` …），跨文档全局唯一。原 `ISS-NNN` 写法不再使用，因多个 Task 常对应同一 Issue/PR，容易造成 1:1 映射的歧义。

## [v1.1.0] - 2026-06-01

### Changed
- **精简项目类型为 4 种：** 开发项目、Skill 开发、法律文档、内容写作；移除前端和数据分析两个 profile
- **开发项目：** 新增 git-workflow、release-workflow、multi-agent-orchestration、cross-agent-coordination、agent-email；移除 skill-lint、repo-research
- **法律文档项目：** 用 legal-ocr 替代 mineru-ocr + paddle-ocr；新增 pdf-processor、pdf-organizer、img2pdf、yuandian-law-search
- **移除 private-skills 和 myagents 技能源**，仅保留 legal-skills

## [v1.0.0] - 2026-05-16

### Added
- **项目类型检测：** 自动识别 6 种项目类型（开发、Skill、前端、数据分析、法律文档、内容写作）
- **配置驱动：** YAML 格式配置文件，支持自定义项目类型、Skill 列表和检测规则
- **Skill 安装：** 委托 skill-manager 处理符号链接创建
- **CLAUDE.md 生成指南：** 6 种项目类型的段落定义、结构模板和脱敏范例（simple / development / frontend / comprehensive-development / data-analysis / skill-project），通过 `@include ~/.claude/CLAUDE.md` 引入全局协议
- **大型项目可选段落：** 架构分层、禁止事项、测试层级、并行调度、实施范围说明等结构模板，按需组装
- **项目文档模板：** ROADMAP.md、DECISIONS.md、TASKS.md、ARCHITECTURE.md、DESIGN.md、CHANGELOG.md，格式对齐全局协议
- **settings 模板：** 权限配置参考模板
- **.gitignore 模板：** 通用 gitignore 模板
- **Skill 项目脚手架：** 目录结构 + SKILL.md 模板 + LICENSE.txt
- **示例配置：** profiles.example.yaml 供其他用户自定义
