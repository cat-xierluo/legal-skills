# 手绘对象卡片风格架构

来源说明：本风格架构最初参考了公开博客页面中的低密度对象卡片、暖米白纸底、近黑手绘形体和单色重点色用法；后续根据公众号长文配图测试、用户反馈和本技能沉淀的构图家族重写为中性的“手绘对象卡片”体系。本文只提炼通用结构语言，不要求复制或复用任何品牌官网资产。

## 1. 页面级架构

目标视觉不是单张插画风格，而是一整套内容架构：

- 页面背景：暖米白，主值由主题包 `paper_background` 决定（blue-gray 默认主题接近 `#FAF9F5`）。
- 内容卡片：大量留白，文字和图像明确分区。
- 插画容器：文章卡片和文章 hero 都使用方形物件插画；图像不铺满整个画面，而是作为一个中心对象。
- 文章正文：图像插入在正文段落之间，常用于解释某个产物、流程或界面状态。
- 关联文章卡片：背景是柔和块面，前景是近黑手绘对象；同一张图只使用一种彩色重点色。
- 公开 SVG 里的近黑形体大量使用 `fill` 为近黑色的不规则路径（本 Skill 的墨线色由主题包 `ink_color` 决定，blue-gray 主题接近 `#141413`），而不是统一宽度的 `stroke` 线条；这会带来粗细不均的墨块感。

对公众号配图的启发：

- 首图用“对象卡片 + 宽画布裁切安全区”，而不是海报式大字标题；公众号场景下主体要足够大，避免在正文里显得像小图标。
- 正文图用“一个段落一个隐喻”，而不是把整段内容塞进复杂信息图；主体占比优先保证可读性。
- 一篇文章内多张图应共享线条、留白和配色节奏。

## 2. 色彩系统

> **本 Skill 的色彩已解耦为主题包机制**：色值（重点色、纸面色、墨线色）不再硬编码在文档里，而是由 `themes/<active_theme>/theme.json` 提供，由 `config/style.json` 的 `active_theme` 字段决定激活哪个主题。下面的 Gray/Clay/Mineral 等表格只是**原始公开页面沉淀的色板参考**（用于理解风格来源），实际出图务必用当前主题包的色值。切换或新建主题见 SKILL.md「主题包」章节和 `themes/README.md`。

原始公开页面与后续测试中沉淀的关键色（仅作风格溯源参考，非本 Skill 的强制色值）：

| Token | 色值 | 用法 |
|------|------|------|
| Gray 050 | `#FAF9F5` | 页面和画布主底色（blue-gray 主题的 `paper_background`） |
| Gray 100 | `#F5F4ED` | 轻微分层背景（blue-gray 主题的 `paper_surface`） |
| Gray 150 | `#F0EEE6` | 卡片或次级背景 |
| Gray 250 | `#DEDCD1` | 图形浅灰填充 |
| Gray 750 | `#30302E` | 次级文字/深灰 |
| Gray 950 | `#141413` | 主文字与插画线条（blue-gray 主题的 `ink_color`） |
| Clay | `#D97757` | 原始品牌强调色（本 Skill 不使用，仅溯源） |
| Clay interactive | `#C96442` | 更深的强调色（仅溯源） |
| Peach | `#EBC9B7` | 柔和暖背景（仅溯源） |
| Mineral | `#629987` | 绿色背景/强调（仅溯源） |
| Cactus | `#BCD1CA` | 浅绿背景（仅溯源） |
| Sky | `#6A9BCC` | 蓝色背景/强调（仅溯源） |
| Heather | `#CBCADB` | 紫灰背景（仅溯源） |
| Olive | `#788C5D` | 橄榄绿背景（仅溯源） |

色彩观察：

1. 主画布优先用 Gray 050 / Gray 100 这类暖白（由主题包的 `paper_background` 决定）。
2. 同一张图只选一个彩色 token，作为大色块或少量强调。
3. 不使用霓虹色、高饱和渐变或金属质感。

本 Skill 的落地规则：

1. 重点色不轮换多色，固定由当前主题包的 `accent_color` 决定（blue-gray 默认主题是 `#435C68`）。
2. `paper` 模式：暖米白底（主题包 `paper_background`），重点色只做局部点缀。
3. `inverted` 模式：主题包重点色作为整张图背景，主体用暖米白块面，线条用主题包墨线色。**`inverted` 用的是当前主题的重点色，不一定是蓝灰**。
4. 同一篇文章通过 `paper` / `inverted` 节奏变化形成层次，不变成多色彩虹。

