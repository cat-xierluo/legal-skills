# 0.2.0-rc.2 事实快照（Desktop 2.0.17 实测，2026-10-15）

本机安装版 Desktop 审查期间自动升级 2.0.15→**2.0.17**，内嵌运行时 0.1.7-rc.2→**0.2.0-rc.2**。dsh-plugins `config/dsh-upstream.json` 已于 2026-10-15 换钉（DSH-023）。本文件只记**对插件开发有实质影响**的新版事实；[0.1.7-rc.2 快照](harness-facts-017rc2.md) 保留为历史基线，其结论不自动外推。证据出处：dsh-plugins `docs/evidence/dsh-023-20261015/`（官方能力七条目重核 R2 + client/UI 能力清单 R3，均经 PM 逐锚点抽验）与 `docs/research/2026-09-30-upstream-020rc2-delta.md`（静态差异）。

## 版本矩阵

| 项 | 值 | 证据 |
|---|---|---|
| Desktop | 2.0.17 | `Info.plist` CFBundleShortVersionString；`app/package.json` `dsh-plugin-desktop` |
| 内嵌运行时 | 0.2.0-rc.2 | `app/node_modules/@deepseek-ai/dsh-tool-cordis/package.json`（client UI 全家族同版本） |
| 上游 tag / commit | `dsh-v0.2.0-rc.2` / `639ed015397290b3745d163aafe02ffee4aa3f84` | `git ls-remote` 解析，config/dsh-upstream.json 钉定 |
| 内嵌包数 | 291（含 cordis/cosmokit/schemastery 等第三方） | `ls node_modules/@deepseek-ai` |
| 类型权威 | `dsh-tool-cordis/lib/types/api-catalog.js`（8187 行生成物） | 内嵌树 `.d.ts` 剥离不变 |

**版本锚点纪律**：以安装版实物为锚，npm channel 不作等式（2026-09-30 实测 npm latest 曾领先安装版两周）。

## Host 侧消费面：零破坏（官方能力七条目重核）

七条目对照安装版实物逐条锚定：**6 条 ANCHOR_OK**（ctx.llm / ctx.jobs / schedule / tools register+execute / storageDomain / domain/changed）；#6 Config/settings 三暗门静态确证、**末条「无 schema 自动设置页客户端」已失效**。在库消费者（llm 2 插件、schedule 4、tools 5、storageDomain 8、settings 3、domain/changed 1）**无一需迁移**。锚点位移四处已回写 [official-capabilities](official-capabilities.md)。

## 新版增量事实（目录已补录，此处速查）

| 面 | 0.2.0-rc.2 事实 | 锚点 | 对插件的含义 |
|---|---|---|---|
| settings 编辑面 | `dsh-client-ui-settings` + 10 分域包，schema 驱动自动表单经 remote `settings.describe()` | `dsh-client-ui-settings/lib/client.js:1302,:1469` | 「编辑面=原生配置编辑器独占」作废；手写 schema 三暗门（schemastery 方言门/子节点 toJSON/同步 validate）**仍在**，表单会真的渲染你的 schema |
| settings 服务端 | `update()` 非 volatile 路径服务端拒绝 | `dsh-settings/lib/index.js:507` | 不是前端限制，绕过表单直调同样被拒 |
| storageDomain 表名 | 表名同受 `^[a-z][a-z0-9_]*$` | `dsh-storage-domain/lib/index.js:73`（正则本体 `dsh-storage/lib/index.js:80`） | 连字符表名 open 即拒；dsh-plugins 全仓 18 项声明核对零冲击 |
| storageDomain 校验 | `compatibleVersions` 每条非负整数且 < version；错误码 + `facet-unsupported`；`version-mismatch` 透传 | `lib/index.js:63-64`、`README.zh.md:73` | 排错顺序六步见 `lib/index.js:338-342` |
| domain/changed 护栏 | 宿主伴生插件 `storage-domain-invariant` 校验每条事件与内存一致 | `dsh-storage-domain/lib/invariant.js:19-32` | 翻译层发陈旧值/漏字段会被宿主判 fail——可挂进测试当回归护栏 |
| schedule 留存 | `static Config { deliveryHistoryDays, deliveryHistoryRecords }` | `dsh-schedule/lib/index.js:2598-2601` | 投递历史窗口宿主可配，直读历史的代码不要假设无限 |
| ctx.llm 面 | `registerAdapter`/`registerConfigurableProviders`/`registerModelDiscovery`/`resolveModelInfo` 等 | `api-catalog.js:1302-1387` | GUI 可选模型走 discovery 注册，不止一次性直指 |
| tools 执行 | `ctx.tools.execute(exec)` 唯一执行口 + `snapshotToolValue` 无损 JSON 校验 | `dsh-tools/lib/index.js:3116,:2575,:3542` | 返回值含 `undefined` 等被拒；容器桩直调绕过校验=假绿（EVOLVE-005 教训） |

## client/UI 侧（0.2.0 主战场，DSH-022 设计输入）

