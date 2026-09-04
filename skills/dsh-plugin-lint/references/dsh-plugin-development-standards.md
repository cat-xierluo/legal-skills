# DSH 插件开发规范（dsh-plugin-development-standards）

DeepSeek Harness（DSH）out-of-tree 插件的开发范式。事实核对于 **2026-09-04，对应 harness 0.1.2-rc.1（commit `76fda729`）**；0.1.0-rc.7 时期的历史结论单独标注。DSH 处于 rc 阶段——**升级后按 §参考文件索引 逐条复核**，不采信本文记忆。机械层核查可用 `dsh-plugin-lint/scripts/lint.mjs --harness-root <DSH 源码仓库>` 自动对账（版本、平台模块表、inject/external、主题变量均从当前源码声明读取）。

来源：dsh-contract-copilot 插件全程开发实测（含多轮 e2e 与浏览器验证）+ 0.1.2-rc.1 源码核对，踩坑记录见文末"实测坑清单"。

## 1. 插件形态与分发

- **function plugin**：`export const name / inject / Config / apply(ctx, config)`（命名导出，无 default export）
- **声明 bundle**：`package.json` 的 `"dsh": { "bundle": { "patch": "./cordis.patch.yml" } }`
- **patch 层**：`cordis.patch.yml` 里 `- insert: [{id, name}]` 插入插件 row；profile/用户层可用裸 `- id:` + `config:` 按 id 覆盖整行 config（**必须重述该 row 全部键**，patch 是整行替换不深合并）
- **安装链**（publish.md 核对过）：
  - `dsh plugin --profile <name> add ./<dir>` → pnpm link → `reconcilePlugins`（`apps/cli/src/plugin.ts`）把包追加进 `dsh.profile.bundles`
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

- **lossless JSON**：返回值任何属性值为 `undefined` 都被 `walkJsonValue` 拒（**递归**，0.1.2 位于 `packages/util/values/src/index.ts`；旧路径 `packages/core/session/src/json.ts` 已不存在）——返回前深度剥离 undefined
- **DSL 限制**：`parameters` 不支持对象嵌套对象（拍平为顶层字段）；独立 const 的 schema 字面量要 `as const`（否则字面量类型被拓宽、判型失败）
- `execute(args, exec)`：`exec.signal` 必须响应（长任务传给 spawn 的 AbortSignal）
- 长任务可前台 await（耦合 signal）；后台任务用 `ctx.jobs.start`
- **退码语义**：域结果（如"部分成功"）进 canonical value 不 throw；基础设施失败才 throw

## 3. 事件与上下文注入

- 事件表：`packages/core/agent/src/runtime-types.ts`（0.1.2 复核存在）。`agent/pre-step` 是 waterfall，payload `{agent, messages, turn, step, signal}`，返回 `PreStepDecision`。**没有 `agent/post-step`**——状态写盘放 tool handler 内
- 参照实现：`packages/context/time-context/src/index.ts`（`{prepend:true}` + `createUserMessage({content:[{type:'text',text}], source:{kind:'plugin',...}})`）
- 工具结果观察：`tools/post-execute`（waterfall 可替换 value，但失败路径拿不到 value）
- ask 用户：内置 `ask_user_question` tool（`packages/interaction/tool-ask-user`）

## 4. 浏览器 UI（dsh.client 双面包）

把插件 UI 长进 DSH web app 的**官方路径**：

1. **声明**：`package.json` 加 `"dsh": { "client": { "platform": "web", "inject": [...], "external": [...] } }` + `exports["./client"]` 指向 `./lib/client.js`
2. **扫描与服务**：`packages/client/modules`（`ClientModuleRegistry`）扫 loader 全部 entries（**out-of-tree link 的包同样命中**），写入 `window.__DSH_BOOT__`，按 `/plugins/<id>/client.js` serve 磁盘路径；manifest 解析器对畸形字段整包抛错拒绝激活
3. **client half**：`src/client/index.ts(x)` 是浏览器端 cordis function plugin，`ctx.slots.inject('<slot>', () => ctx.slots.register({...}, ReactComponent))`
4. **host↔client 数据**：host half 用 `ctx.webServer.register({kind:'prefix', path, handler})` 注册同源路由，client 直接 fetch（session-log-export 先例）；**可选服务用 `ctx.get('webServer')`**（硬 `inject` 会在无该服务的 profile 里让整个插件不激活）
5. **slot 类型来源**：slot 的运行时声明与 TS 类型在所属 client 包的**类型化 slot catalog**（`packages/client/<pkg>/src/client/contract/slots.ts`，0.1.2 起的声明权威）——out-of-tree 需要 devDep（类型）+ `dsh.client.inject`（加载顺序）双保险

### dsh.client 字段语义（0.1.2 manifest.ts 核对）

| 字段 | 语义 | 错误后果 |
|---|---|---|
| `platform` | 必须字符串 `"web"` | 非字符串抛错 |
| `inject` | 包名依赖边：工厂先达 + cordis 组合 | 非字符串数组抛错；指向未声明 `dsh.client` 的包则该边永远等不到 |
| `external` | 精确的非基线模块表请求（`<pkg>/client` 与 `<pkg>` 归一等价） | 非字符串数组抛错；**声明自身包名 harness 直接抛错拒绝启动** |
| `immediately` | 一阶段预取标记（boolean） | 非 boolean 抛错 |

