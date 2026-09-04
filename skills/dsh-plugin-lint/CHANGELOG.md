# 变更日志

## [1.0.0] - 2026-09-04

> 版本号从 0.1.0 跳至 1.0.0：本技能位于 `skills/` 正式目录，按项目规范正式版本使用 1.x.x；同时本次为行为级重构（新增多条规则、事实源改为运行时溯源），语义变化显著。

### 新增

- **harness 溯源（§0）**：`--harness-root` 参数 / `DSH_HARNESS_ROOT` 环境变量 / `config/harness-path.local.yaml` 三级解析；DSH 版本优先经官方可执行门（`apps/cli/lib/bin.js --version`）读取并与根 manifest 交叉核对，git commit 一并报告；官方门与 manifest 不一致出 WARN
- **产物 bare require ↔ 模块表对账（§5）**：注释感知扫描 `lib/client.js`，未知 bare require（不在平台基线也不在 `dsh.client.external`）FAIL；内联安全层被外置 FAIL（纯度正则从 harness `tsdown.client.ts` 运行时提取）；bare builtin require 出 WARN 转人工确认
- **构建配置 external 对账（§5）**：从 `tsdown.client.config.ts` 的 externals 语义声明体提取说明符，越界（非基线 ∪ `dsh.client.external`）FAIL；找不到声明体 WARN 转人工
- **dsh.client.inject/external 声明检查（§4）**：inject 目标必须在 harness workspace 或本地 node_modules 声明 `dsh.client`（否则 FAIL——该边永远等不到工厂）；inject ↔ devDep 类型双保险缺失 WARN；`dsh.client.external` 自引用 FAIL（harness 会拒绝启动）、基线冗余行 WARN、产物无对应 require 的死行 WARN
- **主题变量对账（§6）**：从 harness `ui-theme/src/styles/*.css` 收集当前声明集，插件引用不存在的 `--dsw-*`/`--ds-*`/`--shiki-*` 变量 FAIL（回退值会掩盖主题断链）
- **硬编码文案与类型化 locale（§7）**：JSX 文本位置/用户可见属性硬编码 CJK 文案 FAIL；普通 CJK 字符串字面量 WARN；插件 `locales.ts`（或 `locales/zh.ts`+`en.ts`）zh/en 键集平价校验 FAIL
- **文档版本声明检查（§9）**：当前态文档（排除 CHANGELOG 与 acceptance 证据）中的冻结 `0.1.0-rc.x` 引用、已移除平台模块 `dsh-client-runtime` 引用出 WARN
- **DSH 依赖版本漂移（§1）**：`@deepseek-ai/dsh-*` 钉定版本与当前 harness 版本不一致 WARN
- **自测 `scripts/test-lint.mjs`**：自包含 fixture（运行时合成迷你 harness + 有效/无效插件对照），23 项断言证明每条规则抓得住无效样本、放行有效对照
- `--json` 输出（`__DSH_LINT_JSON__` 行）供脚本化消费

### 改进

- 平台模块表（`PLATFORM_MODULES`/`PRELOADED_CLIENT_EXTERNALS`）、纯度正则（`INLINE_SAFE` 等）、主题变量集、client 包 manifest 全部改为**运行时从 `--harness-root` 当前源码读取**，替换冻结的 0.1.0-rc.7 假设；技能内不再预置任何版本号事实
- 头部 manifest 失败即提前退出的行为保留，但 harness 缺失时其余检查继续、相关项标 NOT_VERIFIED，不再崩溃也不假 PASS
- 退出码语义保持 = FAIL 数；WARN/NOT_VERIFIED 不阻塞但正式验收必须逐条人工结论

### 技术优化

- 自研注释感知 JS 扫描器（字符串/模板/正则字面量状态机），支撑产物与源码的确定性规则；零第三方依赖（Node ≥ 18.6，`node:module.isBuiltin`）
- findings 结构化（level + message），文本与 JSON 双通道输出

### 文档完善

- SKILL.md：新增 harness 根解析、§1 规则清单、依赖章节（开箱即用声明）、已知限制重写；HMR 结论标注为历史观察需按版本复核；版本号升 1.0.0
- references/dsh-plugin-development-standards.md：事实基线更新为 0.1.2-rc.1（commit 76fda729）；lossless JSON 路径更正为 `packages/util/values/src/index.ts`；新增 `dsh.client` 字段语义表、平台基线唯一事实源（`platform.ts`）、类型化 slot catalog（`contract/slots.ts`）、主题变量、类型化 locale 章节；实测坑清单增补 4 条（externals 手抄漂移、external 自引用、主题变量 fallback 掩盖、裸写文案）
- templates/plugin-quality-report.md：新增 harness 溯源章节与全部新检查行
- config/harness-path.example.yaml：记录解析优先级与官方版本门说明

## [0.1.0] - 2026-08-19

### Added
- SKILL.md：三模式（设计预检/快速审查/正式验收）+ 五层审查清单（机械/事实/契约/文档/候选绑定）
- scripts/lint.mjs：§1 机械层（声明一致性 + client 工件 banner/footer 契约 + 后缀 + 入口存在性），退出码 = FAIL 数
- references/dsh-plugin-development-standards.md：DSH 插件开发规范（形态/分发/工具/事件/slot/client 工件契约/实测坑清单/harness 参考索引）
- 首个审查对象：dsh-contract-copilot（0 FAIL 0 WARN 通过，并消除一个真 WARN）
