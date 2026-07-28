# 视觉角色与节点表达规范

机器可读的单一真相源是 `config/visual-role-registry.json`。本文件只解释组合方法；角色、主题、状态、强调、密度或形状 token 的枚举发生冲突时，以 JSON 注册表和 `scripts/check_vizspec.py` 的结果为准。

## 三个维度必须分离

每个节点分别声明三个维度，禁止根据诉讼地位推定事实状态或强调等级：

| 维度 | 字段 | 回答的问题 | 例子 |
|---|---|---|---|
| 语义角色 | `visual_role` | 这是什么法律对象？ | `defendant`、`contract`、`evidence` |
| 事实认知状态 | `epistemic_status` | 对它的认知确定到什么程度？ | `confirmed`、`disputed`、`inferred` |
| 图面强调 | `emphasis` | 它在本图是否是阅读重点？ | `high`、`normal`、`low` |

因此：

- 被告可以是 `confirmed + normal`，此时使用实线常规描边。
- 原告可以是 `disputed + low`，此时使用争议虚线且弱化。
- 风险节点不自动等于争议事实；是否虚线由 `epistemic_status` 决定。
- 裁判结论不自动高强调；是否加粗由 `emphasis` 决定。

## 形状限定

| token | draw.io 表达 | 用途 |
|---|---|---|
| `rounded_rect` | `rounded=1` | 主体、文书、金额、证据、风险、裁判、程序、事件 |
| `decision_diamond` | `rhombus` + `visualRole="decision"` | 仅用于确有分支判断的问题节点 |
| `container` | 保留既有 `swimlane` / `container=1` | 分区、阵营、阶段、泳道 |

普通节点不用椭圆、圆柱、文档形、六边形、人形或双椭圆。它们文字可用区不稳定，也会削弱法律图的克制感。`scripts/validate_drawio.py` 的 `shape_policy` 会对非限定形状，以及未声明 `visualRole=decision` 的菱形告警。

## 视觉角色

角色只决定语义类别和基础形状，不决定事实状态或强调等级。

| 类别 | `visual_role` | 形状 |
|---|---|---|
| 当事人与主体 | `plaintiff`、`defendant`、`person`、`company` | 圆角矩形 |
| 次要/辅助主体 | `third_party`、`witness` | 圆角矩形 |
| 机构 | `court`、`authority` | 圆角矩形 |
| 文书 | `contract`、`legal_doc` | 圆角矩形 |
| 证明与财务 | `evidence`、`amount` | 圆角矩形 |
| 风险与结论 | `risk`、`judgment` | 圆角矩形 |
| 流程与时间 | `procedure`、`event` | 圆角矩形 |
| 判断 | `decision` | 菱形 |
| 容器 | `section`、`lane` | 保留容器形状 |

不要在文档或脚本中复制一套颜色值；主题配色由 JSON 注册表按类别给出，`scripts/apply_visual_roles.py` 负责生成最终样式。

## 状态与线型

节点用 `epistemic_status`，关系用 `relations[].status`；两者取值一致，但样式表分别维护。

| 状态 | 含义 | 典型表达 |
|---|---|---|
| `confirmed` | 材料已有可靠支持 | 实线 |
| `disputed` | 双方对事实或关系存在争议 | 红色虚线 |
| `asserted` | 仅一方主张，尚未完成证明 | 主张色虚线 |
| `inferred` | 根据现有材料推定 | 灰色点虚线 |
| `missing` | 材料未提及或待补 | 灰色虚线并在文字中标“待补” |

状态样式只能表达认知确定性，不表达原告/被告身份。

## 强调与密度

- `emphasis: high`：粗描边和粗体，只给本图核心节点。
- `emphasis: normal`：常规描边。
- `emphasis: low`：细描边和弱化文字，用于背景或辅助信息。
- `density: compact | normal | detailed`：由注册表统一控制字号与 padding，不得在每个节点另写一套字号。

## 三套可执行主题

| 主题 | 面向对象 | 特征 |
|---|---|---|
| `client_report` | 客户汇报 | 语义色较清楚，层次明显，便于口头讲解 |
| `court_submit` | 法官/正式提交 | 低饱和、克制、中性色占比更高 |
| `lawyer_workpaper` | 律师工作底稿 | 对比更强、密度默认更紧凑，便于快速扫描 |

三套主题由同一个编译器真实生成，不是文档占位。用法：

```bash
python scripts/check_vizspec.py spec.yaml
python scripts/apply_visual_roles.py source.drawio spec.yaml styled.drawio
python scripts/validate_drawio.py styled.drawio
```

样式编译器只允许修改 `style` 和 `visualRole`、`epistemicStatus`、`visualEmphasis`、`visualTheme`、`relationStatus` 等视觉元数据。全部 `mxGeometry` 在编译前后必须逐项相同，否则阻断输出。

## Emoji 与图标

正式法律图禁用 emoji/icon 前缀。`visual.icons: true` 或节点 `icon` 非空均由 VizSpec 校验器报错；如确需品牌图标或证据缩略图，应作为独立人工设计任务处理，不得伪装成当前注册表能力。

## 修改记录

| 日期 | 变更 | 版本 |
|---|---|---|
| 2026-07-28 | 建立 JSON 单一真相源；分离角色、事实状态和强调；取消原告默认高强调与被告默认虚线；落地三套主题和几何守恒样式编译器 | 0.8.2 |
| 2026-07-28 | 收敛为圆角矩形、决策菱形与容器 | 0.8.1 |
