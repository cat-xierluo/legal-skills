# Orca Worker 额度停滞巡检与错峰唤醒

> 仅在 PM 需要跨项目检查 Orca 管理的 Worker terminal 是否因 provider 429 / rate limit / usage limit 停在 idle，并在显式授权后尝试唤醒时读取。tmux、自动切 provider、后台守护、L3 scheduler 与“确认额度已经恢复”不在本流程范围。

## 1. 能力边界

`scripts/orca_rate_limit_recovery.py` 是一次性批量审计器，不是额度可用性探针：

- 默认 audit 只调用 Orca 的 `terminal list/show/read/wait`，不创建状态目录、不发送输入。
- 只有显式 `--execute` 才可能调用 `orca terminal send --text "继续" --enter --json`。
- `WAKE_ACCEPTED` 只证明 Orca 接受了键盘注入，不证明 provider lane 已恢复，也不证明 Worker 已产生业务进展。随后仍需重新巡检 transcript/cursor，并以 diff、测试、产物或 Delivery 验收实际进展。
- `pm-quota-stall.sh` 继续负责单 provider 的 `quota → available` one-shot 探针；本工具只处理已经停在 idle 的 Worker terminal。两者复用 `provider_error_classifier.py`，认证、配置、网络错误优先于额度分类。
- 本入口收敛原有 Worker 双读判活与批量 check-workers 的零散设想，并为未来 lane availability probe 保留显式 provider/account group 边界；它不实现 lane probe，也不把 Task-064 的真实 provider E2E 标成完成。真实 GLM/MiniMax 429 与真实批量唤醒仍是 `NOT_VERIFIED`。

## 2. 显式清单

复制 `templates/orca-rate-limit-workers.example.json` 到 Git 之外的私有路径，逐项填写。脚本不会替调用方改变 manifest 权限或 Git 状态；调用方必须确保清单不含凭证且不提交：

| 字段 | 约束 |
|---|---|
| `source` | 只能是 `orca`；`tmux` 或其他来源整批拒绝 |
| `terminal_handle` | `orca terminal list --limit 500 --json` 返回的精确 handle |
| `incarnation_id` | 同一 terminal 的精确 `incarnationId`，防 handle 重用 |
| `provider` | 非敏感 provider 标识，如 `glm`、`minimax` |
| `account_group` | PM 自定义的非敏感 lane 代号；不要写邮箱、Token、账号或 settings 内容 |

先运行全量 list 并确认 `.result.truncated == false`。脚本也会复核该字段；截断时整批失败关闭，不把不完整清单称为全量审计。

## 3. 状态判定

脚本要求 terminal 同时出现在未截断 list 中，且 `show` 的 `handle + incarnationId` 与 manifest 一致。状态合同：

| 状态 | 机械证据 | 是否发送 |
|---|---|---|
| `RUNNING` | connected/writable；无可执行额度证据；`tui-idle` 未满足；输出时间新鲜 | 否 |
| `RATE_LIMIT_RETRYING` | 尾部存在明确 provider quota error；cursor/timestamp 新鲜；TUI 仍非 idle 或尚未过 idle 阈值 | 否 |
| `RATE_LIMIT_IDLE` | 明确 quota error + latest cursor + 未过期 `lastOutputAt` + connected/writable + `tui-idle satisfied` + 超过 idle 阈值 | 仅 `--execute` 候选 |
| `UNKNOWN` | 身份缺失/漂移、断连、不可写、陈旧证据、auth/config/network、仅讨论/测试 429、结构不明等 | 否 |

单一 `429` 关键词、源码/测试/fixture 对 429 的讨论、429 后已有实质进展的非锚定 tail、陈旧 tail、`agentWait`、单独 idle 或单独 cursor 都不是充分证据。认证/配置文字和 429 混合时按非额度错误失败关闭。

## 4. 运行

```bash
# 默认只读审计；人类可读结果
python3 scripts/orca_rate_limit_recovery.py \
  --manifest /private/path/orca-workers.json

# 稳定 JSON 回执
python3 scripts/orca_rate_limit_recovery.py \
  --manifest /private/path/orca-workers.json --json

# 显式执行；只对高置信 RATE_LIMIT_IDLE 尝试一次“继续”
python3 scripts/orca_rate_limit_recovery.py \
  --manifest /private/path/orca-workers.json --execute --json
```

默认同一 `provider + account_group` 内相邻 Worker 间隔 8 秒，不同组间隔 15 秒；用 `--terminal-delay-ms`、`--group-delay-ms` 在 100—300000ms 内调整。排序由 group fingerprint、terminal handle 决定，固定且可审计。错峰只降低同 lane 同时重试的冲击，不保证绕过硬性额度限制。

常用判定参数：

- `--idle-seconds 300`：quota 输出距现在至少 5 分钟且 TUI idle，才视为停滞。
- `--evidence-max-age-seconds 21600`：超过 6 小时的 quota tail 视为陈旧。
- `--list-limit 500`：Orca 活跃 terminal 超过此数会返回 truncated，脚本拒绝继续；可在 1—5000 内显式提高。

## 5. 幂等与 TOCTOU

执行状态默认写入 `~/.local/state/multi-agent-orchestration/orca-rate-limit-recovery/`；可用 `--state-dir` 指向其他私有目录。目录必须归当前用户所有、拒绝 symlink、group/world 无权限；state/lock 必须为私有 regular file，FIFO、设备和 socket 均拒绝。锁竞争立即失败，不无限等待。

episode key 绑定 `terminal handle + incarnationId + latestCursor + lastOutputAt + quota evidence fingerprint`。发送前重新执行 show/read/wait，要求 identity、timestamp、cursor 和 idle 均未漂移；随后先持久化 `intent`，再发送固定文本“继续”，最后复核 terminal identity 并把状态改为 `sent`。send 或后置复核结果不确定时保留 `intent`，同一 episode 后续执行只报 `already_handled`，不会盲重发；只有新的 cursor/timestamp 证据才形成新 episode。

状态与回执只保存/输出 fingerprint、分类状态和原因码，不回显 provider 原始错误、settings、凭证或 account group 原文。

## 6. 退出码

| 退出码 | 含义 |
|---:|---|
| `0` | audit 完成，或所有可执行候选均得到 `WAKE_ACCEPTED` / 幂等跳过 |
| `64` | 参数或 Orca CLI 依赖错误 |
| `65` | manifest / JSON 合同错误 |
| `70` | Orca 命令失败或返回畸形合同 |
| `74` | 私有状态目录/文件不安全或 I/O 失败 |
| `75` | terminal identity/cursor/activity 漂移、锁竞争或发送结果不确定 |

任何非零退出都停止后续发送。不要因为某个 terminal 看起来 idle 而手工绕过；修复 manifest、Orca runtime 或状态权限后重新 audit。
