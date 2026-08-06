# 依赖清单（Dependencies）

本 skill 运行链路：**读取本地令牌 → 调用官方 API → 写日志**。所需依赖如下。

> v5.3.8+ 登录态改版说明：新版 WorkBuddy 桌面端把当前登录态写入明文 JSON 文件（`workbuddy-desktop.info`），不再写入 `state.vscdb`。本 skill v1.0.2+ 优先用 Node 读取该明文文件，旧版 `state.vscdb` 仅作回退。v1.0.0/1.0.1 因只认 `state.vscdb`，在 v5.3.8 桌面端上会报「获取令牌失败（未知原因）」，需升级到 1.0.2+。

## 核心依赖（必须有）

| 组件 | 作用 | 获取方式 | 说明 |
|---|---|---|---|
| WorkBuddy 桌面端（已登录） | 提供本地登录态（v5.3.8+ 明文文件 / 旧版 `state.vscdb`） | 官网下载：https://www.codebuddy.cn/work/ | 必须已登录过至少一次，否则没有可读的令牌 |
| Node.js（推荐 20+） | 读取 v5.3.8+ 明文登录态、解析 JSON（主路径） | nodejs.org 下载 LTS；或系统包管理器 | v5.3.8+ 用户必需；可用 `WB_CHECKIN_NODE=<path>` 指定 |
| curl（sh 版） / curl.exe（ps1 版） | 调用签到 API | macOS/Linux 自带；Windows 10 1803+ 自带 curl.exe | — |

## 仅旧版账户需要的依赖

| 组件 | 作用 | 获取方式 | 说明 |
|---|---|---|---|
| Electron 运行时（>= 30，推荐 37） | 仅旧版 `state.vscdb` 分支执行 `safeStorage.decryptString()` 解密令牌 | `scripts/setup.sh` / `setup.ps1`（npm install electron@37，约 100MB） | v5.3.8+ 新版账户**不需要**；旧版 CodeBuddy 用户需设 `WB_CHECKIN_APP_NAME=CodeBuddy` |

## 可选 / 回退依赖（缺了也能跑，只是走回退路径）

| 组件 | 作用 | 缺失时的行为 |
|---|---|---|
| Node.js 内置 `node:sqlite` | 仅旧版分支读取 state.vscdb | 旧版分支自动回退到 python3 |
| python3 | 回退读取 sqlite + 解析 API 响应 JSON（sh 版） | sh 版解析会降级为 unknown，签到仍会执行 |
| npm | 仅旧版 setup 自动下载 Electron | 手动放置 Electron 后通过环境变量/参数指定路径 |

> 说明：旧版分支的 decrypt-token.js 用 Node 内置 `node:sqlite` 读库（Electron 37 内置 Node 22 可用）；
> 若所用 Electron 版本较旧不支持 `node:sqlite`，会自动调用 `python3` 读取，无需额外安装 npm 包。
> 新版明文分支为纯 JSON 文件读取，不涉及 sqlite。

## 网络要求

- 需可访问 `https://copilot.tencent.com`（签到 API）；仅旧版账户首次安装 Electron 时才需 `https://registry.npmjs.org`。v5.3.8+ 新版账户走 Node 直读，无需下载 Electron。
- 国内网络下载 Electron 慢时，配置镜像：
  ```bash
  npm config set registry https://registry.npmmirror.com
  # 并设置 Electron 镜像（可选）
  export ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/"
  ```

## 平台差异速查

新版明文登录态（v5.3.8+，主路径，Node 读取）与旧版 `state.vscdb`（回退，Electron 解密）均自动探测。

| 平台 | Shell | 新版明文登录态（v5.3.8+，主路径） | 旧版 state.vscdb（回退） | Electron 二进制（仅旧版） |
|---|---|---|---|---|
| macOS | `checkin.sh`（bash） | `~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info` | `~/Library/Application Support/WorkBuddy/User/globalStorage/state.vscdb` | `Electron.app/Contents/MacOS/Electron` |
| Windows | `checkin.ps1`（PowerShell）或 Git Bash 下 `checkin.sh` | `%APPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info` | `%APPDATA%\WorkBuddy\User\globalStorage\state.vscdb` | `electron.exe` |
| Linux | `checkin.sh`（bash） | `~/.config/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info` | `~/.config/WorkBuddy/User/globalStorage/state.vscdb` | `electron`（无 .app 包裹） |

> ⚠️ Windows / Linux 的 `CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info` 路径基于 v5.3.8 桌面端约定推导，已在 macOS 实测命中；其他平台如路径不一致，请以实际安装为准并反馈。

## 安装后的目录结构（示意）

```
workbuddy-checkin/
├── SKILL.md
├── references/dependencies.md
├── scripts/
│   ├── decrypt-token.js      # 跨平台：新版明文 Node 读取 + 旧版 state.vscdb Electron 解密
│   ├── checkin.sh            # macOS / Linux / Git Bash（Node 优先，Electron 回退）
│   ├── checkin.ps1           # Windows PowerShell（Node 优先，Electron 回退）
│   ├── setup.sh              # macOS / Linux 环境检查（Node 优先，旧版才需 Electron）
│   └── setup.ps1             # Windows 环境检查
└── logs/                     # 签到日志（自动创建）
```
