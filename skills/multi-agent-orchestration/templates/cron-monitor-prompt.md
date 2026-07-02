# Cron 兜底监测 prompt 模板

> 使用方式：PM 派 worker 后挂 cron 兜底（sentinel 是主监测，cron 抓 sentinel 盲区，见 SKILL.md §7.3）。复制本模板，替换 `{{...}}`，用 CronCreate 注册。worker 全部合入后 `CronDelete` 自删。
>
> 频次：短任务 ~22min、长流水线 10-15min，避开 `:00`/`:30`。

## cron 表达式建议

| 任务粒度 | cron 表达式 | 说明 |
|---|---|---|
| 短任务（< 1h） | `7,29,51 * * * *` | 每 ~22 分钟，错峰 |
| 长流水线（1-4h，推荐） | `3,13,23,33,43,53 * * * *` | 每 10 分钟，错峰 |
| 长流水线（轻量） | `8,23,38,53 * * * *` | 每 15 分钟，错峰 |

> 不要用 `*/10 * * * *`（落在 :00/:30 整点，API 拥堵）；不要低于 10 分钟（过频抵消 token efficiency）。

## prompt 模板

```text
PM 巡检 {{wave_id}}（{{worker_summary}}）。读各 worker 的 STATUS.json：{{status_paths}}，看 status/phase/updated_at/progress；查各自分支 git log {{base_ref}}..HEAD --oneline 看 commit 节奏；tmux capture-pane -t {{session}} -p | tail -15。

判定（按优先级）：
1. 若某 worker status=done → 按 SKILL.md §8 跑 gh pr view <PR> --json mergeable,mergeStateStatus 检查、review、收口；体系性修改标"已完成·待核实"留 TASKS 活跃区等作者复核。全部 worker 合入后 CronDelete 自删本 cron。
2. 若 failed/blocked → 读 STATUS.issues 决定纠偏/重启，向用户简报。
3. 若双信号卡死（STATUS.updated_at 和文件 mtime 都 > {{stale_threshold}} 未变 **且** pane 尾部有死循环证据）→ 先发 tmux send-keys 心跳探针；下一轮 cron 仍无变化才重启 worker。
4. 若 updated_at stale 但 pane 显示正常推进（long thinking）→ 不干预，只回一句话。
5. 若 tmux session 不存活 / sentinel 进程消失 → 诊断（额度耗尽？GLM 5h 重置？被 kill？），向用户简报并处置。

正常推进则只回一句：各 worker 当前 phase/progress。不膨胀上下文。

sentinel {{sentinel_ids}} 在后台，worker 终态会自动唤醒 PM，cron 是兜底。
```

## 占位符

| 占位符 | 含义 | 示例 |
|---|---|---|
| `{{wave_id}}` | Wave 标识 | `wave-svg-deai-260703` |
| `{{worker_summary}}` | worker 一句话摘要 | `W1=svg-t126/minimax 做 T126；W2=deai-full/glm 去AI化` |
| `{{status_paths}}` | 各 worker STATUS.json 路径（空格分隔） | `.claude/worktrees/tmux-X/.claude/agent-sessions/s/STATUS.json 与 .../tmux-Y/.claude/agent-sessions/t/STATUS.json` |
| `{{base_ref}}` | 基线分支 | `main` |
| `{{session}}` | tmux session 名（多 worker 多次 capture） | `svg-t126` 和 `deai-full` |
| `{{stale_threshold}}` | 卡死时间阈值 | 长流水线 `20min`、短任务 `15min` |
| `{{sentinel_ids}}` | sentinel background job id 列表 | `ba1y0g64e(W1)/bz2ag2js4(W2)` |

## 收尾纪律

- worker 全部 `done` 并合入后，PM 必须 `CronDelete` 本 cron，避免孤儿 cron 反复 fire 消耗 token。
- 若 Wave 中途用户中止 / worker 全部 blocked 无法推进，也 `CronDelete`，改为 PM 主动处置。
- cron 是 session-only（默认）或 durable（用户明确要求长期）；session 结束 cron 自动消失，不污染下次。
