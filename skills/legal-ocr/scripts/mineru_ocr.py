from __future__ import annotations

import datetime
import fcntl
import json
import re
import shutil
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError as error:
    print("缺少依赖: httpx")
    print("请使用: uv run scripts/convert.py <input>")
    print("或安装: pip install httpx")
    raise SystemExit(1) from error

from base import BackendResult, ConvertOptions
from common import (
    MINERU_LOCAL_SUFFIXES,
    SourceInfo,
    first_non_empty,
    parse_bool,
    parse_positive_int,
    parse_positive_float,
    retry_with_backoff,
    resolve_mineru_token,
    sanitize_config_value,
    sanitize_name,
)
from pdf_tools import get_pdf_page_count


LIGHT_API_BASE = "https://mineru.net/api/v1/agent"
DEFAULT_TOKEN_API_BASE = "https://mineru.net/api/v4"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".jp2"}
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_BASE_DELAY = 1.0
DEFAULT_RETRY_MAX_DELAY = 30.0


def normalize_page_ranges(value: str | None) -> str:
    text = str(value or "").strip()
    return text


def resolve_token_model_version(configured_value: str | None, source_type: str) -> str:
    value = str(configured_value or "").strip()
    if value in {"pipeline", "vlm"}:
        return value
    if source_type == "remote_html_url":
        return "pipeline"
    return "pipeline"


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as error:
        raise RuntimeError(f"MinerU 返回的不是合法 JSON：{response.text[:200]}") from error
    if not isinstance(payload, dict):
        raise RuntimeError("MinerU 返回结构异常：顶层不是对象")
    return payload


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_upload_url(value: Any) -> str:
    upload_url = value
    if isinstance(upload_url, str):
        try:
            parsed = json.loads(upload_url)
            if isinstance(parsed, str):
                upload_url = parsed
        except ValueError:
            pass
    return str(upload_url).replace("\n", " ").replace("\r", " ").replace("\t", " ").strip()


def _normalize_headers(raw_headers: Any) -> dict[str, str]:
    headers: dict[str, str] = {}
    if isinstance(raw_headers, list):
        for item in raw_headers:
            if isinstance(item, dict):
                for key, value in item.items():
                    headers[str(key)] = str(value)
    elif isinstance(raw_headers, dict):
        for key, value in raw_headers.items():
            headers[str(key)] = str(value)
    return headers


def _find_markdown_file(root: Path) -> Path:
    candidates = sorted(root.rglob("*.md"))
    if not candidates:
        raise RuntimeError("MinerU 结果包中未找到 Markdown 文件")
    full = [path for path in candidates if path.name.lower() in {"full.md", "result.md"}]
    return full[0] if full else candidates[0]


def _copy_local_image_assets(source_root: Path, assets_dir: Path) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    used_names: set[str] = set()
    for image_path in sorted(source_root.rglob("*")):
        if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if assets_dir in image_path.parents:
            continue
        assets_dir.mkdir(parents=True, exist_ok=True)
        filename = sanitize_name(image_path.name)
        while filename in used_names or (assets_dir / filename).exists():
            filename = f"{image_path.stem}_{len(used_names):03d}{image_path.suffix.lower()}"
        used_names.add(filename)
        target = assets_dir / filename
        shutil.copy2(image_path, target)
        images.append(
            {
                "source": str(image_path),
                "path": str(target),
                "filename": filename,
                "kind": "local_asset",
            }
        )
    return images


def _download_remote_markdown_images(markdown: str, assets_dir: Path) -> list[dict[str, str]]:
    urls: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"!\[[^\]]*]\((https?://[^)\s]+)\)", markdown):
        url = match.group(1)
        if url not in seen:
            seen.add(url)
            urls.append(url)

    images: list[dict[str, str]] = []
    for index, url in enumerate(urls, start=1):
        suffix = Path(url.split("?", 1)[0]).suffix.lower()
        if suffix not in IMAGE_SUFFIXES:
            suffix = ".png"
        filename = f"remote_{index:03d}{suffix}"
        target = assets_dir / filename
        try:
            assets_dir.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(url, target)
            downloaded = True
        except Exception:  # noqa: BLE001
            downloaded = False
        images.append(
            {
                "source": url,
                "path": str(target),
                "filename": filename,
                "kind": "remote_markdown_asset",
                "downloaded": str(downloaded).lower(),
            }
        )
    return images


