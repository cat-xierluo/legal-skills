# 布局模板定义

6 种基础布局 + 2 种组合模板。基于 **16开（115mm 通栏）** 物理尺寸推算。

> 所有字号已按印刷可读性校准：节点标签 18px（物理 2.88mm = 8.2pt）。
> 详见 style-guide.md 的物理尺寸推算。

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
  <style>text { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; }</style>
  <defs><marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#2D3436"/></marker></defs>
  <rect width="720" height="400" fill="#FFFFFF"/>

  <!-- 节点 1（起始，强调色） -->
  <rect x="40" y="176" width="140" height="48" rx="6" fill="#EBF5FB" stroke="#3498DB" stroke-width="2"/>
  <text x="110" y="205" text-anchor="middle" font-size="18" fill="#2D3436">识别场景</text>

  <!-- 箭头 -->
  <line x1="184" y1="200" x2="199" y2="200" stroke="#2D3436" stroke-width="2" marker-end="url(#arrow)"/>

  <!-- 节点 2 -->
  <rect x="207" y="176" width="140" height="48" rx="6" fill="#FFFFFF" stroke="#2D3436" stroke-width="2"/>
  <text x="277" y="205" text-anchor="middle" font-size="18" fill="#2D3436">梳理流程</text>

  <!-- 箭头 -->
  <line x1="351" y1="200" x2="365" y2="200" stroke="#2D3436" stroke-width="2" marker-end="url(#arrow)"/>

  <!-- 节点 3 -->
  <rect x="373" y="176" width="140" height="48" rx="6" fill="#FFFFFF" stroke="#2D3436" stroke-width="2"/>
  <text x="443" y="205" text-anchor="middle" font-size="18" fill="#2D3436">编写</text>

  <!-- 箭头 -->
  <line x1="517" y1="200" x2="532" y2="200" stroke="#2D3436" stroke-width="2" marker-end="url(#arrow)"/>

  <!-- 节点 4（终止，深边框） -->
  <rect x="540" y="176" width="140" height="48" rx="6" fill="#FFFFFF" stroke="#2D3436" stroke-width="3"/>
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
  <rect width="720" height="400" fill="#FFFFFF"/>

  <!-- 层 1（顶层，强调色） -->
  <rect x="70" y="80" width="580" height="70" rx="6" fill="#EBF5FB" stroke="#3498DB" stroke-width="2"/>
  <text x="360" y="122" text-anchor="middle" font-size="20" font-weight="600" fill="#2D3436">应用层</text>

  <!-- 层 2 -->
  <rect x="70" y="170" width="580" height="70" rx="6" fill="#FFFFFF" stroke="#2D3436" stroke-width="2"/>
  <text x="360" y="212" text-anchor="middle" font-size="20" font-weight="600" fill="#2D3436">能力层</text>

  <!-- 层 3（底层） -->
  <rect x="70" y="260" width="580" height="70" rx="6" fill="#FFFFFF" stroke="#2D3436" stroke-width="2"/>
  <text x="360" y="302" text-anchor="middle" font-size="20" font-weight="600" fill="#2D3436">基础层</text>
</svg>
```

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
  <rect width="720" height="400" fill="#FFFFFF"/>

  <!-- 左列标题（橙色） -->
  <rect x="40" y="50" width="300" height="48" rx="6" fill="#FEF5E7" stroke="#F39C12" stroke-width="2"/>
  <text x="190" y="80" text-anchor="middle" font-size="18" font-weight="600" fill="#2D3436">方案 A</text>

  <!-- 右列标题（蓝色） -->
  <rect x="380" y="50" width="300" height="48" rx="6" fill="#EBF5FB" stroke="#3498DB" stroke-width="2"/>
  <text x="530" y="80" text-anchor="middle" font-size="18" font-weight="600" fill="#2D3436">方案 B</text>

  <!-- 行单元 -->
  <rect x="40" y="118" width="300" height="60" rx="6" fill="#FFFFFF" stroke="#2D3436" stroke-width="1.5"/>
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
  <rect width="720" height="400" fill="#FFFFFF"/>

  <!-- 连线（底层） -->
  <line x1="360" y1="174" x2="360" y2="87" stroke="#2D3436" stroke-width="1.5"/>
  <!-- ... -->

  <!-- 核心节点 -->
  <rect x="290" y="174" width="140" height="52" rx="6" fill="#EBF5FB" stroke="#3498DB" stroke-width="2"/>
  <text x="360" y="206" text-anchor="middle" font-size="18" font-weight="600" fill="#2D3436">核心概念</text>

  <!-- 外围节点 -->
  <rect x="300" y="50" width="120" height="44" rx="6" fill="#FFFFFF" stroke="#2D3436" stroke-width="1.5"/>
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
  <rect width="720" height="400" fill="#FFFFFF"/>

  <!-- 根节点 -->
  <rect x="280" y="100" width="160" height="48" rx="6" fill="#EBF5FB" stroke="#3498DB" stroke-width="2"/>
  <text x="360" y="130" text-anchor="middle" font-size="18" font-weight="600" fill="#2D3436">根概念</text>

  <!-- 连线 -->
  <line x1="310" y1="148" x2="190" y2="260" stroke="#2D3436" stroke-width="1.5"/>
  <line x1="360" y1="148" x2="360" y2="260" stroke="#2D3436" stroke-width="1.5"/>
  <line x1="410" y1="148" x2="530" y2="260" stroke="#2D3436" stroke-width="1.5"/>

  <!-- 子节点 -->
  <rect x="120" y="260" width="140" height="48" rx="6" fill="#FFFFFF" stroke="#2D3436" stroke-width="2"/>
  <text x="190" y="289" text-anchor="middle" font-size="18" fill="#2D3436">分支 A</text>
  <!-- ... -->
</svg>
```

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
