# PM 统一控制入口

> `scripts/pm-orchestrate.sh`；本页适配 `multi-agent-orchestration` v2.15.0。

## 目录

1. 模式解析
2. 命令
3. Supervised 收口顺序
4. PR 先行与本地集成
5. 安全边界

## 1. 模式解析

脚本读取 `<worktree>/.claude/agent-sessions/<session>/METADATA.json`：

| METADATA | 模式 | 控制面 |
|---|---|---|
| 有 `supervised.dispatch_id` | `orca_supervised` | Dispatch/Delivery/worker-read |
| 仅有 `terminal_handle` | `orca_terminal` | terminal send/read/wait |
| 两者都无 | `tmux` | send-keys/capture-pane |

不要手工覆盖模式；缺 METADATA 时 fail-loud。

### 1.1 手动 register 的路由恢复（Task-092）

`orca-supervised-register.sh` 在 `worker-start` 和 Dispatch 绑定完成后，会从精确 `worktree id/path + terminal handle` 反查唯一 Session Context，并原子补写完整的 `.session.orca.supervised` 合同。成功输出：

```text
ORCAREG_METADATA_BIND=ok
```

如果 worktree 查询失败、Session Context 缺失/不唯一、terminal handle 不匹配、目标是符号链接或写入失败，脚本输出 `ORCAREG_METADATA_BIND=manual-required`，但不重启已经活跃的 worker。此时 PM：

1. 用 `orca worktree show --worktree id:<worktree_id> --json` 核对返回的 id/path 与 register 回执完全一致；
2. 在该精确 path 下查找唯一 `.claude/agent-sessions/*/METADATA.json`，并核对 `.session.orca.terminal_handle`；
3. 仅在身份唯一时，按 register 的 `ORCAREG_RUN_ID/TASK_ID/DISPATCH_ID/COORDINATOR_HANDLE/DISPATCH_BIND` 补写与正常 spawn 相同的 supervised 合同；
4. 立即用 `pm-orchestrate show` 复验路由。身份仍不唯一时保留现场并升级人工处理，不猜 session、不重试 spawn。

在 metadata 尚未恢复时，只能把 `orca terminal show --terminal <handle> --json` 的 `preview` 与 `lastOutputAt` 作为临时活性证据；它们不能证明业务完成，也不能替代 Dispatch/Delivery 生命周期。

## 2. 命令

```bash
# 每个 Wave 一次；输出 .result.run.id
pm-orchestrate.sh run-create --objective "Wave objective"

# 三种模式通用
pm-orchestrate.sh send --worktree "$WT" --session "$S" --text "..."
pm-orchestrate.sh read --worktree "$WT" --session "$S" --lines 50
pm-orchestrate.sh read --worktree "$WT" --session "$S" --lines 5000 --cursor 0
pm-orchestrate.sh peek --worktree "$WT" --session "$S"
pm-orchestrate.sh wait --worktree "$WT" --session "$S" --timeout 900

# supervised 专用
pm-orchestrate.sh show --worktree "$WT" --session "$S"
pm-orchestrate.sh reply --worktree "$WT" --session "$S" --message-id "$MID" --text "..."
pm-orchestrate.sh release --worktree "$WT" --session "$S"
pm-orchestrate.sh retain --worktree "$WT" --session "$S"
pm-orchestrate.sh ack --worktree "$WT" --session "$S" --delivery-id "$DID"
pm-orchestrate.sh settle --worktree "$WT" --session "$S" --reason "..." [--force] [--destroy]
pm-orchestrate.sh reauthorize --worktree "$WT" --session "$S" \
  --allow-cmd "make test" --resume-text "断点续接说明" [--task-id ID]
```

supervised `send` 是结构化 inbox mail，不是 terminal prompt injection；`read` 输出 Orca JSON 并保留 `source/cursor/fallbackReason`，便于 PM 判断读到的是精确 transcript 还是 terminal fallback。除只读 `read/show` 外，supervised 命令先对当前 PM terminal 执行 `run-use --id`，刷新 METADATA 的 coordinator handle；`wait/ack` 随后消费当前绑定 Run，不传陈旧 `--run`。

