#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chat-html 抽取器：识别 Cubox/微信等聊天工具导出 HTML，抽取三类外链资源。

引入版本：v0.12.0；v0.13.0 加固 URL、重定向、大小与覆盖边界。
与 references/chat-html-extract.md 配合使用。
"""

from __future__ import annotations

import base64
import binascii
import http.client
import ipaddress
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# frozenset 防止运行时误改；不出现在 __all__ 中。
DOWNLOAD_DOMAIN_WHITELIST = frozenset({
    "cubox.pro",
    "files.cubox.pro",
    "images.cubox.pro",
    "weixin.qq.com",
    "szfiles.wx.qq.com",
    "wenshu.court.gov.cn",
    "aliyundrive.com",
    "weiyun.com",
    "pan.baidu.com",
})

VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".m4v", ".mkv", ".webm"})

CHAT_HTML_HINTS = (
    'class="reader-page"',
    "chatlog",
    "群聊的聊天记录",
    "微信聊天记录",
)

# inner 限制为非 `<>` 字符，避免 regex 越过嵌套标签切错。
_TAG_A_HREF = re.compile(
    r'<a\b[^>]*\bhref=["\']([^"\']+)["\'][^>]*>([^<>]*?)</a>',
    re.DOTALL | re.IGNORECASE,
)
_TAG_IMG_SRC = re.compile(r'<img\b[^>]*\bsrc=["\']([^"\']+)["\']', re.IGNORECASE)
_TAG_VIDEO_SRC = re.compile(r'<video\b[^>]*\bsrc=["\']([^"\']+)["\']', re.IGNORECASE)
_TAG_SOURCE_SRC = re.compile(r'<source\b[^>]*\bsrc=["\']([^"\']+)["\']', re.IGNORECASE)
_DOWNLOAD_TEXT_HINT = ("下载文件", "下载")
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
MAX_REDIRECTS = 5
ALLOWED_DATA_IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"})
DATA_IMAGE_MAGIC = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/webp": (b"RIFF",),
    "image/bmp": (b"BM",),
}


class HostResolutionError(ValueError):
    """DNS 解析暂时失败，可重试。"""


class UnsafeHostError(ValueError):
    """主机解析到非公网地址或形式非法，永久拒绝。"""


class PermanentDownloadError(ValueError):
    """URL 形式非法或响应超限等永久失败，不重试。"""


@dataclass
class DownloadResult:
    """单条资源下载结果。status: 'ok' | 'failed' | 'access_denied'."""

    url: str
    status: str
    path: Optional[Path] = None
    error: str = ""
    attempts: int = 0
    bytes: int = 0


@dataclass
class ResourceCandidate:
    """单条外链资源候选。

    Note: `download_status` 等下载运行期字段由调用方（scanner / downloader）通过 extra 注入，
    不在抽取层产生。
    """
    resource_id: str
    kind: str
    url: str
    display_filename: str
    sender_context: str = ""
    extra: dict = field(default_factory=dict)

    def to_manifest_extra(self) -> dict:
        """转换为 manifest extra dict。

        Note: `download_status` 等下载运行期字段由调用方（scanner / downloader）通过 extra 注入，
        不在抽取层产生。
        """
        return {
            "resource_id": self.resource_id,
            "kind": self.kind,
            "url": self.url,
            "display_filename": self.display_filename,
            "context": self.sender_context,
            **self.extra,
        }


def recognize_chat_html(html_text: str) -> bool:
    if not html_text:
        return False
    return any(hint in html_text for hint in CHAT_HTML_HINTS)


def _is_public_http_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return False
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _is_public_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if address.version == 6:
        if address.is_site_local:
            return False
        if address.sixtofour is not None and not _is_public_ip(address.sixtofour):
            return False
        if address.teredo is not None:
            _, server = address.teredo
            if not _is_public_ip(server):
                return False
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _resolve_public_addresses(host: str) -> list[str]:
    """解析主机名并只保留公网地址；解析失败或含非公网地址时拒绝。

    目的：避免白名单域名经 DNS 指向私网/回环地址造成 SSRF 绕过。
    """
    normalized = host.rstrip(".").lower()
    try:
        literal = ipaddress.ip_address(normalized)
    except ValueError:
        literal = None
    if literal is not None:
        if not _is_public_ip(literal):
            raise UnsafeHostError(f"host resolves to non-public address: {normalized}")
        return [str(literal)]
    infos: list = []
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            infos.extend(
                socket.getaddrinfo(normalized, None, family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
            )
        except socket.gaierror as exc:
            if family == socket.AF_INET:
                raise HostResolutionError(f"host cannot be resolved: {normalized}") from exc
            continue
    addresses: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        try:
            address = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if not _is_public_ip(address):
            raise UnsafeHostError(f"host resolves to non-public address: {normalized}")
        addresses.append(str(address))
    if not addresses:
        raise HostResolutionError(f"host has no usable address: {normalized}")
    return sorted(set(addresses))


def _assert_resolved_public_host(url: str) -> str:
    """校验 URL 主机可解析且全部解析结果为公网地址，返回规范化主机名。"""
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeHostError("URL has no host")
    _resolve_public_addresses(host)
    return host


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS 连接：socket 连接到已校验 IP，TLS SNI 与 Host 仍使用原始主机名。"""

    def __init__(self, host: str, *, pinned_ip: str, port: int, timeout: int) -> None:
        super().__init__(host, port=port, timeout=timeout)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:  # type: ignore[override]
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        if self._tunnel_host:
            self._tunnel()
        server_hostname = self.host.rstrip(".").lower()
        self.sock = self._context.wrap_socket(
            self.sock,
            server_hostname=server_hostname,
        )


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTP 连接：socket 连接到已校验 IP，Host 头仍使用原始主机名。"""

    def __init__(self, host: str, *, pinned_ip: str, port: int, timeout: int) -> None:
        super().__init__(host, port=port, timeout=timeout)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:  # type: ignore[override]
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        if self._tunnel_host:
            self._tunnel()


def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def _is_download_url(url: str) -> bool:
    if not _is_public_http_url(url):
        return False
    host = (urllib.parse.urlsplit(url).hostname or "").rstrip(".").lower()
    return any(_host_matches(host, domain) for domain in DOWNLOAD_DOMAIN_WHITELIST)


def _is_image_url(url: str) -> bool:
    lower = url.lower()
    if lower.startswith("data:image/"):
        return True
    if not _is_public_http_url(url):
        return False
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").rstrip(".").lower()
    if _host_matches(host, "images.cubox.pro") or _host_matches(host, "images.weserv.nl"):
        return True
    return _host_matches(host, "cubox.pro") and "/images/" in parsed.path.lower()


def _is_video_url(url: str) -> bool:
    lower = url.lower()
    if not _is_public_http_url(url):
        return False
    path = urllib.parse.urlsplit(url).path.lower()
    return any(path.endswith(ext) for ext in VIDEO_EXTENSIONS)


def _display_filename_from_url(url: str) -> str:
    if url.lower().startswith("data:image/"):
        media_type = url[5:].split(";", 1)[0].split(",", 1)[0]
        extension = media_type.split("/", 1)[-1] or "bin"
        return f"inline-image.{extension}"
    name = urllib.parse.unquote(urllib.parse.urlsplit(url).path.rstrip("/").split("/")[-1])
    return name or url


def _new_id() -> str:
    return "R" + uuid.uuid4().hex[:8]


_FILENAME_RE = re.compile(
    r"\.(pdf|docx?|xlsx?|pptx?|zip|rar|7z|jpg|jpeg|png|gif|mp4|mov|m4v|webm|mkv|csv)\b",
    re.IGNORECASE,
)
# 微信/Cubox 聊天中常见的时间戳形态：M-D HH:MM、YYYY-MM-DD HH:MM 等
_TIMESTAMP_RE = re.compile(
    r"^\s*(\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}|\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}|\d{1,2}:\d{2})\s*$"
)
# 含较多汉字则大概率是消息正文（不像文件名）
_CHINESE_CHAR_RE = re.compile(r"[一-鿿]")


def _is_skip_context(text: str) -> bool:
    """判断是否为"应跳过的上下文片段"——文件名、时间戳或纯数字编号。"""
    if not text:
        return True
    if _FILENAME_RE.search(text):
        return True
    if _TIMESTAMP_RE.match(text):
        return True
    if not _CHINESE_CHAR_RE.search(text):
        # 无汉字且仅由字母/数字/下划线/连字符/空格/点/括号组成 → 视作文件名或编号
        if re.fullmatch(r"[A-Za-z0-9_\-.\s()（）]+", text):
            return True
        # 纯数字编号（如 1783761818764）
        if re.fullmatch(r"\d+", text):
            return True
    return False


def _extract_sibling_text(html_text: str, end_pos: int, window: int = 800) -> str:
    """从 end_pos（通常 = `<a>` 标签结束位置）向前看 window 字符，截取最近的 tag-pair 内文字。

    策略：从 end_pos 向前回溯，先定位本锚点 `<a` 的起点。如果紧邻的 tag-pair 内
    是文件名（如 `<span>xxx.pdf</span>`），跳过它继续向上找，再上一个 tag-pair 内的
    文字通常是同发送者的"前一条消息"或上下文注释。
    """
    head = html_text[max(0, end_pos - window):end_pos]
    a_open = head.rfind("<a")
    if a_open == -1:
        # 非锚点路径（img / video / source）：窗口为最近 `</` 之前的 `>` 到 end_pos
        last_close = head.rfind("</")
        if last_close == -1:
            return ""
        open_gt = head.rfind(">", 0, last_close)
        if open_gt == -1:
            return ""
        window_segment = head[open_gt:]
    else:
        # 锚点 `<a>` 路径：循环向前找最近的"非文件名" tag-pair 文本
        cursor = a_open
        last_text = ""
        while cursor > 0:
            prev_close = head.rfind("</", 0, cursor)
            if prev_close == -1:
                break
            prev_gt = head.rfind(">", 0, prev_close)
            if prev_gt == -1:
                break
            window_segment = head[prev_gt: cursor]
            pieces = re.findall(r'>([^<>]{4,80})<', window_segment)
            if pieces:
                candidate = pieces[-1].strip()
                if candidate and not _is_skip_context(candidate):
                    return candidate
                # 是文件名/时间戳/编号，先记住；如果以后再也找不到更合适的文本，至少能用
                if not last_text:
                    last_text = candidate
                cursor = prev_gt
            else:
                cursor = prev_gt
        return last_text
    pieces = re.findall(r'>([^<>]{4,80})<', window_segment)
    return pieces[-1].strip() if pieces else ""


def extract_external_resources(html_text: str) -> list[ResourceCandidate]:
    candidates: list[ResourceCandidate] = []
    seen: set[tuple[str, str]] = set()

    def _add(kind: str, url: str, pos: int) -> None:
        key = (kind, url)
        if key in seen:
            return
        seen.add(key)
        candidates.append(
            ResourceCandidate(
                resource_id=_new_id(),
                kind=kind,
                url=url,
                display_filename=_display_filename_from_url(url),
                sender_context=_extract_sibling_text(html_text, pos),
            )
        )

    for match in _TAG_A_HREF.finditer(html_text):
        url, inner = match.group(1), match.group(2)
        if any(h in inner for h in _DOWNLOAD_TEXT_HINT) and _is_download_url(url):
            _add("download", url, match.end())

    for match in _TAG_IMG_SRC.finditer(html_text):
        url = match.group(1)
        if _is_image_url(url):
            _add("image", url, match.end())

    for match in _TAG_VIDEO_SRC.finditer(html_text):
        url = match.group(1)
        if _is_video_url(url):
            _add("video", url, match.end())

    for match in _TAG_SOURCE_SRC.finditer(html_text):
        url = match.group(1)
        if _is_video_url(url):
            _add("video", url, match.end())

    return candidates


def _safe_filename(name: str) -> str:
    """把一个原始文件名清洗成合法的本地文件名。

    - 替换 /\\:?"<>| 等非法字符为 _
    - 空名用 'untitled'
    - 截断到 120 字符
    """
    name = (name or "").strip() or "untitled"
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", name)
    cleaned = cleaned.lstrip(".") or "untitled"
    return cleaned[:120]


def _available_target(dest_dir: Path, filename: str) -> Path:
    target = dest_dir / filename
    if not target.exists():
        return target
    stem = target.stem or "untitled"
    suffix = target.suffix
    index = 2
    while True:
        candidate = dest_dir / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """保留兼容入口：重定向复核由固定连接循环执行。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        if not _is_public_http_url(newurl):
            raise urllib.error.HTTPError(newurl, 403, "redirect target rejected", headers, fp)
        try:
            _resolve_public_addresses((urllib.parse.urlsplit(newurl).hostname or "").rstrip(".").lower())
        except UnsafeHostError as exc:
            raise urllib.error.HTTPError(newurl, 403, str(exc), headers, fp) from exc
        except HostResolutionError as exc:
            raise urllib.error.HTTPError(newurl, 503, str(exc), headers, fp) from exc
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _prepare_request_target(url: str) -> tuple[str, list[str], str, int, str]:
    """解析请求目标并完成 DNS 公网校验，返回主机、已校验地址、协议、端口与请求路径。"""
    parsed = urllib.parse.urlsplit(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise UnsafeHostError("only public HTTP/HTTPS URLs are allowed")
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeHostError("URL has no host")
    addresses = _resolve_public_addresses(host)
    port = parsed.port or (443 if scheme == "https" else 80)
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"
    return host, addresses, scheme, port, target


def _request_headers(host: str) -> dict[str, str]:
    return {
        "User-Agent": "legal-material-organizer/0.16.1",
        "Host": host,
        "Accept": "*/*",
        "Connection": "close",
    }


def _open_pinned_connection(
    host: str, addresses: list[str], scheme: str, port: int, timeout: int
) -> http.client.HTTPConnection:
    """按已校验地址顺序建立连接；每个候选地址在连接前再次校验为公网。"""
    last_error: Exception | None = None
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as exc:
            raise HostResolutionError(f"invalid resolved address: {address}") from exc
        if not _is_public_ip(parsed):
            raise UnsafeHostError(f"host resolves to non-public address: {host}")
        if scheme == "https":
            return _PinnedHTTPSConnection(host, pinned_ip=address, port=port, timeout=timeout)
        return _PinnedHTTPConnection(host, pinned_ip=address, port=port, timeout=timeout)
    raise HostResolutionError(f"host has no usable address: {host}")


def _request_url(url: str, timeout: int = 30, max_bytes: int = MAX_DOWNLOAD_BYTES) -> bytes:
    """读取受支持资源，拒绝本地 URL、私网地址和超限响应。

    连接目标固定为已校验的公网 IP，避免 DNS 二次解析把请求改写到内网；
    TLS SNI 与 Host 头仍使用原始主机名。
    """
    if url.lower().startswith("data:image/"):
        try:
            header, payload = url.split(",", 1)
            media_type = header[5:].split(";", 1)[0].strip().lower()
            if media_type not in ALLOWED_DATA_IMAGE_TYPES:
                raise PermanentDownloadError(f"unsupported inline image type: {media_type}")
            content = (
                base64.b64decode(payload, validate=True)
                if ";base64" in header.lower()
                else urllib.parse.unquote_to_bytes(payload)
            )
        except PermanentDownloadError:
            raise
        except (ValueError, binascii.Error) as exc:
            raise PermanentDownloadError("invalid data image") from exc
        if len(content) > max_bytes:
            raise PermanentDownloadError(f"resource exceeds {max_bytes} bytes")
        if not content.startswith(DATA_IMAGE_MAGIC[media_type]):
            raise PermanentDownloadError(f"inline image content does not match {media_type}")
        return content
    if not _is_public_http_url(url):
        raise UnsafeHostError("only public HTTP/HTTPS URLs or data:image are allowed")
    current_url = url
    for _ in range(MAX_REDIRECTS + 1):
        host, addresses, scheme, port, target = _prepare_request_target(current_url)
        connection = _open_pinned_connection(host, addresses, scheme, port, timeout)
        try:
            connection.request("GET", target, headers=_request_headers(host))
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise PermanentDownloadError("redirect without location")
                current_url = urllib.parse.urljoin(current_url, location)
                if not _is_public_http_url(current_url):
                    raise UnsafeHostError("redirect target rejected")
                continue
            if response.status >= 400:
                raise urllib.error.HTTPError(current_url, response.status, "http error", response.headers, None)
            declared_size = response.getheader("Content-Length")
            if declared_size:
                try:
                    if int(declared_size) > max_bytes:
                        raise PermanentDownloadError(f"resource exceeds {max_bytes} bytes")
                except ValueError as exc:
                    if "exceeds" in str(exc):
                        raise
            content = response.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise PermanentDownloadError(f"resource exceeds {max_bytes} bytes")
            return content
        finally:
            connection.close()
    raise PermanentDownloadError("too many redirects")


def download_resource(
    url: str,
    dest_dir: Path,
    display_filename: str,
    max_retries: int = 3,
    timeout: int = 30,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> DownloadResult:
    """下载一个外链资源到 dest_dir/display_filename，失败不抛异常。

    参数:
        url: 公网 HTTP/HTTPS URL 或 data:image URL。
        dest_dir: 目标目录，必须存在或可创建。
        display_filename: 文件展示名。
        max_retries: 最大尝试次数，至少执行一次。
        timeout: 单次请求超时秒数。
        max_bytes: 单个资源大小上限。

    返回:
        DownloadResult。status ∈ {ok, failed, access_denied}。
    """
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return DownloadResult(
            url=url,
            status="failed",
            error=f"mkdir failed: {exc}",
            attempts=0,
        )

    target = _available_target(dest_dir, _safe_filename(display_filename))
    last_err = ""
    max_attempts = max(1, int(max_retries))
    for attempt in range(1, max_attempts + 1):
        try:
            content = _request_url(url, timeout=timeout, max_bytes=max_bytes)
            if not content:
                return DownloadResult(
                    url=url,
                    status="access_denied",
                    error="empty body",
                    attempts=attempt,
                )
            target.write_bytes(content)
            return DownloadResult(
                url=url,
                status="ok",
                path=target,
                attempts=attempt,
                bytes=len(content),
            )
        except urllib.error.HTTPError as exc:
            last_err = f"HTTP {exc.code}"
            if exc.code in (401, 403):
                return DownloadResult(
                    url=url,
                    status="access_denied",
                    error=last_err,
                    attempts=attempt,
                )
        except (UnsafeHostError, PermanentDownloadError) as exc:
            return DownloadResult(
                url=url,
                status="access_denied",
                error=str(exc),
                attempts=attempt,
            )
        except HostResolutionError as exc:
            last_err = f"{type(exc).__name__}: {exc}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_err = f"{type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001 — 防御性兜底，不让 bad input kill pipeline
            last_err = f"{type(exc).__name__}: {exc}"
        if attempt < max_attempts:
            time.sleep(min(2 * attempt, 6))

    return DownloadResult(
        url=url,
        status="failed",
        error=last_err,
        attempts=max_attempts,
    )


__all__ = [
    "recognize_chat_html",
    "extract_external_resources",
    "ResourceCandidate",
    "download_resource",
    "DownloadResult",
]
