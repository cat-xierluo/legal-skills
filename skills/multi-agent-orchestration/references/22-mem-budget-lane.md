# Reference 22 — 物理内存预算 lane 与派发排队

> spawn 前物理内存维度的预检门。quota lane 管 API 配额维度，本 lane 管物理内存维度。日常派发只需 SKILL §5 的排队规则；调预算、排障 probe 输出或改判定逻辑时读本文件。

## 1. 定位与边界

- 只读探测 + 派发门槛：`mem_budget_probe.py` 读系统快照、折算额度、输出 JSON；不做任何回收动作（不杀进程、不自动降级其他应用、不清 swap）。
- 不建跨项目全局 worker 注册表/文件锁：每次 spawn 现场探测物理内存，采样反映当时实际占用，不预留未来预算；跨 PM 计划并发仍按共享库存和原 owner 协调。
- 与 v2.20.0 单进程堆顶互补：堆顶管"单个 worker 的失血点"（node 到限自身退出），本门管"总量叠加承诺"。非 node runtime（python 等）无堆顶可依赖，总量门是唯一防线。
- 已交付但进程滞留的 worker 持续消耗额度，收口纪律见 SKILL §6 收口清单第 6 条。

## 2. 数据源与读取

| 源 | 命令（绝对路径） | 用途 | 失败时 |
|---|---|---|---|
| hw.memsize | `/usr/sbin/sysctl -n hw.memsize` | 物理总量，保留比例基数 | exit 1（无总量不可判） |
| vm_stat | `/usr/bin/vm_stat` | 可用页 × page size（可用性基准优先源） | 降级用 memory_pressure 百分比 |
| memory_pressure | `/usr/bin/memory_pressure`（无参数只读形态） | 旧关键词/旧 available 百分比参与既有算法；System-wide free 百分比仅观测 | 该源无有效算法信号，不参与收紧 |
| kern.memorystatus_vm_pressure_level | `/usr/sbin/sysctl -n kern.memorystatus_vm_pressure_level` | 原生 dispatch 通知位 1/2/4，分别 normal/warn/critical，仅观测 | 未知/缺失/畸形保持无有效级别 |
| vm.swapusage | `/usr/sbin/sysctl -n vm.swapusage` | swap used/total 比例（压力信号） | 无 swap 信号 |

- 任一源失败只降级该源信号；物理总量与可用性基准（vm_stat 或 memory_pressure 百分比）都确立不了 → exit 1 且输出不含任何额度字段（fail-closed，绝不编造）。
- macOS 之外的系统（源路径不存在）同样表现为读取失败 → fail-closed。
- 测试/离线诊断注入：`--fixture-dir`（或 `MEM_BUDGET_FIXTURE_DIR`）目录下 `hw_memsize.txt` / `vm_stat.txt` / `memory_pressure.txt` / `vm_swapusage.txt` / `kernel_pressure.txt`，文件缺席 = 该源读取失败，与真实失败同语义。

### 2.1 遥测与准入来源

