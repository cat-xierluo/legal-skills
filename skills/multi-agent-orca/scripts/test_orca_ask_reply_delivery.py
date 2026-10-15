#!/usr/bin/env python3
"""Stateful fake-Orca regression for PM FIFO Delivery and reply receipts."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parent
FAKE_ORCA = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path

root = Path(os.environ["ASK_REPLY_FIXTURE"])
args = sys.argv[1:]
with (root / "calls.jsonl").open("a") as stream:
    stream.write(json.dumps(args) + "\n")
state_path = root / "state.json"
state = json.loads(state_path.read_text())

def parse(valued=(), switches=("--json",), required=()):
    result = {}
    tail = args[2:]
    while tail:
        key, *tail = tail
        if key in result:
            raise SystemExit(94)
        if key in switches:
            result[key] = True
        elif key in valued and tail:
            result[key], *tail = tail
        else:
            raise SystemExit(95)
    if any(key not in result for key in required):
        raise SystemExit(96)
    return result

command = tuple(args[:2])
runtime = "runtime-ask-reply"
response = {"ok": True, "result": {}, "_meta": {"runtimeId": runtime}}
if args == ["status", "--json"]:
    response["result"] = {"runtime": {"reachable": True, "runtimeId": runtime}}
elif command == ("terminal", "show"):
    flags = parse(("--terminal",), required=("--terminal", "--json"))
    response["result"] = {"terminal": {"handle": flags["--terminal"], "connected": True,
                                         "writable": True, "orphaned": False, "exitCause": None}}
elif command == ("orchestration", "run-use"):
    flags = parse(("--id", "--from"), required=("--id", "--from", "--json"))
    if flags["--id"] != "run-ask-reply":
        raise SystemExit(97)
    state["coordinator"] = flags["--from"]
    state_path.write_text(json.dumps(state))
    response["result"] = {"run": {"id": "run-ask-reply", "coordinator_handle": flags["--from"]}}
elif command == ("orchestration", "run-current"):
    flags = parse(("--from",), required=("--from", "--json"))
    response["result"] = {"run": {"id": "run-ask-reply", "coordinator_handle": flags["--from"]}}
elif command == ("orchestration", "worker-show"):
    flags = parse(("--dispatch",), required=("--dispatch", "--json"))
    response["result"] = {
        "dispatch": {"id": "ctx-worker", "task_id": "task-worker",
                     "run_id": "run-ask-reply", "assignee_handle": "term-worker",
                     "status": "dispatched"},
        "worker": {"dispatch_id": "ctx-worker", "agent_terminal_handle": "term-worker",
                   "state": "active"},
    }
elif command == ("orchestration", "check"):
    flags = parse(("--types", "--timeout-ms", "--terminal", "--ack"),
                  switches=("--wait", "--json"), required=("--terminal", "--json"))
    if "--ack" in flags:
        requested = flags["--ack"]
        acknowledged = requested if requested == "delivery-1" else "different-delivery"
        if requested == "delivery-1":
            state["first_acked"] = True
            state_path.write_text(json.dumps(state))
        messages = json.loads((root / "messages.json").read_text())
        batch = messages[50:] if requested == "delivery-1" else messages[:50]
        delivery = "delivery-2" if batch else None
        if state.get("ack_reuses_delivery_id") and batch:
            delivery = requested
        if state.get("ack_bad_message_run_alias") and batch:
            batch[0] = {**batch[0], "runId": state["ack_bad_message_run_alias"]}
        response["result"] = {"runId": state.get("check_run", "run-ask-reply"),
                              "acknowledged": acknowledged, "deliveryId": delivery,
                              "count": len(batch), "messages": batch}
        if state.get("ack_invalid_batch"):
            response["result"].update({"deliveryId": 17, "count": 2, "messages": []})
        if state.get("ack_missing_delivery"):
            response["result"].pop("deliveryId", None)
        if "check_run_alias" in state:
            response["result"]["run_id"] = state["check_run_alias"]
    else:
        messages = json.loads((root / "messages.json").read_text())
        if state.get("overflow"):
            batch, delivery = messages, "delivery-overflow"
        elif state.get("first_acked"):
            batch, delivery = messages[50:], "delivery-2"
        else:
            batch, delivery = messages[:50], "delivery-1"
        if not batch:
            delivery = None
        if "bad_message_id" in state and batch:
            batch[0] = {**batch[0], "id": state["bad_message_id"]}
        if "bad_message_run" in state and batch:
            batch[0] = {**batch[0], "run_id": state["bad_message_run"]}
        if "bad_message_run_alias" in state and batch:
            batch[0] = {**batch[0], "runId": state["bad_message_run_alias"]}
        if "bad_delivery_id" in state:
            delivery = state["bad_delivery_id"]
        response["result"] = {"runId": state.get("check_run", "run-ask-reply"),
                              "deliveryId": delivery, "count": len(batch), "messages": batch}
        if state.get("check_missing_delivery"):
            response["result"].pop("deliveryId", None)
        if "check_run_alias" in state:
            response["result"]["run_id"] = state["check_run_alias"]
elif command == ("orchestration", "reply"):
    flags = parse(("--id", "--body", "--from", "--retry-request"),
                  required=("--id", "--body", "--from", "--json"))
    target = flags["--id"]
    attempt = flags.get("--retry-request", "")
    request = {"target": target, "body": flags["--body"], "from": flags["--from"]}
    prior = state.setdefault("replies", {}).get(target)
    if not prior:
        prior = {"attempt": attempt, "request": request, "reply_id": "reply-" + target}
        state["replies"][target] = prior
        state_path.write_text(json.dumps(state))
    response["result"] = {
        "message": {"id": (target if state.get("reply_reuses_question_id") else prior["reply_id"]),
                    "run_id": "run-ask-reply",
                    "from_handle": "run:run-ask-reply",
                    "to_handle": ("dispatch:ctx-other" if state.get("reply_route_conflict")
                                  else "dispatch:ctx-worker"),
                    "thread_id": target, "body": prior["request"]["body"]},
        "question": {"message_id": target, "run_id": "run-ask-reply",
                     "dispatch_id": "ctx-worker", "asker_handle": "term-worker",
                     "status": "answered",
                     "answer_message_id": (target if state.get("reply_reuses_question_id")
                                           else prior["reply_id"]),
                     "answer_body": prior["request"]["body"]},
        "duplicate": prior["request"] != request or prior["attempt"] != attempt,
    }
    if state.get("reply_null_asker_alias"):
        response["result"]["question"]["askerHandle"] = None
else:
    raise SystemExit(98)
print(json.dumps(response))
'''


class AskReplyDeliveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mao-ask-reply-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.fake = self.root / "orca"
        self.fake.write_text(FAKE_ORCA)
        self.fake.chmod(0o700)
        self.state = self.root / "state.json"
        self.state.write_text(json.dumps({"first_acked": False, "coordinator": "term-pm", "replies": {}}))
        messages = []
        kinds = ["question", "escalation", "worker_done"] + ["status"] * 48
        for index, kind in enumerate(kinds, start=1):
            message_id = f"message-{index:02d}"
            messages.append({"id": message_id, "type": kind,
                             "run_id": "run-ask-reply",
                             "from_handle": "dispatch:ctx-worker",
                             "to_handle": "run:run-ask-reply",
                             "thread_id": message_id,
                             "payload": json.dumps({"taskId": "task-worker",
                                                    "dispatchId": "ctx-worker",
                                                    "question": kind,
                                                    "options": []}),
                             "subject": kind})
        (self.root / "messages.json").write_text(json.dumps(messages))
        (self.root / "calls.jsonl").touch()
        metadata = self.root / ".claude/agent-sessions/worker/METADATA.json"
        metadata.parent.mkdir(parents=True)
        metadata.write_text(json.dumps({
            "session": {"orca": {"runtime_id": "runtime-ask-reply", "terminal_handle": "term-worker",
                                  "supervised": {"run_id": "run-ask-reply",
                                                 "coordinator_handle": "term-pm",
                                                 "task_id": "task-worker",
                                                 "dispatch_id": "ctx-worker"}}}
        }))
        self.env = dict(os.environ, ORCA_CLI_COMMAND=str(self.fake), ASK_REPLY_FIXTURE=str(self.root))

    def pm(self, command, *args, expected=0):
        completed = subprocess.run(
            ["bash", str(SCRIPTS / "pm-orchestrate.sh"), command,
             "--worktree", str(self.root), "--session", "worker", *args],
            cwd=self.root, env=self.env, text=True, capture_output=True, timeout=20,
        )
        diagnostic = f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        if expected == "nonzero":
            self.assertNotEqual(completed.returncode, 0, diagnostic)
        else:
            self.assertEqual(completed.returncode, expected, diagnostic)
        return completed

    def wait(self):
        return json.loads(self.pm("wait", "--timeout", "1").stdout)

    def test_oldest_fifty_replay_until_ack_then_next_batch(self):
        first = self.wait()
        replay = self.wait()
        self.assertEqual(first["result"]["deliveryId"], "delivery-1")
        self.assertEqual(first["result"]["messages"], replay["result"]["messages"])
        receipt = first["mao_delivery_receipt"]
        self.assertEqual(receipt["message_count"], 50)
        self.assertEqual(receipt["ordered_messages"][0]["required_action"], "reply_required")
        self.assertEqual(receipt["ordered_messages"][1]["required_action"], "intervention_required")
        self.assertEqual(receipt["ordered_messages"][2]["required_action"],
                         "validate_and_account_terminal")
        self.assertFalse(receipt["acknowledged"])
        ack = json.loads(self.pm("ack", "--delivery-id", "delivery-1").stdout)
        self.assertEqual(ack["mao_delivery_receipt"]["state"], "delivery_acknowledged")
        self.assertEqual(ack["mao_delivery_receipt"]["next_delivery_id"], "delivery-2")
        self.assertEqual(ack["mao_delivery_receipt"]["next_message_count"], 1)
        self.assertEqual(ack["mao_delivery_receipt"]["next_ordered_messages"][0]["message_id"],
                         "message-51")
        self.assertIn("all_messages_processed", ack["mao_delivery_receipt"]["does_not_prove"])
        second = self.wait()
        self.assertEqual(second["result"]["deliveryId"], "delivery-2")
        self.assertEqual([row["id"] for row in second["result"]["messages"]], ["message-51"])

    def test_ack_requires_exact_positive_native_receipt(self):
        result = self.pm("ack", "--delivery-id", "delivery-wrong", expected="nonzero")
        self.assertIn("PM_DELIVERY_ACK_NOT_VERIFIED", result.stderr)

    def test_wait_and_ack_reject_run_or_id_drift(self):
        state = json.loads(self.state.read_text())
        state["check_run"] = "run-other"
        self.state.write_text(json.dumps(state))
        self.assertIn("PM_DELIVERY_RECEIPT_INVALID",
                      self.pm("wait", "--timeout", "1", expected="nonzero").stderr)
        self.assertIn("PM_DELIVERY_ACK_NOT_VERIFIED",
                      self.pm("ack", "--delivery-id", "delivery-1", expected="nonzero").stderr)

        state["check_run"] = "run-ask-reply"
        state["bad_delivery_id"] = 17
        self.state.write_text(json.dumps(state))
        self.assertIn("PM_DELIVERY_RECEIPT_INVALID",
                      self.pm("wait", "--timeout", "1", expected="nonzero").stderr)

        state.pop("bad_delivery_id")
        state["bad_message_id"] = ""
        self.state.write_text(json.dumps(state))
        self.assertIn("PM_DELIVERY_RECEIPT_INVALID",
                      self.pm("wait", "--timeout", "1", expected="nonzero").stderr)

        state["bad_message_id"] = 17
        self.state.write_text(json.dumps(state))
        self.assertIn("PM_DELIVERY_RECEIPT_INVALID",
                      self.pm("wait", "--timeout", "1", expected="nonzero").stderr)

        state.pop("bad_message_id")
        state["bad_message_run"] = "run-other"
        self.state.write_text(json.dumps(state))
        self.assertIn("PM_DELIVERY_RECEIPT_INVALID",
                      self.pm("wait", "--timeout", "1", expected="nonzero").stderr)

        state["bad_message_run"] = "run-ask-reply"
        state["bad_message_run_alias"] = "run-other"
        self.state.write_text(json.dumps(state))
        self.assertIn("PM_DELIVERY_RECEIPT_INVALID",
                      self.pm("wait", "--timeout", "1", expected="nonzero").stderr)

        state.pop("bad_message_run")
        state.pop("bad_message_run_alias")
        state["check_run_alias"] = "run-other"
        self.state.write_text(json.dumps(state))
        self.assertIn("PM_DELIVERY_RECEIPT_INVALID",
                      self.pm("wait", "--timeout", "1", expected="nonzero").stderr)
        self.assertIn("PM_DELIVERY_ACK_NOT_VERIFIED",
                      self.pm("ack", "--delivery-id", "delivery-1", expected="nonzero").stderr)

    def test_empty_batch_requires_explicit_null_delivery_id(self):
        (self.root / "messages.json").write_text("[]")
        valid = self.wait()
        self.assertIsNone(valid["mao_delivery_receipt"]["delivery_id"])

        state = json.loads(self.state.read_text())
        state["bad_delivery_id"] = "delivery-empty"
        self.state.write_text(json.dumps(state))
        result = self.pm("wait", "--timeout", "1", expected="nonzero")
        self.assertIn("PM_DELIVERY_RECEIPT_INVALID", result.stderr)

        state.pop("bad_delivery_id")
        state["check_missing_delivery"] = True
        self.state.write_text(json.dumps(state))
        result = self.pm("wait", "--timeout", "1", expected="nonzero")
        self.assertIn("PM_DELIVERY_RECEIPT_INVALID", result.stderr)

    def test_ack_validates_the_complete_next_delivery(self):
        state = json.loads(self.state.read_text())
        state["ack_invalid_batch"] = True
        self.state.write_text(json.dumps(state))
        result = self.pm("ack", "--delivery-id", "delivery-1", expected="nonzero")
        self.assertIn("PM_DELIVERY_ACK_NOT_VERIFIED", result.stderr)

        state.pop("ack_invalid_batch")
        state["ack_bad_message_run_alias"] = "run-other"
        self.state.write_text(json.dumps(state))
        result = self.pm("ack", "--delivery-id", "delivery-1", expected="nonzero")
        self.assertIn("PM_DELIVERY_ACK_NOT_VERIFIED", result.stderr)

        state.pop("ack_bad_message_run_alias")
        state["ack_reuses_delivery_id"] = True
        self.state.write_text(json.dumps(state))
        result = self.pm("ack", "--delivery-id", "delivery-1", expected="nonzero")
        self.assertIn("PM_DELIVERY_ACK_NOT_VERIFIED", result.stderr)

        state.pop("ack_reuses_delivery_id")
        state["ack_missing_delivery"] = True
        self.state.write_text(json.dumps(state))
        result = self.pm("ack", "--delivery-id", "delivery-1", expected="nonzero")
        self.assertIn("PM_DELIVERY_ACK_NOT_VERIFIED", result.stderr)

    def test_duplicate_same_answer_is_explicit_and_changed_answer_fails_closed(self):
        args = ("--message-id", "message-01", "--text", "Use option A",
                "--retry-request", "11111111-1111-4111-8111-111111111111")
        first = json.loads(self.pm("reply", *args).stdout)
        replay = json.loads(self.pm("reply", *args).stdout)
        self.assertEqual(first["mao_reply_receipt"], replay["mao_reply_receipt"])
        self.assertEqual(first["mao_reply_receipt"]["state"], "reply_committed")
        self.assertEqual(first["mao_reply_receipt"]["source_delivery_id"], "delivery-1")
        self.assertIn("worker_consumed_reply", first["mao_reply_receipt"]["does_not_prove"])
        duplicate = json.loads(self.pm("reply", "--message-id", "message-01", "--text", "Use option A",
                                       "--retry-request", "22222222-2222-4222-8222-222222222222").stdout)
        self.assertEqual(duplicate["mao_reply_receipt"]["state"], "reply_existing_same_answer")
        self.assertTrue(duplicate["mao_reply_receipt"]["duplicate"])
        changed = self.pm("reply", "--message-id", "message-01", "--text", "Use option B",
                          expected="nonzero")
        self.assertIn("PM_REPLY_RECEIPT_INVALID", changed.stderr)

    def test_reply_rejects_other_dispatch_target_and_conflicting_native_route(self):
        messages = json.loads((self.root / "messages.json").read_text())
        messages.insert(0, {"id": "other-question", "type": "question",
                            "run_id": "run-ask-reply",
                            "from_handle": "dispatch:ctx-other",
                            "to_handle": "run:run-ask-reply",
                            "thread_id": "other-question",
                            "payload": json.dumps({"taskId": "task-other",
                                                   "dispatchId": "ctx-other",
                                                   "question": "Other?", "options": []})})
        (self.root / "messages.json").write_text(json.dumps(messages))
        result = self.pm("reply", "--message-id", "other-question", "--text", "No",
                         expected="nonzero")
        self.assertIn("PM_REPLY_TARGET_INVALID", result.stderr)
        calls = [json.loads(line) for line in (self.root / "calls.jsonl").read_text().splitlines()]
        self.assertFalse(any(call[:2] == ["orchestration", "reply"] for call in calls))

        state = json.loads(self.state.read_text())
        state["reply_route_conflict"] = True
        self.state.write_text(json.dumps(state))
        result = self.pm("reply", "--message-id", "message-01", "--text", "Use option A",
                         expected="nonzero")
        self.assertIn("PM_REPLY_RECEIPT_INVALID", result.stderr)

    def test_reply_receipt_rejects_null_alias_and_reused_question_id(self):
        state = json.loads(self.state.read_text())
        state["reply_null_asker_alias"] = True
        self.state.write_text(json.dumps(state))
        result = self.pm("reply", "--message-id", "message-01", "--text", "Use option A",
                         expected="nonzero")
        self.assertIn("PM_REPLY_RECEIPT_INVALID", result.stderr)

        state.pop("reply_null_asker_alias")
        state["reply_reuses_question_id"] = True
        self.state.write_text(json.dumps(state))
        result = self.pm("reply", "--message-id", "message-01", "--text", "Use option A",
                         expected="nonzero")
        self.assertIn("PM_REPLY_RECEIPT_INVALID", result.stderr)

    def test_runtime_batch_over_fifty_fails_closed(self):
        state = json.loads(self.state.read_text())
        state["overflow"] = True
        self.state.write_text(json.dumps(state))
        result = self.pm("wait", "--timeout", "1", expected="nonzero")
        self.assertIn("PM_DELIVERY_RECEIPT_INVALID", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
