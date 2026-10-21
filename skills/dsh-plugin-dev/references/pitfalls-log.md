# DSH 插件踩坑日志（按症状索引）

形态对齐 hermes-plugin-dev/references/troubleshooting.md：先核版本与实物，再按症状查；"曾见原因"是诊断候选不是永久事实。每条带 dsh-plugins 仓实证出处（PR/commit/evidence）。0.1.2 期的 14 条构建/工件坑见本技能 [dsh-plugin-development-standards.md](dsh-plugin-development-standards.md) §6，不重复收录。

## 装载与组合

| 症状 | 先查 | 曾见原因与修复 | 出处 |
|---|---|---|---|
| 装载即抛 `stateVersion must be a non-negative integer` | 投影 register definition | **stateVersion 是必填字段**（宿主无条件校验），缺省直接 throw、插件不激活。补 `stateVersion: 0` | PR #11 审查阻塞① |
| 插件日志在、但真实会话从不触发预期行为 | 事件 payload 形态 | **真实 turn id 是数字**（`phase.turn + 1`）；按 `typeof === 'string'` 写守卫会静默放空。接受 number\|string 并字符串化 | PR #11 审查阻塞② |
| onChanged 永远收不到自己单元的通知 | wire 字段 | **通知只走 wire 路径**——不声明 `wire {viewSchema, view}` 的单元不通知 | session-projection drive 实现 |
| 投影通知风暴或缺失 | apply 返回值 | 同引用 = 无变化 = 不通知（Object.is）；要通知必返新对象，无关事件返原引用零成本 | 同上 |
| profile 启动被拒 `must directly include dsh-base before dsh-web-app` | bundles 数组 | **GUI profile 必须直接含 `@deepseek-ai/dsh-web-app`**；headless 无此要求 | pilot-load 实验 F1 |
| `import { 类型 } from '@deepseek-ai/dsh-*'` typecheck 失败但运行时在 | api-catalog | 内嵌树 .d.ts 剥离；类型声明集中在 `dsh-tool-cordis/lib/types/api-catalog.js`——先搜它和各包 README.zh.md 再判"不存在" | PR #3 审查修正 |

## 测试与模块

