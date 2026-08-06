---
name: workbuddy-checkin
description: WorkBuddy 每日积分自动签到。自动解密本地登录令牌，调用官方签到 API 完成每日积分领取（100 积分/天，连续第 7 天 1000 积分），并支持配置定时任务。触发词：WorkBuddy 签到、每日积分、check-in、credits。
version: "1.0.2"
license: MIT
---

# WorkBuddy 每日积分签到

自动领取 WorkBuddy 每日积分（100 积分/天，连续第 7 天 1000 积分）。
全流程在本机完成：读取本地登录态 → 调用腾讯官方签到接口。无后端服务。

## 原理

1. WorkBuddy 桌面端登录后，会在本地保存登录态。**v5.3.8+ 的新版桌面端**改为明文 JSON 文件：
   - macOS：`~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info`
   - 结构 `{ account, auth: { accessToken, refreshToken, expiresAt, ... }, accounts }`，桌面端临近过期会自动刷新，纯 Node 即可读取 `auth.accessToken`。
2. **旧版 WorkBuddy/CodeBuddy** 仍把 auth session 用 Electron `safeStorage` 加密存于 `state.vscdb`；新版明文文件缺失时回退到此路径，用 Electron 运行时执行 `safeStorage.decryptString()` 解密（macOS 命中钥匙串；Windows/Linux 走 DPAPI/keyring）。
3. 运行时策略：**Node 优先**（读新版明文文件，无需 Electron），缺失时回退 Electron（解旧版 `state.vscdb`）。
4. 调用腾讯官方签到 API：
   - 查状态：`POST https://copilot.tencent.com/billing/meter/checkin-status`
   - 执行签到：`POST https://copilot.tencent.com/billing/meter/daily-checkin`
   - 认证：`Authorization: Bearer <accessToken>`
5. 脚本幂等：先查状态（命中即跳过）；`daily-checkin` 返回 `code=10001`（今天已签到）同样视为成功，避免重复请求被误报为失败。

> ⚠️ v5.3.8 实测 `checkin-status` 的 `today_checked_in` 字段不可靠（签到成功后仍可能为 `false`）。因此幂等性主要靠 `daily-checkin` 的 `code=10001` 兜底。

兼容旧版应用名 `CodeBuddy`（仅旧版 `state.vscdb` 分支需要，macOS 需设环境变量 `WB_CHECKIN_APP_NAME=CodeBuddy`）。

## 文件结构

```
workbuddy-checkin/
├── SKILL.md
├── references/
│   └── dependencies.md         # 依赖清单与平台差异
└── scripts/
    ├── decrypt-token.js        # 解密令牌（跨平台）
    ├── checkin.sh              # macOS / Linux / Git Bash
    ├── checkin.ps1             # Windows PowerShell
    ├── setup.sh                # macOS / Linux 一键安装
    └── setup.ps1               # Windows 一键安装
```

`logs/` 目录运行后自动创建，存放签到日志。

## 依赖

### 系统依赖

| 依赖 | 用途 | 安装方式 |
|------|------|----------|
| WorkBuddy 桌面端（已登录） | 提供本地登录态（v5.3.8+ 明文文件 / 旧版 `state.vscdb`） | 官网下载，必须登录过至少一次 |
| Node.js（推荐 20+，v5.3.8+ 主路径必需） | 读取新版明文登录态、解析 JSON | nodejs.org 下载，或系统包管理器 |
| curl（macOS/Linux 自带）/ curl.exe | 调用签到 API | Windows 10 1803+ 自带 |
| Electron 运行时（≥ 30，推荐 37） | **仅旧版** `state.vscdb` 分支解密令牌用 | 仅旧版账户需要，运行 `scripts/setup.sh` 或 `setup.ps1` |

> v5.3.8+ 用户：装好 Node.js 并登录桌面端即可直接签到，**无需安装 Electron**。Electron 仅用于尚未迁移到新版明文存储的旧版 WorkBuddy/CodeBuddy 账户。

