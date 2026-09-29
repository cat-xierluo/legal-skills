# Changelog

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
