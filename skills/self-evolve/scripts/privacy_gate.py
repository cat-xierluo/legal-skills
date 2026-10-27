#!/usr/bin/env python3
"""Mandatory privacy gate for Self Evolve review artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from self_evolve_paths import REVIEW_INBOX_ROOT, REVIEW_QUARANTINE_ROOT


MAX_CODE_BLOCK_CHARS = 600
MAX_LINE_CHARS = 1200


@dataclass(frozen=True)
class Finding:
    rule: str
    count: int
    severity: str = "high"


REDACTION_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "private_system_path",
        re.compile(r"(?<![\w.-])/(?:private/(?:var|tmp)|var/(?:folders|tmp)|tmp)(?:/[^\n\r`'\"<>|)]*)?"),
        "<private-path>",
    ),
    (
        "home_path",
        re.compile(
            r"(?<![\w.-])(?:/(?:Users|home)/[^/\s]+(?:/[^\n\r`'\"<>|)]*)?|"
            r"/root(?:/[^\n\r`'\"<>|)]*)?|"
            r"[A-Za-z]:\\Users\\[^\\\s]+(?:\\[^\n\r`'\"<>|)]*)?)"
        ),
        "<private-path>",
    ),
    (
        "mounted_volume_path",
        re.compile(
            r"(?<![\w.-])/(?:Volumes|mnt|media)/[^/\s]+(?:/[^\n\r`'\"<>|)]*)?"
        ),
        "<private-path>",
    ),
    (
        "transcript_path",
        re.compile(r"(?<!\w)(?:[^\s`'\"]+/(?:sessions|archived_sessions|projects)/[^\s`'\"]+\.jsonl)"),
        "<transcript>",
    ),
    (
        "email",
        re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", re.I),
        "<email>",
    ),
    (
        "phone",
        re.compile(r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d(?:[-\s]?\d){8}(?!\d)"),
        "<phone>",
    ),
    (
        "identity_number",
        re.compile(r"(?<!\d)\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[0-9Xx](?!\d)"),
        "<identity-number>",
    ),
    (
        "bank_card",
        re.compile(r"(?<!\d)(?:\d[- ]?){15,18}\d(?!\d)"),
        "<bank-card>",
    ),
    (
        "chinese_name",
        re.compile(
            r"(?:(?:联系人姓名|姓名|当事人|联系人)[：:\s]*)[\u4e00-\u9fff·]{2,8}|"
            r"(?<![\u4e00-\u9fff])[\u4e00-\u9fff·]{2,4}(?=[+＋,，、\s]*(?:住址|地址|住所|银行卡))"
        ),
        "<person-name>",
    ),
    (
        "postal_address",
        re.compile(r"(?:住址|地址|住所|户籍地|联系地址)[：:\s]*[^\n,，;；]{4,100}"),
        "<postal-address>",
    ),
    (
        "case_number",
        re.compile(r"[（(]\d{4}[）)][^\s，。；:：]{1,24}?\d{1,8}号"),
        "<case-number>",
    ),
    (
        "url",
        re.compile(r"https?://[^\s)\]>]+", re.I),
        "<url>",
    ),
    (
        "organization",
        re.compile(r"[\u4e00-\u9fff]{2,30}(?:有限责任公司|股份有限公司|有限公司|律师事务所|集团|研究院)"),
        "<organization>",
    ),
)


RESIDUAL_BLOCK_RULES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, pattern) for name, pattern, _ in REDACTION_RULES if name != "url"
)
BLOCK_ONLY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "prompt_injection",
        re.compile(
            r"(?:ignore|disregard|forget).{0,40}(?:previous|prior|system).{0,20}(?:instruction|prompt)|"
            r"忽略.{0,20}(?:之前|以上|系统).{0,20}(?:指令|提示)|"
            r"(?:system|developer)\s*(?:prompt|message)",
            re.I,
        ),
    ),
    (
        "secret_material",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
            r"(?i:(?:api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+\-=]{12,})|"
            r"(?i:\bBearer\s+[A-Za-z0-9._~+/=\-]{16,})|"
            r"\beyJ[A-Za-z0-9_-]{6,}\.eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b|"
            r"\b(?:sk-(?:proj-|live-|test-)?[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})\b"
        ),
    ),
)
SAFE_ARTIFACT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$")


def _runtime_home_pattern() -> re.Pattern[str] | None:
    """Cover non-standard Unix home roots such as /srv/users/alice."""
    candidates: set[str] = set()
    home_values = [os.environ.get("HOME", "")]
    try:
        home_values.append(str(Path.home()))
    except (OSError, RuntimeError):
        # Minimal containers/service accounts may have neither HOME nor a
        # resolvable passwd entry. Static rules must remain available.
        pass
    for raw in home_values:
        value = raw.strip().rstrip("/")
        if value.startswith("/") and value != "/":
            candidates.add(value)
    if not candidates:
        return None
    roots = "|".join(re.escape(item) for item in sorted(candidates, key=len, reverse=True))
    return re.compile(rf"(?<![\w.-])(?:{roots})(?:/[^\n\r`'\"<>|)]*)?")


def _strip_large_code_blocks(text: str) -> tuple[str, int]:
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        body = match.group(0)
        if len(body) <= MAX_CODE_BLOCK_CHARS:
            return body
        count += 1
        digest = hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()[:12]
        return f"```\n<long-code-redacted sha256={digest}>\n```"

    return re.sub(r"```[\s\S]*?```", replace, text), count


def _truncate_long_lines(text: str) -> tuple[str, int]:
    count = 0
    output: list[str] = []
    for line in text.splitlines():
        if len(line) <= MAX_LINE_CHARS:
            output.append(line)
            continue
        count += 1
        digest = hashlib.sha256(line.encode("utf-8", errors="replace")).hexdigest()[:12]
        output.append(f"<long-line-redacted sha256={digest}>")
    suffix = "\n" if text.endswith("\n") else ""
    return "\n".join(output) + suffix, count


def sanitize_text(text: str) -> tuple[str, list[Finding]]:
    """Redact known identifiers and return a rule-level audit summary."""
    sanitized, code_count = _strip_large_code_blocks(text)
    findings: list[Finding] = []
    if code_count:
        findings.append(Finding("long_code_block", code_count, "medium"))

    sanitized, line_count = _truncate_long_lines(sanitized)
    if line_count:
        findings.append(Finding("long_tool_output", line_count, "medium"))

    runtime_home = _runtime_home_pattern()
    if runtime_home is not None:
        sanitized, count = runtime_home.subn("<private-path>", sanitized)
        if count:
            findings.append(Finding("home_path", count))

    for name, pattern, replacement in REDACTION_RULES:
        sanitized, count = pattern.subn(replacement, sanitized)
        if count:
            findings.append(Finding(name, count))
    return sanitized, findings


def validate_text(text: str) -> list[Finding]:
    """Return unredacted high-risk patterns that must block publication."""
    findings: list[Finding] = []
    runtime_home = _runtime_home_pattern()
    if runtime_home is not None:
        count = len(runtime_home.findall(text))
        if count:
            findings.append(Finding("residual_home_path", count))
    for name, pattern in RESIDUAL_BLOCK_RULES:
        count = len(pattern.findall(text))
        if count:
            findings.append(Finding(f"residual_{name}", count))
    return findings


def validate_untrusted_source(text: str) -> list[Finding]:
    """Return content that must never be copied into a review artifact."""
    findings: list[Finding] = []
    for name, pattern in BLOCK_ONLY_RULES:
        count = len(pattern.findall(text))
        if count:
            findings.append(Finding(name, count, "critical"))
    return findings


def sanitize_structured_text(text: str) -> str:
    """Return storage-safe text or fail closed for non-redactable content."""
    raw = str(text)
    source_blockers = validate_untrusted_source(raw)
    sanitized, _ = sanitize_text(raw)
    residual = validate_text(sanitized)
    if source_blockers or residual:
        rules = ", ".join(item.rule for item in [*source_blockers, *residual])
        raise ValueError(f"structured text failed privacy validation: {rules}")
    return sanitized


def evidence_id(source_session_id: str, summary: str) -> str:
    payload = f"{source_session_id}\0{summary}".encode("utf-8", errors="replace")
    return "ev-" + hashlib.sha256(payload).hexdigest()[:16]


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temp_name).replace(path)
    finally:
        try:
            Path(temp_name).unlink()
        except FileNotFoundError:
            pass


def _open_confined_parent(root: Path, relative: Path, *, create: bool) -> list[int]:
    """Open a relative parent chain from one trusted root without following links."""
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError("invalid confined path")
    if create:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptors: list[int] = []
    try:
        descriptors.append(os.open(root, directory_flags))
        for part in relative.parts[:-1]:
            try:
                child = os.open(part, directory_flags, dir_fd=descriptors[-1])
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, mode=0o700, dir_fd=descriptors[-1])
                os.fsync(descriptors[-1])
                child = os.open(part, directory_flags, dir_fd=descriptors[-1])
            descriptors.append(child)
        return descriptors
    except (OSError, ValueError) as exc:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise ValueError("confined path is missing, invalid, or traverses a symlink") from exc


def _close_descriptors(descriptors: list[int]) -> None:
    for descriptor in reversed(descriptors):
        os.close(descriptor)


def _write_all(descriptor: int, content: bytes) -> None:
    view = memoryview(content)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short write while publishing artifact")
        view = view[written:]


def _read_regular_at(parent_descriptor: int, name: str, *, label: str) -> bytes:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_descriptor,
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f"{label} is not a regular file")
        output = bytearray()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            output.extend(chunk)
        return bytes(output)
    except ValueError:
        raise
    except OSError as exc:
        raise ValueError(f"{label} is missing, unreadable, or traverses a symlink") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def read_confined_regular(root: Path, relative: Path, *, label: str) -> bytes:
    """Read a confined regular file through a pinned parent directory."""
    descriptors = _open_confined_parent(root, relative, create=False)
    try:
        return _read_regular_at(descriptors[-1], relative.name, label=label)
    finally:
        _close_descriptors(descriptors)


def publish_immutable_bytes(root: Path, relative: Path, content: bytes) -> None:
    """Publish no-clobber bytes through a pinned, no-follow parent chain."""
    descriptors = _open_confined_parent(root, relative, create=True)
    parent_descriptor = descriptors[-1]
    temporary = f".{relative.name}.{uuid.uuid4().hex}.tmp"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o400,
            dir_fd=parent_descriptor,
        )
        os.fchmod(descriptor, 0o400)
        _write_all(descriptor, content)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        try:
            os.link(
                temporary,
                relative.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileExistsError:
            existing = _read_regular_at(
                parent_descriptor,
                relative.name,
                label="immutable artifact",
            )
            if existing != content:
                raise ValueError("immutable artifact already exists with different content")
        else:
            os.fsync(parent_descriptor)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            try:
                os.unlink(temporary, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        finally:
            _close_descriptors(descriptors)


def _publish_replace_bytes(root: Path, relative: Path, content: bytes) -> None:
    """Atomically replace one confined file without following its parent path."""
    descriptors = _open_confined_parent(root, relative, create=True)
    parent_descriptor = descriptors[-1]
    temporary = f".{relative.name}.{uuid.uuid4().hex}.tmp"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_descriptor,
        )
        _write_all(descriptor, content)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.rename(
            temporary,
            relative.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        os.fsync(parent_descriptor)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            try:
                os.unlink(temporary, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        finally:
            _close_descriptors(descriptors)


def write_review_artifact(
    destination: Path,
    content: str,
    *,
    artifact_id: str,
    source_session_ids: Iterable[str] = (),
    quarantine_root: Path = REVIEW_QUARANTINE_ROOT,
    immutable: bool = False,
) -> dict[str, object]:
    """Sanitize and publish an artifact, or write safe quarantine metadata."""
    if not SAFE_ARTIFACT_ID.fullmatch(artifact_id):
        raise ValueError("invalid artifact_id")
    destination = destination.expanduser()
    destination = destination.parent.resolve() / destination.name
    inbox_root = REVIEW_INBOX_ROOT.expanduser().resolve()
    quarantine_root = quarantine_root.expanduser().resolve()
    if destination != inbox_root and inbox_root not in destination.parents:
        raise ValueError("destination must be inside review inbox")
    if quarantine_root == inbox_root or inbox_root in quarantine_root.parents:
        raise ValueError("quarantine must be separate from review inbox")

    source_blockers = validate_untrusted_source(content)
    sanitized, redactions = sanitize_text(content)
    blockers = [*source_blockers, *validate_text(sanitized)]
    sanitized_name, filename_redactions = sanitize_text(destination.name)
    if sanitized_name != destination.name or filename_redactions:
        blockers.append(Finding("sensitive_filename", 1, "critical"))
    logical_destination = str(destination.relative_to(inbox_root))
    source_hashes = sorted(
        {
            hashlib.sha256(str(item).encode("utf-8", errors="replace")).hexdigest()[:16]
            for item in source_session_ids
            if str(item)
        }
    )
    result: dict[str, object] = {
        "artifact_id": artifact_id,
        "destination": logical_destination,
        "redactions": [asdict(item) for item in redactions],
        "blockers": [asdict(item) for item in blockers],
        "source_session_hashes": source_hashes,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if blockers:
        result["status"] = "quarantined"
        result["content_sha256"] = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
        quarantine_path = (quarantine_root / f"{artifact_id}.json").resolve()
        if quarantine_root not in quarantine_path.parents:
            raise ValueError("invalid quarantine path")
        _atomic_write(quarantine_path, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        result["quarantine_path"] = str(quarantine_path)
        return result

    sanitized_bytes = sanitized.encode("utf-8")
    sanitized_digest = hashlib.sha256(sanitized_bytes).hexdigest()
    if immutable:
        destination = destination.with_name(
            f"{destination.stem}-{sanitized_digest}{destination.suffix}"
        )
        logical_destination = str(destination.relative_to(inbox_root))
        result["destination"] = logical_destination
        publish_immutable_bytes(inbox_root, Path(logical_destination), sanitized_bytes)
    else:
        _publish_replace_bytes(inbox_root, Path(logical_destination), sanitized_bytes)
    result["status"] = "published"
    result["content_sha256"] = sanitized_digest
    return result


def scan_paths(paths: Iterable[Path]) -> dict[str, object]:
    reports: list[dict[str, object]] = []
    blocked = 0
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            reports.append({"path": str(path), "status": "error", "error": str(exc)})
            blocked += 1
            continue
        findings = [*validate_untrusted_source(text), *validate_text(text)]
        status = "blocked" if findings else "ok"
        blocked += int(bool(findings))
        reports.append(
            {"path": str(path), "status": status, "findings": [asdict(item) for item in findings]}
        )
    return {"ok": blocked == 0, "blocked_files": blocked, "files": reports}


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint Self Evolve artifacts for privacy leaks.")
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    expanded: list[Path] = []
    for path in args.paths:
        path = path.expanduser()
        if path.is_dir():
            expanded.extend(item for item in path.rglob("*") if item.is_file())
        else:
            expanded.append(path)
    report = scan_paths(expanded)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for item in report["files"]:
            print(f"{item['status']}: {item['path']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
