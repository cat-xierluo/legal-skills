---
name: subtree-publish
author: 杨卫薪律师（微信 ywxlaw）
version: "1.7.0"
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

README.md 是独立 GitHub 仓库的人类展示页，不是 skill runtime 文件。创建或重写时必须遵守：

- **首屏讲清结果**：标题、首段和引用句必须让访客在 30 秒内知道“这个 skill 帮谁，在什么场景下，产出什么”。不要先讲 frontmatter、目录结构或内部实现。
- **真实提问开场**：在前半部分放一个真实用户提问和 AI 介入方式，优先展示“怎么用”，而不是罗列功能。
- **安装路径可执行**：必须包含 GitHub Releases 下载、解压到 skill 目录、启用环境这三步；如需 Python/CLI/API Key 等依赖，必须就近写出安装或配置命令。
- **产物可预期**：用清单说明会产出哪些文件、报告、表格、批注、检索结果或行动清单；避免只写“提高效率”“智能分析”等空泛词。
- **边界与责任清楚**：必须分别说明适合与不适合的场景。法律、专利、商标、合规类 skill 必须写明“不替代正式法律意见/代理判断/注册成功承诺”等边界。
- **可信度有支撑**：复杂或重点推广 skill 应说明方法框架、覆盖范围、关键文件、评测/示例/脚本等质量支撑，但不要把 README 写成完整技术文档。
- **许可证一致**：README 的许可证类型必须与 `SKILL.md` frontmatter 和 `LICENSE.txt` 保持一致；CC BY-NC 类 skill 应提示商用授权联系方式以 `LICENSE.txt` 为准。
- **外部导流收尾**：底部应说明本仓库所属的上游项目或技能集合，并推荐相关项目、主仓库或作者联系方式。不要把“所有修改在 monorepo 中进行”“通过 git subtree 同步”这类内部维护机制写给最终用户。

如需统一作者信息、二维码、主仓库链接或相关项目推荐，先读取 `config/readme-profile.json`；该文件为本地个性化配置，默认不提交。没有本地配置时，参考 `config/readme-profile.example.json` 的字段结构，并用通用占位符生成 README。

写作前按复杂度选择 profile：

- `minimal`：简单工具型 skill。保留“典型场景 / 能产出什么 / 安装方式 / 使用边界 / 许可证 / 作者 / 关联项目”。
- `standard`：大多数公开 skill。在 minimal 基础上增加“适合谁用 / 当前覆盖范围 / 常见用法”。
- `showcase`：重点推广、复杂法律或高风险 skill。在 standard 基础上增加“项目解决什么问题 / 核心设计 / 示例输出 / 质量支撑 / 关键文件”。

发布前用以下检查清单复核 README：

1. 首屏是否能直接判断目标用户、核心场景和输出结果？
2. 是否有真实用户提问示例，而不是只有功能列表？
3. 安装步骤是否足以让外部用户开始试用？
4. 是否写明适合/不适合，且高风险场景有免责声明？
5. 许可证、作者、关联项目是否与当前 skill 元数据一致？
6. 是否删除了模板占位符、内部维护口吻和过长目录树？

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

### config/readme-profile.json（可选）

本地 README 个性化配置。用于统一生成独立仓库 README 的作者入口、二维码、上游项目导流和相关项目推荐。该文件通常包含个人或项目特定信息，应保留在本地；发布包和版本库只保留 `config/readme-profile.example.json`。

读取优先级：

1. 环境变量（临时覆盖）
2. `config/readme-profile.json`（本地固定配置）
3. `config/readme-profile.example.json`（字段结构示例）
4. `references/readme-template.md` 中的通用占位符

常用环境变量：

- `SUBTREE_README_UPSTREAM_NAME`
- `SUBTREE_README_UPSTREAM_URL`
- `SUBTREE_README_AUTHOR_DISPLAY`
- `SUBTREE_README_WECHAT_ID`
- `SUBTREE_README_QR_IMAGE_URL`
- `SUBTREE_README_CONTACT_DEFAULT`
- `SUBTREE_README_CONTACT_LEGAL`
- `SUBTREE_README_CONTACT_TOOL`

推荐字段：

- `upstream`: 上游项目或技能集合信息
- `author`: 作者展示名、联系方式、二维码图片 URL
- `contact_messages`: 默认、法律业务类、工具类联系文案
- `related_projects`: 可推荐的相关项目池
- `skill_overrides`: 按 skill 名定制推荐项目、联系文案或 profile

发布规则：

- 不要把真实的 `readme-profile.json` 写入公开发布包
- `scripts/create-release.sh` 会排除非 example 的 `config/*.json`，保留 `*.example.json`

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
