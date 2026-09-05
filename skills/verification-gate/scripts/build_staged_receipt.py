#!/usr/bin/env python3
"""Build a PEA staged receipt from already-executed verification facts.

This adapter deliberately does not execute any reported command and does not
decide whether a candidate is ready or released.  It validates one narrow input
contract and emits evidence for production-engineering-audit to adjudicate.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


INPUT_CONTRACT = "verification-gate-stage-report/v1"
OUTPUT_CONTRACT = "production-engineering-completion-evidence/v1"
CLAIM_TYPES = {"bugfix", "feature", "performance", "refactor", "release"}
TARGET_TYPES = {"application", "service", "workflow", "skill"}
STAGE_KINDS = {"static", "unit", "build", "integration", "e2e", "runtime"}
STAGE_STATUSES = {"passed", "failed", "skipped", "not_run"}
# Live canary and release receipts need environment/release facts that this
# deliberately narrow verification-stage adapter does not collect.
SUPPORTED_CLAIMED_LEVELS = {"tested", "reproduced", "e2e_verified"}

TOP_LEVEL_KEYS = {
    "contract",
    "claim",
    "candidate",
    "target",
    "stages",
    "consumer",
    "unsupported_claims",
    "original_symptom",
    "negative_control",
}
CLAIM_KEYS = {"id", "type", "statement", "claimed_level", "observed_at"}
CANDIDATE_KEYS = {"git_commit"}
TARGET_KEYS = {"type", "name"}
STAGE_KEYS = {
    "id",
    "kind",
    "status",
    "required",
    "command",
    "exit_code",
    "failure_count",
    "evidence",
    "skip_reason",
    "fresh_context",
}
CONSUMER_KEYS = {"name", "observed", "evidence"}
SYMPTOM_KEYS = {"status", "evidence"}
CONTROL_KEYS = {"status", "evidence"}

GIT_OBJECT_RE = re.compile(r"^[0-9a-f]{40,64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
FILE_URI_RE = re.compile(r"\bfile:(?://)?/[^\s<>\"']+", re.I)
WEB_URI_RE = re.compile(
    r"(?<![A-Za-z0-9+.-])(?!file://)[A-Za-z][A-Za-z0-9+.-]{0,31}://"
    r"[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+",
    re.I,
)
WINDOWS_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/][^\s<>\"']*|\\\\[^\\/\s]+[\\/][^\s<>\"']*)"
)
TILDE_PATH_RE = re.compile(r"(?<![A-Za-z0-9])~[\\/][^\s<>\"']+")
UNIX_ABSOLUTE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9._~/-])/{1,2}[^\s<>\"']+"
)
SECRET_PATTERNS = (
    re.compile(r"\b(?:sk|ghp|github_pat|xox[baprs])-?[A-Za-z0-9_-]{12,}\b", re.I),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.I),
    re.compile(r"\b(?:api[_-]?key|password|secret|token)\s*[:=]\s*\S+", re.I),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----",
        re.I,
    ),
    re.compile(
        r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{5,}\."
        r"[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}(?![A-Za-z0-9_-])"
    ),
    re.compile(
        r"(?<![A-Za-z0-9+.-])[A-Za-z][A-Za-z0-9+.-]{0,31}://"
        r"[^\s/@:]+:[^\s/@]+@",
        re.I,
    ),
)
BASIC_AUTH_RE = re.compile(r"\bBasic\s+([A-Za-z0-9+/]{8,}={0,2})(?=$|[\s,;])", re.I)


class ReceiptError(ValueError):
    """A safe, user-correctable contract error."""


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ReceiptError(f"argument error: {message}")


def _reject_duplicate_keys(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReceiptError("input JSON contains a duplicate object key")
        result[key] = value
    return result


def load_report(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ReceiptError("input report is unavailable or is not UTF-8") from exc
    try:
        report = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise ReceiptError("input report is not valid JSON") from exc
    if not isinstance(report, dict):
        raise ReceiptError("input report root must be an object")
    return report


def _expect_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReceiptError(f"{field} must be an object")
    return value


def _expect_exact_keys(
    value: dict[str, Any], allowed: set[str], required: set[str], field: str
) -> None:
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown:
        raise ReceiptError(f"{field} contains unsupported fields")
    if missing:
        raise ReceiptError(f"{field} is missing required fields")


def _contains_absolute_filesystem_reference(text: str) -> bool:
    """Detect local absolute paths while leaving ordinary web URLs untouched."""

    if FILE_URI_RE.search(text):
        return True
    without_web_uris = WEB_URI_RE.sub("", text)
    return any(
        pattern.search(without_web_uris)
        for pattern in (WINDOWS_PATH_RE, TILDE_PATH_RE, UNIX_ABSOLUTE_PATH_RE)
    )


def _contains_secret(text: str) -> bool:
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        return True
    for match in BASIC_AUTH_RE.finditer(text):
        encoded = match.group(1)
        padded = encoded + "=" * (-len(encoded) % 4)
        try:
            decoded = base64.b64decode(padded, validate=True)
        except (binascii.Error, ValueError):
            continue
        if b":" in decoded:
            return True
    return False


def _safe_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReceiptError(f"{field} must be a non-empty string")
    text = value.strip()
    if any(ord(char) < 32 for char in text):
        raise ReceiptError(f"{field} contains control characters")
    if _contains_absolute_filesystem_reference(text):
        raise ReceiptError(f"{field} contains an absolute filesystem path")
    if _contains_secret(text):
        raise ReceiptError(f"{field} appears to contain a secret")
    return text


def _enum_text(value: Any, field: str, allowed: set[str]) -> str:
    text = _safe_text(value, field)
    if text not in allowed:
        raise ReceiptError(f"{field} has an unsupported value")
    return text


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ReceiptError(f"{field} must be a boolean")
    return value


def _non_negative_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ReceiptError(f"{field} must be a non-negative integer")
    return value


def _timestamp(value: Any, field: str) -> str:
    text = _safe_text(value, field)
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReceiptError(f"{field} must be an ISO-8601 timestamp") from exc
    if stamp.tzinfo is None:
        raise ReceiptError(f"{field} must include a timezone")
    if stamp.astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ReceiptError(f"{field} cannot be in the future")
    return text


def _repo_root(repo_arg: Path) -> Path:
    try:
        repo = repo_arg.resolve(strict=True)
    except OSError as exc:
        raise ReceiptError("repository is unavailable") from exc
    if not repo.is_dir():
        raise ReceiptError("repository must be a directory")
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReceiptError("repository Git metadata is unavailable") from exc
    if completed.returncode != 0:
        raise ReceiptError("repository is not a Git checkout")
    try:
        top = Path(completed.stdout.strip()).resolve(strict=True)
    except OSError as exc:
        raise ReceiptError("repository Git root is unavailable") from exc
    if top != repo:
        raise ReceiptError("--repo must point to the Git worktree root")
    return repo


def _current_head(repo: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReceiptError("current Git candidate is unavailable") from exc
    head = completed.stdout.strip().lower()
    if completed.returncode != 0 or not GIT_OBJECT_RE.fullmatch(head):
        raise ReceiptError("current Git candidate is unavailable")
    return head


def _evidence_path(repo: Path, value: Any, field: str) -> str:
    text = _safe_text(value, field)
    if "\\" in text or text.startswith("~"):
        raise ReceiptError(f"{field} must be a repository-relative POSIX path")
    relative = PurePosixPath(text)
    if relative.is_absolute() or ".." in relative.parts or text in {".", ".."}:
        raise ReceiptError(f"{field} must be a repository-relative path without traversal")
    if relative.as_posix() != text or "//" in text:
        raise ReceiptError(f"{field} must be a normalized repository-relative path")
    candidate = repo.joinpath(*relative.parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(repo)
    except (OSError, ValueError) as exc:
        raise ReceiptError(f"{field} does not resolve to an in-repository file") from exc
    if not resolved.is_file():
        raise ReceiptError(f"{field} does not resolve to an in-repository file")
    return text


def _validate_claim(report: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    claim = _expect_object(report.get("claim"), "claim")
    _expect_exact_keys(claim, CLAIM_KEYS, CLAIM_KEYS, "claim")
    claim_id = _safe_text(claim["id"], "claim.id")
    if not ID_RE.fullmatch(claim_id):
        raise ReceiptError("claim.id has an invalid format")
    claim_type = _enum_text(claim["type"], "claim.type", CLAIM_TYPES)
    level = _enum_text(
        claim["claimed_level"], "claim.claimed_level", SUPPORTED_CLAIMED_LEVELS
    )
    normalized = {
        "claim_id": claim_id,
        "claim_type": claim_type,
        "claim": _safe_text(claim["statement"], "claim.statement"),
        "level": level,
        "observed_at": _timestamp(claim["observed_at"], "claim.observed_at"),
    }
    return normalized, claim_type, level


def _validate_target(report: dict[str, Any]) -> dict[str, str]:
    target = _expect_object(report.get("target"), "target")
    _expect_exact_keys(target, TARGET_KEYS, TARGET_KEYS, "target")
    return {
        "type": _enum_text(target["type"], "target.type", TARGET_TYPES),
        "name": _safe_text(target["name"], "target.name"),
    }


def _validate_candidate(report: dict[str, Any], head: str) -> dict[str, str]:
    candidate = _expect_object(report.get("candidate"), "candidate")
    _expect_exact_keys(candidate, CANDIDATE_KEYS, CANDIDATE_KEYS, "candidate")
    commit = _safe_text(candidate["git_commit"], "candidate.git_commit").lower()
    if not GIT_OBJECT_RE.fullmatch(commit):
        raise ReceiptError("candidate.git_commit must be a full Git object id")
    if commit != head:
        raise ReceiptError("candidate.git_commit does not match the current Git HEAD")
    return {"git_commit": commit}


def _validate_stage(repo: Path, raw: Any, index: int, seen: set[str]) -> dict[str, Any]:
    field = f"stages[{index}]"
    stage = _expect_object(raw, field)
    required_keys = {"id", "kind", "status", "required"}
    _expect_exact_keys(stage, STAGE_KEYS, required_keys, field)
    stage_id = _safe_text(stage["id"], f"{field}.id")
    if not ID_RE.fullmatch(stage_id):
        raise ReceiptError(f"{field}.id has an invalid format")
    if stage_id in seen:
        raise ReceiptError("stage ids must be unique")
    seen.add(stage_id)
    kind = _enum_text(stage["kind"], f"{field}.kind", STAGE_KINDS)
    status = _enum_text(stage["status"], f"{field}.status", STAGE_STATUSES)
    required = _boolean(stage["required"], f"{field}.required")
    result: dict[str, Any] = {
        "id": stage_id,
        "kind": kind,
        "status": status,
        "required": required,
    }

    executed_fields = {"command", "exit_code", "failure_count", "evidence"}
    present_executed = executed_fields & set(stage)
    if status in {"skipped", "not_run"}:
        if required:
            raise ReceiptError(f"{field} cannot skip a required stage")
        if present_executed:
            raise ReceiptError(f"{field} cannot contain execution facts when not executed")
        if "fresh_context" in stage:
            raise ReceiptError(f"{field} cannot claim fresh_context when not executed")
        reason = _safe_text(stage.get("skip_reason"), f"{field}.skip_reason")
        result["skip_reason"] = reason
        return result

    if "skip_reason" in stage:
        raise ReceiptError(f"{field} cannot contain skip_reason when executed")
    if present_executed != executed_fields:
        raise ReceiptError(f"{field} is missing executed-stage facts")
    command = _safe_text(stage["command"], f"{field}.command")
    exit_code = _non_negative_int(stage["exit_code"], f"{field}.exit_code")
    failure_count = _non_negative_int(
        stage["failure_count"], f"{field}.failure_count"
    )
    if status == "passed" and (exit_code != 0 or failure_count != 0):
        raise ReceiptError(f"{field} passed status contradicts its execution facts")
    if status == "failed" and exit_code == 0 and failure_count == 0:
        raise ReceiptError(f"{field} failed status contradicts its execution facts")
    result.update(
        {
            "command": command,
            "exit_code": exit_code,
            "failure_count": failure_count,
            "evidence": _evidence_path(repo, stage["evidence"], f"{field}.evidence"),
        }
    )
    if "fresh_context" in stage:
        if kind != "runtime":
            raise ReceiptError(f"{field}.fresh_context is only valid for runtime stages")
        result["fresh_context"] = _boolean(
            stage["fresh_context"], f"{field}.fresh_context"
        )
    return result


def _validate_stages(repo: Path, report: dict[str, Any]) -> list[dict[str, Any]]:
    stages = report.get("stages")
    if not isinstance(stages, list) or not stages:
        raise ReceiptError("stages must be a non-empty array")
    seen: set[str] = set()
    return [_validate_stage(repo, stage, index, seen) for index, stage in enumerate(stages)]


def _validate_consumer(repo: Path, report: dict[str, Any]) -> dict[str, Any]:
    consumer = _expect_object(report.get("consumer"), "consumer")
    _expect_exact_keys(
        consumer, CONSUMER_KEYS, {"name", "observed"}, "consumer"
    )
    observed = _boolean(consumer["observed"], "consumer.observed")
    result: dict[str, Any] = {
        "name": _safe_text(consumer["name"], "consumer.name"),
        "observed": observed,
    }
    if observed:
        if "evidence" not in consumer:
            raise ReceiptError("consumer.evidence is required when observed is true")
        result["evidence"] = _evidence_path(
            repo, consumer["evidence"], "consumer.evidence"
        )
    elif "evidence" in consumer:
        raise ReceiptError("consumer.evidence contradicts observed=false")
    return result


def _validate_defect_evidence(
    repo: Path, report: dict[str, Any], claim_type: str
) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    has_symptom = "original_symptom" in report
    has_control = "negative_control" in report
    defect_claim = claim_type in {"bugfix", "performance"}
    if defect_claim and not (has_symptom and has_control):
        raise ReceiptError(
            "bugfix/performance reports require original_symptom and negative_control"
        )
    if not defect_claim and (has_symptom or has_control):
        raise ReceiptError(
            "original_symptom and negative_control are only valid for bugfix/performance"
        )
    if not defect_claim:
        return None, None

    symptom = _expect_object(report["original_symptom"], "original_symptom")
    _expect_exact_keys(symptom, SYMPTOM_KEYS, SYMPTOM_KEYS, "original_symptom")
    symptom_status = _enum_text(
        symptom["status"],
        "original_symptom.status",
        {"reproduced", "not_verified"},
    )
    symptom_result = {
        "status": symptom_status,
        "evidence": _evidence_path(
            repo, symptom["evidence"], "original_symptom.evidence"
        ),
    }

    control = _expect_object(report["negative_control"], "negative_control")
    _expect_exact_keys(control, CONTROL_KEYS, CONTROL_KEYS, "negative_control")
    control_status = _enum_text(
        control["status"], "negative_control.status", {"proved", "not_proved"}
    )
    control_result = {
        "status": control_status,
        "evidence": _evidence_path(
            repo, control["evidence"], "negative_control.evidence"
        ),
    }
    return symptom_result, control_result


def _validate_unsupported(report: dict[str, Any]) -> list[str]:
    raw = report.get("unsupported_claims")
    if not isinstance(raw, list):
        raise ReceiptError("unsupported_claims must be an array")
    return [_safe_text(item, f"unsupported_claims[{index}]") for index, item in enumerate(raw)]


def build_receipt(repo_arg: Path, report: dict[str, Any]) -> dict[str, Any]:
    """Validate a stage report and return a deterministic PEA receipt object."""

    repo = _repo_root(repo_arg)
    _expect_exact_keys(
        report,
        TOP_LEVEL_KEYS,
        {
            "contract",
            "claim",
            "candidate",
            "target",
            "stages",
            "consumer",
            "unsupported_claims",
        },
        "report",
    )
    if report.get("contract") != INPUT_CONTRACT:
        raise ReceiptError(f"contract must be {INPUT_CONTRACT}")
    head = _current_head(repo)
    claim, claim_type, _level = _validate_claim(report)
    symptom, control = _validate_defect_evidence(repo, report, claim_type)
    receipt: dict[str, Any] = {
        "contract": OUTPUT_CONTRACT,
        **claim,
        "candidate": _validate_candidate(report, head),
        "target": _validate_target(report),
        "verification": {
            "kind": "staged",
            "stages": _validate_stages(repo, report),
        },
        "consumer": _validate_consumer(repo, report),
        "unsupported_claims": _validate_unsupported(report),
    }
    if symptom is not None and control is not None:
        receipt["original_symptom"] = symptom
        receipt["negative_control"] = control
    serialized = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
    if str(repo) in serialized or _contains_absolute_filesystem_reference(serialized):
        raise ReceiptError("generated receipt contains an absolute filesystem path")
    if _contains_secret(serialized):
        raise ReceiptError("generated receipt appears to contain a secret")
    return receipt


def _safe_output_path(repo: Path, value: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ReceiptError("--output must be a repository-relative POSIX path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != value:
        raise ReceiptError("--output must be a normalized repository-relative path")
    output = repo.joinpath(*relative.parts)
    if output.exists() and output.is_symlink():
        raise ReceiptError("--output cannot replace a symlink")
    try:
        parent = output.parent.resolve(strict=True)
        parent.relative_to(repo)
    except (OSError, ValueError) as exc:
        raise ReceiptError("--output parent must already exist inside the repository") from exc
    if output.exists() and not output.is_file():
        raise ReceiptError("--output must name a file")
    return output


def write_receipt(repo: Path, output_arg: str, receipt: dict[str, Any]) -> None:
    output = _safe_output_path(repo, output_arg)
    payload = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent, prefix=f".{output.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, output)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def parser() -> SafeArgumentParser:
    result = SafeArgumentParser(
        description="Convert existing verification stage facts into a PEA staged receipt."
    )
    result.add_argument("--repo", required=True, help="Git worktree root")
    result.add_argument("--input", required=True, help="stage report JSON")
    result.add_argument(
        "--output", required=True, help="repository-relative PEA receipt JSON"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        repo = _repo_root(Path(args.repo))
        input_path = Path(args.input)
        try:
            if input_path.resolve(strict=True) == (repo / args.output).resolve(strict=False):
                raise ReceiptError("--input and --output must be different files")
        except OSError as exc:
            raise ReceiptError("input report is unavailable") from exc
        report = load_report(input_path)
        receipt = build_receipt(repo, report)
        write_receipt(repo, args.output, receipt)
    except ReceiptError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 65
    except OSError:
        print(
            json.dumps(
                {"ok": False, "error": "receipt output could not be written"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 74
    print(json.dumps({"ok": True, "output": args.output}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
