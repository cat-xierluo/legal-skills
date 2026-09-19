---
name: legal-skill-evaluation
description: 法律 Skill 分层质量评测工具。消费 skill-lint 的通用质量结论，再用三份测试材料、通用六维度、场景微调和律师 taste 评估法律产出，并定位最小修复单元。本技能应在审查、回归验证或发布验收法律 Skill 时使用。不要用于代替通用 Skill lint、正式法律意见或跨场景排名。
version: "0.8.12"
license: CC-BY-NC
author: 杨卫薪律师（微信ywxlaw）
homepage: https://github.com/cat-xierluo/legal-skills
---

# Legal Skill Evaluation

评估一个法律 Skill 是否能在指定场景稳定产出可接手的法律工作产品。先消费通用质量门，再执行法律领域动态评测；不复制 skill-lint 规则，不用单一总分掩盖红线。

## 适用与边界

在以下任务中使用：

- 审查一个法律 Skill 当前是否可用；
- 比较修复前后是否真正改善；
- 为发布验收准备候选绑定的评测证据；
- 从失败产出定位应修改的指令、参考、模板、检查器、样本或输入边界。

不要用于：

- 创建或一般性修改 Skill；
- 只做格式 lint 或代码审查；
- 对不同法律场景做总分排名；
- 代替承办律师核验事实、法源时效和正式交付。

## 三档评测模式

| 模式 | 使用时机 | 最小动作 | 证据结论 |
|------|----------|----------|----------|
| 快速 | 早期诊断、材料暂不齐 | 快速通用核查 + 至少一份代表性产出 + 六维度/taste 初筛 | NOT_VERIFIED |
| 标准 | 日常质量审查、修复迭代 | 候选绑定通用结论 + 三份材料 + 完整评分 + 最小修复单元 + 机器门禁 | 按实际收据填写 |
| 发布 | 发布或正式验收 | 标准模式全部动作 + Harness/稳定性/领域外部收据 + 回归双门槛 | 仅签发已有证据支持的正式标记 |

用户未指定时使用标准模式。材料不足以运行标准模式时降为快速模式，并在报告中说明缺口。

## 输入

开始前确认：

1. 被测 Skill 目录与本次候选版本；
2. 单一法律场景、声称交付物和目标读者；
3. 三份脱敏测试材料及已知关注点；
4. 每份材料由候选 Skill 真实运行得到的产出；
5. 可选：skill-lint 报告、旧版评测包、历史失败样本和外部签发收据。

若 Skill 同时覆盖多个场景，一次只选择一个场景；分别评测，不做平均。

## 安全规则

- 对测试材料、报告、样本和收据做脱敏，不保留真实姓名、案号、客户名或可反查组合。
- 法律准确性涉及现行法、监管口径或裁判尺度时，记录核验时间与来源；无法核验时标为待复核。
- 高风险结论、正式法律文书和外部交付由合格律师复核。
- 模拟产出显式标注“模拟”，不得冒充候选 Skill 的真实运行结果。

## 八步流程

### 步骤 1：锁定模式与评测范围

记录模式、场景、交付物、读者、排除项和验收目标。案件分析底稿归入 case-analysis；它不是起诉状、答辩状等终端诉讼文书，不套用不相关的法定格式要求。

### 步骤 2：绑定候选快照

计算候选目录哈希。评公开/可发布候选时优先使用 Git 跟踪范围，避免 `archive/`、本地配置和运行产物污染候选；不在 Git 工作树内时使用默认完整目录范围：

    python3 scripts/evaluation_package_gate.py hash --candidate-root /path/to/skill --scope git-tracked

把哈希和范围分别写入 `candidate.sha256` 与 `candidate.hash_scope`。候选内容或范围变化后重新计算；旧报告只作历史背景。

### 步骤 3：消费通用质量门

