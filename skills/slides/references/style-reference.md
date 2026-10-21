# HTML 幻灯片风格参考

面向 AI 生成 HTML 幻灯片时的风格速查手册。选择一个风格后，使用对应的 CSS 变量和设计参数生成 HTML。

---

## 0. 设计哲学

在编写代码之前，先确定一个**大胆的美学方向**：

- **Purpose**: 这个幻灯片解决什么问题？谁在看？
- **Tone**: 选择一个明确的风格方向：极简克制 / 极繁华丽 / 复古未来 / 有机自然 / 奢华精致 / 杂志编辑 / 科技赛博
- **Differentiation**: 什么让观众记住这个演示？一个令人难忘的视觉记忆点是什么？

**关键原则**: 选择一个清晰的概念方向，精准执行。大胆的极繁和精致的极简都可行——关键是意图明确，而非强度高低。

### 空间构图

打破常规布局，创造视觉张力：

- **非对称布局** — 不要总是居中对齐
- **重叠元素** — 卡片、图片可以部分重叠
- **对角线流动** — 引导视线从左上到右下
- **打破网格** — 偶尔让元素突破边界
- **大胆留白** 或 **控制密度** — 两者都可行，但要有意为之

### 背景与氛围

不要默认使用纯色背景。添加深度和氛围：

```css
/* 纯色光晕（PDF 安全，推荐） */
.glow {
  background: rgba(217,119,6,0.04);
}
```

装饰元素：模糊光斑（`blur-3xl` + 低透明度）、渐变边框、微妙的阴影层次。

> **PDF 兼容警告**：避免使用 `radial-gradient` / `linear-gradient`。CSS 渐变会导致 Chromium 在 PDF 中光栅化文字，失去矢量文字层。装饰性光晕用纯色 `rgba()` 替代渐变。如果必须使用渐变装饰，请放到 `.glow` class 中，转换脚本会在 PDF 生成时自动隐藏。详见 `pptx-guide.md` 的"PDF 文字光栅化陷阱"章节。

---

## 1. 风格速查表

| 风格 | 关键词 | 适用场景 | 主色 |
|------|--------|---------|------|
| 法律黑金 | 专业、克制、深色 | 法律讲座、培训课件、专业演示 | `#18181B` + `#D97706` |
| 商务权威 | 正式、经典、商务 | 年度报告、财务分析、政府公文 | `#2B2D42` + `#EF233C` |
| 科技暗夜 | 深邃、科技、发光 | 科技发布、AI产品、夜间主题 | `#000814` + `#FFC300` |
| 铂金白金 | 高端、极简、精致 | 金融科技、企业官网、奢侈品牌 | `#FFFFFF` + `#0070F3` + `#D4AF37` |
| 教育图表 | 清晰、数据、逻辑 | 统计报告、市场分析、教育 | `#264653` + `#2A9D8F` |
| 活力科技 | 动感、运动、年轻 | 体育赛事、创业路演、青年教育 | `#023047` + `#FFB703` |
| 学术复古 | 经典、学术、历史 | 学术讲座、历史回顾、博物馆 | `#780000` + `#003049` |
| 自然森系 | 大地、环保、清新 | ESG报告、环保主题、生活方式 | `#344E41` + `#A3B18A` |

---

## 2. 各风格 CSS 变量定义

### 法律黑金

适合法律行业课件、专业培训演示。深色背景配金色强调，极简克制。

```css
:root {
  --primary: #18181B;
  --accent: #D97706;
  --accent-light: #F59E0B;
  --bg-light: #FAFAF8;
  --bg-white: #FFFFFF;
  --text-primary: #18181B;
  --text-light: #FFFFFF;
  --text-muted: #52525B;
}
```

**字号参考**: 标题 49.7/32.5/34.5px, 正文 18/16.9px, 标签 12.7px
**边距**: 左 62px, 上 39px, 内容宽 876px

### 商务权威

适合年度报告、财务分析、政府公文。深蓝主色配红色强调。

```css
:root {
  --primary: #2B2D42;
  --accent: #EF233C;
  --accent-dark: #D90429;
  --bg-light: #EDF2F4;
  --bg-white: #FFFFFF;
  --text-muted: #8D99AE;
  --text-light: #FFFFFF;
}
```

**圆角**: 0.1"（Soft & Balanced）

### 科技暗夜

适合科技发布会、AI 产品。深色背景配金色高光。

```css
:root {
  --bg-primary: #000814;
  --bg-secondary: #001D3D;
  --bg-tertiary: #003566;
  --accent-gold: #FFC300;
  --accent-gold-light: #FFD60A;
  --text-light: #FFFFFF;
}
```

**圆角**: 0.05"（Sharp & Compact）

### 铂金白金

适合金融科技、企业官网。白色基底配蓝金双强调色。

```css
:root {
  --bg-primary: #FFFFFF;
  --bg-secondary: #FAFAFA;
  --bg-tertiary: #F5F5F5;
  --accent-blue: #0070F3;
  --accent-gold: #D4AF37;
  --text-primary: #0A0A0A;
  --text-muted: #525252;
}
```

