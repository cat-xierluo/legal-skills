# 评测方法论（Anthropic + LLM-as-judge + benchmark 迁移）

> **来源**：DR-5《法律 Skill 评测前沿调研》（`research/issue-123-skill-eval-deep-research-chatgpt.md`，OpenAI Deep Research，2026-06-20）。
> 凡 Anthropic 等公开材料可核验的结论标"已核验"；本文件对 DR-5 的本地化转写标"本报告推断"（指 DR-5 报告的推断）。

本文件回答三个工程问题：① 评测怎么分层、用什么 grader；② LLM-as-judge 怎么校准才不漂移；③ 怎么用"双门槛"判定一个修补算不算真的修好。它是 SKILL.md「四-B 评测方法论」与「四-C LLM-as-judge 四校准」的依据文件，**不是新场景维度清单**——场景维度仍由 `scenarios/` 下三份清单负责。

## 一、三层评测栈与三类 grader（已核验 · Anthropic）

DR-5 综合多份 Anthropic 官方材料（Demystifying evals for AI agents、Define success criteria、Extend Claude with skills、multi-agent research system）得出一个一致结论：**agent 评测不宜追求一个抽象总分框架，而应分层 + 多 grader 混合**。法律 Skill 与之高度同构。

### 1. 三层评测栈（与 skill-lint 的两层划界互补）

| 层 | 内容 | 谁负责 | DR-5 出处 |
|----|------|--------|-----------|
| ① 规整性层 | 目录 / frontmatter / 引用 / 触发词 / 安全 / 业务流五层 / Hard Fail | **skill-lint** | DR-5「Demystifying evals」deterministic grader 的"结构 / 格式 / 字段"部分 |
| ② 输出合理性层 | 在某法律场景里输出是否完整、有据、不误导、不遗漏关键风险/要件 | **本技能（场景维度清单）** | DR-5「Anthropic LLM rubric grader」（coverage / groundedness / correctness） |
| ③ 专家 taste 层 | 只对高影响 / 高争议样本运行 pairwise / 人工复核 | 本技能 taste 项 + 人工 | DR-5「human grader + BigLaw Bench Arena」 |

①层是 skill-lint 的既有职责，本技能只引用其结论；②③两层是本技能主战场。这恰好把 v0.1.0 的"两层评测（规整性 / 输出合理性）"进一步拆细：②层里"可结构化的覆盖/根据/完整性"和③层里"不可结构化的说服力 / 商业语气"分开建模。

### 2. 三类 grader（已核验）

DR-5 从 Anthropic「Demystifying evals for AI agents」抽出三类 grader，**法律 Skill 应混合使用**，不是择一：

| grader 类型 | 法律场景对应做法 | 适用维度示例 |
|------------|----------------|------------|
| **deterministic（确定性）** | 字段存在性、条款编号格式、法源引用格式、必备要素是否齐、是否命中官方示范文本要素 | 合同字段抽取、诉状必备要素、合规依据精确到条款 |
| **model-based（LLM rubric）** | 用锁定 rubric + 证据锚定的 LLM judge 评覆盖 / 根据 / 完整性 / 是否把不确定写成确定 | 风险分级合理性、请求权基础定性、法源覆盖度 |
| **human（专家）** | 律师抽检高分歧 / 高影响样本，做 pairwise 偏好或人工 verdict | "能否真发给客户 / 法官"、说服节奏、商业语气 |

skill-lint 的 Hard Fail 检查本质是 deterministic grader（结构断言）；本技能的场景维度 1-6 评的是 model-based grader 该评的内容；taste 项是 human grader 的领域。

### 3. capability eval vs regression eval 分离（已核验）

Anthropic 明确把 eval 拆成两类，DR-5 建议法律 Skill 同样分开维护：

- **capability eval（能力评测）**：评"这个 Skill 能不能做这件事"。用一组覆盖场景典型难度的任务，目的是发现能力上限 / 短板。**少量、精选、有代表性**。
- **regression eval（回归评测）**：评"这次改动有没有把原来能做的事搞坏"。用一组历史真实失败案例回灌，每次改 SKILL.md / references 后都跑一遍。

