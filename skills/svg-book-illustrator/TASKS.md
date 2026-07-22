# TASKS

## 当前任务

- [ ] T002：让 SVG producer 与 writing-reviewer v0.16+ 的 shape containment 语义一致（本地 VERIFIED，待 PR / `main` source check / v1.8.10 发布）
  - 任何候选源中的 `data-overlap-role` 只允许 `container`；禁止 `decoration`、任意自造 role 与候选自发 `data-allow-overlap`。
  - 只有真实承载内层 shape 的外层 area shape 才能声明 container，并同时绑定单图唯一的安全原生 `id`、明示承载关系的 `data-overlap-note` 与可静态证明非透明的 hex/rgb/hsl `fill`；意外重叠必须修坐标、尺寸或层级。
  - producer contract 必须拒绝缺失/不安全/重复/namespaced id，缺失/空白/短或加前缀泛化/孤立/namespaced note，透明/继承/paint server/零 opacity 容器、非法 role 和非 area shape 声明；生成器产物与模板 SVG 块共用同一断言。
  - 静态声明通过不等于几何通过；最终由 writing-reviewer v0.16+ render gate 以真实浏览器几何判定，并在 evidence 中记录实际命中的 outer / inner / reason。
  - 当前本地证据：TDD RED 累计 28 类坏样本被旧断言漏过；TDD GREEN 后目标测试通过，全量 producer contract 为 5 tests passed。
  - 完成条件：① 分支 PR 合并；② `main` 上 `Source producer contract` 绿色；③ v1.8.10 release zip 可访问；④ writing-reviewer v0.16+ 已合并可用，且至少一组合法 container / 装饰语义绕过对照已由真实 render gate 生成 candidate-bound 跨 Skill 证据。未满足前保持未勾选。

- [ ] T001：消除 SVG 生产器与 Skill 硬规则冲突（VERIFIED，PR #51 已合并且 `main` source check 已通过，待 v1.8.9 或后续版本发布）
  - 5 个生成器的最小有效输出必须是可解析 XML，并带完整 `viewBox`、`width`、`height` 和稳定 `data-figure-id`；支持默认 output stem 与显式 `--figure-id`，非法值写文件前失败。
  - 画布必须严格为 `viewBox="0 0 720 H"`、`width="720"`、`height="H"`；生成产物及全部模板 SVG 块不得包含 `<style>`、`style=`、内嵌 `font-family`、`class`、CSS 变量或画布背景矩形。
  - librsvg 与浏览器导出必须共同读取 `assets/render-fonts.css`，字体栈不得复制；受控 librsvg 与旧内嵌 style 基线 5/5 `pixel AE = 0`。
  - 新生成/新落稿 SVG 的 ID 必须在项目 canonical scope 内唯一，模板 `fig-template-*` 落稿前替换；只约束未来 producer，不在本任务回改历史书稿。
  - 以上约束必须由可重复执行的生成产物回归测试证明，不能仅靠文档声明或人工抽查。
  - PR 与 `main` 推送必须由 GitHub Actions 自动运行 source producer contract；没有明确绿色 check 时保持不可合并。该 check 不替代视觉门禁。
  - 当前证据：原始 RED 暴露 15 项样式/尺寸冲突及 3 个 fail-open；身份契约 RED 再暴露 15 个 producer/template 缺 ID；4 个测试全绿（5 生成器 / 10 模板 / 16 坏样本 / ID 默认-显式-非法与批内唯一 / 双渲染器接线）；`scripts/verify_render_font_equivalence.py` 可重复证明字体交付方式与身份元数据两组对照均为 5/5 `AE = 0`。
  - 合并证据：PR #51 已于 2026-07-14 squash merge（`e32a73a6`）；`main` 上 `SVG Book Source Producer Contract` run `29323054523` 结论为 `SUCCESS`。
  - 完成条件：① PR #51 合并✅；② `main` 上 source check 通过✅；③ v1.8.9 或包含相同能力的后续 release zip 可访问⏳。目前发布资产仍为 `PENDING`，因此不得勾选完成。

> 本文件自 v1.8.9 建立。更早版本的任务演进保留在 `CHANGELOG.md`，不在此追补或改写历史。
