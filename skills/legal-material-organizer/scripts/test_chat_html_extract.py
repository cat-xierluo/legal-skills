#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for chat_html_extract.py"""

from __future__ import annotations

import base64
import socket
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import chat_html_extract
from chat_html_extract import (
    recognize_chat_html,
    extract_external_resources,
    ResourceCandidate,
    download_resource,
    DownloadResult,
)


class RecognizeChatHtmlTest(unittest.TestCase):
    def test_cubox_html_is_recognized(self) -> None:
        html = '<html><body><div class="reader-page">群聊的聊天记录</div></body></html>'
        self.assertTrue(recognize_chat_html(html))

    def test_plain_html_is_not_recognized(self) -> None:
        html = "<html><body><h1>Hello</h1></body></html>"
        self.assertFalse(recognize_chat_html(html))

    def test_empty_string_is_not_recognized(self) -> None:
        self.assertFalse(recognize_chat_html(""))

    def test_chatlog_keyword_recognized(self) -> None:
        html = "<html><body>chatlog 12345</body></html>"
        self.assertTrue(recognize_chat_html(html))


class DnsBindingTest(unittest.TestCase):
    """DNS 解析结果必须为公网地址，并真正作为连接目标。"""

    def test_private_dns_answer_is_rejected(self) -> None:
        with patch(
            "chat_html_extract.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))],
        ):
            with self.assertRaises(chat_html_extract.UnsafeHostError):
                chat_html_extract._assert_resolved_public_host("https://files.cubox.pro/a.pdf")

    def test_unresolvable_host_is_rejected(self) -> None:
        with patch("chat_html_extract.socket.getaddrinfo", side_effect=socket.gaierror("no dns")):
            with self.assertRaises(chat_html_extract.HostResolutionError):
                chat_html_extract._assert_resolved_public_host("https://files.cubox.pro/a.pdf")

    def test_public_dns_answer_is_accepted(self) -> None:
        with patch(
            "chat_html_extract.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
        ):
            host = chat_html_extract._assert_resolved_public_host("https://files.cubox.pro/a.pdf")
        self.assertEqual(host, "files.cubox.pro")

    def test_ipv6_unique_local_address_is_rejected(self) -> None:
        with patch(
            "chat_html_extract.socket.getaddrinfo",
            return_value=[(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fd00::1", 0, 0, 0))],
        ):
            with self.assertRaises(chat_html_extract.UnsafeHostError):
                chat_html_extract._assert_resolved_public_host("https://files.cubox.pro/a.pdf")

    def test_ipv6_link_local_address_is_rejected(self) -> None:
        with patch(
            "chat_html_extract.socket.getaddrinfo",
            return_value=[(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fe80::1", 0, 0, 0))],
        ):
            with self.assertRaises(chat_html_extract.UnsafeHostError):
                chat_html_extract._assert_resolved_public_host("https://files.cubox.pro/a.pdf")

    def test_request_rejects_host_resolving_to_private_address(self) -> None:
        with patch(
            "chat_html_extract.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0))],
        ):
            with self.assertRaises(chat_html_extract.UnsafeHostError):
                chat_html_extract._request_url("https://files.cubox.pro/a.pdf")

    def test_connection_target_is_pinned_to_validated_ip(self) -> None:
        """连接必须使用已校验 IP，TLS SNI 与 Host 保留原主机名。"""
        captured = {}

        class _FakeConnection:
            def __init__(self, host: str, *, pinned_ip: str, port: int, timeout: int) -> None:
                captured["host"] = host
                captured["pinned_ip"] = pinned_ip
                captured["port"] = port

            def request(self, method: str, target: str, headers=None):  # type: ignore[no-untyped-def]
                captured["method"] = method
                captured["target"] = target
                captured["headers"] = headers or {}

            def getresponse(self):  # type: ignore[no-untyped-def]
                raise AssertionError("no response expected")

            def close(self) -> None:
                captured["closed"] = True

        with patch(
            "chat_html_extract.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
        ):
            with patch("chat_html_extract._PinnedHTTPSConnection", _FakeConnection):
                with self.assertRaises(AssertionError):
                    chat_html_extract._request_url("https://files.cubox.pro/a.pdf")
        self.assertEqual(captured["host"], "files.cubox.pro")
        self.assertEqual(captured["pinned_ip"], "93.184.216.34")
        self.assertEqual(captured["port"], 443)
        self.assertEqual(captured["headers"]["Host"], "files.cubox.pro")
        self.assertTrue(captured["closed"])

    def test_connection_does_not_resolve_dns_again(self) -> None:
        """DNS rebinding 防护：连接只使用首次校验的地址，请求期不再解析 DNS。"""
        calls = {"n": 0}

        def fake_getaddrinfo(host, port, family, *args, **kwargs):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            if family == socket.AF_INET:
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
            return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700::1111", 0, 0, 0))]

        with patch("chat_html_extract.socket.getaddrinfo", side_effect=fake_getaddrinfo):
            host, addresses, _scheme, _port, _target = chat_html_extract._prepare_request_target(
                "https://files.cubox.pro/a.pdf"
            )
        self.assertEqual(host, "files.cubox.pro")
        self.assertEqual(addresses, ["2606:4700::1111", "93.184.216.34"])
        resolution_calls = calls["n"]

        with patch("chat_html_extract.socket.getaddrinfo", side_effect=fake_getaddrinfo):
            connection = chat_html_extract._open_pinned_connection(
                host, addresses, "https", 443, 5
            )
        self.assertEqual(calls["n"], resolution_calls)
        self.assertEqual(connection._pinned_ip, addresses[0])
        self.assertEqual(connection.host, "files.cubox.pro")
        connection.close()

    def test_mixed_public_and_private_answers_are_rejected(self) -> None:
        """任一解析结果指向私网即整体拒绝，不做部分放行。"""
        def fake_getaddrinfo(*args, **kwargs):  # type: ignore[no-untyped-def]
            family = args[0] if args else kwargs.get("family")
            if family == socket.AF_INET:
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
            return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fd00::1", 0, 0, 0))]

        with patch("chat_html_extract.socket.getaddrinfo", side_effect=fake_getaddrinfo):
            with self.assertRaises(chat_html_extract.UnsafeHostError):
                chat_html_extract._prepare_request_target("https://files.cubox.pro/a.pdf")

    def test_redirect_to_private_host_is_rejected(self) -> None:
        handler = chat_html_extract._SafeRedirectHandler()
        with patch(
            "chat_html_extract.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.10", 0))],
        ):
            with self.assertRaises(urllib.error.HTTPError):
                handler.redirect_request(
                    urllib.request.Request("https://files.cubox.pro/a.pdf"),
                    None,
                    302,
                    "Found",
                    {},
                    "http://files.cubox.pro/redirect.pdf",
                )


class DownloadErrorClassificationTest(unittest.TestCase):
    """永久失败与可重试失败必须区分，避免无效重试或误放行。"""

    def test_dns_failure_is_retried(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "chat_html_extract.socket.getaddrinfo",
                side_effect=socket.gaierror("dns unavailable"),
            ):
                result = download_resource(
                    url="https://files.cubox.pro/missing.pdf",
                    dest_dir=Path(tmp) / "out",
                    display_filename="missing.pdf",
                    max_retries=3,
                    timeout=2,
                )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.attempts, 3)

    def test_private_address_is_rejected_without_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "chat_html_extract.socket.getaddrinfo",
                return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0))],
            ):
                result = download_resource(
                    url="https://files.cubox.pro/missing.pdf",
                    dest_dir=Path(tmp) / "out",
                    display_filename="missing.pdf",
                    max_retries=3,
                    timeout=2,
                )
        self.assertEqual(result.status, "access_denied")
        self.assertEqual(result.attempts, 1)

    def test_oversized_response_is_rejected_without_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "chat_html_extract._request_url",
                side_effect=chat_html_extract.PermanentDownloadError("resource exceeds 10 bytes"),
            ):
                result = download_resource(
                    url="https://files.cubox.pro/big.pdf",
                    dest_dir=Path(tmp) / "out",
                    display_filename="big.pdf",
                    max_retries=3,
                    timeout=2,
                )
        self.assertEqual(result.status, "access_denied")
        self.assertEqual(result.attempts, 1)