**圆角**: 0.1"（Soft & Balanced）

### 教育图表

适合统计报告、数据分析。天然适合图表配色。

```css
:root {
  --chart-1: #264653;
  --chart-2: #2A9D8F;
  --chart-3: #E9C46A;
  --chart-4: #F4A261;
  --chart-5: #E76F51;
  --bg-white: #FFFFFF;
  --bg-light: #F8F9FA;
}
```

**圆角**: 0.05"（Sharp & Compact）

### 活力科技

适合创业路演、体育赛事。深蓝底配橙色高亮。

```css
:root {
  --primary: #023047;
  --accent-orange: #FFB703;
  --accent-cyan: #219EBC;
  --accent-light: #8ECAE6;
  --text-light: #FFFFFF;
}
```

### 学术复古

适合学术讲座、历史主题。深红配深蓝的经典对比。

```css
:root {
  --primary-red: #780000;
  --accent-red: #C1121F;
  --bg-cream: #FDF0D5;
  --primary-blue: #003049;
  --accent-blue: #669BBC;
}
```

### 自然森系

适合 ESG 报告、环保主题。绿色单色系，安全协调。

```css
:root {
  --forest-dark: #344E41;
  --forest-mid: #3A5A40;
  --forest-main: #588157;
  --forest-light: #A3B18A;
  --forest-pale: #DAD7CD;
  --bg-warm: #FEFAE0;
}
```

---

## 3. 完整配色方案速查

来源：design-system 18 个配色方案，按场景分类。

### 商务/政务

| 名称 | 主色 | 辅色 | 强调色 | 背景 |
|------|------|------|--------|------|
| 商务权威 | `#2B2D42` | `#8D99AE` | `#EF233C` | `#EDF2F4` |
| 奢华神秘 | `#22223B` | `#4A4E69` | `#9A8C98` | `#F2E9E4` |
| 铂金白金 | `#0A0A0A` | `#0070F3` | `#D4AF37` | `#F5F5F5` |

### 科技/互联网

| 名称 | 主色 | 辅色 | 强调色 | 背景 |
|------|------|------|--------|------|
| 科技暗夜 | `#000814` | `#001D3D` | `#FFC300` | `#003566` |
| 纯净科技蓝 | `#03045E` | `#0077B6` | `#00B4D8` | `#CAF0F8` |
| 活力科技 | `#023047` | `#219EBC` | `#FFB703` | `#8ECAE6` |

### 教育/学术

| 名称 | 主色 | 辅色 | 强调色 | 背景 |
|------|------|------|--------|------|
| 教育图表 | `#264653` | `#2A9D8F` | `#E9C46A` | `#F4A261` |
| 学术复古 | `#780000` | `#003049` | `#C1121F` | `#FDF0D5` |
| 自然森系 | `#344E41` | `#3A5A40` | `#588157` | `#FEFAE0` |

### 创意/生活

| 名称 | 主色 | 辅色 | 强调色 | 背景 |
|------|------|------|--------|------|
| 现代养生 | `#006D77` | `#83C5BE` | `#E29578` | `#EDF6F9` |
| 柔和创意 | `#CDB4DB` | `#FFC8DD` | `#BDE0FE` | `#FFAFCC` |
| 波西米亚 | `#CCD5AE` | `#E9EDC9` | `#D4A373` | `#FEFAE0` |
| 工匠手作 | `#7F5539` | `#656D4A` | `#A68A64` | `#EDE0D4` |
| 艺术美食 | `#335C67` | `#9E2A2B` | `#E09F3E` | `#FFF3B0` |
| 海滨珊瑚 | `#0081A7` | `#00AFB9` | `#F07167` | `#FDFCDC` |
| 明亮橙薄荷 | `#FF9F1C` | `#2EC4B6` | `#FFBF69` | `#CBF3F0` |
| 优雅时尚 | `#4A5759` | `#EDAFB8` | `#B0C4B1` | `#DED7D2` |

---

## 4. 字体搭配推荐

### 中文场景

| 场景 | 中文字体 | 英文标题字体 | 英文字体 |
|------|---------|------------|---------|
| 专业/法律 | Microsoft YaHei | — | — |
| 科技 | PingFang SC | Sora | Source Sans 3 |
| 学术 | Noto Sans SC | Georgia | Calibri |
| 创意 | PingFang SC | DM Sans | Nunito Sans |
| 极简 | Microsoft YaHei | Manrope | Work Sans |

### 字号体系

```css
/* 推荐字号梯度 */
--title-xl: 49px;    /* 封面主标题 */
--title-lg: 36px;    /* 章节标题 */
--title-md: 28px;    /* 小节标题 */
--title-sm: 24px;    /* 卡片标题 */
--body-lg: 18px;     /* 重点正文 */
--body-md: 16px;     /* 正文 */
--body-sm: 14px;     /* 辅助文字 */
--caption: 12px;     /* 标签/注脚 */
--micro: 10px;       /* 页码等 */
```

### 禁止使用

