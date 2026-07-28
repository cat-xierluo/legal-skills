# VizSpec 2.1 制图规格

VizSpec 是 Legal Visualization 的中间结构：先声明法律语义和场景，再生成 draw.io 几何，最后用样式编译器把主题、角色、事实状态和强调写入图形。合法枚举的机器真相源是 `config/visual-role-registry.json`。

## 最小可执行结构

```yaml
vizspec_version: "2.1"

title: 多主体借款关系图
audience: client
purpose: 说明签约主体、实际用款人与收款账户的关系
core_message: 名义借款与实际用款分离，资金落点待补证

routing:
  primary_scene: multi-party-relation
  selection_reason: 需要呈现多主体、多关系及不同事实状态

template:
  id: multi-party-relation
  path: templates/litigation/multi-party-relation.drawio
  lock_geometry: true
  overflow_policy: split_appendix

visual:
  theme: client_report
  density: normal

entities:
  - id: lender
    label: 贷款人（原告）
    visual_role: plaintiff
    epistemic_status: confirmed
    emphasis: high
  - id: nominal
    label: 名义借款人（被告）
    visual_role: defendant
    epistemic_status: confirmed
    emphasis: normal
  - id: actual
    label: 实际用款人（第三人）
    visual_role: third_party
    epistemic_status: inferred
    emphasis: normal

amounts:
  - id: account
    label: 收款账户（待补开户行）
    visual_role: amount
    epistemic_status: missing
    emphasis: low

relations:
  - id: e1
    source: actual
    target: nominal
    label: 实际用款（推定）
    relation_type: payment
    status: inferred
```

可直接校验的完整示例见 `assets/examples/multi-party-visual-spec.yaml`。

## 必填约束

1. `vizspec_version` 必须为 `"2.1"`。
2. `routing.primary_scene` 与 `routing.selection_reason` 必须为非空字符串。
3. `visual.theme` 只能是 `client_report`、`court_submit`、`lawyer_workpaper`；`density` 只能是 `compact`、`normal`、`detailed`。
4. `entities`、`events`、`amounts`、`sections` 中的每个节点必须有全局唯一 `id` 和合法 `visual_role`。
5. 每条 `relations` 必须有唯一 `id`、存在的 `source/target` 和合法 `status`。
6. 正式法律图禁用 emoji/icon；不要写节点 `icon`。兼容旧规格时 `visual.icons` 只能为 `false`。

## 角色、状态、强调

三个字段相互独立：

| 字段 | 作用 | 默认值 |
|---|---|---|
| `visual_role` | 决定语义类别与基础形状 | 无，必须声明 |
| `epistemic_status` | 决定节点事实状态线型 | `confirmed` |
| `emphasis` | 决定描边粗细和字重 | `normal` |

不得把诉讼地位当事实状态：`visual_role: defendant` 不自动产生虚线，`visual_role: plaintiff` 不自动产生粗边。只有显式 `epistemic_status: disputed` 才表示争议，只有显式 `emphasis: high` 才表示本图重点。

`shape_token` 通常不要手写；它由角色注册表推导。`decision` 自动使用 `decision_diamond`，普通角色自动使用 `rounded_rect`。校验器拒绝用 `shape_token` 覆盖角色规定的形状。

## 其他节点集合

事件、金额和分区也必须进入同一视觉系统：

```yaml
events:
  - id: hearing
    label: 开庭
    date: 2026-08-10
    visual_role: event
    epistemic_status: confirmed
    emphasis: normal

amounts:
  - id: principal
    label: 本金 100 万元
    visual_role: amount
    epistemic_status: asserted
    emphasis: high

sections:
  - id: claimant-lane
    label: 原告证据区
    visual_role: lane
    epistemic_status: confirmed
    emphasis: normal
    contains: [lender, principal]
```

分区 `section/lane` 会保留模板已有的容器形状；样式编译器不重写其几何。

## 关系状态

| `status` | 含义 | 视觉表达 |
|---|---|---|
| `confirmed` | 已有可靠材料支持 | 实线 |
| `disputed` | 存在明确争议 | 红色虚线 |
| `asserted` | 仅一方主张 | 主张色虚线 |
| `inferred` | 根据材料推定 | 灰色点虚线 |
| `missing` | 关系或关键事实待补 | 灰色虚线 |

文字标签仍应写“争议”“主张”“推定”“待补”等自然语言，不能只依赖颜色或线型传达法律状态。

## 执行顺序

1. 按场景路由填写 `routing`，绑定模板并确定一图一观点。
2. 声明全部节点、关系、事实状态和强调等级。
3. 运行 `python scripts/check_vizspec.py spec.yaml`；任何 error 都要先修正。
4. 实例化模板或生成自定义 draw.io 几何。
5. 运行 `python scripts/apply_visual_roles.py source.drawio spec.yaml styled.drawio`。
6. 确认报告中的 `geometry_preserved: true`，再运行 draw.io 领域门禁和图片导出。
7. 打开实际 SVG/PNG，目视检查主题、文字、连线、边界和信息层级。

样式编译器找不到 VizSpec 声明的节点或连线 ID、发现非法字段、改变几何或生成无效 draw.io 时必须非零退出。

## 输出前自问

- 是否只表达一个主观点？
- `visual_role`、`epistemic_status`、`emphasis` 是否分别基于语义、证据状态和阅读重点填写？
- 争议与待补是否同时使用文字和线型表达？
- 模板几何是否保持锁定，容量不足时是否拆附图？
- 三套主题中是否选了与受众匹配的一套？
- `.drawio` 是否可编辑，实际 SVG/PNG 是否完整且无裁切？
