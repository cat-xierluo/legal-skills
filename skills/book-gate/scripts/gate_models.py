#!/usr/bin/env python3
"""book-gate 的共享数据模型与确定性文件清单工具。"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any
import json


@dataclass
class Finding:
    req_id: str
    file: str
    line: int
    severity: str
    message: str
    suggestion: str = ""
    artifact_id: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "req_id": self.req_id,
            "file": self.file,
            "line": self.line,
            "severity": self.severity,
            "message": self.message,
            "suggestion": self.suggestion,
        }
        if self.artifact_id:
            data["artifact_id"] = self.artifact_id
        if self.details:
            data["details"] = self.details
        return data


@dataclass
class CheckerOutput:
    findings: list[Finding] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class GateContext:
    project_root: Path
    requirements_path: Path
    output_dir: Path
    candidate_sha: str
    input_manifest: list[dict[str, Any]]
    selected_stage: str
    config: dict[str, Any] = field(default_factory=dict)
    docx_path: Path | None = None
    rendered_pdf_path: Path | None = None
    visual_review_path: Path | None = None
    producer_id: str = ""

    def rel(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.project_root.resolve()).as_posix()
        except ValueError:
            return path.name

    def scope_files(self, requirement: dict[str, Any]) -> list[Path]:
        scopes = requirement.get("scope", [])
        if isinstance(scopes, str):
            scopes = [scopes]
        files: set[Path] = set()
        for pattern in scopes:
            if not isinstance(pattern, str) or not pattern.strip():
                continue
            if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
                raise ValueError(f"scope 只能是项目内相对 glob：{pattern}")
            for item in self.project_root.glob(pattern):
                if item.is_file():
                    files.add(item.resolve())
        return sorted(files, key=lambda p: self.rel(p))


def sha256_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(payload)


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1
