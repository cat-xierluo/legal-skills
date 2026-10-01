# 独立 ZCode CLI 与 BigModel Coding Plan

## 适用范围

本说明针对 `zcode-cli` backend 的原生 `zcode` TUI／`--prompt`。2026-09-30 实测本机安装的 runtime 3.14.3，内置 agent help 版本 0.16.9；两者不是同一个版本号。旧 `zcode` backend 的 app-server driver 继续遵守 ref 24，不能把以下独立 CLI 结果当作其验证结果。

新增支持仍只在用户指定时选用，不进入日常派发池。2026-09-30 的探针仅研究模型与套餐通道；2026-10-01 的文件任务另见下文，不自动修改用户共享默认模型、复制认证到 worker 或建立新的派发权限。

## 模型与认证契约

新版模型供应商配置为 `~/.zcode/v2/provider_config.json`，默认模型放在 `config.defaultModelSelection`。旧 `~/.zcode/cli/config.json` 的 `builtin:bigmodel-coding-plan/...` 不能覆盖已有新版默认模型。本机新版默认明确是 `minimax/MiniMax-M3`，并不是 ZCode 产品固定默认 MiniMax。

个人套餐 provider 为 `account:bigmodel-individual-coding-plan`；模型使用官方大小写 `GLM-5.3` 或 `GLM-5.3-Flash`。不要混用 `bigmodel-api`（API Key 通道）、`account:bigmodel-start-plan`（体验套餐）、团队或闲时套餐。

原生独立 CLI 的账号读取与 app-server 不同：

- TUI／`--prompt` 初始化 standalone account source，从共享凭证库读取该 provider 的 identity 与对应 Coding Plan API Key；每次请求前回读同一关联，使用已存在的套餐凭证。
- app-server／agent-server 等待宿主通过 `provider/updateAccountConfig` 提供账号权限；直接启动不会把上述 standalone 账号自动装载进去。单纯设置同一个模型 providerId 不够，也不应伪造 `entitled` 或应答宿主认证请求。
- 本机已有对应个人套餐 secret，却缺少新版 CLI 的 identity 关联。未修复的原始副本与补齐关联的隔离副本分别做 TUI 对照；后者才可选择 BigModel。隔离实验只关联已有凭证，未生成新密钥、未改用户原件。此实验不作为自动迁移脚本或通用认证修复配方。

配置默认模型时必须带该模型支持的 `options.reasoningLevel`。实测只填 provider/model、漏掉 reasoning 时，CLI 不报启动错误，而从 registry 选择第一个可用模型：要求 Flash 的实验实际用了 GLM-5.3。补齐 `reasoningLevel: max` 后，真实请求记录确认使用 Flash。**不能把配置值或退出码 0 当作实际模型选择证据。**

## 用户操作入口

需要建立独立 CLI 认证时，使用官方入口；该命令会更新登录关联和默认模型，只在用户明确授权配置时执行：

```bash
zcode login bigmodel
zcode tui --mode build --cwd /absolute/path/workspace
```

在 TUI 中明确查看和选择；原生 `/model` 会补齐当前模型的默认 reasoning，按需用 `/effort` 调整：

```text
/model list
/model account:bigmodel-individual-coding-plan/GLM-5.3
/model account:bigmodel-individual-coding-plan/GLM-5.3-Flash
/effort max
```

若套餐 provider 不在列表、切换被拒绝或请求失败，停止并处理认证/套餐权限；不要继续让 MiniMax、体验套餐或通用余额替代执行。当前 renderer 对 `zcode-cli --model` 明确拒绝，原生 CLI 没有该 flag。本次没有新增未经验证的自动模型注入包装；指定模型的 worker 须先在其原生会话选择并核对，再投业务任务。

## 隔离探针及真实证据

本次测试使用私有临时配置、凭证副本、独立工作区、独立数据库与日志。保持系统 HOME 不变，通过已安装 runtime 的配置解析器确认以下覆盖方式；不借旧 driver 的 `--settings`：

| 变量 | 用途 |
|---|---|
| `ZCODE_BUILTIN_PROVIDER_CONFIG_FILE`、`ZCODE_PERSONAL_PROVIDER_CONFIG_FILE` | 必须成对提供；builtin 指向已安装的官方配置，personal 为隔离副本 |
| `ZCODE_DATA_BASE_DIR` | 认证库解析为该目录下 `.zcode/v2/credentials.json`，避免更新共享认证 |
| `ZCODE_SESSION_DB_PATH` | 独立 session SQLite 路径；源码按 `ZCODE_` 前缀动态解析，不是完整字符串常量 |
| `ZCODE_STORAGE_DIR`、`ZCODE_LOG_DIR` | 私有缓存/执行与日志目录 |

临时认证复制只获本次研究授权，不加入默认 worker 配方；不要在命令行参数、Git、公开日志中传密钥。后台覆盖变量属于已测版本的内部实现，更新 runtime 后须重新核对，不能承诺稳定公共 API。

验证结果：

