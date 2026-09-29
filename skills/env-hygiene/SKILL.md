---
name: env-hygiene
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.1.0"
license: MIT
description: 本机运行时环境的审计、账本与安装纪律（node/npm/npx/python/brew/nvm/bun、~/.local/bin 垫片、PATH、LaunchAgents）。当用户问「node 为什么是 v22」「npm 全局包装到哪了」「环境怎么又乱了」，或任何 agent 在安装全局包（npm i -g / uv tool / brew）、修改 shell rc 文件、注册 LaunchAgent/cron、触碰 ~/.local/bin 符号链接、或在厂商 agent 应用（Hermes/Deck/Wukong/Eigent 等）更新后复核环境之前，必须先读本 skill 的纪律并遵守。不要用于：单个项目内的 node_modules / venv 依赖管理、CI 环境或 Linux 服务器初始化。仅 macOS。
---

# env-hygiene · 运行时环境审计与账本

本机装了大量自带运行时的 agent 应用（Hermes、Deck、Wukong、Eigent……），它们各自往
`~/.local/bin` 塞垫片、改 rc 文件、注册 LaunchAgent。摩擦全部出现在接缝处：谁排 PATH
前面、node 归谁、全局包装进哪个 prefix。本 skill 用「确定性审计 + 账本 + 安装纪律」把
地质层变成可查账的：脏了立刻可见，每次变更有据可查。

## 硬纪律（所有 agent 必须遵守，先于任何环境写操作）

1. **全局安装只允许三个落点**：nvm 当前默认版本的 `npm i -g`、`uv tool install`（Python
   CLI）、`brew install`。装完必须用 `record` 记账（一条命令的事）。
2. **三类操作默认禁止**，除非用户当次明示授权且完成后立即记账：修改 shell rc 文件
   （`~/.zshenv` / `~/.zprofile` / `~/.zshrc` / `~/.profile`）；注册 LaunchAgent 或
   cron；在 `~/.local/bin` 新增或改指 node/npm/npx/python 等运行时垫片。
3. **`~/.local/bin` 是全机唯一垫片层**：这里的 node/npm/npx 链接决定所有 shell（包括
   launchd 拉起的干净 shell）的默认运行时。只允许跟随 nvm default 重指，且必须记账。
4. **厂商应用升级后先审计**：跑一次 `env-audit.sh`，若报 🚨（垫片漂移，多为 Hermes 等
   把 node 链接抢回自家），**只报告用户，不擅自改回**——那可能是该应用有意的依赖。
5. **判断运行时归属看链接指向，不看表面**：`which -a node` + `readlink` 读出真实目标，
   版本号一致不代表是同一个 node（本机曾有 4 个并存）。

## 审计（确定性检测）

```bash
bash "<本skill目录>/scripts/env-audit.sh"          # 全量审计
bash "<本skill目录>/scripts/env-audit.sh" record "说明"   # 记账
```

输出六段：① 垫片归属比对（✅/🚨）② PATH 实际解析 ③ node 版本与缓存体积 ④
`~/.local/bin` 全部符号链接与死链 ⑤ LaunchAgents 清单 ⑥ 账本尾部。
退出码：`0` 正常；`2` 检测到漂移（见 🚨 标记）；`3` 无法解析 nvm 默认、未验证。
agent 巡检时以退出码为准。

## 记账

账本在 `~/.config/env-ledger.md`（纯文本，随写随追加），每行一条：
`- 日期 时间 — 谁做了什么、如何回滚`。环境被谁动过、怎么还原，查这里，不做考古。

## 已知基线

机器现状（4 个 node 的分布、Hermes 自管边界、历史修复与回滚命令）见
[references/known-baseline.md](references/known-baseline.md)。基线漂移时更新该文件并记账。

## 依赖

无外部依赖：bash 3.2+ 与 macOS 标准命令（readlink/du/ls），brew 缺失时对应段自动降级。

## 部署

`~/.agents/skills/env-hygiene` → 本目录（符号链接），跨 agent 生效。
