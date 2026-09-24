# 决策记录

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