| 检查 | 真实结果 |
|---|---|
| 原生 TUI `/model list` | 隔离恢复关联后列出个人套餐 GLM-5.3、Flash |
| 原生 TUI `/model <provider/model>` | 两次切换均显示精确 provider/model 与 max；未触发推理请求 |
| 省略 reasoning 的默认模型 | 请求成功但实际为 GLM-5.3，证明静默回落风险 |
| 带 reasoning 的 Flash 默认模型 | 原生 `--prompt` 成功，SQLite `model_usage` 为个人套餐 provider / GLM-5.3-Flash |
| 两次短请求 | 各 1 次 provider 请求，0 retry、0 tool call；返回固定探针文本；本地数据库记录分别 completed |
| 请求地址 | runtime 请求日志均为 `https://open.bigmodel.cn/api/anthropic`，无 MiniMax/Start Plan 回落 |
| 服务端套餐/额度 | 同一凭证只读接口返回 GLM Coding Pro / VALID 与 pro 的套餐积分限额；模型用量为按小时汇总 |
| 逐请求积分明细 | 端点未返回可用 JSON；无独占前后积分差，精确扣分归因 `NOT_VERIFIED` |
| 原件与隔离 | 共享 provider、CLI/v2 config、credentials 前后 SHA-256 相同；独立 SQLite 真实生成；临时认证副本完成后删除 |

两次短提示仍各有约 3.1 万 input tokens 的 runtime 系统上下文；不能按用户提示长度估计成本。2026-09-30 的两次短探针没有读写业务文件、工具调用或子智能体派发。该次成功证明原生模型切换和个人套餐请求通道，不证明完整 worker 生命周期、scope hook、持续纠偏或 Orca supervised 已通过。

脱敏证据与候选哈希写回 TASKS；私有账户响应、原始认证和日志不放进 Skill。

## 2026-10-01 tmux 文件任务与证据边界

后续按用户具名授权，在隔离工作树以 `zcode-cli` tmux fallback 完成有界 probe 文件任务。产物提交为 `08230b664fcaee9e6a2ee5f3257ec977073ffc9d`；PM 执行3项测试通过，diff 仅涉及 probe 任务文件。独立会话 SQLite 的13条 `model_usage` 均为 completed，实际 provider 为 `account:bigmodel-individual-coding-plan`、模型为 `GLM-5.3-Flash`，retry 为0。该次临时研究认证/配置副本已按精确路径删除，tmux 已关闭。独立产物验收为 `ACCEPT`（限tmux实际任务），以 TASKS 的 LIVE-WORKER-ACCEPTANCE 卡更新为准。

Orca 1.4.217 的两次 ZCode 尝试均报 `terminal_handle_stale`，未发送业务 prompt；tmux 任务不证明 Orca terminal-managed、supervised 或 settlement 成功。使用显式 prompt-only 降级，bootstrap 曾运行超出精确 shell allowlist 的 `ls`，不能声称机械 scope/hook 已验证。

私人路由只读观测、预算规划与启动前身份复核用于这一次研究副本；本轮没有真实账号切换、耗卡或产品化自动认证/身份绑定。准备脚本在进程内计算共享文件 before/after 并断言相等，但未持久化本次共享原件 baseline；副本哈希不能替代原件 baseline，因此独立共享 before/after 重放是 `NOT_VERIFIED`。实际模型调用通道也不等于逐请求服务端积分扣分证据，精确计费仍 `NOT_VERIFIED`。不公开账户身份、原始日志、认证副本路径或凭证内容。

## 交互CLI长程与Orca TUI边界

用户当前要求保留交互CLI长程工作。已实测的 ZCode worker 路径为上述 tmux 原生交互会话：保留同一会话完成具名任务，并由PM回读产物、原生模型记录和会话收口证据。当前 MAO Orca spawn 仍采用创建TUI、等待真实就绪、再投递的合同；本轮没有新增无头替代配方、runner或其他启动模式。

对于当前实测的 Orca 1.4.217、ZCode CLI 0.16.9 / runtime 3.14.3 组合，用户已指定 `zcode-cli` 时，按现有 spawn 门禁显式传入 `--no-orca-mode`，选择已验的 tmux 交互路径，并保留同一 session 接续任务。这是既有兼容选择；无需先创建 Orca 终端试探或伪造 ready，不改变默认 worker 池、backend 或其他门禁。升级 Orca 后的自动 TUI 路径须重新验收，不能沿用上述 tmux 或旧版本诊断作为就绪证明。

后续零业务提示的专用启动诊断中，Orca终端已connected/writable、renderer pane已挂载，屏幕出现composer，但 `tui-idle` 仍返回timeout。已安装 ZCode 源码显示新会话的 `SessionStart` hook 在首次turn初始化期间运行；Orca的ZCode ready合成依赖原生状态/title信号，屏幕上的输入提示不能单独证明该信号已产生。这提示首次投递前存在就绪循环，但尚未形成可独立验收的Orca交互兼容修复。聚焦终端、延长等待或已安装hook状态均不足以宣布兼容成功；不得伪造ready或绕过门禁投递。

Orca ZCode TUI、完整长程监督和settlement仍为 `NOT_VERIFIED`。tmux任务的已验范围不扩大为这些层的证明；按[本地账号调度调用合同](29-local-account-routing-skill.md)做现场校验，也不能替代真实TUI就绪或建立持续身份锁。

## 官方来源

[ZCode 连接模型与套餐](https://zcode.z.ai/cn/docs/configuration) 说明账号 Coding Plan、API Key 和资源包端点的区别：BigModel 编程套餐 OpenAI 地址是 `/api/coding/paas/v4`，Anthropic 地址是 `/api/anthropic`；通用余额 OpenAI 地址是 `/api/paas/v4`。购买过套餐的账号在该 Anthropic 通道不会自动改从余额扣费。

[ZCode 使用统计](https://zcode.z.ai/cn/docs/usage-stats) 说明端内用量查看；[官方源码](https://github.com/zai-org/ZCode) 与实际安装 runtime 的 provider resolver、standalone credentials、模型 selection 校验以及 quota provider 是本次实现核对来源。服务端权益变化以当前账号返回为准。
