# draw.io XML 参考

详细记录 draw.io 图表的样式属性、连线路由和容器用法。

## 基础结构

```xml
<mxGraphModel adaptiveColors="auto">
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
    <!-- 所有节点和连线从 id=2 开始，parent="1" -->
  </root>
</mxGraphModel>
```

**关键规则**：
- `id="0"` 和 `id="1"` 是保留节点，禁止删除或修改
- 所有顶层元素 `parent="1"`
- 子元素（容器内）`parent="容器id"`，使用相对坐标

## 常见样式

### 节点样式属性

| 属性 | 值 | 说明 |
|------|-----|------|
| `rounded=1` | 0/1 | 圆角 |
| `whiteSpace=wrap` | wrap | 自动换行 |
| `fillColor` | `#RRGGBB` | 背景色 |
| `strokeColor` | `#RRGGBB` | 边框色 |
| `strokeWidth` | 数值 | 边框宽度 |
| `fontColor` | `#RRGGBB` | 文字颜色 |
| `fontSize` | 数值 | 字体大小 |
| `fontStyle=1` | 0/1/2/4 | 1=粗体, 2=斜体, 4=下划线 |
| `align` | left/center/right | 水平对齐 |
| `verticalAlign` | top/middle/bottom | 垂直对齐 |
| `shadow=0` | 0/1 | 阴影 |

### 常用形状

**圆角矩形（默认）**：
```xml
style="rounded=1;whiteSpace=wrap;fillColor=#E3F2FD;strokeColor=#1976D2;strokeWidth=2;"
```

**菱形（判断/决策）**：
```xml
style="rhombus;whiteSpace=wrap;fillColor=#FFF3E0;strokeColor=#EF6C00;strokeWidth=2;"
```

**圆柱体（数据库/存储）**：
```xml
style="shape=cylinder3;whiteSpace=wrap;fillColor=#FFF3E0;strokeColor=#EF6C00;strokeWidth=2;size=12;"
```

**文档形状**：
```xml
style="shape=document;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#1976D2;strokeWidth=2;"
```

**六边形**：
```xml
style="hexagon;whiteSpace=wrap;fillColor=#E8F5E9;strokeColor=#43A047;strokeWidth=2;"
```

**人形（当事人）**：
```xml
style="shape=mxgraph.basic.person;fillColor=#E3F2FD;strokeColor=#1976D2;"
```

**时间线节点（圆形）**：
```xml
style="ellipse;whiteSpace=wrap;fillColor=#E8F5E9;strokeColor=#43A047;strokeWidth=2;"
```

## 连线（Edge）规则

**⚠️ 最重要规则：每个 edge 必须有子元素**

```xml
<!-- ❌ 错误：自闭合 edge 不会渲染 -->
<mxCell id="e1" edge="1" source="2" target="3" .../>

<!-- ✅ 正确：包含 mxGeometry 子元素 -->
<mxCell id="e1" edge="1" source="2" target="3" ...>
  <mxGeometry relative="1" as="geometry"/>
</mxCell>
```

### 正交连线（直角转弯）

```xml
<mxCell id="e1" value="标签" 
  style="endArrow=classic;strokeWidth=2;strokeColor=#78909C;exitX=1;exitY=0.5;entryX=0;entryY=0.5;edgeStyle=orthogonalEdgeStyle;curved=1;"
  edge="1" source="2" target="3" parent="1">
  <mxGeometry relative="1" as="geometry"/>
</mxCell>
```

### 箭头类型

| 类型 | style 值 |
|------|---------|
| 实心箭头 | `endArrow=classic` |
| 空心箭头 | `endArrow=classicThin` |
| 菱形 | `endArrow=diamond` |
| 无箭头（线条） | 不加 endArrow |

### 连线方向控制

**从上到下**：`exitX=0.5;exitY=1; entryX=0.5;entryY=0;`

