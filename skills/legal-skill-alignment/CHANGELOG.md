# CHANGELOG

## [v1.0.7] - 2026-09-19

### 改进（迁移至公开仓 legal-skills 发布）

- **迁移发布**：自私有仓整树快照迁移至 `legal-skills/skills/legal-skill-alignment/`（不走逐提交 cherry-pick，避免混入无关目录改动与历史中间版本内容），版本历史以本 CHANGELOG 为准。v1.0.6"私有分发范围"的口径自此解除。
- **下游引用措辞修订**：SKILL.md 中 `legal-skill-creator`（私有仓内部技能，公开环境不存在）泛化为"法律领域 Skill 编排器"；五问流程、Brief v1 交接契约、判定矩阵均无变更。
- **evals 路径相对化**：`case-bundle-260728/b6-compatibility-analysis/README.md` 的本机绝对路径改为通用表述。`evals/independent-review-260823/worker-inputs/` 属 sha256 固化的不可变证据，保留原文（其本机路径仅为材料定位信息，无敏感凭证）。
- **证据链说明**：`evals/independent-review-260823/hashes.txt` 固化的 `../../SKILL.md` 哈希对应 2026-08-23 的 v1.0.6 候选快照；本版措辞修订后当前 SKILL.md 与该历史快照哈希不一致，属候选演进的预期状态，不改动历史哈希记录。

## [v1.0.6 独立复核通过] - 2026-08-23（无 skill 代码变更）

> v1.0.6 于 2026-08-11 撤回 v1.0.5 的 promotion 结论并降级 `NOT_VERIFIED` 后，按 T-019 独立复核四要件完成本轮验证。**v1.0.6 恢复可分发状态**（用户终审确认，详见 DECISIONS `D-2026-08-23-01`；属私有分发范围扩大，非 marketplace 公开发布）。

### 独立复核结果（证据：`evals/independent-review-260823/`，sha256 固化）

- **5 轮独立运行**：case-01 R1/R2（同输入复跑）/ case-02 / case-03 / case-05a（负向触发），worker 输入零预期泄露（无评分清单、无规则提示）。
- **硬约束**：14 项 × 4 份 Brief，blocker 级 FAIL **0**；状态四项独立重算 **16/16 一致，零虚标**——v1.0.6 撤回结论时质疑的"评分与产物矛盾"未再出现。
- **v1.0.6 判定矩阵实测生效**：三案素材均无法源原文且产出具体法律建议，三轮全部登记"关键法源原文缺失"blocker 并判 `handoff_ready=false`（法域已知 CN 未降级）。
- **稳定性**：R1/R2 同输入判定零漂移（STABLE），SOP 阈值口径冲突（注册资本 4 倍 vs 5 倍）被两个互不知晓的实例独立发现。
- **负向触发**：非法律类请求（douyin 下载）正确不触发、零 Brief 产出、正确指路 skill-creator。
- **下游可消费性（T-001 补充证据）**：真实消费者视角实测 **7/10**——Brief 五问可近乎一对一映射为下游 SKILL.md 结构，blocker/warning 语义被下游正确理解，无结构性障碍。

### 登记为下次 minor 版本回填项（不阻塞分发）

- **产出侧**：metadata 枚举值命名 kebab vs snake（3/4 轮 warning 级 FAIL；C-02 顶部双标注形式偏差）。
- **源规范自相矛盾 ×2**：`standard-prompt-output.md` 命名约定表（snake_case）与同文件示例（kebab-case）冲突；安全段模板示例"是否涉及最终法律结论：否"与 SKILL.md 权威判定冲突。
- **模板增补考量（来自下游反馈）**：非目标专段、产物文件格式、输入通道约定、目标 skill 命名说明。

### 任务状态

- T-019 / T-014 关闭（独立复核通过）；T-011 负向触发部分、T-001 下游可消费性部分补入实测证据；零起点访谈（case-04）与完整下游编译仍保留待办。

## [v1.0.6] - 2026-08-11

### 修复

