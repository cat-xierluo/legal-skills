---
name: skill-evaluation
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.2.0"
license: MIT
description: 法律 Skill 的场景化评测工具（基于 DR-5 前沿：场景化 rubric + 多 grader 混合 + 专家校准）。本技能应在用户需要评测一个法律 Skill（合同、诉讼、合规、法律检索、文书起草、尽调等）能不能用、输出质量是否合格、是否回归到某个法律场景的真实判断标准时使用；触发词包括"评测 skill""验证 skill 可用性""skill 质量""eval skill""skill 评测""这个法律 skill 好不好用""合同 skill 怎么评""诉讼 skill 怎么评"。不构建通用六维度基准；规整性（目录、frontmatter、安全、发布）由 skill-lint 负责，本技能不重复造，只对接其结论并在此基础上做内容质量评测。不要用于：创建新 Skill（用 skill-creator / legal-knowledge-engine）、纯格式 lint（用 skill-lint）、通用代码审查。
---

# Skill Evaluation（法律 Skill 场景化评测）

本技能解决一个具体问题：一个法律 Skill 跑出来的输出，**在它声称覆盖的那个法律场景里**，到底合不合格。

它不假装能给所有 Skill 一套放之四海皆准的分数表。合同初审、诉讼文书起草、合规风险扫描、法律检索，它们的合格标准长得完全不一样；强行套一套维度，只会让评测本身成为又一个看起来严谨但没用的产物。

## 一、核心定位（与 ch07 第六节 #91 协同）

本书第七章第六节原来给了一套"六维度评价标准"（法律准确性 / 事实叙述与证据运用 / 逻辑说服力 / 争议焦点把握 / 实务可用性 / 文书格式完整度）。那是**面向合同初审这类文书型输出的参考起点**，不是通用基准。

- 合同型输出，那套六维度基本适用。
- 诉讼型输出（起诉状、答辩状、代理词），重点会偏到请求权基础、证据组织、诉讼请求与理由的对应，六维度覆盖不全。
- 合规型输出（合规风险扫描、整改建议），重点会偏到风险等级判定、监管依据精确度、整改路径可执行性，又是另一套侧重。

本技能的责任：**按场景把评测维度讲清楚**，并在维度之外强调每个法律人自己的 taste——某些东西是"对场景敏感的律师"一眼就会觉得不对，这些 taste 项必须被显式列出，不能被通用维度稀释掉。

## 二、两层评测，与 skill-lint 划界

法律 Skill 的"好不好用"可以拆成两层，**本技能只负责第二层**：

| 层 | 内容 | 负责工具 | 本技能做什么 |
|----|------|----------|--------------|
| ① 规整性层 | 目录结构、frontmatter、引用一致性、触发词边界、安全、发布版本、Hard Fail、业务流深度（Trigger/Intake/Reasoning/Output/Safety 五层是否齐备） | **skill-lint** | 不重复造。读取其审查报告或结论，作为本技能"结构是否可评测"的前置条件 |
| ② 输出合理性层 | 在某个法律场景里，输出内容是否准确、忠实、可执行、符合该场景交付物的真实判断标准 | **skill-evaluation（本技能）** | 本技能的主战场 |

划界规则：

- 如果被评测 Skill 还没过 skill-lint 的 Hard Fail（编造依据、未标注信息不足却给确定结论、把草稿当正式意见等），**先回去修 Hard Fail**，再做内容评测。在 Hard Fail 之上做内容评测没有意义。
- 如果用户跳过 skill-lint 直接要内容评测，本技能会先把 skill-lint 的可评估性基础项（是否声明评估范围、是否有 Hard Fail、是否有 benchmark case、是否有输出验收标准、是否区分静态检查与动态评估）当作"结构是否可评测"的前置，缺了就提示补；不替代 skill-lint 出正式质量意见报告。
- skill-lint 的"业务流深度"判则评的是**文档是否承载了流程**；本技能评的是**这个流程跑出来的结果对不对**。两者互补，不重叠。

## 三、评测流程与方法论

本节是 v0.2.0 的主结构。下面四个子节按"流程—方法论—校准—判定"顺序排：

- **步骤 1-7（评测流程）**：怎么从识别场景跑到产出报告。v0.1.0 既有内容，v0.2.0 不改主流程。
- **评测方法论**：分层栈 + 三类 grader + capability/regression 分离 + 参考解三档口径（来源 DR-5）。
- **LLM-as-judge 四校准**：锚点样本 / 顺序翻转 / 多 judge 共识 / 证据锚定 + 长文单独建模 + pairwise vs 绝对评分（来源 DR-5）。
- **双门槛判定**：FAIL_TO_PASS / PASS_TO_PASS（来源 DR-5，SWE-bench 迁移）。