| 症状 | 先查 | 曾见原因与修复 | 出处 |
|---|---|---|---|
| 遗留 `.js` 源码报 `require is not defined in ES module scope` | 同目录 package.json | 新增的 `"type": "module"` 改变整目录模块解释。去掉 type 声明、ESM 入口改 `.mjs` | PR #7（合并组合回归） |
| 各分支测试全绿、合并后全红 | 跨分支相互作用 | 单分支 diff 看不见共享目录声明的组合效应（package.json type 字段）。**同目录声明变更必须与既有测试组合验证**；合并后全量重跑 | PR #7 教训 |
| mock 测试全绿、真实宿主炸 | mock 是否复刻宿主校验 | mock registry 收任意 definition 掩盖必填校验。mock 复刻宿主校验，或宿主核过一次再信 mock | PR #11 |
| 测试样本行为与宿主不符 | 样本数据形态 | 样本必须贴实物形态（数字 turnId 而非字符串） | PR #11 |
| 并行分支各自测试数与合并后对不上 | 计数口径 | 同基线并行分支各只见自己的新增（83+11/+15/+18 三分支），合并后 main 为并集（127）——验收数字以**合并后 main 实测**为准 | PR #48 验收实证 |
| 多插件共载时自检链误报 FAIL（单插件时全绿） | 自检断言是否全局独占 | 自检断言了「整个会话/全局恰 1 条记录」——共载时看到别的插件 selftest 记录。**自检只断言自身命名空间（按 businessId/key 过滤），别对全局独占做假设** | PR #37（四插件 snapshotLinks 同修） |
| mock ctx（普通对象）全绿、真实宿主装载即抛 `cannot get property "X" without inject` | 可选服务的读取方式 | 真实 cordis ctx 是代理——**未声明 inject 的属性读取直接抛**，mock 普通对象不重现该纪律。可选缝必须 `ctx.get('X')`（mock 假体无 get 时回退属性读，两种 ctx 形态均可驱动）；已 grep 全插件排查同类 | PR #55→#58（headless lab V7 实测抓出） |
| 功能在 mock 全绿、真后端上静默失效（如缓存永不落盘） | 写路径是否过真 schema + 有无 best-effort 吞错 | 域写边界的 `valueSchema.parse` 会拒绝缺字段的记录，而「缓存失败不阻断」的 try/catch 把拒绝**静默吞掉**——两者组合即静默数据丢失。编排器写路径必须有**过真实域校验**的回归用例（不能只用不校验的内存 mock） | PR #62 审查 B1（cachedAt 缺失实测） |
| 门 A/B 串行流程里断言了 B 的结果，B 实际没被执行 | 前一道门是否先行短路 | 门序断言必须确认**前道门没有先行短路**：如 README 翻译的 already_zh 门（首尾中文检测）在授权门之前——fixture 文案混了中文就会在 already_zh 早退，授权门断言全假。fixture 与门序逐段对齐后再断言 | PR #66（driver 首版实测） |
| 「零调用/零网络」证据来自运行时计数器，但复核发现计数恒 0 | 计数器是否真注入被测路径 | 构造了包装却没注入任何服务面的计数器是**死计数器**——恒 0 且不可证伪，比没证据更危险。零调用优先用**代码路径论证**（门在调用点之前 return + dump 佐证），计数器必须真注入 | PR #66 审查 B1 |
| 证据文档说「X 落盘已证」，实际只生成了文件没有写入记录 | 域文件生成 ≠ 记录写入 | storageDomain open 即生成域文件（装载即 open），记录写入是另一回事——门在写入路径之前早退时文件照样在。表述区分「文件级（open）」与「记录级（put/命中读）」 | PR #66 审查 B3 |
| 证据文档说「真引擎不可达时 fail-closed」，实际没发任何网络连接 | 传输形态叙述先核实 | 注入缝缺失 → 离线桩 → status 0，**根本没有 socket 尝试**——「真引擎 X 未起」是虚构叙述。写证据前先确认传输形态（transportKind 字段/装配日志） | PR #66 审查 B2 |
| 多轮实验后早期成功轮的产物丢失，引用字段在库里不存在 | dump 是否同名覆盖 | 同路径多轮 dump 会覆盖——先成功的实验轮产物被后失败轮覆盖，引用即断裂。**每轮异名落盘**；driver 与 dump 同 commit 互证（栈帧行号锚定） | PR #58 审查 B1（run1 产物被覆盖） |
| 投影/记录里的引擎地址与实际转发目标不一致 | 静态 baseUrl vs 动态 currentTarget | 支持动态改址的代理里，`proxy.baseUrl` 是构造期静态值，生效值在 `currentTarget()`——投影/日志落静态值会在 settings 改址后与转发目标错位。记录一律取动态取值器 | PR #66 回归轮暴露、#67 修复 |
| mock 假体逐 open 隔离记录、真后端同域共享 | 同名域多次 open 的语义 | 真实 storageDomain 同名域多次 open 看到同一存储；mock 假体 per-open 隔离会让「跨代水合/回放」用例测出假象。假体按域名共享记录 | PR #57（star-unstar 装载即回放用例） |
| mock storageDomain 全绿、宿主装载即拒 | mock 是否复刻域名校验 | 域名**仅 `[a-z][a-z0-9_]*`（下划线，连字符非法）**——真实后端 kv.open 强校验（backend.ts UNIT_NAME_RE）。mock 的 open() 应加同款正则校验；命名用下划线形态 | PR #42 发现（star_board_list 裁决）、PR #43 修复 session_pilot_board/suit_agent_read |
| 源码钉值核验全绿、实际执行的是另一个文件 | 核验对象与执行对象是否同一文件 | 适配器接受调用方传入的执行路径（如 `renderPath`/`scriptPath`），钉值核验却读 `skillRoot` 下冻结文件——**执行面与核验面解耦**：传 `/unreviewed/x.py` 照样 `ok`+`verified=true`。修复：执行路径必须 realpath 等于钉值文件（`bindPinnedExecutionPath`），否则 SOURCE_DRIFT 预检拒（零 spawn 零 run）；钉值循环改哈希**实际执行文件**；缺省回落语义按分支差异定（必填合同勿降级为可选——md2word 必填 required=true，viz/proposals 缺省回落） | dsh-plugins 裁定 3（PR #203/#204/#205——md2word 首分支漏修被定向复审 PoC 实证） |
| mock 测试全绿、真实持久层该守卫恒空转 | fixture 字段是否伪造了不存在的形状 | 测试 fixture 直接塞了 schema 里不存在的字段（如 run 记录上的 `sessionRefs`），读取端按该形状写——mock 验证了**不存在的形状**，真实存储里守卫永远读 undefined。**fixture 必须源自真实持久形状**（从 schema/写入口面推导）；跨实例语义也要核（另一实例 seed 的 running run 会被本实例懒 open 的 reconcile 语义 unknown 化——同域共享即跨实例可见） | dsh-plugins 013b 上游审计（PR #188/#192/#196 五连返修） |
| CLI 成败只看退出码、或测试改输入让断言通过 | 退出码语义+输入修正的边界 | 外部 CLI 失败仍 exit 0（md2word 布局失败）、或 exit 0+零产物是合法特例——成败须**输出三验**（存在/格式签名/非空白）不信退出码，且三验只能称「文件初筛」（伪头+填充可过，不能证格式完整/图面非空白，保留人工目视）；测试补 frontmatter 使真实链通过属**输入修正非机械勘误**（改变成功用例前提）——须如实登记、保留原失败反例（缺字段稿仍拒），避免改输入掩盖失败 | dsh-plugins 012 三分支（PR #145/#200 裁定 3+PM 收编边界裁定） |
| 「实测先行」产物只有 worker 自跑证据、源漂移时测试不红 | 环境缺失跳过与源漂移失败的区分 | 外部脚本行为（省略 --output-dir 即写源目录/退出码 1 两义同码/缺 CLI 不写某键）靠实测发现后，对应测试若用手写 mock 或环境缺失即 SKIP——**源已变化但用例静默跳过**。区分两态：钉值源在位时漂移即 fail（读源真实字节非伪造），环境不备才 skip；**回退证明**（实现单独回退后新用例转红）验证咬合力；「绝不读取」类红线自证放测试侧，实现零读取（grep 静态钉） | dsh-plugins viz 分支（PR #201/#203 裁定 3 第 3 自疑点+R200-PII-1） |

