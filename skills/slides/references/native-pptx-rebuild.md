# 动态 HTML → 原生可编辑 PPTX · 混合式重建工作流

## 目标

同一份课件同时满足两种交付：

- HTML 演示保留 WebGL、ASCII、canvas、视频或粒子等动态背景；
- PowerPoint 把背景冻结为静态画面，但标题、正文、卡片、线条和前景图片仍是原生可编辑对象。

不要把整页截图塞进 PPTX。整页截图只能作为视觉校验基准，不能替代对象级重建。

## 两层结构

### 背景层

给浏览器专属背景加稳定标记：

```html
<canvas class="ascii-bg" data-ppt-background aria-hidden="true"></canvas>
```

也可使用 `canvas.bg`、`canvas.ascii-bg` 或 `video[data-ppt-background]`。导出时只显示这些元素并截取一帧，作为 PPTX 的静态背景图。

### 前景层

标题、正文、页眉页脚、卡片、流程、分隔线和普通 `<img>` 继续走 DOM 几何与样式提取，在 PowerPoint 中逐项重建。前景不要合并进背景截图。

讲者备注优先写在 slide 上：

```html
<section class="slide" data-note="本页口播与停留时间……">
```

也支持 `[data-speaker-notes]`、`aside.notes` 或 `.speaker-notes`。

## 背景策略

`convert.js` 支持：

- `--background-mode auto`：默认；检测到动态背景标记时冻结，否则保留原生背景色/背景图。
- `--background-mode freeze`：无论是否检测到标记都截取背景帧，适合复杂 CSS 纹理。
- `--background-mode native`：不截图，全部按既有 DOM/CSS 转换，适合纯色和普通背景图。

```bash
cd scripts
node convert.js 课件.html -o 课件-v2.pptx --background-mode auto --strict
```

始终输出新版本文件，不覆盖已验收的旧版。

## 两种原生重建引擎

### Codex Presentations Runtime 可用时

优先用 `@oai/artifact-tool`：

1. Playwright 固定视口打开 HTML，逐页提取 DOM 文本、图片、形状、边框与讲者备注。
2. 单独截取背景层画面，并作为每页背景图。
3. 用 Artifact Tool 重建前景对象。
4. 用官方 finalizer 校验页数、包完整性、字体和几何。
5. 渲染全部页面逐页检查；不能只看第一页或 contact sheet。

### 普通本地环境

使用内置 Playwright + PptxGenJS 转换器。它遵循同一层次边界：只冻结背景，前景逐项重建，并把讲者备注写入 PowerPoint notes。

## 验收门槛

1. HTML：动态背景可运行；低功耗/减少动态模式有静态回退；翻页后深浅背景正确切换。
2. PPTX：页数正确；背景存在；标题/正文/卡片可单独选中编辑；前景不是单张全页图片。
3. Notes：抽检封面、介绍页、正文页和收尾页，讲者备注可见。
4. 版式：每页单独渲染检查裁切、重叠、图片变形和字号。
5. 文件：通过 zip/package integrity；输出文件名带新版本号。

## 常见误区

- 把整个页面截图作为 PPTX：看似保真，但失去可编辑性。
- 只删掉动态 canvas：PPTX 虽可编辑，但品牌背景丢失。
- 背景截图时没有隐藏前景：会产生重影，文字看起来加粗。
- 用未来场次或未核验数字装饰讲师介绍：会把可信度问题带进课件。
- 把“HTML 动态”误解为“PowerPoint 动画”：本流程只承诺 PowerPoint 中静态背景 + 原生前景对象。
