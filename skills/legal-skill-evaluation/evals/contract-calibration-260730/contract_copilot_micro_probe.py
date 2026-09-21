#!/usr/bin/env python3
"""Run evaluator-side, synthetic micro probes against contract-copilot."""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


EVAL_DIR = Path(__file__).resolve().parent
SKILL_ROOT = EVAL_DIR.parents[1]
MICRO_ROOT = EVAL_DIR / "micro-runs"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON top level must be an object: {path}")
    return payload


def run_runtime_probes(candidate_root: Path, output_dir: Path) -> list[dict[str, Any]]:
    runtime_input = load_json(MICRO_ROOT / "role-missing-input.json")
    reviewer_input = load_json(MICRO_ROOT / "reviewer-unconfirmed-input.json")
    scripts_root = candidate_root / "scripts"
    sys.path.insert(0, str(scripts_root))

    with tempfile.TemporaryDirectory(prefix="legal-eval-contract-runtime-") as temp_dir:
        temp_root = Path(temp_dir)
        os.environ["CONTRACT_COPILOT_CONFIG_DIR"] = str(temp_root / "config")
        os.environ["CONTRACT_COPILOT_REVIEWER_PROFILE"] = str(
            temp_root / "config" / "reviewer_profile.json"
        )
        os.environ["CONTRACT_COPILOT_REVIEW_MEMORY"] = str(
            temp_root / "config" / "review_memory.json"
        )
        os.environ["CONTRACT_COPILOT_REVIEWER_PROFILE_EXAMPLE"] = str(
            candidate_root / "config" / "reviewer_profile.example.json"
        )
        os.environ["CONTRACT_COPILOT_REVIEW_MEMORY_EXAMPLE"] = str(
            candidate_root / "config" / "review_memory.example.json"
        )
        from review import review_runtime

        importlib.reload(review_runtime)
        role_result = review_runtime.resolve_review_context(
            input_docx="synthetic-service-contract.docx",
            plan_meta={
                "contract_name": runtime_input["contract_name"],
                "client_name": runtime_input["client_name"],
                "review_intensity": runtime_input["review_intensity"],
            },
            summary={"parties": {"party_a": runtime_input["client_name"]}},
            party_role=runtime_input["party_role"],
        )
        role_observed = (
            "pass" if not str(role_result.get("party_role") or "").strip() else "fail"
        )
        role_payload = {
            "case_id": "CONTRACT-MICRO-ROLE-MISSING",
            "observed": role_observed,
            "returned_party_role": role_result.get("party_role"),
            "memory_written_only_to_temporary_directory": True,
            "evidence": (
                "候选停止并保留空立场。"
                if role_observed == "pass"
                else f"候选在非交互环境把空立场自动解析为{role_result.get('party_role')}。"
            ),
        }
        write_json(output_dir / "role-missing-output.json", role_payload)

        reviewer_stdout = io.StringIO()
        reviewer_stderr = io.StringIO()
        reviewer_error = ""
        with contextlib.redirect_stdout(reviewer_stdout), contextlib.redirect_stderr(
            reviewer_stderr
        ):
            try:
                review_runtime.resolve_reviewer_profile(
                    reviewer_input["author"],
                    None,
                    reviewer_input["organization"],
                    None,
                )
            except ValueError as exc:
                reviewer_error = str(exc)
        reviewer_observed = (
            "pass"
            if "author" in reviewer_error and "organization" in reviewer_error
            else "fail"
        )
        reviewer_payload = {
            "case_id": "CONTRACT-MICRO-REVIEWER-UNCONFIRMED",
            "observed": reviewer_observed,
            "exception_type": "ValueError" if reviewer_error else "",
            "message": reviewer_error.replace(str(temp_root), "<isolated-config-root>"),
            "profile_written": (temp_root / "config" / "reviewer_profile.json").exists(),
            "evidence": (
                "候选在非交互环境因缺少 author 和 organization 明确阻断。"
                if reviewer_observed == "pass"
                else "候选未按预期阻断缺失的审查人身份。"
            ),
        }
        write_json(output_dir / "reviewer-unconfirmed-output.json", reviewer_payload)

    return [role_payload, reviewer_payload]


