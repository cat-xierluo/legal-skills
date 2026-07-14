# 布局模板定义

6 种基础布局 + 2 种组合模板。基于 **16开（115mm 通栏）** 物理尺寸推算。

> 所有字号已按印刷可读性校准：节点标签 18px（物理 2.88mm = 8.2pt）。
> 详见 style-guide.md 的物理尺寸推算。
>
> **viewBox 高度裁剪（v1.7.1）**：以下骨架示例里的 `viewBox="0 0 720 400"` 只是**坐标参考系**（便于推算节点位置），**实际生成时 viewBox 高度 H = 内容底边最大 y + 40px**，不固定 400——避免内容少的图底部留白过大、SVG 下边缘离图注间距忽大忽小（详见 style-guide.md §一）。例：layer 3 层内容底 y=330 → `viewBox="0 0 720 370"`；flow 水平 4 节点内容底 y=224 → `viewBox="0 0 720 264"`；tree 2 层内容底 y=308 → `viewBox="0 0 720 348"`。骨架内坐标（节点 x/y）不变，只裁掉底部多余画布。

> **配色说明（v1.7.0 条件化拆分）**：以下骨架示例是**透明背景**——**不画任何背景矩形**，直接画模块。
> - **layer / tree / 金字塔**模板：**同色相灰度梯度**——从顶层到底层用同一色组的 5 档明度渐深，营造层次下沉感。示例用 **G2 法律米梯度**（`#F4ECDC / #E8D8C0 / #D8C4A4 / #C4AE88 / #B8A282`）——本 skill 主推的法律书暖色梯度。
> - **flow / matrix / hub / cycle**模板：从 **P1-P8 调色板**选 1 组组内不同模块色（相邻不同色、一图 4-6 色柔和区分）。
> 文字色统一深灰 `#2D3436`/`#636E72`。详见 style-guide.md §5.0 总则 + §5.2 / §5.2b。
>
> **字体说明**：骨架中**不再出现** `<style>text { font-family... }</style>` 块——字体由渲染环境继承默认无衬线。这是已验证的 Obsidian 渲染硬约束（memory `feedback_svg_embed_syntax`）。若个别环境需强制字体，在每个 `<text>` 上单独写 `font-family`，绝不在 `<svg>` 开标签或 `<style>` 块统一设置。

---

## 1. flow（流程图）

**适用**：步骤流程、管道图、工作流、分叉路径

### 结构特征
- 节点水平或垂直排列，箭头连接
- 起始节点用强调色，终止节点加深边框
- 分支用分叉箭头

### 布局参考

**水平流程（最多 4 节点）**：
```
3 节点：宽 150px，高 48px
4 节点：宽 140px，高 48px
y 居中：176

3 节点 rect x = 40, 285, 530（中心 x = 115, 360, 605）
4 节点 rect x = 40, 207, 373, 540（中心 x = 110, 277, 443, 610）
```

**垂直流程（最多 5 节点）**：
```
节点尺寸：宽 200px，高 48px
x 居中：260（偏左，右侧可放注释）

3 节点：y = 60, 170, 300（间距 110）
4 节点：y = 45, 130, 215, 300（间距 85）
5 节点：y = 30, 105, 180, 255, 330（间距 75）
```

**分叉流程**：
```
主干水平 3 节点，第二个节点向下扇出 2-3 条分支
分支 y = 主干 y + 90
分支间距 140px
```

### SVG 骨架

```svg
<svg viewBox="0 0 720 400" width="720" height="400">
  <defs>
    <!-- 箭头 marker：markerUnits=userSpaceOnUse 固定像素；orient=auto 单 marker 通吃水平/垂直/斜向 -->
    <marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="10" markerHeight="10" orient="auto" markerUnits="userSpaceOnUse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#2D3436"/></marker>
  </defs>
  <!-- 注意：无背景矩形，透明底 -->

  <!-- 节点 1（起始，P1 雾蓝系模块色 1） -->
  <rect x="40" y="176" width="140" height="48" rx="6" fill="#D6E4F0" stroke="#2D3436" stroke-width="2"/>
  <text x="110" y="205" text-anchor="middle" font-size="18" fill="#2D3436">识别场景</text>

  <!-- 箭头：x1 = 源框右边 + 4；x2 = 目标框左边 - 4 -->
  <line x1="184" y1="200" x2="203" y2="200" stroke="#2D3436" stroke-width="2" marker-end="url(#arrow)"/>

  <!-- 节点 2（模块色 2，与节点 1 不同色） -->
  <rect x="207" y="176" width="140" height="48" rx="6" fill="#C5D9E8" stroke="#2D3436" stroke-width="2"/>
  <text x="277" y="205" text-anchor="middle" font-size="18" fill="#2D3436">梳理流程</text>

  <!-- 箭头 -->
  <line x1="351" y1="200" x2="369" y2="200" stroke="#2D3436" stroke-width="2" marker-end="url(#arrow)"/>

  <!-- 节点 3（模块色 3） -->
  <rect x="373" y="176" width="140" height="48" rx="6" fill="#B8CFE0" stroke="#2D3436" stroke-width="2"/>
  <text x="443" y="205" text-anchor="middle" font-size="18" fill="#2D3436">编写</text>

  <!-- 箭头 -->
  <line x1="517" y1="200" x2="536" y2="200" stroke="#2D3436" stroke-width="2" marker-end="url(#arrow)"/>

  <!-- 节点 4（终止，模块色 4，深边框强调） -->
  <rect x="540" y="176" width="140" height="48" rx="6" fill="#DCE8F2" stroke="#2D3436" stroke-width="3"/>
  <text x="610" y="205" text-anchor="middle" font-size="18" fill="#2D3436">验证</text>
</svg>
```

