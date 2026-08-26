# Autopilot 持久化控制面：跨会话状态、租约、对账与恢复

适用：项目已经按 `references/14-wave-autopilot.md` 跑通 live PM session 内的 Wave Autopilot，且用户要求“PM 会话退出、机器重启或换 Agent 后仍可恢复”“尽量少人工介入”时。本文定义目标控制面和验收，不表示对应 controller/scheduler 已经实现。

当前发布边界：v2.8.1 只提供设计与任务合同。Task-066 完成并通过故障注入前报告 `AUTOPILOT_L2_CONTROLLER_NOT_IMPLEMENTED`；Task-067 完成并通过故障注入前报告 `AUTOPILOT_L3_SCHEDULER_NOT_IMPLEMENTED`。Task-066 交付 L2 后应停止报告前一个标记，但仍保留 L3 标记，直到外部 scheduler 真正交付。

## 1. 为什么 reference 14 不等于持久控制器

reference 14 已解决 live-session 的核心纪律：项目侧授权/策略、三通道监控、Dispatch 完成权威、最终树验收、safe-push/PR/squash、fix-worker 和 fail-closed 泊车。它仍依赖一个活着的 PM 会话理解策略、维护 recurring cron、记住当前 Wave 并执行下一步。

以下机制都不能单独提供跨会话持久性：

- 项目 `TASKS.md`：保存任务意图与状态，不保存当前 PM owner、attempt、Dispatch、PR、retry 时间和唯一 next action；
- session recurring cron：会话关闭或迁移后不再是可靠调度源；
- Orca Run/Task/Dispatch：保存执行事实，不知道项目任务源语义、PR 门禁和写回是否完成；
- provider lease：限制 backend 并发，不阻止两个 PM 同时组同一 Wave；
- Git worktree/branch：保存代码，不知道 worker 是否仍活跃或是否允许重派；
- 消息队列：推送可能丢失，且消息存在与 Dispatch 结算是两条路径。

因此需要一个薄控制面把这些事实对账成幂等状态转换，而不是继续增加自然语言提醒。

## 2. 能力等级与声明边界

| 等级 | 能力 | 最低证据 |
|---|---|---|
| `L0 / MANUAL_WAVE` | 每波由用户/PM 手动发车 | 项目任务源与单波验收 |
| `L1 / LIVE_SESSION_AUTOPILOT` | 活跃 PM 会话内自动链式推进；session cron 补偿推送丢失 | reference 14 三通道 + 完整 Wave |
| `L2 / CROSS_SESSION_RECOVERABLE` | 新 PM 能接管旧 Wave，不重复 mutation | runtime ledger + PM lease/fencing + reconcile 故障注入 |
| `L3 / UNATTENDED_DURABLE` | 无活跃聊天会话时，外部 scheduler 可定时唤醒、恢复和 soft park/resume | L2 + durable scheduler + provider/reset/重启演练 |

禁止从 `L1` 文档、一次 cron 触发或 happy-path Wave 推导 `L2/L3`。

## 3. 事实源分层

### 3.1 项目策略层（Git 跟踪）

项目继续负责：

- 用户授权范围、撤销方式与泊车条件；
- 当前任务源、READY/DRAFT/依赖与泳道；
- 每波最大并发、允许 backend/profile 与安全规则；
- 项目测试门禁、PR/merge/写回规则；
- 重要取舍与重新评估条件。

通用 Skill 不复制项目授权，也不从 Roadmap 自由发明任务。

### 3.2 运行状态层（Git common dir）

推荐可信根：

```text
$(git rev-parse --git-common-dir)/orchestration/autopilot/
├── state.json
├── events.jsonl
├── lease.json
└── lock
```

理由：同仓所有 worktree 可见、不会进入 PR、能复用现有 provider lease 的路径/锁/原子写入安全惯例。普通项目文件、Session Context 与 worker worktree 都不是合适的单一 runtime root。

运行态不得保存：Token、完整环境变量、settings 内容、用户媒体路径、案件/客户敏感信息、完整 transcript 或模型输出正文。

### 3.3 外部事实层

- Orca：Run、Task、Dispatch、worker/resource state；
- Git：worktree、branch、fork point、commit、dirty state；
- GitHub：PR、checks、review、mergedAt；
- scheduler：last tick、next tick、job identity；
- project task source：任务状态与允许的下一组合。

controller 只做对账和受限 mutation，不把外部事实复制成另一个不可校验的真相。

## 4. 最小 runtime schema

```json
{
  "schema_version": 1,
  "project_id": "<stable-repo-id>",
  "policy_commit": "<git-oid>",
  "wave_id": "wave-<n>",
  "run_id": "run_<id>",
  "state": "RUNNING",
  "pm_owner": "<stable-owner-id>",
  "fencing_token": 7,
  "lease_expires_at": "<rfc3339>",
  "last_tick_at": "<rfc3339>",
  "last_event_id": "<monotonic-id>",
  "items": [
    {
      "task_id": "<project-task-id>",
      "attempt": 1,
      "branch": "<branch>",
      "worktree": "<resolved-path>",
      "dispatch_id": "ctx_<id>",
      "provider": "<backend/profile>",
      "pr_number": null,
      "last_heartbeat_at": "<rfc3339>",
      "retry_at": null,
      "next_action": "inspect_dispatch"
    }
  ],
  "parking_code": null,
  "parking_detail": null
}
```

