# Changelog

## [0.6.14] - 2026-06-12

### 修复

- 修复 `templates/litigation/three-line-flow.drawio` 导出后连线标签与线条、节点边界重叠的问题。
- 保留三线关系的直连表达，将 edge 上的长标签改为独立文本块，避免导出 PNG/SVG 后文字重叠。

### 改进

- 在 `references/visual-composition-rules.md` 和 `references/quality-checklist.md` 增加连线标签避让规则，避免后续模板继续把长标签压在线上。

### 技术优化

- 重新导出三件套抽检，确认 `.drawio`、`.svg`、`.png` 均能生成，PNG 视觉检查未见文字重叠。

## [0.6.13] - 2026-06-12

### 新增

- 新增 `references/advanced-case-patterns.md`，沉淀复杂案件、高阶论证图和图表化证据目录的编排套路。
- 新增 9 个 `.drawio` 模板，覆盖三线流向、统一入口流程、争点-证据矩阵、制度路径对比、工期延误进度、股权变动前后、项目平面标注、服务路线图和范围-交付物矩阵。

### 改进

- 在 `references/visual-composition-rules.md` 显性化 3S 精简原则，强化“简单、直接、服务策略”的取舍标准。
- 更新 `references/template-guide.md`、`references/chart-decision-tree.md` 和 `references/scene-composition-playbook.md`，让新增模板进入模板索引、图型选择和模板优先级表。
- 修正新增模板中的主体称谓和争议/待补充状态标签，使其通过命名规范抽查。

### 技术优化

- 运行脚本编译、全量 draw.io XML 校验、命名规范抽查和三件套导出抽检，确认 `.drawio + .svg + .png` 默认交付链路可用。

## [0.6.12] - 2026-06-12

### 改进

- 明确默认交付为 `.drawio + .svg + .png` 三件套：`.drawio` 是可编辑源文件，SVG 和 PNG 均由 draw.io / diagrams.net 从源文件导出。
- `SKILL.md`、`references/output-workflow.md` 和 `references/template-guide.md` 同步改为三件套表述。
- `scripts/export_drawio.py` 的帮助文本明确 `--format` 只控制图片格式，`.drawio` 源文件始终保留。

### 技术优化

- 增加默认导出抽检，确认未指定 `--format` 时输出目录包含 `.drawio`、`.svg`、`.png` 和 `export-report.json`。

## [0.6.11] - 2026-06-12

### 改进

- `scripts/export_drawio.py` 默认将 `.drawio` 源文件与 PNG/SVG/PDF 一起写入输出目录，确保用户拿到图片后也能继续编辑源文件。
- 即使未检测到 draw.io CLI，导出流程也会尽量保留 `.drawio` 源文件，并在报告中说明图片未能自动导出。
- `SKILL.md` 和 `references/output-workflow.md` 明确要求交付目录必须包含 `.drawio` 源文件。

### 技术优化

- 导出报告新增 `source_drawio` 字段，记录源文件保存路径、大小和是否复制到归档目录。

## [0.6.10] - 2026-06-12

### 改进

- 移除 Skill 内部关于特定外部来源的表述，不再在主入口、任务记录、变更记录或决策记录中引用该来源。
- 将 `SKILL.md` 定位改为“面向法律业务场景的法律图解与图表生成技能”。
- 保留 `Legal Visualization` / “法律可视化”作为现行名称。

### 文档完善

- 更新技能级记录，并完成全文检索确认。

## [0.6.9] - 2026-06-12

### 改进

- 将 Skill 目录从 `legal-viz` 迁移为 `legal-visualization`，让技术标识与对外英文名一致。
- 将 `SKILL.md` frontmatter `name` 调整为 `legal-visualization`，避免继续使用 `Viz` 缩写。
- 更新脚本帮助文本中的默认归档路径说明。

### 文档完善

- 更新 `TASKS.md` 和 `DECISIONS.md` 记录本轮内部标识迁移；历史记录中的旧名保留用于追溯。

## [0.6.8] - 2026-06-12

### 改进

- 将对外英文名从中英混排的 `Legal 可视化` 调整为完整英文 `Legal Visualization`。
- 从现行 `SKILL.md` description 中移除 `Legal Viz` 缩写，避免继续使用用户不喜欢的缩写表达。
- 保留“法律可视化”作为中文触发词，并保留法律业务场景定位。

### 文档完善

- 更新脚本帮助文本和现行参考文件中的名称表述，历史记录中的旧称保留用于追溯。

## [0.6.7] - 2026-06-12

### 改进

