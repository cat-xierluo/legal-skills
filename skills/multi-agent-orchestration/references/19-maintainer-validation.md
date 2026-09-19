# 维护者验证矩阵

> 仅在修改本 Skill 的脚本、模板、配置或主文档时读取。日常派发和收口不要加载本文件。

## 1. 模块边界

`spawn-worker.sh` 只保留启动顺序、全局默认值和跨模块编排。下列 sourced 模块不得绕过入口门禁独立执行生产副作用：

- `spawn-worker-flags.sh`：usage 与参数解析。
- `spawn-worker-orca.sh`：Orca runtime 检测、worktree 创建和 terminal 注入。
- `spawn-worker-metadata.sh`：Session Context `METADATA.json` 合同。
- `spawn-worker-provider-lease.sh`：provider lease acquire/finalize/provisional cleanup。
- `spawn-worker-launch.sh`：tmux/Orca 共用启动边界与 supervised 注册。

模块继续使用入口已初始化的全局变量，以保持 CLI 和生命周期语义。结构重构不得顺带改变行为；模块合同测试仍需配合真实入口 smoke。

## 2. 分层验证

先运行与变更直接相关的测试，再运行完整矩阵。Shell 文件必须先做语法检查；Python 入口按受影响范围编译或运行测试。失败不得用后续绿灯覆盖。

```bash
find scripts -type f -name '*.sh' -print0 | xargs -0 -n1 bash -n
python3 -m py_compile scripts/provider_error_classifier.py scripts/orca_rate_limit_recovery.py scripts/test_orca_rate_limit_recovery.py
python3 scripts/test_orca_rate_limit_recovery.py
python3 scripts/test_runtime_settlement.py -v
python3 scripts/test_provider_lease_runtime.py -v
python3 scripts/test_pm_runtime_reconcile.py -v
bash scripts/test-spawn-worker-flags.sh
bash scripts/test-spawn-worker-orca.sh
bash scripts/test-pm-quota-stall.sh
python3 scripts/test-quota-preflight.py
python3 scripts/test-mem-budget-probe.py
python3 scripts/test-quota-summary-zcode.py
bash scripts/test-pm-orchestrate-handoff.sh
bash scripts/test-pm-message-contract.sh
bash scripts/test-pm-reauthorize.sh
bash scripts/test-night-watch.sh
bash scripts/test-spawn-worker-metadata.sh
bash scripts/test-spawn-worker-provider-lease.sh
bash scripts/test-spawn-worker-launch.sh
bash scripts/lint-wait-script.sh
bash scripts/test-dependency-install-guard.sh
bash scripts/test-completion-authority.sh
python3 scripts/test_completion_authority.py
bash scripts/test-pm-cleanup-worker.sh
bash scripts/test-pm-run-bind.sh
bash scripts/test-post-merge-cleanup.sh
bash scripts/test-harness-backend-policy.sh
bash scripts/test-render-runtime-profile.sh
bash scripts/test-worker-command-policy.sh
bash scripts/test-zcode-driver.sh
bash scripts/test-provider-lease.sh
bash scripts/test-spawn-worker-deps.sh
bash scripts/test-spawn-worker-verification.sh
bash scripts/test-dispatch-value-gate.sh
bash scripts/test-worker-value-postflight.sh
bash scripts/test-review-acceptance-gate.sh
bash scripts/test-blocker-recovery.sh
bash scripts/test-orca-wave-lifecycle.sh
bash scripts/test-orca-runtime-identity.sh
bash scripts/test-orca-auto-register.sh
python3 scripts/test_orca_registration_concurrency.py
python3 scripts/test_pm_sender_binding.py
python3 scripts/test_worker_delivery_prompt.py
python3 scripts/test_orca_ask_reply_delivery.py
bash scripts/test-pm-monitor.sh
bash scripts/test-reviewer-scope-guard.sh
bash scripts/test-settle-liveness.sh
bash scripts/test-settle-command.sh
bash scripts/test-recover-unconfigured.sh
bash scripts/test-pr-audit.sh
bash scripts/test-pm-closeout.sh
python3 scripts/test-autopilot-controller.py
python3 scripts/test-autopilot-facts.py
bash scripts/smoke-sentinel.sh
bash scripts/smoke-tmux-worker.sh
bash scripts/smoke-orca-worker.sh
bash scripts/smoke-orca-control-plane.sh
```

## 3. 证据边界

