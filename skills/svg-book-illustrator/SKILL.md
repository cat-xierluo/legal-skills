---
name: svg-book-illustrator
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.8.9"
license: MIT
description: 书籍/文章 SVG 配图生成工具，专注于架构图、流程图、层次图等专业技术配图。当用户需要为书籍章节或正式文章生成配图、创建架构图/流程图/层次图，或提到"章节配图"、"书籍插图"、"架构图"、"流程图"时使用此技能。
---

# SVG Book Illustrator

为书籍章节和正式文章生成简洁专业的 SVG 技术配图。

> 本 Skill 生成**静态 SVG**，直接嵌入 Markdown 文件（`<svg>` 标签），风格为简洁专业、透明背景 + 按模板语义分类配色（v1.7.0：层级类 layer/tree/金字塔走 G1-G4 灰度梯度；多样性类 flow/matrix/hub/cycle 走 P1-P8 多色调色板），适合纸质出版。

## 快速开始

```
/svg-book-illustrator @path/to/chapter.md
```

## 核心工作流程

### 第一阶段：分析章节，规划插图

1. 读取章节 Markdown 文件
2. 如果 `references/diagram-catalog.md` 有当前章节的预定义插图，匹配之
3. 扫描章节内容，识别适合配图的位置：
   - 架构描述处（"X 层"、"体系"、"架构"等）
   - 流程描述处（"步骤"、"流程"、"阶段"等）
   - 对比描述处（"vs"、"对比"、"前后"等）
   - 层次描述处（"层级"、"分类"、"金字塔"等）
   - 循环描述处（"循环"、"迭代"、"闭环"等）
   - 生态/关系描述处（"生态"、"要素"、"关系"等）
   - 多维数值对比描述处（"维度"、"能力评估"、"理论 vs 实际"、"国内外对比"、"模型适配"等）→ radar
   - Skill 介绍/结构描述处（"Skill"、"SKILL.md"、"三件套"、"references/scripts"、"输入→输出"等）→ skill-card
   - 多角色/多主体时间推进描述处（"时间轴"、"多角色"、"推进"、"节点"、"诉讼时效"、"案件流程"等）→ timeline-lane
   - 两维交叉对照描述处（"风险×条款"、"特征矩阵"、"覆盖度"、"交叉对照"、"评估表"等）→ matrix-grid
   - 三分类/三版本对仗描述处（"三种"、"三类"、"三栏"、"三方案"、"三种打法"等）→ three-col
4. 在合适位置插入占位符 `[[FIG:N:简要描述]]`（N 从 1 开始编号）
5. 列出所有规划的插图（类型、位置、描述），除非用户明确要求先确认，否则继续生成 SVG

**插图密度**：每章「一节一张」为基准，数万字章节 6-8 张，宁精勿滥；纯 walkthrough / 总结节可省图避免冗余。密度指标：**图/节 ≥ 0.7、图/万字 ≥ 0.8**，低于判「偏少」并提示补图位置（详见第四阶段 + `references/review-checklist.md`）。

### 第二阶段：生成 SVG

完成插图规划后，逐张生成：

1. 根据插图描述选择布局模板（flow / layer / matrix / hub / tree / cycle / radar / skill-card / timeline-lane / matrix-grid / three-col，或组合模板）
2. 读取 `references/layout-templates.md` 获取模板规范
3. 按 `references/style-guide.md` 的设计规范生成 SVG 代码
4. 将 `<svg>` 标签嵌入 Markdown，替换对应占位符
5. 在 SVG 下方添加图注：`**图 N-X：图标题**`

### 第三阶段：归档

生成完成后，提取所有 SVG 到独立文件：

```bash
python scripts/extract_svgs.py path/to/chapter.md --output output/figures/
```

### 第四阶段：审查与验收（必须过四道门禁）

生成 + 嵌入后，逐章过审查门禁，详见 `references/review-checklist.md`：

**① 配图密度审查**：图/节 ≥ 0.7、图/万字 ≥ 0.8；低于判「偏少」，列出可补图的小节。跨章均衡——相邻章密度不宜骤变（认知/入门篇图密度不应远低于方法/实战篇）。

**② 图-正文论点一致性审查**：每张图回溯所在小节，核对节点数 / 层级名 / 流程方向 / 对比维度 与正文表述一致；替换 mermaid / ASCII 图时原信息（节点、关系、标注）不丢失；图注准确概括图内容，不夸大不遗漏。

