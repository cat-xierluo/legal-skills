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
- 自由布局的同坐标空间 sibling 节点建议保留至少 60px 水平/垂直间距；表格单元格、泳道分栏和模板声明的紧凑 slot 可以边界相接，但不得正面积相交。
- 容器必须使用真实 `parent` 关系，或在扁平背景框上声明 `container=1`；不能仅凭颜色或大矩形外观推断容器语义。

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

节点视觉（配色 / 线型 / 强调 / 形状）的权威映射见 `references/shape-registry.md`。0.8.1 起形状收敛为**统一圆角矩形**（菱形仅决策点，容器为背景框），放弃椭圆 / 圆柱 / 文档形 / 六边形等不规则形状。本表为速查，新增节点一律按 shape-registry 的 `visual_role` 取值；palette 色值绑定仍以本文件为准。

| 节点类型 | shape | fillColor | strokeColor | 线型 |
|---|---|---|---|---|
| 主体/当事人（原告/被告/第三人/法院/公司/自然人） | `rounded=1` | `primary_light` | `primary` | 被告/争议用 `dashed=1` |
| 合同/文书 | `rounded=1` | `#FFFDE7` | `#F9A825` | 实线 |
| 证据 | `rounded=1` | `#E8F5E9` | `#43A047` | 实线 |
| 资金/金额 | `rounded=1` | `accent_decision_light` | `accent_decision` | 实线 |
| 决策/判断（仅流程判断点） | `rhombus` | `accent_decision_light` | `accent_decision` | 实线 |
| 风险/违约/争议 | `rounded=1` | `accent_dispute_light` | `accent_dispute` | `dashed=1` |
| 裁判/结论 | `rounded=1` | `accent_dispute_light` | `accent_dispute` | 实线 |
| 程序节点 | `rounded=1` | `grey_missing_light` | `grey_missing` | 实线 |
| 时间线节点 | `rounded=1` | `primary_light` | `primary` | 实线 |
| 缺失/待补充 | `rounded=1` | `grey_missing_light` | `grey_missing` | `dashed=1` |
| 容器/泳道 | `swimlane` | `frame_bg` | `frame` | — |
| 标题 | `text` | none | none | — |
| 注释/小字 | `text` | none | none | — |

## 节点尺寸参考

以下尺寸用于自由布局的初始估算；表格、泳道和锁定模板按各自 slot 容量执行：

| 节点数 | 节点宽 | 节点高 | 水平间距 | 垂直间距 |
|---|---|---|---|---|
| 1-7 | 160 | 70 | 220 | 160 |
| 8-15 | 140 | 60 | 180 | 130 |
| 16+ | 120 | 50 | 150 | 110 |

文本容量由 `scripts/validate_drawio.py` 统一预检：全角/CJK 字符按 1.0 显示单位、半角字母数字按 0.56、标点按 0.5、空格按 0.35；显示单位乘 `fontSize` 后再计入 padding。`whiteSpace=wrap` 时按可用宽度估算换行行数和 `1.2 × fontSize` 行高；确定溢出阻断，临界容量告警。该估算不替代最终 PNG/SVG 目视检查。

edge 标签超过 8 显示单位进入人工复核，超过 14 显示单位阻断；长说明移到独立文本节点、侧栏或图例。

## 复用入口

- `references/output-workflow.md`：draw.io 生成规则引用本文件代替硬编码。
- `references/quality-checklist.md`：颜色含义检查引用本文件。
- `references/vizspec-schema.md`：关系状态样式引用本文件。
- `references/xml-reference.md`：节点样式属性引用本文件。
- `scripts/validate_drawio.py`：不校验颜色语义；校验 XML 结构、parent/容器关系、节点几何重叠、文本容量和 edge 标签风险。
- `scripts/normalize_naming.py`：引用本文件 + `naming-conventions.md`。

## 修改记录

| 日期 | 变更 | 版本 |
|---|---|---|
| 2026-07-28 | 方向修正：节点样式回退统一圆角矩形，放弃椭圆/圆柱/文档形/六边形/平行四边形/双椭圆等多形状；区分改靠配色+线型（虚线表对抗/争议）+描边粗细；菱形仅保留给决策判断点 | 0.8.1 |
| 2026-07-28 | 节点样式映射表降级为速查，权威指向 `shape-registry.md`；新增公司/法院/证据/风险/裁判/程序形状；弃用 `mxgraph.basic.person` | 0.8.0 |
| 2026-07-26 | 增加容器语义、自由布局间距例外、文本容量与 edge 标签门禁常量 | 0.7.0 |
| 2026-06-07 | 初版沉淀，源自 v0.5.1 `output-workflow.md` 行 37-39 硬编码 | 0.6.0 |
