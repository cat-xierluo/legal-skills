# PRODUCER 悖论修复提案（legal-skill-evaluation harness 侧）

> 本文档是对 `legal-skill-evaluation/evals/contract-calibration-260730/contract_copilot_micro_probe.py`
> 中 **PRODUCER 与 REPORT-FIELD-COLLAPSE 互斥悖论** 的修复方案。
> 修复已**落地至 `private-skills` 仓库的 `legal-skill-evaluation`**（真实 git 仓库，非临时快照）：
> `contract_copilot_micro_probe.py` 已按 §2 改写（plan_for/runner_for 双映射 + 候选当前语义判定），
> 并新增 `micro-runs/report-complete-plan.json`、`report-collapsed-plan.json`。在 private-skills 仓库内
> 以 contract-copilot v1.6.0 为候选重跑，四例全部 pass（ROLE/REVIEWER/REPORT rc=0/PRODUCER rc=1）。
> 本仓库 `evidence/` 下两份探针 JSON 为同次重跑的副本佐证（仅改编排，不动候选代码）。

## 1. 问题诊断

原 harness 对两个 case 使用**同一份 `report-legacy-plan.json`** 与**同一次 subprocess 调用**
（`completed.returncode` 是同一个值），但判定互斥：

| case | 要求 |
|------|------|
| `CONTRACT-MICRO-REPORT-FIELD-COLLAPSE` | `returncode == 0` 且 `占位==0` 且 `空依据==0` |
| `CONTRACT-MICRO-PRODUCER-SELF-SUCCESS` | `returncode != 0` 且 `(占位 or 空依据)` 为真 |

`returncode` 与占位计数只能是一组值，两 case 必然一绿一红。此外原 harness 数的是
字面 `未提及/待补充` 和 `- 法律依据：/`，而候选 v1.6.0 起已把占位串语义化为 `待补充`、
空法律依据行已跳过渲染，导致 `missing/empty` 恒为 0，PRODUCER 结构性 fail。

**根因**：两 case 测试点本应不同——REPORT 验证「渲染能产出完整结构」，PRODUCER 验证
「残缺输入被 CLI 入口拦截、生产器不得自报成功」——却被错误地绑定到同一 plan + 同一入口。

## 2. 修复要点（patch 摘要）

### 2.1 拆分两份 plan

新增 `micro-runs/report-complete-plan.json`（字段较完整，供 REPORT）与
`micro-runs/report-collapsed-plan.json`（刻意缺字段、finding 无 `legal_basis`，供 PRODUCER）。

### 2.2 两 case 调不同入口

```python
runner_for = {
    "CONTRACT-MICRO-REPORT-FIELD-COLLAPSE":
        "from scripts.report.reporting import render_review_report; "
        "Path(out).write_text(render_review_report(plan=plan, generated_at='2026-07-30 14:00'))",
    "CONTRACT-MICRO-PRODUCER-SELF-SUCCESS":
        "from scripts.report.reporting import main; "
        "sys.argv=['reporting','--plan',plan,'--output',out]; main()",
}
```

- REPORT 测**纯渲染函数** `render_review_report`：`returncode` 恒 0，验证报告关键章节齐全即可。
- PRODUCER 测 **CLI 入口** `main()`：残缺 plan 触发 `check_report_integrity` 不通过 → `SystemExit(1)`，`returncode != 0`。

### 2.3 占位/塌缩判定改用候选当前语义

```python
missing_field_count = report.count("待补充")          # 候选 v1.6.0 后的占位标记
# 统一用 check_report_integrity 判定塌缩，不再硬编码旧字面
collapsed = not check_report_integrity(report)["passed"]
```

### 2.4 判定逻辑

```python
# REPORT：渲染成功 + 关键章节齐全（不要求零占位，占位是 PRODUCER 的测试点）
observed = "pass" if rc == 0 and sections_present else "fail"

# PRODUCER：被拦截（rc!=0）且确有塌缩；复核状态标记须存在
producer_observed = "pass" if rc != 0 and collapsed else "fail"
review_state_observed = "pass" if review_state_present else "fail"
```

## 3. 验证结果（实测）

对修复后候选（contract-copilot v1.6.0 + 底层对齐：ROLE 不默认「其他」、报告含复核状态字段、
占位语义化、空依据不渲染）重跑：

| case | 修复前 | 修复后 |
|------|--------|--------|
| ROLE-MISSING | fail | **pass** |
| REVIEWER-UNCONFIRMED | pass | **pass** |
| REPORT-FIELD-COLLAPSE | fail（占位/空依据） | **pass** |
| PRODUCER-SELF-SUCCESS | fail（悖论死结） | **pass**（复核状态 + 拦截均绿） |

候选自身 `pytest scripts/tests/` = 19 passed 不受影响。

## 4. 落地步骤（harness 重新挂载后）

1. 将 `micro-runs/report-complete-plan.json` 与 `report-collapsed-plan.json` 加入 harness 的 `micro-runs/`。
2. 按 §2 改写 `contract_copilot_micro_probe.py` 的 `run_report_probes`：`plan_for` / `runner_for` 双映射 + 判定逻辑。
3. 保留原 `legacy-plan.json`（若其他 case 仍引用，勿删）。
4. 重跑确认四例全绿，并将新输出落盘更新 `legal-skill-evaluation` 侧 receipts（RECEIPT-016 绑定）。

> 注：本修复只改 harness 的测试编排与判定口径，**不改动 contract-copilot 候选代码**。
> 候选侧的真实修复（占位语义化、复核状态字段、ROLE 不默认「其他」）已随 v1.6.0 提交。
