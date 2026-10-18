---
name: slides
license: MIT
metadata:
  version: "1.5.16"
  homepage: https://github.com/cat-xierluo/legal-skills
  author: 杨卫薪律师（微信ywxlaw）
description: 幻灯片全流程创作工具。本技能应在需要从文稿或主题生成精美幻灯片、将 HTML 转换为可编辑 PPTX/PDF、从现有课件提取风格、或围绕主题做结构化研究时使用。不要用于纯文档排版（用 md2word）或图片处理（用 imagemagick）。
---

# slides — 幻灯片全流程创作工具

从主题研究到最终交付的一体化幻灯片创作工具：主题研究 → 风格选择 → AI 生成 HTML → 转换可编辑 PPTX / PDF。支持从现有幻灯片中提取可复用的设计风格，构建个人风格库。

## 核心能力

- **主题研究**：输入主题和受众，自动产出结构化研究报告（`research.md`）和分页大纲（`slides_outline.json`）
- **可编辑 PPTX**：文字保留为可编辑文本框（非截图），位置、字号、颜色精确还原
- **混合式动态背景**：HTML 保留 WebGL / ASCII / canvas 动效；导出 PPTX 时只冻结背景层，前景文字、卡片、线条与图片继续逐项重建为原生对象
- **高保真 PDF**：基于 Chromium 渲染，以浏览器渲染为基础，交付前逐页核对
- **风格提取**：从现有 HTML 幻灯片提取配色、字体、布局等风格参数，保存为可复用的 JSON 风格文件
- **风格库**：内置 38 个预设风格（法律黑金、极简编辑白、咨询蓝、深度报道、客观网格等），支持用户自行提取和扩展
- **设计系统**：内置 CSS 设计语言（排版刻度、间距系统、组件模式、视觉层级规则），12 个完整 HTML 模板文件可直接 clone 替换内容
- **预检验证**：转换前用 Playwright 检查 slide 容器、尺寸、溢出、渐变/inset 阴影、裸 `div` 文本、远程/base64 图片、文字背景/边框等风险
- **兼容任意 HTML**：自动处理视口相对单位（100vh、clamp()、vw）、flexbox、grid 布局
- **动画系统**：浏览器模式支持入场动画（fadeSlideUp/Left/Right/Scale）、延迟级联（d1-d6）、页面转场策略（cascade/hero/quote/directional），PPTX 导出时自动降级
- **多页检测**：自动识别 `.slide` / `section` 容器，单文件多页一键转换
- **通用可分发**：不内置任何个人信息；讲者身份、联系方式、头像与二维码来自本地配置，未配置时按匿名默认生成，开箱即用
- **本地转换**：转换引擎不需要云端 API；HTML 中的远程字体、图片或脚本仍可能联网，处理私有材料时应使用本地资源并核对输入来源。

## 输入/输出

### 输入
- **HTML 幻灯片文件**（必需）：包含 `.slide` 或 `section` 容器的 HTML 文件
- **输出格式**（可选）：`--format pptx|pdf|both`；显式参数优先，否则按输出文件的 `.pptx` / `.pdf` 后缀选择，没有可识别后缀时默认 PPTX。
- **布局比例**（可选）：`--layout 16:9|4:3`，默认 16:9
- **风格参数**（可选）：`--extract-style` 提取风格，`--save 名称` 保存到风格库

### 输出
- **PPTX 文件**：可编辑 PowerPoint（文字保留为文本框）
- **PDF 文件**：基于 Chromium 渲染的高保真 PDF
- **风格 JSON**：`--extract-style` 时输出结构化风格参数

## 技术架构

```
HTML 文件 → Playwright 渲染（固定视口）
    → 动态背景层单独冻结为静态 PNG
    → getBoundingClientRect() / getComputedStyle() 提取前景位置与样式
    → Codex Presentations Runtime：Artifact Tool 逐项重建 + finalizer
    → 本地 CLI 回退：PptxGenJS 逐项重建
    → PDF：Chromium 高保真渲染

风格提取 → 遍历 DOM 元素收集配色/字体/布局
    → 聚类去重 → 结构化 JSON → 风格库
```

