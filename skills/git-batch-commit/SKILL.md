---
name: git-batch-commit
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.4.1"
license: MIT
description: '智能 Git 批量提交快捷按钮。触发词："git 提交"、"批量提交"、"拆分提交"、"整理提交"，或用户明确要把已暂存变更拆成多个聚焦 commit 时使用。只负责 commit 拆分和提交信息生成；分支、PR、push、merge、Issue 关闭语义以 git-workflow 为准。'
---

# Git 批量提交工具

## 概述

将混合的修改自动拆分为多个聚焦的、逻辑清晰的提交。而不是创建一个包含"更新各种文件"的大提交，而是创建多个清晰的提交，如"docs: 更新 README"、"chore: 更新依赖"、"license: 更新 license 文件"。

## 与 git-workflow 的职责边界

`git-batch-commit` 是提交拆分工具，不是完整 Git 工作流控制器。

| 场景 | 使用哪个 Skill | 说明 |
|------|---------------|------|
| 将已暂存的混合变更拆成多个 commit | `git-batch-commit` | 本 Skill 的核心职责 |
| 判断是否能 merge / push / close PR | `git-workflow` | 本 Skill 不做合并门禁 |
| PR 合入 main 的 commit 标题是否带 `(#N)` | `git-workflow` | 本 Skill 只在生成普通 commit 时保留 Issue/Task 引用 |
| 直接解决 GitHub Issue 是否应写 `Closes #N` | `git-workflow` | 本 Skill 只写 `Refs #N`，不关闭 Issue |
| 项目本地任务引用 | `cross-agent-collab` 定任务来源，`git-batch-commit` 写引用 | 使用 `--local-ref "project-task Issue #13"` |

当用户只是说“把这些改动提交一下 / 拆分提交”，使用本 Skill；当用户说“合并 PR / 拉 PR 到 main / 推送 / 关闭 issue”，同时遵循 `git-workflow`。

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

# 这组提交关联 GitHub Issue #13：每个标题追加 (#13)，正文写 Refs #13
python3 skills/git-batch-commit/scripts/interactive_commit.py --issue 13

# 这组提交关联项目本地任务，不误关 GitHub Issue
python3 skills/git-batch-commit/scripts/interactive_commit.py --local-ref "project-task Issue #13"
```

**命令行参数**：
- `--yes`, `-y`：跳过交互式确认，自动创建提交
- `--dry-run`：仅显示分组建议，不实际创建提交
- `--issue N`：关联 GitHub Issue，提交标题追加 `(#N)`，正文写 `Refs #N`
- `--local-ref "..."`：关联项目本地任务，如 `project-task Issue #13`，只写 `Refs: ...`，不会关闭 GitHub Issue

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

### 同 Skill 内伴随变更合并规则

**核心原则**：同一 Skill 内的功能变更及其直接关联的配套文件更新，应合并为一条提交，不要按文件类型拆分。

具体规则：
- 当 `SKILL.md` 有功能变更（feat/fix/style），同 Skill 下的 `CHANGELOG.md` 更新应**合并进同一条提交**，不单独拆出 `docs` 提交
- 同理，版本号变更、配置微调（如删除 `.clawhubignore`）等配套小改动也一并合并
- 判断标准：这些文件变动是否由**同一个功能变更**引起？如果是，就是一条提交
- 只有当 CHANGELOG 独立更新（如补录历史版本）且无对应功能变更时，才单独使用 `docs` 类型

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

**Issue / Task 引用规则**：
- 若一组批量提交关联 GitHub Issue，使用 `--issue N`。每个提交标题会包含 `(#N)`，正文写 `Refs #N`。
- 本 Skill 不生成 `Closes #N`。是否关闭 GitHub Issue 属于 `git-workflow` 的判断范围。
- 若编号来自项目本地任务源而非 GitHub Issue，使用 `--local-ref "project-task Issue #N"` 或项目约定的等价引用，不要写 `Closes #N`。
- PR 合并提交的 `(#PR编号)` 规则不由本 Skill 决定，遵循 `git-workflow`。

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
- **`clawhub-sync-check.md`** - ClawHub 同步检查详细流程（工作流第5步）
- **`subtree-push-check.md`** - Subtree 推送检查详细流程（工作流第6步）
