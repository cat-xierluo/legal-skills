#!/usr/bin/env python3
"""验证独立视觉 reviewer 的逐图哈希覆盖与逐维度结论。"""

from __future__ import annotations

from pathlib import Path
import json

from gate_models import CheckerOutput, Finding, GateContext, canonical_hash, sha256_file


def attestation_complete(ctx: GateContext, requirement: dict) -> CheckerOutput:
    rid = requirement["id"]
    findings: list[Finding] = []
    manifest, manifest_hash, manifest_finding = _combined_manifest(ctx, rid)
    if manifest_finding:
        return CheckerOutput(findings=[manifest_finding])
    expected = {item["artifact_id"]: item for item in manifest.get("artifacts", [])}
    dimensions = ctx.config.get("visual_review", {}).get("dimensions", [])
    dimension_map = {item["id"]: item for item in dimensions}
    _write_review_template(ctx, manifest_hash, expected, dimensions)
    if ctx.visual_review_path is None:
        return CheckerOutput(findings=[Finding(
            rid, "", 0, "hard", "release/visual 阶段缺少 --visual-review。",
            "让独立 Subagent/视觉 reviewer 按 template 逐图填写 JSON，再把文件或目录传入。",
        )])
    review_files = _review_files(ctx.visual_review_path)
    if not review_files:
        return CheckerOutput(findings=[Finding(
            rid, ctx.visual_review_path.name, 0, "hard", "没有找到视觉 review JSON。",
            "传入填写完成的 JSON 文件或包含分批 JSON 的目录。",
        )])

    covered: dict[str, tuple[dict, Path]] = {}
    reviewers: set[str] = set()
    review_hashes: list[dict] = []

    for review_file in review_files:
        try:
            review = json.loads(review_file.read_text(encoding="utf-8"))
        except Exception as exc:
            findings.append(Finding(
                rid, review_file.name, 0, "hard", f"视觉 review JSON 无法读取：{exc}",
                "修复 JSON 语法。",
            ))
            continue
        review_hashes.append({"file": review_file.name, "sha256": sha256_file(review_file)})
        reviewer = str(review.get("reviewer_id", "")).strip()
        producer = str(review.get("producer_id", "")).strip()
        session = str(review.get("reviewer_session_id", "")).strip()
        if review.get("candidate_sha") != ctx.candidate_sha or review.get("render_manifest_sha") != manifest_hash:
            findings.append(Finding(
                rid, review_file.name, 0, "hard", "视觉 review 的 candidate/render hash 已过期。",
                "基于当前 template 和 PNG 重新审阅。",
            ))
        if not reviewer or not session or review.get("independent") is not True:
            findings.append(Finding(
                rid, review_file.name, 0, "hard", "缺少 reviewer_id/session 或 independent=true。",
                "必须由 fresh-context 独立 reviewer 填写身份与 session。",
            ))
        if not producer or producer != ctx.producer_id:
            findings.append(Finding(
                rid, review_file.name, 0, "hard", "视觉 review 的 producer_id 与本次命令不一致。",
                "使用生成 template 时的 producer_id，禁止手工换 candidate 身份。",
            ))
        if reviewer and producer and reviewer == producer:
            findings.append(Finding(
                rid, review_file.name, 0, "hard", "producer 与 reviewer 是同一身份。",
                "生产者只能提交 CANDIDATE；另开 fresh-context reviewer 复验。",
            ))
        if reviewer:
            reviewers.add(reviewer)

        for entry in review.get("artifacts", []):
            aid = entry.get("artifact_id", "")
            if aid in covered:
                findings.append(Finding(
                    rid, review_file.name, 0, "hard", f"artifact 被重复签署：{aid}",
                    "分批 reviewer 的 artifact 范围必须互不重叠。", aid,
                ))
                continue
            covered[aid] = (entry, review_file)

    for aid, expected_item in expected.items():
        if aid not in covered:
            findings.append(Finding(
                rid, expected_item["source_file"], expected_item["line"], "hard",
                "该图没有独立视觉 reviewer 结论。",
                "必须逐图覆盖；不能用抽样或全局一句 PASS 代替。", aid,
            ))
            continue
        entry, review_file = covered[aid]
        if entry.get("png_sha256") != expected_item.get("png_sha256"):
            findings.append(Finding(
                rid, review_file.name, 0, "hard", "review 对应的 PNG hash 已失效。",
                "重新打开当前 PNG 审阅。", aid,
            ))
        if entry.get("verdict") != "PASS":
            findings.append(Finding(
                rid, expected_item["source_file"], expected_item["line"], "hard",
                f"视觉总判定不是 PASS：{entry.get('verdict', 'MISSING')}",
                "修图后重渲染并重新独立审阅。", aid,
            ))
        dimension_results = entry.get("dimensions", {})
        for dimension_id, dimension in dimension_map.items():
            applies_to = dimension.get("applies_to", []) or []
            if applies_to and expected_item.get("kind") not in applies_to:
                continue
            result = dimension_results.get(dimension_id)
            if not isinstance(result, dict):
                findings.append(Finding(
                    rid, expected_item["source_file"], expected_item["line"], "hard",
                    f"缺少视觉维度：{dimension_id}",
                    "逐维度填写 PASS/FAIL/NA；不得漏项。", aid,
                ))
                continue
            verdict = result.get("verdict")
            note = str(result.get("note", "")).strip()
            allow_na = bool(dimension.get("allow_na", False))
            if verdict == "NA" and allow_na and note:
                continue
            if verdict != "PASS":
                findings.append(Finding(
                    rid, expected_item["source_file"], expected_item["line"], "hard",
                    f"视觉维度 {dimension_id} 未通过：{verdict or 'MISSING'}",
                    "修复后重审；NA 仅在规则允许且写明理由时有效。", aid,
                    {"review_note": note},
                ))

    for extra in sorted(set(covered) - set(expected)):
        entry, review_file = covered[extra]
        findings.append(Finding(
            rid, review_file.name, 0, "hard", f"review 包含 manifest 中不存在的 artifact：{extra}",
            "删除陈旧条目并基于当前 manifest 重审。", extra,
        ))

    return CheckerOutput(
        findings=findings,
        metrics={
            "expected_artifacts": len(expected),
            "reviewed_artifacts": len(set(covered) & set(expected)),
            "reviewers": sorted(reviewers),
            "review_files": review_hashes,
            "render_manifest_sha": manifest_hash,
            "artifact_kinds": _kind_counts(expected.values()),
        },
    )


