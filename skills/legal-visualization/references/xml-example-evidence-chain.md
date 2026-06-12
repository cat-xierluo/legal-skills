# 证据链图 XML 示例

## 用途

展示证据之间的关系、证明方向和逻辑链条。用于分析案件中各证据如何相互印证、共同证明待证事实。

## 核心概念

- **证据节点**：具体证据（书证、物证、证人证言等）
- **证明方向**：证据指向的待证事实
- **印证关系**：证据之间的相互支持关系

## 布局

**从左到右** 或 **从下到上** 的层级布局：
- 左侧/下方：各类证据
- 中间：证明过程
- 右侧/上方：待证事实

## 证据分类样式

| 证据类型 | 形状 | fillColor | strokeColor |
|---------|------|-----------|-------------|
| 书证 | 文档形 | `#E3F2FD` | `#1976D2` |
| 物证 | 六边形 | `#FFF3E0` | `#EF6C00` |
| 证人证言 | 菱形 | `#F3E5F5` | `#7B1FA2` |
| 当事人陈述 | 圆角矩形 | `#E8F5E9` | `#43A047` |
| 鉴定意见 | 圆柱体 | `#E0F7FA` | `#00838F` |
| 电子数据 | 平行四边形 | `#FFF8E1` | `#F9A825` |

## XML 结构示例

```xml
<!-- 标题 -->
<mxCell id="title" value="证据链关系图"
  style="text;fontSize=24;fontStyle=1;align=center;fillColor=none;strokeColor=none;"
  vertex="1" parent="1">
  <mxGeometry x="200" y="20" width="400" height="40" as="geometry"/>
</mxCell>

<!-- 证据组容器 -->
<mxCell id="evidence_group" value="证据"
  style="swimlane;startSize=30;fillColor=#F5F5F5;strokeColor=#BDBDBD;strokeWidth=2;fontSize=14;fontStyle=1;"
  vertex="1" parent="1">
  <mxGeometry x="60" y="80" width="280" height="200" as="geometry"/>
</mxCell>

<!-- 书证 -->
<mxCell id="ev1" value="合同原件&#xa;（书证）" style="shape=document;whiteSpace=wrap;fillColor=#E3F2FD;strokeColor=#1976D2;strokeWidth=2;" vertex="1" parent="evidence_group">
  <mxGeometry x="20" y="50" width="100" height="60" as="geometry"/>
</mxCell>

<!-- 物证 -->
<mxCell id="ev2" value="侵权产品&#xa;（物证）" style="hexagon;whiteSpace=wrap;fillColor=#FFF3E0;strokeColor=#EF6C00;strokeWidth=2;" vertex="1" parent="evidence_group">
  <mxGeometry x="150" y="50" width="100" height="60" as="geometry"/>
</mxCell>

<!-- 证人证言 -->
<mxCell id="ev3" value="证人A证言&#xa;（证人）" style="rhombus;whiteSpace=wrap;fillColor=#F3E5F5;strokeColor=#7B1FAFA;strokeWidth=2;" vertex="1" parent="evidence_group">
  <mxGeometry x="85" y="130" width="100" height="60" as="geometry"/>
</mxCell>

<!-- 待证事实 -->
<mxCell id="fact" value="待证事实：&#xa;被告侵权行为"
  style="rounded=1;whiteSpace=wrap;fillColor=#FFEBEE;strokeColor=#C62828;strokeWidth=3;fontSize=14;fontStyle=1;"
  vertex="1" parent="1">
  <mxGeometry x="400" y="120" width="160" height="80" as="geometry"/>
</mxCell>

<!-- 证据 → 待证事实 连线 -->
<mxCell id="e1" value="证明" style="endArrow=classic;strokeWidth=2;strokeColor=#78909C;exitX=1;exitY=0.5;entryX=0;entryY=0.3;edgeStyle=orthogonalEdgeStyle;" edge="1" source="ev1" target="fact" parent="1">
  <mxGeometry relative="1" as="geometry"/>
</mxCell>
<mxCell id="e2" value="证明" style="endArrow=classic;strokeWidth=2;strokeColor=#78909C;exitX=1;exitY=0.5;entryX=0;entryY=0.7;edgeStyle=orthogonalEdgeStyle;" edge="1" source="ev2" target="fact" parent="1">
  <mxGeometry relative="1" as="geometry"/>
</mxCell>

<!-- 证据之间印证关系 -->
<mxCell id="e3" value="印证" style="endArrow=classic;dashed=1;strokeWidth=1;strokeColor=#90A4AE;exitX=0.5;exitY=1;entryX=0.5;entryY=0;edgeStyle=orthogonalEdgeStyle;" edge="1" source="ev1" target="ev3" parent="1">
  <mxGeometry relative="1" as="geometry"/>
</mxCell>
```

## 触发词

- "证据链"
- "证据关系"
- "举证"
- "证明"
- "证据目录"
- "evidence chain"

## 布局建议

- 用 swimlane 容器将证据分组
- 用**实线箭头**表示证明方向（证据 → 待证事实）
- 用**虚线箭头**表示印证关系（证据 ↔ 证据）
- 待证事实用醒目颜色突出（红色边框）
- 证据数量多时按类型分行排列
