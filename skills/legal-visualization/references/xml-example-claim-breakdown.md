# 权利要求分解图 XML 示例

## 用途

展示专利权利要求的**层次结构**，包括独立权利要求和从属权利要求的引用关系。帮助理解权利要求的技术方案组成和保护范围。

## 布局

**树状结构**：
- 顶部：独立权利要求（Claim 1）
- 下方：从属权利要求（Claim 2、3...）
- 引用关系用箭头连接

## XML 结构示例

```xml
<!-- 标题 -->
<mxCell id="title" value="权利要求结构分解"
  style="text;fontSize=24;fontStyle=1;align=center;fillColor=none;strokeColor=none;"
  vertex="1" parent="1">
  <mxGeometry x="200" y="20" width="400" height="40" as="geometry"/>
</mxCell>

<!-- 独立权利要求1 -->
<mxCell id="clm1" value="权利要求1&#xa;（独立权利要求）"
  style="rounded=1;whiteSpace=wrap;fillColor=#E3F2FD;strokeColor=#1976D2;strokeWidth=3;fontSize=14;fontStyle=1;align=center;"
  vertex="1" parent="1">
  <mxGeometry x="200" y="80" width="200" height="60" as="geometry"/>
</mxCell>

<!-- 技术特征分解（独立权利要求内含） -->
<mxCell id="clm1_features" value="" style="group;" vertex="1" parent="1">
  <mxGeometry x="80" y="160" width="440" height="80" as="geometry"/>
</mxCell>
<mxCell id="f1" value="特征A" style="rounded=1;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#1976D2;fontSize=11;" vertex="1" parent="clm1_features">
  <mxGeometry x="0" y="0" width="100" height="35" as="geometry"/>
</mxCell>
<mxCell id="f2" value="特征B" style="rounded=1;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#1976D2;fontSize=11;" vertex="1" parent="clm1_features">
  <mxGeometry x="115" y="0" width="100" height="35" as="geometry"/>
</mxCell>
<mxCell id="f3" value="特征C" style="rounded=1;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#1976D2;fontSize=11;" vertex="1" parent="clm1_features">
  <mxGeometry x="230" y="0" width="100" height="35" as="geometry"/>
</mxCell>
<mxCell id="f4" value="特征D" style="rounded=1;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#1976D2;fontSize=11;" vertex="1" parent="clm1_features">
  <mxGeometry x="345" y="0" width="100" height="35" as="geometry"/>
</mxCell>

<!-- 从属权利要求2 -->
<mxCell id="clm2" value="权利要求2&#xa;（引用1）"
  style="rounded=1;whiteSpace=wrap;fillColor=#E8F5E9;strokeColor=#43A047;strokeWidth=2;fontSize=13;fontStyle=1;align=center;"
  vertex="1" parent="1">
  <mxGeometry x="80" y="260" width="140" height="60" as="geometry"/>
</mxCell>
<mxCell id="clm2_add" value="+特征E" style="rounded=1;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#43A047;fontSize=11;" vertex="1" parent="1">
  <mxGeometry x="90" y="330" width="120" height="30" as="geometry"/>
</mxCell>

<!-- 从属权利要求3 -->
<mxCell id="clm3" value="权利要求3&#xa;（引用1+2）"
  style="rounded=1;whiteSpace=wrap;fillColor=#FFF3E0;strokeColor=#EF6C00;strokeWidth=2;fontSize=13;fontStyle=1;align=center;"
  vertex="1" parent="1">
  <mxGeometry x="280" y="260" width="140" height="60" as="geometry"/>
</mxCell>
<mxCell id="clm3_add" value="+特征F" style="rounded=1;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#EF6C00;fontSize=11;" vertex="1" parent="1">
  <mxGeometry x="290" y="330" width="120" height="30" as="geometry"/>
</mxCell>

<!-- 从属权利要求4 -->
<mxCell id="clm4" value="权利要求4&#xa;（引用1）"
  style="rounded=1;whiteSpace=wrap;fillColor=#F3E5F5;strokeColor=#7B1FA2;strokeWidth=2;fontSize=13;fontStyle=1;align=center;"
  vertex="1" parent="1">
  <mxGeometry x="480" y="260" width="140" height="60" as="geometry"/>
</mxCell>
<mxCell id="clm4_add" value="+特征G" style="rounded=1;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#7B1FA2;fontSize=11;" vertex="1" parent="1">
  <mxGeometry x="490" y="330" width="120" height="30" as="geometry"/>
</mxCell>

<!-- 连线：独立→从属 -->
<mxCell id="e1_2" value="" style="endArrow=classic;strokeWidth=2;strokeColor=#78909C;exitX=0.2;exitY=1;entryX=0.5;entryY=0;edgeStyle=orthogonalEdgeStyle;" edge="1" source="clm1" target="clm2" parent="1">
  <mxGeometry relative="1" as="geometry"/>
</mxCell>
<mxCell id="e1_3" value="" style="endArrow=classic;strokeWidth=2;strokeColor=#78909C;exitX=0.5;exitY=1;entryX=0.5;entryY=0;edgeStyle=orthogonalEdgeStyle;" edge="1" source="clm1" target="clm3" parent="1">
  <mxGeometry relative="1" as="geometry"/>
</mxCell>
<mxCell id="e1_4" value="" style="endArrow=classic;strokeWidth=2;strokeColor=#78909C;exitX=0.8;exitY=1;entryX=0.5;entryY=0;edgeStyle=orthogonalEdgeStyle;" edge="1" source="clm1" target="clm4" parent="1">
  <mxGeometry relative="1" as="geometry"/>
</mxCell>

<!-- 引用关系标注 -->
<mxCell id="ref_2_3" value="引用2" style="text;fontSize=9;fontColor=#757575;align=center;fillColor=none;strokeColor=none;" vertex="1" parent="1">
  <mxGeometry x="180" y="290" width="40" height="20" as="geometry"/>
</mxCell>
```

## 触发词

- "权利要求分解"
- "claim chart"
- "权利要求结构"
- "专利权利要求"
- "claim breakdown"

## 配色方案

| 权利要求类型 | fillColor | strokeColor |
|------------|-----------|-------------|
| 独立权利要求 | `#E3F2FD` | `#1976D2`（粗边框）|
| 从属权利要求(引用1) | `#E8F5E9` | `#43A047` |
| 从属权利要求(引用1+2) | `#FFF3E0` | `#EF6C00` |
| 从属权利要求(引用1+3) | `#F3E5F5` | `#7B1FA2` |
| 附加技术特征 | `#FFFFFF` | 对应颜色 |

## 布局建议

- 独立权利要求用**粗边框**突出
- 从属权利要求按引用关系分行/列排列
- 每个权利要求下方显示其**附加的技术特征**
- 用**虚线箭头**表示引用关系
- 权利要求编号和"引用X"同时标注
- 特征分解用小矩形横向排列
