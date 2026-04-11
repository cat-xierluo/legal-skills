# HTML 幻灯片编写指南

为获得最佳 PPTX 转换效果，编写 HTML 时建议遵循以下规范。

## 最佳实践（PPTX 模式）

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

### 5. 多页 HTML 结构

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

## PDF 模式

PDF 模式兼容所有 CSS 特性（渐变、动画定格、flexbox、grid），因为直接使用 Chromium 渲染。如果不需要编辑，优先使用 PDF。

### PDF 分页控制

```css
/* 强制分页 */
.page-break { page-break-after: always; }

/* 防止元素跨页 */
.no-break { page-break-inside: avoid; }

/* 自定义页面尺寸 */
@page { size: 254mm 143mm; margin: 0; }
```

## 支持的元素和属性一览

### 文字

| HTML 标签 | PPTX 支持 | PDF 支持 |
|-----------|----------|---------|
| `<p>` | 可编辑文本框 | 原生 |
| `<h1>`-`<h6>` | 可编辑文本框 | 原生 |
| `<span>`, `<b>`, `<i>`, `<u>` | 内联格式（粗体/斜体/下划线/颜色） | 原生 |
| `<br>` | 换行 | 原生 |

### 列表

| HTML 标签 | PPTX 支持 | PDF 支持 |
|-----------|----------|---------|
| `<ul>` | 原生项目符号 | 原生 |
| `<ol>` | 原生编号 | 原生 |

### 布局

| CSS 属性 | PPTX 支持 | PDF 支持 |
|---------|----------|---------|
| `position: absolute` | 精确还原 | 原生 |
| `display: flex` | 计算后定位 | 原生 |
| `display: grid` | 计算后定位 | 原生 |
| `100vh` / `100vw` | 强制视口后还原 | 原生 |
| `clamp()` | 计算后还原 | 原生 |

### 样式

| CSS 属性 | PPTX 支持 | PDF 支持 |
|---------|----------|---------|
| `background-color` | 形状填充 | 原生 |
| `background-image: url()` | 图片背景 | 原生 |
| `background: gradient` | 不支持 | 原生 |
| `border` | 形状边框 | 原生 |
| `border-radius` | 圆角形状 | 原生 |
| `box-shadow` (outer) | PPTX 阴影 | 原生 |
| `box-shadow` (inset) | 不支持（会损坏文件） | 原生 |
| `transform: rotate()` | 旋转 | 原生 |
| `opacity` | 透明度 | 原生 |
| `writing-mode: vertical-*` | 竖排文字 | 原生 |

### 图片

| 类型 | PPTX 支持 | PDF 支持 |
|------|----------|---------|
| `<img>` (本地路径) | 原生图片 | 原生 |
| `<img>` (base64) | 不支持 | 原生 |
| `<img>` (远程 URL) | 不支持 | 原生 |

## 中文字体映射

| 系统字体 | PPTX 字体 |
|---------|----------|
| PingFang SC (macOS) | PingFang SC |
| Microsoft YaHei (Windows) | Microsoft YaHei |
| Noto Sans SC (Linux) | Noto Sans SC |

建议在 HTML 中指定字体栈：
```css
font-family: 'Microsoft YaHei', 'PingFang SC', 'Noto Sans SC', sans-serif;
```
