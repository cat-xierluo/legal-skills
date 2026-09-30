# Changelog

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
