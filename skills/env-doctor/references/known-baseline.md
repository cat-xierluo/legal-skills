# 已知基线（2026-09-30 建立，同日随 v0.2.0 扩域）

机器运行时环境的权威快照。基线漂移时更新本文件并记账（`env-doctor.sh record`）。

## node 分布（共 4 个，各有归属）

| node | 路径 | 归属 | 纪律 |
|---|---|---|---|
| v24.11.0 | `~/.nvm/versions/node/v24.11.0` | **用户默认**（nvm default = lts/krypton） | `npm i -g` 唯一合法落点 |
| v22.22.3 | `~/.hermes/node` | Hermes 自管 | 勿手动升级/删除其下全局包（codex/codebuddy/agently/lark/cubox/docx 等 8 个） |
| v25.2.1 | `/opt/homebrew/Cellar/node/` | brew | brew 自管 |
| v20.12.0 | `/usr/local/bin/node` | 2024-03 pkg 安装残留（root 所有，192M） | PATH 最末兜底，无害，清掉需 sudo |

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

## 垫片层

- `~/.local/bin` 是全机唯一垫片层（约 47 项：uv tools、claude、zcode、Hermes CLI 等）。
- node/npm/npx → `~/.nvm/versions/node/v24.11.0/bin/`（2026-09-30 由 Hermes 的
  `~/.hermes/node` 重指向而来）。
- **回滚**：`ln -sfn ~/.hermes/node/bin/<t> ~/.local/bin/<t>`（t=node/npm/npx）。
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
