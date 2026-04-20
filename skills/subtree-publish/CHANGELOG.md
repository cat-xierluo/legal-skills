# Changelog

All notable changes to this skill will be documented in this file.

## [v1.5.0] - 2026-04-19

### 新增

- README 模板升级为“固定骨架 + 可选叙事模块”的结构，支持 `minimal` / `standard` / `showcase` 三种复杂度 profile
- README 写作原则：结果优先、示例优先、边界清晰、安装简单
- 首次注册流程新增 README 创建规则，要求根据 skill 复杂度选择合适展开层级

### 修改

- `references/readme-template.md` 从轻量固定模板改为面向独立 GitHub 仓库的人类展示模板
- `SKILL.md` 中明确 README.md 是独立仓库展示页，不属于 skill runtime 文件

## [v1.4.0] - 2026-04-19

### 新增

- Release 创建规则：每次 subtree push 后自动检查 SKILL.md 版本号，如无对应 tag 则创建 GitHub Release
- Release 附加 zip 压缩包（排除 README.md 和 .DS_Store），用户下载后可直接放入 `.claude/skills/` 使用
- README.md 是面向独立仓库浏览者的展示文件，不属于 skill 运行所需，不纳入压缩包
- 新增 `scripts/create-release.sh` 脚本，自动化 Release 创建流程
- Release Notes 优先从 CHANGELOG.md 提取，无则使用默认文本
- 首次注册流程新增 Step 7：创建首个 Release
- 仓库名默认规则：独立仓库名默认为 `<name>.skill`

### 修改

- 配置文件引用改为指向实际文件和 example 文件，移除内联 JSON 示例
- 版本跃迁说明：支持非连续版本号（如 1.2.0 → 1.2.2），只为当前推送的版本创建 Release

## [v1.3.0] - 2026-04-19

### 新增

- 首次注册流程新增 Step 2 前置校验：推送前必须检查子目录是否存在 README.md，不存在则必须先创建

### 修复

- 修正首次注册流程中 Step 编号重复的问题（原文有两个 Step 3 和重复的 gh repo create 命令）

## [v1.2.0] - 2026-04-19

### 修改
- 配置文件从 TXT 格式迁移到 JSON 格式（`config/subtree-skills.json`）
- 支持子目录名与 GitHub 仓库名的映射（如 `opc-legal-counsel` → `opc-legal-counsel.skill`）
- 脚本从 JSON 配置中读取 `org` 和 `prefix`，不再硬编码
- SKILL.md 措辞通用化，去除 legal-skills 特定引用

## [v1.1.0] - 2026-04-19

### 新增
- `--auto` 模式：自动检测最近 commit 涉及的子项目并推送
- `config/subtree-skills.txt` 注册清单

### 修改
- SKILL.md 中添加已注册子项目清单表格

## [v1.0.0] - 2026-04-19

### 新增
- 初始版本：支持单子项目推送（`--setup`、`--dry-run`）
- 自动创建 GitHub 仓库
- 自动添加 git remote
