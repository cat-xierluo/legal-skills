# 原生 ZCode CLI 接入 Orca

## 启动合同

仅在用户指定 `zcode-cli`，且 Orca runtime 为 1.4.218 或更新时，启用本路径。Orca 的 `worker-start --agent zcode` 等待真实首次 composer，再投递唯一 Task spec；它启动交互 CLI，不向 ZCode 传 `--prompt`。后续派发复用已结算且已证明空闲的原终端。

原生 worker-start 没有逐次设置 env/command 的接口。用 Orca 设置 → 智能体 → ZCode 的正式自定义命令配置启动桥，保留 MAO 已通过门禁后生成的环境、Session Context 与 authority 绑定。使用绝对路径：

```text
python3 /absolute/skill/scripts/zcode-orca-launcher.py launch --requests-root /private/launch-requests --default-zcode /absolute/bin/zcode --
```

请求目录必须是当前用户所有、0700、无符号链接的独立目录。保留用户原有默认智能体、模型、启动参数、权限和 hooks。普通工作区没有对应请求时沿用原生 ZCode 参数；存在匹配请求却无效、过期、冲突或已消费时拒绝，不自动改走裸 CLI。桥不读取私人账号库、不复制认证、不选择账号或耗卡。

## 派发与接续

先按 [派发profile合同](32-dispatch-profiles.md) 核实官方桥并在个人配置启用。已指定 `--worker-backend zcode-cli` 且使用auto时，入口自动取得requests root并选择supervised；仍须完整Task、runtime/coordinator、验证与scope合同。缺失/禁用个人桥配置在资源副作用前拒绝，不静默落入通用入口。

保留旧显式配方；在原有 spawn 参数中加入：

```text
--worker-backend zcode-cli --orca-supervised
--orca-zcode-native-requests /private/launch-requests
--allow-prompt-only-install-guard "用户已指定 ZCode CLI，此任务允许 prompt-only 安装边界"
```

旧配方的native参数须成对提供。auto现会选择已配置原生桥；要测试通用兼容入口，必须显式 `--dispatch-profile orca-generic`，不会根据native失败自动回退。通用 `terminal create → tui-idle → worker-start --terminal` 仍可能在首次composer前停在readiness。长程 ZCode 使用上面的原生桥，不改用 headless。已失败的原 Task 按其 native receipt 和 residualResources 恢复，不为补 native 参数再次注入完整任务。

继续提供完整 Task spec、verification contract、精确允许范围与 coordinator/runtime 身份。全部价值、额度、内存、provider lease、工作树隔离与 authority 门通过后才创建单次请求。请求绑定实际工作树、Session Context、启动脚本和 authority 摘要以及 runtime；启动桥原子消费并核对原生 terminal/worktree 身份，native start 回执必须与其相同。启动回执中的 `created` 只证明本轮创建。结算前重读 live ownership；原生用户接管后的 `user_owned/retained` 由 release 保护，不能靠旧 metadata 宣称仍可自动关闭。不得把 terminal close 当作 worker-release 的替代。

模型来自 ZCode 的原生配置；Orca 不接受 ZCode 的 `--model`。按 [BigModel 模型合同](28-zcode-cli-bigmodel-coding-plan.md) 在原生会话操作 `/model`，用真实请求证据确认模型和 provider。账户调度仍依 [本地 Skill 调用合同](29-local-account-routing-skill.md) 获取新鲜结果；启动校验不代表长期身份锁或持续预算控制。

收到合法 `worker_done` 后先验收真实结果。立即接续时，按当前 Orca 运行时指南把已证明的原终端移交给新 Dispatch；否则执行 worker-release，核对实际回执，再 ack 完整 Delivery。release 对用户接管终端返回 retained 时，记录保留原因；仅在用户明确授权精确终端后另行关闭并保留日志，不能绕过保护。STATUS、idle、commit、输入 accepted 均不能代替这条链。派发失败或结果不确定时保留 native receipt 和 residualResources，按原请求身份恢复，不自动重拉或双投。

已有 long-lived 工作树且没有原 MAO Session 时，仅按 [显式借用入口](31-borrowed-existing-worktree.md) 创建新 Session；普通 `--worktree` 不能复用，恢复命令不适用于首次接入。

## 已关闭原 Session 的具名恢复

