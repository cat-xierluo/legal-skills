# [skill-name] 法律 Skill 分层评测报告

## 0. 评测身份与证据绑定

| 字段 | 值 |
|------|----|
| 评测时间 | YYYY-MM-DD HH:MM |
| 评测模式 | 快速 / 标准 / 发布 |
| 被测 Skill 路径 | path |
| 候选 SHA-256 | sha256 |
| 候选哈希范围 | git-tracked / full-directory |
| 场景 / 交付物 / 读者 | scenario / deliverable / audience |
| 评测包 | evaluation-package.json |
| 评测人 | 脱敏代号 |

## 1. 通用质量门

| 项目 | 结果 | 证据收据 |
|------|------|----------|
| skill-lint 版本 | | |
| 候选哈希一致 | ✅ / ❌ | |
| 原始 Hard Findings | 无 / 列表 | |
| Finding 裁决 | 无 / finding ID + disposition + 理由 + 证据 | |
| 未解决阻断发现 | 无 / 列表 | |
| Harness | HARNESS_REVIEW_VERIFIED / NOT_VERIFIED | |
| 指令稳定性 | INSTRUCTION_STABILITY_VERIFIED / NOT_VERIFIED | |
| 法律领域 | DOMAIN_VERIFIED / NOT_VERIFIED | |

说明 NOT_VERIFIED 的具体缺口，不把它改写成“已通过”。

## 2. 三份测试材料

| 类型 | 材料代号 | 候选绑定 | 输入 bundle 哈希 | 输出哈希 | 主要用途 |
|------|----------|----------|------------------|----------|----------|
| 熟悉材料 | | current-candidate / historical-unbound | | | 检查重点识别 |
| 同类不熟悉材料 | | current-candidate / historical-unbound | | | 检查结构稳定 |
| 缺失背景材料 | | current-candidate / historical-unbound | | | 检查边界稳定 |

材料和产出均保持脱敏；真实姓名、案号、客户名不写入报告。历史未绑定案例只能用于校准和回归发现，不能支撑 DOMAIN_VERIFIED 或 enter-workflow。

## 3. 通用六维度

每个案例填写六维度。确实不适用时写 N/A 和理由，不以空白或零分代替。

### 案例：[case-id]

| 维度 | 分数（1–5 / N/A） | 证据定位 | 不适用理由 |
|------|------------------|----------|------------|
| DIM-1 法律准确性 | | | |
| DIM-2 事实叙述与证据运用 | | | |
| DIM-3 逻辑说服力 | | | |
| DIM-4 争议焦点与关键把握 | | | |
| DIM-5 实务可用性 | | | |
| DIM-6 交付物格式完整度 | | | |

本次场景微调：contract / litigation / compliance / case-analysis / nearest-fit。

## 4. 通用 taste

| taste | 结果 | 证据定位 |
|-------|------|----------|
| TASTE-1 不把不确定写成确定 | PASS / FAIL | |
| TASTE-2 区分法律风险与商业判断 | PASS / FAIL | |
| TASTE-3 区分风险与事实缺口 | PASS / FAIL | |
| TASTE-4 保持本方与角色立场 | PASS / FAIL | |
| TASTE-5 避免绝对化承诺 | PASS / FAIL | |
| TASTE-6 不把草稿当正式意见 | PASS / FAIL | |
| TASTE-7 提示人工复核 | PASS / FAIL | |
| TASTE-8 提示材料缺失影响 | PASS / FAIL | |

边缘结论或特异争议，再附场景深度 rubric 的核查记录。

## 5. 最小修复单元

| # | 失败证据 | 目标层 | 最小修复 | 回归案例 |
|---|----------|--------|----------|----------|
| 1 | | skill-instruction / reference / template-schema / checker / fixture / intake-boundary | | |

不默认把所有问题都改成“在 SKILL.md 补一句话”；优先选择能直接约束失败行为的最小层。

## 6. 双门槛闭环

| 门槛 | 结果 | 收据 |
|------|------|------|
| FAIL_TO_PASS：原失败是否被修复 | PASS / FAIL / 未执行 | |
| PASS_TO_PASS：既有通过项是否保持 | PASS / FAIL / 未执行 | |

未执行回归时，结论保持 NOT_VERIFIED。

## 7. 总体建议

- [ ] enter-workflow：无阻断项，六维度与 taste 达到本次验收标准，回归闭环成立。
- [ ] revise-and-retest：存在可定位缺陷，按最小修复单元修复后重测。
- [ ] blocked：通用门禁或法律红线命中，不能进入工作流。

正式证据标记：HARNESS_REVIEW_VERIFIED / INSTRUCTION_STABILITY_VERIFIED / DOMAIN_VERIFIED / NOT_VERIFIED（按实际证据填写，可多选；NOT_VERIFIED 不与任何正式标记并列）。

## 8. 机器门禁收据

### 8.1 评测包

    命令：python3 scripts/evaluation_package_gate.py check --input evaluation-package.json [--candidate-root skill-dir]
    退出码：
    artifact_sha256：
    passed_constraint_ids / failed_constraint_ids：

### 8.2 Capability suite（若本轮建立）

    命令：python3 scripts/capability_suite_gate.py --input capability-suite.json --candidate-root skill-dir
    退出码：
    executed-pass / executed-fail / not-run：
    suite_status：

### 8.3 结构化运行收据（存在 executed 案例时）

    命令：python3 scripts/capability_run_receipt_gate.py --suite capability-suite.json --receipts current-run-receipts.json --candidate-root skill-dir --evidence-root evaluation-root
    退出码：
    artifact-backed / digest-only：
    receipt_record_count / verified_artifact_count：
    passed_constraint_ids / failed_constraint_ids：

`digest-only` 只能支撑回归发现和当前状态记录，不能单独支撑 verified suite；律师语义审阅与 `DOMAIN_VERIFIED` 另行记录。

## 9. 安全声明

本报告只评估被测 Skill 与其脱敏产出，不替代正式法律意见，也不对作者作人身评价。法律时效性、事实真实性和最终交付仍由承办律师复核。
