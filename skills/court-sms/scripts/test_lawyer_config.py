"""Private-profile and identity-gate tests with synthetic data only."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import download_zxfw as download
import lawyer_config as config


MOBILE = "1" + "38000" + "00123"
PARAMS = {"qdbh": "Q", "sdbh": "S", "sdsin": "T", "mm": "DEMO_MM"}
URL = "https://zxfw.court.gov.cn/zxfw/#/index?qdbh=Q&sdbh=S&sdsin=T&mm=DEMO_MM"


class ProfileTests(unittest.TestCase):
    def test_save_update_preserves_other_lawyers_and_leading_zero_tail(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            config.save_profile(path, "lawyer-a", "Lawyer A", {"mobile": MOBILE})
            config.save_profile(path, "lawyer-b", "Lawyer B", {"mobile": "1" + "39000" + "00456"})
            config.save_profile(path, "lawyer-a", "Lawyer A", {"id_last4": "00aX"})
            self.assertEqual(config.select_identity(path, "lawyer-a"), ("lawyer-a", "0123"))
            self.assertEqual(config.select_identity(path, "lawyer-a", "zjhm"), ("lawyer-a", "00aX"))
            self.assertEqual(len(config.load_profiles(path)["lawyers"]), 2)
            with self.assertRaisesRegex(config.ProfileError, "lawyer_selection_required"):
                config.select_identity(path)
            if os.name == "posix":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertFalse(path.with_name("lawyers.json.lock").exists())

    def test_invalid_updates_do_not_change_existing_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            config.save_profile(path, "lawyer-a", "Lawyer A", {"mobile": MOBILE})
            old = path.read_bytes()
            for data in ({"mobile": "1234"}, {"id_last4": "FULL_ID_NOT_ACCEPTED"}, {"unknown": "value"}):
                with self.subTest(data=data), self.assertRaises(config.ProfileError):
                    config.save_profile(path, "lawyer-a", "Lawyer A", data)
                self.assertEqual(path.read_bytes(), old)

    def test_single_profile_still_requires_confirmed_recipient_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            config.save_profile(path, "other-lawyer", "Other Lawyer", {"mobile": MOBILE})
            with self.assertRaisesRegex(config.ProfileError, "lawyer_selection_required"):
                config.select_identity(path)
            requester = mock.Mock()
            result = download.verify_identity(PARAMS, timeout=1, config_path=path, requester=requester)
            self.assertEqual(result["status"], "needs_config")
            requester.assert_not_called()

    def test_mobile_tail_only_profile_is_valid_and_selected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            config.save_profile(path, "recipient", "Recipient", {"mobile_last4": "0456"})
            self.assertEqual(config.select_identity(path, "recipient"), ("recipient", "0456"))
            profile = config.load_profiles(path)["lawyers"]["recipient"]
            self.assertEqual(profile["mobile_last4"], "0456")
            self.assertNotIn("mobile", profile)

    def test_mobile_tail_must_match_a_full_mobile_when_both_are_present(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            config.save_profile(path, "demo", "Demo", {"mobile": MOBILE, "mobile_last4": "0123"})
            self.assertEqual(config.select_identity(path, "demo"), ("demo", "0123"))
            before = path.read_bytes()
            with self.assertRaisesRegex(config.ProfileError, "mobile_tail_conflict"):
                config.save_profile(path, "demo", "Demo", {"mobile_last4": "9999"})
            self.assertEqual(path.read_bytes(), before)

    def test_invalid_tail_and_corrupt_saved_tail_never_reach_the_court(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            for tail in ("123", "12345", "12a4", "１２３４", 1234, "", None):
                with self.subTest(tail=tail), self.assertRaises(config.ProfileError):
                    config.normalize_mobile_last4(tail)
            path.write_text(json.dumps({"schema_version": 1, "lawyers": {
                "demo": {"name": "Demo", "mobile_last4": "12a4"}}}))
            requester = mock.Mock()
            result = download.verify_identity_candidates(
                PARAMS, timeout=1, config_path=path, lawyer_id="demo", requester=requester)
            self.assertEqual(result["status"], "needs_config")
            requester.assert_not_called()

    def test_cli_reads_secret_from_stdin_and_list_does_not_echo_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            script = Path(__file__).with_name("lawyer_config.py")
            base = [sys.executable, str(script), "--config", str(path)]
            process = subprocess.run(
                [*base, "set", "--lawyer-id", "demo", "--name", "Demo", "--stdin"],
                input=json.dumps({"mobile": MOBILE}), text=True, capture_output=True,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertNotIn(MOBILE, process.stdout + process.stderr)
            listing = subprocess.run([*base, "list"], text=True, capture_output=True)
            self.assertEqual(listing.returncode, 0)
            self.assertNotIn(MOBILE, listing.stdout)
            getting = subprocess.run([*base, "get", "--lawyer-id", "demo"], text=True, capture_output=True)
            self.assertNotIn("0123", getting.stdout)
            revealed = subprocess.run([*base, "get", "--lawyer-id", "demo", "--reveal"], text=True, capture_output=True)
            self.assertEqual(json.loads(revealed.stdout)["last4"], "0123")


class IdentityTests(unittest.TestCase):
    def test_gate_boolean_and_string_values(self):
        for value, expected in ((True, "required"), ("true", "required"), (False, "not_required"), ("false", "not_required")):
            with self.subTest(value=value):
                result = download.identity_gate(
                    PARAMS, timeout=1, requester=lambda *a, **k: {"code": 200, "data": value},
                )
                self.assertEqual(result["status"], expected)

    def test_required_gate_missing_profile_stops_before_receipt_or_list(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = mock.Mock()
            fetcher = mock.Mock(side_effect=download.IdentityRequiredApiError())
            result = download.run(
                URL, Path(temporary) / "staging", lawyers_config=Path(temporary) / "absent.json",
                receipt_authorized=True, receipt_sender=receipt, fetcher=fetcher,
                gate_checker=lambda *a, **k: {"status": "required"},
            )
            self.assertEqual(result["status"], "needs_config")
            self.assertEqual(result["identity"]["reason"], "lawyer_selection_required")
            receipt.assert_not_called()
            fetcher.assert_called_once()

    def test_unknown_gate_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as temporary:
            fetcher = mock.Mock()
            result = download.run(
                URL, Path(temporary), fetcher=fetcher, identity_only=True,
                gate_checker=lambda *a, **k: {"status": "unknown"},
            )
            self.assertEqual(result["status"], "identity_blocked")
            fetcher.assert_not_called()

    def test_exact_identity_payload_and_no_retry_after_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            config.save_profile(path, "demo", "Demo", {"mobile": MOBILE})
            requester = mock.Mock(return_value={"code": 403, "msg": "手机号后四位不匹配"})
            result = download.verify_identity(
                PARAMS, timeout=1, config_path=path, lawyer_id="demo", requester=requester,
            )
            self.assertEqual(result["status"], "rejected")
            requester.assert_called_once()
            payload = requester.call_args.kwargs["payload"]
            self.assertEqual(payload, {**PARAMS, "jylx": "sjhm", "jyz": "0123"})
            self.assertNotIn(MOBILE, json.dumps(result))
            self.assertNotIn("0123", json.dumps(result))
            self.assertEqual(result["next_action"], "ask_recipient_mobile_last4")

    def test_optional_mm_parameter_is_preserved(self):
        self.assertEqual(download.extract_url_params(URL), PARAMS)

    def test_rejected_mobile_returns_to_user_without_trying_saved_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            config.save_profile(path, "demo", "Demo", {"mobile": MOBILE, "id_last4": "00aX"})
            seen = []

            def requester(url, **kwargs):
                seen.append(kwargs["payload"]["jyz"])
                if kwargs["payload"]["jylx"] == "sjhm":
                    return {"code": 403, "msg": "手机号后四位不匹配"}
                return {"code": 200}

            result = download.verify_identity_candidates(
                PARAMS, timeout=1, config_path=path, lawyer_id="demo",
                requester=requester, sleeper=lambda delay: None,
            )
            self.assertEqual(result["status"], "rejected")
            self.assertEqual(seen, ["0123"])
            self.assertEqual(result["next_action"], "ask_recipient_mobile_last4")

    def test_requested_method_is_tried_first(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            config.save_profile(path, "demo", "Demo", {"mobile": MOBILE, "id_last4": "00aX"})
            seen = []

            def requester(url, **kwargs):
                seen.append(kwargs["payload"]["jylx"])
                return {"code": 403, "msg": "手机号后四位不匹配"}

            download.verify_identity_candidates(
                PARAMS, timeout=1, config_path=path, lawyer_id="demo", method="zjhm",
                requester=requester, sleeper=lambda delay: None,
            )
            self.assertEqual(seen, ["zjhm"])

    def test_missing_credential_for_the_requested_method_is_distinguishable(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            config.save_profile(path, "demo", "Demo", {"mobile": MOBILE})
            requester = mock.Mock()
            result = download.verify_identity_candidates(
                PARAMS, timeout=1, config_path=path, lawyer_id="demo", method="zjhm", requester=requester,
            )
            self.assertEqual(result["reason"], "missing_zjhm_credential")
            self.assertEqual(result["next_action"], "configure_selected_profile")
            requester.assert_not_called()

    def test_more_candidates_than_budget_stops_without_requests(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            config.save_profile(path, "a", "A", {"mobile": MOBILE, "id_last4": "00aX"})
            config.save_profile(path, "b", "B", {"mobile": MOBILE, "id_last4": "00bX"})
            requester = mock.Mock()
            result = download.verify_identity_candidates(
                PARAMS, timeout=1, config_path=path, requester=requester, max_attempts=2,
            )
            self.assertEqual(result["status"], "needs_config")
            self.assertEqual(result["reason"], "lawyer_selection_required")
            requester.assert_not_called()

    def test_without_lawyer_id_no_configured_lawyer_is_contacted(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            config.save_profile(path, "a", "A", {"mobile": MOBILE})
            config.save_profile(path, "b", "B", {"mobile": MOBILE})
            requester = mock.Mock()
            result = download.verify_identity_candidates(
                PARAMS, timeout=1, config_path=path, requester=requester,
            )
            self.assertEqual(result["status"], "needs_config")
            self.assertEqual(result["reason"], "lawyer_selection_required")
            requester.assert_not_called()

    def test_rejected_candidate_does_not_fall_through_to_other_lawyers(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            config.save_profile(path, "lawyer-a", "A", {"mobile": MOBILE})
            config.save_profile(path, "lawyer-b", "B", {"mobile": MOBILE})
            requester = mock.Mock(return_value={"code": 403, "msg": "手机号后四位不匹配"})
            result = download.verify_identity_candidates(
                PARAMS, timeout=1, config_path=path, lawyer_id="lawyer-a",
                requester=requester, sleeper=lambda delay: None,
            )
            self.assertEqual(result["status"], "rejected")
            requester.assert_called_once()

    def test_delivery_recipient_flag_is_stored_and_validated(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            config.save_profile(path, "demo", "Demo", {"mobile": MOBILE, "delivery_recipient": True})
            profile = config.load_profiles(path)["lawyers"]["demo"]
            self.assertTrue(profile["delivery_recipient"])
            with self.assertRaises(config.ProfileError):
                config.save_profile(path, "demo", "Demo", {"delivery_recipient": "yes"})

    def test_tail_only_recipient_is_sent_as_mobile_credential(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            config.save_profile(path, "recipient", "Recipient", {"mobile_last4": "0456"})
            requester = mock.Mock(return_value={"code": 200})
            result = download.verify_identity_candidates(
                PARAMS, timeout=1, config_path=path, lawyer_id="recipient", requester=requester,
            )
            self.assertEqual(result["status"], "verified")
            self.assertEqual(requester.call_args.kwargs["payload"]["jyz"], "0456")
            self.assertEqual(requester.call_args.kwargs["payload"]["jylx"], "sjhm")

    def test_identity_only_mode_skips_receipt_and_list(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            config.save_profile(path, "demo", "Demo", {"mobile": MOBILE})
            receipt, fetcher = mock.Mock(), mock.Mock()
            result = download.run(
                URL, Path(temporary), lawyers_config=path, lawyer_id="demo",
                identity_only=True, receipt_authorized=True,
                receipt_sender=receipt, fetcher=fetcher,
                gate_checker=lambda *a, **k: {"status": "required"},
                identity_checker=lambda *a, **k: {"status": "verified", "lawyer_id": "demo"},
            )
            self.assertEqual(result["status"], "identity_checked")
            receipt.assert_not_called()
            fetcher.assert_not_called()

    def test_one_time_answer_overrides_profile_without_loading_or_saving_it(self):
        requester = mock.Mock(return_value={"code": 200})
        with mock.patch.object(download, "load_profiles", side_effect=AssertionError("must not load profile")):
            result = download.verify_identity_candidates(
                PARAMS, timeout=1, recipient_mobile_last4="0456", requester=requester)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["source"], "user_input")
        self.assertNotIn("lawyer_id", result)
        self.assertEqual(requester.call_args.kwargs["payload"], {
            **PARAMS, "jylx": "sjhm", "jyz": "0456"})
        self.assertNotIn("0456", json.dumps(result))

    def test_unknown_or_service_failure_does_not_prompt_for_new_personal_data(self):
        for response in (None, [], {}, {"code": "403"}, {"code": 201}, {"code": 401}, {"code": 403}, {"code": 404}, {"code": 429}, {"code": 503}, {"code": 600}):
            with self.subTest(response=response):
                result = download.verify_identity_candidates(
                    PARAMS, timeout=1, recipient_mobile_last4="0456",
                    requester=lambda *a, **k: response)
                self.assertEqual(result["status"], "unknown")
                self.assertNotIn("next_action", result)

    def test_service_failure_with_identity_wording_is_not_a_recipient_rejection(self):
        for response in (
            {"code": 500, "msg": "身份核验服务错误"},
            {"code": 500, "msg": "手机号核验失败，系统异常"},
            {"code": 503, "msg": "手机号后四位不匹配"},
            {"code": 500, "msg": "身份核验失败，请稍后重试"},
            {"code": 600, "msg": "手机号后四位不匹配"},
        ):
            with self.subTest(response=response):
                result = download.verify_identity_candidates(
                    PARAMS, timeout=1, recipient_mobile_last4="0456",
                    requester=lambda *a, **k: response)
                self.assertEqual(result["status"], "unknown")
                self.assertNotIn("next_action", result)

    def test_business_500_requires_an_explicit_credential_mismatch_message(self):
        result = download.verify_identity_candidates(
            PARAMS, timeout=1, recipient_mobile_last4="0456",
            requester=lambda *a, **k: {"code": 500, "msg": "手机号后四位不匹配"})
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["next_action"], "ask_recipient_mobile_last4")


class CliIdentityTests(unittest.TestCase):
    """End-to-end CLI checks with the HTTP layer replaced by a local stub."""

    def run_cli(self, temporary, extra_args, responses, config=None, input_text=None):
        launcher = Path(temporary) / "cli_stub.py"
        launcher.write_text(
            "import sys, json\n"
            f"sys.path.insert(0, {str(Path(__file__).parent)!r})\n"
            "import download_zxfw as helper\n"
            "calls = []\n"
            "verified = False\n"
            f"responses = {responses!r}\n"
            "def stub(url, **kwargs):\n"
            "    global verified\n"
            "    name = url.rsplit('/', 1)[-1]\n"
            "    calls.append(name)\n"
            "    if (name == 'getWsListBySdbhNew' and name not in responses and not verified\n"
            "        and responses.get('getSfhyKg', {}).get('data') is True):\n"
            "        return {'code': 401, 'msg': '请先进行身份核验'}\n"
            "    result = responses.get(name, {'code': 200, 'data': []})\n"
            "    if name == 'checkSdryxx' and result.get('code') == 200:\n"
            "        verified = True\n"
            "    return result\n"
            "helper.request_json = stub\n"
            "helper.download_file = lambda url, path, **kwargs: path.write_bytes(b'%PDF-1.4 demo')\n"
            "code = helper.main()\n"
            "print('CALLS:' + json.dumps(calls))\n"
            "raise SystemExit(code)\n"
        )
        command = [sys.executable, str(launcher), "--url", URL, "--output", temporary, *extra_args]
        if config:
            command += ["--lawyers-config", str(config)]
        process = subprocess.run(
            command, capture_output=True, text=True, input=input_text,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, timeout=20,
        )
        calls = []
        payload_text = []
        for line in process.stdout.splitlines():
            if line.startswith("CALLS:"):
                calls = json.loads(line[len("CALLS:"):])
            elif payload_text or line.startswith("{"):
                payload_text.append(line)
        payload = json.loads("\n".join(payload_text))
        if input_text:
            submitted = json.loads(input_text)
            for secret in submitted.values() if isinstance(submitted, dict) else []:
                if isinstance(secret, str) and secret:
                    self.assertNotIn(secret, process.stdout + process.stderr)
        return process.returncode, payload, calls

    def test_identity_only_cli_never_receipts_or_lists(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "lawyers.json"
            config.save_profile(config_path, "demo", "Demo", {"mobile": MOBILE})
            responses = {
                "getSfhyKg": {"code": 200, "data": True},
                "checkSdryxx": {"code": 200},
                "getWsListBySdbhNew": {"code": 200, "data": [
                    {"c_wsmc": "notice", "c_wjgs": "pdf", "wjlj": "https://signed.example/1"}]},
            }
            code, payload, calls = self.run_cli(
                temporary, ["--identity-only", "--confirm-receipt", "--lawyer-id", "demo"], responses, config_path,
            )
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["status"], "identity_checked")
            self.assertEqual(calls, ["getSfhyKg", "checkSdryxx"])
            self.assertNotIn("updateSdxxBySdzt", calls)
            self.assertNotIn("getWsListBySdbhNew", calls)

    def test_cli_without_lawyer_id_sends_no_identity_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "lawyers.json"
            config.save_profile(config_path, "a", "A", {"mobile": MOBILE})
            config.save_profile(config_path, "b", "B", {"mobile": MOBILE})
            responses = {"getSfhyKg": {"code": 200, "data": True}}
            code, payload, calls = self.run_cli(temporary, [], responses, config_path)
            self.assertEqual(code, 2)
            self.assertEqual(payload["status"], "needs_config")
            self.assertNotIn("checkSdryxx", calls)

    def test_single_marked_recipient_may_proceed_without_lawyer_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "lawyers.json"
            config.save_profile(config_path, "client", "Client", {"mobile": MOBILE, "delivery_recipient": True})
            config.save_profile(config_path, "lawyer", "Lawyer", {"mobile": MOBILE})
            responses = {"getSfhyKg": {"code": 200, "data": True}, "checkSdryxx": {"code": 200}}
            code, payload, calls = self.run_cli(temporary, ["--identity-only"], responses, config_path)
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["identity"]["lawyer_id"], "client")

    def test_identity_attempts_cannot_exceed_the_hard_cap(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "lawyers.json"
            config.save_profile(config_path, "demo", "Demo", {"mobile": MOBILE, "id_last4": "00aX"})
            responses = {"getSfhyKg": {"code": 200, "data": True}, "checkSdryxx": {"code": 403, "msg": "手机号后四位不匹配"}}
            code, payload, calls = self.run_cli(
                temporary, ["--identity-only", "--lawyer-id", "demo", "--identity-attempts", "99"], responses, config_path,
            )
            self.assertEqual(code, 2)
            self.assertEqual(calls.count("checkSdryxx"), 1)
            self.assertEqual(payload["identity"]["attempts_limit"], 2)

    def test_rejected_identity_blocks_receipt_and_list(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "lawyers.json"
            config.save_profile(config_path, "demo", "Demo", {"mobile": MOBILE})
            responses = {"getSfhyKg": {"code": 200, "data": True}, "checkSdryxx": {"code": 403, "msg": "手机号后四位不匹配"}}
            code, payload, calls = self.run_cli(
                temporary, ["--lawyer-id", "demo", "--confirm-receipt"], responses, config_path,
            )
            self.assertEqual(code, 2)
            self.assertEqual(payload["status"], "identity_blocked")
            self.assertEqual(payload["identity"]["next_action"], "ask_recipient_mobile_last4")
            self.assertNotIn("updateSdxxBySdzt", calls)
            self.assertEqual(calls.count("getWsListBySdbhNew"), 1)

    def test_set_tail_command_accepts_the_answered_tail_from_stdin(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            script = Path(__file__).with_name("lawyer_config.py")
            process = subprocess.run(
                [sys.executable, str(script), "--config", str(path), "set-tail",
                 "--lawyer-id", "client", "--name", "Client", "--stdin"],
                input=json.dumps({"mobile_last4": "0456"}), text=True, capture_output=True,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertNotIn("0456", process.stdout + process.stderr)
            profile = config.load_profiles(path)["lawyers"]["client"]
            self.assertEqual(profile["mobile_last4"], "0456")
            self.assertEqual(config.select_identity(path, "client"), ("client", "0456"))

    def test_null_tail_cannot_be_saved_as_a_successful_answer(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            config.save_profile(path, "demo", "Demo", {"mobile": MOBILE})
            before = path.read_bytes()
            process = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("lawyer_config.py")),
                 "--config", str(path), "set-tail", "--lawyer-id", "demo", "--name", "Demo", "--stdin"],
                input=json.dumps({"mobile_last4": None}), text=True, capture_output=True)
            self.assertEqual(process.returncode, 2)
            self.assertEqual(json.loads(process.stdout)["reason"], "invalid_mobile_last4")
            self.assertEqual(path.read_bytes(), before)

    def test_get_command_hides_the_last_four_digits_by_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            script = Path(__file__).with_name("lawyer_config.py")
            base = [sys.executable, str(script), "--config", str(path)]
            subprocess.run(
                [*base, "set", "--lawyer-id", "demo", "--name", "Demo", "--stdin"],
                input=json.dumps({"mobile": MOBILE}), text=True, capture_output=True, check=True,
            )
            hidden = subprocess.run([*base, "get", "--lawyer-id", "demo"], text=True, capture_output=True)
            self.assertNotIn("0123", hidden.stdout)
            revealed = subprocess.run([*base, "get", "--lawyer-id", "demo", "--reveal"], text=True, capture_output=True)
            self.assertEqual(json.loads(revealed.stdout)["last4"], "0123")

    def test_null_update_does_not_clear_a_stored_mobile(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            config.save_profile(path, "demo", "Demo", {"mobile": MOBILE})
            config.save_profile(path, "demo", "Demo", {"mobile": None})
            self.assertEqual(config.load_profiles(path)["lawyers"]["demo"]["mobile"], MOBILE)

    def test_reject_ask_answer_then_download_preserves_local_phone_and_authorization(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lawyers.json"
            config.save_profile(path, "demo", "Demo", {"mobile": MOBILE, "id_last4": "00aX"})
            before = path.read_bytes()
            rejected = {"getSfhyKg": {"code": 200, "data": True}, "checkSdryxx": {"code": 403, "msg": "手机号后四位不匹配"}}
            code, blocked, calls = self.run_cli(
                temporary, ["--lawyer-id", "demo", "--confirm-receipt"], rejected, path)
            self.assertEqual(code, 2)
            self.assertEqual(calls, ["getWsListBySdbhNew", "getSfhyKg", "checkSdryxx"])
            self.assertEqual(blocked["identity"]["next_action"], "ask_recipient_mobile_last4")
            success = {
                "getSfhyKg": {"code": 200, "data": True}, "checkSdryxx": {"code": 200},
                "getWsListBySdbhNew": {"code": 200, "data": [
                    {"c_wsmc": "notice", "c_wjgs": "pdf", "wjlj": "https://signed.example/1"}]},
            }
            args = ["--identity-stdin", "--retry-identity-from", blocked["manifest_path"], "--confirm-receipt"]
            code, result, calls = self.run_cli(
                temporary, args, success, path, input_text=json.dumps({"mobile_last4": "0456"}))
            self.assertEqual(code, 0, result)
            self.assertEqual(result["status"], "downloaded")
            self.assertEqual(result["identity"]["source"], "user_input")
            self.assertEqual(result["identity"]["attempts_used"], 2)
            self.assertEqual(result["receipt"]["status"], "confirmed")
            self.assertEqual(calls, ["getSfhyKg", "checkSdryxx", "updateSdxxBySdzt", "getWsListBySdbhNew"])
            self.assertTrue(Path(result["documents"][0]["file"]).read_bytes().startswith(b"%PDF-"))
            self.assertEqual(path.read_bytes(), before)
            self.assertNotIn("0456", Path(result["manifest_path"]).read_text())

    def test_second_rejection_stops_and_cannot_replay_failed_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            responses = {"getSfhyKg": {"code": 200, "data": True}, "checkSdryxx": {"code": 403, "msg": "手机号后四位不匹配"}}
            answer = json.dumps({"mobile_last4": "0456"})
            code, first, calls = self.run_cli(temporary, ["--identity-stdin"], responses, input_text=answer)
            args = ["--identity-stdin", "--retry-identity-from", first["manifest_path"]]
            code, second, calls = self.run_cli(temporary, args, responses, input_text=answer)
            self.assertEqual(code, 2)
            self.assertEqual(calls, ["getSfhyKg", "checkSdryxx"])
            self.assertEqual(second["identity"]["next_action"], "check_delivery_registration")
            code, replay, calls = self.run_cli(temporary, args, responses, input_text=answer)
            self.assertEqual(calls, [])
            self.assertEqual(replay["identity"]["reason"], "identity_retry_already_used")
            exhausted = ["--identity-stdin", "--retry-identity-from", second["manifest_path"]]
            code, exhausted, calls = self.run_cli(temporary, exhausted, responses, input_text=answer)
            self.assertEqual(calls, [])
            self.assertEqual(exhausted["identity"]["reason"], "identity_attempt_budget_exhausted")

    def test_client_input_can_download_without_creating_any_profile_or_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "absent.json"
            responses = {
                "getSfhyKg": {"code": 200, "data": True}, "checkSdryxx": {"code": 200},
                "getWsListBySdbhNew": {"code": 200, "data": [
                    {"c_wsmc": "notice", "c_wjgs": "pdf", "wjlj": "https://signed.example/1"}]},
            }
            code, result, calls = self.run_cli(
                temporary, ["--identity-stdin"], responses, path,
                input_text=json.dumps({"mobile_last4": "0456"}))
            self.assertEqual(code, 0)
            self.assertEqual(result["receipt"]["status"], "not_requested")
            self.assertNotIn("updateSdxxBySdzt", calls)
            self.assertFalse(path.exists())

    def test_bad_one_time_inputs_stop_before_any_request(self):
        for value in ({"mobile_last4": "12a4"}, {"mobile_last4": 1234}, {"mobile": MOBILE}, []):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temporary:
                code, result, calls = self.run_cli(
                    temporary, ["--identity-stdin"], {}, input_text=json.dumps(value))
                self.assertEqual(code, 2)
                self.assertEqual(result["status"], "error")
                self.assertEqual(calls, [])

    def test_retry_manifest_from_another_delivery_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            responses = {"getSfhyKg": {"code": 200, "data": True}, "checkSdryxx": {"code": 403, "msg": "手机号后四位不匹配"}}
            answer = json.dumps({"mobile_last4": "0456"})
            _, first, _ = self.run_cli(temporary, ["--identity-stdin"], responses, input_text=answer)
            wrong = Path(first["manifest_path"])
            data = json.loads(wrong.read_text())
            data["delivery_fingerprint"] = "wrong-delivery"
            wrong.write_text(json.dumps(data))
            code, result, calls = self.run_cli(
                temporary, ["--identity-stdin", "--retry-identity-from", str(wrong)],
                responses, input_text=answer)
            self.assertEqual(code, 2)
            self.assertEqual(result["reason"], "invalid_identity_retry_manifest")
            self.assertEqual(calls, [])

    def test_copy_of_consumed_manifest_cannot_start_another_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            responses = {"getSfhyKg": {"code": 200, "data": True},
                         "checkSdryxx": {"code": 403, "msg": "手机号后四位不匹配"}}
            answer = json.dumps({"mobile_last4": "0456"})
            _, first, _ = self.run_cli(temporary, ["--identity-stdin"], responses, input_text=answer)
            copied = Path(temporary) / "copy.json"
            copied.write_bytes(Path(first["manifest_path"]).read_bytes())
            self.run_cli(
                temporary, ["--identity-stdin", "--retry-identity-from", first["manifest_path"]],
                responses, input_text=answer)
            code, result, calls = self.run_cli(
                temporary, ["--identity-stdin", "--retry-identity-from", str(copied)],
                responses, input_text=answer)
            self.assertEqual(code, 2)
            self.assertEqual(calls, [])
            self.assertEqual(result["identity"]["reason"], "identity_retry_already_used")


if __name__ == "__main__":
    unittest.main()
