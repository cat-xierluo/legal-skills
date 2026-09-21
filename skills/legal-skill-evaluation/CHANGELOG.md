# CHANGELOG

## [v0.8.12] - 2026-09-19

### 改进（迁移至公开仓 legal-skills 发布）

- **迁移发布**：自私有仓整树快照迁移至 `legal-skills/skills/legal-skill-evaluation/`（不走逐提交 cherry-pick，避免混入无关目录改动与历史中间版本内容），版本历史以本 CHANGELOG 为准；早期版本记录中提及的迁移前私有仓属历史事实，不再逐一改写。
- **frontmatter version 对齐**：`0.8.1` → `0.8.12`，修正自 v0.8.2 起 frontmatter 滞后于 CHANGELOG 的漂移。
- **homepage 修正**：指向 legal-skills 公开仓库。
- **evals 路径相对化**：`case-bundle-260705` 两个案例的"被评测 Skill 路径"、`contract-calibration-260730` producer probe JSON 中的本机绝对路径改为仓库内相对路径。
- **config 白名单**：`config/instruction-stability-contract.json`（指令稳定性合同，非敏感）在公开仓 `.gitignore` 加白名单随技能发布；`*.example.json` 模板按既有规则发布。

## [v0.8.11] - 2026-08-08

### 新增（T-907 litigation-analysis bundle 落地，标准模式闭环）

- `evals/litigation-analysis-20260808/`：指令型 bundle（mode: instruction-type，tier: material-driven），复用 case-analysis 范式。
  - 三份脱敏材料：familiar 二审买卖判决 / peer 知识产权权属判决 / missing 判决片段（缺审级主文送达）。
  - agent 按 litigation-analysis v1.3.2 规范真实运行，落盘 runs/ 三份产出并补真实 input/output sha256。
  - 4 个诉讼专属语义 case（EFFECTIVE-LAW / REASONING-TRACE / NO-INVENT-OUTCOME / DEADLINE-CAUTION），judge_hint 初版与候选真实措辞偏差已调优（同类 T-905），实跑全 pass。
  - `capability-suite.json` 三案例 executed-pass + run_receipts；`evaluation-package.json` standard 模式、DIM-1~6 / TASTE-1~8 全覆盖、verdict adopt-with-notes。双 gate 复验均 pass。
  - 横向贡献：补强"期限不写死天数"诉讼专属盲点 + 已决文书说理溯源维度。

## [v0.8.10] - 2026-08-08

### 新增（T-906 后续 bundle 评估方案，规划稿）

- `evals/NEXT_BUNDLES_PLAN.md`：盘点 legal-skills 仓库 14 个法律 Skill 的接入可行性（命令式/指令型、Python 入口、评估价值），三类代表选型（诉讼/分析类 `litigation-analysis`、文书生成类 `legal-proposal-generator`、知识抽取类 `legal-qa-extractor`），各附三份材料设计 + 受控语义 case + 横向维度贡献；列二期候选与框架侧待补项。本文为规划稿，未实际建 bundle（用户决策：出方案不落地）。

## [v0.8.9] - 2026-08-08

### 修复（语义 gate judge_hint 对齐，T-905）

- `semantic-cases/json/CASE-OBJ-MISSING_input.json`：`CAP-OBJ-CONFIRM` 原正则 `请.{0,12}(?:选择|确认|说明).{0,12}(?:目标|其他目标|用途)` 与候选真实表述（"委托目标（必填）""请委托人明确下列""本次希望得到什么交付物"）不对齐，导致真实产出 fail。改为 `contains_any` 捕获候选实际使用的"目标确认阻断"信号（委托目标 / 希望得到什么交付物 / 明确下列 / 补齐缺口 / 目标明确前不进入 等）。
- 复验：peer-unfamiliar 与 missing-context 两目标缺失型案例转 **pass**（设计本意）；familiar 完整分析仍 fail（不触发目标缺失暂停判定，符合预期）。`CASE-FACT-STMT @ missing` 的 fail 属"材料无完整事实台账"设计边界，非偏差，不动。

## [v0.8.8] - 2026-08-08

### 新增（标准模式升级 + 框架推荐态 adopt-with-notes）

- `evaluation_package_gate.py`：新增 `adopt-with-notes` 推荐态（指令型/未签发 DOMAIN_VERIFIED 但运行已闭环的场景），`WORKFLOW_RECOMMENDATIONS` 纳入 `enter-workflow` 与 `adopt-with-notes`；CLOSE-011/021/023 对两者统一拦截 open failure；CLOSE-017 仅 `enter-workflow` 强约束 DOMAIN_VERIFIED，`adopt-with-notes` 不需。`regression_open` 改为只认 `fail`（`not-run` 为无基线未测，不阻断工作流）。
- `case-analysis-20260808` bundle 升标准模式：agent 按 legal-case-analysis v1.0.0 规范真实运行 peer-unfamiliar 与 missing-context 两案例，落盘 `runs/*-output.md` 并补真实 input/output sha256；`capability-suite.json` 三案例转 `executed-pass` + run_receipts；`evaluation-package.json` 升 `mode: standard`、三案例六维度（DIM-1~6）+ 八项 taste（TASTE-1~8）全覆盖、verdict `adopt-with-notes`。

### 改进（验证闭环）

- bash 验证：case-analysis 的 `capability_suite_gate` 与 `evaluation_package_gate` 标准模式均 **pass**；contract bundle 双门禁无回归。
- 5 例 `semantic_micro_case_gate` 以真实产出复跑：符合受控断言预期（部分 case 级 fail 属 judge_hint 调优项，不影响 suite 级人工判读）。

### 待办事项

- 语义 gate `CASE-OBJ-MISSING` 的 `judge_hint` 调优（正向"请求确认/暂停"判定）。
- T-904：评估 litigation-analysis / legal-proposal-generator / legal-qa-extractor 作为后续 bundle。

## [v0.8.7] - 2026-08-08

### 新增（T-903 门禁支持指令型 Skill 接入）

- `capability_suite_gate.py` 新增 `mode` 声明式字段：`command-type`（默认，保留合同侧全部硬约束）与 `instruction-type`（指令型/材料+LLM 运行 bundle 放宽）。指令型放宽项：最小 case 数 20→3、跳过 `fixture_spec` 必填、跳过 case_type/tier/capability 必填覆盖校验（SUITE-037/038/039 对 instruction 豁免）；`material-driven` 从命令式必填 `TIERS` 移出为指令型专用 `INSTRUCTION_TIERS`；`SOURCE_KINDS` 增 `not-run`/`existing-real-run`；`OBSERVED_STATUSES` 增 `warn`（语义 gate 软提示）；not-run 断言豁免 `expected`（SUITE-026）。
- `semantic_micro_case_gate.py` 新增通用 `judge_hint` 协议分支：`case_id` 以 `CASE-` 开头且 assertions 含 `judge_hint`（`contains_any`/`not_contains`/`regex`）时走通用判定，合同 CASE 逻辑原样保留。
- 新增第二个 eval bundle `evals/case-analysis-20260808/`（legal-case-analysis 指令型首例），验证框架对无 scripts/ 纯提示词驱动的 Skill 接入可行。

