# 规划：legal-case-analysis 评测包（第二个 eval bundle）

> 目标：以 `legal-case-analysis`（v1.0.0，纯指令型 Skill）为**第二个 eval bundle**，验证
> `legal-skill-evaluation` 框架的通用性，并趟出「指令型 Skill」的标准接入范式，反推 harness 迭代。
> 本文件仅为方案，不含代码实现。待评审确认后由实现任务落地。

## 0. 为什么是 legal-case-analysis

- 它是 legal-skills 里成熟度高的**前置法律分析引擎**，被多个下游 Skill 复用，评测价值高。
- 关键点：**它没有 `scripts/` 目录**，是纯指令型（SKILL.md + references 引导 LLM）。
- 这正好暴露当前 harness 的偏科：`contract-calibration-260730` 的 micro-probe 直接
  `import scripts.report.reporting` / `scripts.review.review_runtime`，只服务**有 Python
  接口的命令式 Skill**。指令型 Skill 没有可被子进程确定性调用的入口，**micro-probe 路线不适用**。
- 为它建 bundle = 补 harness 对指令型 Skill 的接入盲点，是框架迭代的真实驱动力。

## 1. 接入路线选择

harness 的「标准模式」八步流程里，与具体 Python 接口解耦的是：

- 步骤 2 候选绑定（`evaluation_package_gate.py hash`）
- 步骤 3 通用质量门（skill-lint 收据复用 / `regularity-checklist.md`）
- 步骤 4 三份脱敏测试材料 + 候选真实运行产出
- 步骤 5—7 六维度 / taste / 领域门禁
- 机器门禁走 `semantic_micro_case_gate.py`（验证产出最小语义，如"目标缺失时应暂停"
  而非"自选自的"）、`capability_suite_gate.py`（能力 suite 覆盖）

**因此 legal-case-analysis 走「材料 + LLM 真实运行 + 语义/能力门禁」路线，而非 micro-probe 路线。**

## 2. 拟新建的 bundle 结构（对照 contract-calibration-260730）

```
evals/case-analysis-<YYYYMMDD>/
├── evaluation-package.json      # 候选绑定 + 场景(legal-analysis) + 通用门禁结论
├── capability-suite.json        # 能力 suite（familiar/novel/edge 分层，覆盖目标）
├── calibration-report.md        # 六维度 + taste + 最小修复单元
├── materials/                   # 三份脱敏测试材料（案情/合同/证据 各一）
├── runs/                        # 候选真实运行产出（LLM 调用，非子进程 import）
└── semantic-cases/              # 受控语义 micro-case（如"分析目标缺失时须暂停"）
```

> 不创建 `contract_copilot_micro_probe.py` 这类命令式探针；语义校验改由
> `semantic_micro_case_gate.py` 针对 `runs/` 产出做最小语义断言。

## 3. 受控语义 case 设计（首批建议 3—5 例）

指令型 Skill 的「最小修复单元」多落在 SKILL.md / references 口径，可转化为语义断言：

1. **目标缺失不自选**：给材料但不给分析目标，产出须显式请求确认目标，不得自行选
   「评估是否起诉 / 出具报告」等并直接产出结论。（对应 contract 侧 OBJECTIVE-MISSING）
2. **事实与陈述区分**：含一方当事人陈述 + 一方证据矛盾的材料，产出须区分"陈述"与
   "证据"，不得混同为已证事实。
3. **条号不凭记忆**：材料中未给条号、未检索时，产出不得出现具体法条条号/司法解释全称，
   须标「条号待检索」或仅写规则内容+法律名称（核心原则第 10 条）。
4. **未提及不补全**：关键要素（如管辖、时效）材料未提，产出标「未提及/待补充」，不得臆造。
5. **脱敏模式开关**：声明用于公开演示时，产出须对主体/地域做匿名化且不丢法律关系结构。

## 4. 对 harness 本身的迭代诉求（反向推动）

为支持指令型 bundle，harness 可能需要补：

- **bundle 模板**：把"材料 + runs + semantic-cases"的标准骨架固化（contract 侧是命令式特例）。
- **门禁输入适配**：`semantic_micro_case_gate.py` 当前样例偏合同语义，需确认其对通用
  法律产出的断言语法可复用，或抽出"场景无关最小语义断言"子集。
- **文档**：SKILL.md 八步流程里显式区分「命令式 Skill（micro-probe）」与「指令型 Skill
  （材料+LLM 运行+语义门禁）」两条接入路径，避免后人误用 micro-probe。

## 5. 落地步骤（确认后执行）

1. 在 `evals/` 下建 `case-analysis-<date>/`，填 evaluation-package.json（候选 sha256、
   scenario=legal-analysis、deliverable=法律分析底稿/报告、audience=承办律师）。
2. 准备三份脱敏材料（复用/改写 `legal-case-analysis/examples/` 或新建）。
3. 用候选真实运行产出到 `runs/`（标注"真实运行"，不冒充合成）。
4. 写 `semantic-cases/` 受控断言，跑 `semantic_micro_case_gate.py` 与 `capability_suite_gate.py`。
5. 补 `calibration-report.md`，登记最小修复单元（若有）。
6. 若 harness 缺指令型接入范式，按 §4 补模板/门禁/文档，提交为 harness 自身的迭代。

## 6. 开放问题（待用户/律师拍板）

- 真实运行产出行 LLM 调用，成本和可复现性如何约束？（建议固定模型 + 缓存 runs/）
- 三份材料是否脱敏：legal-case-analysis 默认不脱敏（真实办案），但评测包应脱敏——
  需确认材料来源合规（用示例/合成，或已授权脱敏样本）。
- 是否要先只做"快速模式"（NOT_VERIFIED）探路，再升标准模式。
