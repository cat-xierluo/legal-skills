---
name: dsh-plugin-lint
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.1.0"
license: MIT
description: DeepSeek Harness（DSH）插件的设计预检、质量审查与发布验收工具。在用户创建、重大改造或审查 DSH 插件（dsh.bundle / dsh.client 双面包），需要核对 harness 事实引用、工件契约、lossless JSON、fail-loud 语义，或发布前验收 boot/浏览器证据时使用。开发规范见 references/dsh-plugin-development-standards.md。不要用于：普通 npm 包审查、与 DSH 无关的 agent 项目。
---

# DSH Plugin Lint

审查一个 DSH 插件是否：声明与工件一致、对 harness 的引用真实存在、契约坑已规避、文档已同步、验收证据可绑定候选。

开发与范式依据：[references/dsh-plugin-development-standards.md](references/dsh-plugin-development-standards.md)（插件形态、分发、工具/事件/slot、client 工件契约、harness 参考文件索引）。

本技能不代替实现者。创建插件时先做设计预检，实现后回来做正式验收——审查器与生产者不混同责任。

## 工作原则

- 先机械后语义：脚本能查的（声明/工件）不浪费人工。
- **对 harness 的每个 API/事件/slot 引用必须溯源到源码路径**——不采信文档记忆，DSH 处于 rc 阶段，文档会超前或滞后于代码（实测案例：SKILL.md 写过不存在的 CLI flag、插件设计稿写过不存在的 `agent/post-step` 事件）。
- 不采信自报 PASS；正式验收必须绑定当前 commit 的 boot 证据 + 浏览器渲染证据。
- 客观缺陷 fail-closed；无法确认的标 `NOT_VERIFIED`。

## 模式

| 模式 | 时机 | 必做 |
|---|---|---|
| 设计预检 | 写代码前 | 过一遍开发规范的契约节；事件/slot 名先溯源 |
| 快速审查 | 第三方/草稿 | §1 机械 + §2 事实 + §3 契约；结论带 NOT_VERIFIED |
| 正式验收 | 发布/声称完成前 | 全部 + §5 候选绑定证据 |

## §1 机械层（跑 `scripts/lint.mjs <插件目录>`）

声明一致性 + 工件契约（banner/footer、后缀、文件存在性）。FAIL 即阻塞，退出码 = FAIL 数。

## §2 事实层（对照 harness 源码逐条核对）

| 审查项 | 溯源方法 |
|---|---|
| 事件名存在且语义对 | `packages/core/agent/src/runtime-types.ts`（注意：**没有 `agent/post-step`**） |
| slot 名真实声明过 | `packages/client/ui-*/src` 里 grep `slots.inject('` / `renderSlot('`；slot 的**类型声明**在所属 client 包（如 ui-conversation），out-of-tree 需 devDep + `dsh.client.inject` |
| 工具 API 形状 | `docs/cookbook/adding-a-tool.md` + `packages/core/tools/src/index.ts` |
| 生命周期/服务 | `ctx.get`（可选）vs `inject`（硬依赖，缺则整个插件不激活） |

harness 仓库路径与完整索引见开发规范 §参考文件索引。

## §3 契约层（实测踩过的坑，逐条核对）

1. **lossless JSON**：tool 返回值任何属性值为 `undefined` 都被拒（递归）——返回前深度剥离。
2. **DSL 限制**：`parameters` 不支持对象嵌套对象；独立 const 的 schema 字面量要 `as const`。
3. **client 工件**：banner 必须构造 `var module = { exports: {} }; var exports = module.exports;`；`"type":"module"` 包内 cjs 产物须 `outExtensions` 强制 `.js`。
4. **client 纯度**：非平台表的 `@deepseek-ai/*` 值导入禁止（type-only 会被擦除，不受限）。
5. **子进程**：长任务异步 `spawn` + `exec.signal`；`spawnSync` 冻结整个 harness。
6. **显式传参**：不依赖被调 CLI 的静默默认值（实测案例：contract-copilot 的 review_intensity 缺省静默变"强势"）。
7. **fail-loud**：配置错在 apply 里 throw；可选服务缺省要明示降级路径。
8. **退码分类**：域结果（partial/rejected）进 canonical value 不 throw；基础设施失败才 throw。
9. **构建管线**：不要用会吞退出码的管道（`cmd | grep | head && next` 曾让 tsc 失败静默、旧 bundle 留盘数小时）。
10. **HMR 边界**：out-of-tree 插件更新 client bundle 后必须重启 dsh web（rev 不被重扫）。

## §4 文档层

目标插件仓库的 CHANGELOG / DECISIONS / ROADMAP / ARCHITECTURE 与本次改动同步；决策可追溯（编号连续、含撤回记录）。

## §5 正式验收（候选绑定）

1. `git rev-parse HEAD` 记录候选 commit
2. 干净 profile 安装：`dsh plugin --profile <验收名> add <路径>` → `--dump-config` 出层
3. node half：boot 无错；tool 在 headless 真实调用成功（有 LLM 则全链路，无则单工具）
4. client half（若有）：`__DSH_BOOT__` 含本包 → `/plugins/<id>/client.js` 可下 → **浏览器渲染截图**（slot 组件真实出现）
5. 证据（commit + 命令输出 + 截图）写进验收报告；缺任一 → `NOT_VERIFIED`

## 输出格式

```
dsh-plugin-lint 报告 <目标> @ <commit>
§1 机械: [PASS|FAIL...]（脚本输出）
§2 事实: 每条引用 → 源码路径 → PASS/FAIL
§3 契约: 逐条 PASS/FAIL/NA
§4 文档: ...
§5 验收: PASS / NOT_VERIFIED（缺什么证据）
结论: 可发布 / 需修复（清单）/ 未验证
```

## 已知限制（v0.1）

- 机械层不解析 YAML 全语法（正则级）；复杂 patch 结构转人工
- 不自动执行目标仓库的 build/test（报告应跑的命令，防误伤）
- 平台模块表与 slot 清单以 harness 0.1.0-rc.7 为准；DSH 升级后先更新开发规范再审查