---
name: clawhub-sync
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.6.0"
license: MIT
description: 将本地开发的 Skills 批量同步到 ClawHub 与腾讯 SkillHub 两个平台。支持智能 .gitignore 过滤、白名单控制、增量同步、单个 skill 同步、双平台并行发布。本技能应在用户需要将本地 skills 发布到 ClawHub/SkillHub、批量同步技能、检查发布状态时使用。
---

# Skill 同步工具（ClawHub + 腾讯 SkillHub）

将本地开发的 Skills 批量同步到两个公开平台：

- **ClawHub** — 国际通用 Skills 社区，强制 MIT-0 许可证
- **腾讯 SkillHub** — 专为中国用户优化的 Skills 社区，无许可证限制

支持读取 `.gitignore` 智能忽略敏感文件和临时文件。两个平台可独立或并行发布。

## 依赖

### 系统依赖

| 依赖 | 用途 | 安装方式 |
|------|------|----------|
| `rsync` | `prepare-publish.sh` 复制过滤文件到临时发布目录 | macOS 自带；Linux: `sudo apt-get install rsync` |
| `git` | `prepare-publish.sh` 用 `git ls-files` 精确匹配追踪文件 | macOS 自带；Linux: `sudo apt-get install git` |
| Python 3 | 运行腾讯 SkillHub CLI（Python 脚本） | macOS 自带；Linux: `sudo apt-get install python3` |

### CLI 工具（按目标平台按需安装）

