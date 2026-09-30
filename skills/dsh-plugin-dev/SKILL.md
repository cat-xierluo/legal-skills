---
name: dsh-plugin-dev
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.5.0"
license: MIT
description: DeepSeek Harness（DSH）插件的设计、开发、装载验证、版本迁移与发布审查指引（版本感知）。在用户要为 DSH Desktop 开发插件、把 Pi/Hermes 插件迁移到 DSH、做隔离装载实验、排查插件在真实宿主的行为、跟进 DSH 版本升级适配，或在发布前做机械审查与验收（dsh.bundle / dsh.client 双面包工件契约、inject/external 对账、主题变量、类型化 locale）时使用。不要用于普通 npm 包审查或与 DSH 无关的 agent 项目。
---

# DSH Plugin Dev

DSH 插件开发指引 Skill（2026-09-29 由 dsh-plugin-lint 并入吸收：开发主线 + 机械审查一体）。沉淀来源：dsh-plugins 仓库全程开发实测（真实 DSH Desktop 2.0.15 / 内嵌运行时 0.1.7-rc.2，五次隔离装载实验、14 个 PR 的独立审查修复）+ dsh-contract-copilot 0.1.2 期开发实测。

本技能不代替实现者：创建插件时先做设计预检，实现后回来做正式验收——审查器与生产者不混同责任。

## 配套文件

- `scripts/lint.mjs` → 机械审查层（版本感知，规则清单见下）
- `scripts/test-lint.mjs` → 自测（自包含 fixture，证明每条规则抓得住无效样本、放行有效对照）
- `config/harness-path.example.yaml` → 复制为 `config/harness-path.local.yaml` 填本地 harness 仓库路径（不提交）
- `templates/plugin-quality-report.md` → 正式审查的报告模板（结论带 NOT_VERIFIED 语义）

## 依赖

- Node ≥ 18.6（lint.mjs 用 `node:module.isBuiltin`），无第三方包——脚本开箱即用。
- harness 溯源需要本地一份 DSH 源码仓库；三者皆缺时版本相关检查标 NOT_VERIFIED（进程不崩）。**本机 Desktop 内嵌运行时**（`/Applications/DSH Desktop.app/.../node_modules/@deepseek-ai/`）是另一事实源，二者对照用。

## 开发路径

1. **定形态**：插件身份（package.json name + `dsh.bundle.patch` → cordis.patch.yml，insert 行 id/name 均 string）、半体范围（先 Host-only 再 client）、服务依赖（inject——硬依赖缺失插件等待不激活）、零依赖原则（`@deepseek-ai/*` 视为宿主 external）。要点见 [host-plugin-essentials](references/host-plugin-essentials.md)。**Pi 插件 DSH 化起手切片**（PR #37 三插件实证）：新建打包层三件套（package.json/patch/index.mjs，Pi 源码一字不动、不 import）+ bizlink 消费者（owner kind 命名空间）+ 自检链（只断言自身命名空间）——mock 级先行，装载验证批量入用户窗口。**起手后的领域平移走 [porting-semantics](references/porting-semantics.md)**：源码去 flopi-candidate 找全量、语义出处行号锚定、偏离只许更严方向、外部 IO 一律注入缝 + 缺省 fail-closed（PR #42/#45/#46/#49/#51 实证）。
2. **写 Host 半体**：手写 ESM function plugin（name/inject/apply 命名导出）；同目录有 CJS 遗留源码时**不声明 `type: module`、入口用 `.mjs`**（实测组合回归）；`ctx.provide` + `ctx.logger.info` 启动标记 + `ctx.effect` 返回 disposer。类型查找先搜 `dsh-tool-cordis/lib/types/api-catalog.js` 与各包 README.zh.md——**内嵌树 .d.ts 已剥离，包 lib 导出面查不到 ≠ 全树缺失**。
3. **接业务**：会话状态用投影（[projection-cookbook](references/session-projection-cookbook.md)：register 必填 `stateVersion`、通知只走 wire、真实 turn id 是数字）；业务对象↔会话关联走共享服务（dsh-bizlink 先例：owner 在 revision 权威处做乐观并发）；**模型调用与一切公共能力先查官方复用**（[official-capabilities](references/official-capabilities.md)：目录 + 查证方法；已核 `ctx.llm` 为唯一受支持模型调用入口，勿自建）。
4. **隔离装载验证**：按 [desktop-load-and-isolation](references/desktop-load-and-isolation.md) 建实验 profile（GUI profile 必须直接含 `@deepseek-ai/dsh-web-app`；官方 bundle 从安装锚点解析，本地插件放符号链接即可零物化装载）、`DSH_HOME` 隔离启动、宿主日志找激活标记、SIGTERM 分步退出、恢复生产（profile-selection 快照/恢复）。
5. **审查与回写**：mock ctx 集成测试（真实双插件串接）→ 机械审查（下节）→ 独立审查（角色分离）→ 装载证据绑定候选。踩坑回写 [pitfalls-log](references/pitfalls-log.md)，版本迁移差异回写 [harness-facts](references/harness-facts-017rc2.md)。

## 机械审查（`scripts/lint.mjs`）

```bash
node skills/dsh-plugin-dev/scripts/lint.mjs <插件目录> --harness-root <DSH 源码仓库>
node skills/dsh-plugin-dev/scripts/test-lint.mjs   # 自测，退出码 0 = 全部规则自证有效
```

