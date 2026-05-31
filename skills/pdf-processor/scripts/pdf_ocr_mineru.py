#!/usr/bin/env python3
"""
MinerU API 后端模块。

负责：
- MinerU Token 认证与刷新提示
- MinerU API 请求构造（创建任务、上传文件、轮询结果）
- MinerU 结果解析（JSON/ZIP -> 分页 entries）
- MinerU 后端执行流程

依赖：
- pdf_runtime: HTTP 工具、response_success
- pdf_ocr_layered: extract_payload, apply_page_entries_as_layered_pdf
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import zipfile
from pathlib import Path
from urllib import error

from pdf_runtime import (
    http_get_bytes,
    http_get_json,
    http_post_json,
    http_put_bytes,
    response_success,
)

from pdf_ocr_layered import (
    apply_page_entries_as_layered_pdf,
    extract_payload,
    _as_float,
    _bbox_to_poly4,
    _poly_to_points,
)


# ---------- MinerU 常量 ----------

MINERU_TOKEN_REFRESH_URL = "https://mineru.net/apiManage/token"
MINERU_TOKEN_TTL_DAYS = 90


# ---------- Token 认证异常 ----------

class MinerUTokenExpiredError(RuntimeError):
    """MinerU Token 无效或过期。"""


def build_mineru_token_refresh_message(detail: str = "") -> str:
    msg = (
        f"MinerU API Token 可能无效或已过期（有效期约 {MINERU_TOKEN_TTL_DAYS} 天）。"
        f"请前往 {MINERU_TOKEN_REFRESH_URL} 更新 Token，"
        "并同步更新 config/.env 中的 MINERU_API_TOKEN（如使用则同时更新 MINERU_USER_TOKEN）。"
    )
    detail = (detail or "").strip()
    if detail:
        return f"{msg} 详情: {detail}"
    return msg


def _contains_mineru_auth_error_text(raw: str) -> bool:
    text = (raw or "").strip().lower()
    if not text:
        return False
    keywords = (
        "unauthorized",
        "invalid token",
        "token expired",
        "token is expired",
        "access denied",
        "forbidden",
        "signature has expired",
        "token无效",
        "token过期",
        "令牌无效",
        "令牌过期",
        "鉴权失败",
        "无权限",
    )
    if any(k in text for k in keywords):
        return True
    if ("401" in text or "403" in text) and ("token" in text or "auth" in text):
        return True
    return False


def _extract_http_error_detail(exc: error.HTTPError) -> str:
    body = ""
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""
    parts = [f"HTTP {exc.code}"]
    if exc.reason:
        parts.append(str(exc.reason))
    if body:
        parts.append(body.strip())
    return " | ".join(parts)


def _is_mineru_auth_error_payload(resp: dict) -> bool:
    if not isinstance(resp, dict):
        return False

    for key in ("errorCode", "code", "status", "http_code", "httpStatus"):
        val = resp.get(key)
        if val is None:
            continue
        if str(val).strip().lower() in {"401", "403", "unauthorized", "forbidden"}:
            return True

    for key in ("msg", "message", "error", "err_msg", "error_msg", "detail"):
        val = resp.get(key)
        if isinstance(val, str) and _contains_mineru_auth_error_text(val):
            return True

    try:
        merged = json.dumps(resp, ensure_ascii=False)
    except Exception:
        merged = str(resp)
    return _contains_mineru_auth_error_text(merged)


def _raise_if_mineru_auth_failed(resp: dict):
    if _is_mineru_auth_error_payload(resp):
        raise MinerUTokenExpiredError(build_mineru_token_refresh_message())


# ---------- MinerU API 辅助 ----------

def map_tesseract_lang_to_mineru(language: str) -> str:
    """将 Tesseract 风格语言参数映射为 MinerU 语言参数。"""
    lang = (language or "").lower()
    if "chi_sim" in lang or "chi_tra" in lang or "ch" in lang:
        return "ch"
    if "eng" in lang and "+" not in lang:
        return "en"
    return "auto"


def mineru_api_url(base_url: str, path: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    suffix = path if path.startswith("/") else f"/{path}"
    if base.lower().endswith("/api/v4") and suffix.lower().startswith("/api/v4/"):
        suffix = suffix[len("/api/v4"):]
    return f"{base}{suffix}"


def build_mineru_headers(args) -> dict:
    headers = {"Content-Type": "application/json"}
    token = os.getenv(args.mineru_api_token_env, "").strip()
    if not token and args.mineru_api_token_env != "TOKEN":
        token = os.getenv("TOKEN", "").strip()
    user_token = os.getenv(args.mineru_user_token_env, "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if user_token:
        headers["token"] = user_token
    elif token:
        headers["token"] = token
    return headers


def build_mineru_create_payload(args, extra_payload: dict) -> dict:
    payload = {
        "files": [
            {
                "name": Path(args.input).name,
                "is_ocr": True,
            }
        ]
    }
    if args.mineru_model_version:
        payload["model_version"] = args.mineru_model_version
    if args.mineru_language:
        payload["language"] = args.mineru_language
    else:
        payload["language"] = map_tesseract_lang_to_mineru(args.language)
    payload["enable_formula"] = bool(args.mineru_enable_formula)
    payload["enable_table"] = bool(args.mineru_enable_table)
    payload.update(extra_payload)
    return payload


def extract_mineru_batch_info(data_payload: dict) -> tuple[str, str]:
    batch_id = str(data_payload.get("batch_id") or data_payload.get("id") or "").strip()
    upload_url = ""

    candidates = data_payload.get("file_urls") or data_payload.get("upload_urls") or []
    if isinstance(candidates, list):
        for item in candidates:
            if isinstance(item, str) and item.strip():
                upload_url = item.strip()
                break
            if isinstance(item, dict):
                for key in ("upload_url", "url", "file_url", "put_url"):
                    val = str(item.get(key) or "").strip()
                    if val:
                        upload_url = val
                        break
            if upload_url:
                break

    if not upload_url:
        upload_url = str(data_payload.get("upload_url") or "").strip()
    return batch_id, upload_url


def extract_mineru_upload_headers(data_payload: dict) -> dict:
    """
    解析 MinerU 创建任务返回中的上传请求头（用于 OSS PUT）。
    常见格式：headers=[{"x-oss-...":"..."}, ...]
    """
    raw = data_payload.get("headers") if isinstance(data_payload, dict) else None
    if not raw:
        return {}

    headers: dict[str, str] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k is None:
                continue
            key = str(k).strip()
            if not key:
                continue
            headers[key] = "" if v is None else str(v)
        return headers

    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                for k, v in item.items():
                    if k is None:
                        continue
                    key = str(k).strip()
                    if not key:
                        continue
                    headers[key] = "" if v is None else str(v)
    return headers


# ---------- MinerU JSON 结果解析 ----------

def _as_num_list(obj, length: int) -> list[float] | None:
    if not isinstance(obj, (list, tuple)) or len(obj) < length:
        return None
    nums = []
    for i in range(length):
        try:
            nums.append(float(obj[i]))
        except Exception:
            return None
    return nums


def _collect_rows_from_mineru_obj(obj, rows: list[tuple[str, float, list[list[float]]]]):
    if isinstance(obj, list):
        for item in obj:
            _collect_rows_from_mineru_obj(item, rows)
        return

    if not isinstance(obj, dict):
        return

    content = obj.get("content")
    category = str(obj.get("type") or obj.get("category_type") or "").lower()
    if isinstance(content, str):
        text = content.strip()
        if text and category not in {"image", "table", "figure"}:
            poly = _poly_to_points(obj.get("poly"))
            if len(poly) < 4:
                poly = _bbox_to_poly4(obj.get("bbox"))
            if len(poly) >= 4:
                score = _as_float(obj.get("score"), default=1.0)
                rows.append((text, score, poly[:4]))

    for val in obj.values():
        if isinstance(val, (dict, list)):
            _collect_rows_from_mineru_obj(val, rows)


def extract_mineru_page_entries_from_json(doc_json) -> list[dict]:
    pages = None
    if isinstance(doc_json, dict):
        for key in ("pdf_info", "pages", "results", "doc_layout_result"):
            if isinstance(doc_json.get(key), list):
                pages = doc_json.get(key)
                break
        if pages is None and isinstance(doc_json.get("layout_dets"), list):
            pages = [doc_json]
    elif isinstance(doc_json, list):
        pages = doc_json

    if not isinstance(pages, list):
        return []

    entries = []
    for page_obj in pages:
        if not isinstance(page_obj, dict):
            continue
        rows: list[tuple[str, float, list[list[float]]]] = []
        _collect_rows_from_mineru_obj(page_obj, rows)

        width = None
        height = None
        page_size = page_obj.get("page_size")
        size_nums = _as_num_list(page_size, 2)
        if size_nums:
            width, height = size_nums[0], size_nums[1]
        if (not width or not height) and rows:
            max_x = 0.0
            max_y = 0.0
            for _, _, poly in rows:
                for p in poly:
                    max_x = max(max_x, _as_float(p[0], 0.0))
                    max_y = max(max_y, _as_float(p[1], 0.0))
            if max_x > 0 and max_y > 0:
                width, height = max_x, max_y

        entries.append({"rows": rows, "width": width, "height": height})
    return entries


def extract_mineru_page_entries_from_zip(zip_bytes: bytes) -> list[dict]:
    with tempfile.TemporaryDirectory(prefix="mineru_ocr_") as tmpdir:
        zip_path = Path(tmpdir) / "result.zip"
        zip_path.write_bytes(zip_bytes)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmpdir)

        json_files = [p for p in Path(tmpdir).rglob("*.json")]
        if not json_files:
            return []

        def priority(path: Path) -> tuple[int, str]:
            name = path.name.lower()
            if name.endswith("_middle.json"):
                return (0, name)
            if "middle" in name:
                return (1, name)
            if name.endswith("_model.json"):
                return (2, name)
            if "model" in name:
                return (3, name)
            return (9, name)

        for jp in sorted(json_files, key=priority):
            try:
                data = json.loads(jp.read_text(encoding="utf-8"))
            except Exception:
                continue
            entries = extract_mineru_page_entries_from_json(data)
            if any((e.get("rows") or []) for e in entries):
                return entries
    return []


# ---------- MinerU 后端执行 ----------

def run_mineru_api_backend(args):
    """执行 MinerU API 后端（异步任务 + 结果 zip 解析 + 本地叠层）。"""
    if not args.mineru_api_base:
        raise ValueError("使用 MinerU 后端时必须提供 --mineru-api-base")

    import importlib
    pdf_ocr = importlib.import_module("pdf-ocr")
    load_json_file = pdf_ocr.load_json_file
    run_local_ocrmypdf_backend = pdf_ocr.run_local_ocrmypdf_backend

    extra_payload = load_json_file(args.mineru_api_extra_json)
    if not args.quiet:
        print("\nMinerU API 后端参数:")
        print(f"  base: {args.mineru_api_base}")
        print(f"  timeout: {args.mineru_api_timeout}s")
        print(f"  poll_interval: {args.mineru_poll_interval}s")
        print(f"  poll_timeout: {args.mineru_poll_timeout}s")
        print(f"  fallback_local: {not args.no_paddle_fallback_local}")

    if args.dry_run:
        print("[DRY-RUN] MinerU API 后端参数已输出，未实际请求。")
        args.backend_used = "mineru_api"
        return

    file_bytes = Path(args.input).read_bytes()
    headers = build_mineru_headers(args)
    create_payload = build_mineru_create_payload(args, extra_payload)

    try:
        if "Authorization" not in headers:
            raise RuntimeError(
                "MinerU API Token 未配置，请在 config/.env 中设置 MINERU_API_TOKEN。"
            )

        create_resp = http_post_json(
            mineru_api_url(args.mineru_api_base, "/api/v4/file-urls/batch"),
            create_payload,
            headers=headers,
            timeout=args.mineru_api_timeout,
        )
        if not isinstance(create_resp, dict):
            raise RuntimeError("MinerU 创建任务返回格式不是 JSON 对象")
        if not response_success(create_resp):
            _raise_if_mineru_auth_failed(create_resp)
            raise RuntimeError(f"MinerU 创建任务失败: {create_resp}")
        create_data = extract_payload(create_resp)
        batch_id, upload_url = extract_mineru_batch_info(create_data)
        if not batch_id or not upload_url:
            raise RuntimeError(f"MinerU 返回缺少 batch_id/upload_url: {create_data}")

        upload_headers = extract_mineru_upload_headers(create_data)
        http_put_bytes(
            upload_url,
            file_bytes,
            headers=upload_headers,
            timeout=args.mineru_api_timeout,
        )

        poll_url = mineru_api_url(args.mineru_api_base, f"/api/v4/extract-results/batch/{batch_id}")
        deadline = time.time() + max(1, args.mineru_poll_timeout)
        full_zip_url = ""
        failed_msg = ""
        while time.time() < deadline:
            poll_resp = http_get_json(poll_url, headers=headers, timeout=args.mineru_api_timeout)
            if not isinstance(poll_resp, dict):
                raise RuntimeError("MinerU 查询任务返回格式不是 JSON 对象")
            if not response_success(poll_resp):
                _raise_if_mineru_auth_failed(poll_resp)
                raise RuntimeError(f"MinerU 查询任务失败: {poll_resp}")

            poll_data = extract_payload(poll_resp)
            results = []
            if isinstance(poll_data, dict):
                val = (
                    poll_data.get("extract_result")
                    or poll_data.get("results")
                    or poll_data.get("extract_results")
                )
                if isinstance(val, list):
                    results = val
            elif isinstance(poll_data, list):
                results = poll_data

            target = results[0] if results else {}
            if isinstance(target, dict):
                state = str(target.get("state") or target.get("status") or "").lower()
                full_zip_url = str(
                    target.get("full_zip_url")
                    or target.get("zip_url")
                    or target.get("result_zip_url")
                    or ""
                ).strip()
                failed_msg = str(target.get("err_msg") or target.get("error_msg") or "").strip()
            else:
                state = ""

            if state in {"done", "success", "succeeded", "finished", "complete", "completed"} and full_zip_url:
                break
            if state in {"failed", "error", "cancelled", "canceled"}:
                raise RuntimeError(f"MinerU 任务失败: {failed_msg or state}")

            time.sleep(max(1, args.mineru_poll_interval))

        if not full_zip_url:
            raise RuntimeError("MinerU 任务轮询超时或未返回 full_zip_url")

        zip_bytes = http_get_bytes(full_zip_url, timeout=args.mineru_api_timeout)
        page_entries = extract_mineru_page_entries_from_zip(zip_bytes)
        if not page_entries:
            raise RuntimeError("MinerU 结果中未解析到可叠层文字坐标")

        layered_ok = apply_page_entries_as_layered_pdf(page_entries, args, source_name="MinerU")
        if not layered_ok:
            raise RuntimeError("MinerU 叠层失败")
        args.backend_used = "mineru_api(layered)"
        return
    except Exception as e:
        token_expired_msg = ""
        if isinstance(e, MinerUTokenExpiredError):
            token_expired_msg = str(e)
        elif isinstance(e, error.HTTPError):
            detail = _extract_http_error_detail(e)
            if e.code in {401, 403} or _contains_mineru_auth_error_text(detail):
                token_expired_msg = build_mineru_token_refresh_message(detail)
        elif _contains_mineru_auth_error_text(str(e)):
            token_expired_msg = build_mineru_token_refresh_message(str(e))

        if token_expired_msg:
            if args.no_paddle_fallback_local:
                raise RuntimeError(token_expired_msg)
            if not args.quiet:
                print(f"警告: {token_expired_msg}")
            run_local_ocrmypdf_backend(args)
            return

        if args.no_paddle_fallback_local:
            raise RuntimeError(f"MinerU API 后端失败: {e}")
        if not args.quiet:
            print(f"警告: MinerU API 后端失败，回退到本地 ocrmypdf。原因: {e}")
        run_local_ocrmypdf_backend(args)
