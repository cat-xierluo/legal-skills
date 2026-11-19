#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent / "scan_materials.py"


class ScanMaterialsTest(unittest.TestCase):
    def run_scan(self, source: Path, archive_root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "python3",
                str(SCRIPT_PATH),
                str(source),
                "--archive-dir",
                str(archive_root),
                "--work-dir",
                str(source.parent / "work"),
                *extra,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def latest_archive(self, archive_root: Path) -> Path:
        archives = sorted(path for path in archive_root.iterdir() if path.is_dir())
        self.assertTrue(archives, "未生成 archive 运行目录")
        return archives[-1]

    def read_manifest(self, archive_dir: Path) -> dict:
        return json.loads((archive_dir / "materials_manifest.json").read_text(encoding="utf-8"))

    def test_default_writes_markdown_to_source_and_json_to_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "case"
            archive_root = root / "archive"
            source.mkdir()
            (source / "a.txt").write_text("hello", encoding="utf-8")

            self.run_scan(source, archive_root)

            archive_dir = self.latest_archive(archive_root)
            self.assertTrue((source / "材料清单.md").exists())
            self.assertFalse((source / "materials_manifest.json").exists())
            self.assertFalse((source / "processed").exists())
            self.assertTrue((archive_dir / "materials_manifest.json").exists())
            self.assertTrue((archive_dir / "run_meta.json").exists())
            self.assertTrue((archive_dir / "材料清单.md").exists())
            manifest = self.read_manifest(archive_dir)
            self.assertEqual(manifest["material_count"], 1)
            self.assertEqual(manifest["materials"][0]["material_id"], "M-000001")
            self.assertEqual(manifest["materials"][0]["display_code"], "D001")
            self.assertEqual(manifest["materials"][0]["reference_level"], "D")
            self.assertIn("material_sets", manifest)
            self.assertIn("variants", manifest)
            self.assertIn("processing_runs", manifest)
            self.assertIn("follow_up_candidates", manifest)
            self.assertEqual(manifest["materials"][0]["primary_readable_variant_id"], "variant_M_000001_original")
            self.assertEqual(manifest["variants"][0]["variant_id"], "variant_M_000001_original")
            self.assertTrue(manifest["variants"][0]["is_primary_readable"])
            self.assertTrue((archive_dir / "filing_plan.json").exists())
            self.assertTrue((archive_dir / "renaming_map.json").exists())
            markdown = (source / "材料清单.md").read_text(encoding="utf-8")
            self.assertIn("D001", markdown)
            self.assertIn("所属材料组", markdown)
            self.assertIn("可读性", markdown)
            self.assertIn("待处理动作", markdown)
            self.assertNotIn("M-000001", markdown)

    def test_default_runtime_state_is_source_adjacent_not_in_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "case"
            source.mkdir()
            (source / "a.txt").write_text("hello", encoding="utf-8")

            subprocess.run(
                ["python3", str(SCRIPT_PATH), str(source), "--no-write-md", "--no-expand-archives"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            state_root = root / ".legal-material-organizer" / "case"
            self.assertTrue((state_root / "archive").is_dir())
            self.assertFalse((SCRIPT_PATH.parent.parent / "archive" / "processed").exists())

    def test_no_write_md_keeps_source_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "case"
            archive_root = root / "archive"
            source.mkdir()
            (source / "a.txt").write_text("hello", encoding="utf-8")

            self.run_scan(source, archive_root, "--no-write-md")

            archive_dir = self.latest_archive(archive_root)
            self.assertFalse((source / "材料清单.md").exists())
            self.assertTrue((archive_dir / "材料清单.md").exists())
            self.assertTrue((archive_dir / "materials_manifest.json").exists())

    def test_rejects_overlapping_archive_and_work_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "case"
            state = root / "state"
            source.mkdir()
            (source / "a.txt").write_text("hello", encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT_PATH),
                    str(source),
                    "--archive-dir",
                    str(state),
                    "--work-dir",
                    str(state / "work"),
                    "--no-write-md",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("必须彼此分离", result.stderr)

    def test_rejects_runtime_paths_inside_skill_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "case"
            source.mkdir()
            (source / "a.txt").write_text("hello", encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT_PATH),
                    str(source),
                    "--archive-dir",
                    str(SCRIPT_PATH.parent.parent / "archive" / "forbidden"),
                    "--work-dir",
                    str(root / "work"),
                    "--no-write-md",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("不得位于 Skill 包内", result.stderr)

    def test_incremental_scan_reuses_existing_ids_and_marks_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "case"
            archive_root = root / "archive"
            source.mkdir()
            first_file = source / "a.txt"
            second_file = source / "b.txt"
            first_file.write_text("hello", encoding="utf-8")

            self.run_scan(source, archive_root)
            first_manifest = self.read_manifest(self.latest_archive(archive_root))
            self.assertEqual(first_manifest["materials"][0]["material_id"], "M-000001")

            second_file.write_text("new", encoding="utf-8")
            self.run_scan(source, archive_root)
            second_manifest = self.read_manifest(self.latest_archive(archive_root))
            active = {item["display_path"]: item for item in second_manifest["materials"] if item["lifecycle_status"] == "active"}
            self.assertEqual(active["a.txt"]["material_id"], "M-000001")
            self.assertEqual(active["b.txt"]["material_id"], "M-000002")
            self.assertIn("material_sets", second_manifest)

            first_file.unlink()
            self.run_scan(source, archive_root)
            third_manifest = self.read_manifest(self.latest_archive(archive_root))
            missing = [item for item in third_manifest["materials"] if item["lifecycle_status"] == "missing"]
            self.assertEqual(missing[0]["display_path"], "a.txt")
            self.assertEqual(missing[0]["material_id"], "M-000001")
            missing_variant = next(item for item in third_manifest["variants"] if item["material_id"] == "M-000001")
            self.assertEqual(missing_variant["asset_status"], "missing")
            self.assertFalse(missing_variant["is_primary_readable"])

    def test_display_code_reorders_without_changing_material_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "case"
            archive_root = root / "archive"
            source.mkdir()
            (source / "a.txt").write_text("a", encoding="utf-8")
            (source / "b.txt").write_text("b", encoding="utf-8")

            self.run_scan(source, archive_root)
            archive_dir = self.latest_archive(archive_root)
            manifest_path = archive_dir / "materials_manifest.json"
            manifest = self.read_manifest(archive_dir)
            for item in manifest["materials"]:
                if item["display_path"] == "a.txt":
                    item["reference_level"] = "B"
                    item["reference_score"] = 80
                if item["display_path"] == "b.txt":
                    item["reference_level"] = "A"
                    item["reference_score"] = 20
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

            self.run_scan(source, archive_root)
            second_manifest = self.read_manifest(self.latest_archive(archive_root))
            active = {item["display_path"]: item for item in second_manifest["materials"] if item["lifecycle_status"] == "active"}
            self.assertEqual(active["a.txt"]["material_id"], "M-000001")
            self.assertEqual(active["a.txt"]["display_code"], "B002")
            self.assertEqual(active["b.txt"]["material_id"], "M-000002")
            self.assertEqual(active["b.txt"]["display_code"], "A001")

    def test_legacy_display_id_manifest_is_migrated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "case"
            archive_root = root / "archive"
            source.mkdir()
            file_path = source / "a.txt"
            file_path.write_text("hello", encoding="utf-8")
            fingerprint = __import__("hashlib").sha256(file_path.read_bytes()).hexdigest()
            legacy_dir = archive_root / "20260101_000000_case"
            legacy_dir.mkdir(parents=True)
            legacy_manifest = {
                "source": str(source.resolve()),
                "materials": [
                    {
                        "material_id": "D-001",
                        "display_path": "a.txt",
                        "fingerprint": fingerprint,
                        "lifecycle_status": "active",
                    }
                ],
            }
            (legacy_dir / "materials_manifest.json").write_text(
                json.dumps(legacy_manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            self.run_scan(source, archive_root)
            manifest = self.read_manifest(self.latest_archive(archive_root))
            record = manifest["materials"][0]
            self.assertEqual(record["material_id"], "M-000001")
            self.assertEqual(record["display_code"], "D001")
            self.assertIn("D-001", record["legacy_ids"])
            self.assertEqual(record["readability_status"], "readable")
            self.assertEqual(record["processing_need"], "none")
            self.assertEqual(record["primary_readable_variant_id"], "variant_M_000001_original")
            self.assertTrue(manifest["variants"][0]["is_primary_readable"])

    def test_legacy_manifest_infers_processing_need_from_current_file_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "case"
            archive_root = root / "archive"
            source.mkdir()
            file_path = source / "scan.pdf"
            file_path.write_bytes(b"%PDF-1.4 fake")
            fingerprint = __import__("hashlib").sha256(file_path.read_bytes()).hexdigest()
            legacy_dir = archive_root / "20260101_000000_case"
            legacy_dir.mkdir(parents=True)
            legacy_manifest = {
                "source": str(source.resolve()),
                "materials": [
                    {
                        "material_id": "M-001",
                        "display_path": "scan.pdf",
                        "fingerprint": fingerprint,
                        "lifecycle_status": "active",
                    }
                ],
            }
            (legacy_dir / "materials_manifest.json").write_text(
                json.dumps(legacy_manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            self.run_scan(source, archive_root)
            manifest = self.read_manifest(self.latest_archive(archive_root))
            record = manifest["materials"][0]
            self.assertEqual(record["readability_status"], "unknown")
            self.assertEqual(record["processing_need"], "need_ocr_or_visual")
            self.assertIsNone(record["primary_readable_variant_id"])
            self.assertTrue(any(item["candidate_type"] == "preprocess_material" for item in manifest["follow_up_candidates"]))

    def test_archive_keeps_metadata_only_and_extracts_to_work_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "case"
            archive_root = root / "archive"
            source.mkdir()
            with zipfile.ZipFile(source / "pack.zip", "w") as zf:
                zf.writestr("inside.txt", "zip content")

            self.run_scan(source, archive_root)

            archive_dir = self.latest_archive(archive_root)
            work_dir = source.parent / "work"
            manifest = self.read_manifest(archive_dir)
            display_paths = {item["display_path"] for item in manifest["materials"]}
            self.assertIn("pack.zip", display_paths)
            self.assertIn("pack.zip!/inside.txt", display_paths)
            self.assertFalse((archive_dir / "processed").exists())
            self.assertTrue((work_dir / "extracted_containers").exists())
            self.assertTrue(manifest["work_dir"].endswith("/work"))
            self.assertFalse((source / "processed").exists())
            self.assertFalse((source / "inside.txt").exists())
            runs = [item for item in manifest["processing_runs"] if item["run_type"] == "extract"]
            self.assertTrue(runs)
            self.assertEqual(runs[0]["status"], "completed")
            self.assertTrue(runs[0]["input_path"].endswith("pack.zip"))
            archive_record = next(item for item in manifest["materials"] if item["display_path"] == "pack.zip")
            self.assertEqual(archive_record["processing_need"], "none")
            self.assertFalse(
                any(
                    item.get("material_id") == archive_record["material_id"]
                    and item.get("candidate_type") == "preprocess_material"
                    for item in manifest["follow_up_candidates"]
                )
            )

    def test_pdf_gets_preprocess_candidate_and_non_readable_variant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "case"
            archive_root = root / "archive"
            source.mkdir()
            (source / "scan.pdf").write_bytes(b"%PDF-1.4 fake")

            self.run_scan(source, archive_root)

            manifest = self.read_manifest(self.latest_archive(archive_root))
            record = manifest["materials"][0]
            self.assertEqual(record["processing_need"], "need_ocr_or_visual")
            self.assertIsNone(record["primary_readable_variant_id"])
            variant = manifest["variants"][0]
            self.assertEqual(variant["readability_status"], "unknown")
            candidates = manifest["follow_up_candidates"]
            self.assertTrue(any(item["candidate_type"] == "preprocess_material" for item in candidates))

    def test_follow_up_candidate_status_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "case"
            archive_root = root / "archive"
            source.mkdir()
            (source / "scan.pdf").write_bytes(b"%PDF-1.4 fake")

            self.run_scan(source, archive_root)
            archive_dir = self.latest_archive(archive_root)
            manifest_path = archive_dir / "materials_manifest.json"
            manifest = self.read_manifest(archive_dir)
            manifest["follow_up_candidates"][0]["status"] = "ignored"
            manifest["follow_up_candidates"][0]["extra_json"] = {"reviewed_by": "human"}
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

            self.run_scan(source, archive_root)
            second_manifest = self.read_manifest(self.latest_archive(archive_root))
            candidate = second_manifest["follow_up_candidates"][0]
            self.assertEqual(candidate["status"], "ignored")
            self.assertEqual(candidate["extra_json"], {"reviewed_by": "human"})

    def test_material_sets_group_multiple_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "case"
            archive_root = root / "archive"
            source.mkdir()
            (source / "a.txt").write_text("a", encoding="utf-8")
            (source / "b.md").write_text("# b", encoding="utf-8")

            self.run_scan(source, archive_root)

            manifest = self.read_manifest(self.latest_archive(archive_root))
            sets = {item["set_id"]: item for item in manifest["material_sets"]}
            self.assertIn("set_documents", sets)
            self.assertEqual(len(sets["set_documents"]["material_ids"]), 2)
            filing_plan = json.loads((self.latest_archive(archive_root) / "filing_plan.json").read_text(encoding="utf-8"))
            self.assertIn("material_sets", filing_plan)

    def test_rejects_tar_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "case"
            archive_root = root / "archive"
            source.mkdir()
            tar_path = source / "bad.tar"
            with tarfile.open(tar_path, "w") as tf:
                info = tarfile.TarInfo("../evil.txt")
                data = b"evil"
                info.size = len(data)
                tf.addfile(info, fileobj=__import__("io").BytesIO(data))

            self.run_scan(source, archive_root)

            archive_dir = self.latest_archive(archive_root)
            manifest = self.read_manifest(archive_dir)
            bad = next(item for item in manifest["materials"] if item["display_path"] == "bad.tar")
            self.assertEqual(bad["status"], "待外部解压")
            failed = next(item for item in manifest["processing_runs"] if item["status"] == "failed")
            self.assertTrue(failed["input_path"].endswith("bad.tar"))
            self.assertIn("error_message", failed)
            self.assertFalse((root / "evil.txt").exists())

    def test_scanner_recognizes_chat_html_source(self) -> None:
        """chat-html 输入应当在 manifest extra_json.chat_html 写入 recognized=True。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            archive_root = root / "archive"
            source.mkdir()
            html = (
                '<html><body><div class="reader-page">群聊的聊天记录</div>'
                '<a href="https://files.cubox.pro/123/foo.pdf">下载文件</a>'
                '</body></html>'
            )
            (source / "群聊记录.html").write_text(html, encoding="utf-8")
            self.run_scan(source, archive_root, "--no-write-md")
            archive_dir = self.latest_archive(archive_root)
            manifest = self.read_manifest(archive_dir)
            self.assertEqual(len(manifest["materials"]), 1)
            entry = manifest["materials"][0]
            self.assertEqual(entry["extra_json"]["chat_html"]["recognized"], True)
            self.assertGreaterEqual(len(entry["extra_json"]["chat_html"]["resources"]), 1)

    def test_scanner_dry_run_writes_dryrun_manifest(self) -> None:
        """--chat-html-dry-run 应当生成 dryrun_manifest.json 包含 counts_by_kind。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            archive_root = root / "archive"
            source.mkdir()
            html = (
                '<html><body><div class="reader-page">群聊的聊天记录</div>'
                '<a href="https://files.cubox.pro/123/foo.pdf">下载文件</a>'
                '<img src="https://images.cubox.pro/x.jpg" />'
                '<video src="https://example.com/c.mp4"></video>'
                '</body></html>'
            )
            (source / "群聊记录.html").write_text(html, encoding="utf-8")
            self.run_scan(source, archive_root, "--no-write-md", "--chat-html-dry-run")
            archive_dir = self.latest_archive(archive_root)
            self.assertTrue((archive_dir / "dryrun_manifest.json").exists())

    def test_scanner_normal_html_is_not_chat_html(self) -> None:
        """普通 HTML 不会被认作 chat-html。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            archive_root = root / "archive"
            source.mkdir()
            (source / "page.html").write_text(
                "<html><body><h1>普通页面</h1></body></html>",
                encoding="utf-8",
            )
            self.run_scan(source, archive_root, "--no-write-md")
            archive_dir = self.latest_archive(archive_root)
            manifest = self.read_manifest(archive_dir)
            entry = manifest["materials"][0]
            self.assertNotIn("chat_html", entry.get("extra_json", {}))

    def test_scanner_chat_html_download_stub_records_results(self) -> None:
        """--chat-html-download 使用受控 stub，验证 downloads 数组被填入 chat_meta。"""
        # 直接 import scan_materials 模块，绕开 subprocess；mock 抽取与下载，避免真实联网。
        import importlib
        import sys as _sys  # noqa: WPS433
        from unittest.mock import patch

        if str(SCRIPT_PATH.parent) not in _sys.path:
            _sys.path.insert(0, str(SCRIPT_PATH.parent))

        scan_module = importlib.import_module("scan_materials")
        chat_module = importlib.import_module("chat_html_extract")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_root = root / "archive"
            archive_root.mkdir()

            external_dir = root / "external"
            external_dir.mkdir()

            fake_candidate = chat_module.ResourceCandidate(
                resource_id="R-test-001",
                kind="download",
                url="https://files.cubox.pro/example/sample.pdf",
                display_filename="sample.pdf",
                sender_context="stub",
            )

            html = '<html><body><div class="reader-page">群聊的聊天记录</div></body></html>'
            html_file = root / "fake_chat.html"
            html_file.write_text(html, encoding="utf-8")

            scanner = scan_module.MaterialScanner(
                source=html_file,
                markdown_output_dir=root,
                archive_dir=archive_root,
                work_dir=root / "work",
                previous_manifest=None,
                expand_archives=False,
                allow_external_extractor=False,
                max_archive_depth=0,
                include_hidden=False,
                write_md=False,
            )
            scanner.chat_html_download = True
            scanner.chat_html_resource_dir = external_dir

            fake_result = chat_module.DownloadResult(
                url=fake_candidate.url,
                status="ok",
                path=external_dir / "sample.pdf",
                attempts=1,
                bytes=18,
            )
            with (
                patch.object(scan_module, "_chat_html_extract", return_value=[fake_candidate]),
                patch.object(scan_module, "_chat_html_download", return_value=fake_result),
            ):
                scanner.scan()
                # _handle_chat_html 把 chat_meta 写入 record.extra_json，
                # 但 materials_manifest.json 由 write_outputs 写出。这里手动序列化。
                manifest = {
                    "materials": [
                        {
                            "absolute_path": scanner.records[0].absolute_path,
                            "extra_json": scanner.records[0].extra_json,
                        }
                    ]
                }
                downloads = manifest["materials"][0]["extra_json"]["chat_html"].get("downloads", [])
                self.assertGreaterEqual(len(downloads), 1)
                self.assertEqual(downloads[0]["kind"], "download")
                self.assertEqual(downloads[0]["status"], "ok")
                self.assertIn("external", downloads[0]["path"])

    def test_chat_html_checklist_section_appended_to_markdown(self) -> None:
        """chat-html 来源时，材料清单应当包含「外部资源抽取对账」小节。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            archive_root = root / "archive"
            source.mkdir()
            html = (
                '<html><body><div class="reader-page">群聊的聊天记录</div>'
                '<a href="https://files.cubox.pro/123/foo.pdf">下载文件</a>'
                '<img src="https://images.cubox.pro/x.jpg" />'
                '<video src="https://example.com/c.mp4"></video>'
                '</body></html>'
            )
            (source / "群聊记录.html").write_text(html, encoding="utf-8")
            self.run_scan(source, archive_root)  # 默认写材料清单
            md = (source / "材料清单.md").read_text(encoding="utf-8")
            self.assertIn("外部资源抽取对账", md)
            self.assertIn("| 合计", md)
            self.assertIn("download", md)

    def test_chat_html_checklist_section_absent_for_non_chat_html(self) -> None:
        """普通 HTML 不应当触发对账小节。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            archive_root = root / "archive"
            source.mkdir()
            (source / "page.html").write_text("<html><body><h1>x</h1></body></html>", encoding="utf-8")
            self.run_scan(source, archive_root)
            md = (source / "材料清单.md").read_text(encoding="utf-8")
            self.assertNotIn("外部资源抽取对账", md)


if __name__ == "__main__":
    unittest.main()
