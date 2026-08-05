---
name: dingtalk-minutes
description: 钉钉 AI 听记（妙记）读取封装。当用户要查询/读取 AI 听记的列表、摘要、语音转写原文（逐字稿）、关键词、待办或音频地址时使用。基于 dws CLI（钉钉官方 Workspace CLI）。写文档走 dingtalk-doc，建待办走 dingtalk-todo，日程走 dingtalk-calendar。
license: MIT
author: 杨卫薪律师（微信ywxlaw）
version: "0.2.0"
homepage: https://github.com/cat-xierluo/legal-skills
metadata:
  cli_version: ">=1.0.15"
  category: product
  requires:
    bins:
      - dws
---

# 钉钉 AI 听记读取 Skill（薄壳封装）

本技能是对 `dws`（钉钉官方 Workspace CLI）中 `minutes` 服务的**读取能力封装**，聚焦"查询与读取 AI 听记内容"——不含写入/修改/录音控制等写操作。所有命令均通过 `dws` 执行，不绕开 CLI 直接调 HTTP API。

> 底层命令参考：[references/minutes.md](references/minutes.md)；剧本/实战：[references/07-minutes.md](references/07-minutes.md)；速查：[references/lite-recipes.md](references/lite-recipes.md)；通用规范：[references/_common/conventions.md](references/_common/conventions.md)。
> **首次部署必读（安装/授权/踩坑）**：[references/setup-troubleshooting.md](references/setup-troubleshooting.md)。

## 依赖

### 系统依赖

| 依赖 | 安装方式 |
|------|----------|
| `dws`（钉钉官方 Workspace CLI） | macOS/Linux：`curl -fsSL https://raw.githubusercontent.com/DingTalk-Real-AI/dingtalk-workspace-cli/main/scripts/install.sh \| sh`（注意路径是 `scripts/install.sh`，非根目录 `install.sh`） |
| `python3`（同步脚本用） | macOS 通常自带；如缺失 `brew install python` |
| `curl`（安装脚本用） | macOS 通常自带；如缺失 `brew install curl` |

**PATH 配置**：dws 默认装到 `~/.local/bin`，需加入 shell PATH：

```bash
grep -q '.local/bin' ~/.zshrc || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
```

### 授权与组织开关（缺一不可）

本 skill 依赖三项独立前置条件，任一步缺失都无法读取：安装 dws → 开启组织「CLI 访问管理」开关 → 授权登录。详细步骤、开关反直觉语义、授权必须后台运行等坑，见 [references/setup-troubleshooting.md](references/setup-troubleshooting.md)。

### 开箱即用与需依赖功能

- **开箱即用**：本 skill 的核心读取命令（list / +detail / get *）均为对 dws 的调用，装好 dws 并授权后即可用。
- **需本地 Python**：`scripts/sync.py`（本地归档与增量同步）、`minutes_extract_todos.py` 等脚本需 `python3`（仅标准库，无第三方包依赖）。

## 前置条件

1. **已安装 dws**：`dws version` 可正常返回（见上方「依赖」安装说明）。
2. **已授权**：`dws auth status` 显示 `authenticated: true`。授权用 `dws auth login --device`（**后台运行**，扫码后等回调完成，见踩坑文档）。
3. **组织开关已开**：钉钉开放平台 → 开发者平台 → 更多 → 基本信息 → CLI 访问管理，开关文案为「禁止所有成员使用 CLI」时需**关闭**它才是允许（详见踩坑文档）。
4. 所有 `dws` 命令**必须带 `--format json`** 以获取可解析输出。

## 核心能力（读取）

| 用户意图 | 命令 |
|----------|------|
| 列出我的听记 | `dws minutes list mine [--query "<关键词>"] [--start "<ISO>"] [--end "<ISO>"]` |
| 列出我可访问的全部听记（含他人共享） | `dws minutes list all` |
| 列出他人共享给我的 | `dws minutes list shared` |
| 一条取全（基础信息/摘要/关键词/逐字稿/待办） | `dws minutes +detail --uuid <taskUuid>` |
| 读取 AI 摘要 | `dws minutes get summary --id <taskUuid>` |
| 读取语音转写原文（逐字稿） | `dws minutes get transcription --id <taskUuid>` |
| 读取关键词 | `dws minutes get keywords --id <taskUuid>` |
| 读取待办事项 | `dws minutes get todos --id <taskUuid>` |
| 读取音频下载地址 | `dws minutes get audio --id <taskUuid>` |
| 近期听记摘要合并 | `python scripts/minutes_recent_summary.py --max 5` |
| 提取某篇会议待办 | `python scripts/minutes_extract_todos.py --id <taskUuid>` |

## 标准 SOP

### SOP-1 查听记列表（query-minutes）

1. **选 scope（铁律）**：`mine`=我创建/发起；`shared`=他人共享给我；`all`=我可访问的全部（mine∪shared）。用户说"我能访问/可见/所有/我的听记"一律 `all`；仅明确"我创建的/我发起的"才用 `mine`。
2. **执行**：`dws minutes list all|mine|shared --format json`；关键词加 `--query`，时间加 `--start/--end`，限条数 `--max <n>`，翻页 `--next-token <token>`。
3. **解析**：从 `itemList[]` 取真实 `taskUuid` + `title` + 时间；多候选让用户确认，禁止默认取第一条。

