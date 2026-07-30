---
name: project-init
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.2.1"
license: MIT License - 详见 LICENSE.txt
description: |
  项目初始化工具。读取全局协议 ~/.claude/CLAUDE.md，分析项目实际情况，生成项目特定的 CLAUDE.md 和 docs/ 上下文。本技能应在用户说"初始化项目"、"项目设置"、"配置 Claude Code"、"新建项目配置"时使用，或在进入一个新项目需要快速配置时使用。不要用于：Skill 内容开发或验收（用 skill-lint）、单次 Skill 安装（用 skill-manager）、代码生成。
---

# Project Init

读取全局协议，分析项目，生成上下文。

## 工作流程

### Step 1: 读取全局协议

读取 `~/.claude/CLAUDE.md`（及其 `@include` 引用的文件），理解全局协作协议。这是生成项目上下文的基准——项目文档的格式和结构应对齐全局协议中的定义（如文档体系、SOP、DECISIONS 格式等）。

### Step 2: 读取配置

读取本 skill 目录下的 `config/profiles.yaml`，获取：
- `skill_sources`: Skill 源仓库路径
- `profiles`: 各项目类型的检测规则和 Skill 列表

### Step 3: 检测项目类型

1. 调用 `scripts/init.sh detect <project_dir>` 获取指示文件列表。
2. 按配置中 profiles 的定义顺序评估 `detect` 规则：
   - `any_of`: 任一文件存在即匹配
   - `has_skill_md`: 根目录或 `skills/` 子目录下存在 SKILL.md
   - `extensions`: 指定扩展名文件数 >= `min_count`
   - `dir_patterns`: 任一目录名存在即匹配
3. 第一个命中的 profile 即为检测结果。未命中则使用 `default_profile`。

### Step 4: 分析项目

**在生成任何文件之前，先分析项目实际情况：**

- 读取 `package.json` / `pyproject.toml` / `Cargo.toml` 等获取技术栈
- 扫描目录结构了解项目架构（`src/`、`app/`、`lib/` 等）
- 读取已有的 README.md 或代码了解项目用途
- 检查是否已有 `.claude/`、`CLAUDE.md`、`docs/` 等

将这些信息汇总，作为后续生成上下文的素材。

### Step 5: 展示计划并确认

向用户展示检测结果和生成计划，**必须等待确认**。若计划使用文件化任务源，同时说明：

- 任务文件的名称与位置；
- 根据风险与复杂度选择的 `Lite`、`Standard` 或 `Strict` 配置及理由；
- 将写入的首批真实任务，以及已有任务文件的合并或跳过策略。

### Step 6: 创建 .claude/ 和安装 Skill

```bash
mkdir -p .claude/skills/
```

对 profile 中 `skills` 字段列出的每个 Skill，通过调用 skill-manager Skill 以符号链接方式安装到项目的 `.claude/skills/` 目录。skill-manager 会自动处理路径解析、去重和版本追踪。

### Step 7: 生成 AGENTS.md 和 CLAUDE.md

**不是复制模板，而是基于全局协议 + 项目分析结果生成项目特定的 AGENTS.md。**

参考 `templates/agents.md` 中各项目类型的结构模板和生成指南，结合 Step 4 的分析结果，生成包含真实项目信息的内容，写入 `AGENTS.md`。

`templates/agents.md` 包含所有项目类型的段落定义、结构模板和脱敏范例，无需参考其他外部文件。

`CLAUDE.md` 不重复写内容，仅写入：
```
@include ./AGENTS.md
```

这样 Claude Code 和 Codex 共享同一份项目协议，只维护一个源文件。

已有 `AGENTS.md` 时展示 diff，让用户决定覆盖/合并/跳过。已有 `CLAUDE.md` 但内容不是纯 `@include` 时，同样展示 diff。

### Step 8: 生成 settings.json

将 `assets/claude-settings-template.json` 原样复制为项目 `.claude/settings.json`。已有则跳过。

### Step 9: 创建 .codex/ 目录

```bash
bash scripts/init.sh codex "<project_dir>"
```

创建 `.codex/` 目录结构：

- `config.toml`：从 `assets/codex-config.toml` 复制
- `rules/default.rules`：从 `assets/codex-default.rules` 复制
- `skills`：符号链接 → `../.claude/skills`（与 `.claude/skills/` 共享，不重复安装）

已有则跳过。`.codex/skills` 软链确保 Codex 能直接访问 `.claude/skills/` 中已安装的 Skill。

### Step 10: 生成 docs/ 文档

**不是复制空模板，而是基于全局协议的文档体系定义 + 项目分析结果生成有实际内容的文档。**

按需读取对应文档模板，结合项目选择的协作文档体系生成真实初始内容；不要复制空壳或保留占位符：

- **docs/ROADMAP.md**: 读取 `templates/roadmap.md`，从 README、版本和当前实现提取愿景、状态与阶段规划
- **docs/DECISIONS.md**: 读取 `templates/decision-log.md`，记录真实存在的初始化决策和工作日志，不虚构备选方案
- **任务清单文件**: 仅当项目选择文件化任务源时创建；读取 `templates/task-template.md`，根据项目风险选择一个任务配置，生成真实队列与任务卡。不要逐字复制生成指南，也不要生成与所选配置无关的空章节。文件名和位置由项目上下文决定
- **docs/ARCHITECTURE.md**: 读取 `templates/architecture.md`，从目录结构、入口和技术栈生成初始架构描述
- **DESIGN.md**: 仅包含前端的项目读取 `templates/design.md`，结合实际设计系统和技术栈生成
- **CHANGELOG.md**: 项目需要变更日志且文件不存在时读取 `templates/changelog.md`，使用明确版本号和日期生成初始化记录

任务文件只作为当前任务入口：长期方向留在 ROADMAP，重要取舍留在 DECISIONS，用户可见历史留在 CHANGELOG。仅创建不存在的文件；已有任务文件时展示 diff，由用户决定合并或跳过，不直接覆盖。

### Step 11: 创建 .gitignore

将 `assets/gitignore-template` 原样复制为项目 `.gitignore`。已有则跳过。

### Step 12: Skill 脚手架（仅 skill-project 类型）

```bash
bash scripts/init.sh scaffold "<project_dir>" "<skill_name>"
```

创建 `references/`、`scripts/`、`assets/`、`SKILL.md`、`LICENSE.txt`。

## 配置说明

编辑 `config/profiles.yaml` 自定义。

## 资源目录

- `templates/`：读取后结合项目事实选择、裁剪和填充；不得原样复制，也不得保留占位符。
- `assets/`：不需要载入上下文，按步骤或脚本原样复制到目标位置；已有目标文件时遵循幂等规则。
- 新增资源时按消费方式归类，不按文件扩展名归类。同为文本文件，需理解后生成的进入 `templates/`，固定内容进入 `assets/`。

## 幂等性

符号链接相同目标 → 跳过；文件已存在 → 不覆盖。