当前实测边界（2026-10-03）：Orca 1.4.218 / ZCode CLI 0.16.9（runtime 3.14.3）的空输入恢复可启动，但原生CLI会改写进程title与argv，公开terminal的agentIdentity仍null，现有身份门无法证明它。此组合保持`CONTINUATION_NOT_READY`；不执行新的prepare/open/register，先取得正式runtime识别与原生进程身份的受审支持。以下命令保留为受限恢复合同，不能据模拟通过宣称真实已接通。

已有状态为`launched`、绑定确切terminal与runner PID的意图只做只读诊断：

```bash
python3 scripts/zcode_closed_recovery.py diagnose --intent "$RECOVERY_INTENT"
```

报告固定`diagnostic_only=true`、`ready_for_retry=false`，核原绑定、当前owner和持久模型，指出closed、缺失agentIdentity、title改写或argv不符。它不修改intent、路由或业务状态。已关闭的单次意图不能重open；日志/SID、进程标题和Node内核路径均不能单独替代真实Agent/Session归属。后续恢复由原PM沿原卡和累计失败预算验收，真实请求/计费仍待证。

首次启动桥不接纳已消费Session或旧terminal。原失败Task的关闭恢复单独使用`zcode_closed_recovery.py`，不走`reauthorize`或`reset-failed`。原PM先核原任务卡、剩余episode预算和具名providerSession来源；恢复只创建空业务输入的原生`--resume sess_… --mode yolo`会话，不新建Task。

按原PM冻结的真实绝对路径和目标模型执行：

```bash
python3 scripts/zcode_closed_recovery.py prepare \
  --metadata "$ORIGINAL_METADATA" --authority "$ORIGINAL_AUTHORITY" \
  --failed-dispatch "$FAILED_DISPATCH" --provider-session "$ORIGINAL_PROVIDER_SESSION" \
  --provider "$EXPECTED_PROVIDER" --model "$EXPECTED_MODEL" --effort "$EXPECTED_EFFORT" \
  --orca-bin "$ORCA_BIN" --zcode-bin "$ZCODE_BIN" --zcode-entry "$ZCODE_ENTRY" \
  --zcode-node "$ZCODE_NODE"
python3 scripts/zcode_closed_recovery.py open --intent "$RECOVERY_INTENT"
python3 scripts/zcode_closed_recovery.py verify --intent "$RECOVERY_INTENT"
```

`prepare`核原authority/completion与初始→后继失败attempt同runtime/run/旧terminal/process的公开链；只接受正向退出与旧cap撤销证明。`RECOVERY_INTENT`必须取本次真实输出，不自行拼接。`open`在新鲜内存准入后只恢复精确Session；`verify`核新terminal/incarnation、实际native进程argv和只读SQLite里的唯一主Session、worktree、yolo、provider/model/effort。数据库缺失、模型不符、未知/live旧目标或身份漂移均拒绝。持久化模型选择不证明实际请求或计费；Orca尚未报告providerSession时明确记录`NOT_ORCA_PROVIDER_PROVENANCE`，不伪造其字段。

通过后由原业务PM将原已核完整register参数与以下参数合用，单次调用：

```text
--task-id FAILED_TASK --terminal-handle RECOVERED_TERMINAL
--metadata-file ORIGINAL_METADATA --authority-receipt ORIGINAL_AUTHORITY
--retry-of FAILED_DISPATCH --closed-recovery RECOVERY_INTENT
```

继续传原run、当前合法coordinator、runtime与worktree身份；不传旧完整输入，不以`--task-spec`造新Task。该入口核模型后采用公开同failed Task `worker-start --retry-of`，将真实新Dispatch的process/cap摘要绑定到原完成路径并更新路由，保留原authority及attempt历史。恢复意图一次消费；不确定或post-start采用失败时保留真实回执与资源，只对账，不重发业务。原PM负责业务独验及预算记账；模拟通过不能代签DSH原022实际恢复。 业务已接受而本地采用被中断时，读取同意图状态：处于`adopting`时用`rollback --intent`复核并恢复原路由；已经`adoption_failed_rolled_back`时直接用`adopt --intent ... --new-dispatch ...`采用意图中记录的同一个新Dispatch。实时身份或当前文件状态未知时拒绝，禁止再次register。本地文件事务与跨系统业务完成分别验收。

## 单 worker 权限与 CLI 接续

