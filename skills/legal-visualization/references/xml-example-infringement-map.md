# 侵权对比图 XML 示例

## 用途

对比分析专利权利要求与被诉产品的技术特征，判断是否落入保护范围。展示逐项比对结果（全面覆盖原则、等同原则）。

## 布局

**左右对比** 或 **矩阵表格** 形式：
- 左侧：权利要求的技术特征
- 右侧：被诉产品的对应特征
- 中间/底部：比对结果

## XML 结构示例

```xml
<!-- 标题 -->
<mxCell id="title" value="权利要求1 侵权比对分析"
  style="text;fontSize=24;fontStyle=1;align=center;fillColor=none;strokeColor=none;"
  vertex="1" parent="1">
  <mxGeometry x="200" y="20" width="400" height="40" as="geometry"/>
</mxCell>

<!-- 表头 -->
<mxCell id="header_claim" value="权利要求特征"
  style="rounded=1;whiteSpace=wrap;fillColor=#1976D2;strokeColor=#1976D2;strokeWidth=2;fontColor=#FFFFFF;fontSize=13;fontStyle=1;align=center;"
  vertex="1" parent="1">
  <mxGeometry x="60" y="80" width="180" height="40" as="geometry"/>
</mxCell>
<mxCell id="header_result" value="比对结果"
  style="rounded=1;whiteSpace=wrap;fillColor=#7B1FA2;strokeColor=#7B1FA2;strokeWidth=2;fontColor=#FFFFFF;fontSize=13;fontStyle=1;align=center;"
  vertex="1" parent="1">
  <mxGeometry x="260" y="80" width="80" height="40" as="geometry"/>
</mxCell>
<mxCell id="header_product" value="被诉产品特征"
  style="rounded=1;whiteSpace=wrap;fillColor=#C62828;strokeColor=#C62828;strokeWidth=2;fontColor=#FFFFFF;fontSize=13;fontStyle=1;align=center;"
  vertex="1" parent="1">
  <mxGeometry x="360" y="80" width="180" height="40" as="geometry"/>
</mxCell>

<!-- 特征行1 -->
<mxCell id="c1_row" value="A. 主板集成CPU&#xa;和存储器"
  style="rounded=1;whiteSpace=wrap;fillColor=#E3F2FD;strokeColor=#1976D2;strokeWidth=1;align=left;spacingLeft=10;"
  vertex="1" parent="1">
  <mxGeometry x="60" y="130" width="180" height="50" as="geometry"/>
</mxCell>
<mxCell id="r1" value="✓"
  style="text;fontSize=20;fontColor=#43A047;align=center;fillColor=none;strokeColor=none;fontStyle=1;"
  vertex="1" parent="1">
  <mxGeometry x="260" y="130" width="80" height="50" as="geometry"/>
</mxCell>
<mxCell id="p1_row" value="产品包含CPU芯片&#xa;和存储芯片"
  style="rounded=1;whiteSpace=wrap;fillColor=#FFEBEE;strokeColor=#C62828;strokeWidth=1;align=left;spacingLeft=10;"
  vertex="1" parent="1">
  <mxGeometry x="360" y="130" width="180" height="50" as="geometry"/>
</mxCell>
<mxCell id="e1" value="对应" style="endArrow=classic;dashed=1;strokeWidth=1;strokeColor=#90A4AE;exitX=1;exitY=0.5;entryX=0;entryY=0.5;" edge="1" source="c1_row" target="r1" parent="1">
  <mxGeometry relative="1" as="geometry"/>
</mxCell>
<mxCell id="e2" value="" style="endArrow=none;dashed=1;strokeWidth=1;strokeColor=#90A4AE;exitX=1;exitY=0.5;entryX=0;entryY=0.5;" edge="1" source="r1" target="p1_row" parent="1">
  <mxGeometry relative="1" as="geometry"/>
</mxCell>

<!-- 特征行2 -->
<mxCell id="c2_row" value="B. 显示模块连接&#xa;主板"
  style="rounded=1;whiteSpace=wrap;fillColor=#E3F2FD;strokeColor=#1976D2;strokeWidth=1;align=left;spacingLeft=10;"
  vertex="1" parent="1">
  <mxGeometry x="60" y="190" width="180" height="50" as="geometry"/>
</mxCell>
<mxCell id="r2" value="≈"
  style="text;fontSize=20;fontColor=#F9A825;align=center;fillColor=none;strokeColor=none;fontStyle=1;"
  vertex="1" parent="1">
  <mxGeometry x="260" y="190" width="80" height="50" as="geometry"/>
</mxCell>
<mxCell id="p2_row" value="显示模块通过排线&#xa;连接主板（等同）"
  style="rounded=1;whiteSpace=wrap;fillColor=#FFF3E0;strokeColor=#EF6C00;strokeWidth=1;align=left;spacingLeft=10;"
  vertex="1" parent="1">
  <mxGeometry x="360" y="190" width="180" height="50" as="geometry"/>
</mxCell>

<!-- 特征行3 -->
<mxCell id="c3_row" value="C. 电源管理IC&#xa;控制功耗"
  style="rounded=1;whiteSpace=wrap;fillColor=#E3F2FD;strokeColor=#1976D2;strokeWidth=1;align=left;spacingLeft=10;"
  vertex="1" parent="1">
  <mxGeometry x="60" y="250" width="180" height="50" as="geometry"/>
</mxCell>
<mxCell id="r3" value="✗"
  style="text;fontSize=20;fontColor=#C62828;align=center;fillColor=none;strokeColor=none;fontStyle=1;"
  vertex="1" parent="1">
  <mxGeometry x="260" y="250" width="80" height="50" as="geometry"/>
</mxCell>
<mxCell id="p3_row" value="产品无电源管理IC&#xa;(功能缺失)"
  style="rounded=1;whiteSpace=wrap;fillColor=#FAFAFA;strokeColor=#BDBDBD;strokeWidth=1;align=left;spacingLeft=10;"
  vertex="1" parent="1">
  <mxGeometry x="360" y="250" width="180" height="50" as="geometry"/>
</mxCell>

<!-- 结论 -->
<mxCell id="conclusion" value="结论：未完全覆盖&#xa;→ 不构成侵权"
  style="rounded=1;whiteSpace=wrap;fillColor=#FFEBEE;strokeColor=#C62828;strokeWidth=3;fontSize=14;fontStyle=1;align=center;"
  vertex="1" parent="1">
  <mxGeometry x="200" y="320" width="200" height="60" as="geometry"/>
</mxCell>
<mxCell id="e_concl" value="" style="endArrow=classic;strokeWidth=2;strokeColor=#C62828;exitX=0.5;exitY=1;entryX=0.5;entryY=0;edgeStyle=orthogonalEdgeStyle;" edge="1" source="p3_row" target="conclusion" parent="1">
  <mxGeometry relative="1" as="geometry"/>
</mxCell>
```

## 触发词

- "侵权对比"
- "技术特征比对"
- "权利要求分析"
- "infringement comparison"
- "claim chart"

## 比对结果标注

| 符号 | 含义 | 颜色 |
|------|------|------|
| ✓ | 完全相同/等同 | 绿色 |
| ≈ | 等同替换 | 橙色 |
| ✗ | 不相同/缺失 | 红色 |
| — | 不涉及 | 灰色 |

## 布局建议

- 用**表格形式**左右对比
- 表头用深色背景（权利要求蓝色、被诉红色）
- 比对结果列居中，用大号符号标注
- 等同特征用虚线边框和橙色
- 缺失特征用灰色或删除线效果
- 底部放结论，用醒目颜色突出
