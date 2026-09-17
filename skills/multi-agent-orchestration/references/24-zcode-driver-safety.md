# ZCode Worker Driver 安全底座（TASK-2026-09-13-ZCODE-DRIVER-SAFETY）

> 配套脚本：`scripts/zcode-worker-driver.py`（重构）、
> `scripts/test-zcode-driver.sh`（契约测试，27 项）、
> `scripts/test_zcode_driver_safety.py`（故障注入，59 项，全部真实
> driver+stub 进程）。上游背景见 references/09-zcode-cli-worker.md。

## 0. 定位与边界

本轮是 zcode worker 安全底座，为后续"社区同会话控制器"与"Start 宿主桥"
接线做前置，**不宣称打通 Start/Weekend、官方远控或机器控制**。官方
0.16.5 `app-server` 不接受 `--settings`，因此本 driver 在该版本上以
`UNSUPPORTED_CONFIG_ISOLATION`（退出码 68）失败关闭，**不能作为默认
worker 入口部署**；待支持 `--settings` 的社区运行时（另立合同）接入后
可直接复用本 driver。

## 1. 启动就绪屏障（readiness barrier）

旧版行为：create 返回即 flush backlog、setModel 失败仅警告并回退全局
模型——存在"套餐错用"风险（任务文本进了未验证的模型会话）。

新版状态机：

```
create → setModel(仅 --model 时) → session/read
       → 实际 {providerId, modelId} 与冻结期望完全一致 → READY → drain
```

- 期望 modelRef 在启动时**冻结**：有 `--model` 用其解析值；无 `--model`
  用私有 settings `model` 字段的完整 `providerId/modelId`（不再"无
  --model 就不校验"）。
- 任何 create/setModel/read 错误、响应畸形、超时（`--bootstrap-timeout`，
  默认 45s）、模型不符 → 退出码 65，**0 条任务文本发出**，排队输入丢弃
  并显式报告，绝不回退到其他模型、绝不标 READY。
- 早到 PM 文本排队，READY 后按序 drain（drain 完才置 ready 事件，无
  乱序/搁浅窗口）；启动期 `/status /stop /compact /quit` 是控制指令，
  **绝不作为会话文本送给模型**。`/quit` 与 EOF 若在有未 drain 输入时
  到达，先等待启动结论（有界），再正常关闭。

## 2. 私有配置隔离（显式入口，失败关闭）

- `--settings <path>` 是**唯一**配置入口：调度方提供的 per-worker 私有
  settings 文件（0600；group/world 可读直接退出 64）。driver 把它以官方
  `--settings` 旗标传给子 CLI（绝对路径——官方 loader 对相对路径按子进程
  自身 cwd 解析）。
- driver **永不**读写共享 `~/.zcode/cli/config.json`、**永不**在退出时
  恢复/改写全局模型（旧版 `restore_global_model` 已删除，不存在
  last-writer-wins 写路径）、**永不**重定向 HOME 或用环境变量注入配置。
  旧 `ZCODE_CLI_CONFIG` 环境变量支持已移除：官方 bundle 无此字面键，
  它只影响 driver 自身读配置、从未隔离子进程（这正是被修复的错用面）。
- **官方 0.16.5 实证**（PM live 回执 2026-09-13）：`app-server --settings`
  报 `Unknown option --settings` 退出 1（`--help` 列出的该旗标属于其他
  入口）。driver 识别该子进程输出，打印 `UNSUPPORTED_CONFIG_ISOLATION`
  行并以退出码 68 结束，0 条协议流量。
- 隔离范围声明：`--settings` 只隔离**用户 settings 层**。会话 DB
  （`~/.zcode/cli/db/`）、桌面认证存储（`~/.zcode/v2/`）、工作区内项目级
  `.zcode` 配置**不在**此隔离范围内（项目层配置位于 PM 控制的 worktree
  内，属可接受残留并在此明示）。
- 语义参考（静态）：官方 bundle 的用户配置解析为
  `tI() = ws("~/.zcode/cli") + "config.json"`，`ws()` 经 `os.homedir()`
  展开 `~`；显式传入路径走 `path.resolve`。本轮未对真实 bundle 做
  live 配置加载验证（`NOT_VERIFIED`）。

## 3. 权限模式显式化

- `--mode build|edit|plan|yolo`，默认 **build**（安全默认：无交互权限
  客户端时变更类工具被拒）；`yolo` 仅显式传入（无人值守，等同
  bypassPermissions 风险级）。旧版硬编码 `"mode": "yolo"` 已移除。