本技能落地：每场景（合同 / 诉讼 / 合规）建议各维护**两套 case bundle**——capability suite（20-30 例覆盖典型难度）+ regression suite（真实失败案例回灌，可持续增长）。两者**不能混用**：拿 capability suite 验回归会漏掉边角失败；拿 regression suite 评能力会被历史失败带偏。

### 4. 20-50 个真实失败案例够第一版（已核验）

DR-5 从 Anthropic 抽出两个明确数字：**20-50 个来自真实失败案例的任务，在早期就足以构成第一版 eval**；每个任务尽量做到"两个领域专家能独立给出同样的 pass/fail verdict"，并为任务准备 reference solution 以证明任务与 grader 可用。

落地口径：本技能 v0.1.0 的"三份测试法"（熟悉 / 同类不熟悉 / 缺失背景）是**评测一次 Skill 输出**的最小材料集；v0.2.0 起，**做长期迭代的 Skill 还应沉淀 20-50 个真实失败案例**作为 regression suite 起点。两者不冲突：三份测试法用于单次评测，20-50 例 case bundle 用于长期回归。

## 二、参考解的三档口径（已核验 + 本报告推断）

DR-5 明确标注：**本轮未在 Anthropic 官方公开材料中核验到以 "golden answer" 为正式术语、且专门面向 skill-creator 的官方数据结构定义**。公开可核验的是 test cases、expected behavior、assertion grading、benchmark、blind A/B、description tuning。

因此本技能**不再使用"黄金答案"这一术语**，改用 DR-5 建议的三档口径（本报告推断是对 Anthropic reference solution + CoCounsel ideal response + LeMAJ reference-free 的本地化合成）：

| 档位 | 适用任务 | 做法 | 法律场景示例 |
|-----|---------|------|------------|
| **reference-rich（参考解富集）** | 可枚举、可对照、有唯一或近唯一正确答案 | 写 reference solution / ideal response，用 deterministic + LLM rubric 对照 | 合同字段抽取、诉状必备要素、法源引用是否正确、结论是否覆盖必要条件 |
| **reference-light（参考解轻量）** | 多个可接受答案但仍可拆成数据点 / 法点 | 写 ideal response，加 material omission / incorrectness / hallucination 三条规则；允许 minor deviation | 合同审查意见、检索报告、合规 memo |
| **reference-free（无参考解）** | 强依赖审美与职业判断 | LeMAJ 式分解（把答案拆成 Legal Data Points 评正确 / 相关 / 遗漏）+ pairwise 专家偏好 + 抽样人工 | 诉讼说服力、商业风险措辞、客户偏好匹配 |

> v0.1.0 SKILL.md 第五节、six-dimensions-origin.md 第五节原先写的"自动化黄金答案比对"表述，**已在 v0.2.0 修订为"参考解三档口径"**，避免暗示 Anthropic 有此正式机制。

落地：评测某 Skill 时，先按它的声称交付物归入某一档，再决定该准备 reference solution、ideal response，还是直接走 reference-free 分解。三场景维度清单（contract / litigation / compliance）末尾的 taste 项，多数属于 reference-free 档（说服节奏、商业语气等），不应强求写参考解。

## 三、LLM-as-judge 四校准（已核验 · 关键）

DR-5 综述多篇论文（MT-Bench / Chatbot Arena、Judging the Judges、PoLL、Pairwise or Pointwise、RULERS、LongJudgeBench、Two Ways to De-Bias、LeMAJ）后给出明确结论：**LLM-as-judge 能用，但不能裸用**。已知问题：position bias、verbosity bias、自我偏好、尺度漂移、长文不稳定、pairwise 对表面特征脆弱。

DR-5 提炼出**四个校准动作**，本技能把它们写进评测流程（见 SKILL.md 四-C）：

### 1. 锚点样本（anchor sample）

用少量典型好 / 中 / 差答案先校量尺，矫正 judge 宽严不一、量尺压缩、风格偏差。**每个场景准备一小组锚点样本**（contract / litigation / compliance 各 3-5 例覆盖好 / 中 / 差），让 judge 在打分前先"读到"该团队对"2 分 vs 4 分"的口径。DR-5 出处：Two Ways to De-Bias、Calibrated LLM Jury in medicine。

