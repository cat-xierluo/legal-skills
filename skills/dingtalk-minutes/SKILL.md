---
name: dingtalk-minutes
description: 钉钉 AI 听记（妙记）读取封装。当用户要查询/读取 AI 听记的列表、摘要、语音转写原文（逐字稿）、关键词、待办或音频地址时使用。基于 dws CLI（钉钉官方 Workspace CLI）。写文档走 dingtalk-doc，建待办走 dingtalk-todo，日程走 dingtalk-calendar。
license: MIT
author: 杨卫薪律师（微信ywxlaw）
version: "1.1.0"
homepage: https://github.com/cat-xierluo/legal-skills
metadata:
  cli_version: ">=1.0.15"
  category: product
  requires:
    bins:
      - dws
---

# 钉钉 AI 听记读取 Skill（薄壳封装）

本技能是对 `dws`（钉钉官方 Workspace CLI）中 `minutes` 服务的**读取能力封装**，聚焦"查询与读取 AI 听记内容"——**对钉钉服务端不含任何写入/修改/录音控制等写操作**（不调用 `update`/`upload`/`record` 等写命令）。所有读取均通过 `dws` 执行，不绕开 CLI 直接调 HTTP API。

> 说明：本技能"只读"指**不改动钉钉云端数据**；但归档（archive）、镜像（mirror）、可选音频下载均为**把已读取内容落到用户本地文件系统**的显式操作，需用户主动运行对应脚本并指定目录，不等同于越权外传。详见下文「本地归档与增量同步」「镜像到外部文件夹」章节。

> 命令参考（仅读取类）：[references/01-commands.md](references/01-commands.md)。
> **首次部署必读（安装/授权/踩坑）**：[references/02-setup.md](references/02-setup.md)。

## 依赖

### 系统依赖

| 依赖 | 安装方式 |
|------|----------|
| `dws`（钉钉官方 Workspace CLI） | macOS/Linux：先下载安装脚本再执行（见下方命令，注意路径是 `scripts/install.sh`，非根目录 `install.sh`） |
| `python3`（同步脚本用） | macOS 通常自带；如缺失 `brew install python` |
| `curl`（安装脚本用） | macOS 通常自带；如缺失 `brew install curl` |

**安装 dws**（先落到临时文件再执行，避免 `curl | sh` 直接执行远端脚本）：

```bash
curl -fsSL https://raw.githubusercontent.com/DingTalk-Real-AI/dingtalk-workspace-cli/main/scripts/install.sh -o /tmp/dws-install.sh
sh /tmp/dws-install.sh
```

**PATH 配置**：dws 默认装到 `~/.local/bin`，需加入 shell PATH。下列命令会修改你的 `~/.zshrc`（持久 shell 配置），仅追加一行 PATH 且幂等（已存在则跳过）；如不想自动改配置，可手动把 `export PATH="$HOME/.local/bin:$PATH"` 加到你的 shell 配置：

```bash
grep -q '.local/bin' ~/.zshrc || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
```

### 授权与组织开关（缺一不可）

本 skill 依赖三项独立前置条件，任一步缺失都无法读取：安装 dws → 开启组织「CLI 访问管理」开关 → 授权登录。详细步骤、开关反直觉语义、授权必须后台运行等坑，见 [references/02-setup.md](references/02-setup.md)。

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

> ⚠️ **隐私与合规提示**：听记逐字稿、摘要、待办可能包含客户机密、当事人隐私或内部业务信息。归档/镜像会把上述内容**写到本地文件系统**——请勿将 `archive/` 或镜像目标目录提交到公开仓库、共享目录或第三方同步服务；`archive/` 与本地镜像配置已默认加入 `.gitignore`。运行前请确认目标位置仅你本人可访问。

### 存档结构

```
archive/
├── index.json                 # 同步状态：last_sync(上次同步时间) + synced_uuids + uuid_to_dir(uuid→目录名映射)
└── <YYMMDD>_<标题>/           # 目录名：日期(两位年，如 260508) + 下划线 + 听记标题
    ├── meta.json              # 结构化元数据：uuid/标题/时间/时长/分享链接/创建人/关键词列表/音频信息
    ├── transcript.md          # 语音转写逐字稿（已翻页拉全，含【发言人 N】前缀）；文件头部含关键词/AI摘要/待办概览
    ├── summary.md             # AI 生成的完整摘要（fullSummary 全文）
    ├── keywords.md            # 关键词列表
    └── todos.md               # 待办事项（含负责人，来自 get todos 详细接口）
```

> 目标：内部 archive 尽量存全。单条听记可提取的全部文字信息都会落盘——逐字稿、AI 摘要、关键词、待办、音频下载地址与元数据。音频文件本身**默认不下载**（URL 带过期鉴权、单条约 150MB）；如需本地音频留底，运行 `python scripts/sync.py --with-audio`。
>
> 目录名示例：`260805_08-05 图书出版协作优化/`。同日期同标题冲突时追加短 uuid 后缀（如 `260805_xxx_3af2c1`）。去重与增量判定以 uuid 为准，目录名仅用于可读，通过 `index.json` 的 `uuid_to_dir` 回溯。

### 同步命令

```bash
python scripts/sync.py                  # 增量同步：仅拉取 last_sync 之后的新听记
python scripts/sync.py --full           # 全量重扫（已存在 uuid 跳过，不重复拉逐字稿）
python scripts/sync.py --list-new       # 只列出本次新增标题，不拉逐字稿
python scripts/sync.py --dry-run        # 预览将执行的 dws 命令，不写文件
python scripts/sync.py --archive-dir /path/to/archive   # 指定存档目录
python scripts/sync.py --no-mirror      # 本次只存档，不自动镜像到外部文件夹
```