- **统一关键法源缺失的状态判定（T-014）**：明确具体法律建议在缺少任何可追溯关键法源原文（`source_url` 或 `source_file`）时，一律登记为 blocker，`handoff_ready=false`；已知或可定位法域不再构成 warning 例外。同步澄清：如实登记 blocker 的 Brief 可以结构完整，但不可交接。
- **法源证据模板自洽**：将“证据”自由文本拆为 `source_url/source_file`、`verified_by`、`verified_at`、`version_as_of` 独立列；禁止以网站名称、“同上”或泛称角色冒充核验记录。合同审查示例改为 `unverified` 并显式标注 blocker，避免示例违反自身门槛。
- **发布状态勘误（T-019）**：撤回 v1.0.5 的 promotion/正式发布结论。既有评测记录因提示词泄露预期、运行产物不完整且评分与产物矛盾，调整为 `NOT_VERIFIED`，等待独立复核。

### 文档完善

- frontmatter 版本升至 `1.0.6`；TASKS 与 DECISIONS 同步记录本轮修复及独立评测的重新验收条件。
- 为旧版 case bundle 标注历史快照边界，避免其旧证据字段被误作当前版本的验收材料。

## [v1.0.5] - 2026-08-07（发布状态已于 v1.0.6 勘误：待独立复核）

> candidate 经 eval-harness 回归轮次（purpose=diagnostic round=1 + purpose=promotion round=2）验证：两轮均 100/100，train C-01~C-14 全 pass 且与 v1.0.4 同构（不退化），held-out C-15~C-17 全 pass（零回归），finding#1 新规则生效。promotion_gate = PASS，用户终审确认 promote（2026-08-07）。

### 新增

- **不登记空壳法源行（finding#1 回填，对应 C-07/C-08 细化）**：二.5 法律依据表每行须为可定位具体法源（jurisdiction + 条号/文件全称/案号 + 三列齐全）；素材仅给法源主题或法规名称而无条号/原文时，**不得**为凑表登记空壳行（名称+三列全空 `unverified`），改为在降级首行占位转录为待补线索，并在待确认清单列明需补条号/版本。此口径源自 promotion 轮次 worker 实测的更严行为，已固化为步骤级强制。

### 待办事项

- ✅ 已闭环：diagnostic（r1）+ promotion（r2）两轮均 100/100，评分见 `eval-harness/evals/legal-skill-alignment-self-evolve-260806/scores.jsonl`。

## [v1.0.4] - 2026-08-07（正式发布，promotion 终审通过）

> 原 candidate（2026-08-06 写入）经 eval-harness promotion 轮次（purpose=promotion，round=2）独立复跑验证：train 三案 C-01~C-14 全 pass 且与 diagnostic 同构（稳定性确认），held-out C-15~C-17 全 pass（零回归）。promotion_gate = PASS，用户终审确认 promote（2026-08-07）。

### 新增

- **负向触发灰度判定表（步骤 0.5）**：把 case-05 灰度例提升为 SKILL.md 步骤级强制判定——非法律类/已给完整 Brief/使用咨询三类直接不触发；"律师工具/技术合规/公司流程"三类灰度场景先追问再判定，减少误触发（对应 C-15~C-17）。
- **第 4 问三子项防错核对（步骤 3，强制）**：组装 Brief 前对 `operator`/`represented_party`/`output_audience` 做互斥核对并在二.4 末尾追加"防错核对"行，把 interview-guide 文字约定固化为步骤级必做（对应 C-06）。
- **法源缺失结构化降级（步骤 3，强制）**：素材无 authorities 原文时，二.5 表首行显式写"法源原文缺失，以下均 unverified"，`effective_date` 一律 `unverified` 不得编造；归 warning 不静默放过（对应 C-07/C-08）。

### 待办事项

- eval-harness 对照轮（control v1.0.3 vs candidate v1.0.4）：train 不退化验证 + held-out（case-04 零起点访谈 / case-05 负向触发）实测，结果回填 `eval-harness/evals/legal-skill-alignment-self-evolve-260806/`。
- ✅ 已闭环：diagnostic（r1）+ promotion（r2）两轮均 100/100，评分见 `eval-harness/evals/legal-skill-alignment-self-evolve-260806/scores.jsonl`。
- 可选增强（finding#1，非 blocker）：将 worker 实测「仅法源主题无条号则不登记空壳条目」的更严口径回填 SKILL.md 二.5 法源段——待后续迭代。

## [v1.0.3] - 2026-08-06（eval-harness 自迭代接入，无 skill 代码变更）

