#!/usr/bin/env python3
"""acceptance-repair-gate.py — docs-only 验收修复的极窄价值合同（fail-closed）。

背景：dispatch-value-gate.v2 正确地拒绝 docs-only 派发（文档不是独立价值），
但这会把一类真实场景逼进死角——一个已具名 PR 的验收只差文档修复（review
blockers、缺失的随行文档），按 v2 无法派发，按旧合同又被直接泊车。

本合同是唯一例外通道，且窄到不可能成为通用 docs-only loophole：

- 必须钉扎一个**既有** PR：`target` = {pr, branch, head_sha(40-hex)}；
- `integration_target` 必须等于 `target.branch`——只能集成回既有 PR 分支，
  不存在创建独立文档 PR 的表达字段；
- `blockers` 必须是结构化 ID 清单（每个都有 id/source/detail），不许占位；
- `file_scope` 必须全部是文档路径（复用 dispatch-value-gate 的
  `is_document_path` 单一语义表），非文档变更属于 implementation 价值，
  必须走 dispatch-value-gate.v2；
- 必须有具名 `consumer`（既有 PR 的验收流程）、时区感知且未过期的
  `expiry`、非空 `verification_commands`；
- `repair_owner` + `--registry` 台账实现序列化 owner：同一 PR 只允许一个
  活跃修复 owner；同 (pr, head_sha) 或与活跃记录 blocker 重叠 = 重复修复，
  机械拒绝；
- `re_review` 必须声明修复 worker 与独立 reviewer 的互异身份；
- `repair_attempts_used` >= 2（acceptance-recovery 默认预算）时拒绝派发，
  必须按分类合同泊车。

preflight 拒绝：缺字段/占位、head 非 40-hex、integration_target 与 target
不一致、blocker 缺失/重复、file_scope 含非文档路径或越权路径、过期、预算
耗尽、自审、重复修复、owner 串行冲突。

postflight 额外拒绝：head 漂移（git 模式要求 delivery head 是 pinned head
的后代且 evidence verified_head 一致）、范围外修改、非文档修改、零 diff、
blocker 未全部解决（evidence.resolved_blockers 覆盖且无多余 ID）、验证
命令未在 evidence 中 exit 0、owner 不一致。

用法：
  acceptance-repair-gate.py preflight --spec S.json --registry R.json [--now TS]
  acceptance-repair-gate.py postflight --spec S.json --registry R.json --evidence E.json
      (--repo REPO --base BASE --head HEAD | --diff PATCH --delivery-head SHA) [--now TS]

退出码：0 = 通过；2 = 拒绝（errors 为机器可读清单）。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


SCHEMA = "acceptance-repair.v1"
HEAD_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PR_RE = re.compile(r"^#?\d+$")
PLACEHOLDERS = {"", "tbd", "todo", "unknown", "n/a", "na", "-", "*", "**", "none"}

TOP_LEVEL_KEYS = {
    "schema_version", "target", "integration_target", "blockers", "file_scope",
    "consumer", "expiry", "verification_commands", "repair_owner",
    "repair_attempts_used", "re_review",
}
TARGET_KEYS = {"pr", "branch", "head_sha"}
BLOCKER_KEYS = {"id", "source", "detail", "resolution_hint"}
REVIEW_KEYS = {
    "worker_dispatch_id", "worker_session_id", "reviewer_dispatch_id", "reviewer_session_id",
}
REGISTRY_REQUIRED_KEYS = {"pr", "head_sha", "blocker_ids", "owner", "status"}
REGISTRY_KEYS = REGISTRY_REQUIRED_KEYS | {"recorded_at"}
REGISTRY_STATUSES = {"active", "integrated", "superseded"}

EXIT_REJECTED = 2


def _load_module(name: str, filename: str):
    module_path = Path(__file__).resolve().parent / filename
    spec_loader = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec_loader)
    spec_loader.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_gate = _load_module("dispatch_value_gate_for_repair", "dispatch-value-gate.py")
_recovery = _load_module("acceptance_recovery_for_repair", "acceptance-recovery.py")
is_document_path = _gate.is_document_path
MAX_REPAIR_ATTEMPTS = _recovery.DEFAULT_MAX_REPAIR_ATTEMPTS


def _parse_time(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _missing(value: Any) -> bool:
    if not isinstance(value, str):
        return True
    stripped = value.strip()
    if stripped.startswith("{{") and stripped.endswith("}}"):
        return True
    return stripped.casefold() in PLACEHOLDERS


def _norm(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _exact_keys(section: Any, allowed: set[str], label: str, errors: list[str]) -> bool:
    if not isinstance(section, dict):
        errors.append(f"{label} must be an object with keys {sorted(allowed)}")
        return False
    unsupported = sorted(set(section) - allowed)
    if unsupported:
        errors.append(f"{label} has unsupported fields: {unsupported}")
    return True


def _load_json(path: Path, label: str, errors: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{label} is unreadable or invalid JSON: {exc}")
        return None


def _safe_scope_path(path: str, errors: list[str], label: str) -> bool:
    normalized = path.strip().replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("../") or "/../" in normalized:
        errors.append(f"{label} must be a repo-relative path without traversal: {path}")
        return False
    return True


def validate_contract(spec: Any, now: datetime, errors: list[str]) -> dict[str, Any]:
    """机械校验修复合同本体；返回归一化摘要供 postflight 复用。"""
    if not isinstance(spec, dict):
        errors.append("spec must be a JSON object")
        return {}
    if spec.get("schema_version") != SCHEMA:
        errors.append(f"schema_version must equal {SCHEMA}")
    unsupported = sorted(set(spec) - TOP_LEVEL_KEYS)
    if unsupported:
        errors.append(f"spec has unsupported fields: {unsupported}")
    missing = sorted(TOP_LEVEL_KEYS - set(spec) - {"repair_attempts_used"})
    if missing:
        errors.append(f"spec is missing required fields: {missing}")
    if errors:
        return {}

    target = spec.get("target")
    if not _exact_keys(target, TARGET_KEYS, "target", errors):
        return {}
    pr = target.get("pr")
    if _missing(pr) or not isinstance(pr, str) or not PR_RE.match(pr.strip()):
        errors.append("target.pr must name an existing PR number (e.g. '#136')")
    branch = target.get("branch")
    if _missing(branch):
        errors.append("target.branch is required and cannot be a placeholder")
    head_sha = target.get("head_sha")
    if not isinstance(head_sha, str) or not HEAD_SHA_RE.match(head_sha.strip().casefold()):
        errors.append("target.head_sha must be an immutable 40-hex revision pinned at contract time")
    if errors:
        return {}

    integration_target = spec.get("integration_target")
    if _missing(integration_target):
        errors.append("integration_target is required and must be the existing PR branch")
    elif isinstance(branch, str) and str(integration_target).strip() != branch.strip():
        errors.append(
            "integration_target must equal target.branch: acceptance repairs may only "
            "integrate back into the existing PR branch, never open an independent docs PR"
        )

    blockers = spec.get("blockers")
    if not isinstance(blockers, list) or not blockers:
        errors.append("blockers must be a non-empty array of structured {id, source, detail} entries")
        blockers = []
    seen_ids: set[str] = set()
    for index, blocker in enumerate(blockers):
        prefix = f"blockers[{index}]"
        if not _exact_keys(blocker, BLOCKER_KEYS, prefix, errors):
            continue
        blocker_id = blocker.get("id")
        if _missing(blocker_id):
            errors.append(f"{prefix}.id is required and cannot be a placeholder")
        elif _norm(str(blocker_id)) in seen_ids:
            errors.append(f"{prefix}.id duplicates an earlier blocker id")
        else:
            seen_ids.add(_norm(str(blocker_id)))
        if _missing(blocker.get("source")):
            errors.append(f"{prefix}.source is required (who raised the blocker)")
        if _missing(blocker.get("detail")):
            errors.append(f"{prefix}.detail is required and cannot be a placeholder")

    file_scope = spec.get("file_scope")
    if not isinstance(file_scope, list) or not file_scope:
        errors.append("file_scope must be a non-empty array of document paths")
        file_scope = []
    seen_paths: set[str] = set()
    for index, path in enumerate(file_scope):
        label = f"file_scope[{index}]"
        if _missing(path):
            errors.append(f"{label} is a placeholder, not a real path")
            continue
        text = str(path).strip()
        if _norm(text) in seen_paths:
            errors.append(f"{label} duplicates an earlier scope entry")
        else:
            seen_paths.add(_norm(text))
        if not _safe_scope_path(text, errors, label):
            continue
        if not is_document_path(text):
            errors.append(
                f"{label} is not a document path: this channel is docs-only; "
                "non-document changes are implementation value and must use dispatch-value-gate.v2"
            )

    if _missing(spec.get("consumer")):
        errors.append("consumer is required: name the acceptance flow that consumes the repair")
    expiry = spec.get("expiry")
    try:
        expiry_time = _parse_time(expiry) if isinstance(expiry, str) else None
    except ValueError as exc:
        errors.append(f"invalid expiry: {exc}")
        expiry_time = None
    if expiry_time is None:
        errors.append("expiry must be a timezone-aware RFC3339 timestamp")
    elif expiry_time <= now:
        errors.append("expiry is already in the past")

    verification = spec.get("verification_commands")
    if not isinstance(verification, list) or not verification:
        errors.append("verification_commands must be a non-empty array of deterministic commands")
    else:
        for index, command in enumerate(verification):
            if _missing(command):
                errors.append(f"verification_commands[{index}] is a placeholder")

    if _missing(spec.get("repair_owner")):
        errors.append("repair_owner is required: name the single serialized writer of this repair")

    attempts = spec.get("repair_attempts_used", 0)
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
        errors.append("repair_attempts_used must be a non-negative integer when provided")
    elif attempts >= MAX_REPAIR_ATTEMPTS:
        errors.append(
            f"repair_attempts_used={attempts} has exhausted the acceptance-recovery budget "
            f"({MAX_REPAIR_ATTEMPTS}); park per the classification contract instead of re-dispatching"
        )

    review = spec.get("re_review")
    if not _exact_keys(review, REVIEW_KEYS, "re_review", errors):
        pass
    else:
        for field in sorted(REVIEW_KEYS):
            if _missing(review.get(field)):
                errors.append(f"re_review.{field} is required and cannot be a placeholder")
        if (
            isinstance(review.get("worker_dispatch_id"), str)
            and isinstance(review.get("reviewer_dispatch_id"), str)
            and _norm(review["worker_dispatch_id"]) == _norm(review["reviewer_dispatch_id"])
        ):
            errors.append("re_review self-review: worker and reviewer dispatch ids must differ")
        if (
            isinstance(review.get("worker_session_id"), str)
            and isinstance(review.get("reviewer_session_id"), str)
            and _norm(review["worker_session_id"]) == _norm(review["reviewer_session_id"])
        ):
            errors.append("re_review self-review: worker and reviewer session ids must differ")

    return {
        "pr": str(pr).strip() if isinstance(pr, str) else "",
        "branch": str(branch).strip() if isinstance(branch, str) else "",
        "head_sha": head_sha.strip().casefold() if isinstance(head_sha, str) else "",
        "blocker_ids": [str(entry.get("id", "")).strip() for entry in blockers if isinstance(entry, dict) and not _missing(entry.get("id"))],
        "owner": str(spec.get("repair_owner", "")).strip(),
        "attempts_used": attempts if isinstance(attempts, int) and not isinstance(attempts, bool) else 0,
    }


def load_registry(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    records = _load_json(path, "registry", errors)
    if not isinstance(records, list):
        errors.append("registry must be a JSON array of repair records")
        return []
    normalized: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        prefix = f"registry[{index}]"
        if not isinstance(record, dict) or not REGISTRY_REQUIRED_KEYS.issubset(record):
            errors.append(f"{prefix} must be an object with keys {sorted(REGISTRY_REQUIRED_KEYS)}")
            continue
        unsupported = sorted(set(record) - REGISTRY_KEYS)
        if unsupported:
            errors.append(f"{prefix} has unsupported fields: {unsupported}")
        if record.get("status") not in REGISTRY_STATUSES:
            errors.append(f"{prefix}.status must be one of {sorted(REGISTRY_STATUSES)}")
        blocker_ids = record.get("blocker_ids")
        if not isinstance(blocker_ids, list) or not all(isinstance(item, str) for item in blocker_ids):
            errors.append(f"{prefix}.blocker_ids must be an array of strings")
        normalized.append(record)
    return normalized


def registry_errors(summary: dict[str, Any], records: list[dict[str, Any]], errors: list[str]) -> None:
    if not summary:
        return
    for index, record in enumerate(records):
        prefix = f"registry[{index}]"
        status = record.get("status")
        if record.get("pr") == summary["pr"] and str(record.get("head_sha", "")).strip().casefold() == summary["head_sha"] and status != "superseded":
            errors.append(
                f"{prefix}: duplicate repair — a record for {summary['pr']} at the same pinned "
                "head already exists; re-pin the moved head in a fresh contract instead"
            )
        if status != "active" or record.get("pr") != summary["pr"]:
            continue
        if _norm(str(record.get("owner", ""))) != _norm(summary["owner"]):
            errors.append(
                f"{prefix}: serialized owner violation — active repair for {summary['pr']} "
                f"is held by '{record.get('owner')}', not '{summary['owner']}'"
            )
        existing_ids = {_norm(item) for item in record.get("blocker_ids") or [] if isinstance(item, str)}
        overlap = sorted({item for item in summary["blocker_ids"] if _norm(item) in existing_ids})
        if overlap:
            errors.append(
                f"{prefix}: duplicate repair — blockers already covered by an active repair: {overlap}"
            )


def preflight(spec: Any, records: list[dict[str, Any]], now: datetime) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    summary = validate_contract(spec, now, errors)
    if summary and not errors:
        registry_errors(summary, records, errors)
    report = {
        "mode": "preflight",
        "pr": summary.get("pr"),
        "pinned_head": summary.get("head_sha"),
        "blocker_ids": summary.get("blocker_ids"),
        "registry_records": len(records),
    }
    return errors, report


# ---------------------------------------------------------------------------
# postflight：diff 实证 + head 绑定 + blocker 解决证据
# ---------------------------------------------------------------------------


def _resolve_git_head(repo: str, head: str, errors: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", repo, "rev-parse", "--verify", f"{head}^{{commit}}"],
            check=False, capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        errors.append(f"git rev-parse failed: {exc}")
        return None
    if result.returncode != 0:
        errors.append(f"head does not resolve to a commit: {head}")
        return None
    resolved = result.stdout.strip().casefold()
    if not HEAD_SHA_RE.match(resolved):
        errors.append(f"resolved head is not a 40-hex commit: {head}")
        return None
    return resolved


def _git_is_ancestor(repo: str, ancestor: str, descendant: str, errors: list[str]) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", repo, "merge-base", "--is-ancestor", ancestor, descendant],
            check=False, capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        errors.append(f"git merge-base failed: {exc}")
        return False
    if result.returncode not in (0, 1):
        errors.append(f"git merge-base failed: {result.stderr.strip() or result.stdout.strip()}")
        return False
    return result.returncode == 0


def _git_changed_paths(repo: str, base: str, head: str, errors: list[str]) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", repo, "diff", "--name-only", base, head],
            check=False, capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        errors.append(f"git diff failed: {exc}")
        return []
    if result.returncode != 0:
        errors.append(f"git diff failed: {result.stderr.strip() or result.stdout.strip()}")
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def _patch_changed_paths(patch: str, errors: list[str]) -> list[str]:
    if "diff --git " not in patch:
        errors.append("patch file contains no 'diff --git' headers")
        return []
    paths: list[str] = []
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            marker = " b/"
            position = line.rfind(marker)
            if position == -1:
                errors.append(f"unparsable diff header: {line}")
                continue
            paths.append(line[position + len(marker):].strip())
    return paths


def _scope_matches(scope: list[str], path: str) -> bool:
    for entry in scope:
        normalized = entry.strip().rstrip("/")
        if path == normalized or path.startswith(normalized + "/"):
            return True
    return False


def _evidence_errors(
    summary: dict[str, Any], evidence: Any, resolved_head: str | None,
    verification: list[str], errors: list[str],
) -> None:
    if not isinstance(evidence, dict):
        errors.append("evidence must be a JSON object")
        return
    verified_head = evidence.get("verified_head")
    if not isinstance(verified_head, str) or not HEAD_SHA_RE.match(verified_head.strip().casefold()):
        errors.append("evidence must record an immutable 40-hex verified_head")
    elif resolved_head is not None and verified_head.strip().casefold() != resolved_head:
        errors.append("evidence verified_head does not match the resolved delivery head")

    if str(evidence.get("repair_owner", "")).strip() != summary["owner"]:
        errors.append(
            f"evidence repair_owner must equal contract repair_owner '{summary['owner']}'"
        )

    resolved = evidence.get("resolved_blockers")
    if not isinstance(resolved, list):
        errors.append("evidence.resolved_blockers must be an array of {id, note} records")
        resolved = []
    resolved_ids: set[str] = set()
    for index, entry in enumerate(resolved):
        prefix = f"evidence.resolved_blockers[{index}]"
        if not isinstance(entry, dict) or _missing(entry.get("id")):
            errors.append(f"{prefix}.id is required")
            continue
        entry_id = _norm(str(entry["id"]))
        if entry_id in resolved_ids:
            errors.append(f"{prefix} duplicates an earlier resolved id")
        else:
            resolved_ids.add(entry_id)
        if _missing(entry.get("note")):
            errors.append(f"{prefix}.note is required and cannot be a placeholder")
    expected_ids = {_norm(item) for item in summary["blocker_ids"]}
    unresolved = sorted(expected_ids - resolved_ids)
    if unresolved:
        errors.append(f"unresolved blockers remain: {unresolved}")
    unknown = sorted(resolved_ids - expected_ids)
    if unknown:
        errors.append(f"resolved blocker ids not declared in the contract: {unknown}")

    executed = evidence.get("executed")
    if not isinstance(executed, list) or not executed:
        errors.append("verification evidence missing: executed[] with command/exit_code is required")
        return
    for command in verification:
        wanted = str(command).strip()
        match = next(
            (item for item in executed if isinstance(item, dict) and str(item.get("command", "")).strip() == wanted),
            None,
        )
        if match is None:
            errors.append(f"verification evidence missing for command: {wanted}")
        elif match.get("exit_code") != 0:
            errors.append(f"verification command failed (exit_code={match.get('exit_code')}): {wanted}")


def postflight(
    spec: Any, records: list[dict[str, Any]], evidence: Any, now: datetime,
    changed: list[str], resolved_head: str | None, ancestry_verified: bool,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    summary = validate_contract(spec, now, errors)
    registry_errors(summary, records, errors)
    if errors:
        return errors, {"mode": "postflight", "changed_paths": changed}

    if resolved_head is None:
        errors.append("delivery head must resolve to an immutable 40-hex commit")
    else:
        if resolved_head == summary["head_sha"]:
            errors.append(
                "delivery head equals the pinned target head: a repair must actually "
                "change the pinned PR branch"
            )
        if not ancestry_verified:
            errors.append(
                "head drift: cannot prove the delivery descends from the pinned target "
                "head (git mode with --repo/--base/--head is required for ancestry proof)"
            )

    if not changed:
        errors.append("zero diff: a docs acceptance repair must change at least one scoped document")
    outside = [path for path in changed if not _scope_matches(spec["file_scope"], path)]
    if outside:
        errors.append(f"changed paths outside the declared file_scope: {outside}")
    non_docs = [path for path in changed if path not in outside and not is_document_path(path)]
    if non_docs:
        errors.append(
            "non-document changes are implementation value and rejected by this "
            f"docs-only channel: {non_docs}"
        )

    _evidence_errors(summary, evidence, resolved_head, spec["verification_commands"], errors)

    report = {
        "mode": "postflight",
        "pr": summary["pr"],
        "pinned_head": summary["head_sha"],
        "delivery_head": resolved_head,
        "ancestry_verified": ancestry_verified,
        "changed_paths": changed,
        "resolved_blockers": summary["blocker_ids"],
    }
    return errors, report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    pre = sub.add_parser("preflight", help="派发前机械校验修复合同")
    pre.add_argument("--spec", type=Path, required=True)
    pre.add_argument("--registry", type=Path, required=True)
    pre.add_argument("--now", help="RFC3339 evaluation time for deterministic tests")

    post = sub.add_parser("postflight", help="交付后机械校验修复 diff 与证据")
    post.add_argument("--spec", type=Path, required=True)
    post.add_argument("--registry", type=Path, required=True)
    post.add_argument("--evidence", type=Path, required=True)
    post.add_argument("--repo", help="Git repository for base/head diff inspection")
    post.add_argument("--base", help="base revision (with --repo/--head)")
    post.add_argument("--head", help="head revision (with --repo/--head)")
    post.add_argument("--diff", type=Path, help="unified diff / patch file to inspect instead")
    post.add_argument("--delivery-head", help="immutable 40-hex delivery revision (patch mode)")
    post.add_argument("--now", help="RFC3339 evaluation time for deterministic tests")
    return parser


def main() -> int:
    args = _parser().parse_args()
    errors: list[str] = []
    try:
        now = _parse_time(args.now) if args.now else datetime.now(timezone.utc)
    except ValueError as exc:
        print(json.dumps({"ok": False, "errors": [f"invalid --now: {exc}"]}, ensure_ascii=False))
        return EXIT_REJECTED

    spec = _load_json(args.spec, "spec", errors)
    records = load_registry(args.registry, errors)

    if args.command == "preflight":
        rejection_errors, report = preflight(spec, records, now)
        errors.extend(rejection_errors)
    else:
        evidence = _load_json(args.evidence, "evidence", errors)
        diff_sources = [bool(args.repo), bool(args.base), bool(args.head)]
        if any(diff_sources) and not all(diff_sources):
            errors.append("--repo, --base and --head must be supplied together")
        if args.diff and any(diff_sources):
            errors.append("use either --diff or --repo/--base/--head, not both")
        if not args.diff and not all(diff_sources):
            errors.append("a diff source is required: --diff or --repo/--base/--head")

        changed: list[str] = []
        resolved_head: str | None = None
        ancestry_verified = False
        if args.diff is not None:
            if args.delivery_head is None:
                errors.append("--delivery-head (immutable 40-hex delivery revision) is required in patch mode")
            elif not isinstance(args.delivery_head, str) or not HEAD_SHA_RE.match(args.delivery_head.strip().casefold()):
                errors.append("--delivery-head must be an immutable 40-hex revision")
            else:
                resolved_head = args.delivery_head.strip().casefold()
            try:
                changed = _patch_changed_paths(args.diff.read_text(encoding="utf-8", errors="replace"), errors)
            except OSError as exc:
                errors.append(f"patch unreadable: {exc}")
        elif args.repo is not None and all(diff_sources):
            resolved_head = _resolve_git_head(args.repo, args.head, errors)
            changed = _git_changed_paths(args.repo, args.base, args.head, errors)
            pinned = (spec or {}).get("target", {}).get("head_sha") if isinstance(spec, dict) else None
            if resolved_head is not None and isinstance(pinned, str) and HEAD_SHA_RE.match(pinned.strip().casefold()):
                ancestry_verified = _git_is_ancestor(args.repo, pinned.strip().casefold(), resolved_head, errors)

        rejection_errors, report = postflight(
            spec, records, evidence, now, changed, resolved_head, ancestry_verified,
        )
        errors.extend(rejection_errors)

    print(json.dumps({"ok": not errors, "errors": errors, "report": report}, ensure_ascii=False))
    return 0 if not errors else EXIT_REJECTED


if __name__ == "__main__":
    sys.exit(main())
