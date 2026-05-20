from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from common import SourceInfo


@dataclass
class ConvertOptions:
    pages: str | None = None
    model: str | None = None
    paddle_model: str | None = None
    log_level: str = "medium"


@dataclass
class BackendResult:
    backend: str
    mode: str
    provider: str
    markdown: str
    images: list[dict[str, str]] = field(default_factory=list)
    batches: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    backend_result_dir: Path | None = None


class OCRBackend(Protocol):
    name: str

    def convert(
        self,
        source: SourceInfo,
        options: ConvertOptions,
        work_dir: Path,
        assets_dir: Path,
    ) -> BackendResult:
        ...
