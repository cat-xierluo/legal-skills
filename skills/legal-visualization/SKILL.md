---
name: legal-visualization
description: Legal Visualization。面向法律业务场景的法律图解与图表生成技能；当用户要求把案件材料、合同材料、合规事项、交易安排、证据链、诉讼流程、时间轴、法律关系、客户汇报、法律服务方案或律师团队工作整理成关系图、流程图、时间轴、证据链、风险图、路线图、PNG/SVG/PDF/.drawio 时使用；也兼容“法律可视化”“案件事实图”“法律关系图”等说法。先按受众、任务动词和路由规则筛选场景，再生成可交付图片，并保留 draw.io 源文件作为可编辑底稿。本技能不用于事实核验，也不替代法律结论判断。
version: "0.6.14"
license: CC-BY-NC
author: 杨卫薪律师（微信ywxlaw）
homepage: https://github.com/cat-xierluo/legal-skills
---

# Legal Visualization

面向法律业务场景的法律图解与图表生成技能。覆盖案件、非诉项目、合规管理、客户协作、团队办案、客户汇报和法律服务方案，生成可直接提交、汇报或嵌入文档的法律图表。对外英文名使用 `Legal Visualization`，中文可称“法律可视化”；Skill 标识和目录名统一为 `legal-visualization`。draw.io / diagrams.net 是默认可编辑底层格式，不是对外定位的边界。

## 硬约束

1. **缺失事实必须显式标注**：材料中未见的主体、时间、金额、合同、证据，不得出现在图中；必须显式写"待补充/待核/一方主张"，禁止补全或推断。
2. **业务条线优先于图型**：先识别"诉讼/公司/合规/知产/争议/合同/客户/服务"等业务条线，再选图型。
3. **VizSpec.routing 必填**：未填 `routing.primary_scene` 与 `routing.selection_reason` 禁止写 drawio。
4. **一图一观点**：超过 1 个核心观点必须拆主图+附图，禁止堆叠。

## 默认目标

- 默认交付三件套：`.drawio` 源文件、`.svg` 矢量图、`.png` 高清预览图；SVG 和 PNG 都从 `.drawio` 通过 draw.io / diagrams.net 导出。
- 用户要求庭审、报告、PPT 或归档时，按需追加 `PDF`。
- PNG 默认按 2 倍倍率导出；如用于打印、大屏汇报或高清插图，可通过 `--png-scale 3` 或 `--png-scale 4` 提高清晰度。
- 默认追求一步到位出图；只有在导出工具不可用或材料关键事实缺失时，才把 draw.io 手工编辑作为兜底。
- 图表必须服务一个核心观点或一个清晰的信息任务，不把所有材料堆进一张图。
- 自动导出的 `.drawio`、图片和报告默认进入 `archive/<timestamp>/`，避免污染 `templates/` 或源文件目录。

## 依赖

### 开箱即用

- 生成 `.drawio` XML、读取参考文件、执行 `scripts/validate_drawio.py` 仅需 Python 3 标准库。
- 没有 draw.io CLI 时，仍可交付 `.drawio` 源文件，并在最终说明中标明图片导出未完成。

### 可选依赖

| 功能 | 依赖 | 安装方式 |
|------|------|----------|
| VizSpec YAML 与 drawio 节点编号一致性检查 | `PyYAML` | `pip install pyyaml` |
| 自动导出 SVG/PNG/PDF | draw.io / diagrams.net 桌面版 CLI | macOS 可安装 diagrams.net；脚本会检测 `drawio`、`draw.io`、`drawio-desktop` 和常见应用路径 |

## 工作流