按 references/skill-lint-handoff.md 判断已有 skill-lint 收据能否复用。正式或发布评测优先运行当前 skill-lint；快速模式可使用 references/regularity-checklist.md 分流，但保持 NOT_VERIFIED。

通用阻断项非空时，把建议固定为 blocked。仍可继续运行领域案例以收集修复证据，但不能用领域分数冲抵阻断项。保留通用门禁的原始 Hard Findings；人工判定误报、不适用或超出本轮模式时，逐项记录 disposition、理由与证据，不得通过删除原始 finding 形成假通过。

### 步骤 3.5：选择接入路径（命令式 vs 指令型）

被测 Skill 的形态决定评测入口，先判定再开工：

- **命令式 Skill**：暴露可被子进程确定性调用的 Python 入口（如 `scripts/report/reporting.main`、`scripts/review/review_runtime`）。走 micro-probe 路线——写 `*_micro_probe.py` 直接 import 候选函数，构造 fixture 调入口、判返回码与产物结构。参考 `evals/contract-calibration-260730/contract_copilot_micro_probe.py`。
- **指令型 Skill**：纯提示词/指令驱动，无 scripts 可执行入口（如 `legal-case-analysis`）。走「材料 + LLM 真实运行 + 语义门禁」路线——三份材料交候选真实运行，产出存 `runs/`，受控语义 case 存 `semantic-cases/`。micro-probe 路线对其**不适用**。

两类 bundle 共用本框架的通用门禁（evaluation_package_gate / capability_suite_gate / semantic_micro_case_gate）。指令型 bundle 当前受 capability_suite_gate 的合约硬编码约束（见 T-903），需框架侧补 instruction-type suite 子类后方可全绿；快速模式可先以 evaluation_package_gate 闭环。首个指令型实例见 `evals/case-analysis-20260808/`。

### 步骤 4：构造三份测试材料

按 references/test-trio-method.md 准备：

1. familiar：评测人熟悉，检查是否抓住真实重点；
2. peer-unfamiliar：同类但不熟悉，检查结构和判断是否稳定；
3. missing-context：故意缺少关键背景，检查边界和不确定性处理。

标准与发布模式各包含一份。快速模式无法集齐时，记录缺失并保持 NOT_VERIFIED。

指令型 Skill 的三份材料放 `materials/`，运行产出放 `runs/`；命令式 Skill 的微案例 fixture 放 `micro-runs/`。

### 步骤 5：运行候选并保存收据

对每份材料运行同一候选 Skill。把文件、提示、角色、配置和附件清单组成输入 bundle 后计算输入哈希，三类案例使用不同 bundle。保存输出哈希、运行命令或会话标识、产出路径和必要日志。

- 命令式 Skill：由 `*_micro_probe.py` 子进程调用，收据含返回码与产物路径。
- 指令型 Skill：由 LLM agent 以材料为输入真实运行候选，产出写入 `runs/`；快速模式可复用候选既有真实运行产物（须标注来源与候选哈希，不得冒充本次运行），not-run 案例在 suite 中标 `not-run` 并补计划。

每个案例显式填写 `candidate_binding`：

- `current-candidate`：必须保存与评测包一致的 `candidate_sha256`；
- `historical-unbound`：只可用于校准与回归发现，必须说明历史来源，不能支撑 `DOMAIN_VERIFIED` 或 `enter-workflow`。

capability suite 中已经执行的案例另写结构化运行收据。收据逐项绑定 suite ID、case ID、候选哈希、输入/输出哈希、执行状态、断言集合和 runner 元数据，并区分：

- `artifact-backed`：保留脱敏输入与真实输出文件，门禁可复算文件哈希；
- `digest-only`：因隐私或体积只保存摘要与哈希，可用于回归发现，但不能单独支撑 verified suite。

不要用任意字符串、Agent 自报 PASS 或没有记录哈希的路径充当运行收据。

### 步骤 6：评估法律产出

