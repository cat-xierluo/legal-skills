#!/usr/bin/env python3
"""presubmit_check.py 回归：真实阻断、误伤边界、输入错误与报告不泄露。"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("presubmit_check.py")
ASSIGNMENT = {
    "schema_version": 1, "run_id": "synthetic-run", "turn_id": "T-0002",
    "role": "plaintiff", "material_version": 1, "read_through": 1, "responds_to": [],
}

DOCUMENTS = [
    {
        "id": "D-001",
        "title": "合同摘录",
        "locator": "合同第3.1条",
        "text": "开发费总额30万元，验收以双方签署《项目验收确认单》为准。",
        "visible_to": ["all"],
    },
    {
        "id": "D-002",
        "title": "确认邮件",
        "locator": "邮件",
        "text": "甲公司回复：我方已接收测试版本并投入生产环境使用三个月。",
        "visible_to": ["all"],
    },
    {
        "id": "P-001",
        "title": "乙公司内部UAT测试笔记",
        "locator": "内部笔记",
        "text": "内部UAT清单42项通过，3项为非致命界面问题；未取得甲公司签署。",
        "visible_to": ["plaintiff"],
    },
    {
        "id": "K-001",
        "title": "运维台账",
        "locator": "台账",
        "text": "尾款结算表显示已扣减8万元质保金，实际应付22万元。",
        "visible_to": ["defendant"],
    },
    {
        "id": "S-001",
        "title": "双方庭前程序约定",
        "locator": "程序",
        "text": "双方同意就验收争议先行调解，调解记录不入卷。",
        "visible_to": ["plaintiff", "defendant"],
    },
]


def make_policy(documents, rules):
    manifest = {"documents": documents}
    digest = hashlib.sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"schema": "moot-court-private-terms-v1",
            "manifest_sha256": digest, "rules": rules}


def run_check(body, *, documents=None, citations=None, submission=None, manifest=None,
              packet=None, run=None, extra_args=(), json_output=True, policy=None):
    documents = DOCUMENTS if documents is None else documents
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        packet_path = tmp / "packet.json"
        manifest_path = tmp / "manifest.json"
        submission_path = tmp / "submission.json"
        packet_path.write_text(json.dumps(packet if packet is not None else {
            "assignment": ASSIGNMENT,
            "documents": [doc for doc in documents
                          if doc["visible_to"] == ["all"] or "plaintiff" in doc["visible_to"]],
        }, ensure_ascii=False), encoding="utf-8")
        manifest_path.write_text(json.dumps(manifest if manifest is not None else {"documents": documents},
                                            ensure_ascii=False), encoding="utf-8")
        submission_path.write_text(json.dumps(submission if submission is not None else {
            **ASSIGNMENT,
            "body": body,
            "citations": citations if citations is not None else ["D-001"],
        }, ensure_ascii=False), encoding="utf-8")
        policy_args = []
        if policy is not None:
            policy_path = tmp / "private-secret-policy.json"
            policy_path.write_text(policy if isinstance(policy, str) else json.dumps(
                policy, ensure_ascii=False), encoding="utf-8")
            policy_args = ["--private-terms", str(policy_path)]
        before = {path: path.read_bytes() for path in tmp.iterdir()}
        proc = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--packet", str(packet_path),
             "--manifest", str(manifest_path), "--submission", str(submission_path),
             *(["--json"] if json_output else []),
             *(["--run", str(run)] if run else []), *policy_args, *extra_args],
            capture_output=True, text=True)
        assert all(path.read_bytes() == content for path, content in before.items())
        payload = (json.loads(proc.stdout) if json_output and proc.stdout.strip() else None)
        return proc, payload


def make_run(tmp, documents, name="hearing"):
    """通过真实书记员 CLI 初始化运行。"""
    run = tmp / name
    manifest = tmp / "materials.json"
    manifest.write_text(json.dumps({"documents": documents}, ensure_ascii=False), encoding="utf-8")
    clerk_json(run, "init", "--case-type", "civil", "--manifest", str(manifest),
               "--max-turns", "4")
    return run


def clerk_json(run, *args):
    proc = subprocess.run([sys.executable, "-B", str(Path(__file__).with_name("clerk.py")),
                           "--run", str(run), *args],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def dispatch(run):
    return clerk_json(run, "dispatch", "--role", "plaintiff",
                      "--issue", "合成", "--stage", "opening", "--prompt", "合成")


def submission_for(packet, body, citations=None):
    return {
        **packet["submission_template"],
        "body": body,
        "citations": ["D-001"] if citations is None else citations,
    }


def file_snapshot(root):
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in root.rglob("*") if path.is_file()}


class PresubmitCheckTest(unittest.TestCase):
    def test_private_terms_synthetic_escape_and_safe_overview(self):
        documents = json.loads(json.dumps(DOCUMENTS, ensure_ascii=False))
        documents[2]["text"] = ("拟核实运输人员能否作证，尚未取得证言。内部核对标识：青石。"
                                "不得把拟取证事项描述为已有证据。")
        policy = make_policy(documents, [
            {"material_id": "P-001", "terms": ["运输环节人员", "尚未取得证言"]},
            {"material_id": "K-001", "terms": ["对方私有线索"]},
        ])
        escaped = "运输环节人员对设备送达与交接过程的证明。该线索尚未取得证言，未入卷"
        proc, out = run_check(escaped, documents=documents)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(out["private_terms_binding"]["status"], "NOT_PROVIDED")
        proc, out = run_check(escaped, documents=documents, policy=policy)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertEqual([f["rule"] for f in out["findings"]].count("MC-PRIVATE-TERM"), 2)
        self.assertEqual(out["private_terms_binding"]["status"], "MANIFEST_BOUND")
        self.assertEqual(out["private_terms_binding"]["rule_count"], 2)
        self.assertEqual(out["private_terms_binding"]["policy_sha256"], hashlib.sha256(
            json.dumps(policy, ensure_ascii=False).encode("utf-8")).hexdigest())
        for secret in ("P-001", "K-001", "运输环节人员", "尚未取得证言",
                       "青石", "private-secret-policy", escaped):
            self.assertNotIn(secret, proc.stdout + proc.stderr)
        proc, out = run_check("拟就有关人员是否知情申请调查，相关情况有待核实。",
                              documents=documents, policy=policy)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc, out = run_check("该事项涉及对方 私有线索。", documents=documents, policy=policy)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("private_doc_2", proc.stdout)
        self.assertIn("MC-PRIVATE-TERM", [item["rule"] for item in out["findings"]])

    def test_private_terms_public_text_exception_and_nontext_fields(self):
        documents = json.loads(json.dumps(DOCUMENTS, ensure_ascii=False))
        documents[0]["text"] += "公开词项已经披露。"
        documents[0]["title"] = "标题专有词项"
        policy = make_policy(documents, [{"material_id": "P-001",
                                          "terms": ["公开词项", "标题专有词项"]}])
        proc, _ = run_check("公开词项", documents=documents, policy=policy)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc, out = run_check("标题专有词项", documents=documents, policy=policy)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("MC-PRIVATE-TERM", [f["rule"] for f in out["findings"]])

    def test_private_terms_findings_are_limited_per_material(self):
        terms = [f"秘密词{mark}" for mark in "一二三四五六"]
        policy = make_policy(DOCUMENTS, [
            {"material_id": "P-001", "terms": terms},
            {"material_id": "K-001", "terms": [f"对方词{mark}" for mark in "一二三四五六"]},
        ])
        body = "".join(terms + [f"对方词{mark}" for mark in "一二三四五六"])
        proc, out = run_check(body, policy=policy)
        self.assertEqual(proc.returncode, 1)
        hits = [finding for finding in out["findings"] if finding["rule"] == "MC-PRIVATE-TERM"]
        self.assertEqual(len(hits), 10)
        self.assertEqual(sum("private_doc_1" in finding["detail"] for finding in hits), 5)
        self.assertEqual(sum("private_doc_2" in finding["detail"] for finding in hits), 5)
        self.assertIn("每组私有材料的词项命中最多列示5条", out["note"])
        for term in terms:
            self.assertNotIn(term, proc.stdout + proc.stderr)

    def test_private_terms_invalid_policies_are_redacted(self):
        good = make_policy(DOCUMENTS, [{"material_id": "P-001", "terms": ["敏感秘密词项"]}])
        cases = [
            {**good, "manifest_sha256": "0" * 64},
            {**good, "extra-secret": "敏感秘密词项"},
            {**good, "schema": []},
            {**good, "rules": {}},
            {**good, "rules": [{"material_id": "UNKNOWN-SECRET", "terms": ["敏感秘密词项"]}]},
            {**good, "rules": [{"material_id": "D-001", "terms": ["敏感秘密词项"]}]},
            {**good, "rules": [{"material_id": "P-001", "terms": []}]},
            {**good, "rules": [{"material_id": "P-001", "terms": [4]}]},
            {**good, "rules": [{"material_id": "P-001", "terms": ["短词"]}]},
            {**good, "rules": [{"material_id": "P-001", "terms": ["长" * 257]}]},
            {**good, "rules": [{"material_id": "P-001", "terms": ["敏感秘密词项", "敏感 秘密词项"]}]},
            {**good, "rules": good["rules"] * 2},
            {**good, "rules": [{**good["rules"][0], "extra": 1}]},
            '{"schema":"敏感秘密词项","schema":"重复","rules":[]}',
            json.dumps(good, ensure_ascii=False).replace('"terms":', '"terms":[],"terms":'),
            '{坏 JSON 敏感秘密词项',
        ]
        for policy in cases:
            with self.subTest(policy=policy):
                proc, _ = run_check("普通公开说明。", policy=policy)
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                for secret in ("P-001", "UNKNOWN-SECRET", "敏感秘密词项",
                               "private-secret-policy", "Traceback"):
                    self.assertNotIn(secret, proc.stdout + proc.stderr)

    def test_private_terms_text_output_and_missing_file_redacted(self):
        policy = make_policy(DOCUMENTS, [{"material_id": "P-001", "terms": ["敏感秘密词项"]}])
        proc, _ = run_check("敏感秘密词项", policy=policy, json_output=False)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("私有词项策略：MANIFEST_BOUND", proc.stdout)
        self.assertIn("策略文件 SHA-256：", proc.stdout)
        self.assertIn("规则数量：1", proc.stdout)
        self.assertNotIn("敏感秘密词项", proc.stdout + proc.stderr)
        proc, _ = run_check("普通公开说明。", extra_args=(
            "--private-terms", "/不存在/私有策略路径.json"))
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("私有策略路径", proc.stderr)

    def test_run_binding_accepts_current_and_rejects_stale_or_leaky_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            documents = json.loads(json.dumps(DOCUMENTS, ensure_ascii=False))
            run = make_run(tmp, documents)
            packet = dispatch(run)
            submission = submission_for(packet, "原告请求给付30万元，依据 D-001 的约定。")
            proc, out = run_check("", documents=documents, packet=packet,
                                  submission=submission, run=run)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue(out["ok"])
            self.assertEqual(out["manifest_binding"]["status"], "RUN_BOUND_PREFIX_ONLY")
            self.assertEqual(out["manifest_binding"]["event_chain_scope"], "VALIDATED_PREFIX")
            self.assertEqual(out["manifest_binding"]["tail_anchor"], "NOT_AVAILABLE")
            expected_sha = hashlib.sha256(json.dumps(
                {"documents": documents}, ensure_ascii=False, sort_keys=True,
                separators=(",", ":")).encode("utf-8")).hexdigest()
            self.assertEqual(out["manifest_binding"]["manifest_sha256"], expected_sha)
            self.assertEqual(out["manifest_binding"]["observed_event_seq"], 2)
            # 两种清单保持本角色可见子集相同，只改动或漏掉他方材料。
            changed = json.loads(json.dumps(documents, ensure_ascii=False))
            changed[3]["text"] = "已删除。"
            for leaky in (changed, documents[:3] + documents[4:]):
                with self.subTest(documents=len(leaky)):
                    proc, _ = run_check("", documents=leaky, packet=packet,
                                        submission=submission, run=run)
                    self.assertEqual(proc.returncode, 2)
                    self.assertIn("当前材料不一致", proc.stderr)
                    self.assertNotIn("Traceback", proc.stderr)

    def test_run_binding_rejects_after_materials_version_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            documents = json.loads(json.dumps(DOCUMENTS, ensure_ascii=False))
            run = make_run(tmp, documents)
            updated = json.loads(json.dumps(documents, ensure_ascii=False))
            updated[0]["text"] += "双方确认适用第159条。"
            manifest = tmp / "materials-v2.json"
            manifest.write_text(json.dumps({"documents": updated}, ensure_ascii=False),
                                encoding="utf-8")
            old_packet = dispatch(run)
            old_submission = submission_for(old_packet, "原告请求。")
            clerk_json(run, "cancel", "--reason", "合成回合结束，更新材料版本")
            clerk_json(run, "materials", "--manifest", str(manifest))
            new_packet = dispatch(run)
            new_submission = submission_for(new_packet, "原告请求。")

            proc, _ = run_check("", documents=documents, packet=old_packet,
                                submission=old_submission, run=run)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("当前材料不一致", proc.stderr)
            proc, _ = run_check("", documents=updated, packet=old_packet,
                                submission=old_submission, run=run)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("当前派发不一致", proc.stderr)
            proc, out = run_check(
                "", documents=updated, packet=new_packet, submission=new_submission, run=run)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue(out["ok"])

    def test_run_binding_rejects_packet_from_another_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            documents = json.loads(json.dumps(DOCUMENTS, ensure_ascii=False))
            first_run = make_run(tmp, documents, name="hearing-a")
            second_run = make_run(tmp, documents, name="hearing-b")
            first_packet = dispatch(first_run)
            dispatch(second_run)
            submission = submission_for(first_packet, "原告请求。")
            proc, _ = run_check("", documents=documents, packet=first_packet,
                                submission=submission, run=second_run)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("当前派发不一致", proc.stderr)

    def test_run_binding_rejects_corrupt_event_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            documents = json.loads(json.dumps(DOCUMENTS, ensure_ascii=False))
            run = make_run(tmp, documents)
            packet = dispatch(run)
            submission = submission_for(packet, "原告请求。")
            event_path = run / "events" / "000002.json"
            event_path.write_text(event_path.read_text(encoding="utf-8").replace(
                '"plaintiff"', '"defendant"'), encoding="utf-8")
            proc, _ = run_check("", documents=documents, packet=packet,
                                submission=submission, run=run)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("记录校验失败", proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)

    def test_run_binding_reports_missing_events_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            run = tmp / "broken"
            run.mkdir()
            proc, _ = run_check("原告请求。", run=run)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("庭审记录", proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)
            run2 = tmp / "empty-events"
            (run2 / "events").mkdir(parents=True)
            proc, _ = run_check("原告请求。", run=run2)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("init", proc.stderr)

    def test_run_binding_rejects_deleted_tail_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            documents = json.loads(json.dumps(DOCUMENTS, ensure_ascii=False))
            run = make_run(tmp, documents)
            packet = dispatch(run)
            submission = submission_for(packet, "原告请求。")
            (run / "events" / "000002.json").unlink()
            proc, _ = run_check("", documents=documents, packet=packet,
                                submission=submission, run=run)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("没有待处理派发", proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)

    def test_tail_truncation_limit_is_explicit(self):
        for tail in ("cancel", "speech", "materials"):
            with self.subTest(tail=tail), tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                documents = json.loads(json.dumps(DOCUMENTS, ensure_ascii=False))
                run = make_run(tmp, documents)
                packet = dispatch(run)
                submission = submission_for(packet, "原告请求。")
                if tail == "speech":
                    path = tmp / "draft.json"
                    path.write_text(json.dumps(submission), encoding="utf-8")
                    clerk_json(run, "commit", "--submission", str(path))
                else:
                    clerk_json(run, "cancel", "--reason", "合成取消")
                if tail == "materials":
                    updated = json.loads(json.dumps(documents))
                    updated[3]["text"] += "新版本合成事项。"
                    path = tmp / "v2.json"
                    path.write_text(json.dumps({"documents": updated}), encoding="utf-8")
                    clerk_json(run, "materials", "--manifest", str(path))
                    (run / "events" / "000004.json").unlink()
                (run / "events" / "000003.json").unlink()
                proc, out = run_check("", documents=documents, packet=packet,
                                      submission=submission, run=run)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertEqual(out["manifest_binding"]["status"], "RUN_BOUND_PREFIX_ONLY")
                self.assertEqual(out["manifest_binding"]["tail_anchor"], "NOT_AVAILABLE")
                self.assertIn("不能发现尾部事件", out["note"])

    def test_cancelled_committed_and_closed_runs_reject_old_packet(self):
        for terminal in ("cancel", "speech", "close"):
            with self.subTest(terminal=terminal), tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                run = make_run(tmp, DOCUMENTS)
                packet = dispatch(run)
                submission = submission_for(packet, "原告请求。")
                if terminal == "speech":
                    path = tmp / "draft.json"
                    path.write_text(json.dumps(submission), encoding="utf-8")
                    clerk_json(run, "commit", "--submission", str(path))
                else:
                    clerk_json(run, "cancel", "--reason", "合成取消")
                if terminal == "close":
                    clerk_json(run, "close", "--incomplete", "--reason", "合成结束")
                proc, _ = run_check("", packet=packet, submission=submission, run=run)
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)

    def test_missing_middle_event_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            run = make_run(tmp, DOCUMENTS)
            dispatch(run)
            clerk_json(run, "cancel", "--reason", "合成取消")
            packet = dispatch(run)
            (run / "events" / "000003.json").unlink()
            proc, _ = run_check("", packet=packet,
                                submission=submission_for(packet, "原告请求。"), run=run)
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("记录编号缺失", proc.stderr)

    def test_run_binding_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            run = make_run(tmp, DOCUMENTS)
            packet = dispatch(run)
            before = file_snapshot(run)
            submission = submission_for(packet, "原告请求。")
            proc, _ = run_check("", packet=packet, submission=submission, run=run)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(file_snapshot(run), before)
            submission = submission_for(packet, "原告依据 P-001 提出主张。")
            proc, _ = run_check("", packet=packet, submission=submission, run=run)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertEqual(file_snapshot(run), before)

    def test_text_output_reports_binding_status(self):
        proc, _ = run_check("原告请求给付30万元，依据 D-001 的约定。", json_output=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("清单绑定：SNAPSHOT_ONLY", proc.stdout)
        proc, _ = run_check("原告依据 P-001 提出主张。", json_output=False)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("清单绑定：SNAPSHOT_ONLY", proc.stdout)
        self.assertNotIn("P-001", proc.stdout)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            documents = json.loads(json.dumps(DOCUMENTS, ensure_ascii=False))
            run = make_run(tmp, documents)
            packet = dispatch(run)
            submission = submission_for(packet, "原告请求。")
            proc, _ = run_check("", documents=documents, packet=packet,
                                submission=submission, run=run, json_output=False)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("清单绑定：RUN_BOUND_PREFIX_ONLY（VALIDATED_PREFIX）", proc.stdout)
            self.assertIn("不能检测尾部删除", proc.stdout)
            submission["body"] = "原告依据 P-001 提出主张。"
            proc, _ = run_check("", documents=documents, packet=packet,
                                submission=submission, run=run, json_output=False)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("清单绑定：RUN_BOUND_PREFIX_ONLY", proc.stdout)
            self.assertNotIn("P-001", proc.stdout)

    def test_clean_submission_passes(self):
        proc, out = run_check("原告请求给付30万元，依据 D-001 的约定。")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(out["ok"])
        self.assertEqual(out["findings"], [])
        self.assertEqual(out["private_docs_considered"], 3)
        self.assertEqual(out["manifest_binding"], {"status": "SNAPSHOT_ONLY"})

    def test_own_private_id_and_text_block(self):
        proc, out = run_check("原告内部材料 P-001 显示：内部UAT清单42项通过，3项为非致命界面问题。")
        self.assertEqual(proc.returncode, 1)
        rules = [f["rule"] for f in out["findings"]]
        self.assertIn("MC-PRIVATE-ID", rules)
        self.assertIn("MC-PRIVATE-TEXT", rules)

    def test_opponent_private_leak_detected_from_manifest(self):
        proc, out = run_check("原告补充：运维台账显示已扣减8万元质保金，实际应付22万元。")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("MC-PRIVATE-TEXT", [f["rule"] for f in out["findings"]])

    def test_private_citation_blocks(self):
        proc, out = run_check("原告请求给付。", citations=["K-001"])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("MC-PRIVATE-CITATION", [f["rule"] for f in out["findings"]])

    def test_multiparty_material_still_private_for_open_record(self):
        proc, out = run_check("原告同意就验收争议先行调解，调解记录不入卷。")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("MC-PRIVATE-TEXT", [f["rule"] for f in out["findings"]])

    def test_quoting_public_text_with_newline_is_not_blocked(self):
        documents = json.loads(json.dumps(DOCUMENTS, ensure_ascii=False))
        documents[1]["text"] += "\n"
        documents[2]["text"] = "庭前备忘：" + documents[1]["text"].strip() + "据此主张验收合格。"
        proc, out = run_check("我方已接收测试版本并投入生产环境使用三个月（D-002 原文）。",
                              documents=documents)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(out["ok"])

    def test_private_memo_quoting_public_text_does_not_false_block(self):
        documents = json.loads(json.dumps(DOCUMENTS, ensure_ascii=False))
        documents[2]["text"] = "庭前要点：" + documents[1]["text"].strip() + "另拟申请证人出庭。"
        proc, out = run_check("原告指出：我方已接收测试版本并投入生产环境使用三个月。",
                              documents=documents)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(out["ok"])

    def test_generic_private_title_does_not_false_block(self):
        documents = json.loads(json.dumps(DOCUMENTS, ensure_ascii=False))
        documents[2]["title"] = "合同"
        proc, out = run_check("原告依据合同主张价款。", documents=documents)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("MC-PRIVATE-ID", [f["rule"] for f in out["findings"]])

    def test_report_does_not_echo_private_content(self):
        body = "原告内部材料 P-001 显示：内部UAT清单42项通过，3项为非致命界面问题。"
        proc, out = run_check(body)
        self.assertEqual(proc.returncode, 1)
        text = proc.stdout
        for secret in ("P-001", "内部UAT清单42项通过", "非致命界面问题", "运维台账",
                       "8万元质保金"):
            self.assertNotIn(secret, text)
        self.assertIn("private_doc_", text)

    def test_stale_packet_is_rejected(self):
        submission = {
            **ASSIGNMENT,
            "body": "原告请求。", "citations": ["D-001"],
            "turn_id": "T-0009", "role": "defendant", "material_version": 2,
        }
        proc, _ = run_check("", submission=submission)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("turn_id", proc.stderr)

    def test_stale_manifest_and_missing_identity_rejected(self):
        manifest = json.loads(json.dumps({"documents": DOCUMENTS}, ensure_ascii=False))
        manifest["documents"][0]["text"] += "新材料版本。"
        proc, _ = run_check("原告请求。", manifest=manifest)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("快照", proc.stderr)
        proc, _ = run_check("", submission={"body": "原告请求。", "citations": []})
        self.assertEqual(proc.returncode, 2)
        self.assertIn("派发字段", proc.stderr)

    def test_bad_input_types_exit_2_without_traceback(self):
        cases = [
            ({"documents": {"id": "D-001"}}, "manifest"),
            ({"documents": ["text"]}, "manifest"),
            ({"documents": [{"id": 42, "title": "t", "text": "x",
                             "visible_to": ["all"]}]}, "manifest"),
        ]
        for manifest, _ in cases:
            with self.subTest(manifest=manifest):
                proc, _ = run_check("原告请求。", manifest=manifest)
                self.assertEqual(proc.returncode, 2)
                self.assertNotIn("Traceback", proc.stderr)
                self.assertIn("manifest", proc.stderr)
        proc, _ = run_check("", submission=["not", "an", "object"])
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("Traceback", proc.stderr)

    def test_unverified_law_article_warns_without_blocking(self):
        proc, out = run_check("依《民法典》第159条，应视为条件已成就。")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("MC-LAW-UNCITED", [f["rule"] for f in out["findings"]])

    def test_contract_clause_numbers_do_not_warn(self):
        proc, out = run_check("按合同第三条验收，第五条付款。")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(out["findings"], [])

    def test_statute_in_same_sentence_as_contract_still_warns(self):
        proc, out = run_check("按合同第三条及《民法典》第159条主张价款。")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("MC-LAW-UNCITED", [f["rule"] for f in out["findings"]])

    def test_public_document_locator_article_does_not_warn(self):
        documents = json.loads(json.dumps(DOCUMENTS, ensure_ascii=False))
        documents.append({
            **documents[0],
            "id": "D-003",
            "title": "聊天摘录",
            "locator": "聊天第3条",
            "text": "“仓库小乙”回复：“东西先放仓库，等负责人来验收。”",
        })
        proc, out = run_check("按 D-001 定位“合同第3.1条”，另按 D-003 聊天第3条说明。",
                              documents=documents, citations=["D-001", "D-003"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("MC-LAW-UNCITED", [f["rule"] for f in out["findings"]])

    def test_public_id_prefix_does_not_match_private_id(self):
        documents = json.loads(json.dumps(DOCUMENTS, ensure_ascii=False))
        documents.append({**documents[0], "id": "P-0010"})
        proc, out = run_check("材料P-0010显示合同约定。", documents=documents, citations=["P-0010"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(out["findings"], [])
        proc, out = run_check("材料P-001显示合同约定。", documents=documents)
        self.assertEqual(proc.returncode, 1)

    def test_long_private_text_tail_is_checked(self):
        documents = json.loads(json.dumps(DOCUMENTS, ensure_ascii=False))
        documents[3]["text"] = "合成备忘上下文。" * 8000 + "尾部独有事项共计二十七笔待核对记录。"
        proc, out = run_check("尾部独有事项共计二十七笔待核对记录。", documents=documents)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("MC-PRIVATE-TEXT", [f["rule"] for f in out["findings"]])

    def test_law_article_present_in_public_material_is_not_flagged(self):
        documents = json.loads(json.dumps(DOCUMENTS, ensure_ascii=False))
        documents[0]["text"] += "双方确认适用第159条。"
        proc, out = run_check("依公开材料所载第159条，应视为条件已成就。",
                              documents=documents)
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn("MC-LAW-UNCITED", [f["rule"] for f in out["findings"]])

    def test_unnamed_rule_proposition_passes(self):
        proc, out = run_check("原告主张：一方为自身利益不正当阻止条件成就时，可能产生相应法律后果（待核验）。")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(out["findings"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
