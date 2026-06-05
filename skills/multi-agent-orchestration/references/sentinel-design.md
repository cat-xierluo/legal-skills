# Sentinel bash 模式 设计文档

> 读取时机：启用 sentinel、调查 PM 没被 worker done 事件唤醒、Sentinel 相关
> 性能调优时。

## 1. 问题

PM 多 Agent 编排的痛点是 **PM 不能事件驱动地被唤醒**：

- `pm-monitor.sh --log-file` 持续写事件日志，**不主动唤起 PM**
- `wait-worker.sh` 退出时 sentinel 还没被发明，是 polling-based
- `DEC-030`（2026-06-05）基于"background bash 不可靠"判断，保守地建议不要用 `run_in_background=true` 等待 worker

但是 2026-06-05 的 3 phase spike 实测验证：**`run_in_background=true` Bash 任务在 exit 时 Claude Code harness 必 re-invoke 父 agent**。Sentinel 模式把这件事工程化。

## 2. 模式

每个 worker 配一个轻量 sentinel bash 进程：

```
PM (foreground)              PM background (run_in_background=true)
   │                                │
   │ Bash: spawn-worker.sh          │ Bash: sentinel.sh
   │  → 创建 worktree               │  → poll STATUS.json
   │  → 启动 tmux worker            │  → 检测到 terminal
   │  → 输出 SPAWN_WORKER_GATE      │  → capture pane
   │  → 输出 SPAWN_WORKER_SENTINEL_CMD
   │                                │  → tmux kill-session
   │                                │  → exit
   │                                │
   │ 读取 gate 结果，决定下一步      │ ⬇ harness task-notification
   │                                │ PM 被 re-invoke
```

PM 端两次调用（foreground spawn + background sentinel），PM 主会话不被阻塞。

## 3. 关键约束与设计选择

### 3.1 Sentinel 是新脚本，不是 `wait-worker.sh` 的 flag

`wait-worker.sh` 的 contract 是"wait and report"（纯函数，可被 pm-monitor.sh 当只读探针用）。Sentinel 的 contract 是"wait and kill"（破坏性）。两者混淆会让 grep 规则和 pm-monitor 解析都混乱。分开维护。

### 3.2 杀 tmux 用 inline `tmux kill-session`，不调 `clean-worktree.sh`

`clean-worktree.sh` 同时处理 worktree 删除 / branch 删除 / force-remove-dirty 等"全量清理"动作。Sentinel 只想释放 worker tmux 资源，**不要**碰 worktree / branch（review 阶段还要看）。

### 3.3 Sentinel 输出到 `SENTINEL_OUT.log`，事件前缀 `SENTINEL_*`

`WAIT_WORKER_*` 事件家族由 `pm-monitor.sh` 当作只读探针事件消费。Sentinel 事件独立命名空间（`SENTINEL_TERMINAL` / `SENTINEL_TMUX_KILLED` / `SENTINEL_TIMEOUT` 等），不污染 `WAIT_WORKER_*` 消费者。

### 3.4 Reuse `redact_sensitive_stream` 内联复制，不抽公共库

`wait-worker.sh:187-203` 的 `redact_sensitive_stream` 函数直接复制进 `sentinel.sh`（line 73-89）。**不**抽成 `lib-redact.sh`：

- 抽公共库需要所有脚本 `source`，引入 cross-script 依赖
- 维护成本（更新 1 处 vs 2 处）大于 15 行代码体积的收益
- 万一 1 处更新漏掉，redact 行为不一致会泄漏密钥

### 3.5 退出码对齐 `wait-worker.sh`

`0` = done，`2` = failed/blocked/stopped，`64` = usage error，`124` = timeout。PM 端可以用同一段处理逻辑。

### 3.6 Sentinel 必须 `run_in_background=true` 启

Foreground 启的 Bash 任务退出时 **harness 不 re-invoke**。这是 sentinel 模式能 work 的关键 — `run_in_background=true` 是 PM 显式 opt-in，告诉 harness："这个任务的 exit 我想收到通知"。

### 3.7 不在 `spawn-worker.sh` 内部启 sentinel

Plan 阶段考虑过把 sentinel 启动合并进 `spawn-worker.sh`。否决的两个原因：

1. **职责分离**：`spawn-worker.sh` 是 PM 用的 fg 工具，sentinel 是 PM 用的 bg 工具。混在一起会让 PM 看不到 gate 验证（如果 `spawn-worker.sh` 本身被 bg 启）。
2. **更稳的 auto mode 兼容性**：Spike 2026-06-05 验证，**单次 foreground Bash 调用 + 一次 explicit `run_in_background=true` 调用**比"单次 Bash 内部 fork 多个 background"更不容易被 auto mode 拒。`spawn-worker.sh` 内部启 sentinel 会让单次 Bash 包含 1 个 fg 子进程 + 1 个 nohup'd background，auto mode 把它当作"多 background"可能拒。

替代方案：让 `spawn-worker.sh` 在 gate 通过后输出 `SPAWN_WORKER_SENTINEL_CMD: ...` 命令，PM 在自己的下一个 Bash 调用里 `run_in_background=true` 启它。**两次 PM 调用** vs "一次但内部 fork"。

## 4. 与 DEC-030 的关系

### 4.1 DEC-030 的判断

DEC-030 说 background bash 不可靠，依据是：

> 多 worker 同时等待时尤其可能没有任何完成消息返回