### 真实 slot 名（0.1.2-rc.1 catalog 复核；以所属包 `contract/slots.ts` 为准）

| slot | 声明 catalog（0.1.2） |
|---|---|
| `settings.general.item` / `settings.section` | `ui-settings/src/client/contract/slots.ts` |
| `conversation.session.header` / `.actions` / `.utilities` / `.lineage` | `ui-conversation/.../contract/slots.ts` |
| `conversation.input.dock` | `ui-conversation/.../contract/slots.ts` |
| `conversation.chat.node` / `conversation.chat.turnTail` / `conversation.chat.assistant-actions` | `ui-chat/.../contract/slots.ts`（0.1.2 起归 ui-chat） |
| `conversation.view` / `conversation.details.tool` | `ui-conversation/.../contract/slots.ts` |
| `sidebar` / `sidebar.workspaces.directoryFlow` | `ui-sidebar/.../contract/slots.ts` |
| `conversation.hero.workspace` / `.agentPreset` | `ui-conversation/.../contract/slots.ts` |

升级后先对 catalog 复核（`grep -r "contract/slots.ts" packages/client`），不采信本表。

### client bundle 构建契约（out-of-tree 必须复刻）

harness 的共享预设 `packages/client/tsdown.client.ts` 不对外发布，自行用 tsdown 复刻（0.1.2 dsh-contract-copilot 的 `tsdown.client.config.ts` 是可用蓝本）：

- `format: 'cjs'`、`platform: 'browser'`、entry `src/client/index.tsx` → 产物 `lib/client.js`（`entryFileNames` 钉死 `client.js`）
- **banner**：`window.__ModuleLoader__.load({ id: <JSON包名>, factory: (require) => {`；**intro**（换行）：`var module = { exports: {} }; var exports = module.exports;`；**footer**：`return module.exports; } });`
- **externals = 平台基线 ∪ 本包 `dsh.client.external` 声明**，二者精确匹配（其余依赖全部 inline）。平台基线唯一事实源是 `packages/client/web/src/platform.ts` 的 `PLATFORM_MODULES` + `PRELOADED_CLIENT_EXTERNALS`（0.1.2-rc.1 为 8 项：`react`、`react/jsx-runtime`、`react-dom`、`react-dom/client`、`@deepseek-ai/cordis`、`@deepseek-ai/dsh-client-store`、`@deepseek-ai/dsh-client-ui-slots`、`@deepseek-ai/dsh-client-ui-primitives`；`PRELOADED` 为空）。**不要在插件里手抄冻结副本**——升级即漂移；lint.mjs 会把构建配置 external 对当前基线对账
- `define`：`process.env.NODE_ENV`、`import.meta.env(.MODE)` 静态替换
- `sourcemap: true`；`clean: false`（别清掉同目录 node half 产物）
- **纯度规则**（`tsdown.client.ts` 的 build-time gate）：非基线、非 `dsh.client.external` 的 `@deepseek-ai/*` 值导入 = 构建错误，除非命中 `INLINE_SAFE`（wire 层，如 `dsh-file-reference`/`dsh-session`/`dsh-llm`/`dsh-tools`/`dsh-util-*` 等内联即无害的层）、`VENDORED_LIBRARY`（`cosmokit`/`schemastery`）或 `<pkg>/remote` 生成贡献——正则的当前事实源同样是 `packages/client/tsdown.client.ts`；type-only import 被擦除不受限。跨插件协作走 cordis 服务

### 主题变量（0.1.2 新增审查维度）

DSH 平台 CSS 自定义属性（`--dsw-*` 设计平台、`--ds-*` 基础、`--shiki-*` 代码高亮）的**唯一声明集**在 `packages/client/ui-theme/src/styles/*.css`（`design-platform.css` 数百个 token + `base.css`/`scrollbar.css` 等）。插件只能引用其中存在的变量；`var(--x, fallback)` 的回退值只是兜底显示，变量名不存在时主题（如暗色）链路已断。lint.mjs §6 按当前 harness 声明集对账。

### 类型化 locale（0.1.2 起的产品文案归属）

- 每个插件自带命名空间词典（先例 `packages/client/ui-theme/src/client/locales.ts`）：**zh 是键集真值**，`en` 用 `satisfies Record<ThemeKey, string>` 对齐 zh 键集（缺键/多键编译报错）
- 组件经 `PropsLocale<'namespace'>` 注入翻译座席，`t('key')` 消费；`Translate`/`LocaleNamespaceMap` 类型由 `@deepseek-ai/dsh-client-ui-slots` 提供，词典 owner 声明 `declare module` 合并自己的命名空间
- **JSX 文本/用户可见属性裸写产品文案即违约**；lint.mjs §7 检查 CJK 硬编码与 zh/en 平价

## 5. 运行与 provider

