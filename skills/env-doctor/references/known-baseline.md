# 已知基线（2026-09-30 建立，同日随 v0.2.0 扩域）

机器运行时环境的权威快照。基线漂移时更新本文件并记账（`env-doctor.sh record`）。

## node 分布（共 4 个，各有归属）

| node | 路径 | 归属 | 纪律 |
|---|---|---|---|
| v24.14.0 | `~/.nvm/versions/node/v24.14.0` | **用户默认**（2026-10-16 起，nvm default = v24.14.0；@dsh CLI 落此） | `npm i -g` 唯一合法落点 |
| v24.11.0 | `~/.nvm/versions/node/v24.11.0` | 用户次级（旧全局 CLI 库：claude-code/gemini-cli/iflow-cli/codex/qwen-code；2026-10-16 修复 0 字节 node 二进制） | 保留；其 CLI 经 PATH node 驱动可用 |
| v22.22.3 | `~/.hermes/node` | Hermes 自管 | 勿手动升级/删除其下全局包（codex/codebuddy/agently/lark/cubox/docx 等 8 个） |
| v25.2.1 | `/opt/homebrew/Cellar/node/` | brew | brew 自管；**v25 起运行时默认自带 localStorage 全局**，含 storage 纯度断言的测试仓勿用 |
| v20.12.0 | `/usr/local/bin/node` | 2024-03 pkg 安装残留（root 所有，192M） | 用户 shell 为 PATH 最末兜底；**agent 壳 shell（无 ~/.local/bin）会解析到它**——测试仓须显式 PATH 或门禁自解析（dsh-plugins pre-push 已免疫） |

**nvm default 坑（2026-10-16）**：`nvm alias default 24.14.0` 写入 alias 文件的是**不带 v** 的 `24.14.0`，而版本目录是 `v24.14.0`——env-doctor 的解析器按目录名直查会失败（报「无法解析 nvm 默认」）。设 alias 一律用带 v 形态（`nvm alias default v24.x.y`）；解析器 v 前缀归一化列为 skill 待改进。另：default 曾为 `lts/*`→krypton→`v24.21.0`（未安装）的死链形态，lts 别名随上游漂移，默认别名的稳定形态是钉具体 vX.Y.Z。

用户 shell 的 node/npm/npx 一律经 `~/.local/bin` 垫片解析到 nvm v24——包括 launchd
拉起的干净 shell（只有 `.zshenv` 生效，PATH 无 brew/nvm）。

## 各包管理器落点（2026-09-30 普查）

| 管理器 | 现状 | 纪律 |
|---|---|---|
| npm | 全局装 nvm v24 prefix（claude-code/gemini-cli/iflow/codex/qwen-code 等）；`~/.hermes/node` 下另有 8 包属 Hermes | 装前 `npm prefix -g` 核对是 nvm |
| uv | tools：blender-mcp、browser-use、kimi-cli、makelive；`~/.local/share/uv/python/` 多套解释器；`~/.local/bin/python3.11/3.12` 指向 uv python | Python CLI 首选通道 |
| pipx | 与 uv tools 同一批 4 个（双通道可见） | 二选一即可，勿重复装 |
| pip --user | `~/Library/Python/3.11/` 一批库 | 原则上不手装 CLI，只放库 |
| brew | 65 leaves、108 过时（2026-09-29 口径） | 升级需用户点名 |
| bun | 全局仅 ccusage + 用户自写 cc-buddy-roller/show-tokens；缓存 2G 已清 | 少用，装了记账 |

## 漂移基线（2026-09-30 立）

- 基线文件 `~/.config/env-doctor/state`：6 个 shell rc 文件的 SHA-256 + 30 个
  LaunchAgents 名单，由 `env-doctor.sh snapshot` 生成。
- 之后每次体检第 8 节自动对照；变更确认合法后重跑 `snapshot` 重立 + `record` 记账。
- 本基线是「谁动了我的环境」的裁判：Deck/Hermes 式 rc 注入、新增 LaunchAgent 都会
  在下一次体检现形。

## 垫片层

- `~/.local/bin` 是全机唯一垫片层（约 47 项：uv tools、claude、zcode、Hermes CLI 等）。
- node/npm/npx → `~/.nvm/versions/node/v24.14.0/bin/`（2026-10-16 三者对齐 nvm default
  v24.14.0；node 先由另会话改指 24.14.0 未记账，本次补账并补齐 npm/npx）。
- **回滚到 24.11.0**：`ln -sfn ~/.nvm/versions/node/v24.11.0/bin/<t> ~/.local/bin/<t>`；
  **回滚到 Hermes**：`ln -sfn ~/.hermes/node/bin/<t> ~/.local/bin/<t>`（t=node/npm/npx）。
- **复发条件**：① 用户换 nvm 默认/删 v24 时须重指；② Hermes 升级重装可能把链接抢回
  自家 node——`env-doctor.sh` 报 🚨 即此因。
- 已知死链（2026-09-30 体检发现，待用户裁决）：openclaw（ClawX 卸载）、
  python3.10（Eigent 更新）、qoderclicn（QoderWork CN 更新）。

## Hermes 自管边界（勿动清单）

- `~/.hermes`（12G）：自带两套 node（`node/` v22.22.3 + `tools/node-26.7.0`）、npm、
  python 3.14、ripgrep、ffmpeg、agent-browser；gateway 走绝对路径，不依赖任何垫片。
- rc 注入：`.zshenv` / `.zprofile` / `.profile` 各有一行
  `export PATH="$HOME/.local/bin:$PATH"`（注释标 Hermes Agent）——合法存在，勿清理。
- `.zshrc` 另有 `# Added by Deck.app` 等其他应用的注入，同属地质层，改动前记账。

## 事件史（摘要，明细看账本 ~/.config/env-ledger.md）

- 2026-09-29：全机普查 + 清理 ~6.7G（删 `~/Skill_Seekers`、nvm 卸 v18.20.8/v22.17.0、
  清 npm 缓存 3.2G 与 bun 缓存 2G）。
- 2026-09-30：node 垫片重指向 nvm v24（见上）；创建本 skill（v0.1.0 时名 env-hygiene，
  同日更名 env-doctor 并扩域至全部包管理器）。
- 2026-10-16（ZCode PM，用户授权 env-doctor 通道）：修复 v24.11.0 的 0 字节 node 二进制
  （官方 tarball 单文件提取 + SHASUMS256 验证 + 原子替换）；nvm default 由失效的
  lts/*→v24.21.0（未安装）钉为 v24.14.0（v 前缀规范形态）；npm/npx 垫片对齐 v24.14.0。
  同日另会话：`npm i -g @deepseek-ai/dsh@0.2.0-rc.2` 落 v24.14.0 + `~/.local/bin/dsh`
  应用级软链（已记账）；参考项目/deepseek-harness pnpm install 修复依赖。
