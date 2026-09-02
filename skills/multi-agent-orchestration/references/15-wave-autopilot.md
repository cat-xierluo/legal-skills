# Wave Autopilot：用户授权的波次自动推进

适用：用户显式授权后，PM 在固定策略内自动执行「组波 → 派单 → 监控 → 验收 → 合并 → 写回 → 组下一波」，链式推进直到泊车条件。badminton-lab Wave 4—5（2026-08-26，PR #21—#25）为首次完整落地的两波 + 泊车实战，§1—§7 与该实战一一对应；§8 是后续 Wave 6—7 持久化审计补充的能力边界。

## 1. 授权合同（先决条件）

- 必须有用户**显式授权**，并记录在**项目上下文**（项目 AGENTS.md/CLAUDE.md 一节 + 指向项目任务源的策略章节）；本 skill 不承载任何项目授权。
- 授权至少固定：授权范围（哪些任务类型可自动派）、泊车条件、撤销方式（用户一句话）、回退条件（发生一次泊车外失误即回退逐波确认）。
- **策略权威 = 项目任务源**（如 docs/TASKS.md 的策略节）：组波规则、泳道、晋级门禁、泊车清单全部落在项目文档里，PM 查表执行、不做自由判断。查表查不到合法组合本身就是泊车条件——这是 Autopilot 能 fail-closed 的根本。

## 2. 生命周期与不变量

```text
组波（查表）→ spawn（receipt + verify-cmd 白名单 + --python-runtime-symlink）
  → 监控（三通道，见 §3）→ worker_done / Dispatch 状态确认
  → PM 独立验收（diff 范围对 fork point + 身份 + 门禁在最终树复跑）
  → safe-push → 唯一 PR → 本地集成候选 → 本地推入或 GitHub merge
  → 资源清理（lease/worktree/分支，远端结果证据）
  → 任务源写回 → 查表组下一波 or 泊车（完整报告后停止）
```

不变量：

1. **验收路径不因自动化放宽**：门禁复跑（sync-merge 后最终树为准，G37）→ safe-push 全 range 身份核验 → 唯一 PR → 冻结精确 head/diff/checks → 最新 main 本地候选复验。只有用户/项目已授权且 main 无保护阻断时，才按 `git-workflow` 本地集成并安全推入 main；否则由 GitHub PR squash/merge。禁止绕过 PR 直推 main，禁止以 worker 自报代替复跑。
2. **透明不阻断**：每波收口向用户发波次摘要（交付/PR/验证证据/下一波构成），不要求确认；泊车必须完整报告并停止，不静默重试。
3. **泊车 fail-closed**：任务开工需用户资产/环境/授权、PM 复跑门禁失败且纠偏路径用尽、同一 worker 连续两次不达标、合并冲突超出项目已固定冲突模式、队列无合法可派组合、用户显式喊停。

## 3. 监控可靠性：三通道并用（实战核心教训）

单一推送通道会丢。Autopilot 活跃期间必须同时具备三条通道：

1. **Orca 推送唤醒**（主通道）：快，但**不可靠**——实测 worker_done 消息在队列里存在、对应系统唤醒从未送达，PM 停摆 6.6 小时直到用户人工戳。
2. **recurring cron 看门狗**（强制）：session 级 recurring cron（建议 `4-59/20 * * * *` 这类避开整点/半点的间隔），每跳执行 §4 清单；泊车时删除自身。它是 live PM session 的低延迟 fast path，**不是跨会话持久性证明**；任务源保存策略/意图，不保存当前 Wave 的完整运行态。跨会话接管或无人值守要求读取 `references/16-autopilot-durability.md`。
3. **Dispatch 状态轮询是完成权威**：`worker_done` 的 Delivery 可能不进 PM 待查队列（消息路由与 Dispatch 结算是两条路径）；`pm-orchestrate show` 的 `dispatch.status=completed` + `worker.state=succeeded/settled` 是可查证的完成事实。**队列无消息 ≠ 未完成；状态停滞 ≠ 完成**——两边都要主动查。

## 4. 看门狗每跳清单

1. `orca orchestration check --run <活跃run>`：有 pending worker_done/escalation → 立即走收口/处置。
   - 报 `This coordinator terminal is bound to run_X` 时：先 `orca orchestration run-use --id <run> --from <PM terminal handle>` 重绑——fix 派发等新建 run 后 PM 终端绑定会漂移。
