# 案件时间轴 XML 示例

## 用途

展示案件的**关键时间节点**，包括：侵权行为发生时间、权利人发现时间、起诉时间、法院审理时间轴等。清晰展示时效分析和程序推进。

## 布局

**从左到右** 的水平时间轴，或**从上到下**的垂直时间轴。

## XML 结构示例

```xml
<!-- 标题 -->
<mxCell id="title" value="案件时间轴"
  style="text;fontSize=24;fontStyle=1;align=center;fillColor=none;strokeColor=none;"
  vertex="1" parent="1">
  <mxGeometry x="200" y="20" width="400" height="40" as="geometry"/>
</mxCell>

<!-- 时间轴基线 -->
<mxCell id="timeline" value="" style="endArrow=none;strokeWidth=3;strokeColor=#78909C;" edge="1" parent="1">
  <mxGeometry relative="1" as="geometry">
    <mxPoint x="60" y="180" as="sourcePoint"/>
    <mxPoint x="740" y="180" as="targetPoint"/>
  </mxGeometry>
</mxCell>

<!-- 时间点1：侵权行为 -->
<mxCell id="t1_dot" value="" style="ellipse;fillColor=#C62828;strokeColor=#C62828;strokeWidth=2;" vertex="1" parent="1">
  <mxGeometry x="80" y="165" width="30" height="30" as="geometry"/>
</mxCell>
<mxCell id="t1_label" value="2023-01-15&#xa;侵权行为发生"
  style="text;fontSize=12;fontColor=#C62828;align=center;fillColor=none;strokeColor=none;"
  vertex="1" parent="1">
  <mxGeometry x="55" y="200" width="80" height="40" as="geometry"/>
</mxCell>
<mxCell id="t1_marker" value="侵权日" style="rounded=1;whiteSpace=wrap;fillColor=#FFEBEE;strokeColor=#C62828;strokeWidth=2;fontSize=10;" vertex="1" parent="1">
  <mxGeometry x="55" y="135" width="80" height="25" as="geometry"/>
</mxCell>

<!-- 时间点2：发现侵权 -->
<mxCell id="t2_dot" value="" style="ellipse;fillColor=#EF6C00;strokeColor=#EF6C00;strokeWidth=2;" vertex="1" parent="1">
  <mxGeometry x="220" y="165" width="30" height="30" as="geometry"/>
</mxCell>
<mxCell id="t2_label" value="2023-06-20&#xa;权利人发现"
  style="text;fontSize=12;fontColor=#EF6C00;align=center;fillColor=none;strokeColor=none;"
  vertex="1" parent="1">
  <mxGeometry x="195" y="200" width="80" height="40" as="geometry"/>
</mxCell>
<mxCell id="t2_marker" value="发现日" style="rounded=1;whiteSpace=wrap;fillColor=#FFF3E0;strokeColor=#EF6C00;strokeWidth=2;fontSize=10;" vertex="1" parent="1">
  <mxGeometry x="195" y="135" width="80" height="25" as="geometry"/>
</mxCell>

<!-- 时间点3：起诉 -->
<mxCell id="t3_dot" value="" style="ellipse;fillColor=#1976D2;strokeColor=#1976D2;strokeWidth=2;" vertex="1" parent="1">
  <mxGeometry x="400" y="165" width="30" height="30" as="geometry"/>
</mxCell>
<mxCell id="t3_label" value="2023-09-01&#xa;起诉立案"
  style="text;fontSize=12;fontColor=#1976D2;align=center;fillColor=none;strokeColor=none;"
  vertex="1" parent="1">
  <mxGeometry x="375" y="200" width="80" height="40" as="geometry"/>
</mxCell>
<mxCell id="t3_marker" value="起诉日" style="rounded=1;whiteSpace=wrap;fillColor=#E3F2FD;strokeColor=#1976D2;strokeWidth=2;fontSize=10;" vertex="1" parent="1">
  <mxGeometry x="375" y="135" width="80" height="25" as="geometry"/>
</mxCell>

<!-- 时间点4：判决 -->
<mxCell id="t4_dot" value="" style="ellipse;fillColor=#43A047;strokeColor=#43A047;strokeWidth=2;" vertex="1" parent="1">
  <mxGeometry x="580" y="165" width="30" height="30" as="geometry"/>
</mxCell>
<mxCell id="t4_label" value="2024-03-15&#xa;一审判决"
  style="text;fontSize=12;fontColor=#43A047;align=center;fillColor=none;strokeColor=none;"
  vertex="1" parent="1">
  <mxGeometry x="555" y="200" width="80" height="40" as="geometry"/>
</mxCell>
<mxCell id="t4_marker" value="判决日" style="rounded=1;whiteSpace=wrap;fillColor=#E8F5E9;strokeColor=#43A047;strokeWidth=2;fontSize=10;" vertex="1" parent="1">
  <mxGeometry x="555" y="135" width="80" height="25" as="geometry"/>
</mxCell>

<!-- 时间点5：生效 -->
<mxCell id="t5_dot" value="" style="ellipse;fillColor=#7B1FA2;strokeColor=#7B1FA2;strokeWidth=2;" vertex="1" parent="1">
  <mxGeometry x="700" y="165" width="30" height="30" as="geometry"/>
</mxCell>
<mxCell id="t5_label" value="2024-04-01&#xa;判决生效"
  style="text;fontSize=12;fontColor=#7B1FA2;align=center;fillColor=none;strokeColor=none;"
  vertex="1" parent="1">
  <mxGeometry x="675" y="200" width="80" height="40" as="geometry"/>
</mxCell>

<!-- 时效标注（虚线区域） -->
<mxCell id="statute_bar" value="3年诉讼时效&#xa;(2026-01-15届满)"
  style="rounded=1;whiteSpace=wrap;fillColor=#FFF8E1;strokeColor=#F9A825;strokeWidth=2;dashed=1;fontSize=11;"
  vertex="1" parent="1">
  <mxGeometry x="80" y="250" width="200" height="50" as="geometry"/>
</mxCell>
<mxCell id="e_statute" value="" style="endArrow=none;dashed=1;strokeWidth=1;strokeColor=#F9A825;exitX=0.5;exitY=0;entryX=0.5;entryY=0;edgeStyle=orthogonalEdgeStyle;" edge="1" source="statute_bar" target="timeline" parent="1">
  <mxGeometry relative="1" as="geometry"/>
</mxCell>
```

## 触发词

- "案件时间轴"
- "timeline"
- "时间节点"
- "案件经过"
- "时效分析"

## 关键时间点类型

| 类型 | 说明 | 样式建议 |
|------|------|---------|
| 侵权日 | 侵权行为发生之日 | 红色，醒目 |
| 发现日 | 权利人知道或应当知道之日 | 橙色 |
| 起诉日 | 立案之日 | 蓝色 |
| 判决日 | 裁判作出之日 | 绿色 |
| 生效日 | 裁判生效之日 | 紫色 |
| 时效届满日 | 诉讼时效截止日 | 金色，虚线 |

## 布局建议

- 时间轴用**水平实线**，两端带箭头
- 时间点用**圆形节点**标记在轴上
- 时间点上方/下方交替放置日期和事件描述
- 时效期间用**虚线框**或**阴影区域**表示
- 时间点间距根据时间跨度和重要性调整
