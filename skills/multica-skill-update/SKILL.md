---
name: multica-skill-update
description: Multica 工作区 Skill 同步工具。当需要把本地来源清单（GitHub / ClawHub / skills.sh / 本地文件）批量导入或更新到 Multica 的 skill 数据库时使用，支持 init（初始化导入）、update（更新刷新）、plan（预览）三种模式。同步目标始终是 Multica skill 数据库，不是本地 `.codebuddy/skills/` 路径。
license: MIT
author: 杨卫薪律师（微信ywxlaw）
homepage: https://github.com/cat-xierluo/legal-skills
version: "0.4.0"
---

# Multica Skill 同步工具

把一份**可维护的来源清单（`config/manifest.local.json`）**中的 skill，批量导入/更新到 **Multica 工作区 skill 数据库**，让"安装/更新一批 skill"变成一条命令或一个定时任务。

## 什么时候用

- 你（或 Orion / Autopilot）需要把多个 skill 从外部来源装进 Multica，且来源会更新。
- 手动逐条 `import` 易漏、易忘版本——用本 skill 按清单批量执行。
- 需要周期性刷新（每周定时）Multica 里的 skill 到最新版本。

## 核心原则（必须遵守）

1. **同步对象 = Multica skill 数据库**，不是本地 `.codebuddy/skills/` 路径。本地路径是平台下发的，改它不会让 agent 读到，还易被覆盖。
2. **本 skill 只负责"怎么做"**（逻辑/清单格式/步骤），不负责"什么时候跑"——定时由 Multica Autopilot 的 CRON 触发。
3. **来源刷新必须走 `import --on-conflict overwrite`**，不是 `multica skill update`（见下方"关键澄清"）。
4. **清单由维护者录入**：把来源 URL 写进 skill 内部的 `config/manifest.local.json` 再安装回 Multica。

## 文件结构

```
multica-skill-update/
├── SKILL.md                      # 本入口文档
├── config/
│   └── manifest.local.json       # 个人来源清单（你维护，含本地文件路径/云端地址；已被 .gitignore 忽略，不入库）
├── .gitignore                    # 忽略 config/manifest.local.json（个人清单含本机路径，不进公开仓库）
├── references/
│   └── manifest.example.json     # 清单模板（复制后填入真实来源；此模板入库）
└── scripts/
    └── sync_skills.py            # init/update/plan 三模式执行脚本
```

> **个人清单机制**：`config/manifest.local.json` 是你的私有同步清单——既可以录入**本地 skill 文件**（`source: "file"`，`url` 写本机路径，如 `/path/to/skill.skill` 或 `.zip`），也可以录入**云端 skill 地址**（`source: "github" | "clawhub" | "skills.sh"`，`url` 写对应 URL）。它已被本 skill 的 `.gitignore` 忽略，**不会进入公开仓库**；`references/manifest.example.json` 只是模板（入库），供他人复制填写。首次使用：
>
> ```bash
> cp references/manifest.example.json config/manifest.local.json
> # 编辑 config/manifest.local.json：本地 skill 用 source=file + 本机路径；云端用 source=github/clawhub/skills.sh + URL
> ```

## 依赖

### 系统依赖

| 依赖 | 安装方式 |
|------|----------|
| `multica` CLI | 独立安装：macOS/Linux: `curl -fsSL https://raw.githubusercontent.com/multica-ai/multica/main/scripts/install.sh \| bash` 或 `brew install multica-ai/tap/multica`<br>Windows: `irm https://raw.githubusercontent.com/multica-ai/multica/main/scripts/install.ps1 \| iex`<br>验证：`multica version` |

**CLI 实际可用路径（本机实测）**：Multica 桌面 App 已内置独立 CLI 二进制，无需单独安装：

```bash
# App 内置 CLI（Go 二进制，v0.4.19+）
MULTICA_BIN="/Applications/Multica.app/Contents/Resources/app.asar.unpacked/resources/bin/multica"
"$MULTICA_BIN" version        # → multica v0.4.19 ...

# 该 CLI 需要指定 App 使用的 profile 才能连上 daemon/server
"$MULTICA_BIN" --profile desktop-api.multica.ai workspace list --output json
```