- 将对外展示名从“法律图表助手”调整为 `Legal 可视化`，强化法律可视化的名称体系。
- 在 `SKILL.md` description 中补充法律业务场景定位。
- 保留“法律图解与图表生成助手”作为中文功能说明，兼顾品牌延续和新用户理解。

### 文档完善

- 更新现行说明文件和脚本帮助文本中的名称表述，历史版本记录保留旧称用于追溯。

## [0.6.6] - 2026-06-12

### 改进

- 删除根目录 `CLAUDE.md`，避免 Skill 内部保留平台专用说明文件。
- 保留 `SKILL.md` 作为唯一主入口，模板说明继续放在 `references/template-guide.md`，工作记录继续放在 `CHANGELOG.md`、`DECISIONS.md` 和 `TASKS.md`。

### 文档完善

- 更新 `SKILL.md` 版本号为 `0.6.6`，记录本轮结构清理。

## [0.6.5] - 2026-06-12

### 改进

- 将对外展示名调整为“法律图表助手”，降低“法律可视化 / Legal Viz”对普通使用者的理解门槛。
- 优化 `SKILL.md` 触发描述，突出“把法律材料整理成关系图、流程图、时间轴、证据链、风险图、路线图”等具体任务。
- 保留 `legal-viz`、`Legal Viz` 和“法律可视化”作为兼容别名，不改动目录名和内部标识。

### 文档完善

- 更新 `CLAUDE.md` 和 `TASKS.md`，明确内部标识与对外名称的关系。

## [0.6.4] - 2026-06-12

### 改进

- 整理 `templates/` 目录：只保留可直接打开的 `.drawio` 模板，不再放置 Markdown 说明文件。
- 将业务条线目录改为英文命名：`litigation/`、`corporate/`、`compliance/`、`contract/`、`intellectual-property/`。
- 将 6 个 XML 语法示例从 `templates/` 移入 `references/`，统一命名为 `xml-example-*.md`。
- 将原 `templates/README.md` 迁移为 `references/template-guide.md`，作为模板目录指南。

### 技术优化

- 更新 `SKILL.md` 和 `CLAUDE.md`，明确模板目录只存放 `.drawio` 文件，XML 示例和说明性文档统一放在 `references/`。

## [0.6.3] - 2026-06-12

### 改进

- `scripts/export_drawio.py` 新增 `--png-scale` 参数，PNG 默认按 2 倍倍率导出，降低聊天分享、文档插图和汇报场景中的模糊感。
- 导出报告新增 `png_scale` 字段，便于追溯 PNG 清晰度设置。
- `SKILL.md`、`references/output-workflow.md`、`CLAUDE.md` 和 `templates/README.md` 同步补充高清 PNG 导出说明。

### 技术优化

- PNG 清晰度参数仅作用于 PNG，不改变 SVG/PDF 的默认输出逻辑。

## [0.6.2] - 2026-06-12

### 新增

- 新增 `archive/` 运行产物归档目录，使用目录内 `.gitignore` 忽略导出图片和报告，仅保留 `.gitkeep`。
- `scripts/export_drawio.py` 默认将 SVG/PNG/PDF 与 `export-report.json` 写入 `archive/<timestamp>/`。

### 改进

- `scripts/export_drawio.py` 增加 `--output-dir`、`--archive-dir` 和 `--in-place` 参数，支持指定归档目录或恢复旧的同目录导出行为。
- `references/output-workflow.md` 增加“归档机制”说明，明确运行产物不进入版本库。
- `SKILL.md` 和 `CLAUDE.md` 同步说明默认归档输出路径。

### 技术优化

- 导出文件名按 Skill 内相对路径生成，批量导出多目录模板时避免同名文件覆盖。

## [0.6.1] - 2026-06-12

### 修复

- 修正 `CLAUDE.md` 中滞留的 0.5.1 状态、旧模板数量和旧目录结构说明。
- 修正 `templates/诉讼/layered-timeline.drawio` 中“对方”等口语化身份词，统一改为“原告/被告”。
- 修正 `scripts/normalize_naming.py` 对“证据目录”“证据初步梳理”等泛称的误报，避免把材料名称当成证据编号错误。

### 改进

- `SKILL.md` 新增“依赖”章节，明确开箱即用能力、可选 PyYAML 功能和 draw.io CLI 导出能力。
- `scripts/export_drawio.py` 调整为明确检测本机 draw.io / diagrams.net CLI，并增加 SVG viewBox、PNG/PDF 文件头等轻量导出检查字段。
- `references/output-workflow.md` 区分 CLI 自动导出、MCP/浏览器/桌面手动导出和无导出环境三类路径，避免脚本能力边界不清。

