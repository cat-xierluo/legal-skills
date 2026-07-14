# TASKS

## 当前任务

- [x] T001：消除 SVG 生产器与 Skill 硬规则冲突（v1.8.9，2026-07-14）
  - 5 个生成器的最小有效输出必须是可解析 XML，并带完整 `viewBox`、`width`、`height`。
  - 生成产物及 `references/layout-templates.md` 中全部 SVG 代码块不得包含 `<style>`、SVG 根 `font-family`、`class`、CSS 变量或画布背景矩形。
  - 以上约束必须由可重复执行的生成产物回归测试证明，不能仅靠文档声明或人工抽查。
  - 完成证据：旧实现 15 个子测试失败；修复后 2 个契约测试全绿，5/5 生成器通过 xmllint 与 librsvg 渲染；版本与发布索引已同步。

> 本文件自 v1.8.9 建立。更早版本的任务演进保留在 `CHANGELOG.md`，不在此追补或改写历史。