## 3. 线条与形态

目标手绘对象卡片的物件有明显特征：

- 主墨色由主题包 `ink_color` 决定（blue-gray 默认主题接近 `#141413`），常是填充出来的黑色形体，不是单纯描边。
- 很多轮廓由不规则路径形成，边缘有手绘/手切的微小起伏；这种起伏更像手工描摹的自然收放，不是算法噪声。
- 同一条轮廓有粗细变化，转角偏钝，局部有轻微鼓包感；但整体轮廓仍然稳定、干净、可识别，不是随机抖动的草稿线。
- 粗细不均不是“整圈边缘随机起伏”。更接近目标构图的做法是：先有稳定外形，再在起笔、收笔、转角、端点、重叠、接缝等结构锚点出现少量笔压变化，长边只保留自然收放。
- 线条不应像机械矢量图标。允许轻微不平行、端点收笔、转角压痕和内部细线的手工放置感。
- 物体往往由大块面和少量内部线条组成。
- 线条服务识别，不做细密纹理。
- 图形有“图标”和“插画”之间的尺度：比 icon 更丰富，比场景插画更克制。

提示词中应写：

```text
near-black hand-inked filled contour paths, stable readable silhouettes, single-pass confident hand tracing, subtle imperfect parallel edges, gently tapered stroke starts and ends, small pressure flattening at corners/overlaps/joints/terminal caps, long edges calm with organic tapering, flat fills, low-detail symbolic object
```

不要写：

```text
smooth uniform rounded stroke, thin monoline icon, mechanical vector icon outline, perfect vector geometry, CAD-straight geometry, ruler-straight edges, perfectly parallel sides, algorithmic uniform bezier curves, random ink blobs, lumpy contour noise, edge noise on every side, jittery random wobble, chaotic deformation, scribbly sketch lines, hyper realistic, cinematic, complex background, highly detailed texture, glossy 3D render
```

## 4. 构图模式

### A. Hero / 首图

- 宽画布，主体放中心安全区。
- 主物件占画面宽度约 60-72%，高度约 55-68%，保留适度留白但不要过空。
- 上下留足裁切空间，适配 `2400x1024`。
- 不在图片里放文章标题，避免生成乱码。

### B. Card / 方形卡片

- 1:1 方形。
- 背景使用 `paper` 或 `inverted` 模式；不要混入其他重点色。
- 中心对象清晰，适合文章列表或朋友圈分享。

### C. Inline / 正文横图

- 16:9。
- 一个主物件 + 1-2 个贴近主体的辅助符号。
- 主物件占画面宽度或视觉重量约 55-68%，避免小图标漂在大留白里。
- 用隐喻解释段落，而不是做长表格或流程图。

## 5. 适合法律公众号的隐喻翻译

| 文章内容 | 手绘对象卡片表达 |
|----------|-------------------|
| 合同审查 | 放大镜 + 合同块 + 少量标记点 |
| 证据链 | 节点轨道 + 证据盒 |
| 风险分级 | 雷达/仪表盘 + 3 个指示点 |
| 公司治理 | 中心节点 + 空白关系卡片 |
| 合规流程 | 闸门/桥 + 通过/拦截的抽象方块 |
| 争议解决 | 两侧模块 + 中间桥或聚焦框 |
| 操作指南 | 浏览器窗口 + 指针/轨道节点 |

## 6. 禁止项

- 不复制任何品牌官网的具体 SVG 路径、Logo、字标、图案组合。
- 不生成可读文字；文档和代码只能用短线、块面、圆点表示。
- 不生成真实 UI 截图，除非用户明确要求截图风格。
- 不生成照片、3D、强阴影、强渐变和复杂背景。
- 不把法律文章画成法槌、天平、法院大楼的俗套组合，除非用户明确要求。

## 7. 自检标准

合格的图应满足：

- 远看 1 秒能知道大概隐喻。
- 近看没有多余文字和复杂细节。
- 放进公众号正文时不喧宾夺主。
- 多张图放在一篇文章内能看出同一套视觉语言。