## 本地配置（可选）

技能**不内置任何个人信息**。没有配置时按匿名默认生成——课件只有本次内容，没有讲者姓名、联系方式、头像、二维码或空白介绍页。

需要个性化时，用本地配置提供讲者身份、联系方式、品牌与展示开关：

```bash
# 引导模式：打印需要收集的字段清单（Agent 逐项询问后回填）
node scripts/init-profile.js

# 非交互写入（默认 ~/.config/slides/profile.local.json）
node scripts/init-profile.js --name "张三" --title 律师 --organization "某某律师事务所" \
  --wechat-qr ~/assets/wx.png --show-wechat-qr --style 商务权威

# 校验（只报字段是否已填与路径状态，不打印资料值）
node scripts/check-profile.js
```

配置在**技能目录之外**，技能升级/重装不覆盖。一次运行只加载一份配置，解析顺序：`--config` / `SLIDES_PROFILE` → 课件项目 `.slides/profile.json` → 技能目录 `config/profile.local.json` → `~/.config/slides/profile.local.json` → 匿名默认。相对路径相对于被选配置文件所在目录解析；显式路径错误或 JSON 损坏直接报错，不回退到他人资料。

公私区分的总约定：**Git 跟踪的 = 可发布通用内容；被 `.gitignore` 忽略的 = 使用者私有**（`config/profile.local.json`、`config/local/`、`assets/local/` 等）。本人旧资料原件放在 `config/local/`（恢复来源，运行时不读取）。

**生成 HTML 时**读取同一份配置：

```bash
node scripts/load-profile.js --json       # 完整配置（供生成流程消费）
node scripts/load-profile.js --footer     # 仅页脚文本
node scripts/load-profile.js --assets     # 已启用素材的解析路径
```

- 身份字段留空即省略该元素，不虚构。介绍页由 `presentation.intro_pages` 决定，收尾形态由 `presentation.closing_mode` 决定。
- `show_profile` / `show_footprints` / `show_wechat_qr` / `show_public_account_qr` 关闭时**不读取**对应图片与来源文件，页面上也不留占位框。
- 二维码是明确要求展示的承诺：启用而缺图片按校验错误处理，不得用旧码或假码顶替。
- 头像 / 二维码 / 字体等私有素材本地创作时直接引用配置路径；**发给他人的课件必须另做资源打包**（复制进课件资源目录、改相对引用并核移动后可打开）。
- 转换时导出元数据（PPTX 作者）与个人风格保存目录都读同一份配置；未配置身份时回退到工具名与个人风格目录。

字段定义与迁移说明见 [本地配置](references/configuration.md)；空白模板见 [config/profile.example.json](config/profile.example.json)。

## 完整创作工作流

```
① 需求澄清      ② 研究/大纲      ③ 风格+版式       ④ 生成 HTML       ⑤ 预检       ⑥ 转换+QA
受众/场景/格式 → research.md → 风格库/版式家族 → 本地 HTML 文件 → validate → PPTX/PDF
页数/证据密度     outline.json    templates/playbook    固定视口/语义标签   strict     打开复核
```