### 技术优化

- 增加常见 macOS draw.io / diagrams.net 应用路径检测，降低用户未配置命令行别名时的导出失败概率。

## [0.6.0] - 2026-06-07

### 新增

- 新增 `references/chart-decision-tree.md`：在 `scene-routing-guide.md` 之后给出"业务条线→图型变体→关键考虑"决策表，是路由的下游不替代路由。
- 新增 `references/naming-conventions.md`：法律节点中文命名规范（程序身份、文书材料、证据编号、关系状态标签前缀、主体分组）。
- 新增 `references/legal-visual-constants.md`：把 `output-workflow.md` 第 37-39 行的硬编码常量（页面、字体、调色板、线型、节点尺寸）沉淀为单一事实源。
- 新增 `scripts/validate_drawio.py`：XML 自检脚本，对位 `quality-checklist.md` 第 32-38 行的 drawio XML 自检项。
- 新增 `scripts/export_drawio.py`：drawio 批量导出脚本，对位 `output-workflow.md` 第 47-49 行的导出策略；检测 drawio CLI/MCP，输出 `export-report.json`。
- 新增 `scripts/normalize_naming.py`：节点命名偏差检查，对照 `naming-conventions.md` 输出偏差清单。
- 新增 9 个业务条线 drawio 模板：`templates/诉讼/{multi-party-relation,layered-timeline,litigation-route}.drawio`、`templates/公司/{equity-structure,transaction-architecture}.drawio`、`templates/合规/{compliance-risk-map,approval-matrix}.drawio`、`templates/合同/contract-review-swim.drawio`、`templates/知产/infringement-compare.drawio`。

### 改进

- `SKILL.md` 顶部新增"硬约束"段（4 条）：缺失事实显式标注、业务条线优先于图型、VizSpec.routing 必填、一图一观点。
- `SKILL.md` 工作流第 3 步路由后追加 chart-decision-tree 引用；第 7 步编排图面后追加 visual-constants 与 naming-conventions 引用。
- `SKILL.md` 参考文件段新增 3 个 references；尾部新增"实现提示"段列出 3 个 scripts 的入口。
- `references/output-workflow.md` 把硬编码的 `x=60, y=80`、12-16px 字号、20-28px 标题改为引用 `legal-visual-constants.md`；导出策略段引用 `scripts/export_drawio.py`。
- `references/visual-composition-rules.md` 第 2 步末加 chart-decision-tree 引用，避免原则散落。
- `references/quality-checklist.md` 顶部"事实与法律表达"段引用 `SKILL.md` 硬约束；"draw.io XML"段引用 `scripts/validate_drawio.py`。
- `references/vizspec-schema.md` 字段说明表增加 `entities[].role` 与 `status` 的引用；关系状态样式段引用 `legal-visual-constants.md`。
- `templates/README.md` 重写为按业务条线子目录组织，并增加 scripts/常量/命名规范的引用段。

### 不变

- 对外契约（默认输出 `.drawio+SVG/PNG/PDF`、受众=律师、drawio 单引擎、触发描述）未变。
- 路由层（`scene-routing-guide.md` + `scene-library.md`）未变。
- 现有 6 份 XML 语法教程 `.md` 保留，仅作为"如何写 drawio XML"参考。

### 待办事项

- 沉淀剩余 6 个 P0 场景模板：法律关系图、分层时间轴、三线流向图、统一入口流程图、争点-证据矩阵、服务路线图。
- 补 5 个真实案例测试输入，验证 VizSpec→validate→normalize→export 全链路。
- 扩 `scene-routing-evals.md` 5 个高冲突用例，覆盖新业务条线。
- 跨平台适配：检测 macOS / Windows / Linux 下的 drawio CLI 路径差异。

## [0.5.1] - 2026-06-02

### 新增

- 新增 `scene-routing-guide.md`，提供大场景库下的评分法、冲突处理和主图/附图选择规则。
- 新增 `scene-routing-evals.md`，提供 20 个高冲突测试用例，用于检查场景误选。

### 改进

- 更新 `SKILL.md`，将场景选择流程调整为先路由、再查场景库、再生成 VizSpec。
- 更新 `vizspec-schema.md`，增加 `routing` 字段，要求记录主场景、备选场景和未选原因。
- 更新 `quality-checklist.md`，增加场景路由与备选场景检查项。

### 待办事项

