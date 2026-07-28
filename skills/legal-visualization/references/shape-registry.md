# 形状注册表（Shape Registry）

法律语义 → 视觉角色（`visual_role`）→ 形状 token（`shape_token`）→ drawio 样式 → 配色的权威映射。VizSpec 声明 `visual_role` 后，按本表注入形状样式，再生成或实例化 `.drawio`。

本文件是节点视觉的**单一真相源**。`legal-visual-constants.md` 的"节点样式映射"速查表、`xml-reference.md` 的形状示例、模板与新写 XML 的样式注入，都以本表为准。

## 设计原则

1. **形状即语义**：每种几何形状对应一类法律语义，不是装饰。读者不看图例也能猜出"六边形大概是公权力机关"。
2. **三维度区分**：几何形状 + 配色 + 描边/字号（`emphasis`）。**不依赖 emoji**。
3. **emoji opt-in**：默认 `icon_mode=off`，不渲染任何 emoji；用户显式声明 `icons: true` 或单节点 `icon` 时才出。法律图保持严肃，emoji 会降低正式感。
4. **原生形状优先**：只用 drawio 原生几何形状（`rounded`、`ellipse`、`rhombus`、`hexagon`、`shape=document`、`shape=cylinder3`、`shape=parallelogram`、`doubleEllipse`、`swimlane`）。**不用** `mxgraph.basic.person` 等依赖外部 stencil 的形状，避免 SVG/PNG 导出缺图。
5. **复用 palette，区分两类颜色**：
   - **强调色**（≤3）：`primary` 蓝、`accent_decision` 橙、`accent_dispute` 红。只给 `emphasis: high` 与争议/风险/决策节点用。
   - **分类辅色**：法院金、监管深蓝、证据绿等浅底，用于区分语义类别，不计入"强调色不超 3 个"。
6. **一图一观点仍优先**：registry 是全集，具体一张图只用其中子集；多主体关系图主要落到主体/文书/资金/风险几类，不要把 9 类全堆进一张图。

## 视觉角色总表

| `visual_role` | 法律语义 | shape_token | drawio 几何 | 默认填充 | 默认描边 | 可选 emoji（opt-in） |
|---|---|---|---|---|---|---|
| `plaintiff` | 原告 | `actor_rounded` | 圆角矩形 `rounded=1` | `#E3F2FD` | `#1f77b4` | 👤 |
| `defendant` | 被告 | `actor_rounded` | 圆角矩形（可叠 `dashed=1`） | `#E3F2FD` | `#1f77b4` | 👤 |
| `third_party` | 第三人 | `actor_ellipse` | 椭圆 `ellipse` | `#E3F2FD` | `#1f77b4` | 👥 |
| `witness` | 证人/鉴定人 | `actor_ellipse` | 椭圆 `ellipse` | `#F5F5F5` | `#9E9E9E` | 👥 |
| `person` | 自然人（泛指） | `actor_rounded` | 圆角矩形 `rounded=1` | `#E3F2FD` | `#1f77b4` | 👤 |
| `company` | 公司/法人 | `actor_rect` | 矩形方角（默认） | `#FFFFFF` | `#1f77b4` | 🏢 |
| `court` | 法院/裁判机关 | `org_hexagon` | 六边形 `hexagon` | `#FFF8E1` | `#F9A825` | 🏛 |
| `authority` | 监管/行政部门 | `org_rect` | 矩形方角 | `#E3F2FD` | `#1565C0` | ⚖️ |
| `contract` | 合同/协议 | `doc_document` | 文档形 `shape=document` | `#FFFFFF` | `#1f77b4` | 📄 |
| `legal_doc` | 判决/律师函/法律文书 | `doc_document` | 文档形 `shape=document` | `#FFF3E0` | `#FF8C00` | ✍️ |
| `evidence` | 证据 | `evidence_parallelogram` | 平行四边形 `shape=parallelogram` | `#E8F5E9` | `#43A047` | 📋 |
| `amount` | 金额/标的/资金 | `money_cylinder` | 圆柱 `shape=cylinder3` | `#FFF3E0` | `#FF8C00` | 💰 |
| `risk` | 风险/违约/争议点 | `risk_rhombus` | 菱形 `rhombus` | `#FDECEA` | `#C0392B` | ⚠️ |
| `judgment` | 裁判/结论 | `judgment_double` | 双椭圆 `doubleEllipse` | `#FDECEA` | `#C0392B` | ⚖️ |
| `procedure` | 程序节点（立案/开庭/执行） | `procedure_capsule` | 胶囊 `rounded=1;arcSize=50` | `#F5F5F5` | `#9E9E9E` | 🔄 |
| `event` | 时间事件 | `event_ellipse` | 椭圆（小号）`ellipse` | `#E8F5E9` | `#43A047` | 📅 |
| `section` | 分区/阵营/阶段背景 | `container_swimlane` | 泳道 `swimlane` 或背景框 `container=1` | `#F5F5F5` | `#BDBDBD` | — |
| `lane` | 泳道（按角色/阶段分栏） | `container_swimlane` | 泳道 `swimlane` | `#F5F5F5` | `#BDBDBD` | — |

