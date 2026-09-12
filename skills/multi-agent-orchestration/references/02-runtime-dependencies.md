# Runtime Dependencies

> 当前可派发 backend 只有 Claude Code、Codex、CodeBuddy、QoderWork CN。OpenCode 等条目仅是历史候选依赖，不属于 `spawn-worker.sh` 的当前运行合同。

> 读取时机：首次使用本 Skill、迁移到新机器、启动 Wave 前、脚本报 command not found 或日期解析异常时。

## 1. 依赖分层

| 场景 | 必需依赖 | 说明 |
| --- | --- | --- |
| 阅读 Skill / 手工规划 | 无 | 只读文档不需要安装工具 |
| 生成 worker command | `bash` | `render-runtime-profile.sh` 只生成命令，不检查 backend CLI 是否存在 |
| 创建本地 worker | `git`、`tmux`、`jq`、`bash`、`python3`、常见 Unix 工具 | `spawn-worker.sh` 需要创建 worktree、写 metadata、安装依赖权限 hook、启动 tmux |
| 单 worker 等待 | `jq`、常见 Unix 工具；tmux 仅在读取 pane tail 时需要 | `wait-worker.sh` 主状态源是 `STATUS.json` |
| 多 worker 监控 | `bash` 4+、`git`、`jq`、常见 Unix 工具；`tmux`、`gh`、`claude` 可选 | `pm-monitor.sh` 用关联数组，macOS 系统 `/bin/bash` 3.2 不够 |
| worktree 总览 / 清理 | `git`；`jq` 推荐；`tmux` 可选 | 没有 `jq` 时只能显示有限 metadata |
| PR 状态 / mergeability | `gh` 且已登录 | `pm-monitor.sh` 无 `gh` 时仍能看 checkpoint/git/tmux，但 PR 判断变弱 |
| Claude worker | `claude`；第三方 provider wrapper 还需要 `jq` | 第三方 provider registry/settings 还需要本地 ignored 配置文件；`claude-provider-env.sh` 用 `jq` 解析 registry 或 settings env |
| Codex worker | `codex` | batch worker 常用 `codex exec -a never -s danger-full-access` |
| OpenCode worker | `opencode` | 可做普通 worker 或 ACP 候选 |
| Codex heartbeat | Codex App automation 能力 | 创建/修改 automation 必须用 `automation_update` 工具 |
| terminal split | 对应终端工具 | Kitty 需要 `kitty @`；WezTerm 需要 `wezterm cli`；macOS GUI 自动化需要 `osascript`/辅助功能授权 |

常见 Unix 工具包括：`awk`、`sed`、`grep`、`find`、`stat`、`date`、`mktemp`、`wc`、`tr`。macOS 和 Linux 默认通常自带，但 `date` 参数不同，脚本已做 macOS/Linux 双路径解析。

## 2. macOS 安装参考（仅用户明确授权后）

下列命令会修改机器环境，只能由用户明确批准后执行。依赖检查或验证要求本身不构成授权；worker 缺依赖时应先查已有安装，仍缺则报告 BLOCKED/RESULT。

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

## 3. Linux 安装参考（仅用户明确授权后）

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

- `check-dependencies.sh` 只报告，不授予安装权限；不得据其 WARN/MISSING 自动执行本页命令。
- 项目本地依赖安装也必须有精确命令与可审计授权来源；正常 lockfile 流程不等于机器级安装授权。
- 不要把 `claude`、`codex`、`opencode` 当作所有模式的硬依赖；只有选用对应 backend 时才需要。
- 不要默认复制 `.env`、真实 provider settings、token 或 key 到 worktree。
- `gh` 用于 PR/mergeability 判断；没有 `gh` 时 PM 必须用其他方式确认 PR 状态，不能假定已合并。
- Claude Code 原生 `--worktree --tmux` 可作为启动后端，但仍要接回本 Skill 的 `METADATA.json` / `STATUS.json` / Wave / review / merge 门禁。

## 6. 验证命令授权

验证命令是 Shell 执行授权，不是安装授权。`spawn-worker.sh` 在任何 terminal、Task、Dispatch 或任务注入前只选择一个来源：

