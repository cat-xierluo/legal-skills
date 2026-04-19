#!/usr/bin/env python3
"""将结构化审查计划批量应用到 DOCX，并生成配套审查报告。"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from defusedxml import minidom

try:
    from .action_executor import apply_finding
    from .archive_service import (
        DEFAULT_ARCHIVE_DIR,
        archive_run,
        create_archive_run_dir,
    )
    from .ooxml.scripts.pack import pack_document
    from .plan_loader import (
        enrich_plan,
        get_findings,
        get_plan_meta,
        load_plan,
        normalize_edit_policy,
    )
    from .report_docx import write_review_report_docx
    from .reporting import render_review_report
    from .review_runtime import (
        ReviewTimeline,
        build_comment_author_display,
        resolve_review_context,
        resolve_reviewer_profile,
    )
    from .reviewer import ContractReviewer
except ImportError:
    from action_executor import apply_finding
    from archive_service import DEFAULT_ARCHIVE_DIR, archive_run, create_archive_run_dir
    from ooxml.scripts.pack import pack_document
    from plan_loader import (
        enrich_plan,
        get_findings,
        get_plan_meta,
        load_plan,
        normalize_edit_policy,
    )
    from report_docx import write_review_report_docx
    from reporting import render_review_report
    from review_runtime import (
        ReviewTimeline,
        build_comment_author_display,
        resolve_review_context,
        resolve_reviewer_profile,
    )
    from reviewer import ContractReviewer


def unpack_docx(input_docx: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    zipfile.ZipFile(input_docx).extractall(output_dir)

    xml_files = list(output_dir.rglob("*.xml")) + list(output_dir.rglob("*.rels"))
    for xml_file in xml_files:
        content = xml_file.read_text(encoding="utf-8")
        dom = minidom.parseString(content)
        xml_file.write_bytes(dom.toprettyxml(indent="  ", encoding="ascii"))


def build_execution_summary(
    applied_results: list[dict[str, Any]],
    source_docx: Path,
    plan_path: Path,
    plan_meta: dict[str, Any],
    reviewer_profile: dict[str, Any],
    review_context: dict[str, Any],
    output_docx: Path,
    report_path: Path,
    report_docx_path: Path,
) -> dict[str, Any]:
    applied = sum(1 for item in applied_results if item["status"] == "applied")
    failed = sum(1 for item in applied_results if item["status"] == "failed")
    skipped = sum(1 for item in applied_results if item["status"] == "skipped")
    report_only = sum(1 for item in applied_results if item["status"] == "report_only")

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_docx": str(source_docx),
        "plan_path": str(plan_path),
        "plan_meta": plan_meta,
        "reviewer_profile": reviewer_profile,
        "review_context": review_context,
        "edit_policy": plan_meta.get("edit_policy"),
        "output_docx": str(output_docx),
        "report_path": str(report_path),
        "report_docx_path": str(report_docx_path),
        "applied": applied,
        "failed": failed,
        "skipped": skipped,
        "report_only": report_only,
        "results": applied_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="批量执行审查计划（批注/修订），并生成审查报告"
    )
    parser.add_argument("--input", required=True, help="输入 DOCX 路径")
    parser.add_argument("--plan", required=True, help="审查计划 JSON 路径")
    parser.add_argument("--output", required=True, help="输出 DOCX 路径")
    parser.add_argument("--report", help="输出 Markdown 报告路径")
    parser.add_argument("--report-docx", help="输出 Word 报告路径")
    parser.add_argument("--log", help="输出执行日志 JSON 路径")
    parser.add_argument(
        "--archive-dir",
        default=str(DEFAULT_ARCHIVE_DIR),
        help="归档目录（默认: contract-copilot/archive）",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="关闭归档功能（默认开启）",
    )
    parser.add_argument(
        "--archive-no-input",
        action="store_true",
        help="归档时不复制原始输入 DOCX",
    )
    parser.add_argument("--author", help="批注/修订作者；未提供时优先读取本地配置")
    parser.add_argument("--initials", help="批注/修订作者缩写；未提供时按姓名推导")
    parser.add_argument("--organization", help="审查报告署名中的律所/公司名称")
    parser.add_argument("--department", help="审查报告署名中的部门名称（可选）")
    parser.add_argument("--client-name", help="客户名称；未提供时优先读取历史记录或从合同主体推断")
    parser.add_argument("--party-role", help="审查立场：甲方 / 乙方 / 中立 / 其他")
    parser.add_argument(
        "--review-intensity",
        help="审查口径：克制 / 常规 / 强势（影响风险识别与表达强度，不直接决定正文落痕）",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="跳过 DOCX 校验（默认会校验）",
    )
    parser.add_argument(
        "--no-enrich-plan",
        action="store_true",
        help="关闭审查计划策略字段自动补全（默认开启）",
    )
    parser.add_argument(
        "--edit-policy",
        choices=["revise-first", "balanced", "comment-first"],
        default=None,
        help="自动分流策略；与审查口径独立，默认 revise-first（能直接改就优先修订）",
    )
    args = parser.parse_args()

    input_docx = Path(args.input).expanduser().resolve()
    plan_path = Path(args.plan).expanduser().resolve()
    output_docx = Path(args.output).expanduser().resolve()
    archive_dir = Path(args.archive_dir).expanduser().resolve()

    if not input_docx.exists():
        raise FileNotFoundError(f"输入 DOCX 不存在: {input_docx}")
    if not plan_path.exists():
        raise FileNotFoundError(f"审查计划文件不存在: {plan_path}")

    plan = load_plan(plan_path)
    plan_meta = get_plan_meta(plan)
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    review_context = resolve_review_context(
        input_docx=input_docx,
        plan_meta=plan_meta,
        summary=summary,
        client_name=args.client_name,
        party_role=args.party_role,
        review_intensity=args.review_intensity,
        edit_policy=args.edit_policy,
    )
    edit_policy = normalize_edit_policy(
        args.edit_policy or plan_meta.get("edit_policy") or review_context.get("edit_policy"),
        default=str(review_context.get("edit_policy") or "revise-first"),
    )
    if not args.no_enrich_plan:
        plan = enrich_plan(plan, edit_policy=edit_policy)
    findings = get_findings(plan)
    plan_meta = get_plan_meta(plan)
    plan_meta["client_name"] = review_context["client_name"]
    plan_meta["party_role"] = review_context["party_role"]
    plan_meta["review_intensity"] = review_context["review_intensity"]
    plan_meta["edit_policy"] = edit_policy
    reviewer_profile = resolve_reviewer_profile(
        args.author,
        args.initials,
        args.organization,
        args.department,
    )
    author = str(reviewer_profile["author"])
    comment_author = build_comment_author_display(reviewer_profile)
    initials = str(reviewer_profile["initials"])
    plan_meta["reviewer"] = author
    plan_meta["reviewer_organization"] = str(
        reviewer_profile.get("organization") or ""
    )
    plan_meta["reviewer_department"] = str(
        reviewer_profile.get("department") or ""
    )
    plan["meta"] = plan_meta
    archive_path = None
    if not args.no_archive:
        archive_path = create_archive_run_dir(
            archive_dir=archive_dir,
            plan_meta=plan_meta,
            output_docx=output_docx,
        )
    report_path = (
        Path(args.report).expanduser().resolve()
        if args.report
        else (
            archive_path / f"{output_docx.stem}_审查报告.md"
            if archive_path
            else output_docx.with_name(f"{output_docx.stem}_审查报告.md")
        )
    )
    report_docx_path = (
        Path(args.report_docx).expanduser().resolve()
        if args.report_docx
        else output_docx.with_name(f"{output_docx.stem}_审查报告.docx")
    )
    log_path = (
        Path(args.log).expanduser().resolve()
        if args.log
        else (
            archive_path / f"{output_docx.stem}_执行日志.json"
            if archive_path
            else output_docx.with_name(f"{output_docx.stem}_执行日志.json")
        )
    )
    review_timeline = ReviewTimeline(
        gap_min_minutes=int(reviewer_profile["time_gap_min_minutes"]),
        gap_max_minutes=int(reviewer_profile["time_gap_max_minutes"]),
    )

    output_docx.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_docx_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    applied_results: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="contract-review-") as temp_dir:
        unpacked_path = Path(temp_dir) / "unpacked"
        unpack_docx(input_docx, unpacked_path)

        reviewer = ContractReviewer(
            unpacked_dir=unpacked_path,
            author=comment_author,
            initials=initials,
        )

        for index, finding in enumerate(findings, start=1):
            if not isinstance(finding, dict):
                applied_results.append(
                    {
                        "id": f"R{index:03d}",
                        "action": "none",
                        "status": "failed",
                        "message": "finding 不是对象",
                    }
                )
                continue

            finding = dict(finding)
            finding.setdefault("id", f"R{index:03d}")

            try:
                reviewer.set_operation_timestamp(review_timeline.start_finding())
                result = apply_finding(reviewer, finding, edit_policy=edit_policy)
            except Exception as exc:
                result = {
                    "id": finding.get("id"),
                    "action": finding.get("action"),
                    "status": "failed",
                    "message": str(exc),
                }
            finally:
                reviewer.clear_operation_timestamp()
                review_timeline.complete_finding()
            applied_results.append(result)

        reviewer.save(validate=not args.no_validate)
        packed = pack_document(unpacked_path, output_docx, validate=not args.no_validate)
        if not packed:
            raise ValueError("DOCX 打包校验失败，请检查计划中的 XML 变更")

    execution_summary = build_execution_summary(
        applied_results=applied_results,
        source_docx=input_docx,
        plan_path=plan_path,
        plan_meta=plan_meta,
        reviewer_profile=reviewer_profile,
        review_context=review_context,
        output_docx=output_docx,
        report_path=report_path,
        report_docx_path=report_docx_path,
    )

    report_content = render_review_report(plan=plan, execution=execution_summary)
    report_path.write_text(report_content, encoding="utf-8")
    write_review_report_docx(
        markdown_content=report_content,
        output_path=report_docx_path,
        title=(
            f"{plan_meta.get('contract_name')}审查意见书"
            if plan_meta.get("contract_name")
            else "合同审查意见书"
        ),
        author=author,
        generated_at=execution_summary["generated_at"][:16],
        validate=not args.no_validate,
    )
    log_path.write_text(
        json.dumps(execution_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if archive_path:
        archive_path = archive_run(
            archive_dir=archive_dir,
            input_docx=input_docx,
            plan_path=plan_path,
            output_docx=output_docx,
            report_path=report_path,
            report_docx_path=report_docx_path,
            log_path=log_path,
            execution_summary=execution_summary,
            include_input=not args.archive_no_input,
            run_dir=archive_path,
        )

    print(f"输出 DOCX: {output_docx}")
    print(f"输出报告 DOCX: {report_docx_path}")
    if args.report or args.no_archive:
        print(f"输出报告: {report_path}")
    if args.log or args.no_archive:
        print(f"执行日志: {log_path}")
    if archive_path:
        print(f"归档目录: {archive_path}")
    print(
        "审查上下文: "
        f"客户={review_context['client_name']}，"
        f"立场={review_context['party_role']}，"
        f"口径={review_context['review_intensity']}"
    )
    print(
        "执行统计: "
        f"成功={execution_summary['applied']}，"
        f"失败={execution_summary['failed']}，"
        f"跳过={execution_summary['skipped']}，"
        f"仅意见书={execution_summary['report_only']}"
    )
    if execution_summary["failed"] > 0:
        if archive_path:
            print("存在失败项，请检查归档目录中的执行日志与审查报告。", file=sys.stderr)
        else:
            print("存在失败项，请检查执行日志与审查报告。", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
