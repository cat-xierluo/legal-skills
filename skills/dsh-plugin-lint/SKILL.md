---
name: dsh-plugin-lint
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.0.0"
license: MIT
description: DeepSeek Harness（DSH）插件的设计预检、质量审查与发布验收工具（版本感知）。在用户创建、重大改造或审查 DSH 插件（dsh.bundle / dsh.client 双面包），需要核对 harness 事实引用、工件契约、inject/external 对账、主题变量、类型化 locale、lossless JSON、fail-loud 语义，或发布前验收 boot/浏览器证据时使用。开发规范见 references/dsh-plugin-development-standards.md。不要用于：普通 npm 包审查、与 DSH 无关的 agent 项目。
---

# DSH Plugin Lint

审查一个 DSH 插件是否：声明与工件一致、对 harness 的引用真实存在、契约坑已规避、文档已同步、验收证据可绑定候选。

开发与范式依据：[references/dsh-plugin-development-standards.md](references/dsh-plugin-development-standards.md)（插件形态、分发、工具/事件/slot、client 工件契约、类型化 locale、主题变量、harness 参考文件索引）。

本技能不代替实现者。创建插件时先做设计预检，实现后回来做正式验收——审查器与生产者不混同责任。

配套文件：
- `scripts/lint.mjs` → §1 机械层（版本感知，规则清单见下）
- `scripts/test-lint.mjs` → 自测（自包含 fixture，证明每条规则抓得住无效样本、放行有效对照）
- `config/harness-path.example.yaml` → 复制为 `config/harness-path.local.yaml` 填本地 harness 仓库路径（不提交）
- `templates/plugin-quality-report.md` → 正式审查的报告模板（结论带 NOT_VERIFIED 语义）

## 依赖

- Node ≥ 18.6（用到 `node:module.isBuiltin`），无第三方包——脚本开箱即用，无需安装。
- harness 溯源需要本地有一份 DSH 源码仓库（`git` 可用时同时报告 commit；不可用则该项 NOT_VERIFIED）。

## 工作原则

- 先机械后语义：脚本能查的（声明/工件/对账）不浪费人工。
- **版本感知，不冻结假设**：平台模块表、内联安全正则、主题变量、包 manifest 全部从当前 harness 源码声明读取；版本与 commit 优先走官方 dsh 可执行门（`apps/cli/lib/bin.js --version`）+ git 溯源。规范文档里的实测结论一律标注核对版本。
- **对 harness 的每个 API/事件/slot 引用必须溯源到源码路径**——不采信文档记忆（实测案例：文档写过不存在的 CLI flag、不存在的 `agent/post-step` 事件、已被移除的 `dsh-client-runtime`）。
- 不采信自报 PASS；正式验收必须绑定当前 commit 的 boot 证据 + 浏览器渲染证据。
- 客观缺陷 fail-closed；**语义不确定只出 WARN / NOT_VERIFIED，绝不出假 PASS**。

## harness 根解析

`lint.mjs` 按以下优先级解析 DSH 源码仓库（harness root）：

1. `--harness-root <路径>` 参数
2. 环境变量 `DSH_HARNESS_ROOT`
3. `config/harness-path.local.yaml`（技能目录内，不提交）

三者皆缺时，版本相关检查项标 `NOT_VERIFIED`（进程不崩，其余检查继续）。解析成功后报告：DSH 版本（官方门 + 根 manifest，两者不一致时 WARN）、git commit、平台模块表项数。所有 harness 依赖检查以该版本为准。

## 模式

| 模式 | 时机 | 必做 |
|---|---|---|
| 设计预检 | 写代码前 | 过一遍开发规范的契约节；事件/slot 名先溯源 |
| 快速审查 | 第三方/草稿 | §1 机械 + §2 事实 + §3 契约；结论带 NOT_VERIFIED |
| 正式验收 | 发布/声称完成前 | 全部 + §5 候选绑定证据 |

## §1 机械层（跑 `scripts/lint.mjs`）

```bash
node skills/dsh-plugin-lint/scripts/lint.mjs <插件目录> --harness-root <DSH 源码仓库>
node skills/dsh-plugin-lint/scripts/test-lint.mjs   # 自测，退出码 0 = 全部规则自证有效
```