def prepare_review_template(ctx: GateContext) -> CheckerOutput:
    """在 source/render/docx 全通过后生成同时覆盖 SVG 与 DOCX 页面的 template。"""
    manifest, manifest_hash, finding = _combined_manifest(ctx, "REVIEW-PACKET")
    if finding:
        return CheckerOutput(findings=[finding])
    expected = {item["artifact_id"]: item for item in manifest.get("artifacts", [])}
    dimensions = ctx.config.get("visual_review", {}).get("dimensions", [])
    path = _write_review_template(ctx, manifest_hash, expected, dimensions)
    return CheckerOutput(metrics={
        "render_manifest_sha": manifest_hash,
        "review_template": path.name,
        "artifact_count": len(expected),
        "artifact_kinds": _kind_counts(expected.values()),
    })


def _combined_manifest(ctx: GateContext, rid: str) -> tuple[dict, str, Finding | None]:
    svg_path = ctx.output_dir / f"render-manifest-{ctx.candidate_sha[:12]}.json"
    svg, svg_hash, finding = _load_manifest(
        svg_path, "render_manifest_sha", ctx.candidate_sha, rid,
    )
    if finding:
        return {}, "", finding
    if ctx.selected_stage not in {"release", "all", "prepare"}:
        return svg, svg_hash, None
    artifacts = list(svg.get("artifacts", []))
    combined = {
        "schema_version": "1.0.0",
        "candidate_sha": ctx.candidate_sha,
        "svg_manifest_sha": svg_hash,
        "artifacts": artifacts,
    }
    page_path = ctx.output_dir / f"docx-page-manifest-{ctx.candidate_sha[:12]}.json"
    pages, page_hash, finding = _load_manifest(
        page_path, "page_manifest_sha", ctx.candidate_sha, rid,
    )
    if finding:
        return {}, "", finding
    combined["docx_page_manifest_sha"] = page_hash
    combined["docx_sha256"] = pages.get("docx_sha256")
    combined["artifacts"] = artifacts + list(pages.get("artifacts", []))
    combined_hash = canonical_hash(combined)
    combined["render_manifest_sha"] = combined_hash
    combined_path = ctx.output_dir / f"combined-render-manifest-{ctx.candidate_sha[:12]}-{ctx.selected_stage}.json"
    combined_path.write_text(json.dumps(combined, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return combined, combined_hash, None


def _load_manifest(path: Path, hash_field: str, candidate_sha: str, rid: str):
    if not path.exists():
        return {}, "", Finding(
            rid, "", 0, "hard", f"缺少当前 candidate 的 {path.name}。",
            "先运行前置渲染阶段；缺页/缺图不得跳过。",
        )
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, "", Finding(
            rid, path.name, 0, "hard", f"manifest 无法解析：{exc}",
            "重新生成 manifest。",
        )
    manifest_hash = manifest.get(hash_field, "")
    payload = {key: value for key, value in manifest.items() if key != hash_field}
    if manifest.get("candidate_sha") != candidate_sha or canonical_hash(payload) != manifest_hash:
        return {}, "", Finding(
            rid, path.name, 0, "hard", "manifest 已损坏或不属于当前 candidate。",
            "重新运行渲染阶段，不要复用旧证据。",
        )
    return manifest, manifest_hash, None


def _write_review_template(ctx, manifest_hash, expected, dimensions):
    template = {
        "schema_version": "1.0.0",
        "candidate_sha": ctx.candidate_sha,
        "render_manifest_sha": manifest_hash,
        "producer_id": ctx.producer_id,
        "reviewer_id": "",
        "reviewer_session_id": "",
        "independent": False,
        "reviewed_at": "",
        "artifacts": [],
    }
    for item in expected.values():
        applicable = [
            dimension for dimension in dimensions
            if not dimension.get("applies_to") or item.get("kind") in dimension.get("applies_to", [])
        ]
        template["artifacts"].append({
            "artifact_id": item["artifact_id"],
            "kind": item.get("kind"),
            "png_sha256": item.get("png_sha256"),
            "verdict": "UNREVIEWED",
            "dimensions": {
                dimension["id"]: {"verdict": "UNREVIEWED", "note": ""}
                for dimension in applicable
            },
            "note": "",
        })
    name = f"visual-review-{ctx.candidate_sha[:12]}-{ctx.selected_stage}.template.json"
    (ctx.output_dir / name).write_text(
        json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return ctx.output_dir / name


def _kind_counts(items):
    counts = {}
    for item in items:
        kind = item.get("kind", "unknown")
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def _review_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(
            item for item in path.glob("*.json")
            if ".template." not in item.name and not item.name.startswith("render-manifest-")
        )
    return []
