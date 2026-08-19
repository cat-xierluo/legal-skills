# DSH 插件开发规范（dsh-plugin-development-standards）

DeepSeek Harness（DSH）out-of-tree 插件的开发范式。事实核对于 2026-08-19，对应 harness 版本 **0.1.0-rc.7**（npm 已发布同版本）。DSH 处于 rc 阶段——**升级后按 §参考文件索引 逐条复核**，不采信本文记忆。

来源：dsh-contract-copilot 插件全程开发实测（含多轮 e2e 与浏览器验证），踩坑记录见文末"实测坑清单"。

## 1. 插件形态与分发

- **function plugin**：`export const name / inject / Config / apply(ctx, config)`（命名导出，无 default export）
- **声明 bundle**：`package.json` 的 `"dsh": { "bundle": { "patch": "./cordis.patch.yml" } }`
- **patch 层**：`cordis.patch.yml` 里 `- insert: [{id, name}]` 插入插件 row；profile/用户层可用裸 `- id:` + `config:` 按 id 覆盖整行 config（**必须重述该 row 全部键**，patch 是整行替换不深合并）
- **安装链**（publish.md 全部核实）：
  - `dsh plugin --profile <name> add ./<dir>` → pnpm link → `reconcilePlugins`（`apps/cli/src/plugin.ts:59`）把包追加进 `dsh.profile.bundles`
  - GitHub 安装：`dsh plugin --profile <name> add github:<owner>/<repo>`；需包自带**自包含** `prepare` 脚本（不假设 monorepo）+ 用户侧 `pnpm-workspace.yaml` 加 `allowBuilds: { '<pkg-full-name>': true }`
  - tarball（`pnpm pack`）与 npm publish 是免 allowBuilds 的替代；scoped 包 npm 发布需 `publishConfig.access: "public"`
- **配置**：schemastery `z.object({...})` 导出 `Config`；误配 fail loud（apply 里校验并 throw）
- **profile 层序**：bundles 依序 → profile `cordis.patch.yml` → `$DSH_HOME/cordis.patch.yml` → `--patch` 覆盖

## 2. 工具（model-facing）

```ts
import { defineTool } from '@deepseek-ai/dsh-tools'
ctx.tools.register(defineTool({
  name: 'xxx_yyy',
  description: '…',
  parameters: { key: { type: 'string', required: true, description: '…' } },
  output: { schema: { type: 'object' }, render: (_args, value) => [{ type: 'text', text: … }] },
  async execute(args, exec) { return value },
}))
```

硬约束（全部实测）：

- **lossless JSON**：返回值任何属性值为 `undefined` 都被 `walkJsonValue` 拒（**递归**，`packages/core/session/src/json.ts`）——返回前深度剥离 undefined
- **DSL 限制**：`parameters` 不支持对象嵌套对象（拍平为顶层字段）；独立 const 的 schema 字面量要 `as const`（否则字面量类型被拓宽、判型失败）
- `execute(args, exec)`：`exec.signal` 必须响应（长任务传给 spawn 的 AbortSignal）
- 长任务可前台 await（耦合 signal）；后台任务用 `ctx.jobs.start`
- **退码语义**：域结果（如"部分成功"）进 canonical value 不 throw；基础设施失败才 throw

## 3. 事件与上下文注入

- 事件表：`packages/core/agent/src/runtime-types.ts`。`agent/pre-step` 是 waterfall，payload `{agent, messages, turn, step, signal}`，返回 `PreStepDecision`。**没有 `agent/post-step`**——状态写盘放 tool handler 内
- 参照实现：`packages/context/time-context/src/index.ts:170`（`{prepend:true}` + `createUserMessage({content:[{type:'text',text}], source:{kind:'plugin',...}})`）
- 工具结果观察：`tools/post-execute`（waterfall 可替换 value，但失败路径拿不到 value）
- ask 用户：内置 `ask_user_question` tool（`packages/interaction/tool-ask-user`）

## 4. 浏览器 UI（dsh.client 双面包）

把插件 UI 长进 DSH web app 的**官方路径**：

1. **声明**：`package.json` 加 `"dsh": { "client": { "platform": "web", "inject": [...] } }` + `exports["./client"]` 指向 `./lib/client.js`
2. **扫描与服务**：`packages/client/modules`（`ClientModuleRegistry`）扫 loader 全部 entries（**out-of-tree link 的包同样命中**，`createRequire(ctx.baseUrl).resolve`），写入 `window.__DSH_BOOT__`，按 `/plugins/<id>/client.js` serve 磁盘路径
3. **client half**：`src/client/index.ts(x)` 是浏览器端 cordis function plugin，`ctx.slots.inject('<slot>', () => ctx.slots.register({...}, ReactComponent))`
4. **host↔client 数据**：host half 用 `ctx.webServer.register({kind:'prefix', path, handler})` 注册同源路由，client 直接 fetch（session-log-export 先例）；**可选服务用 `ctx.get('webServer')`**（硬 `inject` 会在无该服务的 profile 里让整个插件不激活）
5. **slot 类型来源**：slot 的运行时声明与 TS 类型都在所属 client 包（如 `conversation.*` 在 `@deepseek-ai/dsh-client-ui-conversation`）——out-of-tree 需要 devDep（类型）+ `dsh.client.inject`（加载顺序）双保险

### 真实 slot 名（rc.7 实测枚举）

