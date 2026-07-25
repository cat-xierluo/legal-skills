#!/usr/bin/env python3
"""harness_failure_audit 的去具体化 bad/good twin 回归。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from harness_failure_audit import audit_candidate, audit_collection
from instruction_stability_gate import static_assessment


SCRIPT = SCRIPTS_DIR / "harness_failure_audit.py"
INSTRUCTION_GATE = SCRIPTS_DIR / "instruction_stability_gate.py"


class HarnessFailureAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write(self, root: Path, relative: str, text: str) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def make_bad(self, name: str = "bad-curator") -> Path:
        root = self.root / name
        root.mkdir()
        self.write(
            root,
            "SKILL.md",
            "---\nname: bad-curator\n---\n"
            "扫描完成后更新 state.json 的 last_scan_at 和 history。\n"
            "自适应阈值必须使用基线 × multiplier，监控文件全部由 config 驱动。\n",
        )
        self.write(
            root,
            "scripts/lib/common.sh",
            'SKILL_ROOT="$(pwd)"\nREPO_ROOT="${REPO_ROOT:-$PWD}"\n'
            'STATE_FILE="$SKILL_ROOT/state.json"\n'
            '_CFG="$(awk -f yaml-flatten.awk "$CONFIG" 2>/dev/null || true)"\n'
            "emit_result() {\n"
            "  printf '{\"severity\":\"%s\",\"message\":\"%s\"}\\n' \"$1\" \"$2\"\n"
            "}\n",
        )
        self.write(
            root,
            "scripts/scan.sh",
            "#!/usr/bin/env bash\n"
            "while [ $# -gt 0 ]; do\n"
            " case \"$1\" in\n"
            "   --repo) REPO=\"$2\"; shift 2 ;;\n"
            "   *) shift ;;\n"
            " esac\n"
            "done\n"
            "run_checker() { bash scripts/lib/check-one.sh; }\n"
            "{ run_checker; } > \"$RESULTS\" 2>&1 || true\n"
            "while read -r row; do echo \"$row\"; done < <(run_checker)\n"
            'print_pass "全部检查通过"\n',
        )
        self.write(
            root,
            "scripts/first-baseline.sh",
            "#!/usr/bin/env bash\n"
            "declare -A files=([\"docs/TASKS.md\"]=\"docs/TASKS.md\")\n"
            "active=$(grep -cE '^### ISS-[0-9]+' \"$TASKS\" || echo 0)\n",
        )
        self.write(
            root,
            "scripts/maintenance-pr.sh",
            "#!/usr/bin/env bash\n"
            "scan_output=$(bash scripts/scan.sh 2>&1 || true)\n"
            "count=$(printf '%s' \"$scan_output\" | grep -c 'hard' || echo 0)\n"
            'git -C "$REPO_ROOT" checkout -b chore/demo\n'
            "# trim progress log entries，保留最近 5 条记录\n"
            "awk '/trim/ { next } { print }' \"$TASKS\" > \"$tmpfile\"\n"
            'mv "$tmpfile" "$TASKS"\n'
            'git -C "$REPO_ROOT" commit -m maintenance\n'
            'git -C "$REPO_ROOT" push origin chore/demo\n'
            "gh pr create --base main --head chore/demo || print_warn failed\n"
            'print_pass "PR 已创建"\n',
        )
        self.write(
            root,
            "scripts/lib/check-one.sh",
            "#!/usr/bin/env bash\n"
            'PATTERN="$(cfg_pattern)"\n'
            'grep -cE "$PATTERN" "$TARGET" || true\n',
        )
        self.write(
            root,
            "evals/run-evals.sh",
            "#!/usr/bin/env bash\nout=$(bash scripts/scan.sh 2>&1 || true)\n"
            'grep -q "severity" <<< "$out"\n',
        )
        return root

    def make_good(self, name: str = "good-curator") -> Path:
        root = self.root / name
        root.mkdir()
        self.write(
            root,
            "SKILL.md",
            "---\nname: good-curator\n---\n"
            "运行确定性检查器；任何配置错误或 checker 失败必须非零退出。\n",
        )
        self.write(
            root,
            "scripts/scan.py",
            "import argparse\nimport json\nfrom pathlib import Path\n"
            "p=argparse.ArgumentParser()\np.add_argument('--repo', required=True)\n"
            "args=p.parse_args()\n"
            "state=Path(args.repo)/'.local'/'state.json'\n"
            "print(json.dumps({'severity':'ok','state':str(state)}))\n",
        )
        self.write(
            root,
            "tests/test_scan.py",
            "import subprocess\n"
            "result=subprocess.run(['python3','scripts/scan.py','--repo','.'])\n"
            "assert result.returncode == 0\n",
        )
        return root

    def test_bad_fixture_hits_all_concrete_failure_families(self) -> None:
        report = audit_candidate(self.make_bad())
        ids = {item["id"] for item in report["findings"]}
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            {
                "HFA-001",
                "HFA-002",
                "HFA-003",
                "HFA-004",
                "HFA-005",
                "HFA-006",
                "HFA-007",
                "HFA-008",
                "HFA-009",
                "HFA-010",
                "HFA-011",
                "HFA-012",
                "HFA-013",
                "HRA-001",
                "HRA-002",
            }.issubset(ids),
            ids,
        )
        for finding in report["findings"]:
            self.assertTrue(finding["file"])
            self.assertGreater(finding["line"], 0)
            self.assertTrue(finding["evidence"])
            self.assertTrue(finding["impact"])
            self.assertTrue(finding["recommendation"])

    def test_good_twin_does_not_trigger(self) -> None:
        root = self.make_good()
        self.write(
            root,
            "scripts/lib/classify.sh",
            "#!/usr/bin/env bash\n"
            "case \"$severity\" in hard) exit 1 ;; *) continue ;; esac\n"
            "printf '%s' \"$results\" | grep severity | while read -r row; do echo \"$row\"; done\n"
            "printf '%s' \"$scan_output\" | grep -c hard\n"
            "do_thing || print_warn failed\n"
            "exit 1\n"
            'print_pass "已完成"\n'
            "python3 record.py 2>/dev/null || true\n"
            "verify_json=$(printf '%s\\n' \"$checks\" | jq -R . | jq -s .)\n"
            "echo 'bypass permissions on'\n"
            "command || echo '无'\n"
            "\n"
            "echo '=== 已完成待通知 ==='\n"
            "# rewrite a generated document without bounded record pruning\n"
            "printf '%s' \"$document\" > \"$output\"\n",
        )
        self.write(
            root,
            "scripts/safe-push.sh",
            "#!/usr/bin/env bash\n"
            "# check-outgoing-identities: expected-email and author/committer guard\n"
            "git push origin HEAD\n",
        )
        self.write(
            root,
            "scripts/test-safe-push.sh",
            "#!/usr/bin/env bash\n"
            "git push origin fixture\n"
            "cat /tmp/test.out /tmp/test.err >&2 || true\n"
            "tmux kill-session -t fixture 2>/dev/null || true\n"
            "git worktree remove --force /tmp/fixture 2>/dev/null || true\n",
        )
        self.write(
            root,
            "scripts/smoke-git.sh",
            "#!/usr/bin/env bash\ngit commit -m fixture\n",
        )
        self.write(
            root,
            "scripts/temp-clone.sh",
            "#!/usr/bin/env bash\n"
            'tmp="$(mktemp -d)"\n'
            'cd "$tmp"\n'
            "git init\n"
            "git checkout main\n",
        )
        report = audit_candidate(root)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["findings"], [])

    def test_real_shaped_yaml_parser_failure_is_not_silenced(self) -> None:
        root = self.make_good("yaml-parser")
        self.write(
            root,
            "scripts/lib/common.sh",
            "#!/usr/bin/env bash\n"
            '_CFG_FLAT="$(awk -f "$LIB/yaml-flatten.awk" "$CONFIG_FILE" '
            '2>/dev/null || true)"\n',
        )
        report = audit_candidate(root)
        matches = [item for item in report["findings"] if item["id"] == "HFA-009"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["file"], "scripts/lib/common.sh")

    def test_batch_discovery_excludes_archive_and_summarizes(self) -> None:
        self.make_bad()
        self.make_good()
        archived = self.root / "archive" / "old"
        archived.mkdir(parents=True)
        self.write(archived, "SKILL.md", "---\nname: old\n---\n")
        report = audit_collection(self.root)
        self.assertEqual(report["summary"]["skills"], 2)
        self.assertEqual(report["summary"]["failed_skills"], 1)
        self.assertEqual([item["skill"] for item in report["skills"]], ["bad-curator", "good-curator"])

    def test_empty_batch_is_blocked_not_passed(self) -> None:
        command = [
            sys.executable,
            str(SCRIPT),
            "batch",
            "--root",
            str(self.root),
        ]
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("未发现任何 SKILL.md", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_json_and_exit_code_are_stable(self) -> None:
        candidate = self.make_bad()
        command = [
            sys.executable,
            str(SCRIPT),
            "audit",
            "--candidate-root",
            str(candidate),
        ]
        first = subprocess.run(command, text=True, capture_output=True, check=False)
        second = subprocess.run(command, text=True, capture_output=True, check=False)
        self.assertEqual(first.returncode, 1)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(json.loads(first.stdout)["status"], "FAIL")

    def test_assess_combines_isg_and_concrete_findings(self) -> None:
        candidate = self.make_bad()
        result = subprocess.run(
            [
                sys.executable,
                str(INSTRUCTION_GATE),
                "assess",
                "--candidate-root",
                str(candidate),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout.splitlines()[0])
        ids = {item["id"] for item in report["findings"]}
        self.assertIn("ISG-001", ids)
        self.assertIn("HFA-001", ids)
        self.assertIn("HRA-001", ids)

    def test_history_svg_discussion_does_not_trigger_visual_modality(self) -> None:
        root = self.make_good("governance")
        self.write(
            root,
            "TASKS.md",
            "历史：曾检查 SVG figures、颜色、位置和重叠问题。\n",
        )
        report = static_assessment(root)
        self.assertNotIn("ISG-002", {item["id"] for item in report["findings"]})

    def test_normative_svg_producer_still_triggers_visual_modality(self) -> None:
        root = self.root / "svg-producer"
        root.mkdir()
        self.write(
            root,
            "SKILL.md",
            "---\nname: svg-producer\n---\n"
            "必须检查 SVG 的颜色、定位和重叠，并验证真实渲染结果。\n",
        )
        report = static_assessment(root)
        self.assertIn("ISG-002", {item["id"] for item in report["findings"]})


if __name__ == "__main__":
    unittest.main()
