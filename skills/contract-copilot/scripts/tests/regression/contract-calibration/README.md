# contract-copilot T-401 回归测试集

固化 `legal-skill-evaluation` v0.8.6 在 T-401 收尾时识别出的 **7 例 `executed-fail` 行为层缺陷**，并在 contract-copilot v1.6.0 修复后转为**必过回归**。

> 候选快照 `sha256 f3fa86a8…`（修复前）曾对这 7 例存在行为缺陷，已用 `@XFAIL_DEFECT` 标注；
> v1.6.0 修复后，按修复后 SKILL.md 规则刷新 `baseline-outputs/` 并移除 xfail，7 例现为必过回归。
> 注意：baseline 为按修复后规则推导的期望行为样例（非真实 LLM 实跑产物），用于锁定「修复后应满足的行为契约」。

## 来源

- 上游：`legal-skill-evaluation/evals/contract-calibration-260730/capability-suite.json`
- 筛选条件：`execution_status == executed-fail` 且 `assertions[0].observed == fail`（共 7 例）
- 本目录 `fixtures/` 与 `baseline-outputs/` 为可复现快照，sha256 见各 `*-input.json`

## 缺陷分类

| 类别 | case | 断言（期望行为） |
|------|------|------------------|
| intake | CONTRACT-MICRO-ROLE-MISSING | 立场缺失时停止并请求确认，不得解析为「其他」继续 |
| intake | CONTRACT-MICRO-OBJECTIVE-MISSING | 目标缺失时暂停，不自行选择交付强度、不出正式结论 |
| clause-boundary | CONTRACT-MICRO-ACCEPTANCE-PAYMENT | 信息补齐前暂停，不出正式可签结论 |
| clause-boundary | CONTRACT-MICRO-CHANGE-FEE | 同上 |
| clause-boundary | CONTRACT-MICRO-PENALTY-STACKING | 同上 |
| report-integrity | CONTRACT-MICRO-REPORT-FIELD-COLLAPSE | 最终报告字段不得批量塌缩（待补占位 / 空法律依据） |
| report-integrity | CONTRACT-MICRO-PRODUCER-SELF-SUCCESS | 生产器自报成功不得关闭回归，独立 checker 应非零退出 |

## 运行

```bash
# 默认：7 例均为必过回归（baseline 已刷新为 v1.6.0 修复后期望行为）
python3 -m pytest scripts/tests/regression/contract-calibration/ -q

# 全量（含既有脚本层回归）
python3 -m pytest scripts/tests/ -q
```

## 修复验证模式（CC_REGEN=1，保留作为重跑入口）

若未来由外部 agent 按 `fixtures/*-input.json` 真实重跑候选，可将新输出按
`<case_id>-baseline-output.md` 命名放入 `$CC_REGEN_DIR`，再：

```bash
CC_REGEN=1 CC_REGEN_DIR=/path/to/new-outputs \
  python3 -m pytest scripts/tests/regression/contract-calibration/ -q
```

此时 xfail 标记自动解除（`REGEN=True` 时 `XFAIL_DEFECT` 为 no-op），直接验证期望行为。

## 设计说明（路径 A）

T-401 的 fail 属 **agent 行为层**缺陷（是否暂停 / 自选自的 / 下正式结论），
候选当前无程序化分析入口，故采用半自动回归：跑候选 → 落 output → 机器比对。
不自动调用 LLM。RECEIPT-016 类 artifact 绑定由 `legal-skill-evaluation` 侧 gate 负责。
