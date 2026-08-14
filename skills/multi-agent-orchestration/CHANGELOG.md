# Changelog

## [2.5.4] - 2026-08-14

### 新增

- `pm-orchestrate settle` 子命令（Task-047 v2，PR #84 review 修复版）：supervised dispatch 死锁兜底——worker 进程死但未发 `worker_done` 时，按 Orca 官方 lifecycle fence+stop（`worker-abandon` fence dispatch、`worker-stop` 停 terminal），不破坏 METADATA。默认安全（不删 worktree/files，PM 后续跑 `clean-worktree.sh --execute --force-remove-dirty`）；`--destroy` 一站式清理（含 symlink unlink + dirty 检查 + git worktree remove + orca worktree rm + lease release + session_context 清）。`--reason` 强制审计；liveness gate 用真字段 `.result.observation.status`/`.result.worker.state`，任一缺失或仍 active → REFUSED（除非 `--force`）。

### 修复

- PR #84 review BLOCKER 1：liveness gate 不再用 `.result.workerSession`（该字段在真 Orca 响应里不存在 → 永远 DEAD 等于无门槛，会误杀活 worker）。
- PR #84 review BLOCKER 2：不再删 METADATA（导致 dispatch/run_id 丢失，`worker-abandon` 变 unrecoverable leak），保留 METADATA 给 PM 后续清理。
- PR #84 review MAJOR 3：--destroy 路径先 unlink `node_modules` 软链（`[ -L ] && rm -f` 无尾斜杠），不跟随软链误删主仓。
- PR #84 review MAJOR 4：provider-lease release fail-loud（禁止 `>/dev/null 2>&1` 吞错），失败 exit 非 0。
- PR #84 review MAJOR 5：--destroy 路径含 dirty 检查 + git worktree remove，与 `clean-worktree.sh` 同步。
- PR #84 review MAJOR 6：references/12-orca-cli-worker.md §9 + references/13-pm-orchestrate.md 命令清单同步更新（之前文档与 v1 行为矛盾）。

### 改进

- PR #84 review MINOR 7：session_context 删除顺序正确（--destroy 末尾，且 fence+stop 已成功）。
- PR #84 review MINOR 8：liveness gate 兼容 `set -euo pipefail`（局部 `set +e +o pipefail`），PARSE_ERROR fallback 可达。
- PR #84 review NIT 9：`--force/--reason` 是 settle-specific（cmd_settle 内部局部变量），不污染其他子命令；`--reason` 用于审计。
- PR #84 review NIT 10：新增 `scripts/test-settle-liveness.sh`（9 fixture cases）+ `scripts/tests/fixtures/worker-show-*.json`（真 Orca worker-show **完整包装** response）。

### 修复（PR #86 review-v2，对真 Orca CLI 验证后）

- **BLOCKER B1**：`settle_liveness_check` jq 路径缺 `.result` 前缀（fixture 预解包导致测试绿但生产无效——同 v1 BLOCKER 1 形状）。改 `.result.observation.status` / `.result.worker.state`；fixture 改完整包装（含 `_meta/id/ok/result`）。gate 逻辑改：拒绝 `active`/`input_accepted`（活），允许 `missing`/`exited`/`succeeded`（死/GC），双 ABSENT 保守拒绝（completed dispatch 的 observation 在 GC 后是 `missing` 非 `exited`）。
- **BLOCKER B2**：`--force` 未在全局 args 解析（cmd_settle 内部解析是死代码，$@ 在 dispatch 时空）。全局加 `--force) FORCE=1`，cmd_settle 读 `${FORCE:-0}`。
- **MAJOR M1**：删无效 symlink `scripts/tests/fixtures/fixtures`（残渣，指错绝对路径）。
- **MAJOR M2**：`--reason` 持久化到 `SETTLE_AUDIT.log`（之前只 echo）；usage "encouraged" 改 "required"。
- **MAJOR M3**：`worker-show`/`worker-stop` 调用用 `set +e` 保护（`set -euo pipefail` 下失败击穿脚本，liveness REFUSED 和 WARN 分支不可达）。
- **MAJOR M4**：`settle_destroy_worktree` 注释改"故意偏离 clean-worktree 顺序"（git 先 vs orca 先，所有权语义不同）。
- **MINOR m1**：`wt_id` 空时 WARN（不静默跳过 orca worktree rm）。
- **MINOR m2**：usage "encouraged" 与强制矛盾修正（并入 M2）。
- **NIT n1**：测试用 env var 传 JSON（避免 eval 单引号脆弱）。
- **NIT n2**：fixture 加 README 说明（observation GC 语义 + 死锁未真测）。

## [2.5.3] - 2026-08-14

### 改进

- `references/05-legal-domain-patterns.md` §2.1 新增「诉讼 worker 的证据访问约定」（Task-049）：澄清代码 `node_modules`「隐式解析 → 必须软链」与诉讼证据「显式访问 → 绝对路径直读」的机制差异；规定 PM spawn 诉讼 worker 时 prompt 必须包含「主仓项目根 + 案件相对路径 + 产出写路径 + md 引证用相对名」四要素，并明确反模式（不软链证据目录、不硬编码绝对路径、不让 worker 假设完整路径）。文档示例全部用 `<占位符>` 表达，不绑定具体运行机器/案件，保证 Skill 跨用户可复用。

## [2.5.2] - 2026-08-14

### 改进

- SKILL.md §3.3 新增「PM spawn 操作纪律」（Task-041~044，Wave-2 实战撞坑固化）：spawn 后不重复 send 完整 prompt（与 `worker-start` live preamble 重复，Task-042）；`run-create` 只调一次避免 `consumer_fenced`（Task-043）；supervised worker 不用 `pm-monitor`/`sentinel` 判完成（靠 `worker_done → Delivery`，Task-041）；spawn 前后独立 Bash 调用并行（Task-044）。

## [2.5.1] - 2026-08-14

### 修复

- Orca supervised worker 无法自验（Task-045/046，G31）：worktree 落在 `~/orca/workspaces/`（独立路径树，不在主仓父链）→ `npm run` 向上解析找不到主仓 `node_modules` → `tsc/vitest/eslint: command not found`；`VERIFY_COMMANDS` 默认空 → `allowed_shell` 仅 3 条 → worker 跑不了验证门/推不了 PR。tmux worktree 靠在主仓子树（`.claude/worktrees/`）的路径巧合白嫖向上解析（G28），Orca 路径打破后塌方。

### 新增

- `scripts/spawn-worker-deps.sh`（独立 source 文件，不加剧 spawn-worker.sh 膨胀）：`ensure_worktree_deps` 项目类型感知依赖补偿（Node 软链 `node_modules` / Rust cargo 共享 / Python venv 路径敏感标 blocked）；`inject_default_verify_commands` 按 `package.json` scripts 注入默认 `npm run typecheck/lint/test/build` 到白名单（PM 显式 `--verify-cmd` 优先不覆盖）。
- `spawn-worker.sh` source deps + 两处调用（worktree 创建后 `ensure_worktree_deps`、`write_install_authorization` 前 `inject_default_verify_commands`）。
- `clean-worktree.sh` 删 worktree 前安全 unlink `node_modules` 软链（`[ -L ] && rm -f` 无尾斜杠，绝不跟随删主仓）。

### 改进

- `SKILL.md` §3.2 + `worker-prompt.md` + G31 lesson（`references/09`）说明依赖补偿 + 默认 verify 机制；G31 含「统一 Orca worktree 路径到主仓」的 A-否决查证（Orca `worktree create` 无 `--path`，软链是唯一实际补偿）。

## [2.5.0] - 2026-08-13

### 修复

- Harness 权限改为对完整可证明祖先链取白名单交集；弱宿主嵌套 Codex/Claude Code 仍只能保留弱权限，链路读取不完整时失败关闭。
- 新增 worker backend/启动命令身份绑定，拒绝标签伪装、命令链、不透明 wrapper 与任意命令替换；安装守卫的 prompt-only 降级不再能绕过 backend 身份门禁。
- Harness 的 Orca 证据统一使用版本匹配的 `orca-runtime.sh`，避免权限检测与 worker 控制选择不同 CLI。

### 新增

- 新增跨 worktree 的 provider 原子并发租约：按个人配置在副作用前占槽，启动后绑定精确 tmux session 或 Orca terminal，并在真实资源结算后释放。
- 租约存放于 Git common dir 的可信根，使用文件锁与原子写入；释放同时校验可信路径、session、资源句柄和运行时存活状态，未知状态失败关闭。
- 新增 `test-worker-command-policy.sh` 与 `test-provider-lease.sh`，覆盖四后端 renderer、wrapper、伪装命令、额度竞争、陈旧租约、越界路径和存活资源提前释放。

### 改进

- Orca worktree 创建显式继承项目 setup 策略；继续采用门禁优先的两阶段启动，不直接切换会在权限文件落盘前启动 Agent 的 `worktree create --agent`。
- 当前运行合同明确收口为 Claude Code、Codex、CodeBuddy、QoderWork CN 四个 backend；OpenCode/custom 等旧内容只保留为历史调研或独立诊断，不构成派发授权。
- 同步 `SKILL.md`、Orca reference、个人配置模板和根 README 的 v2.5.0 说明，传统 tmux 路径保持可用。

### 验证

- Harness 层级门禁 26/26、命令身份门禁 15/15、provider lease 原子与生命周期回归全部通过。
- 在 Orca 1.4.180 中使用本地无模型调用的假 Codex 完成真实 worktree/terminal/metadata/lease/close/clean 闭环；终端关闭后为 `connected=false`、`writable=false`，未消耗模型额度。

## [2.4.0] - 2026-08-13

### 新增 — Harness 调用层级门禁

- 新增 `config/harness-backend-policy.json` 和 `scripts/harness-backend-policy.sh`：Claude Code/Codex PM 可派发 Claude Code、Codex、CodeBuddy、QoderWork CN；CodeBuddy 与 QoderWork CN PM 只能派发自身。
- 派发 backend 收口为上述四种；旧版兼容代码中出现的 OpenCode、custom 或未知 backend 均不再获得 spawn 权限，防止个人配置扩张授权面。
- `spawn-worker.sh` 在创建 worktree/terminal 之前从真实进程祖先识别 PM 宿主，并在 Orca 能唯一定位 working agent 时交叉校验；多 Agent 共用 worktree 时不让模糊 UI 信号覆盖进程证据，未知、真实冲突或不可证明身份仍失败关闭。
- `--pm-harness` 仅作为预期身份断言，不能覆盖运行时证据或向上提权；授权结果写入 `METADATA.runtime.harness_authority`。

### 测试

- 新增 `test-harness-backend-policy.sh`，覆盖 10 个允许组合、8 个拒绝组合、未知 backend、运行时识别及伪造宿主断言。
- 既有 Orca/tmux smoke 改用已配置 backend，确保层级门禁进入真实 spawn 回归而非只做静态文档约束。

## [2.3.0] - 2026-08-12

### 修复 — Orca runtime 与 supervised 生命周期

- Orca auto-detect 改用 `worktree current` 的实际项目路径，不再依赖真实会话可能缺失的 `TERM_PROGRAM` / `ORCA_WORKTREE_ID`；新增 `scripts/orca-runtime.sh` 统一版本匹配 CLI。
- supervised 注册固定为共享 Run 下的 `task-create → worker-start --terminal`，worker-start 成为唯一任务注入器；注册失败返回非零并保留恢复证据，不再静默降级为“看似 supervised”。
- Sentinel 不再根据 STATUS/timeout 自动 stop、release 或关闭 supervised terminal；`worker_done`、完整 Delivery、reuse/release/retain、ack 成为单一结算顺序。
- `clean-worktree.sh` 仅在 Dispatch 已 settled 且 terminal accounting 可证明安全时结算，active/unknown/release_pending/release_unknown 均失败关闭。
- `pm-orchestrate.sh` 扩展为 supervised / terminal-managed / tmux 三模式，支持 Dispatch guidance、worker transcript、show、Delivery wait、reply、release、retain 和显式 ack。
- supervised 注册保存并显式传递 coordinator handle，修复真实 Run 下的 `consumer_fenced`；external terminal 清理增加 settled 状态、ownership/reason 与精确句柄四重校验。
- Codex render 识别已固定相同 sandbox/approval 的本地安全 launcher，避免重复参数导致 CLI 启动失败；不匹配或不可证明时仍显式传参。

### 改进 — Orca-first 多 CLI 总控

- CodeBuddy、QoderWork 和 custom CLI 可保留在 Orca terminal-managed 层，由 UI 展示 worktree/branch/terminal，PM 用 terminal read/send/wait 巡检；未被 Orca 识别时不伪造 Task/Dispatch。
- trust/permission/external-import watcher 支持 Orca terminal read/send，不再因脱离 tmux 而失效。
- `worktree-status.sh` 和 `pm-monitor.sh` 统一使用实际 Orca CLI；文档重写为双层能力、运行时检测、共享 Run、UI 状态来源和恢复边界。
- terminal-managed `read` 支持 Orca cursor 增量读取，并明确 `tui-idle` 只是 liveness/readiness，不能冒充任务完成信号。

### 安全与 Git

- 根 `.gitignore` 新增 `**/config/*.bak*`，阻止带真实凭证的 provider 配置备份进入普通 Git 历史。
- 核查确认既有 Orca 提交已经进入 `origin/main`，因此不重写公开历史，改用本版本前向修复 metadata/version 漂移与契约问题。
- `SKILL.md` 新增本地命令、worktree/terminal、Orca 状态写入、清理与 provider Token 的权限/副作用声明。
- `SKILL.md` 从 1000+ 行压缩为核心路由与生命周期入口，backend、checkpoint、Sentinel 和历史踩坑继续按需下沉到既有 references，恢复 Progressive Disclosure。

### 测试

- 新增 `smoke-orca-control-plane.sh`，以本地 fake CLI 验证注册顺序、Dispatch 路由、worker-read、Delivery wait 不自动 ack 及 release/retain/ack 命令。
- `smoke-orca-worker.sh` 覆盖无宿主环境变量识别、opt-out、轻量模式边界与 supervised 单一注入。
- 修正 `claude --bare` 安装门禁回归断言，与既有“明确记录 prompt-only 降级”设计一致。
- 真实前向矩阵：Claude Code 与 Codex 在 Orca supervised 中完成 `worker_done → Delivery → external terminal 结算 → ack`；CodeBuddy 在 Orca terminal 中得到完整响应；QoderWork 验证 cursor history 与批处理响应；传统 tmux 下 Codex 完成响应，Claude 启动/收发链路通过但当次 provider 因 429 额度限制未完成模型响应。
- 六份 Claude provider settings 探针 5 份通过；MiniMax M2.7 返回 401，需更新本地凭证。

## [2.2.0] - 2026-08-12

### 新增 — PM 控制 worker 统一入口（Task-034）

PM 90% 场景用 `pm-orchestrate.sh` 一个统一入口控制 worker（ORCA / tmux 双模式自动判断），不用手敲 `orca terminal send` 或 `tmux send-keys`。

- `scripts/pm-orchestrate.sh` 新脚本：子命令 `send / read / peek / wait`
- 读 `<worktree>/.claude/agent-sessions/<session>/METADATA.json` 自动路由：
  - `session.orca.terminal_handle` 非空 → ORCA（`orca terminal send/read/wait`）
  - 否则 → tmux（`tmux send-keys/capture-pane`，session 名 = `<session>`）
- `send` 超长（>500 字符 或含反引号/`$`/`|`/``` ```）自动走 SKILL §5.2 WORKER_PROMPT.md + 短 Read 指令（避免终端注入转义问题）
- `peek` = `read --lines 15`（PM 快速 peek 常用）
- `wait` tmux 模式无原生 tui-idle，降级 sleep（建议用 sentinel.sh）

端到端验证（ORCA claude worker）：`send --text "请只回一句：pm-orchestrate send OK"` → `read --lines 100` 显示 `❯ 请只回一句：pm-orchestrate send OK` + `⏺ pm-orchestrate send OK`，PM 一个命令管 worker ✓。

- `references/13-pm-orchestrate.md` 新 reference：双模式自动判断 + 子命令 + 与 sentinel/pm-monitor/CLI 兜底的关系 + 实战范例 + 已知限制
- SKILL §7.1 ORCA PM 分支加 pm-orchestrate 段落（替代手敲 orca terminal send）
- SKILL §10 references + scripts 列表加 references/13 和 pm-orchestrate.sh

非 ORCA / tmux 不受影响（向后兼容，PM 不传也用 tmux 默认）。

## [2.1.0] - 2026-08-12

### 新增 — ORCA 检测 + STATUS.json 分层互补（Task-032）

sentinel ORCA 模式 done 判定加双信号：`STATUS=done` 时先查 `orca worktree ps` 的 agent state，`working` 拒绝认终态（抗 worker LLM 谎报 done），`done/idle` 才 sync + exit。ORCA 检测（进程层客观）+ STATUS.json（任务层自报告）分层互补。实测：claude worker 跑 sleep 30（state=working）+ 谎报 done → sentinel 12s 内 5 次 SENTINEL_ORCA_STATUS_CONFLICT 拒绝误杀。

- `sentinel.sh`：`orca_agent_state()` 函数（查 worktree ps 的 `.worktreeId` 匹配 + `agents[0].state`）；done 分支双信号判定

### 新增 — ORCA supervised 深度对接（Task-033）