### 技术优化

- **接入 eval-harness 自迭代闭环（T-019）**：新建回归库 `eval-harness/evals/legal-skill-alignment-self-evolve-260806/`，首轮 diagnostic control（v1.0.3，commit 8a4962db）经 codebuddy+hy3 tmux worker 实跑，C-01~C-14 全 pass，总分 100/100；三份 Brief 均 `handoff_ready=false`（blocker 由 golden fixture 缺 authorities 驱动，非 skill 缺陷）。
- 反膨胀行为确认有效：法源全 `unverified`、个案值拒绝固化、无素材走「无法评估」、角色三子项零混淆。
- 闭环暴露 2 个 harness 缺陷，已路由 `eval-harness/TASKS.md` [TC-R5.1]（PM 评分清单经 `golden-input/**` 泄露进 worker 可读树）/ [TC-R5.2]（golden train 包仅含元数据、无 authorities 原文）。详见 `reflections/round-1.md` 与 `HANDOFF.md`。

## [v1.0.3] - 2026-07-30

> **评测骨架版（私有分发）/ T-001 口径修正 + T-004 访谈脚本 + T-011 评测骨架**
>
> 本次推进 T-001 证据口径修正、T-004 无素材访谈脚本、T-011 评测案例骨架三部分。剩余实测依赖真实运行/独立会话/真实用户访谈，已转为明确的人工任务清单。

### 改进

- **T-001 证据口径修正**：B6 报告 / CHANGELOG / DECISIONS 中的"PASS（自动）"统一改为 `STATIC_COMPATIBILITY_REVIEW / NOT_VERIFIED`，明确区分静态兼容性审查与真实下游运行。B6 报告 §六 实测状态表、§七 总结对照表同步修正。
- **T-004 无素材访谈脚本**：`interview-guide.md` 新增"零起点开题脚本"段——含开场白（破冰+定向）、零起点判定边界表、逐题追问完整脚本（每题配话术/锚点/追问触发/复述模板）、收尾成型检查、典型陷阱表（5 类）。把模糊的"我想做 skill"引导为可访谈的具体场景。
- **T-011 评测案例骨架**：新建 `evals/case-bundle-260730/`，含：
  - `EVALUATION.md`：T-011 完整评测汇总（四类场景覆盖 + 负向触发清单 + 零起点案例 + 硬约束追踪 + 多轮稳定性 + B1-B6/F1-F3 回归固化 + 人工任务清单）。
  - `case-04-zero-start-interview/README.md`：零起点访谈案例（劳动仲裁答辩 + 合同用印审批两个场景，含模拟访谈流程 + 预期 Brief 字段 + 验收标准）。
  - `case-05-negative-triggers/README.md`：负向触发案例（case-05a/05b 非法律类 + case-06 已提供完整 Brief + case-07 使用咨询，含近似正例对比 + 边界例）。
  - `constraints-tracker.md`：硬约束追踪表（C-01~C-17，含约束/字段/验证方式/回归案例/严重度 + 断点对应关系 + 多轮稳定性模板）。

### 文档完善

- SKILL.md frontmatter version 升 `1.0.2` → `1.0.3`。
- TASKS T-001 / T-002 / T-004 / T-011 状态更新（标注已完成部分 + 待人工部分）。
- DECISIONS 新增 `D-2026-07-30-02`（v1.0.3 评测骨架）。

### 待办事项（人工任务）

- T-001 B6 实测：手动跑通 3 个 v1 case 的下游 skill-creator 编译。
- T-004 / T-002：找真实"零起点"用户跑完访谈脚本，产出 v1 Brief，归入 case-04。
- T-011 负向触发测试：在 Claude Code 中跑 case-05/06/07。
- T-011 多轮稳定性：对 case-01 跑 3 轮，回填 constraints-tracker。
- T-003：法律分类自动化可信度系统评估。

---

## [v1.0.2] - 2026-07-30

> **规范收紧版（私有分发）/ 基于本轮审查的 7 项修复**
>
> 本次推进 TASKS T-012 返工、T-013、T-014、T-015、T-016、T-017、T-018 共 7 条任务，集中修复 v1.0.1 审查发现的法源证据门槛缺失、状态判定歧义、失效链接、分发口径冲突、触发契约过宽、术语错字等问题。无协议层 BREAKING CHANGE，但 Brief 模板新增 `证据` 列与 `状态判定` 段，既有 v1 案例已同步。

