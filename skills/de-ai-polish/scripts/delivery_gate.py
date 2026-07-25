#!/usr/bin/env python3
"""验证 de-ai-polish 的场景声明、Protected Spans 与评分门禁回执。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_RUBRIC_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "quality-score-rubric.json"
)
SCENE_CONSTRAINT = "SCENE-DECLARED-BEFORE-REWRITE"
SPANS_CONSTRAINT = "PROTECTED-SPANS-PRESERVED"
SCORE_CONSTRAINT = "QUALITY-SCORE-GATE-PASSED"
CONSTRAINT_IDS = (SCENE_CONSTRAINT, SPANS_CONSTRAINT, SCORE_CONSTRAINT)
SCENES = {
    "legal_document",
    "wechat_public_comment",
    "chat_reply",
    "general",
}
SPAN_CATEGORIES = {
    "statute",
    "entity",
    "procedure",
    "direct_quote",
    "contract_clause",
    "number_date_amount",
    "url_case_number",
    "other",
}
DIMENSIONS = {
    "naturalness",
    "rhythm",
    "professionalism",
    "individuality",
    "conciseness",
}
VOICE_CHECKS = {
    "profile_matched",
    "no_sample_copy",
    "no_fact_leak",
    "no_counterexample_reuse",
}


class GateError(Exception):
    """输入、manifest 或文件绑定非法。"""


class ConstraintViolation(Exception):
    """候选产物违反可归因的交付约束。"""

    def __init__(self, constraint_id: str, message: str):
        super().__init__(message)
        self.constraint_id = constraint_id


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise GateError(f"文件不存在: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise GateError(f"{label}不存在: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"{label}无法读取: {exc}") from exc
    if not isinstance(value, dict):
        raise GateError(f"{label}必须是 JSON object")
    return value


def validate_run_plan(data: dict[str, Any]) -> dict[str, Any]:
    required = {"schema_version", "scene", "author_sample_used", "protected_spans"}
    if set(data) != required or data.get("schema_version") != SCHEMA_VERSION:
        raise ConstraintViolation(SCENE_CONSTRAINT, "运行计划字段或版本非法")
    if data["scene"] not in SCENES:
        raise ConstraintViolation(SCENE_CONSTRAINT, "运行计划未声明合法 scene")
    if not isinstance(data["author_sample_used"], bool):
        raise ConstraintViolation(SCENE_CONSTRAINT, "author_sample_used 必须是布尔值")
    if not isinstance(data["protected_spans"], list):
        raise ConstraintViolation(SPANS_CONSTRAINT, "protected_spans 必须是数组")

    seen_ids: set[str] = set()
    spans: list[dict[str, str]] = []
    for item in data["protected_spans"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"id", "category", "text"}
            or not isinstance(item["id"], str)
            or not item["id"]
            or item["id"] in seen_ids
            or item["category"] not in SPAN_CATEGORIES
            or not isinstance(item["text"], str)
            or not item["text"]
        ):
            raise ConstraintViolation(SPANS_CONSTRAINT, "Protected Span 条目非法")
        seen_ids.add(item["id"])
        spans.append(dict(item))
    return {
        "scene": data["scene"],
        "author_sample_used": data["author_sample_used"],
        "protected_spans": spans,
    }


def validate_rubric(data: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "score_method",
        "dimensions",
        "thresholds",
        "voice_profile_checks",
    }
    if (
        set(data) != required
        or data.get("schema_version") != SCHEMA_VERSION
        or data.get("score_method") != "sum"
        or not isinstance(data.get("dimensions"), dict)
        or set(data["dimensions"]) != DIMENSIONS
    ):
        raise GateError("质量评分规则结构或版本非法")

    dimensions: dict[str, dict[str, float]] = {}
    for dimension_id, limits in data["dimensions"].items():
        if (
            not isinstance(limits, dict)
            or set(limits) != {"minimum", "maximum"}
            or any(
                not isinstance(limits[key], (int, float))
                or isinstance(limits[key], bool)
                for key in ("minimum", "maximum")
            )
            or float(limits["minimum"]) < 0
            or float(limits["maximum"]) <= float(limits["minimum"])
        ):
            raise GateError(f"质量评分维度范围非法: {dimension_id}")
        dimensions[dimension_id] = {
            "minimum": float(limits["minimum"]),
            "maximum": float(limits["maximum"]),
        }

    threshold_keys = {
        "total_minimum",
        "naturalness_minimum",
        "individuality_exclusive_minimum",
        "legal_document_professionalism_minimum",
    }
    thresholds = data["thresholds"]
    if (
        not isinstance(thresholds, dict)
        or set(thresholds) != threshold_keys
        or any(
            not isinstance(value, (int, float)) or isinstance(value, bool)
            for value in thresholds.values()
        )
    ):
        raise GateError("质量评分阈值非法")
    total_maximum = sum(item["maximum"] for item in dimensions.values())
    if (
        float(thresholds["total_minimum"]) <= 0
        or float(thresholds["total_minimum"]) > total_maximum
        or not (
            dimensions["naturalness"]["minimum"]
            <= float(thresholds["naturalness_minimum"])
            <= dimensions["naturalness"]["maximum"]
        )
        or not (
            dimensions["individuality"]["minimum"]
            <= float(thresholds["individuality_exclusive_minimum"])
            < dimensions["individuality"]["maximum"]
        )
        or not (
            dimensions["professionalism"]["minimum"]
            <= float(thresholds["legal_document_professionalism_minimum"])
            <= dimensions["professionalism"]["maximum"]
        )
    ):
        raise GateError("质量评分阈值超出 rubric 分值范围")

    voice_checks = data["voice_profile_checks"]
    if (
        not isinstance(voice_checks, list)
        or len(voice_checks) != len(VOICE_CHECKS)
        or set(voice_checks) != VOICE_CHECKS
    ):
        raise GateError("voice profile 检查项非法")
    return {
        "dimensions": dimensions,
        "thresholds": {key: float(value) for key, value in thresholds.items()},
        "voice_profile_checks": set(voice_checks),
    }


def build_span_records(
    source_path: Path, spans: list[dict[str, str]]
) -> list[dict[str, Any]]:
    source = source_path.read_bytes()
    records: list[dict[str, Any]] = []
    for span in spans:
        value = span["text"].encode("utf-8")
        count = source.count(value)
        if count < 1:
            raise ConstraintViolation(
                SPANS_CONSTRAINT,
                f"源稿未找到 Protected Span: {span['id']}",
            )
        records.append(
            {
                "id": span["id"],
                "category": span["category"],
                "text_base64": base64.b64encode(value).decode("ascii"),
                "sha256": sha256_bytes(value),
                "source_count": count,
            }
        )
    return records


def verify_spans(
    final_path: Path, records: list[dict[str, Any]]
) -> tuple[bool, list[str]]:
    final = final_path.read_bytes()
    failed: list[str] = []
    for record in records:
        try:
            value = base64.b64decode(str(record["text_base64"]), validate=True)
            expected_count = int(record["source_count"])
        except (KeyError, TypeError, ValueError) as exc:
            raise GateError("Protected Span manifest 内容非法") from exc
        if (
            sha256_bytes(value) != record.get("sha256")
            or final.count(value) != expected_count
        ):
            failed.append(str(record.get("id", "unknown")))
    return not failed, failed


def validate_score_receipt(
    data: dict[str, Any],
    final_path: Path,
    scene: str,
    author_sample_used: bool,
    rubric: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    required = {
        "schema_version",
        "final_sha256",
        "scene",
        "author_sample_used",
        "dimensions",
        "total",
        "voice_profile_checks",
    }
    if set(data) != required or data.get("schema_version") != SCHEMA_VERSION:
        return False, {"reason": "score-receipt-shape"}
    if (
        data["final_sha256"] != sha256_file(final_path)
        or data["scene"] != scene
        or data["author_sample_used"] is not author_sample_used
        or not isinstance(data["dimensions"], dict)
        or set(data["dimensions"]) != DIMENSIONS
    ):
        return False, {"reason": "score-receipt-binding"}

    values = data["dimensions"]
    for dimension_id, value in values.items():
        limits = rubric["dimensions"][dimension_id]
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or float(value) < limits["minimum"]
            or float(value) > limits["maximum"]
        ):
            return False, {"reason": "score-dimension-range"}
    total = data["total"]
    if (
        not isinstance(total, (int, float))
        or isinstance(total, bool)
        or not math.isclose(float(total), sum(float(v) for v in values.values()))
    ):
        return False, {"reason": "score-total-mismatch"}

    thresholds = rubric["thresholds"]
    thresholds_passed = (
        float(total) >= thresholds["total_minimum"]
        and float(values["naturalness"]) >= thresholds["naturalness_minimum"]
        and float(values["individuality"])
        > thresholds["individuality_exclusive_minimum"]
        and (
            scene != "legal_document"
            or float(values["professionalism"])
            >= thresholds["legal_document_professionalism_minimum"]
        )
    )
    voice_checks = data["voice_profile_checks"]
    if author_sample_used:
        thresholds_passed = (
            thresholds_passed
            and isinstance(voice_checks, dict)
            and set(voice_checks) == rubric["voice_profile_checks"]
            and all(value is True for value in voice_checks.values())
        )
    elif voice_checks is not None:
        thresholds_passed = False
    return thresholds_passed, {
        "total": total,
        "naturalness": values["naturalness"],
        "professionalism": values["professionalism"],
        "individuality": values["individuality"],
    }


def artifact_hashes(
    source: Path, final: Path, run_plan: Path, score_receipt: Path
) -> dict[str, str]:
    return {
        "source-markdown": sha256_file(source),
        "final-markdown": sha256_file(final),
        "run-plan": sha256_file(run_plan),
        "score-receipt": sha256_file(score_receipt),
    }


def protocol_output(
    failures: list[str],
    hashes: dict[str, str],
    scene: str | None,
    span_ids: list[str],
    failed_span_ids: list[str],
    score_detail: dict[str, Any],
) -> dict[str, Any]:
    measurements = {
        SCENE_CONSTRAINT: {"scene-declared": SCENE_CONSTRAINT not in failures},
        SPANS_CONSTRAINT: {
            "protected-spans-preserved": SPANS_CONSTRAINT not in failures,
            "failed-span-count": len(failed_span_ids),
        },
        SCORE_CONSTRAINT: {"score-gate-passed": SCORE_CONSTRAINT not in failures},
    }
    if failures:
        return {
            "failed_constraint_ids": failures,
            "artifact_sha256": hashes,
            "measurements": {
                constraint_id: measurements[constraint_id]
                for constraint_id in failures
            },
        }
    return {
        "passed_constraint_ids": list(CONSTRAINT_IDS),
        "artifact_sha256": hashes,
        "measurements": measurements,
        "observables": {
            "scene": [scene],
            "protected-span-ids": span_ids,
            "score-threshold-detail": [
                f"{key}={score_detail[key]}" for key in sorted(score_detail)
            ],
        },
    }


def evaluate(
    source_path: Path,
    final_path: Path,
    run_plan_path: Path,
    score_receipt_path: Path,
    rubric_path: Path = DEFAULT_RUBRIC_PATH,
    span_records: list[dict[str, Any]] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    hashes = artifact_hashes(
        source_path, final_path, run_plan_path, score_receipt_path
    )
    failures: list[str] = []
    failed_span_ids: list[str] = []
    scene: str | None = None
    author_sample_used = False
    records: list[dict[str, Any]] = []
    rubric = validate_rubric(load_json(rubric_path, "质量评分规则"))
    try:
        plan = validate_run_plan(load_json(run_plan_path, "运行计划"))
        scene = str(plan["scene"])
        author_sample_used = bool(plan["author_sample_used"])
        records = (
            build_span_records(source_path, plan["protected_spans"])
            if span_records is None
            else span_records
        )
    except ConstraintViolation as exc:
        failures.append(exc.constraint_id)

    if scene is not None and SPANS_CONSTRAINT not in failures:
        spans_ok, failed_span_ids = verify_spans(final_path, records)
        if not spans_ok:
            failures.append(SPANS_CONSTRAINT)

    score_detail: dict[str, Any] = {}
    if scene is not None:
        score_ok, score_detail = validate_score_receipt(
            load_json(score_receipt_path, "评分回执"),
            final_path,
            scene,
            author_sample_used,
            rubric,
        )
        if not score_ok:
            failures.append(SCORE_CONSTRAINT)

    ordered_failures = [
        constraint_id
        for constraint_id in CONSTRAINT_IDS
        if constraint_id in set(failures)
    ]
    return ordered_failures, protocol_output(
        ordered_failures,
        hashes,
        scene,
        [str(record["id"]) for record in records],
        failed_span_ids,
        score_detail,
    )


def write_new_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise GateError(f"快照已存在，拒绝覆盖: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def command_snapshot(args: argparse.Namespace) -> int:
    source_path = Path(args.input).expanduser().resolve()
    run_plan_path = Path(args.run_plan).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    rubric_path = Path(args.rubric).expanduser().resolve()
    plan = validate_run_plan(load_json(run_plan_path, "运行计划"))
    validate_rubric(load_json(rubric_path, "质量评分规则"))
    records = build_span_records(source_path, plan["protected_spans"])
    payload = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "path": str(source_path),
            "sha256": sha256_file(source_path),
        },
        "run_plan": {
            "path": str(run_plan_path),
            "sha256": sha256_file(run_plan_path),
        },
        "quality_rubric": {
            "path": str(rubric_path),
            "sha256": sha256_file(rubric_path),
        },
        "scene": plan["scene"],
        "author_sample_used": plan["author_sample_used"],
        "protected_spans": records,
    }
    write_new_json(output_path, payload)
    print(
        json.dumps(
            {
                "status": "DE_AI_DELIVERY_SNAPSHOT_READY",
                "manifest": str(output_path),
                "scene": plan["scene"],
                "protected_span_count": len(records),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def command_verify(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve()
    final_path = Path(args.final).expanduser().resolve()
    score_receipt_path = Path(args.score_receipt).expanduser().resolve()
    manifest = load_json(manifest_path, "交付快照")
    required = {
        "schema_version",
        "source",
        "run_plan",
        "quality_rubric",
        "scene",
        "author_sample_used",
        "protected_spans",
    }
    if set(manifest) != required or manifest["schema_version"] != SCHEMA_VERSION:
        raise GateError("交付快照结构非法")
    source_path = Path(manifest["source"]["path"]).resolve()
    run_plan_path = Path(manifest["run_plan"]["path"]).resolve()
    rubric_path = Path(manifest["quality_rubric"]["path"]).resolve()
    if sha256_file(source_path) != manifest["source"]["sha256"]:
        raise GateError("源稿在快照后发生变化，必须重新生成快照")
    if sha256_file(run_plan_path) != manifest["run_plan"]["sha256"]:
        raise GateError("运行计划在快照后发生变化，必须重新生成快照")
    if sha256_file(rubric_path) != manifest["quality_rubric"]["sha256"]:
        raise GateError("质量评分规则在快照后发生变化，必须重新生成快照")
    validate_rubric(load_json(rubric_path, "质量评分规则"))
    plan = validate_run_plan(load_json(run_plan_path, "运行计划"))
    if (
        plan["scene"] != manifest["scene"]
        or plan["author_sample_used"] != manifest["author_sample_used"]
    ):
        raise GateError("运行计划与交付快照不一致")
    failures, output = evaluate(
        source_path,
        final_path,
        run_plan_path,
        score_receipt_path,
        rubric_path=rubric_path,
        span_records=manifest["protected_spans"],
    )
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0 if not failures else 3


def command_check(args: argparse.Namespace) -> int:
    failures, output = evaluate(
        Path(args.source).expanduser().resolve(),
        Path(args.final).expanduser().resolve(),
        Path(args.run_plan).expanduser().resolve(),
        Path(args.score_receipt).expanduser().resolve(),
        rubric_path=Path(args.rubric).expanduser().resolve(),
    )
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0 if not failures else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("--input", required=True)
    snapshot.add_argument("--run-plan", required=True)
    snapshot.add_argument("--rubric", default=str(DEFAULT_RUBRIC_PATH))
    snapshot.add_argument("--output", required=True)
    snapshot.set_defaults(handler=command_snapshot)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--final", required=True)
    verify.add_argument("--score-receipt", required=True)
    verify.set_defaults(handler=command_verify)

    check = subparsers.add_parser("check")
    check.add_argument("--source", required=True)
    check.add_argument("--final", required=True)
    check.add_argument("--run-plan", required=True)
    check.add_argument("--score-receipt", required=True)
    check.add_argument("--rubric", default=str(DEFAULT_RUBRIC_PATH))
    check.set_defaults(handler=command_check)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.handler(args))
    except ConstraintViolation as exc:
        print(
            json.dumps(
                {
                    "failed_constraint_ids": [exc.constraint_id],
                    "measurements": {
                        exc.constraint_id: {"preflight-ready": False}
                    },
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 3
    except (
        GateError,
        OSError,
        UnicodeDecodeError,
        ValueError,
        TypeError,
        KeyError,
    ) as exc:
        print(f"DE_AI_DELIVERY_GATE_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