Orca terminal-managed `read` 同样透传 `--cursor`。alternate-screen TUI 首次从 `0` 读取并保存响应里的 `nextCursor`；后续按 cursor 增量读取，避免默认 tail 只剩 spinner。`wait` 的 `tui-idle` 只表示当前可交互/空闲，不是业务终态。

terminal/tmux 的超长 prompt（>500 字或含反引号、`$`、`|`）会写入 session context 的 `WORKER_PROMPT.md`，再投短 Read 指令。supervised guidance 直接写消息 body，不创建新的 prompt 文件。

`reauthorize`（Task-058）用于 worker 被 `SHELL_COMMAND_NOT_ALLOWLISTED` 拦验证且根因是 spawn 授权快照缺命令时：guard 读 `launch.sh` 内联的 `WORKER_INSTALL_AUTH_B64`（进程环境，运行中改授权文件无效），本命令合并 `--allow-cmd` 进授权文件后重写 B64（回验解码一致）、把被提问/中止翻成 failed 的 Task 复位 ready、在同一 worktree 创建新终端并复用 Task 重注册（worker-start 重注入完整任务）、改写 METADATA 的 terminal_handle/dispatch_id、可选发送 `--resume-text`、最后关闭旧终端句柄。未提交的工作区改动全部保留；provider lease 的 transport 记账留给 release/clean-worktree 阶段。

## 3. Supervised 收口顺序

1. `wait` 获取完整 Delivery；不要立即 ack。
2. 处理每条 `question/escalation/worker_done`。
3. 用 `show` 核对 accepted settlement，用 `read` 和真实 diff/tests 验收。只读状态与业务验收不能替代生命周期 settlement。
4. 每个 settled worker 选择立即复用、`release` 或用户明确要求时 `retain`。
5. 全部处理完后 `ack --delivery-id ...`。
6. 继续 `wait`，直到所有预期 Dispatch settle。

`wait` timeout 是 checkpoint，不是 failure；不要因此 stop/release worker。

## 4. PR 先行与本地集成

Orca worktree/terminal 是高频执行面；PR 是 PM 收口时的审阅边界。默认顺序是：

```text
worker 分支提交
  → safe-push
  → 创建或接管唯一匹配 PR
  → 冻结 PR base/head SHA、diff、checks 与 review
  → 在最新 origin/main 上建立本地集成候选
  → 复跑最终门禁
  → 按仓库规则本地推入 main，或交给 GitHub PR merge
  → 核对远端结果后再清理
```

这只是默认顺序，不是外部写入授权。没有用户或项目授权时，PM 停在只读 PR 审计与本地候选验证，不 push main、不 merge、不 close PR。

### 4.1 先查已有 PR，避免双开

worker 可能已经自行 push/开 PR。先运行只读审计：

```bash
bash scripts/pm-orchestrate.sh pr-audit \
  --worktree "$WT" --base-ref main --head-ref "$BRANCH" --head-sha "$HEAD_SHA" \
  --task-id Task-097 --agent-id agent-name
```

- stdout 只有一个 `pr-audit.v1` JSON；stderr 只写摘要 receipt，机器消费者不得混读。
- `exact` 同时要求 canonical repo/Git common dir、base ref/OID、head owner/ref/OID、真实 diff 指纹相等以及独立 `Task:`/`Agent:` trailer 一致；恰好一个 exact 且零 suspected 才返回 `adopt`。
- 同 head 错 SHA、同内容异分支、fork/cross-repository、归属不完整、diff/候选事实未知或 101 条候选截断都归 `suspected/ambiguous`，禁止 push/create。
- `create` 只表示当前只读证据允许进入授权门禁；不是 push 或创建权限。
- 接管 worker 自建 PR 不降低门禁：仍检查完整 diff、identity、checks、review、敏感文件和声明范围。

### 4.2 授权回执与 `pm-closeout`

所有 mutation 授权只接受本次 CLI 的显式参数，不从可继承环境变量取得。push/create 的第一阶段回执必须与脚本打印的 expected 字符串逐字一致：

