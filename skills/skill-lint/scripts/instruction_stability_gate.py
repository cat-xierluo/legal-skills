#!/usr/bin/env python3
"""识别叙述型旧 Skill，并验证多轮真实产物的指令覆盖稳定性。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
RECEIPT_VERSION = 1
CONTRACT_PATH = "config/instruction-stability-contract.json"
SKIP_DIRS = {".git", "archive", "__pycache__", ".pytest_cache"}
STAGES = {"input", "source", "intermediate", "rendered", "final", "state"}
REQUIREMENT_MODALITIES = {
    "text": {"text", "schema", "semantic"},
    "schema": {"schema"},
    "coverage": {"schema", "semantic", "human"},
    "geometry": {"geometry", "render", "visual"},
    "appearance": {"render", "visual"},
    "semantic": {"semantic", "human"},
    "interaction": {"interaction", "e2e"},
    "state": {"state", "integration"},
    "security": {"security", "static", "sandbox"},
}
RUNTIME_SUFFIXES = {
    "python3": {".py"},
    "bash": {".sh"},
    "sh": {".sh"},
    "node": {".js", ".mjs", ".cjs"},
}
CASE_KINDS = {"positive", "fault", "historical", "mutation"}
COMPARISONS = {"exact", "set_equal", "numeric_tolerance"}
MEASUREMENT_TYPES = {"integer", "number", "boolean", "string", "string_set"}
MEASUREMENT_CONDITIONS = {"equals", "gte", "lte", "contains_all"}
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
ARTIFACT_PLACEHOLDER = re.compile(r"^\{artifact:([A-Za-z0-9][A-Za-z0-9._-]{0,127})\}$")
CONSTRAINT_MARKER = re.compile(
    r"<!--\s*skill-lint:constraint\s+([A-Za-z0-9][A-Za-z0-9._-]{0,127})\s*-->"
)
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
REQUIREMENT_WORDS = re.compile(
    r"(必须|不得|禁止|应当|务必|逐项|完整|验收|验证|完成|Hard\s*Fail|\bmust\b|\bshould\b|\bnever\b)",
    re.IGNORECASE,
)
VISUAL_WORDS = re.compile(
    r"(SVG|配图|颜色|定位|位置|重叠|遮挡|边界|几何|渲染|render|geometry|overlap)",
    re.IGNORECASE,
)
REVIEW_WORDS = re.compile(
    r"(审稿|审阅|review|内容质量|论证|维度|遗漏|语义|章节|术语|口吻)",
    re.IGNORECASE,
)
COMPLETION_WORDS = re.compile(
    r"(已完成|完成声明|声明完成|可交付|通过验收|VERIFIED|PASS|done)",
    re.IGNORECASE,
)
HARD_REQUIREMENT_WORDS = re.compile(
    r"(必须|不得|禁止|应当|务必|Hard\s*Fail|\bmust\b|\bshall\b|\bnever\b)",
    re.IGNORECASE,
)


class GateError(Exception):
    """稳定性合同或证据不满足门禁。"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def public_key_id(public_key: Path) -> str:
    return sha256_file(public_key)[:16]


def resolve_evaluator_public_key(
    raw_value: str, candidate_root: Path | None = None
) -> Path:
    raw = Path(raw_value).expanduser()
    if raw.is_symlink():
        raise GateError("evaluator public key 不允许符号链接")
    public_key = raw.resolve()
    if not public_key.is_file():
        raise GateError("evaluator public key 不存在")
    if candidate_root is not None:
        try:
            public_key.relative_to(candidate_root.resolve())
        except ValueError:
            pass
        else:
            raise GateError("evaluator public key 必须位于候选 Skill 目录之外")
    return public_key


def resolve_external_directory(
    raw_value: str, label: str, candidate_root: Path
) -> Path:
    raw = Path(raw_value).expanduser()
    if raw.is_symlink():
        raise GateError(f"{label}不允许符号链接")
    directory = raw.resolve()
    if not directory.is_dir():
        raise GateError(f"{label}不存在或不是目录")
    try:
        directory.relative_to(candidate_root.resolve())
    except ValueError:
        return directory
    raise GateError(f"{label}必须位于候选 Skill 目录之外")


