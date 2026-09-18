#!/usr/bin/env python3
"""使用临时合成材料与真实 CLI 子进程验证协议，不联网、不执行 Agent。"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("clerk.py")
ASSETS = SCRIPT.parent.parent / "assets"


class ClerkTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="moot-court-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.run = self.base / "hearing"
        self.cli("init", "--case-type", "civil", "--manifest", ASSETS / "civil-case.example.json")

    def cli(self, *args, fails=False):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--run", str(self.run),
                                 *map(str, args)], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 2 if fails else 0, result.stderr + result.stdout)
        if fails:
            self.assertNotIn("Traceback", result.stderr)
            return json.loads(result.stderr)
        return json.loads(result.stdout)

    def dispatch(self, role="plaintiff", responds=()):
        return self.cli("dispatch", "--role", role, "--stage", "evidence", "--issue", "I-001",
                        "--prompt", "说明依据并回应指定发言", "--respond-to", *responds)

    def submission(self, packet):
        value = copy.deepcopy(packet["submission_template"])
        value.update(body="根据 D-003 签收栏，现有单据未记载签收人；仍需结合其他材料核实。", citations=["D-003"])
        return value

    def save(self, value, name="submission.json"):
        path = self.base / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def commit(self, value, fails=False):
        return self.cli("commit", "--submission", self.save(value), fails=fails)

    def test_real_civil_chain_and_derived_recovery(self):
        previous = []
        for role in ("plaintiff", "defendant", "judge"):
            packet = self.dispatch(role, previous)
            self.assertEqual([h["seq"] for h in packet["history"]], previous)
            result = self.commit(self.submission(packet))
            previous.append(result["accepted_seq"])
        self.cli("close", "--reason", "合成协议样例结束")
        self.cli("render")
        transcript = (self.run / "transcript.md").read_text()
        self.assertIn("E-000003", transcript)
        self.assertIn("defendant", transcript)
        self.assertNotIn("青石", transcript)
        (self.run / "state.json").write_text('{"active":"fake"}')
        self.assertIsNone(self.cli("status")["active"])
        self.cli("render")
        self.assertIsNone(json.loads((self.run / "state.json").read_text())["active"])

    def test_duplicate_is_idempotent_but_changed_body_fails(self):
        submission = self.submission(self.dispatch())
        first = self.commit(submission)
        before = self.cli("status")["last_seq"]
        again = self.commit(submission)
        self.assertTrue(again["duplicate"])
        self.assertEqual(first["accepted_seq"], again["accepted_seq"])
        self.assertEqual(before, self.cli("status")["last_seq"])
        submission["body"] += "更改观点"
        self.commit(submission, fails=True)

    def test_wrong_envelope_rejected_without_advancing(self):
        submission = self.submission(self.dispatch())
        for field, bad in (("role", "defendant"), ("material_version", 0),
                           ("read_through", 999), ("run_id", "other"),
                           ("turn_id", "T-9999"), ("schema_version", True)):
            with self.subTest(field=field):
                changed = dict(submission, **{field: bad})
                self.commit(changed, fails=True)
                self.assertEqual(self.cli("status")["last_seq"], 2)
        self.commit(submission)

    def test_required_response_not_omittable(self):
        seq = self.commit(self.submission(self.dispatch()))["accepted_seq"]
        submission = self.submission(self.dispatch("defendant", [seq]))
        submission["responds_to"] = []
        self.commit(submission, fails=True)
        self.cli("cancel", "--reason", "重新安排")
        self.cli("dispatch", "--role", "judge", "--stage", "questions", "--issue", "I-001",
                 "--prompt", "追问", "--respond-to", 999, fails=True)

    def test_visibility_and_private_citation(self):
        packet = self.dispatch("defendant")
        self.assertNotIn("青石", json.dumps(packet, ensure_ascii=False))
        submission = self.submission(packet)
        submission["citations"] = ["P-001"]
        self.commit(submission, fails=True)
        submission["citations"] = ["missing"]
        self.commit(submission, fails=True)
        self.cli("cancel", "--reason", "切换角色")
        packet = self.dispatch("plaintiff")
        self.assertIn("青石", json.dumps(packet, ensure_ascii=False))

    def test_partial_json_and_empty_body_do_not_commit(self):
        packet = self.dispatch()
        partial = self.base / "partial.json"
        partial.write_text('{"body":')
        self.cli("commit", "--submission", partial, fails=True)
        submission = self.submission(packet)
        submission["body"] = " "
        self.commit(submission, fails=True)
        submission["body"] = "陈述"
        submission["unknown"] = "字段"
        self.commit(submission, fails=True)
        self.assertEqual(self.cli("status")["last_seq"], 2)

    def test_object_citations_rejected_then_corrected_without_new_dispatch(self):
        packet = self.dispatch("judge")
        submission = self.submission(packet)
        submission["citations"] = [{"material_id": "D-003", "locator": "签收栏"}]
        self.commit(submission, fails=True)
        self.assertEqual(self.cli("packet"), packet)
        submission["citations"] = ["D-003"]
        result = self.commit(submission)
        self.assertEqual(result["accepted_seq"], 3)

    def test_cancel_update_and_late_submission(self):
        old = self.submission(self.dispatch())
        self.cli("materials", "--manifest", ASSETS / "civil-case.example.json", fails=True)
        self.cli("cancel", "--reason", "补充材料")
        self.cli("materials", "--manifest", ASSETS / "civil-case.example.json")
        new_packet = self.dispatch()
        self.assertEqual(new_packet["assignment"]["material_version"], 2)
        self.assertEqual(new_packet["assignment"]["turn_id"], "T-0002")
        self.commit(old, fails=True)
        self.commit(self.submission(new_packet))

    def test_single_pending_turn_and_resume_packet(self):
        original = self.dispatch()
        self.cli("dispatch", "--role", "judge", "--issue", "I-001", "--stage", "questions",
                 "--prompt", "追问", fails=True)
        self.assertEqual(self.cli("packet"), original)

    def test_incomplete_close_and_closed_run(self):
        self.cli("close", "--reason", "未执行", fails=True)
        self.dispatch()
        self.cli("close", "--reason", "中止", "--incomplete", fails=True)
        self.cli("cancel", "--reason", "角色超时")
        self.cli("close", "--reason", "运行故障", "--incomplete")
        self.cli("render")
        self.assertIn("不评价实体攻防", (self.run / "transcript.md").read_text())
        self.cli("dispatch", "--role", "judge", "--issue", "I-001", "--stage", "closing",
                 "--prompt", "继续", fails=True)

    def test_criminal_roles_and_turn_budget(self):
        self.run = self.base / "criminal"
        self.cli("init", "--case-type", "criminal", "--manifest", ASSETS / "criminal-case.example.json",
                 "--max-turns", 3)
        self.cli("dispatch", "--role", "plaintiff", "--issue", "I-001", "--stage", "opening",
                 "--prompt", "开庭", fails=True)
        for role in ("prosecution", "defense", "judge"):
            self.commit(self.submission(self.dispatch(role)))
        self.cli("dispatch", "--role", "judge", "--issue", "I-001", "--stage", "closing",
                 "--prompt", "继续", fails=True)
        self.cli("close", "--reason", "协议样例完成")

    def test_corrupt_event_and_number_gap_fail_closed(self):
        path = self.run / "events" / "000001.json"
        original = path.read_text()
        value = json.loads(original)
        value["payload"]["max_turns"] = 999
        path.write_text(json.dumps(value))
        self.cli("status", fails=True)
        path.write_text(original)
        self.dispatch()
        (self.run / "events" / "000002.json").rename(self.run / "events" / "000003.json")
        self.cli("render", fails=True)

    def test_pending_temp_file_ignored_and_init_no_overwrite(self):
        (self.run / "events" / ".pending-synthetic").write_text("partial")
        self.assertEqual(self.cli("status")["last_seq"], 1)
        self.cli("init", "--case-type", "civil", "--manifest", ASSETS / "civil-case.example.json", fails=True)
        self.assertEqual(self.cli("status")["last_seq"], 1)

    def test_bad_manifest_rejected(self):
        self.run = self.base / "invalid"
        for manifest in ({"documents": []}, {"documents": ["bad"]},
                         {"documents": [], "unknown": 1}):
            self.cli("init", "--case-type", "civil", "--manifest", self.save(manifest), fails=True)
            self.assertFalse(self.run.exists())

    def test_competing_dispatches_never_create_two_active_turns(self):
        command = [sys.executable, "-B", str(SCRIPT), "--run", str(self.run), "dispatch",
                   "--role", "judge", "--stage", "questions", "--issue", "I-001", "--prompt", "追问"]
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for _ in range(2)]
        for process in processes:
            process.communicate(timeout=15)
        self.assertEqual(sorted(p.returncode for p in processes), [0, 2])
        state = self.cli("status")
        self.assertEqual(state["turns"], 1)
        self.assertEqual(state["last_seq"], 2)

    def test_duplicate_ids_and_invalid_visibility_rejected(self):
        original = json.loads((ASSETS / "civil-case.example.json").read_text())
        manifest = copy.deepcopy(original)
        manifest["documents"].append(copy.deepcopy(manifest["documents"][0]))
        self.cli("materials", "--manifest", self.save(manifest), fails=True)
        for audience in (["all", "judge"], ["unknown"], [], ["judge", "judge"]):
            manifest = copy.deepcopy(original)
            manifest["documents"][0]["visible_to"] = audience
            self.cli("materials", "--manifest", self.save(manifest), fails=True)
        self.assertEqual(self.cli("status")["material_version"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