spawn-worker `--orca-supervised` flag：ORCA 模式 spawn 后把 worker terminal 纳入 ORCA supervised 体系（run-create + task-create + worker-start --terminal），保留 provider env 隔离。worker 出现在 `worker-list`，绑定 task + worktree resource，可被 send/reply/inbox + gate 管理。

- `scripts/orca-supervised-register.sh` 新 helper：run-create + task-create + worker-start --terminal --worktree --task；输出 run_id/task_id/dispatch_id（KV）。worker-start 前 sleep 6s（runtime 注册延迟）+ 单次不 retry（retry 致 task_not_startable/failed）+ worker-list 兜底查 dispatch（应对 runtime_unavailable 但 server 端成功）
- `spawn-worker.sh`：`--orca-supervised` / `--task-spec` / `--task-title` flag；ORCA 模式调 helper；METADATA `session.orca.supervised.{run_id,task_id,dispatch_id}`；SENTINEL_CMD 加 `--dispatch-id`
- `sentinel.sh`：`--dispatch-id` 参数 + `sync_orca_supervised_release()`；done→worker-release, failed/timeout→worker-stop
- `clean-worktree.sh`：读 METADATA dispatch_id，清理时 worker-stop（在 orca worktree rm 前）
- `references/12-orca-cli-worker.md` §11：supervised 体系 / spawn 集成 / 全生命周期闭环 / helper 踩坑 / PM 巡检增益

端到端验证（真实 claude worker）：spawn `--orca-supervised` → worker-list workerState=ready → sentinel done worker-release → clean --execute worker-stop + worktree rm，全链路通。

### 改进 — ORCA 模式 task-032/033 配套

- SKILL §6.5 加 supervised 深度对接 + 分层互补段落
- 非 ORCA / 不加 `--orca-supervised` 零变化（向后兼容 v2.0）

## [2.0.0] - 2026-08-12

### 新增 — ORCA CLI worker backend（DEC-114）

PM 在 ORCA 桌面端内嵌终端里调 `spawn-worker.sh` 时，auto-detect 走 ORCA worktree + ORCA terminal 路径，ORCA UI 直接反映 worker 生命周期（spawn 立即出卡 `in-progress`、sentinel 终态自动切 `completed`/`in-review`、stale 同步 `in-review`、clean-worktree 删 ORCA 跟踪）。

**触发**：`TERM_PROGRAM=Orca` + `ORCA_WORKTREE_ID` 非空 + worktree path 段 = `PROJECT_DIR` git toplevel + `orca status --json` 成功 + capability 含 `terminal.multiplex.v1`。命中走 ORCA；非 ORCA 终端 / 跨 repo / `--no-orca-mode` 走原 tmux 路径不变。详见 SKILL §6.5 + `references/12-orca-cli-worker.md`。

**改动**：

- `scripts/spawn-worker.sh`：新增 `detect_orca_mode()` / `orca_worktree_create()` / `orca_terminal_create_and_send()` 三个 helper + `--no-orca-mode` flag + METADATA `session.orca` 子块（mode / worktree_id / worktree_path / terminal_handle / tui_ready_method / app_version / capabilities）；ORCA 模式跳过 trust/permission/external-imports dialog 监控（ORCA 桌面端自管）
- `scripts/sentinel.sh`：新增 `--terminal-handle --worktree-id` 双路径（与 `--tmux-session` 二选一）+ `sync_orca_worktree_status()`（done→completed / failed→in-review / timeout→in-review）
- `scripts/pm-monitor.sh`：新增 `orca_worktree_set_status()` helper；`CHECKPOINT_STALE` + `WORKER_STALE_NO_COMMIT` 两个 emit 后同步 ORCA `in-review`
- `scripts/clean-worktree.sh`：tmux kill 后加 `orca worktree rm --force` 同步清理 ORCA 跟踪（dry-run 友好）
- `scripts/worktree-status.sh`：加 ORCA 只读状态块（`ORCA_WORKSPACE_STATUS` / `ORCA_CARD_STATUS` / `ORCA_COMMENT`）
- `references/12-orca-cli-worker.md`：新建完整 Level 2 reference（9 节：边界 / 检测协议 / ORCA API 速查 / METADATA 锚点 / sentinel 双路径 / pm-monitor 同步点 / clean-worktree 清理 / 已知限制 / 实战范例）
- `SKILL.md`：§6.5 ORCA 终端模式新节 + §7.1 加 ORCA PM 分支 + §10 references 加 references/12

### 改进 — `ensure-claude-path.sh` 参数化为 `ensure_in_path <bin>`

候选目录追加 `/Applications/Orca.app/Contents/Resources/bin`，让 spawn-worker.sh ORCA 模式可直接 `ensure_in_path orca` 探测 ORCA CLI。保留 `ensure_claude_in_path` 作为 `ensure_in_path claude` 的别名，所有现有调用方零改动。

### Known Limitations / Follow-up

- ORCA 模式与 `--no-worktree` 轻量模式互斥（ORCA worktree 必须有 git 仓），命中轻量模式自动回落 tmux
- ORCA app 未运行 / `orca` CLI 不在 PATH / 缺 `terminal.multiplex.v1` capability → fail-loud `exit 64`（提示 `orca open` 或 `--no-orca-mode`）
- **`--command` 必须是 agent CLI（claude/codex/opencode）ORCA 才自动识别为 agent session**（references/12 §9 关键发现 1）；用 shell 命令测试时 agent session 不显示，但 worktree 卡片 + workspace-status 仍正常
- **端到端验证（2026-08-12）暴露并修复 4 个 jq 嵌套字段 bug**：`worktree create` / `terminal create` / `terminal read` / `worktree show` 响应都嵌套在 `.result.<resource>`（不是顶层）。共性模式记入 references/12 §9 关键发现 3
- **下一步探索**：ORCA 有更高层的 `orchestration worker-start` / `task-create` / `dispatch` / `gate-create` / `send` 体系（supervised worker + 任务 + decision gate + inter-agent 消息）。当前 skill 对接底层 `terminal create`，后续评估切到 `orchestration worker-start` 层（references/12 §9 关键发现 4）

## [1.20.5] - 2026-08-05

### 改进 — qoderclicn v1.0.45 + codebuddy v2.115.0 模型清单同步

CLI 升级后模型清单大变化，references/07 §4 + references/06 §0/§7.2/§5A + personal example + SKILL §2.4 全部同步实测（`qoderclicn --list-models` + `codebuddy --help --model` 权威输出）。

#### qoderclicn（1.0.24 → 1.0.45）

- **新旗舰 `Qwen3.8-Max`**：`qmodel_latest` alias 仍解析 3.7-Max（没跟 3.8）→ **推荐用具体名 `-m Qwen3.8-Max`**
- **新增 `GLM-5.2` / `Kimi-K2.7-Code` / `MiniMax-M2.7`**（旧 alias `gm51model`/`kmodel` 映射过时）
- 模型表从"alias key"改成"`--list-models` 实际名（推荐）+ 旧 alias（兼容过时）"双列
- 普通终端用：`~/.local/bin/qoderclicn` symlink（指向 .app bundle）+ `qoderclicn login`，之后 `qoderclicn --list-models` / `-m Qwen3.8-Max`

#### codebuddy（2.103.3 → 2.115.0）

- `--model` 权威列表：`auto, hy3, glm-5.2, glm-5.1, glm-5v-turbo, minimax-m3, kimi-k3-1, kimi-k2.7, kimi-k2.6, deepseek-v4-flash, deepseek-v4-pro, custom-local:*`（references/08 §4.1 主力已覆盖；新增 `kimi-k3-1` / `glm-5v-turbo` / `custom-local` 系列）
- 用户偏好 `hy3` / `deepseek-v4-flash` 仍在 ✓

#### personal example + SKILL §2.4

- `backend_model_routing.qoderwork-cn.default_models`：`["qmodel_latest",...]` → `["Qwen3.8-Max", "Qwen3.7-Max", "Qwen3.7-Plus", "DeepSeek-V4-Pro", "GLM-5.2", "Kimi-K2.7-Code"]`（具体名优先）
- SKILL §2.4 qoderwork-cn 偏好同步 + "推荐具体名，旧 alias 过时"提示

### Test

- `qoderclicn --list-models` → 10 模型（Qwen3.8-Max 新旗舰确认）；`qoderclicn --version` → 1.0.45
- `codebuddy --version` → 2.115.0
- `~/.local/bin/qoderclicn` symlink 普通终端 PATH 可达（`which qoderclicn` + `--version` 确认）
- 纯文档/配置同步，smoke 不涉及

## [1.20.4] - 2026-08-05

### 改进 — CodeBuddy 拼写校正 + ref 08 结构精简

#### 拼写校正（qodebuddy → CodeBuddy，腾讯产品名）

修正全 skill 共 59 处 `qodebuddy`（错误拼写）→ `CodeBuddy`（正确产品名，腾讯旗下）。文件系统客观路径不动（`codebuddy` CLI 二进制名、`WorkBuddy.app` app bundle、`~/.codebuddy/` / `~/.workbuddy/` 配置目录、`CODEBUDDY_*` 环境变量）。

- **references/08-codebuddy-cli-worker.md**：40 处（全文 Python 批量替换）
- **SKILL.md**：7 处 + 4 处文件名引用 `08-qodebuddy-cli-worker.md` → `08-codebuddy-cli-worker.md`
- **references/06-agent-cli-reference.md**：6 处（表格行、章节标题、注释）
- **scripts/render-runtime-profile.sh**：3 处注释
- **scripts/spawn-worker.sh**：1 处注释
- **scripts/check-dependencies.sh**：1 处提示信息
- **config/orchestration-personal.example.json**：1 处注释 + 文件名引用

#### ref 08 结构精简（945 → 858 行）

- **合并旧 §10（2026-07-05 五轮）+ 旧 §14（2026-07-08 三轮）→ 新 §10「spawn 实战坑点」**：原两节讲同一批坑（权限/Enter/session 断流）的二次叙述，按"坑点类型"重组，两张速查表合一。新增 §10.6 session 断流、§10.7 原生 `--worktree --tmux` 对比测方向、§10.8 合并速查表。删除旧 §10.7（§9 修订说明，合并后失效）和整个旧 §14。
- **删除旧 §6.6 / §6.7 历史实测段**：snapshot-copy-into-worktree pattern 已固化为 SKILL.md §2.3 + DEC-037；render-runtime-profile 支持情况见 `--help`。保留 §6.6 精简指针段。
- **版本记录区压缩**：8 条 2026-07-08 过程性微调（"首次"~"第七次"逐条 smoke test 中间态）合并为 1 条关键节点。
- **交叉引用校准**：L330 旧 `§6.7` 引用改 `§5`（MCP 关闭规则实际位置）。

### 待办清零 + qoderclicn trust dialog 修复（本次推进）

- **ref 08 §3 主标题补齐 + L159 孤立 §2.6 消除**（上面"待办事项"两条其实是同一问题）：L159 `### 2.6`（孤立重复编号）→ `## 3. 命令行用法`（§3 主标题，§3.1/§3.2 归属正确）。历史遗留待办清零。
- **Task-031 trust_auto backend-specific 选项处理**（`scripts/spawn-worker.sh`）：qoderclicn 2 选项 trust dialog（1=Trust folder / 2=Don't trust and exit，**默认高亮 option 2 Don't trust**）被旧 generic fallback `Down×3+Enter` 误选 option 2 = Don't trust → qoderclicn 立即 exit 42。修复：generic fallback 加 `WORKER_BACKEND` case，`qoderwork-cn|qoderclicn` 发数字键 `"1"` 选 Trust folder（与 `permission_auto` `"2"` 同数字键模式，不依赖默认高亮）；codebuddy（4 选项）等保留 `Down×3+Enter`。
- **qoderclicn 真机端到端验证（Task-031）**：spawn-worker **5 秒 exit** + `SPAWN_WORKER_TRUST_AUTO: trust dialog detected (qoder 2-option), selecting option 1 Trust folder (key '1')` + qoderclicn **过 trust 进 REPL ready**（pane: `Thinking ▪ 准备好了，请告诉我需要做什么` + `Qwen3.7-Max Model · ctx 15%`，**无 "The current folder is not trusted. Exiting."**）。qoderclicn backend 端到端可用 ✓。

### Test

- `bash scripts/smoke-auto-bypass.sh` → **21/21 PASS**
- `bash scripts/smoke-sentinel.sh` / `smoke-tmux-worker.sh` / `lint-wait-script.sh` → 全 OK
- `bash -n scripts/spawn-worker.sh scripts/render-runtime-profile.sh` → OK
- **qoderclicn 真机 throwaway（Task-031）**：5s spawn-worker exit + trust 处理 + REPL ready ✓

## [1.20.3] - 2026-08-05

### 新增 — folia Wave-1 + W1/W2 dogfood 实战撞坑修复（Task-026 ~ Task-030）

本轮在 v1.20.2 setsid 修复基础上，针对 W1 (claude-code) + W2 (codebuddy) dogfood 撞坑沉淀的 G29 6 项实战问题（references/09-parallel-lessons.md）完成 5 项修复。**Task-026 真机 throwaway 验证：codebuddy spawn-worker 主进程 22 秒 exit**（v1.20.2 W2 撞坑 120s+ SIGTERM），节省 ~98 秒，< 60s 目标达成。

#### scripts/spawn-worker.sh（Task-026）

- **`resolve_backend_defaults` 加 `codebuddy/qoderwork-cn/qoderclicn` 默认 `PERMISSION_AUTO=0`**（与 `claude-code` 同分支）：acceptEdits 仍弹 dialog（references/08 §14.1），但同步监控空等浪费 + 撞 PM Bash 2min timeout（v1.20.2 W2 撞坑实测）。bg 段（`permission_auto_bg` setsid）独立处理 dialog，不依赖 sync。
- **`trust_auto` backend-specific max_wait**：`codebuddy/qoderwork-cn/qoderclicn` 默认 30→15s（acceptEdits 不弹 trust dialog，30s 空等浪费）。

#### scripts/render-runtime-profile.sh（Task-027）

- **`resolve_settings_path` 函数**：`--settings` / `--provider-registry` 相对路径自动转绝对（fallback：render cwd → `SCRIPT_DIR` → `SKILL_DIR/config/`）；绝对路径验证存在；URL 跳过。消除 W1 撞坑（`config/*.json` 相对路径在 worktree cwd 找不到 + gitignore）。
- **5 场景测试全过**：相对路径 / basename / 绝对存在 / 绝对不存在（exit 64）/ 相对不存在（exit 64）。

#### scripts/dependency-install-guard.py（Task-028）

- **`is_safe_lifecycle_command` 加 `date` 允许**（拒绝 `-s` / `--set` / `--reference` 改系统时间）：解决 W2 写 `STATUS.updated_at` 时 `date -u +"%Y-%m-%dT%H:%M:%SZ"` 被 `SHELL_COMMAND_NOT_ALLOWLED` 拦的撞坑。
- **12/12 测试通过**：W2 场景 allow + 安全（`-s` / `--set` / `--reference` deny）+ 回归（`pwd` / `stat` 不变）。

#### templates/worker-prompt.md（Task-029 + Task-030）

- **Bootstrap Isolation Gate 加 STATUS/RESULT path sanity 硬约束（Task-030）**：所有 `STATUS.json` / `RESULT.md` / `PATCH_SUMMARY.md` 必须在 `$(pwd)/.claude/agent-sessions/<session-id>/` 下，写错位置 = done 信号无效。解决 W2 写 `skills/.../STATUS.json` 撞坑。
- **Process step 8 加 Commit-Verify 硬约束（Task-029）**：commit 前必跑 Verify 全部 PASS；commit 后 `git show --stat HEAD` + `git diff --stat HEAD~1..HEAD` 验证文件实际改了；LLM 幻觉 done = done 信号无效。引用 W2 `64cd3d7` 撞坑（commit message 说改 4 文件但实际破坏 smoke + 错位置 STATUS）为实证。

### Test — 多轮验证全绿

- `bash scripts/smoke-auto-bypass.sh` → **21/21 PASS**（v1.18.3 + v1.18.4 + v1.20.2 + v1.20.3 + HRA-001 exit 64 断言）
- `bash scripts/smoke-sentinel.sh` → SMOKE_SENTINEL_OK
- `bash scripts/smoke-tmux-worker.sh` → SMOKE_TMUX_WORKER_OK
- `bash scripts/lint-wait-script.sh` → LINT_WAIT_SCRIPT_OK
- `dependency-install-guard.py` `is_safe_lifecycle_command` → 12/12 PASS（Task-028）
- `render-runtime-profile.sh` `resolve_settings_path` → 5/5 PASS（Task-027）
- **真机 throwaway codebuddy**（Task-026）：spawn-worker 主进程 **22 秒 exit**（< 60s 目标；v1.20.2 W2 撞坑 120s+ SIGTERM），`accept edits on` ready，session ALIVE

### Known Limitations / Follow-up

- **Task-026 qoderclicn throwaway 未真机验证**：harness 自动拒绝 spawn qoderclicn 的二次执行（视为"launch-workbuddy daemon force-killed"）；codebuddy 验证通过 + 改动代码对 `codebuddy/qoderwork-cn/qoderclicn` 三个 backend 一致 case pattern，逻辑上 qoderclicn 应有同等效果。下次派 worker 跑 qoderclicn 真机复测。
- **TASKS.md（本地 gitignored）**：记录 v1.20.3 候选 DRAFT（`Task-026` ~ `Task-030`）已全部完成，可清理或转历史。