- Inter, Roboto — AI 生成典型标志
- Arial, Helvetica — 过于通用
- Times New Roman — 不适合屏幕
- Comic Sans — 除非有意为之

---

## 5. 布局参考

### 绝对定位布局（推荐用于精确还原）

```css
.slide {
  position: relative;
  width: 1000px;
  height: 562.5px;
  overflow: hidden;
}
/* 每个元素使用 position: absolute + left/top 精确定位 */
```

**边距参考**: 左 60px, 上 40px, 内容宽 880px

### Flexbox 布局（推荐用于响应式）

```css
.slide {
  display: flex;
  flex-direction: column;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  padding: clamp(1rem, 4vw, 4rem);
}
```

---

## 6. 设计规则

### 必须遵守

1. **只用提供的配色方案中的颜色**，不要随意创造新颜色
2. **标题粗体，正文不加粗**（bold = 700, normal = 400）
3. **每个 slide 不超出视口**（无滚动，内容溢出时拆分多页）
4. **使用 CSS 变量**统一管理颜色和字号

### 不要使用

1. CSS 渐变（PPTX 不支持）
2. 紫色渐变 + 白色背景（AI slop 典型标志）
3. Inter/Roboto 字体
4. 千篇一律的居中卡片网格
5. 过于饱和的霓虹色

### 风格食谱（圆角 + 间距）

| 风格 | 小圆角 | 中圆角 | 大圆角 | 内边距 | 间距 | 适用 |
|------|--------|--------|--------|--------|------|------|
| 锐利紧凑 | 0" | 0.03" | 0.05" | 0.1-0.15" | 0.1-0.2" | 数据密集、专业报告 |
| 柔和平衡 | 0.05" | 0.08" | 0.12" | 0.15-0.2" | 0.15-0.25" | 商务通用 |
| 圆润宽松 | 0.1" | 0.15" | 0.25" | 0.2-0.3" | 0.25-0.4" | 产品介绍、营销 |
| 药丸通透 | 0.2" | 0.3" | 0.5" | 0.25-0.4" | 0.3-0.5" | 品牌展示、发布会 |

### Anti-AI-Slop 检查清单

每个 Slide 生成后必须检查：

- [ ] 没有使用 Inter / Roboto / Arial 字体
- [ ] 没有紫色渐变 + 白底的组合
- [ ] 配色有明确的主导色，不是均匀分布
- [ ] 布局有变化，不是千篇一律的卡片网格
- [ ] 有至少一个视觉记忆点
- [ ] 背景有氛围感，不是纯色

**记住**: 每个设计都应该不同。在浅色/深色主题、不同字体、不同美学之间变化。**永远不要**在多次生成中收敛到相同的选择。

---

## 7. 12 个前端演示风格预设

以下是面向浏览器直接演示的前端风格预设，每个预设来自真实设计参考。**仅使用抽象形状——不使用插画**。

### 暗色主题

| # | 风格 | 关键词 | 字体搭配 | 主色 |
| --- | ------ | -------- | ---------- | ------ |
| 1 | Bold Signal | 自信、大胆、高冲击 | Archivo Black + Space Grotesk | `#1a1a1a` + `#FF5722` |
| 2 | Electric Studio | 干净、专业、高对比 | Manrope 800 + Manrope 400 | `#0a0a0a` + `#4361ee` |
| 3 | Creative Voltage | 创意、能量、复古现代 | Syne + Space Mono | `#0066ff` + `#d4ff00` |
| 4 | Dark Botanical | 优雅、精致、艺术感 | Cormorant + IBM Plex Sans | `#0f0f0f` + `#d4a574` |

### 浅色主题

| # | 风格 | 关键词 | 字体搭配 | 主色 |
| --- | ------ | -------- | ---------- | ------ |
| 5 | Notebook Tabs | 编辑风、触感、优雅 | Bodoni Moda + DM Sans | `#2d2d2d` + `#f8f6f1` |
| 6 | Pastel Geometry | 友好、有序、现代 | Plus Jakarta Sans | `#c8d9e6` + `#faf9f7` |
| 7 | Split Pastel | 活泼、创意 | Outfit | `#f5e6dc` + `#e4dff0` |
| 8 | Vintage Editorial | 个性、编辑风 | Fraunces + Work Sans | `#f5f3ee` + `#1a1a1a` |

### 特殊主题

| # | 风格 | 关键词 | 字体搭配 | 主色 |
| --- | ------ | -------- | ---------- | ------ |
| 9 | Neon Cyber | 未来感、科技 | Clash Display + Satoshi | `#0a0f1c` + `#00ffcc` |
| 10 | Terminal Green | 开发者、黑客美学 | JetBrains Mono | `#0d1117` + `#39d353` |
| 11 | Swiss Modern | 精确、包豪斯 | Archivo + Nunito | 白 + 黑 + `#ff3300` |
| 12 | Paper & Ink | 编辑、文学 | Cormorant Garamond + Source Serif 4 | `#faf9f7` + `#1a1a1a` |

各风格的 CSS 变量定义和签名元素详见 `references/styles/raw/STYLE_PRESETS.md`。
