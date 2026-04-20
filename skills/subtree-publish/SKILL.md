---
name: subtree-publish
author: 杨卫薪律师（微信 ywxlaw）
version: "1.5.0"
license: MIT
description: 将 monorepo 中的子目录通过 git subtree 推送到独立 GitHub 仓库。支持注册清单、变更自动检测、增量推送。本技能应在用户提交涉及已注册子项目的变更后，或手动请求推送到独立仓库时使用。不要用于初次创建 monorepo 或管理 git submodule。
---

# Subtree Publish

将 monorepo 中指定子目录通过 `git subtree push` 推送到独立 GitHub 仓库。

文件只存一份（在 monorepo 中），一条命令同步到独立仓库。

## 前置条件

- 当前工作目录是 monorepo 根目录
- 子目录位于 `<prefix>/<name>/`
- 已安装上述依赖（git subtree、gh、jq）

## 依赖

### 系统依赖

| 依赖 | 用途 | 安装方式 |
|------|------|----------|
| git（含 subtree） | 子目录拆分与推送 | macOS: 已预装 |
| gh | GitHub CLI，创建仓库和认证 | macOS: `brew install gh` |
| jq | JSON 配置解析 | macOS: `brew install jq` |

## 使用方式

### 1. 自动检测并推送（推荐）

当用户完成一次 git commit 后，如果本次提交涉及清单中的子项目：

```bash
bash scripts/subtree-push.sh --auto
```

脚本会检查最近一次 commit 涉及的文件，如果命中清单中的子目录，自动推送到对应独立仓库。

**触发时机：** 用户说"提交完了"、"帮我推到独立仓库"、"同步 subtree"时，先检查是否有清单中的子项目被修改。

### 2. 首次注册新子项目

当用户说"注册 subtree"、"新增独立仓库发布"时：

**Step 1: 确认子目录存在**

```bash
ls <prefix>/<name>/SKILL.md
```

**Step 2: 前置校验 — 检查 README.md**

在执行任何远程操作之前，必须先检查子目录中是否已存在 `README.md`：

```bash
ls <prefix>/<name>/README.md
```

- **如果不存在**：必须先创建 README.md，才能继续后续步骤。不得跳过。创建时参照 `references/readme-template.md` 模板。
- **如果已存在**：跳过创建，继续下一步。

README.md 是独立 GitHub 仓库的人类展示页，不是 skill runtime 文件。创建时必须遵守：

- **固定骨架，不固定叙事**：必须回答“给谁用、解决什么、典型场景、能产出什么、如何安装、使用边界、许可证、作者、关联项目”，但可以根据 skill 复杂度增删扩展模块。
- **结果优先**：优先说明 skill 帮用户完成什么结果，不要把 README 写成 `SKILL.md`、frontmatter 或目录结构说明。
- **示例优先**：尽早给一个真实用户提问和 AI 介入方式，让访客能快速理解用途。
- **边界清晰**：必须说明适合什么、不适合什么，尤其是法律、专利、合规等高风险 skill。
- **按复杂度选择 profile**：
  - `minimal`：简单工具型 skill，只保留核心骨架。
  - `standard`：大多数公开 skill，增加目标用户和覆盖范围。
  - `showcase`：重点推广或复杂 skill，增加问题背景、核心设计、示例输出、项目结构和质量支撑。

**Step 3: 创建独立 GitHub 仓库**（如果需要首次设置）

```bash
gh repo create <org>/<repo-name> --public --description "<描述>"
```

**Step 4: 添加 remote**

```bash
git remote add <name>-standalone https://github.com/<org>/<repo-name>.git
```

**Step 5: 首次推送**

```bash
git subtree push --prefix=<prefix>/<name> <name>-standalone main
```

**Step 6: 注册到清单**

将子项目信息加入 `config/subtree-skills.json`，并更新上面的清单表格。

**Step 7: 创建首个 Release**

首次推送后，运行脚本创建 GitHub Release：

```bash
bash scripts/create-release.sh <name>
```