| CLI | 用途 | 安装命令 | 必需场景 |
|------|------|----------|----------|
| `clawhub` | 发布到 ClawHub | 见 [ClawHub 官方文档](https://docs.openclaw.ai/clawhub/cli) | 仅发布 ClawHub 时 |
| `skillhub` | 发布到腾讯 SkillHub | 官方 CLI，`skillhub self-upgrade` 升级（须 ≥ 2026.7.29） | 仅发布 SkillHub 时 |

> **⚠️ 版本要求（重要）**
>
> 腾讯 `skillhub` CLI **必须 ≥ 2026.7.29** 才支持 `publish`/`login`。早期版本（如 2026.3.18）只有 `search`/`install`，不能发布。
> 运行 `skillhub self-upgrade` 升级到最新版；不确定时先用 `skillhub self-upgrade --check-only` 检查是否有新版。

### 首次安装清单（SkillHub 发布）

```bash
# 1. 安装 CLI（macOS/Linux）
curl -fsSL https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com/install/install.sh | bash

# 2. 升级到支持发布的版本（≥ 2026.7.29）
skillhub self-upgrade

# 3. 验证（应含 publish/login 命令）
skillhub --help

# 4. 登录（token 从 https://skillhub.cn 个人设置获取，skh_ 前缀）
skillhub login --key skh_xxx

# 5. 确认身份
skillhub auth whoami
```



> **ClawHub 强制使用 MIT-0 许可证**（无需署名，允许商业使用）。
> **腾讯 SkillHub 无许可证限制**，CC-BY-NC / MIT / Apache 等均可发布。
>
> **ClawHub 许可证关键条款**（来自官方 Skill Format 文档，截至 2026-08 核实）：
> - "All skills published on ClawHub are licensed under `MIT-0`." —— 所有发布即等同 MIT-0。
> - "Anyone may use, modify, and redistribute published skills, including commercially." —— 允许任何人商用。
> - "Attribution is not required." —— 不要求署名。
> - "ClawHub does not support per-skill license overrides." —— **不支持按 skill 覆盖许可证**（frontmatter 写 `license: CC-BY-NC` 平台层面不生效）。
> - "Do not add conflicting license terms in `SKILL.md`." —— **禁止在 SKILL.md 内加冲突的许可证条款**。
>
> 因此：
> - MIT 许可证的 skill → 可发布到**两个平台**
> - CC-BY-NC 等限制性许可证的 skill → **只能发布到 SkillHub**（与 ClawHub MIT-0 冲突）
>
> 这意味着仓库内被 ClawHub 拒之门外的法律类 skill（legal-qa-extractor、patent-analysis、trademark-assistant 等）可以通过 SkillHub 公开发布。
>
> ClawHub 许可证详见 [ClawHub Skill Format 官方文档](https://docs.openclaw.ai/clawhub/skill-format)

---

## 平台对比

| 维度 | ClawHub | 腾讯 SkillHub |
|------|---------|---------------|
| CLI 工具 | `clawhub` | `skillhub`（官方 CLI，`skillhub self-upgrade` 升级；**须 ≥ 2026.7.29** 才支持 publish/login） |
| 登录命令 | `clawhub login` | `skillhub login --key skh_xxx` |
| 发布命令 | `clawhub publish <path> --slug --name --version --changelog` | `skillhub publish <path> [--version] [--changelog] [--dry-run]` |
| skill 标识 | `--slug` + `--name`（命令行传入） | `slug` + `displayName`（prepare-publish.sh 从 sync-allowlist.yaml 注入临时副本；源 SKILL.md 不含） |
| 可见性 | 无 | —（无此概念） |
| **许可证** | **强制 MIT-0** | **无限制** |
| 默认 registry/API | 内置 | `https://api.skillhub.cn` |
| 官方教程 | — | https://skillhub.cn/tutorials#publish-via-cli |

---

## 前置条件

### SKILL.md frontmatter 必需字段

```yaml
---
name: skill-name
description: 技能描述
version: "1.0.0"  # 推荐但不强制
homepage: https://github.com/cat-xierluo/legal-skills  # 自动设置
---
```

> **slug / displayName 不写进 SKILL.md**。SkillHub 需要的 `slug`（默认取 `name`，重名/被占用时在 `sync-allowlist.yaml` 覆盖）和 `displayName`（中文展示名）下沉到本地 `config/sync-allowlist.yaml`，发布前由 `prepare-publish.sh` 自动注入临时副本 frontmatter。源 SKILL.md 只保留 skill 标准字段，平台元数据与 skill 本体解耦。

### CLI 安装

CLI 工具的完整安装方式、版本要求，详见本文档开头「[依赖](#依赖)」章节。

快速验证已安装：

```bash
clawhub --version      # ClawHub
skillhub --help        # SkillHub（确认含 publish/login 命令即为发布版）
```

---

## 使用方式

### 1. 登录平台（首次使用）

**ClawHub**：

```bash
clawhub login
```

**腾讯 SkillHub**（使用 API Token，格式 `skh_xxx`，从 SkillHub 个人设置获取）：

```bash
# token 从 https://skillhub.cn 个人设置获取（skh_ 前缀）
skillhub login --key skh_xxx

# 如需临时使用其他 token 覆盖登录态（不写入本地）
skillhub login --key skh_yyy
```

> 登录后 token 存在本地，后续发布命令无需重复传 token。也可在 `skillhub publish` 时用 `--token skh_xxx` 临时覆盖。

### 2. 验证登录状态

```bash
# ClawHub
clawhub whoami

# 腾讯 SkillHub
skillhub auth whoami
```

### 3. 同步技能

#### ClawHub

**同步单个技能**：

```bash
clawhub sync skills/<skill-name>
```

**同步所有技能**：

```bash
clawhub sync --all
```

> 注意：`--all` 会受 `skills/clawhub-sync/config/sync-allowlist.yaml` 约束。只有 `platforms` 数组中包含 `clawhub` 的 skill 才会同步到 ClawHub。

#### 腾讯 SkillHub

SkillHub 推荐逐个 skill 发布（通过 `publish` 命令指定目录，标识来自 SKILL.md frontmatter，见下方「单个 Skill 同步工作流」）。

```bash
# 发布目录（自动打包）
skillhub publish ./my-skill

# 指定版本和 changelog
skillhub publish ./my-skill --version 1.2.0 --changelog "新增xxx"

# 先预检（只校验 + 打包，不实际发请求）
skillhub publish ./my-skill --dry-run
```

> SkillHub 用 `slug` + `displayName`（发布前由 prepare-publish.sh 从 sync-allowlist.yaml 注入临时副本，源 SKILL.md 不含）标识 skill，namespace 绑定在账号上（发布时无需命令行指定）。没有可见性概念。

**交互式选择同步**：用户可指定要同步的技能列表与目标平台，我会逐个执行同步命令。

---

## 单个 Skill 同步工作流

当需要同步指定的 skill（而非全部）时，使用此工作流。流程对两个平台通用，仅在「执行发布」步骤区分命令。

### 前置检查

1. **检查登录状态**
   ```bash
   clawhub whoami           # ClawHub
   skillhub auth whoami     # 腾讯 SkillHub
   ```

2. **检查白名单**
   - 读取 `skills/clawhub-sync/config/sync-allowlist.yaml`
   - 确认目标 skill 存在，且其 `platforms` 数组包含目标平台（`clawhub` 或 `skillhub`）

3. **检查许可证**（仅 ClawHub 需要）
   - 读取目标 skill 的 SKILL.md frontmatter 中的 `license` 字段
   - ClawHub：只有 MIT 许可证的 skill 才能同步
   - SkillHub：无许可证限制，均可同步

### 版本检测

比较两个版本号（按目标平台读取记录）：

| 来源 | 位置 | 格式 |
|------|------|------|
| **新版本** | `skills/<skill-name>/SKILL.md` frontmatter 的 `version` | `"1.2.0"` |
| **已记录版本** | `skills/clawhub-sync/config/sync-records.yaml` 中 `records.<skill>.platforms.<platform>.version` | `"1.1.0"` |

**版本比较逻辑**（语义化版本）：
```
new_version > recorded_version → 需要同步
new_version == recorded_version → 跳过（无变化）
new_version < recorded_version → 警告（版本回退？）
recorded_version 为 null → 需要同步（首次发布）
```

### 执行同步

#### 步骤 1：准备发布目录

```bash
# ClawHub（默认平台，可省略 --platform）
bash skills/clawhub-sync/scripts/prepare-publish.sh skills/<skill-name>

# 腾讯 SkillHub
bash skills/clawhub-sync/scripts/prepare-publish.sh --platform skillhub skills/<skill-name>
```

脚本会创建临时目录：
- ClawHub：`/tmp/clawhub-publish-<skill-name>`
- SkillHub：`/tmp/skillhub-publish-<skill-name>`

#### 步骤 2：执行发布

**ClawHub**（使用 `clawhub publish`，显式指定 slug 和 name）：

```bash
clawhub publish /tmp/clawhub-publish-<skill-name> \
  --slug <skill-name> \
  --name "<Display Name>" \
  --version "<新版本号>" \
  --changelog "<变更说明>"
```

> **⚠️ 必须指定 --slug 和 --name**
> - 临时目录名可能包含前缀（如 `clawhub-publish-`），导致发布时 slug 不正确
> - `--slug <skill-name>` 确保使用正确的 skill 标识符
> - `--name "<Display Name>"` 确保在 ClawHub 上显示正确的名称

**腾讯 SkillHub**（使用 `skillhub publish`，指定版本与 changelog）：

```bash
skillhub publish /tmp/skillhub-publish-<skill-name> \
  --version "<新版本号>" \
  --changelog "<变更说明>"
```

> **腾讯用 slug + displayName 标识 skill**：这两个字段**不写进源 SKILL.md**，而是发布前由 `prepare-publish.sh` 从 `config/sync-allowlist.yaml` 读取并注入临时副本 frontmatter（slug 默认取 `name`，displayName 取配置的 `display_name`）。namespace 绑定在账号上（发布时无需命令行指定），没有可见性概念。
> 版本号与 changelog 通过 `--version` / `--changelog` 显式传入；不带 `--version` 时由 CLI 决定。发布前可加 `--dry-run` 只做预检。

#### 步骤 3：更新同步记录

更新 `skills/clawhub-sync/config/sync-records.yaml`，在对应平台下写入记录：

```yaml
records:
  <skill-name>:
    platforms:
      clawhub:                      # 或 skillhub
        version: "<新版本号>"
        last_sync: "<ISO 8601 时间>"
        git_hash: "<当前 commit hash>"
        status: synced
        changelog_summary: "<变更说明>"
        url: "https://clawhub.ai/skills/<skill-name>"      # ClawHub
        # 或 SkillHub：
        # url: "https://skillhub.cn/skills/<slug>"
        publish_id: "<从命令输出获取>"
```

### 示例：同步 git-batch-commit 到两个平台

```bash
# 1. 检查白名单
grep -A1 "git-batch-commit:" skills/clawhub-sync/config/sync-allowlist.yaml
# 输出：platforms: [clawhub, skillhub]   # 两平台均可

# 2. 比较版本
# SKILL.md: version: "1.2.0"
# sync-records.yaml: platforms.clawhub.version: "1.1.0"，platforms.skillhub.version: null
# 结论：两平台都需要同步

# 3a. 准备并发布到 ClawHub
bash skills/clawhub-sync/scripts/prepare-publish.sh skills/git-batch-commit
clawhub publish /tmp/clawhub-publish-git-batch-commit \
  --slug git-batch-commit --name "Git Batch Commit" \
  --version "1.2.0" --changelog "添加双平台同步工作流"

# 3b. 准备并发布到 SkillHub
bash skills/clawhub-sync/scripts/prepare-publish.sh --platform skillhub skills/git-batch-commit
skillhub publish /tmp/skillhub-publish-git-batch-commit \
  --version "1.2.0" --changelog "添加双平台同步工作流"

# 4. 更新记录（编辑 sync-records.yaml，更新 git-batch-commit 条目的两个平台字段）
```

### 失败处理

- 同步失败时记录 `status: failed`
- 不重试，让用户决定后续操作
- 记录失败原因到 `changelog_summary`

---

## SkillHub 专属说明

### Token 获取

1. 登录 [SkillHub](https://skillhub.cn)
2. 在个人设置中生成 API Token（格式 `skh_xxx`，前缀 `skh_`）
3. 通过 `skillhub login --key skh_xxx` 保存到本地

```bash
skillhub login --key skh_xxx
skillhub auth whoami     # 确认身份
```

> **安全提醒**：Token 等同于账号密码，**绝对不要**写入配置文件或提交到 Git。`skillhub login` 已将 token 存到本地，后续发布命令无需重复传 token（CLI 自动读取）；如需临时覆盖，可在 `skillhub publish` 时用 `--token skh_xxx`。

### slug / namespace 与版本号规则

腾讯 SkillHub 用 `slug` + `displayName` + `namespace`（账号绑定）标识 skill。**slug/displayName 不写进源 SKILL.md**，而在 `config/sync-allowlist.yaml` 配置，发布前由 `prepare-publish.sh` 注入临时副本 frontmatter：

- **slug**：kebab-case，2-128 字符（实测校验正则）。默认 = skill 目录名（即 `name`）；在 `sync-allowlist.yaml` 用 `slug:` 字段覆盖（处理重名/被占用）。slug 在同一 namespace 下唯一，跨 namespace 可重名（如 `@cat-xierluo/md2word` 与他人的 `@xxx/md2word` 不冲突）
- **namespace**：命名空间，**绑定在账号上**（服务端 `@<namespace>/<slug>` 格式），发布命令**无需也无法**命令行指定——CLI 用登录账号的身份，服务端自动归到你的 namespace 下。你的 namespace 可通过 `skillhub search <你的skill>` 查看已发布 skill 的 `@xxx/slug` 前缀得知
- **version**：合法 SemVer（`major.minor.patch`），如 `1.0.0`。建议从 `0.1.0` 或 `1.0.0` 开始。已发布的版本不可修改，只能发布新版本

### API host

默认 API host 为 `https://api.skillhub.cn`。如需覆盖，`skillhub publish` 时用 `--host <URL>` 指定。

### SKILL.md frontmatter 要求

腾讯 SkillHub 发布时从（临时副本的）SKILL.md frontmatter 读取 skill 元数据。**源 SKILL.md 不需要写 slug/displayName**——`prepare-publish.sh` 会从 `config/sync-allowlist.yaml` 读取并注入临时副本：

| 字段 | 来源 | 说明 |
|------|------|------|
| `slug` | 默认取 `name`；`sync-allowlist.yaml` 的 `slug:` 可覆盖 | kebab-case，2-128 字符 |
| `displayName` | `sync-allowlist.yaml` 的 `display_name:`（必填） | SkillHub 展示名（中文） |
| `version` | 源 SKILL.md frontmatter（或 `--version` 覆盖） | 合法 SemVer |
| `summary` | 源 SKILL.md（可选） | 简短摘要 |
| `description` | 源 SKILL.md（可选） | 较长描述 |
| `tags` | 源 SKILL.md（可选） | 标签数组 |
| `license` | 源 SKILL.md（可选） | 许可证标识 |
| `homepage` | 源 SKILL.md（可选） | 主页地址 |

> **ClawHub 与腾讯字段差异**：ClawHub 用 `name` 字段 + 命令行 `--slug`/`--name`；腾讯用 `slug` + `displayName`（注入临时副本，源文件不写；namespace 绑定账号）。源 SKILL.md 只保留 `name`/`description`/`version` 等标准字段，两个平台的标识需求都由发布流程（命令行参数 / 配置注入）满足，不污染 skill 本体。

### CLI 版本注意

腾讯 `skillhub` CLI 是 Python 脚本。**老版本（< 2026.7.29）不支持 `publish`/`login`**，运行 `skillhub self-upgrade` 升级到最新版；不确定时先用 `skillhub self-upgrade --check-only` 检查是否有新版。

---

## 同步策略

### 版本号处理

- 从技能的 `CHANGELOG.md` 第一行提取版本号
- 格式要求：`## [x.y.z] - YYYY-MM-DD`
- 自动处理 `v` 前缀（`v1.0.0` → `1.0.0`）

### 自动字段

| 字段      | 处理方式                                     |
| --------- | -------------------------------------------- |
| `homepage` | 自动设置为 GitHub 仓库地址                   |
| `version`  | 从 CHANGELOG.md 提取（如 SKILL.md 中未指定） |

### 同步范围控制（白名单机制）

**配置文件：** `skills/clawhub-sync/config/sync-allowlist.yaml`（skill 自包含）

**优先级：白名单 > 默认忽略规则**

- 如果 `sync-allowlist.yaml` **存在**：只同步文件中列出的 skill，且只同步到其 `platforms` 数组中列出的平台
- 如果 `sync-allowlist.yaml` **不存在**：使用默认忽略规则（忽略 test/、private-skills/、node_modules/）

**配置格式（结构化 platforms 字段）：**

```yaml
# MIT 许可证 → 两平台均可
md2word:
  platforms: [clawhub, skillhub]

# CC-BY-NC 许可证 → 仅 SkillHub（ClawHub 强制 MIT-0，冲突）
legal-qa-extractor:
  platforms: [skillhub]
```

如需启用/禁用某 skill 的某平台，调整其 `platforms` 数组即可（注释掉整条则该 skill 不发布）。

### 配置文件与隐私（example vs 本地）

配置文件分公开模板和本地真实两份，便于本技能被他人复用：

| 文件 | 角色 | 是否入库 | 含本地真实数据 |
|------|------|----------|----------------|
| `config/sync-allowlist.example.yaml` | 公开模板 | ✅ 入库 | 无 |
| `config/sync-records.example.yaml` | 公开模板 | ✅ 入库 | 用占位符 |
| `config/sync-allowlist.yaml` | 本地真实配置 | ❌ gitignore 排除 | — |
| `config/sync-records.yaml` | 本地真实配置 | ❌ gitignore 排除 | 填入实际 publish_id 等 |

> **首次使用**：复制 `.example.yaml` 去掉 `.example` 后缀，填入你的实际数据。
> `sync-allowlist.yaml` 除 `platforms` 外，还为每个 skill 配 `display_name`（SkillHub 展示名，必填）和可选 `slug`（重名时覆盖）；发布前由 `prepare-publish.sh` 注入临时副本，源 SKILL.md 不含这两个字段。`sync-records.yaml` 记录 `publish_id` 等发布结果。
>
> 根目录 `.gitignore` 的 `**/config/*.yaml` + `!**/config/*.example.yaml` 规则**对 ClawHub 与 SkillHub 两平台均生效**（共用 `prepare-publish.sh` 过滤逻辑）。实测发布 `clawhub-sync` 自身时，真实 `sync-allowlist.yaml`/`sync-records.yaml` 不进入临时目录，只有 `.example.yaml` 模板会上传。
>
> 根目录 `.gitignore` 已通过 `**/config/*.yaml` + `!**/config/*.example.yaml` 规则，自动排除真实配置、保留模板。

### 文件过滤规则

发布时会自动应用 .gitignore 过滤规则，确保敏感文件和临时文件不会被上传。两个平台共用同一套过滤逻辑。

**双重过滤机制**：

1. **项目根目录 .gitignore** - 自动检测 Git 仓库根目录的 `.gitignore`
2. **技能内部 .gitignore** - 如果技能目录有自己的 `.gitignore`，会额外应用

**默认排除**（始终生效）：

- `.git/` - Git 目录
- `node_modules/` - Node.js 依赖
- `__pycache__/` - Python 缓存
- `.DS_Store` - macOS 系统文件

### 同步流程

每次同步前，会自动：

1. **创建临时目录** - 前缀随平台变化：`/tmp/clawhub-publish-<skill>` 或 `/tmp/skillhub-publish-<skill>`
2. **复制过滤后的文件** - 使用 rsync 遵循 .gitignore 规则复制文件
3. **发布到目标平台** - 从临时目录执行对应平台的发布命令
4. **清理临时目录** - 发布完成后自动清理

### 手动准备发布目录

如需手动检查将要发布的文件：

```bash
# ClawHub（默认）
bash skills/clawhub-sync/scripts/prepare-publish.sh skills/trademark-assistant
ls -la /tmp/clawhub-publish-trademark-assistant/

# 腾讯 SkillHub
bash skills/clawhub-sync/scripts/prepare-publish.sh --platform skillhub skills/trademark-assistant
ls -la /tmp/skillhub-publish-trademark-assistant/
```

## 安全最佳实践

### 发布前检查清单

- [ ] 确认 `.gitignore` 包含所有敏感文件模式
- [ ] 使用 `prepare-publish.sh` 检查将要发布的文件
- [ ] 不要在技能中包含 API keys、密码等
- [ ] 使用 `.env.example` 代替 `.env` 文件

### 常见敏感文件

- `.env` - 环境变量（使用 `.env.example` 作为模板）
- `config.yaml` - 配置文件（使用 `config.example.yaml` 作为模板）
- `*.db`, `*.sqlite` - 数据库文件
- `logs/` - 日志目录
- `downloads/`, `output/` - 输出目录

### 修复已发布的技能

如果发现已发布的技能包含敏感信息：

1. **立即更新** - 从技能目录中删除敏感文件
2. **更新 .gitignore** - 确保未来不会再次包含
3. **重新发布** - 用 `clawhub publish` 或 `skillhub publish` 更新对应平台
4. **联系平台支持** - 如果需要删除旧版本

**重要提醒**：

- **两个平台都是公开平台**：发布的技能任何人都可以访问
- **不要包含客户信息**：案例文件、沟通记录等应排除
- **不要包含凭证**：API keys、tokens 等应使用环境变量

## 常见问题

### 版本号未更新？

检查 CHANGELOG.md 格式：

```markdown
## [1.0.0] - 2026-03-21

### 新增
- 新功能描述
```

### 同步失败？

1. ClawHub：运行 `clawhub sync --dry-run` 检查配置
2. SkillHub：确认 `skillhub auth whoami` 登录正常、`sync-allowlist.yaml` 已为该 skill 配 `display_name`（slug 默认取 name；缺 display_name 时 prepare-publish.sh 会 fail-closed 报错）
3. 确认 SKILL.md frontmatter 格式正确
4. 检查白名单：目标 skill 的 `platforms` 是否包含目标平台

### ClawHub 提示许可证冲突？

CC-BY-NC 等 license 与 ClawHub MIT-0 冲突，无法发布到 ClawHub。这类 skill 改发 SkillHub（无许可证限制）。详见 [ClawHub Skill Format 官方文档](https://docs.openclaw.ai/clawhub/skill-format)。

## 输入/输出

### 输入

- 必需：本地开发的 skill 目录
- 可选：指定技能名称列表、目标平台（clawhub / skillhub）、白名单配置

### 输出

- 同步结果报告（成功/失败列表，按平台分组）
- 错误信息（如有）

## 同步记录

每次同步后，会更新 `config/sync-records.yaml` 记录文件，便于溯源和增量同步。记录按平台分别存储。

### 记录结构

```yaml
records:
  <skill-name>:
    platforms:
      clawhub:    # ClawHub 平台记录
        <fields>
      skillhub:   # 腾讯 SkillHub 平台记录
        <fields>
```

### 记录字段

| 字段 | 说明 | 适用平台 |
|------|------|----------|
| `version` | 同步时的版本号 | 两者 |
| `last_sync` | 最后同步时间 (ISO 8601) | 两者 |
| `git_hash` | 同步时的 commit hash | 两者 |
| `status` | `synced` / `pending` / `failed` / `skipped` / `slug_conflict` / `deleted` | 两者 |
| `changelog_summary` | 变更摘要 | 两者 |
| `url` | 平台发布地址 | 两者 |
| `publish_id` | 平台内部 ID | 两者 |
| `namespace` | 命名空间（账号绑定，如 `cat-xierluo`；发布时不传，记录用于溯源安装命令） | SkillHub |

### 记录示例

```yaml
records:
  md2word:
    platforms:
      clawhub:
        version: "1.1.8"
        last_sync: "2026-03-24T16:42:00+08:00"
        git_hash: "fbb1db4"
        status: synced
        changelog_summary: "全书自动更新目录域"
        url: "https://clawhub.ai/skills/md2word"
        publish_id: "k97dtn63cty6ezwzj9g9ry85818axkdq"
      skillhub:
        namespace: "cat-xierluo"
        version: "1.1.8"
        last_sync: "2026-08-01T10:00:00+08:00"
        git_hash: "fbb1db4"
        status: synced
        changelog_summary: "首次发布 SkillHub"
        url: "https://skillhub.cn/cat-xierluo/md2word"
        publish_id: "sh_xxxxxxxxxxxxxxxx"
```

### 用途

1. **增量同步**：只同步 `status: pending` 或版本更新的 skill（按平台独立判断）
2. **溯源**：通过 `git_hash` 追溯发布时的代码状态
3. **快速访问**：通过 `url` 直接访问平台上的 skill 页面