1. **提取制图任务**：从材料中提取受众、案件/项目类型、核心问题、主体、时间、金额、标的物、流程、证据、风险、客户动作、团队动作和用户立场。缺少非关键事实时先合理标注“待补充”，不要停下等待。
2. **确定受众**：给法官的图保持客观、克制、可核对；给客户的图突出策略、风险和可能结果；给业务团队的图突出流程、责任和交付物；给律师团队的图可以保留更多细节和证据索引。
3. **路由场景**：先读 `references/scene-routing-guide.md`，按受众、任务动词、材料阶段和信息形态筛出 1-3 个候选场景；再读 `references/scene-library.md` 中对应章节定主场景。不要直接在完整场景库中凭关键词跳选。scene_id 选定后，从 `references/chart-decision-tree.md` 选图型变体与节点布局；该决策树是路由的下游，不替代路由。
4. **解决冲突**：如果多个场景都能命中，按“用户指定 > 受众匹配 > 更窄业务领域 > 当前材料阶段 > 通用场景”选择主图；未选场景只作为附图候选。
5. **确定内容**：按“全面罗列 -> 逻辑整合 -> 精简内容”处理材料。复杂案件先做细节图，再按核心主体、核心时间线或核心法律关系组合。
6. **生成 VizSpec**：按 `references/vizspec-schema.md` 先写结构化制图规格，明确路由结论、场景 ID、主图观点、节点、连线、分区、注释和待核事实。
7. **编排图面**：按 `references/visual-composition-rules.md` 和 `references/scene-composition-playbook.md` 控制图表逻辑、配色、线条、注释和重点表达；复杂案件、制度路径、背景趋势、票据回路和工期延误类图表还要读 `references/advanced-case-patterns.md`。颜色、字体、起始坐标、节点尺寸等视觉常量全部按 `references/legal-visual-constants.md` 取值，禁止在图中硬编码。节点命名按 `references/naming-conventions.md` 规范。
8. **生成 draw.io**：按 `references/xml-reference.md` 写 `.drawio` XML；`templates/` 仅作为可打开的 draw.io 模板起点，XML 写法示例见 `references/xml-example-*.md`。
9. **导出图片**：按 `references/output-workflow.md` 导出 `SVG/PNG/PDF`，并保留 `.drawio`。导出后检查图片非空、文字不截断、主体不拥挤。
10. **质检交付**：按 `references/quality-checklist.md` 自查后，再向用户说明输出文件、使用场景和未能验证的环节。

## 场景路由速查

| 输入特征 | 首选图表 | 读取 |
|------|------|------|
| 事件先后、时效、保证期间、工期、程序经过、项目里程碑 | 时间轴、分层时间轴、时间区间图、路线图 | `scene-library.md` 通用、建设工程、服务方案 |
| 多主体、多合同、资金/票据/货物/股权流转 | 法律关系图、流向图、组合关系图 | `scene-library.md` 借款、票据、公司、国际贸易 |
| 多笔金额、工程价款、出资比例、费用趋势 | 表格、柱状图、折线图、占比图 | `scene-library.md` 数据与公司 |
| 诉讼程序、业务流程、审批流程、交易步骤、服务交付 | 流程图、泳道流程图、路线图 | `scene-library.md` 通用、国际贸易、土地、服务方案、合同、合规 |
| 法律服务方案、客户汇报、项目报价、工作计划 | 服务路线图、范围-交付物矩阵、方案对比图 | `scene-library.md` 服务方案 |
| 合同起草审查、履约管理、违约处置、标准文本体系 | 合同生命周期图、审查泳道、条款风险图、义务台账 | `scene-library.md` 合同 |
| 企业合规、内控、公司治理、监管整改 | 风险地图、审批矩阵、制度架构、整改路线图 | `scene-library.md` 合规治理 |
| 投融资、并购、资产交易、尽职调查 | 交易架构图、尽调问题地图、交割条件清单 | `scene-library.md` 交易 |
| 劳动人事、知识产权、数据合规、债务化解、家族财富、行政监管 | 生命周期图、权属链、数据流、清偿顺位、财产结构、监管路径 | `scene-library.md` 对应专题 |
| 初次咨询、签约、材料收集、服务进度、结案续约 | 客户生命周期图、材料收集清单、服务进度看板 | `scene-library.md` 客户全生命周期 |
| 诉前评估、起诉准备、庭审、调解、判后、执行、再审 | 案件办理路线图、庭审攻防图、执行推进图 | `scene-library.md` 案件办理全流程 |
| 证据发现、固定、补强、举证、质证、归档 | 证据生命周期图、证明责任图、质证攻防图 | `scene-library.md` 证据工作全生命周期 |
| 起诉状、答辩状、律师函、法律意见书、尽调报告 | 文书生产流程图、文书结构图、版本演变图 | `scene-library.md` 法律文书生产 |
| 谈判、调解、仲裁、诉讼、行政投诉、刑民交叉、执行转破产 | 争议路径选择图、并行程序泳道图、成本周期对比图 | `scene-library.md` 争议解决路径 |
| 团队分工、材料流转、庭审准备、复核、复盘、知识沉淀 | 任务分工图、材料流转图、甘特图、质量复核图 | `scene-library.md` 团队协作 |
| 工程现场、房地产项目、路线、空间位置 | 平面图、空间示意图 | `scene-library.md` 空间、房地产 |
| 证据证明方向、间接证据组合、争点拆解 | 证据链图、争点-证据矩阵 | `scene-library.md` 证据与复合案件 |