def verify_evaluator_signature(
    data: dict[str, Any], label: str, public_key: Path
) -> dict[str, Any]:
    signature = data.get("signature")
    if not isinstance(signature, dict) or set(signature) != {
        "algorithm",
        "key_id",
        "value",
    }:
        raise GateError(f"{label}缺少 evaluator Ed25519 signature")
    if signature["algorithm"] != "ed25519":
        raise GateError(f"{label} signature algorithm 必须是 ed25519")
    if signature["key_id"] != public_key_id(public_key):
        raise GateError(f"{label} signature key_id 与受信公钥不匹配")
    try:
        signature_bytes = base64.b64decode(signature["value"], validate=True)
    except (TypeError, ValueError) as exc:
        raise GateError(f"{label} signature value 不是合法 base64") from exc
    if len(signature_bytes) != 64:
        raise GateError(f"{label} Ed25519 signature 长度非法")
    unsigned = {key: value for key, value in data.items() if key != "signature"}
    with tempfile.TemporaryDirectory(prefix="skill-lint-ed25519-") as temp_dir:
        payload_path = Path(temp_dir) / "payload.json"
        signature_path = Path(temp_dir) / "signature.bin"
        payload_path.write_bytes(canonical_json_bytes(unsigned))
        signature_path.write_bytes(signature_bytes)
        try:
            completed = subprocess.run(
                [
                    "openssl",
                    "pkeyutl",
                    "-verify",
                    "-rawin",
                    "-pubin",
                    "-inkey",
                    str(public_key),
                    "-sigfile",
                    str(signature_path),
                    "-in",
                    str(payload_path),
                ],
                env=minimal_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
                timeout=30,
                check=False,
                shell=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise GateError(f"{label} 无法调用 OpenSSL 验签: {exc}") from exc
    if completed.returncode != 0:
        raise GateError(f"{label} evaluator Ed25519 signature 无效")
    return unsigned


def safe_path(root: Path, relative: str, label: str) -> Path:
    if not isinstance(relative, str) or not relative or "\0" in relative:
        raise GateError(f"{label}路径为空或格式错误")
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts:
        raise GateError(f"{label}路径非法: {relative!r}")
    root = root.resolve()
    target = root.joinpath(raw)
    if target.is_symlink():
        raise GateError(f"{label}不允许符号链接: {relative}")
    resolved = target.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise GateError(f"{label}越出根目录: {relative}") from exc
    return resolved


def candidate_manifest(root: Path) -> list[dict[str, str]]:
    root = root.resolve()
    if not root.is_dir() or not (root / "SKILL.md").is_file():
        raise GateError(f"候选目录不存在或缺少 SKILL.md: {root}")
    files: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        if path.is_symlink():
            raise GateError(f"候选范围内不允许符号链接: {relative.as_posix()}")
        if not path.is_file() or path.suffix == ".pyc" or ".local." in path.name:
            continue
        files.append({"path": relative.as_posix(), "sha256": sha256_file(path)})
    if not files:
        raise GateError("候选文件清单为空")
    return files


def tree_manifest(root: Path) -> list[dict[str, str]]:
    root = root.resolve()
    if not root.is_dir():
        raise GateError(f"运行产物根目录不存在: {root}")
    files: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_symlink():
            raise GateError(f"运行产物不允许符号链接: {relative.as_posix()}")
        if path.is_file():
            files.append({"path": relative.as_posix(), "sha256": sha256_file(path)})
    if not files:
        raise GateError("运行产物范围为空")
    return files


def stage_artifacts(
    artifact_paths: dict[str, Path], staged_root: Path
) -> dict[str, Path]:
    staged: dict[str, Path] = {}
    for artifact_id, source in sorted(artifact_paths.items()):
        destination = staged_root / f"{secrets.token_hex(16)}{source.suffix}"
        shutil.copyfile(source, destination)
        staged[artifact_id] = destination
    return staged


def aggregate_digest(manifest: list[dict[str, str]]) -> str:
    payload = "".join(f"{item['path']}\0{item['sha256']}\n" for item in manifest)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_json(path: Path, label: str) -> Any:
    if not path.is_file():
        raise GateError(f"{label}不存在: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"{label}无法读取: {exc}") from exc


def frontmatter_identity(candidate_root: Path) -> dict[str, str]:
    text = (candidate_root / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise GateError("SKILL.md 缺少可识别 frontmatter")
    frontmatter = text[4:].split("\n---\n", 1)[0]
    identity: dict[str, str] = {}
    for key in ("name", "version"):
        match = re.search(
            rf"^{key}:\s*[\"']?([^\"'\n]+?)[\"']?\s*$",
            frontmatter,
            flags=re.MULTILINE,
        )
        if not match:
            raise GateError(f"SKILL.md frontmatter 缺少 {key}")
        identity[key] = match.group(1).strip()
    return identity


def exact_keys(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise GateError(f"{label}字段缺失或包含未知字段")
    return value


def require_id(value: Any, label: str, seen: set[str]) -> str:
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value) or value in seen:
        raise GateError(f"{label} id 缺失、非法或重复: {value!r}")
    seen.add(value)
    return value


def require_id_list(value: Any, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not SAFE_ID.fullmatch(item) for item in value)
        or len(set(value)) != len(value)
    ):
        raise GateError(f"{label}必须是非空、唯一的安全 id 列表")
    return value


def measurement_value_matches(value: Any, value_type: str) -> bool:
    if value_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if value_type == "number":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        )
    if value_type == "boolean":
        return isinstance(value, bool)
    if value_type == "string":
        return isinstance(value, str)
    return (
        isinstance(value, list)
        and all(isinstance(item, str) for item in value)
        and len(set(value)) == len(value)
    )


def measurement_passes(value: Any, definition: dict[str, Any]) -> bool:
    if not measurement_value_matches(value, definition["value_type"]):
        return False
    expected = definition["expected"]
    condition = definition["condition"]
    if condition == "equals":
        return value == expected
    if condition == "gte":
        return value >= expected
    if condition == "lte":
        return value <= expected
    return set(expected).issubset(set(value))


def resolve_contract(candidate_root: Path, contract_arg: str | None) -> Path:
    if contract_arg:
        raw = Path(contract_arg)
        contract = raw.resolve() if raw.is_absolute() else safe_path(
            candidate_root, contract_arg, "合同"
        )
    else:
        contract = safe_path(candidate_root, CONTRACT_PATH, "合同")
    try:
        contract.relative_to(candidate_root.resolve())
    except ValueError as exc:
        raise GateError("稳定性合同必须位于候选 Skill 目录内") from exc
    if contract.is_symlink():
        raise GateError("稳定性合同不允许符号链接")
    return contract


def requirement_source_text(text: str) -> str:
    """移除 Markdown 代码示例，避免把 marker 文档误当成真实硬约束。"""
    without_fences = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    return re.sub(r"`[^`\n]*`", "", without_fences)


def discover_constraint_markers(candidate_root: Path) -> dict[str, list[str]]:
    """读取候选内显式硬约束锚点，作为合同完整性差异审计的一侧。"""
    markers: dict[str, list[str]] = {}
    for path in sorted(candidate_root.rglob("*.md")):
        relative = path.relative_to(candidate_root)
        if any(part in SKIP_DIRS for part in relative.parts) or path.is_symlink():
            continue
        text = requirement_source_text(
            path.read_text(encoding="utf-8", errors="replace")
        )
        for marker in CONSTRAINT_MARKER.findall(text):
            markers.setdefault(marker, []).append(relative.as_posix())
    return markers


def validate_source_ref(candidate_root: Path, constraint_id: str, ref: str) -> None:
    if not isinstance(ref, str) or not ref.strip() or "#" not in ref:
        raise GateError(
            f"constraint {constraint_id} 的 source_ref 必须包含显式约束锚点"
        )
    source_file, anchor = ref.rsplit("#", 1)
    if anchor != constraint_id:
        raise GateError(
            f"constraint {constraint_id} 的 source_ref 锚点必须与 constraint id 相同"
        )
    source_path = safe_path(
        candidate_root, source_file, f"constraint {constraint_id} source_ref "
    )
    if not source_path.is_file():
        raise GateError(f"constraint {constraint_id} 的 source_ref 文件不存在")
    markers = CONSTRAINT_MARKER.findall(
        requirement_source_text(
            source_path.read_text(encoding="utf-8", errors="replace")
        )
    )
    if markers.count(constraint_id) != 1:
        raise GateError(
            f"constraint {constraint_id} 的 source_ref 未命中唯一显式锚点"
        )


def unanchored_hard_requirements(path: Path) -> list[int]:
    text = requirement_source_text(
        path.read_text(encoding="utf-8", errors="replace")
    )
    previous_nonempty = ""
    findings: list[int] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if HARD_REQUIREMENT_WORDS.search(line):
            current_markers = CONSTRAINT_MARKER.findall(line)
            previous_markers = CONSTRAINT_MARKER.findall(previous_nonempty)
            if len(current_markers) + len(previous_markers) != 1:
                findings.append(line_number)
        if stripped:
            previous_nonempty = stripped
    return findings


def discover_hard_requirement_sources(candidate_root: Path) -> set[str]:
    candidates = [candidate_root / "SKILL.md"]
    references = candidate_root / "references"
    if references.is_dir():
        candidates.extend(sorted(references.rglob("*.md")))
    discovered: set[str] = set()
    for path in candidates:
        if (
            path.is_file()
            and not path.is_symlink()
            and HARD_REQUIREMENT_WORDS.search(
                requirement_source_text(
                    path.read_text(encoding="utf-8", errors="replace")
                )
            )
        ):
            discovered.add(path.relative_to(candidate_root).as_posix())
    return discovered


def validate_contract(candidate_root: Path, data: Any) -> dict[str, Any]:
    data = exact_keys(
        data,
        {
            "schema_version",
            "skill",
            "producer",
            "artifacts",
            "checkers",
            "constraints",
            "cases",
            "stability",
        },
        "合同",
    )
    if data["schema_version"] != SCHEMA_VERSION:
        raise GateError("合同 schema_version 不受支持")

    skill = exact_keys(data["skill"], {"name", "version"}, "skill")
    if not all(isinstance(skill[key], str) and skill[key].strip() for key in skill):
        raise GateError("skill name/version 不能为空")
    if skill != frontmatter_identity(candidate_root):
        raise GateError("合同 skill name/version 与 SKILL.md frontmatter 不一致")

    producer = exact_keys(
        data["producer"], {"id", "implementation_paths"}, "producer"
    )
    producer_id = producer["id"]
    if not isinstance(producer_id, str) or not SAFE_ID.fullmatch(producer_id):
        raise GateError("producer id 非法")
    implementation_paths = producer["implementation_paths"]
    if (
        not isinstance(implementation_paths, list)
        or not implementation_paths
        or len(set(implementation_paths)) != len(implementation_paths)
        or any(not isinstance(path, str) or not path for path in implementation_paths)
    ):
        raise GateError("producer implementation_paths 非法")
    producer_manifest: list[dict[str, str]] = []
    for relative in sorted(implementation_paths):
        path = safe_path(candidate_root, relative, "producer implementation ")
        if not path.is_file():
            raise GateError(f"producer implementation 不存在: {relative}")
        producer_manifest.append(
            {"path": relative, "sha256": sha256_file(path)}
        )
    producer = {
        **producer,
        "manifest": producer_manifest,
        "sha256": aggregate_digest(producer_manifest),
    }

    artifact_ids: set[str] = set()
    artifacts: dict[str, dict[str, Any]] = {}
    if not isinstance(data["artifacts"], list) or not data["artifacts"]:
        raise GateError("artifacts 不能为空")
    for index, raw in enumerate(data["artifacts"], 1):
        item = exact_keys(raw, {"id", "stage", "required"}, f"artifact #{index}")
        item_id = require_id(item["id"], f"artifact #{index}", artifact_ids)
        if item["stage"] not in STAGES or not isinstance(item["required"], bool):
            raise GateError(f"artifact {item_id} 的 stage/required 非法")
        artifacts[item_id] = item

    checker_ids: set[str] = set()
    checkers: dict[str, dict[str, Any]] = {}
    if not isinstance(data["checkers"], list) or not data["checkers"]:
        raise GateError("checkers 不能为空")
    for index, raw in enumerate(data["checkers"], 1):
        item = exact_keys(
            raw,
            {
                "id",
                "kind",
                "modality",
                "artifact_stages",
                "independent_from_producer",
                "runtime",
                "implementation",
                "args",
                "timeout_seconds",
            },
            f"checker #{index}",
        )
        item_id = require_id(item["id"], f"checker #{index}", checker_ids)
        if item["kind"] != "active":
            raise GateError(f"checker {item_id} 必须是 active；人工语义判断不能冒充硬门禁")
        if item["modality"] not in set().union(*REQUIREMENT_MODALITIES.values()):
            raise GateError(f"checker {item_id} 使用未知 modality")
        stages = item["artifact_stages"]
        if (
            not isinstance(stages, list)
            or not stages
            or len(set(stages)) != len(stages)
            or any(stage not in STAGES for stage in stages)
        ):
            raise GateError(f"checker {item_id} 的 artifact_stages 非法")
        if item["independent_from_producer"] is not True:
            raise GateError(f"checker {item_id} 未与生产者独立")
        runtime = item["runtime"]
        implementation = item["implementation"]
        if runtime not in RUNTIME_SUFFIXES or not isinstance(implementation, str):
            raise GateError(f"checker {item_id} 的 runtime/implementation 非法")
        checker_path = safe_path(candidate_root, implementation, f"checker {item_id} ")
        if (
            not checker_path.is_file()
            or checker_path.suffix.lower() not in RUNTIME_SUFFIXES[runtime]
        ):
            raise GateError(f"checker {item_id} 的实现不存在或后缀与 runtime 不匹配")
        args = item["args"]
        if (
            not isinstance(args, list)
            or len(args) > 64
            or any(
                not isinstance(arg, str) or "\0" in arg or len(arg) > 4096
                for arg in args
            )
        ):
            raise GateError(f"checker {item_id} 的 args 非法")
        placeholder_stages: set[str] = set()
        for arg in args:
            match = ARTIFACT_PLACEHOLDER.fullmatch(arg)
            if arg.startswith("{artifact:") and not match:
                raise GateError(f"checker {item_id} 使用非法 artifact 占位符")
            if match:
                artifact_id = match.group(1)
                if artifact_id not in artifacts:
                    raise GateError(f"checker {item_id} 引用未知 artifact: {artifact_id}")
                if artifacts[artifact_id]["stage"] not in stages:
                    raise GateError(f"checker {item_id} 的参数与声明产物阶段不一致")
                placeholder_stages.add(artifacts[artifact_id]["stage"])
        if not set(stages).issubset(placeholder_stages):
            raise GateError(
                f"checker {item_id} 未通过 artifact 参数读取其声明的全部产物阶段"
            )
        timeout = item["timeout_seconds"]
        if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 600:
            raise GateError(f"checker {item_id} 的 timeout_seconds 必须在 1—600")
        checkers[item_id] = item

    constraint_ids: set[str] = set()
    constraints: dict[str, dict[str, Any]] = {}
    if not isinstance(data["constraints"], list) or not data["constraints"]:
        raise GateError("constraints 不能为空")
    for index, raw in enumerate(data["constraints"], 1):
        item = exact_keys(
            raw,
            {
                "id",
                "severity",
                "requirement_type",
                "stage",
                "source_refs",
                "checker_ids",
                "case_ids",
                "historical_failure_known",
            },
            f"constraint #{index}",
        )
        item_id = require_id(item["id"], f"constraint #{index}", constraint_ids)
        if item["severity"] not in {"hard", "warning"}:
            raise GateError(f"constraint {item_id} 的 severity 非法")
        requirement_type = item["requirement_type"]
        if requirement_type not in REQUIREMENT_MODALITIES or item["stage"] not in STAGES:
            raise GateError(f"constraint {item_id} 的 requirement_type/stage 非法")
        refs = item["source_refs"]
        if not isinstance(refs, list) or not refs:
            raise GateError(f"constraint {item_id} 缺少 source_refs")
        for ref in refs:
            validate_source_ref(candidate_root, item_id, ref)
        mapped_checkers = require_id_list(
            item["checker_ids"], f"constraint {item_id} checker_ids"
        )
        require_id_list(item["case_ids"], f"constraint {item_id} case_ids")
        if not isinstance(item["historical_failure_known"], bool):
            raise GateError(f"constraint {item_id} historical_failure_known 必须为布尔值")
        for checker_id in mapped_checkers:
            if checker_id not in checkers:
                raise GateError(f"constraint {item_id} 引用未知 checker: {checker_id}")
            checker = checkers[checker_id]
            if checker["modality"] not in REQUIREMENT_MODALITIES[requirement_type]:
                raise GateError(
                    f"constraint {item_id} 的 {requirement_type} 约束不能由 "
                    f"{checker['modality']} 模态验证"
                )
            if item["stage"] not in checker["artifact_stages"]:
                raise GateError(
                    f"constraint {item_id} 要求检查 {item['stage']}，"
                    f"checker {checker_id} 未覆盖该产物阶段"
                )
        constraints[item_id] = item

    hard_constraint_ids = {
        constraint_id
        for constraint_id, item in constraints.items()
        if item["severity"] == "hard"
    }
    markers = discover_constraint_markers(candidate_root)
    duplicate_markers = {
        constraint_id: paths
        for constraint_id, paths in markers.items()
        if len(paths) != 1
    }
    if duplicate_markers:
        raise GateError(f"显式约束锚点必须全局唯一: {duplicate_markers}")
    if set(markers) != hard_constraint_ids:
        missing_from_contract = sorted(set(markers) - hard_constraint_ids)
        missing_from_sources = sorted(hard_constraint_ids - set(markers))
        raise GateError(
            "硬约束锚点与合同不完整映射；"
            f"合同漏项={missing_from_contract}，来源漏锚点={missing_from_sources}"
        )

    case_ids: set[str] = set()
    cases: dict[str, dict[str, Any]] = {}
    if not isinstance(data["cases"], list) or not data["cases"]:
        raise GateError("cases 不能为空")
    for index, raw in enumerate(data["cases"], 1):
        item = exact_keys(
            raw,
            {
                "id",
                "kind",
                "constraint_ids",
                "checker_ids",
                "artifacts",
                "expected",
                "expected_exit_code",
            },
            f"case #{index}",
        )
        item_id = require_id(item["id"], f"case #{index}", case_ids)
        if item["kind"] not in CASE_KINDS or item["expected"] not in {"pass", "blocked"}:
            raise GateError(f"case {item_id} 的 kind/expected 非法")
        mapped_constraints = require_id_list(
            item["constraint_ids"], f"case {item_id} constraint_ids"
        )
        mapped_checkers = require_id_list(
            item["checker_ids"], f"case {item_id} checker_ids"
        )
        if any(value not in constraints for value in mapped_constraints):
            raise GateError(f"case {item_id} 引用未知 constraint")
        if any(value not in checkers for value in mapped_checkers):
            raise GateError(f"case {item_id} 引用未知 checker")
        for constraint_id in mapped_constraints:
            if not set(mapped_checkers).issubset(constraints[constraint_id]["checker_ids"]):
                raise GateError(
                    f"case {item_id} 的 checker 未映射到 constraint {constraint_id}"
                )
        if not isinstance(item["artifacts"], list) or not item["artifacts"]:
            raise GateError(f"case {item_id} 缺少 fixture artifacts")
        seen_case_artifacts: set[str] = set()
        fixture_paths: dict[str, str] = {}
        for artifact_index, artifact_raw in enumerate(item["artifacts"], 1):
            artifact = exact_keys(
                artifact_raw,
                {"artifact_id", "path"},
                f"case {item_id} artifact #{artifact_index}",
            )
            artifact_id = require_id(
                artifact["artifact_id"],
                f"case {item_id} artifact #{artifact_index}",
                seen_case_artifacts,
            )
            if artifact_id not in artifacts:
                raise GateError(f"case {item_id} 引用未知 artifact: {artifact_id}")
            fixture = safe_path(
                candidate_root, artifact["path"], f"case {item_id} fixture "
            )
            if not fixture.is_file():
                raise GateError(f"case {item_id} fixture 不存在: {artifact['path']}")
            fixture_paths[artifact_id] = artifact["path"]
        for checker_id in mapped_checkers:
            required_ids = {
                match.group(1)
                for arg in checkers[checker_id]["args"]
                if (match := ARTIFACT_PLACEHOLDER.fullmatch(arg))
            }
            if not required_ids.issubset(seen_case_artifacts):
                raise GateError(
                    f"case {item_id} 缺少 checker {checker_id} 所需 fixture artifact"
                )
        if item["kind"] == "positive" and item["expected"] != "pass":
            raise GateError(f"positive case {item_id} 必须预期 pass")
        if item["kind"] != "positive" and item["expected"] != "blocked":
            raise GateError(f"负向 case {item_id} 必须预期 blocked")
        if item["kind"] != "positive" and (
            len(mapped_constraints) != 1 or len(mapped_checkers) != 1
        ):
            raise GateError(
                f"负向 case {item_id} 必须只隔离一个 constraint 和一个 checker"
            )
        expected_exit = item["expected_exit_code"]
        if item["expected"] == "pass":
            if expected_exit != 0:
                raise GateError(f"positive case {item_id} 必须预期退出码 0")
        elif (
            not isinstance(expected_exit, int)
            or isinstance(expected_exit, bool)
            or not 1 <= expected_exit <= 255
        ):
            raise GateError(f"负向 case {item_id} 必须声明 1—255 的预期退出码")
        item["fixture_paths"] = fixture_paths
        cases[item_id] = item

    for constraint_id, constraint in constraints.items():
        declared = set(constraint["case_ids"])
        if any(case_id not in cases for case_id in declared):
            raise GateError(f"constraint {constraint_id} 引用未知 case")
        actual = {
            case_id for case_id, case in cases.items()
            if constraint_id in case["constraint_ids"]
        }
        if declared != actual:
            raise GateError(f"constraint {constraint_id} 与 cases 的双向映射不一致")
        kinds = {cases[case_id]["kind"] for case_id in declared}
        if constraint["severity"] == "hard":
            if "positive" not in kinds or not kinds.intersection({"fault", "mutation"}):
                raise GateError(f"hard constraint {constraint_id} 缺少正例或故障/变异反例")
            if constraint["historical_failure_known"] and "historical" not in kinds:
                raise GateError(f"constraint {constraint_id} 已知历史失效但未固化历史回归")

    stability = exact_keys(
        data["stability"],
        {"minimum_runs", "measurements", "observables"},
        "stability",
    )
    minimum_runs = stability["minimum_runs"]
    if not isinstance(minimum_runs, int) or isinstance(minimum_runs, bool) or minimum_runs < 3:
        raise GateError("minimum_runs 必须至少为 3")
    if not isinstance(stability["observables"], list) or not stability["observables"]:
        raise GateError("stability.observables 不能为空")
    observable_ids: set[str] = set()
    observables: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(stability["observables"], 1):
        item = exact_keys(
            raw,
            {
                "id",
                "checker_id",
                "constraint_ids",
                "comparison",
                "required",
                "tolerance",
            },
            f"observable #{index}",
        )
        item_id = require_id(item["id"], f"observable #{index}", observable_ids)
        if item["checker_id"] not in checkers:
            raise GateError(f"observable {item_id} 引用未知 checker")
        observable_constraints = require_id_list(
            item["constraint_ids"], f"observable {item_id} constraint_ids"
        )
        if any(value not in hard_constraint_ids for value in observable_constraints):
            raise GateError(f"observable {item_id} 只能映射已声明的 hard constraint")
        for constraint_id in observable_constraints:
            if item["checker_id"] not in constraints[constraint_id]["checker_ids"]:
                raise GateError(
                    f"observable {item_id} 的 checker 未映射到 constraint {constraint_id}"
                )
        if item["comparison"] not in COMPARISONS or item["required"] is not True:
            raise GateError(f"observable {item_id} 的 comparison/required 非法")
        tolerance = item["tolerance"]
        if item["comparison"] == "numeric_tolerance":
            if (
                not isinstance(tolerance, (int, float))
                or isinstance(tolerance, bool)
                or not math.isfinite(tolerance)
                or tolerance < 0
            ):
                raise GateError(f"observable {item_id} 需要非负有限 tolerance")
        elif tolerance is not None:
            raise GateError(f"observable {item_id} 仅 numeric_tolerance 可设置 tolerance")
        observables[item_id] = item

    constraints_without_observable = sorted(
        constraint_id
        for constraint_id in hard_constraint_ids
        if not any(
            constraint_id in observable["constraint_ids"]
            for observable in observables.values()
        )
    )
    if constraints_without_observable:
        raise GateError(
            "每条 hard constraint 至少需要一个 artifact-derived observable: "
            f"{constraints_without_observable}"
        )

    if not isinstance(stability["measurements"], list) or not stability["measurements"]:
        raise GateError("stability.measurements 不能为空")
    measurement_ids: set[str] = set()
    measurements: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(stability["measurements"], 1):
        item = exact_keys(
            raw,
            {
                "id",
                "checker_id",
                "constraint_id",
                "value_type",
                "condition",
                "expected",
            },
            f"measurement #{index}",
        )
        item_id = require_id(item["id"], f"measurement #{index}", measurement_ids)
        constraint_id = item["constraint_id"]
        checker_id = item["checker_id"]
        if constraint_id not in hard_constraint_ids:
            raise GateError(f"measurement {item_id} 引用未知 hard constraint")
        if checker_id not in constraints[constraint_id]["checker_ids"]:
            raise GateError(
                f"measurement {item_id} 的 checker 未映射到 constraint {constraint_id}"
            )
        value_type = item["value_type"]
        condition = item["condition"]
        if value_type not in MEASUREMENT_TYPES or condition not in MEASUREMENT_CONDITIONS:
            raise GateError(f"measurement {item_id} 的 type/condition 非法")
        if condition in {"gte", "lte"} and value_type not in {"integer", "number"}:
            raise GateError(f"measurement {item_id} 的数值条件与类型不匹配")
        if condition == "contains_all" and value_type != "string_set":
            raise GateError(f"measurement {item_id} 的 contains_all 需要 string_set")
        if condition == "equals" and not measurement_value_matches(
            item["expected"], value_type
        ):
            raise GateError(f"measurement {item_id} 的 expected 与类型不匹配")
        if condition in {"gte", "lte"} and not measurement_value_matches(
            item["expected"], value_type
        ):
            raise GateError(f"measurement {item_id} 的 expected 与类型不匹配")
        if condition == "contains_all" and not measurement_value_matches(
            item["expected"], "string_set"
        ):
            raise GateError(f"measurement {item_id} 的 expected 与类型不匹配")
        measurements[item_id] = item

    constraints_without_measurement = sorted(
        constraint_id
        for constraint_id in hard_constraint_ids
        if not any(
            item["constraint_id"] == constraint_id
            for item in measurements.values()
        )
    )
    if constraints_without_measurement:
        raise GateError(
            "每条 hard constraint 至少需要一个有类型和阈值的 measurement: "
            f"{constraints_without_measurement}"
        )

    checker_constraints = {
        checker_id: sorted(
            constraint_id for constraint_id, item in constraints.items()
            if checker_id in item["checker_ids"]
        )
        for checker_id in checkers
    }
    unused_checkers = sorted(
        checker_id for checker_id, mapped in checker_constraints.items() if not mapped
    )
    if unused_checkers:
        raise GateError(f"checker 未映射到任何 constraint: {unused_checkers}")
    checker_observables = {
        checker_id: sorted(
            observable_id for observable_id, item in observables.items()
            if item["checker_id"] == checker_id
        )
        for checker_id in checkers
    }
    checker_measurements = {
        checker_id: {
            constraint_id: sorted(
                measurement_id
                for measurement_id, item in measurements.items()
                if item["checker_id"] == checker_id
                and item["constraint_id"] == constraint_id
            )
            for constraint_id in checker_constraints[checker_id]
        }
        for checker_id in checkers
    }
    return {
        "raw": data,
        "artifacts": artifacts,
        "producer": producer,
        "checkers": checkers,
        "constraints": constraints,
        "cases": cases,
        "observables": observables,
        "measurements": measurements,
        "checker_constraints": checker_constraints,
        "checker_observables": checker_observables,
        "checker_measurements": checker_measurements,
        "minimum_runs": minimum_runs,
    }


def static_assessment(candidate_root: Path) -> dict[str, Any]:
    texts: list[str] = []
    for path in sorted(candidate_root.rglob("*.md")):
        relative = path.relative_to(candidate_root)
        if any(part in SKIP_DIRS for part in relative.parts) or path.is_symlink():
            continue
        texts.append(path.read_text(encoding="utf-8", errors="replace"))
    content = "\n".join(texts)
    findings = [
        {
            "id": "ISG-001",
            "severity": "hard",
            "message": "缺少机器可读的约束追踪合同，无法证明每条硬约束都有验证器、产物阶段和回归用例。",
        }
    ]
    if VISUAL_WORDS.search(content):
        findings.append(
            {
                "id": "ISG-002",
                "severity": "hard",
                "message": "检测到视觉/几何约束，但未证明使用 geometry/render/visual 模态检查真实渲染产物。",
            }
        )
    if REVIEW_WORDS.search(content):
        findings.append(
            {
                "id": "ISG-003",
                "severity": "hard",
                "message": "检测到多维审阅或语义任务，但没有至少三轮的逐约束覆盖与稳定观测证据。",
            }
        )
    if COMPLETION_WORDS.search(content):
        findings.append(
            {
                "id": "ISG-004",
                "severity": "hard",
                "message": "检测到完成/验证声明，但没有绑定多轮真实产物的稳定性回执。",
            }
        )
    scripts = [
        path.relative_to(candidate_root).as_posix()
        for path in sorted((candidate_root / "scripts").glob("*"))
        if path.is_file()
    ] if (candidate_root / "scripts").is_dir() else []
    if scripts:
        findings.append(
            {
                "id": "ISG-005",
                "severity": "hard",
                "message": "候选包含脚本，但缺少“约束 → checker → 产物阶段 → case”的可审计映射，不能用脚本数量代替覆盖证明。",
            }
        )
    return {
        "schema_version": 1,
        "status": "NOT_VERIFIED",
        "contract": CONTRACT_PATH,
        "requirement_signal_count": len(REQUIREMENT_WORDS.findall(content)),
        "scripts_found": scripts,
        "findings": findings,
    }


def new_output_path(raw_path: str | Path, label: str) -> Path:
    raw = Path(raw_path).expanduser()
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    if raw.parent.is_symlink():
        raise GateError(f"{label}父目录不允许符号链接")
    raw.parent.mkdir(parents=True, exist_ok=True)
    if raw.parent.is_symlink():
        raise GateError(f"{label}父目录不允许符号链接")
    if os.path.lexists(raw):
        raise GateError(f"{label}已存在；为保留审计历史，不允许覆盖")
    return raw.parent.resolve() / raw.name


def write_new_json(path: Path, payload: Any, label: str) -> None:
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise GateError(
            f"{label}已存在；为保留审计历史，不允许覆盖"
        ) from exc
    except OSError as exc:
        raise GateError(f"{label}无法安全创建: {exc}") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def validate_requirements_baseline(
    baseline_path: Path,
    candidate_root: Path,
    candidate_files: list[dict[str, str]],
    contract: dict[str, Any],
    public_key: Path,
) -> dict[str, Any]:
    if baseline_path.is_symlink():
        raise GateError("硬约束基线不允许符号链接")
    signed_data = load_json(baseline_path, "硬约束基线")
    signed_data = exact_keys(
        signed_data,
        {
            "schema_version",
            "candidate_sha256",
            "requirement_sources",
            "requirement_exclusions",
            "hard_constraints",
            "signature",
        },
        "硬约束基线",
    )
    data = verify_evaluator_signature(signed_data, "硬约束基线", public_key)
    if data["schema_version"] != SCHEMA_VERSION:
        raise GateError("硬约束基线 schema_version 不受支持")
    candidate_sha256 = aggregate_digest(candidate_files)
    if data["candidate_sha256"] != candidate_sha256:
        raise GateError("硬约束基线未绑定当前完整候选")
    if not isinstance(data["hard_constraints"], list) or not data["hard_constraints"]:
        raise GateError("硬约束基线 hard_constraints 不能为空")
    sources = data["requirement_sources"]
    if (
        not isinstance(sources, list)
        or not sources
        or any(not isinstance(source, str) or not source for source in sources)
        or len(set(sources)) != len(sources)
    ):
        raise GateError("硬约束基线 requirement_sources 非法")
    source_set = set(sources)
    exclusions_raw = data["requirement_exclusions"]
    if not isinstance(exclusions_raw, list):
        raise GateError("硬约束基线 requirement_exclusions 必须是列表")
    exclusion_paths: set[str] = set()
    for index, raw in enumerate(exclusions_raw, 1):
        exclusion = exact_keys(
            raw, {"path", "rationale"}, f"requirement exclusion #{index}"
        )
        path = exclusion["path"]
        rationale = exclusion["rationale"]
        if (
            not isinstance(path, str)
            or not path
            or path in exclusion_paths
            or not isinstance(rationale, str)
            or len(rationale.strip()) < 10
        ):
            raise GateError(f"requirement exclusion #{index} 格式非法")
        safe_path(candidate_root, path, "requirement exclusion ")
        exclusion_paths.add(path)
    if source_set.intersection(exclusion_paths):
        raise GateError("requirement source 与 exclusion 不得重叠")
    discovered_sources = discover_hard_requirement_sources(candidate_root)
    if source_set.union(exclusion_paths) != discovered_sources:
        raise GateError(
            "requirement_sources/exclusions 未完整枚举候选中含硬要求信号的 "
            f"SKILL/references 文件；发现={sorted(discovered_sources)}"
        )
    referenced_sources = {
        ref.rsplit("#", 1)[0]
        for item in contract["constraints"].values()
        if item["severity"] == "hard"
        for ref in item["source_refs"]
    }
    if not referenced_sources.issubset(source_set):
        raise GateError("硬约束基线漏列合同引用的 requirement source")
    for source in sources:
        source_path = safe_path(
            candidate_root, source, "硬约束基线 requirement source "
        )
        if not source_path.is_file():
            raise GateError(f"requirement source 不存在: {source}")
        unanchored = unanchored_hard_requirements(source_path)
        if unanchored:
            raise GateError(
                f"requirement source {source} 存在未加唯一 constraint marker "
                f"的硬要求行: {unanchored}"
            )
    seen: set[str] = set()
    actual: dict[str, list[str]] = {}
    for index, raw in enumerate(data["hard_constraints"], 1):
        item = exact_keys(raw, {"id", "source_refs"}, f"基线 constraint #{index}")
        constraint_id = require_id(item["id"], f"基线 constraint #{index}", seen)
        refs = item["source_refs"]
        if (
            not isinstance(refs, list)
            or not refs
            or any(not isinstance(ref, str) or not ref for ref in refs)
            or len(set(refs)) != len(refs)
        ):
            raise GateError(f"基线 constraint {constraint_id} source_refs 非法")
        actual[constraint_id] = sorted(refs)
    expected = {
        constraint_id: sorted(item["source_refs"])
        for constraint_id, item in contract["constraints"].items()
        if item["severity"] == "hard"
    }
    if actual != expected:
        raise GateError(
            "独立硬约束基线与合同不一致；不得遗漏或额外自报 hard constraint"
        )
    return {
        "sha256": sha256_file(baseline_path),
        "candidate_sha256": candidate_sha256,
        "hard_constraint_ids": sorted(actual),
    }


def validate_held_out_cases(
    manifest_path: Path,
    held_out_root: Path,
    candidate_files: list[dict[str, str]],
    contract: dict[str, Any],
    public_key: Path,
) -> dict[str, Any]:
    if manifest_path.is_symlink() or held_out_root.is_symlink():
        raise GateError("held-out manifest/root 不允许符号链接")
    signed_data = load_json(manifest_path, "held-out 用例清单")
    signed_data = exact_keys(
        signed_data,
        {"schema_version", "candidate_sha256", "cases", "signature"},
        "held-out 用例清单",
    )
    data = verify_evaluator_signature(
        signed_data, "held-out 用例清单", public_key
    )
    if data["schema_version"] != SCHEMA_VERSION:
        raise GateError("held-out 用例 schema_version 不受支持")
    if data["candidate_sha256"] != aggregate_digest(candidate_files):
        raise GateError("held-out 用例未绑定当前完整候选")
    if not isinstance(data["cases"], list) or not data["cases"]:
        raise GateError("held-out cases 不能为空")
    seen: set[str] = set()
    cases: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(data["cases"], 1):
        item = exact_keys(
            raw,
            {
                "id",
                "kind",
                "constraint_id",
                "checker_id",
                "artifacts",
                "expected_exit_code",
            },
            f"held-out case #{index}",
        )
        case_id = require_id(item["id"], f"held-out case #{index}", seen)
        if item["kind"] not in {"positive", "mutation", "historical"}:
            raise GateError(f"held-out case {case_id} kind 非法")
        constraint_id = item["constraint_id"]
        checker_id = item["checker_id"]
        constraint = contract["constraints"].get(constraint_id)
        if not constraint or constraint["severity"] != "hard":
            raise GateError(f"held-out case {case_id} 引用未知 hard constraint")
        if checker_id not in constraint["checker_ids"]:
            raise GateError(
                f"held-out case {case_id} checker 未映射到目标 constraint"
            )
        expected_exit = item["expected_exit_code"]
        if item["kind"] == "positive":
            if expected_exit != 0:
                raise GateError(f"held-out positive case {case_id} 必须退出 0")
        elif (
            not isinstance(expected_exit, int)
            or isinstance(expected_exit, bool)
            or not 1 <= expected_exit <= 255
        ):
            raise GateError(f"held-out negative case {case_id} 退出码非法")
        artifacts_raw = item["artifacts"]
        if not isinstance(artifacts_raw, list) or not artifacts_raw:
            raise GateError(f"held-out case {case_id} artifacts 不能为空")
        artifact_ids: set[str] = set()
        paths: dict[str, Path] = {}
        records: list[dict[str, str]] = []
        for artifact_index, artifact_raw in enumerate(artifacts_raw, 1):
            artifact = exact_keys(
                artifact_raw,
                {"artifact_id", "path", "sha256"},
                f"held-out case {case_id} artifact #{artifact_index}",
            )
            artifact_id = require_id(
                artifact["artifact_id"],
                f"held-out case {case_id} artifact #{artifact_index}",
                artifact_ids,
            )
            if artifact_id not in contract["artifacts"]:
                raise GateError(
                    f"held-out case {case_id} 引用未知 artifact: {artifact_id}"
                )
            path = safe_path(
                held_out_root, artifact["path"], f"held-out case {case_id} "
            )
            if not path.is_file() or sha256_file(path) != artifact["sha256"]:
                raise GateError(
                    f"held-out case {case_id} artifact 不存在或哈希不匹配"
                )
            paths[artifact_id] = path
            records.append(artifact)
        required_ids = {
            match.group(1)
            for arg in contract["checkers"][checker_id]["args"]
            if (match := ARTIFACT_PLACEHOLDER.fullmatch(arg))
        }
        if not required_ids.issubset(artifact_ids):
            raise GateError(
                f"held-out case {case_id} 缺少 checker 所需 artifact"
            )
        cases[case_id] = {
            **item,
            "artifact_paths": paths,
            "artifact_records": sorted(
                records, key=lambda value: value["artifact_id"]
            ),
        }
    hard_ids = {
        constraint_id
        for constraint_id, item in contract["constraints"].items()
        if item["severity"] == "hard"
    }
    for constraint_id in hard_ids:
        kinds = {
            item["kind"]
            for item in cases.values()
            if item["constraint_id"] == constraint_id
        }
        if "positive" not in kinds or not kinds.intersection(
            {"mutation", "historical"}
        ):
            raise GateError(
                f"hard constraint {constraint_id} 缺少 evaluator-signed "
                "held-out 正例或反例"
            )
    return {
        "sha256": sha256_file(manifest_path),
        "cases": cases,
    }


def verify_harness_review(
    candidate_root: Path,
    policy_root: Path,
    evidence_path: Path,
) -> dict[str, str]:
    if evidence_path.is_symlink():
        raise GateError("Harness 审查证据不允许符号链接")
    try:
        evidence_path.relative_to(candidate_root)
    except ValueError:
        pass
    else:
        raise GateError("Harness 审查证据必须位于候选 Skill 目录之外")
    gate = safe_path(
        policy_root, "scripts/harness_evidence_gate.py", "Harness 审查门禁 "
    )
    if not gate.is_file():
        raise GateError("policy-root 缺少 harness_evidence_gate.py")
    command = [
        "python3",
        str(gate),
        "verify",
        "--candidate-root",
        str(candidate_root),
        "--policy-root",
        str(policy_root),
        "--evidence",
        str(evidence_path),
        "--confirm-trusted-candidate",
    ]
    try:
        with tempfile.TemporaryDirectory(prefix="skill-lint-harness-") as temp_home:
            environment = minimal_environment()
            environment.update(
                {"HOME": temp_home, "TMPDIR": temp_home, "TEMP": temp_home, "TMP": temp_home}
            )
            completed = subprocess.run(
                command,
                cwd=policy_root,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
                timeout=900,
                check=False,
                shell=False,
            )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise GateError(f"Harness 审查门禁无法完成: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        raise GateError(
            "当前候选未取得可复算的 HARNESS_REVIEW_VERIFIED"
            + (f": {detail[-1]}" if detail else "")
        )
    marker = next(
        (
            line
            for line in reversed(completed.stdout.splitlines())
            if line.startswith("HARNESS_REVIEW_VERIFIED ")
        ),
        None,
    )
    if marker is None:
        raise GateError("Harness 审查门禁未返回可识别的 VERIFIED marker")
    match = re.fullmatch(
        r"HARNESS_REVIEW_VERIFIED candidate_sha256=([0-9a-f]{64}) "
        r"policy_sha256=([0-9a-f]{64}) executed=([1-9][0-9]*)",
        marker,
    )
    if not match:
        raise GateError("Harness VERIFIED marker 格式非法")
    return {
        "candidate_sha256": match.group(1),
        "policy_sha256": match.group(2),
        "executed": match.group(3),
        "evidence_sha256": sha256_file(evidence_path),
    }


def assess(args: argparse.Namespace) -> int:
    candidate_root = Path(args.candidate_root).resolve()
    candidate_files = candidate_manifest(candidate_root)
    contract_path = resolve_contract(candidate_root, args.contract)
    if contract_path.is_file():
        try:
            contract_data = load_json(contract_path, "稳定性合同")
            validated = validate_contract(candidate_root, contract_data)
            baseline_result: dict[str, Any] | None = None
            if args.requirements_baseline:
                if not args.evaluator_public_key:
                    raise GateError(
                        "验证硬约束基线必须提供 --evaluator-public-key"
                    )
                public_key = resolve_evaluator_public_key(
                    args.evaluator_public_key, candidate_root
                )
                baseline_raw = Path(args.requirements_baseline).expanduser()
                if baseline_raw.is_symlink():
                    raise GateError("硬约束基线不允许符号链接")
                baseline_path = baseline_raw.resolve()
                try:
                    baseline_path.relative_to(candidate_root)
                except ValueError:
                    pass
                else:
                    raise GateError("硬约束基线必须位于候选 Skill 目录之外")
                baseline_result = validate_requirements_baseline(
                    baseline_path,
                    candidate_root,
                    candidate_files,
                    validated,
                    public_key,
                )
            report = {
                "schema_version": 1,
                "status": "CONTRACT_READY" if baseline_result else "NOT_VERIFIED",
                "contract": contract_path.relative_to(candidate_root).as_posix(),
                "contract_sha256": sha256_file(contract_path),
                "hard_constraint_count": sum(
                    item["severity"] == "hard"
                    for item in validated["constraints"].values()
                ),
                "checker_count": len(validated["checkers"]),
                "minimum_runs": validated["minimum_runs"],
                "requirement_signal_count": static_assessment(candidate_root)[
                    "requirement_signal_count"
                ],
                "findings": (
                    []
                    if baseline_result
                    else [
                        {
                            "id": "ISG-006",
                            "severity": "hard",
                            "message": "合同存在，但缺少候选外独立硬约束基线，无法证明合同没有漏列规则。",
                        }
                    ]
                ),
                "requirements_baseline_sha256": (
                    baseline_result["sha256"] if baseline_result else None
                ),
                "message": (
                    "合同与独立硬约束基线已对齐，但尚未验证多轮真实产物。"
                    if baseline_result
                    else "合同结构已解析，但完整性尚未由候选外基线确认。"
                ),
            }
        except GateError as exc:
            report = static_assessment(candidate_root)
            report["contract"] = contract_path.relative_to(candidate_root).as_posix()
            report["contract_sha256"] = sha256_file(contract_path)
            report["findings"].append(
                {
                    "id": "ISG-007",
                    "severity": "hard",
                    "message": f"现有稳定性合同无效或可绕过：{exc}",
                }
            )
    else:
        report = static_assessment(candidate_root)
    if args.output:
        output = new_output_path(args.output, "评估报告")
        try:
            output.relative_to(candidate_root)
        except ValueError:
            pass
        else:
            raise GateError("评估报告必须放在候选 Skill 目录之外")
        write_new_json(output, report, "评估报告")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    print(f"INSTRUCTION_STABILITY_{report['status']}")
    return 2


def sign_evidence(args: argparse.Namespace) -> int:
    source = Path(args.input).resolve()
    data = load_json(source, "待签名 JSON")
    if not isinstance(data, dict) or "signature" in data:
        raise GateError("待签名 JSON 必须是尚无 signature 的对象")
    private_key_raw = Path(args.private_key).expanduser()
    if private_key_raw.is_symlink():
        raise GateError("evaluator private key 不存在或为符号链接")
    private_key = private_key_raw.resolve()
    if not private_key.is_file():
        raise GateError("evaluator private key 不存在或为符号链接")
    with tempfile.TemporaryDirectory(prefix="skill-lint-ed25519-sign-") as temp_dir:
        payload_path = Path(temp_dir) / "payload.json"
        signature_path = Path(temp_dir) / "signature.bin"
        public_key_path = Path(temp_dir) / "public.pem"
        payload_path.write_bytes(canonical_json_bytes(data))
        commands = [
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-rawin",
                "-inkey",
                str(private_key),
                "-in",
                str(payload_path),
                "-out",
                str(signature_path),
            ],
            [
                "openssl",
                "pkey",
                "-in",
                str(private_key),
                "-pubout",
                "-out",
                str(public_key_path),
            ],
        ]
        for command in commands:
            try:
                completed = subprocess.run(
                    command,
                    env=minimal_environment(),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    errors="replace",
                    timeout=30,
                    check=False,
                    shell=False,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                raise GateError(f"无法调用 OpenSSL 签名: {exc}") from exc
            if completed.returncode != 0:
                raise GateError(
                    "OpenSSL Ed25519 签名失败: "
                    + (completed.stderr.strip() or completed.stdout.strip())
                )
        signature_value = base64.b64encode(
            signature_path.read_bytes()
        ).decode("ascii")
        key_id = public_key_id(public_key_path)
    payload = {
        **data,
        "signature": {
            "algorithm": "ed25519",
            "key_id": key_id,
            "value": signature_value,
        },
    }
    output = new_output_path(args.output, "签名证据")
    write_new_json(output, payload, "签名证据")
    print(f"EVALUATOR_EVIDENCE_SIGNED {output}")
    return 0


def parse_run_evidence(
    data: Any,
    runs_root: Path,
    artifacts: dict[str, Any],
    candidate_sha256: str,
    producer: dict[str, Any],
    public_key: Path,
) -> list[dict[str, Any]]:
    data = exact_keys(data, {"schema_version", "evaluation_id", "runs"}, "运行证据")
    if data["schema_version"] != SCHEMA_VERSION:
        raise GateError("运行证据 schema_version 不受支持")
    if not isinstance(data["runs"], list) or not data["runs"]:
        raise GateError("runs 不能为空")
    evaluation_id = data["evaluation_id"]
    if not isinstance(evaluation_id, str) or not SAFE_ID.fullmatch(evaluation_id):
        raise GateError("运行证据 evaluation_id 非法")
    run_ids: set[str] = set()
    required_artifacts = {
        artifact_id for artifact_id, item in artifacts.items() if item["required"]
    }
    runs: list[dict[str, Any]] = []
    execution_nonces: set[str] = set()
    artifact_paths_seen: set[Path] = set()
    producer_logs_seen: set[Path] = set()
    common_input_sha256: str | None = None
    common_config_sha256: str | None = None
    for index, raw in enumerate(data["runs"], 1):
        item = exact_keys(
            raw,
            {
                "id",
                "execution_nonce",
                "input_sha256",
                "config_sha256",
                "producer_log",
                "artifacts",
            },
            f"run #{index}",
        )
        run_id = require_id(item["id"], f"run #{index}", run_ids)
        nonce = require_id(
            item["execution_nonce"], f"run {run_id} execution_nonce", execution_nonces
        )
        for key in ("input_sha256", "config_sha256"):
            if not isinstance(item[key], str) or not SHA256_HEX.fullmatch(item[key]):
                raise GateError(f"run {run_id} 的 {key} 必须是 SHA-256")
        if common_input_sha256 is None:
            common_input_sha256 = item["input_sha256"]
            common_config_sha256 = item["config_sha256"]
        elif (
            item["input_sha256"] != common_input_sha256
            or item["config_sha256"] != common_config_sha256
        ):
            raise GateError("多轮运行必须绑定相同 input_sha256 和 config_sha256")
        producer_log_relative = item["producer_log"]
        if (
            not isinstance(producer_log_relative, str)
            or not producer_log_relative.startswith(f"{run_id}/")
        ):
            raise GateError(f"run {run_id} producer_log 必须位于独立 run 目录")
        producer_log = safe_path(
            runs_root, producer_log_relative, f"run {run_id} producer_log "
        )
        if not producer_log.is_file():
            raise GateError(f"run {run_id} producer_log 不存在")
        if producer_log in producer_logs_seen:
            raise GateError("不同运行不得复用同一个 producer_log")
        producer_logs_seen.add(producer_log)
        if not isinstance(item["artifacts"], list) or not item["artifacts"]:
            raise GateError(f"run {run_id} artifacts 不能为空")
        seen_artifacts: set[str] = set()
        resolved: dict[str, Path] = {}
        records: list[dict[str, str]] = []
        for artifact_index, artifact_raw in enumerate(item["artifacts"], 1):
            artifact = exact_keys(
                artifact_raw, {"artifact_id", "path"},
                f"run {run_id} artifact #{artifact_index}",
            )
            artifact_id = require_id(
                artifact["artifact_id"],
                f"run {run_id} artifact #{artifact_index}",
                seen_artifacts,
            )
            if artifact_id not in artifacts:
                raise GateError(f"run {run_id} 引用未知 artifact: {artifact_id}")
            if not artifact["path"].startswith(f"{run_id}/"):
                raise GateError(
                    f"run {run_id} artifact 必须位于自己的独立 run 目录"
                )
            path = safe_path(runs_root, artifact["path"], f"run {run_id} artifact ")
            if not path.is_file():
                raise GateError(f"run {run_id} artifact 不存在: {artifact['path']}")
            if path in artifact_paths_seen:
                raise GateError("不同运行不得复用同一个 artifact 路径")
            artifact_paths_seen.add(path)
            resolved[artifact_id] = path
            records.append(
                {
                    "artifact_id": artifact_id,
                    "path": artifact["path"],
                    "sha256": sha256_file(path),
                }
            )
        if not required_artifacts.issubset(seen_artifacts):
            missing = sorted(required_artifacts - seen_artifacts)
            raise GateError(f"run {run_id} 缺少必需 artifact: {missing}")
        log_data = load_json(producer_log, f"run {run_id} producer_log")
        log_data = exact_keys(
            log_data,
            {
                "schema_version",
                "run_id",
                "execution_nonce",
                "input_sha256",
                "config_sha256",
                "candidate_sha256",
                "producer_id",
                "producer_sha256",
                "evaluation_id",
                "artifacts",
                "signature",
            },
            f"run {run_id} producer_log",
        )
        log_data = verify_evaluator_signature(
            log_data, f"run {run_id} producer_log", public_key
        )
        expected_log = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "execution_nonce": nonce,
            "input_sha256": item["input_sha256"],
            "config_sha256": item["config_sha256"],
            "candidate_sha256": candidate_sha256,
            "producer_id": producer["id"],
            "producer_sha256": producer["sha256"],
            "evaluation_id": evaluation_id,
            "artifacts": sorted(records, key=lambda value: value["artifact_id"]),
        }
        if log_data != expected_log:
            raise GateError(
                f"run {run_id} producer_log 与本轮输入、配置或真实产物不一致"
            )
        runs.append(
            {
                "id": run_id,
                "execution_nonce": nonce,
                "input_sha256": item["input_sha256"],
                "config_sha256": item["config_sha256"],
                "evaluation_id": evaluation_id,
                "producer_log": {
                    "path": producer_log_relative,
                    "sha256": sha256_file(producer_log),
                },
                "artifact_paths": resolved,
                "artifact_records": sorted(records, key=lambda value: value["artifact_id"]),
            }
        )
    return runs


