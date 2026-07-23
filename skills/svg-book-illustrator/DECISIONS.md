# DECISIONS

## DEC-022：shape 包含只允许可审计的 container 窄声明

- 日期：2026-07-16
- 状态：已采纳
- 关联任务：T002

### 背景

writing-reviewer v0.16+ 不再把“一个 shape 完全包含另一个 shape”自动猜成合法容器，因为同一几何现象也可能来自坐标写错、遮挡或装饰底纹压住信息卡。与此同时，书籍配图确有“外层面板承载内层卡片”的正常构图；若一律阻断，会制造无法表达的误报。现有 producer contract 对所有 `data-overlap-role` 属性完全不检查，候选可用 `decoration` 或任意 role 自发隐藏问题，也可声明 `container` 却不提供稳定身份与理由，导致 producer 与 reviewer 契约断裂。

### 决策

1. 默认把 shape/shape 包含或重叠视为待修布局问题；先改坐标、尺寸或层级，不给候选 SVG 通用重叠逃生口。
2. 唯一允许写入候选源的 role 是 `data-overlap-role="container"`。禁止 `decoration`、`background` 等自造 role，也禁止候选自发 `data-allow-overlap`。
3. container 只标在 writing-reviewer 实际审计的外层 area shape（`rect` / `circle` / `ellipse` / `polygon` / `path`），并同时绑定：
   - 单张 SVG 内唯一、无 namespace 的安全稳定 `id`；
   - 无 namespace、至少六字、包含“承载/包含/容纳”等关系词且不能只是“这里允许重叠/覆盖”的具体 `data-overlap-note`；
   - 可静态证明非透明的 hex/rgb/hsl `fill`；禁止 `none/transparent`、零 alpha、命名色、继承/全局关键字和无法在 producer 侧证明的 paint server，且 opacity/fill-opacity 必须大于 0。
4. producer contract 对声明做静态 fail-closed：缺失/不安全/重复/namespaced id，缺失/空白/泛化/孤立/namespaced note，透明/继承/零 opacity、非法 role、非 area shape 声明一律失败；生成器产物、模板 SVG 块与坏样本共用同一断言。
5. 静态元数据只证明意图可审计，不证明几何合法。最终必须由 writing-reviewer v0.16+ render gate 在真实浏览器中判断 outer 是否实际包含 inner，并把 outer / inner / reason 写入 candidate-bound evidence。
6. 不在 producer 中复制一套浏览器几何计算器。两个几何实现会随 transform、path、字体和 renderer 演进而漂移；producer 负责生成期契约，writing-reviewer 负责 canonical source/render 验收。

### 取舍

- “完全禁止任何 shape 包含”最简单，但会误伤卡片嵌套等真实版式。
- “允许 decoration / 任意 role”最灵活，却把 finding 的裁量权交回候选源，重现本次治理要解决的假绿。
- 采用单一 container 窄声明，把意图写进源文件、把实际命中写进 evidence，同时保留真实几何门禁。

### 兼容性

现有 5 个生成器和 10 个模板 SVG 块均未使用 `data-overlap-role`，因此节点、坐标、渲染像素和既有产物不变。只有未来新增的容器声明受新静态契约约束；历史书稿是否补声明由各项目决定，不在本 Skill 版本中批量迁移。

## DEC-021：生产规则必须由生成产物回归测试闭环

- 日期：2026-07-14
- 状态：已采纳
- 关联任务：T001

### 背景

`SKILL.md` 与 `references/style-guide.md` 已把 `<style>`、SVG 根 `font-family`、CSS class/变量和背景矩形列为硬禁项，但 5 个随 Skill 发布的生成器及 5 个模板示例仍持续输出 `<style>`。规则只存在于说明文字，未成为生产器的可执行约束，因此 review 反复发现同类问题。

### 决策

1. 生产器不得与自身公开硬规则冲突；生成器和模板示例使用同一份可机判契约。
2. 硬规则必须检查实际生成产物，而不是只扫描生成器源码。
3. 回归测试执行全部生成器的最小有效调用，并检查 `layout-templates.md` 的全部 `svg` 代码块；新增模板或生成器会自动进入同类验收范围。
4. 相关 PR 与 `main` 推送由 path-filtered GitHub Actions 自动运行 source producer contract；check 未明确通过时不可合并，但绿色 check 不代表视觉通过。
5. 违反契约时测试失败，不能以人工 review、渲染器容错或“文档已写明”替代。
6. 源 SVG 保持无嵌入样式；正式渲染字体只在 `assets/render-fonts.css` 维护，librsvg wrapper 与 `svg2png.js` 共同读取。裸渲染器输出不构成验收证据；`scripts/verify_render_font_equivalence.py` 以临时旧式基线提供可重复的像素等价证据。
7. 画布契约固定为 `0 0 720 H` / `width=720` / `height=H`，并禁止所有元素 `style=` 与内嵌 `font-family`，避免检查器再次 fail-open 或外部字体被覆盖。
8. `VERIFIED`、`MERGEABLE` 与 `COMPLETED` 分离：本地/PR 证据只能进入 VERIFIED/MERGEABLE；只有 PR 已合并、`main` check 绿色且发布资产可访问，T001 才能标完成。
9. producer 与 review inventory 以 SVG 根 `data-figure-id` 为跨工具主键：新产物必须安全且项目内唯一，生成器默认 output stem、允许显式 ID，模板 ID 落稿前替换。项目级 inventory 负责 canonical scope 全局唯一性；本次不迁移历史书稿。

### 兼容性

源 SVG 移除内嵌 CSS，并为旧模板骨架补显式画布尺寸；正式导出通过受控外部 CSS 保持旧字体基线，5 个生成器像素对照均为零差。新增 `data-figure-id` 前后 5/5 受控渲染 `AE = 0`；不改变节点、坐标、颜色、文字或图形语义。

> 本文件自 DEC-021 建立。DEC-001 至 DEC-020 的历史摘要仍以 `CHANGELOG.md` 中的原记录为准，不在此虚构补录。