- 前置要求：Multica 桌面 App / daemon 已在运行（CLI 与 server/daemon 通信）。
- **profile**：App 自动运行时用的 profile 名通常是 `desktop-api.multica.ai`（对应 `~/.multica/profiles/<name>/config.json`）；CLI 默认用 `default` profile 会报 `No server configured. Run 'multica setup' first.`，此时需显式加 `--profile`。
- **workspace**：`skill list` 等命令要求 `--workspace-id` 或 `--workspace-slug`；`multica --profile <p> workspace list --output json` 可查。
- 脚本已做预检：`multica` 不在 PATH 时输出安装提示并退出码 2；真实调用可用 `--multica-bin` 指向 App 内置路径。

## 清单格式（config/manifest.local.json）

```json
{
  "version": 1,
  "skills": [
    {
      "name": "review-helper",
      "source": "github",
      "url": "https://github.com/owner/repo",
      "on_conflict": "overwrite",
      "enabled": true
    },
    {
      "name": "doc-gen",
      "source": "github",
      "url": "https://github.com/owner/doc-skill",
      "on_conflict": "skip",
      "enabled": true
    }
  ]
}
```

字段说明：

| 字段 | 取值 | 说明 |
|------|------|------|
| `version` | `1` | 清单格式版本 |
| `skills[].name` | 字符串 | 技能名（仅作报告标识） |
| `skills[].source` | `github` \| `clawhub` \| `skills.sh` \| `file` | 来源类型；`import` 对 URL 来源用 `--url`，`file` 用 `--file` |
| `skills[].url` | URL 或本机路径 | 来源地址；`source=file` 时为本机路径，支持**技能目录**（含符号链接，脚本自动打包成临时 zip）或 `.skill`/`.zip` 归档 |
| `skills[].on_conflict` | `fail`(默认) \| `overwrite` \| `rename` \| `skip` | 同名冲突策略 |
| `skills[].enabled` | `true` \| `false` | `false` 跳过该条，方便临时停用不删记录 |
| `skills[].category` | `development` \| `legal-document` \| `content-writing` 等 | **分类标签（仅存于本地清单，用于按 agent 维度筛选导入）**。Multica 服务端不支持 skill 标签，标签不参与导入，仅作 `--category` 过滤维度 |
| `skills[].group` | 字符串 | 人类可读的分组说明（与 `category` 对应，如 `legal-document / 法律文档`），仅展示用 |

> **分类标签的用途**：Multica 各 Agent 需要配置的 skill 类型不同。给清单每条打 `category` 后，
> 可用 `--category <值>` 只把某一类导入/刷新到工作区，便于「针对性给某个 agent 配一批 skill」。
> 分类维度复用本仓库 `project-init` 的 profile 分法（development / legal-document / content-writing）。

## 使用步骤

### 1. 准备清单

`config/manifest.local.json` 是个人清单（已被 `.gitignore` 忽略，不进 Git）。首次使用复制模板并填入真实来源：

```bash
cp references/manifest.example.json config/manifest.local.json
# 编辑 config/manifest.local.json：本地 skill 用 source=file + 本机路径；云端用 source=github/clawhub/skills.sh + URL
```

- 本地 skill **目录**（推荐，含符号链接）：`{"name": "xxx", "source": "file", "url": "/path/to/skills/xxx", "on_conflict": "overwrite", "enabled": true}`
  —— 脚本自动打包成临时 zip 再上传，用完即删，无需手工压缩。
- 本地 skill 归档：`{"name": "xxx", "source": "file", "url": "/path/to/xxx.skill", ...}`（`.skill` 或 `.zip`）
- 云端 skill：`{"name": "xxx", "source": "github", "url": "https://github.com/owner/xxx", "on_conflict": "skip", "enabled": true}`

### 2. 执行同步