### Hotfix v1.20.3.1 — bg watcher 真机端到端修复（2026-08-05 当日）

**严重 bug**（v1.20.2 引入，v1.20.3 端到端真机验证发现）：`spawn-worker.sh` 的 `permission_auto_bg` / `external_imports_auto` 后台 watcher 用 `nohup` / `setsid`（外部 binary）调用 spawn-worker.sh 的 bash 函数 —— 但 nohup / setsid 子进程找不到父 shell 函数定义，报 `command not found`，**bg watcher 从未启动**。v1.20.2 假设 `setsid / nohup` 能调用 bash 函数是错的（v1.18.3 旧版用 subshell `( ... & disown )` 模式继承函数能跑）。

- **修复**：`scripts/spawn-worker.sh` PERMISSION_AUTO_BG + EXTERNAL_IMPORTS_AUTO 段改回 v1.18.3 subshell inherit function 模式（`( func "$SESSION" & disown ) >/dev/null 2>&1 < /dev/null &`）。已知限制：spawn-worker SIGTERM 时同进程组 bg 会死（v1.18.3 限制）；mitigation = Task-026 让 spawn-worker 主进程 < 60s exit（v1.20.3 验证 19 秒），bg 有时间跑完（dialog 通常 30s 内弹）。
- `scripts/smoke-auto-bypass.sh` 的 v1.20.2 检查 #5（`permission_auto_bg`）/ #17（`external_imports_auto`）—— 原来匹配 `setsid / nohup` 字符串改为匹配 subshell inherit function 模式（v1.20.3.1 hotfix 实现形式）。

#### 真机端到端验证（codebuddy + `--permission-mode acceptEdits`）

- spawn-worker 主进程 **19 秒 exit**（< 60s ✓）
- worker 跑 `pwd` 命令：bg watcher 真启（PID detached subshell, PPID=1）+ 自动按 `2` 处理 `"Do you want to proceed?"` dialog（session-allow）+ pwd 命令输出（端到端通过）
- `bash scripts/smoke-auto-bypass.sh` → **21/21 PASS**（hotfix + smoke check 更新）
- `bash scripts/smoke-sentinel.sh` / `smoke-tmux-worker.sh` / `lint-wait-script.sh` → 全 OK

## [1.20.2] - 2026-08-05

### 新增 — folia Wave-1 实战三修 + 本 skill 自身 dogfood 验证

本轮来自 folia Wave-1（2026-08-04/05，claude-code + codebuddy 5-worker）实战沉淀，覆盖 spawn / 监测 / prompt 投递 / 收口四个环节。**Task-016/017 由本 skill 自身 dogfood**（W1 worker 改 `pm-sentinel-response.md`）真机完成，验证 spawn-worker.sh 修复 + sentinel 事件驱动 + 超长 prompt 投递全链路。

#### spawn-worker.sh（Task-019/020/021）

- **Task-019 — claude-code `--bare` 自动降级 prompt-only**：`render-runtime-profile.sh` 对 claude-code provider-isolation 默认加 `--bare`（必需：skip keychain/OAuth/CLAUDE.md auto-discovery），但 `--bare` 触发 spawn-worker install-guard fail-closed（`:520-528` 要 PM 手写 `--allow-prompt-only-install-guard`）。新增 `claude_command_has_bare()` 检测：claude-code + `--bare` 自动降级 prompt-only + 内置来源文本（`CLAUDE_CODE_BARE_AUTO_DEGRADE=1`，`--no-claude-code-bare-auto-degrade` opt-out），PM 不再手写降级。`--safe-mode` / `--setting-sources` 排除 local / 缺 claude token 仍 fail-closed（非 `--bare` 不自动降级）。**真机验证**：dogfood W1 spawn 输出 `SPAWN_WORKER_BARE_AUTO_DEGRADE: claude-code --bare detected, install-guard auto prompt_only_degraded (source recorded)`，worker 正常启动（banner `glm-5.2[1M]`）。
- **Task-020 — `external_imports_auto()` 监控 claude-code external imports dialog**：CLAUDE.md `@import` 触发 claude 首启弹 "Yes allow external imports" dialog（v1.18.4 默认关 trust/permission 不覆盖此类）。新增 `external_imports_auto()` 后台 watcher（120s，option 1 默认放行），claude-code 默认开（`EXTERNAL_IMPORTS_AUTO=1`，`--no-external-imports-auto` opt-out）。`--bare` 模式下 CLAUDE.md 被 skip、dialog 通常不弹，watcher 作兜底无副作用。
- **Task-021 — `permission_auto_bg` setsid + codebuddy Bash timeout 文档**：`:1207` `( permission_auto_bg & disown ) &` 改 `setsid`（macOS 无 setsid 时 fallback `nohup + disown`），spawn-worker 被 SIGTERM 时 watcher 尽量存活。SKILL §6 补"codebuddy 同步监控逼近 PM Bash 2min timeout，建议 PM Bash timeout 调到 180s+"。

#### pm-sentinel-response.md（Task-016/017，W1 dogfood 完成）

- **Task-016 — §2 显式归类 exit 137/143（SIGKILL/SIGTERM）**：exit code 表补 137/143 两行；新增 §2.5「Exit 137/143（signal kill）」分支（session 状态 × STATUS 终态组合诊断 + 137 OOM/harness 强杀/手动 kill + 143 温和）；§4 降级段加指向 §2.5 的交叉引用。folia Wave-1 复盘：sentinel 被 signal 杀时 PM 缺明确分支。
- **Task-017 — §1 step 2 `tail -5` 改 grep 关键标记**：长任务 sentinel 持续写 `SENTINEL_PENDING`（5s/行）刷掉前面的 TERMINAL/TIMEOUT/UNKNOWN_STATUS。改 `grep -E "SENTINEL_(TERMINAL|TIMEOUT|UNKNOWN_STATUS|FAILED)" | tail -5` + 保留 `tail -5` 看上下文。

#### cron-monitor-prompt.md（Task-024）

- **Task-024 — 自删改硬指令第 0 步**：prompt 模板判定段加第 0 步硬指令（最高优先级）：读所有 worker STATUS，全终态（done/failed/blocked/stopped）且无 pending PR/未合入 → 立即 `CronDelete` 本 cron，不做巡检。folia Wave-1：3 worker 全 done 后 cron 仍触发一次兜底巡检，PM 手动 CronDelete。

#### SKILL.md 文档（Task-022/025）

- **Task-022 — §5.2 超长 prompt 投递标准模式**：Full Worker Prompt 填任务后超 2-4 KB + 特殊字符，直接 `send-keys -l` 有转义/截断风险。标准模式：写 `{session_context}/WORKER_PROMPT.md` + `send-keys` 短读取指令（"请 Read WORKER_PROMPT.md 并执行"）。folia 3 worker + 本轮 W1 dogfood 均此模式，100% 投递成功。
- **Task-025 — §3 第 11 步 webview 项目分流**：Tauri/Electron/WKWebView 的 webview 不暴露 macOS a11y，orca/computer-use 读不了（`role:null`）也写不了（click 不触发 React 事件）。web 交互必须走 Playwright e2e，orca 仅原生控件 + screencapture。folia（Tauri）#92 验证：orca 4 次 click 截图字节零变化。修正 TASKS 里 stale 的 §3.11 引用（实际是 §3 第 11 步）。

### 改进 — smoke HRA-001 修复（skill-lint 验收触发）

skill-lint `harness_failure_audit` 基线报 3 处 hard finding（HRA-001：测试 `|| true` 丢被测命令退出码）。本轮全部修复：
- **`smoke-sentinel.sh:167/170`**：usage 路径 `|| true` 改显式断言 exit 64（no-arg + --bogus 都 exit 64）+ `assert_contains`。
- **`smoke-auto-bypass.sh:87/143`**：spawn-worker 无参 `|| true` 改显式保存 exit code + 断言 exit 64（#6 加新 check）；smoke 总数 13 → 21（v1.18.4 + v1.20.2 段 + exit 64 断言）。
- **`smoke-provider-settings.sh:86`**：provider 调用 `|| true` 改保存 exit code，区分 ERROR（provider exit≠0 + 无 token）vs FAIL（exit 0 + 无 token），PASS 若 exit≠0 附诊断。⚠️ 本项未真机验证（provider 调用非确定，依赖网络/token），逻辑保留 capture-response-诊断语义。

### 入库 — G25-G28 FaroPDF Wave 1+2 实战沉淀（references/09-parallel-lessons.md）

G25-G28（2026-08-04 FaroPDF 5-worker：codebuddy W1 + claude-code W2-W5）此前已写进 `09-parallel-lessons.md` 工作区但未入 CHANGELOG，本轮正式入库：
- **G25**：spawn-worker backend token 检查（`--command` basename 必须含 backend；bash launch.sh wrapper 会触发 fail-closed，改用 backend 二进制直起 + `/tmp/empty-mcp.json` 文件避 tmux 引号吞）。
- **G26**：claude-code worker 派 subagent 不可用（glm 第三方 provider API 1211/500）→ 主进程 Grep 替代 + prompt 显式禁 subagent。
- **G27**：漏 commit 也犯 claude-code（不只 codebuddy）—— 收口必查 `git log main..HEAD` 非空。
- **G28**：verify 用主仓 node_modules（worktree 向上解析，免 npm ci）+ 提效/降 token 汇总表。

### Test — dogfood 链路全验证（本 skill 自身做 PM）

- Task-016/017 由 W1 worker（claude-code/glm-5.2[1M]）在 worktree 完成：spawn（render + settings 绝对路径 + `--bare` 自动降级）→ 投递（§5.2 WORKER_PROMPT.md + 短指令）→ worker 自主执行（Isolation Gate + STATUS + 改文件 + Verify + commit `755ffe3` + done）→ sentinel exit 0 唤醒 PM → 收口 apply。
- `bash scripts/smoke-auto-bypass.sh` → **21/21 PASS**（v1.18.3 + v1.18.4 + v1.20.2 段 + HRA-001 exit 64 断言）。
- `bash scripts/smoke-sentinel.sh` → SMOKE_SENTINEL_OK（含 HRA-001 exit 64 断言）。
- `bash scripts/smoke-tmux-worker.sh` → SMOKE_TMUX_WORKER_OK。
- `bash scripts/lint-wait-script.sh` → LINT_WAIT_SCRIPT_OK。

### 关联

- 来源：folia Wave-1（2026-08-04/05，5-worker / 2-backend）+ FaroPDF Wave 1+2（2026-08-04）实战沉淀。
- 关联章节：§2.1 防逃逸门禁、§3.8 spawn 后核验、§3 第 11 步 webview 分流、§5.2 超长 prompt 投递、§6 启动方式（setsid / Bash timeout）、§7.2/§7.3 sentinel + cron。
- 已知 follow-up：Task-019/020/021 的 codebuddy 端真机验证（本轮验证 claude-code 端；codebuddy 同步监控提速 + setsid 在 codebuddy spawn 的效果待 codebuddy Wave 验证）。

## [1.20.1] - 2026-08-01

### 新增 — 非 CLI 主会话不宜扮演 PM 的适用边界

- **`references/09-parallel-lessons.md` G24（新）**：记录 2026-08-01 FaroPDF 仓审计 Wave 实战教训。在 ZCode 这类**非 CLI 的 harness 内嵌 agent**会话里扮演 PM、调 `spawn-worker.sh` + tmux + sentinel 派只读审计 worker，编排层勉强跑通但三个 worker 全部 `SENTINEL_TIMEOUT` + `TMUX_KILLED`、零产出。根因是 **CLI 范式错配**（非配置问题）：skill 的 worker 启动（`claude-provider-env.sh` wrapper）、权限路由（`--permission-mode`）、进程生命周期都依赖 CLI 能力，非 CLI agent 够不着这些层。三个具体卡点：① provider env 污染（tmux session 继承混合 env → 模型不存在，必须走 wrapper）② permission dialog 杀死只读 worker（`acceptEdits` 不自动批准 Shell，审计跑 `grep`/`find` 逐条弹 dialog → 卡死 → 超时）③ 监测盲区（只挂 sentinel 不做定时 pane 巡检 → silent 卡死无人发现）。结论：多 worktree worker 编排应在 Claude Code CLI 会话做 PM；ZCode 类 harness 要并行改用自带 subagent/Agent 工具。
- **SKILL.md §1 边界**：「不使用本 Skill」新增「PM 是非 CLI 的 harness 内嵌 agent（ZCode 等）」一条，指向 G24。

### 关联

- 来源：FaroPDF 仓审计 Wave 实战（3 个只读 worker：任务源 / 技术债 / 架构，GLM `glm-5.2[1M]` provider）。链路逐段验证通过（worktree 隔离 / wrapper 统一 provider / scope-guard / worker 收 prompt 建清单），但卡在 permission dialog 层全军覆没。本条不否定 skill 在 CLI 环境的价值，只划清适用边界：**PM 必须是能被 spawn、能配 permission、能跑 settings 路由的 CLI 会话**。
- 关联章节：§2.1 防逃逸门禁、§3.8.1 spawn 后核验、§6 启动方式（wrapper）、§7 巡检与介入。
- 附带发现（不入 skill，记 FaroPDF 仓内处理）：`.claude/-settings.json` 文件名带横杠且缺 `ANTHROPIC_MODEL` 字段为坏配置；GLM token 在诊断过程中二次泄露到会话日志（需 rotate）。

## [1.20.0] - 2026-07-31

### 新增 — Issue 分组与合并 PR 判断

- **`references/11-issue-grouping.md`（新）**：补齐 SKILL.md §3「先分组」缺失的两个维度。原「先分组」只覆盖依赖链，本文给出三维度骨架：**① 同根因合并**（多 Issue → 一个 worker → 一个 PR）、**② 依赖链顺序**、**③ 独立并行**。每维度给触发信号 / 前置条件，配套软阈值（同根因合并建议合并后 diff < ~300 行、组内 ≤ 3 个）、决策树、反模式清单（默认一对一 / 硬塞不同类型 / 为凑数合并 / 大改动打包 / 跨模块强合等）。
- **任务源：本地 task 卡 vs 云端 GitHub Issue**：明确区分两类任务源的分组前预处理。本地结构化任务文件字段齐全、依赖显式；云端 Issue 他人提交、自由文本、依赖需从 body 推断，必须先 `gh issue list/view` 读 body + labels + 最近 commits 做相关性分析，并配套分组 SOP 命令。覆盖原 Skill 任务源模型偏本地、未处理云端 Issue 的缺口。
- **`templates/issue-batch-pr.md`（新）**：维度①「同根因合并」时的多 Issue PR 描述模板。核心是「统一根因」段（让 reviewer 一眼看清为什么这几个 Issue 要一起改）+ 逐 Issue 修复点 + `Closes #xx, #yy` 批量关闭 + 逐个 Issue 手动验证勾选。含与单 Issue PR 的区别速查、使用纪律（每个 Issue 必须单独验证、写不出统一根因说明可能不该合并）。

### 改进

- **SKILL.md §3 标准流程**：把第 2 步「先分组」从一句话扩成三维度判断（指向 `references/11`）；新增第 1.5 步「识别任务源形态」，要求区分本地 task 卡和云端 Issue 并做不同预处理。强调拿不准时默认**分开**。
- **SKILL.md §10 参考**：references 列表加 `11-issue-grouping.md`，templates 列表加 `issue-batch-pr.md`。
- **frontmatter**：version 1.19.0 → 1.20.0。

### 关联

- 来源：Folia 项目 issue 分组审查实测。发现 Skill 原「先分组」逻辑只处理依赖链，既没覆盖「多 Issue → 一个 PR」的打包合并场景，任务源模型也偏本地结构化任务，未处理云端他人提的 GitHub Issue。
- 范例：Folia `#75`（标题输入英文生成多余 `****`）+ `#76`（标题行删除/方向键时光标漂移）判定为维度①同根因合并（均发生在标题行 WYSIWYG、涉及 heading 节点 IR/Selection、改动位置重叠、均为小修），`#78`（内置 Word 模板导出非预期颜色）单独处理（纯导出模块、与编辑器那组正交）。

## [1.19.0] - 2026-07-13

### 新增 — 验证不授权安装依赖的可执行边界

- 新增 `dependency-install-guard.py` + hook wrapper：PreToolUse 对直接 Shell 工具调用默认 fail-closed，窄生命周期命令或 spawn 的精确 allowlist 才放行；系统/语言包管理器、全局链接、项目本地安装与 `npx`/`npm exec`/`pnpm dlx` 等按需获取命令还须精确安装授权及来源。授权快照缺失/损坏、hook 输入异常均 fail-closed。
- `spawn-worker.sh` 新增安装与 Shell 精确授权参数；权威快照及 SHA-256 receipt 落到 Git common-dir，worktree 内 JSON 明确只是 mirror。hook 读 spawn 进程快照，并阻断文件工具改写 receipt/settings/mirror。settings 合并只移除旧 guard command，不丢同 entry 的其他 audit hooks。
- 新增 Git identity 参数，把 author/committer 四个一次性环境变量绑定 worker 进程（不写共享 config），生成并精确放行 `git-workflow/safe-push.sh`；raw push 被 Shell gate 阻断，safe-push 把完整 PR range 身份证据绑定实际推送 OID。
- 未接入 PreToolUse 的 Codex / OpenCode / custom backend 默认拒绝 spawn；只有 `--allow-prompt-only-install-guard '<来源>'` 显式接受降级并留痕时才放行。
- Claude Code `--bare` / `--safe-mode` / `CLAUDE_CODE_SIMPLE=1`、排除 local settings 或不可证明的 wrapper 命令默认 fail-closed；CodeBuddy/Qoder backend 也须暴露对应 executable token。初始 METADATA 只记 `settings_wired...runtime_unproven`，首次 hook 调用另写 PM-side attestation；显式降级写 `prompt_only_no_mechanical_enforcement`，不虚报 hook 执行。
- 新增 49 项故障注入，覆盖命令绕行、按需获取工具、危险 Git/rg/awk 参数、授权快照防篡改、settings 多 hook 保留、PM receipt/runtime attestation、backend executable proof、显式降级、install-like verify 拒绝、worker 进程 Git identity 与 safe-push spawn 集成。