## 宿主验证与证据纪律（headless lab 波实证，PR #58/#66）

| 症状 | 先查 | 纪律 | 出处 |
|---|---|---|---|
| 证据文档引用的字段在提交产物里不存在 | 每条声称是否有产物支撑 | 证据文档的每条「已证」必须能在随仓产物（dump/listing）中逐字段对上；引用了不存在的产物 = 证据链断裂，审查按 REQUEST_CHANGES 打回 | PR #58 一轮审查 |
| 提交的 driver 产不出提交的 dump | 两者是否同源 | driver 与 dump 必须**同一 commit 互证**（错误栈的文件:行号可反向锚定到入库代码）；叙事时序必须从产物反推，不凭记忆写 | PR #58/二轮审查 |
| headless 组合下 settings 编辑类写路径全抛 `HMR is disposed` | 组合是否含 hmr 条目及其状态 | headless（RunAsNode CLI）组合下经 `configEditor.edit → hmr.runExclusive` 的写路径可能抛宿主侧异常（0.1.7-rc.2 观察，含离线 dump-config 与运行时条目状态矛盾的疑点）——**写路径宿主级验证在 headless 不做，归 GUI 组合窗口**；triage 材料先停盲改 | PR #58（triage-p3-hmr.md） |
| 补证复跑在 enable 段抛 `cannot create effect on inactive context` | fiber 状态与重载时序 | loader 条目 disable→enable 的重载链在 headless 下有时序脆弱性（run1 成功 run5 失败同组合）——重载 enable 半的宿主级结论须谨慎，失败轮如实降级 NOT_VERIFIED 不冒充 | PR #58 二轮 |

## 隔离实验与进程

| 症状 | 先查 | 曾见原因与修复 | 出处 |
|---|---|---|---|
| 实验后生产 profile 选择变了 | 共享 userData | profile-selection 按 userData 存放，`DSH_HOME` 隔离不了。实验前后快照/恢复该文件 | dsh002-gui 实验 F2 |
| 每次启动重弹基础配置向导 | profile-setup/<homeHash>/ | 只有 `state.json.pending` 就重弹；按完成态 schema 补种（7 字段/哈希匹配/outcome/version=2） | pilot-load F4 |
| `open -a` 恢复生产"没反应" | 进程是否真死 | 单例锁把启动请求转发给未死尽的实验实例。**SIGTERM 后循环探测进程消失，确认后才执行恢复命令**（分步、逐门） | consumer-selftest F3 |
| renderer boot failed（30s 健康超时） | stderr + 形态 | 两种形态（compatibility-chrome ERR_FAILED / Unknown client plugin）；五次两现、非系统性；Host 侧不受影响，GUI 验收前置问题 | slice3 F2（含 PR #10 F5 的再定性修正） |
| 全屏截图混入私人窗口 | 取证方式 | 不用全屏截图做宿主证据；Host 半体以宿主日志为权威 | pilot-load F5 |
| `compactUndefinedDeep` 类克隆工具被 `__proto__` 击穿 | JSON.parse 产物 | 自有 `__proto__` 键经普通赋值改写克隆原型（原型污染）。`Object.defineProperty` 落自有键；用攻击载荷回归 | PR #6 审查（bizlink） |