### 修复

- **T-013 法源 verified 证据门槛**：`verified` 必须满足最小证据要求（`source_url`/`source_file` + `verified_by` + `verified_at` + `version_as_of`）；`effective_date` 明确为**施行日期**（非通过日 / 公布日）。
  - 修正 case-02 著作权法 `effective_date`：`2020-11-11`（通过/公布日）→ `2021-06-01`（施行日）。
  - 修正 case-03 / case-01 网络安全法版本：`2017-06-01`（旧版）→ `2026-01-01`（2025 修改决定施行日，涉 AI 治理 + 14 处修改 + 条文顺序调整）。
  - 标准模板、SKILL.md 安全段、interview-guide 第 5 问同步加入证据门槛说明。
  - 新增负向规则：仅有法条名称或从样本反推时，**不得**升级为 `verified`。
- **T-014 拆分 `structurally_complete` 与 `handoff_ready`**：解决"字段齐全但含 blocker 却标可交接"的歧义。`handoff_ready = true` 当且仅当 `structurally_complete = true` **且 blocker 数 = 0**。SKILL.md 完整性规则段重写状态转换表；标准模板 / 3 个 v1 案例补状态判定字段；EVALUATION 加状态判定验证列。
- **T-015 修复 6 个失效相对链接**：`alignment-strategies.md` 多余 `references/` 前缀；EVALUATION.md 与 3 个 case 的 v0 基线路径少一级（`../` → `../../` 或 `../../../`）。全 Skill Markdown 链接检查通过。
- **T-016 统一"首个公开版"与私有分发口径**：CHANGELOG / DECISIONS 中的"首个公开版"/"可对外说明"表述改为"首个协议稳定版（私有分发）"；D-2026-07-28-02 的私有分发决策与版本号含义不再冲突。
- **T-018 术语错字清理**：全 Skill 17 处"对接"的生僻字错写（字形近似的异体字）统一为规范"对接"；11 处不成对中文引号修复（`"..."` → `"..."`）。

### 改进

- **T-012 返工：LICENSE.txt 完整法律文本**：v1.0.1 的 LICENSE.txt 仅含摘要，本次替换为 CC BY-NC 4.0 完整法律文本（161 行，含 Section 1-8 全文 + 版权信息 + 商用许可联系方式），与 `legal-case-analysis` 等兄弟技能模板对齐。
- **T-017 收紧 frontmatter 触发契约**：description 从 264 字压缩到 187 字（含"做什么 + 何时触发 + 关键输出 + 两类负向边界"）；SKILL.md 边界段新增"不应触发的场景"专章（非法律类 Skill / 已提供完整 Brief 要求直接编译 / 使用咨询）。

### 文档完善

- SKILL.md frontmatter version 升 `1.0.0` → `1.0.2`。
- DECISIONS 新增 `D-2026-07-30-01`（v1.0.2 规范收紧）。
- TASKS T-012 / T-013 / T-014 / T-015 / T-016 / T-017 / T-018 标记完成。

### 待办事项

- T-001 B6 实测：手动跑通 3 个 v1 case 的下游编译（仍为人工任务）。
- T-002 / T-003 / T-004：无素材路径验证 + 分类自动化可信度。
- T-011：v1 完整评测（无素材 / 负向触发 / 下游交接）。

---

## [v1.0.1] - 2026-07-28

### 新增

- **B6 对接分析报告**（`evals/case-bundle-260728/b6-compatibility-analysis/README.md`）：调研通用 `skill-creator` 的 frontmatter 白名单与工作流，3 个 v1 case 静态兼容性审查通过（STATIC_COMPATIBILITY_REVIEW），实测 NOT_VERIFIED，附 5 步手动验证手册。

### 文档完善

- **新增 LICENSE.txt**：CC BY-NC 4.0 全文 + 商用许可联系方式（与 AGENTS.md 许可证管理规范一致，与 SKILL.md frontmatter `license: CC-BY-NC` 对齐）。
- **新增 .gitignore**：防止 macOS 系统缓存（`.DS_Store` 等）与敏感配置文件再次入库（与 AGENTS.md 敏感信息安全规范一致）。
- **清理 `.DS_Store`**：本目录与子目录的 `.DS_Store` 系统缓存文件已删除。

