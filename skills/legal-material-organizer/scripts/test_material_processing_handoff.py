#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
SCANNER = SKILL_ROOT / "scripts" / "scan_materials.py"
HANDOFF = SKILL_ROOT / "scripts" / "material_processing_handoff.py"
CHECKER = SKILL_ROOT / "scripts" / "check_material_manifest.py"


class MaterialProcessingHandoffTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "input"
        self.source.mkdir()
        (self.source / "sample.pdf").write_bytes(b"%PDF-1.4 synthetic")
        scan = subprocess.run(
            ["python3", str(SCANNER), str(self.source), "--no-write-md"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(scan.returncode, 0, scan.stdout + scan.stderr)
        manifests = list((self.root / ".legal-material-organizer").rglob("materials_manifest.json"))
        self.assertEqual(len(manifests), 1)
        self.manifest_path = manifests[0]

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_handoff(self, *args: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        completed = subprocess.run(
            ["python3", str(HANDOFF), *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
        return completed, payload

    def export_task(self) -> dict:
        completed, payload = self.run_handoff("export", "--manifest", str(self.manifest_path))
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(payload["task_count"], 1)
        return payload["tasks"][0]

    def write_result(self, payload: dict, name: str = "result.json") -> Path:
        path = self.root / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def check_manifest(self, path: Path | None = None) -> dict:
        completed = subprocess.run(
            ["python3", str(CHECKER), "--input", str(path or self.manifest_path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return json.loads(completed.stdout.strip().splitlines()[-1])

    def completed_result(self, output_path: Path, readability: str = "readable") -> dict:
        task = self.export_task()
        return {
            "schema_version": 1,
            "material_id": task["material_id"],
            "candidate_id": task["candidate_id"],
            "status": "completed",
            "capability": "text_extract",
            "producer": "available-document-reader",
            "output_path": str(output_path),
            "variant_kind": "clean_markdown",
            "readability_status": readability,
        }

    def test_export_is_tool_neutral_and_traceable(self) -> None:
        task = self.export_task()
        self.assertEqual(task["processing_need"], "need_ocr_or_visual")
        self.assertEqual(task["material_id"], "M-000001")
        self.assertIn("text_extract", task["acceptable_capabilities"])
        rendered = json.dumps(task, ensure_ascii=False).casefold()
        self.assertNotIn("mineru", rendered)
        self.assertNotIn("pdf-processor", rendered)

    def test_completed_result_creates_traceable_readable_variant(self) -> None:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        output = Path(manifest["work_dir"]) / "readable" / "sample.md"
        output.parent.mkdir(parents=True)
        output.write_text("合成提取文本", encoding="utf-8")
        result_path = self.write_result(self.completed_result(output))

        completed, receipt = self.run_handoff(
            "record", "--manifest", str(self.manifest_path), "--result", str(result_path)
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertTrue(receipt["changed"])
        updated = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        material = updated["materials"][0]
        self.assertEqual(material["processing_need"], "none")
        self.assertEqual(material["readability_status"], "readable")
        self.assertEqual(material["primary_readable_variant_id"], receipt["variant_id"])
        variant = next(item for item in updated["variants"] if item["variant_id"] == receipt["variant_id"])
        run = next(item for item in updated["processing_runs"] if item["run_id"] == receipt["run_id"])
        candidate = next(item for item in updated["follow_up_candidates"] if item["candidate_id"] == run["candidate_id"])
        self.assertEqual(variant["file_path"], str(output.resolve()))
        self.assertEqual(run["output_variant_id"], variant["variant_id"])
        self.assertEqual(candidate["status"], "completed")

        self.check_manifest()

    def test_same_result_is_idempotent(self) -> None:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        output = Path(manifest["work_dir"]) / "sample.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("相同结果", encoding="utf-8")
        result_path = self.write_result(self.completed_result(output))
        first, first_receipt = self.run_handoff(
            "record", "--manifest", str(self.manifest_path), "--result", str(result_path)
        )
        self.assertEqual(first.returncode, 0)
        before = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        second, second_receipt = self.run_handoff(
            "record", "--manifest", str(self.manifest_path), "--result", str(result_path)
        )
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertFalse(second_receipt["changed"])
        self.assertEqual(second_receipt["run_id"], first_receipt["run_id"])
        after = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(before, after)

    def test_output_outside_work_is_blocked_without_mutation(self) -> None:
        output = self.root / "outside.md"
        output.write_text("不得登记", encoding="utf-8")
        result_path = self.write_result(self.completed_result(output))
        before = self.manifest_path.read_bytes()
        completed, payload = self.run_handoff(
            "record", "--manifest", str(self.manifest_path), "--result", str(result_path)
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["status"], "blocked")
        self.assertIn("work_dir", payload["error"])
        self.assertEqual(self.manifest_path.read_bytes(), before)

    def test_material_body_in_result_json_is_blocked(self) -> None:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        output = Path(manifest["work_dir"]) / "sample.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("正文只应留在工作目录", encoding="utf-8")
        payload = self.completed_result(output)
        payload["extra_json"] = {"raw_text": "不应写入 manifest 的材料全文"}
        result_path = self.write_result(payload)
        before = self.manifest_path.read_bytes()
        completed, response = self.run_handoff(
            "record", "--manifest", str(self.manifest_path), "--result", str(result_path)
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("材料正文", response["error"])
        self.assertEqual(self.manifest_path.read_bytes(), before)

    def test_missing_completed_output_is_blocked_without_mutation(self) -> None:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        missing = Path(manifest["work_dir"]) / "missing.md"
        result_path = self.write_result(self.completed_result(missing))
        before = self.manifest_path.read_bytes()
        completed, payload = self.run_handoff(
            "record", "--manifest", str(self.manifest_path), "--result", str(result_path)
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("已存在", payload["error"])
        self.assertEqual(self.manifest_path.read_bytes(), before)

    def test_symlink_output_is_blocked_without_mutation(self) -> None:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        work_dir = Path(manifest["work_dir"])
        work_dir.mkdir(parents=True, exist_ok=True)
        real_output = work_dir / "real.md"
        real_output.write_text("合成结果", encoding="utf-8")
        link_output = work_dir / "link.md"
        link_output.symlink_to(real_output)
        result_path = self.write_result(self.completed_result(link_output))
        before = self.manifest_path.read_bytes()
        completed, payload = self.run_handoff(
            "record", "--manifest", str(self.manifest_path), "--result", str(result_path)
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("符号链接", payload["error"])
        self.assertEqual(self.manifest_path.read_bytes(), before)

    def test_failed_result_routes_human_review(self) -> None:
        task = self.export_task()
        result_path = self.write_result(
            {
                "schema_version": 1,
                "material_id": task["material_id"],
                "candidate_id": task["candidate_id"],
                "status": "failed",
                "capability": "ocr",
                "producer": "available-text-reader",
                "error_message": "输入损坏，未生成可读文本",
            }
        )
        completed, receipt = self.run_handoff(
            "record", "--manifest", str(self.manifest_path), "--result", str(result_path)
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        updated = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        material = updated["materials"][0]
        self.assertTrue(material["needs_human_review"])
        self.assertTrue(any("输入损坏" in reason for reason in material["review_reasons"]))
        run = next(item for item in updated["processing_runs"] if item["run_id"] == receipt["run_id"])
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error_message"], "输入损坏，未生成可读文本")
        self.assertTrue(
            any(
                item.get("material_id") == task["material_id"]
                and item.get("candidate_type") == "human_review"
                and item.get("status") == "candidate"
                for item in updated["follow_up_candidates"]
            )
        )
        self.check_manifest()

    def test_partial_result_keeps_review_route(self) -> None:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        output = Path(manifest["work_dir"]) / "partial.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("部分可读结果", encoding="utf-8")
        result_path = self.write_result(self.completed_result(output, readability="partial"))
        completed, _receipt = self.run_handoff(
            "record", "--manifest", str(self.manifest_path), "--result", str(result_path)
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        updated = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        material = updated["materials"][0]
        self.assertEqual(material["processing_need"], "need_review")
        self.assertTrue(material["needs_human_review"])
        preprocess = next(item for item in updated["follow_up_candidates"] if item["candidate_type"] == "preprocess_material")
        self.assertEqual(preprocess["status"], "needs_review")
        self.check_manifest()

    def test_three_completed_runs_preserve_processing_observable(self) -> None:
        observed: list[list[str]] = []
        for index in range(3):
            run_root = self.root / f"repeat-{index}"
            source = run_root / "input"
            source.mkdir(parents=True)
            (source / "sample.pdf").write_bytes(b"%PDF-1.4 synthetic")
            scan = subprocess.run(
                ["python3", str(SCANNER), str(source), "--no-write-md"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(scan.returncode, 0, scan.stdout + scan.stderr)
            manifest_path = next((run_root / ".legal-material-organizer").rglob("materials_manifest.json"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            task_result = subprocess.run(
                ["python3", str(HANDOFF), "export", "--manifest", str(manifest_path)],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(task_result.returncode, 0, task_result.stdout + task_result.stderr)
            task = json.loads(task_result.stdout)["tasks"][0]
            output = Path(manifest["work_dir"]) / "readable" / "sample.md"
            output.parent.mkdir(parents=True)
            output.write_text("三轮相同合成结果", encoding="utf-8")
            result_path = run_root / "result.json"
            result_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "material_id": task["material_id"],
                        "candidate_id": task["candidate_id"],
                        "status": "completed",
                        "capability": "text_extract",
                        "producer": "available-document-reader",
                        "output_path": str(output),
                        "variant_kind": "clean_markdown",
                        "readability_status": "readable",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            record = subprocess.run(
                [
                    "python3",
                    str(HANDOFF),
                    "record",
                    "--manifest",
                    str(manifest_path),
                    "--result",
                    str(result_path),
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(record.returncode, 0, record.stdout + record.stderr)
            observed.append(self.check_manifest(manifest_path)["observables"]["processing-closure-set"])
        self.assertEqual(observed, [observed[0], observed[0], observed[0]])

    def test_mismatched_candidate_is_blocked(self) -> None:
        task = self.export_task()
        result_path = self.write_result(
            {
                "schema_version": 1,
                "material_id": task["material_id"],
                "candidate_id": "follow_M_999999_need_ocr_or_visual",
                "status": "failed",
                "capability": "ocr",
                "producer": "available-text-reader",
                "error_message": "合成失败",
            }
        )
        completed, payload = self.run_handoff(
            "record", "--manifest", str(self.manifest_path), "--result", str(result_path)
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("candidate_id", payload["error"])


if __name__ == "__main__":
    unittest.main()