后三个子节是 v0.2.0 新增的方法论补强，**不替换** v0.1.0 的流程；它们告诉评测人在"步骤 5 逐维度评分 + 步骤 6 定位要补哪句话"这两步里，怎么把分判得更稳、把修补判得更严。方法论的依据文件是 `references/eval-methodology.md`。

> 注：方法论的三个子节在文档里以 `评测方法论` / `LLM-as-judge 四校准` / `双门槛判定` 为标题，对应 `references/eval-methodology.md` 的第一至六节（eval-methodology.md 内部引用本 SKILL 时使用"四-B / 四-C / 四-D"作为别名，即此处三个子节）。

### 步骤 1：识别被评测 Skill 声称覆盖的法律场景

读 SKILL.md 的 description、使用场景、输入材料、输出格式、边界提醒。回答：

- 它声称覆盖**哪一类**法律场景？（合同 / 诉讼 / 合规 / 法律检索 / 文书起草 / 尽调 / 法律咨询答复 / 其他）
- 它声称的交付物是什么？（初审意见、风险表、起诉状、答辩状、检索报告、合规清单、尽调备忘录……）
- 它声称的交付对象是谁？（内部业务、外部客户、合规律师、诉讼律师、法官……）

如果它声称覆盖多类场景，要求用户指定本次评测针对哪一类；本技能**不做跨场景的"平均分"**。

### 步骤 2：前置——结构是否可评测

调用或读取 skill-lint 结论，确认：

- 是否声明了评估范围
- 是否声明了 Hard Fail
- 是否提供了 benchmark case 或样例
- 是否提供了输出验收标准
- 是否区分了静态检查与动态评估

任一项缺失，在评测报告里记为"结构性缺口"，并提示用户先回 skill-lint 补齐；不阻塞本次内容评测，但要在报告里明确"本次评测基于不完整结构"。

### 步骤 3：按场景选择评测维度集

读取 `references/scenarios/` 下对应场景的维度清单：

- `contract-scenario-rubric.md`：合同型输出（初审 / 审查 / 起草）
- `litigation-scenario-rubric.md`：诉讼型输出（起诉状 / 答辩状 / 代理词 / 证据目录）
- `compliance-scenario-rubric.md`：合规型输出（风险扫描 / 整改建议 / 尽调备忘录）

未被清单覆盖的场景（如法律检索、文书润色），先用合同型作为最接近的起点，并在报告里明确标注"本次评测降级套用合同型维度，建议补充该场景专属清单"。

### 步骤 4：跑测试材料

要求用户至少提供三类测试材料（对齐 ch07 第六节"三份测试法"）：

- 一份用户非常熟悉的材料（检查是否抓住该场景的重点）
- 一份同类但不熟悉的材料（检查结构是否稳定）
- 一份故意缺失关键背景的材料（检查边界是否稳定）

让被评测 Skill 对每份材料产出输出。

### 步骤 5：逐维度评分 + taste 项核查

对每份输出按所选场景维度清单逐项打分（1–5 分，初评不追求精密），并**单独核查 taste 项**（每个场景维度清单末尾的"场景 taste 项"，是经验律师一眼会觉得不对的东西，必须显式列出，不能被维度稀释）。

### 步骤 6：定位要补哪句话（不是给 Skill 打总分）

评测的目的不是给 Skill 一个 4.2 分的标签，而是定位"要回 SKILL.md 补哪句话"。对每个低分项或 taste 命中项，给一句可执行的修补建议（参照 ch07 第六节"验证后如何修补 Skill"表）。

### 步骤 7：产出评测报告

用 `templates/skill-evaluation-report.md` 输出。报告必须包含：

- 被评测 Skill 路径、声称场景、声称交付物、声称交付对象
- skill-lint 前置结论摘要（含结构性缺口）
- 本次使用的测试材料清单（脱敏，不写入真实当事人 / 案号 / 客户名）
- 按场景维度逐项评分表
- taste 项核查结果
- 定位到的"要补的句子"清单（每条对应一个低分项或 taste 命中项）
- 四校准动作记录（若本次用 LLM judge，见四-C；纯人工评测则标"本次未启用 LLM judge"）
- 双门槛判定（见四-D，针对"某次迭代后的修补是否算成功"）
- 总体结论：✅ 进入工作流 / ⚠️ 修后再测 / ❌ 回退到 Hard Fail 或场景识别

### 评测方法论（别名 四-B）

> 完整依据见 `references/eval-methodology.md` 第一节、第二节。本子节只列落地口径。