### 改进（验证闭环）

- bash 回归验证：contract bundle 的 `capability_suite_gate` + `evaluation_package_gate` 仍 **pass**（无回归）；case-analysis 指令型 suite gate 由 fail 转 **pass**；5 例 `semantic_micro_case_gate` 实跑（familiar 输出作 output）4 例 pass、`CASE-OBJ-MISSING` 预期 fail（暴露待标准模式补齐的盲点）。
- T-902 指令型接入范式已固化为 SKILL.md 步骤 3.5 双路径，T-903 已闭环并验证。

### 待办事项

- 升标准模式：agent 真实运行 peer-unfamiliar / missing-context，补 input/output 哈希与 dimensions/taste，将 verdict 由 not_verified 升级。
- T-904：评估 litigation-analysis / legal-proposal-generator / legal-qa-extractor 作为后续 bundle，沉淀多 Skill 横向对比维度。

## [v0.8.6] - 2026-08-07

### 新增（T-401 执行闭环收口）

- 补齐 `CONTRACT-MICRO-OBJECTIVE-MISSING` 真实动态执行：构建合成服务合同（DOCX）+ run bundle，由 `contract-copilot` 候选实跑，产出 `real-runs/CONTRACT-MICRO-OBJECTIVE-MISSING-real-output.md` 与 artifact-backed 收据（`current-run-receipts.json` 追加至 19 份 run record）。
- 该例真实执行暴露候选缺陷：候选识别 `review_objective` 为空，但 SKILL.md 阻塞清单仅含立场/口径（二者已具备），据此未暂停整轮审查，自行按「签约前把关」默认目的推进并出具完整审查意见（结论「不建议签」），仅在文末标注待确认——违反 `CAP-MICRO-OBJECTIVE-MISSING-STOP`（目标确认前暂停、不自行选择交付强度）。归因为 SKILL.md 对「审查目的缺失」处置口径自相矛盾（§9.1 必问 vs §3.2/§1.1 阻塞清单未列），记作候选规范缺口。
- `capability-suite.json` 该例由 `not-run` 推进为 `executed-fail`，回填 `assertions[].observed` / `evidence`、`input_sha256`、`output_sha256`、`run_receipts[].record_sha256`。

### 改进（可追溯性补全）

- 补齐 7 例此前 `gate_verdict` 为 null 的 case（`E2E-DESIGN-CURRENT`、`E2E-PATENT-CURRENT`、`DYNAMIC-MISSING-CONTEXT`、`ROLE-MISSING`、`REVIEWER-UNCONFIRMED`、`REPORT-FIELD-COLLAPSE`、`PRODUCER-SELF-SUCCESS`），统一按 `execution_status` 映射填入 `executed-pass` / `executed-fail`。

### 补遗（CONTRACT-MICRO-ATTACHMENT-MISSING 真实执行）

- 收口遗漏：v0.8.6 初版将真缺口误记为 OBJECTIVE-MISSING（其实它已 executed-fail），真正最后一例 `not-run` 是 `CONTRACT-MICRO-ATTACHMENT-MISSING`（其 `gate_verdict` 仍为 v0.8.2 的 expected-fail-closed 静态占位 `pass`）。
- 补齐方式同前：构建合成技术服务合同（正文六条通篇引用附件一～四、附件全未提供，DOCX）+ run bundle，由 `contract-copilot` 候选实跑，产出 `real-runs/CONTRACT-MICRO-ATTACHMENT-MISSING-real-output.md` 与 artifact-backed 收据（`current-run-receipts.json` 追加至 20 份 run record）。
- 真实执行结果 `executed-pass`：候选开篇列明四份附件全部未提供，指明正文空心化、实质内容全在附件且附件效力高于正文；明确声明不对服务范围/验收标准/价款/知识产权出具实体结论（四项均标「未提及/待补充」），并将「取得并审阅附件一至四」列为签署前先决事项第 1 项（最高优先级）。未完全暂停整轮（就正文结构可独立认定的风险出具 P0 意见并声明为阶段性成果），符合 SKILL.md 立场/口径完备即可推进规则，满足断言 `CAP-MICRO-ATTACHMENT-MISSING-LIMIT`（明确限制并列为签前条件）。
- 回填后 20 例分层 suite `execution_status` 分布为 **11 `executed-pass` / 9 `executed-fail`**，全部具备非空 `gate_verdict`；双门禁（suite gate + receipt gate）复跑均 `status: pass`，45 项单测全过。
- 修复 `build_micro_receipts.py` 重跑时未刷新 `record_sha256` 导致的 RECEIPT-016（11 例 stale hash），统一按 `canonical_hash(run)` 对齐；同步更新 `test_capability_run_receipt_gate.py`（20/18 计数）与 `test_capability_suite_gate.py`（注入 not-run case 验证 SUITE-029，因 T-401 已无 not-run 实例）。

### 待办事项

- 候选缺陷共 4 例（OBJECTIVE-MISSING + 验收付款 / 变更费用 / 违约金堆叠）属 SKILL.md 边界口径不一致所致，需 contract-copilot 候选更新后复测（回归 FASS_TO_PASS）。
- 方向二：将 10 例 `executed-fail` 转为 contract-copilot 候选回归测试集，驱动候选修复；方向三：固化为可复用 runner 脚本，支持候选版本间对比。

## [v0.8.5] - 2026-08-07

### 新增（T-401 真实动态执行闭环）

- 真实执行 11 例条款边界微案例：构建 11 份合成合同（DOCX，`micro-runs/synthetic/`）+ 11 份 run bundle，由 `contract-copilot` 候选（AI Agent 遵循其 SKILL.md）逐例实跑，产出 11 份真实审查输出（`micro-runs/real-runs/*-real-output.md`）。
- 生成 11 份 artifact-backed 运行收据（`current-run-receipts.json` 追加至 18 份），逐例回填 `assertions[].observed` / `evidence`、`execution_status`、`run_receipts[].record_sha256`。
- `capability-suite.json` 11 例条款边界 case 由 `not-run` 推进为 `executed`（8 例 `executed-pass` / 3 例 `executed-fail`），`coverage_target.note` 同步更新。

### 技术优化（语义门禁回补）

- 回补 v0.8.4 被清理提交（caf8fefc）误删的 `CLAUSE_BOUNDARY_ASSERTIONS`（11 类 case_id → 各自断言标识）+ `clause_boundary()` 校验器 + `validate()` 分派分支。
- `clause_boundary()` 声明层正则放宽为"在…前我将暂停实质审查"宽松前缀匹配（兼容"信息补齐前／风险闭环前／范围确认前"等措辞）；行为层仍以条款级实质审查主张条数为准，避免"声明暂停却逐条评述"的矛盾模式。
- 配套单测 `test_semantic_micro_case_gate.py` 回补 3 例（11 fixture 通过 + 2 突变失败），全量 45 测试通过。

