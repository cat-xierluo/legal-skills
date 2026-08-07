# contract-copilot T-401 回归测试集

固化 `legal-skill-evaluation` v0.8.6 在 T-401 收尾时识别出的 **7 例 `executed-fail` 行为层缺陷**（候选 `sha256 f3fa86a8…`）。

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
# 默认：以 baseline 为「当前候选行为基线」，7 例均标记 xfail（预期失败，已知缺陷）
python3 -m pytest scripts/tests/regression/contract-calibration/ -q

# 全量（含既有脚本层回归）
python3 -m pytest scripts/tests/ -q
```

## 修复验证模式（CC_REGEN=1）

候选修复后，由外部 agent 按 `fixtures/*-input.json` 重跑候选，将新输出按
`<case_id>-baseline-output.md` 命名放入 `$CC_REGEN_DIR`，再：

```bash
CC_REGEN=1 CC_REGEN_DIR=/path/to/new-outputs \
  python3 -m pytest scripts/tests/regression/contract-calibration/ -q
```

此时 xfail 标记自动解除，测试直接验证「期望行为」是否达成：全绿=缺陷已修复，
红=仍有缺陷。修复确认后，应移除对应用例的 `@XFAIL_DEFECT` 装饰将其转为必过回归。

## 设计说明（路径 A）

T-401 的 fail 属 **agent 行为层**缺陷（是否暂停 / 自选自的 / 下正式结论），
候选当前无程序化分析入口，故采用半自动回归：跑候选 → 落 output → 机器比对。
不自动调用 LLM。RECEIPT-016 类 artifact 绑定由 `legal-skill-evaluation` 侧 gate 负责。
