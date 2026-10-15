# Reference 21 — zcode 额度 lane 的 summary 生产方

> 本文档是 SKILL.md 第 7 节"Backend、额度与依赖"的按需参考。读取时机：要为 zcode worker 接入真实额度信号、搭建/排障 zcode lane 的 summary 生产链路，或评估第二期接线点时。**本文档是纯知识文档：任何脚本永不读取它。**

## 1. 定位与公私边界

zcode worker（BigModel coding plan）的 5h 窗口额度是真实判停信号，但查询它需要解密本机 Zcode GUI 凭证（`~/.zcode/v2/credentials.json`，AES-256-GCM）。该解密逻辑属于个人监测脚本 `~/bin/zcode-quota`（详见 DEC-140）：

- **公开侧（本 Skill）只做中立合同的消费方与合并写入方**：`scripts/quota_summary_zcode.py` 把 zcode-quota 的观测输出转成 `quota-aware-routing.summary.v1` 的 zcode lane。它不接触凭证、不直接调官方接口。
- **私侧（个人脚本）是唯一碰凭证的生产方**：`zcode-quota --watch` 持续监测（120s 一轮）、`--json` 现场拉取。凭证解密代码永不进入公开仓库。

## 2. 数据流与数据源优先级

```
zcode-quota --watch ──(每轮 obs JSON)──┐
zcode-quota --json  ──(现场拉取)──────┤
~/.zcode/quota-watch-log.jsonl ────────┤→ quota_summary_zcode.py → 合并写入 summary_path
```

`quota_summary_zcode.py` 数据源优先级（全部失败 exit 1、不写文件，消费方按 stale fail-closed）：

1. `--stdin-obs`：stdin 读 obs JSON（watch 钩子直连，无新鲜度判断）；
2. `--watch-log`（默认 `~/.zcode/quota-watch-log.jsonl`）：末尾第一条新鲜（`--freshness-seconds`，默认 300s）且有 `tokens_pct` 的记录；
3. `--script`（默认 `~/bin/zcode-quota`）：`--json` 现场拉取。

## 3. 合并语义（多生产方共存）

summary 文件可能同时有其他生产方（例如私仓 idle-task-runner 的 `dump_quota_summary.py` 整文件重写 glm/minimax/网关 lane）。适配器约定：

- **只替换 zcode lane**，其余 lane 原样保留；
- **`generated_at` 保留原值**：合并方不得替别的生产方"续期"。生产方停摆必须表现为整体 stale 被预检门拒绝，而不是被 zcode lane 的刷新掩盖（与 2026-08-29 过期快照事故的 fail-closed 方向一致）；
- 无既有文件或文件里只有 zcode lane 时，`generated_at` = 本次数据时刻；
- 原子写（同目录 tmp + `os.replace`）；lane 记录带 `updated_at` / `source` 溯源附加键（v1 消费方忽略未知键）。

lane 字段映射：`remaining_percent = 100 - tokens_pct`（钳到 [0,100]），`resets_at` = `TOKENS_LIMIT.nextResetTime` 转 ISO（可缺省），`type: fuel`。

## 4. 启用方式

1. 个人配置 `quota_aware_routing.lanes` 增加一条（**不要**加进任何 `tier_policy` 链，避免 route_suggest 自动补选把非 claude-code provider 派给 claude-code worker；第二期接线完成前该 lane 仅在显式 `--provider zcode` 时被预检门消费）：

   ```json
   "zcode": {"type": "fuel", "providers": ["zcode"]}
   ```

2. 让数据活起来（三选一）：

   ```bash
   # a. watch 钩子直连（推荐，随监测进程 120s 自动刷新）
   ZCODE_QUOTA_SUMMARY_HOOK="python3 '<skill>/scripts/quota_summary_zcode.py' --stdin-obs --out '<summary_path>'" \
     nohup ~/bin/zcode-quota --watch 120 --auto-claim > ~/.zcode/quota-watch.out 2>&1 &

   # b. 手动/定时一次性刷新（日志新鲜则免 API 调用）
   python3 '<skill>/scripts/quota_summary_zcode.py' --out '<summary_path>'

   # c. PM 派单前现场确认（走 live-pull）
   python3 '<skill>/scripts/quota_summary_zcode.py' --out '<summary_path>' && \
     python3 '<skill>/scripts/quota_preflight.py' --config '<个人配置>' --provider zcode --backend zcode
   ```

3. 验证：`test-quota-summary-zcode.py` 覆盖数据源回退链、合并语义与预检门联动。

## 5. fail-closed 行为汇总

| 情形 | 行为 |
|---|---|
| watch 进程死、日志过期、脚本缺失 | exit 1 不写文件；既有 summary 过期后预检门 `stale_summary` 拒绝 |
| `tokens_pct` 缺失（额度接口失败） | 该观测不可用，向下一数据源回退 |
| 其他 lane 的生产方停摆 | `generated_at` 不被续期，整体 stale 如实暴露 |
| 适配器输出路径不可写 | exit 2，不产生半截 JSON |

## 6. 第二期接线点（尚未实现）

- **spawn 侧**：`spawn-worker.sh` 对 `--worker-backend zcode` 且未显式 provider 时，尚不会以 `provider=zcode` 调用预检门（当前 `not_applicable` 放行）。接线需同步定义"backend 隐式 provider 未配置 lane"的语义，并补 spawn 测试矩阵。
- **429 恢复侧**：`orca_rate_limit_recovery.py` 唤醒前可用 zcode lane/现场拉取确认 5h 窗口真实余量，避免"WAKE_ACCEPTED 但窗口仍尽"的空唤醒。
- **summary v2**：若引入 per-lane 时间戳合同，可解除"单一 `generated_at` 约束全部 lane"的限制，届时合并语义可重估（见 DEC-140 重新评估条件）。
