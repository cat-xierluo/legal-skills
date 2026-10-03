"""Synthetic PDFs only: manifest validation and ordered provenance contracts."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter

import pdf_organizer as organizer
import pdf_page_refs as page_refs


class ManifestContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.a = self.make_pdf("a.pdf", [101, 102])
        self.b = self.make_pdf("b.pdf", [201])
        self.output = self.root / "output"
        self.archive = self.root / "archive"
        self.manifest_path = self.root / "manifest.json"

    def make_pdf(self, name, widths):
        path = self.root / name
        writer = PdfWriter()
        for width in widths:
            writer.add_blank_page(width=width, height=300)
        with path.open("wb") as stream:
            writer.write(stream)
        return path

    def manifest(self, segments, mode="strict"):
        data = {"output_dir": str(self.output), "archive_root": str(self.archive),
                "text_check": "off", "coverage_check": mode, "segments": segments}
        self.manifest_path.write_text(json.dumps(data), encoding="utf-8")
        return data

    def run_cli(self, flag="--manifest", *extra):
        return subprocess.run(
            [sys.executable, str(Path(organizer.__file__)), flag, str(self.manifest_path), *extra],
            capture_output=True, text=True, timeout=10,
        )

    def full_segment(self, ident="D001", name="valid.pdf"):
        return {"id": ident, "input_file": str(self.a), "suggested_filename": name}

    def test_duplicate_ids_rejected_before_pdf_writes_in_all_modes(self):
        for mode in ("strict", "warn", "off"):
            with self.subTest(mode=mode):
                self.manifest([self.full_segment(), self.full_segment(name="second.pdf")], mode)
                for flag in ("--validate-manifest", "--manifest"):
                    result = self.run_cli(flag)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn("duplicate segment id", (result.stdout + result.stderr).lower())
                self.assertFalse(list(self.output.glob("*.pdf")))

    def test_explicit_id_cannot_collide_with_generated_default(self):
        self.manifest([self.full_segment("D002"), {"input_file": str(self.b)}])
        self.assertNotEqual(self.run_cli("--validate-manifest").returncode, 0)
        self.assertNotEqual(self.run_cli().returncode, 0)
        self.assertFalse(list(self.output.glob("*.pdf")))

    def test_distinct_ids_still_find_duplicate_pages(self):
        self.manifest([self.full_segment("first"), self.full_segment("second")])
        self.assertEqual(self.run_cli("--validate-manifest").returncode, 1)
        self.assertEqual(self.run_cli().returncode, 1)
        self.assertFalse(list(self.output.glob("*.pdf")))

    def test_strict_compile_failure_blocks_valid_subset(self):
        self.output.mkdir()
        sentinel = self.output / "existing.pdf"
        sentinel.write_bytes(b"existing output sentinel")
        self.manifest([self.full_segment(), {"id": "D002", "input_file": "missing.pdf"}])
        self.assertEqual(self.run_cli().returncode, 1)
        self.assertEqual(list(self.output.glob("*.pdf")), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b"existing output sentinel")

    def test_warn_and_off_compile_failure_retain_partial_success_contract(self):
        for mode in ("warn", "off"):
            with self.subTest(mode=mode):
                self.output = self.root / mode
                self.archive = self.root / (mode + "-archive")
                self.manifest([self.full_segment(), {"id": "D002", "input_file": "missing.pdf"}], mode)
                self.assertEqual(self.run_cli().returncode, 1)
                self.assertEqual((self.output / "valid.pdf").read_bytes(), self.a.read_bytes())
                resolved = json.loads(next(self.archive.rglob("organize_manifest.resolved.json")).read_text())
                self.assertEqual(resolved["segments"][0]["status"], "ok")
                self.assertTrue(resolved["segments"][1]["status"].startswith("error:"))

    def test_validation_audit_exception_is_failure(self):
        self.manifest([self.full_segment()])
        with patch.object(organizer, "audit_page_coverage", side_effect=OSError("synthetic audit failure")):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                result = organizer.validate_manifest_command(str(self.manifest_path), None)
        self.assertEqual(result, 1)
        self.assertIn("synthetic audit failure", output.getvalue())

    def test_strict_execution_audit_exception_writes_no_pdf(self):
        self.manifest([self.full_segment()])
        with patch.object(organizer, "audit_page_coverage", side_effect=OSError("synthetic audit failure")):
            with patch.object(sys, "argv", ["pdf_organizer.py", "--manifest", str(self.manifest_path)]):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(organizer.main(), 1)
        self.assertFalse(list(self.output.glob("*.pdf")))

    def test_audit_unknown_page_count_does_not_claim_clean(self):
        counts = page_refs.PageCountCache()
        with patch.object(counts, "get", side_effect=OSError("synthetic page count failure")):
            with self.assertRaises(OSError):
                page_refs.audit_page_coverage({"D001": [(self.a, 1)]}, counts)

    def test_invalid_coverage_mode_fails_validation(self):
        self.manifest([self.full_segment()], "strcit")
        self.assertNotEqual(self.run_cli("--validate-manifest").returncode, 0)

    def test_out_of_bounds_range_checked_before_expansion(self):
        # A tripwire proves the bound is checked before calling range, without allocating huge lists.
        with patch.object(page_refs, "range", side_effect=AssertionError("range expanded"), create=True):
            with self.assertRaises(ValueError):
                page_refs.parse_pages_spec("1-1000000000000", 2)
            with self.assertRaises(ValueError):
                page_refs.parse_pages_spec("0-2", 2)

    def test_page_specs_preserve_order_and_duplicates(self):
        self.assertEqual(page_refs.parse_pages_spec("3,1-2,2", 3), [3, 1, 2, 2])
        self.assertEqual(page_refs.parse_pages_spec("2-3"), [2, 3])
        for spec in ("0", "4", "3-2", "", "one"):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                page_refs.parse_pages_spec(spec, 3)

    def test_compact_refs_and_labels_preserve_interleaving(self):
        refs = [(self.a, 1), (self.b, 1), (self.a, 2), (self.a, 1)]
        compact = page_refs.refs_to_compact(refs)
        self.assertEqual(compact, [
            {"file": str(self.a), "pages": [1]},
            {"file": str(self.b), "pages": [1]},
            {"file": str(self.a), "pages": [2, 1]},
        ])
        self.assertEqual(page_refs.refs_pages_label(refs), "a.pdf P1 + b.pdf P1 + a.pdf P2,1")
        self.assertEqual(page_refs.refs_pages_label([(self.a, 2), (self.a, 1), (self.a, 1)]), "P2,1,1")
        self.assertEqual(page_refs.refs_to_compact([]), [])
        self.assertEqual(page_refs.refs_pages_label([]), "")

    def test_real_pdf_output_matches_resolved_and_handoff_order(self):
        self.manifest([{"refs": [{"file": str(self.a), "pages": "1"},
                                 {"file": str(self.b)}, {"file": str(self.a), "pages": "2"}],
                        "suggested_filename": "combined.pdf"}])
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        reader = PdfReader(self.output / "combined.pdf")
        self.assertEqual([int(p.mediabox.width) for p in reader.pages], [101, 201, 102])
        resolved = json.loads(next(self.archive.rglob("organize_manifest.resolved.json")).read_text())
        handoff = json.loads(next(self.archive.rglob("handoff.json")).read_text())
        expected = [{"file": str(self.a), "pages": [1]}, {"file": str(self.b), "pages": [1]},
                    {"file": str(self.a), "pages": [2]}]
        self.assertEqual(resolved["segments"][0]["page_refs"], expected)
        self.assertEqual(handoff["documents"][0]["source_refs"], expected)
        self.assertEqual(handoff["documents"][0]["source_refs_label"], "a.pdf P1 + b.pdf P1 + a.pdf P2")
        # Consume the unchanged list-of-groups shape, including repeated file values.
        restored = [(Path(group["file"]), page) for group in handoff["documents"][0]["source_refs"]
                    for page in group["pages"]]
        roundtrip = self.root / "roundtrip.pdf"
        page_refs.write_refs_pdf(restored, roundtrip)
        self.assertEqual([int(p.mediabox.width) for p in PdfReader(roundtrip).pages], [101, 201, 102])

    def test_zero_page_sources_fail_consistently_in_all_forms_and_modes(self):
        empty = self.make_pdf("empty.pdf", [])
        self.assertEqual(len(PdfReader(empty).pages), 0)
        forms = ({"input_file": str(empty)}, {"refs": [{"file": str(empty)}]},
                 {"source_items": [{"file": str(empty)}]})
        for mode in ("strict", "warn", "off"):
            for segment in forms:
                with self.subTest(mode=mode, segment=segment):
                    self.manifest([segment], mode)
                    for flag in ("--validate-manifest", "--manifest"):
                        result = self.run_cli(flag)
                        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                        self.assertIn("Input PDF has no pages", result.stdout + result.stderr)
                        self.assertNotIn("Traceback", result.stderr)
                    self.assertFalse(list(self.output.glob("*.pdf")))

    def test_default_ids_and_copy_fast_path_remain_compatible(self):
        self.manifest([{"input_file": str(self.a), "suggested_filename": "a-copy.pdf"},
                       {"source_items": [{"file": str(self.b)}], "suggested_filename": "b-copy.pdf"}])
        self.assertEqual(self.run_cli("--validate-manifest").returncode, 0)
        self.assertEqual(self.run_cli().returncode, 0)
        self.assertEqual((self.output / "a-copy.pdf").read_bytes(), self.a.read_bytes())
        self.assertEqual((self.output / "b-copy.pdf").read_bytes(), self.b.read_bytes())


if __name__ == "__main__":
    unittest.main()
