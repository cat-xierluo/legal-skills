from __future__ import annotations

import base64
import math
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

DEFAULT_TIMEOUT_SECONDS = 600
DEFAULT_BATCH_PAGES = 40
DEFAULT_MAX_BASE64_MB = 20.0

SUPPORTED_IMAGE_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tiff",
    ".tif",
    ".webp",
)
SUPPORTED_LOCAL_SUFFIXES = (".pdf",) + SUPPORTED_IMAGE_SUFFIXES


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


def first_non_empty(env: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = env.get(key, "").strip()
        if value:
            return value
    return ""


def normalize_api_url(api_url: str) -> str:
    url = api_url.strip()
    if not url:
        raise ValueError("未配置 PaddleOCR API 地址")
    if "://" not in url:
        url = f"https://{url}"

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"https", "http"}:
        raise ValueError("PaddleOCR API 地址必须以 https:// 或 http:// 开头")
    if parsed.scheme == "http" and host not in {"127.0.0.1", "localhost"}:
        raise ValueError("仅允许 localhost / 127.0.0.1 使用 http://")
    if not parsed.path.rstrip("/").endswith("/layout-parsing"):
        raise ValueError(
            "PaddleOCR API 地址必须是完整的 layout-parsing 端点，例如 "
            "https://your-endpoint/layout-parsing"
        )
    return url


def get_runtime_config() -> dict[str, Any]:
    file_env = read_env_file(get_config_path())
    merged_env = {**file_env, **os.environ}

    api_url = first_non_empty(merged_env, "PADDLEOCR_DOC_PARSING_API_URL")
    access_token = first_non_empty(merged_env, "PADDLEOCR_ACCESS_TOKEN")

    if not api_url:
        raise ValueError(
            "未配置 PADDLEOCR_DOC_PARSING_API_URL。请先编辑 paddle-ocr/config/.env。"
        )
    if not access_token:
        raise ValueError(
            "未配置 PADDLEOCR_ACCESS_TOKEN。请先编辑 paddle-ocr/config/.env。"
        )

    return {
        "api_url": normalize_api_url(api_url),
        "access_token": access_token,
        "doc_orientation": parse_bool(
            first_non_empty(merged_env, "PADDLEOCR_DOC_ORIENTATION"),
            default=False,
        ),
        "doc_unwarp": parse_bool(
            first_non_empty(merged_env, "PADDLEOCR_DOC_UNWARP"),
            default=False,
        ),
        "chart_recognition": parse_bool(
            first_non_empty(merged_env, "PADDLEOCR_CHART_RECOG"),
            default=False,
        ),
        "timeout_seconds": parse_positive_float(
            first_non_empty(merged_env, "PADDLEOCR_DOC_PARSING_TIMEOUT"),
            default=DEFAULT_TIMEOUT_SECONDS,
        ),
        "batch_pages": parse_positive_int(
            first_non_empty(merged_env, "PADDLEOCR_BATCH_PAGES"),
            default=DEFAULT_BATCH_PAGES,
        ),
        "max_base64_mb": parse_positive_float(
            first_non_empty(merged_env, "PADDLEOCR_MAX_BASE64_MB"),
            default=DEFAULT_MAX_BASE64_MB,
        ),
        "log_level": first_non_empty(merged_env, "PADDLEOCR_LOG_LEVEL") or "medium",
    }


def detect_file_type(path_or_url: str) -> int:
    normalized = path_or_url.lower()
    if normalized.startswith(("http://", "https://")):
        normalized = unquote(urlparse(normalized).path)

    if normalized.endswith(".pdf"):
        return 0
    if normalized.endswith(SUPPORTED_IMAGE_SUFFIXES):
        return 1
    raise ValueError(f"不支持的文件类型：{path_or_url}")


def is_pdf_file(path: Path) -> bool:
    return path.suffix.lower() == ".pdf"


def load_file_as_base64(file_path: str) -> str:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在：{file_path}")
    if not path.is_file():
        raise ValueError(f"不是普通文件：{file_path}")
    if path.stat().st_size == 0:
        raise ValueError(f"文件为空：{file_path}")
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def _error(code: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "text": "",
        "result": None,
        "error": {"code": code, "message": message},
    }


