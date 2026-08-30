# RESULT — reauthorize 支持 dispatched/等待态 worker（Task-081）

任务：`pm-orchestrate.sh reauthorize` 对仍处于 `dispatched`（如卡 escalation/question 等待）的 supervised worker 支持原地重授权，并消除换终端链路中的双活终端泄漏。

## 改前失败模式（2026-08-30 实测事故 + 本地复现）

事故现场：worker 卡 escalation 等待（task 仍 `dispatched`）时执行 reauthorize：

- Step 4 worker-start 被 Orca 单活 fencing 以 `TASK_REUSED` 拒绝（活 Dispatch 未结算前不允许重复注册，属硬限制，与 failed/blocked 可复位的 `task_not_startable` 不同）；
- 脚本只输出裸 `ERROR: re-registration failed` 便 exit 2，而 Step 3 的新 terminal 已创建、旧 terminal 未关闭 → 双活终端泄漏（实测泄漏 2 个 terminal）；
- 重复执行 reauthorize 每次都再开一个新 terminal，泄漏持续累积。

本地 fake-orca 复现（改前代码跑本 PR 新增的测试矩阵）：Case A（dispatched+escalation 消息）与 Case B（dispatched 无消息）均为——新终端已创建（terminals.live 增至 2）、`ERROR: re-registration failed` 退出码 2、旧终端未关；Case F2 连跑两次后活终端数持续增长。

## 方案（仅动 reauthorize 及其辅助函数，其余 action 零变化）

1. `reauthorize_task_state`：经 task-list 尽力探测 task 状态；旧 runtime 无该子命令时降级 `unknown`，既有行为零变化。
2. Step 0 预检：仅 `dispatched` 时调 `reauthorize_consume_pending_wait`——对 check 中该 dispatch 的未消费 escalation/question 以 `--resume-text`（或缺省续接说明）reply，worker 等待解锁继续执行，task 保持 `dispatched`；无匹配消息则跳过并提示 `PM_REAUTHORIZE_WAIT_NONE`。
3. `reauthorize_rollback_new_terminal`：新 terminal 建立后的任何中间失败（task-update 复位失败 / 重注册失败 / METADATA 改路由失败）先关新终端、保留旧终端——任意时刻至多一个活终端，重复调用不累积终端。
4. 注册失败分类：`task_not_startable` 分支原样保留（复位 ready→重试一次）；`task_reused`（大小写不敏感）→ 回滚新终端 + 输出 manual-recovery 三选一指引（等 worker_done 自然结算后重跑 / 先 settle 再重跑 / runbook #18 三步补绑），退出码 2；其他失败 → 回滚新终端 + 原错误信息。
5. failed/blocked/completed/ready 走原有链路零变化（Case C/D/E 断言输出序列与关闭顺序不变）。

## 改后验证

`bash scripts/test-pm-reauthorize.sh`（新增，mock orca CLI，9 场景 55 断言）：**55 pass, 0 fail**

- A dispatched+escalation 消息：reply 消费等待（msg id / body 逐字断言）、授权合并 + B64 刷新生效、TASK_REUSED 分类标记 + runbook #18 指引 + settle 选项、新终端回滚、旧终端唯一存活、METADATA 仍路由旧终端、旧终端未被 close
- B dispatched 无消息：跳过消费、无 reply 调用，其余同 A
- C/D failed、blocked：复位 ready → 重试 → 换终端 → 关旧，既有路径零变化
- E completed：通用 task_not_startable 路径成功
- F 幂等：成功链与 dispatched 回滚链各连跑两次，活终端数均不增长（dispatched 两次后仍只剩旧终端）
- G terminal create 失败：无 worker-start 副作用，旧终端保留，METADATA 未变
- H register 其他失败：回滚新终端，旧终端唯一存活
- I 旧 runtime 无 task-list：状态降级 unknown，TASK_REUSED 仍给 manual-recovery 而非裸错误

回归：`bash scripts/test-orca-wave-lifecycle.sh` **10 pass, 0 fail**（wait/run-use 路径未受影响）。

## 边界与未验证（NOT_VERIFIED）

- `test-settle-command.sh` / `test-settle-liveness.sh` 未跑：本沙箱 shell 精确白名单不含其入口；本次 diff 未触碰 settle 相关代码路径。
- 全部验证基于 mock orca CLI（按真机响应形态构造，TASK_REUSED 粘滞 / task_not_startable 一次性语义已建模）；未在真 Orca 实测 dispatched 等待消费链。
- `TASK_REUSED` 按 worker-start 错误文本大小写不敏感匹配；Orca 未来改错误码需同步。
- 沙箱禁删文件（rm/git clean 均被 fail-closed 拦截）：仓库根 `scripts/*.sh` 为本 worker 的 4 个 4 行转发包装器（沙箱 cwd 固化所致的脚手架），非交付物、可直接删除；测试真身在 `skills/multi-agent-orchestration/scripts/test-pm-reauthorize.sh`，其中 `scripts/test-pm-reauthorize.sh` 恰好也是验收命令 `bash scripts/test-pm-reauthorize.sh` 的入口。

## 改动文件

- `skills/multi-agent-orchestration/scripts/pm-orchestrate.sh`（reauthorize：Step 0 预检 + 3 个辅助函数 + 注册失败分类回滚 + usage）
- `skills/multi-agent-orchestration/scripts/test-pm-reauthorize.sh`（新增测试矩阵）
- `skills/multi-agent-orchestration/RESULT.md`（本文件）