**标准流程**：
1. **需求澄清**：先读本地配置（`node scripts/load-profile.js`）确定讲者身份、页脚与展示开关；未配置即匿名生成，不补位任何个人信息。再确认受众、场景、页数、交付格式（PPTX/PDF/both）、是否需要后续编辑、证据密度和视觉语气；缺失信息标记为“待补充”。
2. **研究与大纲**：用户只有主题时，先产出 `research.md` + `slides_outline.json`（参考 `references/research/`）；用户已有文稿时，先拆成分页目标。
3. **风格与版式选择**：默认风格取配置的 `brand.style`（未配置则由场景决定）；从风格库选择预设或提取旧课件风格；再依据 `references/layout-theme-playbook.md` 选择版式家族，使用 `references/templates/` 下的完整 HTML 模板文件（12 个页面类型，共享 `_base.css` 设计系统）。
4. **生成 HTML**：clone `references/templates/` 中对应的模板文件，替换占位内容，切换 `:root` 主题变量。遵守 `_base.css` 的设计系统：语义标签、本地图片、固定视口。动态背景统一标记 `data-ppt-background`，讲者备注写在 slide 的 `data-note` 或 `[data-speaker-notes]` 中。
5. **预检验证**：执行 `cd scripts && npm run validate -- ../example.html --strict`；正式文件替换为目标 HTML 路径。先修复 errors，再处理 warnings。
6. **转换输出**：执行 `node convert.js 新内容.html -o 输出 --format both --background-mode auto`，或按需输出 PPTX/PDF。Codex 环境若提供 Presentations Runtime，优先按 `references/native-pptx-rebuild.md` 用 Artifact Tool 重建并通过 finalizer；本地 CLI 则用内置 PptxGenJS 转换器。
7. **最终 QA**：浏览器预览、PPTX 打开、PDF 打开三处复核：页面尺寸、文字裁切、图片缺失、PDF 文字是否可选、PPTX 前景是否可逐项编辑、动态背景是否已在 PPTX 中静态保留、讲者备注是否写入。

**常用参考**：
- 版式与主题：`references/layout-theme-playbook.md`
- 完整 HTML 模板：`references/templates/`（12 个页面类型 + `_base.css` 设计系统 + `README.md` 索引）
- PPTX/PDF 稳定性：`references/pptx-guide.md`
- 混合式原生重建：`references/native-pptx-rebuild.md`
- 风格参考：`references/style-reference.md`
- 本地配置（身份/素材/偏好/初始化/迁移）：`references/configuration.md`
- 中文课件排版与去冗余：`references/cn-deck-polish.md`（§1–23：不用斜体 / 页眉脚极简 / 封面分节去冗余 / 去出处标注 / 照片比例 / 内联色防隐形 / 计数同步 / 介绍页按配置拆页 / 收尾按配置定形态 / 招牌背景可见性 / 深浅搭配 / 翻页导航交互 / 素材按本地创作与对外交付两种策略 / §14 视口 overflow 三层陷阱 / §15–19 流程总览分步 / 并列卡密度 / Skill 命名精确 / 专有名词统一 / 跨页字号统一 / §20–22 组件复用先读 CSS / 720p 预算与 DOM 几何验证 / 页码全量重编（两处计数器按页分组同号）+ 排版基准附录 / §23 竖向引擎衬底与 slide 同族）——生成与审计中文 deck 前过一遍

## 主题研究模块

当用户只有主题想法，尚无可用讲稿和幻灯片大纲时，使用内置的研究框架：

**输入**：
- `topic`：研究主题
- `audience`：受众（律师团队/企业法务/公开分享等）
- `target_pages`：目标页数（建议 8-12）
- `tone`：表达风格（专业严谨/前瞻创新/培训导向等）

**输出**：
- `research.md`：结构化研究报告（含核心结论、证据、风险与边界）
- `slides_outline.json`：分页大纲（每页包含标题、摘要、布局类型、要点、演讲者备注）

**研究资源**：
- 研究框架：`references/research/research_framework.md`
- 报告模板：`references/research/research_report_template.md`
- 大纲 Schema：`references/research/slides_outline.schema.json`

**写作原则**：
- 事实先于观点：先给证据，再给结论
- 结论可执行：每页至少 1 条可落地建议
- 术语可解释：首次出现的关键术语补一句定义

## 使用方式

### 命令行

三条交付路径均保留：PPTX 用于后续编辑，PDF 用于阅读与分发，`both` 同时生成两者。`--format` 优先于文件名后缀；未指定格式且输出没有可识别后缀时仍默认 PPTX。多文件/目录输入目前仅支持合并为 PPTX；PDF 或双格式需要先把内容组织为一个多页 HTML，避免静默遗漏后续文件。


