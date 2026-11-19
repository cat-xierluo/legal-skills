#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for chat_html_extract.py"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
            result = download_resource(
                url="https://example.invalid/missing.pdf",
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
