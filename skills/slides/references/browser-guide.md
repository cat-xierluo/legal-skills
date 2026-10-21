# 浏览器演示模式指南

当 HTML 幻灯片需要在浏览器中直接演示（而非转换为 PPTX/PDF）时，遵循本指南。浏览器模式无 PPTX 的 CSS 限制，可以使用渐变、动画、base64 图片等所有 CSS 特性。

---

## 内容密度限制

**每张 Slide 必须完全适配视口，不允许滚动。**

| 页面类型 | 最大内容量 |
| -------- | ---------- |
| 封面页 | 1 个标题 + 1 个副标题 |
| 内容页 | 1 个标题 + 4-6 个要点（每个最多 2 行） |
| 特性网格 | 1 个标题 + 6 个卡片（2×3 或 3×2） |
| 代码页 | 1 个标题 + 8-10 行代码 |
| 引言页 | 1 段引言（最多 3 行）+ 出处 |

**内容太多？→ 拆分为多页。永远不要滚动。**

---

## 响应式视口适配 CSS

```css
/* 1. 锁定文档到视口 */
html, body {
  height: 100%;
  overflow-x: hidden;
}

html {
  scroll-snap-type: y mandatory;
  scroll-behavior: smooth;
}

/* 2. 每个 slide = 精确视口高度 */
.slide {
  width: 100vw;
  height: 100vh;
  height: 100dvh; /* 动态视口（移动端） */
  overflow: hidden; /* 关键：禁止溢出 */
  scroll-snap-align: start;
  display: flex;
  flex-direction: column;
  position: relative;
}

/* 3. 所有尺寸使用 clamp() — 随视口缩放 */
:root {
  --title-size: clamp(1.5rem, 5vw, 4rem);
  --h2-size: clamp(1.25rem, 3.5vw, 2.5rem);
  --body-size: clamp(0.75rem, 1.5vw, 1.125rem);
  --small-size: clamp(0.65rem, 1vw, 0.875rem);
  --slide-padding: clamp(1rem, 4vw, 4rem);
  --content-gap: clamp(0.5rem, 2vw, 2rem);
}

/* 4. 短屏幕断点 */
@media (max-height: 700px) {
  :root {
    --slide-padding: clamp(0.75rem, 3vw, 2rem);
    --title-size: clamp(1.25rem, 4.5vw, 2.5rem);
  }
}

@media (max-height: 600px) {
  :root {
    --slide-padding: clamp(0.5rem, 2.5vw, 1.5rem);
    --body-size: clamp(0.7rem, 1.2vw, 0.95rem);
  }
  .decorative { display: none; }
}

@media (max-height: 500px) {
  :root {
    --slide-padding: clamp(0.4rem, 2vw, 1rem);
    --title-size: clamp(1rem, 3.5vw, 1.5rem);
    --body-size: clamp(0.65rem, 1vw, 0.85rem);
  }
}

/* 窄屏幕 */
@media (max-width: 600px) {
  .grid { grid-template-columns: 1fr; }
}

/* 减少动画偏好 */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.2s !important;
  }
}
```

---

## CSS 动画

浏览器模式支持 CSS 动画和过渡。PPTX 导出时动画自动降级（元素静态可见）。

### 动画触发机制

使用 `data-anim` 属性标记需要入场动画的元素。翻页时（IntersectionObserver 或 scroll-snap）触发动画。

```html
<!-- 默认级联淡入 -->
<h2 data-anim>标题</h2>
<p data-anim>正文</p>

<!-- 指定动画方向 -->
<h2 data-anim="left">从左滑入</h2>
<h2 data-anim="right">从右滑入</h2>
<h2 data-anim="scale">缩放淡入</h2>
```

### 延迟级联

使用 `.d1` 到 `.d6` 类控制逐个入场的时间差：

```html
<div data-anim class="d1">第一个</div>
<div data-anim class="d2">第二个</div>
<div data-anim class="d3">第三个</div>
```

### 内置动画类型

| 属性值 | 效果 | 适用场景 |
|--------|------|---------|
| （默认） | fadeSlideUp：上移淡入 | 大部分正文页 |
| `left` | fadeSlideLeft：左移淡入 | 对比页左列、流程左半 |
| `right` | fadeSlideRight：右移淡入 | 对比页右列、流程右半 |
| `scale` | fadeScale：缩放淡入 | KPI 大数字、图片 |

### 页面转场动画

在 `.slide` 容器上添加 `data-animate` 属性指定整页动画策略：

| 策略 | 效果 | 适用页面 |
|------|------|---------|
| （默认 cascade） | 子元素逐个级联淡入 | 大部分正文页 |
| `hero` | 节奏更慢更仪式感 | 封面、章节分隔 |
| `quote` | 一句一句揭示（550ms stagger） | 金句页 |
| `directional` | 左进 → 分割 → 右进 | 对比页（Before/After） |

```html
<!-- 封面页：仪式感入场 -->
<div class="slide dark" data-animate="hero">
  <h1 data-anim>标题</h1>
  <p data-anim>副标题</p>
</div>

<!-- 对比页：左右分别入场 -->
<div class="slide light" data-animate="directional">
  <div data-anim="left">左列</div>
  <div data-anim="right">右列</div>
</div>
```

### 自定义动画

如需自定义动画，在 `<style>` 中定义新 keyframes 并通过类名引用：

```css
@keyframes highlightPulse {
  0% { background-color: transparent; }
  50% { background-color: rgba(217,119,6,0.15); }
  100% { background-color: transparent; }
}
.highlight-pulse { animation: highlightPulse 2s ease infinite; }
```

### 动画降级保底

- PPTX 导出时所有 `data-anim` 元素直接设为 `opacity: 1`
- `prefers-reduced-motion: reduce` 时动画时长缩短为 0.01ms
- JS 未加载时通过 `<noscript>` 或 CSS 默认 `opacity: 1` 确保内容可见

---

## 检查清单

完成每份演示文稿后验证：

- [ ] 每个 `.slide` 都有 `height: 100vh; height: 100dvh; overflow: hidden;`
- [ ] 所有字号使用 `clamp(min, preferred, max)`
- [ ] 所有间距使用 `clamp()` 或视口单位
- [ ] 存在高度断点：700px、600px、500px
- [ ] 内容遵守密度限制（最多 6 个要点、6 个卡片）
- [ ] 没有固定像素高度的内容元素
- [ ] 图片有 `max-height` 约束

---

## 常见问题排查

| 问题 | 解决方案 |
| ---- | -------- |
| 内容溢出 slide | 检查 `overflow: hidden`；减少内容拆分多页；确保字号用 `clamp()` |
| 手机文字太小 | 使用 `font-size: clamp(1rem, 3vw, 2.5rem)` 格式 |
| 短屏内容不填满 | 添加 `@media (max-height: 600px)` 断点；减少 padding；隐藏装饰元素 |
