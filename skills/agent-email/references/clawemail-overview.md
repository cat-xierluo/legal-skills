# ClawEmail 完整介绍与使用指南

> 来源：[ClawEmail 官方文档](https://claw.163.com/projects/doc/)，整合至本 Skill 供离线参考。

## 一、ClawEmail 是什么

**`claw.163.com`** 是网易专门给 AI Agent 用的邮箱域名。

你的私人邮箱是 `xxx@163.com`，ClawEmail 让你给 Agent 开独立的工作邮箱，比如 `brandbot@claw.163.com`。Agent 用自己的身份收信、读信、回信，不碰你的私人邮箱。

围绕这个邮箱域名，ClawEmail 提供了两个核心组件：

| 组件 | 是什么 | 怎么用 |
|------|--------|--------|
| **Email Channel** | OpenClaw 的通信插件 | 支持 Channel 的 Agent 框架（如 OpenClaw、Hermes）直接对话触发，邮件即交互 |
| **mail-cli** | Agent 邮箱命令行工具 | 命令行界面下管理账号、凭证，以及邮箱收发信 |

简单说：**mail-cli 负责"搭台"，Email Channel 负责"唱戏"。**

## 二、如何申请与开通

### 前提条件

- 需要一个网易 163 邮箱作为主账号（宿主邮箱）
- 访问 [claw.163.com](https://claw.163.com) 注册/登录

### 开通步骤

本 skill 已内置 `claw_init` 一键配置（纯 mail-cli 模式，不依赖 OpenClaw 插件 / claw-setup）：

1. **访问 ClawEmail 平台**：打开 [claw.163.com](https://claw.163.com)，使用 163 主邮箱登录
2. **获取认证 URL**：在平台控制台获取 Agent 认证 URL（格式如 `t1/xxxxxx`，有效期 30 分钟）
3. **配置通信规则**：在 ClawEmail 后台 → Agent 邮箱管理 → 通信规则，开放外部收发权限（**新建子邮箱默认未开放外部通信，必须手动配置**）
4. **一键配置**：
   ```bash
   source skills/agent-email/scripts/mail-ops.sh
   claw_init "t1/你的认证URL" "你的显示名称"
   ```
5. **验证连通**：`claw_init` 会自动跑 `folder list` 验证，并写入 `.env`
6. **（可选）创建子邮箱**：
   ```bash
   mail-cli clawemail create --prefix mybot --type sub --display-name "我的Agent"
   ```

> 完整配置流程见 `clawemail-setup-guide.md`。腾讯 Agent Mail（QQ 邮箱）的配置见 `agently-setup-guide.md`；两家后端的安装对照见 `backends-install.md`。

### 认证 URL 说明

认证 URL 是 ClawEmail 平台分配给 Agent 的身份凭证。`claw_init` 会 curl 解析它拿到邮箱前缀和 `ck_live_xxx` API Key，存入系统钥匙串并创建 mail-cli Profile。

> **安全提示**：认证 URL 是敏感信息，不要提交到 Git 或公开分享。

## 三、两种模式对比

### Email Channel — 邮件内容即指令

邮件到达后，Agent 把邮件正文当作**需要理解和执行的指令**——判断意图、做出决策、生成回复。**消耗 LLM token**。

### CLI 工具 — 邮件内容即数据

CLI 模式下，邮件只是被操作的数据对象。指令来自脚本里的 `mail-cli` 命令——拉取、过滤、下载、转发、归档。**零 token 消耗**。

### 对比一览

| | Email Channel | CLI 工具 |
|---|---------------|----------|
| **邮件内容的角色** | **指令** — Agent 必须理解邮件在说什么 | **数据** — 脚本只需要拉取、过滤、搬运邮件 |
| **谁给出指令** | 邮件发件人（通过邮件内容） | 脚本/人类（通过 CLI 命令） |
| **类比** | 收到一封信 → 读懂它 → 决定怎么回 | 收到一批包裹 → 按标签分拣 → 放到对应货架 |
| **Token 消耗** | 有（理解指令需要 LLM 推理） | 零（操作数据不需要理解内容） |
| **响应速度** | 秒级（取决于推理复杂度） | 毫秒级（本地命令执行） |

## 四、场景速查 — 我该用哪种模式？

| # | 场景 | 推荐模式 | 邮件内容的角色 |
|---|------|----------|---------------|
| 1 | 智能客服（理解用户诉求） | **Channel** | 指令 — 用户通过邮件下达请求 |
| 2 | 商务邮件助手 | **Channel** | 指令 — 合作方通过邮件传达意图 |
| 3 | 技术支持（分析日志附件） | **Channel** | 指令 — 用户要求诊断问题 |
| 4 | 内容审核（判断质量） | **Channel** | 指令 — 投稿者要求审核内容 |
| 5 | 批量邮件分拣 | **CLI** | 数据 — 按元信息分流，不读正文 |
| 6 | 定时巡检与日报 | **CLI** | 数据 — 统计数量，不读内容 |
| 7 | 邮箱池扩缩容 | **CLI** | 无关 — 操作对象是邮箱不是邮件 |
| 8 | 附件批量下载归档 | **CLI** | 数据 — 附件是文件，不是指令 |
| 9 | 多邮箱并行采集 | **CLI** | 数据 — 采集未读数，不读内容 |
| 10 | 邮件数据管道 | **CLI** | 数据 — 邮件是上游数据源 |
| 11 | 高频邮件精准处理 | **混合** | 90% 当数据处理，10% 当指令理解 |

## 五、Claude Code / Codex 用户的使用方式

OpenClaw 和 Hermes 平台已内置 ClawEmail 支持。但如果你使用的是 **Claude Code** 或 **Codex**：

1. 你**无法直接使用 Email Channel 模式**（需要 OpenClaw 网关）
2. 但你可以通过 **mail-cli** 完成所有邮件操作（收发、搜索、附件）
3. 本 Skill 提供了完整的脚本封装和操作函数库

### 典型工作流

```
Agent 通过 mail-cli 拉取邮件 → 解析邮件内容 → 执行业务逻辑 → 通过 mail-cli 回复
```

这本质上是**手动实现了 Email Channel 的功能**，但给了你更大的灵活性。

## 六、官方 Skill 参考

ClawEmail 平台提供了一些官方 Skill，可供参考学习：

| Skill | 一句话描述 | 创建的子邮箱 | 定时策略 | 适合谁 |
|-------|-----------|-------------|----------|--------|
| **github-triage** | GitHub 通知按紧急度自动分拣 | `用户名.github@claw.163.com` | 每 5 分钟 + 每日 18:00 汇总 | 每天收大量 GitHub 通知的开发者 |
| **daily-report** | 所有子邮箱健康状态巡检日报 | 不创建新邮箱 | 每日 08:00 | 管理多个 Agent 子邮箱的用户 |
| **support-router** | AI 客服邮件自动分类回复 | `用户名.support` + `用户名.csbot` | 每分钟轮询 | 独立开发者 / 小团队 |
| **notify-hub** | 多平台通知统一收取分层处理 | `用户名.notify@claw.163.com` | 每 10 分钟 + 每日 09:00 汇总 | 同时用多个 SaaS 工具的用户 |

安装官方 Skill：

```bash
npx skills add https://claw.163.com/s/<skill-name>.git
```

> **注意**：官方 Skill 需要 OpenClaw 平台支持。Claude Code / Codex 用户可参考其逻辑，用 mail-cli 自行实现。

## 七、常见问题排查

### 邮件发送成功但对方未收到

1. **检查通信规则**：ClawEmail 后台（[claw.163.com](https://claw.163.com)）→ Agent 邮箱管理 → 通信规则，需配置允许外部收发的白名单。**新建的子邮箱默认未开放外部通信，必须手动配置。**
2. **检查垃圾邮件**：对方邮箱可能将 `@claw.163.com` 发件人过滤到垃圾邮件文件夹。
3. **检查邮箱状态**：`claw_mailboxes` 确认邮箱状态为 `active`。

### 发件人名称不显示 / 显示为邮箱前缀

`clawemail profile --display-name` 只修改平台侧名称，**不影响 SMTP From 头**。发信时必须通过 `--from "\"显示名称\" <邮箱@claw.163.com>"` 指定。使用 `claw_send` 函数会自动从 `.env` 读取 `DISPLAY_NAME` 并构造 `--from` 参数。

### Profile 未找到

```bash
npx "@clawemail/mail-cli@latest" auth login \
  --user "xxx@claw.163.com" --auth-method password --password "ck_live_xxx"
```

### 认证 URL 过期

认证 URL 有效期 **30 分钟**，过期后需从 ClawEmail 平台重新获取。

### npx 安装慢或失败

可全局安装以加速后续调用：`npm install -g "@clawemail/mail-cli"`

## 八、安全注意事项

- **API Key 是敏感信息**：不要提交到 Git，不要公开分享
- **认证 URL 有效期 30 分钟**：过期需重新获取
- **邮件内容可能包含敏感数据**：处理时注意隐私保护
