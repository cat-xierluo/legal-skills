# 依赖清单（Dependencies）

本 skill 运行链路：**解密本地令牌 → 调用官方 API → 写日志**。所需依赖如下。

## 核心依赖（必须有）

| 组件 | 作用 | 获取方式 | 说明 |
|---|---|---|---|
| WorkBuddy 桌面端（已登录） | 提供本地登录会话（state.vscdb） | 官网下载：https://www.codebuddy.cn/work/ | 必须已登录过至少一次，否则没有可解密的令牌 |
| Electron 运行时（>= 30，推荐 37） | 执行 `safeStorage.decryptString()` 解密令牌 | `scripts/setup.sh` / `setup.ps1` 自动下载（npm install electron@37），约 100MB | 与 WorkBuddy 桌面端同版本的 Electron 最稳；旧版 CodeBuddy 用户需设 `WB_CHECKIN_APP_NAME=CodeBuddy` |
| curl（sh 版） / curl.exe（ps1 版） | 调用签到 API | macOS/Linux 自带；Windows 10 1803+ 自带 curl.exe | — |

## 可选 / 回退依赖（缺了也能跑，只是走回退路径）

| 组件 | 作用 | 缺失时的行为 |
|---|---|---|
| Node.js 内置 `node:sqlite` | 读取 state.vscdb | 解密脚本自动回退到 python3 |
| python3 | 回退读取 sqlite + 解析 API 响应 JSON（sh 版） | sh 版解析会降级为 unknown，签到仍会执行 |
| npm | 自动下载 Electron | 手动放置 Electron 后通过环境变量/参数指定路径 |

> 说明：decrypt-token.js 用 Node 内置 `node:sqlite` 读库（Electron 37 内置 Node 22 可用）；
> 若所用 Electron 版本较旧不支持 `node:sqlite`，会自动调用 `python3` 读取，无需额外安装 npm 包。

## 网络要求

- 需可访问 `https://copilot.tencent.com`（签到 API）与 `https://registry.npmjs.org`（首次安装 Electron）。
- 国内网络下载 Electron 慢时，配置镜像：
  ```bash
  npm config set registry https://registry.npmmirror.com
  # 并设置 Electron 镜像（可选）
  export ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/"
  ```

## 平台差异速查

| 平台 | Shell | 会话库路径（自动探测） | Electron 二进制 |
|---|---|---|---|
| macOS | `checkin.sh`（bash） | `~/Library/Application Support/WorkBuddy/User/globalStorage/state.vscdb` | `Electron.app/Contents/MacOS/Electron` |
| Windows | `checkin.ps1`（PowerShell）或 Git Bash 下 `checkin.sh` | `%APPDATA%\WorkBuddy\User\globalStorage\state.vscdb` | `electron.exe` |
| Linux | `checkin.sh`（bash） | `~/.config/WorkBuddy/User/globalStorage/state.vscdb` | `electron`（无 .app 包裹） |

## 安装后的目录结构（示意）

```
workbuddy-checkin/
├── SKILL.md
├── references/dependencies.md
├── scripts/
│   ├── decrypt-token.js      # 跨平台，唯一需要 Electron 执行的脚本
│   ├── checkin.sh            # macOS / Linux / Git Bash
│   ├── checkin.ps1           # Windows PowerShell
│   ├── setup.sh              # macOS / Linux 一键安装
│   └── setup.ps1             # Windows 一键安装
└── logs/                     # 签到日志（自动创建）
```