---

## 2. layer（层次图）

**适用**：分层架构、堆叠结构、层级依赖

### 布局参考

```
3 层布局：
  层 1：y = 80,  高度 70px（强调色）
  层 2：y = 170, 高度 70px
  层 3：y = 260, 高度 70px

4 层布局：
  层 1：y = 45,  高度 56px
  层 2：y = 121, 高度 56px
  层 3：y = 197, 高度 56px
  层 4：y = 273, 高度 56px

每层宽度：580px（x: 70–650）
层间距：20px
层标签居中：20px, font-weight 600
```

### SVG 骨架

```svg
<svg viewBox="0 0 720 400" width="720" height="400">
  <!-- 无背景矩形，透明底 -->

  <!-- 层 1（顶层，G2 法律米梯度 档 1，最浅） -->
  <rect x="70" y="80" width="580" height="70" rx="6" fill="#F4ECDC" stroke="#2D3436" stroke-width="2"/>
  <text x="360" y="122" text-anchor="middle" font-size="20" font-weight="600" fill="#2D3436">应用层</text>

  <!-- 层 2（G2 档 2，中间明度） -->
  <rect x="70" y="170" width="580" height="70" rx="6" fill="#E8D8C0" stroke="#2D3436" stroke-width="2"/>
  <text x="360" y="212" text-anchor="middle" font-size="20" font-weight="600" fill="#2D3436">能力层</text>

  <!-- 层 3（底层，G2 档 3，最深——3 层时取档 1-3；5 层时取档 1-5 全套） -->
  <rect x="70" y="260" width="580" height="70" rx="6" fill="#D8C4A4" stroke="#2D3436" stroke-width="2"/>
  <text x="360" y="302" text-anchor="middle" font-size="20" font-weight="600" fill="#2D3436">基础层</text>
</svg>
```

> **配色要点**：layer 模板必须用 G1-G4 灰度梯度中任一组，**色相统一**、仅明度变化。**禁止**误用 P1-P8 多色（v1.5.0 旧规范）——把同色系层画成不同色相会破坏层级归属的视觉语义（详见 DEC-012）。5 层变体取档 1-5 全套：`#F4ECDC / #E8D8C0 / #D8C4A4 / #C4AE88 / #B8A282`。

---

## 3. matrix（对比图）

**适用**：前后对比、方案对比、四象限

### 布局参考

```
2 列对比：
  左列：x = 40–340，宽 300px
  右列：x = 380–680，宽 300px
  列间距：40px

列标题：y = 50，高度 48px
行单元：y 从 118 开始，每行高度 60px，间距 12px
  3 行：y = 118, 190, 262
```

### SVG 骨架

```svg
<svg viewBox="0 0 720 400" width="720" height="400">
  <!-- 无背景矩形，透明底 -->

  <!-- 左列标题（P8 混合系暖米色） -->
  <rect x="40" y="50" width="300" height="48" rx="6" fill="#E8D8C0" stroke="#2D3436" stroke-width="2"/>
  <text x="190" y="80" text-anchor="middle" font-size="18" font-weight="600" fill="#2D3436">方案 A</text>

  <!-- 右列标题（P8 混合系雾蓝色，与左列不同色相） -->
  <rect x="380" y="50" width="300" height="48" rx="6" fill="#D6E4F0" stroke="#2D3436" stroke-width="2"/>
  <text x="530" y="80" text-anchor="middle" font-size="18" font-weight="600" fill="#2D3436">方案 B</text>

  <!-- 行单元（同列内浅一档模块色） -->
  <rect x="40" y="118" width="300" height="60" rx="6" fill="#EDDFC8" stroke="#2D3436" stroke-width="1.5"/>
  <text x="190" y="153" text-anchor="middle" font-size="18" fill="#2D3436">特点 1</text>
  <!-- ... -->
</svg>
```

---

## 4. hub（中心辐射图）

**适用**：生态关系、核心概念+关联要素

### 布局参考

```
核心节点：中心 (360, 200)，尺寸 140×52
外围节点：半径 130px 的圆上均匀分布，尺寸 120×44

4 个外围（十字形）：
  上(360, 65)   右(505, 200)  下(360, 335)   左(215, 200)

5 个外围：
  (360, 65)  (483, 140)  (440, 300)  (280, 300)  (237, 140)
```

### SVG 骨架

```svg
<svg viewBox="0 0 720 400" width="720" height="400">
  <defs>
    <!-- 箭头 marker：markerUnits=userSpaceOnUse 固定像素；orient=auto 单 marker 通吃水平/垂直/斜向 -->
    <marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="10" markerHeight="10" orient="auto" markerUnits="userSpaceOnUse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#2D3436"/></marker>
  </defs>
  <!-- 无背景矩形，透明底 -->

  <!-- 连线（底层）：线终点 = 外围节点底边 - 4px 间隙（外围上节点 y=50 高 44 → 底边 94 → y2=98） -->
  <line x1="360" y1="174" x2="360" y2="98" stroke="#2D3436" stroke-width="1.5" marker-end="url(#arrow)"/>
  <!-- ... -->

  <!-- 核心节点（P1 雾蓝系模块色 1，深边框强调） -->
  <rect x="290" y="174" width="140" height="52" rx="6" fill="#D6E4F0" stroke="#2D3436" stroke-width="2.5"/>
  <text x="360" y="206" text-anchor="middle" font-size="18" font-weight="600" fill="#2D3436">核心概念</text>

  <!-- 外围节点（每个用同组不同模块色，避免色块连片） -->
  <rect x="300" y="50" width="120" height="44" rx="6" fill="#C5D9E8" stroke="#2D3436" stroke-width="1.5"/>
  <text x="360" y="78" text-anchor="middle" font-size="18" fill="#2D3436">要素 A</text>
  <!-- ... -->
</svg>
```

