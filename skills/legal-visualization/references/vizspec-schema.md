# VizSpec 制图规格

VizSpec 是 Legal Visualization 的中间结构。先生成 VizSpec，再转 draw.io XML。这样可以降低随机发挥，稳定实现一步到位出图。

## 必填结构

```yaml
vizspec_version: "2.0"
title: ""
audience: "court | client | team | public"
purpose: ""
case_type: ""
routing:
  task: "explain | prove | choose | advance | manage | deliver"
  material_stage: "consultation | service | litigation | evidence | drafting | transaction | compliance | execution | review"
  primary_scene: ""
  alternatives_considered:
    - scene_id: ""
      reason_not_selected: ""
  selection_reason: ""
template:
  id: "template-id | custom"
  path: "templates/<domain>/<template>.drawio | null"
  lock_geometry: true
  overflow_policy: "split_appendix | reject"
scene_ids: []
main_chart_type: "timeline | relation | data | process | spatial | evidence | composite"
stance: "neutral | claimant | respondent | internal"
core_message: ""
output:
  source: ".drawio"
  images: ["svg", "png"]
  optional: ["pdf"]
visual:
  theme: "client_report | court_submit | lawyer_workpaper"
  density: "compact | normal | detailed"
  icons: false
facts:
  confirmed: []
  disputed: []
  missing: []
entities:
  - id: ""
    label: ""
    role: ""
    group: ""
    visual_role: ""
    shape_token: ""
    emphasis: "high | normal | low"
    icon: ""
    style_key: ""
events:
  - id: ""
    date: ""
    label: ""
    actor: ""
    legal_effect: ""
    evidence_ref: ""
amounts:
  - id: ""
    label: ""
    value: ""
    unit: ""
    category: ""
relations:
  - id: ""
    source: ""
    target: ""
    label: ""
    relation_type: "contract | payment | delivery | bill | equity | procedure | evidence | claim"
    status: "confirmed | disputed | asserted | inferred | missing"
    style_key: ""
sections:
  - id: ""
    label: ""
    purpose: ""
    contains: []
annotations:
  - id: ""
    text: ""
    anchor: ""
    type: "note | conclusion | evidence | risk | legend"
layout:
  direction: "left-to-right | top-down | center-out | matrix | lanes | map"
  lanes: []
  emphasis: []
  avoid: []
quality_checks:
  - ""
```

## 字段说明

| 字段 | 用途 |
|------|------|
| `purpose` | 本图的信息任务，例如“说明合同主体与实际履行主体不一致” |
| `core_message` | 一句话主观点，必须能放进标题、副标题或结论栏 |
| `routing` | 场景路由结论，记录主场景、备选场景和排除理由（**必填**，见 `SKILL.md` 硬约束第 3 条） |
| `template` | 记录模板绑定。命中模板时 `lock_geometry=true`，只替换 value；容量不足按 `overflow_policy` 拆附图或阻断。没有适配模板时填 `id: custom` |
| `entities[].role` | 节点身份（原告/被告/第三人等），取值规范见 `references/naming-conventions.md` |
| `scene_ids` | 来自 `scene-library.md` 的场景 ID，可多个 |
| `confirmed/disputed/missing` | 防止把争议事实画成确定事实 |
| `relation_type` | 决定线条颜色、箭头和图例 |
| `status` | 决定实线、虚线、灰色或待证标注（颜色常量见 `references/legal-visual-constants.md`） |
| `sections` | 用来划分阵营、阶段、法律关系、制度路径或项目范围 |
| `layout` | 指定总体布局，避免边生成边想 |
| `entities[].visual_role` | 法律语义角色（`plaintiff` / `contract` / `amount` / `risk` 等），决定**配色、线型与强调**（形状统一圆角矩形），取值见 `references/shape-registry.md` |
| `entities[].shape_token` / `emphasis` / `icon` | 可选：形状 token（默认圆角矩形，仅决策点用菱形）、强调（`high` 粗边粗体 / `normal` / `low` 灰细）、单节点 emoji（覆盖整图 `icons`） |
| `visual.theme` / `density` / `icons` | 整图视觉：主题（默认 `client_report`）、留白档位、是否渲染 emoji（默认 `false`，法律图保持严肃） |

## 生成顺序

1. 先写 `title`、`audience`、`purpose`、`core_message`。
2. 按 `scene-routing-guide.md` 先填 `routing`，再绑定 `template`，最后填 `scene_ids` 和 `main_chart_type`。
3. 提取实体、事件、金额、关系和证据；按 `shape-registry.md` 为每个节点声明 `visual_role`，整图声明 `theme` 与 `icons`（默认 `false`）。
4. 标出确定事实、争议事实、缺失事实。
5. 设计分区、泳道、图例和注释。
6. 命中模板时锁定几何实例化；无模板时将 VizSpec 转成新 draw.io XML。
7. 运行领域校验，错误为零后才能导出图片并按质量清单检查。

## 关系状态样式

| 状态 | 视觉表达 |
|------|------|
| `confirmed` | 实线、常规色 |
| `disputed` | 虚线或双线，旁注“争议” |
| `asserted` | 虚线，使用主张方颜色 |
| `inferred` | 点线或浅色，标注“推定/需结合证据” |
| `missing` | 灰色、问号或待补充标签 |

具体颜色常量与线型绑定规则见 `references/legal-visual-constants.md` "线型与状态绑定" 段。

## 输出前自问

- 这张图是不是只讲一个主观点？
- 主场景是否比备选场景更贴近受众、任务和材料阶段？
- 读者不听讲解能否看出主体、关系和结论？
- 哪些事实是争议或待补充，是否已经视觉区分？
- 是否需要拆出附图，避免主图拥挤？
- 节点是否统一圆角矩形？非限定形状（椭圆 / 圆柱 / 文档形等）会被 `validate_drawio.py` 的 `shape_policy` 告警。
- `.drawio` 能否继续编辑，SVG/PNG 是否能直接交付？