```bash
# 安装依赖（首次）
cd scripts && npm install
npx playwright install chromium

# ── 文件转换 ──
# 单文件 → PPTX
node convert.js slides.html -o output.pptx --background-mode auto

# 单文件 → PDF
node convert.js slides.html -o output.pdf --format pdf

# 单文件 → PPTX + PDF
node convert.js slides.html -o output --format both

# 目录批量转换
node convert.js ./slides-dir/ -o presentation.pptx

# 4:3 布局
node convert.js slides.html -o output.pptx --layout 4:3

# ── 风格提取 ──
# 从 HTML 提取风格，输出 JSON
node convert.js slides.html --extract-style -o style.json

# 提取并保存到风格库
node convert.js slides.html --extract-style --save 商务法律风

# 列出风格库中所有可用风格
node convert.js --list-styles

# ── 转换前预检 ──
# 宽松模式：输出错误/警告但不中断
npm run validate -- ../example.html

# 严格模式：存在错误时退出非零
npm run validate -- ../example.html --strict

# 指定 4:3 视口
npm run validate -- ../example.html --viewport 1000x750 --strict
```



### html2pdf.js 保真选项表（v1.5.11+）

`html2pdf` 在保留 v1.5.10 默认行为的基础上，新增以下可选参数。所有选项**默认关闭**，与 v1.5.10 完全等价；按需开启以提升保真度。

| 选项 | 取值 | 作用 | 默认 |
|---|---|---|---|
| `textRendering` | `geometricPrecision` / `optimizeLegibility` / `auto` | 减少 macOS 上 CJK 字形栅格化为 Type3 的概率 | `auto` |
| `backgroundStrategy` | `as-is` / `freeze` / `hide` | 动态背景处理：`freeze` 把 canvas 当前帧 snapshot 成静态图（保纹理、仍是栅格背景）；`hide` 完全隐藏（最干净矢量文字）；`as-is` 不动 | `as-is` |
| `preferExactSize` | `true` / `false` | 用整数像素尺寸替代 mm 浮点换算（消除 `960.96×540.96` 漂移） | `false` |
| `outline` | `true` / `false` | PDF outline/bookmark，从 `[data-pdf-outline]` / `<header>` / `.kicker` 抽取 | `false` |
| `tagged` | `true` / `false` | 输出 tagged PDF（可访问性朗读） | `false` |
| `marginMode` | `none` / `compact` / `normal` / `wide` | 单页 PDF 边距预设；多页 deck 默认仍为 `none` | `none` |
| `margin` | `{top,right,bottom,left}` | 显式覆盖 `marginMode`（接受数字字符串或 mm 单位） | — |

**典型用法**：

```js
// 单页 HTML 报告：紧凑边距
await html2pdf('report.html', 'report.pdf', { marginMode: 'compact' });

// 多页 deck：保留动态背景纹理
await html2pdf('deck.html', 'deck.pdf', { backgroundStrategy: 'freeze' });

// 跨设备归档：尺寸精确 + 可访问性标签
await html2pdf('deck.html', 'deck.pdf', { preferExactSize: true, tagged: true });
```

**回归保证**：v1.5.11 已通过 7 项单元测试（`scripts/tests/test-html2pdf-fidelity.mjs`），覆盖默认路径与所有新选项组合；默认调用产物与 v1.5.10 二进制兼容。



`scripts/` 下有 **3 个不同的转换入口**，适用场景不同：

| HTML 类型 | 检测特征 | 用脚本 | 输出 |
|-----------|---------|--------|------|
| **垂直分页 deck**（默认情况）| `.slide` 容器**垂直堆叠**（无 `#deck` 容器）| `convert.js` 或 `html2pdf.js` | 多页 PDF（文字可选）|
| **水平翻页 carousel** ⚠️ | `#deck { position:fixed; width:10000vw; transform:translateX }` 模式（reveal.js / 自写 carousel）| **`html2pdf.js`**（≥v1.5.2，文字层 PDF）⭐；`html2pdf-carousel-hd.js` 降为 fallback（图片型）| 多页 PDF（**文字可选**）|
| **垂直 scroll-snap + WebGL 招牌** ⚠️ | `body{scroll-snap-type:y}` + `.slide{width:100vw;height:100vh}` + `position:fixed` WebGL/canvas 动态背景（scroll-snap 课件形态）| **`html2pdf-scrollsnap-hd.js`** ⭐ | 多页 PDF（图片型，按浏览器画面栅格化）|
| **单页 HTML** | 仅 1 个 `.slide` 或无 `.slide` 容器 | `convert.js` 或 `html2pdf.js` | 单页 PDF |