**③ 字宽/坐标硬算自检（v1.8.5+，先于视觉目检）**：生成器产出后，按 **CJK≈Fpx/字、Latin≈0.55Fpx/字** 估算文字宽度 ≤ 容器宽，相邻元素 y 差 ≥ 20px，viewBox H 足够——**计算闸**，防视觉目检对"轻微溢出/贴近"漏检（v1.8.5 radar 图例重叠、three-col 子卡片溢出两例均靠此抓出）。详见 `review-checklist.md` §③。

**④ 视觉目检（多模态渲染后眼检）**：SVG 用受控字体渲染为 PNG（快速预览运行 `python3 scripts/render_svg.py input.svg output.png`；高 DPI 运行 `node scripts/svg2png.js input.svg output.png 300`）后，用多模态模型逐张查——文字不溢出容器、框不重叠（间距 ≥24px）、箭头落位方向正确、字号可读（节点≥16px 副≥12px）、黑白可辨、整体美观留白合理。发现问题回改 SVG 坐标，复检直到目检通过。

> **多模态生产提示**：若环境支持图像理解，④ 必须真正"看"渲染图，不能只靠 xmllint / rsvg 无警告间接验证——语法通过 ≠ 布局美观，溢出/重叠/箭头错位只有肉眼（或多模态模型）能发现。但视觉目检对"轻微溢出/贴近"易判 OK，故须先过 ③ 字宽硬算自检。

**生产器契约回归（v1.8.9+）**：修改 `scripts/gen-*.py` 或 `references/layout-templates.md` 后，必须运行：

```bash
python3 -m unittest discover -s scripts/tests -p 'test_*.py' -v
```

只有退出码为 0 才能进入合并候选。该测试实际执行全部生成器，并检查模板文档中的全部 SVG 代码块；viewBox 必须严格为 `0 0 720 H`，根 `width` 必须为 720、`height` 必须等于 H；XML、`<style>`、元素 `style=`、任一元素的 `font-family`、class/CSS 变量和背景矩形任一不合规都会失败。

仓库内 `.github/workflows/svg-book-producer-contract.yml` 会在本 Skill 或工作流自身发生 PR 改动，以及相关改动推入 `main` 时自动运行同一命令。没有明确通过的 `Source producer contract` check，不应把生产器改动视为可合并。该 CI **只证明源 SVG 生产契约**，不替代受控字体渲染、像素等价验证或多模态视觉目检。

**受控字体渲染（v1.8.9+）**：源 SVG 为保证 Markdown/Obsidian 兼容，不嵌 `<style>` 或字体栈；导出工具统一读取单一权威源 `assets/render-fonts.css`：

```bash
# 快速预览（librsvg；固定外部 CSS + 宽 720，不指定高度）
python3 scripts/render_svg.py input.svg output.png

# 高 DPI（Puppeteer/Chrome；注入同一外部 CSS）
node scripts/svg2png.js input.svg output.png 300

# 修改字体接线或 SVG 生成器后：与旧内嵌字体基线逐像素比对
python3 scripts/verify_render_font_equivalence.py
```

禁止用裸 `rsvg-convert` 结果作为验收证据：它会按环境默认字体渲染，已实测产生 serif 退化和像素漂移。浏览器预览可继承宿主字体，但正式导出/验收必须走上述受控入口。像素等价脚本是本地渲染回归证据，需要机器已有 `rsvg-convert` 与 ImageMagick；它不属于只校验源码契约的 GitHub Actions check，也不替代逐图视觉目检。

---

## 布局模板

13 种布局模板（11 种基础 + 2 种组合），详见 `references/layout-templates.md`。

| 模板 | 适用场景 | 典型元素数 |
|------|---------|-----------|
| **flow** | 流程图、步骤图、管道图 | 3-5 个节点（水平≤4） |
| **layer** | 层次架构、分层堆叠 | 3-4 层 |
| **matrix** | 前后对比、并排比较 | 2 列 |
| **hub** | 中心辐射、生态关系 | 1 核心 + 4-8 外围 |
| **tree** | 层级结构、组织图、金字塔 | 3 层 |
| **cycle** | 循环流程、迭代闭环 | 4-6 个节点 |
| **radar**（v1.8.0） | 多维度数值对比（理论 vs 实际 / 能力评估 / 国内外 / 模型适配） | 6-12 维，1-2 系列 |
| **skill-card**（v1.8.1） | 单个 Skill 的结构（输入→Skill 三件套+流程→输出） | 1 Skill + 3-5 步 |
| **timeline-lane**（v1.8.2） | 多角色/多主体时间推进（诉讼多角色时间线/案件流程节点） | 3-5 泳道，每道 2-5 事件 |
| **matrix-grid**（v1.8.3） | 两维交叉对照（风险×条款 / 特征×产品 / 能力×模型） | N×M 网格（3-6 × 3-7） |
| **three-col**（v1.8.4） | 三分类/三版本对仗并列（每栏带子卡片） | 3 栏 × 3-4 子卡片 |
| **flow+matrix** | 递进流程附带阶段对比 | 3-4 阶段 + 对比区 |
| **flow+hub** | 编排流程中节点展开 | 主流程 + 展开节点 |

