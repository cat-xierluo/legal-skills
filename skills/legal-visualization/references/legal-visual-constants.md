# 法律视觉常量

本文件沉淀 Legal Visualization 的页面、字体、布局和通用线条常量。角色、主题、事实状态、强调、密度与形状 token 的机器可读真相源是 `config/visual-role-registry.json`，不得在本文件或其他脚本重复维护另一套枚举与主题色。

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

`relations.status` 与线型/颜色必须严格对应（具体可执行值以视觉注册表为准）：

| status | 视觉表达 | 颜色 | 标签前缀 |
|---|---|---|---|
| `confirmed` | 实线、常规色 | `palette.line_solid` | 无 |
| `disputed` | 虚线、强调色 | `palette.accent_dispute` | "争议" |
| `asserted` | 虚线、主张方颜色 | `palette.primary` | "主张" |
| `inferred` | 点线、浅色 | `palette.line_dotted` | "推定" |
| `missing` | 灰色、问号、待补充标签 | `palette.grey_missing` | "待补充" |

## 节点样式映射

节点视觉的权威映射见 `config/visual-role-registry.json`，组合方法见 `references/shape-registry.md`。形状收敛为**统一圆角矩形**（菱形仅决策点，容器保留既有形状）。下表只说明语义类别，不作为主题色或默认状态的第二真相源。

| 节点类型 | shape | fillColor | strokeColor | 线型 |
|---|---|---|---|---|
| 主体/当事人/机构 | `rounded=1` | 按主题的主体/机构类别 | 按主题 | 由 `epistemic_status` 决定 |
| 合同/文书 | `rounded=1` | 按主题的文书类别 | 按主题 | 由 `epistemic_status` 决定 |
| 证据 | `rounded=1` | 按主题的证据类别 | 按主题 | 由 `epistemic_status` 决定 |
| 资金/金额 | `rounded=1` | 按主题的财务类别 | 按主题 | 由 `epistemic_status` 决定 |
| 风险/违约 | `rounded=1` | 按主题的风险类别 | 按主题 | 由 `epistemic_status` 决定 |
| 裁判/结论 | `rounded=1` | 按主题的结论类别 | 按主题 | 由 `epistemic_status` 决定 |
| 程序/时间节点 | `rounded=1` | 按主题的程序/事件类别 | 按主题 | 由 `epistemic_status` 决定 |
| 决策/判断 | `rhombus` | 按主题的决策类别 | 按主题 | 仅 `visual_role=decision` |
| 容器/泳道 | 保留 `swimlane` / `container=1` | 按主题容器类别 | 按主题 | — |
| 标题/注释 | `text` | none | none | — |

当事人角色不提供默认线型或默认强调：被告不自动虚线，原告不自动粗边。事实状态用 `epistemic_status`，阅读重点用 `emphasis` 显式声明。

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
| 2026-07-28 | 将主题与视觉语义真相源迁到 JSON 注册表；取消当事人角色推定线型/强调；本文件收敛为页面、字体和通用布局常量 | 0.8.2 |
| 2026-07-28 | 方向修正：节点样式回退统一圆角矩形，放弃椭圆/圆柱/文档形/六边形/平行四边形/双椭圆等多形状；区分改靠配色+线型（虚线表对抗/争议）+描边粗细；菱形仅保留给决策判断点 | 0.8.1 |
| 2026-07-28 | 节点样式映射表降级为速查，权威指向 `shape-registry.md`；新增公司/法院/证据/风险/裁判/程序形状；弃用 `mxgraph.basic.person` | 0.8.0 |
| 2026-07-26 | 增加容器语义、自由布局间距例外、文本容量与 edge 标签门禁常量 | 0.7.0 |
| 2026-06-07 | 初版沉淀，源自 v0.5.1 `output-workflow.md` 行 37-39 硬编码 | 0.6.0 |