def minimal_environment() -> dict[str, str]:
    environment = {
        key: os.environ[key] for key in PASSTHROUGH_ENV_KEYS if key in os.environ
    }
    environment.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"})
    return environment


def validate_measurement_output(
    value: Any,
    expected_constraints: list[str],
    expected_ids: dict[str, list[str]],
    definitions: dict[str, dict[str, Any]],
    require_pass: bool,
    label: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict) or sorted(value) != sorted(expected_constraints):
        raise GateError(f"{label}缺少逐约束 measurements")
    failed_conditions = 0
    for constraint_id in expected_constraints:
        measurements = value[constraint_id]
        measurement_ids = expected_ids[constraint_id]
        if not isinstance(measurements, dict) or sorted(measurements) != measurement_ids:
            raise GateError(
                f"{label}constraint {constraint_id} 的 measurement IDs 与合同不一致"
            )
        for measurement_id, observed in measurements.items():
            definition = definitions[measurement_id]
            if not measurement_value_matches(observed, definition["value_type"]):
                raise GateError(
                    f"{label}measurement {measurement_id} 的值类型不符合合同"
                )
            passed = measurement_passes(observed, definition)
            if require_pass and not passed:
                raise GateError(
                    f"{label}measurement {measurement_id} 未满足 "
                    f"{definition['condition']} {definition['expected']!r}"
                )
            if not passed:
                failed_conditions += 1
    if not require_pass and failed_conditions == 0:
        raise GateError(f"{label}负向用例没有违反目标 constraint 的 measurement 阈值")
    return value


