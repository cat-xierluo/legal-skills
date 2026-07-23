#!/usr/bin/env python3
"""book-gate：把源稿、渲染、独立视觉审查和最终 DOCX 串成 fail-closed gate。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import argparse
import json
import sys

try:
    import yaml
except ImportError:
    print("❌ book-gate 缺少 PyYAML。请运行：python3 -m pip install PyYAML", file=sys.stderr)
    raise SystemExit(2)

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from gate_models import (  # noqa: E402
    CheckerOutput,
    GateContext,
    canonical_hash,
    sha256_file,
)
import docx_checker  # noqa: E402
import markdown_checker  # noqa: E402
import svg_checker  # noqa: E402
import visual_checker  # noqa: E402


GATE_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"
ALLOWED_REQUIREMENT_STAGES = {"source", "render", "visual", "docx"}
STAGE_PLAN = {
    "source": ("source",),
    "render": ("source", "render"),
    "visual": ("source", "render", "visual"),
    "docx": ("source", "docx"),
    "prepare": ("source", "render", "docx"),
    # release 先生成 DOCX 分页 PNG，再由 visual 阶段一起核 SVG 与最终页面。
    "release": ("source", "render", "docx", "visual"),
    "all": ("source", "render", "docx", "visual"),
}
NEXT_STATE = {
    "source": "SOURCE_VERIFIED",
    "render": "RENDERED",
    "visual": "INDEPENDENT_VERIFIED",
    "docx": "DOCX_VERIFIED",
    "prepare": "REVIEW_PACKET_READY",
    "release": "RELEASE_VERIFIED",
    "all": "RELEASE_VERIFIED",
}

Verifier = Callable[[GateContext, dict[str, Any]], CheckerOutput]
VERIFIERS: dict[str, Verifier] = {
    "markdown.no_diagram_dsl": markdown_checker.no_diagram_dsl,
    "markdown.no_ascii_cjk_quote": markdown_checker.no_ascii_cjk_quote,
    "markdown.figure_separation": markdown_checker.figure_separation,
    "markdown.image_targets_exist": markdown_checker.image_targets_exist,
    "markdown.footnote_references_resolve": markdown_checker.footnote_references_resolve,
    "svg.source_policy": svg_checker.source_policy,
    "svg.marker_integrity": svg_checker.marker_integrity,
    "svg.render_and_measure": svg_checker.render_and_measure,
    "visual.attestation_complete": visual_checker.attestation_complete,
    "docx.package_and_content": docx_checker.package_and_content,
    "docx.image_coverage": docx_checker.image_coverage,
    "docx.layout_and_fonts": docx_checker.layout_and_fonts,
    "docx.render_pages": docx_checker.render_pages,
}


class SpecError(ValueError):
    pass


def load_spec(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SpecError(f"requirements 文件不存在：{path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SpecError(f"requirements YAML 无法解析：{exc}") from exc
    if not isinstance(data, dict):
        raise SpecError("requirements 根节点必须是 mapping")
    validate_spec(data)
    return data


def validate_spec(spec: dict[str, Any]) -> None:
    if str(spec.get("schema_version")) != SCHEMA_VERSION:
        raise SpecError(f"schema_version 必须是 {SCHEMA_VERSION}")
    hash_inputs = spec.get("hash_inputs")
    if not isinstance(hash_inputs, list) or not hash_inputs:
        raise SpecError("hash_inputs 必须是非空列表")
    requirements = spec.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        raise SpecError("requirements 必须是非空列表；空规则集不得放行")
    ids: set[str] = set()
    stages: set[str] = set()
    for index, requirement in enumerate(requirements, 1):
        if not isinstance(requirement, dict):
            raise SpecError(f"第 {index} 条 requirement 不是 mapping")
        rid = str(requirement.get("id", "")).strip()
        if not rid or rid in ids:
            raise SpecError(f"requirement id 缺失或重复：{rid or index}")
        ids.add(rid)
        stage = str(requirement.get("stage", ""))
        if stage not in ALLOWED_REQUIREMENT_STAGES:
            raise SpecError(f"{rid} 的 stage 非法：{stage}")
        stages.add(stage)
        scope = requirement.get("scope")
        if not isinstance(scope, (str, list)) or not scope:
            raise SpecError(f"{rid} 缺少 scope")
        blocking = requirement.get("blocking")
        if not isinstance(blocking, bool):
            raise SpecError(f"{rid} 的 blocking 必须是 YAML bool")
        threshold = requirement.get("threshold", 0)
        if not isinstance(threshold, int) or threshold < 0:
            raise SpecError(f"{rid} 的 threshold 必须是非负整数")
        verifier = str(requirement.get("verifier", "")).strip()
        needs_human = requirement.get("needs_human_review", False)
        if not isinstance(needs_human, bool):
            raise SpecError(f"{rid} 的 needs_human_review 必须是 YAML bool")
        if not verifier and not needs_human:
            raise SpecError(f"{rid} 既无 verifier，也未显式 needs_human_review")
        if verifier and verifier not in VERIFIERS:
            raise SpecError(f"{rid} 引用了未知 verifier：{verifier}")
    required_stages = set(spec.get("release", {}).get("required_stages", ALLOWED_REQUIREMENT_STAGES))
    unknown = required_stages - ALLOWED_REQUIREMENT_STAGES
    if unknown:
        raise SpecError(f"release.required_stages 含未知阶段：{sorted(unknown)}")
    missing = required_stages - stages
    if missing:
        raise SpecError(f"release 必需阶段没有任何 requirement：{sorted(missing)}")


def build_input_manifest(project_root: Path, spec: dict[str, Any]) -> tuple[list[dict], str]:
    files: set[Path] = set()
    unmatched: list[str] = []
    for pattern in spec["hash_inputs"]:
        if not isinstance(pattern, str) or Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise SpecError(f"hash_inputs 只能使用项目内相对 glob：{pattern}")
        matches = [item.resolve() for item in project_root.glob(pattern) if item.is_file()]
        if not matches:
            unmatched.append(pattern)
        files.update(matches)
    if not files:
        raise SpecError("hash_inputs 没有匹配任何文件；空项目不得放行")
    if unmatched and spec.get("require_each_hash_input", True):
        raise SpecError(f"以下 hash_inputs 没有匹配文件：{unmatched}")
    manifest = [
        {
            "path": path.relative_to(project_root.resolve()).as_posix(),
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
        }
        for path in sorted(files, key=lambda item: item.relative_to(project_root.resolve()).as_posix())
    ]
    return manifest, canonical_hash(manifest)


def run_gate(
    project_root: Path,
    requirements_path: Path,
    stage: str,
    output_dir: Path,
    docx_path: Path | None,
    rendered_pdf_path: Path | None,
    visual_review_path: Path | None,
    producer_id: str,
) -> tuple[int, dict[str, Any]]:
    spec = load_spec(requirements_path)
    manifest, candidate_sha = build_input_manifest(project_root, spec)
    selected = STAGE_PLAN[stage]
    requirements = [item for item in spec["requirements"] if item["stage"] in selected]
    requirements.sort(key=lambda item: selected.index(item["stage"]))
    present_stages = {item["stage"] for item in requirements}
    missing_selected = set(selected) - present_stages
    if missing_selected:
        raise SpecError(f"所选 gate 阶段没有 requirement：{sorted(missing_selected)}")
    output_dir.mkdir(parents=True, exist_ok=True)
    ctx = GateContext(
        project_root=project_root,
        requirements_path=requirements_path,
        output_dir=output_dir,
        candidate_sha=candidate_sha,
        input_manifest=manifest,
        selected_stage=stage,
        config=spec,
        docx_path=docx_path,
        rendered_pdf_path=rendered_pdf_path,
        visual_review_path=visual_review_path,
        producer_id=producer_id,
    )
    results: list[dict[str, Any]] = []
    blocked = False
    stage_metrics: dict[str, Any] = {}
    artifact_index: dict[str, dict] = {}

    for requirement in requirements:
        rid = requirement["id"]
        blocking = requirement["blocking"]
        scope_count = len(ctx.scope_files(requirement))
        if scope_count == 0 and not requirement.get("allow_empty_scope", False):
            results.append({
                "req_id": rid,
                "stage": requirement["stage"],
                "blocking": blocking,
                "verdict": "ERROR",
                "error": "scope 没有匹配任何文件",
                "scope": requirement["scope"],
            })
            blocked = True
            continue
        if requirement.get("needs_human_review", False):
            results.append({
                "req_id": rid,
                "stage": requirement["stage"],
                "blocking": blocking,
                "verdict": "NEEDS_HUMAN_REVIEW",
                "note": requirement.get("note", "无自动 verifier，证据不足"),
            })
            blocked = True
            continue
        try:
            output = VERIFIERS[requirement["verifier"]](ctx, requirement)
            if not isinstance(output, CheckerOutput):
                raise TypeError("verifier 必须返回 CheckerOutput")
            count = len(output.findings)
            threshold = requirement.get("threshold", 0)
            if count > threshold:
                verdict = "FAIL" if blocking else "PARTIAL"
                if blocking:
                    blocked = True
            else:
                verdict = "PASS"
            result = {
                "req_id": rid,
                "stage": requirement["stage"],
                "blocking": blocking,
                "verdict": verdict,
                "finding_count": count,
                "threshold": threshold,
                "scope_count": scope_count,
                "findings": [finding.to_dict() for finding in output.findings],
                "metrics": output.metrics,
            }
            results.append(result)
            stage_metrics[rid] = output.metrics
            for artifact in output.artifacts:
                if artifact.get("artifact_id"):
                    artifact_index[artifact["artifact_id"]] = artifact
        except Exception as exc:
            results.append({
                "req_id": rid,
                "stage": requirement["stage"],
                "blocking": blocking,
                "verdict": "ERROR",
                "error": f"{type(exc).__name__}: {exc}",
            })
            blocked = True

    if stage == "prepare" and not blocked:
        packet = visual_checker.prepare_review_template(ctx)
        packet_blocked = bool(packet.findings)
        results.append({
            "req_id": "REVIEW-PACKET",
            "stage": "prepare",
            "blocking": True,
            "verdict": "FAIL" if packet_blocked else "PASS",
            "finding_count": len(packet.findings),
            "threshold": 0,
            "findings": [finding.to_dict() for finding in packet.findings],
            "metrics": packet.metrics,
        })
        stage_metrics["REVIEW-PACKET"] = packet.metrics
        blocked = blocked or packet_blocked

    evidence = {
        "schema_version": SCHEMA_VERSION,
        "gate_version": GATE_VERSION,
        "candidate_sha": candidate_sha,
        "requirements_sha256": sha256_file(requirements_path),
        "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "requested_stage": stage,
        "selected_stages": list(selected),
        "next_state_if_pass": NEXT_STATE[stage],
        "overall": "BLOCKED" if blocked else NEXT_STATE[stage],
        "hash_inputs": spec["hash_inputs"],
        "input_manifest": manifest,
        "results": results,
        "stage_metrics": stage_metrics,
        "artifact_count": len(artifact_index),
    }
    evidence_path = output_dir / f"evidence-{candidate_sha[:12]}-{stage}.json"
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence["evidence_file"] = evidence_path.name
    return (1 if blocked else 0), evidence


def status(evidence_path: Path, project_root: Path, requirements_path: Path | None) -> int:
    files = [evidence_path] if evidence_path.is_file() else sorted(evidence_path.glob("evidence-*.json"))
    if not files:
        print("没有 evidence JSON", file=sys.stderr)
        return 2
    stale_any = False
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        manifest = []
        for item in data.get("input_manifest", []):
            candidate = project_root / item["path"]
            if not candidate.is_file():
                manifest.append({"path": item["path"], "sha256": "MISSING", "size": 0})
            else:
                manifest.append({
                    "path": item["path"],
                    "sha256": sha256_file(candidate),
                    "size": candidate.stat().st_size,
                })
        current_sha = canonical_hash(manifest)
        stale = current_sha != data.get("candidate_sha")
        if requirements_path is not None:
            stale = stale or sha256_file(requirements_path) != data.get("requirements_sha256")
        stale_any = stale_any or stale
        label = "STALE" if stale else data.get("overall", "UNKNOWN")
        print(
            f"{path.name}: {label} candidate={data.get('candidate_sha', '')[:12]} "
            f"stage={data.get('requested_stage')}"
        )
    return 1 if stale_any else 0


def _resolve_project_root(raw: Path) -> Path:
    resolved = raw.expanduser().resolve()
    if resolved.name == "manuscript":
        return resolved.parent
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(prog="book-gate", description="书籍最终成品 acceptance gate")
    sub = parser.add_subparsers(dest="command", required=True)
    verify_parser = sub.add_parser("verify", help="运行 source/render/visual/docx/release gate")
    verify_parser.add_argument("project_root", type=Path)
    verify_parser.add_argument("--requirements", "-r", type=Path)
    verify_parser.add_argument("--stage", choices=tuple(STAGE_PLAN), default="source")
    verify_parser.add_argument("--out", type=Path)
    verify_parser.add_argument("--docx", type=Path)
    verify_parser.add_argument("--pdf", type=Path, help="由 Microsoft Word/WPS 导出的作者所见 PDF；优先于 LibreOffice fallback")
    verify_parser.add_argument("--visual-review", type=Path)
    verify_parser.add_argument("--producer-id", default="")
    status_parser = sub.add_parser("status", help="重算输入 hash，识别陈旧证据")
    status_parser.add_argument("evidence", type=Path)
    status_parser.add_argument("--project-root", required=True, type=Path)
    status_parser.add_argument("--requirements", type=Path)
    args = parser.parse_args()

    if args.command == "status":
        return status(
            args.evidence.expanduser().resolve(),
            _resolve_project_root(args.project_root),
            args.requirements.expanduser().resolve() if args.requirements else None,
        )

    project_root = _resolve_project_root(args.project_root)
    requirements_path = (
        args.requirements.expanduser().resolve()
        if args.requirements
        else (SCRIPT_DIR.parent / "requirements.yaml").resolve()
    )
    output_dir = (
        args.out.expanduser().resolve()
        if args.out
        else project_root / ".book-gate-evidence"
    )
    try:
        code, evidence = run_gate(
            project_root,
            requirements_path,
            args.stage,
            output_dir,
            args.docx.expanduser().resolve() if args.docx else None,
            args.pdf.expanduser().resolve() if args.pdf else None,
            args.visual_review.expanduser().resolve() if args.visual_review else None,
            args.producer_id.strip(),
        )
    except SpecError as exc:
        print(f"❌ requirements/gate 配置错误：{exc}", file=sys.stderr)
        return 2
    print(
        f"candidate={evidence['candidate_sha'][:12]} overall={evidence['overall']} "
        f"stage={evidence['requested_stage']} evidence={evidence['evidence_file']}"
    )
    for result in evidence["results"]:
        if result["verdict"] != "PASS":
            detail = result.get("finding_count", result.get("error", result.get("note", "")))
            print(f"  [{result['verdict']}] {result['req_id']}: {detail}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