**三层评测栈 + 三类 grader**。本技能把"好不好用"拆成三层：① 规整性层（skill-lint 负责，本质是 deterministic grader）；② 输出合理性层（本技能场景维度清单，是 model-based LLM rubric grader 的领域）；③ 专家 taste 层（human grader）。三层**混合使用、不择一**：deterministic 查字段/格式/官方要素，model-based 查覆盖/根据/完整性，human 查说服力/商业语气。

**capability eval 与 regression eval 分离**。每场景（合同/诉讼/合规）建议各维护两套 case bundle：capability suite（20-30 例覆盖典型难度，评能力上限）+ regression suite（真实失败案例回灌，每次改 SKILL.md/references 后跑，防回归）。两者**不能混用**。

**20-50 个真实失败案例够第一版**（已核验，来源 Anthropic）。本技能 v0.1.0 的"三份测试法"用于**单次评测**；做长期迭代的 Skill 还应沉淀 20-50 例真实失败案例作为 regression suite 起点。两者不冲突。

**参考解三档口径**（v0.2.0 替换 v0.1.0 的"黄金答案"表述）：

| 档位 | 适用任务 | 做法 |
|-----|---------|------|
| reference-rich（参考解富集） | 可枚举、可对照、有唯一或近唯一正确答案 | 写 reference solution / ideal response，deterministic + LLM rubric 对照 |
| reference-light（参考解轻量） | 多个可接受答案但仍可拆成数据点 | 写 ideal response，加 material omission / incorrectness / hallucination 三条规则，允许 minor deviation |
| reference-free（无参考解） | 强依赖审美与职业判断 | LeMAJ 式分解（拆成 Legal Data Points 评正确/相关/遗漏）+ pairwise 专家偏好 + 抽样人工 |

> **未核验说明**（DR-5 明确标注）：本轮未在 Anthropic 官方公开材料中核验到以 "golden answer" 为正式术语、且专门面向 skill-creator 的官方数据结构定义。本技能使用的"参考解 / ideal response / reference solution"术语是 DR-5 对 Anthropic reference solution + CoCounsel ideal response + LeMAJ reference-free 的**本地化合成（本报告推断）**，不是 Anthropic 官方命名。

### LLM-as-judge 四校准（别名 四-C）

> 完整依据见 `references/eval-methodology.md` 第三节、第五节。本子节只列四个动作。

DR-5 结论：**LLM-as-judge 能用，但不能裸用**。已知问题：position bias、verbosity bias、自我偏好、尺度漂移、长文不稳定、pairwise 对表面特征脆弱。本技能在四-A 步骤 5（逐维度评分）启用 LLM judge 时，**必须执行四个校准动作**：

1. **锚点样本**：每场景准备 3-5 例覆盖好/中/差的锚点样本，让 judge 打分前先读到该团队对"2 分 vs 4 分"的口径。矫正宽严不一、量尺压缩、风格偏差。
2. **顺序翻转**：做 pairwise 时必须随机打乱左右顺序、做顺序翻转、记录一致性。翻转后 verdict 翻转的样本，必须升级人工。
3. **多 judge 共识**：一个强 judge + 两个便宜 judge 组成异质 panel（PoLL）；低置信度/高分歧样本升级人工。早期项目默认 3 judge，不鼓励一上来做复杂聚合（DR-5 引 panel calibration 研究明确建议暂缓）。
4. **证据锚定**：judge 必须给出其判分所依据的法源、条款或文书片段（evidence-anchored），不接受裸分。判"法源覆盖度低"必须指明漏了哪部法规第几条，判"请求权基础混乱"必须指明主张与依据在哪一句不对应。

**长文 judge 单独建模**：答辩状、起诉状、合规 memo 都是长文，长文 judge 稳定性明显下降（DR-5 引 LongJudgeBench）。诉讼型、合规型长文输出的 judge panel 配置应更保守（更多锚点样本、更窄 rubric、更多人工抽检），不能照搬合同字段抽取这类短任务的 judge 参数。

**pairwise vs 绝对评分**（关键，防误用）：pairwise 偏好翻转约 35%、绝对评分约 9%（DR-5 引 Pairwise or Pointwise）。

- "是否完整 / 是否误导 / 是否虚构 / 是否遗漏"这类有客观参照的判断 → 用**绝对评分**，更稳。
- "哪份更像能发出去 / 哪份更有说服力"这类纯主观偏好 → 用 **pairwise**，但必须配合顺序翻转 + 锚点样本。
- **不要一律 pairwise**——这是常见误用。

### 双门槛判定（别名 四-D）

> 完整依据见 `references/eval-methodology.md` 第四节。

DR-5 引 SWE-bench Verified：用 **FAIL_TO_PASS / PASS_TO_PASS 双重测试**验证任务是否被真正修复。法律文书没有单元测试，但 DR-5 明确这个思想可直接迁移成"补齐关键遗漏且不引入新问题"的双门槛：

