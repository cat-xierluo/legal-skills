# 原生 ZCode CLI 接入 Orca

## 启动合同

仅在用户指定 `zcode-cli`，且 Orca runtime 为 1.4.218 或更新时，启用本路径。Orca 的 `worker-start --agent zcode` 等待真实首次 composer，再投递唯一 Task spec；它启动交互 CLI，不向 ZCode 传 `--prompt`。后续派发复用已结算且已证明空闲的原终端。

原生 worker-start 没有逐次设置 env/command 的接口。用 Orca 设置 → 智能体 → ZCode 的正式自定义命令配置启动桥，保留 MAO 已通过门禁后生成的环境、Session Context 与 authority 绑定。使用绝对路径：

```text
python3 /absolute/skill/scripts/zcode-orca-launcher.py launch --requests-root /private/launch-requests --default-zcode /absolute/bin/zcode --
```

请求目录必须是当前用户所有、0700、无符号链接的独立目录。保留用户原有默认智能体、模型、启动参数、权限和 hooks。普通工作区没有对应请求时沿用原生 ZCode 参数；存在匹配请求却无效、过期、冲突或已消费时拒绝，不自动改走裸 CLI。桥不读取私人账号库、不复制认证、不选择账号或耗卡。

## 派发与接续

在原有 spawn 参数中显式加入：

```text
--worker-backend zcode-cli --orca-supervised
--orca-zcode-native-requests /private/launch-requests
--allow-prompt-only-install-guard "用户已指定 ZCode CLI，此任务允许 prompt-only 安装边界"
```

继续提供完整 Task spec、verification contract、精确允许范围与 coordinator/runtime 身份。全部价值、额度、内存、provider lease、工作树隔离与 authority 门通过后才创建单次请求。请求绑定实际工作树、Session Context、启动脚本和 authority 摘要以及 runtime；启动桥原子消费并核对原生 terminal/worktree 身份，native start 回执必须与其相同。启动回执中的 `created` 只证明本轮创建。结算前重读 live ownership；原生用户接管后的 `user_owned/retained` 由 release 保护，不能靠旧 metadata 宣称仍可自动关闭。不得把 terminal close 当作 worker-release 的替代。

模型来自 ZCode 的原生配置；Orca 不接受 ZCode 的 `--model`。按 [BigModel 模型合同](28-zcode-cli-bigmodel-coding-plan.md) 在原生会话操作 `/model`，用真实请求证据确认模型和 provider。账户调度仍依 [本地 Skill 调用合同](29-local-account-routing-skill.md) 获取新鲜结果；启动校验不代表长期身份锁或持续预算控制。

收到合法 `worker_done` 后先验收真实结果。立即接续时，按当前 Orca 运行时指南把已证明的原终端移交给新 Dispatch；否则执行 worker-release，核对实际回执，再 ack 完整 Delivery。release 对用户接管终端返回 retained 时，记录保留原因；仅在用户明确授权精确终端后另行关闭并保留日志，不能绕过保护。STATUS、idle、commit、输入 accepted 均不能代替这条链。派发失败或结果不确定时保留 native receipt 和 residualResources，按原请求身份恢复，不自动重拉或双投。

已有 long-lived 工作树且没有原 MAO Session 时，仅按 [显式借用入口](31-borrowed-existing-worktree.md) 创建新 Session；普通 `--worktree` 不能复用，恢复命令不适用于首次接入。

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