## [v1.0.0] - 2026-07-28

> **首个协议稳定版（私有分发）/ 协议层重构 / BREAKING CHANGE**
>
> ⚠️ **分发范围说明**：v1.0.0 是首个协议稳定版，但**仍属私有分发**（D-2026-07-28-02）——不注册 `marketplace.json`、不对外公开推广。版本号 1.0.0 表示协议层成熟度，不等于公开发布。
>
> 本次推进 TASKS T-005~T-010，集中修复 alignment 与下游的交接契约、方法论完整性、角色语义、字段一致性、素材路由与安全边界六类历史遗留问题。**BREAKING CHANGE**：与 `legal-skill-creator` 的硬绑定解除、Brief 格式重命名、第 4 问拆三子项、素材分类扩展——所有 v0.x 案例保留为快照，新案例须按 v1 重对齐。

### 新增（Breaking）

- **legal-skill-brief/v1 规范**：标准化产出格式重命名，可被通用 `skill-creator` 与 `legal-skill-creator` 共同消费（`references/standard-prompt-output.md` 全面重写）。
- **question-set/v1**：方法论版本化命名（替代"五问法"），锁定完整性规则、非目标、禁止事项、成功标准、失败条件、人工复核点。
- **第 4 问三角色拆分**：`operator` / `represented_party` / `output_audience` 分别明确，附防错提示（法官不是 represented_party）。
- **完整性规则段**：阻塞交接缺口 vs 可带警告交接缺口分类，Brief 必须按 `blocker` / `warning` 标注待确认项。
- **敏感材料识别清单**：覆盖身份证 / 手机号 / 银行卡 / 当事人姓名 / 案件金额等 10 类典型敏感信息（`references/alignment-strategies.md` 顶部新增）。
- **七类素材扩展**：在原"样本 / SOP / Q&A"基础上新增 `rules`（规则包）/ `revisions`（对话修订）/ `tools-data`（工具数据）/ `authorities`（法源原文）。
- **四维正交标签**：动作类型 / 法律领域 / 程序阶段 / 文书类型相互独立，支持跨领域任务与非文书型任务。
- **stage 枚举扩展**：增补刑事 / 家事 / 劳动仲裁等领域 stage 值。
- **法源三列强制**：`effective_date` / `jurisdiction` / `verification_status` 必填，未确认标 `unverified`。
- **规则引擎 source 列**：阈值与判断标准必须带来源（法条 / SOP / 样本 / 用户确认）。
- **素材溯源 quality 必填**：`gold` / `silver` / `bronze` / `unrated`（无法判断时填 unrated + 注明）。
- **安全与脱敏说明段**：必填，含敏感材料状态、外传策略、高风险结论复核。
- **非文书型任务专章**：工具 / 数据包 / 看板 / 检查清单在 Brief 中的差异化处理。

### 改进

- **下游兼容性双列表**：在 `standard-prompt-output.md` 末尾新增对照表，明确 Brief 与通用 `skill-creator` 与 `legal-skill-creator` 的兼容性。
- **字段命名约定**：identifier 用 kebab-case（如 `labor-contract-review`）；stage / role / doc_type 用 snake_case。v0.x 的 snake_case 标识符列入迁移指南。
- **嵌套围栏 bug 修复**：用 4 反引号外层方案，让内层 3 反引号示例可正确嵌套。
- **v0 → v1 迁移指南**：在 `standard-prompt-output.md` 末尾新增对照表，覆盖所有命名 / 字段 / 语义变更。

### 文档完善

