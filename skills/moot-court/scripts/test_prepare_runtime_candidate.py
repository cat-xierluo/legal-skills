#!/usr/bin/env python3
"""prepare_runtime_candidate.py 回归：真实 CLI、允许/排除集、hash 复算与拒绝路径。

正常与拒绝路径使用 `python3 -B` 子进程；写入中断用被测 main 的 fsync 故障注入，
核对真实文件而非自报，不联网。
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

SCRIPT = Path(__file__).with_name("prepare_runtime_candidate.py")
REPO_SKILL = Path(__file__).resolve().parent.parent

DEV_PARAGRAPH = ("开发验证命令：`python3 scripts/test_clerk.py`；"
                 "合成案例与前向评估入口见 [验证样例](references/evaluation.md)；"
                 "盲评见[盲评探针](references/blind-probe.md)。\n")


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *map(str, args)],
        capture_output=True, text=True)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_source(tmp):
    """最小合成源：结构、引用与投影语义和生产 Skill 一致。"""
    source = tmp / "moot-court"
    refs = {
        "checklist.md": "# 核对\n",
        "civil-hearing.md": "# 民事闭环\n\n[书记员](clerk-protocol.md)\n",
        "clerk-protocol.md": "# 书记员协议\n\n[回合](drill.md)\n",
        "criminal-hearing.md": "# 刑事闭环\n\n[方案](procedure-profiles.md)\n",
        "drill.md": "# 调度\n\n[信息模型](information-model.md)\n",
        "fixed-role-hearing-audit.md": "# 固定角色审计\n",
        "information-model.md": "# 信息模型\n",
        "intake.md": "# 材料准备\n\n案卷格式见 "
                    "[civil](../assets/civil-case.example.json)。\n",
        "procedure-profiles.md": "# 程序方案\n\n方法见 [研究](research-methods.md)\n",
        "research-methods.md": "# 研究方法\n\n[调度](drill.md)\n",
        "review-rubric.md": "# 复核标准\n\n方法见 [研究](research-methods.md)\n",
        "role-profiles.md": "# 角色模板\n",
        "runtime-adapters.md": "# Runtime 适配\n\n[门禁](runtime-validation.md)\n",
        "runtime-validation.md": "# 分级验证\n\n[闭环](civil-hearing.md)\n\n"
                                 "> 使用指定路径的moot-court技能，产物放指定的全新临时目录。\n",
        "templates.md": "# 交付模板\n",
    }
    for name, text in refs.items():
        write(source / "references" / name, text)
    write(source / "scripts" / "audit_fixed_role_hearing.py", "# fixed audit\n")
    write(source / "scripts" / "audit_workbuddy_trace.py", "# workbuddy audit\n")
    write(source / "scripts" / "clerk.py", "# clerk\n")
    write(source / "scripts" / "presubmit_check.py", "# presubmit\n")
    write(source / "assets" / "civil-case.example.json", '{"documents": []}\n')
    write(source / "assets" / "criminal-case.example.json", '{"documents": []}\n')
    write(source / "LICENSE.txt", "CC-BY-NC\n")
    write(source / "SKILL.md",
          "# moot-court\n\n先读 [民事闭环](references/civil-hearing.md) "
          "与[协议](references/clerk-protocol.md#权威记录与目录)。\n\n"
          "脚本运行 `python3 scripts/clerk.py`。\n\n" + DEV_PARAGRAPH)
    # 永不带入的干扰项
    write(source / "CHANGELOG.md",
          "# 变更\n\n协议见 [blind](references/blind-probe.md)\n")
    write(source / "TASKS.md", "# 任务\n")
    write(source / "DECISIONS.md", "# 决策\n")
    write(source / "archive" / "old-run.md", "# 旧产物\n")
    write(source / "references" / "evaluation.md", "# 验证样例\n答案在这里\n")
    write(source / "references" / "blind-probe.md", "# 盲评\n答案在这里\n")
    write(source / "scripts" / "test_clerk.py", "# test\n")
    write(source / "scripts" / "test_presubmit_check.py", "# test\n")
    write(source / "scripts" / "test_prepare_probe.py", "# test\n")
    write(source / "scripts" / "test_index_claude_trace.py", "# test\n")
    write(source / "scripts" / "test_audit_fixed_role_hearing.py", "# test\n")
    write(source / "scripts" / "test_audit_workbuddy_trace.py", "# test\n")
    write(source / "scripts" / "index_claude_trace.py", "# indexer\n")
    write(source / "scripts" / "prepare_probe.py", "# probe\n")
    write(source / "assets" / "semantic-probe-reviewer.json", '{"answer": "x"}\n')
    write(source / "assets" / "claude-stream.example.jsonl", "{}\n")
    return source


def make_inputs(tmp, task_text=None):
    manifest = tmp / "case-materials.json"
    write(manifest, json.dumps({"documents": [{
        "id": "D-001", "title": "合同", "locator": "第1页",
        "text": "总价10万元。", "visible_to": ["all"]}]}, ensure_ascii=False))
    task = tmp / "runtime-task.txt"
    if task_text is None:
        task_text = ("使用 {skill_dir} 技能和 {manifest} 案卷完成通用民事闭环，"
                     "产物放入 {run_dir} 并保留证据。\n")
    write(task, task_text)
    return manifest, task


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HappyPathTest(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self._cwd)

    def test_synthetic_bundle_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            manifest, task = make_inputs(tmp)
            output = tmp / "bundle"
            before = {rel: sha(source / rel) for rel in
                      ["SKILL.md", "CHANGELOG.md", "references/evaluation.md",
                       "assets/semantic-probe-reviewer.json", "TASKS.md"]}
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", output)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)

            # 1) 顶层结构
            self.assertEqual(sorted(p.name for p in output.iterdir()),
                             ["manifest.json", "materials.json", "skill",
                              "task-source.txt", "task.md"])
            # 2) 允许集精确、排除项不带入
            actual = sorted(p.relative_to(output / "skill").as_posix()
                            for p in (output / "skill").rglob("*") if p.is_file())
            expected = sorted(["SKILL.md", "LICENSE.txt",
                               "scripts/audit_fixed_role_hearing.py",
                               "scripts/audit_workbuddy_trace.py",
                               "scripts/clerk.py", "scripts/presubmit_check.py",
                               "assets/civil-case.example.json",
                               "assets/criminal-case.example.json"] +
                              [f"references/{n}" for n in
                               ["checklist.md", "civil-hearing.md", "clerk-protocol.md",
                                "criminal-hearing.md", "drill.md",
                                "fixed-role-hearing-audit.md", "information-model.md",
                                "intake.md", "procedure-profiles.md", "research-methods.md",
                                "review-rubric.md", "role-profiles.md", "runtime-adapters.md",
                                "runtime-validation.md", "templates.md"]])
            self.assertEqual(actual, expected)
            manifest_obj = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest_obj["allowed_original_paths"], expected)
            self.assertEqual(
                manifest_obj["excluded_paths"],
                sorted(["CHANGELOG.md", "TASKS.md", "DECISIONS.md", "archive/old-run.md",
                        "references/evaluation.md", "references/blind-probe.md",
                        "scripts/test_clerk.py", "scripts/test_presubmit_check.py",
                        "scripts/test_prepare_probe.py", "scripts/test_index_claude_trace.py",
                        "scripts/test_audit_fixed_role_hearing.py",
                        "scripts/test_audit_workbuddy_trace.py",
                        "scripts/index_claude_trace.py", "scripts/prepare_probe.py",
                        "assets/semantic-probe-reviewer.json",
                        "assets/claude-stream.example.jsonl"]))
            for leaked in ("evaluation", "blind-probe", "semantic-probe-reviewer",
                           "test_clerk", "TASKS.md"):
                self.assertNotIn(leaked, (output / "skill" / "SKILL.md").read_text(encoding="utf-8"))

            # 3) 投影：只剔除开发段，其余字节保留
            skill_text = (output / "skill" / "SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn("开发验证命令", skill_text)
            self.assertIn("脚本运行 `python3 scripts/clerk.py`", skill_text)
            self.assertIn("[民事闭环](references/civil-hearing.md)", skill_text)
            projection = manifest_obj["projections"][0]
            self.assertEqual(projection["marker"], "开发验证命令：")
            self.assertEqual(projection["before_sha256"], before["SKILL.md"])
            self.assertEqual(projection["after_sha256"], sha(output / "skill" / "SKILL.md"))

            # 4) 源文件未被修改
            for rel, digest in before.items():
                self.assertEqual(sha(source / rel), digest, f"源文件被改动：{rel}")

            # 5) 三个占位符正确展开，原始任务保留
            task_md = (output / "task.md").read_text(encoding="utf-8")
            # 任务必须指向 bundle 内副本，不能指回源 Skill/源案卷，否则宿主仍可读取排除项。
            self.assertIn(str(output / "skill"), task_md)
            self.assertIn(str(output / "materials.json"), task_md)
            self.assertNotIn(str(source), task_md)
            self.assertNotIn(str(manifest), task_md)
            self.assertIn(str(output / "hearing"), task_md)
            self.assertNotIn("{skill_dir}", task_md)
            self.assertIn("{skill_dir}", (output / "task-source.txt").read_text(encoding="utf-8"))
            self.assertFalse((output / "hearing").exists())

            # 6) 摘要可复算（源/候选/输入/整清单 hash）
            for rel, digest in manifest_obj["source_readonly"]["files"].items():
                self.assertEqual(sha(source / rel), digest)
            for rel, digest in manifest_obj["candidate_files_sha256"].items():
                self.assertEqual(sha(output / "skill" / rel), digest)
            self.assertEqual(manifest_obj["inputs"]["manifest"]["sha256"], sha(manifest))
            self.assertEqual(manifest_obj["inputs"]["manifest"]["original_filename"],
                             "case-materials.json")
            self.assertEqual(manifest_obj["inputs"]["task_source"]["sha256"], sha(task))
            self.assertEqual(manifest_obj["inputs"]["task_expanded"]["sha256"],
                             sha(output / "task.md"))
            self.assertEqual(sha(output / "materials.json"), sha(manifest))
            core = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            recorded = core.pop("bundle_manifest_sha256")
            canonical = json.dumps(core, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":"))
            self.assertEqual(recorded,
                             hashlib.sha256(canonical.encode("utf-8")).hexdigest())

            # 7) 链接全部可达
            self.assertGreaterEqual(len(manifest_obj["link_check"]["checked"]), 10)

    def test_real_repo_skill_generates_consumable_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            manifest = REPO_SKILL / "assets" / "civil-case.example.json"
            task = tmp / "task.txt"
            write(task, "使用 {skill_dir} 与 {manifest} 完成七环节，产物放 {run_dir}。\n")
            output = tmp / "real-bundle"
            proc = run_cli("--skill-dir", REPO_SKILL, "--manifest", manifest,
                           "--task-file", task, "--output", output)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            manifest_obj = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest_obj["allowed_original_paths"]), 23)
            self.assertNotIn("references/evaluation.md", manifest_obj["allowed_original_paths"])
            self.assertNotIn("references/blind-probe.md", manifest_obj["allowed_original_paths"])
            self.assertIn("scripts/test_clerk.py", manifest_obj["excluded_paths"])
            self.assertIn("assets/semantic-probe-reviewer.json", manifest_obj["excluded_paths"])
            self.assertIn("CHANGELOG.md", manifest_obj["excluded_paths"])
            skill_text = (output / "skill" / "SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn("开发验证命令", skill_text)
            self.assertIn("skill-lint:constraint MC-VISIBILITY", skill_text)
            # bundle 内不存在断链：逐条真实解析
            for item in manifest_obj["link_check"]["checked"]:
                self.assertTrue((output / "skill" / item["target"]).is_file(),
                                f"{item['source']} → {item['target']}")
            # 复算候选与源 hash（源仍只读未变）
            for rel, digest in manifest_obj["candidate_files_sha256"].items():
                self.assertEqual(sha(output / "skill" / rel), digest)
            for rel, digest in manifest_obj["source_readonly"]["files"].items():
                self.assertEqual(sha(REPO_SKILL / rel), digest)


class RejectionTest(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self._cwd)

    def assert_rejected(self, proc, *needles):
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr, proc.stderr)
        for needle in needles:
            self.assertIn(needle, proc.stderr)

    def test_existing_output_rejected_caller_files_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            manifest, task = make_inputs(tmp)
            output = tmp / "bundle"
            output.mkdir()
            keeper = output / "caller-file.txt"
            write(keeper, "keep")
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", output)
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertTrue(keeper.exists())
            self.assertFalse((output / "skill").exists())

    def test_dangling_symlink_output_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            manifest, task = make_inputs(tmp)
            output = tmp / "bundle"
            output.symlink_to(tmp / "nowhere")
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", output)
            self.assert_rejected(proc, "symlink")

    def test_output_inside_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            manifest, task = make_inputs(tmp)
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", source / "build" / "bundle")
            self.assert_rejected(proc, "不得嵌在源 Skill")
            self.assertFalse((source / "build").exists())

    def test_missing_allowed_file_rejected_no_partial_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            (source / "scripts" / "presubmit_check.py").unlink()
            manifest, task = make_inputs(tmp)
            output = tmp / "bundle"
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", output)
            self.assert_rejected(proc, "允许集缺文件")
            self.assertFalse(output.exists())

    def test_allowed_source_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            outside = tmp / "outside-license.txt"
            write(outside, "CC-BY-NC\n")
            (source / "LICENSE.txt").unlink()
            (source / "LICENSE.txt").symlink_to(outside)
            manifest, task = make_inputs(tmp)
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", tmp / "bundle")
            self.assert_rejected(proc, "symlink")
            self.assertTrue(outside.exists())
            self.assertFalse((tmp / "bundle").exists())

    def test_link_escape_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            skill = source / "SKILL.md"
            text = skill.read_text(encoding="utf-8")
            skill.write_text(text.replace("[民事闭环](references/civil-hearing.md)",
                                          "[逃逸](../../../outside-secret.md)"), encoding="utf-8")
            manifest, task = make_inputs(tmp)
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", tmp / "bundle")
            self.assert_rejected(proc, "逃出 skill 目录")
            self.assertFalse((tmp / "bundle").exists())

    def test_link_to_excluded_doc_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            skill = source / "SKILL.md"
            text = skill.read_text(encoding="utf-8")
            # 在保留正文里加一条指向评测文档的链接（不在被剔除的开发段内）
            skill.write_text(text.replace("脚本运行 `python3 scripts/clerk.py`。",
                                          "样例见 [评测](references/evaluation.md)；"
                                          "脚本运行 `python3 scripts/clerk.py`。"),
                             encoding="utf-8")
            manifest, task = make_inputs(tmp)
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", tmp / "bundle")
            self.assert_rejected(proc, "evaluation.md")

    def test_missing_dev_paragraph_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            skill = source / "SKILL.md"
            skill.write_text(skill.read_text(encoding="utf-8").replace(DEV_PARAGRAPH, ""),
                             encoding="utf-8")
            manifest, task = make_inputs(tmp)
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", tmp / "bundle")
            self.assert_rejected(proc, "出现 0 次")

    def test_ambiguous_dev_paragraph_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            skill = source / "SKILL.md"
            skill.write_text(skill.read_text(encoding="utf-8") + "\n" + DEV_PARAGRAPH,
                             encoding="utf-8")
            manifest, task = make_inputs(tmp)
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", tmp / "bundle")
            self.assert_rejected(proc, "出现 2 次")

    def test_unknown_placeholder_rejected_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            manifest, task = make_inputs(
                tmp, task_text="用 {skill_dir} 和 {manifest}，产物 {run_dir}，还有 {evil_cmd}\n")
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", tmp / "bundle")
            self.assert_rejected(proc, "未定义占位符", "{evil_cmd}")
            self.assertFalse((tmp / "bundle").exists())

    def test_unknown_placeholder_allowed_and_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            manifest, task = make_inputs(
                tmp, task_text="用 {skill_dir} 和 {manifest}，产物 {run_dir}，还有 {note}\n")
            output = tmp / "bundle"
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", output,
                           "--allow-unknown-placeholders")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            manifest_obj = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest_obj["inputs"]["unknown_placeholders_kept"], ["note"])
            self.assertIn("{note}", (output / "task.md").read_text(encoding="utf-8"))

    def test_duplicate_placeholder_allowed_full_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            manifest, task = make_inputs(
                tmp, task_text="用 {skill_dir} 与 {manifest}，产物 {run_dir}，再看 {run_dir}；"
                               "规范见 {skill_dir}/SKILL.md\n")
            output = tmp / "bundle"
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", output)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            task_md = (output / "task.md").read_text(encoding="utf-8")
            self.assertEqual(task_md.count("{run_dir}"), 0)
            self.assertEqual(task_md.count("{skill_dir}"), 0)
            self.assertEqual(task_md.count(str(output / "skill")), 2)
            self.assertEqual(task_md.count(str(output / "hearing")), 2)
            bundle_obj = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            counts = {e["name"]: e["source_occurrences"]
                      for e in bundle_obj["inputs"]["placeholder_expansion"]}
            self.assertEqual(counts, {"skill_dir": 2, "manifest": 1, "run_dir": 2})

    def test_write_failure_cleans_own_files_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            manifest, task = make_inputs(tmp)
            output = tmp / "bundle"
            # 调用方先占住 skill/SKILL.md：工具 O_EXCL 写入必须失败，
            # 且只能清理自己创建的文件，绝不能碰调用方内容。
            keeper = output / "skill" / "SKILL.md"
            write(keeper, "caller content")
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", output)
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertTrue(keeper.exists())
            self.assertEqual(keeper.read_text(encoding="utf-8"), "caller content")
            for name in ("materials.json", "task-source.txt", "task.md", "manifest.json",
                         "LICENSE.txt"):
                self.assertFalse((output / name).exists(), name)
            self.assertFalse((output / "skill" / "LICENSE.txt").exists())

    def test_missing_input_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            manifest, task = make_inputs(tmp)
            proc = run_cli("--skill-dir", source, "--manifest", tmp / "nope.json",
                           "--task-file", task, "--output", tmp / "bundle")
            self.assert_rejected(proc, "不是常规文件")

    def test_relative_output_honors_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            manifest, task = make_inputs(tmp)
            workdir = tmp / "workdir"
            workdir.mkdir()
            os.chdir(workdir)
            try:
                proc = run_cli("--skill-dir", source, "--manifest", manifest,
                               "--task-file", task, "--output", "rel-bundle")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertTrue((workdir / "rel-bundle" / "manifest.json").is_file())
            finally:
                os.chdir(self._cwd)


class ClerkCompatibilityTest(unittest.TestCase):
    def test_run_dir_from_expanded_task_init_succeeds(self):
        """bundle 的 task.md 展开出的 run_dir 未预创建，书记员 init 必须能接受。"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            # 用真实 clerk.py 语义：需要一个能 init 的案卷，改用真实仓样例
            manifest, task = make_inputs(tmp)
            output = tmp / "bundle"
            proc = run_cli("--skill-dir", REPO_SKILL, "--manifest",
                           REPO_SKILL / "assets" / "civil-case.example.json",
                           "--task-file", task, "--output", output)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            task_md = (output / "task.md").read_text(encoding="utf-8")
            run_dir = str(output / "hearing")
            self.assertIn(run_dir, task_md)
            clerk = REPO_SKILL / "scripts" / "clerk.py"
            init = subprocess.run(
                [sys.executable, "-B", str(clerk), "--run", run_dir, "init",
                 "--case-type", "civil",
                 "--manifest", str(output / "materials.json")],
                capture_output=True, text=True)
            self.assertEqual(init.returncode, 0, init.stderr)
            status = subprocess.run(
                [sys.executable, "-B", str(clerk), "--run", run_dir, "status"],
                capture_output=True, text=True)
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(json.loads(status.stdout)["case_type"], "civil")

    def test_source_skill_untouched_after_repo_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            before = {p: sha(p) for p in
                      [REPO_SKILL / "SKILL.md", REPO_SKILL / "CHANGELOG.md",
                       REPO_SKILL / "scripts" / "clerk.py",
                       REPO_SKILL / "assets" / "semantic-probe-reviewer.json"]}
            manifest, task = make_inputs(tmp)
            proc = run_cli("--skill-dir", REPO_SKILL, "--manifest", manifest,
                           "--task-file", task, "--output", tmp / "bundle")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            for path, digest in before.items():
                self.assertEqual(sha(path), digest, f"源文件被改动：{path}")