2. 逐活跃 worker 执行 `pm-orchestrate show --worktree WT --session S`：`completed/succeeded/settled` → 走验收（**即使 check 队列为空**）。
3. 判活：`pm-orchestrate peek` 返回的 transcript `timestamp`（epoch ms）与当前差值 > 30 分钟且非已知长任务 → 处置矩阵：
   - TUI idle（worker ready）且工作未完 → 按 G39 键盘注入唤醒：`orca terminal send --terminal <handle> --text "..." --enter`（supervised 的 `pm-orchestrate send` 走 Dispatch inbox，idle worker 不拉取，`ok:true` ≠ 被消费）；
   - 429 限流重试循环（同账号多 worker **同时**触发）→ 记录并等重置点，CLI 会自动恢复；turn 被打断停 idle 才需要注入；
   - 进程死且 dispatch 卡 `dispatched` → `pm-orchestrate settle`（身份/审计/liveness 门禁见 SKILL §4.5）。
4. 全部 wave 收口 + 队列查表无可派 → CronDelete 看门狗 → 发泊车报告。

### 4.1 守夜 v2：脱链、核活与恢复分流

已知恢复时间时使用 `scripts/night-revive-timer.sh`，按 `--pm-terminal/--workers-file/--revive-at/--wake-at/--revive-text/--wake-text/--log` 提供完整输入；打摆 lane 用 `--repeat <秒> --until <时刻>`。进程必须由 `nohup caffeinate -dis` 脱离 Orca/Electron 进程树，恢复时间变化时重启模板，不现场手写另一份脚本。

布防和巡检遵守四条铁律：

1. **先做双通道自测**：立即向 PM 自身 terminal 注入一行探针，并向任一 worker terminal 注入一行探针；两条都确认送达才算布防完成。
2. **核活必须双读**：单次快照、`worker=ready` 或空 transcript 都不可信。先间隔 30—40 秒双读计时器；超过 1 小时导致分钟粒度失效时，改用两次 `latest cursor` 的推进作为最终运行时活性证据。活性不等于业务进展，仍需 diff/commit/tests。
3. **先区分硬额度与瞬发拥塞再复活**：PM 自身可用、任一 worker 能维持长 turn、复活探针被消费且有增量进展，表示边际可用；冻死 worker ≤3 个/批、间隔 8 秒错峰复活并周期重试。只有单请求也稳定 429 才等刷新点统一恢复。
4. **完成权威先查 task-list**：每跳第一项运行 `orca orchestration task-list --run <run> --json`；队列空不等于 worker 未完成。并核对每个 spawn receipt 的 `SPAWN_WORKER_DISPATCH_BIND`，出现 `manual-required` 立即按 `references/14-pm-orchestrate.md` §1.1 恢复路由，不等到 worker_done 缺失才处理。

## 5. 组波查表规则（模板；具体值落项目策略节）

只派 `READY`；`DRAFT` 默认不可派，也不自动生成“晋级合同”。只有命名实现已经具备全部非文档输入、且缺少的合同是唯一阻塞时，PM 才能新建一次合同任务。实现仍被用户资产、环境、授权或真实样本卡住时直接泊车。

每个候选先通过消费者合同：

| 字段 | 必须回答 |
|---|---|
| `consumer` | 哪个实现、用户决策、发布门禁或验收流程会消费 |
| `decision_or_gate_changed` | 产出会改变哪个状态/判定，而非只“形成材料” |
| `consume_by` | 预计在哪一到两个波次内消费 |
| `expiry` | 到期未消费时归档、重评或删除哪个派生资产 |
| `observable_acceptance` | 真实 diff、测试、fixture、基准、交互或状态迁移 |
| `resource_owner` | 服务、端口和子进程的 owner/cleanup；没有则为 `none` |

说不出任一字段不派。docs-only 必须至少带来 `DRAFT → READY`、关闭阻塞决策或新增被消费者实际调用的门禁；纯摘要、手写镜像索引和没有入站引用的预扫不成为独立 PR。派生地图能由工具生成则优先生成，无法生成且没有稳定刷新触发器则不维护。

