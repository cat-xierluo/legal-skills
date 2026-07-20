## [0.4.1] - 2026-07-20

### 变更
- 腾讯 agently 写操作的 ctk 两步确认改为**自动完成**：新增 `_agently_auto_two_step`，在 `mail_send` / `mail_reply` / `mail_forward` / `mail_trash` 内部「拿 ctk + 立即带 ctk 真发」，调用方一次完成，无 ctk 5 分钟过期问题
- 确认环节从 ctk 层移到**对话层**：Agent 拟稿 → 用户说"发" → 一次发出；自动化（cron）场景已预设授权、直接发
- 手动 `--confirmation-token` 仍可选透传（向后兼容）
- 真机验证：一次 `mail_send` 自动两步 → `queued:true` → 收件箱收到

### 文档
- SKILL.md「两步确认协议」改为「写操作确认（对话层）」
- `agently-cli-guide.md` 加「本 skill 自动完成两步」说明（DEC-006）

## [0.4.0] - 2026-07-20

### 变更
- 升级为**多 provider 统一邮箱管理**：新增腾讯 Agent Mail（`@tencent-qqmail/agently-cli`）后端，与网易 ClawEmail 并列
- `scripts/mail-ops.sh` 重构为三层 API：`mail_*` 统一入口 / `_claw_*` + `_agently_*` 实现层 / `claw_*` 向后兼容别名，由 `_dispatch` 按 `MAIL_PROVIDER` 路由
- 新增 `MAIL_PROVIDER` 环境变量切换后端（默认 `claw`）
- 新增腾讯 OAuth 工程化封装 `agently_login`（macOS `script` pty + grep 抓授权 URL，补上腾讯官方甩给宿主的部分）
- 同步网易 mail-cli 官方最新参数：`read body/structure/attachment` 统一 `--id`、`attachment` 用 `--part --out-file`、`mail list/search` 支持 `--json/--unread/--since`、`compose send` 支持 `--body-file`、新增 `clawemail master-user`
- SKILL.md 重构：新增「服务商选择」「两步确认协议」「安全规则」「邮件正文规范」章节；邮件操作改 `mail_*` 统一 API

### 新增
- `references/agently-overview.md` / `agently-setup-guide.md` / `agently-cli-guide.md`：内化腾讯官方 skill 内容（命令集、两步确认 `ctk` 协议、exit code 0-8 矩阵、prompt injection 安全规则 6 条）
- `references/backends-install.md`：两家后端 CLI 安装与认证对照，作为基础配置入口

### 文档
- 更新 `references/clawemail-mail-cli-guide.md`：对齐 2026-07 官方最新参数，加 JSON + jq 管道示例（场景 5/6/8）
- 更新 `references/clawemail-overview.md`：开通步骤改用 `claw_init`，移除已废弃的 claw-setup 依赖

### 注意
- 腾讯 agently 后端的写操作（send/reply/forward/trash）走**两步确认**（`ctk_xxx`），与网易 claw 直接执行不同
- 腾讯 `agently-cli` 需全局安装（OAuth 凭据持久化），网易 `mail-cli` 仍走 npx 即用
- `claw_*` 旧函数名保留为别名，已有 cron / 脚本无需改动

## [0.3.1] - 2026-05-17

### 修复
- 修复 `mail-ops.sh` 中 `npx` 参数分隔导致 mail-cli 收到多余参数的问题
- 修复 `claw_send` 的 `--from`、`--body` 等参数组装，支持显示名和正文中的空格
- 修复 `.env.example` 与首次配置指南中的 `DISPLAY_NAME` 示例，避免 source 时因空格中断
- 移除函数库顶层 shell 选项修改，避免 `source scripts/mail-ops.sh` 影响调用方终端

### 文档完善
- 同步 SKILL frontmatter、README 和 Marketplace 清单版本为 `0.3.1`

## [0.3.0] - 2026-05-17

### 变更
- 技能重命名：`claw-mail` → `agent-email`，定位为通用 Agent 邮箱服务（ClawEmail 为首个支持的服务商）
- SKILL.md 重构：新增「这是什么」章节、适用场景，ClawEmail 细节移至 references
- 首次配置章节移至 `references/clawemail-setup-guide.md`，SKILL.md 聚焦日常邮件操作
- 邮件操作章节统一展示封装函数 + 原始命令
- 新增典型工作流：Agent 任务分发（邮件发任务 → PR 收结果）
- 常见问题排查扩充：发件人名称不显示、npx 安装慢

## [0.2.0] - 2026-05-17

### 变更
- 重定位为纯 mail-cli 模式，移除 claw-setup / OpenClaw 插件依赖
- 删除 `scripts/setup.sh` 和 `scripts/.env.example`
- 重写 `scripts/mail-ops.sh`：去掉 .env 依赖，改用 npx 调用，新增 `claw_init` 一键配置
- SKILL.md 全面重写，聚焦 mail-cli 操作和首次配置流程

## [0.1.0] - 2026-05-16

### 新增
- 初始版本：ClawEmail 邮件服务接入 Skill
