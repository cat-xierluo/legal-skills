# Reference 22 — 物理内存预算 lane 与派发排队

> spawn 前物理内存维度的预检门。quota lane 管 API 配额维度，本 lane 管物理内存维度。日常派发只需 SKILL §5 的排队规则；调预算、排障 probe 输出或改判定逻辑时读本文件。

## 1. 定位与边界

- 只读探测 + 派发门槛：`mem_budget_probe.py` 读系统快照、折算额度、输出 JSON；不做任何回收动作（不杀进程、不自动降级其他应用、不清 swap）。
- 不建跨项目全局 worker 注册表/文件锁：每次 spawn 现场探测物理内存，其他项目/会话的占用天然反映在可用额度里，无需对账。
- 与 v2.20.0 单进程堆顶互补：堆顶管"单个 worker 的失血点"（node 到限自身退出），本门管"总量叠加承诺"。非 node runtime（python 等）无堆顶可依赖，总量门是唯一防线。
- 已交付但进程滞留的 worker 持续消耗额度，收口纪律见 SKILL §6 收口清单第 6 条。

## 2. 数据源与读取

| 源 | 命令（绝对路径） | 用途 | 失败时 |
|---|---|---|---|
| hw.memsize | `/usr/sbin/sysctl -n hw.memsize` | 物理总量，保留比例基数 | exit 1（无总量不可判） |
| vm_stat | `/usr/bin/vm_stat` | 可用页 × page size（可用性基准优先源） | 降级用 memory_pressure 百分比 |
| memory_pressure | `/usr/bin/memory_pressure`（无参数只读形态） | 官方压力分级 + 可用百分比 | 该源无信号，不参与收紧 |
| vm.swapusage | `/usr/sbin/sysctl -n vm.swapusage` | swap used/total 比例（压力信号） | 无 swap 信号 |

- 任一源失败只降级该源信号；物理总量与可用性基准（vm_stat 或 memory_pressure 百分比）都确立不了 → exit 1 且输出不含任何额度字段（fail-closed，绝不编造）。
- macOS 之外的系统（源路径不存在）同样表现为读取失败 → fail-closed。
- 测试/离线诊断注入：`--fixture-dir`（或 `MEM_BUDGET_FIXTURE_DIR`）目录下 `hw_memsize.txt` / `vm_stat.txt` / `memory_pressure.txt` / `vm_swapusage.txt`，文件缺席 = 该源读取失败，与真实失败同语义。

## 3. 预算推导与压力收紧

```text
available_bytes  = (Pages free + speculative + inactive) × page_size   # vm_stat 优先
                   或 total_bytes × available_percent / 100             # memory_pressure 兜底
                   （钳位到 [0, total_bytes]）
reserve_bytes    = max(2 GiB, 10% × total_bytes)   # 系统底仓，不派给 worker
safe_available   = max(0, available_bytes − reserve_bytes)
tighten          = normal 1.0 | warn 0.5 | critical 0.0
slots            = floor(safe_available × tighten / budget_bytes)
```

- per-worker 预算默认 3 GiB：agent 本体（约 1.2 GiB）+ 测试/构建余量（约 2 GiB），与 v2.20.0 `--max-old-space-size=2048` 堆顶量级对齐。`SPAWN_WORKER_MEM_BUDGET_BYTES` 调整（十进制字节数；`--budget` 可临时覆盖，优先级 flag > env > 默认），非法值 exit 1；`=0` 显式关闭整道门（探测数据照常输出，slots 为 null）。
- 压力分级取各信号最坏值：memory_pressure 关键词（`critical` / `increasing pressure` / `sufficient space`；无关键词但有官方可用百分比时按 ≤5% critical、≤15% warn 推导）与 swap used 比例（≥0.95 critical、≥0.75 warn）。warn 把可承诺额度折半，critical 直接 slots=0。
- vm_stat 的 Swapins/Swapouts 是开机累计计数、不是瞬时压力，不参与判定。
- available 计入 inactive 页：可回收但可能触发换出 I/O；保留底仓 + 压力收紧覆盖尾部风险，换取正常负载下的合理吞吐。

## 4. spawn 接线与退出码

| 场景 | probe rc | spawn 行为 |
|---|---|---|
| ok（slots ≥ 1） | 0 | 放行；PM 日志 `SPAWN_WORKER_MEM_BUDGET: available=<safe_available> budget=<budget> slots=<n> pressure=<level>` |
| disabled（预算 =0） | 0 | 放行；日志 `SPAWN_WORKER_MEM_BUDGET: disabled (SPAWN_WORKER_MEM_BUDGET_BYTES=0)` |
| denied（slots = 0） | 3 | exit 4 + `SPAWN_WORKER_MEM_BUDGET_DENIED` + 可用/预算/缺口诊断 |
| unprobeable / config_invalid / probe 崩溃 | 1 / 其他 | exit 4 + `SPAWN_WORKER_MEM_BUDGET_PROBE_FAILED`（坏门永远不放行） |

- 门的位置：既有 worktree 预门禁与 quota preflight 之后、provider lease / Orca worktree create / Session Context / terminal / dispatch 之前——与 quota 门同一条"任何副作用之前"边界。
- exit 4 是本门专用退出码（区别于 3 = quota / 既有 worktree 预门禁、2 = isolation、64 = 参数与配置）。
- 每次 spawn 现场探测、不缓存：多项目并发时放行额度由物理事实自然收敛，无需注册表；同一任务 OOM 退避后的重拉也天然重跑 probe。

## 5. 排队状态机（PM 巡检）

```text
待派发 ──spawn exit 4──▶ PARKED_FOR_MEMORY（本轮记 probe 输出）
   ▲                          │
   └──────下一轮巡检重试───────┤
                              └──连续 3 轮不足──▶ 泊车 + 向用户报告（附 probe JSON）
额度恢复（worker 收口 / 负载回落）后，下一轮巡检自然放行
```

- 拒绝不是丢弃：任务保持待派发态，PM 按巡检节奏重试；禁止忙等，禁止绕过门手动 spawn。
- 不足轮次按任务计数；连续 3 轮不足 → 正式泊车并向用户报告。常见根因是机器整体过载或预算与机型不匹配（调整 `SPAWN_WORKER_MEM_BUDGET_BYTES` 需用户确认，不让 PM 自行放宽）。

## 6. 与 OOM 退避的交互（v2.20.0）

- worker node OOM（SKILL §5 判定）后同任务不得立即重拉；重拉 spawn 会重新现场跑 probe——OOM 场景常伴随高内存占用，额度不足时任务自然排队，退避规则之外不需要再叠加独立检查。
- OOM 退避的"全局并发 -1"与本门 slots 账本互补：退避管该任务的失败模式，账本管物理承诺总量。
- 滞留的已交付 worker（STATUS=done 进程仍活）按 SKILL §6 当轮收口——它们不退出，额度就回不来。

## 7. 维护矩阵

| 变更 | 必跑 |
|---|---|
| probe 判定 / 解析 / schema | `python3 scripts/test-mem-budget-probe.py`；动了解析先在测试里钉住新形态再改 parser |
| spawn 门位置 / 退出码 / 输出行 | 同上，另 `bash -n scripts/spawn-worker.sh`、`bash scripts/test-spawn-worker-orca.sh`（E2E 成功路径会过真实门） |
| 预算默认值 / 保留公式 / 收紧档位 | 更新本文件 §3 与 SKILL §5 段落；测试 fixture 期望值同步（fixture 数值即推导文档） |
| macOS 源输出形态变化 | 在 test-mem-budget-probe.py 增补该形态用例后复跑全套 |