1. 无文件合同时，使用重复的 `--verify-cmd '<完整命令>'`；或使用 `--verification-contract <dispatch-value-gate.v2.json> --verification-task-id <ID>` 选择的唯一任务，两者互斥；
2. 上述均未提供时，读取 `.claude/orchestration.config.json`（或显式 `--project-config`）中的 `verification.default` / `verification.by_worker_type[<--worker-type>]`；
3. 没有项目配置时，才使用项目根的有界 Node/Make/Python 发现。

不要合并多个权威来源；CLI 与合同并存会失败关闭。合同中的 `implementation` / `reusable_verification` 自动要求非空验证命令；其他要求自验的派发传 `--require-verification`，项目也可设置 `verification.required: true`。Python 自动发现只认根 `pyproject.toml` / `requirements.txt` / `setup.py` 与根 `tests/`，固定注入 unittest discover；嵌套项目必须在 `by_worker_type` 显式声明完整命令。

命令原字符串同时写入 authorization snapshot、Git common-dir authority receipt 和 METADATA。空白、换行、U+0000、重复、安装型命令、未知 worker type、非唯一 task 或畸形配置都会在数组解码和派发副作用前拒绝。`verification.required: true` 的项目模板只保留可执行 profile；docs-only 工作本来就不可独立派发，不用空数组伪装成可选 profile。运行中的 Worker 使用不可变进程快照；漏授权须用 `pm-orchestrate.sh reauthorize --allow-cmd '<exact command>'` 重建，不得手改镜像 JSON。

### 任务辅助命令

已有 `--allow-shell-command '<完整精确命令>'` 可在启动前声明生成图标、转换本任务输入等辅助命令。它与验证命令列表分开，不授予安装权限，不是目录信任或通配授权。PM 核对输入、输出、工作目录与文件范围后，连同验证合同派发；Worker 以不可变授权快照为准。

运行中漏授权时，先说明命令的输入、输出、幂等性与范围，由 PM 选择限定代跑并记录证据，或经现有 `pm-orchestrate.sh reauthorize --allow-cmd '<精确命令>'` 正规重建。后者仍须满足 live Dispatch 等入口门禁，不能对已结算目标强行使用；不得热改 B64、镜像 JSON 或 authority receipt 绕过。未获授权则记录 BLOCKED，不反复变形命令。

## 7. 根级 .venv 的显式复用

内置 `--python-runtime-symlink` 仅服务 `.runtime/venv` 布局；根级 `.venv` 使用以下 opt-in 手工流程，不默认跨项目共享。

1. PM 证明源 venv 与目标 worktree 属于本任务、源解释器可执行，且目标 `.venv` 不存在（包括 dangling symlink）。不得覆盖既有目标。
2. 用已核实的绝对源路径创建目标 `.venv` 符号链接；路径始终引用。不复制凭据、不安装依赖、不升级共享 venv。共享源被其他任务更新会使验证失效，优先采用独立环境或固定依赖约定。
3. `.gitignore` 的 `.venv/` 不保证忽略软链。在 `git rev-parse --git-common-dir` 对应的 `info/exclude` 保留原内容，缺少时仅追加精确根模式 `/.venv`；不得覆盖整个文件。linked worktree 共用 exclude，先告知 owner 这一影响。已跟踪路径不受新 exclude 影响，发现时停止并交 PM 判断。
4. 执行 `git check-ignore -v .venv`、`git status --short --untracked-files=all`，并用链接解释器实际运行最小 import/目标测试。只授予 worker 所需 helper/test 的精确命令。提交前核对 staged paths 不含 `.venv`，不以 `git add -A` 代替授权文件清单。
5. 回收只移除本次证明归属的软链，或随干净一次性 worktree 收口，绝不删除源 venv。来源不可靠、解释器损坏或缺依赖时记录 NOT_VERIFIED/BLOCKED，不自行安装。

纯临时 Git + `venv --without-pip` 实操已证明目录忽略陷阱、链接解释器可运行和精确 exclude 防误收；这不保证所有第三方包均可跨路径复用。