class MinerUBackend:
    name = "mineru"

    def __init__(self, env: dict[str, str]) -> None:
        self.env = env
        self.api_base = sanitize_config_value(first_non_empty(env, "MINERU_API_BASE")) or DEFAULT_TOKEN_API_BASE
        self.api_token = resolve_mineru_token(env)
        self.enable_ocr = parse_bool(first_non_empty(env, "MINERU_ENABLE_OCR"), default=True)
        self.enable_table = parse_bool(first_non_empty(env, "MINERU_ENABLE_TABLE"), default=True)
        self.enable_formula = parse_bool(first_non_empty(env, "MINERU_ENABLE_FORMULA"), default=False)
        self.language_code = first_non_empty(env, "MINERU_LANGUAGE_CODE") or "ch"
        self.model_version = first_non_empty(env, "MINERU_MODEL_VERSION") or "pipeline"
        self.page_ranges = normalize_page_ranges(first_non_empty(env, "MINERU_PAGE_RANGES"))
        self.poll_max = parse_positive_int(first_non_empty(env, "MINERU_POLL_MAX"), default=20)
        self.poll_sleep = parse_positive_int(first_non_empty(env, "MINERU_POLL_SLEEP"), default=10)
        self.retry_attempts = parse_positive_int(
            first_non_empty(env, "MINERU_RETRY_ATTEMPTS", "LEGAL_OCR_RETRY_ATTEMPTS"),
            default=DEFAULT_RETRY_ATTEMPTS,
        )
        self.retry_base_delay = parse_positive_float(
            first_non_empty(env, "MINERU_RETRY_BASE_DELAY", "LEGAL_OCR_RETRY_BASE_DELAY"),
            default=DEFAULT_RETRY_BASE_DELAY,
        )
        self.retry_max_delay = parse_positive_float(
            first_non_empty(env, "MINERU_RETRY_MAX_DELAY", "LEGAL_OCR_RETRY_MAX_DELAY"),
            default=DEFAULT_RETRY_MAX_DELAY,
        )
        self.daily_page_limit = parse_positive_int(
            first_non_empty(env, "MINERU_DAILY_PAGE_LIMIT"),
            default=0,
        )
        self._daily_usage_file = Path(
            first_non_empty(env, "MINERU_DAILY_USAGE_FILE")
            or "/tmp/mineru_daily_usage.json",
        )

    def _log_retry(self, attempt: int, exc: BaseException, delay: float) -> None:
        print(
            f"MinerU 瞬态错误 {type(exc).__name__}：{exc}。"
            f"第 {attempt}/{self.retry_attempts - 1} 次重试，等待 {delay:.1f}s",
            file=__import__("sys").stderr,
        )

    def verify_token(self) -> str:
        if not self.api_token:
            return "当前未配置 MinerU Token。默认仍可使用免登录轻量接口。"
        probe_task_id = "00000000-0000-0000-0000-000000000000"
        url = f"{self.api_base}/extract/task/{probe_task_id}"
        try:
            response = retry_with_backoff(
                lambda: httpx.get(
                    url,
                    headers={"Authorization": f"Bearer {self.api_token}"},
                    timeout=20,
                    # 2026-06-14 v1.4.3:绕过 env / 系统代理,避免 cron 沙箱下
                    # *_PROXY 含畸形值(如 ~/.zshrc 的 HTTPS_PROXY=http://127.0.0.1:$undef
                    # 被展开为 `http://127.0.0.1:`)导致 httpx 解析 proxy URL 抛
                    # `InvalidURL: Invalid port: ':1]'`。调的是公网 MinerU API,
                    # 本不该走本机代理。
                    trust_env=False,
                ),
                max_attempts=self.retry_attempts,
                base_delay=self.retry_base_delay,
                max_delay=self.retry_max_delay,
                on_retry=self._log_retry,
            )
        except httpx.RequestError as error:
            return f"Token 已读取，但当前无法连接到 {self.api_base}。诊断信息：{error}"

        if response.status_code in {401, 403}:
            raise RuntimeError("MinerU Token 已读取，但鉴权失败。请重新申请并更新 MINERU_API_TOKEN。")
        if response.status_code not in {200, 404}:
            return f"Token 已读取，但自检接口返回 HTTP {response.status_code}。响应：{response.text[:200]}"
        return f"Token 自检通过：已成功携带 Authorization 访问 {self.api_base}。"

    def _client(self) -> httpx.Client:
        # 2026-06-14 v1.4.3:trust_env=False,见 _self_test 注释
        return httpx.Client(timeout=None, trust_env=False)

    def _mode(self) -> str:
        return "token" if self.api_token else "light"

    def _effective_model(self, options: ConvertOptions, source: SourceInfo) -> str:
        return resolve_token_model_version(options.model or self.model_version, source.source_type)

    def _effective_page_ranges(self, options: ConvertOptions) -> str:
        return normalize_page_ranges(options.pages or self.page_ranges)

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
            data = json.loads(self._daily_usage_file.read_text(encoding="utf-8"))
            if data.get("date") == datetime.date.today().isoformat():
                return data
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            pass
        return {"date": datetime.date.today().isoformat(), "pages": 0}

    def _add_daily_pages(self, pages: int) -> None:
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
                data = {"date": datetime.date.today().isoformat(), "pages": 0}
            data["pages"] = data.get("pages", 0) + pages
            fd.seek(0)
            fd.truncate()
            fd.write(json.dumps(data, ensure_ascii=False))

        self._with_daily_lock(_update)

    def _check_daily_limit(self) -> None:
        if not self.daily_page_limit:
            return
        data = self._read_daily_usage()
        used = data.get("pages", 0)
        if used >= self.daily_page_limit:
            raise RuntimeError(
                f"MinerU 每日限额：今日已用 {used} 页，"
                f"限额 {self.daily_page_limit} 页（MINERU_DAILY_PAGE_LIMIT）"
            )

    def _check_light_limits(self, source: SourceInfo) -> None:
        if source.source_type == "remote_html_url":
            raise RuntimeError("网页 URL 需要配置 MinerU Token，免登录轻量接口不支持网页提取。")
        if not source.path:
            return
        if source.size_bytes and source.size_bytes > 10 * 1024 * 1024:
            raise RuntimeError("免登录轻量接口限制单文件 10 MB 内，请配置 MinerU Token 后重试。")
        page_count = source.page_count
        if source.suffix == ".pdf" and page_count is None:
            page_count = get_pdf_page_count(source.path)
        if page_count and page_count > 20:
            raise RuntimeError("免登录轻量接口限制 PDF 20 页内，请配置 MinerU Token 后重试。")

    def _download_zip_and_extract(self, result_url: str, backend_dir: Path, extract_dir: Path) -> Path:
        backend_dir.mkdir(parents=True, exist_ok=True)
        zip_path = backend_dir / "result.zip"
        with self._client() as client:
            try:
                response = retry_with_backoff(
                    lambda: client.get(result_url),
                    max_attempts=self.retry_attempts,
                    base_delay=self.retry_base_delay,
                    max_delay=self.retry_max_delay,
                    on_retry=self._log_retry,
                )
            except httpx.InvalidURL as error:
                # 2026-06-14 诊断性 logging:暴露服务端返回的 full_zip_url 真值,
                # 上游 `Invalid port: ':1]'` 短文案无法定位
                raise RuntimeError(
                    f"MinerU 结果包 URL 非法:full_zip_url={result_url!r} "
                    f"(httpx.InvalidURL: {error})"
                ) from error
            if response.status_code != 200:
                raise RuntimeError(f"下载 MinerU 结果包失败（HTTP {response.status_code}）")
            zip_path.write_bytes(response.content)
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(extract_dir)
        return _find_markdown_file(extract_dir)

    def _finalize_work_dir(
        self,
        *,
        mode: str,
        provider: str,
        markdown_file: Path,
        backend_dir: Path,
        assets_dir: Path,
        metadata: dict[str, Any],
        extraction_root: Path,
    ) -> BackendResult:
        markdown = markdown_file.read_text(encoding="utf-8", errors="replace").strip()
        if not markdown:
            raise RuntimeError("MinerU 完成，但 Markdown 为空")
        images = _copy_local_image_assets(extraction_root, assets_dir)
        images.extend(_download_remote_markdown_images(markdown, assets_dir))
        page_count = metadata.get("total_pages") or metadata.get("page_count") or 1
        self._add_daily_pages(int(page_count))
        return BackendResult(
            backend=self.name,
            mode=mode,
            provider=provider,
            markdown=markdown,
            images=images,
            batches=[],
            metadata=metadata,
            backend_result_dir=backend_dir,
        )

    def _convert_local_with_token(
        self,
        source: SourceInfo,
        options: ConvertOptions,
        work_dir: Path,
        assets_dir: Path,
    ) -> BackendResult:
        assert source.path is not None
        backend_dir = work_dir / "backend_result"
        extraction_root = work_dir / "extracted"
        page_ranges = self._effective_page_ranges(options)
        model_version = self._effective_model(options, source)
        data_id = f"convert_{int(time.time())}_{sanitize_name(source.base_name)}"
        file_item: dict[str, Any] = {
            "name": source.file_name,
            "is_ocr": self.enable_ocr,
            "data_id": data_id,
        }
        if page_ranges:
            file_item["page_ranges"] = page_ranges
        request_body = {
            "enable_formula": self.enable_formula,
            "language": self.language_code,
            "enable_table": self.enable_table,
            "model_version": model_version,
            "files": [file_item],
        }
        upload_ticket_path = backend_dir / "upload_ticket.json"

        with self._client() as client:
            response = retry_with_backoff(
                lambda: client.post(
                    f"{self.api_base}/file-urls/batch",
                    headers={
                        "Authorization": f"Bearer {self.api_token}",
                        "Content-Type": "application/json",
                    },
                    json=request_body,
                ),
                max_attempts=self.retry_attempts,
                base_delay=self.retry_base_delay,
                max_delay=self.retry_max_delay,
                on_retry=self._log_retry,
            )
            upload_ticket_path.parent.mkdir(parents=True, exist_ok=True)
            upload_ticket_path.write_text(response.text, encoding="utf-8")
            if response.status_code in {401, 403}:
                raise RuntimeError("MinerU Token 鉴权失败，请更新 MINERU_API_TOKEN。")
            if response.status_code not in {200, 201}:
                raise RuntimeError(f"申请 MinerU 上传地址失败（HTTP {response.status_code}）：{response.text[:500]}")

            upload_ticket = _safe_json(response)
            data = upload_ticket.get("data") if isinstance(upload_ticket.get("data"), dict) else upload_ticket
            batch_id = data.get("batch_id") or ""
            file_urls = data.get("file_urls") or []
            oss_headers = data.get("headers") or []
            if not batch_id or not file_urls:
                raise RuntimeError(f"MinerU 上传地址响应缺少 batch_id 或 file_urls：{upload_ticket}")
            upload_url = _normalize_upload_url(file_urls[0])
            headers = _normalize_headers(oss_headers)

            with source.path.open("rb") as handle:
                try:
                    upload_response = retry_with_backoff(
                        lambda: client.put(upload_url, content=handle.read(), headers=headers),
                        max_attempts=self.retry_attempts,
                        base_delay=self.retry_base_delay,
                        max_delay=self.retry_max_delay,
                        on_retry=self._log_retry,
                    )
                except httpx.InvalidURL as error:
                    # 2026-06-14 诊断性 logging:暴露 file_urls[0] 真值,
                    # _normalize_upload_url 不校验 URL,这是最高嫌疑点
                    raise RuntimeError(
                        f"MinerU 上传 URL 非法:file_urls[0]={file_urls[0]!r} "
                        f"normalized={upload_url!r} (httpx.InvalidURL: {error})"
                    ) from error
            if upload_response.status_code not in {200, 201}:
                raise RuntimeError(f"MinerU 文件上传失败（HTTP {upload_response.status_code}）")

            poll_path = backend_dir / "token_poll.json"
            result_url = ""
            last_payload: dict[str, Any] = {}
            for poll_count in range(1, self.poll_max + 1):
                time.sleep(self.poll_sleep)
                poll_response = retry_with_backoff(
                    lambda: client.get(
                        f"{self.api_base}/extract-results/batch/{batch_id}",
                        headers={"Authorization": f"Bearer {self.api_token}"},
                    ),
                    max_attempts=self.retry_attempts,
                    base_delay=self.retry_base_delay,
                    max_delay=self.retry_max_delay,
                    on_retry=self._log_retry,
                )
                poll_path.write_text(poll_response.text, encoding="utf-8")
                if poll_response.status_code in {401, 403}:
                    raise RuntimeError("MinerU Token 鉴权失败，请更新 MINERU_API_TOKEN。")
                if poll_response.status_code not in {200, 201}:
                    raise RuntimeError(f"查询 MinerU 结果失败（HTTP {poll_response.status_code}）：{poll_response.text[:500]}")
                last_payload = _safe_json(poll_response)
                result_list = ((last_payload.get("data") or {}).get("extract_result") or [])
                for item in result_list:
                    if item.get("state") == "done" and item.get("full_zip_url"):
                        result_url = item["full_zip_url"]
                        break
                    if item.get("state") == "failed":
                        raise RuntimeError(f"MinerU 处理失败：{item.get('err_msg') or '未知错误'}")
                if result_url:
                    break
            if not result_url:
                raise RuntimeError(f"MinerU 处理超时，已尝试 {self.poll_max} 次")
            _write_json(backend_dir / "token_final_poll.json", last_payload)

        markdown_file = self._download_zip_and_extract(result_url, backend_dir, extraction_root)
        return self._finalize_work_dir(
            mode="token",
            provider="MinerU Token API",
            markdown_file=markdown_file,
            backend_dir=backend_dir,
            assets_dir=assets_dir,
            extraction_root=extraction_root,
            metadata={
                "processing": {
                    "mode": "token-local",
                    "batch_id": batch_id,
                    "page_ranges": page_ranges or None,
                    "model_version": model_version,
                },
                "config": {
                    "api_base": self.api_base,
                    "enable_ocr": self.enable_ocr,
                    "enable_table": self.enable_table,
                    "enable_formula": self.enable_formula,
                    "language_code": self.language_code,
                },
            },
        )

    def _convert_remote_with_token(
        self,
        source: SourceInfo,
        options: ConvertOptions,
        work_dir: Path,
        assets_dir: Path,
    ) -> BackendResult:
        backend_dir = work_dir / "backend_result"
        extraction_root = work_dir / "extracted"
        page_ranges = self._effective_page_ranges(options)
        model_version = self._effective_model(options, source)
        request_body: dict[str, Any] = {
            "url": source.raw,
            "language": self.language_code,
            "is_ocr": self.enable_ocr,
            "enable_table": self.enable_table,
            "enable_formula": self.enable_formula,
            "model_version": model_version,
        }
        if page_ranges and source.source_type != "remote_html_url":
            request_body["page_ranges"] = page_ranges

        with self._client() as client:
            create_response = retry_with_backoff(
                lambda: client.post(
                    f"{self.api_base}/extract/task",
                    headers={
                        "Authorization": f"Bearer {self.api_token}",
                        "Content-Type": "application/json",
                    },
                    json=request_body,
                ),
                max_attempts=self.retry_attempts,
                base_delay=self.retry_base_delay,
                max_delay=self.retry_max_delay,
                on_retry=self._log_retry,
            )
            backend_dir.mkdir(parents=True, exist_ok=True)
            (backend_dir / "token_url_create.json").write_text(create_response.text, encoding="utf-8")
            if create_response.status_code in {401, 403}:
                raise RuntimeError("MinerU Token 鉴权失败，请更新 MINERU_API_TOKEN。")
            if create_response.status_code not in {200, 201}:
                raise RuntimeError(f"创建 MinerU URL 任务失败（HTTP {create_response.status_code}）：{create_response.text[:500]}")
            create_payload = _safe_json(create_response)
            task_id = ((create_payload.get("data") or {}).get("task_id")) or ""
            if create_payload.get("code") not in {0, None} or not task_id:
                raise RuntimeError(f"创建 MinerU URL 任务失败：{create_payload.get('msg') or create_payload}")

            poll_path = backend_dir / "token_url_poll.json"
            result_url = ""
            last_payload: dict[str, Any] = {}
            for _poll_count in range(1, self.poll_max + 1):
                time.sleep(self.poll_sleep)
                poll_response = retry_with_backoff(
                    lambda: client.get(
                        f"{self.api_base}/extract/task/{task_id}",
                        headers={"Authorization": f"Bearer {self.api_token}"},
                    ),
                    max_attempts=self.retry_attempts,
                    base_delay=self.retry_base_delay,
                    max_delay=self.retry_max_delay,
                    on_retry=self._log_retry,
                )
                poll_path.write_text(poll_response.text, encoding="utf-8")
                if poll_response.status_code in {401, 403}:
                    raise RuntimeError("MinerU Token 鉴权失败，请更新 MINERU_API_TOKEN。")
                if poll_response.status_code not in {200, 201}:
                    raise RuntimeError(f"查询 MinerU URL 任务失败（HTTP {poll_response.status_code}）：{poll_response.text[:500]}")
                last_payload = _safe_json(poll_response)
                data = last_payload.get("data") or {}
                if data.get("state") == "done" and data.get("full_zip_url"):
                    result_url = data["full_zip_url"]
                    break
                if data.get("state") == "failed":
                    raise RuntimeError(f"MinerU 处理失败：{data.get('err_msg') or '未知错误'}")
            if not result_url:
                raise RuntimeError(f"MinerU URL 任务处理超时，已尝试 {self.poll_max} 次")
            _write_json(backend_dir / "token_url_final_poll.json", last_payload)

        markdown_file = self._download_zip_and_extract(result_url, backend_dir, extraction_root)
        return self._finalize_work_dir(
            mode="token",
            provider="MinerU Token API",
            markdown_file=markdown_file,
            backend_dir=backend_dir,
            assets_dir=assets_dir,
            extraction_root=extraction_root,
            metadata={
                "processing": {
                    "mode": "token-url",
                    "task_id": task_id,
                    "source_type": source.source_type,
                    "page_ranges": page_ranges or None,
                    "model_version": model_version,
                },
                "config": {
                    "api_base": self.api_base,
                    "enable_ocr": self.enable_ocr,
                    "enable_table": self.enable_table,
                    "enable_formula": self.enable_formula,
                    "language_code": self.language_code,
                },
            },
        )

    def _convert_local_with_light(
        self,
        source: SourceInfo,
        work_dir: Path,
        assets_dir: Path,
    ) -> BackendResult:
        assert source.path is not None
        self._check_light_limits(source)
        backend_dir = work_dir / "backend_result"
        extraction_root = work_dir / "light"
        submit_body = {
            "file_name": source.file_name,
            "language": self.language_code,
            "is_ocr": self.enable_ocr,
        }

        with self._client() as client:
            response = retry_with_backoff(
                lambda: client.post(
                    f"{LIGHT_API_BASE}/parse/file",
                    headers={"Content-Type": "application/json"},
                    json=submit_body,
                ),
                max_attempts=self.retry_attempts,
                base_delay=self.retry_base_delay,
                max_delay=self.retry_max_delay,
                on_retry=self._log_retry,
            )
            backend_dir.mkdir(parents=True, exist_ok=True)
            (backend_dir / "light_submit.json").write_text(response.text, encoding="utf-8")
            if response.status_code not in {200, 201}:
                raise RuntimeError(f"MinerU 轻量接口提交失败（HTTP {response.status_code}）：{response.text[:500]}")
            submit_payload = _safe_json(response)
            data = submit_payload.get("data") or {}
            task_id = data.get("task_id") or ""
            upload_url = data.get("file_url") or ""
            if submit_payload.get("code") != 0 or not task_id or not upload_url:
                raise RuntimeError(f"MinerU 轻量接口提交失败：{submit_payload.get('msg') or submit_payload}")

            with source.path.open("rb") as handle:
                upload_response = retry_with_backoff(
                    lambda: client.put(upload_url, content=handle.read()),
                    max_attempts=self.retry_attempts,
                    base_delay=self.retry_base_delay,
                    max_delay=self.retry_max_delay,
                    on_retry=self._log_retry,
                )
            if upload_response.status_code not in {200, 201}:
                raise RuntimeError(f"MinerU 轻量接口文件上传失败（HTTP {upload_response.status_code}）")

            markdown_url = ""
            last_payload: dict[str, Any] = {}
            poll_path = backend_dir / "light_poll.json"
            for _poll_count in range(1, self.poll_max + 1):
                time.sleep(self.poll_sleep)
                poll_response = retry_with_backoff(
                    lambda: client.get(f"{LIGHT_API_BASE}/parse/{task_id}"),
                    max_attempts=self.retry_attempts,
                    base_delay=self.retry_base_delay,
                    max_delay=self.retry_max_delay,
                    on_retry=self._log_retry,
                )
                poll_path.write_text(poll_response.text, encoding="utf-8")
                if poll_response.status_code not in {200, 201}:
                    raise RuntimeError(f"MinerU 轻量接口轮询失败（HTTP {poll_response.status_code}）：{poll_response.text[:500]}")
                last_payload = _safe_json(poll_response)
                data = last_payload.get("data") or {}
                if data.get("state") == "done" and data.get("markdown_url"):
                    markdown_url = data["markdown_url"]
                    break
                if data.get("state") == "failed":
                    raise RuntimeError(f"MinerU 轻量接口处理失败：{data.get('err_msg') or '未知错误'}")
            if not markdown_url:
                raise RuntimeError(f"MinerU 轻量接口处理超时，已尝试 {self.poll_max} 次")
            _write_json(backend_dir / "light_final_poll.json", last_payload)

            extraction_root.mkdir(parents=True, exist_ok=True)
            markdown_file = extraction_root / "full.md"
            markdown_response = retry_with_backoff(
                lambda: client.get(markdown_url),
                max_attempts=self.retry_attempts,
                base_delay=self.retry_base_delay,
                max_delay=self.retry_max_delay,
                on_retry=self._log_retry,
            )
            if markdown_response.status_code not in {200, 201}:
                raise RuntimeError(f"下载 MinerU 轻量接口 Markdown 失败（HTTP {markdown_response.status_code}）")
            markdown_file.write_bytes(markdown_response.content)

        return self._finalize_work_dir(
            mode="light",
            provider="MinerU Light API",
            markdown_file=markdown_file,
            backend_dir=backend_dir,
            assets_dir=assets_dir,
            extraction_root=extraction_root,
            metadata={
                "processing": {
                    "mode": "light-local",
                    "task_id": task_id,
                    "markdown_url": markdown_url,
                },
                "config": {
                    "language_code": self.language_code,
                    "enable_ocr": self.enable_ocr,
                },
            },
        )

    def _convert_remote_with_light(
        self,
        source: SourceInfo,
        work_dir: Path,
        assets_dir: Path,
    ) -> BackendResult:
        self._check_light_limits(source)
        backend_dir = work_dir / "backend_result"
        extraction_root = work_dir / "light"
        submit_body = {
            "url": source.raw,
            "file_name": source.file_name,
            "language": self.language_code,
            "is_ocr": self.enable_ocr,
        }

        with self._client() as client:
            response = retry_with_backoff(
                lambda: client.post(
                    f"{LIGHT_API_BASE}/parse/url",
                    headers={"Content-Type": "application/json"},
                    json=submit_body,
                ),
                max_attempts=self.retry_attempts,
                base_delay=self.retry_base_delay,
                max_delay=self.retry_max_delay,
                on_retry=self._log_retry,
            )
            backend_dir.mkdir(parents=True, exist_ok=True)
            (backend_dir / "light_url_submit.json").write_text(response.text, encoding="utf-8")
            if response.status_code not in {200, 201}:
                raise RuntimeError(f"MinerU 轻量 URL 提交失败（HTTP {response.status_code}）：{response.text[:500]}")
            submit_payload = _safe_json(response)
            data = submit_payload.get("data") or {}
            task_id = data.get("task_id") or ""
            if submit_payload.get("code") != 0 or not task_id:
                raise RuntimeError(f"MinerU 轻量 URL 提交失败：{submit_payload.get('msg') or submit_payload}")

            markdown_url = ""
            last_payload: dict[str, Any] = {}
            poll_path = backend_dir / "light_url_poll.json"
            for _poll_count in range(1, self.poll_max + 1):
                time.sleep(self.poll_sleep)
                poll_response = retry_with_backoff(
                    lambda: client.get(f"{LIGHT_API_BASE}/parse/{task_id}"),
                    max_attempts=self.retry_attempts,
                    base_delay=self.retry_base_delay,
                    max_delay=self.retry_max_delay,
                    on_retry=self._log_retry,
                )
                poll_path.write_text(poll_response.text, encoding="utf-8")
                if poll_response.status_code not in {200, 201}:
                    raise RuntimeError(f"MinerU 轻量 URL 轮询失败（HTTP {poll_response.status_code}）：{poll_response.text[:500]}")
                last_payload = _safe_json(poll_response)
                data = last_payload.get("data") or {}
                if data.get("state") == "done" and data.get("markdown_url"):
                    markdown_url = data["markdown_url"]
                    break
                if data.get("state") == "failed":
                    raise RuntimeError(f"MinerU 轻量 URL 处理失败：{data.get('err_msg') or '未知错误'}")
            if not markdown_url:
                raise RuntimeError(f"MinerU 轻量 URL 处理超时，已尝试 {self.poll_max} 次")
            _write_json(backend_dir / "light_url_final_poll.json", last_payload)

            extraction_root.mkdir(parents=True, exist_ok=True)
            markdown_file = extraction_root / "full.md"
            markdown_response = retry_with_backoff(
                lambda: client.get(markdown_url),
                max_attempts=self.retry_attempts,
                base_delay=self.retry_base_delay,
                max_delay=self.retry_max_delay,
                on_retry=self._log_retry,
            )
            if markdown_response.status_code not in {200, 201}:
                raise RuntimeError(f"下载 MinerU 轻量 URL Markdown 失败（HTTP {markdown_response.status_code}）")
            markdown_file.write_bytes(markdown_response.content)

        return self._finalize_work_dir(
            mode="light",
            provider="MinerU Light API",
            markdown_file=markdown_file,
            backend_dir=backend_dir,
            assets_dir=assets_dir,
            extraction_root=extraction_root,
            metadata={
                "processing": {
                    "mode": "light-url",
                    "task_id": task_id,
                    "markdown_url": markdown_url,
                    "source_type": source.source_type,
                },
                "config": {
                    "language_code": self.language_code,
                    "enable_ocr": self.enable_ocr,
                },
            },
        )

    def convert(
        self,
        source: SourceInfo,
        options: ConvertOptions,
        work_dir: Path,
        assets_dir: Path,
    ) -> BackendResult:
        if source.source_type == "local_file" and source.suffix not in MINERU_LOCAL_SUFFIXES:
            raise ValueError(f"MinerU 不支持该本地文件类型：{source.suffix}")

        self._check_daily_limit()
        mode = self._mode()
        if mode == "token":
            if source.source_type == "local_file":
                return self._convert_local_with_token(source, options, work_dir, assets_dir)
            return self._convert_remote_with_token(source, options, work_dir, assets_dir)

        if source.source_type == "local_file":
            return self._convert_local_with_light(source, work_dir, assets_dir)
        return self._convert_remote_with_light(source, work_dir, assets_dir)
