# Runtime/resource 结算

用于长周期 supervised 运行的证据核对。先冻结实际 Run、Task、Dispatch、Worker、terminal、worktree、Session 和 provider lease，再从已捕获的命令响应推导结算状态。文件一致性验证不替代可信观察者或有权限的 coordinator。

## 1. 捕获与复算

按 `../templates/runtime-settlement-binding.example.json` 冻结身份。区分初始观察者 runtime、Worker 的 `runtime_epoch` 和 `process_incarnation`；新一轮捕获另填 request 的 `observer_runtime_id`。同一捕获的 RPC 响应必须来自同一个 runtime，不能拼接不同代的状态。

原始命令证据采用 `../templates/runtime-settlement-command.example.json`：精确 argv、退出码、带时区时间、stdout/stderr 相对路径和 SHA-256。用 `../templates/runtime-settlement-request.example.json` 关联绑定与命令。保留完整原件在受信的本地证据目录；不要把带任务正文的响应发布到公共仓库。

```bash
python3 scripts/runtime-reconcile.py observe --request /absolute/evidence/request.json \
  --output /absolute/evidence/snapshot.json
bash scripts/pm-orchestrate.sh reconcile --snapshot /absolute/evidence/snapshot.json \
  --output /absolute/evidence/receipt.json
python3 scripts/runtime-reconcile.py verify --receipt /absolute/evidence/receipt.json
```

三个入口均不发送 RPC、启动进程、修改 Task、释放资源或 ack。`observe` 读取已有命令响应，`reconcile` 生成推导收据，`verify` 重新读取 request 和全部原始证据。相同输出幂等，不同内容不得覆盖。文件缺失、哈希漂移、重复 JSON 键、身份混用或符号链接路径使入口非零退出。

退出码 0 表示证据可复算；检查 `complete` 才能判断完整结算。合法的 `UNSETTLED` 也可退出 0，必须保留 `missing_evidence` 和 `next_actions`。所有恢复动作仅为建议，由有权限的 owner 按现有控制协议执行后重新捕获。

## 2. 结算条件

| 维度 | 必需证据 |
| --- | --- |
| 运行身份 | Run/Task/Dispatch、Worker epoch/incarnation、terminal/worktree 与冻结绑定一致；全部成功 RPC 的观察者 runtime 一致 |
| 逻辑终态 | Task 和 Dispatch 的终态一致；`Task ready + Dispatch failed` 不完成 |
| terminal | 精确归属的 terminalResource 已释放；missing、abandon 或 capability 撤销单独不足 |
| provider lease | 已声明无需 lease，或精确 allocation 的原记录与真实释放收据一致；文件消失不算释放证明 |
| Delivery | 整批消息得到处理，目标 worker_done 与运行结果一致，ack 的目标 Delivery ID 明确确认 |

`worker_done` 路径不得声明无需 Delivery。只有明确的 terminal-loss 恢复才允许该例外；它仍须完成逻辑及资源结算。批次含其他 Task/Dispatch 消息时，不能仅处理当前 Worker 就代替整批完成。

Orca 的 ack 响应中 `acknowledged` 对应已确认的 Delivery；响应 `deliveryId` 可能是下一批，不能混用。Run consumer generation 与 Worker generation 分别核对，不根据当前 runtime 猜测旧 Run 已可接管。

## 3. Provider lease 证据

使用新增的绑定/释放入口生成真实收据。先将实际活跃 lease 与冻结 runtime binding 关联，再保全绑定后的原记录：

```bash
python3 scripts/provider-lease.py bind-runtime --root /absolute/provider-leases \
  --lease-file /absolute/provider-leases/provider/session.json --session session-1 \
  --runtime-binding /absolute/evidence/binding.json
```

该命令返回 `lease_record_sha256` 和唯一的 `release_receipt_path`。将原 lease 另存为捕获目录下的小型证据件，核对哈希；运行资源结算后，原样使用返回路径释放：

```bash
python3 scripts/provider-lease.py release --root /absolute/provider-leases \
  --lease-file /absolute/provider-leases/provider/session.json --session session-1 \
  --resource-settled --orca-cli /absolute/path/to/orca \
  --runtime-binding /absolute/evidence/binding.json \
  --release-receipt /absolute/provider-leases/.runtime-release-receipts/BINDING_SHA256.json
```

最后一个路径是前一步实际返回值，示例中的 `BINDING_SHA256` 不可原样使用。保存命令退出码、stdout、stderr 和释放收据供观察器读取。绑定后的 lease 在显式释放前保守占用额度，不能被旧终端句柄扫描自动回收；释放入口自身也核实精确 Worker 的资源后态。

重试必须沿用原释放收据。只有 lease 文件已不存在而没有原收据时，不得推定释放成功。旧未绑定 lease 继续兼容既有生命周期；不能将历史缺文件升级为新结算事实。

## 4. 事实来源与边界

原始字段形状核对于本机 Orca 1.4.197：`out/cli/handlers/orchestration/message-check-handler.js`、`message-inbox-handlers.js`、`worker-terminal-handlers.js` 及 `out/main/index.js`。主模块 SHA-256 为 `a60fbf4dd11a08f21c9cf8f37219a398e02f2b286b6fdbd2081006ff6d4e8f4d`。不复制第三方实现正文；短 fixture 由测试独立构造。

本次验收覆盖真实 CLI 的本地证据处理及隔离假 RPC，真实 provider 计费、生产 release/ack 和旧 Run 权限恢复仍为 `NOT_VERIFIED`。没有 coordinator 权限的旧 Run 继续输出未结算及人工动作，不自动 takeover。Harness 可冻结本适配器并保存复验结果，评测质量和归档许可由其自己的事实与结算门决定。

## 5. 本轮验收（2026-09-11）

- 真实入口专项：适配器 20、绑定 lease 7、PM wrapper 4 项通过。
- 邻接兼容：旧 provider lease 8、spawn provider lease 17、settle liveness 10、settle command 14 项通过；总计 80 项。
- 独立前向审查：252 条断言、192 次 CLI 调用通过，覆盖正常 worker_done、Round27 等价矛盾及恢复后态、quota park、provider 无效运行、递归漂移、并发与归档。测试只使用自造短 fixture 和隔离 RPC shim。
- 两条原反例已修：过滤后的 Delivery 列表不能作为整批完成；lease 收据内部的 worker-show 必须从嵌入原始 stdout/stderr 复算，不能只校验哈希格式。另保留一次夹具 ack 时间早于真实隔离释放的失败，修正夹具时序后复测通过。
- 全脚本语法检查通过。安全扫描 0 critical/high；Harness 静态审查仍报基线旧文件 8 hard，涉及旧清理/配置/测试规则，本轮未新增，不声称整项全绿。

最终受审生产文件 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| scripts/runtime_settlement.py | `6ca9c93e3394f0013a6bae627eba3d5573de19a8e4299d6daf39dae8d7fab08d` |
| scripts/runtime-reconcile.py | `e79b3dfabc421b2e106691994708635e3e9757ab033606fd242ae3160fdb6bcd` |
| scripts/provider-lease.py | `5e38f621fc546614c99128dd43092c7bbe1f42ec23f5234bd227b7a87688463d` |
| scripts/pm-orchestrate.sh | `7a194ad9a34b70fe7b2fed07cd416af88eb8f3f3ed48510b8b283c4768728642` |

专项 CI 定义在 `.github/workflows/orchestration-runtime-settlement.yml`，检查绑定当前 PR head。提交/合并结果以 GitHub PR 和其检查记录为准。
