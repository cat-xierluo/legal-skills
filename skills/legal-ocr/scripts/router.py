from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from common import (
    MINERU_LOCAL_SUFFIXES,
    PADDLE_LOCAL_SUFFIXES,
    SourceInfo,
    first_non_empty,
    has_paddle_config,
    resolve_mineru_token,
    sanitize_config_value,
)


OFFICE_SUFFIXES = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}


@dataclass
class RouteDecision:
    preferred: str
    candidates: list[str]
    reason: str
    fallback_allowed: bool = True
    notes: list[str] = field(default_factory=list)


def _mineru_supports(source: SourceInfo) -> bool:
    if source.is_url:
        return True
    return source.suffix in MINERU_LOCAL_SUFFIXES


def _paddle_protocol(env: dict[str, str]) -> str:
    configured = first_non_empty(env, "PADDLEOCR_API_PROTOCOL", "PADDLE_API_PROTOCOL").lower()
    if configured in {"sync", "async"}:
        return configured

    api_url = sanitize_config_value(
        first_non_empty(
            env,
            "PADDLEOCR_DOC_PARSING_API_URL",
            "PADDLE_OCR_API_ENDPOINT",
            "API_URL",
        )
    )
    if api_url and "://" not in api_url:
        api_url = f"https://{api_url}"
    return "sync" if urlparse(api_url).path.rstrip("/").endswith("/layout-parsing") else "async"


def _paddle_supports(source: SourceInfo, env: dict[str, str]) -> bool:
    if source.is_url:
        return (
            source.source_type == "remote_doc_url"
            and source.suffix in PADDLE_LOCAL_SUFFIXES
            and _paddle_protocol(env) == "sync"
        )
    return source.suffix in PADDLE_LOCAL_SUFFIXES


def _append_unique(candidates: list[str], backend: str) -> None:
    if backend not in candidates:
        candidates.append(backend)


def _light_note(source: SourceInfo) -> str:
    if source.source_type == "remote_html_url":
        return "网页 URL 需要 MinerU Token；未配置时会失败并提示补充 Token"
    return "未检测到 MinerU Token 时会使用轻量接口；大文件、长 PDF 或高频请求可能受限"


def _optimal_candidates(
    source: SourceInfo,
    env: dict[str, str],
    *,
    paddle_ready: bool,
    mineru_ready: bool,
    notes: list[str],
) -> list[str]:
    candidates: list[str] = []
    paddle_supports = paddle_ready and _paddle_supports(source, env)
    mineru_supports = _mineru_supports(source)

    if source.source_type == "remote_html_url":
        _append_unique(candidates, "mineru")
        return candidates

    if source.suffix in OFFICE_SUFFIXES:
        _append_unique(candidates, "mineru")
        return candidates

    if source.is_url:
        if mineru_supports:
            _append_unique(candidates, "mineru")
        if paddle_supports:
            _append_unique(candidates, "paddle")
        elif paddle_ready and source.suffix in PADDLE_LOCAL_SUFFIXES:
            notes.append("PaddleOCR 异步任务接口不能直接提交远程 URL，远程文档优先使用 MinerU")
        return candidates

    if source.suffix in PADDLE_LOCAL_SUFFIXES:
        if paddle_supports:
            _append_unique(candidates, "paddle")
        if mineru_supports and mineru_ready:
            _append_unique(candidates, "mineru")
        return candidates

    if mineru_supports:
        _append_unique(candidates, "mineru")
    return candidates


def choose_backend(
    source: SourceInfo,
    env: dict[str, str],
    explicit_backend: str = "auto",
) -> RouteDecision:
    explicit_backend = (explicit_backend or "auto").lower()
    paddle_ready = has_paddle_config(env)
    mineru_ready = bool(resolve_mineru_token(env))

    if explicit_backend in {"paddle", "mineru"}:
        return RouteDecision(
            preferred=explicit_backend,
            candidates=[explicit_backend],
            reason=f"用户显式指定 {explicit_backend} 后端",
            fallback_allowed=False,
        )

    notes: list[str] = []

    if paddle_ready and mineru_ready:
        candidates = _optimal_candidates(
            source,
            env,
            paddle_ready=paddle_ready,
            mineru_ready=mineru_ready,
            notes=notes,
        )
        if not candidates:
            raise ValueError(f"不支持的输入类型：{source.suffix or source.raw}")
        return RouteDecision(
            preferred=candidates[0],
            candidates=candidates,
            reason="已检测到 PaddleOCR 与 MinerU 两套 API，按输入类型选择最优后端，并保留失败回退",
            fallback_allowed=len(candidates) > 1,
            notes=notes,
        )

    if paddle_ready and not mineru_ready:
        candidates: list[str] = []
        if _paddle_supports(source, env):
            _append_unique(candidates, "paddle")
        elif _mineru_supports(source):
            _append_unique(candidates, "mineru")
            notes.append("已检测到 PaddleOCR 配置，但该输入类型不适合 PaddleOCR，改用 MinerU 支持链路")
            notes.append(_light_note(source))
        else:
            raise ValueError(f"不支持的输入类型：{source.suffix or source.raw}")
        return RouteDecision(
            preferred=candidates[0],
            candidates=candidates,
            reason="仅检测到 PaddleOCR API 配置，优先使用 PaddleOCR；超出 PaddleOCR 能力时才改用 MinerU",
            fallback_allowed=False,
            notes=notes,
        )

    if mineru_ready and not paddle_ready:
        if not _mineru_supports(source):
            raise ValueError(f"不支持的输入类型：{source.suffix or source.raw}")
        return RouteDecision(
            preferred="mineru",
            candidates=["mineru"],
            reason="仅检测到 MinerU Token/API 配置，所有支持的输入统一使用 MinerU",
            fallback_allowed=False,
            notes=notes,
        )

    if _mineru_supports(source):
        notes.append(_light_note(source))
        return RouteDecision(
            preferred="mineru",
            candidates=["mineru"],
            reason="未检测到可用 OCR API 配置，使用 MinerU 轻量接口作为开箱即用回退",
            fallback_allowed=False,
            notes=notes,
        )

    raise ValueError(f"不支持的输入类型：{source.suffix or source.raw}")