### 2. 顺序翻转（pairwise 防位置偏差）

若做 pairwise 比较，**必须随机打乱左右顺序、做顺序翻转、记录一致性**。否则"前一个看起来更像律师写的"会被系统性高估。DR-5 出处：Judging the Judges（系统证明位置偏差非随机噪声）。法律文书 pairwise 时若翻转后 verdict 翻转，该样本必须升级人工。

### 3. 多 judge 共识（PoLL 异质 panel）

用一个强 judge + 两个便宜 judge 组成异质 panel（PoLL，Panel of LLMs），降低 intramodel bias；**低置信度 / 高分歧样本升级到人工**。DR-5 出处：Replacing Judges with Juries。早期项目 judge 数量不必多（强 1 + 便宜 2 已够筛争议样本）。

> **暂缓提醒**（已核验）：DR-5 引用最新 panel calibration 研究指出，是否值得上更复杂的多 judge 联合校准，取决于可用人工标签预算与 judge 间交互是否可估；**早期项目通常不划算**。本技能默认 3 judge panel，不鼓励一上来就做复杂聚合。

### 4. 证据锚定（evidence-anchored scoring）

要求 judge **给出其判分所依据的法源、条款或文书片段**（evidence-anchored），而不是只给一个裸分。把自然语言 rubric 编译成锁定、可执行、证据锚定的评分规范（locked rubric）。DR-5 出处：RULERS（locked rubric + evidence-anchored scoring）。

法律场景最怕 rubric 漂移；evidence-anchored 几乎就是法律输出评测天然需要的方向——判"法源覆盖度低"必须指明漏了哪部法规第几条，判"请求权基础混乱"必须指明主张与依据在哪一句不对应。

### 补充：长文 judge 单独建模（已核验）

DR-5 引 LongJudgeBench：LLM judge 在长文输出上稳定性明显下降，rubric 和 reference 也不总是够。**答辩状、起诉状、合规 memo 都是长文**，长文 judge 的不稳定性必须被单独建模，不能直接套用短答 judge 的经验。

落地：诉讼型、合规型长文输出，judge panel 配置应更保守（更多锚点样本、更窄的 rubric、更多人工抽检），不能照搬合同字段抽取这类短任务的 judge 参数。

## 四、SWE-bench 双门槛迁移（已核验 · 需改造）

DR-5 引 SWE-bench Verified：用 **FAIL_TO_PASS / PASS_TO_PASS 双重测试**验证任务是否被真正修复——既要求原本失败的测试通过（FAIL_TO_PASS），又要求原本通过的测试仍通过（PASS_TO_PASS，防止改一处坏一片）。

法律文书没有单元测试，但 DR-5 明确指出这个思想可直接迁移：**"补齐关键遗漏且不引入新问题"的双门槛**。

| 门槛 | SWE-bench 原义 | 法律 Skill 迁移义 |
|-----|---------------|-----------------|
| **FAIL_TO_PASS** | 原本失败的测试现在通过 | 本次修补是否补齐了原来的关键遗漏（漏法源 / 漏条款 / 漏要件 / 漏风险） |
| **PASS_TO_PASS** | 原本通过的测试仍通过 | 本次修补是否**没有**新增幻觉 / 逻辑冲突 / 越界结论 / 把草稿写成正式意见 |

落地：评测一个 Skill 的某次迭代时，**不能只看 FAIL_TO_PASS**（"上次漏的条款这次补上了"），必须同时跑 PASS_TO_PASS（"补这条的同时有没有引入新问题"）。后者命中任何一条，迭代不算成功，回退重做。这与本技能 taste 项核查天然耦合——多数 taste 项（混淆法律风险与商业谈判点、把不确定写成确定、混淆本方与对方主张）正是 PASS_TO_PASS 要守的底线。

## 五、taste 结构化的边界（已核验 + 本报告推断）

