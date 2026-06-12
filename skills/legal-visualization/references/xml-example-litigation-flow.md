# 诉讼流程图 XML 示例

## 用途

展示民事诉讼或刑事诉讼各阶段的流程和流转关系。

## 布局

**从上到下** 或 **从左到右** 的阶段式布局。

## 阶段划分

### 民事诉讼标准阶段

1. **立案阶段** — 起诉、立案、送达
2. **庭前准备** — 举证、答辩、证据交换
3. **开庭审理** — 庭审、辩论
4. **裁判阶段** — 判决、裁定
5. **执行阶段** — 申请执行、强制执行

### 刑事诉讼标准阶段

1. **立案** — 报案、审查
2. **侦查** — 调查取证、拘留、逮捕
3. **审查起诉** — 检察院审查
4. **审判** — 一审、二审
5. **执行** — 生效裁判执行

## XML 结构示例

```xml
<!-- 标题 -->
<mxCell id="title" value="民事诉讼流程图"
  style="text;fontSize=24;fontStyle=1;align=center;fillColor=none;strokeColor=none;"
  vertex="1" parent="1">
  <mxGeometry x="200" y="20" width="400" height="40" as="geometry"/>
</mxCell>

<!-- 阶段1：立案 -->
<mxCell id="stage1" value="立案阶段"
  style="swimlane;startSize=30;fillColor=#E3F2FD;strokeColor=#1976D2;strokeWidth=2;fontSize=14;fontStyle=1;"
  vertex="1" parent="1">
  <mxGeometry x="60" y="80" width="200" height="120" as="geometry"/>
</mxCell>
<mxCell id="n1_1" value="起诉" style="rounded=1;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#1976D2;" vertex="1" parent="stage1">
  <mxGeometry x="10" y="40" width="80" height="40" as="geometry"/>
</mxCell>
<mxCell id="n1_2" value="立案审查" style="rounded=1;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#1976D2;" vertex="1" parent="stage1">
  <mxGeometry x="110" y="40" width="80" height="40" as="geometry"/>
</mxCell>
<mxCell id="n1_3" value="送达" style="rounded=1;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#1976D2;" vertex="1" parent="stage1">
  <mxGeometry x="60" y="90" width="80" height="40" as="geometry"/>
</mxCell>

<!-- 阶段2：庭前准备 -->
<mxCell id="stage2" value="庭前准备"
  style="swimlane;startSize=30;fillColor=#FFF3E0;strokeColor=#EF6C00;strokeWidth=2;fontSize=14;fontStyle=1;"
  vertex="1" parent="1">
  <mxGeometry x="60" y="220" width="200" height="120" as="geometry"/>
</mxCell>
<mxCell id="n2_1" value="举证" style="rounded=1;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#EF6C00;" vertex="1" parent="stage2">
  <mxGeometry x="10" y="40" width="80" height="40" as="geometry"/>
</mxCell>
<mxCell id="n2_2" value="答辩" style="rounded=1;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#EF6C00;" vertex="1" parent="stage2">
  <mxGeometry x="110" y="40" width="80" height="40" as="geometry"/>
</mxCell>

<!-- 阶段1 → 阶段2 连线 -->
<mxCell id="e1_2" value="" style="endArrow=classic;strokeWidth=2;strokeColor=#78909C;exitX=0.5;exitY=1;entryX=0.5;entryY=0;edgeStyle=orthogonalEdgeStyle;" edge="1" source="stage1" target="stage2" parent="1">
  <mxGeometry relative="1" as="geometry"/>
</mxCell>
```

## 触发词

- "诉讼流程图"
- "立案流程"
- "开庭流程"
- "民事诉讼"
- "刑事诉讼"
- "litigation flow"

## 配色方案

| 阶段类型 | fillColor | strokeColor |
|---------|-----------|-------------|
| 立案 | `#E3F2FD` | `#1976D2` |
| 庭前准备 | `#FFF3E0` | `#EF6C00` |
| 开庭审理 | `#F3E5F5` | `#7B1FA2` |
| 裁判 | `#E0F7FA` | `#00838F` |
| 执行 | `#E8F5E9` | `#43A047` |

## 布局建议

- 每个阶段用 swimlane 容器包裹
- 阶段之间用粗箭头连接
- 阶段内各步骤用虚线箭头表示顺序
- 关键节点（判决、上诉）用醒目颜色
