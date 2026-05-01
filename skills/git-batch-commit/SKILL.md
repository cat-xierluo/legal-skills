---
name: git-batch-commit
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.3.0"
license: MIT
description: 智能 Git 批量提交工具。当用户说 "git 提交"、"git commit"、"批量提交"、"拆分提交"、"整理提交" 时使用，或者当用户暂存了多个不同类型的文件需要分开提交时使用。自动将混合的文件修改按类型分类（依赖管理、文档更新、license 文件、配置、源代码等），并创建多个清晰聚焦的提交，使用标准化的提交信息格式。帮助保持清晰的 Git 历史，确保每个提交都有单一、明确的目的。使用英文前缀（docs:、feat:、fix: 等）加中文内容，支持 GitHub 彩色标签显示。
---

# Git 批量提交工具

## 概述

将混合的修改自动拆分为多个聚焦的、逻辑清晰的提交。而不是创建一个包含"更新各种文件"的大提交，而是创建多个清晰的提交，如"docs: 更新 README"、"chore: 更新依赖"、"license: 更新 license 文件"。

## 使用场景

- 用户暂存的文件来自多个类别（文档 + 代码 + 配置）
- 用户希望保持清晰、标准化的提交历史
- 用户提到"批量提交"、"拆分提交"或"整理提交"
- 用户修改了许多文件，希望按逻辑分组

## 快速开始

### 方式一：使用交互式脚本

```bash
# 首先暂存你的文件
git add file1.py file2.md package.json

# 运行交互式批量提交工具（需要确认）
python3 skills/git-batch-commit/scripts/interactive_commit.py

# 或使用 --yes 参数自动确认（适用于非交互式环境）
python3 skills/git-batch-commit/scripts/interactive_commit.py --yes

# 使用 --dry-run 仅查看分组，不实际提交
python3 skills/git-batch-commit/scripts/interactive_commit.py --dry-run
```

**命令行参数**：
- `--yes`, `-y`：跳过交互式确认，自动创建提交
- `--dry-run`：仅显示分组建议，不实际创建提交

### 方式二：手动分类

```bash
python3 skills/git-batch-commit/scripts/categorize_changes.py
python3 skills/git-batch-commit/scripts/categorize_changes.py --json
```

## 提交分类

支持类型：**docs**, **feat**, **fix**, **refactor**, **style**, **chore**, **license**, **config**, **test**

完整定义和检测逻辑详见 `references/commit-types.md`

### 技能核心文件的特殊处理

**重要规则**：`SKILL.md` 虽然是 Markdown 格式，但它是**技能的核心功能文件**，不应归类为 `docs` 类型。

| 文件类型 | 正确分类 | 理由 |
|:---------|:---------|:-----|
| `SKILL.md` | `feat`/`style`/`fix` | 技能核心文件，修改它相当于修改功能/代码 |
| `AGENTS.md` | `docs` | 项目协作规范，属于文档 |
| `DECISIONS.md` | `docs` | 决策记录，属于文档 |
| `CHANGELOG.md` | `docs` | 变更日志，属于文档 |
| `TASKS.md` | `docs` | 任务列表，属于文档 |

**判断依据**：
- 如果修改的是**定义行为/功能**的文件（如 `SKILL.md`、`.py`、`.ts`），视为代码变更
- 如果修改的是**记录/说明**性质的文件（如 `README.md`、`CHANGELOG.md`），视为文档变更

## 提交信息格式

所有提交遵循格式：

```text
<类型>: <标题>

<正文描述>
```

**重要规则：每个提交必须包含正文（body），不能只有标题。** 正文用于补充变更的具体内容和原因，方便后续追溯。

使用英文前缀加中文内容，确保 GitHub 能识别并显示彩色标签。完整示例见 `references/conventional-commits.md`

**Multi-Module/Multi-Skill 仓库规则**：
- 描述中应包含模块名称：`docs: course-generator 更新 CHANGELOG`
- 如果一次修改涉及多个模块，**必须按模块分别提交**
- 描述中的模块名称使用原始英文名称，不要翻译

## 工作流程

1. **暂存文件** - 使用 `git add` 正常暂存
2. **运行交互式脚本** - 查看分类结果
3. **审核** - 检查提议的提交分组
4. **确认** - 创建提交或取消以调整
5. **ClawHub 同步检查** - 仅当 `skills/clawhub-sync/` 存在时执行，详见 `references/clawhub-sync-check.md`。不存在则静默跳过
6. **Subtree 推送检查** - 仅当 `skills/subtree-publish/config/subtree-skills.json` 存在时执行，详见 `references/subtree-push-check.md`。不存在则静默跳过
7. **完成** - 获得清晰历史的聚焦提交

## 资源文件

### scripts/

- **`categorize_changes.py`** - 分析 git diff 并按类别分组文件
- **`generate_commit_message.py`** - 生成约定式提交信息
- **`interactive_commit.py`** - 批量提交的主交互式工具

### references/

- **`commit-types.md`** - 详细的类别定义和检测逻辑
- **`conventional-commits.md`** - 提交信息规范
- **`issue-pr-format.md`** - Issue 与 PR 命名规范
- **`clawhub-sync-check.md`** - ClawHub 同步检查详细流程（工作流第5步）
- **`subtree-push-check.md`** - Subtree 推送检查详细流程（工作流第6步）