### ⚠️ 水平翻页 carousel 的脚本选择（2026-09-07 修订）

> **修订（html2pdf.js v1.5.2 / v1.5.3）**：v1.5.1 补丁后仍单页/渲染不全的真正病根是 `html,body { height:100%; overflow:hidden }` 把 static 化的内容重新裁成一页——v1.5.2 已放开；v1.5.3 新增 `body.exporting` 导出态约定（课件可隐藏放映 HUD）。**自 v1.5.2 起，水平翻页 carousel 默认用 `html2pdf.js`：37 页 carousel deck 实测正确分页、文字层可选中可搜索**（案例：多页宣讲课件回归样例）。carousel-hd 降为打印路径失败时的 fallback（图片型）。
> 前提条件：转换等待需满足 `document.fonts.ready`（html2pdf.js 已内建）；课件应提供 `body.exporting` 隐藏规则。

**历史教训（v1.5.1 时代，保留备查）——当时为什么退到了截图法：**

- `convert.js` 检测到 `.slide` 容器数（看似 38 张）但 `@page size + page-break-after` 在 `position:fixed; width:10000vw` 容器下**不生效**
- 结果：`detectCount: 38`，但 PDF 实际只输出 1 页（其余 37 张被 `#deck` 横向 transform 推出视口）
- `html2pdf.js` v1.5.1 已有 #deck static 补丁，但**单页** 渲染——动画完成度依赖 `waitForTimeout(100)`，常导致字体未加载 / data-anim 元素 opacity=0 / WebGL canvas 未绘制

**carousel-hd 脚本的正确做法**（`scripts/html2pdf-carousel-hd.js`）：

1. 固定 viewport 到 `1280×720`（slide 自然尺寸）
2. `deviceScaleFactor=2` → 每张 PNG 2560×1440（HD）
3. `await page.evaluate(() => document.fonts.ready)` — **等 web fonts 加载完**
4. 对每个 `.slide`：
   - 注入 `__revealForCapture()` → 取消所有 web animation + 强制 `data-anim` 元素 `opacity: 1`
   - `await page.waitForTimeout(900)` — 等 CSS `transition .9s` 动画完成
5. `page.screenshot({ clip })` 截单张 slide
6. ImageMagick `convert *.png output.pdf` 合并为多页 PDF

**使用方法**：

```bash
cd scripts
node html2pdf-carousel-hd.js <input.html> <output.pdf>
# 输出示例：carousel-hd: 检测到 38 张幻灯片 @ 1280×720 ×2DPR
#          carousel-hd: 合并 38 张 PNG → PDF (ImageMagick)
```

**视觉验证脚本**：

```bash
# 转完用 PyMuPDF 抽 3 张看
python3 -c "
import fitz
doc = fitz.open('output.pdf')
for i in [0, 1, 9, 19, 37]:
    pix = doc[i].get_pixmap(matrix=fitz.Matrix(0.4, 0.4))
    pix.save(f'page_{i+1}.png')
"
# 找最大 PNG（封面 / 结语通常内容最满）—— 几张图加起来应 < 5 MB
```

**已知权衡**：

- ✅ 按浏览器画面栅格化（包括 web fonts、WebGL 滤镜、data-anim 元素）
- ❌ PDF 文字是图片——`pdftotext` / PyMuPDF `get_text()` 拿不到字
- ❌ 不能搜索 / 复制
- ❌ 文件较大（38 张 carousel PDF ≈ 6 MB；vs 文字型 PDF 38 页 ≈ 0.4 MB）

**如果必须文字可选**：

- 修改 HTML，让 `.slide` 在 carousel 状态下隐藏 / 显示切换（不用 `transform translateX`，用 `display:none` 切换）→ 此时 `convert.js` / `html2pdf.js` 可用

### ⚠️ 垂直 scroll-snap + WebGL 招牌背景 用 scrollsnap-hd 脚本