---

## 5. tree（层级/树形图）

**适用**：组织结构、分类体系、金字塔

### 布局参考

```
2 层（1→3-5）：
  根：x=360, y=100, 宽 160px, 高 48px
  子节点：y=260, 宽 140px, 高 48px
  3 子：x = 120, 360, 600
  5 子：x = 50, 190, 360, 530, 660

3 层（1→3→5）：
  根：y=40, 宽 160px
  分支：y=180, 宽 140px, x = 120, 360, 600
  叶子：y=320, 宽 120px, 每分支下 1-2 个

金字塔（3 层）：
  层 1：宽 200px, 居中, y=70, 高 64px
  层 2：宽 400px, 居中, y=170, 高 64px
  层 3：宽 580px, 居中, y=270, 高 64px
```

### SVG 骨架

```svg
<svg viewBox="0 0 720 400" width="720" height="400">
  <defs>
    <!-- 箭头 marker：markerUnits=userSpaceOnUse 固定像素；orient=auto 单 marker 通吃水平/垂直/斜向 -->
    <marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="10" markerHeight="10" orient="auto" markerUnits="userSpaceOnUse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#2D3436"/></marker>
  </defs>
  <!-- 无背景矩形，透明底 -->

  <!-- 根节点（G2 法律米梯度 档 1，最浅——根在上，浅色轻盈） -->
  <rect x="280" y="100" width="160" height="48" rx="6" fill="#F4ECDC" stroke="#2D3436" stroke-width="2"/>
  <text x="360" y="130" text-anchor="middle" font-size="18" font-weight="600" fill="#2D3436">根概念</text>

  <!-- 连线：线终点 = 子节点顶边 - 4px 间隙（子节点 y=260 → y2=256） -->
  <line x1="310" y1="148" x2="190" y2="256" stroke="#2D3436" stroke-width="1.5"/>
  <line x1="360" y1="148" x2="360" y2="256" stroke="#2D3436" stroke-width="1.5"/>
  <line x1="410" y1="148" x2="530" y2="256" stroke="#2D3436" stroke-width="1.5"/>

  <!-- 子节点（G2 档 2，中间明度——同色相比根更深） -->
  <rect x="120" y="260" width="140" height="48" rx="6" fill="#E8D8C0" stroke="#2D3436" stroke-width="2"/>
  <text x="190" y="289" text-anchor="middle" font-size="18" fill="#2D3436">分支 A</text>
  <!-- ... -->
</svg>
```

> tree 骨架连线**不**带 `marker-end`——tree（组织/分类/金字塔）通常用纯连线表示层级归属，不强调方向。需要方向箭头时按 style-guide §六「箭头」自行加 `marker-end="url(#arrow)"`。

---

## 6. cycle（循环图）

**适用**：闭环流程、迭代循环

### 布局参考

```
4 节点（矩形排列）：
  上：(305, 50), 140×48
  右：(520, 176), 140×48
  下：(305, 302), 140×48
  左：(60, 176), 140×48

中心标签：x=360, y=205, 18px

5 节点（圆上均布，半径 120px）：
  中心 (360, 200)
```

---

## 7. 组合模板

### flow+matrix

上下分区：
```
上半部分（y: 50–150）：3-4 个水平阶段节点，宽 130px，高 48px
下半部分（y: 170–380）：每阶段下方的对比区域
```

### flow+hub

主流程 + 关键节点展开：
```
主流程 y 上移至 100，节点宽 130px, 高 48px
关键节点下方展开 3-4 个子节点（y: 230–340）
虚线框圈出展开区域
```

---

## 8. radar（雷达图，v1.8.0 新增）

**适用**：多维度对比——理论 vs 实际、国内外、能力评估、题型 vs 模型适配；需要 6-12 个维度同屏对比的**连续数值**。填补 v1.7.x "数据可视化不在范围" 的最大缺口。

### 结构特征
- N 条轴线（6-12，典型 6-8）从中心等角辐射（i=0 朝上，顺时针）
- 4-5 层同心多边形网格（浅灰 `#E8E8E8` 弱线，不抢戏）
- 1-2 个数据多边形叠加（每个一种 P 色半透明填充 + 同色加深一档描边）
- 维度标签在外圈（18px `#2D3436`，anchor 按方向：左 end / 右 start / 上中 / 下中）
- ≥2 系列时加底部图例（16px）