| 门槛 | SWE-bench 原义 | 法律 Skill 迁移义 |
|-----|---------------|-----------------|
| **FAIL_TO_PASS** | 原本失败的测试现在通过 | 本次修补是否补齐了原来的关键遗漏（漏法源/漏条款/漏要件/漏风险） |
| **PASS_TO_PASS** | 原本通过的测试仍通过 | 本次修补是否**没有**新增幻觉/逻辑冲突/越界结论/把草稿写成正式意见 |

落地：评测某 Skill 的**某次迭代**时（即"改了一版 SKILL.md/references 后重测"），不能只看 FAIL_TO_PASS（"上次漏的条款这次补上了"），必须同时跑 PASS_TO_PASS（"补这条的同时有没有引入新问题"）。后者命中任何一条，迭代不算成功，回退重做。这与 taste 项核查天然耦合——多数 taste 项（混淆法律风险与商业谈判点、把不确定写成确定、混淆本方与对方主张）正是 PASS_TO_PASS 要守的底线。

> 四-D 只在"评测某次迭代后的修补是否算成功"时启用；首次评测（没有"上一版"作对照）不需要 FAIL_TO_PASS/PASS_TO_PASS。

## 四、关于"通用基准"的明确边界

本技能**不输出**以下内容：

- 一个适用于所有法律 Skill 的"六维度通用基准"和单一总分
- 跨场景的"平均分"或"加权总分"
- 把不同场景 Skill 排进同一张榜单的横向比较

理由：法律场景之间的差异远大于共性。强行套基准，评测本身会变成另一个看起来严谨但没用的产物。本技能的价值，在于**把每个场景该看的维度讲清楚**，并尊重每个法律人自己积累的 taste。

六维度评价标准（法律准确性 / 事实叙述 / 逻辑说服力 / 争议焦点 / 实务可用性 / 格式完整）可以作为合同型场景的**参考默认起点**，但不是本技能的强制基准。

## 五、参考业界方案但不照搬

本技能的设计参考了三类业界思路，但都做了场景化调整（v0.2.0 依据 DR-5 前沿调研扩到三类）：

- **Anthropic eval 方法论**（DR-5 综合 Demystifying evals / Define success criteria / multi-agent research system 等）：本技能吸收其三层评测栈 + 三类 grader + capability/regression 分离 + 20-50 案例。落地口径见四-B、`references/eval-methodology.md`。
- **Claude skill creator 的 eval 验证思路**（test cases / expected behavior / assertion grading / benchmark / blind A / description tuning）：本技能借鉴其"用熟悉材料做基准"的思路，但**不使用"黄金答案"这一术语**——DR-5 明确标注该术语未在 Anthropic 官方公开材料核验到。法律 Skill 改用"参考解三档口径"（reference-rich / reference-light / reference-free），法律输出的人工 taste 判断无法被自动比对替代。详见四-B。
- **LLM-as-judge 四校准**（DR-5 综合多篇论文）：本技能吸收锚点样本 / 顺序翻转 / 多 judge 共识 / 证据锚定，落地口径见四-C。
- **作者既有文书质量评测尝试**（六维度评价标准）：本技能把它降级为合同型场景的参考起点，并补充诉讼型、合规型的专属维度。

## 六、安全边界

- 测试材料中的真实当事人、案号、客户名、可反查组合信息，在评测报告里必须脱敏。
- 不把评测报告用于对 Skill 作者的人身评价，只针对 Skill 输出。
- 评测结论不能替代正式法律意见；评测"输出是否合格"不等于"输出可作为正式法律意见交付"。

## 参考规则

- `references/scenarios/contract-scenario-rubric.md`：合同型场景评测维度清单（初审 / 审查 / 起草）
- `references/scenarios/litigation-scenario-rubric.md`：诉讼型场景评测维度清单（起诉状 / 答辩状 / 代理词 / 证据目录；末尾含中国法律语境三层指向）
- `references/scenarios/compliance-scenario-rubric.md`：合规型场景评测维度清单（风险扫描 / 整改建议 / 尽调备忘录）
- `references/eval-methodology.md`：评测方法论（v0.2.0 新增）。三层评测栈 + 三类 grader + capability/regression 分离 + 参考解三档 + LLM-as-judge 四校准 + SWE-bench 双门槛 + 中国法律语境 + taste 结构化边界。是 SKILL.md 四-B / 四-C / 四-D 的依据文件
- `references/skill-lint-handoff.md`：与 skill-lint 的对接协议（前置结论如何读、结构性缺口如何处理）
- `references/six-dimensions-origin.md`：六维度评价标准的来源与降级说明（来自 ch07 第六节，作为合同型场景的参考起点）
- `templates/skill-evaluation-report.md`：评测报告模板