`--json` 会在文末追加一行 `__DSH_LINT_JSON__{...}` 机器可读结果。退出码 = FAIL 数。

| 节 | 检查内容 |
|---|---|
| §0 harness 溯源 | 版本（官方门 + manifest 交叉）、git commit、平台模块表/纯度正则可解析性、config 基线漂移 |
| §1 package.json | name 解析；`@deepseek-ai/dsh-*` 依赖钉定版本与当前 harness 版本漂移 |
| §2 dsh.bundle | patch 文件存在、row 引用包名 |
| §3 exports["."] | node half 入口存在 |
| §4 dsh.client | platform=web；inject 目标在 harness workspace / 本地 node_modules 声明了 `dsh.client`（否则该边永远等不到工厂，FAIL）；inject ↔ devDep 类型双保险（WARN）；`dsh.client.external` 字段类型、自引用（FAIL）、基线冗余行（WARN） |
| §5 client 工件 | 存在性、`.cjs` 后缀、banner/footer 契约；**产物 bare require ↔ 模块表对账**（注释感知扫描：未知说明符 FAIL——模块表无法应答必抛；内联安全层被外置 FAIL；bare builtin require WARN——须人工确认在 inliner 特征探测内）；**构建配置 external ↔ 平台基线 ∪ dsh.client.external 对账**（越界 FAIL，未找到 externals 声明体 WARN 转人工）；external 死行（WARN） |
| §6 主题变量 | 对 `var(--…)` 引用做声明集对账（声明源：harness `ui-theme/src/styles/*.css` + 插件自身声明）：不存在的 DSH 变量 FAIL（回退值会掩盖主题断链）；未用变量不报 |
| §7 文案与 locale | JSX 文本/用户可见属性硬编码 CJK 文案 FAIL；普通 CJK 字符串字面量 WARN；`locales.ts`（或 `locales/zh.ts`+`en.ts`）zh/en 键集平价 FAIL |
| §8 卫生 | scoped 包 publishConfig.access、scripts.build/test |
| §9 文档版本声明 | 当前态文档（README/AGENTS/CLAUDE/docs，排除 CHANGELOG 与 acceptance 证据）中的冻结 `0.1.0-rc.x` 引用与已移除模块 `dsh-client-runtime` 引用（WARN） |

FAIL 即阻塞。WARN 与 NOT_VERIFIED 不阻塞，但正式验收报告必须逐条给出人工结论。

## §2 事实层（对照 harness 源码逐条核对）

| 审查项 | 溯源方法 |
|---|---|
| 事件名存在且语义对 | `packages/core/agent/src/runtime-types.ts`（注意：**没有 `agent/post-step`**） |
| slot 名真实声明过 | `packages/client/ui-*/src` 里 grep `slots.inject('` / `renderSlot('`；slot 的**类型声明**在所属 client 包，out-of-tree 需 devDep（类型）+ `dsh.client.inject`（加载顺序）双保险 |
| 工具 API 形状 | `docs/cookbook/adding-a-tool.md` + `packages/core/tools/src/index.ts` |
| lossless JSON 校验 | `packages/util/values/src/index.ts`（`walkJsonValue`；旧路径 `packages/core/session/src/json.ts` 已不存在） |
| 生命周期/服务 | `ctx.get`（可选）vs `inject`（硬依赖，缺则整个插件不激活） |

harness 仓库路径与完整索引见开发规范 §参考文件索引。核对时以 `--harness-root` 指向的仓库为准，并在报告记录其版本与 commit。

## §3 契约层（实测踩过的坑，逐条核对）

