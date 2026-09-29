# Host 插件要领与版本差异（0.1.7-rc.2 实测）

出处：dsh-plugins 仓 PR #5/#7/#9/#11 及五次装载实验（evidence/dsh-*-20260929）。0.1.2 期规范见本技能 [dsh-plugin-development-standards.md](dsh-plugin-development-standards.md)；本文只记增量与差异。

## 插件形态（最小可装载集）

- **function plugin**：`export const name / inject / apply`（命名导出，无 default）；`apply` 可为 async（await 后再 provide 也正常装载）。
- **包声明**：package.json 的 `dsh.bundle.patch` 指向 cordis.patch.yml；insert 行只要求 `id` 与 `name` 均为 string（plugin-manager declaredRows 校验；name 不得以 `.`/`/` 开头或含 `:`）。`dsh.manifestVersion` 可选（安装器/加载器不强制）。
- **入口解析**：Loader 对 insert 行 name 做裸 `import(name)`（Node ESM 包解析，`exports` 优先 `main`），`unwrapExports` 取 `exports.default ?? exports`。
- **module 身份**：`ctx.logger` 名 = 导出 `name`（日志中 `[session-pilot-dsh]`）——把它当装载观测锚点。

## 同目录遗留 CJS 源码的共存规则（实测组合回归，PR #7）

- 在既有 `.js` 源码目录新增 package.json 时：**不要声明 `"type": "module"`**——它会改变同目录全部 `.js` 的模块解释，CommonJS 遗留文件（require）从测试侧被 require 时直接报 `require is not defined in ES module scope`。
- 正确做法：不声明 type，ESM 入口用 **`.mjs` 扩展名**（Node 按扩展名识别，与 type:module+.js 等价且不外溢）。
- 该类回归在单分支审查视角下不可见（各自分支都绿），合并后必现——涉及共享目录声明的变更必须与既有测试套件组合验证。

## cordis ctx 实证（0.1.7-rc.2）

- `ctx.provide(name, service)`：注册命名服务；消费者 `inject=['name']` 等待（服务缺失时消费者不激活、不失败）。
- `ctx.logger.info/warn`：宿主日志（logs/host/dsh-<date>.log）。
- `ctx.effect(() => () => dispose())`：**回调必须返回 disposer**；fiber 卸载自动执行——插件卸载清理由此承担，不手工簿记。
- 多插件共存：同 profile 内先后 apply（日志毫秒级相邻），无顺序竞态；inject 的等待语义保证消费方晚于服务方。

## 零依赖与 schema 策略

- `@deepseek-ai/*` 全部视为宿主 external，不进 dependencies——本地 link 安装即零物化装载（官方 bundle 从安装锚点解析）。
- 需要 Schema 形对象（如投影的 stateSchema/viewSchema，运行时只调 `.parse(v)`）时：duck-typed 恒等 `{ parse: (v) => v }` 可满足运行时（identitySchema 先例，PR #11）；正式化再换声明式（届时依赖策略需重议）。
- 服务间不共享 JS 对象到 client——client 通道走官方 connection（RPC/SSE），见 contract-copilot src/host-api.ts 先例（0.1.2 形态，0.1.7 运行时面已核在）。

## 类型查找路径（0.1.7 关键差异）

- **内嵌树全部包的 .d.ts 已被剥离**（仅剩 .d.ts.map，package.json types 字段指向不存在文件）——内嵌树只能验证运行时符号；类型级核对用 npm 分发包或 api-catalog。
- **`dsh-tool-cordis/lib/types/api-catalog.js` 是全量类型声明库**：`PreStepDecision`（:5855）、`ToolRunContext`（:7503）、`ToolDefinition`（:7416，execute 签名即用 ToolRunContext）等都在这里。各包 `README.zh.md` 也常带类型文档（dsh-agent README:85 记 PreStepDecision 形状）。
- **教训**：包 lib 导出面 grep 不到 ≠ 全树缺失。0.1.2 式 `import { PreStepDecision } from '@deepseek-ai/dsh-agent'` 会失败（类型不在包导出面）——改引 api-catalog 来源或本地声明；先搜 README + api-catalog 再下"不存在"结论（dsh-plugins PR #3 审查修正的实证）。

## 0.1.2 → 0.1.7 迁移要点（对照 lint 规范逐项）

| 主题 | 0.1.2 规范 | 0.1.7-rc.2 实测 |
|---|---|---|
| agents 服务 | `ctx.agents.create/resume/get` | 形状不变（sessionId/meta/agentOptions、resumeSessionId 均在） |
| agent/pre-step | waterfall，decision `{kind:'enter'/'reject'}` | 不变（dsh-agent-loop:911-920）；`{prepend:true}` 仍被读取 |
| PreStepDecision/ToolRunContext 类型 | 从原包 import | 不在包导出面；声明在 api-catalog（见上） |
| schemastery | ^3.18.1 | 3.18.4，default 导出 Schema（lib/index.mjs 尾） |
| cordis | 4.0.2 | 4.0.4（provide/notify/Service/effect 均在，inject 等待语义同） |
| dsh-code-runtime | devDep 常见 | 内嵌树缺失（源码零引用则低影响） |
| 依赖钉定 | 0.1.2-rc.1 | 真实宿主内嵌 0.1.7-rc.2——dedupe 策略未验证前存在双版本 schema 漂移风险（P1，contract-copilot 差距调研） |
