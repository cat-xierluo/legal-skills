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
| mock 假体逐 open 隔离记录、真后端同域共享 | 同名域多次 open 的语义 | 真实 storageDomain 同名域多次 open 看到同一存储；mock 假体 per-open 隔离会让「跨代水合/回放」用例测出假象。假体按域名共享记录 | PR #57（star-unstar 装载即回放用例） | 域名**仅 `[a-z][a-z0-9_]*`（下划线，连字符非法）**——真实后端 kv.open 强校验（backend.ts UNIT_NAME_RE），mock 假体不校验就漏检。mock 的 open() 应加同款正则校验；命名用下划线形态 | PR #42 发现（star_board_list 裁决）、PR #43 修复 session_pilot_board/suit_agent_read |

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
