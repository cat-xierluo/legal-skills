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
<svg viewBox="0 0 720 400">
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
<svg viewBox="0 0 720 400">
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
<svg viewBox="0 0 720 400">
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
<svg viewBox="0 0 720 400">
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
<svg viewBox="0 0 720 400">
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
| 递进效果+数据 | flow+matrix |
| 流程+关键展开 | flow+hub |

### 可变通

| 场景 | 变通方式 | 局限 |
|------|---------|------|
| 时间线 | flow（水平+时间标注） | 无刻度标记 |
| 多角色并行 | flow（按角色分行） | 非严格泳道 |
| 韦恩/交叉 | hub（中心为交集） | 无真正重叠圆 |
| 简单数据对比 | matrix（矩形高度代表值） | 非正式图表 |

### 不在范围内

- 复杂数据可视化（柱状图、折线图、饼图）
- 地图/空间布局
- 交互原型
