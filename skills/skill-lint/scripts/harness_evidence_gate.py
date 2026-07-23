#!/usr/bin/env python3
"""生成并验证与当前 Skill 候选绑定的 Harness 审查证据。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 2
REQUIRED_LAYERS = (
    "contract",
    "producer",
    "verifier",
    "evidence_binding",
    "fault_injection",
    "closure",
    "composition",
)
OPTIONAL_LAYERS = {"closure", "composition"}
REQUIRED_POLICY_FILES = (
    "SKILL.md",
    "references/harness-reliability-standards.md",
    "references/workflow-output-standards.md",
    "references/business-flow-rubric.md",
    "references/reporting-standards.md",
)
SKIP_DIRS = {".git", "archive", "__pycache__", ".pytest_cache"}
RUNTIME_SUFFIXES = {
    "python3": {".py"},
    "bash": {".sh"},
    "sh": {".sh"},
    "node": {".js", ".mjs", ".cjs"},
}
CHECK_FIELDS = {"id", "runtime", "checker", "args", "timeout_seconds"}
FAULT_FIELDS = CHECK_FIELDS | {"target", "expected_exit_code"}
PASSTHROUGH_ENV_KEYS = (
    "PATH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
)


class GateError(Exception):
    """审查证据不满足门禁。"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_resolve(root: Path, relative: str, label: str) -> Path:
    raw = Path(relative)
    if raw.is_absolute() or not relative or ".." in raw.parts:
        raise GateError(f"{label} 路径非法: {relative!r}")
    root_resolved = root.resolve()
    target = root_resolved.joinpath(raw)
    if target.is_symlink():
        raise GateError(f"{label} 不允许符号链接: {relative}")
    resolved = target.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise GateError(f"{label} 越出根目录: {relative}") from exc
    return resolved


def discover_candidate_files(root: Path) -> list[dict[str, str]]:
    root = root.resolve()
    if not root.is_dir() or not (root / "SKILL.md").is_file():
        raise GateError(f"候选目录不存在或缺少 SKILL.md: {root}")

    manifest: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        if path.is_symlink():
            raise GateError(f"候选范围内不允许符号链接: {relative.as_posix()}")
        if not path.is_file() or path.suffix == ".pyc" or ".local." in path.name:
            continue
        manifest.append({"path": relative.as_posix(), "sha256": sha256_file(path)})

    if not manifest:
        raise GateError("候选文件清单为空")
    return manifest


def policy_manifest(policy_root: Path) -> list[dict[str, str]]:
    for relative in REQUIRED_POLICY_FILES:
        path = safe_resolve(policy_root, relative, "策略文件")
        if not path.is_file():
            raise GateError(f"策略文件不存在: {relative}")
    return discover_candidate_files(policy_root)