```text
operation=<branch-push|pr-create|main-push|remote-merge|pr-close>;
repo=<HOST/OWNER/REPO>;pr=<PR号或none>;head=<branch>;sha=<40-hex>
```

实际值为单行、无换行；上方仅为字段说明。典型调用：

```bash
bash scripts/pm-closeout.sh \
  --worktree "$WT" --main-worktree "$MAIN_WT" \
  --mode local-after-pr --main-protection auto \
  --task-id Task-097 --agent-id agent-name \
  --integration-path skills/multi-agent-orchestration \
  --title "feat(multi-agent-orchestration): ..." \
  --safe-push-script /absolute/path/to/git-workflow/scripts/safe-push.sh \
  --verify-cmd bash --verify-arg scripts/test-pm-closeout.sh \
  --authorize-main-push 'operation=main-push;repo=github.com/OWNER/REPO;pr=123;head=feat/x;sha=<40-hex>' \
  --authorize-main-candidate 'operation=main-push-candidate;repo=github.com/OWNER/REPO;pr=123;head=feat/x;sha=<40-hex>;base=<40-hex>;candidate=<40-hex>;tree=<40-hex>'
```

若预审为 zero，还需在任何写入前同时提供绑定相同 repo/head/SHA 的 `--authorize-branch-push` 与 `--authorize-pr-create`；worker 已自建 exact PR 时两者都不需要。`--authorize-pr-close` 独立可选：省略时本地集成完成后保留 PR open；提供但不匹配时在 main push 前失败。

候选完成后还有第二阶段 mutation challenge，绑定最终 `base/candidate/tree`；调用方必须把完整 expected 值原样传回 `--authorize-main-candidate` 或 `--authorize-remote-candidate`。main 前移会改变 challenge，旧回执不可复用：首次调用可以停在 exit 8 的 `VALIDATE_ONLY`，审阅 challenge 后再用同一参数重跑。粗粒度 `main-push/remote-merge` 回执与候选回执缺一不可。

调用方 `body-file` 不得自带 `Task:`/`Agent:` trailer；脚本在任何 push/create 前拒绝，由唯一写入点追加，避免重复或冲突归属导致“PR 已创建但无法接管”。

`--main-protection auto` 读取 GitHub branch metadata 的类型化 `.protected` 布尔值；该字段同时覆盖 classic branch protection 与 rulesets。只有明确 `false` 才认定 unprotected；403/404、缺字段、畸形响应或未知状态都降为非成功 `VALIDATE_ONLY`。本地 main push 前再次读取该字段，候选验证期间从 false 变为 true/unknown 时不沿用旧结论。`--main-protection protected` 只允许显式选择更保守的远端路径，不提供 `unprotected` 绕过开关。

### 4.3 三种收口结果

| 结果 | 适用条件 | 行为 |
|---|---|---|
| `LOCAL_AFTER_PR` | branch metadata 正向证明 main unprotected，存在唯一 clean/idle main worktree，且两阶段 main-push 授权均匹配 | 在隔离 main clone 对冻结 worker patch 做三方应用并验证；从隔离 clone safe-push，远端确认后才 `--ff-only` 同步真实 main；提交主题带 `(#PR)` |
| `REMOTE_PR` | main 有 classic protection/ruleset，或项目明确以 GitHub 为合并权威 | 同样先建本地候选并验证；mutation 前重审唯一 PR 集合与冻结快照，确认无原生 merge queue 后用 `--match-head-commit` 合并，并复核 `state/mergedAt/mergeCommit`、merge 第一父提交等于已审 base、merge tree 等于候选 tree，且 merge commit 已进入 main |
| `VALIDATE_ONLY` | 用户显式只读，或 main/PR/checks/review/授权/范围/保护状态任一不明 | 显式请求时退出 0；由写入模式自动降级时退出 8，不 push、不 create、不 merge、不 close |

两种写入模式都必须至少提供一个仓库相对的 `--integration-path`；拒绝绝对路径、`..`、symlink 逃逸与 pathspec magic。候选从冻结 `WORKER_BASE..WORKER_TIP` 生成限定范围的 binary/full-index patch，在 fresh main 上 `--3way --index` 应用；同文件非重叠修改可保留，语义冲突则停在零 main mutation。

