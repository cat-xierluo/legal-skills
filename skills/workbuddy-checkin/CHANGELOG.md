# 变更日志

## [1.0.0] - 2026-08-05

### 新增

- 初始版本：WorkBuddy 每日积分自动签到 skill 正式纳入 legal-skills 仓库
- 跨平台签到脚本：`scripts/checkin.sh`（macOS/Linux/Git Bash）与 `scripts/checkin.ps1`（Windows PowerShell，兼容 PS 5.1）
- 令牌解密脚本 `scripts/decrypt-token.js`：基于 Electron `safeStorage` 解密本地 `state.vscdb` 会话，`node:sqlite` 不可用时自动回退 `python3`
- 一键安装脚本 `scripts/setup.sh` / `scripts/setup.ps1`：自动检测或通过 npm 下载 Electron 运行时，并验证解密链路
- 多 Agent 框架适配（WorkBuddy 自动化任务 / Claude Code / Codex / OpenClaw / 纯终端），定时方式覆盖 crontab / launchd / schtasks / WorkBuddy recurring
- 幂等保护：每次运行先查 `checkin-status`，今日已签到立即跳过，支持一天多时间点补签（默认推荐 09/12/15/18/21 点）
- 随机错峰：`WB_CHECKIN_JITTER=<秒>` 环境变量让脚本启动前随机等待，避免整点风暴
- 兼容旧版应用名 CodeBuddy：`WB_CHECKIN_APP_NAME=CodeBuddy` 覆盖钥匙串绑定名

### 设计要点

- **全本机运行**：不含任何后端服务，令牌仅发往腾讯官方接口 `copilot.tencent.com`，不上传第三方
- **令牌不落盘**：仅在内存中传递；`logs/` 只记录签到结果（积分/连续天数），不含令牌
- **沙箱兼容**：WorkBuddy 等 Agent 沙箱默认设 `ELECTRON_RUN_AS_NODE=1` 会导致 `require('electron')` 拿不到 `safeStorage`，脚本已用 `env -u`（sh）/ `Remove-Item Env:`（ps1）显式处理

### 已知限制

- 签到按自然日结算，若整天未开机则当日无法补签，次日首个运行点自动重新开始（连续天数会重置）
- 令牌过期（401）需打开 WorkBuddy 桌面端刷新登录态，次日自动恢复
- macOS 应用名与钥匙串绑定：新装为 `WorkBuddy`，旧版迁移可能仍是 `CodeBuddy`

### 合规提示

- 本 skill 等价于「每天手动点一次领取今日礼包」，仅操作本机当前登录用户自己的 WorkBuddy 账户
- 请勿用于他人账户、批量注册刷分或任何违反 WorkBuddy 用户协议的用途
- 使用者需自行承担使用风险，确保来源可信