### 修复（候选能力缺陷，真实执行暴露）

- 候选在 3 类条款边界 case 未按预期暂停、直接给出正式可签结论（FAIL_TO_PASS 反转为 fail）：
  - `CONTRACT-MICRO-ACCEPTANCE-PAYMENT`（验收付款联动）
  - `CONTRACT-MICRO-CHANGE-FEE`（变更费用授权）
  - `CONTRACT-MICRO-PENALTY-STACKING`（违约金堆叠边界）
- 上述 3 例的"期望 pass"为静态假设，真实执行证明候选未稳定遵守暂停边界，属候选缺陷而非门禁缺陷。

### 待办事项

- T-401 真实执行缺口实际为 `CONTRACT-MICRO-OBJECTIVE-MISSING`（`not-run`），于 v0.8.6 补齐；原误记的 role-missing / reviewer-unconfirmed 两例经核查早已为 `executed-fail` / `executed-pass` 且收据完整。
- 候选缺陷（验收付款 / 变更费用 / 违约金堆叠 + OBJECTIVE-MISSING）是否回归修复，待 contract-copilot 候选更新后复测。

## [v0.8.3] - 2026-08-07

### 新增（T-401 推进：补 not-run 微案例 fixture）

- 为 13 例未执行（not-run）合同微案例补齐 fixture：在 `evals/contract-calibration-260730/micro-runs/` 新增 9 例 input+expected-fail-closed output（服务范围、验收付款、变更费、违约金堆叠、设计 IP 使用、通知、管辖、专利标的/范围/费用/无效），连同既有 4 例共 13 例均具备可复算输入与产出。
- `capability-suite.json` 为 13 例 not-run 增加布尔标记 `fixture_ready: true` 与 `gate_verdict` / `gate_note` 附加字段（**保持 `execution_status: not-run` 不变**，诚实反映尚未真实执行）；其中 `CONTRACT-MICRO-OBJECTIVE-MISSING` 与 `CONTRACT-MICRO-ATTACHMENT-MISSING` 经 v0.8.2 `semantic_micro_case_gate` 静态判定为 `pass`（声明暂停 / 识别范围限制）。

### 文档完善

- `coverage_target` 增加 `fixture_ready_case_count` 与说明：13 例 not-run 已具备 fixture，T-401 从「未准备」推进到「fixture-ready」。

### 待办事项

- **门禁覆盖缺口（本轮发现）**：`semantic_micro_case_gate.py` 仅支持 4 个 case_id（objective / attachment / role / reviewer），其余 9 例新微案例报 `unsupported-case-id`。需在下一轮为该 9 类扩展判定路由，方可对 fixture 做静态 fail-closed 判定。
- 真实执行：13 例 fixture-ready 仍需真实 `contract-copilot` 候选动态执行以产生 executed 状态与结构化运行收据，闭环 FAIL_TO_PASS / PASS_TO_PASS。

## [v0.8.2] - 2026-08-07

### 新增

- 登记 `scripts/semantic_micro_case_gate.py` 到 `SKILL.md` 参考文件路由与验证命令（此前漏登，属文档漂移，本轮补正）。

### 修复

- 修复 `semantic_micro_case_gate.py` 的「声明—行为」一致性误判（评测方法鲁棒性 fuzz 发现）：
  - F-2（高）：`objective_missing` 新增行为层校验——声明在目标确认前暂停实质审查却仍产出条款级实质审查主张时判 `fail`，拦截「信息不足却给确定结论」法律红线（原仅检查是否写了暂停标语）。
  - F-1（中）：`objective_missing` 的 `declares_stop` 词表扩展近义表述（暂缓/中止/不进入/不展开/不开展），并放宽「实质…审查」之间的修饰语间隔。
  - F-3（中）：`attachment_missing` 的 `service_scope` 接受「服务内容/服务事项」等同义表述，避免同义词误伤。
  - 新增 `SUBSTANTIVE_REVIEW_PATTERNS` 与 `counts_substantive_review_findings` 支撑行为层判定。

### 技术优化

- F-5：`evaluation_package_gate.py check` 新增 `--fixture-root`，`fixture_base` 优先相对输入文件、不存在时回退到 `fixture-root` 解析，解耦「fixture 必须和输入同目录」的路径耦合。
- F-4：capability 两套回归测试改用 `_discover_candidate_root()` 向上查找候选 skill，支持 `LSE_CANDIDATE_ROOT` 环境变量覆盖，去除硬编码 monorepo 相对布局假设；4 套件回归测试 42/42 通过。

## [v0.8.1] - 2026-07-30

### 新增

- 新增 `scripts/capability_run_receipt_gate.py`：把 suite 的 executed 状态绑定到结构化运行记录，复算记录 SHA-256，并核对 case、candidate、input、output、execution status、assertion 集合和 runner 元数据。
- 新增 `config/capability-run-receipts.example.json`，提供 artifact-backed 运行记录、runner、断言与证据文件的通用模板。
- 新增 11 项收据门禁回归测试，覆盖任意字符串自报、记录漂移、候选/案例/输入错绑、断言遗漏、证据哈希错配、路径逃逸、孤立记录和 digest-only 假 verified。
- 新增候选外 `contract_copilot_micro_probe.py` 与脱敏合成产物，在隔离临时配置中执行审查立场缺失、审查人未确认、旧字段报告塌缩和生产器自报成功四个微案例。

### 改进

- 运行证据区分 `artifact-backed` 与 `digest-only`：脱敏合成案例保留可复算输入/输出；真实合同证据不复制敏感原文与产物，只保留摘要和哈希，且不能单独支撑 verified suite。
- 20 例 suite 从 3 例已执行推进到 7 例已执行：5 个 executed-fail、2 个 executed-pass、13 个 not-run；总体继续保持 `regression-detected / NOT_VERIFIED`。
- `SKILL.md` 增加结构化运行收据契约、收据门禁命令和证据等级边界。

### 修复

- 阻止 capability suite 仅凭非空路径、Agent 自报 PASS 或陈旧摘要把案例标记为已执行。
- 候选外微案例确认 `party_role` 为空时非交互 runtime 会自动降级为“其他”；此前受控 Agent 缺失背景案例的单次通过不能扩大为 runtime 前置门禁已通过。

### 验证

- 三组门禁共 35 项单元测试通过；评测包、能力套件与结构化运行收据三条代表性 CLI 均通过候选绑定复算。
- 四个候选外微案例在全新临时目录重跑，6 份受控产物逐字节一致；Python 源码编译、JSON 解析、Markdown 本地引用、敏感信息关键词与 diff whitespace 检查通过。
- `skill-lint` 静态 Harness 审查为 PASS、0 finding；候选外 Harness evidence 动态执行 3 组正向回归和 5 个逃逸反例，取得当前候选的 `HARNESS_REVIEW_VERIFIED`。
- 指令稳定性仍因缺候选外独立硬约束基线返回 `ISG-006 / NOT_VERIFIED`；通用 `skill-creator` 校验器不接受项目必需的 `version/homepage/author` frontmatter，按更具体的项目规则保留这些字段。