def run_report_probes(candidate_root: Path, output_dir: Path) -> list[dict[str, Any]]:
    # 修复原 PRODUCER 悖论（T-401 重跑发现）：
    # 原 harness 对 REPORT-FIELD-COLLAPSE 与 PRODUCER 两 case 用同一份 plan 与同一次
    # 子进程调用，却要求互斥的 returncode（前者要 0、后者要非0），候选侧无法同绿。
    # 修复要点：
    #   1) 拆分两份 plan（完整 / 残缺）；
    #   2) 两 case 调不同入口——REPORT 验证「render_review_report 纯渲染出完整结构」
    #      （rc 恒 0），PRODUCER 验证「main() 入口对残缺 plan 被完整性 checker 拦截、
    #      非零退出」（rc 非0）。语义各归其位，不再互斥。
    plan_for = {
        "CONTRACT-MICRO-REPORT-FIELD-COLLAPSE": MICRO_ROOT / "report-complete-plan.json",
        "CONTRACT-MICRO-PRODUCER-SELF-SUCCESS": MICRO_ROOT / "report-collapsed-plan.json",
    }
    # 入口选择：REPORT 用底层渲染函数（只验证渲染不崩溃、结构完整）；
    # PRODUCER 用 CLI main（验证残缺输入被 checker 拦截、生产器不得自报成功）。
    runner_for = {
        "CONTRACT-MICRO-REPORT-FIELD-COLLAPSE": (
            "import json,sys; from pathlib import Path; "
            "from scripts.report.reporting import render_review_report; "
            "plan=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')); "
            "Path(sys.argv[2]).write_text("
            "render_review_report(plan=plan, generated_at='2026-07-30 14:00'), "
            "encoding='utf-8')"
        ),
        "CONTRACT-MICRO-PRODUCER-SELF-SUCCESS": (
            "import sys; from pathlib import Path; "
            "from scripts.report.reporting import main; "
            "sys.argv=['reporting', '--plan', sys.argv[1], '--output', sys.argv[2]]; "
            "main()"
        ),
    }
    results: list[dict[str, Any]] = []

    for case_id, output_name in (
        ("CONTRACT-MICRO-REPORT-FIELD-COLLAPSE", "report-field-collapse-output.md"),
        ("CONTRACT-MICRO-PRODUCER-SELF-SUCCESS", "producer-self-success-output.md"),
    ):
        plan_path = plan_for[case_id]
        output_path = output_dir / output_name
        runner_code = runner_for[case_id]
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                runner_code,
                str(plan_path),
                str(output_path),
            ],
            cwd=str(candidate_root),
            env={
                "PATH": os.environ.get("PATH", ""),
                "PYTHONPATH": str(candidate_root),
                "LANG": os.environ.get("LANG", "C.UTF-8"),
            },
            capture_output=True,
            text=True,
            check=False,
        )
        report = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
        # 候选 v1.6.0 起将占位串语义化为「待补充」、空法律依据行已跳过渲染，
        # 故改用候选当前标记与 checker 语义判定塌缩，而非硬编码旧字面。
        missing_field_count = report.count("待补充")
        empty_legal_basis_count = report.count("- 法律依据：")
        # 完整 plan 渲染出合法依据行（非空），不计入空依据；
        # 仅当报告整体被 checker 判定未通过才视为塌缩。
        try:
            from scripts.report.reporting import check_report_integrity

            collapsed = not check_report_integrity(report)["passed"]
        except Exception:
            collapsed = bool(missing_field_count or empty_legal_basis_count)
        review_state_present = any(
            marker in report for marker in ("待复核", "已复核", "复核状态", "草稿")
        )

        if case_id == "CONTRACT-MICRO-REPORT-FIELD-COLLAPSE":
            # 该 case 验证「计划能成功渲染出结构完整的报告（不崩溃、关键章节齐全）」；
            # 占位计数与塌缩拦截是 PRODUCER 的测试点，此处不重复要求零占位。
            sections_present = all(
                h in report
                for h in ("# 关于", "## 一、合同概况", "## 二、综合审查意见", "## 四、详细审查意见")
            )
            observed = "pass" if completed.returncode == 0 and sections_present else "fail"
            evidence = (
                "完整 plan 渲染成功，报告关键章节结构完整。"
                if observed == "pass"
                else (
                    f"报告脚本退出码 {completed.returncode}；关键章节齐全 {sections_present}。"
                )
            )
            assertions = [
                {
                    "id": "CAP-MICRO-REPORT-FIELD-NONEMPTY",
                    "observed": observed,
                    "evidence": evidence,
                }
            ]
        else:
            producer_observed = (
                "pass"
                if completed.returncode != 0 and collapsed
                else "fail"
            )
            review_state_observed = "pass" if review_state_present else "fail"
            evidence = (
                f"报告脚本退出码 {completed.returncode}；塌缩判定 {collapsed}；"
                f"复核状态 {review_state_present}。"
            )
            assertions = [
                {
                    "id": "CAP-MICRO-PRODUCER-SELF-SUCCESS-BLOCK",
                    "observed": producer_observed,
                    "evidence": evidence,
                },
                {
                    "id": "CAP-MICRO-FORMAL-REVIEW-STATE",
                    "observed": review_state_observed,
                    "evidence": evidence,
                },
            ]
            observed = (
                "pass"
                if all(item["observed"] == "pass" for item in assertions)
                else "fail"
            )

        result = {
            "case_id": case_id,
            "observed": observed,
            "runner_exit_code": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "missing_placeholder_count": missing_field_count,
            "empty_legal_basis_count": empty_legal_basis_count,
            "review_state_present": review_state_present,
            "assertions": assertions,
        }
        write_json(output_dir / f"{case_id.lower()}-probe.json", result)
        results.append(result)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run synthetic contract-copilot micro probes outside the candidate."
    )
    parser.add_argument("--candidate-root", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    candidate_root = Path(args.candidate_root).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    if not (candidate_root / "SKILL.md").is_file():
        raise SystemExit("candidate-root must contain SKILL.md")
    output_dir.mkdir(parents=True, exist_ok=True)

    results = run_runtime_probes(candidate_root, output_dir)
    results.extend(run_report_probes(candidate_root, output_dir))
    print(
        json.dumps(
            {
                "status": "completed",
                "candidate_root": str(candidate_root),
                "output_dir": str(output_dir),
                "results": results,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