class CleanupScopeTest(unittest.TestCase):
    """返修点 1：清理只碰本次登记物，绝不向未登记祖先爬升。"""

    def test_preexisting_empty_output_parent_survives_precheck_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            manifest, task = make_inputs(tmp)
            parent = tmp / "staged-parent"
            parent.mkdir()
            output = parent / "bundle"
            (source / "references" / "drill.md").unlink()
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", output)
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertTrue(parent.is_dir(), "预存空父目录被误删")
            self.assertFalse(output.exists())

    def test_preexisting_empty_output_parent_survives_write_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            manifest, task = make_inputs(tmp)
            parent = tmp / "outer-parent"
            parent.mkdir()
            output = parent / "bundle"
            (output / "skill").mkdir(parents=True)
            keeper = output / "skill" / "SKILL.md"
            keeper.write_text("caller content", encoding="utf-8")
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", output)
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertTrue(parent.is_dir(), "未登记祖先被爬升删除")
            self.assertTrue(output.is_dir())
            self.assertFalse((output / "skill" / "LICENSE.txt").exists())
            for name in ("materials.json", "task.md", "task-source.txt", "manifest.json"):
                self.assertFalse((output / name).exists(), name)

    def test_fsync_failure_cleans_created_files_and_preserves_parent(self):
        self.check_fsync_failure(keep_foreign=False)

    def test_fsync_failure_preserves_foreign_file_added_during_write(self):
        self.check_fsync_failure(keep_foreign=True)

    def check_fsync_failure(self, keep_foreign):
        spec = importlib.util.spec_from_file_location("mc_candidate_fault_probe", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            manifest, task = make_inputs(tmp)
            parent = tmp / "preexisting-empty-parent"
            parent.mkdir()
            output = parent / "bundle"
            foreign = output / "caller-added.txt"

            def fail_fsync(fd):
                self.assertTrue(output.is_dir(), "故障必须发生在本次创建 bundle 之后")
                self.assertTrue(any((output / "skill").rglob("*")),
                                "故障必须发生在实际写文件之后")
                if keep_foreign:
                    foreign.write_text("caller owned bytes", encoding="utf-8")
                raise OSError("injected fsync failure")

            error = io.StringIO()
            with mock.patch.object(module.os, "fsync", side_effect=fail_fsync):
                with contextlib.redirect_stderr(error):
                    code = module.main(["--skill-dir", str(source), "--manifest", str(manifest),
                                        "--task-file", str(task), "--output", str(output)])
            self.assertEqual(code, 2)
            self.assertIn("写入", error.getvalue())
            self.assertNotIn("Traceback", error.getvalue())
            self.assertTrue(parent.is_dir())
            if keep_foreign:
                self.assertEqual(foreign.read_text(), "caller owned bytes")
                self.assertEqual(sorted(p.name for p in output.iterdir()), ["caller-added.txt"])
            else:
                self.assertFalse(output.exists())


class SymlinkPathTest(unittest.TestCase):
    """返修点 2：显式路径与源树 symlink 的实际合同。"""

    def assert_rejected(self, proc, *needles):
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr, proc.stderr)
        for needle in needles:
            self.assertIn(needle, proc.stderr)

    def test_skill_dir_itself_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            link = tmp / "skill-link"
            link.symlink_to(source)
            manifest, task = make_inputs(tmp)
            proc = run_cli("--skill-dir", link, "--manifest", manifest,
                           "--task-file", task, "--output", tmp / "bundle")
            self.assert_rejected(proc, "--skill-dir 本身是 symlink")
            self.assertFalse((tmp / "bundle").exists())

    def test_manifest_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            real_manifest = tmp / "real-materials.json"
            write(real_manifest, '{"documents": []}')
            link_manifest = tmp / "materials-link.json"
            link_manifest.symlink_to(real_manifest)
            task = tmp / "task.txt"
            write(task, "用 {skill_dir} 与 {manifest}，产物 {run_dir}")
            proc = run_cli("--skill-dir", source, "--manifest", link_manifest,
                           "--task-file", task, "--output", tmp / "bundle")
            self.assert_rejected(proc, "--manifest")

    def test_task_file_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            real_task = tmp / "real-task.txt"
            write(real_task, "用 {skill_dir} 与 {manifest}，产物 {run_dir}")
            link_task = tmp / "task-link.txt"
            link_task.symlink_to(real_task)
            manifest = tmp / "materials.json"
            write(manifest, '{"documents": []}')
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", link_task, "--output", tmp / "bundle")
            self.assert_rejected(proc, "--task-file")

    def test_symlink_path_inside_tmpdir_system_link_still_works(self):
        # macOS 临时目录本身是 /private/var 的软链；系统级软链豁免，正常出包。
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            manifest, task = make_inputs(tmp)
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", tmp / "bundle")
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_source_internal_symlink_dir_rejected_as_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            outside = tmp / "outside-refs"
            outside.mkdir()
            for name in sorted(q.name for q in (source / "references").iterdir()):
                shutil.copy(source / "references" / name, outside / name)
            shutil.rmtree(source / "references")
            (source / "references").symlink_to(outside)
            manifest, task = make_inputs(tmp)
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", tmp / "bundle")
            self.assert_rejected(proc, "允许集缺文件")
            self.assertFalse((tmp / "bundle").exists())
            self.assertTrue(outside.is_dir(), "外部 symlink 目标被清理误删")