- **slot 台账可静态读出**：宿主 `CLIENT_SLOT_API` **90 条**（`dsh-cordis-client-runner/lib/client.js:2363+`），每条 `kind/scope/replaceRisk/standardProps/registerOptions/declaredBy`——`replaceRisk`（`none` additive / `shadows-shipped-ui`）首次有**宿主自述**，不必再凭印象评级。
- **覆盖语义官方一等（2026-10-17 C-1 实证修订）**：`register()` 允许不同 `priority` 共存、同 priority 才抛；`entriesOfSlot` 按 priority 升序 **lowest renders**（`dsh-client-ui-slots/lib/index.js:168-186,:267-290`）——shadowing 是设计内机制，**不带 children 注册即成功抢占**（真宿主实证：priority -1 胜者替换官方浏览区渲染，官方子座位声明与 menu/pin 等子 entry 全保留可消费）。此前「抢占父座位使子座位声明权易主」的口径**不准确**：`:190-193` 的排他发生在**两份 children 表之间**——任何第二个携带 children 的 register（无论顺序）都抛 `already declared`，与 priority 无关；现实模块图顺序下后到者是自研插件，且该未捕获异常会**中断整个 client 装载**（永卡 "Loading plugins…"）。带 id 的 entry 注册（如 schedule 的行标记）与谁声明座位无关、四场景全共存——「C 与 B'/schedule 互斥」的旧判定不成立（dsh-plugins PR #339 SlotCore 四场景复演 + 真宿主双对照）。
- **侧栏事实**（与 DSH-022 live Inspect 结论一致）：工作区 record 仍无分类字段（`dsh-workspace/lib/types/spec.js:18-23`）；`sidebar.workspaces` 子座位全是会话行（4 子座位 + directoryFlow），`ProjectRowItem` 零 `renderSlot`（`dsh-client-ui-workspace/lib/client.js:1270-1345`）。
- **workspace 三层服务面**：Host `ctx.workspaceRegistry`（`dsh-workspace/lib/index.js:354-948`，CRUD/归档/置顶）；client `ctx.workspaces` 含 `follow(signal)` 增量流（`dsh-api-workspace-controller/lib/client.js:476`，upsert/remove/order/archived/pinned 帧）；`ctx.uiWorkspace.openWorkspace(id, beforeOpen?)` async 跳转（`dsh-client-ui-workspace/lib/client.js:824-838`）。
- **primitives 仍是库非 client 插件**：`dsh-client-ui-primitives` 无 `./client` 导出、无 `dsh.client` 声明（2026-10-09 教训②未变）；官方 jobs/schedule/subagent 把它列进自身 inject，但**第三方 bundle 能否 require 它为 NOT_VERIFIED**（`dsh-client-modules` external 表是运行时数据）——设计按「自绘 + 主题 tokens」。
- **主题 tokens 开放**：`--dsw-*` 去重 **403** 个（`dsh-client-ui-theme/lib/`）；theme 包有 `./client` 导出 + `dsh.client` 声明（platform web，immediately）。

## client 插件装载契约（C-1 实证，2026-10-17）

第三方 client 插件在真宿主装载的**四件硬契约**（dsh-plugins PR #339，缺一即死/不激活）：

1. **bundle 形态**：被服务的 `client.js` 必须是 `window.__ModuleLoader__.load({id, factory:(require)=>{…}})` 工厂封装——裸 ESM 源码永不注册，client 永卡 "Loading plugins…"。仓内构建先例 `scripts/build-client.mjs`（pdf-organizer / registry-board / workspace-partitions）：ESM 源 `lib/client.mjs` → 产物 `lib/client.js`，`require('react')` 等由 loader 供给（package.json `exports["./client"]` 指产物）。
2. **inject 服务键**：client 模块导出的插件对象需含 `inject:['slots',…]`——**服务键**而非模块 id（"slots and theme are the usual UI seats"，`dsh-cordis-client-runner/lib/client.js:331`）；package.json `dsh.client.inject` 写**模块 id**（依赖边）——两层声明各管一面，都要写。
3. **组件契约**：slot 胜者组件按 React 渲染——返回裸 DOM 节点（`document.createElement`）会炸渲染；React 经 `require('react')` 取用。
4. **apply 返回值**（Host 与 client 同规）：返回值被当 effect 处置器收集，非函数非空即 `Invalid effect`——服务面只经 provide。

另两则配套事实：0.2.0-rc.2 真宿主 `ctx.logger` 是**函数**（携带 info/warn/error/debug 方法，直读合法）；观察 DSH web client 用 HTML 内联 `__DSH_BOOT__` manifest（curl+cookie）+ 截图 + 对照 profile，勿依赖 evaluate（重型 SPA 会饿死观察通道）。

## NOT_VERIFIED 边界（新版仍未实机验证）

- 行为语义类：#6 门②子节点缺 toJSON 是否当场 TypeError、`_commitVolatile` 免重挂载的运行时效果、`domain/changed` 跨域交错与监听者异常下的写序。
- ~~覆盖类：抢占后重声明子座位 / schedule 共存 / 渲染残留~~ **2026-10-17 已验**（dsh-plugins PR #339）：重声明必抛（排他）；**不带 children 抢占成立**且 schedule 共存无损、shadow 渲染实证；0.1.7 时代 enable 半 `inactive context` 异常在 0.2.0-rc.2 **未复现**（bizlink disable→enable 全链路通，含装载即回放）。HMR disposed（P3 settings 活移植面）仍未复测。
- 第三方 bundle require primitives 的模块表放行；slot `ownerProps` 完整契约（只取到 `standardProps`）。
- ~~五插件装载复跑~~ **2026-10-17 已收口**：五 Host 插件（含 bizlink）0.2.0-rc.2 headless 隔离装载零告警全覆盖 + 2026-09-30 三宿主标记（共载自检/disable 半/跨进程回放）全部重现（dsh-plugins PR #337/#338）；GUI/profile 级归用户在场窗口。
- 观察差异未定因：storages 域文件在 0.2.0-rc.2 似改**首写物化**（装载即 open 不再生成文件；0.1.7 是装载即物化 5-7 个域文件）——不影响域行为，未深挖。

## 观测点

- 0.1.7-rc.2 期沉淀的 ctx 代理纪律（未声明 inject 读取即抛）、投影 stateVersion 必填、数字 turnId、wire 通知等关键面经 WA-006 二次重锚逐项对照实物**未变**。
- 换钉后任何历史证据引用须注明其 2.0.15 基线；新实验一律重钉字节。
