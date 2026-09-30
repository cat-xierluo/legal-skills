# 决策记录

## DEC-2026-09-30-ZCODE-CLI-ACCOUNT-CONTRACT — 原生 CLI 与宿主 app-server 分开验证

- 日期：2026-09-30；状态：已采纳，来源为用户要求进一步实测 BigModel Coding Plan。
- 事实：原生 TUI/prompt 使用 standalone account 凭证关联；app-server 不自动装载该账号。已有个人套餐 secret 但缺新版 identity 时，原生 CLI 无法选中套餐；仅省略 reasoning 的配置还可能静默选择其他模型。
- 决定：保留 zcode-cli 原生入口与 zcode 历史 driver 的隔离边界；不自动伪造 account entitlement、不把补齐临时关联的实验产品化、不修改共享默认。指导使用官方 login 与原生 /model，并以实际模型状态/请求记录核对选择。
- 验证：原生 GLM-5.3 与 Flash 各一次 completed，请求个人 Coding Plan /api/anthropic；服务端 Pro 有效及积分限额已读。逐请求精确扣分、认证迁移与 Orca 全生命周期不扩大为已验证。
- 重新评估条件：官方稳定提供独立 CLI 模型启动 flag/配置隔离契约或账号迁移 API 后，再实现并验证自动选择适配。

## DEC-2026-09-30-OPTIONAL-CLI-BACKENDS — 能力支持与日常派发分离

- 日期：2026-09-30；状态：已采纳，来源为用户当前明确指令。
- 决定：主要支持独立 ZCode CLI、MiniMax Code CLI；CodeBuddy 保留，QoderWork 移除；独立 Qoder CN CLI 和千问办公单独接入。可选 backend 仅用户指定时派发，不因额度或宿主同名自动选择；日常 Claude Code/Codex/provider 路由保持。
- 实现边界：新独立 ZCode 用 `zcode-cli`，保留 `zcode` 作为历史 app-server driver，避免把两种启动/配置契约混同。MiniMax 用 `minimax-code`/`mcode`。同名 qoderclicn 按实路径区分独立 Qoder CN 与 QwenWork bundle，拒绝旧 QoderWork。
- 权限：只增加既有 Claude/Codex/Hermes PM 的可选 worker 能力；不新增 PM 宿主。新 CLI 的编排 hook 未集成，必须显式 prompt-only 降级，不能借旧 QoderWork 的 hook 记录声明新产品已受机械保护。千问 native tools 与 bundled coding 不推断账号/额度共享，配置目录显式提供。
- 重新评估条件：用户调整默认派发偏好，或新 CLI 的 hook、账号与完整生命周期已独立实测，再变更默认路由/权限等级。

## DEC-2026-09-29-REMOTE-NODE-DISPATCH — 远程节点 Worker 派发走 SSH 桥 + 一次性 receipt