def execute_checker(
    candidate_root: Path,
    checker: dict[str, Any],
    artifact_paths: dict[str, Path],
    expected_constraints: list[str],
    expected_observables: list[str],
    expected_measurements: dict[str, list[str]],
    measurement_definitions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    expected_artifact_sha256 = {
        artifact_id: sha256_file(path)
        for artifact_id, path in sorted(artifact_paths.items())
    }
    args: list[str] = []
    for arg in checker["args"]:
        match = ARTIFACT_PLACEHOLDER.fullmatch(arg)
        if match:
            artifact_id = match.group(1)
            if artifact_id not in artifact_paths:
                raise GateError(f"checker {checker['id']} 缺少运行 artifact: {artifact_id}")
            args.append(str(artifact_paths[artifact_id]))
        else:
            args.append(arg)
    implementation = safe_path(
        candidate_root, checker["implementation"], f"checker {checker['id']} "
    )
    command = [checker["runtime"], str(implementation), *args]
    try:
        with tempfile.TemporaryDirectory(prefix="skill-lint-stability-") as temp_home:
            environment = minimal_environment()
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
                timeout=checker["timeout_seconds"],
                check=False,
                shell=False,
            )
    except FileNotFoundError as exc:
        raise GateError(f"checker {checker['id']} runtime 不可用") from exc
    except subprocess.TimeoutExpired as exc:
        raise GateError(f"checker {checker['id']} 执行超时") from exc
    combined = completed.stdout + completed.stderr
    if {
        artifact_id: sha256_file(path)
        for artifact_id, path in sorted(artifact_paths.items())
    } != expected_artifact_sha256:
        raise GateError(f"checker {checker['id']} 修改了输入 artifact")
    if completed.returncode != 0:
        raise GateError(
            f"checker {checker['id']} 未通过，退出码 {completed.returncode}"
        )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise GateError(f"checker {checker['id']} 没有输出结构化结果")
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise GateError(f"checker {checker['id']} 最后一行不是 JSON") from exc
    payload = exact_keys(
        payload,
        {
            "passed_constraint_ids",
            "artifact_sha256",
            "measurements",
            "observables",
        },
        f"checker {checker['id']} 输出",
    )
    actual_constraints = payload["passed_constraint_ids"]
    if (
        not isinstance(actual_constraints, list)
        or any(
            not isinstance(item, str) or not SAFE_ID.fullmatch(item)
            for item in actual_constraints
        )
        or len(set(actual_constraints)) != len(actual_constraints)
    ):
        raise GateError(f"checker {checker['id']} 输出 passed_constraint_ids 格式非法")
    if sorted(actual_constraints) != expected_constraints:
        raise GateError(
            f"checker {checker['id']} 未逐项报告全部映射约束；"
            f"预期 {expected_constraints}，实际 {sorted(actual_constraints)}"
        )
    observables = payload["observables"]
    if not isinstance(observables, dict) or sorted(observables) != expected_observables:
        raise GateError(
            f"checker {checker['id']} 的 observables 与合同不一致；"
            f"预期 {expected_observables}"
        )
    if payload["artifact_sha256"] != expected_artifact_sha256:
        raise GateError(
            f"checker {checker['id']} 未绑定它实际读取的 artifact SHA-256"
        )
    measurements = validate_measurement_output(
        payload["measurements"],
        expected_constraints,
        expected_measurements,
        measurement_definitions,
        True,
        f"checker {checker['id']} ",
    )
    return {
        "checker_id": checker["id"],
        "passed_constraint_ids": sorted(actual_constraints),
        "artifact_sha256": expected_artifact_sha256,
        "measurements": measurements,
        "observables": observables,
        "exit_code": completed.returncode,
        "output_sha256": hashlib.sha256(combined.encode("utf-8")).hexdigest(),
    }


