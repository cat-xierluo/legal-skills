# Changelog

All notable changes to this skill will be documented in this file.

## [v1.3.0] - 2026-03-01

### 新增

- **skill-standards.md 统一**：与 skill-architect 使用相同的规范文件

### 修改

- 重命名 `references/checklist.md` → `references/skill-standards.md`
- 重构为 16 节结构
- 新增 §4 目录层级检查（扁平结构要求）
- 新增 §16 审查报告模板
- 审查摘要新增 SKILL.md 行数、目录层级检查项

## [v1.2.0] - 2026-03-01

### 新增

- **负向触发条件检查**：description 中需包含"不要用于"说明
- **SKILL.md 行数检查**（§4）：限制 ≤ 500 行
- **目录层级检查**（§5）：references/scripts/assets 扁平结构
- **description 长度检查**：≤ 1024 字符（原 100 字符）
- 同步 SKILL-DEV-GUIDE.md 至 v2.3.0

### 修改

- 审查报告模板更新：新增行数和目录层级检查项
- 章节编号调整：§4→SKILL.md 行数，§5→目录层级，§6-§16 顺延
- 修复重复章节编号问题（原 §11、§12 各有两个）

## [v1.1.0] - 2026-02-28

### 新增

- **模块化设计检查**（§7）：独立功能解耦、跨 skill 协调规范
- **安全审计检查**（§8）：禁止危险删除命令、API keys 硬编码检查
- 同步 SKILL-DEV-GUIDE.md 至 v2.2.0

### 修改

- 审查清单新增 §7 模块化设计检查、§8 安全审计检查
- 审查报告模板新增模块化设计和安全审计检查行
- 章节编号调整：原 §7-§13 顺延为 §9-§15

## [v1.0.0] - 2026-02-28

### 新增

- 初始版本发布
- 基于 SKILL-DEV-GUIDE.md 规范的 12 类合规检查规则
- 支持生成结构化审查报告