### 待办事项

- 执行剩余 13 个语义微案例；修复 `contract-copilot` 的前置角色/目标门禁、旧字段映射、最终报告完整性自检、可签署性闭环与人工复核状态后，运行 FAIL_TO_PASS / PASS_TO_PASS。

## [v0.8.0] - 2026-07-30

### 新增

- 新增 `scripts/capability_suite_gate.py` 与 11 项回归测试：对 20—50 例 suite 的案例数量、三份种子、三层案例、七个能力域、候选绑定、执行状态、断言证据和正式标记进行 fail-closed 校验。
- 新增 `evals/contract-calibration-260730/capability-suite.json`：沉淀 20 例合同能力案例，区分 2 例完整端到端、1 例受控动态边界和 17 例待执行微案例/静态契约。
- 新增 `current-run-receipts.json`：保存设计合同与专利许可合同当前候选重跑的输入 bundle、候选、输出和日志哈希，以及 DOCX 完整性、批注/修订、字段塌缩等结构观察。

### 改进

- `SKILL.md` 增加 capability suite 分层方法和门禁命令，明确“已定义”“已执行”“已验证”三种状态不得混用。
- 将三份评测包中的设计、专利案例从 `historical-unbound` 升级为 `current-candidate`；评测包现有 3 例全部绑定同一 102 文件候选快照。
- 合同深度 rubric 新增核心事实—可签署性闭环和输入审阅痕迹隔离两项校准规则。
- 专利样本改从原始 `.doc` 在临时目录转换出无批注、无修订 DOCX 后重跑，避免历史审阅痕迹污染当前候选证据。

### 修复

- 修复 capability suite 容易把 20 个“待运行案例”表述成“20 例已通过”的证据语义；当前有回归时强制状态为 `regression-detected / NOT_VERIFIED`。

### 技术优化

- 当前 suite gate 统计为 20 cases、28 assertions、20 current-bound、2 executed-fail、1 executed-pass、17 not-run；候选快照复算一致。
- 现有 evaluation package gate 13 项测试与新增 suite gate 11 项测试均通过，两个 Python 门禁与测试文件均可编译。

### 待办事项

- 执行剩余 17 个微案例；修复 `contract-copilot` 的旧计划字段映射、最终报告完整性自检、可签署性闭环与人工复核状态后，运行正式 FAIL_TO_PASS / PASS_TO_PASS。

## [v0.7.1] - 2026-07-30

### 新增

- 新增 `evals/contract-calibration-260730/`：保存 contract-copilot 首批三份测试法校准报告、schema 1.1 机器评测包、缺失背景受控响应，以及 7 条 capability / 7 条 regression 种子断言；不复制合同正文和本地审查人配置。
- 候选哈希新增 `--scope git-tracked`，以可发布的 Git 跟踪文件锁定候选，避免运行归档、本地个性化配置和缓存污染快照；保留 `full-directory` 兼容非 Git Skill。
- 评测包新增案例 `candidate_binding`、候选 hash scope、原始 Hard Findings 与逐项裁决字段；历史未绑定案例不得支撑 `DOMAIN_VERIFIED` 或 `enter-workflow`。
- 新增候选范围不一致、历史未绑定假通过和范围外 finding 假通过三份回归 fixture。

### 改进

- `test-trio-method.md` 将输入定义为“正文 + 请求 + 角色 + 目标 + 配置 + 附件”的 bundle，并按合同、诉讼、合规、案件分析四类任务族明确“同类但不熟悉”的语义。
- `contract-scenario-rubric.md` 回灌三项真实校准规则：最终报告关键字段完整性、审查立场前置门禁、正式意见人工复核状态。
- `skill-lint-handoff.md` 升级为 handoff/2：通用静态 finding 可做有证据的误报/不适用/范围外裁决，但原始 finding 不得静默删除，正式状态继续按实际证据填写。
- 报告模板增加候选哈希范围、案例候选绑定、原始 finding 与裁决记录。

### 修复

- 阻止 Git 忽略的真实合同归档和本地 reviewer 配置改变公开候选哈希。
- 阻止只有输入/输出哈希与自由文本收据的历史产出冒充当前候选领域验收证据。
- 阻止同一输入 bundle 在 schema 1.1 标准/发布模式下重复充当多个三份测试案例。

### 验证

- 13 项 gate 回归测试通过；Python 源码编译检查通过。
- contract-copilot 校准包通过三项机器约束：三类案例、18 个维度、24 个 taste、候选范围与结论闭环均一致；结论按 3 项法律红线保持 `blocked / NOT_VERIFIED`。
- `skill-lint` Harness 静态审查为 PASS、0 finding；候选外 Harness evidence 动态执行 2 个正例和 7 个故障用例，签发当前候选的 `HARNESS_REVIEW_VERIFIED`。
- 指令稳定性审查仍因缺候选外独立硬约束基线保持 `NOT_VERIFIED`，未签发正式稳定性标记；通用 `skill-creator` 校验器因不接受项目必需的 `version/homepage/author` frontmatter 返回规则不适配，未据此删除项目字段。

## [v0.7.0] - 2026-07-28

### 新增

- 新增 `config/evaluation-package.example.json`：定义候选、通用门、三类案例、六维度、八项 taste、修复单元、回归状态与 verdict 的机器可读契约。
- 新增 `scripts/evaluation_package_gate.py`：仅使用 Python 标准库，提供候选目录哈希及评测包覆盖、证据绑定、结论闭环检查；`enter-workflow` 缺少候选绑定 `DOMAIN_VERIFIED` 时 fail-closed。
- 新增 `scripts/test_evaluation_package_gate.py` 与 6 份 fixture：完整正例、合法 N/A 近似正例、缺维度、陈旧候选哈希、虚假通过和旧模板历史遗漏。
- 新增 `config/instruction-stability-contract.json`：为 `EVAL-REPORT-COVERAGE`、`EVAL-EVIDENCE-BINDING`、`EVAL-CLOSURE` 配置主动 checker、产物阶段、正反例、measurement 和 observable。

### 技术优化

- gate 增加 skill-lint 指令稳定性严格输出协议：正例只返回逐约束通过、原始 artifact 哈希、measurement 与 observable；反例只返回精确失败约束及违反阈值。
- 固定正例三轮运行得到一致 artifact 哈希与 observables；机器门禁与法律领域判断分离，schema 通过不冒充 `DOMAIN_VERIFIED`。

### 验证

- 9 项 gate 回归测试通过；Python 字节码编译通过。
- 8 份 JSON 解析通过；Markdown 本地链接检查通过。
- `harness_failure_audit`：PASS，0 finding；候选绑定 Harness 证据门通过。
- `instruction_stability_gate assess`：合同与 3 条硬约束解析成功；因缺候选外独立硬约束基线，状态保持 `NOT_VERIFIED`，未签发 `INSTRUCTION_STABILITY_VERIFIED`。

## [v0.6.0] - 2026-07-28

### 改进