意思是：如果 PM 启 N 个 background wait，harness 不会保证每条完成消息都送达 PM，事件可能丢。

### 4.2 Sentinel 模式如何不同

| 维度 | DEC-030 假设 | Sentinel 模式实际 |
|------|------------|------------------|
| PM 同时启的 background 数量 | N×N（worker 互相等） | **线性**（= 未完结 worker 数）|
| Background 任务的语义 | "我想知道 worker 状态" | "worker 一进终态就通知我" |
| Exit 事件粒度 | 任意时间点 | 终态原子事件 |
| 失败模式 | 消息丢失，PM 不知道 | graceful 降级到 pm-monitor |

### 4.3 Spike 实测数据（2026-06-05）

3 phases 全部通过，可重放脚本保留在 `/tmp/faropdf-spike-00{1,002,003-*}/`：

| Phase | 场景 | Exit | 唤醒延迟 | Harness 行为 |
|-------|------|------|---------|------------|
| 1 | 单 worker → done → sentinel exit 0 | 0 | 亚秒级 | task-notification 送达 |
| 2a | worker → failed → sentinel exit 0 | 0 | 亚秒级 | 同上 |
| 2b | worker 永远 hang → sentinel 8s timeout | **1** | 亚秒级 | `failed with exit code 1` 通知也送达 |
| 3 | 3 worker 错峰并行 | 0/0/0 | 5 个 notification 同 turn 批处理 | 5/6 调用成功，1 拒 → Sentinel timeout 兜底 |

**关键观察**：

- Harness **不区分 exit code**，0 / 1 / 124 都 re-invoke
- **多次并发 notification 同 turn 批处理**，不会拆成多次唤醒
- 单 background 调用拒率 < 100%（spike 1/6 = 17%），但 graceful 降级是默认行为

### 4.4 DEC-031（新建）的判断

Sentinel 模式是 DEC-030 的"限定条件下的可工作版本"：

- 限定条件：PM 同时启的 background sentinel 数量 = 当前未完结 worker 数（线性而非 N×N）
- 限定条件：每个 sentinel 是单进程、独立 cwd、独立 STATUS.json 路径
- 限定条件：sentinel 失败 = graceful 降级到 pm-monitor，不影响 Wave 整体进度

## 5. 失败降级路径

| 失败 | 检测 | 降级 |
|------|------|------|
| Sentinel 启动被 auto mode 拒 | `SENTINEL_START` 日志 5 秒内未出现 | 用 `pm-monitor.sh --log-file` 替代 |
| Sentinel 进程被 SIGKILL | 没有 exit code，pm-monitor 看不到 status 变化 | 重新启一个 sentinel |
| Sentinel 写错 STATUS_FILE 路径 | 一直 SENTINEL_PENDING / SENTINEL_TIMEOUT | 检查 `spawn-worker.sh --session` 与 `sentinel.sh --tmux-session` 是否一致 |
| Worker 卡死（sentinel timeout 124）| Exit 124 + 工人 tmux 还活着 | tmux 截屏看 pane，纠偏或重启（详见 `templates/pm-sentinel-response.md` §2.3）|

## 6. 调优

### 6.1 轮询间隔

默认 5s，spike 验证 1s 也行。

- 太密（< 2s）：worker 写 STATUS 时 sentinel 大量空转，浪费 CPU
- 太稀（> 30s）：PM 唤醒延迟 + worker 终态到 sentinel exit 的间隔变大
- 推荐：根据 worker 平均 step 长度调整。如果 worker 单次 thinking 5-10 分钟，5s 间隔足够；如果 worker 单次 30s，1s 间隔更即时

### 6.2 最大等待时间

默认 7200s（2h）。

- 配合 `worker-prompt.md` 的 30-60 分钟阶段 commit 习惯：worker 跑超 2h 大概率卡死或偏题，应已被 pm-monitor stale 告警
- 短任务（< 10 分钟）：可设 900s
- 长任务（> 2h）：考虑分 worker，每个 worker 自己的 `--max-wait`

### 6.3 阶段 commit 频率

Sentinel 依赖 `STATUS.json` 终态事件，不依赖 commit。但：

- 阶段 commit 帮助 PM 在 worker done 后快速 review
- `pm-monitor.sh` 的 `WORKER_STALE_NO_COMMIT` 告警和 sentinel 互补

## 7. 相关文件

- `scripts/sentinel.sh`：sentinel 主脚本
- `scripts/spawn-worker.sh`：输出 `SPAWN_WORKER_SENTINEL_CMD` 提示 PM
- `scripts/smoke-sentinel.sh`：端到端 smoke test
- `scripts/lint-wait-script.sh`：把 sentinel.sh 加进默认 lint
- `templates/pm-sentinel-response.md`：PM 收到 notification 后的响应清单
- `references/checkpoint-files.md`：STATUS.json 终态定义
- `DEC-030`：被 supersede 的历史判断
- `DEC-031`：sentinel 模式 DEC（新增）

## 8. 已知不覆盖

- **多 sentinel 对单 worker 去重**：PM 行为层处理（一个 worker 只能启一个 sentinel），sentinel 假设 1:1
- **Codex / OpenCode 路径**：暂未实测 Codex heartbeat automation 集成，按 `templates/codex-heartbeat-wait.md` 单独处理
- **Wave 6 之前**：保留 DEC-030 文本，PM 仍可走 pm-monitor 巡检模式