class RunDirBoundaryTest(unittest.TestCase):
    """返修点 3：--run-dir 越界拒绝；默认与外部合法；空 hearing 语义。"""

    def assert_rejected(self, proc, *needles):
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr, proc.stderr)
        for needle in needles:
            self.assertIn(needle, proc.stderr)

    def test_run_dir_inside_source_skill_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            manifest, task = make_inputs(tmp)
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", tmp / "bundle",
                           "--run-dir", str(source / "hearing-outside-tree"))
            self.assert_rejected(proc, "--run-dir 不得位于源 Skill")
            self.assertFalse((tmp / "bundle").exists())

    def test_run_dir_inside_bundle_skill_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            manifest, task = make_inputs(tmp)
            output = tmp / "bundle"
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", output,
                           "--run-dir", str(output / "skill" / "hearing"))
            self.assert_rejected(proc, "--run-dir 不得位于候选 skill")
            self.assertFalse(output.exists())

    def test_run_dir_equal_to_bundle_root_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            manifest, task = make_inputs(tmp)
            output = tmp / "bundle"
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", output, "--run-dir", output)
            self.assert_rejected(proc, "bundle")
            self.assertFalse(output.exists())

    def test_run_dir_inside_bundle_root_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            manifest, task = make_inputs(tmp)
            output = tmp / "bundle"
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", output,
                           "--run-dir", str(output / "outer-hearing"))
            self.assert_rejected(proc, "--run-dir 不得位于 bundle")
            self.assertFalse(output.exists())

    def test_run_dir_external_new_dir_accepted_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            manifest, task = make_inputs(tmp)
            output = tmp / "bundle"
            run_dir = tmp / "case-work" / "hearing-001"
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", output,
                           "--run-dir", str(run_dir))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn(str(run_dir), (output / "task.md").read_text(encoding="utf-8"))
            self.assertFalse(run_dir.exists(), "不得替调用方创建演练目录")
            bundle_obj = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(bundle_obj["inputs"]["run_dir_policy"]["mode"], "caller-specified")

    def test_precreated_empty_hearing_accepted_by_real_clerk(self):
        # 文档合同：clerk init 接受不存在或完全为空的目录；混入材料才拒。
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            manifest, task = make_inputs(tmp)
            output = tmp / "bundle"
            proc = run_cli("--skill-dir", REPO_SKILL, "--manifest",
                           REPO_SKILL / "assets" / "civil-case.example.json",
                           "--task-file", task, "--output", output)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            hearing = output / "hearing"
            hearing.mkdir()
            init = subprocess.run(
                [sys.executable, "-B", str(REPO_SKILL / "scripts" / "clerk.py"),
                 "--run", str(hearing), "init", "--case-type", "civil",
                 "--manifest", str(output / "materials.json")],
                capture_output=True, text=True)
            self.assertEqual(init.returncode, 0, init.stderr)
            self.assertTrue((hearing / "events").is_dir())