### 开箱即用 vs 需安装

- **开箱即用（v5.3.8+）**：已装 WorkBuddy 桌面端并登录 + 系统已有 Node.js → 直接运行签到脚本。
- **需安装 Node.js**：提示「未找到 Node」时，到 nodejs.org 安装，或用 `WB_CHECKIN_NODE=<path>` 指定。
- **旧版账户需 Electron**：使用旧版 WorkBuddy/CodeBuddy（`state.vscdb`）且提示「未找到 Electron」时，执行：

  ```bash
  # macOS / Linux
  bash scripts/setup.sh
  # Windows（PowerShell）
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
  ```

### 可选 / 回退依赖

| 依赖 | 缺失时行为 |
|------|------------|
| Electron 运行时 | 仅旧版 `state.vscdb` 账户需要；v5.3.8+ 新版明文路径不需要 |
| Node.js 内置 `node:sqlite`（Electron 37 / Node 22+ 自带） | 旧版分支自动回退到 `python3` 读取 sqlite |
| `python3` | sh 版 JSON 解析降级为 `unknown`，签到请求仍会执行 |
| `npm`（仅旧版 setup 首次安装 Electron 用） | 手动放置 Electron 后用 `WB_CHECKIN_ELECTRON=<path>`（sh）/ `-ElectronPath <path>`（ps1）指定 |

完整依赖说明见 `references/dependencies.md`。

## 快速开始

macOS / Linux：
```bash
bash scripts/setup.sh     # 检测运行时并验证令牌链路（v5.3.8+ 用 Node，旧版才需 Electron）
bash scripts/checkin.sh   # 立即签到一次（验证）
```

Windows（PowerShell）：
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File scripts\checkin.ps1
```

前提：本机已安装并**登录** WorkBuddy 桌面端；系统已安装 Node.js（v5.3.8+ 主路径）。

## 设置定时任务

电脑非全天开机时，建议配置多个时间点补签（脚本幂等，重复运行无副作用）。推荐 `09:00 / 12:00 / 15:00 / 18:00 / 21:00` 各尝试一次，只要电脑在任一时间点开机就能签上。

### macOS / Linux（crontab）
```bash
crontab -e
0 9,12,15,18,21 * * * /path/to/scripts/checkin.sh >> /path/to/logs/checkin.log 2>&1
```

### Windows（任务计划程序）
```powershell
schtasks /Create /TN WorkBuddyDailyCheckin /TR "powershell -ExecutionPolicy Bypass -File C:\path\checkin.ps1" /SC DAILY /ST 09:00 /F
schtasks /Create /TN WorkBuddyDailyCheckin2 /TR "powershell -ExecutionPolicy Bypass -File C:\path\checkin.ps1" /SC DAILY /ST 12:00 /F
# （schtasks 单任务只支持一个 /ST，多时间点需建多个任务）
```

### macOS launchd（长期后台）

创建 `~/Library/LaunchAgents/com.user.workbuddy-checkin.plist`，`StartCalendarInterval` 用数组配置多时间点：
```xml
<key>StartCalendarInterval</key>
<array>
  <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
  <dict><key>Hour</key><integer>12</integer><key>Minute</key><integer>0</integer></dict>
  <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>0</integer></dict>
  <dict><key>Hour</key><integer>18</integer><key>Minute</key><integer>0</integer></dict>
  <dict><key>Hour</key><integer>21</integer><key>Minute</key><integer>0</integer></dict>