- **DECISIONS 新增 2 条**：`D-2026-07-28-01 v1.0.0 协议层重构` + `D-2026-07-28-02 marketplace 不注册仍属私有分发`。
- **evals 新增 case-bundle-260728/v1-realigned/**：3 个历史案例按 v1 重对齐 + 汇总评估。原 `case-bundle-260705/` 完整保留为 v0 快照。
- **TASKS 收尾**：T-005~T-010 标记完成，新增 `v1.0.0 协议层重构（2026-07-28）` 子条目到"已完成 / 已移出"段。

### 待办事项

- T-001 B6：实测下游编译（待 v1.0.0 协议稳定后另推）
- T-002 / T-003 / T-004：苏格拉底式访谈无素材路径验证 + 分类自动化可信度（与本次协议层重构解耦）
- T-011：v1 完整评测（无素材 / 负向触发 / 下游交接）
- T-012：清理 .DS_Store / LICENSE.txt（与本次范围解耦）
- 后续可扩展 `question-set/v2`（如六问 / 七问版）——本 v1 已为此预留空间

---

## [v0.2.0] - 2026-07-05

### 改名 + 重新定位

- **改名**：`five-question-distill` → `legal-skill-alignment`（git mv，保留历史）。
- **重新定位**：从"五问蒸馏法"重新定位为"写法律 Skill 前的前置步骤——苏格拉底式提问做目标对齐"。

**用户原话**：
- "distill 听起来好像不是很贴切。它本质上其实是一个苏格拉底式的一个 ask you a question 去进行目标对齐的一个过程。只不过因为法律类的 skill 的话，它最后落实到我们本书的这五个方向"。
- "我们有可能后续关于这个五问法变成四问或者六问之类的，这个风险我们也要去避免"。

**变更要点**：
- **SKILL.md**：name 改为 `legal-skill-alignment`，version 升 0.2.0，顶层定位改为通用"提问对齐"（不锁数字），内部保留"五问法"作为当前默认方法论 + 新增"扩展说明"段。
- **references/ 措辞调**：`distill-strategies.md` → `alignment-strategies.md`（git mv），内部"蒸馏"措辞改"对齐/厘清"。其他 references（interview-guide / legal-domain-mapping / standard-prompt-output）同步去"蒸馏"措辞。
- **evals/ 措辞调**：EVALUATION.md 中"蒸馏"措辞改为"对齐"，保留 case 内容不动。
- **CHANGELOG/TASKS/DECISIONS**：同步更新，记改名 + 重新定位。

**不动的**：
- "五问法"方法论名保留（本书 ch07 方法论仍叫五问法）。
- 其他 skill 未改。
- 书稿仓（ch07 引用更新）留 PM 后续。

---

## [v0.1.1] - 2026-07-05

### 修复（基于 T-001 端到端验证断点）
- **SKILL.md 步骤 1A.4**：新增"素材未覆盖要素的补全策略"，定义当素材未直接体现第 3/4/5 问时如何推断与确认（B1 断点修复）。
- **legal-domain-mapping.md**：扩展 stage 枚举，增加合规（pre_launch/post_launch/annual_audit 等）、知产、尽调、合同的细分 stage 值（B2 断点修复）。
- **distill-strategies.md**：新增"单样本/少样本处理策略"段，定义单样本时仍可提取的内容 vs 需标注"待补充"的内容（B3 断点修复）。
- **standard-prompt-output.md**：
  - 新增"规则引擎"可选段，支持在 prompt 中承载量化阈值、判断标准和风险评分规则（B4 断点修复）。
  - 新增"输出格式多样化指引"，支持表格化、混合格式输出的描述方式（B5 断点修复）。
  - "素材溯源"段补充质量过滤标准字段（quality = gold/silver/bronze）。

### 新增
- **evals/case-bundle-260705/**：首批 3 个评测案例（合同/诉讼/合规各 1），含素材、蒸馏输出 prompt、断点记录、评估汇总。
- **EVALUATION.md**：T-001 端到端验证汇总，含五问评估矩阵、6 条断点清单、字段映射检查。

---

## [v0.1.0] - 2026-06-20

### 新增
- 首版五问蒸馏法 skill（来源：法律AI书 ch07 下，游初《二轮对焦》）。
- **双路径**：有素材（样本 / SOP / Q&A 三分类蒸馏）+ 无素材（苏格拉底式访谈逐题引导）。
- **五问齐全**：输入什么 / 输出什么 / 处理逻辑 / 向谁交付 / 需要哪些知识支撑（与本书 ch07 命名一致）。
- 法律分类识别 + 标准 prompt 输出模板（接 `legal-skill-creator`，含五标识符字段映射）。
- references：`distill-strategies` / `legal-domain-mapping` / `interview-guide` / `standard-prompt-output`。
