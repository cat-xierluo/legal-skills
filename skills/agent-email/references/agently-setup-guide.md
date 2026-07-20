# 腾讯 Agent Mail 首次配置指南

## 前提

- 已安装 Node.js 18+（macOS: `brew install node`）
- 已在 [agent.qq.com](https://agent.qq.com) 开通 Agent Mail（用 QQ 邮箱账号登录）
- 已全局安装 agently-cli：`npm install -g @tencent-qqmail/agently-cli`

> 两家后端的安装对照见 `backends-install.md`。

## 方式一：一键配置（推荐）

本 skill 封装了 OAuth 全流程（后台 pty 跑 `auth login` + 自动抓授权 URL + 验证）：

```bash
source skills/agent-email/scripts/mail-ops.sh
export MAIL_PROVIDER=agently
mail_login
```

`mail_login`（agently 后端的 `agently_login`）自动完成：
1. 检查 agently-cli 已安装
2. 后台开 pty 跑 `agently-cli auth login`，从输出抓取授权 URL
3. 原样展示授权 URL 给你（opaque，不编码 / 不拼接）
4. 你在浏览器完成授权后命令自动退出
5. 跑 `agently-cli +me` 验证，返回邮箱地址

成功后输出：
> 邮箱地址 xxx 已授权成功，可以用它来收发邮件了。

## 方式二：手动配置

### 1. 安装 CLI
```bash
npm install -g @tencent-qqmail/agently-cli
```

### 2. OAuth 授权

`agently-cli auth login` 是**交互式长命令**，必须后台运行（background + pty），从 stdout/stderr 提取它输出的原始授权 URL 给用户。用户在浏览器完成授权后命令自动退出。

**URL 输出规则**：将 URL 视为不可修改的 opaque string，不要做任何修改（包括 URL 编码 / 解码、添加空格或标点、重新拼接 query），用只包含原始 URL 的代码块单独展示。

```bash
agently-cli auth login
```

执行注意：
- **必须**先安装 / 更新 CLI 到最新
- 失败或超时**不要重试**，直接反馈错误

### 3. 验证
```bash
agently-cli +me
```
返回邮箱地址即授权成功。

### 4. 切到 agently 后端

在 `scripts/.env` 设 `MAIL_PROVIDER=agently`，或运行前 `export MAIL_PROVIDER=agently`。

## 配置产物

| 位置 | 说明 |
|------|------|
| agently-cli 自管 | OAuth 凭据由 CLI 保存到本机（不进 .env） |
| `scripts/.env` | 只记录 `MAIL_PROVIDER=agently`（和可选的 `AGENTLY_EMAIL` 备忘） |

## 常见问题

### 未找到 agently-cli

全局安装：`npm install -g @tencent-qqmail/agently-cli`。本 skill 不像网易那样走 npx 即用，腾讯 CLI 需要全局装（因为 OAuth 凭据要持久化在本机）。

### auth login 超时 / 失败

**不要重试**，直接看错误反馈。常见原因：CLI 版本旧（更新到最新）、网络问题、QQ 邮箱账号未开通 Agent Mail。

### 授权失效（exit code 3）

重新跑 `mail_login`（或 `agently-cli auth login`）走 OAuth。

### 切换回网易

`export MAIL_PROVIDER=claw` 即可，无需重新配置——两家凭据各自独立保存在本机。
