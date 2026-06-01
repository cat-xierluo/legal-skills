---
name: project-init
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
license: MIT License - 详见 LICENSE.txt
description: |
  项目初始化工具。读取全局协议 ~/.claude/CLAUDE.md，分析项目实际情况，生成项目特定的 CLAUDE.md 和 docs/ 上下文。本技能应在用户说"初始化项目"、"项目设置"、"配置 Claude Code"、"新建项目配置"时使用，或在进入一个新项目需要快速配置时使用。不要用于：Skill 内容开发（用 skill-architect）、单次 Skill 安装（用 skill-manager）、代码生成。
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

向用户展示检测结果和生成计划，**必须等待确认**。

### Step 6: 创建 .claude/ 和安装 Skill

```bash
mkdir -p .claude/skills/
```

对 profile 中 `skills` 字段列出的每个 Skill，通过调用 skill-manager Skill 以符号链接方式安装到项目的 `.claude/skills/` 目录。skill-manager 会自动处理路径解析、去重和版本追踪。

### Step 7: 生成 CLAUDE.md

**不是复制模板，而是基于全局协议 + 项目分析结果生成项目特定的 CLAUDE.md。**

参考 `references/CLAUDE.md` 中各项目类型的结构指南和生成范例，结合 Step 4 的分析结果，生成包含真实项目信息的内容。

`references/CLAUDE.md` 包含所有项目类型的段落定义、结构模板和脱敏范例，无需参考其他外部文件。

已有 `CLAUDE.md` 时展示 diff，让用户决定覆盖/合并/跳过。

### Step 8: 生成 settings.json

直接复制 `references/settings-template.json`。已有则跳过。

### Step 9: 生成 docs/ 文档

**不是复制空模板，而是基于全局协议的文档体系定义 + 项目分析结果生成有实际内容的文档。**

参考 `references/CLAUDE.md` 中各项目类型的段落定义，结合项目选择的协作文档体系，生成包含项目初始信息的文档：

- **docs/ROADMAP.md**: 项目愿景（从 README/package.json 提取）、初始阶段规划
- **docs/DECISIONS.md**: 第一条决策记录（项目初始化的技术选型）
- **任务清单文件**: 仅当项目选择文件化任务源时创建；文件名和格式由项目上下文决定
- **docs/ARCHITECTURE.md**: 从目录结构和技术栈生成初始架构描述
- **DESIGN.md**: 仅包含前端的项目，从 `references/DESIGN.md` 了解九段式结构，结合实际技术栈生成

仅创建不存在的文件。

### Step 10: 创建 .gitignore

从 `references/.gitignore` 复制。已有则跳过。

### Step 11: Skill 脚手架（仅 skill-project 类型）

```bash
bash scripts/init.sh scaffold "<project_dir>" "<skill_name>"
```

创建 `references/`、`scripts/`、`assets/`、`SKILL.md`、`LICENSE.txt`。

## 配置说明

编辑 `config/profiles.yaml` 自定义。

## 幂等性

符号链接相同目标 → 跳过；文件已存在 → 不覆盖。
