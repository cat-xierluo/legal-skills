# PPTX / PDF 转换稳定性指南

为获得最佳 PPTX/PDF 转换效果，编写 HTML 时必须把“浏览器预览好看”和“PowerPoint 可编辑稳定”同时纳入约束。本指南优先服务现有架构：本地 HTML → Playwright 固定视口渲染 → PPTX/PDF 转换。

---

## 固定视口与幻灯片尺寸

### 推荐尺寸

默认使用 16:9：

```css
* { box-sizing: border-box; }
html, body { width: 1000px; height: 562.5px; margin: 0; overflow: hidden; }
.slide {
  width: 1000px;
  height: 562.5px;
  position: relative;
  overflow: hidden;
}
```

如果需要 4:3，统一使用 `1000px × 750px`，并在转换时加 `--layout 4:3`。

### 规则

- `.slide` 或 `section` 必须是每页的根容器，不要把多页内容塞进一个长页面。
- 每页容器必须有明确宽高；允许 `100vw/100vh`，但推荐固定像素以减少浮点误差。
- `body` 不应出现滚动条；页面内部也不应依赖滚动展示内容。
- 底部重要文字保留至少 0.5 英寸安全区，避免 PowerPoint 字体差异造成截断。
- 转换前用验证脚本确认尺寸与溢出：`npm run validate -- ../example.html --strict`。

---

## 五条 PPTX 铁律

### 1. 文字必须用语义标签包裹

```html
<!-- 推荐 -->
<div style="position: absolute; ...">
  <h1>标题文字</h1>
  <p>正文内容</p>
</div>

<!-- 避免：div 中的裸文本 -->
<div style="...">裸文本不会被提取</div>
```

### 2. 文字元素不要有背景/边框

```html
<!-- 推荐：用 div 做背景容器，文字放在里面 -->
<div style="background: #1a1a1a; border-radius: 8px; padding: 20px;">
  <p style="color: white;">卡片内容</p>
</div>

<!-- 避免：p 标签直接加背景 -->
<p style="background: #1a1a1a;">背景色会丢失</p>
```

### 3. 背景使用纯色或图片

```html
<!-- 推荐 -->
<body style="background-color: #0f172a;">
<body style="background-image: url('bg.png');">

<!-- 避免：CSS 渐变（PPTX 不支持） -->
<body style="background: linear-gradient(135deg, #667eea, #764ba2);">
```

### 4. 颜色使用 RGB/HEX

```css
/* 推荐 */
color: #ffffff;
color: rgb(255, 255, 255);
color: rgba(255, 255, 255, 0.8);  /* 支持透明度 */

/* 避免 */
color: hsl(240, 100%, 50%);
color: currentColor;
```

### 5. 不用 inset 阴影

会损坏 PPTX 文件。只用外阴影。

---

## 文本稳定规则

### 语义标签优先

- 标题：`h1`-`h3`
- 正文：`p`
- 列表：`ul/ol/li`
- 标签/页码：仍使用 `p` 或 `span` 包裹，不要直接写在 `div` 文本节点中

### 换行与溢出

- 中文正文建议 `line-height: 1.5`-`1.8`，短标签可用 `1.2`。
- 宽度固定的文本框必须显式设置 `width`；不要依赖内容自动撑开。
- 长标题优先手动断句，避免浏览器和 PowerPoint 换行不一致。
- 不要用 `white-space: nowrap` 承载长句；只用于短标签、编号、日期。
- 不要把正文放进有背景或边框的 `p/li/h*` 中；背景放在父级容器。

### 字体

建议字体栈：

```css
font-family: 'Microsoft YaHei', 'PingFang SC', 'Noto Sans SC', sans-serif;
```

- 同一份课件最多使用 1 个中文字体栈 + 1 个数字/英文强调字体。
- 不使用网络字体；转换环境离线时会回退，导致文字宽度变化。
- 如果目标是在 Windows 上继续编辑，优先使用 `Microsoft YaHei`。

---

## 图片稳定规则