class InlineImageTest(unittest.TestCase):
    """data:image 只允许明确类型，并校验内容签名。"""

    def test_unsupported_inline_type_is_rejected(self) -> None:
        with self.assertRaises(chat_html_extract.PermanentDownloadError):
            chat_html_extract._request_url("data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=")

    def test_inline_content_signature_mismatch_is_rejected(self) -> None:
        payload = base64.b64encode(b"not-a-png").decode()
        with self.assertRaises(chat_html_extract.PermanentDownloadError):
            chat_html_extract._request_url(f"data:image/png;base64,{payload}")

    def test_valid_inline_png_is_accepted(self) -> None:
        payload = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 16).decode()
        content = chat_html_extract._request_url(f"data:image/png;base64,{payload}")
        self.assertTrue(content.startswith(b"\x89PNG"))


class ExtractResourcesTest(unittest.TestCase):
    def test_extract_returns_three_categories(self) -> None:
        html = (
            '<html><body>'
            '下载 <a href="https://files.cubox.pro/123/foo.pdf">下载文件</a>'
            '<img src="https://images.cubox.pro/abc/x.jpg" />'
            '<video src="https://example.com/clip.mp4"></video>'
            '</body></html>'
        )
        result = extract_external_resources(html)
        kinds = {c.kind for c in result}
        self.assertIn("download", kinds)
        self.assertIn("image", kinds)
        self.assertIn("video", kinds)

    def test_extract_assigns_unique_ids(self) -> None:
        html = (
            '<a href="https://files.cubox.pro/123/a.pdf">下载</a>'
            '<a href="https://files.cubox.pro/123/b.pdf">下载</a>'
        )
        result = extract_external_resources(html)
        ids = [c.resource_id for c in result]
        self.assertEqual(len(ids), len(set(ids)))

    def test_extract_skips_non_whitelist_download_url(self) -> None:
        html = '<a href="https://randomdomain.example/foo.pdf">下载</a>'
        result = extract_external_resources(html)
        self.assertEqual(len(result), 0)

    def test_extract_rejects_domain_substring_spoofing(self) -> None:
        html = '<a href="https://files.cubox.pro.evil.example/foo.pdf">下载</a>'
        self.assertEqual(extract_external_resources(html), [])

    def test_extract_captures_sender_context(self) -> None:
        html = (
            '<html><body>'
            '<div>7-11 15:18</div><div>这是我们在卖的产品</div>'
            '<div>7-11 15:19</div>'
            '<a href="https://files.cubox.pro/123/foo.pdf">下载文件</a>'
            '</body></html>'
        )
        result = extract_external_resources(html)
        self.assertTrue(result)
        first = result[0]
        self.assertTrue(first.sender_context)

    def test_extract_handles_no_video(self) -> None:
        html = (
            '<a href="https://files.cubox.pro/123/foo.pdf">下载</a>'
            '<img src="https://images.cubox.pro/x.jpg" />'
        )
        result = extract_external_resources(html)
        kinds = [c.kind for c in result]
        self.assertNotIn("video", kinds)

    def test_extract_handles_base64_inline_image(self) -> None:
        html = '<img src="data:image/png;base64,iVBORw0KGgo=" alt="x" />'
        result = extract_external_resources(html)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].kind, "image")
        self.assertTrue(result[0].url.startswith("data:image/"))

    def test_extract_handles_amp_encoded_url(self) -> None:
        html = '<a href="https://files.cubox.pro/123/a%20b.pdf">下载</a>'
        result = extract_external_resources(html)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].kind, "download")

    def test_extract_wechat_only_chatlog_keyword(self) -> None:
        html = '<html><body>chatlog session 9999 ... <a href="https://szfiles.wx.qq.com/x.pdf">下载</a></body></html>'
        result = extract_external_resources(html)
        self.assertTrue(any(c.url.startswith("https://szfiles.wx.qq.com") for c in result))

    def test_extract_realistic_cubox_layout_sender_context(self) -> None:
        """模拟真实 Cubox HTML：每个资源前有 2-3 个 <div>...</div> 含发送时间和文字。"""
        html = (
            '<html><body>'
            '<div class="reader-page">'
            '<div><div>7-11 15:18</div><div>各位好，方便的话，可以把公司的权利基础，还有对方的侵权行为简单群里说一下，我好评估一下情况</div></div>'
            '<div><div>7-11 15:19</div><div>这是示例产品的结构资料</div></div>'
            '<div><div>7-11 15:19</div>'
            '<span>20250101 示例技术资料.pdf</span>'
            '<a href="https://files.cubox.pro/example/20250101_example.pdf" target="_blank">下载文件</a>'
            '</div>'
            '</div></body></html>'
        )
        result = extract_external_resources(html)
        self.assertEqual(len(result), 1)
        candidate = result[0]
        self.assertEqual(candidate.kind, "download")
        self.assertTrue(any(kw in candidate.sender_context for kw in ["示例产品", "结构资料", "权利基础"]), f"context={candidate.sender_context!r}")