### SOP-2 取听记详情（get-minute-detail）

1. **前置**：先按 SOP-1 拿到目标 `taskUuid`。
2. **执行（按需选一）**：`get summary` / `get transcription` / `get keywords` / `get todos` / `get info` / `get audio`，全部带 `--format json`。
3. **转写翻页（必须）**：`get transcription` 单次最多返回约 50 段，返回含 `nextToken` 时**必须**继续 `--next-token` 翻页拉全，再总结。
4. **解析**：`--id`/`--uuid`/`--task-uuid` 等价，**推荐统一用 `--id`**；禁止编造 taskUuid。

## 高频硬约束

- **URL 自动提取**：用户给 `shanji.dingtalk.com/app/transcribes/<taskUuid>` 类链接时，自动提取 hex 串作 `--id`，禁止把整条 URL 当参数、禁止用浏览器打开。
- **时间自行计算**：用户说今天/本周/上周/最近 N 天/某日期范围时，自行算 `--start/--end`（ISO-8601，如 `2026-05-11T00:00:00+08:00`），不要反问。
- **服务端过滤优先**：时间范围和关键词能服务端过滤时，必须放进同一条 `list all --start --end --query`，不要全量拉回本地过滤。
- **空列表兜底**：同范围 `list all` → 去掉关键词保留时间 → 明确告知无数据。禁止虚构听记内容生成纪要。
- **先取数再生成**：生成纪要/文档/待办前，必须先 `list` → 锁定真实 `taskUuid` → `get summary`（需原文/行动项再 `get transcription`/`get todos`）。数据没拿到就停止说明卡点。
- **导出原文不降级**：用户要"下载/导出逐字稿"时，必须逐条 `get transcription` 并翻页到结束，不能降级为摘要。
- **禁止 shell 管道**：不要用 `|`、`head`、`grep`、`jq` 截断输出；用 `--format json` 在内存处理。

## 本地归档与增量同步（archive / sync）

本技能支持把钉钉 AI 听记**同步到技能内的 `archive/` 目录**，形成本地留底，避免遗忘历史内容、并只增量拉取新听记。

### 存档结构

```
archive/
├── index.json                 # 同步状态：last_sync(上次同步时间) + synced_uuids(已同步集合)
└── <uuid>/
    ├── meta.json              # 列表元数据 + 摘要(summary) + 待办(todos) + 关键词
    └── transcript.md          # 语音转写逐字稿（已翻页拉全，含【发言人 N】前缀）
```

### 同步命令

```bash
python scripts/sync.py                  # 增量同步：仅拉取 last_sync 之后的新听记
python scripts/sync.py --full           # 全量重扫（已存在 uuid 跳过，不重复拉逐字稿）
python scripts/sync.py --list-new       # 只列出本次新增标题，不拉逐字稿
python scripts/sync.py --dry-run        # 预览将执行的 dws 命令，不写文件
python scripts/sync.py --archive-dir /path/to/archive   # 指定存档目录
```

### 增量原理

1. 读取 `archive/index.json` 的 `last_sync` 作为 `dws minutes list all --start <last_sync>` 的参数，服务端只返回该时间之后的听记。
2. 本地 `synced_uuids` 中已有的跳过，避免重复拉取。
3. 对每条新听记：拉 `get transcription`（翻页拉全）存 `transcript.md`，拉 `get summary`/`get todos`/`get keywords` 存 `meta.json`。
4. 更新 `index.json`：把最新听记的 `startTimeISO` 写入 `last_sync`，uuid 并入 `synced_uuids`。

### 使用约定

- 首次运行无 `index.json` → 全量扫描（受 dws 列表分页限制，脚本自动翻页）。
- 想知道"上次同步到哪、本次新增了什么"→ 看脚本输出的 `last_sync` 与新增标题清单，或直接读 `archive/index.json`。
- 存档目录按 AGENTS.md 约定加入 `.gitignore`（或纳入私有仓库单独管理），避免把逐字稿误提交到公开仓库。

## 跨产品协作

- 把待办批量建任务 → 切 `dingtalk-todo`
- 把摘要发同事 → 切 `dingtalk-chat`
- 日程/会议室 → 切 `dingtalk-calendar`
- 落盘成文档 → 切 `dingtalk-doc`

## 本技能范围边界（薄壳）

- ✅ 仅封装**读取**能力：列表、摘要、转写、关键词、待办、音频地址、近期合并、待办提取脚本。
- ❌ 不含写操作：修改标题/摘要（`update`）、全文替换（`replace-text`/`+replace-batch`）、上传音频（`upload`）、录音控制（`record`）、权限管理（`permission`）、发言人匹配/校正。如需这些，直接调用 `dws minutes <cmd>` 或参考完整 `minutes.md`。

## 依赖

系统依赖：需安装 `dws`（钉钉官方 Workspace CLI，version >= 1.0.15）。

Python 包：无第三方依赖（`scripts/` 下脚本使用标准库）。

## 参考与致谢

- 命令契约源自钉钉官方 `dingtalk-workspace-cli` 内置 `dingtalk-minutes` skill（references/minutes.md 等），本技能在其基础上精简为只读薄壳。
