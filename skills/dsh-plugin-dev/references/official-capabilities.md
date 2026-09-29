# 官方能力复用目录（official-capabilities）

目的：**自建任何共享/公共层之前，先查官方 harness 是否已有该能力**——官方有的直接复用，查证结论沉淀在本目录，避免每次重新研究。本文件只收「可在插件里直接消费的官方能力」条目；每条锚定版本与证据出处，版本升级时按 [harness-facts](harness-facts-017rc2.md) 流程重核。

## 查证方法（怎么找官方能力）

1. **版本锚定**：以 dsh-plugins `config/dsh-upstream.json` 钉定的 tag/commit 为准（npm `latest` = Desktop 内嵌运行时；`next` 是预发布线，不作为开发依据）。
2. **本机读旧版源码**：本机 harness 检出（`maoscripts/参考项目/deepseek-harness`）可能停在任意版本，但对象库通常含历史 tag commit——`git worktree add --detach <临时路径> <commit>` 即可零污染地读任意旧版，读完 `git worktree remove`。临时路径放 `/tmp` 可接受（随时可能被并行会话清理，靠 commit/分支保全状态，勿存未提交工作）。
3. **文档优先于 grep**：官方 `packages/<组>/README(.zh).md` 是逐包契约文档（含用法示例与刻意设计说明），`docs/subsystems/*.md` 是子系统文档，`.agents/notes/implemented/architecture/` 是实现决策笔记——先读再 grep，能少走弯路。
4. **找官方消费者范例**：确认能力可用后，grep 官方自己的消费代码（如 `inject: ['llm']`、`ctx.llm.stream`）找最小可照抄范例——官方非会话消费者（session-title、compaction summarizer）是「一次性调用」类用法的现成模板。
5. **结论写回两处**：证据全文进 dsh-plugins `docs/research/`（研究文档），复用结论进本目录（条目）；涉及取舍的记 dsh-plugins `docs/DECISIONS.md`。单一事实源：本目录不复制研究全文，只留结论 + 指针。

## 目录条目

### #1 模型调用（一次性/任意场景）——`ctx.llm`（2026-09-29 核查，0.1.7-rc.2 实物）

- **结论：插件需要调用模型（含非会话一次性调用）时，`ctx.llm.stream(GenerateOptions)` 是唯一受支持的官方入口**（`@deepseek-ai/dsh-llm`，cordis 服务键 `'llm'`，`static inject = ['llm']` 标准注入）。不要自建模型调用共享层，不要绕过 adapter 直连 provider。
- **可照抄范例**：官方 compaction 摘要器 `packages/compaction/compaction-basic/src/summarizer.ts`——`GenerateOptions{provider, model, messages, maxTokens, purpose, signal}` → `for await (chunk of ctx.llm.stream(o)) assembler.push(chunk)` → `BlockAssembler` 收块 → 从 `finish` chunk 判终态。
- **关键语义**：
  - 流必以唯一 terminal `finish` chunk 结束（`{kind:'error'|'aborted', failure}`），消费方按此统一处理成功/失败/取消。
  - `messages` 支持非持久 `RequestUserInput`（无 id/source）——一次性调用无需先建持久消息；要留痕可重建的调用（如标题生成）才要求持久 `Message`。
  - **服务自身从不重试**（官方 retry 包只挂 agent 失败步骤）；一次性调用的重试策略调用方自管。
  - 稳定错误码按码路由不读文案：`NO_ADAPTER`/`MISSING_CREDENTIAL`/`INVALID_CREDENTIAL`/`AUTH`/`RATE_LIMIT`/`QUOTA`（provider 中立耗尽）/`ACCOUNT_QUOTA`（第一方账户余额）/`CONTEXT_WINDOW_EXCEEDED`。
- **Provider 路由三形态**（`GenerateOptions.provider` 选路由）：

  | adapter | 认证 | 适用 |
  |---|---|---|
  | `dsh-llm-deepseek-api-key` | `apiKeyEnv` 凭据引用（密钥不进配置文件） | DeepSeek 官方路由，key 计费 |
  | `dsh-llm-deepseek-account` | 账户 token | 第一方账户（`ACCOUNT_QUOTA`） |
  | `dsh-llm-pi-ai` | 每路由 `apiKeyEnv` 或 pi-ai ambient 发现 | 多 provider：pi-ai 目录 + **手工声明网关** |

- **第三方自有 key（如 GLM/OpenAI-compatible）**：pi-ai 的 `providers` 字典手工声明路由（`baseURL`/协议/模型目录/`retryPolicy`）；settings 变更下一请求即生效、无需重启；授权门 = 凭据引用存在性 + `MISSING_CREDENTIAL`/`QUOTA` 错误码的 UI 呈现。
- **注意**：GUI 里供用户选择的模型要求 adapter 实现 `listModels` 并入目录；一次性调用直接指定 provider/model 字符串不受此限。实现时先 `ctx.llm.listProviders()` 探测宿主实际激活的路由（取决于 profile/设置，不能假设）。
- 证据全文：dsh-plugins `docs/research/2026-09-29-dsh006-llm-call-entry.md`（DSH-006 关闭记录，含 NOT_VERIFIED 边界：宿主实际激活路由、GLM 网关连通性归实现验收）。

### #2 会话内长任务——`ctx.jobs`（2026-09-30 核查，0.1.7-rc.2 实物）

- **结论**：agent 会话内的长任务注册表（`@deepseek-ai/dsh-jobs`，服务键 `'jobs'`）：`<kind>-N` 稳定 id，owner=发起 agent 会话（围栏是授权不是保密），可读输出/限时等待/请求取消；结算经事件流→`dsh-tool-jobs` 转会话内通知（免轮询）；输出进有界环形缓冲（stdout/stderr 到模型、log 仅观察者）。
- **边界**：进程内存储（`jobs-local`），**不跨重启、无定时语义**；启动需 controller（组合须加载 tool-jobs）；适合「工具把长活挂后台、agent 继续干」——不适合定时调度。
- 证据：dsh-plugins `docs/research/2026-09-30-dsh003-jobs-schedule-capability.md`。

