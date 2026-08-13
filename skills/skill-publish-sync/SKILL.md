---
name: skill-publish-sync
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.7.2"
license: MIT
description: 将本地开发的 Skills 同步到 ClawHub、腾讯 SkillHub 与联想开放平台。支持智能 .gitignore 过滤、平台独立白名单、增量与单个 skill 同步。本技能应在用户需要将本地 skills 发布到上述平台、批量同步技能或检查发布状态时使用。
---

# Skill 同步工具（ClawHub + 腾讯 SkillHub）

将本地开发的 Skills 批量同步到三个公开平台：

- **ClawHub** — 国际通用 Skills 社区，强制 MIT-0 许可证
- **腾讯 SkillHub** — 专为中国用户优化的 Skills 社区，无许可证限制
- **联想开放平台** — 面向联想 AI 智能体生态，使用 `@lenovo-open/skill-cli` (Node.js)；无强制许可证

支持读取 `.gitignore` 智能忽略敏感文件和临时文件。三个平台各自维护独立的 allowlist 列表文件（`allowlist-clawhub.yaml` / `allowlist-skillhub.yaml` / `allowlist-lenovo.yaml`），同一 skill 可在多份文件中独立维护字段（一对多，不强制不重复分发）。

## 依赖

### 系统依赖

| 依赖 | 用途 | 安装方式 |
|------|------|----------|
| `rsync` | `prepare-publish.sh` 复制过滤文件到临时发布目录 | macOS 自带；Linux: `sudo apt-get install rsync` |
| `git` | `prepare-publish.sh` 用 `git ls-files` 精确匹配追踪文件 | macOS 自带；Linux: `sudo apt-get install git` |
| Python 3 | 运行腾讯 SkillHub CLI（Python 脚本） | macOS 自带；Linux: `sudo apt-get install python3` |
| Node.js（≥ 18）+ `npm` | 运行联想 `lenovoskill` CLI（`npx @lenovo-open/skill-cli` 走 Node.js 运行时） | macOS 自带或 `brew install node`；Linux: `sudo apt-get install -y nodejs npm` |

### CLI 工具（按目标平台按需安装）

