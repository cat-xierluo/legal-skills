# mail-cli 完整命令参考（网易 ClawEmail）

> 来源：[ClawEmail 官方文档](https://claw.163.com/projects/doc/)，已对齐 2026-07 最新命令参数。
> 本 skill 的 `mail_*` / `claw_*` 函数就是对下面这些命令的封装。

## 概述

`mail-cli` 是 ClawEmail 的命令行工具，邮件内容被视为**数据**而非指令，不触发 LLM 推理，**零 token 成本**。本 skill 默认通过 `npx --yes @clawemail/mail-cli@latest` 即用即跑，无需全局安装。

> **写操作安全**：网易 mail-cli 的写操作（`compose send`、`clawemail create/disable`）直接执行，无两步确认。腾讯 agently 后端的写操作走 `ctk_xxx` 两步确认（见 `agently-cli-guide.md`）。

## 邮件列表

```bash
# 列出收件箱邮件（--fid 1 = 收件箱, 3 = 已发送）
mail-cli mail list --fid 1 --limit 20

# 只看未读
mail-cli mail list --fid 1 --unread

# 结构化输出（配合 jq 做管道处理）
mail-cli mail list --fid 1 --unread --limit 100 --json
```

## 邮件搜索

```bash
# 按关键词搜索
mail-cli mail search --fid 1 --keyword "合同审查"

# 按时间范围（近一天）
mail-cli mail search --fid 1 --keyword "" --since "$(date -v-1d +%Y-%m-%d)" --json

# 结构化输出
mail-cli mail search --fid 1 --keyword "项目进度" --json | jq 'length'
```

## 读取邮件

```bash
# 读取正文（用 --id 指定邮件 ID）
mail-cli read body --id "<mail-id>"

# 读取结构（含附件列表与附件 part-id，下载附件时需要）
mail-cli read structure --id "<mail-id>"

# 结构化输出（jq 提取附件 part-id）
mail-cli read structure --id "<mail-id>" --json | jq -r '.[] | select(.filename != null) | .partId'
```

## 附件操作

附件下载需要先 `read structure` 拿到附件的 **part-id**，再按 part-id 下载：

```bash
# 1. 查看邮件结构，拿到附件 part-id（例如 2）
mail-cli read structure --id "<mail-id>"

# 2. 按 part-id 下载到指定目录
mail-cli read attachment --id "<mail-id>" --part 2 --out-file ./attachments/
```

> 本 skill 的 `mail_download`（claw 后端）封装了上述流程；旧式 `claw_download <mail-id>` 仍兼容，但建议用 `--id --part --out-file` 精确下载。

## 发送邮件

```bash
# 发送纯文本
mail-cli compose send --to "recipient@example.com" --subject "主题" --body "正文"

# 指定发件人显示名（控制对方收件箱里显示的名称）
mail-cli compose send \
  --from "\"我的Agent\" <agent@claw.163.com>" \
  --to "recipient@example.com" --subject "主题" --body "正文"

# 发送 HTML 邮件
mail-cli compose send --to "r@e.com" --subject "主题" --body "<h1>标题</h1><p>内容</p>" --html

# 正文从文件读取（长邮件 / 日报 / JSON 报告）
mail-cli compose send --to "human@163.com" --subject "每日汇总" --body-file /tmp/daily_report.json
```

> 本 skill 的 `mail_send` / `claw_send` 会自动从 `.env` 的 `DISPLAY_NAME` + `AGENT_EMAIL` 构造 `--from`，无需手写。

## 邮箱管理（子邮箱）

```bash
# 列出账号下所有子邮箱
mail-cli clawemail list

# 创建子邮箱
mail-cli clawemail create --prefix mybot --type sub --display-name "我的Agent"

# 停用子邮箱
mail-cli clawemail disable --uid "mybot@claw.163.com"

# 获取主邮箱地址（daily-report 等场景自动取收件人）
mail-cli clawemail master-user
```

## 多 Profile（多账号）

```bash
# 指定 profile 操作（profile 由 auth login --profile 创建）
mail-cli --profile work mail list --fid 1
mail-cli --profile salesbot compose send --to "a@b.com" --subject "Hi" --body "Hello"

# 多邮箱并行采集示例
for pool in salesbot supportbot reviewbot; do
  count=$(mail-cli --profile "$pool" mail list --fid 1 --unread --json | jq 'length')
  echo "$pool: $count unread"
done
```

## JSON + jq 管道示例（批量场景）

### 批量分拣（场景 5）

```bash
mails=$(mail-cli mail list --fid 1 --unread --limit 100 --json)
echo "$mails" | jq -r '.[] | select(.from | contains("@partner.com")) | .id' | while read -r mid; do
  body=$(mail-cli read body --id "$mid")
  mail-cli compose send --to salesbot@claw.163.com --subject "转发: partner 邮件" --body "$body"
done
```

### 定时日报（场景 6）

```bash
mail-cli mail search --fid 1 --keyword "" --since "$(date -v-1d +%Y-%m-%d)" --json | \
  jq '{total: length, unread: [.[] | select(.read==false)] | length,
       by_sender: (group_by(.from) | map({sender: .[0].from, count: length}))}' \
  > /tmp/daily_report.json

mail-cli compose send --to human@163.com \
  --subject "ClawEmail 每日邮件汇总 $(date +%Y-%m-%d)" \
  --body-file /tmp/daily_report.json
```

### 附件批量下载归档（场景 8）

```bash
mail-cli mail list --fid 1 --unread --json | \
  jq -r '.[] | select(.attachSize > 0) | .id' | while read -r mid; do
    mail-cli read structure --id "$mid" --json | \
      jq -r '.[] | select(.filename != null) | .partId' | while read -r pid; do
        mail-cli read attachment --id "$mid" --part "$pid" --out-file ./inbox_attachments/
      done
  done
```

## 与 Email Channel 的区别

| 特性 | mail-cli（本 skill 用） | Email Channel |
|------|----------|---------------|
| 邮件内容处理 | 作为**数据**处理 | 作为**指令**触发 LLM |
| Token 消耗 | 零 | 有（理解指令需推理） |
| 适用场景 | 批量处理、自动化、数据提取 | 实时响应邮件指令、交互式对话 |
| 控制方式 | CLI 命令 | Channel Prompt（需 OpenClaw 网关） |
| 平台依赖 | 任何能跑 shell 的 Agent | OpenClaw / Hermes 等支持 Channel 的框架 |

## 常见问题

### mail-cli 未找到？

本 skill 通过 `npx --yes @clawemail/mail-cli@latest` 自动拉取，无需手动安装。若想加速，可全局安装：`npm install -g @clawemail/mail-cli`。

### 认证失败 / Profile 未找到？

用 `claw_init "t1/认证URL" "显示名"` 重新配置，或手动：

```bash
npx "@clawemail/mail-cli@latest" auth apikey set "ck_live_xxx"
npx "@clawemail/mail-cli@latest" auth login \
  --user "xxx@claw.163.com" --auth-method password --password "ck_live_xxx"
```

### 旧脚本用位置参数 `<mail-id>` 报错？

官方已统一改用 `--id <mail-id>`。把 `read body <mid>` 改成 `read body --id <mid>` 即可。本 skill 的 `mail_read` 已是 `--id` 风格。