```bash
# 初始化导入（同名已存在视为正常，不报错）
python scripts/sync_skills.py --mode init

# 更新刷新（on_conflict 按清单策略：overwrite 刷新 / skip 跳过非本人）
python scripts/sync_skills.py --mode update

# 预览将执行的操作，不实际调用 import
python scripts/sync_skills.py --mode plan

# 按分类筛选：只导入某类 skill（便于针对某个 agent 配置）
python scripts/sync_skills.py --mode init  --category legal-document
python scripts/sync_skills.py --mode update --category development

# 指定清单路径 / dry-run 只打印命令
python scripts/sync_skills.py --manifest config/manifest.local.json --mode init
python scripts/sync_skills.py --dry-run
```

**连接参数（本机实测必需）**：使用 Multica 桌面 App 内置 CLI 时，通常需要显式指定 profile 与 workspace：

```bash
# 先查 workspace（用 App 的 profile）
MULTICA="/Applications/Multica.app/Contents/Resources/app.asar.unpacked/resources/bin/multica"
"$MULTICA" --profile desktop-api.multica.ai workspace list --output json
# → [{"id": "...", "name": "xierluo", "slug": "xierluo"}]

# 同步时带上 profile + workspace-id
python scripts/sync_skills.py --mode update \
  --profile desktop-api.multica.ai \
  --workspace-id <workspace-id>
```

- 脚本会自动探测 multica CLI（PATH → App 内置）；也可用 `--multica-bin /path/to/multica` 显式指定。
- 不指定 profile 时默认 `default`，可能报 `No server configured`——用 `--profile desktop-api.multica.ai`（对应 App 运行 profile，见 `~/.multica/profiles/`）。
- 完整示例见下方"真实调用示例"。

### 3. 查看报告

每次运行输出结构化小结：

```
=== 同步报告 ===
imported: 3 (created 1, updated 2)
conflict(existed): 1
skipped: 1 (not creator 1, disabled 0)
failed: 0
```

- `imported`：成功导入（created=新建，updated=覆盖刷新）
- `conflict(existed)`：同名已存在，按策略跳过
- `skipped`：`not creator`（非本人创建的 overwrite/skip 跳过）+ `disabled`（enabled=false）
- `failed`：真实失败（URL 无效、非法策略等）——**有失败时退出码非零**，便于 Autopilot/CI 感知

## 真实调用示例（本机实测）

以下命令在 Multica 桌面 App + 内置 CLI 环境实测通过：

```bash
# 0) 定位 CLI 与 workspace
MULTICA="/Applications/Multica.app/Contents/Resources/app.asar.unpacked/resources/bin/multica"
"$MULTICA" --profile desktop-api.multica.ai workspace list --output json
# → [{"id": "043a79ce-...", "name": "xierluo", "slug": "xierluo"}]

# 1) 预览（plan）
python scripts/sync_skills.py --manifest references/manifest.example.json \
  --mode plan --profile desktop-api.multica.ai \
  --workspace-id 043a79ce-69f5-464e-891b-3a7bbca344a4

# 2) 初始化导入（update 同理）
python scripts/sync_skills.py --mode init \
  --profile desktop-api.multica.ai \
  --workspace-id 043a79ce-69f5-464e-891b-3a7bbca344a4
```

实测要点：
- `workspace list` 成功 → 连接正常。
- `skill import --file` 需要 `.skill`/`.zip` 归档，**不接受目录**——脚本自动打包解决。
- 本地目录导入实测通过：`git-batch-commit`、`git-workflow`、`legal-ocr` 均成功落库。
- 重复导入同一目录，服务端返回 `status: updated` 且 **skill ID 不变**（`f7d522b6...`），验证 `overwrite` 保留 ID 语义属实。
- `on_conflict` 四种策略实测均按内置 skill 文档所述行为：`fail`→`conflict`、`skip`→`skipped`、`overwrite`→`updated`。
- 服务端偶发 `temporarily unavailable`（连接检查会误报未连接），重跑即可，属 Multica 服务端抖动。

## 与平台内置 `multica-skill-importing` 的分工

