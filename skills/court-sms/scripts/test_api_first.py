"""Synthetic API-first consumer checks. No real court or phone data."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import download_zxfw as helper
import lawyer_config


URL = "https://zxfw.court.gov.cn/zxfw/#/index?qdbh=Q&sdbh=S&sdsin=T"
PDF = b"%PDF-1.4\nsynthetic document\n%%EOF"
DOCUMENTS = [{"c_wsmc": "notice", "c_wjgs": "pdf", "wjlj": "https://signed.example/notice"}]
LIST = {"code": 200, "data": DOCUMENTS}
REQUIRED = {"code": 401, "msg": "请先进行身份核验"}
REJECTED = {"code": 403, "msg": "手机号后四位不匹配"}
GATE = {"code": 200, "data": True}


class ApiFirstTests(unittest.TestCase):
    def test_identity_requirement_needs_explicit_supported_business_response(self):
        for message in ("请先进行身份核验", "请核验身份后查阅", "身份核验未通过",
                        "请填写接收本条送达短信的手机号后四位", "手机号后四位不匹配"):
            with self.subTest(message=message):
                self.assertTrue(helper.api_requires_identity({"code": 401, "msg": message}))
        for response in ({"code": 200, "data": DOCUMENTS}, {"code": 401},
                         {"code": 600, "msg": "请进行身份核验"},
                         {"code": 500, "msg": "身份核验失败，请稍后重试"},
                         {"code": 503, "msg": "请先进行身份核验"}):
            with self.subTest(response=response):
                self.assertFalse(helper.api_requires_identity(response))

    def run_case(self, temporary, responses, **kwargs):
        calls = []
        outcomes = {key: list(value) if isinstance(value, list) else value for key, value in responses.items()}

        def request(url, **options):
            endpoint = url.rsplit("/", 1)[-1]
            calls.append(endpoint)
            result = outcomes.get(endpoint)
            if isinstance(result, list):
                result = result.pop(0)
            if isinstance(result, Exception):
                raise result
            if result is None:
                raise AssertionError("unexpected endpoint: " + endpoint)
            return result

        with mock.patch.object(helper, "request_json", side_effect=request):
            result = helper.run(
                URL, Path(temporary) / "staging",
                downloader=lambda url, path, **options: path.write_bytes(PDF), **kwargs)
        return result, calls

    def profile(self, temporary):
        path = Path(temporary) / "lawyers.json"
        lawyer_config.save_profile(path, "demo", "Demo", {"mobile": "1" + "38000" + "00123"})
        return path

    def test_direct_success_never_reads_config_or_queries_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "broken.json"
            config.write_text("broken private config")
            with mock.patch.object(helper, "load_profiles", side_effect=AssertionError("read config")):
                result, calls = self.run_case(
                    temporary, {"getWsListBySdbhNew": LIST}, lawyers_config=config)
            self.assertEqual(result["status"], "downloaded")
            self.assertEqual(calls, ["getWsListBySdbhNew"])
            self.assertEqual(result["identity"]["status"], "not_requested")
            self.assertEqual(result["identity"]["attempts_used"], 0)
            self.assertEqual(result["receipt"]["status"], "not_requested")
            self.assertEqual(Path(result["documents"][0]["file"]).read_bytes(), PDF)

    def test_authorized_direct_path_probes_then_receipts_then_refreshes_list(self):
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(helper, "load_profiles", side_effect=AssertionError("read config")):
                result, calls = self.run_case(temporary, {
                    "getWsListBySdbhNew": [LIST, LIST], "updateSdxxBySdzt": {"code": 200},
                }, receipt_authorized=True)
            self.assertEqual(result["status"], "downloaded")
            self.assertEqual(calls, ["getWsListBySdbhNew", "updateSdxxBySdzt", "getWsListBySdbhNew"])

    def test_explicit_requirement_reads_profile_and_reuses_one_http_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.profile(temporary)
            before = config.read_bytes()
            result, calls = self.run_case(temporary, {
                "getWsListBySdbhNew": [REQUIRED, LIST], "getSfhyKg": GATE,
                "checkSdryxx": {"code": 200}, "updateSdxxBySdzt": {"code": 200},
            }, lawyers_config=config, lawyer_id="demo", receipt_authorized=True)
            self.assertEqual(result["status"], "downloaded")
            self.assertEqual(result["identity"]["status"], "verified")
            self.assertEqual(calls, ["getWsListBySdbhNew", "getSfhyKg", "checkSdryxx",
                                     "updateSdxxBySdzt", "getWsListBySdbhNew"])
            self.assertEqual(config.read_bytes(), before)

    def test_ui_flag_false_cannot_overrule_explicit_list_identity_requirement(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.profile(temporary)
            result, calls = self.run_case(temporary, {
                "getWsListBySdbhNew": [REQUIRED, LIST], "getSfhyKg": {"code": 200, "data": False},
                "checkSdryxx": {"code": 200},
            }, lawyers_config=config, lawyer_id="demo")
            self.assertEqual(result["status"], "downloaded")
            self.assertIn("checkSdryxx", calls)

    def test_rejection_stops_after_probe_without_receipt_or_another_list(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.profile(temporary)
            result, calls = self.run_case(temporary, {
                "getWsListBySdbhNew": REQUIRED, "getSfhyKg": GATE, "checkSdryxx": REJECTED,
            }, lawyers_config=config, lawyer_id="demo", receipt_authorized=True)
            self.assertEqual(result["status"], "identity_blocked")
            self.assertEqual(result["identity"]["next_action"], "ask_recipient_mobile_last4")
            self.assertEqual(calls, ["getWsListBySdbhNew", "getSfhyKg", "checkSdryxx"])

    def test_known_rejection_resume_never_repeats_anonymous_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.profile(temporary)
            first, _ = self.run_case(temporary, {
                "getWsListBySdbhNew": REQUIRED, "getSfhyKg": GATE, "checkSdryxx": REJECTED,
            }, lawyers_config=config, lawyer_id="demo", receipt_authorized=True)
            before = config.read_bytes()
            result, calls = self.run_case(temporary, {
                "getSfhyKg": GATE, "checkSdryxx": {"code": 200},
                "updateSdxxBySdzt": {"code": 200}, "getWsListBySdbhNew": LIST,
            }, recipient_mobile_last4="0456", identity_retry_from=Path(first["manifest_path"]),
                receipt_authorized=True)
            self.assertEqual(result["status"], "downloaded")
            self.assertEqual(calls, ["getSfhyKg", "checkSdryxx", "updateSdxxBySdzt", "getWsListBySdbhNew"])
            self.assertEqual(config.read_bytes(), before)
            self.assertEqual(result["identity"]["attempts_used"], 2)

    def test_generic_api_failures_and_empty_list_do_not_read_phone(self):
        for response, expected in (
            ({"code": 403, "msg": "signature expired"}, "error"),
            ({"code": 401, "msg": "请登录"}, "error"),
            ({"code": 500, "msg": "身份核验服务异常"}, "error"),
            ({"code": 200, "data": []}, "empty"),
            (helper.PermanentApiError("invalid_json"), "error"),
        ):
            with self.subTest(response=type(response).__name__), tempfile.TemporaryDirectory() as temporary:
                with mock.patch.object(helper, "load_profiles", side_effect=AssertionError("read config")):
                    result, calls = self.run_case(
                        temporary, {"getWsListBySdbhNew": response}, attempts=1)
                self.assertEqual(result["status"], expected)
                self.assertEqual(calls, ["getWsListBySdbhNew"])
                self.assertNotIn("next_action", result["identity"])

    def test_network_failure_does_not_turn_into_phone_question_or_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, calls = self.run_case(
                temporary, {"getWsListBySdbhNew": helper.TransientDownloadError("timeout")},
                attempts=1, receipt_authorized=True)
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["reason"], "list_attempts_exhausted")
            self.assertEqual(calls, ["getWsListBySdbhNew"])
            self.assertEqual(result["receipt"]["status"], "not_requested")

    def test_unknown_gate_after_real_requirement_does_not_read_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(helper, "load_profiles", side_effect=AssertionError("read config")):
                result, calls = self.run_case(temporary, {
                    "getWsListBySdbhNew": REQUIRED, "getSfhyKg": {"code": 503},
                })
            self.assertEqual(result["status"], "identity_blocked")
            self.assertEqual(calls, ["getWsListBySdbhNew", "getSfhyKg"])

    def test_late_requirement_resume_keeps_confirmed_receipt_without_resending(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.profile(temporary)
            first, calls = self.run_case(temporary, {
                "getWsListBySdbhNew": [LIST, REQUIRED], "updateSdxxBySdzt": {"code": 200},
                "getSfhyKg": GATE, "checkSdryxx": REJECTED,
            }, lawyers_config=config, lawyer_id="demo", receipt_authorized=True)
            self.assertEqual(first["status"], "identity_blocked")
            self.assertEqual(first["receipt"]["status"], "confirmed")
            result, calls = self.run_case(temporary, {
                "getSfhyKg": GATE, "checkSdryxx": {"code": 200}, "getWsListBySdbhNew": LIST,
            }, identity_retry_from=Path(first["manifest_path"]), recipient_mobile_last4="0456",
                receipt_authorized=True)
            self.assertEqual(result["status"], "downloaded")
            self.assertEqual(result["receipt"]["status"], "confirmed")
            self.assertEqual(calls, ["getSfhyKg", "checkSdryxx", "getWsListBySdbhNew"])

    def test_late_missing_config_can_resume_without_losing_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "absent.json"
            first, _ = self.run_case(temporary, {
                "getWsListBySdbhNew": [LIST, REQUIRED], "updateSdxxBySdzt": {"code": 200}, "getSfhyKg": GATE,
            }, lawyers_config=config, receipt_authorized=True)
            self.assertEqual(first["status"], "needs_config")
            self.assertEqual(first["identity"]["attempts_used"], 0)
            result, calls = self.run_case(temporary, {
                "getSfhyKg": GATE, "checkSdryxx": {"code": 200}, "getWsListBySdbhNew": LIST,
            }, identity_retry_from=Path(first["manifest_path"]), recipient_mobile_last4="0456",
                receipt_authorized=True)
            self.assertEqual(result["status"], "downloaded")
            self.assertNotIn("updateSdxxBySdzt", calls)

    def test_missing_config_resume_can_use_selected_profile_without_new_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            absent = Path(temporary) / "absent.json"
            first, _ = self.run_case(temporary, {
                "getWsListBySdbhNew": REQUIRED, "getSfhyKg": GATE,
            }, lawyers_config=absent)
            self.assertEqual(first["status"], "needs_config")
            profile = self.profile(temporary)
            result, calls = self.run_case(temporary, {
                "getSfhyKg": GATE, "checkSdryxx": {"code": 200}, "getWsListBySdbhNew": LIST,
            }, identity_retry_from=Path(first["manifest_path"]), lawyer_id="demo", lawyers_config=profile)
            self.assertEqual(result["status"], "downloaded")
            self.assertEqual(calls, ["getSfhyKg", "checkSdryxx", "getWsListBySdbhNew"])
            self.assertEqual(result["identity"]["attempts_used"], 1)

    def test_rejected_identity_cannot_resume_with_another_stored_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile = self.profile(temporary)
            first, _ = self.run_case(temporary, {
                "getWsListBySdbhNew": REQUIRED, "getSfhyKg": GATE, "checkSdryxx": REJECTED,
            }, lawyers_config=profile, lawyer_id="demo")
            with mock.patch.object(helper, "request_json") as request:
                with self.assertRaisesRegex(ValueError, "retry_requires_recipient_input"):
                    helper.run(URL, Path(temporary), identity_retry_from=Path(first["manifest_path"]),
                               lawyer_id="demo", lawyers_config=profile)
                request.assert_not_called()

    def test_verified_identity_still_denied_by_list_does_not_try_other_numbers(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.profile(temporary)
            result, calls = self.run_case(temporary, {
                "getWsListBySdbhNew": [REQUIRED, REQUIRED], "getSfhyKg": GATE, "checkSdryxx": {"code": 200},
            }, lawyers_config=config, lawyer_id="demo")
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["reason"], "identity_not_accepted_by_list")
            self.assertEqual(calls.count("checkSdryxx"), 1)


if __name__ == "__main__":
    unittest.main()
