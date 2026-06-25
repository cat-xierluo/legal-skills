# CHANGELOG

## [v0.2.0] - 2026-06-20

### 背景
融入 **#123 / DR-5**《法律 Skill 评测前沿调研》（OpenAI Deep Research，2026-06-20，`research/issue-123-skill-eval-deep-research-chatgpt.md`，40 条来源逐条核验）。DR-5 的核心结论是"法律 Skill 评测不宜追求一套跨场景通用大一统维度，而应采用场景化 rubric + 多 grader 混合 + 专家校准"——这与 v0.1.0 既有定位（不构建通用六维度、按场景、回归 taste、与 skill-lint 划界）完全同向，本次迭代把 DR-5 的可落地方法吸收进既有框架，不另起通用基准。

### 新增
- **评测方法论依据文件** `references/eval-methodology.md`：三层评测栈 + 三类 grader（deterministic / model-based / human）+ capability/regression 分离 + 参考解三档口径 + LLM-as-judge 四校准 + SWE-bench 双门槛迁移 + 中国法律语境三层 + taste 结构化边界 + 暂缓事项。是 SKILL.md 方法论三子节的依据文件。
- **SKILL.md 评测流程补强**：在 v0.1.0 步骤 1-7 之后补三个方法论子节——评测方法论（别名 四-B）/ LLM-as-judge 四校准（别名 四-C）/ 双门槛判定（别名 四-D）。**不替换** v0.1.0 主流程。
- **LLM-as-judge 四校准**：锚点样本 / 顺序翻转（防 pairwise 位置偏差，约 35% 偏好翻转）/ 多 judge 共识（PoLL 异质 panel，低置信升级人工）/ 证据锚定（RULERS locked rubric，judge 必须给所依赖法源/条款/片段）。补充长文 judge 单独建模（LongJudgeBench：答辩状/起诉状/合规 memo 是长文，不能套短答经验）+ pairwise vs 绝对评分协议选择（防"一律 pairwise"误用）。
- **SWE-bench 双门槛迁移**：FAIL_TO_PASS（补齐关键遗漏）+ PASS_TO_PASS（不新增幻觉/逻辑冲突/越界结论）双门槛，用于"评测某次迭代后的修补是否算成功"。与 taste 项核查天然耦合。
- **中国法律语境三层**（诉讼型专属）：官方结构与要素是否齐（示范文本/文书样式，deterministic 可查）/ 法源案由程序位置是否对（LLM rubric + evidence-anchored）/ 裁判尺度与案例检索资源使用是否像中国实务（human + 案例库对照）。补到 `litigation-scenario-rubric.md` 第三节，指向 `eval-methodology.md` 第六节。
- **评测报告模板补两段**：`templates/skill-evaluation-report.md` 新增"四校准动作记录"（仅启用 LLM judge 时填）+ "双门槛判定"（仅评测某次迭代时填）。

### 变更
- **术语**：v0.1.0 使用的"黄金答案"表述，依据 DR-5「未核验说明」（该术语未在 Anthropic 官方公开材料核验到），**改为"参考解三档口径"**（reference-rich / reference-light / reference-free）。涉及 `SKILL.md` 第五节、`references/six-dimensions-origin.md` 第五节。
- **SKILL.md description**：补"基于 DR-5 前沿：场景化 rubric + 多 grader 混合 + 专家校准"。
- **SKILL.md version**：0.1.0 → 0.2.0。
- **SKILL.md 参考规则段**：列入 `references/eval-methodology.md`。

### 暂缓（DR-5 明确建议，本版本同步采纳）
- 暂缓构建跨合同/诉讼/合规的统一总分模型。
- 暂缓把"说服力/专业感"全自动化成唯一 pass/fail（长文 judge 不稳定、pairwise 对表面特征脆弱）。
- 暂缓在样本不足时做复杂多 judge 联合校准（早期项目默认 3 judge panel）。
- 暂缓把公开法律 benchmark（LegalBench / LexGLUE / LAiW）分数直接当成产出物质量指标。

### 不变（保留 v0.1.0 核心定位）
- 不构建通用六维度基准；按法律场景（合同/诉讼/合规）分维度评测产出物质量。
- 与 skill-lint 划界（规整性层 vs 输出合理性层），本技能只负责第二层。
- 评测目的：定位"要回 SKILL.md 补哪句话"，而非给 Skill 打总分。
- 三份测试法（熟悉/同类不熟悉/缺失背景）仍是单次评测的最小材料集。

### 待办（v0.3.0 主任务）
- 用真实合同/诉讼/合规 Skill 各 1-2 个跑评测，把 20-50 例 case bundle（capability suite + regression suite）真正沉淀出来。这是闭卷完成不了的，需真实 skill 校准。

## [v0.1.0] - 2026-06-20

### 新增
- 首版法律 Skill 场景化评测 skill（来源：法律AI书 ch07 第六节 #91 / #119，游初《二轮对焦》）。
- **核心定位**：不构建通用六维度基准，按法律场景（合同 / 诉讼 / 合规）分维度评测**产出物质量**；与 `skill-lint` 划界（规整性层 vs 输出合理性层）。
- **三场景维度清单**：`contract` / `litigation` / `compliance`，各含 taste 项（经验律师一眼觉得不对的东西显式化）。
- 评测目的：定位"要回 SKILL.md 补哪句话"，而非给 Skill 打总分。

### ⚠️ 开放难题（作者 2026-06-20 明确）
验证法律 Skill 产出物质量、不同文书不同标准、taste 结构化是**开放难题，非一次创建可定**。v0.1.0 为**起点**，待 **#123 / DR-5**（skill eval 前沿调研，在法律AI书仓库 `research/deep-research-prompts/DR-5-skill-eval.md`）回传后迭代维度集。详见 TASKS.md。