DR-5 综合多篇研究（Pairwise or Pointwise、BigLaw Bench Arena、LeMAJ、CoCounsel ideal response、I beg to differ、Best-Worst Scaling、Counting on Consensus）给出折中方案：**经验律师的 taste 至少有一半可结构化，剩余保留 pairwise / 人工**。

### 1. 可结构化的 taste 项（适合 rubric / 断言 / evidence-anchored）

DR-5「本报告推断」列出以下可结构化项（多数已在 v0.1.0 三场景 taste 清单里）：

- 是否遗漏关键条件、例外或保留
- 是否把不确定说成确定
- 是否引用错误法源或错误层级
- 是否在文书中出现逻辑冲突
- 是否未区分事实、法律判断与策略建议
- 是否与官方文本样式 / 程序位置不匹配
- 是否应升级人工但未提示

这些可用 ideal response、Legal Data Points、断言检查、evidence-anchored scoring 来做。三场景 taste 清单已覆盖大部分，v0.2.0 不再扩列，但补一条元规则：**凡可结构化的 taste 项，必须能写出"判它命中需要依据哪条法源 / 哪个条款 / 哪句输出"**，否则不算真正结构化。

### 2. 应保留 pairwise / 人工的 taste 项（已核验）

DR-5 明确这些不宜压成绝对评分：

- 行文是否"够像要出门的成稿"
- 说服力是否足以面对特定法官 / 对手
- 风险口径是否符合特定客户偏好
- 是否把握了特定法官 / 地区 / 行业的隐性偏好
- 复杂商业语境下"虽然字面正确但不专业"的直觉

工业实践（Harvey BigLaw Bench Arena）选择让律师直接 head-to-head 比偏好，而不是硬把这类问题压成统一 rubric——这恰说明这里更适合 pairwise 与人工复核。

### 3. pairwise vs 绝对评分的协议选择（已核验 · 关键）

DR-5 引 Pairwise or Pointwise：**pairwise 偏好翻转约 35%，绝对评分约 9%**。法律文书易被篇幅、行文气势、模板感误导，pairwise 在这种场景下更脆弱。

落地口径（写进 SKILL.md 四-C）：

- **"是否完整 / 是否误导 / 是否虚构 / 是否遗漏"** 这类有客观参照的判断 → 用**绝对评分（pointwise）**，更稳。
- **"哪份更像能发出去 / 哪份更有说服力"** 这类纯主观偏好 → 用 **pairwise**，但必须配合顺序翻转 + 锚点样本。
- **不要一律 pairwise**——这是常见误用。

## 六、中国法律语境的特殊层（已核验）

DR-5 综合最高法案例库、示范文本、诉讼文书样式、LAiW、TW-LegalBench、JuDGE 得出明确结论：**中国诉讼 / 合规类 Skill 的评测，至少要有一层检查"是否符合官方模板生态与裁判 / 检索生态"**。

### 1. 三类官方制度资源（已核验）

- **最高法案例库**：同类案件审理应参考入库案例，统一体例提升检索精度与裁判尺度统一。
- **示范文本**：最高法、司法部、全国律协自 2025 年起全面推广部分案件起诉状 / 答辩状示范文本，覆盖 9 个领域 67 类常见纠纷。
- **诉讼文书样式与文书类别体系**：最高法长期维护。

### 2. 把"律师一眼觉得不对"拆成三层可判定结构（本报告推断）

DR-5「本报告推断」：如果法律 Skill 产出物含中文诉讼文书，评测至少把"是否像律师写的"拆成三层：

1. **官方结构与要素是否齐**——是否符合示范文本 / 文书样式的必备要素（deterministic grader 可查）。
2. **所引法源、案由、程序位置是否对**——案由匹配请求权基础、法源层级与时效正确、程序位置（一审 / 二审 / 再审 / 特别程序）准确（LLM rubric + evidence-anchored）。
3. **对裁判尺度与案例检索资源的使用是否像中国实务**——是否参考同类入库案例、是否贴合裁判要旨与案情关键词的对应、是否避免"像一般大模型作文"（human + 案例库对照）。

### 3. civil-law 不能套 common-law benchmark（已核验）