- PPTX 模式只使用本地图片路径：`./assets/chart.png`、`../images/photo.jpg`。
- 禁用远程图片：`https://...` 在离线或转换环境中不稳定。
- 禁用 base64 图片：PPTX 转换不支持或会显著增大文件体积。
- 图片文件名避免中文空格混杂，优先 `kebab-case.png`。
- 复杂图表、渐变背景、SVG 装饰建议预先导出为 PNG，再作为本地图片插入。
- 图片比例用 CSS 固定：`object-fit: cover` 或 `object-fit: contain`，不要让原图尺寸决定版面。

---

## 背景、渐变与阴影

### PPTX 优先

- 背景使用纯色或本地图片。
- 渐变、复杂滤镜、毛玻璃效果应预先光栅化为本地 PNG。
- 只使用外阴影，且阴影半径克制；禁止 `inset`。

### PDF 优先

- PDF 可渲染更多 CSS，但渐变叠加文字区域可能触发整页光栅化。
- 如果文字需要可选中/可搜索，避免在文字父容器上使用 `linear-gradient`、`radial-gradient`、`filter`。
- 用独立装饰层承载渐变，并与正文区域错开。

---

## 多页 HTML 结构

```html
<!DOCTYPE html>
<html>
<head>
  <style>
    .slide { width: 100%; height: 100vh; overflow: hidden; position: relative; }
  </style>
</head>
<body>
  <section class="slide" style="background-color: #1a1a1a;">
    <h1 style="...">封面</h1>
  </section>
  <section class="slide" style="background-color: #ffffff;">
    <h2 style="...">内容页</h2>
    <ul><li>要点一</li><li>要点二</li></ul>
  </section>
</body>
</html>
```

自动检测 `.slide` / `<section>` 容器，单文件多页一键转换。

---

## 输出格式对比

| 维度 | PPTX | PDF |
| ---- | ---- | --- |
| 编辑性 | 文字可编辑文本框 | 不可编辑 |
| CSS 渐变 | 不支持 | 支持 |
| CSS 动画 | 不支持 | 支持（定格） |
| inset 阴影 | 会损坏文件 | 支持 |
| base64 图片 | 不支持 | 支持 |
| 远程 URL 图片 | 不支持 | 支持 |
| 适用场景 | 需要后续编辑 | 定稿分发 |

**PDF 模式兼容多数 CSS 特性**，因为直接使用 Chromium 渲染。如果不需要编辑，优先使用 PDF；但若 PDF 需要保持文字可搜索、可选中，仍应遵守下方光栅化风险规则。

### PDF 文字光栅化陷阱

**CSS 渐变（`linear-gradient` / `radial-gradient`）会导致 PDF 中文字被光栅化**，失去矢量文字层，表现为文字模糊、不可选中、不可搜索。

```css
/* 避免：渐变叠加在文字区域上 */
.glow { background: radial-gradient(ellipse, rgba(255,255,255,0.08) 0%, transparent 50%); }
<div style="background: linear-gradient(135deg, #667eea, #764ba2);">

/* 推荐：用纯色替代 */
.glow { background: rgba(217,119,6,0.04); }
```

**根因**：Chromium 在生成 PDF 时，遇到渐变背景与文字重叠的区域会触发整页光栅化。

**解决方案**：
1. 装饰性渐变元素（光晕、氛围层）使用独立的 `.glow` class，转换脚本会自动隐藏
2. 内联渐变（如数据条、背景色块）改用纯色 `rgba()` 替代
3. HTML 中添加 `print-color-adjust: exact` 保证颜色精准

**检测方法**：PDF 文件体积异常偏大（>100KB/页）通常是光栅化的信号。

### PDF 分页控制

```css
.page-break { page-break-after: always; }
.no-break { page-break-inside: avoid; }
@page { size: 254mm 143mm; margin: 0; }
```

### PDF 光栅化风险清单

出现以下情况时，PDF 可能变成大图，导致文件变大、文字不可选中或打印模糊：

- 渐变背景覆盖正文区域。
- `filter: blur()`、`backdrop-filter`、混合模式覆盖整页。
- 大面积半透明叠层压在文字上方。
- 远程字体加载失败后触发布局重排。
- 将整页作为 SVG 或 canvas 绘制。

处理方式：优先改纯色；必要的复杂视觉先导出本地 PNG，并保证文字层独立。

---

## 元素支持一览

### 文字

