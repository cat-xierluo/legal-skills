---
name: git-batch-commit
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.2.0"
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

脚本将：

1. 分析已暂存的文件
2. 按类别分组
3. 显示提议的提交和提交信息
4. 请求确认（使用 `--yes` 可跳过）
5. 创建提交

**命令行参数**：
- `--yes`, `-y`：跳过交互式确认，自动创建提交（适用于 CI/CD 或 AI 助手等非交互式环境）
- `--dry-run`：仅显示分组建议，不实际创建提交

### 方式二：手动分类

```bash
# 查看变更如何被分类
python3 skills/git-batch-commit/scripts/categorize_changes.py

# 或以 JSON 格式输出
python3 skills/git-batch-commit/scripts/categorize_changes.py --json
```

## 提交分类

| 类型 | 描述 | 示例文件 |
|------|-------------| ---------------|
| **docs** | 文档变更 | `*.md`、`README*`、`CHANGELOG*`、`docs/` |
| **feat** | 新功能 | 添加了新内容的源文件 |
| **fix** | Bug 修复 | 包含修复关键字的源文件 |
| **refactor** | 代码重构 | 删除内容多于添加的源文件 |
| **style** | 代码风格 | 格式化或小改动的源文件 |
| **chore** | 依赖和工具 | `package.json`、`Makefile`、`.github/` |
| **license** | License 更新 | `LICENSE`、`LICENSE.txt` |
| **config** | 配置文件 | `*.env.*`、`*.yaml`、`config/` |
| **test** | 测试变更 | `test_*.py`、`*_test.go`、`test/` |

### ⚠️ 技能核心文件的特殊处理

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

所有提交遵循格式：**`<类型>: <描述>`**

使用英文前缀加中文内容，确保 GitHub 能识别并显示彩色标签。

### 单一项目仓库

对于只包含一个项目的仓库：

```text
docs: 更新 README 文档
feat: 添加用户认证功能
fix: 修复解析器内存泄漏
chore: 更新依赖
license: 更新 license 文件
refactor: 简化数据层
config: 更新环境配置
test: 添加解析器单元测试
```

### Multi-Module/Multi-Skill 仓库

对于包含多个独立模块或技能的仓库（如 skills 仓库），**描述中应包含模块名称**以确保聚焦：

```text
docs: course-generator 更新 CHANGELOG
fix: skill-manager 修复符号链接创建位置问题
docs: legal-proposal-generator 优化模板文档
fix: svg-article-illustrator 修复 PNG 导出问题
```

**重要规则**：
- 如果一次修改涉及多个模块，**必须按模块分别提交**
- 每个提交只包含一个模块的变更
- 描述中的模块名称使用原始英文名称，不要翻译

## 工作流程

1. **暂存文件** - 使用 `git add` 正常暂存
2. **运行交互式脚本** - 查看分类结果
3. **审核** - 检查提议的提交分组
4. **确认** - 创建提交或取消以调整
5. **完成** - 获得清晰历史的聚焦提交

## 实现说明

分类使用两遍扫描方法：

1. **文件模式匹配** - 文件按路径和扩展名模式分类
2. **Diff 内容分析** - 对于源代码，分析实际的 git diff 以区分功能、修复、重构和风格变更

检测规则：

- **Fix**: diff 中包含 "fix"、"bug"、"error" 等关键字
- **Feat**: diff 中包含 "add"、"new"、"implement" 等关键字且添加多于删除
- **Refactor**: 删除多于添加
- **Style**: 添加和删除平衡（源文件默认）

## 资源文件

### scripts/

- **`categorize_changes.py`** - 分析 git diff 并按类别分组文件
- **`generate_commit_message.py`** - 生成约定式提交信息
- **`interactive_commit.py`** - 批量提交的主交互式工具

### references/

- **`commit-types.md`** - 详细的类别定义和检测逻辑
- **`conventional-commits.md`** - 提交信息规范

## 使用示例