> 配色与 `legal-visual-constants.md` palette 对齐：`#E3F2FD/#1f77b4` = primary，`#FFF3E0/#FF8C00` = accent_decision，`#FDECEA/#C0392B` = accent_dispute，`#F5F5F5/#9E9E9E` = grey_missing，`#F5F5F5/#BDBDBD` = frame。法院金 `#FFF8E1/#F9A825`、监管深蓝 `#1565C0`、证据/时间绿 `#E8F5E9/#43A047` 为分类辅色。

## 各 token 的 drawio 样式串

以下样式串可直接写入 `mxCell` 的 `style` 属性。`fontSize` 按 `legal-visual-constants.md` 字体表取值（节点正文 14，小字 12）；`emphasis` 影响见下节。

**主体·自然人**（`plaintiff` / `person`）：
```
rounded=1;whiteSpace=wrap;fillColor=#E3F2FD;strokeColor=#1f77b4;strokeWidth=2;fontSize=14;
```

**被告**（`defendant`，叠加虚线描边表示对抗/待定）：
```
rounded=1;whiteSpace=wrap;fillColor=#E3F2FD;strokeColor=#1f77b4;strokeWidth=2;dashed=1;fontSize=14;
```

**第三人 / 证人**（`third_party` / `witness`，椭圆与原告被告区分）：
```
ellipse;whiteSpace=wrap;fillColor=#E3F2FD;strokeColor=#1f77b4;strokeWidth=2;fontSize=14;
```

**公司 / 法人**（`company`，方角矩形与自然人圆角区分）：
```
whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#1f77b4;strokeWidth=2;fontSize=14;
```

**法院 / 裁判机关**（`court`，六边形 + 金色，权威语义）：
```
hexagon;whiteSpace=wrap;fillColor=#FFF8E1;strokeColor=#F9A825;strokeWidth=2;fontSize=14;
```

**监管 / 行政部门**（`authority`，方角 + 深蓝）：
```
whiteSpace=wrap;fillColor=#E3F2FD;strokeColor=#1565C0;strokeWidth=2;fontSize=14;
```

**合同 / 协议**（`contract`，文档形）：
```
shape=document;whiteSpace=wrap;fillColor=#FFFFFF;strokeColor=#1f77b4;strokeWidth=2;fontSize=14;
```

**判决 / 律师函 / 法律文书**（`legal_doc`，文档形 + 决策橙）：
```
shape=document;whiteSpace=wrap;fillColor=#FFF3E0;strokeColor=#FF8C00;strokeWidth=2;fontSize=14;
```

**证据**（`evidence`，平行四边形）：
```
shape=parallelogram;whiteSpace=wrap;fillColor=#E8F5E9;strokeColor=#43A047;strokeWidth=2;fontSize=14;
```

**金额 / 标的 / 资金**（`amount`，圆柱）：
```
shape=cylinder3;whiteSpace=wrap;fillColor=#FFF3E0;strokeColor=#FF8C00;strokeWidth=2;size=12;fontSize=14;
```

**风险 / 违约 / 争议点**（`risk`，菱形 + 争议红）：
```
rhombus;whiteSpace=wrap;fillColor=#FDECEA;strokeColor=#C0392B;strokeWidth=2;fontSize=14;
```

**裁判 / 结论**（`judgment`，双椭圆，强结论）：
```
doubleEllipse;whiteSpace=wrap;fillColor=#FDECEA;strokeColor=#C0392B;strokeWidth=2;fontSize=14;
```

**程序节点**（`procedure`，胶囊/圆头）：
```
rounded=1;arcSize=50;whiteSpace=wrap;fillColor=#F5F5F5;strokeColor=#9E9E9E;strokeWidth=2;fontSize=14;
```

