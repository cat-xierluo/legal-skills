# AI 听记读取命令参考（薄壳）

本文件覆盖 `dingtalk-minutes` 薄壳所需的**全部读取类命令**。所有命令通过 `dws`（钉钉官方 Workspace CLI）执行，**必须带 `--format json`** 以获取可解析输出。

> 薄壳边界：仅读取，不含写操作（`update` / `replace-text` / `upload` / `record` / `permission` / `speaker` 等）。如需写操作，直接执行 `dws minutes <cmd>` 或切到对应写能力 skill。

## 命令层级（防混淆，必须先读）

```
dws minutes
├── list          # 列出听记（必须带 scope: mine | shared | all）
│   ├── mine      # 我创建的
│   ├── shared    # 他人共享给我的
│   └── all       # 我可访问的全部（含共享）
├── +detail       # 一条取全（基础信息/摘要/关键词/逐字稿/待办），参数 --uuid
└── get           # 单字段读取，参数 --id <taskUuid>
    ├── info          # 基础信息（标题/时长/时间/分享链接/创建人）
    ├── summary       # AI 摘要
    ├── transcription # 语音转写原文（逐字稿，需翻页）
    ├── keywords      # 关键词
    ├── todos         # 待办事项
    └── audio         # 音频下载地址
```

**高频参数陷阱**：
- `list` 后必须带 scope（`mine`/`shared`/`all`），裸 `list` 只打印帮助不返回数据。
- `+detail` 用 `--uuid`；`get` 下各子命令用 `--id`，且 `--id` **只接受 taskUuid**（hex 串），不接受完整 URL——需先从听记链接提取 uuid。
- `transcription` 在 `get` 下，不是顶层命令（错误：`dws minutes transcription`）。
- 逐字稿单次最多返回 50 段，需翻页（见下方「转写翻页」）。

## 列出听记

```bash
dws minutes list all   [--query "<关键词>"] [--start "<ISO>"] [--end "<ISO>"] [--max <N>] --format json
dws minutes list mine  [--query "<关键词>"] [--start "<ISO>"] [--end "<ISO>"] [--max <N>] --format json
dws minutes list shared [--max <N>] --format json
```

返回字段（每条）：`uuid`、`title`、`startTimeISO`、`endTimeISO`、`duration`、`keywords`、`shareUrl`、`creator`。

- `--start "<ISO>"` 服务端按开始时间过滤，用于增量（见 `scripts/sync.py`）。
- `--max` 单页上限，列表本身也可能分页；批量拉取用脚本循环 `--next-token`。

## 聚合取一条（最常用）

```bash
dws minutes +detail --uuid <taskUuid> --format json
```

返回五字段：`basic`（基础信息）、`keywords`、`summary`（AI 摘要）、`todos`（待办）、`transcript`（逐字稿原文）。一次拿到核心内容，优先用此命令。

## 单字段读取

```bash
dws minutes get info          --id <taskUuid> --format json
dws minutes get summary       --id <taskUuid> --format json
dws minutes get keywords      --id <taskUuid> --format json
dws minutes get todos         --id <taskUuid> --format json
dws minutes get audio         --id <taskUuid> --format json
```

- `get todos` 返回结构化行动项（可推成待办）。
- `get audio` 返回原音频下载地址，可本地保存。

## 转写翻页（transcription）

逐字稿单次最多 50 段，需循环翻页直到 `hasNext=false`：

```bash
dws minutes get transcription --id <taskUuid> --format json            # 第一页
dws minutes get transcription --id <taskUuid> --next-token <token> --format json   # 后续页
```

返回：`paragraphList`（每段含 `nickName`/`speakerDisplay`、`paragraph`、`sentenceList` 与时间戳）、`hasNext`、`nextToken`。

> 本 skill 的 `scripts/sync.py` 已封装翻页 + 落盘，无需手动循环。

## 错误响应诊断

| 报错 | 原因 | 处理 |
|------|------|------|
| `CLI data access is not enabled` | 组织未开 CLI 访问开关 | 见 `02-setup.md` 开启组织开关 |
| `该组织已禁止所有成员使用 CLI` | 开关被打开成"禁止" | 关掉该开关（见 `02-setup.md`） |
| `authenticated: false` | 授权未落盘 | 后台重跑 `dws auth login --device`（见 `02-setup.md`） |
| `invalid id` / 空结果 | `--id` 传了 URL 或错误 uuid | 提取 taskUuid（hex 串） |
| 逐字稿只看到前 1/3 | 未翻页 | 用 `--next-token` 循环 |

## 注意事项

- 逐字稿里的「发言人 1 / 发言人 2」是钉钉默认编号，声纹匹配（speaker 写操作）不在薄壳范围；要人名需在钉钉 App 内手动匹配。
- 所有时间字段为 ISO 8601（`startTimeISO` 等），增量同步以 `startTimeISO` 作锚点。
- 私有化/自建应用 Access Token 方式不在本 skill 范围；本 skill 面向个人账号 OAuth（device 模式）。