def policy_version(policy_root: Path) -> str:
    skill_file = safe_resolve(policy_root, "SKILL.md", "策略文件")
    match = re.search(
        r'^version:\s*["\']?([^"\'\s]+)["\']?\s*$',
        skill_file.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    if not match:
        raise GateError("策略 SKILL.md 缺少可识别的 version")
    return match.group(1)


def aggregate_digest(manifest: list[dict[str, str]]) -> str:
    payload = "".join(f"{item['path']}\0{item['sha256']}\n" for item in manifest)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def require_exact_manifest(
    actual: list[dict[str, str]], recorded: Any, label: str
) -> None:
    if not isinstance(recorded, list) or not recorded:
        raise GateError(f"{label}为空或格式错误")
    if recorded != actual:
        raise GateError(f"{label}与当前文件不一致，证据已陈旧或范围不完整")


def validate_case_shape(
    entry: Any,
    expected_fields: set[str],
    seen_ids: set[str],
    label: str,
) -> dict[str, Any]:
    if not isinstance(entry, dict) or set(entry) != expected_fields:
        raise GateError(f"{label}字段缺失或包含自报结果/未知字段")
    case_id = entry.get("id")
    if not isinstance(case_id, str) or not case_id.strip() or case_id in seen_ids:
        raise GateError(f"{label}的 id 缺失或重复")
    seen_ids.add(case_id)
    runtime = entry.get("runtime")
    if runtime not in RUNTIME_SUFFIXES:
        raise GateError(f"{label}使用未知 runtime: {runtime!r}")
    checker = entry.get("checker")
    if not isinstance(checker, str) or not checker.strip():
        raise GateError(f"{label}缺少 checker")
    args = entry.get("args")
    if (
        not isinstance(args, list)
        or len(args) > 64
        or any(
            not isinstance(arg, str) or "\0" in arg or len(arg) > 4096
            for arg in args
        )
    ):
        raise GateError(f"{label}的 args 格式错误")
    timeout = entry.get("timeout_seconds")
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 600:
        raise GateError(f"{label}的 timeout_seconds 必须在 1—600 之间")
    return entry


def validate_review(review: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(review, dict):
        raise GateError("review 缺失或格式错误")
    if set(review) != {"layers", "hard_findings", "checks", "fault_cases", "overall"}:
        raise GateError("review 字段缺失或包含未知自报字段")

    layers = review.get("layers")
    if not isinstance(layers, dict) or set(layers) != set(REQUIRED_LAYERS):
        raise GateError("七层可靠性结论缺失或包含未知层")
    for name in REQUIRED_LAYERS:
        value = layers[name]
        if not isinstance(value, dict) or set(value) != {"status", "rationale"}:
            raise GateError(f"层 {name} 的结论格式错误")
        status = value.get("status")
        rationale = value.get("rationale", "")
        if status == "pass":
            if not isinstance(rationale, str) or len(rationale.strip()) < 5:
                raise GateError(f"层 {name} 的通过依据过短")
        elif status == "not_applicable" and name in OPTIONAL_LAYERS:
            if not isinstance(rationale, str) or len(rationale.strip()) < 10:
                raise GateError(f"层 {name} 标记不适用时必须说明边界")
        else:
            raise GateError(f"层 {name} 未通过: {status!r}")

    findings = review.get("hard_findings")
    if findings != []:
        raise GateError("仍有未关闭的 Hard Fail")

    checks = review.get("checks")
    if not isinstance(checks, list) or not checks:
        raise GateError("至少需要一项真实执行检查")
    seen_ids: set[str] = set()
    for index, check in enumerate(checks, 1):
        validate_case_shape(check, CHECK_FIELDS, seen_ids, f"检查 #{index}")

    fault_cases = review.get("fault_cases")
    if not isinstance(fault_cases, list) or not fault_cases:
        raise GateError("至少需要一个故障注入或逃逸反例")
    seen_faults: set[str] = set()
    for index, case in enumerate(fault_cases, 1):
        case = validate_case_shape(
            case, FAULT_FIELDS, seen_faults, f"故障用例 #{index}"
        )
        case_id = case["id"]
        if not isinstance(case.get("target"), str) or not case["target"].strip():
            raise GateError(f"故障用例 {case_id} 缺少目标失效描述")
        expected_exit = case.get("expected_exit_code")
        if (
            not isinstance(expected_exit, int)
            or isinstance(expected_exit, bool)
            or not 1 <= expected_exit <= 255
        ):
            raise GateError(f"故障用例 {case_id} 必须声明 1—255 的预期退出码")

    if review.get("overall") != "pass":
        raise GateError("overall 不是 pass")
    return checks, fault_cases


def run_case(
    entry: dict[str, Any],
    candidate_root: Path,
    manifest_paths: set[str],
    expected_exit_code: int,
    label: str,
) -> dict[str, Any]:
    checker_relative = entry["checker"]
    if checker_relative not in manifest_paths:
        raise GateError(f"{label} checker 不在候选清单: {checker_relative}")
    checker = safe_resolve(candidate_root, checker_relative, f"{label} checker")
    if not checker.is_file():
        raise GateError(f"{label} checker 不存在: {checker_relative}")
    runtime = entry["runtime"]
    if checker.suffix.lower() not in RUNTIME_SUFFIXES[runtime]:
        raise GateError(
            f"{label} checker 后缀 {checker.suffix!r} 与 runtime {runtime!r} 不匹配"
        )

    command = [runtime, str(checker), *entry["args"]]
    environment = {
        key: os.environ[key] for key in PASSTHROUGH_ENV_KEYS if key in os.environ
    }
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        }
    )
    try:
        with tempfile.TemporaryDirectory(prefix="skill-lint-checker-") as temp_home:
            environment.update(
                {"HOME": temp_home, "TMPDIR": temp_home, "TEMP": temp_home, "TMP": temp_home}
            )
            completed = subprocess.run(
                command,
                cwd=candidate_root,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
                timeout=entry["timeout_seconds"],
                check=False,
                shell=False,
            )
    except FileNotFoundError as exc:
        raise GateError(f"{label} runtime 不可用: {runtime}") from exc
    except subprocess.TimeoutExpired as exc:
        raise GateError(f"{label}执行超时，不得视为通过或成功阻断") from exc

    output = completed.stdout + completed.stderr
    if not output.strip():
        raise GateError(f"{label}没有产生可审计输出")
    if completed.returncode != expected_exit_code:
        raise GateError(
            f"{label}退出码为 {completed.returncode}，预期 {expected_exit_code}"
        )
    output_hash = hashlib.sha256(output.encode("utf-8")).hexdigest()
    print(
        f"HARNESS_CHECK_EXECUTED id={entry['id']} exit_code={completed.returncode} "
        f"output_sha256={output_hash}"
    )
    return {
        "id": entry["id"],
        "checker": checker_relative,
        "runtime": runtime,
        "args": entry["args"],
        "exit_code": completed.returncode,
        "output_sha256": output_hash,
    }