### 3. 手动推送单个子项目

```bash
bash scripts/subtree-push.sh <name> [--setup] [--dry-run]
```

- `--setup`: 同时创建 GitHub 仓库和添加 remote
- `--dry-run`: 只显示将要执行的操作，不实际推送

## Remote 命名规则

独立仓库的 remote 名称统一为 `<name>-standalone`。

## Release 创建规则

每次 subtree push 后，自动检查是否需要创建 GitHub Release。

### 触发条件

1. 读取 `<prefix>/<name>/SKILL.md` 中的 `version` 字段，获取当前版本号
2. 通过 `gh release list --repo <org>/<repo-name> --limit 1` 检查最新 Release 的 tag
3. 如果当前版本号对应的 `v<version>` tag 尚不存在，则创建 Release
4. 如果已存在相同版本的 Release，跳过

### 执行步骤

```bash
bash scripts/create-release.sh <name> [--dry-run]
```

脚本会自动完成：读取版本号 → 检查已有 Release → 提取 CHANGELOG → 打包（排除 README.md 和 .DS_Store）→ 创建 Release。

### Release Notes 来源

- 优先从 `<prefix>/<name>/CHANGELOG.md` 提取对应版本的变更记录
- 如果 CHANGELOG.md 不存在或无对应版本，使用默认文本：`"发布 v<version>"`

### 压缩包内容

压缩包解压后得到 `<name>/` 文件夹（如 `code2patent/`），用户直接放入 `.claude/skills/` 即可使用。排除 `README.md` 和 `.DS_Store`。

README.md 面向独立仓库浏览者（GitHub 页面展示），不属于 skill 运行所需文件，因此不纳入压缩包。

### 版本跃迁

支持非连续版本号（如 `1.2.0` → `1.2.2`，跳过 `1.2.1`）。每次只为当前推送的版本创建 Release，不会补建中间版本的 Release。

## 注意事项

- 不要在独立仓库中直接修改文件，所有修改都应在 monorepo 中进行
- `git subtree push` 在大仓库上可能较慢，这是正常的
- 独立仓库中的文件位于根目录（不是嵌套的子目录）
- Git subtree 只推送已 commit 的文件，受 monorepo 根目录 `.gitignore` 控制

## 配置文件

### config/subtree-skills.json

实际配置文件位于 `config/subtree-skills.json`，用于 `--auto` 模式检测和仓库名映射。如需新建配置，可参考 `config/subtree-skills.example.json`。

字段说明：

- `prefix`: 子目录前缀（相对于 monorepo 根目录）
- `org`: GitHub 组织/用户名
- `skills`: 子项目数组
  - `name`: 子目录名称（必填）
  - `repo`: 独立仓库名（可选，默认为 `<name>.skill`）
  - `version`: 当前 SKILL.md 中的版本号（可选，用于核查是否需要发布新 Release）
  - `last_release`: 最新已发布的 Release tag（可选，如 `v1.0.0`）
  - `last_updated`: 最近一次 subtree push 或 Release 更新时间（可选，格式 `YYYY-MM-DDTHH:MM:SS`）

## 仓库名默认规则

独立仓库名默认在子目录名后追加 `.skill` 后缀。例如：

- `opc-legal-counsel` → `opc-legal-counsel.skill`
- `code2patent` → `code2patent.skill`

用户可以在 `config/subtree-skills.json` 中通过 `repo` 字段显式指定不同的仓库名，但如果不指定则自动使用 `<name>.skill`。

## 脚本

### scripts/subtree-push.sh

自动化 subtree 推送流程，支持 `--auto` 变更检测和仓庝名映射。

### scripts/create-release.sh

自动化 GitHub Release 创建流程。用法：`bash scripts/create-release.sh <name> [--dry-run]`

脚本自动完成：读取 SKILL.md 版本号 → 检查已有 Release → 提取 CHANGELOG 作为 Release Notes → 打包（排除 README.md 和 .DS_Store，解压后得到 `<name>/` 文件夹）→ 创建 Release 并附上压缩包。