Multica 平台内置了一个 **`multica-skill-importing`** skill（`user-invocable: false`，随平台更新覆盖，**不可修改**）。本 skill 与它是**上下游关系，不是竞争关系**：

| | 内置 `multica-skill-importing` | 本 skill `multica-skill-update` |
|---|---|---|
| 职责 | 导入**单个**已知 URL/slug 的 skill | 按**清单批量**导入/刷新 |
| 输入 | 一个具体 URL 或 slug | `config/manifest.local.json`（N 条来源） |
| 触发 | 平台内部调用（不可被用户直接唤起） | 用户/Autopilot 主动调用 |
| 关注点 | 单次导入的正确性与结果解读 | 批量编排、幂等、报告、定时 |

**协调原则**：内置 skill 定义了「单条导入的权威语义」，本 skill **严格复用同一套语义**，不另立标准——它变我变，避免行为漂移。具体对齐了以下几点：

1. **唯一合法路径**：`POST /api/skills/import`（即 `multica skill import`）。绝不用 `npx skills add`（装到本地环境，Multica 无法管理），也绝不用 `multica skill update`（只改字段，不拉来源）。
2. **结构化结果信封**：不猜 exit code、不做字符串匹配，直接读 `status` 字段：

   ```json
   {"status": "created|updated|conflict|skipped|failed",
    "reason": "...", "skill": {...},
    "existing_skill": {"id": "...", "name": "...", "can_overwrite": true}}
   ```

   脚本 `_handle_result()` 逐一映射这五种 status，并在 `can_overwrite=false` 时把 `failed` 归类为「非本人创建」而非真实错误。旧版服务端只回 `409 + {error, existing_skill}` 或纯字符串时，回退到字符串判断。
3. **`overwrite` 的确切语义**：保留 skill ID、`created_by`、`created_at` **及 agent 绑定**，只替换 description/content/config/supporting files；且**仅原创建者可执行**。这正是"刷新同步"想要的语义，也是清单默认用 `overwrite` 的依据。
4. **服务端硬限制**（脚本在打包后预检并告警，不阻断）：

   | 限制 | 阈值 |
   |------|------|
   | 单文件 | 1 MiB |
   | 整包（解压后） | 8 MiB |
   | 文件数 | 256 |
   | 上传（压缩后） | 16 MiB |

5. **服务端会丢弃的内容**：dotfiles、`__MACOSX`、license 文件、二进制资产。本地打包时提前剔除，省流量也让预检数字贴近真实。
6. **`SKILL.md` 是保留文件名**：支持文件若也叫 `SKILL.md`（如 `references/SKILL.md`），导入**仍会成功但该文件被静默丢弃**。脚本会显式告警，避免"文件莫名消失"。
7. **zip 布局**：服务端 root 到**最浅的 `SKILL.md`**，顶层目录名仅作 name 兜底（frontmatter `name` 优先）。所以 `my-skill/SKILL.md` 嵌套布局与根级 `SKILL.md` 都被接受，本 skill 采用前者。
8. **agent 绑定用 `add` 不用 `set`**：`add` 追加，`set` 会**清空该 agent 所有现有绑定**再写入。本 skill 目前不动绑定关系；若将来扩展，只用 `add`。

> **为什么要排除 `archive/` 等工作产物目录**：实测 `legal-ocr` 的 `archive/` 达 7.6 GB / 11 万文件，整包打进去必然触发全部四项限制。剔除后仅 21 个文件 / 82 KB，导入成功。同类目录（`output/`、`tmp/`、`.cache/`、`node_modules/` 等）已一并加入排除名单，见 `scripts/sync_skills.py` 的 `PACK_EXCLUDE_DIRS`。

## 反向溯源：在 Multica 发现问题后改本地源文件

**核心前提**：本清单里 `source=file` 的 `url` 指向**本机仓库里的真实 skill 目录**（不是服务端副本）。
因此 Multica 工作区里的 skill 是本地源的"投影"——**永远改本地源，再重导，绝不改服务端投影**。