候选验证后、任何 main push/GitHub merge 前都重新 fetch main、重跑 `pr-audit` 并核对同一 PR 的 base/head/diff/checks/review；任何漂移回到审计，不沿用旧结论。Monorepo 禁止直接 `git merge <feature>`；最终本地同步只允许将已经远端确认的隔离 main 候选 `--ff-only` 到同一 Git common dir 的唯一 clean main worktree。

Task-097 不消费 GitHub 原生 merge queue：远端 mutation 前必须读到类型化 rules 数组且确认没有 `merge_queue`；发现 queue 或 API 状态未知都停在 exit 8 的 `VALIDATE_ONLY`，不得让 `gh pr merge` 留下稍后异步修改 main 的排队项。队列消费和延迟复核属于 Task-070。

普通失败（exit 2–8）都发生在 main commit point 前，因此必须保持 main 未修改。分布式写入存在不可消除的“服务端已提交、客户端回执丢失”窗口；写入调用开始后若无法确认，不得伪称零 mutation，也不得误报成功，而以 exit 9 输出可恢复状态：`PR_CREATE_OUTCOME_UNKNOWN`、`PR_CREATED_REVIEW_REQUIRED`、`REMOTE_MERGE_OUTCOME_UNKNOWN`、`REMOTE_MERGED_REVIEW_REQUIRED`、`MAIN_PUSH_OUTCOME_UNKNOWN`、`REMOTE_MAIN_APPLIED_LOCAL_PENDING` 或 `LOCAL_AFTER_PR_CLOSE_OUTCOME_UNKNOWN`。看到这些状态必须先读取远端真实 PR/main 再决定恢复动作，禁止盲重试 mutation。

`gh pr create` 本身也是分布式 commit point，GitHub 不提供本流程可用的幂等键，另一个 creator 可能在最终审计与 create 之间同时提交。因此本脚本能机械保证的是“commit point 前零 create、单次调用至多一次 create、结果不明时不重试”，不能承诺仓库最终全局零重复 open PR。post-create 重审发现多个候选时保留新建 PR 回执并进入 `PR_CREATED_REVIEW_REQUIRED`；不得在没有独立 close 授权时用自动关闭补偿掩盖竞态。

### 4.4 远端结果与清理

- 本地集成提交成功推入 main 后，原 PR 若未被 GitHub 自动标为 merged，使用包含 main commit SHA 的说明关闭；不得把 `CLOSED` 伪报成 GitHub `MERGED`。
- GitHub 合并路径以 `state == MERGED`、非空 `mergedAt` 和 `mergeCommit.oid` 为成功证据。
- 只有远端结果已确认且 worker/worktree 无未提交改动，才进入 release、分支和 worktree 清理。自动清理仍属于 Task-103，当前不得假装已实现。

## 5. 安全边界

- 脚本不自动 ack Delivery、不自动 release active worker、不删除 worktree（`settle` 例外兜底，但需 `--destroy` 显式升级）。worker 仍活着却漏发 `worker_done` 时先发结构化提醒；确认已死才 settle。
- `release/retain/reply/ack/settle` 仅对有 supervised metadata 的 worker 生效。`settle` 需 `--reason` 并先持久审计，默认以 `worker-stop` 原子 fence+stop 后不动文件；stop 失败时 `worker-abandon` 只作 fence 兜底且禁止 destroy。`--destroy` 仅在 stop 成功后释放 lease并删除精确 Orca/Git worktree。
- `--force` 只覆盖 liveness gate；不会绕过仓库身份、审计落盘、worker-stop、lease 或 worktree 删除失败。
- stale terminal handle 要先按 worktree 重新解析；禁止同时给旧/新 handle 双发。
- 普通 terminal worker 没有 `worker_done` 义务；不要用 terminal 文本伪造 Dispatch 完成。
- 对 external supervised terminal，`release` 后 retained 不必然是错误；文件清理仍须由 `clean-worktree.sh` 验证 settled 状态、external ownership、retained reason 和精确句柄后处理。
