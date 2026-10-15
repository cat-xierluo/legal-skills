# settle liveness gate fixtures

这些 fixture 来自真实 Orca 1.4.180 `orca orchestration worker-show --dispatch <D> --json` 输出（dispatch ctx_2a4f1a0679b6，completed/settled 状态）。

- `worker-show-exited.json`：完整包装（`_meta/id/ok/result`）的真实响应。`.result.observation.status = "missing"`（observation 在 release 后被 GC，不是 "exited"——exited 是窄生命周期窗口值）。`.result.worker.state = "succeeded"`。**注意**：这是 completed dispatch 的快照；真正死锁 dispatch（worker 死、dispatch dispatched）的 observation 语义未真测，gate 逻辑保守地只拒绝 active/input_accepted。
- `worker-show-active.json`：基于 exited 改 `.result.observation.status = "active"` + `.result.worker.state = "active"`（模拟活 worker）。
- `worker-show-missing.json`：基于 exited 删 `.result.observation` + `.result.worker.state`（模拟 schema 变/字段缺失）。

测试（test-settle-liveness.sh）用这些完整包装 fixture 验证 settle_liveness_check 的 jq 路径（`.result.*`）和 gate 逻辑。