## 版本与研究

| 症状 | 先查 | 曾见原因与修复 | 出处 |
|---|---|---|---|
| 按源码研究写的接口在真机上不存在/变形 | 源码 tag vs 内嵌版本 | 研究版本与安装版错位（0.2.0-rc.1 是 next 线，无桌面内嵌）。**源码固定必须匹配内嵌版**，错位结论按实物重核 | DSH-002（重固定决策） |
| 内嵌包 grep 不到某类型/导出 | README + api-catalog | 包 lib 导出面 ≠ 全树事实；.d.ts 剥离是 0.1.7 现状 | PR #3 |

## 记录约定

新坑按症状入上表：症状（可 grep 的错误特征）→ 先查 → 曾见原因与修复 → 出处（仓内 PR/commit/evidence 路径）。版本敏感结论标注核对版本；被后续版本推翻时保留原条目并加"已失效于 x.y.z"注记，不删历史。

## 宿主 ctx 语义与插件激活（内容工厂 001b-001e 实测批，2026-10-11）

| 症状 | 先查 | 曾见原因与修复 | 出处 |
|---|---|---|---|
| 插件整体不激活（`1 entry did not activate`），headless RPC 全 404，含此前已验收的旧功能 | 辅助模块是否直接读 cordis `ctx` 的未 inject 属性 | **cordis ctx 是 Proxy：未在 inject 声明的属性「读取即抛」**（`cannot get property X without inject`）——`?.` 只防 null/undefined 不防 getter throw。辅助模块签名收 `{ host: ctx }`、模块内读 `host.sessionController` ⇒ apply() 抛错全灭。修复：inject 声明该服务（orchestrator 先例证明可注入）+ 调用点传**已解构纯对象**（不传裸 ctx） | 内容工厂 W7 真机（PR #259） |
| 上述缺陷在单测全绿下漏网 | 测试假件是否模拟宿主语义 | 普通 fakeCtx 读未声明属性返回 undefined **永不抛**——Proxy 语义类缺陷（读取即抛）在普通对象假件下结构性不可见。回归门=**cordis Proxy 语义假件**（get trap 对白名单外属性抛错）+ 形状断言（禁止裸 ctx 下传） | 同上（W7 审查 F1 三重静默教训） |
| 交付轮 PR 夹带「已修复」实为漏提交（同族二次） | 多文件同款修复是否逐文件入库 | 同款修复分散多测试文件时**逐文件 add**，交付前 `git status` 必须干净 + `git branch --show-current` 核对（防 detached/串树） | PR #260/#266 拦截记录 |
| GUI 显示「Unknown client plugin」+ Renderer 30s boot health 超时 | **先对照已知显示伪影**（见 desktop-load-and-isolation「renderer 偶发 boot failed」条的 2026-09-29 静态归因） | 该文案是插件列表空时的**占位伪影**，真实含义=渲染器 30s 整体静默，与被测插件无关。W7 时段与系统代理（scutil --proxy 的 1082）瞬断吻合——三假设中「系统代理」假设的实证。**勿据伪影文案把静默归因为插件问题**（内容工厂 W7 曾误定性后勘正） | 内容工厂 W7（PR #274）+ desktop-load-and-isolation |
| 真机取证（boot 日志/cookie 文件）入库含活凭证 | 入库前脱敏 | boot 日志的 `token=`、cookie 文件的 `v1.eyJ` 签名都是凭证。入库前正则脱敏（**正则须含 cookie 名下划线** `[A-Za-z0-9_]+`——曾漏匹配）；配套销毁隔离 home 的 credentials 使泄露 Cookie 失效 | 内容工厂 W7→PR #268 |
| 多轮真机探针共用实例的结果被串轮污染 | 删除类探针是否破坏后续探针的夹具前提 | R18c 删 objB 批后 R11②④ 被「批不存在」污染——探针幂等重建夹具，或删除类探针放最后 | 内容工厂 W8 复跑 |
| Web 页面路径验证通过 ≠ Desktop GUI 路径通过 | 两条 client 装配链分开验证 | client bundle 在 web server combo（外部 Chromium 连）与 desktop-shell Renderer（Electron 内置）是**两条装配链**——Web 多次通过、GUI 同代码可能「Unknown client plugin」（见上伪影条）。验收口径分开陈述 | 内容工厂 001b-001d |