- 反向权限请求（`interaction/requestPermission`、`requestUserInput`、
  `requestOfficialMcpAuthHeaders`）及一切未知 server→client 请求：
  回**可识别错误帧**（-32601 + "driver does not support …"），绝不猜
  成功回包、绝不静默放行；对应工作随拒绝停止，不会挂死 15s。本次未
  获得完整可靠的权限应答 schema，故一律拒绝（`NOT_VERIFIED`：真实
  权限流程交互）。

## 4. Start/Weekend runtime headers：失败关闭

- `interaction/requestProviderRuntimeHeaders`（含 `captcha-retry`）按
  官方 fail-closed 通道回 `{headersApplied: false, errorMessage: …}`——
  bundle 静态证据（`EKi`/`nAt` strict zod）表明该 false 会使模型请求
  结构化失败（-32031），**错误不等于完成**。
- 未接正式宿主桥的 driver 明确**不具备**该能力：不采集/输出/转发/缓存
  验证码、header、票据材料；宿主桥是另立的合同。

## 5. 输出卫生（脱敏 ≠ 截短）

- 所有渲染行经单一出口 `emit()`：先结构化掩码（`mask_value`：header
  块/凭证键），再文本正则脱敏（bearer/sk-/authorization/cookie/apiKey/
  password…），最后限长。**截短从不替代脱敏**。
- 未知通知只打印方法名 + 参数**键名**（值永不渲染）；`state.updated`
  只渲染白名单字段（status/reason）；子进程非 JSON 行（含 stderr 合流）
  同样先脱敏再限长。

## 6. 有界关闭与精确 child 句柄

- `/quit`：发 `session/close`，有界等待 ack（`--close-timeout`，默认 5s）
  → 精确句柄 SIGTERM → 3s 等待 → SIGKILL → 等待；**绝不按进程名
  kill**。ack 确认（或从未建会话）才退出 0，未确认退出 70。
- EOF（tmux pane 被杀）：有界 teardown，退出 0。
- SIGINT→130 / SIGTERM→143：信号驱动有界结算。
- 子进程异常退出：退出 66；启动期拒绝 `--settings`：退出 68。
- 读线程**不再 `os._exit`**：子进程死亡置事件，由主线程统一结算清理。
- request id 与 pending 表加锁（读写双线程安全）；写帧经 write_lock
  串行化。

## 7. 退出码一览

| 码 | 含义 |
|---|---|
| 0 | /quit 干净关闭（close 确认或无会话）/ EOF 有界 teardown |
| 64 | 配置错误（--mode/--settings/--bin/--cwd、权限过松、modelRef 不可用） |
| 65 | 启动未验证（create/setModel/read 错误、超时、畸形、模型不符），0 条任务 |
| 66 | 子进程异常退出 |
| 68 | UNSUPPORTED_CONFIG_ISOLATION（官方 0.16.5 拒绝 --settings） |
| 70 | /quit 的 close 未在限时内确认 |
| 130/143 | SIGINT/SIGINT 结算完成 |

## 8. 验证与未验证范围

已验证（stub 真实进程，两套件 86 项全绿）：

- setModel 延迟/失败、read 回读不符、无回包、无 create → 65 + 0 发送；
- 早输入按序 drain、控制指令永不入会话、延迟 /quit 不丢 drain；
- 双实例并发各自验证各自模型、settings 源文件字节不变；
- 恶意子进程改写自己拿到的 settings（写入落在私有文件，全局配置不在场）；
- 68/66/70/130/0 各关闭路径有界；
- 敏感字段脱敏（token/cookie/ticket/apiKey）、未知通知只出键名、
  runtime-headers fail-closed 回包、权限请求可识别拒绝。

`NOT_VERIFIED`（本轮明确不声称）：

- 真实 provider 上的任何请求（0 模型请求、0 凭证使用）；
- 官方 bundle 的 `--settings` 配置加载行为（已知反而被拒）与任何真实
  隔离效果；支持该旗标的社区运行时尚未接入；
- 桌面宿主 / Start 宿主桥 / 官方远控 / MAO ZCode supervised 链路；
- `spawn-worker.sh` 默认命令仍指向本 driver——**在官方 0.16.5 上会
  得到 68**，需 PM 决策切换条件（不在本任务 4 文件范围）。

## 版本记录

- 2026-09-13：随 TASK-2026-09-13-ZCODE-DRIVER-SAFETY 新增。driver
  就绪屏障/显式隔离/安全 mode/脱敏/有界关闭落地；官方 0.16.5 拒绝
  --settings 的失败关闭路径（68）与 PM 实测回执入库。