---

## 设计规范

详见 `references/style-guide.md`。核心要点：

- **画布**：**宽 720px 固定（16开 115mm 通栏物理尺寸），高度按内容裁剪**（v1.7.1）——viewBox="0 0 720 H"，H = 内容底边最大 y + 40px；**不再固定 400**（固定 400 会让内容少的图底部留白过大、SVG 下边缘离图注间距忽大忽小）。**透明背景（硬约束）**——不画背景矩形、不设底色；左右 + 顶部安全边距 40px，底部 = H − 内容底（即 40px）。底色由书页/排版提供。
- **风格**：简洁、专业、静态（无动画、无渐变、无滤镜、无 emoji）
- **颜色（v1.5.0 透明背景 + 内部模块多色版）**：新生成图**透明底**，配色用于 **SVG 内部不同模块 / 分支 / 方向 / 层级之间的多色柔和区分**——颜色尽量多样（一图 4-6 种甚至更多柔和模块色）。从 8 组预定义调色板（P1 雾蓝系 / P2 浅青系 / P3 嫩绿系 / P4 暖米系 / P5 浅紫系 / P6 浅粉系 / P7 暖灰系 / P8 混合柔和系）选 1 组，组内 5-6 个柔和模块色按"模块 1 取色 1、模块 2 取色 2…"依次分配，相邻模块不同色。文字色统一深灰 `#2D3436`/`#636E72` 保证可读。打印友好约束（文字 vs 所在模块填充色对比 ≥4.5:1 WCAG AA、相邻模块区分度 ≥10%、模块色明度 L*≥80、禁高饱和荧光、CMYK 不偏色、灰度差≥10%）。**仅新生成图用新配色，main 上既有 34 张白底单色 SVG 保持稳定不回改**。
- **颜色语法硬约束**：颜色只用 `fill`/`stroke` 属性内联——**禁 `<style>` 块定义颜色、禁 `<svg>` 开标签写 font-family、禁 CSS 变量/class、禁画背景矩形**（已验证的 Obsidian 渲染 + 透明背景硬约束，详见 style-guide.md §5.4）。
- **可视友好化配色与渲染禁忌（v1.8.7 硬约束，详见 style-guide.md §5.5）**：① **深底浅字**——深色填充（L* ≤ 50，如 `#2C5282`/`#1A202C`/G4 深档/项目 canonical 强调色）的模块内 `<text>` 必须用 `#FFFFFF`/`#EDF2F7`，**禁深底深字**；② **字色对比度**——文字 fill 与所在模块 fill 对比 ≥ 4.5:1（AA，大文本 ≥ 3:1）；③ **箭头落点**——marker 单 `id="arrow"` + `markerUnits=userSpaceOnUse` + `orient=auto`，落点 `x2 = 目标框边 − 4px`、方向指向目标节点；④ **文字完整性**——每个有标题语义的节点框都有非空 `<text>`、文字坐标在框内、fill 与模块不同色。源 T134 review 实测：图 7-6 箭头错位 / 图 11-8 字色不可辨 / 图 11-9 深蓝底深字 / 图 7-13/8-3/6-7 框内文字缺失。
- **蓝色焦点 + 文字二档（v1.8.8 通用规则，DEC-020，详见 style-guide.md §5.0/§5.1）**：① **文字色统一深灰二档**——图内所有文字仅允许 `#2D3436`（主）/`#636E72`（次），深底走 `#FFFFFF`/`#EDF2F7`；**不再用 `#1A202C`/`#4A5568`**（收敛二档消除四档混用）。② **项目 canonical 主色（如 `#2C5282`/`#1A365D` 蓝）只用于焦点节点填充/描边，禁作文字 fill**——以色块承载强调，文字强调改用字重/字号；这是通用纪律，非项目指针（任何项目锁定主色为视觉标识时都适用）。③ **每张结构/流程图 ≥1 焦点节点**——layer/tree/flow/hub/cycle/matrix 应至少有 1 个焦点节点（canonical 主色或更深一档填充/描边）承载层次，反对纯灰平铺；纯并列清单无自然焦点时用灰阶递进 + 边框粗细区分。源法律 AI Skill 实战 DEC-114 方案 A 定调（图 1-6 灰阶 + 唯一蓝色焦点 = 层次标杆、零蓝字）。
- **文字**：继承渲染环境默认无衬线字体（PingFang SC / Microsoft YaHei 落在系统层），节点标签 18px 起（16开 115mm 通栏下物理 2.88mm = 8.2pt）
- **形状**：圆角矩形（rx="6"）、简洁箭头、最小 24px 间距
- **印刷**：黑白可辨，颜色不是唯一区分手段（黑白降级仍可辨是硬约束）

