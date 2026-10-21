# Changelog

## [0.6.4] - 2026-10-17

### 真宿主实证批回写（dsh-plugins DSH-023 标记轮 PR #338 + DSH-022 C-1 PR #339，Desktop 2.0.17 / 0.2.0-rc.2 隔离 headless + 浏览器 client）

- **harness-facts-020rc2 覆盖语义实证修订**：此前「抢占父座位使子座位声明权易主」口径**订正**——排他发生在两份 children 表之间（任何第二个携带 children 的 register 都抛 `already declared`，与 priority 无关；现实模块图顺序下后到者是自研插件且未捕获异常会中断整个 client 装载）；**不带 children 注册即成功抢占**（priority -1 胜者替换官方浏览区渲染，官方子座位声明与子 entry 全保留可消费）；带 id 的 entry 注册（schedule 行标记）与谁声明都共存——「C 与 B'/schedule 互斥」旧判定不成立（真实 SlotCore 四场景复演 + 真宿主双 profile 对照）。
- 新增「client 插件装载契约（C-1 实证）」节：bundle 必须是 `window.__ModuleLoader__.load({id, factory})` 工厂封装（裸 ESM 永卡 Loading plugins；`build-client.mjs` 构建先例）；client 模块需导出 `inject:['slots',…]` **服务键**（与 package.json `dsh.client.inject` 模块 id 是两层声明）；slot 胜者组件按 React 渲染（裸 DOM 返回值会炸）；apply 返回值被当 effect 处置器（非函数非空即 Invalid effect）。
- NOT_VERIFIED 收口：五插件 0.2.0-rc.2 装载复跑与 2026-09-30 三宿主标记（共载自检/disable 半/跨进程回放）全部重现（PR #337/#338）；0.1.7 时代 enable 半 `inactive context` 异常在新版**未复现**；HMR disposed 面仍未复测。新登记观察差异：storages 域文件似改首写物化（未定因）。
- pitfalls-log 新增「slot 抢占与 client 装载契约」批（9 条症状）：children 排他/裸 ESM、inject 服务键、Invalid effect、undeclared 依赖假绿、`{...ctx}` 展开丢 logger（mock 假绿族）、`dsh` CLI node v20 静默 no-op（`import.meta.main` undefined）、实验 host 未清致 pre-push 负载闪断、重型 SPA 饿死浏览器观察通道（替代观察面：`__DSH_BOOT__` manifest/截图/对照）、装配后 token 抓取时序。
- SKILL.md：版本 0.6.4；沉淀来源注明 2026-10-17 实证批。


## [0.6.3] - 2026-10-15

### 版本复核（Desktop 2.0.17 / 内嵌 0.2.0-rc.2，dsh-plugins DSH-023）

- 新增 `references/harness-facts-020rc2.md`：当前基线事实快照——版本矩阵（tag `dsh-v0.2.0-rc.2` / `639ed015`）、Host 消费面零破坏结论（官方能力七条目 6 ANCHOR_OK）、新版增量事实速查、client 侧 90-slot 宿主台账与 priority-shadowing 官方语义、primitives/tokens 现状、NOT_VERIFIED 边界。0.1.7-rc.2 快照保留为历史基线。
- official-capabilities 七条目按安装版实物复核并回写：抬头标注复核结论；#1 范例锚点改指安装版 `dsh-compaction-basic/lib/index.js` + 补 `registerModelDiscovery` 等服务面；#3 补 schedule `static Config` 留存上限 + inject 六键实物锚点；#4 补 `ctx.tools.execute` 唯一执行口与 `snapshotToolValue` 无损 JSON 校验（EVOLVE-005 实证）、取消码锚点改指 lib；#5 UNIT_NAME_RE 锚点改 `dsh-storage/lib/index.js:80`、**表名同受正则**、补 `compatibleVersions`/`facet-unsupported`/`version-mismatch` 透传/open 六步顺序；**#6 末条 ANCHOR_GONE 改写**（`dsh-client-ui-settings` + 10 分域包的 schema 自动设置页已存在）+ `update()` 服务端非 volatile 拒绝；#7 补宿主 `storage-domain-invariant` 不变式护栏。
- 查证方法修正：#1 版本锚点改为「安装版实物为锚、npm channel 不作等式」（与 0.6.2 SKILL 修正一致）；#2 改为「安装版内嵌 node_modules 只读优先（api-catalog.js + README.zh.md），harness 源码检出为备选」——R2/R3 两任务全程离线按此法完成。
- SKILL.md：沉淀来源注明 2.0.17/0.2.0-rc.2 复核；参考节双基线并列；回写指向当前基线。
- 证据：dsh-plugins `docs/evidence/dsh-023-20261015/`（oc-recheck/REPORT.md 249 行、client-survey/README.md 224 行，含 PM 勘正附记）。行为语义类事实维持 NOT_VERIFIED，不以静态复核冒充实机验证。

## [0.6.2] - 2026-10-14

### 修复（审计 DPD-AUDIT-001，F01–F08 逐项绑定最小反例入回归）

