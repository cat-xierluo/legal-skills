#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test-zcode-pr-acceptance — zcode-pr-acceptance.py 的黑盒定向测试。

任务号：TASK-2026-10-04-ZGUI-PR-ACCEPTANCE
归属：本文件由该任务的测试子代理编写（只交付测试文件与真实运行结果，不修改被测实现、不自行验收）。
依赖：仅 Python 标准库（unittest / json / subprocess / tempfile / hashlib / copy / shutil / os / sys / datetime）。

测试方式：
- 用 tempfile 写入临时输入 JSON，通过 subprocess(sys.executable) 调用真实 CLI
  （同目录 zcode-pr-acceptance.py），断言退出码与 stdout 单行 verdict JSON。
- 单次 CLI 调用超时上限 15 秒；全量用例预期总时长 < 90 秒。
- 临时数据统一落在 /private/tmp/zgui-expanded-20261004/pr-acceptance/subagent-tests-tmp。

重要声明：
- 合成正例（虚构 sha/SID/repo）仅证明接口契约：business_semantics_proven 恒为 false，
  PASS 不代表任何真实 PR 的业务语义被证明。
- "真实已合并 PR 历史快照" fixture 的数据来源是本仓库 git 历史中真实存在的 squash-merge
  记录 dcc37d49 (#263)，测试中将其离线重构成 evidence JSON；这是离线重构，不是实时
  GitHub 读取，也不声称 GitHub 当前状态。
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

TASK_ID = "TASK-2026-10-04-ZGUI-PR-ACCEPTANCE"
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
CLI_PATH = os.path.join(SCRIPTS_DIR, "zcode-pr-acceptance.py")
BASE_TMP = "/private/tmp/zgui-expanded-20261004/pr-acceptance/subagent-tests-tmp"

EXPECTATIONS_SCHEMA = "zgui-pr-acceptance/expectations@1"
EVIDENCE_SCHEMA = "zgui-pr-acceptance/evidence@1"
VERDICT_SCHEMA = "zgui-pr-acceptance/verdict@1"

EXIT_PASS, EXIT_REJECT, EXIT_UNKNOWN, EXIT_INTERNAL, EXIT_USAGE = 0, 10, 20, 30, 2
UNKNOWN_LEVEL_REASONS = {
    "BRANCH_PR_LIST_EMPTY", "BRANCH_PR_NOT_LISTED", "REQUIRED_CHECKS_UNSPECIFIED",
    "EVIDENCE_STALE", "EVIDENCE_TIME_INVALID",
}

# ---- 合成 fixture（仅证明接口契约，sha/SID/repo 全部虚构） -------------------------------
DEFAULT_NOW = "2026-10-04T12:05:00Z"       # 注入时钟
COLLECTED_AT = "2026-10-04T12:00:00Z"      # now - 300s，恰好新鲜（max_age=900）
SHA_BASE = "1" * 40
SHA_HEAD = "2" * 40
SHA_OTHER = "3" * 40
SYNTH_REPO = "example-owner/example-repo"
SYNTH_BRANCH = "feat/example-branch"
SYNTH_BASE_REF = "integration/example-line"
SYNTH_TASK = "TASK-SYNTH-INTERFACE-ONLY"
PATH_A = "skills/example/scripts/tool.py"
PATH_B = "skills/example/scripts/test_tool.py"

SYNTH_EXPECTATIONS = {
    "schema": EXPECTATIONS_SCHEMA,
    "task_sid": SYNTH_TASK,
    "repo": SYNTH_REPO,
    "expected_base_ref": SYNTH_BASE_REF,
    "expected_base": SHA_BASE,
    "expected_head": SHA_HEAD,
    "expected_branch": SYNTH_BRANCH,
    "allowed_paths": [PATH_A, PATH_B],
    "author_sid": "SID-AUTHOR",
    "reviewer_sid": "SID-REVIEWER",
    "required_checks": ["ci"],
    "evidence_max_age_seconds": 900,
}

SYNTH_EVIDENCE = {
    "schema": EVIDENCE_SCHEMA,
    "collected_at": COLLECTED_AT,
    "repo": SYNTH_REPO,
    "pr": {
        "number": 7,
        "state": "OPEN",
        "is_draft": False,
        "branch": SYNTH_BRANCH,
        "head_sha": SHA_HEAD,
        "base_ref": SYNTH_BASE_REF,
        "base_sha": SHA_BASE,
        "author_sid": "SID-AUTHOR",
        "files": [
            {"path": PATH_A, "status": "added"},
            {"path": PATH_B, "status": "added"},
        ],
    },
    "branch_prs": [
        {"number": 7, "state": "OPEN", "branch": SYNTH_BRANCH, "head_sha": SHA_HEAD},
    ],
    "head_checks": {
        "head_sha": SHA_HEAD,
        "checks": [{"name": "ci", "status": "completed", "conclusion": "success"}],
    },
    "review": {
        "reviewer_sid": "SID-REVIEWER",
        "head_sha": SHA_HEAD,
        "verdict": "APPROVE",
        "blockers": [],
    },
}

# ---- 真实历史快照 fixture（来源=仓库 git 历史，离线重构，非实时 GitHub 读取） -------------
# git show dcc37d49:
#   dcc37d498efcc1dc7588c0bb81c38c231bc74bfa
#   M  skills/multi-agent-orchestration/TASKS.md
#   docs(multi-agent-orchestration): close cloud PR audit and record remaining
#   dependencies (#263)   （squash-merge 提交，作者日期 2026-10-03 16:04:52 +0800）
# 其 parent 1d9f3a4808c699aa517eaeafbc0e370c5cf4f105 是 #262 的 squash-merge 提交。
# remote origin = https://github.com/cat-xierluo/legal-skills.git
# 旁证（同链历史，未在本测试中直接引用）：#260=17f857dc、#252=2f12a1de。
REAL_REPO = "cat-xierluo/legal-skills"
REAL_PR_263 = 263
REAL_PR_263_HEAD = "dcc37d498efcc1dc7588c0bb81c38c231bc74bfa"
REAL_PR_263_BASE = "1d9f3a4808c699aa517eaeafbc0e370c5cf4f105"  # #262 = dcc37d49 的 parent
REAL_PR_263_FILE = "skills/multi-agent-orchestration/TASKS.md"
REAL_PR_263_BRANCH = "feat/zgui-cloud-pr-audit-263"  # 分支名为离线重构（ref 模式合法）
REAL_PR_263_COLLECTED_AT = "2026-10-03T08:04:52Z"    # dcc37d49 作者日期的 UTC
REAL_PR_263_NOW = "2026-10-03T08:05:00Z"             # 快照后 8 秒判定，确保新鲜

REAL_EXPECTATIONS = {
    "schema": EXPECTATIONS_SCHEMA,
    "task_sid": TASK_ID,
    "repo": REAL_REPO,
    "expected_base_ref": "main",
    "expected_base": REAL_PR_263_BASE,
    "expected_head": REAL_PR_263_HEAD,
    "expected_branch": REAL_PR_263_BRANCH,
    "allowed_paths": [REAL_PR_263_FILE],
    "author_sid": "SID-A263",
    "reviewer_sid": "SID-R263",
    "required_checks": ["ci"],
    "evidence_max_age_seconds": 900,
}

# 如今已 MERGED 的历史快照：state=MERGED（真实终态），其余字段离线重构保持自洽。
REAL_EVIDENCE_MERGED = {
    "schema": EVIDENCE_SCHEMA,
    "collected_at": REAL_PR_263_COLLECTED_AT,
    "repo": REAL_REPO,
    "pr": {
        "number": REAL_PR_263,
        "state": "MERGED",
        "is_draft": False,
        "branch": REAL_PR_263_BRANCH,
        "head_sha": REAL_PR_263_HEAD,
        "base_ref": "main",
        "base_sha": REAL_PR_263_BASE,
        "author_sid": "SID-A263",
        "files": [{"path": REAL_PR_263_FILE, "status": "modified"}],
    },
    "branch_prs": [
        {"number": REAL_PR_263, "state": "MERGED",
         "branch": REAL_PR_263_BRANCH, "head_sha": REAL_PR_263_HEAD},
    ],
    "head_checks": {
        "head_sha": REAL_PR_263_HEAD,
        "checks": [{"name": "ci", "status": "completed", "conclusion": "success"}],
    },
    "review": {
        "reviewer_sid": "SID-R263",
        "head_sha": REAL_PR_263_HEAD,
        "verdict": "APPROVE",
        "blockers": [],
    },
}

VERDICT_KEYS = {
    "schema", "tool_version", "decision", "reasons", "reason_details",
    "task_sid", "repo", "pr_number", "expected_head", "expected_base",
    "inputs", "clock", "evidence_age_seconds", "generated_at_utc",
    "business_semantics_proven",
}

_DELETE = object()


def _merge(base, overrides):
    out = copy.deepcopy(base)
    for k, v in overrides.items():
        if v is _DELETE:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def synth_exp(**overrides):
    return _merge(SYNTH_EXPECTATIONS, overrides)


def synth_ev(**overrides):
    return _merge(SYNTH_EVIDENCE, overrides)


def real_exp(**overrides):
    return _merge(REAL_EXPECTATIONS, overrides)


def real_ev(**overrides):
    return _merge(REAL_EVIDENCE_MERGED, overrides)


class PrAcceptanceTests(unittest.TestCase):
    """zcode-pr-acceptance.py 黑盒契约测试（真实子进程调用）。"""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(CLI_PATH):
            raise RuntimeError("被测 CLI 不存在: %s" % CLI_PATH)
        os.makedirs(BASE_TMP, exist_ok=True)

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="zgui-pr-acc-", dir=BASE_TMP)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ---- 运行与断言辅助 ---------------------------------------------------------------

    def _write_input(self, value, name):
        """dict/list → JSON 文件；str → 原样字节；返回写入的原始字节。"""
        path = os.path.join(self.tmpdir, name)
        if isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False, indent=2)
        else:
            text = str(value)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return text.encode("utf-8")

    def run_cli(self, exp, ev, now_iso=DEFAULT_NOW, out=None, cwd=None,
                exp_name="expectations.json", ev_name="evidence.json"):
        """exp/ev 为 dict/str 时写入文件；为 None 时指向不存在的路径。"""
        if exp is None:
            exp_path = os.path.join(self.tmpdir, "missing-expectations.json")
        else:
            exp_path = os.path.join(self.tmpdir, exp_name)
            self._write_input(exp, exp_name)
        if ev is None:
            ev_path = os.path.join(self.tmpdir, "missing-evidence.json")
        else:
            ev_path = os.path.join(self.tmpdir, ev_name)
            self._write_input(ev, ev_name)
        cmd = [sys.executable, CLI_PATH, "--expectations", exp_path, "--evidence", ev_path]
        if now_iso is not None:
            cmd += ["--now-iso", now_iso]
        if out is not None:
            cmd += ["--out", out]
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=15, cwd=cwd or self.tmpdir)

    def check(self, proc, exit_code, decision, reasons_in=None,
              reasons_not_in=None, reasons_exact=None):
        self.assertEqual(
            proc.returncode, exit_code,
            msg="exit=%r stderr=%r stdout=%r" % (proc.returncode, proc.stderr, proc.stdout))
        self.assertTrue(proc.stdout.endswith("\n"), "stdout 应以换行结束")
        self.assertEqual(proc.stdout.count("\n"), 1, "stdout 必须是单行 JSON")
        verdict = json.loads(proc.stdout)
        self.assertEqual(verdict["decision"], decision)
        if reasons_exact is not None:
            self.assertEqual(verdict["reasons"], reasons_exact)
        for r in (reasons_in or []):
            self.assertIn(r, verdict["reasons"],
                          msg="reasons=%r" % (verdict["reasons"],))
        for r in (reasons_not_in or []):
            self.assertNotIn(r, verdict["reasons"],
                             msg="reasons=%r" % (verdict["reasons"],))
        return verdict

    # ---- 1. 合成正例 PASS ---------------------------------------------------------------

    def test_pass_synthetic_positive(self):
        """合成正例：exit 0 / reasons==[] / business_semantics_proven==false。

        声明：本用例的 sha/SID/repo 全部虚构，仅证明接口契约，不证明任何真实 PR。
        """
        proc = self.run_cli(synth_exp(), synth_ev())
        v = self.check(proc, EXIT_PASS, "PASS", reasons_exact=[])
        # verdict 字段完整性
        self.assertEqual(set(v.keys()), VERDICT_KEYS)
        self.assertEqual(v["schema"], VERDICT_SCHEMA)
        self.assertEqual(v["business_semantics_proven"], False)
        self.assertEqual(v["reason_details"], {})
        # 注入时钟自我声明
        self.assertEqual(v["clock"], {"source": "argument", "now_utc": DEFAULT_NOW})
        # 新鲜度：now 12:05:00 - collected 12:00:00 = 300s（max_age=900 内）
        self.assertEqual(v["evidence_age_seconds"], 300)
        # 回显消费方绑定字段
        self.assertEqual(v["expected_head"], SHA_HEAD)
        self.assertEqual(v["expected_base"], SHA_BASE)
        self.assertEqual(v["pr_number"], 7)
        self.assertEqual(v["task_sid"], SYNTH_TASK)
        self.assertEqual(v["repo"], SYNTH_REPO)
        # 输入 SHA256 与写入字节精确绑定
        exp_bytes = self._write_input(synth_exp(), "re-exp.json")
        ev_bytes = self._write_input(synth_ev(), "re-ev.json")
        self.assertEqual(v["inputs"]["expectations_sha256"],
                         hashlib.sha256(exp_bytes).hexdigest())
        self.assertEqual(v["inputs"]["evidence_sha256"],
                         hashlib.sha256(ev_bytes).hexdigest())
        # stdout 为 sort_keys 紧凑单行
        canon = json.dumps(v, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        self.assertEqual(proc.stdout.strip(), canon)

    def test_pass_system_clock(self):
        """默认系统时钟：clock.source=system，且新鲜 PASS。"""
        collected = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ev = synth_ev(collected_at=collected)
        exp = synth_exp(evidence_max_age_seconds=3600)
        proc = self.run_cli(exp, ev, now_iso=None)
        v = self.check(proc, EXIT_PASS, "PASS", reasons_exact=[])
        self.assertEqual(v["clock"]["source"], "system")
        self.assertTrue(v["clock"]["now_utc"].endswith("Z"))
        self.assertTrue(0 <= v["evidence_age_seconds"] <= 30,
                        msg="age=%r" % v["evidence_age_seconds"])

    # ---- 2. 真实已合并 PR 历史快照负例 ---------------------------------------------------

    def test_real_merged_pr_263_rejected(self):
        """真实历史快照：#263（dcc37d49 squash-merge）如今已 MERGED → REJECT PR_NOT_OPEN。

        fixture 数据来源：仓库 git 历史真实提交（离线重构，非实时 GitHub 读取）。
        """
        proc = self.run_cli(real_exp(), real_ev(), now_iso=REAL_PR_263_NOW)
        self.check(proc, EXIT_REJECT, "REJECT", reasons_in=["PR_NOT_OPEN"])

    def test_real_merged_pr_263_draft_variant(self):
        """真实快照的 draft 期变体：is_draft=true → REJECT 含 PR_DRAFT。"""
        ev = real_ev(**{"pr": {"is_draft": True}})
        proc = self.run_cli(real_exp(), ev, now_iso=REAL_PR_263_NOW)
        self.check(proc, EXIT_REJECT, "REJECT", reasons_in=["PR_DRAFT"])

    # ---- 3. OPEN 偏差 --------------------------------------------------------------------

    def test_deviation_state_closed(self):
        ev = synth_ev(**{"pr": {"state": "CLOSED"}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["PR_NOT_OPEN"])

    def test_deviation_head_mismatch(self):
        ev = synth_ev(**{"pr": {"head_sha": SHA_OTHER}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["HEAD_MISMATCH"])

    def test_deviation_base_sha_mismatch(self):
        ev = synth_ev(**{"pr": {"base_sha": SHA_OTHER}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["BASE_MISMATCH"])

    def test_deviation_base_ref_mismatch(self):
        ev = synth_ev(**{"pr": {"base_ref": "integration/other-line"}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["BASE_MISMATCH"])

    def test_deviation_repo_mismatch(self):
        ev = synth_ev(repo="other-owner/other-repo")
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["REPO_MISMATCH"])

    def test_deviation_branch_mismatch(self):
        ev = synth_ev(**{"pr": {"branch": "feat/other-branch"},
                         "branch_prs": [{"number": 7, "state": "OPEN",
                                         "branch": "feat/other-branch",
                                         "head_sha": SHA_HEAD}]})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["BRANCH_MISMATCH"])

    def test_deviation_is_draft_true(self):
        ev = synth_ev(**{"pr": {"is_draft": True}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["PR_DRAFT"])

    # ---- 4. 路径 --------------------------------------------------------------------------

    def test_paths_extra_file(self):
        ev = synth_ev(**{"pr": {"files": [
            {"path": PATH_A, "status": "added"},
            {"path": PATH_B, "status": "added"},
            {"path": "skills/example/scripts/extra.py", "status": "added"},
        ]}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["PATHS_MISMATCH"])

    def test_paths_missing_file(self):
        ev = synth_ev(**{"pr": {"files": [{"path": PATH_A, "status": "added"}]}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["PATHS_MISMATCH"])

    def test_paths_different_file(self):
        ev = synth_ev(**{"pr": {"files": [
            {"path": PATH_A, "status": "added"},
            {"path": "skills/example/scripts/different.py", "status": "added"},
        ]}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["PATHS_MISMATCH"])

    def test_allowed_paths_duplicate(self):
        exp = synth_exp(allowed_paths=[PATH_A, PATH_A])
        self.check(self.run_cli(exp, synth_ev()),
                   EXIT_REJECT, "REJECT", reasons_in=["PATH_DUPLICATE"])

    def test_path_traversal_vectors(self):
        """坏路径向量（按实现均为 PATH_TRAVERSAL，REJECT 级）。"""
        vectors = ["a/../b.py", "/abs/path", "a\\b", "a//b", "a/", "./a"]
        for bad in vectors:
            with self.subTest(path=bad):
                exp = synth_exp(allowed_paths=[bad, PATH_B])
                ev = synth_ev(**{"pr": {"files": [{"path": bad, "status": "modified"},
                                                  {"path": PATH_B, "status": "modified"}]}})
                v = self.check(self.run_cli(exp, ev),
                               EXIT_REJECT, "REJECT", reasons_in=["PATH_TRAVERSAL"])
                # PATH_TRAVERSAL 是 REJECT 级枚举（exit 10 已证明）；
                # 实现将单字段 detail 折叠为标量：detail 即 expectations.allowed_paths
                self.assertNotIn("PATH_TRAVERSAL", UNKNOWN_LEVEL_REASONS)
                self.assertEqual(v["reason_details"].get("PATH_TRAVERSAL"),
                                 "expectations.allowed_paths")

    def test_file_status_removed(self):
        ev = synth_ev(**{"pr": {"files": [{"path": PATH_A, "status": "removed"},
                                          {"path": PATH_B, "status": "added"}]}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["FILE_STATUS_UNSUPPORTED"])

    # ---- 5. 类型 --------------------------------------------------------------------------

    def test_bool_as_int_pr_number(self):
        ev = synth_ev(**{"pr": {"number": True}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["BOOL_AS_INT"])

    def test_bool_as_int_max_age(self):
        exp = synth_exp(evidence_max_age_seconds=True)
        self.check(self.run_cli(exp, synth_ev()),
                   EXIT_REJECT, "REJECT", reasons_in=["BOOL_AS_INT"])

    def test_type_mismatch_is_draft_string(self):
        ev = synth_ev(**{"pr": {"is_draft": "false"}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["TYPE_MISMATCH"])

    def test_type_mismatch_files_string(self):
        ev = synth_ev(**{"pr": {"files": "x"}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["TYPE_MISMATCH"])

    def test_value_invalid_uppercase_sha(self):
        ev = synth_ev(**{"pr": {"head_sha": "F" * 40}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["VALUE_INVALID"])

    def test_value_invalid_short_sha(self):
        ev = synth_ev(**{"pr": {"head_sha": "2" * 39}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["VALUE_INVALID"])

    def test_value_invalid_lowercase_state(self):
        ev = synth_ev(**{"pr": {"state": "open"}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["VALUE_INVALID"])

    # ---- 6. schema / 输入 ------------------------------------------------------------------

    def test_schema_wrong_string(self):
        exp = synth_exp(schema="zgui-pr-acceptance/expectations@2")
        self.check(self.run_cli(exp, synth_ev()),
                   EXIT_REJECT, "REJECT", reasons_in=["SCHEMA_UNKNOWN"])

    def test_schema_key_missing(self):
        exp = synth_exp()
        exp.pop("schema")
        self.check(self.run_cli(exp, synth_ev()),
                   EXIT_REJECT, "REJECT", reasons_in=["SCHEMA_UNKNOWN"])

    def test_schema_missing_required_field(self):
        exp = synth_exp()
        exp.pop("expected_head")
        v = self.check(self.run_cli(exp, synth_ev()),
                       EXIT_REJECT, "REJECT", reasons_in=["SCHEMA_MISSING_FIELD"])
        self.assertEqual(v["reason_details"].get("SCHEMA_MISSING_FIELD"),
                         "expectations.expected_head")

    def test_inputs_swapped(self):
        """两份文件互换（--expectations 传 evidence 文件）→ SCHEMA_UNKNOWN。"""
        exp_path = os.path.join(self.tmpdir, "evidence-as-expectations.json")
        ev_path = os.path.join(self.tmpdir, "expectations-as-evidence.json")
        self._write_input(synth_ev(), os.path.basename(exp_path))
        self._write_input(synth_exp(), os.path.basename(ev_path))
        cmd = [sys.executable, CLI_PATH,
               "--expectations", exp_path, "--evidence", ev_path,
               "--now-iso", DEFAULT_NOW]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=15, cwd=self.tmpdir)
        self.check(proc, EXIT_REJECT, "REJECT", reasons_in=["SCHEMA_UNKNOWN"])

    def test_input_unparseable(self):
        self.check(self.run_cli("{ not valid json", synth_ev()),
                   EXIT_REJECT, "REJECT", reasons_in=["INPUT_UNPARSEABLE"])

    def test_input_missing_file(self):
        self.check(self.run_cli(synth_exp(), None),
                   EXIT_REJECT, "REJECT", reasons_in=["INPUT_MISSING"])

    def test_input_not_object(self):
        self.check(self.run_cli("[1, 2, 3]", synth_ev()),
                   EXIT_REJECT, "REJECT", reasons_in=["INPUT_NOT_OBJECT"])

    # ---- 7. SID 绑定 ------------------------------------------------------------------------

    def test_author_sid_mismatch(self):
        ev = synth_ev(**{"pr": {"author_sid": "SID-IMPOSTOR"}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["AUTHOR_SID_MISMATCH"])

    def test_reviewer_sid_mismatch(self):
        ev = synth_ev(**{"review": {"reviewer_sid": "SID-OTHER"}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["REVIEWER_SID_MISMATCH"])

    def test_reviewer_not_independent_in_expectations(self):
        exp = synth_exp(author_sid="SID-SAME", reviewer_sid="SID-SAME")
        self.check(self.run_cli(exp, synth_ev()),
                   EXIT_REJECT, "REJECT", reasons_in=["REVIEWER_NOT_INDEPENDENT"])

    def test_reviewer_not_independent_in_evidence(self):
        """evidence 中 PR 作者 SID == 审查者 SID → REVIEWER_NOT_INDEPENDENT。"""
        ev = synth_ev(**{"pr": {"author_sid": "SID-REVIEWER"}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["REVIEWER_NOT_INDEPENDENT"])

    # ---- 8. 审查 ------------------------------------------------------------------------------

    def test_review_head_mismatch(self):
        ev = synth_ev(**{"review": {"head_sha": SHA_OTHER}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT",
                   reasons_in=["REVIEW_HEAD_MISMATCH"], reasons_not_in=["HEAD_MISMATCH"])

    def test_review_verdict_reject(self):
        ev = synth_ev(**{"review": {"verdict": "REJECT"}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["REVIEW_VERDICT_REJECT"])

    def test_review_blockers_nonempty(self):
        """blockers 非空 → REVIEW_BLOCKERS，且自由文本内容永不回显（见 test_no_leak）。"""
        ev = synth_ev(**{"review": {"blockers": ["blocker text one"]}})
        v = self.check(self.run_cli(synth_exp(), ev),
                       EXIT_REJECT, "REJECT", reasons_in=["REVIEW_BLOCKERS"])
        self.assertEqual(v["reason_details"].get("REVIEW_BLOCKERS"), 1)

    # ---- 9. 同 branch PR 清单 --------------------------------------------------------------------

    def _branch_pr_entry(self, number, state, branch=SYNTH_BRANCH):
        return {"number": number, "state": state, "branch": branch, "head_sha": SHA_OTHER}

    def test_duplicate_branch_pr_other_open(self):
        ev = synth_ev(branch_prs=[
            {"number": 7, "state": "OPEN", "branch": SYNTH_BRANCH, "head_sha": SHA_HEAD},
            self._branch_pr_entry(8, "OPEN"),
        ])
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["DUPLICATE_BRANCH_PR"])

    def test_duplicate_branch_pr_other_merged(self):
        """同 branch 任何状态的其他 PR（含 MERGED）都算重复。"""
        ev = synth_ev(branch_prs=[
            {"number": 7, "state": "OPEN", "branch": SYNTH_BRANCH, "head_sha": SHA_HEAD},
            self._branch_pr_entry(9, "MERGED"),
        ])
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["DUPLICATE_BRANCH_PR"])

    def test_branch_pr_list_empty_unknown(self):
        ev = synth_ev(branch_prs=[])
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_UNKNOWN, "UNKNOWN", reasons_in=["BRANCH_PR_LIST_EMPTY"])

    def test_branch_pr_not_listed(self):
        ev = synth_ev(branch_prs=[self._branch_pr_entry(8, "OPEN", branch="feat/other-line")])
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_UNKNOWN, "UNKNOWN", reasons_in=["BRANCH_PR_NOT_LISTED"])

    def test_branch_pr_list_duplicate(self):
        ev = synth_ev(branch_prs=[
            {"number": 7, "state": "OPEN", "branch": SYNTH_BRANCH, "head_sha": SHA_HEAD},
            {"number": 7, "state": "MERGED", "branch": SYNTH_BRANCH, "head_sha": SHA_HEAD},
        ])
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT",
                   reasons_in=["BRANCH_PR_LIST_DUPLICATE"],
                   reasons_not_in=["DUPLICATE_BRANCH_PR"])

    # ---- 10. checks --------------------------------------------------------------------------

    def test_checks_head_mismatch(self):
        ev = synth_ev(**{"head_checks": {"head_sha": SHA_OTHER}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT",
                   reasons_in=["CHECKS_HEAD_MISMATCH"],
                   reasons_not_in=["REQUIRED_CHECK_MISSING", "CHECK_NOT_SUCCESS"])

    def test_required_check_missing(self):
        exp = synth_exp(required_checks=["ci", "lint"])
        ev = synth_ev()  # 只有 ci
        v = self.check(self.run_cli(exp, ev),
                       EXIT_REJECT, "REJECT", reasons_in=["REQUIRED_CHECK_MISSING"])
        # 实现将单字段 detail 折叠为标量：缺失的 check 名即 detail
        self.assertEqual(v["reason_details"].get("REQUIRED_CHECK_MISSING"), "lint")

    def test_check_in_progress_null_conclusion(self):
        ev = synth_ev(**{"head_checks": {"checks": [
            {"name": "ci", "status": "in_progress", "conclusion": None}]}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["CHECK_NOT_SUCCESS"])

    def test_check_completed_failure(self):
        ev = synth_ev(**{"head_checks": {"checks": [
            {"name": "ci", "status": "completed", "conclusion": "failure"}]}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["CHECK_NOT_SUCCESS"])

    def test_check_completed_conclusion_absent(self):
        ev = synth_ev(**{"head_checks": {"checks": [
            {"name": "ci", "status": "completed"}]}})  # 无 conclusion 键 → null
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["CHECK_NOT_SUCCESS"])

    def test_check_duplicate_names(self):
        ev = synth_ev(**{"head_checks": {"checks": [
            {"name": "ci", "status": "completed", "conclusion": "success"},
            {"name": "ci", "status": "completed", "conclusion": "failure"}]}})
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_REJECT, "REJECT", reasons_in=["CHECK_DUPLICATE"])

    def test_required_checks_unspecified(self):
        exp = synth_exp(required_checks=[])
        self.check(self.run_cli(exp, synth_ev()),
                   EXIT_UNKNOWN, "UNKNOWN", reasons_in=["REQUIRED_CHECKS_UNSPECIFIED"])

    # ---- 11. 新鲜度 ------------------------------------------------------------------------------

    def test_evidence_time_invalid_future(self):
        """collected_at 晚于注入时钟 360s（>300s 容忍）→ UNKNOWN EVIDENCE_TIME_INVALID。"""
        ev = synth_ev(collected_at="2026-10-04T12:11:00Z")
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_UNKNOWN, "UNKNOWN", reasons_in=["EVIDENCE_TIME_INVALID"])

    def test_evidence_stale(self):
        """age=2100s > max_age=900 → UNKNOWN EVIDENCE_STALE。"""
        ev = synth_ev(collected_at="2026-10-04T11:30:00Z")
        self.check(self.run_cli(synth_exp(), ev),
                   EXIT_UNKNOWN, "UNKNOWN", reasons_in=["EVIDENCE_STALE"])

    def test_reject_priority_over_unknown(self):
        """同时存在 REJECT 级违规（HEAD_MISMATCH）与 UNKNOWN 级过期 → 整体 REJECT。

        只偏差 evidence 侧 pr.head_sha，避免连带 REVIEW/CHECKS 的 head mismatch。
        """
        ev = synth_ev(collected_at="2026-10-04T11:30:00Z",
                      **{"pr": {"head_sha": SHA_OTHER}})
        v = self.check(self.run_cli(synth_exp(), ev), EXIT_REJECT, "REJECT")
        self.assertEqual(set(v["reasons"]), {"HEAD_MISMATCH", "EVIDENCE_STALE"})

    # ---- 12. 消费者绑定 -------------------------------------------------------------------------

    def test_evidence_sha256_single_field_binding(self):
        """两份 evidence 只差一个（被忽略的）字段 → 判定同为 PASS 但 sha256 不同。"""
        ev_a = synth_ev()
        ev_b = synth_ev(note="variant-b")
        va = self.check(self.run_cli(synth_exp(), ev_a, ev_name="evidence-a.json"),
                        EXIT_PASS, "PASS")
        vb = self.check(self.run_cli(synth_exp(), ev_b, ev_name="evidence-b.json"),
                        EXIT_PASS, "PASS")
        self.assertNotEqual(va["inputs"]["evidence_sha256"],
                            vb["inputs"]["evidence_sha256"])
        self.assertEqual(va["inputs"]["expectations_sha256"],
                         vb["inputs"]["expectations_sha256"])

    def test_determinism_same_inputs(self):
        """同输入两次运行 → 除 generated_at_utc 外 verdict 完全一致（含 reasons 顺序）。"""
        first = self.run_cli(synth_exp(), synth_ev(), exp_name="d1.json", ev_name="e1.json")
        second = self.run_cli(synth_exp(), synth_ev(), exp_name="d2.json", ev_name="e2.json")
        self.assertEqual(first.returncode, second.returncode, EXIT_PASS)
        v1, v2 = json.loads(first.stdout), json.loads(second.stdout)
        g1 = v1.pop("generated_at_utc")
        g2 = v2.pop("generated_at_utc")
        self.assertEqual(v1, v2)
        self.assertTrue(g1 and g2)

    def test_expectations_head_pinning(self):
        """消费方改钉 expected_head → HEAD_MISMATCH，且 verdict 回显新 head。"""
        exp = synth_exp(expected_head="9" * 40)
        v = self.check(self.run_cli(exp, synth_ev()),
                       EXIT_REJECT, "REJECT", reasons_in=["HEAD_MISMATCH"])
        self.assertEqual(v["expected_head"], "9" * 40)

    def test_verdict_echoes_expected_values(self):
        v = self.check(self.run_cli(synth_exp(), synth_ev()), EXIT_PASS, "PASS")
        self.assertEqual(v["expected_head"], SHA_HEAD)
        self.assertEqual(v["expected_base"], SHA_BASE)

    # ---- 13. 不泄漏 ---------------------------------------------------------------------------

    def test_no_leak_unknown_fields_still_pass(self):
        """多余自由文本/token 字段被忽略且不回显；判定仍 PASS（前向兼容）。"""
        ev = synth_ev(title="<script>alert(1)</script>", token="ghp_TESTSECRET123")
        proc = self.run_cli(synth_exp(), ev)
        self.check(proc, EXIT_PASS, "PASS", reasons_exact=[])
        for secret in ("<script>alert(1)</script>", "ghp_TESTSECRET123"):
            self.assertNotIn(secret, proc.stdout)
            self.assertNotIn(secret, proc.stderr)

    def test_no_leak_blockers_free_text(self):
        """blockers 自由文本只回显计数，内容不进入 stdout/stderr。"""
        marker = "SECRET-BLOCKER-FREETEXT-9f3a"
        ev = synth_ev(**{"review": {"blockers": [marker]}})
        proc = self.run_cli(synth_exp(), ev)
        v = self.check(proc, EXIT_REJECT, "REJECT", reasons_in=["REVIEW_BLOCKERS"])
        self.assertNotIn(marker, proc.stdout)
        self.assertNotIn(marker, proc.stderr)
        self.assertEqual(v["reason_details"].get("REVIEW_BLOCKERS"), 1)

    # ---- 14. 源码卫生 ---------------------------------------------------------------------------

    def test_source_hygiene(self):
        """被测 CLI 源码：无网络/subprocess/os.system/环境变量读取。"""
        with open(CLI_PATH, "r", encoding="utf-8") as fh:
            src = fh.read()
        for forbidden in ("subprocess", "socket", "urllib", "requests",
                          "os.system", "os.popen", "environ", "os.exec", "os.spawn"):
            self.assertNotIn(forbidden, src, msg="源码包含禁用符号 %r" % forbidden)
        # import 白名单：全部 import 只能来自标准库允许集合
        imported = set()
        for m in re.finditer(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", src, re.MULTILINE):
            imported.add(m.group(1).split(".")[0])
        self.assertTrue(imported)
        self.assertEqual(imported - {"__future__", "argparse", "hashlib", "json",
                                     "re", "sys", "datetime"}, set(),
                         msg="发现白名单之外的 import: %r" % imported)

    # ---- 15. 无副作用 / --out ---------------------------------------------------------------------

    def test_no_side_effects_without_out(self):
        """临时 cwd 内运行（无 --out）不产生任何新文件。"""
        workdir = os.path.join(self.tmpdir, "cwd")
        os.makedirs(workdir)
        self.assertEqual(os.listdir(workdir), [])
        proc = self.run_cli(synth_exp(), synth_ev(), cwd=workdir)
        self.assertEqual(proc.returncode, EXIT_PASS)
        self.assertEqual(os.listdir(workdir), [])

    def test_out_file_matches_stdout(self):
        out_path = os.path.join(self.tmpdir, "verdict.json")
        proc = self.run_cli(synth_exp(), synth_ev(), out=out_path)
        self.assertEqual(proc.returncode, EXIT_PASS)
        self.assertTrue(os.path.isfile(out_path))
        with open(out_path, "rb") as fh:
            written = fh.read()
        self.assertEqual(written, proc.stdout.encode("utf-8"))
        self.assertEqual(json.loads(written.decode("utf-8"))["decision"], "PASS")

    # ---- 16. 退出码精确保留（argparse 用法错误 = 2） ------------------------------------------------

    def test_exit_code_2_usage_error(self):
        cmd = [sys.executable, CLI_PATH, "--expectations",
               os.path.join(self.tmpdir, "expectations.json")]
        self._write_input(synth_exp(), "expectations.json")
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=15, cwd=self.tmpdir)
        self.assertEqual(proc.returncode, EXIT_USAGE)
        self.assertTrue(proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
