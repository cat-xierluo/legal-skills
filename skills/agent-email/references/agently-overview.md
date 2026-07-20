# 腾讯 Agent Mail 服务总览

> 来源：腾讯 [Agent Mail 官网](https://agent.qq.com) 与 [CLI 文档](https://agent.qq.com/doc/cli-setup.md)。

## 一、Agent Mail 是什么

Agent Mail 是 QQ 邮箱团队为 AI Agent 打造的原生邮箱，**与个人 QQ 邮箱隔离**。Agent 用独立的专属邮箱收发邮件，不碰你的私人邮箱。管理后台在 [agent.qq.com](https://agent.qq.com)。

核心组件：`agently-cli`（npm 包 `@tencent-qqmail/agently-cli`）—— OAuth 授权后，用命令行收发、搜索、回复、转发、整理邮件。腾讯自己也发了一个纯文档型 skill `agently-mail`，本 skill 已把它的命令集、两步确认协议、错误码、安全规则等内容**内化**进来（和 DEC-002 内化网易文档同一路子），不需要再平行安装那个 skill。

## 二、和网易 ClawEmail 的对比

本 skill 同时支持两家后端，用 `MAIL_PROVIDER` 切换。何时用哪家？

| 维度 | 网易 ClawEmail（claw） | 腾讯 Agent Mail（agently） |
|------|------------------------|----------------------------|
| 邮箱域名 | `xxx@claw.163.com` | QQ 邮箱体系（agent.qq.com 管理） |
| 认证模型 | API Key（`ck_live_xxx`，认证 URL 换取） | OAuth（浏览器授权） |
| CLI 包 | `@clawemail/mail-cli`（npx 即用） | `@tencent-qqmail/agently-cli`（全局安装） |
| 命令风格 | 动词式（`mail list` / `compose send`） | 名词+动词（`message +list` / `message +send`） |
| 写操作确认 | 无（直接执行） | **两步确认（ctk_xxx）** |
| 回复 / 转发 | 无原生（用 send 模拟） | 原生 `+reply` / `+forward` |
| 删除 | 不支持 | `+trash`（软删，30 天清理） |
| 新邮件监听 | 无（cron 轮询） | `+watch`（NDJSON 长连接流） |
| 附件上传 | 不支持 | `attachment +upload` |
| 搜索维度 | 关键词 + 文件夹 + 时间 | 关键词 + 发件人 + 时间 + 有附件 + 未读 + 范围 |
| 子邮箱管理 | `clawemail create/disable` | agent.qq.com 管理端 |
| 正文规范 | 可加 Agent 署名（旧约定） | **不加 Agent 署名** |
| token 消耗 | 零（数据模式） | 零（数据模式） |

**怎么选：**
- 需要 **回复 / 转发 / 删除 / 长连接监听** → 腾讯 agently（命令更全）
- 需要 **批量子邮箱管理**（建 / 停子邮箱）→ 网易 claw（`clawemail create/disable`）
- 对接 **网易生态**（163 主邮箱）→ claw
- 对接 **QQ / 微信生态** → agently
- 两家都配好，按 `MAIL_PROVIDER` 随时切换，互不干扰

## 三、Claude Code / Codex 用户

和网易 ClawEmail 一样，agently-cli 是纯 CLI 工具，任何能跑 shell 的 Agent 都能用。本 skill 已把 agently-cli 封装进 `mail_*` 统一 API：

```bash
source skills/agent-email/scripts/mail-ops.sh
export MAIL_PROVIDER=agently    # 切到腾讯
mail_list --dir inbox --limit 10
mail_send --to someone@example.com --subject "测试" --body "内容"   # 走两步确认
```

切回网易：`export MAIL_PROVIDER=claw`。两家凭据各自独立保存，切换无需重配。

## 四、相关文档

- `agently-setup-guide.md` — agently-cli 安装 + OAuth 授权流程
- `agently-cli-guide.md` — 完整命令参考 + 两步确认 + 错误码 + 安全规则
- `backends-install.md` — 两家后端 CLI 安装与依赖对照
- `clawemail-overview.md` — 网易 ClawEmail 服务总览
