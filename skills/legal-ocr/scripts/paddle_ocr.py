from __future__ import annotations

import base64
import datetime
import fcntl
import json
import re
import shutil
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import httpx
except ImportError as error:
    print("缺少依赖: httpx")
    print("请使用: uv run scripts/convert.py <input>")
    print("或安装: pip install httpx")
    raise SystemExit(1) from error

from base import BackendResult, ConvertOptions
from common import (
    PADDLE_LOCAL_SUFFIXES,
    SourceInfo,
    estimate_base64_mb,
    first_non_empty,
    parse_bool,
    parse_positive_float,
    parse_positive_int,
    retry_with_backoff,
    sanitize_config_value,
    sanitize_name,
)
from pdf_tools import (
    extract_pages_to_pdf,
    format_pages_compact,
    get_pdf_page_count,
    parse_pages_spec,
    split_pdf_by_batch_size,
)


DEFAULT_TIMEOUT_SECONDS = 600
DEFAULT_BATCH_PAGES = 40
DEFAULT_MAX_BASE64_MB = 20.0
DEFAULT_POLL_INTERVAL = 5
DEFAULT_POLL_TIMEOUT = 1800
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_BASE_DELAY = 1.0
DEFAULT_RETRY_MAX_DELAY = 30.0
PADDLE_JOB_MODEL = "PP-OCRv5"
PADDLE_VL_MODEL = "PaddleOCR-VL-1.5"
VL_MODEL_PREFIX = "PaddleOCR-VL"
ASYNC_PATH_MARKER = "/api/v2/ocr/jobs"

VL_TEXT_LABELS = {
    "text",
    "doc_title",
    "title",
    "header",
    "footer",
    "list",
    "reference",
    "abstract",
    "catalog",
    "code",
    "table",
    "table_caption",
    "content",
    "paragraph_title",
    "section_title",
    "seal",
}


def normalize_api_url(api_url: str, protocol: str) -> str:
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
    if protocol == "sync" and not parsed.path.rstrip("/").endswith("/layout-parsing"):
        raise ValueError(
            "PaddleOCR API 地址必须是完整的 layout-parsing 端点，例如 "
            "https://your-endpoint/layout-parsing"
        )
    return url


def detect_file_type(path_or_url: str) -> int:
    lowered = path_or_url.lower()
    if lowered.startswith(("http://", "https://")):
        lowered = urlparse(lowered).path
    if lowered.endswith(".pdf"):
        return 0
    return 1


def load_file_as_base64(file_path: str) -> str:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在：{file_path}")
    if not path.is_file():
        raise ValueError(f"不是普通文件：{file_path}")
    if path.stat().st_size == 0:
        raise ValueError(f"文件为空：{file_path}")
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def decode_base64_image(raw_data: str) -> bytes:
    payload = raw_data.strip()
    if payload.startswith("data:") and "," in payload:
        payload = payload.split(",", 1)[1]
    return base64.b64decode(payload)


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


def extract_sync_page_count(provider_result: dict[str, Any]) -> int | None:
    raw_result = provider_result.get("result")
    if not isinstance(raw_result, dict):
        return None

    data_info = raw_result.get("dataInfo")
    if not isinstance(data_info, dict):
        return None

    counts: list[int] = []
    num_pages = data_info.get("numPages")
    if isinstance(num_pages, int) and num_pages >= 0:
        counts.append(num_pages)
    pages = data_info.get("pages")
    if isinstance(pages, list):
        counts.append(len(pages))
    return max(counts) if counts else None


def validate_sync_page_count(
    *,
    label: str,
    expected_pages: int | None,
    returned_pages: int | None,
) -> None:
    if expected_pages is None or returned_pages is None:
        return
    if returned_pages >= expected_pages:
        return
    raise RuntimeError(
        f"{label} PaddleOCR 返回页数不足：预期 {expected_pages} 页，实际返回 {returned_pages} 页。"
        "这通常说明服务端存在单次页数上限；请降低 PADDLEOCR_BATCH_PAGES，"
        "或使用 --pages 按更小范围重跑后再记录 OCR 完成。"
    )