scroll-snap + WebGL 招牌课件常见形态：`body{scroll-snap-type:y proximity}` + `.slide{width:100vw;height:100vh}` + `position:fixed` 的 WebGL 双 canvas（`bg-dark`/`bg-light`）+ IntersectionObserver 按 slide 切 `body.light-bg`（**克隆注意**：同步的 body 类必须有配套 CSS 消费，slide 半透明底时每页衬底须与 slide 同族——见 `cn-deck-polish.md` §23）+ `data-anim` 入场动画 + low-power 降级。`@page`+`page-break` 对 `position:fixed` canvas 不生效，`convert.js`/`html2pdf.js` 会丢背景或只出 1 页。

**`scripts/html2pdf-scrollsnap-hd.js` 的做法**：`channel=chrome` + `--use-gl=swiftshader` 让 headless 真绘制 WebGL；`emulateMedia reducedMotion:'no-preference'` 防 low-power 降级；注入 CSS 隐藏 `#nav/#hint/#overview`、关 scroll-snap；逐张 `scrollIntoView({behavior:'instant'})` + 强制 `[data-anim]` opacity:1 + 等 IntersectionObserver 与多帧 RAF；screenshot 截视口（1280×720×2DPR）；magick 合并。

```bash
cd scripts
# 若 HTML 含 Google Fonts 外链（思源宋体等），先造去字体副本避免 goto 超时
grep -vE "fonts\.(googleapis|gstatic)\.com" 原.html > /tmp/副本.html
node html2pdf-scrollsnap-hd.js /tmp/副本.html 输出.pdf
# 输出示例：scrollsnap-hd: 检测到 45 张幻灯片 @ 1280×720 ×2DPR
#           scrollsnap-hd: 合并 45 张 PNG → PDF (ImageMagick)
```

权衡同 carousel-hd：按浏览器画面栅格化（含 WebGL 招牌、明暗底切换、ASCII 封面层、data-anim 入场），但 PDF 文字为图片、不可选/搜索、文件较大（45 页 ≈ 20 MB）。

## 内置风格库

38 个预设风格位于 `references/styles/` 目录，AI 生成新 HTML 时可直接引用。按场景分类：

**法律/政务**
| 风格 | 适用场景 | 主配色 |
|------|---------|--------|
| 法律黑金 | 法律讲座、培训课件 | 黑底 + 金色 |
| 极简编辑白 | 培训、讲座、专业分享 | 白底 + 翡翠绿 |
| 政务红 | 政府报告、党建课件 | 红色系 |
| 政策公文 | 政策解读、行业规范 | 深蓝红双色 |

**商务/金融**
| 风格 | 适用场景 | 主配色 |
|------|---------|--------|
| 商务权威 | 年度报告、财务分析 | 深蓝 + 红色 |
| 商务金 | 企业报告、商务演示 | 金色调 |
| 咨询蓝 | 战略分析、管理报告 | 专业深蓝 |
| 金融深灰 | 投资分析、基金路演 | 深灰 + 金色 |
| 投行黑 | IPO 路演、交易展示 | 纯黑 + 红蓝 |
| 保险蓝白 | 保险产品、风控报告 | 深蓝白底 |

**科技/创意**
| 风格 | 适用场景 | 主配色 |
|------|---------|--------|
| 科技暗夜 | 科技发布、AI 产品 | 黑蓝 + 金光 |
| 科技蓝 | 技术分享、产品发布 | 蓝色系 |
| 赛博朋克 | 科技创意、游戏发布 | 霓虹粉青紫 |
| 毛玻璃 | SaaS 产品、UI 展示 | 半透明紫蓝 |
| 北欧极光 | 高端消费品、品牌定位 | 冰蓝 + 极光色 |
| 创业路演 | 融资 BP、增长汇报 | 紫青撞色 |

**编辑/网格**
| 风格 | 适用场景 | 主配色 |
|------|---------|--------|
| 深度报道 | 深度长文、行业观察、人物专访 | 暖骨白 + 墨黑 + 砖红 |
| 客观网格 | 数据汇报、架构说明、方法论讲解 | 纯白 + 石墨黑 + 正红 |