def execute_negative_case(
    candidate_root: Path,
    checker: dict[str, Any],
    artifact_paths: dict[str, Path],
    expected_exit_code: int,
    expected_constraints: list[str],
    expected_measurements: dict[str, list[str]],
    measurement_definitions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    expected_artifact_sha256 = {
        artifact_id: sha256_file(path)
        for artifact_id, path in sorted(artifact_paths.items())
    }
    args: list[str] = []
    for arg in checker["args"]:
        match = ARTIFACT_PLACEHOLDER.fullmatch(arg)
        if match:
            artifact_id = match.group(1)
            if artifact_id not in artifact_paths:
                raise GateError(
                    f"case checker {checker['id']} 缺少 fixture artifact: {artifact_id}"
                )
            args.append(str(artifact_paths[artifact_id]))
        else:
            args.append(arg)
    implementation = safe_path(
        candidate_root, checker["implementation"], f"checker {checker['id']} "
    )
    try:
        with tempfile.TemporaryDirectory(prefix="skill-lint-stability-case-") as temp_home:
            environment = minimal_environment()
            environment.update(
                {"HOME": temp_home, "TMPDIR": temp_home, "TEMP": temp_home, "TMP": temp_home}
            )
            completed = subprocess.run(
                [checker["runtime"], str(implementation), *args],
                cwd=candidate_root,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
                timeout=checker["timeout_seconds"],
                check=False,
                shell=False,
            )
    except FileNotFoundError as exc:
        raise GateError(f"case checker {checker['id']} runtime 不可用") from exc
    except subprocess.TimeoutExpired as exc:
        raise GateError(f"case checker {checker['id']} 执行超时") from exc
    output = completed.stdout + completed.stderr
    if {
        artifact_id: sha256_file(path)
        for artifact_id, path in sorted(artifact_paths.items())
    } != expected_artifact_sha256:
        raise GateError(f"case checker {checker['id']} 修改了输入 artifact")
    if not output.strip():
        raise GateError(f"case checker {checker['id']} 没有产生可审计输出")
    if completed.returncode != expected_exit_code:
        raise GateError(
            f"case checker {checker['id']} 退出码 {completed.returncode}，"
            f"预期 {expected_exit_code}"
        )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise GateError(f"case checker {checker['id']} 没有结构化失败输出")
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise GateError(
            f"case checker {checker['id']} 最后一行不是失败 JSON"
        ) from exc
    payload = exact_keys(
        payload,
        {"failed_constraint_ids", "artifact_sha256", "measurements"},
        f"case checker {checker['id']} 失败输出",
    )
    failed = payload["failed_constraint_ids"]
    if (
        not isinstance(failed, list)
        or any(not isinstance(item, str) or not SAFE_ID.fullmatch(item) for item in failed)
        or len(set(failed)) != len(failed)
        or sorted(failed) != sorted(expected_constraints)
    ):
        raise GateError(
            f"case checker {checker['id']} 未精确命中目标 constraint；"
            f"预期 {sorted(expected_constraints)}，实际 {failed!r}"
        )
    if payload["artifact_sha256"] != expected_artifact_sha256:
        raise GateError(
            f"case checker {checker['id']} 失败输出未绑定 fixture SHA-256"
        )
    measurements = validate_measurement_output(
        payload["measurements"],
        expected_constraints,
        expected_measurements,
        measurement_definitions,
        False,
        f"case checker {checker['id']} ",
    )
    return {
        "checker_id": checker["id"],
        "failed_constraint_ids": sorted(failed),
        "artifact_sha256": expected_artifact_sha256,
        "measurements": measurements,
        "exit_code": completed.returncode,
        "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
    }


def compare_observables(
    observations: dict[str, list[Any]], definitions: dict[str, dict[str, Any]]
) -> None:
    for observable_id, values in observations.items():
        definition = definitions[observable_id]
        comparison = definition["comparison"]
        if comparison == "exact":
            if any(value != values[0] for value in values[1:]):
                raise GateError(f"observable {observable_id} 在多轮执行中发生漂移")
        elif comparison == "set_equal":
            normalized: list[set[str]] = []
            for value in values:
                if (
                    not isinstance(value, list)
                    or any(not isinstance(item, str) for item in value)
                    or len(set(value)) != len(value)
                ):
                    raise GateError(f"observable {observable_id} 必须输出唯一字符串列表")
                normalized.append(set(value))
            if any(value != normalized[0] for value in normalized[1:]):
                raise GateError(f"observable {observable_id} 的覆盖集合在多轮执行中漂移")
        else:
            if any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                for value in values
            ):
                raise GateError(f"observable {observable_id} 必须输出有限数值")
            if max(values) - min(values) > definition["tolerance"]:
                raise GateError(
                    f"observable {observable_id} 的波动超过 tolerance="
                    f"{definition['tolerance']}"
                )


