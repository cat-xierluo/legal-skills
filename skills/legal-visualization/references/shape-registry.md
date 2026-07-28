# 节点表达规范（Shape Registry）

法律语义 → 视觉角色（`visual_role`）→ **配色 / 线型 / 强调** → drawio 样式的权威映射。VizSpec 声明 `visual_role` 后，按本表注入配色、线型和描边粗细，生成统一、严肃、清晰的矩形图。

本文件是节点视觉的**单一真相源**。`legal-visual-constants.md` 的节点样式速查、`xml-reference.md` 的形状示例、模板与新写 XML 的样式注入，都以本表为准。

## 设计原则（0.8.1 方向修正）

> 0.8.0 曾尝试用"九类语义各配不同几何形状"（椭圆 / 圆柱 / 文档形 / 六边形 / 平行四边形等）提升美观度。实测后发现：形状多样性反而显得奇怪，且不规则形状（圆柱顶椭圆 / 文档形波浪底）会让文字压到边线。用户反馈明确要"统一矩形、干净严肃、限定几种形状"。故 0.8.1 收敛为：

1. **统一圆角矩形**：绝大多数节点用圆角矩形 `rounded=1`，干净、严肃、文字区规整不压边。
2. **形状限定极少数**：只允许 圆角矩形（默认）、菱形（仅"决策 / 判断 / 分支"点，流程图惯例，默认不用）、容器 / 泳道（背景框）。**不用**椭圆、圆柱、文档形、六边形、平行四边形、双椭圆等奇怪形状。
3. **区分靠三维度，不靠形状**：
   - **线型**：实线 = 已证 / 确定；虚线 = 对抗 / 争议 / 待证 / 推定；点线 = 推定（见 status 映射）
   - **配色**：语义类别（蓝 = 主体 / 确认，橙 = 第三人 / 决策 / 资金，红 = 风险 / 争议，灰 = 辅助 / 待补，浅黄 = 文书，浅绿 = 证据）
   - **描边粗细（emphasis）**：粗边粗体 = 核心主体 / 核心观点；常规 = 一般；细边灰 = 辅助
4. **虚线表对抗 / 争议 / 待证**：被告、争议事实、待补信息一律虚线（用户认可的表达）。
5. **emoji opt-in**：默认 `icon_mode=off`，不渲染 emoji，法律图保持严肃；用户显式声明才出。
6. **复用 palette**：强调色 ≤ 3（蓝 / 橙 / 红），分类辅色（浅黄 / 浅绿）不计入配额。

## 形状策略（限定清单）

| 形状 | drawio | 用途 | 何时用 |
|---|---|---|---|
| 圆角矩形 | `rounded=1` | 所有主体、文书、金额、证据、程序、时间、裁判节点 | **默认**，绝大多数节点 |
| 菱形 | `rhombus` | 决策 / 判断 / 分支点 | 仅流程图里"需要判断"的节点，默认不用 |
| 容器 / 泳道 | `swimlane` 或 `container=1` | 分区、阵营、阶段、泳道背景 | 组织分组时 |

其他几何形状（椭圆、圆柱、文档形、六边形、平行四边形、双椭圆等）**不再使用**。`validate_drawio.py` 的 `shape_policy` 检查会对非白名单形状告警。

## 视觉角色 → 配色 / 线型 / 强调 映射

每个 `visual_role` 映射到（配色，线型，emphasis），形状统一圆角矩形：

| `visual_role` | 法律语义 | 配色（填充 / 描边） | 线型 | 默认 emphasis |
|---|---|---|---|---|
| `plaintiff` | 原告 | 蓝 `#E3F2FD` / `#1f77b4` | 实线 | `high`（核心主体，粗边粗体） |
| `defendant` | 被告 | 蓝 `#E3F2FD` / `#1f77b4` | **虚线**（对抗 / 待定） | `normal` |
| `third_party` | 第三人 | 橙 `#FFF3E0` / `#FF8C00` | 实线 | `normal` |
| `witness` | 证人 / 鉴定人 | 灰 `#F5F5F5` / `#9E9E9E` | 实线 | `low` |
| `person` | 自然人 | 蓝 `#E3F2FD` / `#1f77b4` | 实线 | `normal` |
| `company` | 公司 / 法人 | 蓝 `#E3F2FD` / `#1f77b4` | 实线 | `normal` |
| `court` | 法院 / 裁判机关 | 蓝 `#E3F2FD` / `#1f77b4` | 实线 | `normal` |
| `authority` | 监管 / 行政部门 | 蓝 `#E3F2FD` / `#1f77b4` | 实线 | `normal` |
| `contract` | 合同 / 协议 | 浅黄 `#FFFDE7` / `#F9A825` | 实线 | `normal` |
| `legal_doc` | 判决 / 律师函 / 文书 | 浅黄 `#FFFDE7` / `#F9A825` | 实线 | `normal` |
| `evidence` | 证据 | 浅绿 `#E8F5E9` / `#43A047` | 实线 | `normal` |
| `amount` | 金额 / 标的 / 资金 | 橙 `#FFF3E0` / `#FF8C00` | 实线 | `normal` |
| `risk` | 风险 / 违约 / 争议点 | 红 `#FDECEA` / `#C0392B` | **虚线** | `high` |
| `judgment` | 裁判 / 结论 | 红 `#FDECEA` / `#C0392B` | 实线 | `high` |
| `procedure` | 程序节点（立案 / 开庭 / 执行） | 灰 `#F5F5F5` / `#9E9E9E` | 实线 | `normal` |
| `event` | 时间事件 | 蓝 `#E3F2FD` / `#1f77b4` | 实线 | `normal` |
| `decision` | 决策 / 判断 / 分支 | 橙 `#FFF3E0` / `#FF8C00` | 实线 | `normal`（**形状用菱形**） |