### 改进

- worker prompt、STATUS、RESULT 增加 allowed Shell、PM receipt、enforcement source 与 identity-bound safe-push 证据字段；缺依赖时先找已有二进制，仍缺则 `status=blocked` 并记录 skipped verification，不得把验证要求解释成安装权限。
- 依赖参考文档与 PATH-less 检查移除自动安装/全局 symlink 暗示；安装命令只作为用户明确批准后的参考。`check-dependencies.sh` 增加 `python3` 只读检查并明确只报告、不授权安装。

### 关联

- 通用化来源：法律 AI 书项目 T159 / DEC-131。本仓只沉淀可执行机制，不复制项目决策正文；`multi-agent-orchestration` 的 ignored 本地 TASKS/DECISIONS 继续不入库。

## [1.18.4] - 2026-07-11

### Changed — spawn 启动期提速 + spawn 后异步纪律（2026-07-10 多 worker Wave 实战三连修）

- **`scripts/spawn-worker.sh` 同步 dialog 监控默认值按 backend 分支化**（T1）：claude-code backend 实测 `--permission-mode auto --bare` 不弹 dialog，默认 `--no-trust-auto --no-permission-auto --no-permission-auto-bg`（省 trust_auto 30s + permission_auto 60s = 90s 空等）；其他 backend（codebuddy / qoderwork-cn / codex / opencode）默认全开。新增 `resolve_backend_defaults()` 函数 + 3 个 `*_OVERRIDE` 标志 + 主流程 PERMISSION_AUTO_BG 独立 gate（与 sync 解耦）。
- **6 个 `--*/--no-*` flag 精细控制**：`--trust-auto` / `--permission-auto` / `--permission-auto-bg`（显式 opt-in，升级后 dialog 行为变化兜底）；`--no-trust-auto` / `--no-permission-auto`（v1.18.3 兼容，分别同时关 trust+permission / sync+bg）；`--no-permission-auto-bg`（只关 bg watcher）。`--no-permission-auto` 保留 v1.18.3 "both off" 语义。
- **`SKILL.md` 新增 §3.8**（T2+T3）：`§3.8.1` spawn 后 30 秒内必跑的 4 条核验命令（tmux has-session / capture-pane / METADATA.json / STATUS.json with timeout 120）；`§3.8.2` 并行 spawn 投递纪律（一开始就并行 spawn，不先串行验证流程）；`§3.8.3` 反模式清单（TaskOutput block=true / tmux attach / while sleep 不带 timeout 等）；`§3.8.4` v1.18.4 backend 分支化同步 dialog 监控默认值说明。注：原计划 §3.7 已被 commit a33f057 用作"派发 SOP 必带 skill 路径清单"（当前以 `## Project Skills` 形式存在），故 renumber 到 §3.8。
- **`SKILL.md §6` 行 593 后补 4 条核验 snippet**：spawn 后立即跑 4 条命令 + 反向引用 §3.8.1。
- **`SKILL.md §3.5` 末尾加 v1.18.4 注**：claude-code backend 默认全关反向引用 §3.8.4。
- **`SKILL.md` frontmatter**：version 1.18.2 → 1.18.4（v1.18.3 由 commit 4d168a1 部分入仓但 frontmatter 未更新）。
- **新增 `templates/pm-spawn-postflight.md`**：4 条核验命令扩展版 cheatsheet（何时用 / 反例 / 多 worker 并行 spawn 提示）。
- **`references/09-parallel-lessons.md` 加 G23**：spawn 阶段并行投递纪律与已有 G22（wave 内任务颗粒度）形成两层闭环。

### 受影响的 PM 行为
- 单次 claude-code backend spawn 主进程退出时间从 v1.18.3 实测 2-4 min 降到 v1.18.4 秒级返回。
- PM 派活后**禁止**用 `TaskOutput block=true` 等 `spawn-worker.sh` 退出，必须跑 §3.8.1 的 4 条核验命令。
- 多 worker Wave 一开始就并行 spawn（每个 worker 走 `bg spawn-worker.sh` + `bg sentinel.sh` 各一次 fg Bash 调用），不先串行验证流程再补并行。

### Test
- `bash scripts/smoke-auto-bypass.sh` → 13/13 PASS（v1.18.3 7 项 + v1.18.4 6 项）。

### Background
- 来源：2026-07-10 某客户委托项目多 worker Wave 实战（3 个不同 skill backend 的 worker，全 claude-code backend），PM 派发阶段（spawn 3 worker + 投 prompt）实测耗 20+ min，用户反馈「着实影响并行推进任务」。TASKS.md L116-118 登记三条 follow-up，合并 v1.18.4。详见 DEC-112（gitignore 本地）。

## [1.18.3] - 2026-07-08

### Changed — spawn-worker.sh auto-bypass permission dialog（踩坑 7 真正修复）

v1.18.2 文档化了 "acceptEdits -y 仍弹 dialog" 但**未改默认行为**，PM 仍需 spawn 后 `tmux attach` 手按 2。v1.18.3 真正自动化：

- **`permission_auto()` 关键修复**：旧版用 `tmux send-keys -t "$session" Down Enter`（按箭头 + Enter 选 option 2），PM 2026-07-08 wave-1 实测在某些 TUI 状态不稳。v1.18.3 改用 `tmux send-keys -t "$session" "2"`（直接发数字键），稳定 work。
- **`permission_auto_bg()` 新加**：后台 watcher 通过 `( permission_auto_bg "$SESSION" & disown ) &` 启 disown，spawn-worker.sh 退出不影响 watcher。watcher 默认 7200s（与 sentinel --max-wait 对齐），覆盖同步 60s 窗口外的 dialog（worker 启动后 60-7200s 期间任何 tool 调用都自动按 2）。可用 env var `SPAWN_PERMISSION_BG_MAX_WAIT` / `SPAWN_PERMISSION_BG_POLL`（默认 5s）调整。
- **新 flag `--no-permission-auto`**（v1.18.3 精细 opt-out）：**只**关 permission_auto + permission_auto_bg（不影响 trust_auto）。与 `--no-trust-auto`（同时关 trust + permission）区分，给精细控制。
- **新 smoke `scripts/smoke-auto-bypass.sh`**：v1.18.3 新增验证脚本，跑 7 项 check（permission_auto 函数定义、数字键 `2`、permission_auto_bg 函数、--no-permission-auto flag 解析、调用点 disown、usage 输出、头部 v1.18.3 标记）。
- **SKILL.md**：
  - §3.5 改写为"spawn 后 auto-bypass（v1.18.3）—— PM 不需要手按 dialog"。
  - 新增 §3.5.1"auto-bypass 实现细节"：v1.18.3 修复点、permission_auto_bg 行为、opt-out flag、smoke 验证。
- **scripts/spawn-worker.sh 头部注释**：trust + permission dialog 兜底章节改写，明确 v1.18.3 auto-bypass 三层保护（trust_auto / permission_auto / permission_auto_bg），PM 默认不需要 attach tmux 盯。

### 受影响的 spawn-worker.sh 行为
- 默认情况下，PM 派活后**不需要**任何手按（trust_auto + permission_auto + permission_auto_bg 三层自动）。仅当 worker 在 1-2 分钟还没写 STATUS.json 时，再 `tmux attach` 手动 inspect（说明 dialog 真卡住）。
- 仍用 `--no-trust-auto` opt-out 同时关 trust + permission（向后兼容）。
- 新增 `--no-permission-auto` 精细 opt-out（v1.18.3）。

### Test
- `bash scripts/smoke-auto-bypass.sh` → 7/7 PASS（v1.18.3 验证）。

### Background
- v1.18.3 由 PM 主动接管，原因是 wave-3 派 worker G 时撞 WorkBuddy 平台 `sg.tgalileo.com` 端点临时 hang（axios 旧 connection 不释放），worker 反复死锁失败。PM 按 §2.1 防逃逸门禁例外"修复 PM 自己生成的 orchestration 文档/配置"直接改 spawn-worker.sh（worker 任务范围明确 + 范围小）。worker G 在 workbuddy 平台恢复后再跑相同任务应能复现。

## [1.18.2] - 2026-07-08

### Added
- **CodeBuddy tmux spawn 实测改进**（`references/08-workbuddy-cli-worker.md` §14）：基于三轮不同形态的 spawn 任务（多步文本编辑 / SVG 生成 / CLI 研究调研）补强 §10（2026-07-05 五轮实测）。三个具体卡点 + 顺跑配置：
  - **权限机制坑（§14.1）**：`acceptEdits -y` 组合下，acceptEdits 只 accept edits，**读 worktree 外路径 / 特殊路径（tmux socket、跨 worktree 符号链接）仍弹权限对话框**；`-y`（`--dangerously-skip-permissions`）被 acceptEdits 覆盖、没真正跳过读权限；`--add-dir <项目根>` 只预授权文件目录、不覆盖工具调用层。后果：**多步任务（Read 多文件 + Bash 多次）权限循环卡死**，单步少路径任务勉强过。顺跑：多步任务一律 `--permission-mode bypassPermissions`（§10.1 launch.sh），`acceptEdits` 只适合单步 / 少路径。
  - **Enter 提交坑（§14.2）**：`tmux send-keys -t <session> "prompt" Enter` 的 `Enter` **没提交 prompt**（pane 显示 prompt 完整在 `>` 输入框但没执行）——codebuddy TUI 稳定行为，**与 glm worker 同坑**。顺跑投递配方：`send-keys -l` 投文本 + 单独 `send-keys Enter`（或 `C-m` 更稳）+ sleep 12-15s + 兜底补一发 Enter。
  - **session 断流坑（§14.3）**：权限确认对话框（选 don't-ask / session-allow）后，prompt 流程被打断，codebuddy 回 `>` 空等、**不自动续原 prompt**。顺跑：重发 prompt（§14.2 配方）或 `codebuddy -c` resume；最佳策略=bypassPermissions 从根上绕开权限框。
  - **原生替代方向（§14.4）**：CodeBuddy 原生支持 `--worktree --tmux`（§7.3），可替代 spawn-worker.sh + launch.sh 手工组合；记为 long-term 优化方向，**待对比测（权限框透传 / pm-monitor 识别 / worktree 收口三项未测），未测前不替换 spawn-worker.sh 路径**。
  - SKILL.md frontmatter version 1.18.1→1.18.2。
- 原则跨项目通用（不绑定具体项目 / 章节 / AGENTS / DEC），案例匿名化。

## [1.18.1] - 2026-07-08

### Added
- **G22 多维度任务的颗粒度纪律**（`references/09-parallel-lessons.md`）：单 worker 改多章 × 多维度时注意力被高优维度（Critical / Important）占满、末位维度（如"标题删重"）静默漏掉。沉淀三条通用改进：①多维度任务 prompt 用 **checklist 强制逐维度**（每维度独立 commit / 勾选，worker 必须覆盖完所有维度才算完成）；②大批量改后必派 **wave2 复查 worker**（只读 review）抓漏；③精细深查（箭头落点 / 字体逐核 / 像素对齐）拆**单维度 worker**处理深度。主因非模型能力，是任务粒度 + prompt 结构。原则跨项目通用，不绑定具体项目或章节。
- SKILL.md §3.1 Wave 模式段加一段交叉引用，指向 G22；frontmatter version 1.18.0→1.18.1。

## [1.18.0] - 2026-07-07

### BREAKING — 删除全部 headless / batch 模式（DEC-044）
- **`render-runtime-profile.sh` 移除 `--mode` / `--prompt-file`**：删除参数、校验、`append_redirection` / `shell_wrap` 辅助函数。5 个 backend（claude-code / codex / opencode / codebuddy / qoderwork-cn）只保留 interactive 分支，输出删 `WORKER_MODE`。传 `--mode` / `--prompt-file` 现在显式报错并指向 DEC-044 + 迁移指引（短任务用同宿主 Subagent）。
- **理由（用户原话）**：「我们使用 TMUX 就是要去进行交互式的 worker 监控。如果是 `-p` 模式的话，它更适合那种短程的任务，那种任务其实使用 subagent 也能完成，所以我们要删掉这个模式，避免 agent 错误调用这样一种模式」。headless 一发跑完 = 放弃 tmux 监控可纠偏；而它适合的短任务本就该走 Subagent。分工由此清晰：**短任务 → Subagent；需编排/监控 → tmux 交互 worker**。
- **SKILL.md**：§2 执行模式表 + §6 启动方式删除 Claude Code 批处理 bullet、`< redirect 必须 bash -lc`、`claude -p autocompact thrash` 两条警示，换成「所有 worker 一律交互式」说明；Codex/OpenCode bullet 改为交互式命令。§2 表加「同宿主 Subagent」替代 headless 的说明。
- **references/06/07/08**：顶部加「batch 已于 v1.18.0 移除（DEC-044）」横幅，正文 batch 段保留作历史参考。
- **supersede**：DEC-033（batch 部分）、DEC-040（batch flag 修正）、DEC-042（「保留 batch 兜底」结论）的 batch 相关部分；交互式默认值与 DEC-042 长任务交互 canonical pattern 保留并扩展到短任务。
- **不变**：`smoke-provider-settings.sh` 仍用 `claude -p` 做一次性 provider 验证（测试工具非派 worker，故意保留）。

### Added — 轻量模式 `--no-worktree`（DEC-045）
- **`spawn-worker.sh --no-worktree`**：非默认的轻量隔离模式。worker tmux session cwd 直接指向目标文件夹，不建 git worktree / branch / base ref。两种触发：(a) 用户显式 `--no-worktree`；(b) `--project` 检测为非 git work tree 时自动切换（打印 `SPAWN_WORKER_LIGHTWEIGHT_AUTO`，非静默降级）。
- **`METADATA.json` 加 `isolation_mode` 字段**（`"worktree"` | `"lightweight"`）；轻量模式 `branch / base_ref / base_sha` 留空。
- **Isolation Gate 分支化**：worktree 模式验 cwd + branch；轻量模式只验 cwd（非 git 不验 branch）。info/exclude 写入加 git 存在性 guard（非 git 跳过）。
- **worker-prompt.md**：Context 加 `{{isolation_mode}}`；Isolation Gate / Commit Cadence / Git-PR 段加轻量分支（非 git 文件夹跳过 commit/PR，交付物直接落盘 + RESULT.md 清单）。
- **适用场景**：一个 PM session 派多个 worker 各管一个独立文件夹、目标不是 git 仓、或不需要 git 级隔离。隔离 = 文件夹分离（硬约束：worker 必须占互不重叠的文件夹；越界靠 `--allow-paths` scope-guard 兜底）。SKILL.md 新增 §2.1.1 + §6 轻量 spawn 示例 + §11 轻量 smoke benchmark。

### Changed
- **版本号 frontmatter**：SKILL.md `version` 从 `1.17.6` 修正为 `1.18.0`（此前 1.17.7/1.17.8 patch 未同步 frontmatter，一并修正）。

## [1.17.8] - 2026-07-06

### Fixed
- **第三方 provider worker 串到 Fable 5 / OAuth 的 env 路由 bug（DEC-043）**：`render-runtime-profile.sh` 在 provider-isolation 路径（wrapper）的 `claude_parts` 追加 `--bare`。`--bare`（minimal mode）禁 keychain reads / OAuth / plugin sync / CLAUDE.md auto-discovery，使 Anthropic auth 严格走 wrapper 设的 `ANTHROPIC_API_KEY`（来自 provider registry/settings），不再读 keychain 残留 sk-ant。修前：deepseek/glm worker 启动弹"是否使用此 API key"（sk-ant），选 No 后串 Fable 5 而非目标 provider；MCP 信任框也每次弹。修后实测：claude 直显"deepseek-v4-pro · API Usage Billing"，无 keychain/MCP 框。inherit-style worker（不走 wrapper）不受影响。

## [1.17.7] - 2026-07-05

### Added
- **`config/orchestration-personal.json` 个人偏好初始化**：基于 `config/orchestration-personal.example.json` 模板创建本地个人配置。`host=claude-code`，`main_force.task_routing` 走 deepseek-v4-pro（高端）/ deepseek-v4-flash（简单+多模态）；`codex_policy.policy=explicit_only` + `strict_mode=true`（CodeX 默认锁死，仅用户原话命中 `trigger_phrases` 才解封）；`backend_model_routing.codebuddy.default_models = ["deepseek-v4-pro", "deepseek-v4-flash"]`（workbuddy/codebuddy CLI 只启用这两个模型档位，不引入 kimi/minimax/sonnet/opus 等其它模型）；`backend_model_routing.qoderwork-cn.default_models = ["deepseek-v4-pro", "deepseek-v4-flash", "qmodel_latest", "qmodel"]`（QoderWork CN 启用 Deepseek 两档 + Qwen3.7-Max / Qwen3.7-Plus），其中 Qwen 两个档位通过 `discount_window`（22:00-08:00 Asia/Shanghai，含跨午夜）标注为「二折优惠时段优先」。文件受 `.gitignore` 的 `**/config/*.json` 规则保护，不入库。