- 日期：2026-09-29
- 状态：已采纳（用户两项拍板：传输层=SSH 桥+节点本机 ORCA；节奏=mock 全过先行、真机 E2E 等节点负载回落）；真机 E2E NOT_VERIFIED
- 背景：双机双 GLM key 池（PM 自有 + 节点借用）要并发翻倍并把 worker 的 CPU/内存卸载到第二台机器。ORCA 原生 federation（`worker-start --on`）可用，但 federation 结算链踩已知缺口（TASK-2026-09-28-ORCA-SETTLEMENT-READBACK：真实回执 camelCase 适配失败、external 终端无法结算），且 federation 模式下本 skill 的 quota/mem/lease 门禁不在节点本机执行。
- 考虑方案：①ORCA federation 先行——监督链原生但结算风险在关键路径；②SSH 桥调节点本机 spawn-worker.sh——全套门禁在节点本机原样成立，lease 本机自治恰好是简单集群的正确抽象；③双轨并行——工作量 1.6 倍。
- 决策：M0 采用 SSH 桥。节点侧 harness 身份用一次性 dispatch receipt 传输（PM 本机 detect_pm_harness 的结果 + TTL≤300s + nonce + 绑定 backend/branch/session；消费即 chmod 400 不可逆），receipt 不创造新 authority 只传输已验证事实，交集检查复用原函数不放大；policy 新增 `remote_dispatch` 段（enabled 开关 + max_ttl），不新增 host 键。并发两层：节点本机 provider lease 是硬限制权威，PM 软账（remote-dispatches/）只收紧不放宽，不做分布式锁。完成权威=三证（STATUS 终态 + PR 存在 + PR-fingerprint 验收），不依赖跨机 Orca 回执。worker 读节点自己的 env：远程命令前置 unset 全部 provider 路由变量 + ssh 不转发 env + 节点侧 claude-provider-env 注入。
- 边界：supervised 模式跑远程 NOT_VERIFIED；命令身份不进 receipt（由既有 validate_worker_command 门禁承担）；`--provision` 的 clone 复用 PM 的 origin URL（节点需有对应读取凭证）。
- 重新评估条件：SETTLEMENT-READBACK 关闭且 worker_done 跨机语义实测通过后，评估 federation lane 转正（TASK-2026-09-29-REMOTE-NODE-M1）；若节点侧出现 receipt inbox 滥用迹象，收紧为节点侧预共享密钥签名。


## DEC-2026-09-24-CLAUDE-AUTO-SHELL — Claude Code auto 接管普通 Shell 决策

- 日期：2026-09-24
- 状态：已采纳；本地定向验收通过，真实 Claude Code auto 决策 `NOT_VERIFIED`
- 背景：Claude Code Worker 已用 `--permission-mode auto`，用户也在 Claude Code settings 中配置常规命令，但编排层的 PreToolUse 精确白名单先行拒绝定向 `unittest`，使原生 auto 与用户设置无法生效。
- 考虑方案：逐条补 `--verify-cmd` 维持机械最小权限，但开发循环仍频繁遇到命令变体；复制 settings 的 Bash 模式会重实现 Claude Code 匹配语义，且不能覆盖 auto 分类器；让 hook 对普通 Bash 返回无决定，则可复用原生权限系统。
- 决策：仅在 Claude Code 的本地 hook 生效、实际启动命令显式声明 `--permission-mode auto` 时，冻结 `shell_policy=claude_auto`；普通 Bash 交由 Claude Code auto/settings，编排层继续拦安装、受保护的 Git 操作、Orca 完成协议与 tracked 删除。其他模式与 backend 维持 `exact_allowlist`。验证命令仍是交付证据要求，须原样执行并保留退出码。
- 边界：auto 分类器不是 OS 沙箱，任意 Shell 程序可能写出 `--allow-paths` 范围；编排层只对识别出的保护类做机械拒绝，不把普通 Bash 声称为受范围硬隔离。PM 需审查真实 diff、测试与外部副作用；需要所有 Shell 都受机械范围控制时使用精确白名单模式。
- 重新评估条件：若 Claude Code 提供可验证的 Shell 路径沙箱或编排层有完整命令执行追踪，可强化范围保证；若真实 auto 模式无法加载本地 hook，则回到精确白名单或显式阻断派发。

## DEC-2026-09-20-TRACK-MAINTAINER-CONTEXT — 任务与决策上下文随 Skill 源码维护

- 日期：2026-09-20
- 状态：已采纳
- 背景：`TASKS.md`、`DECISIONS.md` 曾被仓库级 `.gitignore` 排除，导致 PR 已合并、分支已失效后，任务状态仍只停留在某个本地会话；其他 Agent 无法从远端取得同一份依赖、边界和验收上下文。
- 决策：仅为 `skills/multi-agent-orchestration/` 增加跟踪例外。`TASKS.md` 维护当前可执行队列、依赖、验收和接手字段；`DECISIONS.md` 维护仍影响实现的重要取舍。运行期 Session Context、绝对路径、terminal/Dispatch 临时身份和个人配置继续忽略。
- 理由：任务是否可领取属于跨 Worktree 的维护事实，应与代码候选一起 review；运行期状态则短暂且可能含本机或权限信息，不应进入公开仓库。
- 重新评估条件：若仓库明确采用可导出、可版本绑定的外部任务系统作为唯一权威源，可把本文件降为只读索引，但迁移前必须保留任务 ID、依赖和完成证据映射。

