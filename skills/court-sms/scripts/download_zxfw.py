#!/usr/bin/env python3
"""Download documents from the national court service platform (ZXFW).

The list API can be slow for a newly generated delivery. The defaults follow
the upstream-verified policy: three 30-second attempts with 3s/8s pauses.
Business-error responses are not retried because they are final API answers.
"""
from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import http.client
import json
import math
import os
import re
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from lawyer_config import DEFAULT_PATH, ProfileError, load_profiles, normalize_mobile_last4, select_identity


API_ENDPOINT = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/api/v1/sdfw/getWsListBySdbhNew"
RECEIPT_ENDPOINT = API_ENDPOINT.rsplit("/", 1)[0] + "/updateSdxxBySdzt"
IDENTITY_GATE_ENDPOINT = API_ENDPOINT.rsplit("/", 1)[0] + "/getSfhyKg"
IDENTITY_CHECK_ENDPOINT = API_ENDPOINT.rsplit("/", 1)[0] + "/checkSdryxx"
REQUIRED_PARAMS = ("qdbh", "sdbh", "sdsin")
ATTEMPTS = 3
MAX_IDENTITY_ATTEMPTS = 2
RETRY_DELAYS = (3.0, 8.0)
REQUEST_TIMEOUT = 30.0
DOWNLOAD_TIMEOUT = 60.0
API_HEADERS = {
    "Origin": "https://zxfw.court.gov.cn",
    "Referer": "https://zxfw.court.gov.cn/zxfw/",
}


class TransientDownloadError(RuntimeError):
    """A transport failure that may succeed after another attempt."""


class PermanentApiError(RuntimeError):
    """A final API answer; retrying the same request will not help."""


class IdentityRequiredApiError(PermanentApiError):
    """The list API explicitly asks for identity verification."""

    def __init__(self, attempts=1):
        super().__init__("api_requires_identity_verification")
        self.attempts = attempts


def api_requires_identity(response):
    if not isinstance(response, dict) or type(response.get("code")) is not int:
        return False
    if response["code"] not in {400, 401, 403, 500}:
        return False
    message = response.get("msg") or response.get("message")
    if not isinstance(message, str) or any(
        word in message for word in ("服务", "系统", "接口", "超时", "繁忙", "异常", "不可用", "网络", "稍后")
    ):
        return False
    return re.search(
        r"(?:请|需要|须|尚未|未完成|未进行|未通过).{0,12}身份(?:核验|验证|校验)"
        r"|(?:请|需要|须).{0,12}(?:核验|验证|校验)身份"
        r"|身份(?:核验|验证|校验).{0,8}(?:未通过|不通过|未完成)"
        r"|(?:请输入|请填写|请核对).{0,24}(?:手机号|手机号码|证件号码|身份证号码).{0,4}后四位"
        r"|(?:手机号|手机号码|证件号码|身份证号码).{0,4}后四位.{0,8}(?:不匹配|有误|错误|不通过)",
        message,
    ) is not None


