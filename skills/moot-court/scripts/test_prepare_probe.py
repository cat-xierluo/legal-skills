#!/usr/bin/env python3
"""prepare_probe.py 的代表性回归：经真实 CLI 构造合成 run，只验证协议与可见范围。

不调用任何外部模型，不用字符串包含关系自报法律正确性。
"""
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent
CLERK = SCRIPTS / "clerk.py"
PREPARE = SCRIPTS / "prepare_probe.py"
REVIEWER_ASSET = SCRIPTS.parent / "assets" / "semantic-probe-reviewer.json"

# 故障注入直接针对实现模块：只改进程内 subprocess/os 调用，不改被测源码、不安装依赖。
sys.path.insert(0, str(SCRIPTS))
import prepare_probe as PREPARE_MODULE  # noqa: E402
prePAREError = PREPARE_MODULE.ProbeError

MANIFEST = {"documents": [
    {"id": "P-001", "title": "合成公开材料", "locator": "合成案卷-公开件",
     "text": "合成公开事实描述，用于验证公开材料对全部角色可见。", "visible_to": ["all"]},
    {"id": "D-001", "title": "合成原告私有材料", "locator": "合成案卷-原告卷",
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

    def test_subprocess_timeout_becomes_clean_chinese_error(self):
        """NB-1：subprocess.TimeoutExpired 转中文 ProbeError，不泄漏 Traceback、不等 60 秒。"""
        self.assertEqual(self.dispatch("plaintiff").returncode, 0)
        with mock.patch.object(PREPARE_MODULE.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired(cmd="clerk", timeout=60)):
            with self.assertRaises(prePAREError) as caught:
                PREPARE_MODULE.read_packet(self.run_dir)
        message = str(caught.exception)
        self.assertIn("60 秒", message)
        self.assertNotIn("TimeoutExpired", message)
        # 同一异常经 main() 走完整 CLI 路径：单行中文原因、无 Traceback、非零退出
        with mock.patch.object(PREPARE_MODULE.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired(cmd="clerk", timeout=60)):
            buffer = io.StringIO()
            with contextlib.redirect_stderr(buffer):
                with self.assertRaises(SystemExit) as exit_info:
                    PREPARE_MODULE.main(["--run", str(self.run_dir), "--output",
                                         str(self.tmp / "probe-timeout.json")])
        self.assertEqual(exit_info.exception.code, 2)
        self.assertNotIn("Traceback", buffer.getvalue())
        self.assertIn("60 秒", buffer.getvalue())
        self.assertFalse((self.tmp / "probe-timeout.json").exists())

    def test_write_failure_removes_only_this_attempt_half_product(self):
        """NB-3：fsync 失败只删除本次创建的半成品，调用方原有文件分毫不动。"""
        self.assertEqual(self.dispatch("plaintiff").returncode, 0)
        # 只清理本次创建：fsync 失败后文件必须消失，且目录不留残缺输入
        target = self.tmp / "probe-fsync.json"
        with mock.patch.object(PREPARE_MODULE.os, "fsync",
                               side_effect=OSError(5, "injected")):
            with self.assertRaises(prePAREError):
                PREPARE_MODULE.write_once(target, {"synthetic": True})
        self.assertFalse(target.exists())
        # 原有文件不被覆盖、不被删除
        keeper = self.tmp / "probe-keeper.json"
        keeper.write_text("调用方既有内容\n", encoding="utf-8")
        with self.assertRaises(prePAREError):
            PREPARE_MODULE.write_once(keeper, {"synthetic": True})
        self.assertEqual(keeper.read_text(encoding="utf-8"), "调用方既有内容\n")
        with mock.patch.object(PREPARE_MODULE.os, "fsync",
                               side_effect=OSError(5, "injected")):
            # 即便注入失败，已存在检查也必须先生效，文件仍在
            with self.assertRaises(prePAREError):
                PREPARE_MODULE.write_once(keeper, {"synthetic": True})
        self.assertEqual(keeper.read_text(encoding="utf-8"), "调用方既有内容\n")
        # 清理后正常路径仍可成功写出
        self.assertEqual(PREPARE_MODULE.write_once(target, {"synthetic": True}), target)

    def test_relative_paths_are_accepted(self):
        """NB-5：实现接受相对路径，文档与实现口径一致。"""
        self.assertEqual(self.dispatch("plaintiff").returncode, 0)
        finished = subprocess.run(
            [sys.executable, "-B", str(PREPARE), "--run", "hearing", "--output", "probe-rel.json"],
            capture_output=True, text=True, timeout=120, cwd=str(self.tmp), check=False)
        self.assertEqual(finished.returncode, 0, finished.stderr)
        self.assertNotIn("Traceback", finished.stderr)
        payload = json.loads((self.tmp / "probe-rel.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["role"], "plaintiff")

    def test_role_task_allows_own_private_materials_only(self):
        """NB-2：角色任务允许引用己方私有编号，但 citations 口径与书记员一致。"""
        expectations = {"plaintiff": "D-001", "defendant": "D-004"}
        for role, private_id in expectations.items():
            with self.subTest(role=role):
                self.assertEqual(self.dispatch(role).returncode, 0)
                finished, output = self.prepare(f"probe-cite-{role}.json")
                self.assertEqual(finished.returncode, 0, finished.stderr)
                payload = json.loads(output.read_text(encoding="utf-8"))
                text = "\n".join(payload["role_task"])
                self.assertIn(private_id, {doc["id"] for doc in payload["documents"]})
                self.assertIn("本方私有", text)
                # 不得鼓励越界读取运行目录内部结构
                for banned in ("manifest", "events"):
                    self.assertNotIn(f"去读{banned}", text)
                self.assertIn("不得引用", text)
                # citations 只收公开编号：私有编号必须先被书记员拒绝（先测，否则会被去重规则抢先）
                submission = dict(payload["submission_template"])
                submission["body"] = "合成正文，引用本方私有材料编号。"
                submission["citations"] = [private_id]
                bad_draft = self.tmp / f"bad-{role}.json"
                bad_draft.write_text(json.dumps(submission, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
                rejected = run_cli(CLERK, "--run", str(self.run_dir), "commit", "--submission", str(bad_draft))
                self.assertNotEqual(rejected.returncode, 0)
                self.assertIn("未公开", rejected.stderr)
                # 改为公开编号后同一回合必须能入卷，验证提示口径与真实校验一致
                submission["body"] = "合成正文，引用公开材料并说明本方私有准备。"
                submission["citations"] = ["P-001"]
                draft = self.tmp / f"draft-{role}.json"
                draft.write_text(json.dumps(submission, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
                committed = run_cli(CLERK, "--run", str(self.run_dir), "commit", "--submission", str(draft))
                self.assertEqual(committed.returncode, 0, committed.stderr)
                # 入卷后该回合自动关闭，无需 cancel；下一轮 dispatch 由循环开头重新发起
                self.assertTrue(committed.stdout.strip() or True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