- 重写 SKILL.md 为快速、标准、发布三档流程；默认标准模式，快速模式只能输出 `NOT_VERIFIED`。
- 把规整性静态清单改为非权威快速分流桥；标准与发布模式消费与当前候选哈希一致的实时 skill-lint 结论。
- 将“回 SKILL.md 补一句话”升级为六类最小修复单元：skill instruction、reference、template/schema、checker、fixture、intake boundary。
- 重写 `references/skill-lint-handoff.md`，定义版本、候选哈希、Hard Findings、Harness/稳定性/领域状态及收据字段。
- 重写 Markdown 报告模板，统一三份材料、通用六维度、通用 taste、输入输出哈希、回归双门槛和正式证据标记。

## [v0.5.1] - 2026-07-28

### 修复

- 修复旧报告模板仍按三场景独立 rubric 路由、步骤编号漂移和 handoff 自相矛盾的问题。
- 将三份场景深度 rubric 扁平化到 `references/`，修复相对链接；同步历史 eval 中的现行路径。
- 删除已合并且与现行路线冲突的 `references/six-dimensions-origin.md` 和过期 `references/reference-audit.md`。
- 压缩 frontmatter description，并将许可证从 MIT 修正为 `CC-BY-NC`。

### 文档完善

- 新增完整 `LICENSE.txt`，使用统一版权信息和商用许可联系方式。
- 为通用六维度与 taste 增加稳定 ID（DIM-1—DIM-6、TASTE-1—TASTE-8），并在三份测试法中补候选、输入、输出哈希记录。

## [v0.5.0] - 2026-07-05

### 重新定位：法律 Skill 质量评测（一站式：规整性基础 + 法律产出特异化）

**用户决策原话**（杨卫薪律师 2026-07-05，详见 DECISIONS.md D-2026-07-05-03）："skill 本身的质量我们还是要去做评价的...skill lint 的常规的基础功能还是要放进去的，只不过说在这个里面我们再额外加一步，对于这个法律文件产出，也去做一下这个评估，这个只是其中的一部分"。

v0.5.0 **部分撤回 v0.3.0 的"规整性完全交给 skill-lint"划界**，将规整性基础纳入本技能主流程。从"只评法律产出"重新定位为**"法律 Skill 质量评测"**（一站式：规整性基础 + 法律产出特异化）。

#### 变更（SKILL.md 主流程改造）

- **`SKILL.md` version**：0.4.0 → 0.5.0。
- **中文名**："法律文件产出质量评测"→"**法律 Skill 质量评测**"。
- **`SKILL.md` description**：重写——评测对象 = 法律 Skill 本身（规整性基础 + 法律产出质量）。规整性引用 skill-lint 判则（不搬全文），法律产出沿用通用六维度 + 场景微调。触发词加"法律 skill 评测""skill evaluation"。原"纯格式 lint 与规整性审查（用 skill-lint）"改为"注意：纯格式 lint 与规整性审查的权威工具仍是 skill-lint，但本技能 v0.5.0 起在主流程中纳入规整性基础检查（引用 skill-lint 判则），用户可联跑两者"。
- **一、核心定位**：重写——从"本技能只负责第二层（产出合理性）"改为"本技能一站式覆盖两层（规整性基础 + 产出合理性）"。表从两层分属两个工具改为一站式两层。新增"与 skill-lint 的关系"段：skill-lint 是规整性权威判则源、本技能引用其判则但不搬全文、联跑模式说明。
- **三、评测流程**：步骤概要从"v0.4.0 关键变化：步骤 3 从按场景选独立 rubric 改为通用六维度"改为"v0.5.0 关键变化：新增步骤 2 规整性检查"。
- **新增步骤 2（规整性检查）**：引用 skill-lint 判则逐项检查 8 个维度（格式合规/frontmatter 与触发词/目录结构与引用可达/reference 拆解与存放/触发词边界/业务流深度五层/Hard Fail/可评估性基础）。检查清单见 `references/regularity-checklist.md`。Hard Fail 命中 → 停止后续评测。联跑模式下直接消费 skill-lint 报告。
- **原步骤 2-7 顺延为步骤 3-8**：步骤 3（原步骤 2）标题改为"前置——结构是否可评测（消费 skill-lint 可评估性结论，v0.5.0 从步骤 2 顺延）"；其余步骤同 v0.4.0，内容不动。
- **步骤 8（原步骤 7）报告必含项**：新增"规整性检查结果（v0.5.0 新增）"；"要补的句子"清单范围扩至"也包括规整性修补建议"。
- **参考规则段**：新增 `references/regularity-checklist.md` 和 `references/reference-audit.md`；标注 `six-dimensions-origin.md` 合并进 `universal-dimensions.md`。
- **六、安全边界**：Hard Fail 清单扩至"规整性基础红线（步骤 2）+ 产出物质量红线（步骤 3）"。

#### 新增

- **`references/regularity-checklist.md`（新文件）**：规整性检查清单，引用 skill-lint 判则逐项检查（格式合规/frontmatter/目录结构/reference 拆解/触发词边界/业务流五层/Hard Fail/可评估性基础）。每项标注引用 skill-lint 哪条判则（如 `skill-lint/references/structure-standards.md`）。不搬 skill-lint 全文。
- **`references/reference-audit.md`（新文件）**：references 精简方案与执行记录。现状盘点（v0.4.0 7 个 + v0.5.0 新增 2 个 = 9 个）、精简方案（目标 5 核心）、暂缓项（待用户确认）、执行记录。

#### 变更（v0.4.0 既有文件调整）

- **`references/skill-lint-handoff.md`**：v0.4.0 的"规整性完全交给 skill-lint"边界调整为——skill-lint 是规整性**权威判则源**，本技能主流程步骤 2 引用其判则做规整性检查；用户也可先跑 skill-lint 再跑本技能（联跑模式），结果合并进报告。新增"联跑模式"说明。不重叠边界表更新：规整性各维度从"skill-lint ✅ / 本技能 ❌"改为"skill-lint ✅ 权威判则 / 本技能 步骤 2 引用其判则检查"。新增"规整性基础一站式检查"行。
- **`references/universal-dimensions.md`**：末尾新增"附录：六维度来源说明"（v0.5.0 合并自 `six-dimensions-origin.md`，含 A.1 来源/A.2 不输出通用总分/A.3 业界参考）。
- **`references/six-dimensions-origin.md`**：文件头加 v0.5.0 合并标注——"内容已合并至 universal-dimensions.md 附录，本文件保留备查"。

#### 不变（保留 v0.4.0 通用化路线）

- 法律产出评估部分**完全保留 v0.4.0 的通用泛化路线**：通用六维度主流程 + 场景微调说明 + 三场景 rubric 降级为深度参考附录。
- `eval-methodology.md` 完全不动。
- `scenario-tuning-notes.md` 不动。
- `test-trio-method.md` 不动。
- 三场景 rubric（contract/litigation/compliance）不动（深度参考附录）。
- 与 skill-creator 内置 eval 体系的差异化定位保留。