### 布局公式（坐标由 N 与数值决定，建议用生成器脚本）
```
画布：720 × H（6 轴典型 H≈460；8 轴 H≈480；标签长时 +20）
标题：y = 34（22px）
中心：(360, CY)，CY ≈ 250（6 轴）或 260（8 轴）
半径：R = 150-170（视标签长度；标签长则 R 取小）
网格层：GRID_LEVELS=4 层同心多边形（r = R × {0.25,0.5,0.75,1.0}）
轴线：中心 → (CX + R·cosθ_i, CY + R·sinθ_i)，θ_i = -π/2 + i·2π/N
维度标签：在 1.18 × R 处
数据顶点：中心 + R·v_i·(cosθ_i, sinθ_i)，v_i ∈ [0,1]
图例：底部 y = H-30，每项色块 18×13 + 文字
```

### 配色
- 1 系列：P1-P7 任一组主色填充（fill-opacity 0.5）+ 同组深一档描边（如 P1 `#B8CFE0` 填充 + `#7CA0BC` 描边）
- 2 系列：**两组不同色相**（A=P1 雾蓝 `#B8CFE0`/`#7CA0BC`、B=P4 暖米 `#E8D8C0`/`#B8A282`），fill-opacity 0.5 保证重叠区可辨
- 网格/轴：`#E8E8E8`（网格）/ `#B2BEC3`（轴），弱线
- 顶点小圆点（r=3）用描边色，增强可读性

### 生成器脚本（强烈推荐）
雷达图几何随 N 变化，手算易错。用 `scripts/gen-radar.py` 生成：修改脚本顶部 `TITLE/LABELS/SERIES/CX/CY/R` 参数后 `python3 scripts/gen-radar.py output.svg`，再 `rsvg-convert -w 720 output.svg -o output.png` 目检。

### SVG 骨架（6 轴 2 系列，示例 = 法律 AI 生态六层）
```svg
<svg viewBox="0 0 720 505" width="720" height="505" xmlns="http://www.w3.org/2000/svg">
  <text x="360" y="34" text-anchor="middle" font-size="22" font-weight="600" fill="#2D3436">法律 AI 生态六层：理论能力 vs 实际部署</text>
  <!-- 4 层网格（r=37.5/75/112.5/150，中心 360,250） -->
  <polygon points="360,212.5 392.5,231.2 392.5,268.8 360,287.5 327.5,268.8 327.5,231.3" fill="none" stroke="#E8E8E8" stroke-width="1"/>
  <polygon points="360,175 425,212.5 425,287.5 360,325 295,287.5 295,212.5" fill="none" stroke="#E8E8E8" stroke-width="1"/>
  <polygon points="360,137.5 457.4,193.8 457.4,306.2 360,362.5 262.6,306.3 262.6,193.8" fill="none" stroke="#E8E8E8" stroke-width="1"/>
  <polygon points="360,100 489.9,175 489.9,325 360,400 230.1,325 230.1,175" fill="none" stroke="#E8E8E8" stroke-width="1"/>
  <!-- 6 条轴 -->
  <line x1="360" y1="250" x2="360" y2="100" stroke="#B2BEC3" stroke-width="1"/>
  <line x1="360" y1="250" x2="489.9" y2="175" stroke="#B2BEC3" stroke-width="1"/>
  <line x1="360" y1="250" x2="489.9" y2="325" stroke="#B2BEC3" stroke-width="1"/>
  <line x1="360" y1="250" x2="360" y2="400" stroke="#B2BEC3" stroke-width="1"/>
  <line x1="360" y1="250" x2="230.1" y2="325" stroke="#B2BEC3" stroke-width="1"/>
  <line x1="360" y1="250" x2="230.1" y2="175" stroke="#B2BEC3" stroke-width="1"/>
  <!-- 系列 A 理论能力（P1 雾蓝） -->
  <polygon points="360,112 474.3,184 470.4,313.8 360,385 256.1,310 248.3,185.5" fill="#B8CFE0" fill-opacity="0.5" stroke="#7CA0BC" stroke-width="2"/>
  <!-- 系列 B 实际部署（P4 暖米） -->
  <polygon points="360,178 435.3,206.5 431.4,291.2 360,325 279.5,296.5 308,220" fill="#E8D8C0" fill-opacity="0.5" stroke="#B8A282" stroke-width="2"/>
  <!-- 维度标签 -->
  <text x="360" y="71" text-anchor="middle" font-size="18" fill="#2D3436">数据/知识库</text>
  <text x="513.3" y="166.5" text-anchor="start" font-size="18" fill="#2D3436">模型能力</text>
  <text x="513.3" y="343.5" text-anchor="start" font-size="18" fill="#2D3436">Agent/Skill</text>
  <text x="360" y="441" text-anchor="middle" font-size="18" fill="#2D3436">工具/MCP</text>
  <text x="206.7" y="343.5" text-anchor="end" font-size="18" fill="#2D3436">安全/合规</text>
  <text x="206.7" y="166.5" text-anchor="end" font-size="18" fill="#2D3436">生态/平台</text>
  <!-- 图例（在底部轴标签"工具/MCP"(y=441)下方 ~24px，避免重叠） -->
  <rect x="200" y="465" width="18" height="13" fill="#B8CFE0" fill-opacity="0.6" stroke="#7CA0BC" stroke-width="1.5"/>
  <text x="226" y="476" font-size="16" fill="#2D3436">理论能力</text>
  <rect x="360" y="465" width="18" height="13" fill="#E8D8C0" fill-opacity="0.6" stroke="#B8A282" stroke-width="1.5"/>
  <text x="386" y="476" font-size="16" fill="#2D3436">实际部署</text>
</svg>
```