```bash
$ git add *.py *.md requirements.txt
$ python3 skills/git-batch-commit/scripts/interactive_commit.py

Git 批量提交工具
============================================================
发现 5 个已暂存文件

============================================================
提议的提交分组
============================================================

[分组 1] chore: 更新 Python 依赖
类别: deps
文件 (1):
  - requirements.txt

[分组 2] docs: 更新 README 文档
类别: docs
文件 (1):
  - README.md

[分组 3] feat: 添加新功能
类别: feat
文件 (3):
  - src/parser.py
  - src/utils.py
  - tests/test_parser.py

============================================================

选项:
  y - 是，创建这些提交
  n - 否，取消
  e - 编辑分组（手动模式）

是否继续创建这些提交？ [y/n/e]: y

正在创建提交...

  → chore: 更新 Python 依赖
    ✓ 已提交 1 个文件

  → docs: 更新 README 文档
    ✓ 已提交 1 个文件

  → feat: 添加新功能
    ✓ 已提交 3 个文件

============================================================
批量提交完成：3/3 个提交已创建
============================================================
```

## ClawHub 同步工作流（可选）

完成 Git 提交后，如果满足以下条件，自动触发 ClawHub 同步：

### 触发条件（全部满足才执行）

1. **本地存在 clawhub-sync 技能**
   - 检查 `skills/clawhub-sync/` 目录是否存在

2. **提交涉及 skills 目录**
   - 提交的文件中包含 `skills/<skill-name>/` 下的文件

3. **版本号有更新**
   - 读取 `skills/<skill-name>/SKILL.md` 的 frontmatter 中的 `version` 字段
   - 比较 `skills/clawhub-sync/config/sync-records.yaml` 中记录的版本
   - 如果新版本 > 已记录版本（或记录中无版本），则需要同步

4. **在白名单中**
   - 检查 `skills/clawhub-sync/config/sync-allowlist.yaml`
   - skill 必须在白名单中（未被 `#` 注释）

### 执行步骤

对于每个需要同步的 skill，按照 `clawhub-sync` 的"单个 Skill 同步工作流"执行：

**步骤 1：准备发布目录**
```bash
bash skills/clawhub-sync/scripts/prepare-publish.sh skills/<skill-name>
```

**步骤 2：执行发布（使用 publish 命令）**
```bash
clawhub publish /tmp/clawhub-publish-<skill-name> \
  --slug <skill-name> \
  --version "<新版本号>" \
  --changelog "<变更说明>"
```

> **⚠️ 必须指定 --slug**
> 临时目录名可能包含前缀，使用 `--slug` 确保正确的 skill 标识符。

> **为什么用 `publish` 而不是 `sync`？**
> - `clawhub sync` 会扫描所有目录的 skills，可能遇到 slug 冲突
> - `clawhub publish <path>` 只发布指定路径的单个 skill，更精确

**步骤 3：更新同步记录**

更新 `skills/clawhub-sync/config/sync-records.yaml`：
- 更新 `version` 为新版本号
- 更新 `last_sync` 为当前时间
- 更新 `git_hash` 为当前 commit hash
- 更新 `status` 为 `synced`
- 添加 `url` 和 `publish_id`（从命令输出获取）

### 失败处理

- 同步失败时仅显示警告信息
- 不影响 Git 提交结果
- 继续处理其他 skills

### 版本比较逻辑

```
new_version = SKILL.md frontmatter 中的 version（如 "1.2.0"）
recorded_version = sync-records.yaml 中记录的版本（如 "1.1.0"）

if new_version > recorded_version:
    执行同步
```

版本号按语义化版本规则比较（major.minor.patch）。

### 示例场景

| 场景 | 版本变化 | 白名单 | 结果 |
|------|----------|--------|------|
| 版本升级 | "1.0.0" → "1.1.0" | 在白名单 | ✅ 执行同步 |
| 无版本变化 | "1.1.0" → "1.1.0" | 在白名单 | ❌ 跳过 |
| 不在白名单 | 任意 | 被注释 | ❌ 跳过 |
| 首次发布 | "1.0.0" | 在白名单 | ✅ 执行同步（记录中无版本） |
| clawhub-sync 不存在 | - | - | ❌ 静默跳过整个工作流 |