---

## 插图目录

`references/diagram-catalog.md` 定义插图目录格式和创建方法。

---

## PNG 导出

出版社通常需要位图版本。`scripts/svg2png.js` 会读取 `assets/render-fonts.css`，将 SVG 转为高分辨率 PNG：

```bash
# 单张转换（默认 600 DPI）
node scripts/svg2png.js input.svg

# 指定输出文件和 DPI
node scripts/svg2png.js input.svg output.png 300

# 批量转换目录下所有 SVG
find figures/ -name "*.svg" -exec node scripts/svg2png.js {} \;
```

**依赖**：快速预览 wrapper 需要系统已有 `rsvg-convert`；高 DPI 导出需要 Puppeteer 和 Chrome/Chromium。缺失时脚本会明确报错，不会自动安装。首次使用高 DPI 功能前由用户自行运行：`npm install puppeteer`

**印刷 DPI 建议**：
- 300 DPI：最低印刷要求
- 600 DPI：推荐，清晰锐利
- 1200 DPI：线条图最高质量

---

## 成功标准

- 每张图只表达 1-2 个核心概念
- 架构图层次清晰，流程图逻辑通顺
- 风格简洁专业，无装饰性元素
- SVG 在 Markdown 预览中正确渲染（源契约：开标签严格为 viewBox="0 0 720 H"、width="720"、height="H"；无嵌入 font-family、无 `<style>`/`style=`、颜色只用 `fill`/`stroke` 属性内联、**无背景矩形**、xmllint well-formed；受控 wrapper 渲染无警告）
- 图注格式统一：**图 N-X：标题**
- **配图密度达标**：图/节 ≥ 0.7、图/万字 ≥ 0.8
- **图-正文一致**：节点/层级/方向/维度与正文论点吻合，替换 mermaid/ASCII 图信息无损
- **视觉目检通过**：渲染后无溢出/重叠/箭头错位，字号可读、黑白可辨、美观
- 印刷友好：16开 115mm 通栏下文字 ≥8pt 清晰可读，黑白打印可辨，文字对比度 ≥4.5:1（WCAG AA），CMYK 转换不偏色
- 配色合规（v1.5.0）：新生成图**透明背景**（无画布底色矩形）；从调色板 8 组选 1 组，组内模块色用于内部模块多色柔和区分（一图 4-6 色）、相邻模块不同色；文字色统一深灰；颜色只用 `fill`/`stroke` 属性内联；既有 34 张白底单色图保持稳定不回改
- 可视友好化（v1.8.7）：深底（L* ≤ 50）模块内文字走浅色 `#FFFFFF`/`#EDF2F7`（禁深底深字）；文字 vs 所在模块对比 ≥ 4.5:1；箭头落点 `x2 = 目标框边 − 4px`、方向指向目标；每个有标题语义的节点框都有非空 `<text>`、坐标在框内、fill 与模块不同色（详见 style-guide §5.5）
- 蓝色焦点 + 文字二档（v1.8.8）：文字色仅 `#2D3436`/`#636E72`（+ 深底浅字 `#FFFFFF`/`#EDF2F7`），不再用 `#1A202C`/`#4A5568`；项目 canonical 主色只焦点节点填充/描边、禁作文字 fill；每结构/流程图 ≥1 焦点节点（详见 style-guide §5.0/§5.1）

> 源生产契约与受控渲染只是**必要不充分**条件——保证 SVG 可解析、画布与样式受控，不保证图正确美观。密度 + 一致性 + 目检三道审查才是验收依据（`references/review-checklist.md`）。