### 维度选择纪律
- 维度数严选 6-12 个；>12 易失焦
- 维度须 MECE（互斥且穷尽），避免两个轴含义重叠
- 数值 v_i ∈ [0,1] 归一化；同图两系列用同一套维度刻度

---

## 9. skill-card（Skill 结构模板图，v1.8.1 新增）

**适用**：介绍一个具体 Skill 时的标准骨架——输入 → Skill（含三件套 `references/` + `scripts/` + `SKILL.md`，以及 SKILL.md 定义的流程步骤）→ 输出，可选底部虚线"联动"脚注。每章介绍具体 Skill 时复用，保证全书 Skill 图风格统一。

### 结构特征
- 顶/中/底三层数据流，层间用下箭头
- 中央大矩形 = Skill 主体，顶部深色名称带 `Skill: {name}`
- 名称带下：三件套横排（`references/` 清单模板 + `scripts/` 脚本 + `SKILL.md` 流程定义）
- 三件套下：SKILL.md 定义的流程步骤列表（①②③④ 编号 + 步骤名，3-5 步）
- 底部输出框（1-3 份实文档）
- 可选脚注：虚线框写"联动：可接入 X / Y"

### 布局参考
```
画布：720 × H（H 随输入/输出/脚注数动态，典型 480-560）
标题：y = 32（22px）
输入层：y = 56-102（h=46），1-2 框横排居中（自动等分 70-650 宽）
Skill 主框：x=70 y=150 w=580 h≈240
  名称带：h=38（深色填充 + 顶圆角 + 底分隔线）
  三件套：y=204-254（h=50），3 框横排
  流程标签 + 步骤列表：y=275 起，每步 22px 行高
输出层：y=425-471（h=46），1-3 框横排
脚注虚框（可选）：y=485-521（h=36）
```

### 配色
- 全图用**单组 P 色**（不像 matrix/radar 多色相），强调"同一个 Skill 的内部结构"
- 名称带：取该组深一档（如 P1 `#B8CFE0`）—— Skill 身份的视觉锚点
- 三件套：同组主色（如 P1 `#D6E4F0`）
- 输入/输出：同组最浅档（如 P1 `#EDF3F8`）
- 脚注虚框：中灰 `#636E72` 虚线 `stroke-dasharray="6 4"`，无填充

### 生成器脚本
`scripts/gen-skill-card.py`：参数化（TITLE/INPUTS/SKILL_NAME/SATELLITES/STEPS/OUTPUTS/FOOTNOTE/调色板 顶部可改）→ `python3 scripts/gen-skill-card.py out.svg` + rsvg 目检。

### SVG 骨架（示例 = 法律研究 Skill）
```svg
<svg viewBox="0 0 720 561" width="720" height="561" xmlns="http://www.w3.org/2000/svg">
  <text x="360" y="32" text-anchor="middle" font-size="22" font-weight="600" fill="#2D3436">法律研究 Skill 结构图</text>
  <!-- 输入层（2 框） -->
  <rect x="70" y="56" width="278" height="46" rx="6" fill="#EDF3F8" stroke="#2D3436" stroke-width="1.5"/>
  <text x="209" y="85" text-anchor="middle" font-size="17" fill="#2D3436">案件事实</text>
  <rect x="372" y="56" width="278" height="46" rx="6" fill="#EDF3F8" stroke="#2D3436" stroke-width="1.5"/>
  <text x="511" y="85" text-anchor="middle" font-size="17" fill="#2D3436">法律问题</text>
  <line x1="360" y1="104" x2="360" y2="142" stroke="#2D3436" stroke-width="2" marker-end="url(#arrow)"/>
  <!-- Skill 主框 + 名称带 -->
  <rect x="70" y="150" width="580" height="240" rx="10" fill="none" stroke="#2D3436" stroke-width="2.5"/>
  <rect x="70" y="150" width="580" height="38" rx="10" fill="#B8CFE0" stroke="#2D3436" stroke-width="2.5"/>
  <rect x="70" y="178" width="580" height="10" fill="#B8CFE0"/>
  <line x1="70" y1="188" x2="650" y2="188" stroke="#2D3436" stroke-width="2.5"/>
  <text x="360" y="175" text-anchor="middle" font-size="19" font-weight="700" fill="#2D3436">Skill: legal-research</text>
  <!-- 三件套 -->
  <rect x="70" y="204" width="177" height="50" rx="6" fill="#D6E4F0" stroke="#2D3436" stroke-width="1.5"/>
  <text x="158.5" y="225" text-anchor="middle" font-size="16" font-weight="600" fill="#2D3436">references/</text>
  <text x="158.5" y="244" text-anchor="middle" font-size="14" fill="#636E72">清单/模板</text>
  <!-- ...scripts/ 与 SKILL.md 同结构，x=271 / x=472 ... -->
  <!-- 流程步骤列表 -->
  <text x="78" y="282" font-size="16" font-weight="600" fill="#2D3436">SKILL.md 定义的流程：</text>
  <text x="90" y="306" font-size="16" fill="#2D3436"><tspan font-weight="600">①</tspan>  识别法律问题</text>
  <!-- ...②③④ 同结构，y=328/350/372 ... -->
  <line x1="360" y1="392" x2="360" y2="417" stroke="#2D3436" stroke-width="2" marker-end="url(#arrow)"/>
  <!-- 输出层 -->
  <rect x="70" y="425" width="580" height="46" rx="6" fill="#EDF3F8" stroke="#2D3436" stroke-width="1.5"/>
  <text x="360" y="454" text-anchor="middle" font-size="17" fill="#2D3436">研究备忘录.md</text>
  <!-- 联动虚框脚注 -->
  <rect x="70" y="485" width="580" height="36" rx="6" fill="none" stroke="#636E72" stroke-width="1.5" stroke-dasharray="6 4"/>
  <text x="360" y="508" text-anchor="middle" font-size="15" fill="#636E72">联动：可接入起诉状 Skill / 庭审大纲 Skill</text>
  <defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="6" refY="5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L10,5 L0,10 z" fill="#2D3436"/></marker></defs>
</svg>
```