**时间事件**（`event`，小椭圆）：
```
ellipse;whiteSpace=wrap;fillColor=#E8F5E9;strokeColor=#43A047;strokeWidth=2;fontSize=12;
```

**分区 / 泳道**（`section` / `lane`，背景容器）：
```
swimlane;startSize=30;fillColor=#F5F5F5;strokeColor=#BDBDBD;strokeWidth=2;
```
> 扁平背景框（子节点仍 `parent="1"`）必须加 `container=1`，否则 `validate_drawio.py` 会把内部节点报为重叠。

## `emphasis` 与 `density` 影响

`emphasis` 调节点存在感，`density` 调整图留白，均叠加在 token 样式上：

| 字段 | 取值 | 样式叠加 |
|---|---|---|
| `emphasis` | `high` | `strokeWidth=3;fontStyle=1;`（加粗加边，用于核心主体/核心争议） |
| `emphasis` | `normal` | token 默认值（不叠加） |
| `emphasis` | `low` | 改用 grey_missing 色板、`strokeWidth=1;`（辅助事实/背景节点） |
| `density` | `compact` | 节点尺寸降一档、间距收紧（按 `legal-visual-constants.md` 节点尺寸表 16+ 档） |
| `density` | `normal` | 默认尺寸 |
| `density` | `detailed` | 节点尺寸升一档、留白增大（客户汇报默认） |

## 默认主题：客户汇报（`client_report`）

本轮唯一落地的主题。其余两套（法官提交 `court_submit`、律师工作底稿 `lawyer_workpaper`）留待后续版本。

```yaml
theme: client_report
icon_mode: off          # 默认不渲染 emoji
density: detailed       # 适度留白，突出策略与风险
emphasis_palette:        # 强调色只用这三个
  high_primary: "#1f77b4"
  high_decision: "#FF8C00"
  high_dispute: "#C0392B"
dispute_style: dashed    # 争议/待证事实一律虚线 + 旁注
```

客户汇报主题的取材原则：突出策略、风险和可能结果；争议/待证事实用虚线与旁注区分；可启用较丰富的形状分类（主体/文书/资金/风险），但仍守"一图一观点"。

## emoji opt-in 机制

- **默认不渲染**：`theme.icon_mode=off` 时，总表"可选 emoji"列**不写入**节点 `value`。
- **整图开启**：VizSpec 声明 `icons: true`（或 `theme: client_report` 之外的主题显式 `icon_mode: on`）时，按总表把 emoji 作为标签**前缀**写入 `value`，如 `value="🏛 一审法院"`。
- **单节点开启**：节点声明 `icon: "🏛"` 时，仅该节点加前缀，覆盖整图设置。
- emoji 仅作辅助识别，**不得**替代形状区分；即使用 emoji，几何形状仍按 token 取值。

## VizSpec 声明与校验

- VizSpec 节点声明 `visual_role`（必填，命中本表）和可选 `shape_token`（默认由 `visual_role` 映射）、`emphasis`、`icon`。
- 整图声明 `theme`（默认 `client_report`）、`density`、`icons`（默认 `false`）。
- 合法性校验：`python scripts/check_vizspec.py spec.yaml` 检查 `visual_role` / `theme` 是否在本表与主题清单内、`icon` 是否 opt-in。
- 形状多样性校验：`python scripts/validate_drawio.py file.drawio` 的 `shape_diversity` 检查会在单一形状占比 > 80% 且节点 ≥ 5 时告警，提示按本表区分语义。

## 与其他文件的关系

| 文件 | 关系 |
|---|---|
| `legal-visual-constants.md` | 提供 palette、字体、尺寸常量；其"节点样式映射"表指向本表，不再单独维护形状映射 |
| `vizspec-schema.md` | 定义 `visual_role` / `shape_token` / `emphasis` / `theme` / `density` / `icons` 字段，取值合法性引用本表 |
| `xml-reference.md` | 形状示例的样式串以本表为准；本表补充 parallelogram、doubleEllipse、capsule 等新增形状写法 |
| `visual-composition-rules.md` | 编排规则引用本表决定"什么语义用什么形状" |
| `scripts/validate_drawio.py` | `shape_diversity` 检查量化"全方框"风险 |
| `scripts/check_vizspec.py` | 校验 VizSpec 声明的角色与主题合法性 |

## 修改记录

| 日期 | 变更 | 版本 |
|---|---|---|
| 2026-07-28 | 初版：9 类法律语义、17 个视觉角色、形状 token 与样式串、客户汇报主题、emoji opt-in 机制 | 0.8.0 |
