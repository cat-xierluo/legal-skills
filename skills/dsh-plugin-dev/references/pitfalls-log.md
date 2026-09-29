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
