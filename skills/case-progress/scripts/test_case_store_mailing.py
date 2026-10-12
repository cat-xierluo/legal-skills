#!/usr/bin/env python3
"""合成案件的真实 CLI 回归；CASE_STORE_SCRIPT 可指定负对照脚本。"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

SCRIPT = Path(os.environ.get("CASE_STORE_SCRIPT", Path(__file__).with_name("case_store.py"))).resolve()
CASE = "261013-A"
NUMBER = "0012345678901"  # 合成单号，不发往承运商。


class MailingCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.case = self.root / f"{CASE} 合成案件"
        self.path = self.case / "00 - 📅 日程管理" / "case.yaml"
        self.path.parent.mkdir(parents=True)
        self.initial = {
            "meta": {"模板版本": "4.0", "业务领域": "诉讼", "案件短码": CASE},
            "案件基本信息": {"案件类型": "民事", "生命周期状态": "进行中", "程序阶段": "一审"},
            "当事人与代理": {}, "任务": [{"id": "task_001", "名称": "保留", "source": "user", "状态": "todo"}],
            "案件时间线": [], "费用信息": {}, "上下文": {}, "同步": {}, "更新历史": [],
            "扩展信息": {"合成标记": "不得丢失"},
        }
        self.write(self.initial)

    def write(self, data):
        self.path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def data(self):
        return yaml.safe_load(self.path.read_text(encoding="utf-8"))

    def run_cli(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), *args], text=True, capture_output=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stderr)
        return result

    def add(self, *args, number=NUMBER):
        return self.run_cli("add-mailing", CASE, number, "--carrier", "ems", *args)

    def unchanged_failure(self, *args):
        before = self.path.read_bytes()
        result = self.run_cli(*args, ok=False)
        self.assertEqual(self.path.read_bytes(), before)
        return result

    def test_register_show_and_signed_roundtrip(self):
        self.add("--sent", "2026-10-13", "--content", "合成证据目录", "--file", "08 - 🏛️ 法院送达/寄件.jpg")
        self.run_cli("set-mailing", CASE, NUMBER, "--status", "in_transit", "--latest", "合成运输节点")
        self.run_cli("set-mailing", CASE, NUMBER, "--signed", "2026-10-14", "--file", "08 - 🏛️ 法院送达/签收.pdf")
        row = json.loads(self.run_cli("show", CASE).stdout)["邮寄跟踪"][0]
        self.assertEqual(row["单号"], NUMBER)
        self.assertEqual(row["状态"], "signed")
        self.assertEqual(row["签收日期"], "2026-10-14")
        self.assertEqual(row["最新轨迹"], "合成运输节点")
        self.assertEqual(len(row["凭证文件"]), 2)
        data = self.data()
        self.assertEqual(data["任务"], self.initial["任务"])
        self.assertEqual(data["扩展信息"], self.initial["扩展信息"])
        self.assertEqual(len(data["更新历史"]), 3)
        self.assertTrue(data["同步"]["最后同步时间"])
        self.run_cli("validate", CASE)

    def test_legacy_case_show_has_empty_mailing_list(self):
        self.assertEqual(json.loads(self.run_cli("show", CASE).stdout)["邮寄跟踪"], [])

    def test_batch_list_then_show_finds_pending_number(self):
        self.add()
        ids = [row["案件"] for row in json.loads(self.run_cli("list").stdout)]
        rows = [m for cid in ids for m in json.loads(self.run_cli("show", cid).stdout)["邮寄跟踪"] if m["状态"] in ("pending", "in_transit")]
        self.assertEqual([m["单号"] for m in rows], [NUMBER])

    def test_duplicate_and_missing_number_do_not_write(self):
        self.add()
        self.unchanged_failure("add-mailing", CASE, NUMBER, "--carrier", "ems")
        self.unchanged_failure("set-mailing", CASE, "does-not-exist", "--status", "signed")

    def test_user_source_is_protected_and_user_can_update(self):
        self.add("--actor", "user")
        self.unchanged_failure("set-mailing", CASE, NUMBER, "--status", "signed")
        self.run_cli("set-mailing", CASE, NUMBER, "--signed", "2026-10-14", "--actor", "user")
        self.assertEqual(self.data()["邮寄跟踪"][0]["source"], "user")

    def test_mailing_preserves_closed_lifecycle_and_locked_stage(self):
        data = self.data()
        data["案件基本信息"].update({"生命周期状态": "已结案", "程序阶段锁定": True})
        self.write(data)
        self.add()
        self.run_cli("set-mailing", CASE, NUMBER, "--status", "in_transit")
        self.assertEqual(self.data()["案件基本信息"], data["案件基本信息"])

    def test_status_correction_keeps_historical_signed_date(self):
        self.add()
        self.run_cli("set-mailing", CASE, NUMBER, "--signed", "2026-10-14")
        self.run_cli("set-mailing", CASE, NUMBER, "--status", "abnormal", "--latest", "合成签收后退回")
        row = self.data()["邮寄跟踪"][0]
        self.assertEqual(row["状态"], "abnormal")
        self.assertEqual(row["签收日期"], "2026-10-14")

    def test_file_append_is_deduplicated(self):
        self.add("--file", "08/凭证.pdf")
        self.run_cli("set-mailing", CASE, NUMBER, "--file", "08/凭证.pdf")
        self.assertEqual(self.data()["邮寄跟踪"][0]["凭证文件"], ["08/凭证.pdf"])

    def test_bad_dates_do_not_write(self):
        for date in ("2026-02-30", "2026-10", "not-a-date", ""):
            with self.subTest(date=date):
                self.unchanged_failure("add-mailing", CASE, NUMBER, "--carrier", "ems", "--sent", date)
        self.add()
        for date in ("2026-02-30", ""):
            self.unchanged_failure("set-mailing", CASE, NUMBER, "--signed", date)

    def test_bad_enums_empty_number_and_conflicting_status_do_not_write(self):
        self.unchanged_failure("add-mailing", CASE, NUMBER, "--carrier", "fake")
        self.unchanged_failure("add-mailing", CASE, "  ", "--carrier", "ems")
        self.add()
        self.unchanged_failure("set-mailing", CASE, NUMBER, "--status", "fake")
        self.unchanged_failure("set-mailing", CASE, NUMBER, "--status", "in_transit", "--signed", "2026-10-14")

    def test_unsafe_file_paths_do_not_write(self):
        for file in ("/outside/proof.pdf", "../proof.pdf", "08/../../proof.pdf", "C:\\outside\\proof.pdf", "..\\proof.pdf", "~/proof.pdf", ""):
            with self.subTest(file=file):
                self.unchanged_failure("add-mailing", CASE, NUMBER, "--carrier", "ems", "--file", file)
        self.add()
        self.unchanged_failure("set-mailing", CASE, NUMBER, "--file", "../proof.pdf")

    def test_symlink_escape_does_not_write(self):
        (self.case / "external").symlink_to(self.root, target_is_directory=True)
        self.unchanged_failure("add-mailing", CASE, NUMBER, "--carrier", "ems", "--file", "external/proof.pdf")

    def test_set_fields_cannot_replace_mailings(self):
        self.add("--actor", "user")
        for actor in ("ai", "user"):
            self.unchanged_failure("set-fields", CASE, '{"邮寄跟踪": []}', "--actor", actor)

    def test_malformed_mailing_shapes_fail_without_traceback(self):
        for value in ({}, None, "invalid", ["invalid"]):
            with self.subTest(value=value):
                data = copy.deepcopy(self.initial)
                data["邮寄跟踪"] = value
                self.write(data)
                self.unchanged_failure("add-mailing", CASE, NUMBER, "--carrier", "ems")
                self.run_cli("validate", CASE, ok=False)

    def test_schema_rejects_bad_rows(self):
        self.add()
        good = self.data()
        for key, value in (("单号", 123), ("source", "external"), ("承运商", "fake"), ("状态", "fake"), ("签收日期", "2026-02-30"), ("凭证文件", ["../proof.pdf"]), ("凭证文件", "proof.pdf")):
            with self.subTest(key=key, value=value):
                bad = copy.deepcopy(good)
                bad["邮寄跟踪"][0][key] = value
                self.write(bad)
                self.run_cli("validate", CASE, ok=False)
        bad = copy.deepcopy(good)
        bad["邮寄跟踪"].append(copy.deepcopy(bad["邮寄跟踪"][0]))
        self.write(bad)
        self.run_cli("validate", CASE, ok=False)

    def test_concurrent_registration_keeps_both_rows(self):
        procs = [subprocess.Popen([sys.executable, str(SCRIPT), "--root", str(self.root), "add-mailing", CASE, number, "--carrier", "ems"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for number in (NUMBER, "0098765432109")]
        for proc in procs:
            out, err = proc.communicate(timeout=20)
            self.assertEqual(proc.returncode, 0, out + err)
        self.assertEqual({m["单号"] for m in self.data()["邮寄跟踪"]}, {NUMBER, "0098765432109"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
