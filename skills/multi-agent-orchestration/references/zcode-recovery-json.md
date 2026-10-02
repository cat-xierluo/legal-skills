# ZCode 恢复链路 terminal-read JSON 合同（recover-unconfigured-worker）

本文说明 `recover-unconfigured-worker.sh` 对 `orca terminal read --json` 响应的解析合同、
2026-10-02 修复的解析器缺陷触发条件，以及恢复命令的退出码边界。本文是合同与故障说明，
不声称也不替代现场监督式恢复；实际恢复仍由 PM 显式调用脚本并人工复核 receipt。

## 解析合同（read_terminal_tail）

输入：`orca terminal read --terminal <handle> --limit N --json` 的 stdout（stub 场景由
fake-orca 状态文件驱动）。

| 响应形态 | 判定 | 后果 |
|----------|------|------|
| `result.terminal.tail` 为字符串数组 | 合法 | `join("\n")` 交给 TUI 启发式判定 |
| `result.tail`（顶层 tail，原合同）为字符串数组 | 合法 | 同上 |
| `tail` 缺失 / `tail: null` / `tail: []` | 合法空 tail | 视同 `[]` → unknown → manual-required(2) |
| `tail` 为字符串/数字/对象等非数组 | 拒绝 | exit 11 → `terminal-probe-invalid` → manual-required(2) |
| `tail` 数组含 number/object/null 尾项 | 拒绝 | 同上 |
| `ok != true` 或 `result` 非对象（wrong envelope） | 拒绝 | 同上 |
| 响应非合法 JSON | 拒绝 | 同上 |
| `orca terminal read` 命令本身非零退出 | 命令失败 | `terminal-read-failed` → manual-required(2) |

多身份冲突与类型拒绝不因修复而放松：dispatch-show 与 terminal read 的 envelope/类型/
冲突检查保持原语义。

## 缺陷触发条件（已修复）

2026-10-02 前的生产脚本中，`read_terminal_tail` 的 jq 程序把 `as $tail` 绑定直接接在
未加括号的 `if ... end` 之后（`end as $tail`）。这不是合法 jq 语法：`as` 绑定的输入
表达式必须可独立成表达式（此处需括号）。于是整个 jq 程序**编译失败**（jq exit 3），
而调用点 `2>/dev/null` 吞掉了编译错误，脚本把一切响应（包括完全合法的 shell/tui tail）
折叠为"非法 JSON/结构"，恢复链路在terminal read 第一步即 fail-closed：

- 表象：合法 shell/tui 态一律 `RECOVER_REASON=terminal-probe-invalid`，无法走注入/register；
- 误导性：缺 tail/坏 JSON 等"负向"测试期望拒绝，被编译失败碰巧满足而全绿
  （PR250 完整矩阵 72 pass / 11 fail 的 11 个失败全部来自合法形态被拒）；
- 根因修复：给 `if ... end` 加括号（`(if ... end) as $tail`），一行改动，不放宽任何拒绝。

经验法则：调用点用 `2>/dev/null` 折叠 stderr 的 jq `-e` 解析，必须先用最小输入验证
程序可编译，否则编译错误与数据错误在调用点不可区分。

## 命令与退出码边界

```bash
bash skills/multi-agent-orchestration/scripts/recover-unconfigured-worker.sh \
  --worktree <WT> --session <NAME> [--timeout SEC] [--poll-interval SEC] [--tail-lines N]
```

| 退出码 | 含义 | RECOVER_REASON 常见值 |
|--------|------|------------------------|
| 0 | recovered / already-healthy | none |
| 2 | manual-required（terminal 死/状态不明/TUI 未起/register 失败） | terminal-probe-invalid、terminal-read-failed、dispatch-probe-invalid、dispatch-read-failed、manual-required |
| 3 | manual-required（METADATA 缺路由段 / authority receipt 缺失或错配） | authority-receipt-invalid |
| 64 | usage | none |

不变量：任何路径零 `terminal create`；terminal_handle 全程不变。`terminal send`
副作用按阶段区分：注入前拒绝（terminal/dispatch 探针失败、unknown、authority
拒绝等失败路径）零 `terminal send`、零 `worker-start`；已注入后坏读
（poison-after-send）`terminal send` 恰好 1（注入已发生，不重复注入）但立即
停止，零 `worker-start`（绝不 register）。

## 验证

```bash
bash skills/multi-agent-orchestration/scripts/test-recover-unconfigured.sh
```

态10 回归（含 10a–10d）可在旧解析器上得到非零退出（反例：合法顶层 tail、注入后坏读、
空 tail 误判 probe-invalid），证明回归真实覆盖该缺陷，而非仅对新实现恒真。