**教育/学术**
| 风格 | 适用场景 | 主配色 |
|------|---------|--------|
| 教育图表 | 统计报告、数据分析 | 多色图表 |
| 教育绿 | 教育培训、知识分享 | 绿色调 |
| 教育粉笔 | 课堂教学、知识科普 | 墨绿底 + 粉笔白 |
| 学术深蓝 | 论文答辩、学术会议 | 海军蓝 + 暖白 |

**行业/场景**
| 风格 | 适用场景 | 主配色 |
|------|---------|--------|
| 铂金白金 | 金融科技、企业官网 | 白底 + 蓝金 |
| 活力科技 | 创业路演、青年教育 | 深蓝 + 橙色 |
| 学术复古 | 学术讲座、历史回顾 | 深红 + 深蓝 |
| 自然森系 | ESG 报告、环保主题 | 绿色系 |
| 纸墨 | 文化讲座、书法主题 | 米白 + 墨色 |
| 暗色植物 | 生态主题、高端展示 | 深色 + 绿植 |
| 瑞士现代 | 设计分享、品牌展示 | 红黑白 |
| 大胆信号 | 创意演示、品牌发布 | 高对比撞色 |
| 电动工作室 | 创意工坊、新媒体 | 霓虹 + 暗色 |
| 极简日式 | 品牌哲学、生活方式 | 大留白 + 墨色 |
| 工程蓝图 | 工程规格、系统架构 | 蓝图蓝 + 白线 |
| 医疗薄荷 | 医疗报告、健康科普 | 薄荷绿 + 白底 |
| 房地产金 | 楼盘发布、地产报告 | 墨绿黑金 |
| 快消活力 | 产品发布、快消营销 | 明亮多色 |
| 餐饮暖橙 | 餐饮品牌、菜单展示 | 暖橙 + 奶油白 |
| 婚礼香槟 | 婚礼策划、活动提案 | 香槟金 + 柔粉 |

也可从现有 HTML 提取自定义风格：`node convert.js 课件.html --extract-style --save 风格名`

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
| CSS 渐变 | 需预处理为图片；预检会提示 | 原生渲染，但可能触发文字光栅化 |
| 入场动画 | 不支持（自动降级为静态） | data-anim 触发淡入/滑入/缩放 |
| 页面转场 | 不支持 | data-animate 指定 cascade/hero/quote/directional |
| WebGL / ASCII / canvas 动态背景 | 冻结为静态背景图；前景仍可编辑 | 保留动态效果或按 PDF 时点静态渲染 |
| 讲者备注（data-note / data-speaker-notes） | 写入 PowerPoint notes | 浏览器备注面板按 HTML 实现 |

## 目录结构