> 配色复用 `legal-visual-constants.md` palette。法院 / 公司 / 自然人 / 程序 / 时间等主体与流程类统一蓝色，靠标签文字区分角色——主体类同色是"中立客观"的体现，不靠形状或颜色细分。非主体类（资金橙 / 风险红 / 证据绿 / 文书黄）用分类辅色区分。

## 线型与 status 绑定

`relations.status` 与线型 / 颜色严格对应（与 `legal-visual-constants.md` 一致）：

| status | 线型 | 颜色 |
|---|---|---|
| `confirmed` | 实线 | `line_solid #333333` |
| `disputed` | 虚线 + 强调 | `accent_dispute #C0392B` |
| `asserted` | 虚线 + 主张方色 | `primary #1f77b4` |
| `inferred` | 点线 | `line_dotted #9E9E9E` |
| `missing` | 灰虚线 + 待补充标签 | `grey_missing #9E9E9E` |

节点也可用虚线边框表示该节点本身处于对抗 / 待证状态（如 `defendant` 默认虚线边）。

## emphasis 三档

| emphasis | 样式叠加 | 用于 |
|---|---|---|
| `high` | `strokeWidth=3;fontStyle=1;`（粗边粗体） | 核心主体 / 核心观点 / 风险 / 裁判结论 |
| `normal` | `strokeWidth=2;`（默认） | 一般节点 |
| `low` | 改用 grey_missing 色板，`strokeWidth=1;` | 辅助事实 / 背景节点 |

## 默认主题：客户汇报（client_report）

本轮唯一落地的主题。`icon_mode=off`（不渲染 emoji）、`density=detailed`、争议 / 待证一律虚线、核心主体 `emphasis=high`。其余两套（法官提交、律师工作底稿）留待后续。

## emoji opt-in 机制

- **默认不渲染**：`theme.icon_mode=off` 时，不写入任何 emoji。
- **整图开启**：VizSpec 声明 `icons: true` 时，按角色把 emoji 作为标签前缀。
- **单节点开启**：节点声明 `icon: "🏛"` 时仅该节点加前缀。
- emoji 仅作辅助识别，**不得**替代线型 / 配色区分。

## VizSpec 声明与校验

- 节点声明 `visual_role`（必填，命中本表）→ 自动映射（配色，线型，emphasis）。
- 可选 `emphasis` 覆盖默认、`icon`（opt-in）。
- 整图声明 `theme`（默认 `client_report`）、`density`、`icons`（默认 `false`）。
- 合法性校验：`python scripts/check_vizspec.py spec.yaml` 检查 `visual_role` / `theme` 合法。
- 形状规范校验：`python scripts/validate_drawio.py file.drawio` 的 `shape_policy` 检查会对非白名单形状（椭圆 / 圆柱 / 文档形 / 六边形等）告警，提示改回圆角矩形。

## 与其他文件的关系

| 文件 | 关系 |
|---|---|
| `legal-visual-constants.md` | 提供 palette / 字体 / 尺寸常量；节点样式速查指向本表 |
| `vizspec-schema.md` | 定义 `visual_role` / `emphasis` / `theme` / `density` / `icons` 字段，取值合法性引用本表 |
| `xml-reference.md` | 形状示例以本表的限定清单为准（圆角矩形 / 菱形 / 容器） |
| `scripts/validate_drawio.py` | `shape_policy` 检查限定形状白名单，防奇怪形状 |
| `scripts/check_vizspec.py` | 校验 VizSpec 声明的角色与主题合法性 |

## 修改记录

| 日期 | 变更 | 版本 |
|---|---|---|
| 2026-07-28 | 方向修正：放弃形状多样性，收敛"统一圆角矩形 + 菱形（决策可选）+ 容器"；区分靠线型 / 配色 / emphasis。基于用户反馈"形状没本质差别、奇怪形状不要、统一矩形、虚线可以" | 0.8.1 |
| 2026-07-28 | 初版：9 类语义 17 角色各配不同形状（椭圆 / 圆柱 / 文档形 / 六边形 / 平行四边形 / 双椭圆等） | 0.8.0 |