harness 根解析优先级：`--harness-root` 参数 → `DSH_HARNESS_ROOT` 环境变量 → `config/harness-path.local.yaml`。`--json` 追加机器可读行；退出码 = FAIL 数。规则节：§0 harness 溯源（版本/commit/模块表）｜§1 package.json 版本漂移｜§2 dsh.bundle｜§3 exports 入口｜§4 dsh.client（inject 目标声明、external 自引用/越界）｜§5 client 工件（banner/footer、bare require ↔ 模块表、构建 external 对账）｜§6 主题变量声明集对账｜§7 类型化 locale 与 CJK 硬编码｜§8 卫生｜§9 文档版本残留。

| 模式 | 时机 | 必做 |
|---|---|---|
| 设计预检 | 写代码前 | 过一遍 [development-standards](references/dsh-plugin-development-standards.md) 契约节 + 本 SKILL 踩坑；事件/slot 名先溯源 |
| 快速审查 | 第三方/草稿 | 机械 + 事实 + 契约；结论带 NOT_VERIFIED |
| 正式验收 | 发布/声称完成前 | 全部 + 候选绑定证据（commit + 干净 profile 安装 + boot 无错 + 工具真实调用 + 浏览器渲染截图；缺任一 → NOT_VERIFIED） |

审查工作原则（继承自 lint 1.0.0）：先机械后语义；版本感知不冻结假设；对 harness 的每个 API/事件/slot 引用必须溯源到源码路径（实测案例：文档写过不存在的 CLI flag 与 `agent/post-step` 事件）；不采信自报 PASS；客观缺陷 fail-closed，语义不确定只出 WARN/NOT_VERIFIED 绝不出假 PASS。

## 必须守住的边界

- **版本匹配**：开发依据的源码/文档版本必须与本机 Desktop 内嵌运行时一致（npm `latest` = 内嵌版；`next` 是预发布无桌面内嵌）。错位研究必须按实物重核。
- **生产隔离**：实验只用 `DSH_HOME` 隔离目录 + 合成数据；不读生产 sessions/凭据/settings；动共享 userData 前快照后恢复；关生产实例前后向用户报备。
- **退出时序**：SIGTERM 后**分步验证进程真正消失**再执行恢复命令——单例锁会把 premature 的 `open -a` 转发给未死尽的实验实例。
- **不伪造验证**：mock 冒烟 ≠ 宿主验证 ≠ GUI 验证，三层分开陈述；宿主日志是 Host 半体权威证据；缺失标 NOT_VERIFIED。
- **组合回归意识**：单分支 diff 看不见共享目录声明的相互作用（如同目录 package.json 的 type 字段）——此类变更合并前后必须全量重跑既有测试。

## 交付物与完成线

一个开发切片：结构校验 → mock 集成测试 →（有条件时）隔离装载宿主日志证据 → 独立审查处置 → 文档与踩坑回写。发布验收按上节正式模式。缺装载证据明标 NOT_VERIFIED，不宣称"已在真实宿主可用"。

## 参考

- [官方能力复用目录](references/official-capabilities.md)：自建公共层前先查官方的查证方法（源码锚定/包 README/消费者范例）+ 已核五条目（`ctx.llm` 模型调用、`ctx.jobs` 会话内长任务、`packages/schedule` 持久定时、`ctx.tools` 模型工具注册、`ctx.storageDomain` 持久 KV——后两条含零依赖实现姿势）与待查清单。
- [移植语义纪律](references/porting-semantics.md)：flopi-candidate 源码定位规律、行号锚定、偏离只许更严、不虚构未验证分支、外部 IO 注入缝（fail-closed）、并发分支测试计数。
- [Host 插件要领与版本差异](references/host-plugin-essentials.md)：形态、装载解析、零依赖与 schema 策略、api-catalog 类型查找、0.1.2→0.1.7 迁移表。
- [会话投影 Cookbook](references/session-projection-cookbook.md)：sessionProjections 契约、wire 通知、数字 turnId、水位与 fork。
- [Desktop 装载与隔离实验](references/desktop-load-and-isolation.md)：profile 工作区、装载实证、DSH_HOME/单例锁/SIGTERM/向导状态/renderer 已知问题。
- [0.1.7-rc.2 事实快照](references/harness-facts-017rc2.md)：版本矩阵、内嵌包速查、与 0.1.2 规范差异清单。
- [踩坑日志](references/pitfalls-log.md)：按症状索引的实测坑（含出处），跨版本累积。
- [0.1.2 开发规范（历史权威）](references/dsh-plugin-development-standards.md)：插件形态/分发/工具/事件/slot/client 工件契约/主题/locale 全量规范 + 14 条实测坑与 harness 参考文件索引。
- 实证仓库：`maoscripts/dsh-plugins`（evidence 与 PR 审查修复记录，本 Skill 事实的原始出处）。

## 已知限制（继承 lint）

- 正则级解析不构建 AST：复杂 patch 结构、嵌套词典转人工（WARN/NOT_VERIFIED，不出假 PASS）。
- 产物 bare builtin require、JSX CJK 检测为启发式，需人工确认。
- 平台模块表/纯度正则/主题变量集均为运行时从 `--harness-root` 读取的当前事实，不预置版本号。
- 不自动执行目标仓库 build/test（报告应跑的命令）。