### #3 持久定时调度——`packages/schedule`（2026-09-30 核查，0.1.7-rc.2 实物）

- **结论**：Host 拥有的持久提醒/定时任务（`ScheduleService`，Typert Remote）：六种时序选择器（`after_seconds`/`at`/`every_seconds`≥60s/`daily`/`weekly`/五字段 Vixie cron，显式 IANA 时区，cron 最小 1 分钟）；**跨 Host 重启持久化**（storage-domain 后端）；管理面完整（模型工具 schedule_create/list/update/delete + Remote catalog 跨会话巡检 + history 游标分页）。
- **关键边界**：**交付 = 到期以 follow-up 消息投递进原会话触发 agent turn**——每火一次是一次模型成本；不是零模型定时作业。会话归档被活跃提醒阻止，停止即全删。update 是整记录 compare-and-set（`schedule_conflict` 冲突不覆盖）。
- **组合前提**：`static inject = ['agents','sessions','tools','storageDomain','sessionController','sessionPersistence']`——**必须 Host Web 组合内挂载，headless/SDK-only 不能单挂**。
- **消费者取舍模板**（星标 G06 先例）：定时「agent 任务」用 schedule + 专用会话（得编排/重试，有模型成本）；零模型定时拉取只能插件内 host 存活期 timer（不持久、host 退出即停）。两者语义不同，立项时按需选。
- 证据：dsh-plugins `docs/research/2026-09-30-dsh003-jobs-schedule-capability.md`（DSH-003 缺口登记第 3 项判定：剩余空档仅「零模型持久定时作业」，出现再立项）。

### #4 模型工具注册——`ctx.tools.register`（2026-09-30 核查，0.1.7-rc.2 实物）

- **结论**：插件给模型暴露工具走 `ctx.tools.register(definition)`（`inject` 加 `'tools'`；官方范例 `dsh-tool-todo`）。`defineTool()` 只是编译层：属性 map → 标准 JSON Schema + execute 参数校验包装；**registry 只做结构校验**（name 唯一/非保留、`output.render` 为函数、schema 属支持子集）——零依赖插件可手写编译后形态（根级 `required` 数组、属性内不放 required，类型用 type/properties/items/enum/additionalProperties/description），参数校验由 execute 内领域层自证（Pi 原实现同型，dsh-plugins PR #35 P09 实证）。
- **exec 契约要点**：所属会话取 `exec.agent.session.id`（无 owner 会话即拒，todo 工具同款围栏）；**`exec.signal` 协作式取消是迟写防护的框架级替代**——turn 结束中止工具主体，execute 前置检查 `signal.aborted` 即可，不需要自维护 ended/retiredTurns 簿记（Pi→DSH 移植实证，PR #35）。
- 取消语义：主体前取消 `ABORTED_BEFORE_DISPATCH`、主体后取消以 `ABORTED` 替换成功结果（dsh-tools README）。

### #5 持久 KV 存储——`ctx.storageDomain.open`（2026-09-30 核查，0.1.7-rc.2 实物）

- **结论**：Host 侧持久、schema 校验的业务数据走 storageDomain（`inject` 加 `'storageDomain'`）：声明域 `{name, version, tables: {<表名>: {valueSchema}}}`（name 须匹配 `^[a-z][a-z0-9-]*$` 惯例、version 非负整数）→ `const domain = await ctx.storageDomain.open(spec)` → `domain.table('<表名>')` 的 `get`（同步）/`put`/`delete`/`update`（写链上的原子读改写，fn 内 throw 即中止该写）/`entries`（快照迭代）→ `domain.close()`（挂 `ctx.effect` disposer；域声明与 `domainTable(schema) = {valueSchema}` 均可手写，不必 import 包）。
- **schema 调用时机（零依赖姿势的关键）**：表记录 schema **只在 open 的持久读边界被 `valueSchema.parse(raw)` 调用**，写路径不重校验——duck-typed 校验对象 `{parse(v){…真校验…}}` 完全可行；`defineDomain` 的 load-time 检查只针对 `global.schema.safeParse(null)`（**不声明 global 即可绕开**，也就不需要 safeParse 方法）。
- **语义**：每写先落盘后进内存再发 `domain/changed`（写序）；后端失败内存不动（读写不背离）。错误码：`already-open`/`missing-key`（update 不存在记录）/`invalid-record`（存储记录过不了 schema，open 即拒——真·fail-closed）/`closed`/`backend-not-found`。后端路由由宿主组合的 storage-domain 插件配置决定（GUI/Web 组合有后端；headless 组合可能没有——inject 硬依赖语义下插件会等待不激活，属正确行为）。
- **迁移模式**（PR #35 P09 实证）：Pi 时代的单 blob settings（如 4 MiB 上限）改为每业务对象一条记录（key = 对象 id），加 per-key 写链串行与总量/体积护栏；损坏数据靠 open 边界 schema 校验 fail-closed，等价 Pi 的损坏 fail-closed。
- 证据：dsh-plugins PR #35（`plugins/dsh-session-pilot/lib/dsh/board.mjs` + `boardStore.mjs` + tests/pilot-board.test.cjs）。

## 待查清单（已登记未核查的能力问号）

- 读取回执类语义（「读过此案」READ_REQUIRED）：bizlink v1 无此概念，划业务 owner 责任，公共化待第二消费者需求（dsh-plugins DSH-003 公共缺口登记第 2 项）。