def make_request(
    *,
    api_url: str,
    access_token: str,
    payload: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    headers = {
        "Authorization": f"token {access_token}",
        "Content-Type": "application/json",
        "Client-Platform": "private-legal-skill",
    }

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(api_url, json=payload, headers=headers)
    except httpx.TimeoutException as error:
        raise RuntimeError(f"请求超时：{timeout_seconds} 秒") from error
    except httpx.RequestError as error:
        raise RuntimeError(f"网络请求失败：{error}") from error

    if response.status_code != 200:
        detail = response.text[:500].strip() or "空响应"
        if response.status_code == 403:
            raise RuntimeError(f"鉴权失败（403）：{detail}")
        if response.status_code == 429:
            raise RuntimeError(f"配额或频率受限（429）：{detail}")
        raise RuntimeError(f"接口错误（{response.status_code}）：{detail}")

    try:
        result = response.json()
    except ValueError as error:
        raise RuntimeError(f"接口返回的不是合法 JSON：{response.text[:200]}") from error

    if not isinstance(result, dict):
        raise RuntimeError("接口返回结构异常：顶层不是对象")

    if result.get("errorCode", 0) != 0:
        raise RuntimeError(f"接口返回错误：{result.get('errorMsg', '未知错误')}")

    return result


def extract_markdown_and_images(provider_result: dict[str, Any]) -> tuple[str, dict[str, str]]:
    raw_result = provider_result.get("result")
    if not isinstance(raw_result, dict):
        raise ValueError("接口返回结构异常：缺少 result 对象")

    layout_results = raw_result.get("layoutParsingResults")
    if not isinstance(layout_results, list) or not layout_results:
        raise ValueError("接口未返回 layoutParsingResults")

    texts: list[str] = []
    images: dict[str, str] = {}

    for index, page_result in enumerate(layout_results):
        if not isinstance(page_result, dict):
            raise ValueError(f"第 {index + 1} 页结构异常")
        markdown = page_result.get("markdown")
        if not isinstance(markdown, dict):
            raise ValueError(f"第 {index + 1} 页缺少 markdown 字段")
        text = markdown.get("text")
        if isinstance(text, str) and text.strip():
            texts.append(text)
        page_images = markdown.get("images")
        if isinstance(page_images, dict):
            for key, value in page_images.items():
                images[str(key)] = str(value)

    return "\n\n".join(texts), images


def parse_document(
    *,
    file_path: str | None = None,
    file_url: str | None = None,
    file_type: int | None = None,
    visualize: bool = False,
) -> dict[str, Any]:
    if bool(file_path) == bool(file_url):
        return _error("INPUT_ERROR", "必须在 file_path 和 file_url 中二选一")

    try:
        runtime = get_runtime_config()
    except ValueError as error:
        return _error("CONFIG_ERROR", str(error))

    try:
        if file_path:
            resolved_file_type = file_type if file_type is not None else detect_file_type(file_path)
            payload = {
                "file": load_file_as_base64(file_path),
                "fileType": resolved_file_type,
            }
        else:
            assert file_url is not None
            payload = {
                "file": file_url.strip(),
            }
            try:
                resolved_file_type = file_type if file_type is not None else detect_file_type(file_url)
            except ValueError:
                resolved_file_type = None
            if resolved_file_type is not None:
                payload["fileType"] = resolved_file_type

        payload["useDocOrientationClassify"] = runtime["doc_orientation"]
        payload["useDocUnwarping"] = runtime["doc_unwarp"]
        payload["useChartRecognition"] = runtime["chart_recognition"]
        payload["visualize"] = visualize
    except (ValueError, OSError, MemoryError) as error:
        return _error("INPUT_ERROR", str(error))

    try:
        provider_result = make_request(
            api_url=runtime["api_url"],
            access_token=runtime["access_token"],
            payload=payload,
            timeout_seconds=runtime["timeout_seconds"],
        )
        text, _images = extract_markdown_and_images(provider_result)
    except (RuntimeError, ValueError) as error:
        return _error("API_ERROR", str(error))

    return {
        "ok": True,
        "text": text,
        "result": provider_result,
        "error": None,
    }
