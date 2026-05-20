from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


SUPPORTED_IMAGE_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tiff",
    ".tif",
    ".webp",
    ".gif",
    ".jp2",
)
PADDLE_LOCAL_SUFFIXES = (".pdf",) + SUPPORTED_IMAGE_SUFFIXES
MINERU_LOCAL_SUFFIXES = (
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".jp2",
    ".webp",
    ".gif",
    ".bmp",
    ".xls",
    ".xlsx",
)
DOCUMENT_URL_SUFFIXES = MINERU_LOCAL_SUFFIXES


@dataclass(frozen=True)
class SourceInfo:
    raw: str
    is_url: bool
    source_type: str
    suffix: str
    file_name: str
    base_name: str
    path: Path | None = None
    size_bytes: int | None = None
    page_count: int | None = None


def get_skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def get_config_path() -> Path:
    return get_skill_root() / "config" / ".env"


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    env: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def load_env() -> dict[str, str]:
    file_env = read_env_file(get_config_path())
    return {**file_env, **os.environ}


def first_non_empty(env: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = env.get(key, "").strip()
        if value:
            return value
    return ""


def parse_bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on"}


def parse_positive_int(value: str | None, default: int) -> int:
    if not value or not str(value).strip():
        return default
    try:
        parsed = int(str(value).strip())
    except ValueError as error:
        raise ValueError(f"整数配置无效：{value}") from error
    if parsed <= 0:
        raise ValueError(f"整数配置必须大于 0：{value}")
    return parsed


def parse_positive_float(value: str | None, default: float) -> float:
    if not value or not str(value).strip():
        return default
    try:
        parsed = float(str(value).strip())
    except ValueError as error:
        raise ValueError(f"数字配置无效：{value}") from error
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"数字配置必须大于 0：{value}")
    return parsed


def sanitize_name(value: str) -> str:
    sanitized = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", value, flags=re.UNICODE)
    sanitized = sanitized.strip("._")
    return sanitized or "document"


def is_http_url(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))


def suffix_from_url(url: str) -> str:
    path = unquote(urlparse(url).path)
    return Path(path).suffix.lower()


def derive_name_from_url(url: str) -> str:
    parsed_path = unquote(urlparse(url).path).rstrip("/")
    filename = Path(parsed_path).name if parsed_path else ""
    if not filename:
        host = urlparse(url).hostname or "remote-document"
        filename = sanitize_name(host)
    return sanitize_name(filename)


def is_html_like_url(url: str) -> bool:
    suffix = suffix_from_url(url)
    return not suffix or suffix not in DOCUMENT_URL_SUFFIXES


def estimate_base64_mb(path: Path) -> float:
    return (path.stat().st_size * 4 / 3) / 1024 / 1024


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_output_markdown_path(source: SourceInfo, output_arg: str | None) -> Path:
    if output_arg:
        output_path = Path(output_arg).expanduser()
        if output_path.suffix.lower() == ".md":
            return output_path.resolve()
        if output_arg.endswith("/") or output_path.is_dir() or not output_path.suffix:
            return (output_path / f"{source.base_name}.md").resolve()
        return output_path.resolve()

    if source.path:
        return source.path.with_suffix(".md").resolve()
    return (Path.cwd() / f"{source.base_name}.md").resolve()


def resolve_images_dir(markdown_path: Path) -> Path:
    return markdown_path.with_name(f"{markdown_path.stem}_images")


def build_source_info(raw_source: str, page_count: int | None = None) -> SourceInfo:
    raw = raw_source.strip()
    if is_http_url(raw):
        file_name = derive_name_from_url(raw)
        suffix = suffix_from_url(raw)
        base_name = Path(file_name).stem or "remote-document"
        source_type = "remote_html_url" if is_html_like_url(raw) else "remote_doc_url"
        return SourceInfo(
            raw=raw,
            is_url=True,
            source_type=source_type,
            suffix=suffix,
            file_name=file_name,
            base_name=sanitize_name(base_name),
            page_count=page_count,
        )

    path = Path(raw).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"文件不存在：{path}")
    if not path.is_file():
        raise ValueError(f"不是普通文件：{path}")
    if path.stat().st_size == 0:
        raise ValueError(f"文件为空：{path}")

    return SourceInfo(
        raw=str(path),
        is_url=False,
        source_type="local_file",
        suffix=path.suffix.lower(),
        file_name=path.name,
        base_name=sanitize_name(path.stem),
        path=path,
        size_bytes=path.stat().st_size,
        page_count=page_count,
    )


def read_official_mineru_token() -> str:
    yaml_path = Path.home() / ".mineru" / "config.yaml"
    if not yaml_path.exists():
        return ""
    try:
        content = yaml_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    patterns = [
        r"^\s*token\s*:\s*[\"']?([^\"'#\r\n]+)[\"']?\s*$",
        r"^\s*api_token\s*:\s*[\"']?([^\"'#\r\n]+)[\"']?\s*$",
        r"^\s*mineru_token\s*:\s*[\"']?([^\"'#\r\n]+)[\"']?\s*$",
    ]
    for pattern in patterns:
        match = re.search(pattern, content, flags=re.MULTILINE)
        if match:
            return sanitize_config_value(match.group(1))
    return ""


def sanitize_config_value(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    placeholders = {
        "your_token_here",
        "your_mineru_api_token_here",
        "your_access_token_here",
        "your_paddle_token_here",
        "your-endpoint.example.com",
    }
    if lowered in placeholders:
        return ""
    return text


def resolve_mineru_token(env: dict[str, str]) -> str:
    return (
        sanitize_config_value(first_non_empty(env, "MINERU_API_TOKEN"))
        or sanitize_config_value(os.environ.get("MINERU_API_TOKEN"))
        or sanitize_config_value(os.environ.get("MINERU_TOKEN"))
        or read_official_mineru_token()
    )


def has_paddle_config(env: dict[str, str]) -> bool:
    return bool(
        sanitize_config_value(
            first_non_empty(
                env,
                "PADDLEOCR_DOC_PARSING_API_URL",
                "PADDLE_OCR_API_ENDPOINT",
                "API_URL",
            )
        )
        and sanitize_config_value(
            first_non_empty(
                env,
                "PADDLEOCR_ACCESS_TOKEN",
                "PADDLE_OCR_API_KEY",
                "TOKEN",
            )
        )
    )