- `smoke-orca-worker.sh` 通过严格只读代理验证真实 runtime 检测和无/错 sender 的前置拒绝，不启动 Agent 或创建 Run。正向单一任务注入与 Wave 复用由隔离套件验证，不使用虚构 handle 作为真实成功证据。
- `smoke-orca-control-plane.sh` 使用 fake CLI 验证命令路由、cursor 与 external terminal accounting。
- `test_worker_delivery_prompt.py` 检查实际 Task spec/启动命令与真实 guard hook 的准入/拒绝，不启动 provider；`smoke-tmux-worker.sh` 使用独立 tmux socket、固定本地脚本与无转发 Orca stub，按真实记录区分 fake 只读探测和 live 调用。
- `test-spawn-worker-orca.sh` 必须同时证明：正常 worktree create 的真实 argv 含 `--setup skip`；`inherit/run` 在任何 worktree、provider lease、Session Context、terminal、Run/Task/Dispatch 副作用前返回 `ORCA_SETUP_REQUIRES_PRELAUNCH_AUTH_CONTRACT`；`--allow-install-command` 不得把门禁后的授权外溢到 repo Setup。
- `test-pm-message-contract.sh` 必须使用当前真实 Dispatch relay 回执形状（`relay.messageId/dispatchId/destination`）和 `check --peek` 行形状（结构化消息的顶层 `run_id/from_handle/to_handle/thread_id`、字符串 payload 内 camelCase lifecycle IDs，以及原生 reply 的 `runId/from/to/threadId` 无 payload 形状），并证明：所有用户可控消息字段的敏感值、非 Orca UUID retry 及冲突恢复摘要在首次 Orca 调用前拒绝；`worker-show` 证明精确 live Run/Task/Dispatch/worker；合同 payload 固定路由、业务 thread、correlation、expected action 与 typed evidence，原生 thread 固定承载 correlation，transport retry 不进入 payload/业务摘要；send receipt 的 message ID 只能来自同一精确 Dispatch relay，并绑定 sender、业务/原生 thread、correlation、可选 Orca retry UUID 与完整请求摘要且只声明 `durably_enqueued`；`inbox` 只用 `check --peek` 且不调用 run-use、send 或 ack，所有出现的顶层及 payload lifecycle/sender/recipient/type 别名必须一致，拒绝缺/错 sender/recipient、缺 Run/归属证据、同 Run 其他 Dispatch 或任一别名冲突。无 payload 的原生关联消息只有在线程双过滤、精确 worker→coordinator 路由和 correlation thread 下可见，receipt 不得据此声明执行过 reply。fake Orca 不证明真实跨 session 可见性或业务执行。
- `test_orca_ask_reply_delivery.py` 用 stateful fake Orca 验证 PM wrapper 的原生 result/message Run 与 alias 一致性、显式 null Delivery、非空 ID 类型、50 条 FIFO 边界、ack 前同批重放、ack 响应内下一批的完整校验与顺序分类、旧/新 Delivery ID 分离、错 ack receipt 失败关闭，以及当前 Orca question 的真实 `dispatch:<dispatch> → run:<run>` 顶层路由、message-id thread、JSON-string Task/Dispatch payload。它还覆盖当前 Delivery 唯一目标、post-reply asker/route/aliases、独立 reply message ID、同 answer 重复 reply 复用原 message，以及跨 Dispatch、显式 null alias、复用 question ID、不同 answer 或冲突 route 的拒绝。`test_worker_delivery_prompt.py` 与安装门禁回归另行证明 Worker 最终 consuming check/自有 Delivery ack、ask resume、`consumer_fenced` 和 `dispatch_inactive` 停止义务进入真实 Task spec，`peek/all/unread` 不被准入，coordinator handle ack 被拒绝。fake 不证明真实 Orca 跨 session 交付；需用隔离 Run/terminal 现场验证消息层，provider 全生命周期仍按下一条标准。
- Session Context 回归覆盖 Claude/Codex、实施者/reviewer 与有无 scope 的六个实际启动命令组合；路径定位变量不证明 guard 激活，Codex 显式 prompt-only 降级必须保持其真实权限状态。
- 只有实际启动 Orca 支持的 Agent 并观察 `worker_done → Delivery → release/精确外部终端结算 → ack`，才能声明该 backend 的 supervised 路径已验证。
- fake-gh、临时 Git 仓和静态审计不能替代真实 GitHub mutation 证据；缺失时标记 `NOT_VERIFIED`。
- 若 Skill Lint 或 Harness 规则命中已知通用误报，保留原始证据和约束说明，不通过命令变形规避扫描。
- 阴性断言必须区分预期无匹配与读取/执行错误；测试自身的故障注入也须能得到非零测试结算。后端策略测试使用隔离 fixture，不通过修改正式授权配置凑绿。
- 锁竞争验收分别观察真实非阻塞锁操作与 CLI 拒绝结果。完整 CLI 的观测/子进程启动耗时不是单独的锁等待；测试防悬挂 timeout 也不是响应性能承诺。

- runtime-settlement 专项 CI 运行只读适配器、绑定 lease 生产方和 PM wrapper 测试，并复跑既有 provider/settle 邻接回归；仅使用隔离合成 RPC，不调用真实 provider 或生产生命周期。
