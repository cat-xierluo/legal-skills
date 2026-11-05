"""Synthetic ZXFW regression tests. No court service or case data is accessed."""
import http.server
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import download_zxfw as helper
import lawyer_config


DELIVERY_URL = "https://alias.example/zxfw/#/pagesAjkj/app/wssd/index?qdbh=Q&sdbh=S&sdsin=T"
PARAMS = {"qdbh": "Q", "sdbh": "S", "sdsin": "T"}
PDF = b"%PDF-1.4\n% synthetic download fixture\n%%EOF\n"


class Response(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = headers or {}


def documents():
    return [
        {"c_wsmc": "notice", "wjlj": "https://signed.example/1?token=DEMO", "c_wjgs": "pdf"},
        {"c_wsmc": "notice", "wjlj": "https://signed.example/2?token=DEMO", "c_wjgs": "pdf"},
    ]


def write_pdf(url, destination, **kwargs):
    destination.write_bytes(PDF)


class ParameterAndRetryTests(unittest.TestCase):
    def test_fragment_and_query_params(self):
        self.assertEqual(helper.extract_url_params(DELIVERY_URL), PARAMS)
        self.assertEqual(helper.extract_url_params("https://x/?qdbh=Q&sdbh=S&sdsin=T"), PARAMS)
        self.assertEqual(
            helper.extract_url_params("https://x/#/index?qdbh=Q&sdbh=S&sdsin=A%2BB")["sdsin"],
            "A+B",
        )

    def test_missing_parameter_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing_url_params:sdsin"):
            helper.extract_url_params("https://x/?qdbh=Q&sdbh=S")

    def test_transient_list_failure_retries_twice(self):
        delays = []
        with mock.patch.object(helper, "request_json", side_effect=[
            helper.TransientDownloadError("timeout"),
            helper.TransientDownloadError("timeout"),
            {"code": 200, "data": documents()},
        ]) as request:
            result, count = helper.fetch_documents(PARAMS, sleeper=delays.append)
        self.assertEqual(result, documents())
        self.assertEqual(count, 3)
        self.assertEqual(delays, [3, 8])
        self.assertEqual(request.call_count, 3)

    def test_business_error_is_not_retried_or_echoed(self):
        with mock.patch.object(helper, "request_json", return_value={
            "code": 500, "msg": "secret signature DEMO", "data": [],
        }) as request:
            with self.assertRaisesRegex(helper.PermanentApiError, "^api_code_500$"):
                helper.fetch_documents(PARAMS)
        request.assert_called_once()

    def test_http_503_is_transient(self):
        error = helper.urllib.error.HTTPError("https://example.test", 503, "busy", {}, None)
        with mock.patch.object(helper.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(helper.TransientDownloadError):
                helper.request_json(helper.API_ENDPOINT, timeout=1)

    def test_html_api_response_is_not_retried(self):
        with mock.patch.object(helper.urllib.request, "urlopen", return_value=Response(b"<html>login</html>")):
            with self.assertRaisesRegex(helper.PermanentApiError, "invalid_json"):
                helper.fetch_documents(PARAMS)


class FileDownloadTests(unittest.TestCase):
    def test_valid_file_is_saved_and_temp_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "notice.pdf"
            with mock.patch.object(helper.urllib.request, "urlopen", return_value=Response(
                PDF, {"Content-Length": str(len(PDF))}
            )):
                helper.download_file("https://signed.example/file", target)
            self.assertEqual(target.read_bytes(), PDF)
            self.assertEqual(list(Path(temporary).iterdir()), [target])

    def test_empty_html_and_wrong_pdf_are_rejected(self):
        for body in (b"", b"<!doctype html><html>expired</html>", b'{"error":"expired"}'):
            with self.subTest(body=body), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary) / "notice.pdf"
                with mock.patch.object(helper.urllib.request, "urlopen", return_value=Response(body)) as request:
                    with self.assertRaises(helper.PermanentApiError):
                        helper.download_file("https://signed.example/file", target)
                request.assert_called_once()
                self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_timeout_fragments_are_cleaned_after_each_attempt(self):
        class Interrupted(Response):
            def read(self, size=-1):
                if self.tell() > 0:
                    raise TimeoutError("synthetic timeout")
                return super().read(4)

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "notice.pdf"
            with mock.patch.object(helper.urllib.request, "urlopen", side_effect=lambda *a, **k: Interrupted(PDF)):
                with self.assertRaises(helper.TransientDownloadError):
                    helper.download_file(
                        "https://signed.example/file", target, sleeper=lambda delay: None,
                    )
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_other_formats_reject_api_errors_and_bom_html(self):
        for suffix in (".doc", ".xls", ".ppt", ".png", ".json"):
            for body in (b'{"code":403,"msg":"expired"}', b'{"error":"expired"}', b"\xef\xbb\xbf<html>login</html>"):
                with self.subTest(suffix=suffix, body=body), tempfile.TemporaryDirectory() as temporary:
                    target = Path(temporary) / ("notice" + suffix)
                    with mock.patch.object(helper.urllib.request, "urlopen", return_value=Response(body)):
                        with self.assertRaises(helper.PermanentApiError):
                            helper.download_file("https://signed.example/file", target)
                    self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_recognized_legacy_doc_and_image_headers_pass(self):
        for suffix, body in (
            (".doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1demo"),
            (".doc", b"{\\rtf1 demo}"),
            (".png", b"\x89PNG\r\n\x1a\ndemo"),
        ):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary) / ("notice" + suffix)
                with mock.patch.object(helper.urllib.request, "urlopen", return_value=Response(body)):
                    helper.download_file("https://signed.example/file", target)
                self.assertEqual(target.read_bytes(), body)

    def test_truncated_response_retries_then_saves_complete_file(self):
        responses = [
            Response(PDF[:10], {"Content-Length": str(len(PDF))}),
            Response(PDF, {"Content-Length": str(len(PDF))}),
        ]
        delays = []
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "notice.pdf"
            with mock.patch.object(helper.urllib.request, "urlopen", side_effect=responses):
                helper.download_file("https://signed.example/file", target, sleeper=delays.append)
            self.assertEqual(target.read_bytes(), PDF)
            self.assertEqual(delays, [3])
            self.assertEqual(list(Path(temporary).iterdir()), [target])