- 后续新增场景时同步补充高冲突路由测试用例，避免场景库膨胀后误选。

## [0.5.0] - 2026-06-02

### 新增

- 新增法律全流程场景库，覆盖客户全生命周期、案件办理全流程、证据工作全生命周期、法律文书生产流程、企业经营全周期、争议解决路径全景和律师团队协作与项目管理。
- 在 `scene-composition-playbook.md` 中新增法律全流程场景编排规则，补充主图候选、必要字段和编排策略。

### 改进

- 更新 `SKILL.md` 触发描述和场景路由，使 Legal Viz 覆盖客户协作、团队办案、证据组织、文书生产和争议路径选择。
- 更新模板优先级，将客户生命周期路线图、案件办理路线图、证据生命周期图、文书生产流程图和争议路径选择图纳入 P0。

### 待办事项

- 后续增加法律全流程测试输入，验证客户生命周期、证据生命周期、案件办理路线和文书生产的一键出图质量。
- 将新增 P0 全流程图表沉淀为可复用 draw.io XML 片段。

## [0.4.0] - 2026-06-01

### 新增

- 扩充法律业务场景库，新增法律服务方案、客户汇报、合同流程、企业合规、投融资并购、劳动人事、知识产权、数据合规、债务化解、家族财富和行政监管场景。
- 在 `scene-composition-playbook.md` 中新增法律业务场景编排规则，覆盖主图候选、必要字段和编排策略。

### 改进

- 更新 `SKILL.md` 触发描述和工作流表述，使 Legal Viz 覆盖案件、非诉项目、合规管理、客户汇报和服务方案。
- 更新模板优先级，将服务路线图、范围-交付物矩阵、合同审查泳道、合规风险地图和交易架构图纳入 P0。

### 待办事项

- 后续将新增 P0 业务图表沉淀为可复用 draw.io XML 片段。
- 增加客户服务方案类测试输入，验证非诉项目一键出图质量。

## [0.3.0] - 2026-06-01

### 新增

- 新增 `scene-composition-playbook.md`，把场景索引扩展为可执行的图表编排手册。
- 新增 `vizspec-schema.md`，提供 Legal Viz 的结构化制图规格，提升一键出图稳定性。
- 新增 `templates/README.md`，说明现有模板定位和后续高频模板开发优先级。

### 改进

- 更新 `SKILL.md` 工作流，要求先生成 VizSpec，再按场景编排手册生成 draw.io。
- 将 `scene-library.md` 明确为场景索引，避免把索引误认为完整模板库。

## [0.2.2] - 2026-06-01

### 改进

- 移除内部文件中的非产品化表述。
- 将方法文件改名为 `visual-composition-rules.md`，统一为自有法律图表编排规则。
- 将描述调整为“法律可视化”“法律图表”“案件图表”等中性表达。

### 文档完善

- 更新 `SKILL.md`、`CLAUDE.md`、`TASKS.md`、`DECISIONS.md` 和场景库说明。

## [0.2.1] - 2026-06-01

### 改进

- 将 Skill name 从 `legal-drawio` 调整为 `legal-viz`，降低对 draw.io 工具名的传播依赖。
- 将对外展示名调整为 Legal Viz，中文定位保持“法律可视化”。
- 更新主入口描述，强调法律可视化场景优先，draw.io 作为默认可编辑源格式保留。

### 文档完善

- 更新 `CLAUDE.md`、`TASKS.md`、`DECISIONS.md` 中的命名和决策记录。

## [0.2.0] - 2026-06-01

### 新增

- 新增首批法律图表场景库，覆盖通用图表、借款、票据、建设工程、土地与房地产、国际货物买卖、公司股权、证据和复合案件。
- 新增法律图表编排规则引用文件，沉淀受众、图表类型、内容筛选和表达规则。
- 新增一步到位输出流程，明确 `.drawio`、SVG、PNG、PDF 的默认交付策略。
- 新增质量检查清单，覆盖事实表达、场景选择、视觉版面、draw.io XML 和导出图片检查。
- 新增 CC-BY-NC 许可证文件。

### 改进

- 将技能主入口从 6 类图表模板扩展为以场景路由驱动的一键出图流程。
- 将默认交付从“生成 XML/按需导出”调整为“默认导出可用图片并保留 draw.io 源文件”。
- 更新 frontmatter，增加版本、许可证、作者和主页信息。

### 文档完善

- 新增 `TASKS.md` 记录当前升级与后续模板化任务。
- 新增 `DECISIONS.md` 记录 draw.io 源文件加默认图片交付的技术路线决策。