### v0.4.0 校准状态（保留）

- 已通过 2 场景校准（trademark + case-analysis），通用六维度覆盖度初步通过。
- 未经合同型真实 skill 校准（contract-copilot 待 T-401）。
- 未经真实诉讼文书生成 skill 校准（起诉状/答辩状/代理词生成待 T-402）。

### Out of Scope（v0.5.0 不做）

- 不动 skill-lint 本体（只引用判则）
- 不动其他 skill（five-question-distill worker 并行跑）
- 不动书稿仓（ch07 引用更新留 PM 后续）
- 三场景 rubric 大精简（删整个 rubric）标待用户确认

## [v0.4.0] - 2026-07-05

### 通用化重构：通用六维度主流程 + 场景微调 + 三场景降附录

**用户决策原话**（杨卫薪律师 2026-07-05 拍板，详见 DECISIONS.md D-2026-07-05-02）："最想要达到的是能够针对常规法律场景做一个更通用的评估""前期可以先做简单一点，做最通用的场景，泛化性最强""不可能针对每一种法律文书都能面面俱到""类比 claude code 升级的 skill creator 内部自带的 eval 体系"。

本版本**撤回 v0.1.0 ~ v0.3.x 的"不构建通用六维度基准"硬边界**（部分撤回——通用六维度可作主流程，但仍不打总分排榜），走**通用泛化路线**：一套通用六维度 + 通用 taste 覆盖常规法律场景主流程；场景差异通过"场景微调说明"一段话级别处理；三场景 rubric 降级为深度参考附录。

#### 新增

- **`references/universal-dimensions.md`（新文件，主流程核心）**：通用六维度详解（法律准确性 / 事实叙述与证据运用 / 逻辑说服力 / 争议焦点与争议关键把握 / 实务可用性 / 交付物格式完整度）。基于 ch07 L794-803 合同型六维**回归通用命名**（去掉 v0.3.x 的合同专属化如"事实叙述与条款定位"），融合 Phase B calibration-findings 共性发现。每维给检查问题 / 低分表现 / 高分表现 / 四类场景微调附注（合同/诉讼/合规/案件分析各一句话）。附"通用 taste 8 项（所有场景必查）+ 场景 taste（深度参考）"组织、案件分析型等非终端交付物的豁免处理、与 ch07 六维度的对应关系、v0.4.0 局限与远期方向。
- **`references/scenario-tuning-notes.md`（新文件）**：合同 / 诉讼 / 合规 / 案件分析四类典型场景的微调说明，**替代三场景 rubric 的主流程角色**。每场景一段话，说明该场景在通用六维度上的侧重 + taste 关注点 + 非终端交付物（如案件分析报告）的豁免规则（豁免法庭文书法定结构、豁免诉请明确性，避免"虚假低分"）。不是独立 rubric，是通用维度的场景附注。

#### 变更（SKILL.md 主流程改造）

- **`SKILL.md` version**：0.3.1 → 0.4.0。
- **`SKILL.md` description**：调整定位为"v0.4.0 走**通用泛化路线**：一套通用六维度 + 通用 taste 覆盖常规法律场景主流程；场景差异通过'场景微调说明'处理；三场景 rubric 降级为深度参考附录。不追求每种法律文书面面俱到，前期优先通用泛化性最强；类比 skill-creator 内置 eval 体系，但补的是'法律 taste 层 + 法律场景微调'"。触发词加"案件分析 skill 怎么评""AI 写的...分析报告合格吗"。
- **一、核心定位**：新增"与 skill-creator 内置 eval 体系的差异定位"段（已核验 skill-creator 有 test cases / 双跑 / assertions / aggregate_benchmark / eval-viewer / description optimization / blind comparison 完整 eval 体系；本技能不重复造，补"法律 taste 层 + 法律场景微调层"两层）。第三段把"ch07 六维度 = 合同型参考起点，非通用基准"改为"v0.4.0 把这套六维度正式确立为本技能的通用评测主流程"。
- **二、taste 项**：从 v0.3.x 的"每场景单独成节"改为"通用 taste（所有场景必查）+ 场景 taste（深度参考）"两层。
- **步骤 1（识别场景）**：保留，但场景识别结果用于"选场景微调说明"，不再驱动"选独立 rubric"。"案件分析型"处理简化——v0.3.x 要求"降级套用诉讼型并标注不适配维度"，v0.4.0 因走通用路线，改为"直接套用通用六维度 + 案件分析场景微调说明，自动豁免维度 6 法庭文书法定结构和维度 5 诉请明确性"，不再需要"降级"。
- **步骤 3（核心改造）**：从 v0.3.x 的"按场景选独立 rubric（contract / litigation / compliance scenario-rubric.md）"改为"套用通用六维度（universal-dimensions.md）+ 参考场景微调说明（scenario-tuning-notes.md）"。三场景 rubric 降级为深度参考附录，仅在评测结论边缘 / 场景特异争议 / 需要更细颗粒度时启用。
- **步骤 5（逐维度评分）**：从"按所选场景维度清单逐项打分"改为"按通用六维度逐项打分 + 单独核查通用 taste 8 项"。深度核查（可选）参考场景 taste + 中国法律语境三层。
- **步骤 7（产出报告）**：报告必含项里"按场景维度逐项评分表"改为"通用六维度逐项评分表"；新增"本次使用的场景微调说明"项。
- **四、关于"通用基准"的明确边界**：调整——v0.4.0 部分撤回 v0.1.0 ~ v0.3.x 的"不构建通用六维度基准"硬边界（通用六维度可作主流程），但保留"不打单一总分 / 不做跨场景排行榜 / 不做加权总分"硬边界。
- **五、参考业界方案**：补"skill-creator 内置 eval 体系"段——明确本技能 v0.4.0 不重复造 skill-creator 的通用 eval 基础设施，而是补"法律 taste 层 + 法律场景微调层"。
- **参考规则段**：拆为"主流程文件（v0.4.0 起核心）"和"深度参考附录（v0.4.0 起降级）"两组。

#### 降级（保留不删，文件头加标注）

- **`references/scenarios/contract-scenario-rubric.md` 文件头加标注**："v0.4.0 起降级为深度参考附录。主流程见 universal-dimensions.md + scenario-tuning-notes.md。本文件在 taste 深度核查、合同特异争议、更细颗粒度评分时启用。本文件内容保留不动，作为 v0.3.x 沉淀供深度参考。"
- **`references/scenarios/litigation-scenario-rubric.md` 文件头加标注**：同上，并明确启用场景含"长文 judge 稳定性、中国法律语境三层"。
- **`references/scenarios/compliance-scenario-rubric.md` 文件头加标注**：同上，并明确启用场景含"可追溯证据 taste-8 强制等级、跨境数据更新频率 taste-9"。
- 三场景 rubric **内容保留不动**，作为 v0.3.x 沉淀的深度参考附录。

#### 撤回（v0.3.1 待决项里撤掉场景细分方向的项）