</array>
```
然后 `launchctl load ~/Library/LaunchAgents/com.user.workbuddy-checkin.plist`。

### 在 WorkBuddy 内（Agent 自动化）

WorkBuddy 环境下可调用自动化任务工具（`automation_update`，recurring 类型），RRULE 多值 `BYHOUR` 实测生效：
```jsonc
{
  "name": "WorkBuddy 每日积分签到",
  "scheduleType": "recurring",
  "rrule": "FREQ=DAILY;BYHOUR=9,12,15,18,21;BYMINUTE=0;BYSECOND=0",
  "cwds": ["<用户工作目录>"],
  "status": "ACTIVE",
  "prompt": "运行 Bash 脚本 scripts/checkin.sh（Windows 用 checkin.ps1）。该脚本幂等：今日已签到会直接跳过。读取输出并汇报：签到成功领取多少积分 / 今日已签到 / 令牌失效需打开 WorkBuddy 刷新。"
}
```
> 注意：`update` 已有任务时必须显式传 `rrule`，否则可能被重置；`cwds` 不能用 Claw 工作区。

## 平台说明

新版明文登录态（v5.3.8+，主路径，Node 读取）与旧版 `state.vscdb`（回退路径，Electron 解密）均自动探测。

| 平台 | 脚本 | 新版明文登录态（v5.3.8+，主路径） | 旧版 state.vscdb（回退） |
|---|---|---|---|
| macOS | `checkin.sh` | `~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info` | `~/Library/Application Support/WorkBuddy/User/globalStorage/state.vscdb` |
| Windows | `checkin.ps1`（或 Git Bash 跑 `checkin.sh`） | `%APPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info` | `%APPDATA%\WorkBuddy\User\globalStorage\state.vscdb` |
| Linux | `checkin.sh` | `~/.config/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info` | `~/.config/WorkBuddy/User/globalStorage/state.vscdb` |

Windows PowerShell 执行策略用 `-ExecutionPolicy Bypass`；需 `curl.exe`（Win10 1803+ 自带）。
旧版 `state.vscdb` 分支在 Linux 需桌面会话 + 系统 keyring（GNOME Keyring / KWallet）；新版明文分支无此要求。

## 环境变量

| 变量 | 作用 |
|------|------|
| `WB_CHECKIN_NODE=<path>` | 指定 Node 二进制路径（v5.3.8+ 主路径用，sh/ps1 通用） |
| `WB_CHECKIN_ELECTRON=<path>` | 指定 Electron 二进制路径（仅旧版 state.vscdb 回退用，sh 版） |
| `-ElectronPath <path>` | 同上（ps1 版参数） |
| `WB_CHECKIN_APP_NAME=CodeBuddy` | 兼容旧版应用名（仅旧版 state.vscdb 分支的 macOS 钥匙串密钥） |
| `WB_CHECKIN_JITTER=<秒>` | 启动前随机等待 0~N 秒，避免整点风暴 |

## 排错

- **「获取令牌失败（未知原因）」/ 未找到本地登录态**：先确认 WorkBuddy 桌面端已登录并打开过至少一次。v5.3.8+ 用户检查 Node.js 是否安装（`node -v`），或用 `WB_CHECKIN_NODE` 指定。
- **v5.3.8 已登录但仍报令牌失败**：本机 skill 版本过旧（< 1.0.2），不识别新版明文存储；升级到 1.0.2+。
- **当日重跑提示「签到未成功 / code=10001」**：旧版本（< 1.0.2）未把 `code=10001` 识别为「已签到」；1.0.2+ 会正确报告「今日已签到」。
- **401 令牌过期**：打开 WorkBuddy 刷新登录态，脚本每次运行会重新读取最新 token，次日自动恢复。
- **macOS 解密报错但已登录（旧版账户）**：旧版迁移应用名仍是 `CodeBuddy`，设 `export WB_CHECKIN_APP_NAME=CodeBuddy` 后重试（仅走 state.vscdb 分支时生效）。
- **Electron 下载慢/失败（旧版账户）**：配置 npm 镜像（见 `references/dependencies.md`）后重跑 setup；或手动放置 Electron 后用环境变量/参数指定。v5.3.8+ 新版账户无需 Electron。
- **Windows 提示不是内部或外部命令**：用 `powershell -ExecutionPolicy Bypass -File …` 运行；确认 `curl.exe` 存在。
- **沙箱里 `require('electron')` 报错**：Agent 沙箱默认设 `ELECTRON_RUN_AS_NODE=1`，脚本已用 `env -u`（sh）/ `Remove-Item Env:`（ps1）处理；v5.3.8+ 主路径用纯 Node，不受此影响。

## 安全说明

> ⚠️ **凭据即账号密码**：本 skill 解密的 `accessToken` 等同你的 WorkBuddy 账号密码，具有高敏感性。请务必遵守以下红线：

- 令牌仅在内存中使用，通过管道立即被签到请求消费，**不写入任何日志文件、不落盘、不回显到终端、不提交到仓库**。
- `logs/` 仅记录签到结果（积分 / 连续天数 / 成功失败），**绝不含令牌原文**。切勿将日志或脚本输出粘贴分享。
- 网络访问仅发往腾讯官方接口 `copilot.tencent.com/billing/meter/*`，不上传任何第三方。
- 解密成功时脚本会向 stderr 打印一行安全提示（不影响 stdout 的 token 管道），便于你确认凭据正在被使用。
- 请勿用于他人账户、批量注册刷分或任何违反 WorkBuddy 用户协议的用途；使用者自行承担使用风险。

### 为何需要这些能力（上下文说明）

本 skill 自述为"每日签到"，但完整链路需以下能力，均为本机运行、无后端，且对完成签到必不可少：

- **读取本地令牌**：WorkBuddy 桌面端登录后把登录态存于本地——v5.3.8+ 为明文 JSON 文件（`workbuddy-desktop.info`，纯 Node 可读），旧版为 Electron `safeStorage` 加密的 `state.vscdb`。必须读到 `accessToken` 才能调用官方签到接口，这是签到功能的核心，无法绕过。
- **Node.js 运行时**：v5.3.8+ 主路径用 Node 直接读取明文登录态并解析 JSON。推荐手动指定已校验的 Node（设 `WB_CHECKIN_NODE`）。
- **Electron 运行时（仅旧版账户）**：只有使用旧版 WorkBuddy/CodeBuddy（`state.vscdb`）时才需要，执行 `safeStorage.decryptString()` 解密令牌（macOS 命中钥匙串、Windows/Linux 走系统 DPAPI/keyring）。推荐手动指定已校验的 Electron（设 `WB_CHECKIN_ELECTRON`），不依赖自动下载。
- **python3 回退（默认关闭）**：仅当旧版分支的 `node:sqlite` 不可用时，设 `WB_CHECKIN_ALLOW_PY_FALLBACK=1` 才会调用外部 `python3` 读取会话库。默认关闭以缩小信任边界。
- **定时任务（crontab / launchd / 任务计划程序）**：用于多时间点幂等补签，脚本本身不写入系统定时，需你显式配置。

### 供应链提示

安装 Electron 默认**不自动下载**（避免静默引入第三方大二进制）。如需自动安装，须显式设置环境变量 `WB_CHECKIN_AUTO_INSTALL_ELECTRON=1` 确认从官方 npm registry 下载 `electron@37`。

## 所需权限

本 skill 运行需以下本地权限，均限定在最小范围：

| 权限 | 范围 | 说明 |
|------|------|------|
| 本地代码执行 | 仅本 skill 的 `checkin.sh/.ps1`、`decrypt-token.js`、`setup.sh/.ps1` | 用户手动或定时触发，非后台常驻 |
| 本地文件读取 | 用户目录下的 WorkBuddy 登录态（v5.3.8+ 明文 `workbuddy-desktop.info` / 旧版 `state.vscdb`） | 读取登录态以获取调用官方接口所需的 accessToken |
| 网络访问 | 仅 `copilot.tencent.com` 官方签到接口 | 不访问任何其他域名 |
| 环境变量读取 | `WB_CHECKIN_*`（Node/Electron 路径、应用名、错峰、回退开关） | 均为本机用户显式配置 |
| 定时任务 | 由用户显式配置 crontab / launchd / 任务计划程序 | skill 不自动写入系统定时 |