| slot | 用途 | 先例 |
|---|---|---|
| `settings.general.item` / `settings.section` | 设置页行/区 | ui-theme、ui-agent-preset |
| `conversation.session.header.utilities` / `.actions` | 会话头部按钮区 | session-log-export |
| `conversation.input.dock` | 输入区 dock 面板 | TodoPanel、QueueDock、ui-goal |
| `conversation.chat.node` | 聊天消息节点渲染 | ui-conversation、ui-goal |
| `conversation.chat.turnTail` / `assistant-actions` | 消息尾部动作 | ui-conversation |
| `conversation.view` | 会话主视图（chain） | ui-conversation |
| `conversation.details.tool` | 详情面板 tool 区 | ui-conversation |
| `sidebar` / `sidebar.workspaces.directoryFlow` | 侧栏 | ui-layout、directory-picker |
| `conversation.hero.workspace` / `.agentPreset` | 空态 hero | ConversationRoot |

### client bundle 构建契约（out-of-tree 必须复刻）

harness 的共享预设 `packages/client/tsdown.client.ts` 不对外发布，自行用 tsdown 复刻：

- `format: 'cjs'`、`platform: 'browser'`、entry `src/client/index.tsx` → 产物 `lib/client.js`
- **banner**：`window.__ModuleLoader__.load({ id: <JSON包名>, factory: (require) => {` + **换行 + `var module = { exports: {} }; var exports = module.exports;`**
- **footer**：`return module.exports; } });`
- **externals**（冻结模块表提供，不打包）：`react`、`react/jsx-runtime`、`react-dom`、`react-dom/client`、`@deepseek-ai/cordis`、`@deepseek-ai/dsh-client-ui-slots`、`@deepseek-ai/dsh-client-web-react`、`@deepseek-ai/dsh-client-ui-primitives`、`@deepseek-ai/dsh-client-ui-attachment`、`@deepseek-ai/dsh-client-schema-form`、`@deepseek-ai/dsh-client-runtime/client`；**其余依赖全部 inline**
- `define`：`process.env.NODE_ENV`、`import.meta.env(.MODE)` 静态替换
- `sourcemap: true`；`clean: false`（别清掉同目录 node half 产物）
- **纯度规则**：非平台表的 `@deepseek-ai/*` 值导入禁止（跨插件协作走 cordis 服务；type-only import 被擦除不受限）

## 5. 运行与 provider

- 从源码跑：harness 仓库内 `pnpm dsh --profile <name> [task]`（headless 单任务）或 `pnpm dsh web --port <n>`
- LLM provider：`DEEPSEEK_BASE_URL` / `DEEPSEEK_API_KEY` 指向任何 OpenAI 协议兼容网关（实测 127.0.0.1:8787 网关 + deepseek-v4-flash）
- **HMR 边界**：out-of-tree 插件更新（node 或 client half）后**必须重启 dsh**——`ClientModuleRegistry` 的 rev 只在启动/内部事件时重扫，`rebuilt()` 只被 harness 仓库 `dev:web` watcher 触发

## 6. 实测坑清单（契约层审查项的出处）

1. banner 缺 `var module = { exports: {} }` → 浏览器端 `exports is not defined`
2. `"type":"module"` 包 cjs 产物默认 `.cjs` 后缀 → registry 找不到 exports 指向的 `./lib/client.js`
3. tool 返回值嵌套 undefined → `value is not lossless JSON`（ToolOutputError）
4. SlotMap 类型只在 slot 所属 client 包声明 → typecheck 报 slot 只认 `'root'`
5. 长 CLI 任务用 `spawnSync` → 冻结整个 harness（HMR/UI/listener 全停）
6. 被调 CLI 的非交互静默默认值（如"强势"口径）→ 必须插件层显式传参
7. `ctx.effect` 回调必须**返回** disposer（`() => () => {...}`）
8. 可选服务用硬 `inject` → headless profile 里整个插件不激活
9. shell 管道 `cmd | grep | head && next` 吞掉构建失败 → 旧 bundle 静默留盘
10. JSX 文本里的 `<中文>` 被当标签解析 → 转义 `{'<…>'}`

## 参考文件索引（harness 仓库内）

| 主题 | 路径 |
|---|---|
| 插件教程（function plugin/工具/配置） | `docs/user/develop/basic/index.md`、`tool.md`、`config.md` |
| 打包与安装（bundle/profile/GitHub） | `docs/user/develop/basic/publish.md` |
| 插件 CLI（reconcilePlugins） | `apps/cli/src/plugin.ts` |
| 工具契约（execute/output/后台任务/Code Mode） | `docs/cookbook/adding-a-tool.md` |
| 工具运行时源码 | `packages/core/tools/src/index.ts` |
| lossless JSON 校验 | `packages/core/session/src/json.ts` |
| agent 事件声明 | `packages/core/agent/src/runtime-types.ts` |
| pre-step 参照 | `packages/context/time-context/src/index.ts` |
| ask_user 工具 | `packages/interaction/tool-ask-user/src/index.ts` |
| client 模块扫描（dsh.client） | `packages/client/modules/src/index.ts` |
| slot 注册表（ui-slots） | `packages/client/ui-slots/` |
| slot 注入先例 | `packages/client/ui-theme/src/client/index.ts`、`packages/session-query/session-log-export/src/client/index.ts` |
| client 构建预设（契约蓝本） | `packages/client/tsdown.client.ts`、`packages/client/web/src/platform.ts`、`packages/client/web/src/seed.ts` |
| 动态插件运行器（进阶） | `packages/extensions/cordis-client-runner/` |
| base bundle（默认插件清单） | `packages/bundle/base/cordis.patch.yml` |
| web bundle | `packages/bundle/web-app/cordis.patch.yml` |

## 范式实例

完整双面包实例见 dsh-contract-copilot 插件仓库（`legal-dsh-plugin/dsh-contract-copilot`）：host half（`src/index.ts`、`src/tools/*`、`src/host-api.ts`）、client half（`src/client/`）、构建（`tsdown.client.config.ts`）、文档四件套。