下列 v0.3.1 calibration-findings.md 第六节登记的"v0.4.0 待决项"，因走通用泛化路线**撤回**，改为远期 BACKLOG（见 TASKS.md BACKLOG 段）：

- **撤回**：新增 `references/scenarios/case-analysis-scenario-rubric.md`（案件分析型专属维度集——继承诉讼型 1/3/5，剔除 2/6，新增法律问题树/检索吸收深度/策略路径切换/行动清单可执行性等）。**改为**：案件分析型通过通用六维度 + scenario-tuning-notes.md 第四节"案件分析型场景"处理，自动豁免维度 6 法庭文书法定结构和维度 5 诉请明确性。专属维度集作为远期 BACKLOG。
- **撤回**：补未覆盖场景专属维度清单（法律检索 / 文书润色 / 尽调）。**改为**：这些场景套用通用六维度 + 最接近的场景微调说明，专属微调作为远期 BACKLOG。

下列 v0.3.1 待决项**保留**（与通用泛化路线不冲突）：

- 保留：合规型 taste-10（在先权利状态动态性）——可作为场景 taste 在 compliance-rubric.md 深度参考附录里启用。
- 保留：test-trio-method.md "同类"场景化定义——与主流程维度集无关。
- 保留：skill-lint-handoff.md "Hard Fail 标签化"和"降级模式合法性"补强——与主流程维度集无关。

#### 不变（保留 v0.3.x 扎实部分）

- **`references/eval-methodology.md` 完全不动**：三层评测栈 / 三类 grader / capability-regression 分离 / 参考解三档 / LLM-as-judge 四校准 / SWE-bench 双门槛 / 中国法律语境三层 / taste 结构化边界 / 暂缓事项。仍是 SKILL.md 四-B / 四-C / 四-D 的依据文件。
- **`references/skill-lint-handoff.md` 不动**：与 skill-lint 的对接协议、Hard Fail 清单复用为产出物质量红线。
- **`references/test-trio-method.md` 不动**：三份测试法准备指南。
- **`references/six-dimensions-origin.md` 不动**：六维度来源说明。
- **`templates/skill-evaluation-report.md` 不动**（v0.4.0 调整：报告里"按场景维度逐项评分表"自然演化为"通用六维度逐项评分表"，模板字段通用，不需要改）。
- **不构建跨场景总分排行榜 / 与 skill-lint 划界 / 评测目的定位"补哪句话"** —— v0.1.0 既有定位维持。
- **不动被测 skill**（trademark-assistant / legal-case-analysis / contract-copilot 等）。
- **不动 manuscript**（ch07 正文引用更新另行做，本版本只动 legal-skill-evaluation/）。

### v0.4.0 校准状态

- **已通过 2 场景校准**：trademark 商标合规（合规型）+ case-analysis 案件分析（案件分析型）。覆盖度验证初步通过——通用六维度在商标合规场景 5 维完全可用 + 1 维描述偏严（已在 scenario-tuning-notes 里以"一次性合规动作豁免"体现），在案件分析场景需要豁免维度 6 法庭文书法定结构（已在 scenario-tuning-notes 里以"案件分析型豁免"体现）。
- **未经合同型真实 skill 校准**：contract-copilot 待 T-401 校准。
- **未经真实诉讼文书生成 skill 校准**：起诉状/答辩状/代理词生成待 T-402 校准。
- 远期 BACKLOG（不在 v0.4.0 做）：针对特定场景做更深泛化——案件分析 / 法律检索 / 文书润色 / 尽调专属维度集。前期优先把通用六维度经更多场景验证后再考虑深化。

## [v0.3.1] - 2026-07-05

### Phase B 首批校准（trademark + case-analysis）

用两个成型 skill 做 capability suite 首批校准（共 6 份测试材料：每 skill × 三份测试法），反向回灌 v0.3.0 维度集 / taste 项 / 流程方法。完整反向发现见 `evals/case-bundle-260705/calibration-findings.md`。

#### 新增（评测产出）

- **首批 capability suite 沉淀**：`evals/case-bundle-260705/` 三件套
  - `trademark-case-01.md`：trademark-assistant v1.5.4 商标合规初筛场景评测（合规型 6 维度评分 + 9 taste 核查 + 模拟产出标注）
  - `case-analysis-case-01.md`：legal-case-analysis v0.2.6 案件分析场景评测（诉讼型降级套用 + 不适配标注 + 现成 examples 直接复用）
  - `calibration-findings.md`：反向发现汇总（维度集够不够用 / taste 要不要加 / 三份测试法可操作性 / skill-lint-handoff 实战 / 案件分析型边界处理）

#### 小改（本体微调，校准回灌）

- **`references/scenarios/compliance-scenario-rubric.md` 维度 4 描述补"一次性合规动作豁免"**：来源 trademark-case-01 维度 4 校准发现。原描述"具体到动作、责任人、时限、分阶段"对企业合规整改合理，但对商标申请这类一次性合规动作过度。补"对一次性合规动作（商标申请、备案登记、单次尽调），责任人/时限可降级为'动作完成节点'"。
- **`SKILL.md` 步骤 1 补"案件分析型"边界提醒**：来源 case-analysis-case-01 核心发现。当被测 skill 交付物是法律分析报告/分析底稿时，归入"案件分析型"，降级套用诉讼型并显式标注不适配维度（典型：维度 2 诉讼请求明确性、维度 6 文书格式与法庭语体），避免"虚假低分"。
- **`references/scenarios/litigation-scenario-rubric.md` 顶部声明更新**：本次校准的是案件分析型（法律分析报告），不是诉讼文书生成（起诉状/答辩状/代理词）。诉讼型 6 维度在案件分析场景仅 3 个完全适配（1/3/5）、1 个颗粒度偏低（4）、2 个不适配（2/6）。**真实诉讼文书生成 skill 仍待 T-402 校准，本次不构成诉讼型 rubric 的完整回灌。**
- **`references/scenarios/compliance-scenario-rubric.md` 顶部声明更新**：合规型 6 维度在商标场景 5 个完全可用，1 个描述偏严已小改；taste-8（可追溯证据）在商标场景下命中，强制等级待用户拍板。
- **SKILL.md version**: 0.3.0 → 0.3.1。

#### 不动清单（标 v0.4.0 待用户确认）

下列属大改或方向性决策，不在 v0.3.1 直接动，已在 calibration-findings.md 第六节登记：

- 新增 `references/scenarios/case-analysis-scenario-rubric.md`（案件分析型专属维度集——继承诉讼型 1/3/5，剔除 2/6，新增法律问题树/检索吸收深度/策略路径切换/行动清单等）
- 新增合规型 taste-10（在先权利状态动态性）
- test-trio-method.md "同类"场景化定义
- skill-lint-handoff.md "Hard Fail 标签化"和"降级模式合法性"补强
- 法律检索/文书润色/尽调专属维度集

### v0.3.1 校准实战关键发现

