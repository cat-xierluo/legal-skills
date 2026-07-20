# CHANGELOG

## [0.3.3] - 2026-07-20

### 重构

- 刑事分析支架犯罪论体系由「四要件为主干 + 三阶层仅审查阻却事由」整体改为**不法—有责二阶层**（张明楷立场，2025 法考刑法标准体系）：先客观不法后主观有责，层层递进、任一层不过即出罪；完全移除四要件作为主干。
- 改动要点：
  - `references/criminal-case-analysis.md`：「犯罪构成框架说明」重写；第三步四要件对照表 → 二阶层递进审查表（不法：客观构成要件 / 主观不法要素 / 违法阻却；有责：责任能力 / 责任形式 / 责任阻却）；第四步共同犯罪由主犯/从犯平面列举 → 正犯/共犯二分 + 限制从属（附 13 岁少年共犯案实务价值），罪数补法条竞合/想象竞合的阶层定位；第八步结论按不法/有责两层给出；第五步证据缺口表、辩护对抗检验、最小输出格式表同步对接二阶层。
  - `SKILL.md`、`references/workflow.md` 刑事路由表述同步；版本 0.3.2→0.3.3。
- 体系选择依据与学理来源见 `references/iteration-context.md`「刑事犯罪论体系决策：不法—有责二阶层」节。

### 清理

- 清除刑事支架内对不存在的 `gutachten-criminal-case` 姊妹 skill 的全部交叉指路（`SKILL.md` / `workflow.md` / `iteration-context.md` / `criminal-case-analysis.md` / `CHANGELOG` / `DECISIONS`）。

## [0.3.2] - 2026-07-15

### 改进

- 完善刑事分析的违法/责任阻却事由审查：用三阶层（构成要件该当性 → 违法性 → 有责性）逐层审查，使正当防卫、紧急避险、责任能力、违法性认识可能性、期待可能性等阻却事由的评价结构更清晰，与四要件定罪主线配合。

## [0.3.1] - 2026-07-15

### 改进

- `references/criminal-case-analysis.md` 依据 GLM 5.2 跨模型试跑研判，固化五处高价值动作（把模型自发做对、但 skill 未显式引导的动作变成显式规则，让更弱模型也稳定做到）：
  - 第二步加「材料性质甄别」：先判断输入是完整卷宗 / 案情概述 / 起诉意见书叙述 / 混合；概述性叙述非法定证据，只作待核实线索。
  - 第五步加「法定证据种类核查」：《刑诉法》第 50 条八类证据逐类核对齐全性。
  - 第三步加「违法/责任阻却事由核查清单」：正当防卫 / 紧急避险 / 责任能力 / 违法性认识 / 期待可能性等，每案逐项过一遍。
  - 第八步「处理意见」从罗列升级为带条件判断（起诉 / 法定不诉 / 相对不诉 / 存疑不诉 / 附条件不诉 / 退补，各附适用条件与法条）。
  - 顶部加「输入完整度决定产出深度」note：概述级输入只出初步研判 + 证据缺口，不得下确定定罪 / 量刑结论。

## [0.3.0] - 2026-07-15

### 新增

- 新增 `references/criminal-case-analysis.md`，沉淀刑事案件分析法（四要件为主干，审查起诉骨架 + 辩护对抗检验），覆盖定罪、罪数与形态、证据审查（确实充分/排除合理怀疑/非法证据排除）、量刑与程序合法性，与民事/民商事的要件式九步法并列。

### 改进

- `references/workflow.md`：诉讼场景改为先判案件类型再选分析支架（民事→九步法 / 刑事→刑事八步法 / 行政→九步法基础上调整）。
- `references/element-litigation-nine-step.md`：开头标注适用范围为民事/民商事请求权争议，刑事转 `criminal-case-analysis.md`，纠正此前刑事被误导入民事请求权框架的问题。
- `SKILL.md`：描述补充“刑事案件研判与审查起诉分析”触发场景；工作方法导航加入刑事分析支架。
- `references/iteration-context.md`：references 清单补入刑事分析支架条目。
- 违法/责任阻却事由用三阶层（违法性、有责性）逐层审查，与四要件定罪主线配合。

## [0.2.6] - 2026-06-05

### 新增

- 新增 `references/analysis-engine-boundary.md`，明确 `legal-case-analysis` 是法律分析引擎，并说明与 `legal-proposal-generator` 的协作边界。
- 新增 `references/element-litigation-nine-step.md`，沉淀要件式诉讼分析九步法，作为诉讼和争议解决场景的分析支架。

### 改进

