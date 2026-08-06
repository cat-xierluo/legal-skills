# 变更日志

## [1.0.2] - 2026-08-06

### 修复

- **兼容 WorkBuddy 桌面端 v5.3.8 新版登录态存储**（#68）：v5.3.8 不再把当前登录态写入 `state.vscdb`，改用明文 JSON 文件 `~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info`（Windows/Linux 同构路径）。旧版（≤1.0.1）只认 `state.vscdb`，导致连续报「获取令牌失败（未知原因）」。
  - `decrypt-token.js` 改为**新版明文文件优先、旧版 `state.vscdb` 回退**；新版分支纯 Node 读取 `auth.accessToken`，无需 Electron `safeStorage` 解密。
  - `require("electron")` 包裹 try/catch，脚本可由普通 `node` 直接执行。
  - 统一 `emitAndExit()`（`process.stdout.write` 后延迟 ~200ms 退出），避免 `console.log` 后立即 `app.exit()` 导致 stdout 未 flush。
- **macOS 运行时策略改为 Node 优先**（#68）：直接调用 WorkBuddy.app 的 Electron 二进制会启动主应用而非执行脚本；新版明文文件用纯 Node 即可读取，无需依赖应用内 Electron。`checkin.sh`/`checkin.ps1`/`setup.sh`/`setup.ps1` 均改为 Node 优先、Electron 回退，新增 `WB_CHECKIN_NODE=<path>` 环境变量。
- **`daily-checkin` 的 `code=10001` 识别为已签到**（#68）：v5.3.8 实测 `checkin-status` 的 `today_checked_in` 不可靠（签到成功后仍为 `false`），当日重跑会再次调 `daily-checkin` 并返回 `code=10001`（今天已签到）；旧版将其误报为「签到未成功」，导致幂等分支失效。1.0.2 起正确报告「今日已签到，无需重复领取」。

### 改进

- 文档同步：`SKILL.md` / `references/dependencies.md` 更新原理、平台路径、依赖（Electron 降级为仅旧版可选）、环境变量（新增 `WB_CHECKIN_NODE`）、排错（v5.3.8 专项条目）。
- `setup.sh`/`setup.ps1`：v5.3.8 用户（仅 Node、无 Electron）不再被误判为「未找到 Electron」而失败。

### 合并前代码评审修复

- **`checkin.sh` / `checkin.ps1` Electron 回退条件修正（高）**：原实现仅当 Node 输出为空才回退 Electron；但旧版 `state.vscdb` 账户在装有 Node 的机器上，纯 Node 会输出非空的 `ERR`（无法解 safeStorage），导致 Electron 回退被跳过、误报失败（对 v1.0.1 旧版账户的回归）。改为「空 或 ERR」均回退。
- **`decrypt-token.js` 部分明文文件不再硬失败**：明文文件存在但缺 `auth.accessToken`（如升级中途 / 写入中）或解析失败时，不再 `exit 5`，而是落入旧版 `state.vscdb` 分支兜底。
- **`decrypt-token.js` 旧版读取异常可观测**：`readValue` 抛错（如 `node:sqlite` 不可用且未开 python3 回退）时不再裸抛，统一经 `DECRYPT_RESULT:ERR` 带原因输出，避免「未知原因」式失败。
- **`checkin.sh` `WB_CHECKIN_JITTER=0` / 非数字不再触发除零中止**：改为先 `[ -gt 0 ]` 校验。
- **`checkin.sh` 缺 `python3` 不再误报「签到未成功」**：结果解析为空时改为提示「请求已提交，缺 python3 无法解析」，避免服务端已成功却被报失败。

### 已知限制

### 已知限制

- Windows / Linux 的 `CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info` 路径基于 v5.3.8 桌面端约定推导，已在 macOS 实测命中，其他平台待真实环境确认。

## [1.0.1] - 2026-08-05

### 改进

- 凭据安全：解密成功时向 stderr 输出安全提示（不污染 token 管道）；python3 回退默认关闭，需 `WB_CHECKIN_ALLOW_PY_FALLBACK=1` 启用
- 安装安全：`setup.sh`/`setup.ps1` 自动 `npm install electron` 默认关闭，需 `WB_CHECKIN_AUTO_INSTALL_ELECTRON=1` 才下载，默认提示手动指定路径并声明供应链风险
- 文档：SKILL.md 安全说明补强，新增「所需权限」清单与「为何需要这些能力」上下文说明，回应 SkillSpector 审计 findings

### 技术优化

- `checkin.sh`/`checkin.ps1` 头部注释补充凭据安全说明

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
