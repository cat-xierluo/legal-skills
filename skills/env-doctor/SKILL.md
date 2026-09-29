---
name: env-doctor
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.3.0"
license: MIT
description: 本机开发环境与全局包的体检、账本与安装纪律，覆盖所有包管理器（npm/npx、nvm、pip/pipx、uv、brew、bun）与运行时环境面（~/.local/bin 垫片、PATH、python 解释器版图、LaunchAgents、cron、shell rc 漂移对照）。当用户问「node/python 为什么是这个版本」「npm/pip 全局包装到哪了」「环境怎么又乱了」「PATH/rc 被谁改了」「多了个 LaunchAgent」，或任何 agent 在执行 npm i -g / uv tool install / pipx install / brew install 等全局安装、修改 shell rc 文件、注册 LaunchAgent/cron、触碰 ~/.local/bin 符号链接、或在厂商应用（Hermes/Deck/Wukong 等）更新后复核环境之前，必须先读本 skill 并遵守其纪律。不要用于：单个项目内的 node_modules / venv 依赖管理、CI 环境、Linux 服务器初始化。仅 macOS。
---

# env-doctor · 环境与全局包体检、账本与安装纪律

本机装了大量自带运行时的 agent 应用（Hermes、Deck、Wukong、Eigent……），加上 nvm /
uv / pipx / brew / bun 多套包管理器并存，摩擦全部出现在接缝处：谁排 PATH 前面、
node/python 归谁、全局包装进哪个 prefix、哪个链接死了。本 skill 用「确定性体检 +
账本 + 安装纪律」把地质层变成可查账的：脏了立刻可见，每次变更有据可查。
（心智模型同 `brew doctor` / `npm doctor`：环境医生。）

## 硬纪律（所有 agent 必须遵守，先于任何环境写操作）

1. **全局安装只走白名单落点，装完必须记账**（`record` 子命令，一条命令的事）：
   - Node 包：`npm i -g`，且 npm 必须是 **nvm 当前默认版本** 的（用 `npm prefix -g`
     核对，不是则先停下报告）；
   - Python CLI：`uv tool install`（或 `pipx install`），**不要** `pip install --user`
     手装 CLI；
   - 系统依赖：`brew install`；
   - bun 全局尽量少用，装了必记账。
2. **三类操作默认禁止**，除非用户当次明示授权且完成后立即记账：修改 shell rc 文件
   （`~/.zshenv` / `~/.zprofile` / `~/.zshrc` / `~/.profile`）；注册 LaunchAgent 或
   cron；在 `~/.local/bin` 新增或改指 node/npm/npx/python 等运行时垫片。
3. **`~/.local/bin` 是全机唯一垫片层**：这里的 node/npm/npx 链接决定所有 shell（包括
   launchd 拉起的干净 shell）的默认运行时。只允许跟随 nvm default 重指，且必须记账。
4. **厂商应用升级后先体检**：跑一次 `env-doctor.sh`，若报 🚨（垫片漂移，多为 Hermes
   等把 node 链接抢回自家），**只报告用户，不擅自改回**——那可能是该应用有意的依赖。
5. **判断运行时/包的归属看链接与 prefix，不看表面**：`which -a node` + `readlink` 读
   出真实目标，`npm prefix -g` / `pip -V` 看真实落点；版本号一致不代表是同一个
   node（本机曾有 4 个并存、pip 有 user/brew/uv 多套）。

## 体检（确定性检测）

```bash
bash "<本skill目录>/scripts/env-doctor.sh"               # 快速体检（本地信息，秒级）
bash "<本skill目录>/scripts/env-doctor.sh" full          # 深度体检（追加 brew outdated，需网络）
bash "<本skill目录>/scripts/env-doctor.sh" snapshot      # 立漂移基线（rc 哈希 + LaunchAgents 名单）
bash "<本skill目录>/scripts/env-doctor.sh" record "说明"  # 记账
```

输出八段：① node/npm/npx 垫片归属比对（✅/🚨）② PATH 实际解析与解释器版图（node
与 python3 全量清单）③ 各包管理器与全局落点（npm 全局清单 / uv tools / pipx /
pip --user / bun / brew leaves 与 services / cron 概览）④ 缓存体积（npm/bun/uv/pip/
brew）⑤ `~/.local/bin` 全部符号链接与死链 ⑥ LaunchAgents 与 cron 明细 ⑦ 账本尾部
⑧ 环境漂移对照——rc 文件哈希与 LaunchAgents 名单 diff 上次 `snapshot` 基线，报
🚨新增/变更、ℹ️消失。
退出码：`0` 正常；`2` 检测到垫片漂移（见 🚨 标记）；`3` 无法解析 nvm 默认、未验证。
第 8 节环境面漂移只报告不计入退出码（见 DECISIONS D7）。agent 巡检以退出码为准；
`full` 模式额外报告 brew 过时包清单。变更确认合法后重跑 `snapshot` 重立基线并记账。

## 记账

账本在 `~/.config/env-ledger.md`（纯文本，随写随追加），每行一条：
`- 日期 时间 — 谁做了什么、如何回滚`。环境被谁动过、怎么还原，查这里，不做考古。
任何全局安装/卸载、垫片改指、rc 修改、LaunchAgent 增删，都要有一行。

## 已知基线

机器现状（4 个 node 的分布、各包管理器落点、Hermes 自管边界、历史修复与回滚命令）
见 [references/known-baseline.md](references/known-baseline.md)。基线漂移时更新该
文件并记账。

## 依赖

无外部硬依赖：bash 3.2+ 与 macOS 标准命令；npm/uv/pipx/brew 缺失时对应段自动降级。

## 部署

`~/.agents/skills/env-doctor` → 本目录（符号链接），跨 agent 生效。