- 从源码跑：harness 仓库内 `pnpm dsh --profile <name> [task]`（headless 单任务）或 `pnpm dsh web --port <n>`；已构建产物可用 `node apps/cli/lib/bin.js --version` 直接取官方版本门
- LLM provider：`DEEPSEEK_BASE_URL` / `DEEPSEEK_API_KEY` 指向任何 OpenAI 协议兼容网关（实测 127.0.0.1:8787 网关 + deepseek-v4-flash）
- **HMR 边界（历史结论，未随版本复测）**：0.1.0-rc.7 时期双向实测 out-of-tree 插件两个 half 都不热加载——node half 改 `lib/` 后长驻进程不重载 apply；client half 的 `__DSH_BOOT__` rev 只在启动时重扫；唯一热的是 profile `cordis.patch.yml` 配置层。**该结论未在 0.1.2 复测**：作为待验证假设处理，更新 bundle 后先重启 dsh 再取证，并以当前 `packages/client/hmr` 实测为准

## 6. 实测坑清单（契约层审查项的出处）

1. banner 缺 `var module = { exports: {} }` → 浏览器端 `exports is not defined`
2. `"type":"module"` 包 cjs 产物默认 `.cjs` 后缀 → registry 找不到 exports 指向的 `./lib/client.js`
3. tool 返回值嵌套 undefined → `value is not lossless JSON`（ToolOutputError）
4. SlotMap 类型只在 slot 所属 client 包声明 → typecheck 报 slot 只认 `'root'`（0.1.2 声明权威是所属包 `contract/slots.ts`）
5. 长 CLI 任务用 `spawnSync` → 冻结整个 harness（HMR/UI/listener 全停）
6. 被调 CLI 的非交互静默默认值（如"强势"口径）→ 必须插件层显式传参
7. `ctx.effect` 回调必须**返回** disposer（`() => () => {...}`）
8. 可选服务用硬 `inject` → headless profile 里整个插件不激活
9. shell 管道 `cmd | grep | head && next` 吞掉构建失败 → 旧 bundle 静默留盘
10. JSX 文本里的 `<中文>` 被当标签解析 → 转义 `{'<…>'}`
11. 构建配置手抄平台基线副本 → harness 升级后基线漂移，产物 bare require 模块表无法应答（浏览器必抛）——externals 集合只准"基线 ∪ dsh.client.external"推导
12. `dsh.client.external` 声明自身包名或拼错说明符 → host 端抛错/边等待，插件整包不激活
13. 引用不存在的 `--dsw-*` 主题变量（靠 fallback 显示）→ 暗色主题断链，且机械层不报错——只准引用 `ui-theme/src/styles` 声明集
14. 产品文案裸写 JSX/属性 → 无语言切换、无词典平价保护——迁入命名空间 locale 词典

## 参考文件索引（harness 仓库内，0.1.2-rc.1 复核）

| 主题 | 路径 |
|---|---|
| 插件教程（function plugin/工具/配置） | `docs/user/develop/basic/index.md`、`tool.md`、`config.md` |
| 打包与安装（bundle/profile/GitHub） | `docs/user/develop/basic/publish.md` |
| 插件 CLI（reconcilePlugins） | `apps/cli/src/plugin.ts`；官方版本门 `apps/cli/lib/bin.js --version` |
| 工具契约（execute/output/后台任务/Code Mode） | `docs/cookbook/adding-a-tool.md` |
| 工具运行时源码 | `packages/core/tools/src/index.ts` |
| lossless JSON 校验（walkJsonValue） | `packages/util/values/src/index.ts` |
| agent 事件声明 | `packages/core/agent/src/runtime-types.ts` |
| pre-step 参照 | `packages/context/time-context/src/index.ts` |
| ask_user 工具 | `packages/interaction/tool-ask-user/src/index.ts` |
| client 模块扫描（dsh.client 字段语义） | `packages/client/modules/src/index.ts`、`packages/client/modules/src/client/manifest.ts` |
| 平台模块表（externals 基线唯一事实源） | `packages/client/web/src/platform.ts` |
| client 构建预设与纯度正则（契约蓝本） | `packages/client/tsdown.client.ts` |
| slot 类型化 catalog（声明权威） | `packages/client/<pkg>/src/client/contract/slots.ts` |
| slot 注入先例 | `packages/client/ui-theme/src/client/index.ts`、`packages/session-query/session-log-export/src/client/index.ts` |
| 类型化 locale 体系 | `packages/client/locale/src/`（含 `locales/zh.ts` 键集真值） |
| 主题变量声明集 | `packages/client/ui-theme/src/styles/*.css` |
| 动态插件运行器（进阶） | `packages/extensions/cordis-client-runner/` |
| base bundle（默认插件清单） | `packages/bundle/base/cordis.patch.yml` |
| web bundle | `packages/bundle/web-app/cordis.patch.yml` |

## 范式实例

完整双面包实例见 dsh-contract-copilot 插件仓库（`legal-dsh-plugin/dsh-contract-copilot`）：host half（`src/index.ts`、`src/tools/*`、`src/host-api.ts`）、client half（`src/client/`，0.1.2 工作台版）、构建（`tsdown.client.config.ts`，externals 从基线推导）、文档四件套。