**溯源依据**：
1. 清单 `url` 字段 = 本地源文件路径（导入时打包的就是它）。
2. 服务端导入结果信封里的 `config.origin` 也记录了来源（`source: file` 时为本地路径），
   与清单 `url` 互为印证，可据此在 Multica 侧反查"这个 skill 来自本地哪个文件"。

**标准工作流**（本 skill 不自动执行修改，只约定流程）：

1. 在 Multica 使用某 skill 发现问题 → 记下 skill 名（如 `contract-copilot`）。
2. 在本清单定位该条，取其 `url`（如 `.../skills/contract-copilot`）→ 这就是要改的源文件根目录。
3. 直接编辑本地源文件（`SKILL.md` / `scripts/` / `references/` 等），走该 skill 正常的
   `DECISIONS.md` / `CHANGELOG.md` / git 提交流程。
4. 改完重导：`python scripts/sync_skills.py --mode update --category <该skill分类>`（或指定单条）。
   `overwrite` 会保留 skill ID 与 agent 绑定，仅刷新内容。

> **为什么不在 Multica 内直接改**：`skill get` 能取回文件、但服务端对 SKILL.md 是"保留文件名"
> （只改 primary content，支持文件需走独立单文件端点且对同名 SKILL.md 静默丢弃）。改服务端投影
> 既不可追溯、又会被下次 `import` 覆盖，还会让"本地源"与"线上版本"分叉。一切以本地源为准。

## 关键澄清（实现时已写入，勿再混淆）

- **`multica skill update <id>` ≠ 从来源重新拉取。** 它只是按 ID 编辑某个已存在 skill 的字段（name/description/content/config），**不会去 GitHub 拉最新**。所以"同步来源"这一步永远用 `import --on-conflict overwrite`，而不是 `skill update`。
- **`import` 的 `--url` 与 `--file` 互斥**；来源在 GitHub / ClawHub / skills.sh 上就用 `--url`。
- **`overwrite` 仅限原始创建者**执行；非创建者会失败。清单里对非本人来源用 `skip`，避免 `failed` 噪音。
- **`--on-conflict` 默认 `fail`**：同名冲突时停止且不修改已有内容。清单里未写明策略的条目按 `fail` 处理（会报告为 failed）。
- `--output json` 是推荐的脚本解析格式（官方文档明确"脚本应使用 JSON 输出而非解析表格"）。

## 定时刷新（Multica Autopilot 集成）

Autopilot 负责"定时"，本 skill 负责"怎么做"。建一个每周 CRON 的 autopilot，派 agent 以 `mode=update` 调用本 skill：

```bash
# 创建 autopilot（--mode create_issue：先建 issue 再派发给 agent）
multica autopilot create --title "Weekly skill sync" \
  --agent <agent-name> --mode create_issue --output json

# 添加每周一 9:00（Asia/Shanghai）的定时触发器
multica autopilot trigger-add <autopilot-id> \
  --kind schedule --cron "0 9 * * 1" --timezone Asia/Shanghai --output json
```

- 手动触发：`multica autopilot trigger <autopilot-id>`
- 查看运行历史：`multica autopilot runs <autopilot-id>`
- cron 为 5 字段（`minute hour day month weekday`，无秒），时区用 IANA 名。
- 执行模式建议 `create_issue`：agent 跑完后结果留在 issue 上，便于复盘；`run only` 结果只在运行历史里。

> ⚠️ 注意：`autopilot create` 的实际 flags 以本机 `multica autopilot create --help` 为准（文档标注 `--title --agent --mode` 为必填，另有 `--priority --project --subscriber`）；`trigger-add` 的 flags 也请先 `--help` 确认。

## 验收标准

1. skill 安装后，`multica skill list` 能看到 `multica-skill-update`。
2. 用 `init` 模式、带一份含 ≥2 条来源的 manifest，能成功导入（或正确报告已存在）。
3. 修改来源内容后，用 `update` 模式能刷新到最新（报告 `updated`）。
4. 非本人创建的技能按 `skip` 策略被跳过，不产生 `failed` 噪音。
5. 接上每周 Autopilot 后，无需手动干预即可周期性同步。