1. **lossless JSON**：tool 返回值任何属性值为 `undefined` 都被拒（递归）——返回前深度剥离。
2. **DSL 限制**：`parameters` 不支持对象嵌套对象；独立 const 的 schema 字面量要 `as const`。
3. **client 工件**：banner 必须构造 `var module = { exports: {} }; var exports = module.exports;`；`"type":"module"` 包内 cjs 产物须 `outExtensions` 强制 `.js`；产物 bare require 只能请求平台基线或 `dsh.client.external` 声明的说明符。
4. **client 纯度**：非基线、非 `dsh.client.external`、非内联安全表的 `@deepseek-ai/*` 值导入禁止（type-only 会被擦除，不受限）——构建 purity gate 会直接报错。
5. **子进程**：长任务异步 `spawn` + `exec.signal`；`spawnSync` 冻结整个 harness。
6. **显式传参**：不依赖被调 CLI 的静默默认值（实测案例：contract-copilot 的 review_intensity 缺省静默变"强势"）。
7. **fail-loud**：配置错在 apply 里 throw；可选服务缺省要明示降级路径。
8. **退码分类**：域结果（partial/rejected）进 canonical value 不 throw；基础设施失败才 throw。
9. **构建管线**：不要用会吞退出码的管道（`cmd | grep | head && next` 曾让 tsc 失败静默、旧 bundle 留盘数小时）。
10. **HMR 边界（历史结论，按版本复核）**：0.1.0-rc.7 时期双向实测 out-of-tree 插件两个 half 都不热加载、更新后必须重启 dsh；该结论未在后续版本复测——审查时作为待验证假设处理（WARN 语义），以当前 harness 的 `packages/client/hmr` 行为实测为准。
11. **主题变量**：只引用 harness 主题声明集里的变量；回退值（`var(--x, #fff)`）只是兜底显示，掩盖不了暗色主题断链。
12. **类型化 locale**：产品 UI 文案走插件自有命名空间词典（zh 为键集真值、en 对齐），组件经 `PropsLocale<'ns'>` 的 `t()` 消费；JSX 文本/属性里裸写文案即违约。

## §4 文档层

目标插件仓库的 CHANGELOG / DECISIONS / ROADMAP / ARCHITECTURE 与本次改动同步；决策可追溯（编号连续、含撤录）。当前态文档不得残留已过期版本声明（§1 §9 会给 WARN 清单）。

## §5 正式验收（候选绑定）

1. `git rev-parse HEAD` 记录候选 commit
2. 干净 profile 安装：`dsh plugin --profile <验收名> add <路径>` → `--dump-config` 出层
3. node half：boot 无错；tool 在 headless 真实调用成功（有 LLM 则全链路，无则单工具）
4. client half（若有）：`__DSH_BOOT__` 含本包 → `/plugins/<id>/client.js` 可下 → **浏览器渲染截图**（slot 组件真实出现）
5. 证据（commit + 命令输出 + 截图）写进验收报告；缺任一 → `NOT_VERIFIED`

**浏览器取证标准工具：ego-browser**（agent 浏览器，任务空间隔离、复用本机登录态）。验收用 `ego-browser nodejs <<'EOF' ... EOF` 驱动：`gotoAndWait` 打开本地 web UI → `snapshotText`/`js` 做 DOM 断言（slot 组件存在、关键内容渲染）→ `captureScreenshot` 留证。localhost 测试无需公网与额外登录；比人工点选快且证据可复核。无 ego-browser 环境时人工验收并标注证据来源。

## 输出格式

```
dsh-plugin-lint 报告 <目标> @ <commit>
harness 溯源: <DSH 版本> @ <harness commit>（解析来源）
§1 机械: [PASS|FAIL|WARN|NOT_VERIFIED...]（脚本输出，退出码 = FAIL 数）
§2 事实: 每条引用 → 源码路径 → PASS/FAIL
§3 契约: 逐条 PASS/FAIL/NA
§4 文档: ...
§5 验收: PASS / NOT_VERIFIED（缺什么证据）
结论: 可发布 / 需修复（清单）/ 未验证
```

## 已知限制

- 正则级解析，不构建 AST：复杂 patch 结构、嵌套词典、非扁平 locale 对象转人工（脚本对解析不了的情形出 WARN/NOT_VERIFIED，不出 PASS）
- 产物 bare builtin require 只能提示人工确认（inliner 的 try/catch 特征探测合法，无法机械判定）
- JSX 文本位置的 CJK 检测是启发式（`>…<` 区间含 CJK），不含 `{}` 表达式内部
- 平台模块表/纯度正则/主题变量集/包 manifest 均为运行时从 `--harness-root` 读取的当前事实；不随本技能分发，也不预置任何版本号
- 不自动执行目标仓库的 build/test（报告应跑的命令，防误伤）