```
slides/
├── SKILL.md                 # 本文件
├── CHANGELOG.md
├── DECISIONS.md
├── TASKS.md
├── .gitignore               # 本地配置与私有素材不入库
├── example.html             # 示例幻灯片（可直接转换测试）
├── assets/                  # 常规素材目录（头像/二维码/照片；图片默认 gitignored，README 说明规则）
├── config/
│   ├── profile.schema.json  # 本地配置字段与默认值
│   ├── profile.example.json # 可复制的空白配置
│   ├── *.local.json / *.local.md # 私有配置与偏好（gitignored，不入库不发布）
│   └── local/               # 旧版个人资料原件（恢复来源，gitignored）
├── references/
│   ├── configuration.md     # 本地配置：解析顺序、字段、初始化、迁移、发布边界
│   ├── pptx-guide.md        # PPTX/PDF 转换规则（五条铁律 + 元素支持矩阵）
│   ├── native-pptx-rebuild.md # 动态背景冻结 + 前景原生对象重建工作流
│   ├── layout-theme-playbook.md # 版式家族、主题字段、反泛化设计规则
│   ├── browser-guide.md     # 浏览器演示模式（视口适配 + 动画 + scroll-snap）
│   ├── style-reference.md   # 风格参考（AI 生成时引用）+ 设计哲学 + 反 AI-slop
│   ├── cn-deck-polish.md    # 中文课件去冗余与隐形坑
│   ├── templates/           # 完整 HTML 模板库（可直接 clone 替换内容）
│   │   ├── _base.css        # 共享设计系统（排版刻度、间距、组件、动画）
│   │   ├── README.md        # 模板索引 + 页面节奏建议
│   │   ├── 01-cover.html    # 封面页（dark）
│   │   ├── 02-content-list.html # 标题+要点列表（light）
│   │   ├── 03-data-grid.html    # 大数据/KPI 看板（dark）
│   │   ├── 04-quote.html        # 金句/引用页（dark）
│   │   ├── 05-timeline.html     # 横向时间线（light）
│   │   ├── 06-two-column.html   # 左右对比（light）
│   │   ├── 07-section-divider.html # 章节分隔（dark）
│   │   ├── 08-case-evidence.html   # 案例/证据卡片（light）
│   │   ├── 09-process-flow.html    # 流程步骤（light）
│   │   ├── 10-risk-matrix.html     # 风险矩阵（light）
│   │   ├── 11-training.html        # 培训讲义（light）
│   │   └── 12-image-text.html      # 图文混排（light）
│   ├── templates.md         # [旧版] 文字描述模板（保留兼容）
│   ├── styles/              # 风格库（38 个内置预设 + 使用者私有风格另存于配置目录）
│   │   ├── README.md
│   │   └── *.json           # 内置风格定义（JSON）
│   └── research/            # 主题研究模块
│       ├── research_framework.md     # 研究框架（六段式结构）
│       ├── research_report_template.md # 研究报告模板
│       └── slides_outline.schema.json # 分页大纲 JSON Schema
└── scripts/
    ├── html2pptx.js         # PPTX 转换核心引擎
    ├── html2pdf.js          # PDF 转换模块
    ├── extract-style.js     # 风格提取模块（保存到个人风格目录）
    ├── validate-slides.js   # HTML 转换前预检脚本
    ├── convert.js           # CLI 入口（读本地配置决定导出元数据）
    ├── load-profile.js      # 配置解析（生成/导出共用；也可作 CLI 查询）
    ├── init-profile.js      # 配置初始化（引导模式 + 非交互回填）
    ├── check-profile.js     # 配置校验
    └── package.json
```

## 已知限制（PPTX 模式）

1. **CSS 渐变** → 需预先光栅化为 PNG 图片
2. **文字元素不能有背景/边框** → 使用 `<div>` 包裹
3. **div 中的裸文本** → 必须用 `<p>` 等标签包裹
4. **内联元素 margin** → PowerPoint 不支持
5. **inset 阴影** → 会损坏 PPTX 文件
6. **远程/base64 图片** → PPTX 不稳定，统一改成本地图片
7. **页面溢出** → 浏览器能滚动但 PPTX 会裁切，必须预检修复
8. **动态背景不会变成 PowerPoint 动画** → `auto` / `freeze` 模式只冻结背景帧；前景对象保持原生可编辑

PDF 模式对 CSS 更宽容，推荐在不需要编辑时使用；但若要求文字可选中、可搜索，仍需避免正文区域叠加渐变、滤镜或大面积半透明层。

## 转换前验证脚本

`scripts/validate-slides.js` 使用 Playwright 本地渲染 HTML，检查常见转换风险：

- 是否存在 `.slide` / `section` 容器
- slide 尺寸是否接近固定视口
- body/slide/子元素是否溢出
- 是否使用渐变、`box-shadow: inset`、远程图片、base64 图片
- 是否有裸 `div` 文本
- 文本元素是否直接带背景或边框

首次安装与运行：

```bash
cd scripts
npm install
npx playwright install chromium
npm run validate -- ../example.html --strict
```

## 依赖

- Node.js >= 18
- Playwright（Chromium，首次运行 `npx playwright install chromium`）
- npm 依赖安装：`cd scripts && npm install`
- 预检脚本：`cd scripts && npm run validate -- ../example.html --strict`
- 系统字体（中文建议使用合法安装的 Microsoft YaHei、PingFang SC 或 Noto Sans CJK）
- 可选高清截图 PDF 路径另需 Google Chrome 与 ImageMagick 7（`magick`）；普通 PPTX/PDF 路径只需 Playwright Chromium。