文本审查之后必须再过机器门禁：按 `templates/dispatch-value-gate.example.json` 生成本波 JSON，运行 `python3 scripts/dispatch-value-gate.py <spec.json>`。退出非零时不得以人工“高价值”判断绕过；若项目确需更宽阈值，先用显式、带到期时间的 explore 窗口表达，而不是改弱 converge 默认值。

默认每波/全局活跃 worker ≤3，research/docs ≤1。PM 待验收 PR >2 时停止新派；项目的用户/真实环境 `AWAITING_ACCEPTANCE` 积压显著时，只派能降低验收成本、修复验收缺陷或补真实证据的工作。只有用户显式开启且限定期限的探索窗口、验收积压为零时，项目才可临时提高并发；窗口结束自动回收敛模式。

泳道互斥、同泳道串行；文件范围正交、验收独立、共享合同冻结才并行。相同根因/模块、共同验收的 2—3 个小项优先一个 worker + 一个 PR，详细粒度读取 `references/12-issue-grouping.md`。`TASKS/DECISIONS/AGENTS/ROADMAP` 等 shared context 默认只有一个 PM writer；编号预分配只分配标识，不授权并发写共享文档。

额度是资源而不是目标。余量充足时可加深确定性测试、fixture、基准、故障注入、验收工具、生成器和独立前向评测，但不得现场发明 quota-burn 任务。每波报告 `consumer_fulfilled / state_transition / acceptance_debt_delta / leaked_process_delta`；到期仍无消费者的研究产物进入归档候选，不继续派生下一层文档。

收口还必须核对 `resource_owner`：本波启动的服务/监听端口/子进程相对启动前基线零净增量。出现无主进程、身份不明端口或共享真值冲突时停止组下一波；只读盘点后按精确身份处理，禁止按进程名批量 kill。

## 6. 验收期确定性缺陷的处置（实战模式）

**先分类再处置（v2.14.0）**：任何验收失败先过 `scripts/acceptance-recovery.py` 的单一机械分类（`classify` 子命令或 module API），不得按「任何门禁失败 => park」直接泊车：

- `internal_recoverable`（PR checks 确定性失败、交付越界、验证证据缺失、review blockers、docs-only 验收修复）：修复预算内动作必须是 `repair`（首次）或 `re_review`（之后），默认预算 **2 次**，耗尽才泊车。预算按「失败 episode」计数，修复在途的重复 reconcile 不重复计数。autopilot runtime 据此规划 `repair_acceptance`（不泊车，state 保持 RUNNING），heartbeat 适配器输出 `decision=review` 且心跳继续。
- `external_dependency`（配额耗尽、上游不可用、缺用户资产/授权）与 `safety_unknown`（事实歧义、身份/head 漂移不可证、安全高风险、runtime 损坏；表外信号一律归此类）：立即泊车，等人工。

PM 复跑门禁**确定性失败**（≥2 次同点，先排除 flake，分类为 internal_recoverable）→ 不放宽门禁、PM 不改业务代码：

1. 诊断收窄：失败断言点、假设列表（按序验证）、允许所有权边界，写成精确 fix spec。
2. 原 dispatch 已结算不复活：把失败分支 safe-push 到远端（身份门禁核验；**门禁失败不阻断 feature 分支推送**），新 fix worker 用**新分支名 + `--base-ref origin/<原分支>`** 派发。
   - 禁止同分支名重新 spawn：Orca 会因 worktree 名撞车建 `<branch>-2` 空 worktree，spawn 的 branch gate 直接 GATE_FAILED；误火用 `settle --force` + `clean-worktree --execute` 清理。
3. fix 交付按确定性复验：目标门禁**连续 3 次**通过 + 全量门禁，随主交付同一 PR 合并，PR 描述写明缺陷根因与修复归属。