先查法律产出红线：编造事实或依据、信息不足却给确定结论、草稿冒充正式意见、关键法源明显错误、高风险场景缺人工复核、泄露未脱敏信息。命中时记录证据并判 blocked。

再按 references/universal-dimensions.md 评六维度，并按 references/scenario-tuning-notes.md 微调。每个维度给 1–5 分和证据；确实不适用时填 N/A 与理由。随后逐项核查通用八项 taste。边缘结论或场景特异争议，才读取合同、诉讼或合规深度 rubric。

指令型 Skill 另用 `semantic-cases/` 下的受控语义 case 做最小语义断言（如「目标缺失须请求确认」「事实与陈述区分」「不凭记忆写条号」「未提及不补全」）。当前 `semantic_micro_case_gate.py` 仅覆盖合同场景的「目标缺失/附件缺失」两类，指令型断言暂以自然语言 judge_hint 人工判定（框架侧协议抽象见 T-903）。

### 步骤 7：定位最小修复单元并回归

从失败证据选择最小修复目标：

- skill-instruction：执行顺序、判断规则或边界未表达；
- reference：领域规则或深度判则缺失；
- template-schema：字段、枚举或结构约束缺失；
- checker：可机器判断的约束没有主动检查；
- fixture：缺少能复现失败的正例、反例或历史样本；
- intake-boundary：输入要求、缺失材料或场景边界不清。

修复后运行 FAIL_TO_PASS；同时用既有通过案例运行 PASS_TO_PASS。没有回归收据时，不宣称修复已经验证。

校准一个场景或准备发布回归时，把三份测试种子扩为 20—50 例分层 capability suite：

- full-e2e：使用真实文件、真实入口和最终交付物，至少保留输入 bundle、候选、输出和日志哈希；
- dynamic-micro：隔离一个角色、事实缺口、条款风险或历史失效，便于做 FAIL_TO_PASS；
- static-contract：检查能力契约、完成语义和证据闭环，不冒充业务动态运行。

每例记录来源、fixture 规格、候选绑定、执行状态和断言。`not-run` 只能写 `not-run`，不得预填 pass/fail；执行失败必须保留失败断言和收据。案例“已定义”不等于案例“已验证”。

### 步骤 8：输出评测包并运行门禁

以 config/evaluation-package.example.json 为起点生成 JSON 评测包，同时用 templates/skill-evaluation-report.md 生成可读报告。

运行：

    python3 scripts/evaluation_package_gate.py check --input /path/to/evaluation-package.json --candidate-root /path/to/skill

若本轮建立 capability suite，再运行：

    python3 scripts/capability_suite_gate.py --input /path/to/capability-suite.json --candidate-root /path/to/skill

存在已执行案例时，再复算结构化收据和本地证据文件：

    python3 scripts/capability_run_receipt_gate.py \
      --suite /path/to/capability-suite.json \
      --receipts /path/to/current-run-receipts.json \
      --candidate-root /path/to/skill \
      --evidence-root /path/to/evaluation-root

退出码 0 只表示评测包、suite 状态或运行收据的结构、候选绑定、实际文件哈希和结论闭环通过对应机器检查，不表示其中案例全部通过，也不替代律师对法律语义的判断。以 gate 输出的 `suite_status`、executed/not-run 计数、证据层级和正式标记为准。

## 不可降级约束

<!-- skill-lint:constraint EVAL-REPORT-COVERAGE -->
标准或发布评测包必须同时包含 familiar、peer-unfamiliar、missing-context 三类案例；每个案例必须覆盖 DIM-1 至 DIM-6 以及 TASTE-1 至 TASTE-8，维度不适用时必须提供理由。

<!-- skill-lint:constraint EVAL-EVIDENCE-BINDING -->
标准或发布评测包必须把候选哈希及其范围、通用门禁、每个当前案例、输入 bundle 和输出绑定到同一候选与同一轮运行；历史未绑定案例必须显式降级，不得复用为当前验收收据。

