# Changelog

All notable changes to this skill will be documented in this file.

## [v1.7.0] - 2026-04-23

### 新增

- 新增 `config/readme-profile.example.json`，用于定义独立仓库 README 的作者入口、二维码、上游项目导流和相关项目推荐字段
- 支持通过本地 `config/readme-profile.json` 或 `SUBTREE_README_*` 环境变量提供 README 个性化信息

### 改进

- README 模板改为从 profile 配置读取作者展示名、联系文案、二维码图片、上游项目和相关项目推荐
- Release 打包排除非 example 的 `config/*.json`，避免本地个性化配置进入公开发布包，同时保留 `*.example.json`

### 文档完善

- 更新 `SKILL.md`、`TASKS.md` 与 `DECISIONS.md`，说明 README profile 的读取优先级、字段结构和发布规则

## [v1.6.0] - 2026-04-22

### 改进

- 强化独立仓库 README 写作要求：从栏目模板升级为首屏价值、真实提问、安装依赖、产物预期、边界责任、可信度支撑和许可证一致性的质量验收标准
- 更新 `references/readme-template.md`，增加依赖/API Key 就近说明、CC BY-NC 商用授权提示和发布前检查清单
- 明确已注册独立仓库 README 应按 skill 复杂度选择 `minimal` / `standard` / `showcase` profile，而不是机械套用固定长模板
- 调整“关联项目”规范：README 应面向最终用户推荐上游项目、相关 skill 或作者入口，不再输出 monorepo/subtree 内部同步说明
- README 模板保持通用占位符，不硬编码特定作者二维码或特定项目推广文案

### 文档完善

- 更新 `TASKS.md` 与 `DECISIONS.md`，记录 README 规范升级的背景、理由和影响范围

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