### 纪律
- 三件套顺序固定 `references/` → `scripts/` → `SKILL.md`（对应 Skill 目录约定）
- 步骤数 3-5；超过 5 步拆分子 Skill 或改用 `flow` 模板
- 名称带必须深于三件套，建立"Skill 身份带"视觉层级
- 全图单组 P 色（同色系明度差建层级），不用多色相

---

## 10. timeline-lane（多泳道时间轴，v1.8.2 新增）

**适用**：多角色/多主体在时间维度上的事件推进——诉讼多角色时间线、案件流程节点、项目多部门进度。比 flow "水平+时间标注" 变通更正式（真刻度 + 泳道分隔）。

### 结构特征
- 顶部时间刻度轴（4-6 个时间标签：日期/月份/阶段）
- N 条横向泳道（3-5 条，每条 = 一个角色/主体/类别），左侧泳道标签
- 事件 = 菱形标记落在 (时间刻度, 泳道中心)，文字标签在标记上下交替（减少碰撞）
- 泳道交替极浅色带（可选）+ 浅灰分隔线

### 布局参考
```
画布：720 × H（H = 90 + N×50 + 30，4 泳道典型 H≈320）
标题：y = 32
时间刻度标签：y = 58（轴上方）
时间轴线：y = 74，x 175→680（宽 505）
泳道标签列：x = 162（右对齐），x<170 为标签区
泳道：top = 90，每条高 50，中心 y = 90 + i×50 + 25
泳道分隔：浅灰 #E8E8E8 横线
事件菱形：边长 10，中心在 (175 + f×505, 泳道中心)，f∈[0,1]
事件标签：13px，上下交替（cy-12 / cy+20）
```

### 配色
- 泳道交替带：极浅 P 色（如 P2 `#EDF5F3`）/ 透明交替（不抢戏）
- 菱形标记：P 色主色填充（如 P2 `#A8D2C9`）+ 深灰描边 `#2D3436`
- 标签/轴：深灰文字 + 浅灰轴 `#B2BEC3`
- 多角色需强区分时，可按泳道分配 P8 混合系不同色相（每泳道一色）——默认单色更克制

### 生成器脚本
`scripts/gen-timeline-lane.py`：参数化（TITLE/LANES/TICKS/EVENTS/调色板顶部可改）→ `python3 scripts/gen-timeline-lane.py out.svg` + rsvg 目检。

### SVG 骨架（示例 = 案件多角色推进时间轴，4 泳道）
```svg
<svg viewBox="0 0 720 320" width="720" height="320" xmlns="http://www.w3.org/2000/svg">
  <text x="360" y="32" text-anchor="middle" font-size="22" font-weight="600" fill="#2D3436">案件多角色推进时间轴</text>
  <!-- 顶部时间刻度 -->
  <text x="175" y="58" text-anchor="middle" font-size="14" fill="#636E72">1月</text>
  <text x="302.5" y="58" text-anchor="middle" font-size="14" fill="#636E72">3月</text>
  <!-- ...6月/9月/12月 同结构... -->
  <line x1="175" y1="74" x2="680" y2="74" stroke="#B2BEC3" stroke-width="1.5"/>
  <!-- 泳道（4 条） -->
  <rect x="175" y="90" width="505" height="50" fill="#EDF5F3"/>           <!-- 偶数泳道浅带 -->
  <line x1="175" y1="90" x2="680" y2="90" stroke="#E8E8E8" stroke-width="1"/>
  <text x="162" y="120" text-anchor="end" font-size="16" font-weight="600" fill="#2D3436">原告律师</text>
  <!-- ...被告律师/法院/当事人 同结构，y=160/210/260 中心... -->
  <!-- 事件菱形 + 标签（上下交替） -->
  <polygon points="185,115 190,120 185,125 180,120" fill="#A8D2C9" stroke="#2D3436" stroke-width="1.5"/>
  <text x="185" y="108" text-anchor="middle" font-size="13" fill="#2D3436">立案</text>
  <polygon points="286,115 291,120 286,125 281,120" fill="#A8D2C9" stroke="#2D3436" stroke-width="1.5"/>
  <text x="286" y="140" text-anchor="middle" font-size="13" fill="#2D3436">举证</text>
  <!-- ...其余事件同结构，标签 idx%2 交替 cy-12/cy+20... -->
</svg>
```

### 纪律
- 泳道数 3-5；超过 5 拆图或改用表格
- 事件标签上下交替（生成器自动 `idx%2`）减少碰撞；密集事件考虑缩短标签或用图例编号
- 时间刻度 4-6 个，等距；非等距时间须标注真实间隔
- 菱形标记必须落在泳道中心线 + 对齐时间刻度（生成器保证）
- 单角色单线时间轴用此模板 N=1 也可（比 flow 变通更正式）