def extract_url_params(raw_url: str) -> Dict[str, str]:
    parsed = urllib.parse.urlsplit(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("invalid_delivery_url")
    # ZXFW places the query after the SPA route fragment, so urlparse().query
    # is normally empty. Parse both forms to support aliases and copied URLs.
    candidates = [parsed.query]
    if "?" in parsed.fragment:
        candidates.append(parsed.fragment.split("?", 1)[1])
    values: Dict[str, str] = {}
    for candidate in candidates:
        parsed_values = urllib.parse.parse_qs(candidate, keep_blank_values=True)
        for key in (*REQUIRED_PARAMS, "mm"):
            found = parsed_values.get(key, [])
            if found:
                values[key] = found[-1]
    if not all(values.get(key) for key in REQUIRED_PARAMS):
        missing = [key for key in REQUIRED_PARAMS if not values.get(key)]
        raise ValueError("missing_url_params:" + ",".join(missing))
    return values


def _error_status(error: urllib.error.HTTPError) -> Optional[int]:
    return error.code if error.code in {408, 425, 429} or 500 <= error.code < 600 else None


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    timeout: float,
    extra_headers: Optional[Dict[str, str]] = None,
    opener=None,
) -> Any:
    data = None
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json, text/plain, */*"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if extra_headers:
        headers.update(extra_headers)
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        open_url = opener.open if opener is not None else urllib.request.urlopen
        with open_url(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as error:
        status = _error_status(error)
        if status is not None:
            raise TransientDownloadError(f"http_{status}") from error
        raise PermanentApiError(f"http_{error.code}") from error
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as error:
        raise TransientDownloadError(type(error).__name__) from error
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PermanentApiError("invalid_json") from error


def confirm_receipt(params: Dict[str, str], *, timeout: float, requester=None) -> Dict[str, Any]:
    """Call the state-changing receipt API once, only after explicit opt-in."""
    try:
        response = (requester or request_json)(
            RECEIPT_ENDPOINT, method="POST", payload=params,
            timeout=timeout, extra_headers=API_HEADERS,
        )
    except TransientDownloadError:
        # A lost response can follow a successful write. Do not repeat it.
        return {"status": "unknown", "reason": "receipt_response_unknown"}
    except PermanentApiError:
        return {"status": "unknown", "reason": "receipt_response_unknown"}
    if isinstance(response, dict) and response.get("code") == 200:
        return {"status": "confirmed"}
    if isinstance(response, dict) and isinstance(response.get("code"), int):
        return {"status": "unconfirmed", "reason": "receipt_business_error"}
    return {"status": "unknown", "reason": "receipt_response_unknown"}


def identity_gate(params, *, timeout, requester=None):
    try:
        response = (requester or request_json)(
            IDENTITY_GATE_ENDPOINT, method="POST", payload=params,
            timeout=timeout, extra_headers=API_HEADERS,
        )
    except (PermanentApiError, TransientDownloadError):
        return {"status": "unknown", "reason": "identity_gate_unavailable"}
    if isinstance(response, dict) and response.get("code") == 200:
        flag = response.get("data")
        if flag is True or flag == "true":
            return {"status": "required"}
        if flag is False or flag == "false":
            return {"status": "not_required"}
    return {"status": "unknown", "reason": "identity_gate_unconfirmed"}


def verify_identity(params, *, timeout, config_path=DEFAULT_PATH, lawyer_id=None, method="sjhm",
                    requester=None, recipient_mobile_last4=None):
    if recipient_mobile_last4 is None:
        try:
            selected, last4 = select_identity(config_path, lawyer_id, method)
        except ProfileError as error:
            return {"status": "needs_config", "reason": str(error)}
        metadata = {"lawyer_id": selected, "method": method, "source": "local_profile"}
    else:
        last4 = normalize_mobile_last4(recipient_mobile_last4)
        method = "sjhm"
        metadata = {"method": method, "source": "user_input"}
    try:
        response = (requester or request_json)(
            IDENTITY_CHECK_ENDPOINT, method="POST",
            payload={**params, "jylx": method, "jyz": last4},
            timeout=timeout, extra_headers=API_HEADERS,
        )
    except (PermanentApiError, TransientDownloadError):
        return {"status": "unknown", "reason": "identity_response_unknown", **metadata}
    if isinstance(response, dict) and response.get("code") == 200:
        return {"status": "verified", **metadata}
    code = response.get("code") if isinstance(response, dict) else None
    message = (response.get("msg") or response.get("message")) if isinstance(response, dict) else None
    mismatch = (
        isinstance(message, str)
        and not any(word in message for word in ("服务", "系统", "接口", "超时", "繁忙", "异常", "不可用", "网络"))
        and re.search(
            r"(?:手机号(?:码)?|手机号码|证件(?:号码)?|身份证(?:号码)?|后四位)"
            r"[^，。；\n]{0,24}(?:有误|错误|不符|不匹配|不一致|不正确|未通过|不通过|校验失败|验证失败|核验失败)",
            message,
        ) is not None
    )
    if type(code) is not int or code not in {400, 403, 500} or not mismatch:
        return {"status": "unknown", "reason": "identity_response_unknown", **metadata}
    return {"status": "rejected", "reason": "identity_check_rejected",
            "next_action": "ask_recipient_mobile_last4", **metadata}


def identity_candidates(path=DEFAULT_PATH, lawyer_id=None, method="sjhm"):
    """List the identities a single delivery may legitimately be checked against."""
    profiles = load_profiles(path)["lawyers"]
    if lawyer_id is None:
        # Enumerating configured lawyers would be guessing identities. A single
        # confirmed recipient is the only case that may proceed without an ID.
        recipients = [key for key, value in profiles.items() if value.get("delivery_recipient")]
        if len(recipients) != 1:
            raise ProfileError("lawyer_selection_required")
        lawyer_id = recipients[0]
    if lawyer_id not in profiles:
        raise ProfileError("unknown_lawyer_id")
    profile = profiles[lawyer_id]
    if method == "sjhm" and not (profile.get("mobile") or profile.get("mobile_last4")):
        return []
    if method == "zjhm" and not profile.get("id_last4"):
        return []
    return [{"lawyer_id": lawyer_id, "method": method}]


def verify_identity_candidates(params, *, timeout, config_path=DEFAULT_PATH, lawyer_id=None,
                               method="sjhm", requester=None, max_attempts=2, sleeper=time.sleep,
                               recipient_mobile_last4=None):
    """Submit one credential, then return control to the agent on rejection."""
    if max_attempts < 1:
        return {"status": "rejected", "reason": "identity_attempt_budget_exhausted",
                "next_action": "check_delivery_registration", "attempts": []}
    if recipient_mobile_last4 is not None:
        result = verify_identity(params, timeout=timeout, requester=requester,
                                 recipient_mobile_last4=recipient_mobile_last4)
        result["attempts"] = [{key: result[key] for key in ("source", "method", "status")}]
        return result
    try:
        candidates = identity_candidates(config_path, lawyer_id, method)
    except ProfileError as error:
        return {"status": "needs_config", "reason": str(error)}
    if not candidates:
        return {"status": "needs_config", "reason": f"missing_{method}_credential",
                "next_action": "configure_selected_profile"}
    result = verify_identity(params, timeout=timeout, config_path=config_path,
                             lawyer_id=candidates[0]["lawyer_id"], method=method, requester=requester)
    result["attempts"] = ([] if result["status"] == "needs_config" else
                          [{key: result[key] for key in ("lawyer_id", "method", "status")}])
    return result


def identity_retry_progress(path, fingerprint):
    """Read a failed run's non-secret retry count and bind it to this delivery."""
    try:
        previous = json.loads(Path(path).read_text(encoding="utf-8"))
        identity = previous["identity"]
        used, limit = identity["attempts_used"], identity["attempts_limit"]
        valid = (
            previous["platform"] == "zxfw" and previous["delivery_fingerprint"] == fingerprint
            and previous["status"] in {"identity_blocked", "needs_config"}
            and identity["status"] in {"rejected", "needs_config"}
            and previous["receipt"]["status"] in {"not_requested", "confirmed", "unconfirmed", "unknown"}
            and previous["documents"] == []
            and type(used) is int and type(limit) is int
            and 0 <= used <= limit <= MAX_IDENTITY_ATTEMPTS
            and (used > 0 or identity["status"] == "needs_config")
        )
        canonical = Path(previous["manifest_path"]).resolve()
        valid = valid and canonical.name == "download-manifest.json"
        valid = valid and canonical.parent == Path(previous["output_dir"]).resolve()
        valid = valid and json.loads(canonical.read_text(encoding="utf-8")) == previous
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError("invalid_identity_retry_manifest") from None
    if not valid:
        raise ValueError("invalid_identity_retry_manifest")
    receipt = {"status": previous["receipt"]["status"]}
    if previous["receipt"].get("reason") in {"receipt_response_unknown", "receipt_business_error"}:
        receipt["reason"] = previous["receipt"]["reason"]
    return used, limit, canonical, receipt, identity["status"]


def fetch_documents(
    params: Dict[str, str], *, timeout: float = REQUEST_TIMEOUT, attempts: int = ATTEMPTS,
    sleeper: Callable[[float], None] = time.sleep,
    requester=None,
) -> Tuple[List[Dict[str, Any]], int]:
    last_error: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            response = (requester or request_json)(
                API_ENDPOINT,
                method="POST",
                payload=params,
                timeout=timeout,
                extra_headers=API_HEADERS,
            )
            if api_requires_identity(response):
                raise IdentityRequiredApiError(attempts=attempt)
            if not isinstance(response, dict) or response.get("code") != 200:
                code = response.get("code") if isinstance(response, dict) else None
                safe_code = str(code) if isinstance(code, int) else "unknown"
                raise PermanentApiError(f"api_code_{safe_code}")
            data = response.get("data")
            if not isinstance(data, list):
                raise PermanentApiError("invalid_data_field")
            return data, attempt
        except TransientDownloadError as error:
            last_error = error
            if attempt < attempts:
                sleeper(RETRY_DELAYS[min(attempt - 1, len(RETRY_DELAYS) - 1)])
    raise TransientDownloadError("list_attempts_exhausted") from last_error


def _safe_extension(value: Optional[str], download_url: str) -> str:
    candidate = str(value or "").strip().lstrip(".").lower()
    if re.fullmatch(r"[a-z0-9]{1,10}", candidate or ""):
        return "." + candidate
    path = urllib.parse.unquote(urllib.parse.urlsplit(download_url).path)
    suffix = Path(path).suffix.lower()
    return suffix if re.fullmatch(r"\.[a-z0-9]{1,10}", suffix or "") else ".pdf"


def _safe_title(value: Any) -> str:
    title = unicodedata.normalize("NFC", str(value or "document"))
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(". ")
    return title.encode("utf-8")[:180].decode("utf-8", errors="ignore") or "document"


def validate_file(path: Path, extension: str) -> None:
    """Reject empty/error responses; this is not a full PDF/document parser."""
    if path.stat().st_size == 0:
        raise PermanentApiError("empty_file")
    with path.open("rb") as stream:
        prefix = stream.read(1024)
    clean = (prefix[3:] if prefix.startswith(b"\xef\xbb\xbf") else prefix).lstrip()
    if re.match(br"(?:<!doctype\s+html|<html\b)", clean, re.IGNORECASE):
        raise PermanentApiError("html_instead_of_document")
    if extension == ".pdf":
        valid = b"%PDF-" in prefix
    elif extension in {".docx", ".xlsx", ".pptx", ".ofd", ".zip"}:
        valid = prefix.startswith(b"PK\x03\x04")
    elif extension in {".doc", ".xls", ".ppt"}:
        valid = prefix.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
        valid = valid or (extension == ".doc" and clean.startswith(b"{\\rtf"))
    elif extension in {".jpg", ".jpeg"}:
        valid = prefix.startswith(b"\xff\xd8\xff")
    elif extension == ".png":
        valid = prefix.startswith(b"\x89PNG\r\n\x1a\n")
    elif extension == ".gif":
        valid = prefix.startswith((b"GIF87a", b"GIF89a"))
    elif extension in {".tif", ".tiff"}:
        valid = prefix.startswith((b"II*\x00", b"MM\x00*"))
    elif extension == ".bmp":
        valid = prefix.startswith(b"BM")
    elif extension == ".json":
        raise PermanentApiError("unverified_json_document")
    else:
        raise PermanentApiError("unsupported_file_format")
    if not valid:
        raise PermanentApiError("invalid_document_header")


def download_file(
    url: str,
    destination: Path,
    *,
    timeout: float = DOWNLOAD_TIMEOUT,
    attempts: int = ATTEMPTS,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    if urllib.parse.urlsplit(url).scheme not in {"http", "https"}:
        raise PermanentApiError("invalid_download_scheme")
    last_error: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        temporary_path = None
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=timeout) as response, tempfile.NamedTemporaryFile(
                dir=destination.parent, delete=False
            ) as temporary:
                temporary_path = Path(temporary.name)
                written = 0
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    temporary.write(chunk)
                    written += len(chunk)
                expected = response.headers.get("Content-Length")
                if expected is not None and written != int(expected):
                    raise TransientDownloadError("truncated_response")
            validate_file(temporary_path, destination.suffix.lower())
            temporary_path.replace(destination)
            return
        except urllib.error.HTTPError as error:
            last_error = error
            status = _error_status(error)
            if status is None:
                raise PermanentApiError(f"http_{error.code}") from error
            if attempt < attempts:
                sleeper(RETRY_DELAYS[min(attempt - 1, len(RETRY_DELAYS) - 1)])
        except (urllib.error.URLError, TimeoutError, ConnectionError,
                http.client.HTTPException, TransientDownloadError) as error:
            last_error = error
            if attempt < attempts:
                sleeper(RETRY_DELAYS[min(attempt - 1, len(RETRY_DELAYS) - 1)])
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
    raise TransientDownloadError("file_attempts_exhausted") from last_error


def _unique_destination(output_dir: Path, title: str, extension: str, used: set) -> Path:
    stem = title[:-len(extension)] if title.lower().endswith(extension) else title
    candidate = output_dir / f"{stem}{extension}"
    serial = 2
    while candidate.name.casefold() in {path.name.casefold() for path in used} or candidate.exists():
        candidate = output_dir / f"{stem}_{serial}{extension}"
        serial += 1
    used.add(candidate)
    return candidate


def run(
    raw_url: str,
    output_dir: Path,
    *,
    timeout: float = REQUEST_TIMEOUT,
    download_timeout: float = DOWNLOAD_TIMEOUT,
    attempts: int = ATTEMPTS,
    receipt_authorized: bool = False,
    lawyer_id: Optional[str] = None,
    lawyers_config: Path = DEFAULT_PATH,
    identity_method: str = "sjhm",
    identity_attempts: int = 2,
    identity_only: bool = False,
    recipient_mobile_last4: Optional[str] = None,
    identity_retry_from: Optional[Path] = None,
    fetcher: Optional[Callable] = None,
    downloader: Optional[Callable] = None,
    receipt_sender: Optional[Callable] = None,
    gate_checker: Optional[Callable] = None,
    identity_checker: Optional[Callable] = None,
) -> Dict[str, Any]:
    if not 1 <= attempts <= ATTEMPTS:
        raise ValueError("attempts_must_be_between_1_and_3")
    if not all(math.isfinite(value) and value > 0 for value in (timeout, download_timeout)):
        raise ValueError("timeouts_must_be_positive_and_finite")
    if recipient_mobile_last4 is not None:
        normalize_mobile_last4(recipient_mobile_last4)
        if lawyer_id is not None or identity_method != "sjhm":
            raise ValueError("recipient_input_cannot_select_a_lawyer_or_id_method")
    fetcher = fetcher or fetch_documents
    downloader = downloader or download_file
    receipt_sender = receipt_sender or confirm_receipt
    gate_checker = gate_checker or identity_gate
    identity_checker = identity_checker or verify_identity_candidates
    session = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def requester(*args, **kwargs):
        return request_json(*args, **kwargs, opener=session)

    params = extract_url_params(raw_url)
    fingerprint = hashlib.sha256(json.dumps(params, sort_keys=True).encode("utf-8")).hexdigest()
    used = 0
    limit = min(MAX_IDENTITY_ATTEMPTS, max(1, int(identity_attempts)))
    retry_manifest = None
    previous_receipt = {"status": "not_requested"}
    if identity_retry_from is not None:
        used, previous_limit, retry_manifest, previous_receipt, prior_identity = identity_retry_progress(
            identity_retry_from, fingerprint)
        limit = min(limit, previous_limit)
        if recipient_mobile_last4 is None and not (
            prior_identity == "needs_config" and used == 0 and lawyer_id is not None
        ):
            raise ValueError("retry_requires_recipient_input")
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_dir = Path(tempfile.mkdtemp(prefix="zxfw-", dir=output_dir))
    manifest_path = output_dir / "download-manifest.json"
    manifest: Dict[str, Any] = {
        "platform": "zxfw",
        "delivery_fingerprint": fingerprint,
        "status": "downloading",
        "output_dir": str(output_dir.resolve()),
        "manifest_path": str(manifest_path.resolve()),
        "receipt": previous_receipt,
        "identity": {"status": "not_checked"},
        "documents": [],
    }

    def authenticate(*, api_required):
        nonlocal used
        manifest["identity"] = gate_checker(params, timeout=timeout, requester=requester)
        # The UI flag cannot overrule an explicit denial from the list API.
        if api_required and manifest["identity"]["status"] in {"required", "not_required"}:
            manifest["identity"] = {"status": "required", "reason": "api_requires_identity"}
        if manifest["identity"]["status"] == "required":
            extra_identity = ({} if recipient_mobile_last4 is None else
                              {"recipient_mobile_last4": recipient_mobile_last4})
            manifest["identity"] = identity_checker(
                params, timeout=timeout, config_path=lawyers_config,
                lawyer_id=lawyer_id, method=identity_method, requester=requester,
                max_attempts=limit - used, **extra_identity,
            )
            used += len(manifest["identity"].get("attempts", []))
        manifest["identity"].update({"attempts_used": used, "attempts_limit": limit})
        status = manifest["identity"]["status"]
        if status not in {"not_required", "verified"}:
            if status == "rejected" and used >= limit:
                manifest["identity"]["next_action"] = "check_delivery_registration"
            manifest["status"] = "needs_config" if status == "needs_config" else "identity_blocked"
            return False
        return True

    try:
        if used >= limit:
            manifest["identity"] = {
                "status": "rejected", "reason": "identity_attempt_budget_exhausted",
                "next_action": "check_delivery_registration",
                "attempts_used": used, "attempts_limit": limit, "attempts": [],
            }
            manifest["status"] = "identity_blocked"
            return manifest
        if identity_retry_from is not None:
            # Consume this continuation once, including an uncertain network result.
            marker = Path(str(retry_manifest) + ".retry-used")
            try:
                with marker.open("x", encoding="utf-8") as stream:
                    os.chmod(marker, 0o600)
                    stream.write("identity retry started\n")
            except FileExistsError:
                manifest["identity"] = {"status": "unknown", "reason": "identity_retry_already_used"}
                manifest["status"] = "identity_blocked"
                return manifest
        documents = None
        attempts_used = 0
        if identity_only or identity_retry_from is not None:
            # A rejected identity must be corrected before any further list read.
            if not authenticate(api_required=identity_retry_from is not None):
                return manifest
            if identity_only:
                if manifest["receipt"]["status"] == "not_requested":
                    manifest["receipt"]["reason"] = "identity_only_mode"
                manifest["status"] = "identity_checked"
                return manifest
        else:
            try:
                documents, attempts_used = fetcher(
                    params, timeout=timeout, attempts=attempts, requester=requester)
                manifest["direct_api"] = {"status": "accessible", "attempts": attempts_used}
                manifest["identity"] = {
                    "status": "not_requested", "reason": "direct_api_accessible",
                    "attempts_used": used, "attempts_limit": limit,
                }
            except IdentityRequiredApiError as error:
                manifest["direct_api"] = {"status": "identity_required", "attempts": error.attempts}
                if not authenticate(api_required=True):
                    return manifest

        receipt_sent = False
        if receipt_authorized and manifest["receipt"]["status"] == "not_requested":
            manifest["receipt"] = receipt_sender(params, timeout=timeout, requester=requester)
            receipt_sent = True
        if documents is None or receipt_sent:
            # After a read-only probe, preserve receipt -> fresh list -> download.
            try:
                documents, attempts_used = fetcher(
                    params, timeout=timeout, attempts=attempts, requester=requester)
            except IdentityRequiredApiError:
                if manifest["identity"]["status"] == "verified":
                    raise PermanentApiError("identity_not_accepted_by_list") from None
                if not authenticate(api_required=True):
                    return manifest
                documents, attempts_used = fetcher(
                    params, timeout=timeout, attempts=attempts, requester=requester)
        manifest["api_attempts"] = attempts_used
        used_paths: set = {manifest_path}
        failures = []
        for index, item in enumerate(documents, start=1):
            if not isinstance(item, dict) or not item.get("wjlj") or not item.get("c_wsmc"):
                failures.append({"index": index, "reason": "missing_name_or_download_url"})
                continue
            title = _safe_title(item.get("c_wsmc"))
            extension = _safe_extension(item.get("c_wjgs"), str(item["wjlj"]))
            destination = _unique_destination(output_dir, title, extension, used_paths)
            try:
                downloader(str(item["wjlj"]), destination, timeout=download_timeout, attempts=attempts)
                validate_file(destination, extension)
            except Exception as error:
                reason = str(error) if isinstance(error, (PermanentApiError, TransientDownloadError)) else type(error).__name__
                failures.append({"index": index, "name": title, "reason": reason})
                continue
            manifest["documents"].append({
                "name": title,
                "file": str(destination.resolve()),
                "court_name": item.get("c_fymc"),
                "document_id": item.get("c_wsbh"),
                "format": item.get("c_wjgs"),
            })
        manifest["status"] = (
            "empty" if not documents else "downloaded" if not failures
            else "partial" if manifest["documents"] else "error"
        )
        manifest["document_count"] = len(documents)
        manifest["failures"] = failures
        return manifest
    except Exception as error:
        manifest["status"] = "error"
        manifest["reason"] = (
            str(error) if isinstance(error, (PermanentApiError, TransientDownloadError))
            else type(error).__name__
        )
        return manifest
    finally:
        with manifest_path.open("x", encoding="utf-8") as stream:
            os.chmod(manifest_path, 0o600)
            stream.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="ZXFW delivery URL from the SMS")
    parser.add_argument("--output", required=True, type=Path, help="staging base; each run creates a private subdirectory")
    parser.add_argument("--timeout", type=float, default=REQUEST_TIMEOUT, help="list/receipt network timeout in seconds")
    parser.add_argument("--download-timeout", type=float, default=DOWNLOAD_TIMEOUT, help="file network timeout in seconds")
    parser.add_argument("--attempts", type=int, default=ATTEMPTS, help="list/file attempts, 1-3; receipt is sent once")
    parser.add_argument("--confirm-receipt", action="store_true", help="explicitly authorize writing a court receipt before listing")
    identity_source = parser.add_mutually_exclusive_group()
    identity_source.add_argument("--lawyer-id", help="selected local lawyer/recipient profile")
    identity_source.add_argument("--identity-stdin", action="store_true",
                                 help="read a one-time recipient mobile_last4 JSON from stdin; never save it")
    parser.add_argument("--lawyers-config", type=Path, default=DEFAULT_PATH, help="private lawyer configuration")
    parser.add_argument("--identity-method", choices=("sjhm", "zjhm"), default="sjhm", help="phone or document-number last four")
    parser.add_argument("--identity-attempts", type=int, default=2, help="identity attempts per delivery, 1-2")
    parser.add_argument("--identity-only", action="store_true",
                        help="verify identity only; never send receipt or fetch the document list")
    parser.add_argument("--retry-identity-from", type=Path,
                        help="rejected/needs-config manifest from this delivery; preserve budget and receipt")
    args = parser.parse_args()
    try:
        recipient_tail = None
        if args.identity_stdin:
            try:
                value = json.load(sys.stdin)
            except (ValueError, UnicodeError):
                raise ValueError("invalid_recipient_mobile_last4_input") from None
            if not isinstance(value, dict) or set(value) != {"mobile_last4"}:
                raise ValueError("invalid_recipient_mobile_last4_input")
            recipient_tail = normalize_mobile_last4(value["mobile_last4"])
        manifest = run(
            args.url, args.output, timeout=args.timeout, download_timeout=args.download_timeout,
            attempts=args.attempts, receipt_authorized=args.confirm_receipt,
            lawyer_id=args.lawyer_id, lawyers_config=args.lawyers_config, identity_method=args.identity_method,
            identity_attempts=args.identity_attempts,
            identity_only=args.identity_only,
            recipient_mobile_last4=recipient_tail, identity_retry_from=args.retry_identity_from,
        )
    except (ValueError, OSError) as error:
        print(json.dumps({"status": "error", "reason": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if manifest.get("status") in {"downloaded", "identity_checked"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
