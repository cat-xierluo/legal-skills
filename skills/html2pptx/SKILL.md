---
name: html2pptx
description: 将 HTML 幻灯片转换为高保真可编辑 PPTX 或 PDF。支持任意 HTML（视口相对单位、flexbox/grid），文字保留为可编辑文本框。触发词：html2pptx、html转pptx、html转pdf、html2pdf、转换幻灯片。
---

# html2pptx — HTML 幻灯片转换器

将 AI 生成的 HTML 幻灯片精确转换为可编辑 PPTX 或高保真 PDF。

## 核心能力

- **可编辑 PPTX**：文字保留为可编辑文本框（非截图），位置、字号、颜色精确还原
- **高保真 PDF**：基于 Chromium 渲染，与浏览器预览 100% 一致
- **兼容任意 HTML**：自动处理视口相对单位（100vh、clamp()、vw）、flexbox、grid 布局
- **多页检测**：自动识别 `.slide` / `section` 容器，单文件多页一键转换
- **纯本地运行**：无云端依赖，数据不离开本机

## 技术架构

```
HTML 文件 → Playwright 渲染（固定视口 960×540）
    → getBoundingClientRect() 提取精确位置
    → getComputedStyle() 提取样式
    → PptxGenJS / page.pdf() 输出
```

## 使用方式

### 方式一：命令行

```bash
# 安装依赖（首次）
cd scripts && npm install

# 单文件 → PPTX
node convert.js slides.html -o output.pptx

# 单文件 → PDF
node convert.js slides.html -o output.pdf

# 单文件 → PPTX + PDF
node convert.js slides.html -o output --format both

# 目录批量转换
node convert.js ./slides-dir/ -o presentation.pptx

# 4:3 布局
node convert.js slides.html -o output.pptx --layout 4:3
```

### 方式二：代码调用

```javascript
const PptxGenJS = require('pptxgenjs');
const html2pptx = require('./scripts/html2pptx');
const { html2pptxMulti } = require('./scripts/html2pptx');

// 单页转换
const pptx = new PptxGenJS();
pptx.layout = 'LAYOUT_16x9';
const { slide, placeholders, warnings } = await html2pptx('slide.html', pptx);
await pptx.writeFile({ fileName: 'output.pptx' });

// 多页转换（自动检测 .slide / section）
const pptx2 = new PptxGenJS();
pptx2.layout = 'LAYOUT_16x9';
const results = await html2pptxMulti('all-slides.html', pptx2);
await pptx2.writeFile({ fileName: 'output.pptx' });

// PDF 转换
const html2pdf = require('./scripts/html2pdf');
await html2pdf('slides.html', 'output.pdf', { format: '16:9' });
```

## 支持的 HTML 特性

| 特性 | PPTX | PDF |
|------|------|-----|
| 文字（p, h1-h6） | 可编辑文本框 | 原生文字 |
| 图片（img） | 原生图片 | 原生图片 |
| 列表（ul, ol） | 原生项目符号 | 原生列表 |
| 背景色 | 形状填充 | CSS 背景 |
| 背景图 | 图片背景 | CSS 背景 |
| 边框、圆角 | 原生形状 | CSS 渲染 |
| 阴影 | PPTX 阴影 | CSS 渲染 |
| Flexbox / Grid | 计算后定位 | 原生渲染 |
| 100vh / clamp() | 强制视口后提取 | 原生渲染 |
| CSS 渐变 | 需预处理为图片 | 原生渲染 |
| 动画 | 不支持 | 不支持 |

## 工作流程（AI 辅助生成）

```
1. AI 根据内容生成 HTML 幻灯片
   → 参考 references/html-guide.md 获取最佳实践

2. 调用转换脚本
   → node convert.js slides.html -o output.pptx

3. 在 PowerPoint 中打开验证
   → 文字可编辑、布局准确
```

## 目录结构

```
html2pptx/
├── SKILL.md                 # 本文件
├── CHANGELOG.md
├── references/
│   └── html-guide.md        # HTML 编写最佳实践
└── scripts/
    ├── html2pptx.js         # PPTX 转换核心引擎
    ├── html2pdf.js          # PDF 转换模块
    ├── convert.js           # CLI 入口
    └── package.json
```

## 已知限制（PPTX 模式）

1. **CSS 渐变** → 需预先光栅化为 PNG 图片
2. **文字元素不能有背景/边框** → 使用 `<div>` 包裹
3. **div 中的裸文本** → 必须用 `<p>` 等标签包裹
4. **内联元素 margin** → PowerPoint 不支持
5. **inset 阴影** → 会损坏 PPTX 文件

PDF 模式无上述限制，推荐在不需要编辑时使用 PDF。

## 依赖

- Node.js >= 18
- Playwright（Chromium，首次运行 `npx playwright install chromium`）
- 系统字体（中文建议安装 Microsoft YaHei 或 PingFang SC）
