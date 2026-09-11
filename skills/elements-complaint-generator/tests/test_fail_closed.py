#!/usr/bin/env python3
"""候选件验证失败时，不得覆盖用户已有目标文件。

覆盖几类 fail-closed 场景：
1. 残留校验失败 → 不发布、不覆盖已有输出（历史回归）。
2. 未知/错位的业务字段路径 → 拒绝渲染，不发布、不覆盖、不留临时文件。
3. 未知字段的 false/0 同样拒绝（只有 None/空字符串/空容器按空值放行）。
4. --allow-unknown-fields 显式放行 → 仅该旗标下才允许发布。
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent
SAMPLE = SKILL_DIR / "tests/fixtures/09-private-lending-sample.json"


def _run_fill(elements_path: Path, output: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            "-B",
            str(SKILL_DIR / "scripts/fill_template.py"),
            "--case-type",
            "09-private-lending",
            "--elements",
            str(elements_path),
            "--output",
            str(output),
            "--layout-check",
            "docx",
            *extra,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _write_elements(directory: Path, name: str, mutate=None) -> Path:
    raw = json.loads(SAMPLE.read_text(encoding="utf-8"))
    if mutate is not None:
        mutate(raw)
    path = directory / name
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


class FailClosedPublishTests(unittest.TestCase):
    def test_residual_failure_preserves_existing_output(self):
        sentinel = b"existing-user-output\n"
        with tempfile.TemporaryDirectory(prefix="ecg-fail-closed-") as directory:
            output = Path(directory) / "existing.docx"
            output.write_bytes(sentinel)
            result = _run_fill(
                SAMPLE, output, "--verify-residual", "民事起诉状",
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(output.read_bytes(), sentinel)
            self.assertIn("旧串仍存在", result.stdout + result.stderr)

    def test_unknown_fields_fail_closed_preserves_existing_output(self):
        """未知且非空业务字段必须拒绝渲染：不覆盖已有输出、不留临时文件。"""
        sentinel = b"existing-user-output\n"
        with tempfile.TemporaryDirectory(prefix="ecg-fail-closed-") as directory:
            work = Path(directory)
            output = work / "existing.docx"
            output.write_bytes(sentinel)
            elements = _write_elements(
                work,
                "unknown-elements.json",
                mutate=lambda raw: raw["elements"].update(
                    {"神秘的附加主张": {"额外要求": "赔偿精神损失"}}
                ),
            )
            result = _run_fill(elements, output)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("未知或错位的业务字段路径", result.stderr)
            self.assertIn("神秘的附加主张.额外要求", result.stderr)
            # 正式产物原样保留，且目录里不得残留发布临时文件
            self.assertEqual(output.read_bytes(), sentinel)
            self.assertEqual(sorted(p.name for p in work.iterdir()),
                             ["existing.docx", "unknown-elements.json"])

    def test_misplaced_field_path_rejected(self):
        """合法字段名放错层级（诉讼请求.姓名）必须拒绝并打印完整路径。"""
        with tempfile.TemporaryDirectory(prefix="ecg-fail-closed-") as directory:
            work = Path(directory)
            output = work / "out.docx"
            elements = _write_elements(
                work,
                "misplaced-elements.json",
                mutate=lambda raw: raw["elements"]["诉讼请求"].update({"姓名": "张三"}),
            )
            result = _run_fill(elements, output)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("诉讼请求.姓名", result.stderr)
            self.assertFalse(output.exists())

    def test_unknown_falsy_values_rejected(self):
        """未知字段的 false/0 是明确业务输入，不得因布尔假值逃逸校验。"""
        with tempfile.TemporaryDirectory(prefix="ecg-fail-closed-") as directory:
            work = Path(directory)
            output = work / "out.docx"
            elements = _write_elements(
                work,
                "falsy-elements.json",
                mutate=lambda raw: raw["elements"]["诉讼请求"].update(
                    {"神秘开关": False, "神秘计数": 0}
                ),
            )
            result = _run_fill(elements, output)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("诉讼请求.神秘开关", result.stderr)
            self.assertIn("诉讼请求.神秘计数", result.stderr)
            self.assertFalse(output.exists())

    def test_legal_falsy_value_still_publishes(self):
        """合法路径上的 false（如放弃诉讼费用）放行不误报。"""
        with tempfile.TemporaryDirectory(prefix="ecg-fail-closed-") as directory:
            work = Path(directory)
            output = work / "out.docx"
            elements = _write_elements(
                work,
                "legal-falsy-elements.json",
                mutate=lambda raw: raw["elements"]["诉讼请求"].update(
                    {"是否主张诉讼费用": False}
                ),
            )
            result = _run_fill(elements, output)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(output.exists())

    def test_unknown_fields_escape_hatch_allows_publish(self):
        """--allow-unknown-fields 显式放行后才可发布（逃生通道可用）。"""
        with tempfile.TemporaryDirectory(prefix="ecg-fail-closed-") as directory:
            work = Path(directory)
            output = work / "out.docx"
            elements = _write_elements(
                work,
                "unknown-elements.json",
                mutate=lambda raw: raw["elements"].update({"神秘的附加主张": "测试"}),
            )
            result = _run_fill(elements, output, "--allow-unknown-fields")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(output.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