- 保留 `memory-budget.summary.v1` 及 legacy `sources`/`pressure` 消费者合同；新增 `telemetry` 区分每源的读取成功、解析有效与解析状态。空输出可读取成功但解析无效，不把 `sources=ok` 当成信号有效。
- `System-wide memory free percentage: 84%` 只保存为 `reported_free_percent`，不当作旧 `available_percent`、available_bytes 兜底或压力级别；缺少 vm_stat 且只有该新百分比时仍不可探测。
- `telemetry.kernel_pressure` 标明原生来源，`used_for_admission=false`；严格单个 1/2/4 映射 normal/warn/critical，未知、多行与非法值不虚造级别。`telemetry.composite_pressure` 标明既有算法来源；实际参与准入计算时 `used_for_admission=true`，disabled/unprobeable 时为 false。native normal 不抵消 swap critical。
- Swap Used 是当前占用空间，vm_stat Swapouts/Pageouts 是累计计数；有限观测窗不能证明冷页归属、swap 可增长性或放行安全。Apple 的[内存压力说明](https://support.apple.com/en-euro/guide/activity-monitor/actmntr1004/mac)说明压力综合多个信号，不能用单一空闲百分比替代。
- 固定样本见 `scripts/fixtures/memory-admission-261002/` 与 SHA 清单；三份实际均报告 84%、kernel=1，原 swap≥0.95 拒绝语义保持。原诊断和窄修沿原任务，不恢复已经泊车的业务。

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

- per-worker 预算默认 3 GiB：agent 本体（约 1.2 GiB）+ 测试/构建余量（约 2 GiB），与 v2.20.0 `--max-old-space-size=2048` 堆顶量级对齐。`SPAWN_WORKER_MEM_BUDGET_BYTES` 调整（十进制字节数；`--budget` 可临时覆盖，优先级 flag > env > 默认），非法值 exit 1；`=0` 显式关闭整道门（`slots=null`，宿主探测数据仅按最佳努力保留，全部不可读也不得把显式 opt-out 变回硬失败）。
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
- 每次 spawn 现场探测、不缓存：不建立原子预留，不把同一快照分别承诺给多个 PM；同一任务 OOM 退避后的重拉也天然重跑 probe。

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
| probe 判定 / 解析 / schema | `python3 scripts/test-mem-budget-probe.py` 与 `python3 scripts/test_memory_telemetry.py`；动了解析先在测试里钉住新形态再改 parser |
| spawn 门位置 / 退出码 / 输出行 | 同上，另 `bash -n scripts/spawn-worker.sh`、`bash scripts/test-spawn-worker-orca.sh`（E2E 成功路径会过真实门） |
| 预算默认值 / 保留公式 / 收紧档位 | 更新本文件 §3 与 SKILL §5 段落；测试 fixture 期望值同步（fixture 数值即推导文档） |
| macOS 源输出形态变化 | 在 test-mem-budget-probe.py 增补该形态用例后复跑全套 |

## 8. 显式任务 profile（资源门校准）

仅通过 `SPAWN_WORKER_MEMORY_TASK_PROFILE=/absolute/canonical/profile.json` 选择；无该变量时完全保留旧 3GiB 默认、swap 阈值、opt-out 和退出码。新 profile 不能用预算 0。文件为当前 UID 的非符号链接常规文件且禁止组/其他用户写入；路径、schema、键、hash 和 task 身份均严格复核。

`schema=memory-task-admission.profile.v1`；`task_id`；`kind=light_node|heavy`；`execution=new_spawn|existing_session`。`measurement`、`oom_history` 使用 `{path,sha256}` 引用独立任务证据。light measurement 含 `kind=node_measurement`、同 task、正整数 peak_rss_bytes、heap_mb≤512、exit_code=0、workload=bounded_node_no_build_no_browser。light 预算是 max(2GiB, 实测RSS+512MiB堆余量+1GiB系统/运行余量)，heavy≥3GiB；不能根据 reuse 字样减成 0。所有数字拒 bool、非有限和非法值。

OOM artifact 包含 `kind=task_oom_history`、同 task、checked_at_epoch、events=[{at_epoch,type=oom}]，coverage 必须为 `task_only_machine_unknown`。证据只能说明具名任务历史；全机近期 OOM 未证明。检查时刻最多1小时且不能未来，任务24小时内有OOM则拒。证据来源/完整性仍由原PM任务材料负责，hash并非事实真实性签章。serial_contract 必须具名 coordinator、同 task、writer_limit=1、scope=original_pm_serial_only。该合同是原PM串行承诺，不是跨PM原子锁；跨PM任务期 reservation/release **NOT_VERIFIED**，不得拿候选作为全局高swap默认放宽。

新 light spawn 复用现 backend command validator 的实际 resolved_argv，要求可读真实 Node 入口或严格 Node shebang。拒绝 caller NODE_OPTIONS、COMMAND 中任何 Node heap/NODE_OPTIONS覆盖和 cap=0/非512。spawn 在所有包装完成后再次复核，在实际exec-bound执行边界复核，强制canonical Node实际argv参数 `--max-old-space-size=480 --max-semi-space-size=1`（首轮真实consumer发现old-space512时总V8堆704MiB；修正后实测483MiB），真实 Node consumer验证堆顶。禁止将非Node Agent runtime按业务将来会运行Node而冒充Node入口；任务后续主动覆盖子进程限制不由本模块全局拦截，业务仍须遵守任务范围。

existing_session 必须实际 `/bin/ps` 复核 UID/PID/start/command hash，并且真实 argv 是 Node 及启动首参数 max-old-space-size≤480、第二参数max-semi-space-size=1；身份消失、漂移、非Node或未来命令无法强制均拒。仍保留≥2GiB，不提供增量discount；spawn入口一律拒 existing_session。具体业务仍须核其实际宿主和将要执行的命令，不能用隔离正例代替。

高swap例外仅显式 light_node（及 §8.4 的限定 MiniMax），不适用于通用 heavy：由真实只读 collector采样至少20秒、至少3样本、严格单调时钟；每个样本 vm_stat物理可用减原reserve≥预算，native dispatch flags 1/2有效非critical；memory_pressure可解析且非critical，旧available-percent/关键词warn不得作为swap-only例外。严格解析累计 Swapouts/Pageouts，所有相邻差分必须0，回退/缺失/重复/增长均拒；swapused量不得增长，账本非负且used≤total。未知native/缺计数/短窗口/任务近期OOM/低可用/heavy拒。

零增量、20秒、1小时证据和24小时OOM窗均是本候选的保守实验合同，**不是Apple官方阈值**。原 telemetry-only native flag 在 opt-in 内成为硬门：critical/unknown即拒；无profile的native语义不变。例外保留原 pressure.level、swapratio及signals，新增 task_admission 说明独立实验权威；允许时最多 slots=1，不伪造normal。离线fixture只一份样本，不能假装现场等待，短窗继续拒。

CLI观察入口：`mem_budget_probe.py --json --task-profile PROFILE --task-command ACTUAL_COMMAND --task-backend BACKEND`；light new_spawn 必须核实际命令。此probe只报告准入证据，实际Node heap强制来自spawn，独立probe不启动worker。任务profile配置失败exit1、资源拒绝exit3，spawn继续映射原资源门exit4；早期launcher/heap身份拒绝exit64。

### 8.1 贯穿准入与执行的身份绑定

`memory-task-spawn.binding.v1` 包含 profile SHA、artifact hash、task/backend/kind、原command SHA、实际入口canonical path/SHA/device/inode/size以及实际Node binary同类指纹、version、实测V8 heap。heavy也绑定profile与实际argv，不按早期cached heap=null跳过late验证。probe传入同一 `--task-binding-b64`，采样前后与新的实际读取严格比较；late `render-launch` 和真正 `exec-bound` 均再次复核。任一identity/byte/profile/解释器漂移即拒绝。

仅支持backend validator核实的直接普通argv；env/bash/provider shell不透明包装早拒。晚期只允许spawn自身形成的env赋值前缀，PATH/NODE_OPTIONS/NODE_PATH/LD_/DYLD_覆盖拒绝。解释器必须是实际Mach-O/ELF，实际启动回读process.execPath/version；轻 Node 要求 V8 heap≤512MiB，MiniMax 按 §8.4 的独立上限；PATH名node脚本wrapper不能证明解释器。轻 Node 实际执行用canonical已核Node路径与固定480/semi1参数及已核入口argv，不交回PATH/shebang启动。原默认路径不调用该guard，保持旧策略。

existing参数检查统一匹配连字符/下划线V8 heap别名，后置覆盖/重复均拒。实验层对每份原始swap total/used/free先严格检查单一有效数值、used/free≤total及账本守恒；不能用旧parser钳位结果授权。旧parser默认行为完全不改。

例外仍保留legacy pressure与effective_available_bytes（可能0）作旧policy证据；新增task_admission.effective_capacity_bytes为窗口内每样本`vm_stat available - 原reserve`的最小值，effective_capacity_source明确该来源、budget_bytes明确预算，并保留legacy_effective_available_bytes。status/slots来自独立实验权威，不把旧0额度称为可用。全机OOM、跨PMreservation、实际共享 Agent 宿主业务和长程安全仍没有扩大验证。

### 8.2 共享 Codex 宿主 followup：分别绑定 Agent 与 Node

使用同一 `memory-task-admission.profile.v1`，`kind=light_node`、`execution=codex_host_followup`；沿同一 `apply_profile`、至少2GiB全额预算、原PM serial-only与全部压力/OOM/稳定窗口硬拒。不是新增模型进程0预算，不提供reuse折扣。`bind-spawn`一律拒宿主profile，spawn早门自然返回64；不创建Agent、terminal、Orca Task或followup。

新增两个 `{path,sha256}` artifact：`host_projection`、`node_plan`。artifact文件同现private/canonical/owned/regular/hash规则并绑定同task。宿主投影仅是原控制器的工具观测attestation，**不是平台签名**，不以hash证明观测真实性。控制器须正式重读 `collaboration.list_agents` 并把当前真实 `CODEX_THREAD_ID` 写入投影；helper将其与自身实际env比较。canonical parent为`/root`，worker为原具名canonical child path，库存须逐项一致、无重复/冲突，parent running、原选worker completed。工具未暴露的Agent UUID/PID保留null，不能借Node PID冒Agent身份。

投影限120秒、非未来，采样后、admit结束和实际执行边界均重读；profile/measurement/OOM/projection/plan字节或Node/cwd/entry身份漂移拒绝。历史投影不签未来资源或业务准入。计划允许future cwd尚未创建并报告planned_not_created，但执行必须要求当前UID owned且非组/其他用户可写目录、实际entry存在与SHA一致，scoped argv与入口/参数物理路径均不得逃逸cwd（包括symlink）。

Node plan只接受canonical实际Node绝对路径及精确480/semi1启动参数，entry是cwd下的相对路径；壳/env启动、heap覆盖/别名、未知路径或entry SHA漂移均拒。实际解释器回读process.execPath、version和V8总heap≤512MiB，并使用固定canonical argv执行，不使用PATH/shebang。Node是测试子进程而非Agent身份。任务后续调用其它进程不由此接口提供全局sandbox，原scope继续负责。

脱敏字段示例（占位符必须用实际读回值填写，不是可直接运行的授权文件）：

```json
{
  "schema": "memory-task-admission.profile.v1",
  "task_id": "TASK-SCOPED-NODE",
  "kind": "light_node",
  "execution": "codex_host_followup",
  "measurement": {"path": "/canonical/private/measurement.json", "sha256": "<64 lowercase hex>"},
  "oom_history": {"path": "/canonical/private/oom.json", "sha256": "<64 lowercase hex>"},
  "host_projection": {"path": "/canonical/private/host.json", "sha256": "<64 lowercase hex>"},
  "node_plan": {"path": "/canonical/private/node-plan.json", "sha256": "<64 lowercase hex>"},
  "serial_contract": {"coordinator": "original-controller", "task_id": "TASK-SCOPED-NODE", "writer_limit": 1, "scope": "original_pm_serial_only"}
}
```

`host_projection`完整字段：

```json
{
  "kind": "codex_host_tool_projection", "task_id": "TASK-SCOPED-NODE", "observed_at_epoch": 0,
  "controller": {"thread_id": "<actual CODEX_THREAD_ID>", "canonical_parent": "/root"},
  "selected_worker": {"canonical_path": "/root/selected_worker", "status": "completed", "opaque_agent_uuid": null, "os_pid": null},
  "agents": [{"canonical_path": "/root", "status": "running"}, {"canonical_path": "/root/selected_worker", "status": "completed"}],
  "source": {"type": "original_controller_tool_attestation", "tool": "collaboration.list_agents", "platform_signed": false}
}
```

`node_plan`完整字段：

```json
{
  "kind": "scoped_node_plan", "task_id": "TASK-SCOPED-NODE", "cwd": "/canonical/owned/task-cwd",
  "argv": ["/canonical/native/node", "--max-old-space-size=480", "--max-semi-space-size=1", "scripts/scoped-test.mjs", "--unit-only"],
  "entry_sha256": "<64 lowercase hex>"
}
```

measurement继续使用node_measurement的既有字段：同task、peak_rss_bytes、heap_mb、exit_code=0、workload=bounded_node_no_build_no_browser；PM需由实际具名消费者的日志/测量证明来源，hash不是事实签章。OOM继续使用task_oom_history的既有字段：同task、实际checked_at_epoch、events=[{at_epoch,type=oom}]、coverage=task_only_machine_unknown；空events只说明任务所见，不签全机无OOM。

正式调用（均由原控制器调用，不由helper发送followup）：

```bash
python3 scripts/host_memory_admission.py inspect --profile /canonical/private/profile.json
python3 scripts/host_memory_admission.py admit --profile /canonical/private/profile.json
python3 scripts/host_memory_admission.py execute-node --profile /canonical/private/profile.json --binding-b64 '<inspect binding canonical JSON的urlsafe base64>'
```

inspect不执行资源准入，admit只通过原共享门只读采样，输出完整memory_gate及绑定；`--fixture-dir`只供离线诊断，明确fixture_files，不能证明live。execute-node不接受caller JSON“status=ok”回执，也不接受fixture授权；在同调用内运行原共享资源门**一次**，只有真实成功再执行固定Node，硬拒时node_executed=false。资源状态不允许即继续denied，不能连续重复采样求放行。thin机械Node测试只验证执行层，不等于资源准入或原业务完成。

原PM仍须核quota、scope、cancellation、原预算与目标任务，正式新鲜重读投影后在原选Agent上发唯一followup。helper不自动followup，不提供跨PM锁，不签具体业务的派发、交付或长期安全。公共契约不硬编码私人业务路径或业务projection schema。

### 8.3 宿主目录、真实采集来源与有界输出

存在cwd的device/inode/uid/mode写入workload_node.cwd_identity，与canonical path、entry inode/hash共同组成绑定。仅保持同path和entryinode不足以证明同目录；采样后、admit后及实际Node执行前对同expected完整比较，目录rename/recreate或owner/mode漂移拒。future cwd仍可inspect并记录cwd_identity=null，但执行要求存在且重新取得新鲜实际绑定。

外层collection_mode以共享gate实际telemetry.collection_mode为权威，严格核对effective fixture来源（flag优先或MEM_BUDGET_FIXTURE_DIR env）。未知/矛盾collector来源拒；环境fixture不悄悄改成live。离线成功也明确authorizing_for_live_followup=false、authority_scope=non_authorizing_diagnostic，不能作为原PM现场followup许可。live成功才有该资源维度标记，原PM仍须scope/quota/cancellation；它不是平台签名或自动派发授权。execute-node继续拒fixture flag/env，而且要求同一次共享gate的live authorizing结果。

薄Node executor采用selectors流式收集stdout/stderr合计最多1048576字节（1MiB），超过上限或120秒超时即拒，终止并回收本调用创建的精确Popen子进程。没有外部PID输入、进程名搜索、进程组或用户资源清理；不把timeout当字节上限，不无界capture_output。输出回执记录output_bytes/output_limit_bytes/timeout_seconds。上限仅控制本接口捕获输出内存，不签整个Agent/子进程树/原业务长期RSS。实测小输出、两流合计超限与短测试时限均为tiny隔离Node消费者，不是实际业务执行。

### 8.4 限定 MiniMax 未测 RSS 合同

`bounded_minimax_unmeasured/new_spawn`只供原 PM 单 writer 串行消费；不是默认 lane，也不是通用 heavy 豁免。整 worker 预算至少3GiB、复用折扣0；固定 Node old-space2048MiB + semi-space1MiB的实际 V8 总堆另行读回，不能称整个 worker RSS 硬限制。全机OOM历史与跨PM原子reservation仍未验证。

profile沿 `memory-task-admission.profile.v1`，绑定owned、canonical、nonlink JSON与SHA；示例必要字段：

```json
{
  "schema": "memory-task-admission.profile.v1",
  "task_id": "bounded-preview-task",
  "kind": "bounded_minimax_unmeasured",
  "execution": "new_spawn",
  "oom_history": {"path": "/private/task/oom.json", "sha256": "actual-sha256"},
  "minimax_contract": {"path": "/private/task/minimax.json", "sha256": "actual-sha256"},
  "serial_contract": {"coordinator": "original-pm", "task_id": "bounded-preview-task", "writer_limit": 1, "scope": "original_pm_serial_only"}
}
```

`minimax_contract`原件的exact字段为 `kind=bounded_minimax_contract`、同task_id、`workload=standard_library_preview_or_readonly_routing_no_build_browser_video_server_install`、`rss_measurement=not_measured`、`whole_worker_budget_bytes=3221225472`、`scope_enforcement=original_PM_contract_not_process_sandbox`。OOM原件沿原任务证据接口，并明确`task_only_machine_unknown`；不得用空事件列表宣称全机无OOM。

代表调用沿现入口：设置 `SPAWN_WORKER_MEMORY_TASK_PROFILE=/private/task/profile.json`，将原 `--command` 保持为单层 `bash -lc 'mcode exec --permission full --model provider/model --timeout 20m --max-steps 60 --input - < /private/task/input.txt'`；其他原scope/verification/quota/cancellation门全部保留。早bind→同collector三样本至少20秒→late render→actual exec都核同profile、artifacts、official wrapper/current/release完整闭包/nativeNode/nativeargv/stdin。

安装release必须是canonical releases直接具名子目录，拒`.`/`..`/外部symlink；目录及每个代码、依赖、chunk、native文件/内部link均记录身份及字节摘要。闭包上限10000项/256MiB，native Node单独256MiB；wrapper/launcher16KiB、pointer128B、stdin1MiB，先stat/fstat核cap再流式hash。安装目录与Node更新会拒旧binding，需由原PM重新完整准入，不能将缓存binding当许可。

batch仅接受唯一owned regular nonlink绝对stdin、原生20m/60steps；exec前NOFOLLOW单次open/fstat/hash/lseek/dup2到同fd。hash后仍可能被同uid并发写入，**不是immutable input snapshot**。interactive保留原argv及PTY；没有原生time/steps机械限，回执明确原PM监督。native `--cwd`/配置或目录override拒绝。实际cwd还必须匹配先前spawn isolation pregate的branch/HEAD/common-dir，及late-bound dev/inode/uid/mode；非Git/lightweight没有这组早门证据时拒此profile。

低swap的限定未测合同同样要求完整20秒窗，但`high_swap_exception=false`；legacy pressure仍原值。native critical/unknown、keyword/available warning、不足物理余量、swap账本非法、计数或swapused增长/回退、近期task OOM、预算低于3GiB均拒。fixture来源只供离线诊断，不能授权actualexec。实际任务模型/产物/release与长程峰RSS仍须原PM独立验证；tiny nonce消费者只签固定执行层。


完整入口验证须覆盖最终 launch 分类器对可信内存 guard 的消费，不能只测 `render-launch` 或 `exec-bound`。前置拒绝核零资源创建；晚期身份拒绝核零终端/任务注入，并如实结算或保留已经创建的精确 owned worktree/context，不能把晚期拒绝写成从未产生任何资源。
