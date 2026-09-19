# 与 skill-lint 的版本化对接协议

协议版本：legal-skill-evaluation-handoff/2

skill-lint 是通用 Skill 质量判则与门禁的权威来源；legal-skill-evaluation 消费其候选绑定结论，并继续执行法律产出质量评测。两者不复制规则，也不互相冒充正式验证者。

## 一、何时复用，何时补跑

满足以下条件时复用已有 skill-lint 结果：

1. 结果记录实际 skill-lint 版本与运行时间；
2. 结果绑定的候选 SHA-256 与本次候选一致；
3. 原始收据仍可定位；
4. 本次所需检查模式已覆盖。

任一条件不满足，按本次评测模式补跑对应检查。不要把旧版本、别的分支或别的候选结果拼接成当前证据。

## 二、交接对象

在评测包的 generic_gate 中保留以下字段：

    {
      "skill_lint_version": "x.y.z",
      "candidate_sha256": "64 位十六进制哈希",
      "candidate_hash_scope": "git-tracked | full-directory",
      "raw_hard_findings": [],
      "hard_findings": [],
      "finding_adjudications": [],
      "harness_status": "HARNESS_REVIEW_VERIFIED | NOT_VERIFIED",
      "instruction_stability_status": "INSTRUCTION_STABILITY_VERIFIED | NOT_VERIFIED",
      "domain_status": "DOMAIN_VERIFIED | NOT_VERIFIED",
      "evidence_receipts": ["相对路径或可追溯收据标识"]
    }

字段语义：

- candidate_hash_scope：哈希读取范围；评可发布候选优先 `git-tracked`，避免运行归档和本地私有配置进入快照。范围不同的哈希不得比较。
- raw_hard_findings：保留通用门禁原始 Hard Findings，不因人工复核而删除。
- hard_findings：经本轮模式裁决后仍未解决的阻断项；非空时，法律内容评测可继续用于定位问题，但结论不能是“进入工作流”。
- finding_adjudications：对原始 finding 的逐项裁决。仅允许误报、不适用或超出本轮模式；每项必须写 finding ID、disposition、理由和证据。未裁决 finding 继续留在 hard_findings。
- harness_status：只消费 skill-lint 对 Harness 七层闭环的正式结果。
- instruction_stability_status：只消费外部评估者基于基线、留出集和多次运行签发的正式结果。
- domain_status：法律领域验收完成后才可由合格领域评估者签发；通用 lint 不代签。
- NOT_VERIFIED：表示证据不足，不等于失败，也不等于通过。

## 三、阻断与继续评测

通用门禁出现阻断项时：

- 将总体建议固定为 blocked；
- 仍可运行三份材料，收集法律领域失败证据；
- 修复顺序先处理通用阻断，再处理法律产出缺陷；
- 修复后重新计算候选哈希，并让所有收据重新绑定。

法律产出红线包括但不限于：编造关键事实或依据、信息不足却给确定结论、把草稿当正式意见、错误法源支撑关键结论、高风险场景缺少人工复核提示、泄露未脱敏信息。命中红线时，维度分数只作诊断，不得冲抵阻断结论。

## 四、三档模式下的最小要求

| 模式 | 通用质量输入 | 允许的证据状态 |
|------|--------------|----------------|
| 快速 | 本技能快速核查桥或已有报告摘要 | NOT_VERIFIED |
| 标准 | 与候选哈希一致的 skill-lint 结果，或明确记录缺失项 | 正式标记或 NOT_VERIFIED |
| 发布 | 候选绑定的通用门禁、Harness 收据、稳定性收据和法律领域收据 | 仅按实际满足的正式标记填写 |

## 五、职责边界

| 问题 | 权威责任方 |
|------|------------|
| 结构、触发、安全、业务流、Harness、发布治理 | skill-lint |
| 法律产出六维度、taste、场景微调 | legal-skill-evaluation |
| 真实案件材料的法律正确性最终判断 | 合格律师 / 领域评估者 |
| 稳定性正式签发 | 与 Skill 生产者独立的评估者 |

当 skill-lint 不可用时，继续执行快速或标准模式的领域评测，但把缺口写入报告并保持 NOT_VERIFIED；不得把人工快速核查包装成正式 lint 结论。

## 六、原始 finding 的裁决边界

人工裁决用于防止通用静态规则在法律语义中误报，不用于绕开真正阻断：

- `false-positive`：证据语义与规则不符，例如“授权边界”被误识别成视觉几何边界；
- `not-applicable`：该规则客观不适用于候选产物类型；
- `out-of-scope`：finding 对发布或稳定性验收有效，但本轮明确只做标准校准且保持 `NOT_VERIFIED`。

裁决不会签发正式标记。需要进入发布验收时，重新按发布模式运行通用门禁；此前标为 `out-of-scope` 的 finding 必须重新进入阻断清单或取得正式证据关闭。