**docs-only 验收修复的极窄通道（`acceptance-repair.v1`）**：既有具名 PR 的验收只差文档修复（review blockers、缺失随行文档）时，唯一合法派发形态是 `templates/acceptance-repair.example.json` 合同 + `scripts/acceptance-repair-gate.py preflight/postflight` 双门禁。合同钉扎既有 PR/branch/40-hex head、结构化 blocker IDs、纯文档 file_scope、具名消费者、到期条件、验证命令、序列化 owner（registry 台账：同 PR 单活跃 owner，同 head 或活跃 blocker 重叠 = 重复修复拒绝）与独立 re-review 身份；只能集成回既有 PR 分支，不存在独立文档 PR 的表达字段；`repair_attempts_used` 耗尽（≥2）拒绝派发，按分类合同泊车。postflight 机械拒绝 head 漂移（patch 模式无法证明谱系，一律拒绝）、范围外/非文档修改、零 diff、未解决 blocker。除本通道外，docs-only 仍一律不可派。

## 6.1 Reviewer dispatch 的写范围

验收/review worker 一律 `spawn-worker.sh --role reviewer`：默认可写范围只有自身 Session Context；修复被审分支必须任务合同显式 `--review-repair-grant <授权来源>`，无授权却传 `--allow-paths` 在任何副作用前 fail-closed。`config/*.local.yaml`（安装 Skill 的本地运行配置）对 reviewer 永远不可写，授权也不例外。角色与授权写入 METADATA `runtime.role` 供收口审计。

## 7. 反模式清单（全部实测踩坑）

- 只依赖 Orca 推送唤醒、不挂 recurring 看门狗 → 6.6h 停摆。
- 用 `No messages` 判定 worker 未完成 → Delivery 可能不进队列，完成权威在 Dispatch 状态。
- PM 终端跨 run 不 `run-use` 重绑就 `check` → binding 报错，误判无消息。
- 修复任务复用同分支名 spawn → `-2` 空 worktree + GATE_FAILED。
- spawn 后手动补 `.runtime` 软链 → 与 worker 启动竞态，escalation 阻塞；spawn 时传 `--python-runtime-symlink`。
- 验收 diff 对着当前 origin/main 而非 fork point → stale-base 假删除（G37）。
- 收口清理遇 "external terminal close failed" 直接跳过 → 重试 clean-worktree（terminal 状态常在首次尝试后收敛）。
- 把 Autopilot 策略写进 skill 或 PM 记忆而非项目任务源 → 授权与策略不可审计、换会话即漂移。
- 把“额度充足”解释成扩大任务源、为 DRAFT 批量写预扫或维持 worker 忙碌 → token 变成验收债务而非资产。
- docs-only 没有状态迁移、命名消费者或过期条件仍开独立 PR → 文档继续派生文档。
- worker 测试启动服务后只清 worktree，不核对 PID/端口净增量 → 无主服务跨波累积，浏览器还可能误连旧分支。
- 把任何门禁失败直接泊车（未过 `acceptance-recovery` 分类）→ 内部可恢复失败被错误泊车、波次无谓中断（v2.14.0 前的真实缺陷）；反过来把 external_dependency/safety_unknown 当可修复继续烧预算 → 同样违规，两类都必须立即泊车。
- docs-only 验收修复绕过 `acceptance-repair-gate` 双门禁、或把该通道当通用 docs-only 后门 → 文档派生文档回潮；通道只服务「既有 PR + 钉扎 head + 结构化 blockers + 序列化 owner」这一种形态。

## 8. 当前能力边界与升级路径

本文覆盖 `L1 / LIVE_SESSION_AUTOPILOT`：活跃 PM 会话内自动链式推进，session cron 补偿推送丢失。以下任一要求出现时，本文清单不够，必须进入持久控制面：

- PM 会话退出/迁移后由新 PM 确定性接管；
- 两个 PM 并发启动时防重复组波与 mutation；
- 没有活跃聊天会话时仍由外部 scheduler 唤醒；
- 429/额度重置后按 `retry_at` 自动 soft park/resume；
- PR、Dispatch、worktree 与任务源漂移后自动对账写回。

目标 runtime schema、PM lease/fencing、幂等 reconcile、shared-context 单写者和故障注入门禁见 `references/16-autopilot-durability.md`。Task-066 已交付 `L2 / CROSS_SESSION_RECOVERABLE` controller core，但真实 Orca/GitHub mutation adapter 与真实断电仍为 `NOT_VERIFIED`；Task-067 完成前继续标记 `AUTOPILOT_L3_SCHEDULER_NOT_IMPLEMENTED`。不得把 session cron、Markdown 任务源或 provider lease 单独描述成持久控制器。
