# 法律视觉常量

本文件沉淀 Legal Visualization 的视觉系统常量。所有 `.drawio` 模板与 `scripts/*.py` 必须按本文件取值；如需变更，先改本文件再传播。

## 设计原则

- **一图一观点**：每张图服务一个核心观点。节点颜色、线型、强调色必须服务该观点。
- **颜色含义优先**：所有颜色都是语义符号，不是装饰。同主体同色，同状态同型，争议/风险用强调色，缺失用灰色。
- **强调色不超 3 个**：主色 + 决策橙 + 争议/缺失红灰。本文件只定义 4 个色板值。

## 页面与画布

```yaml
page:
  paper: A4
  orientation: portrait
  margin_cm: { top: 2.54, bottom: 2.54, left: 3.18, right: 3.18 }
  usable_width_cm: 14.64
  dpi: 260
  grid_unit_px: 10
  origin: { x: 60, y: 80 }
  grid_step: 60
```

- 节点坐标从 `x=60, y=80` 开始画，避免 SVG viewBox 偏移（与 `xml-reference.md` 行 155 一致）。
- 节点间最小水平/垂直间距 60px；同层级节点尺寸一致。

## 字体

```yaml
font:
  family: "Microsoft YaHei, SimHei, PingFang SC, sans-serif"
  size_title_pt: 24       # 图表主标题
  size_subtitle_pt: 14    # 副标题、结论栏
  size_node_pt: 14        # 节点正文
  size_caption_pt: 12     # 注释、证据编号
  size_legend_pt: 10      # 图例、技术标注
  weight_bold: 1          # drawio fontStyle: 1=粗体, 2=斜体, 4=下划线
```

## 调色板

```yaml
palette:
  primary:        "#1f77b4"  # 主色：同主体、合同主线、确认事实
  primary_light:  "#E3F2FD"  # 主色浅底：节点填充
  accent_decision: "#FF8C00"  # 强调-决策：菱形/判断节点
  accent_decision_light: "#FFF3E0"
  accent_dispute: "#C0392B"  # 强调-争议：争议事实、违约、风险
  accent_dispute_light: "#FDECEA"
  grey_missing:   "#9E9E9E"  # 缺失/待补充/未提及
  grey_missing_light: "#F5F5F5"
  line_solid:     "#333333"  # 已证关系实线
  line_dashed:    "#666666"  # 主张/推定虚线
  line_dotted:    "#9E9E9E"  # 推定/待证点线
  text_primary:   "#1a1a2e"  # 主文字色
  text_caption:   "#757575"  # 注释/小字色
  frame:          "#BDBDBD"  # 容器/泳道边框
  frame_bg:       "#F5F5F5"  # 容器/泳道底色
```

## 线型与状态绑定

`relations.status` 与线型/颜色必须严格对应（与 `vizspec-schema.md` 行 103-111 一致）：

| status | 视觉表达 | 颜色 | 标签前缀 |
|---|---|---|---|
| `confirmed` | 实线、常规色 | `palette.line_solid` | 无 |
| `disputed` | 虚线、强调色 | `palette.accent_dispute` | "争议" |
| `asserted` | 虚线、主张方颜色 | `palette.primary` | "主张" |
| `inferred` | 点线、浅色 | `palette.line_dotted` | "推定" |
| `missing` | 灰色、问号、待补充标签 | `palette.grey_missing` | "待补充" |

## 节点样式映射

| 节点类型 | shape | fillColor | strokeColor |
|---|---|---|---|
| 主体/当事人 | `mxgraph.basic.person` 或 `rounded=1` | `primary_light` | `primary` |
| 合同/协议 | `shape=document` | `#FFFFFF` | `primary` |
| 资金/票据/货物 | `shape=cylinder3` | `accent_decision_light` | `accent_decision` |
| 决策/判断 | `rhombus` | `accent_decision_light` | `accent_decision` |
| 时间线节点 | `ellipse` | `#E8F5E9` | `#43A047` |
| 缺失/待补充 | `rounded=1` | `grey_missing_light` | `grey_missing` |
| 容器/泳道 | `swimlane` | `frame_bg` | `frame` |
| 标题 | `text` | none | none |
| 注释/小字 | `text` | none | none |

## 节点尺寸参考

继承 `xml-reference.md` 行 161-165 的自动布局参数，叠加中文宽度修正（行 168-172）：

| 节点数 | 节点宽 | 节点高 | 水平间距 | 垂直间距 |
|---|---|---|---|---|
| 1-7 | 160 | 70 | 220 | 160 |
| 8-15 | 140 | 60 | 180 | 130 |
| 16+ | 120 | 50 | 150 | 110 |

中文节点宽度 = 字符数 × 16px，最小宽度 × 1.3，最大不超过 350px。

## 复用入口

- `references/output-workflow.md`：draw.io 生成规则引用本文件代替硬编码。
- `references/quality-checklist.md`：颜色含义检查引用本文件。
- `references/vizspec-schema.md`：关系状态样式引用本文件。
- `references/xml-reference.md`：节点样式属性引用本文件。
- `scripts/validate_drawio.py`：不校验颜色值（语义层），只校验 XML 结构。
- `scripts/normalize_naming.py`：引用本文件 + `naming-conventions.md`。

## 修改记录

| 日期 | 变更 | 版本 |
|---|---|---|
| 2026-06-07 | 初版沉淀，源自 v0.5.1 `output-workflow.md` 行 37-39 硬编码 | 0.6.0 |