def snapshot(args: argparse.Namespace) -> int:
    candidate_root = Path(args.candidate_root).resolve()
    policy_root = Path(args.policy_root).resolve()
    output = Path(args.output).resolve()
    try:
        output.relative_to(candidate_root)
    except ValueError:
        pass
    else:
        raise GateError("证据文件必须放在候选 Skill 目录之外")
    if output.exists():
        raise GateError("证据文件已存在；为避免覆盖，请使用新的输出路径")

    candidate = discover_candidate_files(candidate_root)
    policy = policy_manifest(policy_root)
    layers = {
        name: {"status": "pending", "rationale": ""} for name in REQUIRED_LAYERS
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "candidate": {
            "files": candidate,
            "aggregate_sha256": aggregate_digest(candidate),
        },
        "review_policy": {
            "skill_lint_version": policy_version(policy_root),
            "files": policy,
            "aggregate_sha256": aggregate_digest(policy),
        },
        "review": {
            "layers": layers,
            "hard_findings": ["待审查"],
            "checks": [],
            "fault_cases": [],
            "overall": "pending",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"HARNESS_REVIEW_SNAPSHOT {output}")
    return 0


def verify(args: argparse.Namespace) -> int:
    if not args.confirm_trusted_candidate:
        raise GateError(
            "动态 verify 只允许用户已确认的自有/可信候选；"
            "第三方未知候选应保持 NOT_VERIFIED 或先进入隔离环境"
        )
    candidate_root = Path(args.candidate_root).resolve()
    policy_root = Path(args.policy_root).resolve()
    evidence_path = Path(args.evidence).resolve()
    if not evidence_path.is_file():
        raise GateError(f"证据文件不存在: {evidence_path}")
    try:
        data = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"证据 JSON 无法读取: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise GateError("schema_version 不受支持")

    candidate = discover_candidate_files(candidate_root)
    candidate_record = data.get("candidate")
    if not isinstance(candidate_record, dict):
        raise GateError("candidate 记录缺失")
    require_exact_manifest(candidate, candidate_record.get("files"), "候选文件清单")
    if candidate_record.get("aggregate_sha256") != aggregate_digest(candidate):
        raise GateError("候选聚合哈希不匹配")

    policy = policy_manifest(policy_root)
    policy_record = data.get("review_policy")
    if not isinstance(policy_record, dict):
        raise GateError("review_policy 记录缺失")
    if policy_record.get("skill_lint_version") != policy_version(policy_root):
        raise GateError("skill-lint 版本不匹配")
    require_exact_manifest(policy, policy_record.get("files"), "策略文件清单")
    if policy_record.get("aggregate_sha256") != aggregate_digest(policy):
        raise GateError("策略聚合哈希不匹配")

    checks, fault_cases = validate_review(data.get("review"))
    manifest_paths = {item["path"] for item in candidate}
    executed: list[dict[str, Any]] = []
    for check in checks:
        executed.append(run_case(check, candidate_root, manifest_paths, 0, "检查"))
    for case in fault_cases:
        executed.append(
            run_case(
                case,
                candidate_root,
                manifest_paths,
                case["expected_exit_code"],
                "故障用例",
            )
        )

    candidate_after = discover_candidate_files(candidate_root)
    policy_after = policy_manifest(policy_root)
    if candidate_after != candidate:
        raise GateError("checker 修改了候选文件，验收结果无效")
    if policy_after != policy:
        raise GateError("checker 修改了审查策略，验收结果无效")
    print(
        "HARNESS_REVIEW_VERIFIED "
        f"candidate_sha256={aggregate_digest(candidate)} "
        f"policy_sha256={aggregate_digest(policy)} "
        f"executed={len(executed)}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    skill_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("snapshot", "verify"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--candidate-root", required=True)
        sub.add_argument("--policy-root", default=str(skill_root))
        if command == "snapshot":
            sub.add_argument("--output", required=True)
            sub.set_defaults(handler=snapshot)
        else:
            sub.add_argument("--evidence", required=True)
            sub.add_argument(
                "--confirm-trusted-candidate",
                action="store_true",
                help="确认候选为用户自有/已审查可信代码；这不是沙箱",
            )
            sub.set_defaults(handler=verify)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.handler(args)
    except GateError as exc:
        print(f"HARNESS_REVIEW_BLOCKED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