def verify(args: argparse.Namespace) -> int:
    if not args.confirm_trusted_candidate:
        raise GateError(
            "动态 verify 会执行候选 checker，只允许用户已确认的自有/可信候选"
        )
    candidate_root = Path(args.candidate_root).resolve()
    runs_root = resolve_external_directory(
        args.runs_root, "运行产物目录", candidate_root
    )
    public_key = resolve_evaluator_public_key(
        args.evaluator_public_key, candidate_root
    )
    receipt = new_output_path(args.receipt, "稳定性回执")
    for root, label in ((candidate_root, "候选"), (runs_root, "运行产物")):
        try:
            receipt.relative_to(root)
        except ValueError:
            continue
        raise GateError(f"稳定性回执必须放在{label}目录之外")

    contract_path = resolve_contract(candidate_root, args.contract)
    contract_data = load_json(contract_path, "稳定性合同")
    contract = validate_contract(candidate_root, contract_data)
    candidate_before = candidate_manifest(candidate_root)

    baseline_raw = Path(args.requirements_baseline).expanduser()
    if baseline_raw.is_symlink():
        raise GateError("硬约束基线不允许符号链接")
    baseline_path = baseline_raw.resolve()
    try:
        baseline_path.relative_to(candidate_root)
    except ValueError:
        pass
    else:
        raise GateError("硬约束基线必须位于候选 Skill 目录之外")
    baseline_result = validate_requirements_baseline(
        baseline_path, candidate_root, candidate_before, contract, public_key
    )

    policy_root = Path(__file__).resolve().parents[1]
    harness_raw = Path(args.harness_evidence).expanduser()
    if harness_raw.is_symlink():
        raise GateError("Harness 审查证据不允许符号链接")
    harness_result = verify_harness_review(
        candidate_root, policy_root, harness_raw.resolve()
    )
    candidate_sha256 = aggregate_digest(candidate_before)
    if harness_result["candidate_sha256"] != candidate_sha256:
        raise GateError("Harness 审查 marker 未绑定当前候选")

    held_out_manifest_raw = Path(args.held_out_cases).expanduser()
    held_out_root_raw = Path(args.held_out_root).expanduser()
    if held_out_manifest_raw.is_symlink() or held_out_root_raw.is_symlink():
        raise GateError("held-out manifest/root 不允许符号链接")
    held_out_manifest_path = held_out_manifest_raw.resolve()
    held_out_root = held_out_root_raw.resolve()
    try:
        receipt.relative_to(held_out_root)
    except ValueError:
        pass
    else:
        raise GateError("稳定性回执必须放在 held-out 目录之外")
    for value, label in (
        (held_out_manifest_path, "held-out manifest"),
        (held_out_root, "held-out root"),
    ):
        try:
            value.relative_to(candidate_root)
        except ValueError:
            pass
        else:
            raise GateError(f"{label} 必须位于候选 Skill 目录之外")
    held_out_before = tree_manifest(held_out_root)
    held_out = validate_held_out_cases(
        held_out_manifest_path,
        held_out_root,
        candidate_before,
        contract,
        public_key,
    )

    run_evidence_raw = Path(args.run_evidence).expanduser()
    if run_evidence_raw.is_symlink():
        raise GateError("运行证据不允许符号链接")
    run_evidence_path = run_evidence_raw.resolve()
    try:
        run_evidence_path.relative_to(candidate_root)
    except ValueError:
        pass
    else:
        raise GateError("运行证据必须放在候选 Skill 目录之外")
    try:
        run_evidence_path.relative_to(runs_root)
    except ValueError:
        pass
    else:
        raise GateError("运行证据必须放在运行产物目录之外")
    run_evidence = load_json(run_evidence_path, "运行证据")

    runs_before = tree_manifest(runs_root)
    runs = parse_run_evidence(
        run_evidence,
        runs_root,
        contract["artifacts"],
        candidate_sha256,
        contract["producer"],
        public_key,
    )
    if len(runs) < contract["minimum_runs"]:
        raise GateError(
            f"有效运行轮次不足：需要 {contract['minimum_runs']}，实际 {len(runs)}"
        )

    all_run_results: list[dict[str, Any]] = []
    observations = {observable_id: [] for observable_id in contract["observables"]}
    for run in runs:
        with tempfile.TemporaryDirectory(prefix="skill-lint-artifacts-") as temp_root:
            staged_paths = stage_artifacts(
                run["artifact_paths"], Path(temp_root)
            )
            checker_results: list[dict[str, Any]] = []
            for checker_id, checker in contract["checkers"].items():
                result = execute_checker(
                    candidate_root,
                    checker,
                    staged_paths,
                    contract["checker_constraints"][checker_id],
                    contract["checker_observables"][checker_id],
                    contract["checker_measurements"][checker_id],
                    contract["measurements"],
                )
                checker_results.append(result)
                for observable_id, value in result["observables"].items():
                    observations[observable_id].append(value)
        all_run_results.append(
            {
                "id": run["id"],
                "execution_nonce": run["execution_nonce"],
                "input_sha256": run["input_sha256"],
                "config_sha256": run["config_sha256"],
                "evaluation_id": run["evaluation_id"],
                "producer_log": run["producer_log"],
                "artifacts": run["artifact_records"],
                "checkers": checker_results,
            }
        )

    case_results: list[dict[str, Any]] = []
    for case_id, case in contract["cases"].items():
        source_fixture_paths = {
            artifact_id: safe_path(
                candidate_root, relative, f"case {case_id} fixture "
            )
            for artifact_id, relative in case["fixture_paths"].items()
        }
        with tempfile.TemporaryDirectory(prefix="skill-lint-artifacts-") as temp_root:
            fixture_paths = stage_artifacts(
                source_fixture_paths, Path(temp_root)
            )
            checker_results: list[dict[str, Any]] = []
            for checker_id in case["checker_ids"]:
                checker = contract["checkers"][checker_id]
                if case["expected_exit_code"] == 0:
                    result = execute_checker(
                        candidate_root,
                        checker,
                        fixture_paths,
                        contract["checker_constraints"][checker_id],
                        contract["checker_observables"][checker_id],
                        contract["checker_measurements"][checker_id],
                        contract["measurements"],
                    )
                else:
                    case_measurements = {
                        constraint_id: contract["checker_measurements"][checker_id][
                            constraint_id
                        ]
                        for constraint_id in case["constraint_ids"]
                    }
                    result = execute_negative_case(
                        candidate_root,
                        checker,
                        fixture_paths,
                        case["expected_exit_code"],
                        case["constraint_ids"],
                        case_measurements,
                        contract["measurements"],
                    )
                checker_results.append(result)
        case_results.append(
            {
                "id": case_id,
                "kind": case["kind"],
                "expected": case["expected"],
                "expected_exit_code": case["expected_exit_code"],
                "checkers": checker_results,
            }
        )

    held_out_results: list[dict[str, Any]] = []
    for case_id, case in held_out["cases"].items():
        with tempfile.TemporaryDirectory(prefix="skill-lint-artifacts-") as temp_root:
            staged_paths = stage_artifacts(
                case["artifact_paths"], Path(temp_root)
            )
            checker_id = case["checker_id"]
            checker = contract["checkers"][checker_id]
            if case["expected_exit_code"] == 0:
                result = execute_checker(
                    candidate_root,
                    checker,
                    staged_paths,
                    contract["checker_constraints"][checker_id],
                    contract["checker_observables"][checker_id],
                    contract["checker_measurements"][checker_id],
                    contract["measurements"],
                )
            else:
                constraint_id = case["constraint_id"]
                result = execute_negative_case(
                    candidate_root,
                    checker,
                    staged_paths,
                    case["expected_exit_code"],
                    [constraint_id],
                    {
                        constraint_id: contract["checker_measurements"][checker_id][
                            constraint_id
                        ]
                    },
                    contract["measurements"],
                )
            held_out_results.append(
                {
                    "id": case_id,
                    "kind": case["kind"],
                    "constraint_id": case["constraint_id"],
                    "checker_id": checker_id,
                    "artifacts": case["artifact_records"],
                    "result": result,
                }
            )

    compare_observables(observations, contract["observables"])
    if candidate_manifest(candidate_root) != candidate_before:
        raise GateError("checker 修改了候选 Skill，稳定性结果无效")
    if tree_manifest(runs_root) != runs_before:
        raise GateError("checker 修改了运行产物，稳定性结果无效")
    if tree_manifest(held_out_root) != held_out_before:
        raise GateError("checker 修改了 evaluator held-out 产物，稳定性结果无效")

    payload = {
        "receipt_version": RECEIPT_VERSION,
        "status": "INSTRUCTION_STABILITY_EVIDENCE_READY",
        "public_key_id": public_key_id(public_key),
        "candidate_sha256": aggregate_digest(candidate_before),
        "contract_sha256": sha256_file(contract_path),
        "requirements_baseline_sha256": baseline_result["sha256"],
        "harness_review": harness_result,
        "held_out_cases_sha256": held_out["sha256"],
        "run_evidence_sha256": sha256_file(run_evidence_path),
        "gate_sha256": sha256_file(Path(__file__)),
        "run_count": len(runs),
        "hard_constraint_ids": sorted(
            constraint_id for constraint_id, item in contract["constraints"].items()
            if item["severity"] == "hard"
        ),
        "observations": observations,
        "runs": all_run_results,
        "cases": case_results,
        "held_out_cases": held_out_results,
    }
    write_new_json(receipt, payload, "稳定性回执")
    print(
        "INSTRUCTION_STABILITY_EVIDENCE_READY "
        f"candidate_sha256={payload['candidate_sha256']} "
        f"contract_sha256={payload['contract_sha256']} "
        f"runs={len(runs)} receipt={receipt}"
    )
    return 0