class MarkdownFormTest(unittest.TestCase):
    """返修点 6：图片同等核验；不支持形态 fail-closed；不误杀生产文档。"""

    def assert_rejected(self, proc, *needles):
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr, proc.stderr)
        for needle in needles:
            self.assertIn(needle, proc.stderr)

    def test_relative_image_broken_target_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            ref = source / "references" / "intake.md"
            ref.write_text(ref.read_text(encoding="utf-8") +
                           "\n![缺失流程图](../assets/diagram.png)\n", encoding="utf-8")
            manifest, task = make_inputs(tmp)
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", tmp / "bundle")
            self.assert_rejected(proc, "图片", "diagram.png")

    def test_relative_image_to_included_file_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            ref = source / "references" / "intake.md"
            ref.write_text(ref.read_text(encoding="utf-8") +
                           "\n![案卷样例](../assets/civil-case.example.json)\n",
                           encoding="utf-8")
            manifest, task = make_inputs(tmp)
            output = tmp / "bundle"
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", output)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            bundle_obj = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            kinds = {(i["kind"], i["target"]) for i in bundle_obj["link_check"]["checked"]}
            self.assertIn(("image", "assets/civil-case.example.json"), kinds)

    def test_reference_style_link_rejected_with_form_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            skill = source / "SKILL.md"
            skill.write_text(skill.read_text(encoding="utf-8") +
                             "\n参见 [协议][proto]。\n\n[proto]: references/clerk-protocol.md\n",
                             encoding="utf-8")
            manifest, task = make_inputs(tmp)
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", tmp / "bundle")
            self.assert_rejected(proc, "引用式链接")

    def test_bare_shortcut_bracket_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            ref = source / "references" / "checklist.md"
            ref.write_text(ref.read_text(encoding="utf-8") + "\n参见 [协议]。\n",
                           encoding="utf-8")
            manifest, task = make_inputs(tmp)
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", tmp / "bundle")
            self.assert_rejected(proc, "快捷链接")

    def test_footnote_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            ref = source / "references" / "checklist.md"
            ref.write_text(ref.read_text(encoding="utf-8") + "\n结论[^1]。\n\n[^1]: 说明\n",
                           encoding="utf-8")
            manifest, task = make_inputs(tmp)
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", tmp / "bundle")
            self.assert_rejected(proc, "脚注")

    def test_absolute_link_target_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            ref = source / "references" / "checklist.md"
            ref.write_text(ref.read_text(encoding="utf-8") +
                           "\n[绝对](/etc/passwd)\n", encoding="utf-8")
            manifest, task = make_inputs(tmp)
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", tmp / "bundle")
            self.assert_rejected(proc, "绝对路径目标")

    def test_brackets_in_code_fence_and_inline_code_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = make_source(tmp)
            ref = source / "references" / "templates.md"
            ref.write_text(ref.read_text(encoding="utf-8") + "\n"
                           "行内 `[占位符]` 不算链接。\n"
                           "\n```markdown\n"
                           "[围栏内引用式链接][ref]\n"
                           "\n[ref]: references/evaluation.md\n"
                           "```\n"
                           "\n<!-- [注释链接](references/blind-probe.md) -->\n",
                           encoding="utf-8")
            manifest, task = make_inputs(tmp)
            output = tmp / "bundle"
            proc = run_cli("--skill-dir", source, "--manifest", manifest,
                           "--task-file", task, "--output", output)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            bundle_obj = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            targets = {i["target"] for i in bundle_obj["link_check"]["checked"]}
            self.assertNotIn("references/evaluation.md", targets)
            self.assertNotIn("references/blind-probe.md", targets)


if __name__ == "__main__":
    unittest.main()
