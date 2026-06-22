# Runtime Dependencies

> 读取时机：首次使用本 Skill、迁移到新机器、启动 Wave 前、脚本报 command not found 或日期解析异常时。

## 1. 依赖分层

| 场景 | 必需依赖 | 说明 |
| --- | --- | --- |
| 阅读 Skill / 手工规划 | 无 | 只读文档不需要安装工具 |
| 生成 worker command | `bash` | `render-runtime-profile.sh` 只生成命令，不检查 backend CLI 是否存在 |
| 创建本地 worker | `git`、`tmux`、`jq`、`bash`、常见 Unix 工具 | `spawn-worker.sh` 需要创建 worktree、写 metadata、启动 tmux |
| 单 worker 等待 | `jq`、常见 Unix 工具；tmux 仅在读取 pane tail 时需要 | `wait-worker.sh` 主状态源是 `STATUS.json` |
| 多 worker 监控 | `bash` 4+、`git`、`jq`、常见 Unix 工具；`tmux`、`gh`、`claude` 可选 | `pm-monitor.sh` 用关联数组，macOS 系统 `/bin/bash` 3.2 不够 |
| worktree 总览 / 清理 | `git`；`jq` 推荐；`tmux` 可选 | 没有 `jq` 时只能显示有限 metadata |
| PR 状态 / mergeability | `gh` 且已登录 | `pm-monitor.sh` 无 `gh` 时仍能看 checkpoint/git/tmux，但 PR 判断变弱 |
| Claude worker | `claude` | 第三方 provider settings 还需要本地 settings 文件 |
| Codex worker | `codex` | batch worker 常用 `codex exec -a never -s danger-full-access` |
| OpenCode worker | `opencode` | 可做普通 worker 或 ACP 候选 |
| Codex heartbeat | Codex App automation 能力 | 创建/修改 automation 必须用 `automation_update` 工具 |
| terminal split | 对应终端工具 | Kitty 需要 `kitty @`；WezTerm 需要 `wezterm cli`；macOS GUI 自动化需要 `osascript`/辅助功能授权 |

常见 Unix 工具包括：`awk`、`sed`、`grep`、`find`、`stat`、`date`、`mktemp`、`wc`、`tr`。macOS 和 Linux 默认通常自带，但 `date` 参数不同，脚本已做 macOS/Linux 双路径解析。

## 2. macOS 安装建议

```bash
brew install bash tmux jq gh
```

可选 backend：

```bash
# 按实际来源安装
claude --version
codex --version
opencode --version
```

`pm-monitor.sh` 要求 bash 4+。在 macOS 上，如果默认 shell 仍调用系统 `/bin/bash` 3.2，应使用 Homebrew bash 运行：

```bash
/opt/homebrew/bin/bash scripts/pm-monitor.sh ...
```

或确保新版 bash 在 `PATH` 前面。

## 3. Linux 安装建议

Debian / Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y bash git tmux jq gh
```

不同发行版的 GitHub CLI 包名和安装源可能不同；以 GitHub CLI 官方安装方式为准。

## 4. 快速检查

```bash
bash scripts/check-dependencies.sh
bash scripts/check-dependencies.sh --backend claude-code --backend codex --check-gh --check-terminal-split
```

检查脚本只报告依赖状态，不安装软件，也不启动 worker。

## 5. 依赖边界

- 不要把 `claude`、`codex`、`opencode` 当作所有模式的硬依赖；只有选用对应 backend 时才需要。
- 不要默认复制 `.env`、真实 provider settings、token 或 key 到 worktree。
- `gh` 用于 PR/mergeability 判断；没有 `gh` 时 PM 必须用其他方式确认 PR 状态，不能假定已合并。
- Claude Code 原生 `--worktree --tmux` 可作为启动后端，但仍要接回本 Skill 的 `METADATA.json` / `STATUS.json` / Wave / review / merge 门禁。