def verify_receipt(args: argparse.Namespace) -> int:
    candidate_root = Path(args.candidate_root).resolve()
    runs_root = resolve_external_directory(
        args.runs_root, "运行产物目录", candidate_root
    )
    held_out_root = resolve_external_directory(
        args.held_out_root, "held-out root", candidate_root
    )
    public_key = resolve_evaluator_public_key(
        args.evaluator_public_key, candidate_root
    )
    receipt_raw = Path(args.receipt).expanduser()
    if receipt_raw.is_symlink():
        raise GateError("签名稳定性回执不允许符号链接")
    receipt_path = receipt_raw.resolve()
    signed = load_json(receipt_path, "签名稳定性回执")
    if not isinstance(signed, dict):
        raise GateError("签名稳定性回执必须是 JSON 对象")
    unsigned = verify_evaluator_signature(signed, "签名稳定性回执", public_key)
    unsigned = exact_keys(
        unsigned,
        {
            "receipt_version",
            "status",
            "public_key_id",
            "candidate_sha256",
            "contract_sha256",
            "requirements_baseline_sha256",
            "harness_review",
            "held_out_cases_sha256",
            "run_evidence_sha256",
            "gate_sha256",
            "run_count",
            "hard_constraint_ids",
            "observations",
            "runs",
            "cases",
            "held_out_cases",
        },
        "签名稳定性回执",
    )
    if unsigned["receipt_version"] != RECEIPT_VERSION:
        raise GateError("签名稳定性回执版本不受支持")
    if unsigned["status"] != "INSTRUCTION_STABILITY_EVIDENCE_READY":
        raise GateError("签名稳定性回执状态不是 EVIDENCE_READY")
    if unsigned["public_key_id"] != public_key_id(public_key):
        raise GateError("签名稳定性回执未绑定当前 evaluator public key")

    candidate_files = candidate_manifest(candidate_root)
    candidate_sha256 = aggregate_digest(candidate_files)
    if unsigned["candidate_sha256"] != candidate_sha256:
        raise GateError("签名稳定性回执未绑定当前完整候选")
    contract_path = resolve_contract(candidate_root, args.contract)
    contract = validate_contract(
        candidate_root, load_json(contract_path, "稳定性合同")
    )
    if unsigned["contract_sha256"] != sha256_file(contract_path):
        raise GateError("签名稳定性回执绑定的合同已变化")
    if unsigned["gate_sha256"] != sha256_file(Path(__file__)):
        raise GateError("签名稳定性回执绑定的稳定性门禁已变化")

    def external_file(raw_value: str, label: str) -> Path:
        raw = Path(raw_value).expanduser()
        if raw.is_symlink():
            raise GateError(f"{label}不允许符号链接")
        path = raw.resolve()
        if not path.is_file():
            raise GateError(f"{label}不存在")
        try:
            path.relative_to(candidate_root)
        except ValueError:
            return path
        raise GateError(f"{label}必须位于候选 Skill 目录之外")

    baseline_path = external_file(
        args.requirements_baseline, "硬约束基线"
    )
    baseline = validate_requirements_baseline(
        baseline_path, candidate_root, candidate_files, contract, public_key
    )
    if unsigned["requirements_baseline_sha256"] != baseline["sha256"]:
        raise GateError("签名稳定性回执绑定的硬约束基线已变化")

    harness_path = external_file(args.harness_evidence, "Harness 审查证据")
    harness = exact_keys(
        unsigned["harness_review"],
        {
            "candidate_sha256",
            "policy_sha256",
            "executed",
            "evidence_sha256",
        },
        "签名稳定性回执 harness_review",
    )
    policy_root = Path(__file__).resolve().parents[1]
    if harness["candidate_sha256"] != candidate_sha256:
        raise GateError("签名稳定性回执的 Harness marker 未绑定当前候选")
    if harness["evidence_sha256"] != sha256_file(harness_path):
        raise GateError("签名稳定性回执绑定的 Harness evidence 已变化")
    if harness["policy_sha256"] != aggregate_digest(candidate_manifest(policy_root)):
        raise GateError("签名稳定性回执绑定的 skill-lint policy 已变化")

    held_out_manifest_path = external_file(
        args.held_out_cases, "held-out 用例清单"
    )
    held_out = validate_held_out_cases(
        held_out_manifest_path,
        held_out_root,
        candidate_files,
        contract,
        public_key,
    )
    if unsigned["held_out_cases_sha256"] != held_out["sha256"]:
        raise GateError("签名稳定性回执绑定的 held-out 用例已变化")

    run_evidence_path = external_file(args.run_evidence, "运行证据")
    if unsigned["run_evidence_sha256"] != sha256_file(run_evidence_path):
        raise GateError("签名稳定性回执绑定的运行证据已变化")
    parsed_runs = parse_run_evidence(
        load_json(run_evidence_path, "运行证据"),
        runs_root,
        contract["artifacts"],
        candidate_sha256,
        contract["producer"],
        public_key,
    )
    if (
        not isinstance(unsigned["run_count"], int)
        or isinstance(unsigned["run_count"], bool)
        or unsigned["run_count"] != len(parsed_runs)
        or len(parsed_runs) < contract["minimum_runs"]
    ):
        raise GateError("签名稳定性回执的运行轮次与当前证据不一致")
    receipt_runs = unsigned["runs"]
    if not isinstance(receipt_runs, list) or len(receipt_runs) != len(parsed_runs):
        raise GateError("签名稳定性回执的 runs 不完整")
    parsed_by_id = {run["id"]: run for run in parsed_runs}
    receipt_run_ids = [
        item.get("id") for item in receipt_runs if isinstance(item, dict)
    ]
    if (
        len(receipt_run_ids) != len(receipt_runs)
        or len(set(receipt_run_ids)) != len(receipt_run_ids)
        or set(receipt_run_ids) != set(parsed_by_id)
    ):
        raise GateError("签名稳定性回执的 run IDs 不完整或重复")
    for index, raw in enumerate(receipt_runs, 1):
        run = exact_keys(
            raw,
            {
                "id",
                "execution_nonce",
                "input_sha256",
                "config_sha256",
                "evaluation_id",
                "producer_log",
                "artifacts",
                "checkers",
            },
            f"签名稳定性回执 run #{index}",
        )
        current = parsed_by_id.get(run["id"])
        if current is None:
            raise GateError("签名稳定性回执包含未知 run")
        for key in (
            "execution_nonce",
            "input_sha256",
            "config_sha256",
            "evaluation_id",
            "producer_log",
        ):
            if run[key] != current[key]:
                raise GateError(f"签名稳定性回执 run {run['id']} 绑定已变化")
        if run["artifacts"] != current["artifact_records"]:
            raise GateError(f"签名稳定性回执 run {run['id']} 产物绑定已变化")

    expected_hard = sorted(
        constraint_id
        for constraint_id, item in contract["constraints"].items()
        if item["severity"] == "hard"
    )
    if unsigned["hard_constraint_ids"] != expected_hard:
        raise GateError("签名稳定性回执未覆盖当前全部 hard constraints")
    observations = unsigned["observations"]
    if (
        not isinstance(observations, dict)
        or set(observations) != set(contract["observables"])
        or any(
            not isinstance(values, list) or len(values) != len(parsed_runs)
            for values in observations.values()
        )
    ):
        raise GateError("签名稳定性回执的 observations 不完整")
    receipt_cases = unsigned["cases"]
    if not isinstance(receipt_cases, list):
        raise GateError("签名稳定性回执 cases 格式非法")
    receipt_case_ids = [
        item.get("id") for item in receipt_cases if isinstance(item, dict)
    ]
    if (
        len(receipt_case_ids) != len(receipt_cases)
        or len(set(receipt_case_ids)) != len(receipt_case_ids)
        or set(receipt_case_ids) != set(contract["cases"])
    ):
        raise GateError("签名稳定性回执的公开 case IDs 不完整或重复")
    receipt_hidden = unsigned["held_out_cases"]
    if not isinstance(receipt_hidden, list):
        raise GateError("签名稳定性回执 held_out_cases 格式非法")
    hidden_by_id = held_out["cases"]
    receipt_hidden_ids = [
        item.get("id") for item in receipt_hidden if isinstance(item, dict)
    ]
    if (
        len(receipt_hidden_ids) != len(receipt_hidden)
        or len(set(receipt_hidden_ids)) != len(receipt_hidden_ids)
        or set(receipt_hidden_ids) != set(hidden_by_id)
    ):
        raise GateError("签名稳定性回执 held_out_cases 不完整")
    for raw in receipt_hidden:
        case = exact_keys(
            raw,
            {
                "id",
                "kind",
                "constraint_id",
                "checker_id",
                "artifacts",
                "result",
            },
            "签名稳定性回执 held-out case",
        )
        current = hidden_by_id[case["id"]]
        if (
            case["kind"] != current["kind"]
            or case["constraint_id"] != current["constraint_id"]
            or case["checker_id"] != current["checker_id"]
            or case["artifacts"] != current["artifact_records"]
        ):
            raise GateError(
                f"签名稳定性回执 held-out case {case['id']} 绑定已变化"
            )

    print(
        "INSTRUCTION_STABILITY_VERIFIED "
        f"candidate_sha256={candidate_sha256} "
        f"contract_sha256={unsigned['contract_sha256']} "
        f"runs={len(parsed_runs)} receipt={receipt_path}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    assess_parser = subparsers.add_parser("assess")
    assess_parser.add_argument("--candidate-root", required=True)
    assess_parser.add_argument("--contract")
    assess_parser.add_argument("--requirements-baseline")
    assess_parser.add_argument("--evaluator-public-key")
    assess_parser.add_argument("--output")
    assess_parser.set_defaults(handler=assess)

    sign_parser = subparsers.add_parser("sign-evidence")
    sign_parser.add_argument("--input", required=True)
    sign_parser.add_argument("--output", required=True)
    sign_parser.add_argument("--private-key", required=True)
    sign_parser.set_defaults(handler=sign_evidence)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--candidate-root", required=True)
    verify_parser.add_argument("--contract")
    verify_parser.add_argument("--evaluator-public-key", required=True)
    verify_parser.add_argument("--requirements-baseline", required=True)
    verify_parser.add_argument("--harness-evidence", required=True)
    verify_parser.add_argument("--held-out-cases", required=True)
    verify_parser.add_argument("--held-out-root", required=True)
    verify_parser.add_argument("--run-evidence", required=True)
    verify_parser.add_argument("--runs-root", required=True)
    verify_parser.add_argument("--receipt", required=True)
    verify_parser.add_argument(
        "--confirm-trusted-candidate",
        action="store_true",
        help="确认候选为用户自有/已审查可信代码；这不是沙箱",
    )
    verify_parser.set_defaults(handler=verify)

    receipt_parser = subparsers.add_parser("verify-receipt")
    receipt_parser.add_argument("--receipt", required=True)
    receipt_parser.add_argument("--candidate-root", required=True)
    receipt_parser.add_argument("--contract")
    receipt_parser.add_argument("--evaluator-public-key", required=True)
    receipt_parser.add_argument("--requirements-baseline", required=True)
    receipt_parser.add_argument("--harness-evidence", required=True)
    receipt_parser.add_argument("--held-out-cases", required=True)
    receipt_parser.add_argument("--held-out-root", required=True)
    receipt_parser.add_argument("--run-evidence", required=True)
    receipt_parser.add_argument("--runs-root", required=True)
    receipt_parser.set_defaults(handler=verify_receipt)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.handler(args)
    except GateError as exc:
        print(f"INSTRUCTION_STABILITY_BLOCKED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