### Changed
- **codebuddy backend 模型白名单收敛**：个人偏好中 `backend_model_routing.codebuddy.default_models` 仅保留 `deepseek-v4-pro` 和 `deepseek-v4-flash`。`kimi-k2.6` / `kimi-k2.7` / `minimax-m3` / `sonnet` / `opus` / `auto` 等档位不启用——后续如需扩展，再追加到 `default_models` 数组。
- **qoderwork-cn backend 模型白名单收敛**：个人偏好中 `backend_model_routing.qoderwork-cn.default_models` 收敛为 `["deepseek-v4-pro", "deepseek-v4-flash", "qmodel_latest", "qmodel"]`，与 codebuddy 共享 Deepseek 两档；Qwen3.7-Max（`qmodel_latest`）和 Qwen3.7-Plus（`qmodel`）在 `discount_window`（22:00-08:00）享受二折优惠，PM 派 qoderwork-cn worker 时若当前时间落在折扣窗口，应优先路由到 `qmodel_latest` / `qmodel`；窗口外则回落 Deepseek 两档。
- **新增 `discount_window` 字段**：在 `backend_model_routing.qoderwork-cn` 下声明折扣时段 `start=22:00 / end=08:00 / timezone=Asia/Shanghai / cross_midnight=true`，并列出 `models_in_window`（Qwen 两档）与 `models_outside_window`（Deepseek 两档），`rate_note="二折（约 20% 原价）"`。当前 `render-runtime-profile.sh` 尚未解析该字段，PM 需手动判断时段后再选 model。
- **CodeX 路由硬规则收紧**：在 SKILL.md §2.4 `codex_policy.policy = "explicit_only"` 基础上，新增 `strict_mode=true` + `trigger_phrases` + `fallback_when_blocked` + `pm_must_log_on_unlock` 字段。PM 必须看到用户原话命中 `trigger_phrases`（如「用 Codex / 调用 Codex / 跑 Codex / use codex / run codex / spawn codex」等）才解封；任何弱暗示（「更适合 Codex / Codex 额度还行 / 试试 Codex」）不算解封。CodeX 被 block 时回落 DeepSeek 两档，不替换为其它高额度模型。解封时必须在 Wave 计划 + `STATUS.json.pm_notes` 记录用户原话、wave_id、worker_id 与 codex profile/model，便于审计。

### Reason
- 来源：用户明确「Workbody 这个 Agent 的 CLI 只选用 Deepseek V4 Pro 和 Deepseek V4 Flash 两个模型」，并补充「qoderwork-cn 也只调用 Deepseek V4 Pro / Deepseek V4 Flash / Qwen3.7-Max / Qwen3.7-Plus，其中后两个更推荐在晚上 10 点到早上 8 点之间调用，因为会打二折」，「除非我明确要求，尽量不要调用 CodeX」。落地为个人偏好 `backend_model_routing.codebuddy` + `backend_model_routing.qoderwork-cn` + `codex_policy`，并通过 `discount_window` 把折扣时段、`trigger_phrases` 把 CodeX 解封条件显式标注，让 PM 派 worker 时能直接看到「此时段是否用 Qwen 两档最划算」与「CodeX 默认锁死、必须看到原话才解封」。

## [1.17.6] - 2026-07-05

### Added
- **`--add-dir` 透传（codebuddy 跨目录访问）**：`render-runtime-profile.sh` 新增 `--add-dir <dir>` 参数（可重复），codebuddy backend 追加到 `cb_parts`。`spawn-worker.sh` 同步新增 `--add-dir <dir>` 参数，写入 `METADATA.json` 的 `add_dirs` 字段。用途：PM 派 worker 时若任务文件/素材在 worktree 外，`spawn-worker.sh --add-dir /tmp --add-dir ../shared-assets`。
- **`permission_auto()` 兜底 runtime "Do you want to proceed" prompt**：`spawn-worker.sh` 新增 `permission_auto()` 函数，启动 tmux 后轮询 pane 内容（最长 60s，2s 间隔），匹配「Do you want to proceed」文本后自动选 option 2「Yes, and don't ask again for session」（Down+Enter=session-allow）。与 `trust_auto` 共用 `--no-trust-auto` opt-out。只自动选 session-allow，不选 bypass（安全：session-allow 仍记录，且只对当前 session）。

### Fixed
- **runtime "Do you want to proceed" prompt 无自动处理**：上一轮（v1.17.5）的 `trust_auto` 只处理了首启 trust folder dialog，但 codebuddy 读取 worktree 外文件时的「跨目录安全门」是另一层 prompt。PM 派 headless worker 时若任务文件在 worktree 外（如 `/tmp`），worker 会卡在 "Do you want to proceed?" 弹窗。新增 `permission_auto()` 兜底此场景。

### Reason
- 来源：2026-07-05 PM 用 codebuddy worker 实战，即使带了 `-y`，读取 `/tmp` 任务文件时仍弹 "Do you want to proceed" 弹窗。`-y`/`--dangerously-skip-permissions` 跳工具权限，但不覆盖 codebuddy 的「跨目录访问」安全门。官方文档的解是 `--add-dir`（settings 或 CLI flag），而 permission_auto 作为兜底自动选 session-allow。

## [1.17.5] - 2026-07-05

### Fixed
- **codebuddy/qoder 交互式 worker 缺 -y / --dangerously-skip-permissions**（问题 2 运行时部分）：`render-runtime-profile.sh` 的 codebuddy case `-y` 逻辑从「batch 恒加 / 交互式仅显式 --dangerously-skip-permissions」改为「交互式也默认加，仅 --no-skip-permissions opt-out」。qoderwork-cn case 同改为默认加 --dangerously-skip-permissions。理由：spawn-worker.sh 派 tmux session 本质 headless（无人在终端应答 runtime permission prompt），DEC-040 F1/F3 只修了 batch 模式，交互式 gap 还在。
- **codebuddy 首启 trust folder dialog 无自动处理**（问题 1）：`spawn-worker.sh` 新增 trust-auto：启动 tmux 后轮询 pane 内容，匹配 codebuddy trust dialog 文本（Trust folder / Trust folder and all subdirectories），自动选 option 3（Down×3+Enter），避免子目录二次 prompt。提供 `--no-trust-auto` opt-out。
- **codebuddy PATH 检测假阴性**（问题 3 补充）：`check-dependencies.sh` 新增 `--print-bundle-path codebuddy|qoderwork-cn`，直接输出 .app bundle 二进制绝对路径。`spawn-worker.sh --help` 加 Troubleshooting 段，提示用 check-dependencies 多源检测或取绝对路径传给 --command/--bin。

### Reason
- 来源：2026-07-05 PM 用 `spawn-worker.sh --backend codebuddy` 派 worker，连续撞 3 个手动 prompt：首启 trust folder dialog → 子目录访问 dialog → which codebuddy 找不到。CHANGELOG v1.16.6/1.17.1/1.17.2 历史上修过 batch 模式 flag 和 PATH-less 检测，但交互式 headless worker 的自动 -y + trust-auto 两个 gap 一直没补。

## [1.17.4] - 2026-07-03

### Added
- **`scripts/qoderclicn-interactive-spawn.sh`**：长任务（10+ tool call）专用 helper。`qoderclicn` 在 batch `-p` 模式下走 SDK/bare 模式 → GUI 主进程 (pid 65090) 的 HeadlessSession → 1-2s 内 `gemini.exitHeadlessMode` 主动 idle-exit（实测日志 `~/.qoderworkcn/logs/runs/...-p65090/process.exiting ... uptime_ms=1176`）。DEC-042 决策：长任务改走 interactive 模式 + tmux `send-keys` 投递 prompt（**无 `-p`**），实测 5 个 tool call（pwd/date/echo/uname/ls）全跑通 + worker 仍在 `>` ready。Helper 自带：
  - argv-form tmux `new-session` 触发（路径空格不丢）
  - trust-folder 自动 `1 + Enter` 接受（可关：`--no-trust-auto`）
  - TUI ready 检测（看 `Type your message` 或 `>`）
  - prompt 12KB/16KB 分段（`send-keys` / `paste-buffer`）
  - thinking/tool_use 出现确认（60s）

- **references/07 §8 新增「长任务专用 helper」指引**：PM 用法 + helper 适用场景 + 与 batch `-p` 对照。

### Reason
- 来源：2026-07-03 doc-curator-iter Wave 1 W2 中途死的根因诊断。investigator 14 行 A/B 测试定位 F1+F3 (DEC-040) 解决了 batch flag + model key，但 worker 仍 1-2s exit 不进 agent loop；进一步排查确认是 SDK/bare 模式的 HeadlessSession 设计问题，**不是 flag 错**。Reference §6.2 已写明 batch 仅限短任务，但 PM 派 W2 时 10+ tool call 仍走 batch 故踩坑。
- 决策：保留 batch `-p` 作为「短任务兜底」（≤3 tool call），新增 interactive helper 作「长任务 canonical」。`spawn-worker.sh` 后续加 `--mode interactive` 集成（本次仅 helper + 文档）。

## [1.17.3] - 2026-07-03

### Security
- **凭证卫生审查（skill-lint 验收触发）**：`config/*.settings.json`（deepseek / glm / minimax）含真实 API key，虽已被 `.gitignore` 的 `**/config/*.json` 拦住不进 git 追踪（Hard Fail #5 未触发），但真实 live key 明文躺在工作区仍是外带风险。**这三把 key 需在各 provider 后台轮换**（DeepSeek / BigModel-GLM / MiniMax），并确认打包与 ClawHub 同步都尊重 `**/config/*.json` 排除。长期方案：真实 token 只放环境变量，settings 文件留占位。

### Fixed
- **`.gitignore` 补 `**/.claude/agent-sessions/`**：SKILL.md §4.1 要求 agent-sessions 巡检产物不进 commit，但仓库 `.gitignore` 此前无对应规则，`git add -A` 会误提交（含本地绝对路径的 `SENTINEL_OUT.log`）。补规则并删除遗留样例 `.claude/agent-sessions/orch-pref/`。
- **personal.json「不入库」表述统一**：`config/orchestration-personal.json` 与 `.example.json` 的 `_comment`/`_path_user` 原写「随 skill 走，在仓库内」，与 §2.4「gitignore 不入库」矛盾（实际行为是 gitignored）。统一为「在 skill config/ 目录内，但被 .gitignore 排除、不入库」。
- **personal.json 路径一致性**：§3.3 用户级 vs 项目级叠加表原写 `~/.claude/orchestration-personal.json`（旧 home 路径），与 §2.4 现行 `config/orchestration-personal.json` 不一致，已统一为 config/ 路径。
- **§2.4 TODO stale 字段**：`main_force.models` → `main_force.task_routing`（schema 已重命名），`coddex` 拼写 → `codex`。
- **registry example 反混淆注释**：`claude-provider-registry.example.json` 的 `_comment` 原直接给出真实 endpoint 对照（open.bigmodel.cn / api.deepseek.com / api.minimaxi.com），使别名脱敏形同虚设，已删除改为占位说明。
- 清理 `.DS_Store`。

### Reason
- 触发：对本 skill 做 skill-lint 发布前验收，命中 1 个凭证暴露风险 + 4 个文档/元数据一致性问题。凭证按「默认按严重处理」，其余为发布一致性修复。

## [1.17.2] - 2026-07-03

### Fixed
- **codebuddy / qoderclicn batch mode 启动参数（CLI flag 误用导致 Wave 1 worker 出货失败）**：派 Wave 1（`doc-curator-iter-2026-07-03`）实测两个 worker 都立即退出 / 卡住，investigator worker 14 行 A/B 测试定位到 render-runtime-profile.sh 生成命令时 2 个 flag 错配 + 个人配置 1 个 model key 错误：
  - **F1**：codebuddy batch 默认 `--permission-mode acceptEdits` 与 `-y` 冲突，CLI 自己报错要求 `codebuddy -p -y "<prompt>"` 或 `--permission-mode bypassPermissions`。改为 batch 默认 `bypassPermissions`（交互式不动）。
  - **F3**：qoderclicn batch 模式必须显式 `--dangerously-skip-permissions`（`--permission-mode auto` 在 headless 不 bypass）。自动加在 `MODE=batch` 路径里（`SKIP_PERMISSIONS=1` 已存在的语义不变）。
  - **F2**：`config/orchestration-personal.json` `backend_model_routing.qoderclicn.default_models` 把 `qoder-3.7MAX` / `qoder-3.7PLUS`（CLI 不接受）换成 `[qmodel_latest, qmodel]`（CLI 1.0.34 实证可用 key 之一）。`tier_note` 同步标注实际对应 `Qwen3.7-Max` / `Qwen3.7-Plus`。
- **诊断先于修复**（meta 流程）：用 investigator worker 14 行 A/B 测试（A/B 改 1-2 个 flag 看哪个 fix pass）+ `/tmp/cli-diagnostic-report.md` 沉淀证据 + CLI 实测拒绝消息。最小 3 行改 + 单 commit，不直接凭印象 patch。

### Reason
- 触发：本次 Wave 1 派发失败时 PM 一度怀疑 GUI 登录态 / trust folder / path 转义。Diagnoser 14 行 A/B 实验逐一排除（GUI app 全部运行中、登录态齐备、空目录 trust folder 也通过、ARG_MAX 1MB ≫ 提示词 6KB、shell 转义正确）。定位到 F1+F3 是 render-profile 默认值错，F2 是 personal.json model 名字错。
- 决策：source 修默认值而非文档「PM 用对 flag」。理由：默认值下 CLI 默认跑通是「先入坑后纠错」的逆向发现，文档「PM 用 -p -y」很多用户不知道；与其让每个 PM 犯错不如让 render-profile 默认发对命令。

## [1.17.1] - 2026-07-03

### Fixed
- **codebuddy / qoderclicn 假阴性检测（PATH-less 已知 .app bundle 多源检测）**：先前 `check-dependencies.sh --backend codebuddy` / `--backend qoderwork-cn` 只跑 `command -v codebuddy` + `command -v qoderclicn`，desktop 端已装但未建 symlink 时（如 `/usr/local/bin/codebuddy`）会假阴性报 MISSING/WARN 但不给出 actionable fix，PM 误判 worker CLI 不可用。新增 `check_app_bundle_binary()` 多源检测：先查 `PATH`，再依次查已知 .app bundle 绝对路径（codebuddy: `/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/bin/codebuddy`; qoderclicn: CN 版 `/Applications/QoderWork CN.app/Contents/Resources/bin/qoderclicn` + 国际版 `/Applications/QoderWork.app/Contents/Resources/bin/qodercli`），找到 bundle 时给 `DEPENDENCY_WARN` + actionable fix（`spawn-worker.sh --command` 直接传绝对路径 / `sudo ln -s` 永久 symlink），都找不到时显式提示装桌面端。两条 backend case 同步加进 usage() 帮助文本。
- **references/07-qoderwork-cli-worker.md §2.1**：新增「PATH-less 检测」一节，指引 PM 在新机器派 worker 前跑 `check-dependencies.sh --backend qoderwork-cn --strict`；附 spawn-worker 传绝对路径 / `sudo ln -s` 两条 fix。
- **references/08-workbuddy-cli-worker.md §2.2**：同 §2.1 形态，codebuddy 版本。
- **新 `--backend` 选项启用**：usage 文本加 `codebuddy | qoderwork-cn`。

### Reason
- 触发：用户 2026-07-03 派 Wave 1 时实测——`which codebuddy` + `which qoderclicn` 都报 `not found`，PM 一度以为 desktop 端没装；后续 ls 发现 `.app bundle` 内二进制其实在，是 symlink 没建。规则：「binary 实际在 app bundle」也算 worker 可用（spawn 传绝对路径即可），不应被漏报。
- 决策：不自动 `sudo ln -s` 创建 symlink（高风险操作、PM/用户应显式确认），改为报告 + 给两条 fix 让 PM 选；`check_app_bundle_binary()` 设计为静默存在性检查（前置于它的 `check_optional_cmd` 已决定 OK/WARN），避免重复 report。

## [1.17.0] - 2026-07-03

### Added
- **cron + sentinel 标准组合监测模式（§7.3）**：sentinel（§7.2）是主监测，但有 3 个盲区——(a) worker 硬卡死不写 STATUS 时 sentinel 轮询到 `--max-wait` 超时（exit 124）；(b) worker 用非标准 STATUS 文件名（如 `issue-XXX-status.json`）时 sentinel 监听 `STATUS.json` 轮询空文件到超时；(c) sentinel 自身被 SIGKILL/SIGTERM 或 harness 未 re-invoke 时静默消失。新增 §7.3 把"sentinel（秒级抓 done）+ cron（兜底：漏合入 + 硬卡死双信号检测 + sentinel 失效）"写成**标准两层组合**，而非二选一。PM 派 worker 后必挂两层。
- **cron 兜底频次硬推荐**：短任务 ~22min、**长流水线 10-15min**，避开 `:00`/`:30` 整点（API 拥堵 + 速率限制）。给出错峰 cron 表达式（`3,13,23,33,43,53 * * * *` 每 10 分钟 / `7,29,51 * * * *` 每 22 分钟）。不低于 10 分钟（过频抵消 token efficiency）。
- **双信号卡死检测**：判 worker 卡死必须 STATUS.updated_at + 文件 mtime 都超阈值（长流水线 20min）**且** pane 尾部有死循环证据，缺一不可；避免把正常 long thinking 误判为死循环。只满足时间信号时发 `tmux send-keys` 心跳探针，下一轮再判。
- **`templates/cron-monitor-prompt.md`**：可复用 cron prompt 模板（worker session + STATUS 路径 + git 分支 + sentinel id + stale 阈值 + 收尾自删 + 无动作一句话汇报），含占位符表 + cron 表达式建议表 + 收尾纪律。