- F02 lint §7：词典平价由正则键集改为**静态叶路径解析**——嵌套键路径错位（zh `a.x/b.y` vs en `a.y/b.x`）此前压扁成集合误报平价 PASS，现按完整路径比对报 FAIL；同文件 const 展开可解析（`{...base}` 缺键被抓），跨文件展开/计算键/方法简写转 NOT_VERIFIED 不出假 PASS；字符串值内花括号不再干扰解析。
- F03 lint §2：patch 引用由文本 includes 改为结构核——纯注释 patch、包名仅在注释或非 id/name 值位置不再假 PASS（FAIL 或转人工），合法 insert 行 id/name 声明仍 PASS。
- F01 lint §4/§5：harness 事实源缺失时相关检查**降级 NOT_VERIFIED 不误报 FAIL**——inject 目标 workspace 核验、产物 bare require 对账、构建 external 对账三处；自注入/非字符串等事实无关 FAIL 保留。
- F04 lint §3：exports["."] 支持字符串、`exports` 顶层字符串与条件导出形态（default/node/import/require 优先序）——合法字符串 exports 不再误报入口不存在；无法解析的条件形态转 NOT_VERIFIED。
- F05 lint §6/§7：client 源扫描扩展 **js/mjs/jsx** 并明示范围（0 文件时 WARN 未覆盖≠无违规）；locale 词典候选兼容 `locales.js` 与 `locales/zh.js` 布局。
- F06 lint §5：`deps.alwaysBundle` 语义修正为**强制内联**（tsdown 语义），不再当 external 误报；新增 alwaysBundle × dsh.client.external 方向冲突 FAIL。
- F07 入口：frontmatter 版本对齐（0.6.0 落后 CHANGELOG 两版 → 0.6.2）；ui-ux-workbench（0.6.1 新增）挂接入 SKILL.md 参考节与设计预检路径。
- F08 porting-semantics 第 2 条事实勘误：JS `encodeURI` 对非 ASCII **同样**百分号编码（`encodeURI('中文')`=`%E4%B8%AD%E6%96%87`，emoji 同理，`%` 两边都编码为 `%25`）——真实差分在保留字符集：`encodeURI` 不编码 `? # & = + $ , ; : / @` 与 `! ' ( ) * - _ . ~`，Python `quote` 默认仅保留 `/`。quotePath safe 集对齐与跨语言差分对照的必要性不变（106 样本实证保留）。
- 附带：pitfalls-log「mock 假体 per-open 隔离」与「域名仅下划线」两坑拆为独立两行（此前挤行把域名校验出处挤出列）。
- test-lint 回归 23 → 41 项断言（每个修复绑定审计反例与合法对照）。

## [0.6.1] - 2026-10-12

### 新增
- references/ui-ux-workbench.md：插件工作台与运行视图的设计与验收方法（真实入口观察、版式按产品任务选择）。

## [0.6.0] - 2026-10-01

- official-capabilities 新增条目 #6（插件 Config 与 settings 表单机制：Config 命名导出/~standard 同步契约/volatile 活引用与写协议/vendor 方言门/子节点 toJSON——零依赖 duck-typed 三暗门，dsh-plugins PR #55）与 #7（`domain/changed` 存储域变更事件：耐久后写序 emit/新快照/进程内边界，PR #68）；待查清单收口「读取回执」项（bizlink v1 固化时评估维持业务侧）。
- porting-semantics 新增「Python→JS 跨语言平移」六条：零宽后顾断言不可降级为消耗式前缀（PR #69 相邻链接漏改写 ~20% 实测）、URL 编码差分对照（quotePath 106 输入零分歧）、内容哈希当不了修订号（PR #68 自查）、round/日期/排序三件套（PR #61）、替换串捕获组即语义、差异申报或消除。
- pitfalls-log 新增九条症状（mock ctx 代理纪律/valueSchema×best-effort 静默丢失/门序短路/死计数器/文件级≠记录级/离线桩≠网络失败/dump 同名覆盖/静态 baseUrl 错位/mock 假体 per-open 隔离）+ 新节「宿主验证与证据纪律」（四条 headless lab 实证）。
- harness-facts 增补：插件 Config/settings 机制摘要与 `domain/changed`/加表不升 version/两处宿主侧观察（HMR disposed/inactive context，定因中）。
- SKILL.md 开发路径新增第 5 步「宿主级验证」（mock 全绿 ≠ 宿主可用）；参考节描述同步。证据锚：dsh-plugins PR #55/#57/#58/#59/#61/#62/#66/#67/#68/#69。


## [0.5.0] - 2026-09-30

- 新增 `references/porting-semantics.md`（移植语义纪律）：flopi-candidate 源码定位规律、行号锚定、平移四原则（语义等价/偏离只许更严/不虚构/读不透保守）、外部 IO 注入缝纪律（三级装配 + 缺省 fail-closed + 凭据零接触）、mock 贴宿主契约与并发分支测试计数。实证锚 dsh-plugins PR #42/#45/#46/#49/#51。
- SKILL.md 开发路径第 1 步挂接（起手切片 → 领域平移）；pitfalls-log 新增「并行分支测试计数」条目。