要求：

- schema 版本化，未知未来版本 fail-closed；
- JSON 通过临时文件 + fsync + atomic rename 写入；事件追加带单调 id；
- 所有路径 resolve 后校验属于预期 repo/worktree root；
- `policy_commit` 变化时先 reconcile，不沿用旧策略静默 spawn；
- 每个外部 mutation 写入 attempt、before/after fact 与 fencing token，便于重放和去重。

## 5. PM lease 与 fencing

PM lease 与 provider lease 是两个维度：

| Lease | 限制对象 | 保护的 mutation |
|---|---|---|
| provider lease | backend/profile 并发槽 | worker 资源创建与配额 |
| PM lease | 单项目 Autopilot owner | 组波、spawn、push、merge、writeback、park/resume |

规则：

1. lease 获取/续期在同一 lock 下原子执行；
2. 每次新 owner 接管递增 `fencing_token`；
3. 所有 mutation 在执行前和提交后都核对 token；旧 owner 即使恢复也只能只读；
4. lease 过期不等于旧 mutation 安全，接管者先 reconcile 外部事实；
5. owner 身份必须稳定可审计，不能只用会变化的 pane title 或自然语言 Agent 名；
6. 无法确认现 owner liveness 时，默认拒绝强抢；显式 force takeover 必须带 reason 并保留事件。

## 6. 幂等状态机

```text
IDLE → PLANNING → DISPATCHING → RUNNING → VERIFYING
     → MERGING → WRITEBACK → COMPLETE → IDLE

任一活动态 → WAITING_PROVIDER_RESET → 原活动态
任一活动态 → PARKED_SOFT → 条件/时间满足后恢复
任一活动态 → PARKED_HARD → 用户/维护者显式恢复
任一活动态 → ERROR_RECONCILE_REQUIRED
```

每个 `tick` 最多执行一个外部 mutation；mutation 后重新读取事实。不得用“已经发过命令”代替“外部事实已经收敛”。

典型去重键：

- spawn：`project_id + wave_id + task_id + attempt`；
- push：immutable local OID + remote branch；
- PR：head branch + base branch；
- merge：PR number + mergedAt/mergeCommit；
- writeback：task id + merge commit + policy commit；
- park/resume：state transition id。

## 7. reconcile 固定顺序

启动、新会话接管、定时 tick 与异常恢复统一执行：

1. 读取并验证项目策略、runtime schema 与 repo identity；
2. 获取/续期 PM lease，确认 fencing token；
3. 枚举 Orca active Run/Task/Dispatch 与 resource；
4. 枚举 Git worktree/branch/dirty/commit 和 GitHub open/merged PR/checks；
5. 对照项目任务源与已完成索引；
6. 对每个 item 输出唯一 action；
7. 若存在冲突/unknown，进入 `ERROR_RECONCILE_REQUIRED` 或 park，不做清理；
8. 否则只执行一个 action，记录 event，再从步骤 1 重读。

允许的 action 词汇至少包括：

```text
adopt | observe | settle | verify | push | open_pr | merge |
writeback | retry_later | reject_duplicate | soft_park | hard_park | complete
```

## 8. durable scheduler 与 session cron

- session recurring cron：低延迟 fast path，负责当前活跃 PM 的 10—20 分钟巡检；泊车/完成时自删；
- external durable scheduler：`L3` 权威唤醒源，独立于聊天会话，按 project id 调用 `reconcile/tick`；
- 两者可以同时触发，因为 PM lease/fencing 与幂等 tick 必须消除重复副作用；
- scheduler 只负责唤醒，不绕过项目授权、不自己解释 Task 标题、不直接 merge；
- 创建、更新、暂停、删除和通知策略必须有宿主正式 API/CLI 合同，不能把一段 raw cron 字符串当成集成完成。

若宿主只能唤醒会话、不能无会话启动任务，则最高只能声明 `L2`，不得包装成 `L3`。

## 9. Provider 限流与 soft park

429/额度重置使用显式状态：

- 记录受影响 provider/profile、attempt、观测时间、可靠的 `retry_at` 来源；
- 若项目策略允许且文件所有权/任务合同不变，可切换合法 fallback；
- 所有允许 provider 都不可用时进入 `WAITING_PROVIDER_RESET` 或 `PARKED_SOFT`，不反复 spawn 消耗资源；
- 到期恢复前重新读取 provider/resource/Dispatch 状态，不能假设旧 turn 已终止；
- 无可靠 reset 时间时 hard park 或请求用户，不编造时间；
- 成本上限、外部发送授权或 Provider Key 缺失始终是项目权限门，不因 Autopilot 扩张。

## 10. shared context 单写者

共享任务源/决策/项目规则是全局资源。推荐合同：