| HTML 标签 | PPTX | PDF |
| --------- | ---- | --- |
| `<p>`, `<h1>`-`<h6>` | 可编辑文本框 | 原生 |
| `<span>`, `<b>`, `<i>`, `<u>` | 内联格式 | 原生 |
| `<br>` | 换行 | 原生 |

### 列表

| HTML 标签 | PPTX | PDF |
| --------- | ---- | --- |
| `<ul>` | 原生项目符号 | 原生 |
| `<ol>` | 原生编号 | 原生 |

### 布局

| CSS 属性 | PPTX | PDF |
| -------- | ---- | --- |
| `position: absolute` | 精确还原 | 原生 |
| `display: flex` | 计算后定位 | 原生 |
| `display: grid` | 计算后定位 | 原生 |
| `100vh` / `100vw` | 强制视口后还原 | 原生 |
| `clamp()` | 计算后还原 | 原生 |

### 样式

| CSS 属性 | PPTX | PDF |
| -------- | ---- | --- |
| `background-color` | 形状填充 | 原生 |
| `background-image: url()` | 图片背景 | 原生 |
| `background: gradient` | 不支持 | 原生 |
| `border` | 形状边框 | 原生 |
| `border-radius` | 圆角形状 | 原生 |
| `box-shadow` (outer) | PPTX 阴影 | 原生 |
| `box-shadow` (inset) | 不支持（损坏文件） | 原生 |
| `transform: rotate()` | 旋转 | 原生 |
| `opacity` | 透明度 | 原生 |
| `writing-mode: vertical-*` | 竖排文字 | 原生 |

### 图片

| 类型 | PPTX | PDF |
| ---- | ---- | --- |
| `<img>` (本地路径) | 原生图片 | 原生 |
| `<img>` (base64) | 不支持 | 原生 |
| `<img>` (远程 URL) | 不支持 | 原生 |

**本地图片预检**：转换前打开 HTML 所在目录，确认所有相对路径图片存在；不要依赖浏览器缓存。

---

## 中文字体映射

| 系统字体 | PPTX 字体 |
| -------- | --------- |
| PingFang SC (macOS) | PingFang SC |
| Microsoft YaHei (Windows) | Microsoft YaHei |
| Noto Sans SC (Linux) | Noto Sans SC |

建议字体栈：`'Microsoft YaHei', 'PingFang SC', 'Noto Sans SC', sans-serif;`

---

## 转换前预检清单

运行：

```bash
cd scripts
npm run validate -- ../example.html --strict
```

人工复核：

- [ ] 每页都有 `.slide` 或 `section` 容器。
- [ ] 每页尺寸接近目标视口（默认 1000×562.5px）。
- [ ] body 与 slide 无横向/纵向滚动溢出。
- [ ] 所有正文使用 `p/h1-h6/ul/ol/li` 包裹，没有裸 `div` 文本。
- [ ] 文字标签本身没有背景色或边框，背景由父级容器承担。
- [ ] 无 `box-shadow: inset`。
- [ ] 无远程图片、base64 图片；图片均为本地路径。
- [ ] 需要 PPTX 可编辑时，避免 CSS 渐变、滤镜和毛玻璃。
- [ ] 需要 PDF 可搜索时，正文区域不要叠加渐变或滤镜。
- [ ] 在浏览器预览、PPTX 打开、PDF 打开三个环节都确认无裁切。

---

## 风格友好写法（便于提取和复用）

### 使用 CSS 变量统一管理配色

```css
:root {
  --primary: #18181B;
  --accent: #D97706;
  --accent-light: #F59E0B;
  --bg-light: #FAFAF8;
  --text-muted: #52525B;
}
```

风格提取工具会自动读取这些变量。

### 保持一致的字号体系

```css
.title-xl { font-size: 49px; }  /* 封面主标题 */
.title-lg { font-size: 36px; }  /* 章节标题 */
.title-md { font-size: 28px; }  /* 小节标题 */
.body-lg  { font-size: 18px; }  /* 重点正文 */
.body-md  { font-size: 16px; }  /* 正文 */
.caption  { font-size: 12px; }  /* 标签/注脚 */
```

### 装饰元素使用语义化 class

```css
.deco-line { height: 0.78px; background: var(--accent); }
.box-dark  { background: var(--primary); color: var(--accent); }
.badge     { font-size: 12px; color: var(--accent); border: 0.7px solid var(--accent); }
```
