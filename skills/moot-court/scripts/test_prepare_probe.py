#!/usr/bin/env python3
"""prepare_probe.py 的代表性回归：经真实 CLI 构造合成 run，只验证协议与可见范围。

不调用任何外部模型，不用字符串包含关系自报法律正确性。
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent
CLERK = SCRIPTS / "clerk.py"
PREPARE = SCRIPTS / "prepare_probe.py"
REVIEWER_ASSET = SCRIPTS.parent / "assets" / "semantic-probe-reviewer.json"

MANIFEST = {"documents": [
    {"id": "P-001", "title": "合成公开材料", "locator": "合成案卷-公开件",
     "text": "合成公开事实描述，用于验证公开材料对全部角色可见。", "visible_to": ["all"]},
    {"id": "D-001", "title": "合成被告私有材料", "locator": "合成案卷-被告卷",
     "text": "合成私有内容，仅原告角色在本轮可见，用于验证角色过滤。", "visible_to": ["plaintiff"]},
    {"id": "D-004", "title": "合成被告私有材料", "locator": "合成案卷-被告卷",
     "text": "合成私有内容，仅被告角色可见，是可见范围标靶。", "visible_to": ["defendant"]},
]}


def run_cli(script, *args):
    return subprocess.run([sys.executable, "-B", str(script), *args],
                          capture_output=True, text=True, timeout=120, check=False)


def snapshot(root):
    """记录运行目录全部文件内容，用于验证探针不污染 run。"""
    state = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            state[str(path.relative_to(root))] = path.read_text(encoding="utf-8")
    return state


class PrepareProbeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="probe-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.run_dir = self.tmp / "hearing"
        self.manifest = self.tmp / "manifest.json"
        self.manifest.write_text(json.dumps(MANIFEST, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
        self.addCleanup(self.manifest.unlink, missing_ok=True)
        init = run_cli(CLERK, "--run", str(self.run_dir), "init",
                       "--manifest", str(self.manifest), "--case-type", "civil", "--max-turns", "6")
        self.assertEqual(init.returncode, 0, init.stderr)

    def dispatch(self, role, issue="合成争点", prompt="合成任务：请就本轮争点作角色发言。"):
        return run_cli(CLERK, "--run", str(self.run_dir), "dispatch",
                       "--role", role, "--issue", issue, "--stage", "evidence", "--prompt", prompt)

    def prepare(self, output_name, run_dir=None):
        output = self.tmp / output_name
        finished = run_cli(PREPARE, "--run", str(run_dir or self.run_dir), "--output", str(output))
        return finished, output

    def test_three_role_filtering_and_no_answer_leak(self):
        """三角色各自只拿本角色材料，且 packet 不含答案、标靶或清单路径。"""
        expectations = {"plaintiff": {"P-001", "D-001"}, "defendant": {"P-001", "D-004"},
                        "judge": {"P-001"}}
        for role, expected in expectations.items():
            with self.subTest(role=role):
                self.assertEqual(self.dispatch(role).returncode, 0)
                finished, output = self.prepare(f"probe-{role}.json")
                self.assertEqual(finished.returncode, 0, finished.stderr)
                payload = json.loads(output.read_text(encoding="utf-8"))
                ids = {doc["id"] for doc in payload["documents"]}
                self.assertEqual(ids, expected)
                for doc in payload["documents"]:
                    self.assertEqual(doc["visible_to"] in (["all"], [role]), True)
                text = output.read_text(encoding="utf-8")
                for banned in ("D-004" if role != "defendant" else "D-001",):
                    if banned not in expectations[role]:
                        self.assertNotIn(banned, text)
                self.assertNotIn(str(self.manifest), text)
                self.assertNotIn("manifest.json", text)
                self.assertNotIn("评审", text)
                # 提交结构原样保留，宿主读 output 即可生成提交
                self.assertEqual(set(payload["submission_template"]),
                                 {"schema_version", "run_id", "turn_id", "role", "material_version",
                                  "read_through", "responds_to", "body", "citations"})
                self.assertEqual(payload["submission_template"]["turn_id"], payload["turn_id"])
                self.assertEqual(payload["submission_template"]["role"], role)
                self.assertEqual(payload["submission_template"]["run_id"], payload["assignment"]["run_id"])
                self.assertEqual(payload["assignment"]["issue"], "合成争点")
                self.assertNotIn(str(self.run_dir), text)
                # 不含复核答案资产
                self.assertNotIn(REVIEWER_ASSET.name, text)
                self.assertNotIn("B1", text)
                # 取消后进入下一角色
                self.assertEqual(run_cli(CLERK, "--run", str(self.run_dir), "cancel",
                                         "--reason", "合成演练轮次结束").returncode, 0)

    def test_reviewer_asset_never_loaded_by_tool(self):
        """工具不打开复核答案资产；资产中的标靶与评分口径不进 packet。"""
        source = PREPARE.read_text(encoding="utf-8")
        # 资产名只允许作为禁止标记出现一次（fail-closed 自检），不得作为读取路径或键。
        self.assertEqual(source.count(REVIEWER_ASSET.stem), 1)
        self.assertIn("FORBIDDEN_MARKERS", source)
        self.assertNotIn("REVIEWER_ASSET", source)
        self.assertNotIn("assets", source)
        self.assertNotIn('read_text', source)
        self.assertNotIn('json.load(', source)
        self.assertTrue(REVIEWER_ASSET.is_file())
        asset = json.loads(REVIEWER_ASSET.read_text(encoding="utf-8"))
        self.assertIn("semantic_boundaries", asset)
        self.assertEqual(self.dispatch("judge").returncode, 0)
        finished, output = self.prepare("probe-asset.json")
        self.assertEqual(finished.returncode, 0, finished.stderr)
        text = output.read_text(encoding="utf-8")
        for value in ("D-004", "scoring_steps", "semantic_boundaries", "expected_use"):
            self.assertNotIn(value, text)

    def test_refuses_overwrite_and_leaves_file_intact(self):
        self.assertEqual(self.dispatch("plaintiff").returncode, 0)
        finished, output = self.prepare("probe-overwrite.json")
        self.assertEqual(finished.returncode, 0, finished.stderr)
        original = output.read_text(encoding="utf-8")
        again, _ = self.prepare("probe-overwrite.json")
        self.assertNotEqual(again.returncode, 0)
        self.assertNotIn("Traceback", again.stderr)
        self.assertIn("已存在", again.stderr)
        self.assertEqual(output.read_text(encoding="utf-8"), original)

    def test_refuses_without_active_dispatch(self):
        finished, output = self.prepare("probe-noactive.json")
        self.assertNotEqual(finished.returncode, 0)
        self.assertNotIn("Traceback", finished.stderr)
        self.assertFalse(output.exists())
        self.assertEqual(self.dispatch("plaintiff").returncode, 0)
        self.assertEqual(run_cli(CLERK, "--run", str(self.run_dir), "cancel",
                                 "--reason", "合成演练轮次结束").returncode, 0)
        after, _ = self.prepare("probe-noactive.json")
        self.assertNotEqual(after.returncode, 0)
        self.assertNotIn("Traceback", after.stderr)

    def test_missing_run_and_missing_dir(self):
        missing, output = self.prepare("probe-missing.json", run_dir=self.tmp / "not-there")
        self.assertNotEqual(missing.returncode, 0)
        self.assertNotIn("Traceback", missing.stderr)
        self.assertIn("不存在", missing.stderr)
        self.assertFalse(output.exists())
        nested = self.tmp / "no-such-dir" / "probe.json"
        failed, _ = self.prepare("probe-missing.json")
        self.assertNotEqual(failed.returncode, 0)
        self.assertNotIn("Traceback", failed.stderr)
        self.assertFalse(nested.exists())
        result = run_cli(PREPARE, "--run", str(self.run_dir), "--output", str(nested))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)

    def test_run_untouched_across_probes(self):
        for role in ("plaintiff", "defendant", "judge"):
            self.assertEqual(self.dispatch(role).returncode, 0)
            # 只在探针调用前后取快照：dispatch/cancel 本身会合法增加事件。
            before = snapshot(self.run_dir)
            finished, _ = self.prepare(f"probe-clean-{role}.json")
            self.assertEqual(finished.returncode, 0, finished.stderr)
            after = snapshot(self.run_dir)
            self.assertEqual(set(after) - set(before), set(), f"探针在 run 内新增了文件：{role}")
            for name in before:
                self.assertEqual(after[name], before[name], f"探针改动了运行文件：{name}")
            self.assertFalse((self.run_dir / "transcript.md").exists())
            self.assertEqual(run_cli(CLERK, "--run", str(self.run_dir), "cancel",
                                     "--reason", "合成演练轮次结束").returncode, 0)
        events = sorted((self.run_dir / "events").glob("*.json"))
        self.assertEqual(len(events), 7)
        self.assertEqual([p.name for p in events],
                         [f"{n:06d}.json" for n in range(1, 8)])
        # 探针输出可被书记员接受，说明协议字段仍然真实可用
        self.assertEqual(self.dispatch("plaintiff").returncode, 0)
        finished, output = self.prepare("probe-commit.json")
        self.assertEqual(finished.returncode, 0, finished.stderr)
        payload = json.loads(output.read_text(encoding="utf-8"))
        submission = dict(payload["submission_template"])
        submission["body"] = "合成发言正文，仅用于验证提交结构可被接受。"
        submission["citations"] = ["P-001"]
        draft = self.tmp / "submission.json"
        draft.write_text(json.dumps(submission, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        committed = run_cli(CLERK, "--run", str(self.run_dir), "commit", "--submission", str(draft))
        self.assertEqual(committed.returncode, 0, committed.stderr)

    def test_broken_run_reports_clean_error(self):
        broken = self.tmp / "broken"
        (broken / "events").mkdir(parents=True)
        (broken / "events" / "000001.json").write_text("{}", encoding="utf-8")
        finished, output = self.prepare("probe-broken.json", run_dir=broken)
        self.assertNotEqual(finished.returncode, 0)
        self.assertNotIn("Traceback", finished.stderr)
        self.assertFalse(output.exists())
        self.assertEqual(snapshot(broken), snapshot(broken))


if __name__ == "__main__":
    unittest.main(verbosity=2)