| CLI | 用途 | 安装命令 | 必需场景 |
|------|------|----------|----------|
| `clawhub` | 发布到 ClawHub | 见 [ClawHub 官方文档](https://docs.openclaw.ai/clawhub/cli) | 仅发布 ClawHub 时 |
| `skillhub` | 发布到腾讯 SkillHub | 官方 CLI，`skillhub self-upgrade` 升级（须 ≥ 2026.7.29） | 仅发布 SkillHub 时 |
| `lenovoskill`（`npx @lenovo-open/skill-cli`） | 上传到联想开放平台 | `npx @lenovo-open/skill-cli <cmd>`（免装，推荐）或 `npm i -g @lenovo-open/skill-cli` | 仅上传联想平台时 |

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
> 因此（**v1.7.1 三份独立列表架构**）：
> - 每个平台独立维护自己的 allowlist 文件：ClawHub / SkillHub / 联想各一份
> - MIT 许可证的通用工具 skill → 默认只发 ClawHub（`allowlist-clawhub.yaml`）
> - CC-BY-NC 等限制性许可证的法律类 skill → 默认只发 SkillHub（`allowlist-skillhub.yaml`，ClawHub MIT-0 冲突不收）
> - 想在 ClawHub / SkillHub 之外额外分发到联想生态的 skill → 在 `allowlist-lenovo.yaml` 里登记（无许可证限制，可与 SkillHub / ClawHub 重复登记，即同一 skill 跨多份文件是完全允许的）
> - ClawHub slug 被占用、发不了的 → 从 `allowlist-clawhub.yaml` 移到 `allowlist-skillhub.yaml` 或 `allowlist-lenovo.yaml`
>
> 即**三份独立 allowlist 文件**，每份独立维护各自平台的 skill 名单与字段；同一 skill 可同时出现在多份文件里（一对多），无需为新平台改动旧 skill 的配置。详见 DECISIONS `D-2026-08-12-02`。
>
> ClawHub 许可证详见 [ClawHub Skill Format 官方文档](https://docs.openclaw.ai/clawhub/skill-format)

---

## 平台对比

| 维度 | ClawHub | 腾讯 SkillHub | 联想开放平台 |
|------|---------|---------------|---------------|
| CLI 工具 | `clawhub` | `skillhub`（官方 CLI，`skillhub self-upgrade` 升级；**须 ≥ 2026.7.29** 才支持 publish/login） | `lenovoskill`（`npx @lenovo-open/skill-cli`，Node.js 运行时） |
| 登录命令 | `clawhub login` | `skillhub login --key skh_xxx` | `lenovoskill login`（OAuth 浏览器授权） |
| 发布命令 | `clawhub publish <path> --slug --name --version --changelog` | `skillhub publish <path> [--version] [--changelog] [--dry-run]` | `lenovoskill package && lenovoskill push`（两步：先打 zip 再传） |
| skill 标识 | `--slug` + `--name`（命令行传入） | `slug` + `displayName`（prepare-publish.sh 从 `allowlist-skillhub.yaml` 注入临时副本；源 SKILL.md 不含） | `slug` + `displayName`（prepare-publish.sh 从 `allowlist-lenovo.yaml` 注入临时副本；源 SKILL.md 不含） + 项目内 `.skill-config.json` |
| 凭证位置 | clawhub CLI 默认 | 本地 skillhub 配置 | `~/.lenovoskill/auth.json`（600，OAuth 双 token：Login Token + Biz Token）+ `~/.lenovoskill/config.json`（默认 API） |
| 可见性 | 无 | —（无此概念） | —（无此概念） |
| namespace | 无 | **有**（绑定账号，发布命令不传，记录用于溯源） | **无**（OAuth 双 token，无 namespace 概念） |
| **许可证** | **强制 MIT-0** | **无限制** | **无限制** |
| 默认 registry/API | 内置 | `https://api.skillhub.cn` | `https://open.lenovomm.com` |
| 官方教程 | — | https://skillhub.cn/tutorials#publish-via-cli | https://open.lenovomm.com |

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

> **slug / displayName 不写进 SKILL.md**。SkillHub 需要的字段从 `config/allowlist-skillhub.yaml` 读取；联想开放平台需要的字段从 `config/allowlist-lenovo.yaml` 读取。**每个平台独立白名单，字段独立维护**（同一 skill 可同时出现在多份文件里，一对多）。发布前由 `prepare-publish.sh`（`--platform skillhub` 或 `--platform lenovo`）自动注入临时副本 frontmatter。源 SKILL.md 只保留 skill 标准字段，平台元数据与 skill 本体解耦。ClawHub 不依赖 frontmatter（用 `--slug`/`--name` 命令行参数）。

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

> 注意：`--all` 会受 `skills/skill-publish-sync/config/allowlist-clawhub.yaml` 约束。只有在该文件中列出的 skill 才会同步到 ClawHub。SkillHub / 联想同理（各自独立白名单文件）。

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

> SkillHub 用 `slug` + `displayName`（发布前由 prepare-publish.sh 从 `config/allowlist-skillhub.yaml` 注入临时副本，源 SKILL.md 不含）标识 skill，namespace 绑定在账号上（发布时无需命令行指定）。没有可见性概念。

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
   - 读取 `skills/skill-publish-sync/config/allowlist-${PLATFORM}.yaml`（平台特定白名单）
   - 确认目标 skill 出现在对应平台的 allowlist 文件中（每平台独立文件,无 `platforms` 字段）
   - 三平台独立文件路径：
     - ClawHub → `allowlist-clawhub.yaml`
     - SkillHub → `allowlist-skillhub.yaml`
     - 联想 → `allowlist-lenovo.yaml`

3. **检查许可证**（仅 ClawHub 需要）
   - 读取目标 skill 的 SKILL.md frontmatter 中的 `license` 字段
   - ClawHub：只有 MIT 许可证的 skill 才能同步
   - SkillHub / 联想：无许可证限制，均可同步

### 版本检测

比较两个版本号（按目标平台读取记录）：

| 来源 | 位置 | 格式 |
|------|------|------|
| **新版本** | `skills/<skill-name>/SKILL.md` frontmatter 的 `version` | `"1.2.0"` |
| **已记录版本** | `skills/skill-publish-sync/config/sync-records.yaml` 中 `records.<skill>.platforms.<platform>.version` | `"1.1.0"` |

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
bash skills/skill-publish-sync/scripts/prepare-publish.sh skills/<skill-name>

# 腾讯 SkillHub
bash skills/skill-publish-sync/scripts/prepare-publish.sh --platform skillhub skills/<skill-name>
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

> **腾讯用 slug + displayName 标识 skill**：这两个字段**不写进源 SKILL.md**，而是发布前由 `prepare-publish.sh --platform skillhub` 从 `config/allowlist-skillhub.yaml` 读取并注入临时副本 frontmatter（slug 默认取 `name`，displayName 取配置的 `display_name`）。namespace 绑定在账号上（发布时无需命令行指定），没有可见性概念。
> 版本号与 changelog 通过 `--version` / `--changelog` 显式传入；不带 `--version` 时由 CLI 决定。发布前可加 `--dry-run` 只做预检。

**联想开放平台**（使用 `lenovoskill`，先打 zip 再传两步）：

```bash
# 1. 准备：先在临时目录生成 .skill-config.json（联想 CLI 项目级配置）
cd /tmp/lenovo-publish-<skill-name>
# 源 skill 若已带 .skill-config.json,prepare-publish.sh 已一并复制,跳过 init;
# 否则跑一次 init 生成默认配置再按需编辑:
lenovoskill init

# 2. 打 zip
lenovoskill package
# → 生成 <skill-name>.zip

# 3. 上传 zip
lenovoskill push
```

> **联想同样从 SKILL.md frontmatter 读 slug + displayName**：这两个字段由 `prepare-publish.sh --platform lenovo` 注入临时副本（与 SkillHub 共用同一段 python 逻辑）。同时联想 CLI 也读项目内 `.skill-config.json`——两者并存，`displayName` / `slug` 字段在 SKILL.md frontmatter 与 `.skill-config.json` 中应保持一致。
> `.skill-config.json` 建议**仅在临时目录生成/复制**，不要 commit 进源 skill（它是联想 CLI 的私有适配层，与 skill 标准结构无关）。

#### 步骤 3：更新同步记录

更新 `skills/skill-publish-sync/config/sync-records.yaml`，在对应平台下写入记录：

```yaml
records:
  <skill-name>:
    platforms:
      clawhub:                      # 或 skillhub / lenovo
        version: "<新版本号>"
        last_sync: "<ISO 8601 时间>"
        git_hash: "<当前 commit hash>"
        status: synced
        changelog_summary: "<变更说明>"
        url: "https://clawhub.ai/skills/<skill-name>"      # ClawHub
        # 或 SkillHub：
        # url: "https://skillhub.cn/skills/<slug>"
        # 或联想开放平台:
        # url: "https://open.lenovomm.com/skills/<slug>"
        publish_id: "<从命令输出获取>"
        # SkillHub 还要加一行 namespace: "<your-namespace>";ClawHub / 联想无 namespace 字段
```

### 示例：同步 skill（按分流策略发到对应平台）

**A. MIT 工具 → ClawHub（以 git-batch-commit 为例）**

```bash
# 1. 检查白名单
grep -A1 "^git-batch-commit:" skills/skill-publish-sync/config/allowlist-clawhub.yaml
# 输出：platforms: [clawhub]   # MIT 工具，只发 ClawHub

# 2. 比较版本
# SKILL.md: version: "1.2.0"
# sync-records.yaml: platforms.clawhub.version: "1.1.0" → 需要同步

# 3. 准备并发布到 ClawHub
bash skills/skill-publish-sync/scripts/prepare-publish.sh skills/git-batch-commit
clawhub publish /tmp/clawhub-publish-git-batch-commit \
  --slug git-batch-commit --name "Git Batch Commit" \
  --version "1.2.0" --changelog "本次变更说明"

# 4. 更新 sync-records.yaml 的 platforms.clawhub 字段
```

**B. CC-BY-NC 法律类 → SkillHub（以 legal-qa-extractor 为例）**

```bash
# 1. 检查白名单
grep -A2 "^legal-qa-extractor:" skills/skill-publish-sync/config/allowlist-skillhub.yaml
# 输出：platforms: [skillhub]  +  display_name: "法律问答知识提取"

# 2. 准备（--platform skillhub 会自动从配置读 display_name/slug 注入临时副本 frontmatter）
bash skills/skill-publish-sync/scripts/prepare-publish.sh --platform skillhub skills/legal-qa-extractor

# 3. 发布到 SkillHub
skillhub publish /tmp/skillhub-publish-legal-qa-extractor \
  --version "<新版本号>" --changelog "<变更说明>"

# 4. 更新 sync-records.yaml 的 platforms.skillhub 字段
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

腾讯 SkillHub 用 `slug` + `displayName` + `namespace`（账号绑定）标识 skill。**slug/displayName 不写进源 SKILL.md**，而在 `config/allowlist-skillhub.yaml`（平台特定白名单）配置，发布前由 `prepare-publish.sh` 注入临时副本 frontmatter：

- **slug**：kebab-case，2-128 字符（实测校验正则）。默认 = skill 目录名（即 `name`）；在 `allowlist-skillhub.yaml` 用 `slug:` 字段覆盖（处理重名/被占用）。slug 在同一 namespace 下唯一，跨 namespace 可重名（如 `@cat-xierluo/md2word` 与他人的 `@xxx/md2word` 不冲突）
- **namespace**：命名空间，**绑定在账号上**（服务端 `@<namespace>/<slug>` 格式），发布命令**无需也无法**命令行指定——CLI 用登录账号的身份，服务端自动归到你的 namespace 下。你的 namespace 可通过 `skillhub search <你的skill>` 查看已发布 skill 的 `@xxx/slug` 前缀得知
- **version**：合法 SemVer（`major.minor.patch`），如 `1.0.0`。建议从 `0.1.0` 或 `1.0.0` 开始。已发布的版本不可修改，只能发布新版本

### API host

默认 API host 为 `https://api.skillhub.cn`。如需覆盖，`skillhub publish` 时用 `--host <URL>` 指定。

### SKILL.md frontmatter 要求

腾讯 SkillHub 发布时从（临时副本的）SKILL.md frontmatter 读取 skill 元数据。**源 SKILL.md 不需要写 slug/displayName**——`prepare-publish.sh` 会从 `config/allowlist-skillhub.yaml` 读取并注入临时副本：

| 字段 | 来源 | 说明 |
|------|------|------|
| `slug` | 默认取 `name`；`allowlist-skillhub.yaml` 的 `slug:` 可覆盖 | kebab-case，2-128 字符 |
| `displayName` | `allowlist-skillhub.yaml` 的 `display_name:`（必填） | SkillHub 展示名（中文） |
| `version` | 源 SKILL.md frontmatter（或 `--version` 覆盖） | 合法 SemVer |
| `summary` | 源 SKILL.md（可选） | 简短摘要 |
| `description` | 源 SKILL.md（可选） | 较长描述 |
| `tags` | 源 SKILL.md（可选） | 标签数组 |
| `license` | 源 SKILL.md（可选） | 许可证标识 |
| `homepage` | 源 SKILL.md（可选） | 主页地址 |

> **ClawHub 与腾讯字段差异**：ClawHub 用 `name` 字段 + 命令行 `--slug`/`--name`；腾讯用 `slug` + `displayName`（注入临时副本，源文件不写；namespace 绑定账号）。源 SKILL.md 只保留 `name`/`description`/`version` 等标准字段，两个平台的标识需求都由发布流程（命令行参数 / 配置注入）满足，不污染 skill 本体。

### CLI 版本注意

腾讯 `skillhub` CLI 是 Python 脚本。**老版本（< 2026.7.29）不支持 `publish`/`login`**，运行 `skillhub self-upgrade` 升级到最新版；不确定时先用 `skillhub self-upgrade --check-only` 检查是否有新版。

### 发布频率限制（避免并发限流）

腾讯 SkillHub API 对发布请求有频率限制。**连续多次 `skillhub publish` 会触发限流**（报错 "请求过于频繁,请稍后再试"），单个 publish 失败需重试，且会拖慢整个批量流程。

**实测安全间隔**：每个 `skillhub publish` 之间 `sleep 12-15` 秒。批量发布 N 个预计总耗时 ≈ N ×（单次发布耗时 + 15s）。

**推荐写法**（**串行 + sleep,不要并行**）:

```bash
while IFS='|' read -r s v; do
  bash prepare-publish.sh --platform skillhub "skills/$s" >/dev/null 2>&1
  echo "$s: $(skillhub publish /tmp/skillhub-publish-$s --version "$v" --changelog '...' 2>&1 | tail -1)"
  sleep 15
done <<EOF
skill-a|1.0.0
skill-b|1.1.0
EOF
```

**失败处理**：遇到限流报错，不要立即重跑整批。`sleep 30-60` 秒后单独重试失败的 skill（从 `sync-records.yaml` 看哪些平台仍是 `pending`）。

**避免**：`for s in ...; do (skillhub publish $s &); done`（并行）—— 100% 触发限流。

---

## 联想开放平台（LenovoSkill CLI）上传

联想开放平台（`https://open.lenovomm.com`）是面向联想 AI 智能体生态的 skill 分发渠道。**v1.7.1 三份独立列表架构下，联想与 ClawHub / SkillHub 是平行的第三渠道**——任何 skill 都可在 `allowlist-lenovo.yaml` 登记（无许可证限制），与 ClawHub / SkillHub 平台独立维护字段。一对多：同一 skill 可同时出现在 `allowlist-clawhub.yaml` + `allowlist-skillhub.yaml` + `allowlist-lenovo.yaml` 多份文件里。

### 与前两个平台的差异

| 维度 | ClawHub | 腾讯 SkillHub | 联想开放平台 |
|------|---------|---------------|--------------|
| 平台角色 | **独立列表平台**（`allowlist-clawhub.yaml`） | **独立列表平台**（`allowlist-skillhub.yaml`） | **独立列表平台**（`allowlist-lenovo.yaml`，与 SkillHub / ClawHub 平行） |
| 工作流 | 单条 `publish` 命令 | 单条 `publish` 命令 | **两步**：`package` 打 zip → `push` 上传 zip |
| CLI | `clawhub` | `skillhub`（Python） | `lenovoskill`（`npx @lenovo-open/skill-cli`，Node.js） |
| 凭证 | `clawhub login` | `skillhub login --key skh_xxx` | `lenovoskill login`（OAuth 浏览器授权） |
| 标识机制 | 命令行 `--slug/--name` | 临时副本 frontmatter（slug/displayName） | 临时副本 frontmatter（slug/displayName）+ 项目内 `.skill-config.json` |
| namespace | 无 | **有**（绑定账号，发布命令不传，记录溯源用） | **无**（OAuth 双 token） |
| 许可证 | 强制 MIT-0 | 无限制 | 无限制 |
| 同步记录 | `sync-records.yaml` `platforms.clawhub` | `sync-records.yaml` `platforms.skillhub`（含 namespace） | `sync-records.yaml` `platforms.lenovo`（无 namespace） |

### CLI 安装

```bash
# 方式 1：npx（推荐，免装、始终最新版）
npx @lenovo-open/skill-cli <cmd>

# 方式 2：全局安装（短命令、可离线）
npm install -g @lenovo-open/skill-cli
# 之后用 lenovoskill 代替 npx @lenovo-open/skill-cli
```

下文统一用 `lenovoskill`；用 npx 时替换即可。**前置依赖：Node.js ≥ 18 + npm**（详见本文档「依赖 · 系统依赖」章节）。

### 首次登录

```bash
lenovoskill login          # 浏览器 OAuth 授权
lenovoskill whoami         # 确认身份
lenovoskill logout         # 退出登录
```

凭证与配置（OAuth 安全存储，**禁止写入仓库或公开平台**）：

| 文件 | 模式 | 用途 |
|------|------|------|
| `~/.lenovoskill/auth.json` | 600 | **Login Token** + **Biz Token**（OAuth 双 token）+ 用户信息 |
| `~/.lenovoskill/config.json` | 默认 | API URL（默认 `https://open.lenovomm.com`）+ 默认可见性 |

### 上传工作流（5 步）

```bash
# ① 准备安全过滤目录（复用 prepare-publish.sh，会触发 SkillHub/联想 共用的 frontmatter 注入段）
bash skills/skill-publish-sync/scripts/prepare-publish.sh --platform lenovo skills/<skill-name>
# → 生成 /tmp/lenovo-publish-<skill-name>;临时副本 SKILL.md 已注入 slug + displayName

cd /tmp/lenovo-publish-<skill-name>

# ② 准备 .skill-config.json（联想 CLI 项目级元数据,与 SKILL.md frontmatter 互补）
#    - 源 skill 目录若已带 .skill-config.json,prepare-publish.sh 已一并复制,直接用
#    - 否则从源目录复制,或在此目录跑一次 lenovoskill init 生成默认配置再按需编辑
lenovoskill init            # 生成默认 .skill-config.json(可手编 ignore patterns)

# ③ 打 zip
lenovoskill package
# → 生成 <skill-name>.zip

# ④ 上传 zip
lenovoskill push
```

> **⚠️ 必须先过 prepare-publish.sh**：联想 CLI 没有内置 .gitignore 过滤,直接打源目录会把本地真实 `config/*.yaml`、`scripts/` 中间产物、`.DS_Store` 等一并打进 zip 上传。先过 prepare-publish.sh,临时目录已是 git ls-files 过滤后的"干净内容",再打 zip 才安全。

### `.skill-config.json`

联想 CLI 在每个 skill 项目根目录读取该文件,包含：

- **Skill 元数据**:name / version / description 等(可与 SKILL.md frontmatter 一致)
- **Ignore patterns**:打包时额外排除的文件(配合 prepare-publish.sh 双重保险)

> **建议**:此文件**仅在临时目录里生成/复制**,不写回源 skill 仓库——它只是联想 CLI 的私有适配层,与 skill 标准结构无关。
>
> **与 frontmatter slug/displayName 的关系**:联想 CLI 同时从 SKILL.md frontmatter 读 `slug` + `displayName`（由 prepare-publish.sh 注入临时副本）和项目内 `.skill-config.json` 读元数据。**两者应保持一致**——`displayName` / `slug` 在 SKILL.md frontmatter 与 `.skill-config.json` 中不能冲突。

### 命令速查

| 命令 | 用途 |
|------|------|
| `lenovoskill login` | 登录联想开放平台（OAuth） |
| `lenovoskill logout` | 注销 |
| `lenovoskill whoami` | 显示当前登录用户 |
| `lenovoskill init` | 在当前目录初始化 .skill-config.json |
| `lenovoskill package` | 将当前目录打包成 zip |
| `lenovoskill push` | 上传 zip 到联想开放平台 |

### 失败处理

- **`push` 失败**:先跑 `lenovoskill whoami` 确认登录态;检查 `.skill-config.json` 字段;确认 zip 是 `package` 刚生成的。
- **打包内容有误**:**回到步骤 1**,改源 skill + 重跑 `prepare-publish.sh`,不要在源目录直接重打(会绕过安全过滤)。
- **想撤销已发布的版本**:参考本文档「修复已发布的技能」章节,但联系联想平台支持由用户自行决定,不在本 skill 范围内。

### 与 sync-records.yaml 的关系

联想平台发布结果**必须**写进 `sync-records.yaml` 的 `platforms.lenovo`——与 SkillHub / ClawHub 一样，是三平台独立白名单架构的固定组成部分。`platforms.lenovo` 字段与 `platforms.skillhub` / `platforms.clawhub` 同构（`version` / `last_sync` / `git_hash` / `status` / `changelog_summary` / `url` / `publish_id`），**无 `namespace` 字段**（OAuth 双 token 机制，没有 namespace 概念）。

```yaml
records:
  <skill-name>:
    platforms:
      lenovo:                      # 三平台独立白名单架构(联想是独立第三选项,允许与其他平台字段独立维护)
        version: "<新版本号>"
        last_sync: "<ISO 8601 时间>"
        git_hash: "<当前 commit hash>"
        status: synced
        changelog_summary: "<变更说明>"
        url: "https://open.lenovomm.com/skills/<slug>"
        publish_id: "<从 lenovoskill push 输出获取>"
        # 无 namespace:联想用 OAuth 双 token(Login Token + Biz Token)
```

> **⚠️ NOT_VERIFIED**：以上 LenovoSkill CLI 命令(`login`/`init`/`package`/`push` 行为、`.skill-config.json` 字段、OAuth 流程、平台许可证审核、**是否实际从 SKILL.md frontmatter 读 slug/displayName**)的细节**来自用户提供的材料,未独立实测**。首次实际推送时以 CLI 实际行为为准;若行为有偏差（比如实测发现联想 CLI 不读 frontmatter 而完全依赖 `.skill-config.json`），回头修正本节——inject 段对 lenovo 可能无意义，需重新评估本决策。

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

### 同步范围控制（白名单机制，v1.7.1 三份独立列表）

**配置文件：** 三份独立白名单文件（v1.7.1 架构，详见 DECISIONS `D-2026-08-12-02`）：

- `skills/skill-publish-sync/config/allowlist-clawhub.yaml`（ClawHub 平台白名单）
- `skills/skill-publish-sync/config/allowlist-skillhub.yaml`（SkillHub 平台白名单）
- `skills/skill-publish-sync/config/allowlist-lenovo.yaml`（联想开放平台白名单）

**优先级：白名单 > 默认忽略规则**

- 如果对应平台的 `allowlist-${PLATFORM}.yaml` **存在**：只同步该文件中列出的 skill（每个平台独立读取自己的白名单文件）
- 如果对应平台的 `allowlist-${PLATFORM}.yaml` **不存在**：使用默认忽略规则（忽略 test/、private-skills/、node_modules/）

**配置格式（v1.7.1 三份独立列表，每份文件无 `platforms` 字段）：**

```yaml
# allowlist-clawhub.yaml（17 条 MIT 通用工具,display_name/slug 可选）
md2word:
patent-download:
# ...

# allowlist-skillhub.yaml（12 条 CC-BY-NC 法律类,display_name 必填）
legal-qa-extractor:
  display_name: "法律问答知识提取"
contract-copilot:
  display_name: "合同起草与审查助手"
# ...

# allowlist-lenovo.yaml（0 条,初始空,用户按需手动添加）
# contract-copilot:
#   display_name: "合同起草与审查助手"    # 与 skillhub 分区独立维护,可不同
```

**一对多语义**：同一 skill 可同时出现在多份文件里（如 contract-copilot 可同时在 `allowlist-skillhub.yaml` 和 `allowlist-lenovo.yaml` 登记，各自维护独立的 `display_name`）。无需为新平台改动旧 skill 的配置。

如需启用/禁用某 skill 在某平台，直接在对应平台的 allowlist 文件里添加/注释该 skill 行即可。

### 配置文件与隐私（example vs 本地，v1.7.1 三份独立列表）

配置文件分公开模板和本地真实两份，便于本技能被他人复用：

| 文件 | 角色 | 是否入库 | 含本地真实数据 |
|------|------|----------|----------------|
| `config/allowlist-clawhub.example.yaml` | ClawHub 白名单公开模板 | ✅ 入库 | 无 |
| `config/allowlist-skillhub.example.yaml` | SkillHub 白名单公开模板 | ✅ 入库 | 无 |
| `config/allowlist-lenovo.example.yaml` | 联想白名单公开模板 | ✅ 入库 | 无 |
| `config/sync-records.example.yaml` | 同步记录公开模板 | ✅ 入库 | 用占位符 |
| `config/allowlist-clawhub.yaml` | ClawHub 本地真实白名单 | ❌ gitignore 排除 | — |
| `config/allowlist-skillhub.yaml` | SkillHub 本地真实白名单 | ❌ gitignore 排除 | — |
| `config/allowlist-lenovo.yaml` | 联想本地真实白名单 | ❌ gitignore 排除 | — |
| `config/sync-records.yaml` | 本地真实同步记录 | ❌ gitignore 排除 | 填入实际 publish_id 等 |

> **首次使用**：复制对应 `.example.yaml` 去掉 `.example` 后缀，填入你的实际数据。三份白名单文件**独立维护**——同一 skill 可在不同白名单中独立登记（一对多）。
> SkillHub / 联想的白名单文件中 `display_name` 必填（中文展示名，发布前由 `prepare-publish.sh` 注入临时副本 frontmatter；源 SKILL.md 不含此字段）。`sync-records.yaml` 记录 `publish_id` 等发布结果。
>
> 根目录 `.gitignore` 的 `**/config/*.yaml` + `!**/config/*.example.yaml` 规则**对所有平台（ClawHub / SkillHub / 联想）均生效**（共用 `prepare-publish.sh` 过滤逻辑）。实测发布 `skill-publish-sync` 自身时，三份真实 `allowlist-*.yaml` 与 `sync-records.yaml` 均不进入临时目录，只有 `.example.yaml` 模板会上传。
>
> 根目录 `.gitignore` 已通过 `**/config/*.yaml` + `!**/config/*.example.yaml` 规则，自动排除真实配置、保留模板。

### 文件过滤规则

发布时会自动应用 .gitignore 过滤规则，确保敏感文件和临时文件不会被上传。三个平台共用同一套过滤逻辑。

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
bash skills/skill-publish-sync/scripts/prepare-publish.sh skills/trademark-assistant
ls -la /tmp/clawhub-publish-trademark-assistant/

# 腾讯 SkillHub
bash skills/skill-publish-sync/scripts/prepare-publish.sh --platform skillhub skills/trademark-assistant
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
3. **重新发布** - 用 `clawhub publish` / `skillhub publish` / `lenovoskill push` 更新对应平台
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
2. SkillHub：确认 `skillhub auth whoami` 登录正常、`config/allowlist-skillhub.yaml` 已为该 skill 配 `display_name`（slug 默认取 name；缺 display_name 时 prepare-publish.sh 会 fail-closed 报错）
3. 联想开放平台：确认 `lenovoskill whoami` 登录正常、`config/allowlist-lenovo.yaml` 已配 `display_name`（联想也由 prepare-publish.sh 注入 frontmatter）；Node.js ≥ 18 + `npx` 可用；临时目录已生成 `.skill-config.json`（init 生成或从源复制）
4. 确认 SKILL.md frontmatter 格式正确
5. 检查白名单：目标 skill 是否在对应平台的 `allowlist-${PLATFORM}.yaml` 中（v1.7.1 三份独立列表，每平台独立文件）

### ClawHub 提示许可证冲突？

CC-BY-NC 等 license 与 ClawHub MIT-0 冲突，无法发布到 ClawHub。这类 skill 改发 SkillHub（无许可证限制）。详见 [ClawHub Skill Format 官方文档](https://docs.openclaw.ai/clawhub/skill-format)。

## 输入/输出

### 输入

- 必需：本地开发的 skill 目录
- 可选：指定技能名称列表、目标平台（`clawhub` / `skillhub` / `lenovo`，每平台独立白名单文件 `allowlist-${PLATFORM}.yaml`；详见平台对比表与同步范围控制章节）、白名单配置

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
      skillhub:   # 腾讯 SkillHub 平台记录(含 namespace 字段)
        <fields>
      lenovo:     # 联想开放平台记录(无 namespace 字段)
        <fields>
```

### 记录字段

| 字段 | 说明 | 适用平台 |
|------|------|----------|
| `version` | 同步时的版本号 | 三者 |
| `last_sync` | 最后同步时间 (ISO 8601) | 三者 |
| `git_hash` | 同步时的 commit hash | 三者 |
| `status` | `synced` / `pending` / `failed` / `skipped` / `slug_conflict` / `deleted` | 三者 |
| `changelog_summary` | 变更摘要 | 三者 |
| `url` | 平台发布地址 | 三者 |
| `publish_id` | 平台内部 ID | 三者 |
| `namespace` | 命名空间（账号绑定，如 `cat-xierluo`；发布时不传，记录用于溯源安装命令） | **仅 SkillHub**（ClawHub / 联想无 namespace 概念） |

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
      lenovo:
        # 无 namespace:联想用 OAuth 双 token(Login Token + Biz Token)
        version: "1.1.8"
        last_sync: "2026-08-12T10:00:00+08:00"
        git_hash: "fbb1db4"
        status: synced
        changelog_summary: "首次发布联想开放平台"
        url: "https://open.lenovomm.com/skills/md2word"
        publish_id: "len_xxxxxxxxxxxxxxxx"
```

### 用途

1. **增量同步**：只同步 `status: pending` 或版本更新的 skill（按平台独立判断）
2. **溯源**：通过 `git_hash` 追溯发布时的代码状态
3. **快速访问**：通过 `url` 直接访问平台上的 skill 页面