class WorkflowTests(unittest.TestCase):
    def run_fixture(self, root, **kwargs):
        return helper.run(
            DELIVERY_URL, Path(root),
            fetcher=kwargs.pop("fetcher", mock.Mock(return_value=(documents(), 1))),
            downloader=kwargs.pop("downloader", write_pdf), **kwargs,
            gate_checker=lambda *a, **k: {"status": "not_required"},
        )

    def test_duplicate_names_private_runs_and_redacted_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            first = self.run_fixture(temporary)
            second = self.run_fixture(temporary)
            self.assertEqual(first["status"], "downloaded")
            self.assertNotEqual(first["output_dir"], second["output_dir"])
            self.assertEqual(
                [Path(item["file"]).name for item in first["documents"]],
                ["notice.pdf", "notice_2.pdf"],
            )
            for item in first["documents"]:
                self.assertEqual(Path(item["file"]).read_bytes(), PDF)
            text = Path(first["manifest_path"]).read_text()
            self.assertNotIn("signed.example", text)
            self.assertNotIn("token=", text)
            if os.name == "posix":
                self.assertEqual(Path(first["output_dir"]).stat().st_mode & 0o777, 0o700)
                self.assertEqual(Path(first["manifest_path"]).stat().st_mode & 0o777, 0o600)

    def test_receipt_is_opt_in_and_sent_before_list(self):
        events = []
        receipt = mock.Mock(side_effect=lambda *a, **k: events.append("receipt") or {"status": "confirmed"})
        fetch = mock.Mock(side_effect=lambda *a, **k: events.append("list") or (documents(), 1))
        with tempfile.TemporaryDirectory() as temporary:
            default = self.run_fixture(temporary, receipt_sender=receipt)
            self.assertEqual(default["receipt"]["status"], "not_requested")
            receipt.assert_not_called()
            result = self.run_fixture(temporary, fetcher=fetch, receipt_sender=receipt, receipt_authorized=True)
        self.assertEqual(events, ["list", "receipt", "list"])
        self.assertEqual(result["receipt"]["status"], "confirmed")

    def test_unknown_receipt_does_not_repeat_or_block_download(self):
        with mock.patch.object(helper, "request_json", side_effect=helper.TransientDownloadError("timeout")) as request:
            with tempfile.TemporaryDirectory() as temporary:
                result = self.run_fixture(temporary, receipt_authorized=True)
        self.assertEqual(result["status"], "downloaded")
        self.assertEqual(result["receipt"]["status"], "unknown")
        request.assert_called_once()

    def test_non_json_receipt_is_unknown_but_explicit_refusal_is_unconfirmed(self):
        with mock.patch.object(helper, "request_json", side_effect=helper.PermanentApiError("invalid_json")) as request:
            self.assertEqual(helper.confirm_receipt(PARAMS, timeout=1)["status"], "unknown")
        request.assert_called_once()
        with mock.patch.object(helper, "request_json", return_value={"code": 403}):
            self.assertEqual(helper.confirm_receipt(PARAMS, timeout=1)["status"], "unconfirmed")

    def test_manifest_name_is_reserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = helper._unique_destination(root, "download-manifest", ".json", {root / "download-manifest.json"})
            self.assertEqual(path.name, "download-manifest_2.json")

    def test_case_variant_of_manifest_name_is_also_reserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = helper._unique_destination(root, "DOWNLOAD-MANIFEST", ".json", {root / "download-manifest.json"})
            self.assertEqual(path.name, "DOWNLOAD-MANIFEST_2.json")

    def test_missing_file_cannot_be_reported_as_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_fixture(temporary, downloader=lambda *a, **k: None)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["documents"], [])

    def test_partial_failure_retains_real_success(self):
        def download(url, path, **kwargs):
            if "/2?" in url:
                raise helper.PermanentApiError("http_403")
            path.write_bytes(PDF)

        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_fixture(temporary, downloader=download)
            self.assertEqual(result["status"], "partial")
            self.assertEqual(len(result["documents"]), 1)
            self.assertEqual(Path(result["documents"][0]["file"]).read_bytes(), PDF)
            self.assertEqual(result["failures"][0]["reason"], "http_403")

    def test_retry_and_timeout_options_reach_file_downloader(self):
        downloader = mock.Mock(side_effect=write_pdf)
        with tempfile.TemporaryDirectory() as temporary:
            self.run_fixture(temporary, downloader=downloader, attempts=1, download_timeout=4)
        self.assertEqual(downloader.call_args.kwargs, {"timeout": 4, "attempts": 1})

    def test_empty_list_is_not_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_fixture(temporary, fetcher=lambda *a, **k: ([], 1))
        self.assertEqual(result["status"], "empty")

    def test_invalid_limits_do_not_start_requests(self):
        fetch = mock.Mock()
        for options in ({"attempts": 0}, {"attempts": 4}, {"timeout": 0}, {"timeout": float("nan")}):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(ValueError):
                    self.run_fixture(temporary, fetcher=fetch, **options)
        fetch.assert_not_called()