## 关键原则

- 一张图只表达一个主观点；多个观点拆成多张图或多页图。
- 颜色必须有含义：同主体同色，同类型关系同线型，争议/风险/违约用强调色，辅助事实用灰色。
- 避免线条交叉和长距离绕行；连接多的主体放在中心或靠近相关节点。
- 图表主体只放短标签；长事实、证据编号、条文依据放侧栏、底注或附表。
- 对法官提交的图，不夸张表达，不把争议事实画成既定事实；争议或待证事实用虚线、问号、标注或灰色处理。

## 输出格式

- `[图名].drawio`：源文件，必须随图片一起交付，便于用户继续编辑。
- `[图名].svg`：从 `.drawio` 导出的矢量图，适合 Word、PPT、网页和继续缩放。
- `[图名].png`：从 `.drawio` 导出的高清预览图，适合微信、飞书、邮件正文、普通预览。
- `[图名].pdf`：适合归档、打印或正式附件。
- `archive/<timestamp>/export-report.json`：批量导出报告，记录 `.drawio` 源文件、导出工具、输出文件和轻量检查结果。

## 参考文件

- `references/scene-library.md`：法律图表场景索引和路由规则。
- `references/scene-routing-guide.md`：大场景库下的选择规则、评分法和冲突处理。
- `references/scene-routing-evals.md`：场景路由测试集，用于检查误选和冲突。
- `references/scene-composition-playbook.md`：场景编排手册，说明各类场景怎么取舍和布局。
- `references/vizspec-schema.md`：结构化制图规格，用来稳定生成图表。
- `references/visual-composition-rules.md`：法律图表编排规则。
- `references/advanced-case-patterns.md`：复杂案件和高阶论证图的编排套路。
- `references/output-workflow.md`：一步到位生成 `.drawio` 与图片的操作流程。
- `references/quality-checklist.md`：交付前检查清单。
- `references/xml-reference.md`：draw.io XML 结构、样式、连线和容器规则。
- `references/chart-decision-tree.md`：scene_id 选定后选图型变体与节点布局。
- `references/legal-visual-constants.md`：视觉常量（页面、字体、调色板、线型）。
- `references/naming-conventions.md`：法律节点中文命名规范。
- `references/template-guide.md`：模板目录结构、模板清单和新增模板规则。
- `references/xml-example-*.md`：XML 语法示例，不放入模板目录。
- `templates/`：只存放可直接打开的 `.drawio` 模板，按英文业务目录组织。

## 实现提示

- XML 校验：`python scripts/validate_drawio.py path/to/file.drawio`，与 `quality-checklist.md` 第 32-38 行自检项对位。
- 批量导出：`python scripts/export_drawio.py path/to/file.drawio` 默认生成 `.drawio + .svg + .png` 三件套，并写入 `archive/<timestamp>/export-report.json`；PNG 默认 2 倍导出，需要更高清可加 `--png-scale 3`，如需旧行为可加 `--in-place`。
- 命名规范检查：`python scripts/normalize_naming.py path/to/file.drawio path/to/spec.yaml`，对照 `naming-conventions.md` 输出偏差清单。
