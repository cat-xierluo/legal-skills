---
name: multica-skill-update
description: Multica 工作区 Skill 同步工具。当需要把本地来源清单（GitHub / ClawHub / skills.sh / 本地文件）批量导入或更新到 Multica 的 skill 数据库时使用，支持 init（初始化导入）、update（更新刷新）、plan（预览）三种模式。同步目标始终是 Multica skill 数据库，不是本地 `.codebuddy/skills/` 路径。
license: MIT
author: 杨卫薪律师（微信ywxlaw）
homepage: https://github.com/cat-xierluo/legal-skills
version: "0.3.0"
---

# Multica Skill 同步工具

把一份**可维护的来源清单（manifest.json）**中的 skill，批量导入/更新到 **Multica 工作区 skill 数据库**，让"安装/更新一批 skill"变成一条命令或一个定时任务。

## 什么时候用

- 你（或 Orion / Autopilot）需要把多个 skill 从外部来源装进 Multica，且来源会更新。
- 手动逐条 `import` 易漏、易忘版本——用本 skill 按清单批量执行。
- 需要周期性刷新（每周定时）Multica 里的 skill 到最新版本。

## 核心原则（必须遵守）

1. **同步对象 = Multica skill 数据库**，不是本地 `.codebuddy/skills/` 路径。本地路径是平台下发的，改它不会让 agent 读到，还易被覆盖。
2. **本 skill 只负责"怎么做"**（逻辑/清单格式/步骤），不负责"什么时候跑"——定时由 Multica Autopilot 的 CRON 触发。
3. **来源刷新必须走 `import --on-conflict overwrite`**，不是 `multica skill update`（见下方"关键澄清"）。
4. **清单由维护者录入**：把来源 URL 写进 skill 内部的 `manifest.json` 再安装回 Multica。

## 文件结构

```
multica-skill-update/
├── SKILL.md                      # 本入口文档
├── manifest.json                 # 个人来源清单（你维护，含本地文件路径/云端地址；已被 .gitignore 忽略，不入库）
├── .gitignore                    # 忽略 manifest.json（个人清单含本机路径，不进公开仓库）
├── references/
│   └── manifest.example.json     # 清单模板（复制后填入真实来源；此模板入库）
└── scripts/
    └── sync_skills.py            # init/update/plan 三模式执行脚本
```

> **个人清单机制**：`manifest.json` 是你的私有同步清单——既可以录入**本地 skill 文件**（`source: "file"`，`url` 写本机路径，如 `/path/to/skill.skill` 或 `.zip`），也可以录入**云端 skill 地址**（`source: "github" | "clawhub" | "skills.sh"`，`url` 写对应 URL）。它已被本 skill 的 `.gitignore` 忽略，**不会进入公开仓库**；`references/manifest.example.json` 只是模板（入库），供他人复制填写。

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

## 清单格式（manifest.json）

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
| `skills[].url` | URL 或本机路径 | 来源地址；`source=file` 时为本地 skill 包路径 |
| `skills[].on_conflict` | `fail`(默认) \| `overwrite` \| `rename` \| `skip` | 同名冲突策略 |
| `skills[].enabled` | `true` \| `false` | `false` 跳过该条，方便临时停用不删记录 |

## 使用步骤

### 1. 准备清单

`manifest.json` 是个人清单（已被 `.gitignore` 忽略，不进 Git）。首次使用复制模板并填入真实来源：

```bash
cp references/manifest.example.json manifest.json
# 编辑 manifest.json：本地 skill 用 source=file + 本机路径；云端用 source=github/clawhub/skills.sh + URL
```

- 本地 skill 文件：`{"name": "xxx", "source": "file", "url": "/path/to/xxx.skill", "on_conflict": "overwrite", "enabled": true}`
- 云端 skill：`{"name": "xxx", "source": "github", "url": "https://github.com/owner/xxx", "on_conflict": "skip", "enabled": true}`

### 2. 执行同步

```bash
# 初始化导入（同名已存在视为正常，不报错）
python scripts/sync_skills.py --mode init

# 更新刷新（on_conflict 按清单策略：overwrite 刷新 / skip 跳过非本人）
python scripts/sync_skills.py --mode update

# 预览将执行的操作，不实际调用 import
python scripts/sync_skills.py --mode plan

# 指定清单路径 / dry-run 只打印命令
python scripts/sync_skills.py --manifest /path/to/manifest.json --mode init
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
- `workspace list` 成功 → 连接正常；`skill list` 返回 `[]` → 当前工作区无 skill。
- `skill import --url <clawhub/github 真实 URL>` 命令格式正确（服务端偶发"temporarily unavailable"是 Multica 服务端问题，非命令错误）。
- `skill import --file` 需要 `.skill`/`.zip` 归档，不能是单个 SKILL.md。

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