> **自动镜像（默认开启）**：本次有新增存档且 `config/mirror-target.local.json` 存在时，同步完成后自动调用 `mirror_output.py` 增量镜像（sha256 校验，顺带补齐之前未镜像成功的文件）；未配置镜像目标时提示跳过，不影响存档。镜像失败也只报告——archive 是权威源。

### 增量原理

1. 读取 `archive/index.json` 的 `last_sync` 作为 `dws minutes list all --start <last_sync>` 的参数，服务端只返回该时间之后的听记。
2. 本地 `synced_uuids` 中已有的跳过，避免重复拉取。
3. 对每条新听记：目录名按 `YYMMDD_标题` 生成，拉 `get transcription`（翻页拉全）存 `transcript.md`，拉 `get summary`/`get todos`/`get keywords` 存 `meta.json`；uuid 与目录名映射记入 `uuid_to_dir`。
4. 更新 `index.json`：把最新听记的 `startTimeISO` 写入 `last_sync`，uuid 并入 `synced_uuids`。

### 使用约定

- 首次运行无 `index.json` → 全量扫描（受 dws 列表分页限制，脚本自动翻页）。
- 想知道"上次同步到哪、本次新增了什么"→ 看脚本输出的 `last_sync` 与新增标题清单，或直接读 `archive/index.json`。
- 存档目录按 AGENTS.md 约定加入 `.gitignore`（或纳入私有仓库单独管理），避免把逐字稿误提交到公开仓库。

## 镜像到外部文件夹（mirror）

把 archive 中的听记成品**单向复制**到外部指定文件夹（如 Obsidian / Clawd 知识库），供人工查阅。archive 是权威源，镜像**不回写 archive**、不改动同步状态。

**`sync.py` 有新增时默认自动镜像**（v1.1.0 起）——同步完成即自动执行下述镜像流程，无需手动跑本节命令；本节命令用于手动补漏、改目标、按日期/单条筛选等场景。

### 用法

```bash
# 默认按 config/mirror-target.local.json 的 dest 镜像全部听记
python scripts/mirror_output.py

# 只镜像指定日期（YYMMDD）之后开始的听记
python scripts/mirror_output.py --since 260801

# 只镜像单条听记（指定 archive 内目录）
python scripts/mirror_output.py --archive "archive/260805_08-05 图书出版协作优化"

# 覆盖目标目录 / 自定义白名单
python scripts/mirror_output.py --dest /path/to/output
python scripts/mirror_output.py --items transcript,summary,todos,keywords

# 预览将复制哪些文件，不写入
python scripts/mirror_output.py --dry-run
```

### 配置

复制模板为本地配置并编辑 `dest`：

```bash
cp config/mirror-target.example.json config/mirror-target.local.json
# 编辑 .local.json 的 dest 字段（本机实际路径）
```

`config/mirror-target.local.json` 已被 `.gitignore` 排除（本机特定路径，不入版本库）。配置文件缺失且未传 `--dest` 时退出码 2 并提示。

### 镜像内容（白名单）

| key | 文件 | 说明 |
|-----|------|------|
| `transcript` | `transcript.md` | 语音转写逐字稿（含概览） |
| `summary` | `summary.md` | AI 摘要全文 |
| `todos` | `todos.md` | 待办事项 |
| `keywords` | `keywords.md` | 关键词（可选） |
| `meta` | `meta.json` | 结构化元数据（可选） |

默认只镜像 `transcript,summary,todos`（三个 md）。**不复制** `meta.json`（除非显式加 `--items ... ,meta`），避免结构化内部数据外泄。缺失的文件跳过不报错（有些听记本身无 todos/summary）。

### 镜像目录结构

```text
<dest>/
├─ 260805_08-05 图书出版协作优化/
│   ├─ transcript.md
│   ├─ summary.md
│   ├─ todos.md
│   └─ .mirror-manifest.json     # 源路径 + 文件列表 + sha256，便于核对
└─ 260729_07-29 医疗损害鉴定听会/
    └─ ...
```

### 增量与校验

- 目标文件已存在且 sha256 一致 → 视为已镜像，跳过不覆盖（增量）。
- 每次镜像在听记子目录下写 `.mirror-manifest.json`（源 archive 路径、镜像时间、文件列表 + sha256），供事后核对。
- 镜像失败只报告，不影响 archive 与同步状态。

## 跨产品协作

- 把待办批量建任务 → 切 `dingtalk-todo`
- 把摘要发同事 → 切 `dingtalk-chat`
- 日程/会议室 → 切 `dingtalk-calendar`
- 落盘成文档 → 切 `dingtalk-doc`

## 本技能范围边界（薄壳）

- ✅ 仅封装**读取**能力：列表、摘要、转写、关键词、待办、音频地址、近期合并、待办提取脚本。
- ❌ 不含写操作：修改标题/摘要（`update`）、全文替换（`replace-text`/`+replace-batch`）、上传音频（`upload`）、录音控制（`record`）、权限管理（`permission`）、发言人匹配/校正。如需这些，直接调用 `dws minutes <cmd>` 或参考钉钉官方 dws 内置 `dingtalk-minutes` 完整文档。

## 依赖

系统依赖：需安装 `dws`（钉钉官方 Workspace CLI，version >= 1.0.15）。

Python 包：无第三方依赖（`scripts/` 下脚本使用标准库）。

## 参考与致谢

- 命令契约源自钉钉官方 `dingtalk-workspace-cli` 内置 `dingtalk-minutes` skill，本技能在其基础上精简为只读薄壳，命令参考见 [references/01-commands.md](references/01-commands.md)。