启动前按任务选权限模式。新隔离worker的renderer与spawn默认命令均明确使用 `yolo`；需要收紧时显式选择 `build/edit/plan`。`build`的普通workspace写入与有副作用Bash通常要求审批。`edit` 允许普通workspace编辑，Bash仍按build判断；`plan`限制有副作用工具；`yolo`可减少普通写入和Bash确认，但需要用户交互、alwaysAsk与plan状态仍有例外。yolo不能提供机械scope/install保护，也不能把普通项目deny规则当作它的范围护栏。

只对已授权、隔离、唯一writer的新任务应用默认模式或显式收紧。保持Orca全局设置；`--permission-mode`是renderer的参数，spawn没有此参数，ZCode原生拼写为`--mode`：

```bash
rendered_command=$(bash "$MAO/scripts/render-runtime-profile.sh" \
  --backend zcode-cli --mode interactive --bin "$APPROVED_ZCODE_BIN" \
  --permission-mode yolo --output command)

bash "$MAO/scripts/spawn-worker.sh" "${APPROVED_SPAWN_ARGS[@]}" \
  --worker-backend zcode-cli --command "$rendered_command" \
  --orca-supervised --orca-zcode-native-requests "$APPROVED_REQUESTS_ROOT" \
  --task-spec "$(cat "$APPROVED_TASK_SPEC_FILE")" \
  --allow-prompt-only-install-guard "$APPROVED_PROMPT_ONLY_AUTHORIZATION"
```

`APPROVED_SPAWN_ARGS`表示原已核对的project/branch/session、scope、verification、认证环境、runtime/coordinator等完整参数数组，不与示例参数重复。复用既有Task时继续提供原run/task/coordinator身份；不新建重复任务或认证副本。匹配请求执行被冻结的launch，Orca附加启动参数不覆盖该command。模型仍按原生 `/model` 合同选择。

已投递任务遇到审批时，用正式CLI读取精确状态，不通过Computer Use推进：

```text
orca terminal show --terminal EXACT_HANDLE --json
orca terminal read --terminal EXACT_HANDLE --screen --json
orca orchestration worker-show --dispatch EXACT_DISPATCH --json
```

`permission_wait`只是PM标签；正式观测为`agentWait`对象、reason/source及真实screen。null仅表示本次未发现等待，字段缺失表示未知；也可能是问题、信任或更新。核terminal/Dispatch/incarnation、原工具命令与当前选项。仅对已批准的原请求，用独立单键移动并每次重读，确认高亮Allow once再Enter：

```bash
orca terminal send --terminal "$EXACT_HANDLE" --text $'\e[A' --json
# 重新读取screen；仅在确实需要再移动时单独发送下一次Up。
# 确认同一请求且高亮Allow once后：
orca terminal send --terminal "$EXACT_HANDLE" --enter --json
```

不要固定发两次Up、盲Enter或选择Always allow。输入accepted仅证明运输，继续读取原请求消失、原调用恢复；身份/命令改变或结果不确定时只读检查。审批不重发业务Task、不创建新worker；续行后重读live ownership，继续唯一worker_done/Delivery/验收/release/ack。若仅因外层sandbox无法访问IPC，应依宿主权限流程运行CLI；不据此重启Orca。

历史2.32.0真实任务使用build并通过CLI逐项审批。2.33.1默认改为yolo，参数消费者与本机原生权限验证以当前TASKS验收记录为准；不得把历史build验收改记为yolo任务成功。具体实现边界依本机匹配版本，勿将权限模式当成新的任务授权。

## 验证状态

Orca 1.4.218 的真实 native 启动与两阶段只读任务已通过：同一 CLI/session/Dispatch 在 Flash 阶段完成35项测试，再经原生 `/model` 切至 GLM-5.3，消费正式指导、完成3项定向反例并发出唯一 `worker_done succeeded`；PM验收 Delivery、执行 release、再 ack。真实 release 返回 `retained/user_takeover`，保护当前 user_owned 终端；coordinator-owned 自动关闭仍 `NOT_VERIFIED`，随后用户具名授权关闭测试终端，真实退出与研究副本清理已确认，日志和绑定归档保留。启动 created、idle 或静态测试不能扩大此结论。以 TASKS 的 ZCODE-ORCA-NATIVE-INTEGRATION 卡维护最新结果，不类推其他后端。

## 官方依据

[Orca 1.4.218 发布记录](https://github.com/stablyai/orca/releases/tag/v1.4.218) 列入 `fix(zcode): wait for composer before first worker dispatch`。每次操作仍读取当前可执行文件 `orca skills get orchestration` 的匹配版本合同，不靠版本号类推其他后端或新的参数。