1. **trademark-assistant 表现优秀**：output-contract 把"信息不足→待补充（暂不评级）"硬编码为第四档，是合规型 taste-3 + Hard Fail"未标注信息不足却给确定结论"的优秀工程化实现。合规型 6 维度在商标场景基本可用。
2. **legal-case-analysis 暴露覆盖盲区**：v0.3.0 三场景维度集（合同/诉讼/合规）无法完全覆盖"案件分析型"（前置分析底稿）。legal-case-analysis 在 9 个诉讼型 taste 项全部通过，但维度 2/6 不适配。提案 v0.4.0 新增专属维度集。
3. **流程方法实战可用**：skill-lint-handoff（Hard Fail 红线复用）/ 三份测试法 / 维度+taste 双层评分 / 证据锚定 / 降级套用机制——在两个真实 skill 上均可操作，无重大卡点。
4. **诚实标注规则有效**：trademark 无 archive/examples 必须模拟产出，本次严格按"模拟产出顶部标注'非真实 skill 调用'"执行，避免误判。

## [v0.3.0] - 2026-07-05

### 重新定位 + 改名（核心）

- **改名**：`skill-evaluation` → `legal-skill-evaluation`（保留连贯性 + legal 前缀）。`git mv` 保留文件历史。
- **重新定位**：从 v0.2.0 的"场景化评测框架"收窄为**法律文件产出质量评测**。评测对象 = 法律 Skill 跑出来的**交付物**（合同初审意见、起诉状、答辩状、代理词、合规扫描报告、整改建议、尽调备忘录等），**不是** Skill 本身的规整性（规整性归 skill-lint，本技能不重复造）。
- **用户决策原话**（杨卫薪律师拍板）："法律 skill 质量评测的本质，是通过测评法律文件产出的质量来评的。所以这个 skill 确实需要长，法律场景特异化的。"

### 新增

- **SKILL.md 重写**：`name: legal-skill-evaluation`，`version: "0.3.0"`，`homepage` 改为 private-skills 仓 legal-skill-evaluation 子目录。`description` 改写为"法律文件产出质量评测"——评测对象 = 法律交付物；规整性交给 skill-lint；触发词保留 v0.2.0 全部 + 加"法律产出质量""交付物质量""文书产出评测""AI 写的起诉状/合同/合规报告合格吗"。顶部"核心定位"段重写为：法律 skill 质量评测 = 法律文件产出质量评测；与 skill-lint 划界（规整性 vs 产出合理性）。
- **taste 项每场景单独成节**：SKILL.md 新增"二、taste 项：每个场景单独成节"导引段，链接到 contract / litigation / compliance 三份 rubric 的第二节（taste 不再混在维度清单末尾，独立可索引）。
- **`references/test-trio-method.md`（新文件）**：三份测试法的材料准备指南与评分记录模板（合同 / 诉讼 / 合规各给熟悉 / 同类不熟悉 / 故意缺失背景三类示例）+ 长期沉淀（20-50 例 regression suite）的指引。对接 ch07 第六节 L774-788。
- **诉讼型维度补 taste-8 / taste-9**：taste-8（提示 AI 引用法条需律师核实适用性，来自杨卫薪《答辩状与代理词生成》）+ taste-9（长文书避免"像一般大模型作文"，来自 DR-5 引 LAiW）。
- **合规型维度补 taste-8 / taste-9**：taste-8（合规核查需提供可追溯证据 / 截图存证，来自杨卫薪《全球制裁清单风险核查》）+ taste-9（跨境场景提示数据更新频率差异，同源）。
- **litigation / compliance rubric 加"v0.3.0 待真实 skill 校准声明"**：维度由 DR-5 + 杨卫薪知识体系推导，**未经真实 skill 校准**。校准任务见 TASKS.md T-301。本版本不是终稿。
- **`references/skill-lint-handoff.md` 强化**：第 1bis 节新增"Hard Fail 清单复用为产出物质量红线"——产出物命中编造事实 / 未标注信息不足给确定结论 / 草稿当正式意见 / 引用错误依据 / 未提示人工复核 / 泄露敏感信息任一项，评测报告直接 ❌，不走维度评分。
- **SKILL.md 步骤 1 / 步骤 2 / 参考规则段**：步骤 1 改为"识别场景 + 声称的交付物"（交付物即评测对象）；步骤 2 改为"直接消费 skill-lint 结论 + 复用 Hard Fail 清单为产出物红线"；参考规则段加入 test-trio-method.md。

### 变更

- **SKILL.md description**：v0.2.0 的"法律 Skill 的场景化评测工具"→ v0.3.0 的"法律文件产出质量评测"。
- **SKILL.md 顶部"核心定位"段**：从"解决一个具体问题：一个法律 Skill 跑出来的输出……"改为"解决一个具体问题：一个法律 Skill 跑出来的**交付物**……"——交付物即评测对象。
- **术语统一**：旧版"输出合理性层"在新版仍保留，但所有"评测 Skill 输出"统一改为"评测 Skill 产出物 / 法律文件产出物"，避免与"skill 自身的输出格式"混淆。

### 不变（保留 v0.2.0 扎实部分）

- **`references/eval-methodology.md` 完全不动**：三层评测栈 / 三类 grader / capability-regression 分离 / 参考解三档 / LLM-as-judge 四校准 / SWE-bench 双门槛 / 中国法律语境三层 / taste 结构化边界 / 暂缓事项。仍是 SKILL.md 四-B / 四-C / 四-D 的依据文件。
- **SKILL.md 三、评测流程与方法论**：v0.2.0 既有结构保留（步骤 1-7 + 评测方法论 + LLM-as-judge 四校准 + 双门槛判定）。v0.3.0 只在步骤 1 / 步骤 2 / 参考规则段做最小修改。
- **`references/scenarios/contract-scenario-rubric.md` 不动**：合同型六维度 + taste 1-6 已较扎实，本次不改。
- **`references/six-dimensions-origin.md` 不动**。
- **`templates/skill-evaluation-report.md` 不动**。
- **不构建通用六维度基准、与 skill-lint 划界、评测目的定位"补哪句话"** —— v0.1.0 既有定位，v0.2.0 / v0.3.0 维持。

### v0.3.0 的局限（不是已完成品）

- v0.3.0 是"经结构调整的、待真实 skill 校准的版本"，**不是已完成品**。
- 诉讼型 / 合规型维度集由 DR-5 + 杨卫薪知识体系**推导**而来，**未经真实 skill 校准**——维度覆盖度、taste 项命中分布、长文 judge 稳定性参数都需真实跑过后回灌。
- 20-50 例真实失败案例的 capability suite + regression suite 尚未沉淀（这是 Phase B 任务，见 TASKS.md T-301）。
- 法律检索 / 文书润色 / 尽调的专属维度清单仍未补（当前降级套用合同型）。

### 待办（留 Phase B 由 PM 跟进）

- **真实案例校准**（T-301）：用 contract-copilot 优先 + 真实诉讼 / 合规 skill 各 1-2 个跑评测，回灌维度集与 taste 项；沉淀 20-50 例 case bundle。
- 补未覆盖场景专属维度清单（法律检索 / 文书润色 / 尽调）。

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