<!-- skill-lint:constraint EVAL-CLOSURE -->
总体建议必须与阻断项、低分维度、taste 失败和回归结果一致：存在通用阻断或法律红线时为 blocked；存在未闭环失败时不得写 enter-workflow。

## 结论与正式标记

总体建议只使用：

- enter-workflow：没有阻断项，领域验收达到标准，要求的回归已经闭环，并有候选绑定的 DOMAIN_VERIFIED 收据；
- revise-and-retest：问题已定位但仍需修复或重测；
- blocked：通用门禁或法律红线阻断。

证据状态只使用：

- HARNESS_REVIEW_VERIFIED：skill-lint Harness 审查有候选绑定收据；
- INSTRUCTION_STABILITY_VERIFIED：独立评估者完成规定的基线、留出集和多次运行；
- DOMAIN_VERIFIED：合格法律领域评估者完成本次候选的领域验收；
- NOT_VERIFIED：证据不足。

NOT_VERIFIED 不等于失败，也不与任何正式标记并列。Skill 作者或本技能自身不为自己的指令稳定性签发正式结论。

## 输出物

标准输出包括：

1. 机器可读 JSON 评测包；
2. 人类可读 Markdown 报告；
3. 通用门禁与运行收据；
4. 最小修复单元清单；
5. 修复后回归收据（若已执行）。

场景校准或发布回归另输出 20—50 例 capability suite；未执行案例必须保留 `not-run`，整体保持 `NOT_VERIFIED`。

## 参考文件路由

主流程按需读取：

- references/skill-lint-handoff.md：通用质量结论的版本化交接；
- references/regularity-checklist.md：无完整收据时的非权威快速分流；
- references/test-trio-method.md：三份材料构造；
- references/universal-dimensions.md：六维度与通用 taste；
- references/scenario-tuning-notes.md：合同、诉讼、合规、案件分析微调；
- references/eval-methodology.md：grader、参考解、judge 校准与双门槛；
- templates/skill-evaluation-report.md：可读报告模板；
- config/evaluation-package.example.json：机器评测包示例。
- config/capability-run-receipts.example.json：已执行 capability case 的结构化收据示例。
- evals/contract-calibration-260730/capability-suite.json：20 例分层 suite 的当前实例；
- scripts/capability_suite_gate.py：suite 数量、分层、绑定、执行状态和结论闭环门禁。
- scripts/capability_run_receipt_gate.py：结构化运行收据、记录哈希和本地输入/输出证据复算门禁。
- scripts/semantic_micro_case_gate.py：受控合同微案例的最小语义边界门禁（目标缺失、附件缺失两类），校验「声明边界」与「实际行为」是否一致，不靠关键词字面判定法律语义。

仅在边缘结论或特异争议时读取：

- references/contract-scenario-rubric.md；
- references/litigation-scenario-rubric.md；
- references/compliance-scenario-rubric.md。

## 依赖

### 系统依赖

| 依赖 | 用途 | 安装 |
|------|------|------|
| Python 3.9+ | 评测包哈希、门禁与回归测试 | macOS 通常自带；或使用包管理器安装 |

脚本只使用 Python 标准库，无需安装第三方包。

## 验证命令

    python3 scripts/test_evaluation_package_gate.py
    python3 scripts/evaluation_package_gate.py check --input assets/evaluation-package-valid.json
    python3 scripts/test_capability_suite_gate.py
    python3 scripts/capability_suite_gate.py --input evals/contract-calibration-260730/capability-suite.json
    python3 scripts/test_capability_run_receipt_gate.py
    python3 scripts/capability_run_receipt_gate.py --suite evals/contract-calibration-260730/capability-suite.json --receipts evals/contract-calibration-260730/current-run-receipts.json --candidate-root /path/to/skill --evidence-root .
    python3 scripts/test_semantic_micro_case_gate.py
    python3 scripts/semantic_micro_case_gate.py --input <micro-case-input.json> --output <micro-case-output.md>