def clean_vl_text(text: str) -> str:
    if not text:
        return ""
    text = re_sub(r"\$?\s*\\underline\{\\text\{([^}]*)\}\}\s*\$?", r"\1", text)
    text = re_sub(r"\$\$[^$]*\$\$", "", text)
    text = re_sub(r"\$([^$]*)\$", lambda match: match.group(1).strip(), text)
    text = re_sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re_sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re_sub(r"[ \t]+", " ", text)
    return text.strip()


def re_sub(pattern: str, repl: Any, text: str, flags: int = 0) -> str:
    import re

    return re.sub(pattern, repl, text, flags=flags)


def parse_pruned_result(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def extract_text_from_pruned(pruned: dict[str, Any]) -> str:
    parsing_blocks = pruned.get("parsing_res_list")
    if isinstance(parsing_blocks, list):
        parts: list[str] = []
        for block in parsing_blocks:
            if not isinstance(block, dict):
                continue
            if str(block.get("block_label", "")) not in VL_TEXT_LABELS:
                continue
            content = clean_vl_text(str(block.get("block_content", "")))
            if content:
                parts.append(content)
        if parts:
            return "\n\n".join(parts)

    rec_texts = pruned.get("rec_texts")
    if isinstance(rec_texts, list):
        return "\n".join(str(item).strip() for item in rec_texts if str(item).strip())
    return ""


def parse_jsonl_markdown(jsonl_text: str) -> tuple[str, dict[str, str], list[dict[str, Any]]]:
    texts: list[str] = []
    images: dict[str, str] = {}
    objects: list[dict[str, Any]] = []

    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            objects.append(obj)
        result = obj.get("result") if isinstance(obj, dict) else obj
        if not isinstance(result, dict):
            continue

        layout_results = result.get("layoutParsingResults")
        if isinstance(layout_results, list):
            for page_result in layout_results:
                if not isinstance(page_result, dict):
                    continue
                page_text_added = False
                markdown = page_result.get("markdown")
                if isinstance(markdown, dict):
                    text = markdown.get("text")
                    if isinstance(text, str) and text.strip():
                        texts.append(text.strip())
                        page_text_added = True
                    page_images = markdown.get("images")
                    if isinstance(page_images, dict):
                        for key, value in page_images.items():
                            images[str(key)] = str(value)
                if not page_text_added:
                    pruned = parse_pruned_result(page_result.get("prunedResult"))
                    if pruned:
                        text = extract_text_from_pruned(pruned)
                        if text:
                            texts.append(text)

        ocr_results = result.get("ocrResults") or result.get("ocrResult")
        if isinstance(ocr_results, dict):
            ocr_results = [ocr_results]
        if isinstance(ocr_results, list):
            for page_result in ocr_results:
                if not isinstance(page_result, dict):
                    continue
                pruned = parse_pruned_result(page_result.get("prunedResult")) or page_result
                text = extract_text_from_pruned(pruned)
                if text:
                    texts.append(text)

    return "\n\n".join(texts).strip(), images, objects


class PaddleOCRBackend:
    name = "paddle"

    def __init__(self, env: dict[str, str]) -> None:
        api_url = sanitize_config_value(
            first_non_empty(
                env,
                "PADDLEOCR_DOC_PARSING_API_URL",
                "PADDLE_OCR_API_ENDPOINT",
                "API_URL",
            )
        )
        access_token = sanitize_config_value(
            first_non_empty(
                env,
                "PADDLEOCR_ACCESS_TOKEN",
                "PADDLE_OCR_API_KEY",
                "TOKEN",
            )
        )
        if not api_url:
            raise ValueError("未配置 PADDLEOCR_DOC_PARSING_API_URL 或 PADDLE_OCR_API_ENDPOINT")
        if not access_token:
            raise ValueError("未配置 PADDLEOCR_ACCESS_TOKEN 或 PADDLE_OCR_API_KEY")

        configured_protocol = first_non_empty(env, "PADDLEOCR_API_PROTOCOL", "PADDLE_API_PROTOCOL").lower()
        if configured_protocol not in {"", "auto", "sync", "async"}:
            raise ValueError("PADDLEOCR_API_PROTOCOL 仅支持 auto/sync/async")
        inferred_protocol = "sync" if urlparse(api_url).path.rstrip("/").endswith("/layout-parsing") else "async"
        self.protocol = configured_protocol if configured_protocol in {"sync", "async"} else inferred_protocol
        self.api_url = normalize_api_url(api_url, self.protocol)
        self.access_token = access_token
        self.model = (
            first_non_empty(env, "PADDLEOCR_MODEL", "PADDLE_MODEL", "PADDLEOCR_API_MODEL")
            or (PADDLE_VL_MODEL if self.protocol == "async" else "layout-parsing")
        )
        fallback_raw = first_non_empty(env, "PADDLEOCR_MODEL_FALLBACK") or ""
        self.model_fallback = [m.strip() for m in fallback_raw.split(",") if m.strip()]
        self._fallback_index = 0
        self.doc_orientation = parse_bool(
            first_non_empty(env, "PADDLEOCR_DOC_ORIENTATION", "PADDLEOCR_VL_DOC_ORIENTATION"),
            default=self.protocol == "async",
        )
        self.doc_unwarp = parse_bool(
            first_non_empty(env, "PADDLEOCR_DOC_UNWARP", "PADDLEOCR_VL_DOC_UNWARPING"),
            default=self.protocol == "async",
        )
        self.chart_recognition = parse_bool(
            first_non_empty(env, "PADDLEOCR_CHART_RECOG", "PADDLEOCR_VL_CHART_RECOGNITION"),
            default=False,
        )
        self.textline_orientation = parse_bool(
            first_non_empty(env, "PADDLEOCR_TEXTLINE_ORIENTATION"),
            default=False,
        )
        self.layout_detection = parse_bool(
            first_non_empty(env, "PADDLEOCR_VL_LAYOUT_DETECTION"),
            default=True,
        )
        self.layout_shape_mode = first_non_empty(env, "PADDLEOCR_VL_LAYOUT_SHAPE_MODE") or "rect"
        self.visualize = parse_bool(first_non_empty(env, "PADDLEOCR_VISUALIZE"), default=False)
        self.extra_json_path = first_non_empty(env, "PADDLEOCR_API_EXTRA_JSON", "PADDLE_API_EXTRA_JSON")
        self.timeout_seconds = parse_positive_float(
            first_non_empty(env, "PADDLEOCR_DOC_PARSING_TIMEOUT"),
            default=DEFAULT_TIMEOUT_SECONDS,
        )
        self.poll_interval = parse_positive_int(
            first_non_empty(env, "PADDLEOCR_POLL_INTERVAL"),
            default=DEFAULT_POLL_INTERVAL,
        )
        self.poll_timeout = parse_positive_int(
            first_non_empty(env, "PADDLEOCR_POLL_TIMEOUT"),
            default=DEFAULT_POLL_TIMEOUT,
        )
        self.batch_pages = parse_positive_int(
            first_non_empty(env, "PADDLEOCR_BATCH_PAGES"),
            default=DEFAULT_BATCH_PAGES,
        )
        self.max_base64_mb = parse_positive_float(
            first_non_empty(env, "PADDLEOCR_MAX_BASE64_MB"),
            default=DEFAULT_MAX_BASE64_MB,
        )
        self.retry_attempts = parse_positive_int(
            first_non_empty(env, "PADDLEOCR_RETRY_ATTEMPTS", "LEGAL_OCR_RETRY_ATTEMPTS"),
            default=DEFAULT_RETRY_ATTEMPTS,
        )
        self.retry_base_delay = parse_positive_float(
            first_non_empty(env, "PADDLEOCR_RETRY_BASE_DELAY", "LEGAL_OCR_RETRY_BASE_DELAY"),
            default=DEFAULT_RETRY_BASE_DELAY,
        )
        self.retry_max_delay = parse_positive_float(
            first_non_empty(env, "PADDLEOCR_RETRY_MAX_DELAY", "LEGAL_OCR_RETRY_MAX_DELAY"),
            default=DEFAULT_RETRY_MAX_DELAY,
        )
        self.daily_page_limit = parse_positive_int(
            first_non_empty(env, "PADDLEOCR_DAILY_PAGE_LIMIT"),
            default=0,
        )
        self._daily_usage_file = Path(
            first_non_empty(env, "PADDLEOCR_DAILY_USAGE_FILE")
            or "/tmp/paddleocr_daily_usage.json",
        )

    def _make_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"token {self.access_token}",
            "Content-Type": "application/json",
            "Client-Platform": "private-legal-skill",
        }

        def _post() -> httpx.Response:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                return client.post(self.api_url, json=payload, headers=headers)

        try:
            response = retry_with_backoff(
                _post,
                max_attempts=self.retry_attempts,
                base_delay=self.retry_base_delay,
                max_delay=self.retry_max_delay,
                on_retry=self._log_retry,
            )
        except httpx.TimeoutException as error:
            raise RuntimeError(f"PaddleOCR 请求超时：{self.timeout_seconds} 秒") from error
        except httpx.RequestError as error:
            raise RuntimeError(f"PaddleOCR 网络请求失败：{error}") from error

        if response.status_code != 200:
            detail = response.text[:500].strip() or "空响应"
            if response.status_code == 403:
                raise RuntimeError(f"PaddleOCR 鉴权失败（403）：{detail}")
            if response.status_code == 429:
                raise RuntimeError(f"PaddleOCR 配额或频率受限（429）：{detail}")
            raise RuntimeError(f"PaddleOCR 接口错误（{response.status_code}）：{detail}")

        try:
            result = response.json()
        except ValueError as error:
            raise RuntimeError(f"PaddleOCR 返回的不是合法 JSON：{response.text[:200]}") from error

        if not isinstance(result, dict):
            raise RuntimeError("PaddleOCR 返回结构异常：顶层不是对象")
        if result.get("errorCode", 0) != 0:
            raise RuntimeError(f"PaddleOCR 返回错误：{result.get('errorMsg', '未知错误')}")
        return result

    def _log_retry(self, attempt: int, exc: BaseException, delay: float) -> None:
        print(
            f"PaddleOCR 瞬态错误 {type(exc).__name__}：{exc}。"
            f"第 {attempt}/{self.retry_attempts - 1} 次重试，等待 {delay:.1f}s",
            file=__import__("sys").stderr,
        )

    def _parse_document(
        self,
        *,
        file_path: str | None = None,
        file_url: str | None = None,
    ) -> dict[str, Any]:
        if bool(file_path) == bool(file_url):
            raise ValueError("必须在 file_path 和 file_url 中二选一")

        if file_path:
            payload: dict[str, Any] = {
                "file": load_file_as_base64(file_path),
                "fileType": detect_file_type(file_path),
            }
        else:
            assert file_url is not None
            payload = {
                "file": file_url.strip(),
                "fileType": detect_file_type(file_url),
            }

        payload["useDocOrientationClassify"] = self.doc_orientation
        payload["useDocUnwarping"] = self.doc_unwarp
        payload["useChartRecognition"] = self.chart_recognition
        payload["visualize"] = False
        return self._make_request(payload)

    def _is_vl_model(self) -> bool:
        return self.model.startswith(VL_MODEL_PREFIX)

    def _build_async_optional_payload(self) -> dict[str, Any]:
        if self._is_vl_model():
            payload: dict[str, Any] = {
                "useDocOrientationClassify": self.doc_orientation,
                "useDocUnwarping": self.doc_unwarp,
                "useLayoutDetection": self.layout_detection,
                "useChartRecognition": self.chart_recognition,
                "layoutShapeMode": self.layout_shape_mode,
                "visualize": self.visualize,
            }
        else:
            payload = {
                "useDocOrientationClassify": self.doc_orientation,
                "useDocUnwarping": self.doc_unwarp,
                "useTextlineOrientation": self.textline_orientation,
                "visualize": self.visualize,
            }

        if self.extra_json_path:
            extra_path = Path(self.extra_json_path).expanduser()
            if extra_path.exists():
                try:
                    extra = json.loads(extra_path.read_text(encoding="utf-8"))
                except ValueError as error:
                    raise ValueError(f"PADDLEOCR_API_EXTRA_JSON 不是合法 JSON：{extra_path}") from error
                if not isinstance(extra, dict):
                    raise ValueError(f"PADDLEOCR_API_EXTRA_JSON 顶层必须是对象：{extra_path}")
                payload.update(extra)
        return payload

    def _submit_async_job(self, input_path: Path) -> tuple[str, dict[str, Any]]:
        optional_payload = self._build_async_optional_payload()
        headers = {"Authorization": f"bearer {self.access_token}"}
        fields = {
            "model": self.model,
            "optionalPayload": json.dumps(optional_payload, ensure_ascii=False),
        }
        files = {"file": (input_path.name, input_path.read_bytes())}

        def _post() -> httpx.Response:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                return client.post(self.api_url, data=fields, files=files, headers=headers)

        try:
            response = retry_with_backoff(
                _post,
                max_attempts=self.retry_attempts,
                base_delay=self.retry_base_delay,
                max_delay=self.retry_max_delay,
                on_retry=self._log_retry,
            )
        except httpx.RequestError as error:
            raise RuntimeError(f"PaddleOCR 异步任务提交失败：{error}") from error

        if response.status_code not in {200, 201}:
            raise RuntimeError(f"PaddleOCR 异步任务提交失败（HTTP {response.status_code}）：{response.text[:500]}")
        try:
            payload = response.json()
        except ValueError as error:
            raise RuntimeError(f"PaddleOCR 异步任务提交返回非 JSON：{response.text[:200]}") from error
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        job_id = str(data.get("jobId") or "").strip() if isinstance(data, dict) else ""
        if not job_id:
            raise RuntimeError(f"PaddleOCR 异步任务未返回 jobId：{payload}")
        return job_id, {"submit_response": payload, "optional_payload": optional_payload}

    def _poll_async_job(self, job_id: str) -> str:
        poll_url = f"{self.api_url.rstrip('/')}/{job_id}"
        headers = {"Authorization": f"bearer {self.access_token}"}
        deadline = time.time() + max(1, self.poll_timeout)
        last_payload: dict[str, Any] | None = None
        with httpx.Client(timeout=self.timeout_seconds) as client:
            while True:
                def _get_poll() -> httpx.Response:
                    return client.get(poll_url, headers=headers)

                try:
                    response = retry_with_backoff(
                        _get_poll,
                        max_attempts=self.retry_attempts,
                        base_delay=self.retry_base_delay,
                        max_delay=self.retry_max_delay,
                        on_retry=self._log_retry,
                    )
                except httpx.RequestError as error:
                    raise RuntimeError(f"PaddleOCR 异步任务轮询网络失败：{error}") from error

                if response.status_code not in {200, 201}:
                    raise RuntimeError(f"PaddleOCR 异步任务轮询失败（HTTP {response.status_code}）：{response.text[:500]}")
                try:
                    payload = response.json()
                except ValueError as error:
                    raise RuntimeError(f"PaddleOCR 异步任务轮询返回非 JSON：{response.text[:200]}") from error
                last_payload = payload
                data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
                if not isinstance(data, dict):
                    raise RuntimeError(f"PaddleOCR 异步任务轮询结构异常：{payload}")
                state = str(data.get("state", "")).lower()
                if state == "done":
                    result_url = data.get("resultUrl")
                    jsonl_url = ""
                    if isinstance(result_url, dict):
                        jsonl_url = str(result_url.get("jsonUrl") or "").strip()
                    if not jsonl_url:
                        raise RuntimeError(f"PaddleOCR 异步任务完成但未返回 jsonUrl：{data}")

                    def _get_jsonl() -> httpx.Response:
                        return client.get(jsonl_url)

                    try:
                        jsonl_response = retry_with_backoff(
                            _get_jsonl,
                            max_attempts=self.retry_attempts,
                            base_delay=self.retry_base_delay,
                            max_delay=self.retry_max_delay,
                            on_retry=self._log_retry,
                        )
                    except httpx.RequestError as error:
                        raise RuntimeError(f"PaddleOCR JSONL 下载网络失败：{error}") from error
                    if jsonl_response.status_code != 200:
                        raise RuntimeError(f"PaddleOCR JSONL 下载失败（HTTP {jsonl_response.status_code}）")
                    return jsonl_response.text
                if state == "failed":
                    raise RuntimeError(f"PaddleOCR 异步任务失败：{data.get('errorMsg') or data.get('errorMessage') or state}")
                if time.time() >= deadline:
                    raise RuntimeError(f"PaddleOCR 异步任务轮询超时（{self.poll_timeout}s）：{last_payload}")
                time.sleep(max(1, self.poll_interval))

    def _with_daily_lock(self, fn):
        self._daily_usage_file.parent.mkdir(parents=True, exist_ok=True)
        fd = open(self._daily_usage_file, "a+")  # noqa: SIM115
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            fd.seek(0)
            fn(fd)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()

    def _read_daily_usage(self) -> dict[str, Any]:
        try:
            text = self._daily_usage_file.read_text(encoding="utf-8")
            data = json.loads(text)
            if data.get("date") == datetime.date.today().isoformat():
                return data
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            pass
        return {"date": datetime.date.today().isoformat(), "models": {}}

    def _write_daily_usage(self, data: dict[str, Any]) -> None:
        tmp = self._daily_usage_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._daily_usage_file)

    def _add_daily_pages(self, model: str, pages: int) -> None:
        if not self.daily_page_limit or pages <= 0:
            return

        def _update(fd):
            fd.seek(0)
            raw = fd.read()
            try:
                data = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                data = {}
            if data.get("date") != datetime.date.today().isoformat():
                data = {"date": datetime.date.today().isoformat(), "models": {}}
            models = data.setdefault("models", {})
            models[model] = models.get(model, 0) + pages
            fd.seek(0)
            fd.truncate()
            fd.write(json.dumps(data, ensure_ascii=False))

        self._with_daily_lock(_update)

    def _check_daily_limit(self) -> None:
        if not self.daily_page_limit:
            return
        data = self._read_daily_usage()
        used = data.get("models", {}).get(self.model, 0)
        if used >= self.daily_page_limit:
            raise RuntimeError(
                f"PaddleOCR 每日限额：模型 {self.model} 今日已用 {used} 页，"
                f"限额 {self.daily_page_limit} 页（PADDLEOCR_DAILY_PAGE_LIMIT）"
            )

    def _is_quota_error(self, exc: Exception) -> bool:
        msg = str(exc).lower()
        return ("429" in msg or "403" in msg or "quota" in msg
                or "频率过高" in msg or "配额" in msg or "limit" in msg
                or "每日页数上限" in msg)

    def _try_model_fallback(self) -> bool:
        if self._fallback_index >= len(self.model_fallback):
            return False
        new_model = self.model_fallback[self._fallback_index]
        self._fallback_index += 1
        print(f"[fallback] 模型回退：{self.model} → {new_model}")
        self.model = new_model
        return True

    def _parse_document_async(self, input_path: Path, backend_dir: Path, label: str) -> dict[str, Any]:
        self._check_daily_limit()
        try:
            job_id, submit_meta = self._submit_async_job(input_path)
        except RuntimeError as exc:
            if self._is_quota_error(exc) and self._try_model_fallback():
                return self._parse_document_async(input_path, backend_dir, label)
            raise
        jsonl_text = self._poll_async_job(job_id)
        estimated_pages = get_pdf_page_count(input_path) or 1
        self._add_daily_pages(self.model, estimated_pages)
        jsonl_text = self._poll_async_job(job_id)
        text, images, objects = parse_jsonl_markdown(jsonl_text)
        if not text.strip():
            raise RuntimeError("PaddleOCR 异步任务完成，但未提取到有效文本")

        safe_label = sanitize_name(label)
        backend_dir.mkdir(parents=True, exist_ok=True)
        (backend_dir / f"{safe_label}.jsonl").write_text(jsonl_text, encoding="utf-8")
        (backend_dir / f"{safe_label}_summary.json").write_text(
            json.dumps(
                {
                    "protocol": "async",
                    "model": self.model,
                    "job_id": job_id,
                    "object_count": len(objects),
                    **submit_meta,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return {
            "ok": True,
            "protocol": "async",
            "model": self.model,
            "job_id": job_id,
            "text": text,
            "images": images,
            "result": {"jsonl_objects": objects},
        }

    def _prepare_pdf_batches(
        self,
        input_path: Path,
        pages_spec: str | None,
        temp_dir: Path,
    ) -> tuple[list[tuple[str, Path]], dict[str, Any]]:
        total_pages = get_pdf_page_count(input_path)
        selected_pages = (
            parse_pages_spec(pages_spec, total_pages)
            if pages_spec
            else list(range(total_pages))
        )
        selected_label = format_pages_compact(selected_pages)
        processed_page_count = len(selected_pages)

        estimated_subset_base64_mb = estimate_base64_mb(input_path)
        if processed_page_count and total_pages:
            estimated_subset_base64_mb *= processed_page_count / total_pages

        needs_batch = (
            processed_page_count > self.batch_pages
            or estimated_subset_base64_mb > self.max_base64_mb
        )

        if needs_batch:
            batch_specs = split_pdf_by_batch_size(
                input_path=input_path,
                output_dir=temp_dir / "pdf-batches",
                batch_size=self.batch_pages,
                page_indices=selected_pages,
            )
            batches = [(str(spec["label"]), Path(spec["path"])) for spec in batch_specs]
        else:
            if pages_spec:
                single_path = temp_dir / f"{input_path.stem}_selected.pdf"
                extract_pages_to_pdf(input_path, single_path, selected_pages)
                batches = [(selected_label, single_path)]
            else:
                batches = [("all-pages", input_path)]

        info = {
            "total_pages": total_pages,
            "processed_pages": processed_page_count,
            "selected_pages": selected_label,
            "needs_batch": needs_batch,
            "batch_pages": self.batch_pages,
            "estimated_base64_mb": round(estimated_subset_base64_mb, 2),
        }
        return batches, info

    def _save_images(
        self,
        batch_outputs: list[dict[str, Any]],
        assets_dir: Path,
    ) -> list[dict[str, str]]:
        saved: list[dict[str, str]] = []
        if not any(batch["images"] for batch in batch_outputs):
            return saved
        if assets_dir.exists():
            shutil.rmtree(assets_dir)
        assets_dir.mkdir(parents=True, exist_ok=True)
        used_names: set[str] = set()

        for batch in batch_outputs:
            batch_label = sanitize_name(batch["label"])
            for index, (source_path, image_data) in enumerate(
                sorted(batch["images"].items()),
                start=1,
            ):
                suffix = Path(str(source_path)).suffix.lower() or ".png"
                filename = f"{batch_label}_{index:03d}{suffix}"
                while filename in used_names:
                    filename = f"{batch_label}_{index:03d}_{len(used_names):03d}{suffix}"
                used_names.add(filename)

                target_path = assets_dir / filename
                if str(image_data).startswith(("http://", "https://")):
                    urllib.request.urlretrieve(str(image_data), target_path)
                else:
                    target_path.write_bytes(decode_base64_image(str(image_data)))

                saved.append(
                    {
                        "batch": batch["label"],
                        "source": str(source_path),
                        "path": str(target_path),
                        "filename": filename,
                    }
                )
        return saved

    def _write_backend_files(
        self,
        backend_dir: Path,
        batch_outputs: list[dict[str, Any]],
    ) -> None:
        backend_dir.mkdir(parents=True, exist_ok=True)
        for index, batch in enumerate(batch_outputs, start=1):
            if batch.get("protocol") == "async":
                continue
            label = sanitize_name(batch["label"])
            path = backend_dir / f"batch_{index:03d}_{label}.json"
            path.write_text(
                json.dumps(batch["envelope"], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def convert(
        self,
        source: SourceInfo,
        options: ConvertOptions,
        work_dir: Path,
        assets_dir: Path,
    ) -> BackendResult:
        if options.paddle_model:
            self.model = options.paddle_model

        if source.is_url:
            if source.suffix not in PADDLE_LOCAL_SUFFIXES:
                raise ValueError(f"PaddleOCR 不支持该远程文件类型：{source.suffix or source.raw}")
        elif source.suffix not in PADDLE_LOCAL_SUFFIXES:
            raise ValueError(f"PaddleOCR 不支持该本地文件类型：{source.suffix}")

        backend_dir = work_dir / "backend_result"
        batch_outputs: list[dict[str, Any]] = []
        processing: dict[str, Any]

        if source.is_url:
            if self.protocol == "async":
                raise ValueError("PaddleOCR 异步任务接口暂不支持直接提交远程 URL，请使用本地文件或 MinerU")
            envelope = self._parse_document(file_url=source.raw)
            text, images = extract_markdown_and_images(envelope)
            if not text.strip():
                raise RuntimeError("PaddleOCR 完成，但未提取到有效文本")
            batch_outputs.append(
                {
                    "label": "remote-url",
                    "input_path": source.raw,
                    "envelope": envelope,
                    "protocol": "sync",
                    "text": text,
                    "images": images,
                }
            )
            processing = {
                "mode": "remote-url",
                "batch_count": 1,
                "total_pages": None,
                "processed_pages": None,
                "selected_pages": options.pages,
            }
        else:
            assert source.path is not None
            if source.suffix == ".pdf":
                batch_inputs, processing = self._prepare_pdf_batches(
                    source.path,
                    options.pages,
                    work_dir,
                )
            else:
                if options.pages:
                    raise ValueError("--pages 仅适用于 PDF 文件")
                batch_inputs = [(source.base_name, source.path)]
                processing = {
                    "mode": "single",
                    "batch_count": 1,
                    "total_pages": None,
                    "processed_pages": 1,
                    "selected_pages": None,
                    "needs_batch": False,
                    "batch_pages": None,
                    "estimated_base64_mb": round(estimate_base64_mb(source.path), 2),
                }

            for label, input_path in batch_inputs:
                expected_pages = get_pdf_page_count(input_path) if source.suffix == ".pdf" else None
                returned_pages = None
                if self.protocol == "async":
                    envelope = self._parse_document_async(input_path, backend_dir, label)
                    text = envelope["text"]
                    images = envelope["images"]
                else:
                    envelope = self._parse_document(file_path=str(input_path))
                    returned_pages = extract_sync_page_count(envelope)
                    validate_sync_page_count(
                        label=label,
                        expected_pages=expected_pages,
                        returned_pages=returned_pages,
                    )
                    text, images = extract_markdown_and_images(envelope)
                if not text.strip():
                    raise RuntimeError(f"{label} OCR 完成，但未提取到有效文本")
                batch_outputs.append(
                    {
                        "label": label,
                        "input_path": str(input_path),
                        "envelope": envelope,
                        "protocol": self.protocol,
                        "expected_pages": expected_pages,
                        "returned_pages": returned_pages,
                        "text": text,
                        "images": images,
                    }
                )

        self._write_backend_files(backend_dir, batch_outputs)
        saved_images = self._save_images(batch_outputs, assets_dir)
        merged_text = "\n\n".join(batch["text"].strip() for batch in batch_outputs).strip()
        batches = [
            {
                "index": index,
                "label": batch["label"],
                "input_path": batch["input_path"],
                "expected_pages": batch.get("expected_pages"),
                "returned_pages": batch.get("returned_pages"),
                "text_length": len(batch["text"]),
                "image_count": len(batch["images"]),
            }
            for index, batch in enumerate(batch_outputs, start=1)
        ]

        metadata = {
            "processing": {
                **processing,
                "batch_count": len(batch_outputs),
                "mode": "batched" if len(batch_outputs) > 1 else processing.get("mode", "single"),
            },
            "config": {
                "timeout_seconds": self.timeout_seconds,
                "doc_orientation": self.doc_orientation,
                "doc_unwarp": self.doc_unwarp,
                "chart_recognition": self.chart_recognition,
                "protocol": self.protocol,
                "model": self.model,
                "textline_orientation": self.textline_orientation,
                "layout_detection": self.layout_detection,
                "layout_shape_mode": self.layout_shape_mode,
                "visualize": self.visualize,
                "poll_interval": self.poll_interval,
                "poll_timeout": self.poll_timeout,
                "batch_pages": self.batch_pages,
                "max_base64_mb": self.max_base64_mb,
            },
        }
        return BackendResult(
            backend=self.name,
            mode="api",
            provider="PaddleOCR Document Parsing API",
            markdown=merged_text,
            images=saved_images,
            batches=batches,
            metadata=metadata,
            backend_result_dir=backend_dir,
        )