- 调整 `SKILL.md` 定位：法律分析不等同于报告生成，报告只是可选交付形态。
- 在 `references/workflow.md` 中加入分析底稿和要件式分析入口。
- 在 `references/iteration-context.md` 中补充分析引擎定位、跨 Skill 边界和后续迭代方向。

## [0.2.5] - 2026-06-05

### 新增

- 新增 `templates/simple-consultation-answer.md`，用于事实较少、目标单一的自然人咨询或简版法律答复。

### 改进

- 在 `SKILL.md` 输出类型和模板导航中加入简版咨询答复。
- 将 `references/report-depth-control.md` 中的简版答复结构改为引用模板，保持“方法进 references、交付格式进 templates”的分层。
- 在 `references/iteration-context.md` 中补充报告详略控制参考文件入口。
- 同步修正 `TASKS.md` 中已删除展示模板的历史性表述，避免与当前模板结构混淆。

## [0.2.4] - 2026-06-05

### 新增

- 新增 `references/report-depth-control.md`，用于按案件复杂度选择简版咨询、标准案件分析或复杂案件分阶段报告。

### 改进

- 在 `SKILL.md` 的工作方法导航中加入报告详略控制入口。
- 在 `references/workflow.md` 启动阶段增加复杂度和报告深度判断。
- 在 `references/iteration-context.md` 的后续迭代方向中加入报告详略控制校准样例。

## [0.2.3] - 2026-06-05

### 新增

- 新增 `references/iteration-context.md`，记录长期迭代上下文、分层原则、非目标、输出风格和后续演进方向。
- 新增 `LICENSE.txt`，按法律专业应用 Skill 使用 CC-BY-NC 许可证。

### 改进

- 补全 `SKILL.md` frontmatter：新增 `homepage`、`author`、`license` 字段，并将版本更新为 `0.2.3`。
- 在 `SKILL.md` 的工作方法导航中加入迭代上下文入口。

## [0.2.2] - 2026-06-05

### 改进

- 精简 `SKILL.md`：主文件只保留入口说明、核心原则、输入输出和资源导航。
- 将分析过程、工作方法和交付检查沉淀到 `references/`。
- 将最终交付格式集中到 `templates/`，保留法律分析报告、检索任务清单和客户说明模板。

### 文档完善

- 在 `references/workflow.md` 中补充交付前检查。
- 从主文件中移除试跑样例入口，降低主上下文负担。

### 调整

- 删除 `templates/presentation-outline.md`，避免将展示提纲与法律报告/检索交付模板混放。

## [0.2.1] - 2026-06-05

### 文档完善

- 将 `legal-case-analysis` 从竞赛方案目录迁入 `legal-skills/skills/` 项目目录，便于后续持续迭代。
- 保留现有 `references/`、`templates/`、`examples/` 和技能级文档结构。

### 待办事项

- 如后续正式公开发布，再补齐 marketplace 和 README 条目。

## [0.2.0] - 2026-06-05

### 新增

- 新增 `references/civil-commercial-analysis-workflow.md`，明确复杂民商事案件在法律检索之外的分析步骤。

### 改进

- 强化 `yuandian-law-search` 的默认优先检索地位：先检索现行法条、司法解释和类案，再基于检索结果分析。
- 在 `SKILL.md` 中补充“按法律分析步骤拆解案件”工作流。
- 在法律检索衔接规则中增加 `yuandian-law-search` 推荐调用顺序。
- 在报告模板中增加请求权基础、构成要件和检索结果回填要求。

## [0.1.2] - 2026-06-05

### 新增

- 新增 `examples/contest-sample-analysis.md`，基于竞赛案例生成脱敏试跑报告。
- 新增 `examples/skill-iteration-evaluation.md`，记录试跑暴露的问题和后续迭代方向。

### 改进

- 在 `SKILL.md` 中补充试跑样例入口。

## [0.1.1] - 2026-06-05

### 改进

- 精简 `SKILL.md` 元数据，仅保留名称、描述和版本。
- 移除包含署名、主页、联系方式和版权信息的授权文件。

## [0.1.0] - 2026-06-04

### 新增

- 创建 `legal-case-analysis` 通用法律分析 Skill 初稿。
- 新增核心工作流：案件画像、事实证据台账、法律问题树、检索任务、法律论证、报告输出。
- 新增与 `yuandian-law-search`、`zhihe-legal-research`、OCR 工具和 `md2word` 的松耦合协作说明。
- 新增四份参考文档：事实证据抽取、问题识别、法律检索衔接、论证与风险评估。
- 新增四份输出模板：法律分析报告、法律检索任务清单、客户说明、路演展示提纲。

### 待办事项

- 使用竞赛赛题材料试跑并根据结果迭代模板。
- 如正式发布至 legal-skills 仓库，补齐 marketplace 和 README 配置。