1. worker 只拥有任务专属代码、合同、研究和测试；
2. worker 在 Delivery/PR 描述中输出结构化 writeback proposal：目标 task、建议状态、证据、决策候选、未验证项；
3. PM 独立验收后，在同一 worker branch 追加单独 writeback commit，或开串行 docs-only PR；
4. 同一项目同时最多一个 shared-context writer；
5. DEC/Task 编号预分配仍保留，但只解决标识分配，不再被当成并发写授权；
6. reconcile 检查“PR 已合并但 writeback 未发生”和“writeback 先于合并/证据”两类漂移。

项目若明确允许某个 contract worker 直接写 shared context，必须把它当作该 Wave 唯一 shared-context writer，而不是与其他合同 worker 并行。

## 11. 故障分类

| 类别 | 默认处置 |
|---|---|
| 推送/消息丢失 | 主动查 Dispatch；不重派 |
| PM lease 冲突 | 非 owner 只读；报告 owner/token/expiry |
| worker dead + Dispatch 未结算 | 走正式 settle，保留审计；不自动删脏 worktree |
| PR merged + writeback missing | 生成一次幂等 writeback |
| task source complete + PR 未合并 | `ERROR_RECONCILE_REQUIRED`，人工判定 |
| branch/worktree 重复 | 通过去重键 adopt 或拒绝；不创建 `-2` 猜测 worktree |
| checks unknown/failed | fail-closed；不 merge |
| 全 provider 429 | soft park/retry_at；无可靠时间则 hard park |
| policy commit 变化 | 停止 mutation，重新规划/对账 |
| runtime 损坏或未来 schema | 只读导出证据，hard park；不自动重建覆盖 |

## 12. 验收演练

Task-066/067 不能只以 unit test 或一次 happy path 关闭，至少运行：

1. RUNNING 中 kill PM，新 PM 接管旧 Dispatch，无重复 spawn；
2. 两个 PM 同时 acquire，只有一个可 mutation；旧 fencing token 被拒绝；
3. 丢弃所有 worker_done 唤醒，scheduler 在一个周期内发现 completed；
4. 全 provider 429，写 `retry_at`、soft park、到期只恢复未完成 item；
5. PR 已 merged、writeback 未做，reconcile 只补一次；
6. shared-context writer 冲突在 spawn/commit 前被拒绝；
7. 脏 worktree、unknown checks、无法解析 runtime 均 fail-closed 且不删除；
8. 新 clone/换机安装固定 Skill 版本，项目策略一致，本机绝对 symlink 不参与正确性。

验收记录必须包含 runtime before/after、fencing token、外部事实快照、执行 action 与无重复副作用证明。

## 13. 实施任务

本次审计落盘期间，另一轮 badminton-lab Wave 7 复盘已先登记三个 live-session DRAFT；为避免编号覆盖，本持久化整改从 Task-066 起排号。三个既有方向与本文的关系如下，公开记录其边界，避免它们只存在于 ignored-only 本地任务源：

| 既有 Task | 方向 | 与持久控制面的关系 |
|---|---|---|
| `Task-063` | 判活信号分级：transcript 时间戳高于文件/commit 变化和静态 provider 横幅 | 提供 live-session observation 语义；Task-066 的 reconcile 复用，不重复定义 |
| `Task-064` | 额度窗口 playbook、idle 注入与当前会话 one-shot 再唤醒 | 提供 429 当前会话处置；Task-067 把 `retry_at`/resume 提升为跨会话持久状态 |
| `Task-065` | shared-doc 冲突的程序化提取/拼装与断言 | 仅作为历史并发写回的恢复工具候选；本文默认仍是 PM 单写者，工具不得反向授权并发写 shared context |

### Task-066 — 持久 runtime core（READY）

实现 runtime schema、原子 ledger/event log、PM lease/fencing、只读 `status`、幂等 `reconcile/tick` 与故障测试。范围只到 `L2`；不创建外部 scheduler，不自由解释项目 Roadmap，不自动删除资源。

### Task-067 — durable scheduler 与 soft park（DRAFT）

依赖 Task-066、Task-064 的 live-session 额度窗口/再唤醒结论和至少一个宿主正式调度合同。实现外部定时唤醒、job identity、暂停/删除、通知、provider `retry_at`/fallback/soft park/resume；宿主无法无会话执行时必须降级声明 L2。Task-064 解决当前会话内的判活与 one-shot 再唤醒，Task-067 只负责把它提升为可跨会话恢复的持久状态，不重复实现同一 playbook。

### Task-068 — 跨会话协议收敛与可移植性回归（DRAFT）

等待 Task-063 的 live-session 判活信号分级与 Task-065 的 shared-doc 冲突工具边界固定后，把 cron 模板与 supervised Dispatch-first 完成权威对齐；增加静态 lint 防 `STATUS/Sentinel` 冒充结算、防“session-only 即 durable”声明；验证 Skill 固定版本可在新 clone/新 worktree 被发现，公开 reference 不依赖 ignored-only 决策或本机绝对链接。Task-065 若继续实现，只能作为历史并发写回的恢复/拼装工具，不能放宽本文的 PM 单写者默认。
