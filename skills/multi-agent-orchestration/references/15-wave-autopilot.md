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
3. 分两维观察，不把任何单一信号写成假死权威：
   - **运行时活性**：supervised 优先 `worker-read --source auto`，terminal-managed 使用 terminal cursor/`lastOutputAt`。cursor 前进只证明 PTY 有输出；cursor、CPU 或时间戳静止都不能单独证明冻结。来源改变、历史截断、PID 身份不可证明、quiet 测试、网络等待或 ask/dialog 时记为 `unknown`。
   - **业务进展**：检查真实 diff、文件/提交、测试产物和结构化阶段；spinner、heartbeat、idle 和持续输出都不能替代业务证据。
   - 确认 TUI 已回到 idle 且工作未完时，PM 才显式键盘注入一次短唤醒：`orca terminal send --terminal <handle> --text "..." --enter`；注入后复读 screen 和 Dispatch 状态。探测器不得自动 Esc/Ctrl+C/stop/release。
   - 进程已知死亡且 dispatch 卡 `dispatched` 时，才按 SKILL §4.5 的身份、审计和 liveness 门禁执行 `pm-orchestrate settle`。
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

## 8. 守夜模式（额度耗尽过夜，Task-064）

适用：已经出现明确额度受限证据，且预计同一 provider/account/model 的额度窗口会自动恢复。不要在“将要耗尽”、首次探测可用、配置错误或网络异常时启动守夜；一次成功探测可能产生实际用量，不能宣称整个探测过程零消耗。

### 8.1 先区分 429 后的三种状态

| 观察 | 处置 |
|---|---|
| turn 内仍在重试，TUI 未回输入态 | 记录额度状态并等待；不得叠加键盘注入 |
| 429 打断 turn，TUI 已 idle，工作未完成 | 等额度恢复后显式注入一次短续作指令，并复读 Dispatch/screen |
| provider 横幅或配置已改变，但原 turn 没有恢复 | 不把横幅变化当恢复证据；用同一 provider identity 的有界探针确认，成功后再注入 |

### 8.2 命令与状态机

先从 wave receipt/METADATA 取得 PM/coordinator handle，再用 `orca terminal show --terminal <handle> --json` 核对返回的是同一可写 handle；单凭 show 不能证明它承担 PM 角色。模型与 provider/account settings 权威文件必须显式给出；自动唤醒路径拒绝非空 setting-sources，脚本不会替调用方猜 provider registry：

```bash
bash scripts/night-watch.sh \
  --terminal "$PM_TERMINAL" \
  --model "$MODEL" \
  --settings "$CLAUDE_SETTINGS" \
  --interval-minutes 15 \
  --max-hours 12
```

`night-watch.sh` 调用 `pm-quota-stall.sh` 做一次有界分类。只有同一 watcher 先收到明确 `quota`，随后收到 `available`，才执行一次 `orca terminal send`。首次即 available 返回 11 并停止；config/auth/network/timeout/unknown、terminal show/send 失败全部非零退出且不唤醒。show 回执必须返回相同 handle 且 `connected/writable=true`；settings 内容 SHA-256 在守夜启动时冻结，探针前和唤醒前漂移均失败关闭。探针禁用 tools、slash commands、MCP、session persistence 和 Chrome，但仍会向目标 provider 发一个最小请求。

达到最长时长只写私有 state-dir 日志并返回 2，不自动向 PM 终端注入“人工检查”文本，因为没有额度恢复证据。每个 terminal handle 使用独立原子锁，重复实例拒绝启动；默认 state-dir 为 `${TMPDIR:-/tmp}/multi-agent-orchestration-night-watch`，日志不记录 provider 原始错误。

### 8.3 恢复后的 PM 动作

收到唤醒后，PM 按 §4 清单检查 Dispatch 权威状态，必要时只对已确认 idle 且未完成的 worker 注入一次续作，再重建 recurring 看门狗。真实 PM terminal 的 `show → quota → available → send → PM 实际恢复`、真实 provider 429 文案覆盖和 macOS 睡眠/整夜运行仍为 `NOT_VERIFIED`；当前证据是 fake provider/Orca 的 39 + 31 项确定性回归。settings 文件必须确实承载或引用 provider/account 身份；脚本能冻结文件内容、当前进程环境和 model，不能验证一个语义上无关的空 settings 就代表同一账号。来源：badminton-lab Wave 7/8（2026-08-26）5h 额度窗口实战。
