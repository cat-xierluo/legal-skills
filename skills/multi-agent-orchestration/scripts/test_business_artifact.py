#!/usr/bin/env python3
"""Offline real-file/CLI consumers for business artifact delivery and review."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from business_artifact_contract import ArtifactError, MAX_FILE_BYTES, observe_delivery


def business_task() -> dict:
    return {
        "task_id": "REPORT-1", "status": "READY", "kind": "research",
        "value_kind": "business_artifact", "value_identity": "source-backed-business-report",
        "problem_target": "Client's concrete workflow design question", "consumer": "Named project decision owner",
        "decision_or_gate_changed": "Choose the documented workflow from a source-backed comparison",
        "engineering_assets": [], "doc_assets": [], "verification_commands": [],
        "worker_pr_policy": "no_worker_pr", "consume_by": "Current decision meeting",
        "expiry": "Archive if the original request is cancelled", "observable_acceptance": "Independent source and criteria review accepts the actual report",
        "starts_external_resources": False, "resource_owner": "none",
        "business_artifact": {
            "purpose_type": "research_report", "purpose": "Deliver the requested workflow comparison",
            "request_ref": "TASK-CUSTOMER-42 original request", "acceptance_mode": "content_review",
            "sources": [{"source_id": "source-a", "reference": "Named supplied workflow memo, section 2"}],
            "artifacts": [{"path": "report.md", "modality": "text", "media_type": "text/markdown"}],
            "acceptance_criteria": [{"criterion_id": "source-comparison", "standard": "State the comparison and its uncertainty with traceable support",
                                     "artifact_paths": ["report.md"], "source_ids": ["source-a"]}],
        },
    }


class BusinessArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="business-artifact-consumer-")
        self.root = Path(self.temp.name).resolve()
        self.task = business_task()
        (self.root / "report.md").write_text("# Workflow comparison\nSource-a section 2 supports option A. Uncertainty: cost is unmeasured.\n")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def spec(self, tasks=None) -> dict:
        return {"schema_version": "dispatch-value-gate.v2", "mode": "converge", "pending_acceptance_prs": 0, "tasks": tasks or [self.task]}

    def evidence(self) -> dict:
        delivery = observe_delivery(self.task, self.root)
        return {"delivery": delivery,
                "implementation": {"dispatch_id": "author-dispatch", "session_id": "author-session", "author_id": "author-one"},
                "content_review": {"reviewer": {"dispatch_id": "review-dispatch", "session_id": "review-session", "author_id": "reviewer-two"},
                    "verdict": "ACCEPT", "delivery_identity": delivery["identity"], "sources_sha256": delivery["sources_sha256"],
                    "criteria": [{"criterion_id": c["criterion_id"], "verdict": "PASS", "artifact_paths": c["artifact_paths"],
                                  "source_ids": c["source_ids"], "evidence": "Report comparison section cites supplied memo section 2 and states unknown cost"}
                                 for c in self.task["business_artifact"]["acceptance_criteria"]],
                    "source_checks": [{"source_id": s["source_id"], "evidence": "Compared report statements with supplied memo section 2"}
                                      for s in self.task["business_artifact"]["sources"]]},
                "executed": [{"command": c, "exit_code": 0} for c in self.task["verification_commands"]]}

    def review(self, evidence: dict) -> dict:
        return {"schema_version": "review-acceptance-gate.v1", "value_kind": "business_artifact",
                "business_task": self.task, "artifact_root": str(self.root), "business_evidence": evidence,
                "delivery_identity": evidence["delivery"]["identity"], "reviewed_identity": evidence["delivery"]["identity"],
                "implementation": evidence["implementation"], "reviewer": evidence["content_review"]["reviewer"],
                "verdict": "ACCEPT", "review_consumer": "Named decision owner", "review_expiry": "Archive after consumption",
                "blocking_findings": [], "role_exception": None}

    def call(self, script: str, payload: dict, *args: str) -> subprocess.CompletedProcess:
        path = self.root / "contract.json"
        path.write_text(json.dumps(payload))
        return subprocess.run([sys.executable, str(HERE / script), str(path), *args], capture_output=True, text=True, timeout=20)

    def preflight(self, task=None, expected=0) -> None:
        result = self.call("dispatch-value-gate.py", self.spec([task or self.task]))
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def postflight(self, evidence: dict, expected=0, extra=None) -> dict:
        spec = self.root / "spec.json"; spec.write_text(json.dumps(self.spec()))
        record = self.root / "evidence.json"; record.write_text(json.dumps(evidence))
        result = subprocess.run([sys.executable, str(HERE / "worker-value-postflight.py"), "--spec", str(spec), "--task-id", self.task["task_id"],
                                 "--artifact-root", str(self.root), "--evidence", str(record), *(extra or [])], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_non_git_text_and_independent_content_review(self) -> None:
        self.assertFalse((self.root / ".git").exists())
        self.preflight()
        evidence = self.evidence()
        result = self.postflight(evidence)
        self.assertEqual(result["report"]["delivery"], evidence["delivery"])
        review = self.call("review-acceptance-gate.py", self.review(evidence))
        self.assertEqual(review.returncode, 0, review.stdout + review.stderr)
        self.assertNotIn("delivery_head", self.review(evidence))

    def test_git_directory_does_not_require_artifact_commit(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.postflight(self.evidence())
        result = subprocess.run(["git", "-C", str(self.root), "rev-parse", "--verify", "HEAD"], capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_binary_fingerprint_and_modality_mismatch(self) -> None:
        block = self.task["business_artifact"]
        block["artifacts"] = [{"path": "report.pdf", "modality": "binary", "media_type": "application/pdf"}]
        block["acceptance_criteria"][0]["artifact_paths"] = ["report.pdf"]
        (self.root / "report.pdf").write_bytes(b"%PDF-1.7\ncontrolled binary fixture\xff\n")
        self.preflight(); self.postflight(self.evidence())
        (self.root / "report.pdf").write_bytes(b"wrong format")
        with self.assertRaises(ArtifactError): observe_delivery(self.task, self.root)

    def test_generated_office_zip_and_readonly_observation_cli(self) -> None:
        formats = [("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "word/document.xml"),
                   ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation", "ppt/presentation.xml"),
                   ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xl/workbook.xml")]
        for extension, mime, part in formats:
            path = "report." + extension
            with zipfile.ZipFile(self.root / path, "w", zipfile.ZIP_DEFLATED) as package:
                package.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
                package.writestr(part, '<?xml version="1.0"?><fixture>controlled source-based Office package</fixture>')
            self.task["business_artifact"]["artifacts"] = [{"path": path, "modality": "binary", "media_type": mime}]
            self.task["business_artifact"]["acceptance_criteria"][0]["artifact_paths"] = [path]
            self.preflight(); self.postflight(self.evidence())
        spec = self.root / "observation-spec.json"; spec.write_text(json.dumps(self.spec()))
        result = subprocess.run([sys.executable, str(HERE / "business_artifact_contract.py"), "--spec", str(spec),
                                 "--task-id", self.task["task_id"], "--artifact-root", str(self.root)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "observed_draft"); self.assertIs(payload["accepted"], False)
        self.assertEqual(payload["delivery"], self.evidence()["delivery"])
        # ZIP signature is only a bounded container observation, not a claim
        # that an Office application opened the file or its content is correct.

    def test_verifier_requires_real_declared_exit_record(self) -> None:
        self.task["business_artifact"]["acceptance_mode"] = "verifier"
        command = "python3 -c 'from pathlib import Path; assert Path(\"report.md\").read_text().startswith(\"#\")'"
        self.task["verification_commands"] = [command]
        self.preflight()
        result = subprocess.run(["bash", "-c", command], cwd=self.root, capture_output=True)
        self.assertEqual(result.returncode, 0)
        evidence = self.evidence(); evidence["executed"][0]["exit_code"] = result.returncode
        self.postflight(evidence)
        for bad in (1, True, None):
            wrong = copy.deepcopy(evidence); wrong["executed"][0]["exit_code"] = bad
            self.postflight(wrong, 2)

    def test_sources_standards_purpose_and_mixed_scope_rejected(self) -> None:
        for field, value in (("sources", []), ("acceptance_criteria", []), ("request_ref", "tbd"),
                             ("purpose_type", "maintenance"), ("purpose", ""), ("acceptance_mode", "unknown")):
            task = copy.deepcopy(self.task); task["business_artifact"][field] = value
            self.preflight(task, 2)
        task = copy.deepcopy(self.task); task["engineering_assets"] = ["main.py"]
        self.preflight(task, 2)
        task = copy.deepcopy(self.task); task["status"] = "DRAFT"
        self.preflight(task, 2)
        review = self.review(self.evidence()); review["business_task"] = task
        self.assertEqual(self.call("review-acceptance-gate.py", review).returncode, 2)

    def test_duplicate_and_unknown_contract_bindings_rejected(self) -> None:
        for field in ("sources", "artifacts", "acceptance_criteria"):
            task = copy.deepcopy(self.task); task["business_artifact"][field] *= 2
            self.preflight(task, 2)
        task = copy.deepcopy(self.task); task["business_artifact"]["acceptance_criteria"][0]["source_ids"] = ["not-declared"]
        self.preflight(task, 2)

    def test_paths_and_symlinks_and_directories_rejected(self) -> None:
        for path in ("../report.md", "/tmp/report.md", "./report.md", "folder//report.md", "folder/../report.md", "*.md", "a\\report.md"):
            task = copy.deepcopy(self.task); task["business_artifact"]["artifacts"][0]["path"] = path
            task["business_artifact"]["acceptance_criteria"][0]["artifact_paths"] = [path]
            self.preflight(task, 2)
        report = self.root / "report.md"; report.unlink(); report.mkdir()
        with self.assertRaises(ArtifactError): observe_delivery(self.task, self.root)
        report.rmdir(); outside = self.root / "outside.md"; outside.write_text("outside")
        report.symlink_to(outside)
        with self.assertRaises(ArtifactError): observe_delivery(self.task, self.root)
        report.unlink(); folder = self.root / "folder"; folder.symlink_to(self.root, target_is_directory=True)
        self.task["business_artifact"]["artifacts"][0]["path"] = "folder/outside.md"
        self.task["business_artifact"]["acceptance_criteria"][0]["artifact_paths"] = ["folder/outside.md"]
        with self.assertRaises(ArtifactError): observe_delivery(self.task, self.root)

    def test_missing_empty_binary_text_and_oversize_rejected(self) -> None:
        report = self.root / "report.md"
        for data in (b"", b" \n\t", b"bad\x00binary", b"\xff"):
            report.write_bytes(data)
            with self.assertRaises(ArtifactError): observe_delivery(self.task, self.root)
        with report.open("wb") as stream: stream.truncate(MAX_FILE_BYTES + 1)
        with self.assertRaises(ArtifactError): observe_delivery(self.task, self.root)
        report.unlink()
        with self.assertRaises(ArtifactError): observe_delivery(self.task, self.root)

    def test_actual_artifact_tampering_and_contract_source_drift(self) -> None:
        evidence = self.evidence()
        (self.root / "report.md").write_text("Changed report content")
        self.postflight(evidence, 2)
        self.assertEqual(self.call("review-acceptance-gate.py", self.review(evidence)).returncode, 2)
        fresh = self.evidence(); self.task["business_artifact"]["sources"][0]["reference"] = "Another source"
        self.postflight(fresh, 2)
        self.postflight(self.evidence(), 2, ["--delivery-head", "1" * 40])

    def test_self_review_wrong_identity_criteria_and_source_checks(self) -> None:
        evidence = self.evidence()
        for field in ("dispatch_id", "session_id", "author_id"):
            wrong = copy.deepcopy(evidence); wrong["content_review"]["reviewer"][field] = evidence["implementation"][field]
            self.postflight(wrong, 2)
            self.assertEqual(self.call("review-acceptance-gate.py", self.review(wrong)).returncode, 2)
        for field, value in (("delivery_identity", "artifact-sha256:" + "0" * 64), ("sources_sha256", "0" * 64),
                             ("criteria", []), ("source_checks", []), ("verdict", "REJECT")):
            wrong = copy.deepcopy(evidence); wrong["content_review"][field] = value
            self.postflight(wrong, 2)
        for field, value in (("criterion_id", "wrong"), ("source_ids", ["wrong"]), ("artifact_paths", ["wrong.md"]), ("evidence", "tbd")):
            wrong = copy.deepcopy(evidence); wrong["content_review"]["criteria"][0][field] = value
            self.postflight(wrong, 2)
        wrong = copy.deepcopy(evidence); wrong["content_review"]["criteria"] *= 2
        self.postflight(wrong, 2)

    def test_business_research_is_not_maintenance_docs_concurrency(self) -> None:
        other = copy.deepcopy(self.task)
        other.update(task_id="REPORT-2", value_identity="distinct-design-delivery", problem_target="Another concrete design question", kind="docs")
        result = self.call("dispatch-value-gate.py", self.spec([self.task, other]))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for kind in ("docs", "research"):
            task = copy.deepcopy(self.task); task.update(kind=kind, value_kind="implementation", engineering_assets=["report.md"])
            self.preflight(task, 2)

    def test_real_spawn_consumes_content_review_without_unrelated_discovery(self) -> None:
        # Only ancestry inputs/dependency presence are synthetic. The actual
        # spawn entry and its whole-contract/verification consumers execute.
        private = self.root / "bin"; private.mkdir()
        ps = private / "ps"
        ps.write_text("#!" + sys.executable + "\n" +
            "import os,sys\nargs=sys.argv[1:];pid=args[args.index('-p')+1];fmt=args[args.index('-o')+1]\n"
            "root=os.environ['HARNESS_TEST_ROOT_PID']\n"
            "if pid==root: parent='900001'; frame='/opt/codex'\n"
            "elif pid=='900001': parent='1'; frame='/bin/sh'\n"
            "else: raise SystemExit(1)\n"
            "if fmt=='ppid=': print(parent)\n"
            "elif fmt in ('comm=','args='): print(frame)\n"
            "else: raise SystemExit(1)\n")
        ps.chmod(0o700)
        tmux = private / "tmux"; tmux.write_text("#!/bin/sh\nexit 99\n"); tmux.chmod(0o700)
        launcher = self.root / "spawn-fixture.sh"
        launcher.write_text('#!/usr/bin/env bash\nexport HARNESS_TEST_ROOT_PID="$$" HARNESS_TEST_CHAIN=codex,neutral\nbash "$@"\n')
        spec = self.root / "spawn-spec.json"; spec.write_text(json.dumps(self.spec()))
        (self.root / "pyproject.toml").write_text('[project]\nname="unrelated-project"\n')
        (self.root / "tests").mkdir()
        env = dict(os.environ, PATH=str(private) + os.pathsep + os.environ["PATH"],
                   ORCA_CLI_COMMAND="/usr/bin/false", ORCA_CLI_BIN="/usr/bin/false",
                   SPAWN_WORKER_MEM_BUDGET_BYTES="0")
        config = self.root / "personal.json"; config.write_text('{"quota_aware_routing":{"enabled":false}}')
        env["MULTI_AGENT_ORCHESTRATION_PERSONAL_CONFIG"] = str(config)
        result = subprocess.run(["bash", str(launcher), str(HERE / "spawn-worker.sh"), "--project", str(self.root),
                                 "--no-worktree", "--no-orca-mode", "--session", "business-fixture", "--command", "codex",
                                 "--worker-backend", "codex", "--verification-contract", str(spec), "--verification-task-id", "REPORT-1",
                                 "--allow-prompt-only-install-guard", "offline business consumer fixture", "--allow-paths", "report.md", "--dry-run"],
                                cwd=self.root, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("source=dispatch-contract:REPORT-1:content_review required=0 count=0", result.stdout)
        self.assertNotIn("unittest discover", result.stdout)
        self.assertFalse((self.root / ".claude/agent-sessions/business-fixture").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