class ResourceCandidateTest(unittest.TestCase):
    def test_to_manifest_extra_row(self) -> None:
        c = ResourceCandidate(
            resource_id="R001",
            kind="download",
            url="https://files.cubox.pro/123/foo.pdf",
            display_filename="foo.pdf",
            sender_context="这是我们在卖的产品",
        )
        row = c.to_manifest_extra()
        self.assertEqual(row["kind"], "download")
        self.assertEqual(row["resource_id"], "R001")
        self.assertEqual(row["url"], "https://files.cubox.pro/123/foo.pdf")
        self.assertEqual(row["display_filename"], "foo.pdf")
        self.assertEqual(row["context"], "这是我们在卖的产品")


class DownloadResourceTest(unittest.TestCase):
    def test_download_stub_returns_success(self) -> None:
        """使用受控 stub 验证目标目录写出文件，不进行真实联网。"""
        with tempfile.TemporaryDirectory() as tmp:
            dest_dir = Path(tmp) / "out"
            content = b"%PDF-1.4 hello world"
            with patch("chat_html_extract._request_url", return_value=content):
                result = download_resource(
                    url="https://files.cubox.pro/example/demo.pdf",
                    dest_dir=dest_dir,
                    display_filename="demo.pdf",
                )
            self.assertEqual(result.status, "ok")
            self.assertIsNotNone(result.path)
            self.assertTrue(Path(result.path).exists())
            self.assertGreater(Path(result.path).stat().st_size, 0)
            self.assertEqual(result.bytes, len(content))
            self.assertEqual(result.attempts, 1)

    def test_download_rejects_local_file_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = download_resource(
                url=f"file://{Path(tmp) / 'secret.txt'}",
                dest_dir=Path(tmp) / "out",
                display_filename="secret.txt",
            )
            self.assertEqual(result.status, "access_denied")
            self.assertIsNone(result.path)

    def test_download_rejects_private_ip_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = download_resource(
                url="http://127.0.0.1/private.pdf",
                dest_dir=Path(tmp) / "out",
                display_filename="private.pdf",
            )
            self.assertEqual(result.status, "access_denied")

    def test_download_does_not_overwrite_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest_dir = Path(tmp) / "out"
            dest_dir.mkdir()
            (dest_dir / "demo.pdf").write_bytes(b"old")
            with patch("chat_html_extract._request_url", return_value=b"new"):
                result = download_resource(
                    url="https://files.cubox.pro/example/demo.pdf",
                    dest_dir=dest_dir,
                    display_filename="demo.pdf",
                )
            self.assertEqual((dest_dir / "demo.pdf").read_bytes(), b"old")
            self.assertEqual(Path(result.path).name, "demo_2.pdf")

    def test_download_inaccessible_url_marks_status(self) -> None:
        """不可达 URL 应当重试后 mark 为 failed；不抛异常。"""
        with tempfile.TemporaryDirectory() as tmp:
            dest_dir = Path(tmp) / "out"
            with patch(
                "chat_html_extract.socket.getaddrinfo",
                side_effect=socket.gaierror("dns unavailable"),
            ):
                result = download_resource(
                    url="https://files.cubox.pro/missing.pdf",
                    dest_dir=dest_dir,
                    display_filename="missing.pdf",
                    max_retries=2,
                    timeout=2,
                )
            self.assertIn(result.status, {"failed", "access_denied"})
            self.assertIsNone(result.path)
            self.assertTrue(result.error)
            self.assertEqual(result.attempts, 2)

    def test_download_mkdir_failure_returns_failed_without_retry(self) -> None:
        """当 dest_dir 是一个已存在的普通文件（mkdir 不能覆盖）时，应该返回 failed 且 attempts=0，不发起网络请求。"""
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "blocker"
            blocker.write_bytes(b"x")
            # dest_dir = blocker 的子目录，mkdir 会失败
            dest_dir = blocker / "subdir"
            result = download_resource(
                url="https://example.invalid/never-called.pdf",
                dest_dir=dest_dir,
                display_filename="never-called.pdf",
            )
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.attempts, 0)
            self.assertTrue(result.error)

    def test_safe_filename_sanitizes_separators(self) -> None:
        """内部 _safe_filename 应去除 / \\ : 等非法字符。"""
        from chat_html_extract import _safe_filename
        self.assertEqual(_safe_filename("a/b/c.pdf"), "a_b_c.pdf")
        self.assertEqual(_safe_filename(""), "untitled")
        self.assertEqual(_safe_filename("name with space.pdf"), "name with space.pdf")  # 空格 OK
        # 长度截断
        long_name = "x" * 200 + ".pdf"
        self.assertLessEqual(len(_safe_filename(long_name)), 120)


if __name__ == "__main__":
    unittest.main()
