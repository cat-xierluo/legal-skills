# Changelog · env-hygiene

## 0.1.0 - 2026-09-30

- 初始版本。
- `scripts/env-audit.sh`：六段审计（垫片归属比对 / PATH 实际解析 / node 版本与缓存 /
  `~/.local/bin` 符号链接与死链 / LaunchAgents / 账本尾部），退出码 0/2 供 agent 巡检；
  `record` 子命令写入 `~/.config/env-ledger.md`。
- SKILL.md 固化五条安装纪律（全局安装三落点、rc/LaunchAgent/垫片默认禁改、
  `~/.local/bin` 唯一垫片层、厂商升级后先审计、归属判断看链接指向）。
- 背景：2026-09-29 全机普查发现 Hermes 经 `~/.local/bin` 垫片遮蔽所有 shell 的 node
  （表面 nvm、实际 v22.22.3），09-30 重指向 nvm v24 修复。本 skill 是该事件的沉淀，
  基线见 `references/known-baseline.md`。