class CliIntegrationTests(unittest.TestCase):
    def test_real_http_and_cli_success_and_failure(self):
        events = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                events.append(self.path)
                if self.path == "/gate":
                    body = {"code": 200, "data": payload["qdbh"] == "IDENTITY"}
                elif self.path == "/verify":
                    if "session=DEMO_COOKIE" not in self.headers.get("Cookie", ""):
                        body = {"code": 403}
                    else:
                        body = {"code": 200 if payload.get("jylx") == "sjhm" and payload.get("jyz") == "0123" else 403}
                elif self.path == "/receipt":
                    body = {"code": 200}
                elif (payload["qdbh"] == "IDENTITY"
                      and "identity_verified=YES" not in self.headers.get("Cookie", "")):
                    body = {"code": 401, "msg": "请先进行身份核验"}
                elif payload["qdbh"] == "FAIL":
                    body = {"code": 400, "msg": "synthetic invalid signature"}
                else:
                    body = {"code": 200, "data": [
                        {"c_wsmc": "notice", "c_wjgs": "pdf",
                         "wjlj": f"http://127.0.0.1:{self.server.server_port}/file"},
                    ]}
                encoded = json.dumps(body).encode()
                self.send_response(200)
                if self.path == "/gate":
                    self.send_header("Set-Cookie", "session=DEMO_COOKIE; Path=/")
                elif self.path == "/verify" and body["code"] == 200:
                    self.send_header("Set-Cookie", "identity_verified=YES; Path=/")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def do_GET(self):
                events.append(self.path)
                self.send_response(200)
                self.send_header("Content-Length", str(len(PDF)))
                self.end_headers()
                self.wfile.write(PDF)

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                launcher = Path(temporary) / "synthetic_cli.py"
                launcher.write_text(
                    "import sys\n"
                    f"sys.path.insert(0, {str(Path(__file__).parent)!r})\n"
                    "import download_zxfw as helper\n"
                    f"helper.API_ENDPOINT = 'http://127.0.0.1:{server.server_port}/list'\n"
                    f"helper.RECEIPT_ENDPOINT = 'http://127.0.0.1:{server.server_port}/receipt'\n"
                    f"helper.IDENTITY_GATE_ENDPOINT = 'http://127.0.0.1:{server.server_port}/gate'\n"
                    f"helper.IDENTITY_CHECK_ENDPOINT = 'http://127.0.0.1:{server.server_port}/verify'\n"
                    "raise SystemExit(helper.main())\n"
                )
                command = [sys.executable, str(launcher), "--url", DELIVERY_URL,
                           "--output", temporary, "--confirm-receipt", "--attempts", "1"]
                env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
                success = subprocess.run(command, capture_output=True, text=True, env=env, timeout=10)
                self.assertEqual(success.returncode, 0, success.stderr)
                result = json.loads(success.stdout)
                self.assertEqual(events, ["/list", "/receipt", "/list", "/file"])
                self.assertEqual(Path(result["documents"][0]["file"]).read_bytes(), PDF)
                events.clear()
                command[command.index(DELIVERY_URL)] = DELIVERY_URL.replace("qdbh=Q", "qdbh=FAIL")
                command.remove("--confirm-receipt")
                failure = subprocess.run(command, capture_output=True, text=True, env=env, timeout=10)
                self.assertEqual(failure.returncode, 2, failure.stderr)
                self.assertEqual(json.loads(failure.stdout)["reason"], "api_code_400")
                self.assertEqual(events, ["/list"])
                events.clear()
                config = Path(temporary) / "lawyers.json"
                lawyer_config.save_profile(
                    config, "demo-lawyer", "Demo Lawyer", {"mobile": "1" + "38000" + "00123"},
                )
                command[command.index(DELIVERY_URL.replace("qdbh=Q", "qdbh=FAIL"))] = DELIVERY_URL.replace("qdbh=Q", "qdbh=IDENTITY")
                command.extend(["--lawyer-id", "demo-lawyer", "--lawyers-config", str(config), "--confirm-receipt"])
                verified = subprocess.run(command, capture_output=True, text=True, env=env, timeout=10)
                self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
                self.assertEqual(events, ["/list", "/gate", "/verify", "/receipt", "/list", "/file"])
                verified_result = json.loads(verified.stdout)
                self.assertEqual(verified_result["identity"]["status"], "verified")
                self.assertNotIn("0123", Path(verified_result["manifest_path"]).read_text())
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
