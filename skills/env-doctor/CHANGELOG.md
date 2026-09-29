# Changelog · env-doctor

## 0.3.0 - 2026-09-30

- **环境漂移对照（第 8 节）+ `snapshot` 子命令**：对 shell rc 文件（zshenv/zprofile/
  zshrc/zlogin/profile/bashrc）取 SHA-256、对 LaunchAgents 取名单存入
  `~/.config/env-doctor/state` 基线；此后每次体检自动 diff，报 🚨新增/变更、ℹ️消失。
  基线只由显式 `snapshot` 重立（体检不自动覆盖，见 DECISIONS D6）；环境面漂移不计入
  退出码（D7）。基线路径可经 `ENV_DOCTOR_STATE` 覆盖以便测试。
- **Python 解释器版图**：第 2 节列出 PATH 上全部 python3（逐个版本）+ `uv python list`
  ——与 node 同构的多解释器问题纳入视野。
- **审计面补全**：cron 明细（第 6 节）、brew services 运行数（第 3 节）、uv/pip 缓存
  体积（第 4 节）。
- **补齐仓库规范内部文档**：DECISIONS.md（D1–D7 设计取舍与重评条件）、TASKS.md
  （T1–T6 路线图：死链清理、MCP 注册漂移、pip --user 迁移、brew 升级、PATH 快照、
  --strict 门禁）、LICENSE.txt（MIT）。
- 脚本头部注释补环境变量说明（ENV_LEDGER / ENV_DOCTOR_STATE）。

## 0.2.0 - 2026-09-30

- **更名**：`env-hygiene` → `env-doctor`（用户反馈原名不易理解；对齐 `brew doctor` /
  `npm doctor` 的「环境医生」心智模型），脚本同步更名 `env-audit.sh` → `env-doctor.sh`。
- **扩域**：从 node/nvm 扩到全部包管理器——npm、pip/pipx、uv、brew、bun。新增体检
  第 3 节「包管理器与全局落点」（npm 全局清单 / uv tools / pipx / pip --user 包数 /
  bun 全局命令 / brew leaves）与 `pip 落点` 检查；纪律 1 改为按管理器的白名单落点。
- 新增 `full` 子命令：追加 brew 过时包清单（需网络，默认快速体检不含）。
- 体检段由六段扩为七段，退出码语义不变（0/2/3）。
- 基线文档补各包管理器落点事实（pipx 4 个、uv python 多套、brew 65 leaves 等）。

## 0.1.0 - 2026-09-30

- 初始版本（时名 env-hygiene）。
- `scripts/env-audit.sh`：六段审计（垫片归属比对 / PATH 实际解析 / node 版本与缓存 /
  `~/.local/bin` 符号链接与死链 / LaunchAgents / 账本尾部），退出码 0/2/3 供 agent 巡检；
  `record` 子命令写入 `~/.config/env-ledger.md`。
- SKILL.md 固化五条安装纪律（全局安装三落点、rc/LaunchAgent/垫片默认禁改、
  `~/.local/bin` 唯一垫片层、厂商升级后先审计、归属判断看链接指向）。
- 背景：2026-09-29 全机普查发现 Hermes 经 `~/.local/bin` 垫片遮蔽所有 shell 的 node
  （表面 nvm、实际 v22.22.3），09-30 重指向 nvm v24 修复。本 skill 是该事件的沉淀，
  基线见 `references/known-baseline.md`。