## slot 抢占与 client 装载契约（DSH-022 C-1 / DSH-023 标记轮实测批，2026-10-17，Desktop 2.0.17 / 0.2.0-rc.2）

| 症状 | 先查 | 曾见原因与修复 | 出处 |
|---|---|---|---|
| web client 永卡 "Loading plugins…"，浏览器 evaluate/DOM 快照全超时、renderer 打满 | 同组合去掉自研插件的对照 profile 是否正常 | 两独立病因可各自单独致死：① slot `register()` 带 `children` 表与官方条目**排他互斥**（后到者抛 `already declared`，未捕获异常中断装载管线）；② client bundle 是裸 ESM 源码——宿主 client-modules 拉取后等待 bundle 调 `window.__ModuleLoader__.load({id, factory})` 注册工厂，裸 ESM 永不注册。修复：shadow 父座位**不带 children 注册**（异 priority 共存 + lowest 渲染，官方子座位声明与子 entry 全保留可消费）+ 构建链产出工厂封装 bundle（`build-client.mjs`，pdf-organizer/registry-board 先例：`require('react')` 由 loader 供给） | dsh-plugins PR #339（C-1 报告四场景 SlotCore 复演 + 真宿主双对照） |
| web boot 报 "entry did not activate"，自研 client 插件不激活 | client 模块是否导出 `inject` 服务键 | client 插件契约：模块导出的插件对象需含 `inject:['slots',…]`——**服务键**（非模块 id）。`ctx.slots` 只有声明后才可读（client runner 激活门，"slots and theme are the usual UI seats"）。注意与 package.json `dsh.client.inject`（模块图依赖边，写模块 id）是**两层不同声明**，都要写 | 同上 |
| Host 半体 `TypeError: Invalid effect`（cordis safeCollect 栈） | `apply(ctx, config)` 的 return 值 | cordis `_execute` 把 apply 的返回值当 effect 处置器收集：函数→collect、可空→忽略、**其余（含服务对象）→抛**。服务面只经 `ctx.provide` 交付，apply 不返回 | 同上 |
| Host 半体 `failed to import`（隔离 profile `link:` 装载，仓内测试却全绿） | package.json `dependencies` vs 实际 import 清单 | undeclared 依赖（如 zod）在隔离 profile 不会被安装——仓内测试靠仓库根 node_modules 解析成功=假绿。schema 走零依赖 duck-typed（PR #35 纪律）或如实声明依赖 | 同上 |
| 装载自检在真宿主收敛 `reading 'warn'` 类 TypeError，mock 级长期绿 | rig/派生 ctx 是否用 `{...ctx}` 展开 | 真实 cordis ctx 是 Proxy：logger/llm **非自有可枚举属性**，展开只剩 `{fiber}`；mock 普通对象展开保留字段——结构性假绿。修复：派生 ctx 用**显式字段**（`{ bizLink, logger: ctx.logger, llm: ctx.llm }`）；回归用例把字段挂**原型**复刻代理展开语义 | dsh-plugins PR #338 |
| `dsh plugin add` 等子命令静默：零输出、零副作用、exit 0 | PATH 首位的 node 版本 | standalone dsh CLI 入口守卫 `if (import.meta.main) await runCli()`——node v20.12 无 `import.meta.main`（undefined），shebang `env node` 解析到旧 node 时整个 CLI **静默 no-op**。修复：dsh 调用统一前置 v24+ 的 bin 到 PATH | dsh-plugins DSH-023 标记轮 |
| pre-push 全套门禁时序敏感测试闪断（全并行红、单文件绿） | 是否有隔离实验的 Electron host 未清 | 实验 host 进程吃满核导致 timing 断言漂移——**推门前先杀 lab host**（`pkill -f "profile <名>"`） | 同上 |
| 浏览器观察 DSH web client：evaluate/DOM 快照周期性超时 | 先跑对照 profile 定基线 | 重型 SPA 会饿死观察通道（健康页面也可能间歇超时）。替代观察面：curl+cookie 会话提取 HTML 内联 `__DSH_BOOT__` manifest（client 模块图权威）、整页截图、DOM 快照文本比对 | dsh-plugins PR #339 |
| 装配后立即抓 web token 拿到空值/旧值 | boot 日志是否已出现 "dsh web" 行 | `plugin add` 触发的 boot 里 URL 行有延迟——轮询等行出现再取 token | 同上 |