---

## 11. matrix-grid（N×M 网格矩阵，v1.8.3 新增）

**适用**：两个维度的交叉对照——风险类型 × 审查维度、特征 × 产品、能力 × 模型。单元格用状态符号（√/×/○/—）或短文本标记 + 颜色编码。比 `matrix`（仅 2 列对比）适合更高维交叉。

### 结构特征
- 左上角 corner label（"维度A \\ 维度B"）
- 顶部列表头（M 个）+ 左侧行表头（N 个），P1 表头带
- N×M 单元格，每格状态符号 + 柔和填充色
- 底部图例（符号 × 含义）

### 布局参考
```
画布：720 × H（H = 100 + N×44 + 60，4×5 典型 H≈340）
标题：y = 32
表头带：y = 62-112（h=50），P1 #D6E4F0
corner：x=40 w=130
网格：x=178-685（宽 507），每格宽 507/M，高 44
图例：底部，每项色块+符号+说明
```

### 配色（状态语义，全部柔和色，禁高饱和红绿）
- √ 重点关注：P3 嫩绿 `#C8EBC8`
- ○ 部分相关：P7 暖灰 `#E8DFD0`
- × 基本无关：P4 暖米浅 `#EDDFC8`
- — 不适用：中性浅灰 `#F0F0F0`
- 表头带：P1 雾蓝 `#D6E4F0`

### 生成器脚本
`scripts/gen-matrix-grid.py`：参数化（TITLE/CORNER_LABEL/ROW_LABELS/COL_LABELS/CELLS/调色板顶部可改）。CELLS 支持 `"yes"`/`"no"`/`"partial"`/`"na"` 或自由文本 → `python3 scripts/gen-matrix-grid.py out.svg` + rsvg 目检。

### SVG 骨架（示例 = 4×5 风险×条款对照矩阵）
```svg
<svg viewBox="0 0 720 340" width="720" height="340" xmlns="http://www.w3.org/2000/svg">
  <text x="360" y="32" text-anchor="middle" font-size="22" font-weight="600" fill="#2D3436">合同审查：4 类风险 × 5 类条款 对照矩阵</text>
  <!-- corner -->
  <rect x="40" y="62" width="130" height="50" fill="#D6E4F0" stroke="#2D3436" stroke-width="1.5"/>
  <text x="105" y="92" text-anchor="middle" font-size="14" font-weight="600" fill="#2D3436">风险 \ 条款</text>
  <!-- 列表头（5） -->
  <rect x="178" y="62" width="101.4" height="50" fill="#D6E4F0" stroke="#2D3436" stroke-width="1.5"/>
  <text x="228.7" y="92" text-anchor="middle" font-size="15" font-weight="600" fill="#2D3436">违约责任</text>
  <!-- ...付款条款/知识产权/保密/终止 同结构... -->
  <!-- 行表头 + 单元格（第 1 行） -->
  <rect x="40" y="116" width="130" height="44" fill="#D6E4F0" stroke="#2D3436" stroke-width="1.5"/>
  <text x="105" y="143" text-anchor="middle" font-size="15" font-weight="600" fill="#2D3436">商业风险</text>
  <rect x="178" y="116" width="101.4" height="44" fill="#C8EBC8" stroke="#2D3436" stroke-width="1"/>
  <text x="228.7" y="145" text-anchor="middle" font-size="20" font-weight="700" fill="#2D3436">√</text>
  <!-- ...其余单元格按 yes/partial/no 填色 + 符号... -->
  <!-- 图例 -->
  <rect x="90" y="315" width="20" height="16" fill="#C8EBC8" stroke="#2D3436" stroke-width="1"/>
  <text x="100" y="328" text-anchor="middle" font-size="14" font-weight="700" fill="#2D3436">√</text>
  <text x="116" y="328" font-size="13" fill="#636E72">重点关注</text>
  <!-- ...○ 部分相关 / × 基本无关 / — 不适用 同结构... -->
</svg>
```

### 纪律
- 维度数 N×M 建议 3-6 × 3-7；超 7 列单元格过窄、文字易溢出
- 状态用 4 档（√/○/×/—）足够；更多档改用色阶（layer G1-G4 明度梯度）
- 单元格符号 ≥ 20px 保证可读；避免在格内塞长文本（长文本放图例或脚注）
- 颜色仅辅助区分，符号本身（√/×/○）须黑白可辨（WCAG + 印刷降级硬约束）

---

## 12. three-col（三栏并列对比，v1.8.4 新增）

**适用**：三分类、三版本、三种打法、三层递进——需要三栏对仗工整、每栏带嵌套子卡片的对比。比 `matrix`（2 列）多一列、比 `matrix-grid`（N×M 网格）更"卡片化"（每栏子卡片承载短句）。

### 结构特征
- 3 等宽栏并列（gap 30），每栏：深色表头 + 3-4 子卡片（浅一档同色相）
- 三栏用 P8 混合系不同色相（雾蓝/嫩绿/暖米），天然多色区分
- 子卡片"标签：内容"格式（特征/适用/示例 等结构化标签）
- 可选底部虚线脚注（"三种可叠加使用"等）

### 布局参考
```
画布：720 × H（3 栏 × 3 卡典型 H≈390）
标题：y = 32
栏：x = 40 / 263 / 486（w=193，gap=30），表头 y=60-110（h=50）
子卡片：y=126 起，每张 h=62（2 行：标签+内容），gap=12
脚注虚框（可选）：底部
```

