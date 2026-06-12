# 合同结构图 XML 示例

## 用途

展示合同的章节结构、条款层级关系，以及合同各方之间的权利义务关系。

## 布局

**树状结构** 或 **层级图**：
- 顶部：合同名称/主体
- 中间：章节/条款
- 底部：具体权利义务

## XML 结构示例

```xml
<!-- 标题 -->
<mxCell id="title" value="合同结构图"
  style="text;fontSize=24;fontStyle=1;align=center;fillColor=none;strokeColor=none;"
  vertex="1" parent="1">
  <mxGeometry x="200" y="20" width="400" height="40" as="geometry"/>
</mxCell>

<!-- 合同主体（顶部） -->
<mxCell id="contract" value="《合同名称》"
  style="rounded=1;whiteSpace=wrap;fillColor=#E3F2FD;strokeColor=#1976D2;strokeWidth=3;fontSize=16;fontStyle=1;"
  vertex="1" parent="1">
  <mxGeometry x="200" y="80" width="200" height="60" as="geometry"/>
</mxCell>

<!-- 章节容器 -->
<mxCell id="chapters" value="" style="group;" vertex="1" parent="1">
  <mxGeometry x="60" y="160" width="480" height="200" as="geometry"/>
</mxCell>

<!-- 第一章 -->
<mxCell id="ch1" value="第一章 总则"
  style="rounded=1;whiteSpace=wrap;fillColor=#E8F5E9;strokeColor=#43A047;strokeWidth=2;fontSize=13;fontStyle=1;"
  vertex="1" parent="chapters">
  <mxGeometry x="0" y="0" width="140" height="80" as="geometry"/>
</mxCell>
<mxCell id="ch1_art1" value="第一条 目的" style="rounded=1;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#43A047;" vertex="1" parent="chapters">
  <mxGeometry x="10" y="35" width="120" height="35" as="geometry"/>
</mxCell>
<mxCell id="ch1_art2" value="第二条 原则" style="rounded=1;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#43A047;" vertex="1" parent="chapters">
  <mxGeometry x="10" y="75" width="120" height="35" as="geometry"/>
</mxCell>

<!-- 第二章 -->
<mxCell id="ch2" value="第二章 各方权利义务"
  style="rounded=1;whiteSpace=wrap;fillColor=#FFF3E0;strokeColor=#EF6C00;strokeWidth=2;fontSize=13;fontStyle=1;"
  vertex="1" parent="chapters">
  <mxGeometry x="170" y="0" width="140" height="80" as="geometry"/>
</mxCell>
<mxCell id="ch2_art3" value="甲方权利义务" style="rounded=1;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#EF6C00;" vertex="1" parent="chapters">
  <mxGeometry x="180" y="35" width="120" height="35" as="geometry"/>
</mxCell>
<mxCell id="ch2_art4" value="乙方权利义务" style="rounded=1;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#EF6C00;" vertex="1" parent="chapters">
  <mxGeometry x="180" y="75" width="120" height="35" as="geometry"/>
</mxCell>

<!-- 第三章 -->
<mxCell id="ch3" value="第三章 违约责任"
  style="rounded=1;whiteSpace=wrap;fillColor=#FFEBEE;strokeColor=#C62828;strokeWidth=2;fontSize=13;fontStyle=1;"
  vertex="1" parent="chapters">
  <mxGeometry x="340" y="0" width="140" height="80" as="geometry"/>
</mxCell>
<mxCell id="ch3_art5" value="违约情形" style="rounded=1;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#C62828;" vertex="1" parent="chapters">
  <mxGeometry x="350" y="35" width="120" height="35" as="geometry"/>
</mxCell>
<mxCell id="ch3_art6" value="违约责任" style="rounded=1;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#C62828;" vertex="1" parent="chapters">
  <mxGeometry x="350" y="75" width="120" height="35" as="geometry"/>
</mxCell>

<!-- 合同 → 各章 连线 -->
<mxCell id="e1" value="" style="endArrow=classic;strokeWidth=2;strokeColor=#78909C;exitX=0.5;exitY=1;entryX=0.2;entryY=0;edgeStyle=orthogonalEdgeStyle;" edge="1" source="contract" target="ch1" parent="1">
  <mxGeometry relative="1" as="geometry"/>
</mxCell>
<mxCell id="e2" value="" style="endArrow=classic;strokeWidth=2;strokeColor=#78909C;exitX=0.5;exitY=1;entryX=0.5;entryY=0;edgeStyle=orthogonalEdgeStyle;" edge="1" source="contract" target="ch2" parent="1">
  <mxGeometry relative="1" as="geometry"/>
</mxCell>
<mxCell id="e3" value="" style="endArrow=classic;strokeWidth=2;strokeColor=#78909C;exitX=0.5;exitY=1;entryX=0.8;entryY=0;edgeStyle=orthogonalEdgeStyle;" edge="1" source="contract" target="ch3" parent="1">
  <mxGeometry relative="1" as="geometry"/>
</mxCell>
```

## 触发词

- "合同结构"
- "合同条款"
- "合同章节"
- "contract structure"
- "contract outline"

## 配色方案

| 章节类型 | fillColor | strokeColor |
|---------|-----------|-------------|
| 合同名称 | `#E3F2FD` | `#1976D2` |
| 总则/定义 | `#E8F5E9` | `#43A047` |
| 权利义务 | `#FFF3E0` | `#EF6C00` |
| 违约责任 | `#FFEBEE` | `#C62828` |
| 争议解决 | `#F3E5F5` | `#7B1FA2` |
| 附则 | `#E0F7FA` | `#00838F` |

## 布局建议

- 用**树状布局**展示层级关系
- 章节用大矩形，条款用小矩形嵌套在内
- 各方权利义务可用**泳道**分隔
- 关键条款（违约金、保密等）用醒目颜色
- 条款编号和名称同时显示