## DEC-2026-09-13-ORCA-NATIVE-CORRELATION-THREAD — 原生 thread 承载 correlation，业务 thread 留在 payload

- 日期：2026-09-13
- 状态：已采纳并交付，PR #153 / merge `49f55385b30ade730fc0b3590df4f9b9092436d5`
- 背景：Orca 1.4.200 的原生 `reply` 只继承顶层 Run、from、to、thread、subject 和 body，不复制原消息的 Task/Dispatch payload、correlation 或 reply marker。若原生 thread 只承载业务分组，PM 无法把无 payload reply 精确关联到单次请求。
- 决策：合同 `send` 的原生 `--thread-id` 使用 correlation；业务 thread 继续作为 payload 字段。只读 `inbox` 对结构化消息逐值校验顶层及 payload 的 lifecycle/sender/recipient/type/thread/correlation/ID 别名；只有同时提供业务 thread 与 correlation 时，才允许无 payload 消息通过精确 Run、worker sender、coordinator recipient 和原生 correlation thread 的受限 bridge。
- 理由：复用 Orca 原生持久消息与 reply 继承行为，不建第二套聊天层；correlation 对单次请求唯一，业务 thread 仍可用于逻辑分组。所有出现别名必须一致，避免一个正确字段遮蔽冲突身份。
- 证据边界：bridge receipt 标记 `native_thread_correlation`，消息级业务 thread 为 `null`，且继续声明不证明 `replied`、已消费、已执行或业务完成。无双过滤或身份/recipient/alias 任一冲突时失败关闭。
- 重新评估条件：若 Orca 后续原生 reply 稳定保留 payload/correlation/reply-to 并提供版本化 schema，可改用原生显式字段；迁移前必须保留旧行兼容与重放测试。

## DEC-2026-09-13-ORCA-SETUP-PREGUARD — Repo Setup 不复用 Worker 安装授权

- 日期：2026-09-13
- 状态：已采纳并交付，PR #151 / merge `b368d62d56fd5ee378cdfbd46a932935ce5602e7`
- 背景：Orca `worktree create` 的 repo Setup 早于 Multi-Agent Orchestration 写入 Session Context、安装门禁和 scope hook。旧入口使用 `--setup inherit`，曾在没有本轮安装授权时执行 `pnpm install`。
- 决策：Orca worktree 创建固定使用 `--setup skip`。`--orca-setup-mode inherit|run` 即使与 `--allow-install-command` 同时出现，也必须在任何 worktree、provider、terminal、Run、Task 或 Dispatch mutation 前失败关闭；后者只授权门禁已就位后的 Worker 阶段。
- 理由：现有授权无法绑定或约束 pre-guard Setup 的精确命令、目录与执行结果；复用该授权会把后置权限静默扩大到未受保护阶段。
- 重新评估条件：只有新增候选绑定的 prelaunch 授权合同，能在创建 worktree 前证明精确 Setup 命令、工作目录、允许路径、执行器和回执，并有独立故障注入验证，才可考虑支持 `inherit/run`。
- 影响：默认 Orca 派发不再自动执行仓库 Setup；需要依赖变更时，在 Worker 门禁已就位后走精确 `--allow-install-command`，或由具备单独授权的外部流程处理。

## DEC-2026-10-01-PRIVATE-ACCOUNT-SKILL

用户明确要求将账号、额度和刷新卡调度抽为私人 Skill，公开 MAO 只保留默认关闭的本地 Skill 调用合同。这样私人实现不进入公开发行；PM 按安装环境调用，缺失则不能获得该功能。调用不改变日常 backend 池，也不等于 spawn 机械账号绑定。