**从左到右**：`exitX=1;exitY=0.5; entryX=0;entryY=0.5;`

**从下到上**：`exitX=0.5;exitY=0; entryX=0.5;entryY=1;`

**从右到左**：`exitX=0;exitY=0.5; entryX=1;entryY=0.5;`

### 带弯角的连线

```xml
<mxCell id="e1" style="endArrow=classic;edgeStyle=orthogonalEdgeStyle;rounded=1;" edge="1" source="2" target="3" parent="1">
  <mxGeometry relative="1" as="geometry">
    <Array as="points">
      <mxPoint x="300" y="150"/>
    </Array>
  </mxGeometry>
</mxCell>
```

## 容器（Container）

### 不可见分组容器

```xml
<mxCell id="grp1" value="" style="group;" vertex="1" parent="1">
  <mxGeometry x="60" y="80" width="600" height="300" as="geometry"/>
</mxCell>
<mxCell id="c1" value="子节点" style="..." vertex="1" parent="grp1">
  <mxGeometry x="10" y="10" width="120" height="60" as="geometry"/>
</mxCell>
```

### 泳道容器（Swimlane）

```xml
<mxCell id="lane1" value="区域名称" style="swimlane;startSize=30;fillColor=#F5F5F5;strokeColor=#BDBDBD;strokeWidth=2;" vertex="1" parent="1">
  <mxGeometry x="60" y="80" width="600" height="300" as="geometry"/>
</mxCell>
```

## 坐标系统

- **顶层元素**：从 `x=60, y=80` 开始（避免从 0,0 开始导致 viewBox 问题）
- **容器内子元素**：使用相对坐标（相对于容器的左上角）
- **网格对齐**：所有坐标为 10 的倍数

### 自动布局参数

| 节点数 | 节点宽度 | 节点高度 | 水平间距 | 垂直间距 |
|--------|---------|---------|---------|---------|
| 1-7 | 160px | 70px | 220px | 160px |
| 8-15 | 140px | 60px | 180px | 130px |
| 16+ | 120px | 50px | 150px | 110px |

### 中文宽度修正

- 纯英文：按字符数 × 10px
- 含中文：按字符数 × 16px，最小宽度 × 1.3
- 最大宽度不超过 350px

## 标题和标签

### 图表标题

```xml
<mxCell id="title" value="图表标题"
  style="text;fontSize=24;fontStyle=1;align=center;fillColor=none;strokeColor=none;fontColor=#1a1a2e;"
  vertex="1" parent="1">
  <mxGeometry x="200" y="20" width="400" height="40" as="geometry"/>
</mxCell>
```

### 技术标注（小字）

```xml
<mxCell id="label" value="补充说明"
  style="text;fontSize=10;fontColor=#757575;align=center;fillColor=none;strokeColor=none;"
  vertex="1" parent="1">
  <mxGeometry x="100" y="160" width="120" height="18" as="geometry"/>
</mxCell>
```

## 暗色模式

`mxGraphModel` 使用 `adaptiveColors="auto"` 启用自动暗色适配。

- `strokeColor`、`fillColor`、`fontColor` 使用默认颜色时自动适配
- 显式颜色在暗色模式下自动反转
- 如需手动指定：`light-dark(lightColor,darkColor)`

## 导出注意事项

### SVG viewBox 修正

导出后如果内容偏移，用文本编辑器修改 SVG 的 `viewBox` 属性：
- 找到内容实际边界（最小 x/y，最大 x+width/y+height）
- 修正为 `viewBox="minX-20 minY-10 width height"`

### 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 导出的 SVG 空白 | viewBox 偏移 | 手动修正 viewBox |
| 节点文字不换行 | 缺少 `whiteSpace=wrap` | 添加属性 |
| 连线不显示 | edge 没有 mxGeometry 子元素 | 按规则添加 |
| XML 解析错误 | 注释中有双破折号 `--` | 改用单破折号 |