### Reason
- 来源：用户 2026-07-03 反馈"cron 兜底频次 30 分钟太低，起码 10 分钟"，并提议改进 skill 兜底频次。排查发现 SKILL.md §7 原本没有 cron 兜底频次的硬性数字（30 分钟是 PM 按 cache 经济性自设，偏稀疏），但 skill 内部 TASKS #69/#70 早已登记"把 cron+sentinel 标准组合 + 10-15min 频次写进 §7 + 建 cron 模板"两条待办，本次一并实施。
- 决策：sentinel 事件驱动零 idle token 是主监测不可废；cron 兜底抓 sentinel 三个盲区 + 卡死双信号检测，是 graceful 降级而非替代。频次按任务粒度（长流水线 10-15min）平衡 catch-up 速度与 re-invoke token 成本。详见 DEC-038。

## [1.16.7] - 2026-07-02

### Added
- **个人 backend 路由偏好配置机制**（用户级，可被任何人自定义）：
  - 新增 `config/orchestration-personal.example.json` 模板，字段：`main_force`（主力 host + model 轮换）、`codex_policy`（`explicit_only` / `allowed`）、`backend_model_routing`（`qoderclicn` / `codebuddy` 的默认 model 列表）、`notes`。任何用户可复制为 `~/.claude/orchestration-personal.json` 后按个人可用 provider / model / 平台额度修改。
  - SKILL.md §2.4 新增「个人路由偏好」小节：PM 派 worker 前先读 `~/.claude/orchestration-personal.json`（缺失回落 example）；字段定义 + 缺省回落表；与 §2.2 / §2.3 / §3.3 的优先级关系。
  - SKILL.md §2.2 加「Backend → 默认模型速查表」：Claude Code 默认 `glm-5.2` / `MiniMax-M3` 轮换；`qoderclicn` 默认 `qoder-3.7MAX` / `qoder-3.7PLUS`；`codebuddy` 默认 `deepseek-v4-pro` / `deepseek-v4-flash`；Codex 默认 `explicit_only`（仅用户明确要求时启用）。
  - SKILL.md §3.3 增「用户级 vs 项目级」叠加表，明确 `~/.claude/orchestration-personal.json` 与 `.claude/orchestration.config.json` 不冲突，字段命名刻意不重叠。
  - `references/06-agent-cli-reference.md` §0 总览表加「默认 model（个人偏好）」列。

### Known Limitations
- **`render-runtime-profile.sh` 暂未自动读 personal config**：本次只做配置 + 文档 + PM 手动遵循。后续增强（解析 `main_force.models` → 默认 `--model`、`codex_policy.policy` → Codex backend gate、`backend_model_routing.<backend>.default_models` → 跨工具 default）需要开新 worker 单独做，避免无人监督下改脚本引入新不确定性。

### Reason
- 来源：用户确认主力 = Claude Code host + GLM-5.2 / MiniMax-M3 轮换；Codex 智能高但额度贵，仅在用户明确要求时启用；`qoderclicn` / `codebuddy` 跨工具 backend 在主力不够或用户明确指定时才派；每个 backend 的默认 model 也是个人偏好（不是 skill 级硬编码）。
- 决策：把"个人偏好"做成跟个人 dotfile 一样不进仓库（`~/.claude/orchestration-personal.json`），skill 内只留 example 模板 + 文档；机制可被其他用户复制和修改。Codex `explicit_only` 作为软推荐（个人偏好层面），不强写进 skill 硬规则。

## [1.16.6] - 2026-06-26

### Added
- **ref 08 §6.7 复测更新（codebuddy 多模型 eval）**：writing-reviewer v0.10.7 cross-model eval 中，codebuddy backend 并发跑 kimi-k2.6 / deepseek-v4-flash / deepseek-v4-pro（同 ch08 baseline 71 hard FAIL），三个 worker pass-1 全部 71→51，backend 在多模型 fan-out 下端到端可用。
- **snapshot-copy-into-worktree pattern（backend 无关关键修复）**：eval skill 快照在主仓库 untracked → fresh worktree 看不到；codebuddy trust-folder 又禁止跨目录读。修复：spawn 时把冻结 snapshot 拷进 worktree，worker 用 worktree-local 相对路径读，同时消除跨目录访问 / trust 限制 / path 漂移三类问题。详见 DEC-037。
- **`codebuddy-spawn.sh` helper**：`research/verification/writing-reviewer-skill-version-eval-260622/codebuddy-spawn.sh`，一条命令完成 worktree add + snapshot 拷贝 + session context + tmux（codebuddy 交互 + MCP off）。codebuddy/qoder spawn 暂用此手动 helper。
- **codebuddy MCP-off 标准flag**：正文修订任务用 `--strict-mcp-config --mcp-config /tmp/empty-mcp.json`（`{"mcpServers":{}}`）关 MCP，减前言 + 避免 WorkBuddy MCP 连接器 GUI 授权弹窗。
- **`render-runtime-profile.sh --no-mcp` 开关**：Claude Code worker 传 `--no-mcp` 自动注入 `--strict-mcp-config --mcp-config '{"mcpServers":{}}'`，跳过 "new MCP servers found" 审批弹窗（实测有效）。
- **eval worker 权限约定（worktree 隔离 → 最高权限）**：eval/test worker 都在独立 worktree 里跑、安全隔离，统一用最高权限免任何手动点击——Claude Code `--permission-mode bypassPermissions`（或 `--dangerously-skip-permissions`，经 render-runtime-profile 的 `--permission-mode` 传入）、codebuddy `-y`（`--dangerously-skip-permissions`）、qoderclicn `--dangerously-skip-permissions`。配合 `--no-mcp`，spawn 后直达 REPL，零点击。

### Known Limitations
- **`render-runtime-profile.sh` 仍不支持 codebuddy / qoderclicn backend**：只支持 claude-code（registry/settings）/ codex / opencode。codebuddy/qoder worker 暂走手动 helper 或原生 `--worktree --tmux`。TODO：把这两个 backend 加进 render-runtime-profile，统一 spawn 路径。

## [1.16.5] - 2026-06-23

### Added
- **Claude provider/model registry 模式**：新增 `config/claude-provider-registry.example.json`，按 MyAgents 的 provider intent 思路，把多个 provider 的 `base_url`、`auth_token_env` / `api_key_env`、`auth_type` 和 `models` 放入一个本地 registry。真实 registry 仍放 ignored local 文件，真实 key 优先用环境变量承载。
- **`claude-provider-env.sh` 支持 registry**：新增 `--provider-registry PATH --api-provider ID --model MODEL_ALIAS`，启动时解析 provider base URL、auth token 和模型别名，构造本次 worker 的有效 env。
- **`render-runtime-profile.sh` 支持 registry**：新增 `--provider-registry`，在渲染阶段把 model alias 解析成真实 provider model，并传给 `claude --model`；旧 `--settings` 路径保留兼容。

### Changed
- **文档改为 registry-first**：`SKILL.md`、`references/01-model-selection-matrix.md`、`references/06-agent-cli-reference.md`、`references/09-parallel-lessons.md` 改为推荐 registry + provider id + model alias，旧的每模型一个 settings 文件标为兼容路径。

### Reason
- 来源：用户确认不同模型来源有不同 Base URL、API key 和模型清单，希望参照 MyAgents 运行时动态选择 provider/model 的方式，减少为每个模型维护独立 settings JSON。
- 决策：保留两种模式。registry 模式作为默认推荐，settings 模式作为已有流程和排障兼容。这样 Agent 后续只需要指定 `api_provider` 与 `model alias`，由 wrapper 动态生成 Claude Code worker 环境。

## [1.16.4] - 2026-06-23

### Added
- **Claude Code provider env isolation wrapper**：新增 `scripts/claude-provider-env.sh`，借鉴 MyAgents 的 runtime snapshot/env 构造思路，在启动第三方 provider worker 前清理继承的 Claude/Anthropic provider 路由变量，从目标 settings JSON 导入 env，补齐 `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_API_KEY`，设置 `CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST=1`，并给 `claude` 注入 `--setting-sources project,local`。
- **runtime metadata env isolation 字段**：`spawn-worker.sh` 新增 `--env-isolation`，写入 `METADATA.json` 的 `runtime.env_isolation`，方便 PM 复盘某个 worker 是否走了 wrapper、OAuth 清理或继承环境。

### Changed
- **`render-runtime-profile.sh` 默认包 wrapper**：`claude-code + --settings + --model` 现在默认生成 `bash scripts/claude-provider-env.sh ... -- claude ...` 命令；排障时可显式 `--no-provider-env-isolation` 绕过。
- **batch render 自动 shell-wrap**：`render-runtime-profile.sh --mode batch` 生成的 Claude/Codex/OpenCode 命令会自动包 `bash -lc`，避免 `<` 重定向或 `$(cat prompt)` 在 `spawn-worker.sh` 的 tmux command 中不展开。
- **Provider smoke 与文档同步**：`smoke-provider-settings.sh` 改为走 wrapper；`SKILL.md`、`references/01-model-selection-matrix.md`、`references/06-agent-cli-reference.md`、`references/09-parallel-lessons.md` 更新为 settings + `--model` + wrapper 三件套口径。
- **Provider settings 模板补全**：example settings 增加 `ANTHROPIC_API_KEY` 和 haiku/opus/sonnet `_MODEL_NAME` 字段；真实 settings 仍保持本地 ignored。

### Reason
- 来源：用户指出另一个项目 MyAgents 在运行时可以动态选择 provider/model，并且可能屏蔽了用户级 Claude settings。对照 MyAgents 发现关键不是 SDK 本身，而是一次会话启动前的有效配置快照、settings-sourced provider env 屏蔽和子进程 env 显式构造。
- 本次把该模式移植到 Claude Code CLI worker 层，解决用户级 `~/.claude/settings.json` 指向 MiniMax 时，任务指定 GLM/DeepSeek/MiniMax 等 provider 仍可能被全局配置污染的问题。

## [1.16.3] - 2026-06-23

### Fixed
- **Claude Code 第三方 provider 启动命令强制显式模型**：`render-runtime-profile.sh` 在 `claude-code + --settings` 但缺少 `--model` 时直接报错，避免用户级 `~/.claude/settings.json` 或继承环境中的 `ANTHROPIC_MODEL` 覆盖 provider profile。
- **Provider settings 模板补全当前模型字段**：`config/claude-provider-settings.example.json` 新增 `ANTHROPIC_MODEL`、`ANTHROPIC_MODEL_NAME`、`ANTHROPIC_DEFAULT_FABLE_MODEL` 和 `ANTHROPIC_DEFAULT_FABLE_MODEL_NAME`，与现有 haiku/opus/sonnet 映射共同描述 provider 模型。
- **启动文档修正**：`SKILL.md`、`references/06-agent-cli-reference.md`、`references/09-parallel-lessons.md` 不再建议只用 `claude --settings <settings>`；第三方 provider worker 标准命令改为 `claude --settings <settings> --model <provider-model> ...`，并要求 PM 核对启动 banner。
- **Provider settings 排障口径**：补充 401/403、429/529、banner 模型错位、MCP 卡启动的判断规则。

### Reason
- 来源：法律 AI 书 `writing-reviewer` skill-version eval 中，PM 以 GLM 5.2 settings 启动 worker，交互界面仍显示 `MiniMax-M3[1m]`。诊断发现用户级 `~/.claude/settings.json` 配置了 `ANTHROPIC_MODEL=MiniMax-M3[1m]`，而本地 provider settings 只配置 base URL、token 和默认模型映射，没有配置当前会话模型。
- 实测结果：只传 `--settings glm-5.2.settings.json` 时 banner 显示 MiniMax；补 `--model glm-5.2[1M]` 后 banner 显示 GLM；在 settings 内补 `ANTHROPIC_MODEL` 后，即使漏传 `--model`，banner 也不再被用户级 MiniMax 默认覆盖。
- 同轮诊断还确认 GLM 5.1 / 5.2 最小请求均返回 `open.bigmodel.cn` 的 529，MiniMax 最小请求正常。这说明 GLM 当时的失败是目标 provider 网关拥塞 / 限流，不是 Claude Code 本地 settings 解析失败或余额不足。

## [1.16.2] - 2026-06-15

### Fixed (文档层)
- **`SKILL.md §6 启动方式`** 加 2 段醒目警示，来源 FaroPDF v0.2 Wave 1 spawn ISS-071 worker 实战（[DEC-033]）：
  - **`<` redirect 必须用 `bash -lc` 包**：`spawn-worker.sh:305` `tmux new-session -d -s "$SESSION" -c "$WORKTREE" "$COMMAND"` 直接 exec command 不通过 shell，shell metacharacter 不展开。错误：`--command 'claude -p < /tmp/x.md'`；正确：`--command "bash -lc 'claude -p < /tmp/x.md'"`。
  - **claude `-p` batch 模式 autocompact thrash 风险**：大 prompt（> 5KB）+ 大 codebase context 会触发 claude 内部 `Autocompact is thrashing` 3 次后自动终止，worker 永远不到达终态。规避：拆小 prompt < 3KB / 用交互式 claude + tmux send-keys / 窄 scope worker。

### Reason
- 2026-06-15 FaroPDF v0.2 推进期间，PM 按 §3.1 启动 Wave 1（3 worker ISS-071/067/070 并行）。spawn ISS-071 一个验证链路，遇到 2 个 skill 层 bug：
  1. `--command 'claude -p < /tmp/iss-071-prompt.md'` 启动后 worker 立即退出，sentinel 等 7211s 后 SENTINEL_TIMEOUT。
  2. 修复 Bug 1 后 worker 真启动 + 写 STATUS.json bootstrap，4 分钟后 claude 进程 autocompact thrash 自动停止，sentinel 持续轮询。
- PM 决策取消 Wave 1，改单 session 直推 ISS-071。详见项目侧 `FaroPDF/docs/DECISIONS.md` DEC-104 + skill 侧 [DEC-033]。
- 本次只改文档警示，不动 `spawn-worker.sh` 脚本（自动检测 shell metachar 留 follow-up，避免覆盖用户的非 bash shell 选择）。

### Follow-up (TASKS 已登记)
- `spawn-worker.sh` opt-in `--shell-wrap` flag 自动包 `bash -lc`（待证据足够时升级）
- `templates/worker-prompt.md` 加专门小节说明 claude -p 模式限制 + 替代方案
- memory `project-multi-agent-state` 补 Wave 1 / Bug A&B 经验

---

## [1.16.1] - 2026-06-05

### Fixed
- **`scripts/sentinel.sh` synonym 兜底**：case 分支接受 worker 实际写的 synonym 终态。成功终态 `done|completed|finished|complete` → exit 0；失败终态 `failed|blocked|stopped|aborted|cancelled` → exit 2。`SENTINEL_UNKNOWN_STATUS` 仍保留 `*)` 诊断 log，但不再让 worker 写 synonym 时死锁轮询到 `--max-wait`。

### Changed
- **`templates/worker-prompt.md` Process §9**：新增"Canonical terminal status (mandatory)"步骤，明确 worker 终态必须用 `status="done"` **exactly**；defensively sentinel 也认 `completed` / `finished` / `complete`，但 worker 不得依赖 synonym。引用项目侧 DEC-060 / skill 侧 [DEC-032]。

### Reason
- 来源：v1.16.0 sentinel bash 模式首次在 FaroPDF Wave 6 真用（2 worker 并行），两位 worker 写 `status="completed"` / `status="finished"` 逃过 sentinel case 分支的 `done` 严格判断，sentinel 持续空转，PM 收不到 harness task-notification，直到用户手动问"进度"才暴露。Spike 阶段只测了 `done` / `failed` 严格用法，没覆盖 LLM 写 synonym 的漂移。
- 验证：Wave 6 实战触发，PM 收口时 kill 2 sentinel（exit 143）+ 写双侧 patch 后已修复。Wave 7+ 工人按 worker-prompt.md §9 写 `status="done"`，sentinel 事件驱动链路恢复。
- 项目侧对应：FaroPDF 仓 `docs/DECISIONS.md` DEC-060（PR #48 / 2026-06-05）记录了实战触发 + 修复方案；本条 CHANGELOG 是 skill 侧 [DEC-032] 的实际交付记录。

## [1.16.0] - 2026-06-05