DR-5 引 LAiW、TW-LegalBench：**不能把 common-law 的 case reasoning benchmark 直接当成 civil-law 语境下的能力代理**。LAiW 明确用 legal syllogism 解释中文法律能力结构，并指出自动评测看起来"会写"，但专家人工评审会发现其缺乏真正的法律三段论严谨性。

落地：本技能**不引用 LegalBench / LexGLUE / LAiW 等公开 benchmark 的分数作为产出物质量指标**——它们适合能力筛查，不宜代替真实工作产品验收（DR-5 明确建议暂缓）。三场景维度清单仍以"产出物在真实场景里合不合格"为准。

## 七、暂缓事项（已核验 · DR-5 明确建议）

DR-5 列出四项**建议暂缓**的方向，本技能在 v0.2.0 同步采纳：

1. **暂缓构建跨合同 / 诉讼 / 合规的统一总分模型**。现有最好实践都更支持 task-specific grading（Harvey BigLaw Bench、CoCounsel、Anthropic）。本技能 v0.1.0 已明确"不输出通用总分"，v0.2.0 维持。
2. **暂缓把"说服力 / 专业感"全自动化成唯一 pass/fail**。长文 judge 在这类任务上仍有不稳定性，pairwise 也可能被表面风格扰动（LongJudgeBench、Pairwise or Pointwise）。
3. **暂缓在样本不足时做复杂多 judge 联合校准**。是否值得上更复杂聚合取决于人工标签预算与 judge 间交互可估性（panel calibration 研究）；早期项目默认 3 judge panel，不扩。
4. **暂缓把公开法律 benchmark 分数直接当成产出物质量指标**。LegalBench / LexGLUE / LAiW 适合能力筛查，不宜代替真实工作产品验收。

## 八、最小可行迭代（DR-5 建议 · 本报告推断）

DR-5 对 #119 的最小可行迭代建议（本报告推断，已部分在 v0.1.0 落地，v0.2.0 补齐剩余）：

- 三套最小场景包：合同 20-30 例、诉讼 20-30 例、合规 20-30 例。
- 每套含：reference / ideal response、critical omissions、should-pass / should-fail、pairwise taste sample。
- 明确 capability suite 与 regression suite 分离。

v0.1.0 已落地：三场景维度清单 + taste 项 + skill-lint 划界 + 三份测试法。
v0.2.0 补齐：eval 方法论（capability/regression 分离 + 三类 grader + 20-50 案例）、参考解三档口径、LLM-as-judge 四校准、SWE-bench 双门槛、中国法律语境三层、taste 结构化边界、暂缓事项。

**尚未落地（留待真实法律 skill 校准）**：用真实合同 / 诉讼 / 合规 Skill 各 1-2 个跑评测，把 20-50 例 case bundle 真正沉淀出来。这是 v0.3.0 的主任务，不是 v0.2.0 能闭卷完成的（见 TASKS.md）。

## 九、来源登记

本文件所有结论的逐条来源见 DR-5 报告来源登记表（40 条），其中与本技能最相关：

- Anthropic 官方：Demystifying evals for AI agents、Define success criteria and build evaluations、Extend Claude with skills、Building effective agents、How we built our multi-agent research system、A statistical approach to model evaluations。
- LLM-as-judge：MT-Bench / Chatbot Arena、Judging the Judges（position bias）、PoLL（Replacing Judges with Juries）、Pairwise or Pointwise、RULERS、LongJudgeBench、Two Ways to De-Bias、LeMAJ。
- benchmark：SWE-bench Verified、WebArena / WebArena Verified、τ-bench、GAIA。
- 法律专属：LegalBench、LexGLUE、Harvey BigLaw Bench / LAB / Contract Intelligence / Arena、Thomson Reuters CoCounsel、JuDGE、LegalEval-Q、LAiW、TW-LegalBench。
- 中国官方：最高法案例库、示范文本、诉讼文书样式。
- 标注分歧：I beg to differ、Best-Worst Scaling、Counting on Consensus。

完整 URL 与核验状态见 DR-5 报告第 194-237 行。