## [0.4.1] - 2026-09-30

- 修条目 #5 域名正则错误：真实约束是 `^[a-z][a-z0-9_]*$`（仅下划线；backend.ts UNIT_NAME_RE 强校验）——此前误写为允许连字符。pitfalls-log 新增「mock storageDomain 全绿、宿主装载即拒」条目（mock 假体须复刻域名校验）。出处 dsh-plugins PR #42 发现/PR #43 修复。


## [0.4.0] - 2026-09-30

- official-capabilities 新增条目 #4 `ctx.tools.register`（defineTool 只是编译层、registry 只做结构校验——零依赖手写编译后形态可行；exec.agent.session.id 所有权围栏；exec.signal 协作式取消 = Pi 迟写簿记的框架级替代）与 #5 `ctx.storageDomain`（表记录 schema 只在 open 边界 .parse()——duck-typed 校验可行；不声明 global 绕开 safeParse 检查；update 原子读改写；单 blob → 每对象一条记录的迁移模式）。证据锚 dsh-plugins PR #35（P09）。
- pitfalls-log 新增「多插件共载自检误报」条目：自检只断言自身命名空间（PR #37 四插件同修）。
- SKILL.md 开发路径第 1 步补「Pi 插件 DSH 化起手切片」模式（PR #37 三插件实证）；参考节条目数更新。


## [0.3.2] - 2026-09-30

- official-capabilities 新增条目 #2 `ctx.jobs`（会话内长任务注册表：进程内、agent 所有、无定时）与 #3 `packages/schedule`（持久定时调度：六种时序选择器、跨重启持久化、交付=会话内 agent turn、须 Host Web 组合）；待查清单撤销「后台作业/定时能力」项（查证方法第二次实战，dsh-plugins PR #33）。


## [0.3.1] - 2026-09-29

- 踩坑表 renderer 行补语义解码：「Unknown client plugin」为插件列表为空时的显示伪影（主进程超时路径构造空报告），真实含义是渲染器 30s 整体静默、与被测插件无关（dsh-plugins renderer 静态归因，PR #32）。

## [0.3.0] - 2026-09-29

- 用户指示：官方 harness 能发掘的能力直接复用，研究结论沉淀进本 skill——新增 `references/official-capabilities.md`（官方能力复用目录）。
- 目录含查证方法五步（版本锚定 config/dsh-upstream.json、本机 harness 检出 detached worktree 读旧 tag、包 README/subsystems/architecture notes 文档优先、grep 官方消费者找可照抄范例、证据进 dsh-plugins docs/research 与结论进目录的双写回约定）。
- 首条目录条目：`ctx.llm` 模型调用（DSH-006 核查，0.1.7-rc.2 实物）——唯一受支持入口、request-only 输入、无自动重试、稳定错误码、provider 三形态与 pi-ai 手工网关（第三方自有 key 对应物）；待查清单登记读取回执与后台作业两项。
- SKILL.md 开发路径第 3 步增「模型调用与公共能力先查官方复用」；参考节挂接；版本 0.3.0。

## [0.2.0] - 2026-09-29

- 用户指示：skill 迁至公开仓 `skills/dsh-plugin-dev/`；`dsh-plugin-lint` 移除、能力并入（DPD-DEC-001 v2/004）。
- 吸收 lint 1.0.0 全部能力：scripts/{lint,test-lint}.mjs、config/harness-path.example.yaml、templates/plugin-quality-report.md、references/dsh-plugin-development-standards.md（0.1.2-rc.1 基线历史权威）；SKILL 增设机械审查章节（§0-§9 规则概要、三模式、审查工作原则、已知限制）。
- frontmatter 对齐公开 skill 格式（homepage/author/version 0.2.0）。

### 继承自 dsh-plugin-lint [1.0.0]（2026-09-04，并入存档）

- harness 三级溯源（--harness-root / DSH_HARNESS_ROOT / 本地 yaml）、官方版本门交叉核对。
- §5 client 工件 bare require ↔ 模块表对账、构建 external 对账；§4 inject 目标声明与 external 自引用检查。
- §6 主题变量声明集对账；§7 类型化 locale 与 CJK 硬编码；fail-closed / NOT_VERIFIED 语义。

## [0.1.0] - 2026-09-29

- 初版：开发主线 SKILL.md + 五份 references（Host 插件要领与 0.1.2→0.1.7 差异、会话投影 Cookbook、Desktop 装载与隔离实验、0.1.7-rc.2 事实快照、踩坑日志）。
- 沉淀来源：dsh-plugins 仓 2026-09-29 全程实测（五次隔离装载实验、PR #1-#14 独立审查修复），核心新知：stateVersion 必填、数字 turnId、wire 通知路径、type:module 组合回归、api-catalog 类型查找、profile 必含 web-app、零物化装载、userData 隔离盲点、SIGTERM 分步退出。
- 与 dsh-plugin-lint 的关系定型：dev 为主线、lint 为验收闸（DPD-DEC-001）。