### Added
- **Sentinel bash 模式**（Task #9）：每个 worker 配一个 `scripts/sentinel.sh` 进程，PM 用 `run_in_background=true` 启，harness 在 sentinel exit 时通过 task-notification 自动 re-invoke PM，实现事件驱动 PM 唤醒，零 idle token 消耗。
- **`scripts/sentinel.sh`**：轮询 `STATUS.json` 终态（`done | failed | blocked | stopped`），命中后 capture tmux pane tail、`tmux kill-session`、`exit`。退出码 0/2/64/124 与 `wait-worker.sh` 对齐。复用 `redact_sensitive_stream` 内联（不抽公共库）。
- **`templates/pm-sentinel-response.md`**：PM 收到 sentinel task-notification 后的标准动作清单，按 exit code 分支（0=done, 2=failed/blocked/stopped, 124=timeout, 64=usage error），含范围检查、graceful 降级到 `pm-monitor.sh` 路径。
- **`references/04-sentinel-design.md`**：设计文档，复述 2026-06-05 3 phase spike 结果，解释为什么 Sentinel 模式与 DEC-030 假设不同（数量线性 / 单进程单 STATUS / 进程语义清晰 / graceful 降级）。
- **`scripts/smoke-sentinel.sh`**：端到端 smoke test，覆盖 done 路径（sentinel exit 0 + tmux killed + pane tail captured + redaction 工作）和 timeout 路径（sentinel exit 124 + max-wait 触发）。

### Changed
- **`scripts/spawn-worker.sh`**：新增 `--with-sentinel`、`--sentinel-poll-interval`、`--sentinel-max-wait`、`--keep-tmux-on-terminal` 标志。`--with-sentinel` 启用时输出 `SPAWN_WORKER_SENTINEL_CMD: ...` 和 `SPAWN_WORKER_RECOMMENDED_NEXT: ...` 提示 PM 在下一次 Bash 调用里 `run_in_background=true` 启 sentinel。**不在 spawn-worker 内部启 sentinel**（职责分离 + 避免 auto mode 拒多 background）。
- **`scripts/lint-wait-script.sh`**：默认 lint 集合加入 `sentinel.sh`，复用现有 `bash -n` + substring expansion 检查。
- **`SKILL.md` §6 工具面**：列出 `sentinel.sh`；§7.1 增加脚注指向 §7.2（"§7.2 是本规则的限定条件下可工作变体"）；新增 §7.2 Sentinel bash 模式章节，描述 PM 端两次 Bash 调用模式、事件命名空间、降级路径、调优建议。
- **`SKILL.md` frontmatter**：version bump `1.15.1` → `1.16.0`。
- **`DECISIONS.md`**：新增 `[DEC-031] - 2026-06-05 - Sentinel bash 模式 (Task #9 实施)`，**限定条件下 supersede DEC-030**，明确 sentinel 数 = 未完结 worker 数（线性而非 N×N）、单进程单 STATUS、graceful 降级是默认行为。DEC-030 文本保留（历史判断）。

### Reason
- 来源：Wave 4/5 实际痛点——PM 用 `pm-monitor.sh --log-file` 巡检是 polling-based，事件驱动不闭环，PM 必须靠用户输入或低频轮询才能感知 worker 终态。Wave 5 收口时把 Task #9 标"designed, not implemented"。
- 验证：2026-06-05 30 分钟 Spike 在 Claude Code 实测 `run_in_background=true` Bash 任务，3 phases 全部通过——harness 不区分 exit code（0/1/124 都 re-invoke），多次并发 notification 同 turn 批处理，单 background 拒率 spike 实测 1/6，graceful 降级是默认行为。
- 结论：在限定条件下（sentinel 数线性、单进程单 STATUS、graceful 降级），`run_in_background=true` Bash 任务可以作为可靠的 PM 唤醒机制。Wave 6 启动时启用。

### Out of Scope（避免在本次 PR 蔓延）
- Codex / OpenCode worker 的 sentinel 集成：暂未实测，Codex 走 `templates/codex-heartbeat-wait.md`
- 多 sentinel 对单 worker 去重：PM 行为层处理
- 重写 `pm-monitor.sh`（Task #6 单独 PR）

## [1.15.1] - 2026-06-05

### Changed
- **Claude Code background wait caveat**：修正 `run-in-background` 描述，明确 background Bash 只负责后台运行等待器，不保证把 worker 终态消息推回 PM / agent session。
- **multi-worker monitoring**：多 worker / Wave 默认使用 `pm-monitor.sh --log-file` + 显式低频巡检，不再建议为每个 worker 启 background wait 并期待宿主自动回调。

### Reason
- 来源：用户在 Claude Code 中实测发现，background Bash 没有可靠触发 agent session；开启多个独立 worker 时可能没有任何消息返回。
- 结论：完成通知必须回到结构化 checkpoint、事件日志和显式巡检；background job 只能作为日志写入器或人工可查看后台进程。

## [1.15.0] - 2026-06-05

### Added
- **optional project config template**：新增 `templates/project-config.json`，声明 trunk、任务源、worktree/session 默认路径、按 worker type 拆分的验证命令、provider slot、非敏感配置复制清单和 hook 边界。

### Changed
- **SKILL.md config discipline**：标准流程增加项目配置读取规则，明确配置只提供默认值，不替代 PM 判断。
- **Goal/worker templates**：增加 project config 字段，要求 PM 写明采用了哪些配置字段、忽略了哪些字段以及安全检查结果。

### Reason
- 来源：TASKS 中仍有“评估项目级配置文件”待办，且用户关注脚本是否过度设计。
- 结论：采用轻量模板，不新增脚本、不自动读取、不自动复制配置、不自动执行 hook；`.env`、真实 settings、token/key/cert 等继续默认禁止。

## [1.14.1] - 2026-06-05

### Changed
- **script surface governance**：明确默认工具面只包含 dependency check、runtime profile render、spawn worker 和 PM monitor；status/clean/wait/test/terminal split 均按场景使用，避免 PM 被脚本数量牵引。
- **provider slot planning**：超过 4 个 worker 时，改为显式声明 `backend + settings/profile path + provider + model + max concurrency`，而不是脚本自动猜测用哪个 settings.json。
- **templates**：worker prompt、checkpoint、Goal Contract 和 Wave Summary 增加 settings/profile path，让每个 worker 的额度来源可审计但不暴露 settings 内容。

### Reason
- 来源：用户担心脚本数量过多、出现过度设计，并追问超过 4 个 worker 时到底如何分配 settings.json。
- 结论：不新增自动 scheduler。现阶段应把 provider pool 做成 PM 可审计的显式 slot 表；如果只有一个可用 settings/profile，则并发 cap 降到 3-4，剩余任务进入下一 Wave。

## [1.14.0] - 2026-06-05

### Added
- **runtime dependency matrix**：新增 `references/02-runtime-dependencies.md`，按 core、tmux/worktree、PR/GitHub、worker backend、Codex heartbeat、terminal split 和验证工具拆分依赖。
- **dependency checker**：新增 `scripts/check-dependencies.sh`，可检查核心依赖、backend CLI、`gh` 和终端分屏工具；脚本只报告状态，不安装软件、不启动 worker。

### Changed
- **SKILL.md dependency section**：将依赖说明从单张系统依赖表升级为分层依赖说明，明确 `claude`、`codex`、`opencode`、`gh` 不是所有模式的硬依赖。
- **smoke test**：`smoke-tmux-worker.sh` 纳入 dependency checker 基础回归。

### Reason
- 来源：用户指出使用本 Skill 可能还有常规依赖需要安装，当前文档没有写清楚。
- 结论：依赖应按执行模式拆分，避免把所有可选 backend 都误解为必装，同时给 PM 一个启动前的本地检查入口。

## [1.13.0] - 2026-06-05

### Added
- **runtime profile command helper**：新增 `scripts/render-runtime-profile.sh`，按 `claude-code`、`claude-oauth`、`codex`、`opencode`、`custom` backend 生成 worker command、prompt context 和 spawn metadata，减少 PM 手写 provider/profile 命令。
- **Agent Teams troubleshooting**：新增 `references/10-agent-teams-troubleshooting.md`，覆盖 agent/team 不可见、错误 cwd、官方 worktree 状态映射、checkpoint 缺失、PR 收口和必须停止的场景。

### Changed
- **spawn flow**：SKILL.md 启动示例改为先用 `render-runtime-profile.sh` 生成 runtime 字段，再传给 `spawn-worker.sh`，保持启动命令生成与 worktree/session gate 分离。
- **smoke test**：`smoke-tmux-worker.sh` 覆盖 runtime profile helper 的 custom、Claude Code 和 Codex 输出。

### Reason
- 来源：用户要求继续推进 TASKS 中可落地的优化项。
- 结论：Agent Teams 排障指南和 runtime profile helper 都能本地落地并提升稳定性；Agent Teams feature flag、真实 Claude 原生 `--worktree --tmux` 后端和跨 PM/worker smoke 仍需要真实宿主环境验证。

## [1.12.0] - 2026-06-05

### Added
- **Goal-Driven Multi-Wave Loop**：SKILL.md 新增 PM 级 Orchestration Goal Loop，支持在成功条件满足前自动收口当前 Wave、读取任务源、选择下一批安全任务并启动下一 Wave。
- **Goal Contract 模板**：新增 `templates/orchestration-goal.md`，要求 PM 在连续推进前写清任务源、成功条件、自主级别、并发/预算上限、继续条件和停止条件。
- **Goal Loop 状态映射**：`checkpoint-status.json` 增加 `orchestration_goal` 字段；`worker-prompt.md` 增加 Goal ID / Loop Iteration，并明确 worker 不得自行领取其他任务。

### Changed
- **Wave summary**：新增 Goal ID、loop iteration、continue/stop decision、remaining tasks 和 next Wave 字段，让每轮自动继续都有可审计记录。
- **Skill 路由**：明确 Claude Code / Codex `/goal` 可作为 PM loop 的宿主续跑能力，但不替代 worktree、tmux、checkpoint、review 和 merge 门禁。

### Reason
- 来源：用户希望多 Agent 编排不止“一次运行一个 Wave”，而是在 PR 验收、验证和任务源状态正常时，能自动继续下一 Wave，直到目标范围内任务耗尽或触发停机条件。
- 结论：连续推进应放在 PM 层，不放给 worker；worker 保持窄任务边界，PM 负责任务池、Wave 收口、继续/停止判断和合并门禁。

## [1.11.0] - 2026-06-04

### Added
- **Wave-Based Orchestration**：SKILL.md 新增 Wave 一等调度概念，要求 PM 在每轮启动前记录 `wave_id`、worker 清单、base ref、共享风险、provider/model/slot、收口顺序和下一轮进入条件。
- **跨 provider 并发池**：明确超过 3-4 个 worker 时不应压在单一 API provider 上，应跨 runtime profile/API 来源分流，并在 Wave 收口时评估模型/provider 表现。
- **worker 类型与验证底线**：worker prompt 新增 `ui-wiring`、`contract-extension`、`tauri-command`、`docs/research` 等类型，明确 Tauri/Rust worker 的 `cargo check --offline` 验证底线和 skipped verification 记录要求。
- **Wave checkpoint 字段与 summary 模板**：`checkpoint-status.json` 新增 `wave`、`worker_class`、provider/model/slot 和 `model_evaluation` 字段；新增 `templates/wave-summary.md`。
- **多信号进展巡检**：`pm-monitor.sh` 新增 `--wave-id`、`--progress-stale-threshold`、`WORKER_SILENT_PROGRESS`、`WORKER_NO_PROGRESS` 和 `WORKER_FINISHED_NO_PHASE_DONE`，结合 STATUS、commit、file mtime 和 dirty state 判断 worker 是否真有进展。
- **wait script lint**：新增 `scripts/lint-wait-script.sh`，用于检查 wait/monitor/custom wait 脚本的 `bash -n` 和 `${VAR:0:N}` substring 闭合错误。
- **worktree metadata**：`spawn-worker.sh` 在 Session Context 写入 `METADATA.json`，记录 base、session、runtime profile、provider slot、验证命令和 PR 占位；`worktree-status.sh` / `clean-worktree.sh` 会展示该摘要。

### Changed
- **worker prompt**：加入 Wave 信息、provider slot、Decision ID race 规则、worker type rules 和验证底线。
- **spawn gate**：`spawn-worker.sh`、`worktree-status.sh` 和 `clean-worktree.sh` 使用物理路径解析，避免 macOS `/var` / `/private/var` 别名导致 cwd gate 误失败。
- **worktree-status.sh**：单 worker 只读总览增加 wave/provider/model/type 输出。
- **smoke test**：`smoke-tmux-worker.sh` 通过 `spawn-worker.sh` 创建 worker，覆盖 metadata 写入、总览展示和清理前摘要。
- **parallel-lessons.md**：补充 Wave worker 类型、Vitest/Vite 二进制资源兼容、DEC 编号 race 和 provider 并发池实战记录。

### Reason
- 来源：用户要求评估 TASKS 中多个优化/升级建议，并把合理项升级为 `multi-agent-orchestration` 的正式机制。
- 结论：Wave、provider 并发池、多信号巡检、worker 类型、验证底线和 DEC race 属于高复用执行协议；Agent Teams 发布状态、终端 split-panes、底层 adapter、Snap mode 等仍留作后续研究。

## [1.10.0] - 2026-06-04

### Added
- **worker 生命周期脚本**：新增 `spawn-worker.sh`、`worktree-status.sh`、`clean-worktree.sh` 和 `smoke-tmux-worker.sh`，把 worktree/session 创建、单 worker 状态总览、安全清理和端到端 smoke test 固化为可执行入口。
- **commit stale 事件**：`pm-monitor.sh` 新增 `--commit-stale-threshold` 和 `WORKER_STALE_NO_COMMIT`，用于提示 session 存活但分支长时间没有阶段性提交的 worker。
- **Codex heartbeat 模板**：新增 `templates/codex-heartbeat-wait.md`，明确 Codex App 用 `wait-worker.sh --once` 做轻量唤醒，创建/修改 automation 时必须使用 `automation_update` 工具。
- **Worker commit cadence**：worker prompt 要求长任务每 30-60 分钟或阶段完成后生成可 review commit，并刷新 `STATUS.json` 的 Git 字段。

### Changed
- **wait-worker.sh 输出脱敏**：tmux pane tail 和 RESULT tail 默认过滤 token/key/secret/auth/password 等敏感行，并替换常见 secret token 片段。
- **SKILL.md 压缩启动章节**：将长启动示例收束为 `spawn-worker.sh` + 常用 command 索引，保留防逃逸门禁和最小验证规则。
- **checkpoint Git 字段**：`templates/checkpoint-status.json` 增加 `git.last_commit_at` 和 `git.commits_since_base`，`pm-monitor.sh` / `worktree-status.sh` 同步显示。
- **脚本 shebang**：核心脚本统一使用 `/usr/bin/env bash`；`pm-monitor.sh` 增加 bash 4+ 版本门禁，避免 macOS 系统 `/bin/bash` 3.2 运行关联数组失败。
- **UTC 时间解析**：`pm-monitor.sh` 和 `wait-worker.sh` 在 macOS 上按 UTC 解析 `updated_at` 的 `Z` 后缀，避免刚写入的 checkpoint 被误报 stale。

### Reason
- 来源：用户希望把 “tmux 独立 session 防逃逸” 做成可执行、可验证、可 smoke 的完整协议，并适配 Codex 的后台等待/heartbeat 方式。
- 目标：让 PM 不再依赖手写命令和主观自律；启动、等待、监控、状态、清理和回归验证都有明确脚本入口。

## [1.9.9] - 2026-06-03

### Added
- **wait-worker.sh tmux 诊断尾部输出**：新增 `--tmux-session`、`--pane-tail-lines`、`--include-pane-on` 和 `--stale-threshold`。默认只在 checkpoint 缺失、过期或终态时读取 tmux pane tail。
- **状态源分层规则**：SKILL.md §7.1 明确 `STATUS.json` / `RESULT.md` / `PATCH_SUMMARY.md` 是主协议，`tmux capture-pane` 只作诊断窗口，不作为完成标准。

### Reason
- 来源：用户提出既然 background Bash 在运行，是否可以直接读取 tmux worker 输出。
- 结论：可以读，但要作为诊断兜底而非主状态源，避免屏幕输出截断、清屏、敏感信息和上下文膨胀影响 PM 判断。

## [1.9.8] - 2026-06-03

### Added
- **scripts/wait-worker.sh**：新增单 worker 等待器，可持续等待或 `--once` 快速检查 `.claude/agent-sessions/<session>/STATUS.json`，在 `done` / `failed` / `blocked` / `stopped` 时输出 RESULT/PATCH_SUMMARY 路径并退出。
- **§7.1 主动等待与宿主唤醒**：明确 `wait-worker.sh` 不替代 `pm-monitor.sh`；Claude Code 可接 Bash background/run-in-background，Codex App 则用当前 thread 的 heartbeat automation 调用 `wait-worker.sh --once` 实现主动唤醒。

### Reason
- 来源：用户希望 Claude Code 的 Bash `run_in_background` 等待体验也能适配 Codex。
- 结论：Codex CLI 没有同名自动通知机制；Codex 适配应通过“通用等待脚本 + Codex heartbeat/thread wakeup”完成，避免把核心 monitor 绑定到单一宿主。

## [1.9.7] - 2026-06-03

