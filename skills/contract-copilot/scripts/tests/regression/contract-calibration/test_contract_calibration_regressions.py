"""contract-copilot T-401 回归测试集（路径 A：夹具 + 机器判定检查器）。

固化 legal-skill-evaluation 在 v0.8.6 收尾时识别出的 7 例 executed-fail 行为层缺陷：
候选在 intake（立场/目标缺失未暂停）、条款边界（信息补齐前给正式可签结论）、
report 完整性（最终报告字段塌缩 / 生产器自报成功关闭回归）三类场景下的真实行为。

来源：legal-skill-evaluation/evals/contract-calibration-260730（capability-suite.json
execution_status=executed-fail 且 assertion observed=fail 的 7 例）。本目录的 fixtures/
与 baseline-outputs/ 是其可复现快照，sha256 见各 *-input.json。

运行方式：
- 默认：读取 baseline-outputs/ 作为「当前候选行为基线」并按期望行为断言。这 7 例
  当前候选（sha256 f3fa86a8…）仍存在缺陷，故用 @pytest.mark.xfail 标注（strict=False，
  即预期失败；候选修复后移除 xfail 即转为必过）。
- CC_REGEN=1：从 $CC_REGEN_DIR 读取外部 agent 重跑候选后的新输出（同名 *-baseline-output.md），
  去掉 xfail 语义，直接验证修复是否达成（达成则全绿，未达成则报 fail）。

注意：本测试不自动调用 LLM 重跑候选（候选无程序化分析入口），属半自动回归：
跑候选 → 落 output → 比对。RECEIPT-016 类 artifact 绑定由 legal-skill-evaluation 侧负责。
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parents[4]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

REGRESSION_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = REGRESSION_DIR / "fixtures"
BASELINE_DIR = REGRESSION_DIR / "baseline-outputs"

REGEN = os.environ.get("CC_REGEN") == "1"
REGEN_DIR = Path(os.environ.get("CC_REGEN_DIR", str(BASELINE_DIR))).resolve()

# 当前候选（sha256 f3fa86a8…）对这 7 例仍存在行为层缺陷，作为已知回归基线。
# 默认用 xfail 标注（预期失败，strict=False）；候选修复后移除 xfail 即转为必过。
# CC_REGEN=1 时视为修复验证模式，去掉 xfail 语义（直接必过/必败）。
XFAIL_DEFECT = pytest.mark.xfail(
    not REGEN, strict=False, reason="T-401 已知行为缺陷，待 contract-copilot 候选修复"
)

# 正式三档结论词：条款边界类断言要求候选在信息补齐前不得出具这些。
FORMAL_CONCLUSION_MARKERS = ("可签", "有条件可签", "不建议签", "建议签", "不予签署")
# 暂停 / 待确认标记：intake 与条款边界类要求候选在缺口前显式暂停或请求确认。
PAUSE_MARKERS = ("暂停", "待确认", "待补充", "请求确认", "请确认", "先确认", "未确认")


def load_fixtures() -> list[dict]:
    fixtures = []
    for path in sorted(FIXTURES_DIR.glob("*-input.json")):
        fixtures.append(json.loads(path.read_text(encoding="utf-8")))
    return fixtures


def read_output(case_id: str) -> str:
    """优先从 REGEN_DIR 读取重跑输出，否则用 baseline。"""
    candidate = REGEN_DIR / f"{case_id}-baseline-output.md"
    if REGEN and candidate.exists():
        return candidate.read_text(encoding="utf-8")
    baseline = BASELINE_DIR / f"{case_id}-baseline-output.md"
    if baseline.exists():
        return baseline.read_text(encoding="utf-8")
    return ""


def expected_fail_for(case: dict) -> bool:
    """当前候选（f3fa86a8…）对该 case 仍存在缺陷，默认期望 xfail。"""
    return True


class ContractCalibrationRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixtures = load_fixtures()
        self.assertGreaterEqual(len(self.fixtures), 7, "应为 7 例 executed-fail 夹具")

    # ---- intake 类：立场 / 目标缺失须暂停并请求确认，不得自行推进 ----

    @XFAIL_DEFECT
    def test_role_missing_does_not_self_resolve_empty_role(self) -> None:
        case = next(c for c in self.fixtures if c["case_id"] == "CONTRACT-MICRO-ROLE-MISSING")
        ctx = case["provided_context"]
        self.assertIsNone(ctx.get("party_role"), "夹具应模拟立场缺失")
        output = read_output(case["case_id"])
        # 期望行为：候选应请求确认代表哪一方，而非把空立场解析为「其他」继续。
        # 当前 baseline 中候选将立场解析为「其他」并继续 → 缺陷未修复时为 xfail。
        self.assertNotIn("其他", output.replace("其他签约方", ""),
                          "候选不应将空立场默认解析为「其他」后继续审查")
        self.assertTrue(
            any(m in output for m in ("请确认", "请求确认", "代表哪一方", "确认立场")),
            "立场缺失时候选应显式请求确认代表哪一方",
        )

    @XFAIL_DEFECT
    def test_objective_missing_does_not_self_select_delivery_strength(self) -> None:
        case = next(c for c in self.fixtures if c["case_id"] == "CONTRACT-MICRO-OBJECTIVE-MISSING")
        ctx = case["provided_context"]
        self.assertIsNone(ctx.get("review_objective"), "夹具应模拟审查目标缺失")
        output = read_output(case["case_id"])
        # 期望行为：目标缺失时暂停、不自行选择交付强度、不出正式结论。
        # 当前候选缺陷自述：第 9 行「审查目的不在阻塞清单内」、第 13 行
        # 「未因审查目的缺失而暂停整轮审查」、第 14 行「按…默认目的推进」。
        self.assertFalse(
            any(m in output for m in ("不建议签", "可签", "有条件可签")),
            "审查目标缺失时候选不应出具正式三档结论",
        )
        self.assertNotIn(
            "未因审查目的缺失而暂停", output,
            "审查目标缺失时候选不应主动决定不暂停并继续推进",
        )
        self.assertNotIn(
            "默认审查目的推进", output,
            "审查目标缺失时候选不应自行选择默认交付目的推进",
        )

    # ---- 条款边界类：信息补齐前暂停，不出正式可签结论 ----

    def _assert_no_formal_conclusion_before_pause(self, case_id: str) -> None:
        case = next(c for c in self.fixtures if c["case_id"] == case_id)
        output = read_output(case["case_id"])
        self.assertFalse(
            any(m in output for m in FORMAL_CONCLUSION_MARKERS),
            f"{case_id}：信息补齐前候选不应出具正式可签结论",
        )
        self.assertTrue(
            any(m in output for m in PAUSE_MARKERS),
            f"{case_id}：候选应在信息补齐前显式暂停或标注待确认",
        )

    @XFAIL_DEFECT
    def test_acceptance_payment_no_formal_conclusion_before_pause(self) -> None:
        self._assert_no_formal_conclusion_before_pause("CONTRACT-MICRO-ACCEPTANCE-PAYMENT")

    @XFAIL_DEFECT
    def test_change_fee_no_formal_conclusion_before_pause(self) -> None:
        self._assert_no_formal_conclusion_before_pause("CONTRACT-MICRO-CHANGE-FEE")

    @XFAIL_DEFECT
    def test_penalty_stacking_no_formal_conclusion_before_pause(self) -> None:
        self._assert_no_formal_conclusion_before_pause("CONTRACT-MICRO-PENALTY-STACKING")

    # ---- report 完整性类：最终报告字段非空 ----

    @XFAIL_DEFECT
    def test_report_field_not_collapsed(self) -> None:
        case = next(c for c in self.fixtures if c["case_id"] == "CONTRACT-MICRO-REPORT-FIELD-COLLAPSE")
        output = read_output(case["case_id"])
        # 期望行为：最终报告不得批量出现待补占位与空法律依据。
        placeholder_count = output.count("待补") + output.count("未提及/待补充")
        self.assertLess(
            placeholder_count, 10,
            "最终报告待补占位不应超过阈值（当前候选塌缩出 14 个待补占位）",
        )
        self.assertNotIn("法律依据：\n", output, "法律依据字段不得为空")

    @XFAIL_DEFECT
    def test_producer_self_success_does_not_close_regression(self) -> None:
        case = next(c for c in self.fixtures if c["case_id"] == "CONTRACT-MICRO-PRODUCER-SELF-SUCCESS")
        output = read_output(case["case_id"])
        placeholder_count = output.count("待补") + output.count("未提及/待补充")
        self.assertLess(
            placeholder_count, 10,
            "生产器自报成功时，独立 checker 应非零退出并保持回归开放（当前候选塌缩）",
        )


if __name__ == "__main__":
    unittest.main()
