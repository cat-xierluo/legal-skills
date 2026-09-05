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
bash scripts/test-spawn-worker-flags.sh
bash scripts/test-spawn-worker-orca.sh
bash scripts/test-pm-quota-stall.sh
python3 scripts/test-quota-preflight.py
bash scripts/test-pm-orchestrate-handoff.sh
bash scripts/test-night-watch.sh
bash scripts/test-spawn-worker-metadata.sh
bash scripts/test-spawn-worker-provider-lease.sh
bash scripts/test-spawn-worker-launch.sh
bash scripts/lint-wait-script.sh
bash scripts/test-dependency-install-guard.sh
bash scripts/test-pm-cleanup-worker.sh
bash scripts/test-harness-backend-policy.sh
bash scripts/test-render-runtime-profile.sh
bash scripts/test-worker-command-policy.sh
bash scripts/test-zcode-driver.sh
bash scripts/test-provider-lease.sh
bash scripts/test-spawn-worker-deps.sh
bash scripts/test-dispatch-value-gate.sh
bash scripts/test-worker-value-postflight.sh
bash scripts/test-review-acceptance-gate.sh
bash scripts/test-blocker-recovery.sh
bash scripts/test-orca-wave-lifecycle.sh
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

- `smoke-orca-worker.sh` 只验证真实 runtime 检测，不启动 Agent。
- `smoke-orca-control-plane.sh` 使用 fake CLI 验证命令路由、cursor 与 external terminal accounting。
- 只有实际启动 Orca 支持的 Agent 并观察 `worker_done → Delivery → release/精确外部终端结算 → ack`，才能声明该 backend 的 supervised 路径已验证。
- fake-gh、临时 Git 仓和静态审计不能替代真实 GitHub mutation 证据；缺失时标记 `NOT_VERIFIED`。
- 若 Skill Lint 或 Harness 规则命中已知通用误报，保留原始证据和约束说明，不通过命令变形规避扫描。
