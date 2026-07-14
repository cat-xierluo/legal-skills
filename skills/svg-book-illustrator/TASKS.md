# TASKS

## 当前任务

- [ ] T001：消除 SVG 生产器与 Skill 硬规则冲突（VERIFIED，待 PR #51 合并与 v1.8.9 发布）
  - 5 个生成器的最小有效输出必须是可解析 XML，并带完整 `viewBox`、`width`、`height` 和稳定 `data-figure-id`；支持默认 output stem 与显式 `--figure-id`，非法值写文件前失败。
  - 画布必须严格为 `viewBox="0 0 720 H"`、`width="720"`、`height="H"`；生成产物及全部模板 SVG 块不得包含 `<style>`、`style=`、内嵌 `font-family`、`class`、CSS 变量或画布背景矩形。
  - librsvg 与浏览器导出必须共同读取 `assets/render-fonts.css`，字体栈不得复制；受控 librsvg 与旧内嵌 style 基线 5/5 `pixel AE = 0`。
  - 新生成/新落稿 SVG 的 ID 必须在项目 canonical scope 内唯一，模板 `fig-template-*` 落稿前替换；只约束未来 producer，不在本任务回改历史书稿。
  - 以上约束必须由可重复执行的生成产物回归测试证明，不能仅靠文档声明或人工抽查。
  - PR 与 `main` 推送必须由 GitHub Actions 自动运行 source producer contract；没有明确绿色 check 时保持不可合并。该 check 不替代视觉门禁。
  - 当前证据：原始 RED 暴露 15 项样式/尺寸冲突及 3 个 fail-open；身份契约 RED 再暴露 15 个 producer/template 缺 ID；4 个测试全绿（5 生成器 / 10 模板 / 16 坏样本 / ID 默认-显式-非法与批内唯一 / 双渲染器接线）；`scripts/verify_render_font_equivalence.py` 可重复证明字体交付方式与身份元数据两组对照均为 5/5 `AE = 0`。
  - 完成条件：① PR #51 合并；② `main` 上 source check 通过；③ v1.8.9 release zip 可访问。目前发布资产为 `PENDING`（下载链接 404），因此不得勾选完成。

> 本文件自 v1.8.9 建立。更早版本的任务演进保留在 `CHANGELOG.md`，不在此追补或改写历史。