### Added
- **防逃逸门禁**：当用户或项目明确要求 tmux / 独立 session / 开 worker 时，PM 在业务实现前必须创建 worktree/branch、启动 session、验证 cwd/branch、派发 worker prompt 并确认 `STATUS.json`，否则报告阻塞，不得静默降级为 PM 直接实现或普通 Subagent。
- **Worker Isolation Gate**：`templates/worker-prompt.md` 要求 worker 在读任务或实现前确认 cwd、branch 和 worktree；不匹配时写 blocked `STATUS.json` 并停止。
- **STATUS orchestration_gate 字段**：`templates/checkpoint-status.json` 新增 session/cwd/branch/worktree/degraded/escape 结构化门禁字段，`pm-monitor.sh` 会输出 `ORCHESTRATION_GATE_FAILED`。

### Fixed
- **pm-monitor.sh 本地未 push 分支误退出**：远端分支不存在时先查 merged PR；若本地分支仍存在，输出 `BRANCH_NOT_PUSHED` 并保持 monitor 运行。
- **SESSION_GONE 去重**：tmux session 消失事件只在状态变化时输出，避免低频巡检日志重复刷屏。

### Reason
- 来源：用户反馈其他模型在 Claude Code 中反复没有按 tmux 独立 session 推进，需要把“不要逃逸”从建议性描述升级成可检查门禁。
- 目标：让 PM、worker 和 monitor 三层都能暴露逃逸：PM 不能绕过启动门禁，worker 不能在错误目录继续实现，monitor 能报告 gate 失败和本地分支未 push。

## [1.9.6] - 2026-06-03

### Changed
- **SKILL.md §6 tmux / Claude Code worker 例子**：去掉 `--max-turns 20` 的限制示例，加注"不要设 `--max-turns`；PM 重点是检测 worker 真在运转而不是限制 turn 数"。
- **scripts/pm-monitor.sh BRANCH 状态区分**：远端 branch 不存在时，区分两种情况：
  - 本地 branch HEAD == main HEAD → `BRANCH_NOT_PUSHED: $branch (waiting for worker to commit and push)`（**新事件**）
  - 本地 branch HEAD != main HEAD → `BRANCH_MERGED: $branch`（保留原行为）
  - 解决"branch 还没 push 被误判为 merged"导致 monitor 立刻退出的问题。

### Reason
- 来源：FaroPDF v0.1 Wave 2 启 worker 后 PM 监控失灵的根因分析。
- 主要根因：
  1. worker prompt 没强调"启动后立即写 STATUS.json 心跳"，导致 max-turns 触发时没 STATUS.json，PM 无从判断 worker 真在运转。
  2. SKILL 自带 pm-monitor.sh 的 BRANCH_MERGED 判断只看 `origin/$branch` 是否存在，忽略了"branch 还没 push"的常见 case，导致 monitor 立刻退出。
  3. SKILL 例子给的 `--max-turns 20` 让我误以为应该设上限，实际应让 worker 跑自然结束。

## [1.9.5] - 2026-06-03

### Added
- **§8.0 PM 在 Worker 提 PR 后的持续同步**（精简版）：
  1. 提 PR 之后立即跑 `gh pr view <N> --json mergeable,mergeStateStatus,baseRefName`；冲突走 `git-workflow` 决策表。
  2. PM 在主目录 commit docs / DEC 之后**立即** `git push origin main`，避免本地与 origin/main drift（squash merge 引入的"内容相同但 history 不同"会让 git 误判冲突）。

### Reason
- 来源：FaroPDF v0.1 Wave 1 真实合并 PR #18 / #19 前的根因复盘。
- 主要根因：PM 没在 worker 提 PR 后立即跑 mergeable 检查；PM 本地 main commit DEC 后没立即 push。

## [1.9.4] - 2026-06-03

### Added
- `parallel-lessons.md` 新增 G17：任务编号从 `ISS-NNN` 改为 `Task-NNN`（与 project-init v1.1.1 对齐）。说明新约定、迁移规则，以及历史 lesson（如 G15 的 `FaroPDF ISS-018`）和 commit history 保持原样不改写。

## [1.9.3] - 2026-06-03

### Changed
- 将 checkpoint 可复制模板从 `references/03-checkpoint-files.md` 移到 `templates/`，包括 `checkpoint-status.json`、`checkpoint-result.md` 和 `checkpoint-patch-summary.md`。
- 新增 `templates/worker-prompt.md`，将 worker prompt 拆成 Bootstrap-only 和 Full worker 两段，并按 Context / Background / Mission / Scope / Deliverables / Process / Verification / Autonomy / Out of Scope / PM Correction 组织。
- 精简 `SKILL.md` 与 `references/03-checkpoint-files.md`：正文只保留规则、字段经济性和模板路径，避免 Skill 主体继续膨胀。

## [1.9.2] - 2026-06-03

### Changed
- 将 `STATUS.json` 升级为 v2 schema，补充 `task_source`、`current_action`、`next_action`、`scope`、`runtime`、`git`、`pm_action_required`、`blocker`、`risks` 和 `last_pm_correction` 等 PM 决策字段。
- 明确 `STATUS.json` 的经济性边界：只记录 PM 自动监控和 review 决策必需的结构化信号，不记录 token、完整环境变量、settings 内容或长日志。
- 增强 `pm-monitor.sh`：新增 `--once`、`--interval`、`--stale-threshold`、`--log-file`，支持一次性巡检、低频后台巡检和事件日志落盘。
- `pm-monitor.sh` 现在会从 checkpoint 输出 `CHECKPOINT_STALE`、`AGENT_NEEDS_INPUT`、`CHECKPOINT_TEST_FAILURE`、`CHECKPOINT_PR` 等事件，减少 PM 前台轮询需求。
- 补充经济型巡检规则：脚本负责事件输出和日志，是否自动唤起 PM 取决于宿主环境；无唤醒能力时用 `--once` 或低频读取 log tail。

## [1.9.1] - 2026-06-03

### Changed
- 将新 worker 的 checkpoint 目录从 `.agent-context/` 调整为 `.claude/agent-sessions/<session-id>/`，复用项目既有 `.claude/` 协作空间；`pm-monitor.sh` 仍兼容读取旧 `.agent-context/`。
- 明确 Claude Code 官方 Agent Teams 的状态源在 `~/.claude/teams/<team>/` 与 `~/.claude/tasks/<team>/`，不要在项目内自造 `.claude/teams/` 冒充官方 team。
- 明确 worktree、分支和 session context 默认由 PM 创建；只有 Claude Code 官方 Agent Teams / agent view 明确使用自身 `--worktree` 能力时，才允许 worker 侧创建隔离环境，PM 仍需验收。
- 将 PM review correction 固化为收口流程：PM review 失败时优先把具体修正发回原 worker，worker 追加修复 commit、更新验证和 PR，PM 再复核。
- 补充环境差异规则：Claude Code provider settings、Claude OAuth/订阅、Codex/OpenAI 和 OpenCode profile 必须分开声明，不默认清理或继承环境变量。

## [1.9.0] - 2026-06-02

### Changed
- 将 PM 从具体产品中解耦：当前 Codex、Claude Code 或其他主会话都可以担任 PM。
- 将 worker backend 抽象为 Claude Code、Codex、OpenCode、shell 和可选 ACP adapter，支持从 Claude Code 启动 Codex/OpenCode worker，或从 Codex 启动 Claude Code/OpenCode worker。
- 补充 runtime profile / 额度路由规则，明确 Claude Code worker 默认走第三方 API provider settings，订阅/OAuth 只作为显式例外。
- 补充 Claude Code 第三方 API provider settings 模式：通过 `--settings /path/to/provider.settings.json` 加载 `ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN` 和默认模型环境变量。
- 将 Claude Code worker 默认额度模式调整为第三方 API provider settings，并新增 `references/claude-provider-settings.example.json` 模板。
- 将 Claude Code tmux worker 默认启动方式调整为交互式后台终端 session；`-p` 仅作为批处理 prompt 的可选模式。
- 将 provider settings 示例调整为 Minimax Anthropic-compatible API 结构，保持 token、base URL、三类默认模型、timeout、thinking tokens 和行为开关一并配置。
- 增加结构化 checkpoint 三件套：`.agent-context/STATUS.json`、`RESULT.md`、`PATCH_SUMMARY.md`，并新增模板参考文档。
- 更新 `pm-monitor.sh`，支持从分支自动定位 worktree、监听 checkpoint 文件变化，并可选通过 `--claude-agents-cwd` 读取 Claude 官方后台 session 状态。
- 补充 Claude Code 官方 agent view / background session 入口：`claude agents`、`claude agents --json`、`--worktree`、`--tmux`，以及版本支持时的 `claude --bg` 和 `/bg`，作为 tmux 之外的 Claude 专用后台会话模式。
- 补充 OpenCode worker 支持：默认用 `opencode run --format json --model <provider/model>`，并将 `opencode acp` 记录为可选 ACP server 候选。
- 补充 custom CLI worker 模板，支持其他可一行命令启动、可在指定 worktree 中运行的 Agent。
- 将 ACP 定位为可选后端：协议层结构化，但默认仍以 `tmux + worktree + checkpoint 文件 + git 状态` 作为稳定执行层。
- 更新 Worker Prompt 模板，加入 PM Host、Worker Backend、Runtime Profile 和 `.agent-context/STATUS.json` / `RESULT.md` / `PATCH_SUMMARY.md` checkpoint 协议。
- 明确用户指定当前会话担任 PM agent 时，PM 默认不直接写业务代码；实现优先委派给 worktree worker、独立 session、Agent Teams 或 Subagent，PM 负责巡检、纠偏、review 和收口。
- 基于 FaroPDF ISS-018 实战补充流程约束：高延迟 provider 可两段式 bootstrap；`.agent-context/` 只作本地 checkpoint，不进入 Git/PR；worker 不应等待 PM 下一步；STATUS 每次写入必须刷新 `updated_at`；窄范围实现默认 low/medium effort。

## [1.8.2] - 2026-06-01

### Changed
- 收口发布包参考文档，只保留模型/执行模式矩阵、实战坑点和法律项目拆解样例。
- 精简法律场景参考，移除未落地的未来模板路径和外部 catalog 设想，明确其只作为本地执行层拆分样例。

### Removed
- 移除已落地或过时的历史平台调研、Agent Teams 优化积压和 Auto PM 蓝图文档，避免与当前 SKILL.md 实现机制重复或冲突。

## [1.8.1] - 2026-05-20

### Changed
- 同步相关 Skill 引用：`cross-agent-collab` 更名为 `cross-agent-coordination` 后，更新任务协调层边界说明和参考文档。

## [1.8.0] - 2026-05-20

### Changed
- 重命名 Skill：`multi-agent-workflow` → `multi-agent-orchestration`，标题改为 Multi-Agent Orchestration，以突出“本地多 Agent 执行编排”而非普通流程说明。
- 同步更新 SKILL.md description 和开篇说明，统一使用“执行编排”表述。
- 同步更新 `cross-agent-coordination` 中对本 Skill 的边界引用。

## [1.7.0] - 2026-05-20

### Changed
- 重命名 Skill：`parallel-agent-workflow` → `multi-agent-workflow`，标题改为 Multi-Agent Workflow，以匹配当前“多 Agent 本地执行编排”的职责边界。
- 优化 SKILL.md frontmatter description，补充正向触发场景和负向边界。
- 补充脚本依赖说明，明确 `pm-monitor.sh` 与 `terminal-split.sh` 的系统依赖和可选终端依赖。
- 同步更新 `cross-agent-coordination` 中对本 Skill 的边界引用。

## [1.6.0] - 2026-05-19

### Changed
- 精简 `SKILL.md` 为执行入口、命名规则、启动方式、巡检和收口规则；复杂细节转交 `references/` 和 `scripts/`。
- 明确任务源由项目配置或项目上下文决定，不在 Skill 中写死固定文件路径。
- 保留 `pm-monitor.sh` 的自动 PM 巡检能力，包括 Agent Teams inbox、tasks、Git SHA、PR 状态和 tmux session 多维监控。
- 保留 `terminal-split.sh` 的多终端分屏能力，包括 iTerm2、Kitty、WezTerm、Warp、Ghostty、Zed 和 Terminal.app。

## [1.5.0] - 2026-05-17

### Added
- 新增从项目任务源形成本地执行计划的通用规则：提取 Issue ID、状态、推进建议、文件/组件、依赖和验收标准。
- 新增 待办事项分组策略：按文件/组件重叠、依赖链、并行安全度和 PR 审查边界决定多个 Issue 是否放入同一 worktree/session。
- 新增 L1/L2/L3 路由说明，明确不是一个 Issue 必然对应一个 session。

### Changed
- `multi-agent-orchestration` 继续只拥有本地执行层；分组计划只服务本轮执行，不成为新的任务状态源。

## [1.4.0] - 2026-05-17

### Changed
- 明确本 Skill 只负责本地 Agent 会话、并行执行、PM 巡检和 worktree 隔离，不拥有任务主状态。
- 标准流程改为从项目任务源接任务；任务读取、外部 Agent 邮件触发和跨平台归属交给 `cross-agent-coordination`。
- 将 `git-task-orchestrator` 定位改为历史蓝图，不再作为当前协作入口，也不迁入其旧 worktree/session 方案。

## [1.3.0] - 2026-05-09

### Added
- **任务列表管理**：复用 Agent Teams 的 tasks 目录结构（JSON 任务项 + .lock 文件锁 + .highwatermark 增量读取）
- **文件锁机制**：agent 认领任务时用 `flock()` 防止并发冲突
- **高水位标记**：agent 增量读取任务列表，已完成任务自动删除并更新 highwatermark
- **pm-monitor.sh v4.1**：新增 `--tasks-dir` 参数、`check_task_states()` 函数、TASK_STATUS/TASK_COMPLETED 事件
- **权限继承自动化**：启动时自动从主仓库复制 `.claude/settings.json` 到每个 worktree
- **Context 恢复**：团队协议持久化到 worktree 的 `CLAUDE.md`，`claude --continue` 后协议不丢失

### Changed
- §6.1 创建 Worktree 增加权限自动复制步骤
- §6.2 初始化增加共享任务列表创建
- §6.3 启动 Agent 增加 CLAUDE.md 持久化步骤
- §6.6 清理增加 tasks 目录清理
- pm-monitor.sh 支持 `--tasks-dir` 参数

## [1.2.0] - 2026-05-09

### Changed
- **[重大] tmux 模式统一使用 Agent Teams 文件通信协议**：tmux 仅作为进程管理层，通信层复用 `~/.claude/teams/` 的 inbox + tasks 机制
- tmux 模式从"降级模式"重命名为"扩展模式"，体现架构对等性
- pm-monitor.sh v4：新增 `--team-dir` 参数，支持 inbox health_report 轮询（6 个新事件类型），保留 git SHA 轮询作为第二维度
- 运行时干预改为 inbox 命令消息 + 短 send-keys 提醒（替代长文本 send-keys）
- 监控巡检改为读取 PM inbox health_report（首选），capture-pane 降为回退方案

### Added
- Agent Teams 通信协议 prompt 模板（health_report 发送、命令检查、agent 间 inbox 通信）
- 团队目录初始化步骤（config.json + inbox 文件创建）
- health_report 消息类型（status/phase/progress/last_commit_sha/context_pct/issues）
- inbox 命令协议（continue/stop/check_review_feedback/rebase/commit_and_push）
- pm-monitor.sh 过时检测（5 分钟无 health_report 自动告警）
- 自动 PM 蓝图中的 tmux 扩展模式通信架构
- parallel-lessons.md 文件通信协议操作手册

## [1.1.0] - 2026-05-08

### Changed
- **[重大] 默认使用 Agent Teams（Teammate 模式）**：在 Claude Code 环境下，重任务优先使用官方 Agent Teams，tmux 降级为非 Claude Code 环境的备选方案
- 任务规模路由从二元（Subagent / tmux）升级为三元（Subagent / Agent Teams / tmux）
- 执行模式对比从二元表扩展为三元表（Subagent / Agent Teams / tmux Session）
- 监控方式从 tmux capture-pane 扩展为 Agent Teams 共享任务列表 + 邮箱系统
- 通信通道增加 Agent Teams 邮箱系统（双向通信，替代单向 send-keys）
- 新增环境检测逻辑（自动选择 Agent Teams 或 tmux 降级）
- 实战经验文档按 Agent Teams / tmux 降级 / 通用三类重组

### Added
- SKILL.md §3 前置条件拆分为 Agent Teams 和 tmux 两组
- SKILL.md §4 环境检测与模式选择
- SKILL.md §5 Agent Teams 标准流程（规划/Worktree/启动 Teammates/监控/干预/审查/合并）
- SKILL.md §6 tmux 降级模式（保留完整流程）
- Agent Teams 详细技术调研

## [1.0.0] - 2026-05-07

### 新增
- SKILL.md 核心技能定义，覆盖并行 Agent 完整生命周期
- terminal-split.sh 跨终端分屏脚本（支持 iTerm2/Kitty/WezTerm/Warp/Ghostty/Zed/Terminal.app）
- pm-monitor.sh 参数化 PM Monitor（基于 git SHA 变化，自动停止）
- 模型选择矩阵（L0/L1/L2 路由 + 运行时升降级）
- 执行模式选择（Subagent vs tmux + 混合模式）
- PM 巡检循环蓝图（健康/任务/PR 三维巡检）
- 实战经验教训文档（tmux 陷阱、合并冲突、IME 干扰）
- 与 git-task-orchestrator 的边界定义和协作路由
- 法律实务任务拆解模板（诉讼/非诉/尽调/合同审查）作为扩展参考
- 多 Agent 平台技术调研（Claude Code/OpenClaw/Codex/Hermes 对比 + Skills 生态评测）作为扩展参考
