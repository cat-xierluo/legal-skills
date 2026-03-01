# Changelog

All notable changes to this skill will be documented in this file.

## [v1.3.0] - 2026-03-01

### 新增

- **skill-standards.md 与 skill-lint/checklist.md 统一**：两个文件现在完全一致，方便维护

### 修改

- references/skill-standards.md 重构为混合格式（检查项 + 状态 + 说明）
- 新增 §4 目录层级检查（扁平结构要求）
- 新增 §16 审查报告模板
- 审查摘要新增 SKILL.md 行数、目录层级检查项

## [v1.2.0] - 2026-03-01

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

## [v1.1.0] - 2026-02-28

### 新增

- **模块化设计检查**（§2）：独立功能解耦、跨 skill 协调规范
- **安全审计检查**（§12）：禁止危险删除命令、API keys 硬编码检查
- 同步 SKILL-DEV-GUIDE.md 至 v2.2.0
- 同步 SKILL-ORCHESTRATION-GUIDE.md 至 v2.0.0

### 修改

- 合规检查清单新增 5.6 模块化设计、5.7 安全审计
- 审查模式检查清单新增 10. 模块化设计检查、11. 安全审计检查
- skill-standards.md 章节编号调整（§2→模块化设计，§12→安全审计）

## [v1.0.1] - 2026-02-28

### 新增

- 审查模式：支持审查现有技能的合规性
- 生成结构化审查报告
- 两种使用模式：

  1. **创建模式** - 创建新技能时遵循规范
  2. **审查模式** - 审查现有技能并生成报告

## [v1.0.0] - 2026-02-28

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