### 配色
- 三栏表头：P8 混合系三色相（P1 雾蓝 `#B8CFE0` / P3 嫩绿 `#C8EBC8` / P4 暖米 `#E8D8C0`）
- 子卡片：同栏表头的浅一档（`#EDF3F8` / `#EDF7ED` / `#F4ECDC`）
- 子卡片 2 行：标签（14px 加粗）+ 内容（13px）——避免单行"标签：内容"在 193px 窄列溢出

### 生成器脚本
`scripts/gen-three-col.py`：参数化（TITLE/COLUMNS/FOOTNOTE/调色板顶部可改）→ `python3 scripts/gen-three-col.py out.svg` + rsvg 目检。

### SVG 骨架（示例 = Skill 三种典型结构）
```svg
<svg viewBox="0 0 720 424" width="720" height="424" xmlns="http://www.w3.org/2000/svg">
  <text x="360" y="32" text-anchor="middle" font-size="22" font-weight="600" fill="#2D3436">Skill 的三种典型结构</text>
  <!-- 第 1 栏 表头（雾蓝） -->
  <rect x="40" y="60" width="193" height="50" rx="6" fill="#B8CFE0" stroke="#2D3436" stroke-width="2"/>
  <text x="136.5" y="91" text-anchor="middle" font-size="18" font-weight="700" fill="#2D3436">纯 SKILL.md 型</text>
  <!-- 第 1 栏 子卡片 -->
  <rect x="40" y="126" width="193" height="62" rx="6" fill="#EDF3F8" stroke="#2D3436" stroke-width="1.5"/>
  <text x="136.5" y="150" text-anchor="middle" font-size="14" font-weight="700" fill="#2D3436">特征</text>
  <text x="136.5" y="173" text-anchor="middle" font-size="13" fill="#636E72">流程全写在 SKILL.md</text>
  <!-- ...其余子卡片 + 第 2/3 栏（嫩绿/暖米）同结构... -->
  <!-- 脚注虚框 -->
  <rect x="40" y="358" width="640" height="36" rx="6" fill="none" stroke="#636E72" stroke-width="1.5" stroke-dasharray="6 4"/>
  <text x="360" y="381" text-anchor="middle" font-size="14" fill="#636E72">三种结构可叠加使用；复杂 Skill 常混合 2-3 种</text>
</svg>
```

### 纪律
- 严格 3 栏（2 栏用 matrix，4+ 栏用 matrix-grid 或拆图）
- 三栏子卡片数对等（3-4 张），不对等时补占位保持视觉对仗
- 子卡片文本一行内（≤16 字），超长换行或精简
- 三色相仅用于"三栏天然并列"场景；非对仗的多分类用 matrix-grid

---

## 模板选择决策树

```
需要表达什么关系？
├── 线性步骤/顺序 → flow
│   └── 有分叉？ → flow（带分支箭头）
├── 上下分层/依赖 → layer
├── 并排对比/差异 → matrix
├── 中心+辐射 → hub
├── 层级/分类/金字塔 → tree
│   └── 下层更宽？ → tree（金字塔变体）
├── 闭环/循环 → cycle
├── 多维度连续数值对比（6-12 维） → radar（v1.8.0）
├── 介绍一个 Skill 的结构（输入→Skill→输出） → skill-card（v1.8.1）
├── 多角色/多主体时间推进 → timeline-lane（v1.8.2）
├── 两维交叉对照（N×M 网格 + 状态符号） → matrix-grid（v1.8.3）
├── 三分类/三版本对仗并列（每栏带子卡片） → three-col（v1.8.4）
└── 混合关系？
    ├── 递进+数据对比 → flow+matrix
    └── 流程+节点展开 → flow+hub
```

---

## 场景覆盖分析

### 已覆盖

| 场景 | 模板 |
|------|------|
| 多步骤工作流 | flow |
| 带分支的流程 | flow（分叉） |
| 系统分层架构 | layer |
| 前后/方案对比 | matrix |
| 核心概念与要素 | hub |
| 组织/分类体系 | tree |
| 金字塔层级 | tree（金字塔变体） |
| 循环/迭代过程 | cycle |
| 多维度数值对比（6-12 维） | radar（v1.8.0） |
| 单个 Skill 的结构（输入→Skill→输出） | skill-card（v1.8.1） |
| 多角色/多主体时间推进 | timeline-lane（v1.8.2） |
| 两维交叉对照（风险×条款/特征×产品） | matrix-grid（v1.8.3） |
| 三分类/三版本对仗并列 | three-col（v1.8.4） |
| 递进效果+数据 | flow+matrix |
| 流程+关键展开 | flow+hub |

### 可变通

| 场景 | 变通方式 | 局限 |
|------|---------|------|
| 时间线 | flow（水平+时间标注） | 无刻度标记（v1.8.2 起多角色时间线改用 timeline-lane） |
| 多角色并行 | flow（按角色分行） | 非严格泳道（v1.8.2 起改用 timeline-lane） |
| 韦恩/交叉 | hub（中心为交集） | 无真正重叠圆 |
| 简单数据对比 | matrix（矩形高度代表值） | 非正式图表 |

### 不在范围内

- 复杂数据可视化（柱状图、折线图、饼图）—— **雷达图 radar 已于 v1.8.0 解禁**；柱/折/饼仍禁
- 地图/空间布局
- 交互原型
