# Wave Autopilot：用户授权的波次自动推进

适用：用户显式授权后，PM 在固定策略内自动执行「组波 → 派单 → 监控 → 验收 → 合并 → 写回 → 组下一波」，链式推进直到泊车条件。badminton-lab Wave 4—5（2026-08-26，PR #21—#25）为首次完整落地的两波 + 泊车实战，本参考全部内容与该实战一一对应。

## 1. 授权合同（先决条件）

- 必须有用户**显式授权**，并记录在**项目上下文**（项目 AGENTS.md/CLAUDE.md 一节 + 指向项目任务源的策略章节）；本 skill 不承载任何项目授权。
- 授权至少固定：授权范围（哪些任务类型可自动派）、泊车条件、撤销方式（用户一句话）、回退条件（发生一次泊车外失误即回退逐波确认）。
- **策略权威 = 项目任务源**（如 docs/TASKS.md 的策略节）：组波规则、泳道、晋级门禁、泊车清单全部落在项目文档里，PM 查表执行、不做自由判断。查表查不到合法组合本身就是泊车条件——这是 Autopilot 能 fail-closed 的根本。

## 2. 生命周期与不变量

```text
组波（查表）→ spawn（receipt + verify-cmd 白名单 + --python-runtime-symlink）
  → 监控（三通道，见 §3）→ worker_done / Dispatch 状态确认
  → PM 独立验收（diff 范围对 fork point + 身份 + 门禁在最终树复跑）
  → safe-push → PR → squash merge → 资源清理（lease/worktree/分支，MERGED 证据）
  → 任务源写回 → 查表组下一波 or 泊车（完整报告后停止）
```

不变量：

1. **验收路径不因自动化放宽**：门禁复跑（sync-merge 后最终树为准，G37）→ safe-push 全 range 身份核验 → PR → squash merge 强制；禁止直推 main，禁止以 worker 自报代替复跑。
2. **透明不阻断**：每波收口向用户发波次摘要（交付/PR/验证证据/下一波构成），不要求确认；泊车必须完整报告并停止，不静默重试。
3. **泊车 fail-closed**：任务开工需用户资产/环境/授权、PM 复跑门禁失败且纠偏路径用尽、同一 worker 连续两次不达标、合并冲突超出项目已固定冲突模式、队列无合法可派组合、用户显式喊停。

## 3. 监控可靠性：三通道并用（实战核心教训）

单一推送通道会丢。Autopilot 活跃期间必须同时具备三条通道：

1. **Orca 推送唤醒**（主通道）：快，但**不可靠**——实测 worker_done 消息在队列里存在、对应系统唤醒从未送达，PM 停摆 6.6 小时直到用户人工戳。
2. **recurring cron 看门狗**（强制）：session 级 recurring cron（建议 `4-59/20 * * * *` 这类避开整点/半点的间隔），每跳执行 §4 清单；泊车时 CronDelete 自删；7 天自动过期是天然兜底。session-only 即可（Autopilot 本就活在 PM 会话里，任务源是持久状态）。
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

## 5. 组波查表规则（模板；具体值落项目策略节）

只派 `READY`；`DRAFT` 先派「晋级合同」任务（docs-only：合同文档 + 决策记录 + 任务源晋级写回），晋级后进后续波次实现。泳道互斥、同泳道串行（上一任务合并进 origin/main 后才派下一个）。每波 ≤N worker（默认 3），文件所有权必须正交。并行任务共写共享文档（决策记录/任务源/CHANGELOG）时**编号预分配**防撞号。review/收口发现的缺口先登记新卡再入波。实现本身被用户输入卡住的任务（需真实样本/环境/授权）不烧晋级合同，直接泊车。

## 6. 验收期确定性缺陷的处置（实战模式）

PM 复跑门禁**确定性失败**（≥2 次同点，先排除 flake）→ 不放宽门禁、PM 不改业务代码：

1. 诊断收窄：失败断言点、假设列表（按序验证）、允许所有权边界，写成精确 fix spec。
2. 原 dispatch 已结算不复活：把失败分支 safe-push 到远端（身份门禁核验；**门禁失败不阻断 feature 分支推送**），新 fix worker 用**新分支名 + `--base-ref origin/<原分支>`** 派发。
   - 禁止同分支名重新 spawn：Orca 会因 worktree 名撞车建 `<branch>-2` 空 worktree，spawn 的 branch gate 直接 GATE_FAILED；误火用 `settle --force` + `clean-worktree --execute` 清理。
3. fix 交付按确定性复验：目标门禁**连续 3 次**通过 + 全量门禁，随主交付同一 PR 合并，PR 描述写明缺陷根因与修复归属。

## 7. 反模式清单（全部实测踩坑）

- 只依赖 Orca 推送唤醒、不挂 recurring 看门狗 → 6.6h 停摆。
- 用 `No messages` 判定 worker 未完成 → Delivery 可能不进队列，完成权威在 Dispatch 状态。
- PM 终端跨 run 不 `run-use` 重绑就 `check` → binding 报错，误判无消息。
- 修复任务复用同分支名 spawn → `-2` 空 worktree + GATE_FAILED。
- spawn 后手动补 `.runtime` 软链 → 与 worker 启动竞态，escalation 阻塞；spawn 时传 `--python-runtime-symlink`。
- 验收 diff 对着当前 origin/main 而非 fork point → stale-base 假删除（G37）。
- 收口清理遇 "external terminal close failed" 直接跳过 → 重试 clean-worktree（terminal 状态常在首次尝试后收敛）。
- 把 Autopilot 策略写进 skill 或 PM 记忆而非项目任务源 → 授权与策略不可审计、换会话即漂移。
