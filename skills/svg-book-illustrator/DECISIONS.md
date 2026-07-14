# DECISIONS

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
