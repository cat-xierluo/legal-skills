#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Targeted tests for zcode-gui-artifacts.py.

Black-box: every case drives the real CLI via subprocess. Covers binary
round trips (0-byte, exact and off-by-one chunk boundaries, nested paths),
pack rejections (traversal, absolute, symlinks incl. parents, duplicates,
limits, non-overwriting outputs), unpack rejections on mutated manifests
(bad types, duplicate JSON keys, missing chunks, duplicate/gapped offsets,
tampered digests, bad base64, over-limit, existing/symlink targets) with
failure-leaves-nothing-on-disk assertions, and emit-chunk fixed keys/bounds.

Standard library only; supports Python 3.9+.
"""

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(HERE, "zcode-gui-artifacts.py")

BASE = "a" * 40
HEAD = "b" * 40
CHUNK = 1000
MIB = 1024 * 1024

TOP_KEYS = {"schema", "task_id", "session_id", "branch", "base", "head",
            "chunk_size", "files"}
EMIT_KEYS = {"schema", "bundle_sha256", "file", "index", "offset",
             "length", "base64"}


def run_cli(args):
    return subprocess.run([sys.executable, CLI] + args,
                          capture_output=True, text=True)


def pack_args(source, out, paths, base=BASE, head=HEAD):
    return ["pack", "--source", source, "--task", "TASK-TEST",
            "--session", "session-test", "--branch", "feat/test",
            "--base", base, "--head", head, "--output", out] + list(paths)


def unpack_args(bundle, target):
    return ["unpack", "--bundle", bundle, "--target", target]


def sha_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def make_tree(root, files):
    for rel, blob in files.items():
        path = os.path.join(root, *rel.split("/"))
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(blob)


def synth_entry(rel, blob):
    chunks = []
    for offset in range(0, len(blob), CHUNK):
        piece = blob[offset:offset + CHUNK]
        chunks.append({"index": offset // CHUNK, "offset": offset,
                       "length": len(piece),
                       "base64": base64.b64encode(piece).decode("ascii")})
    return {"path": rel, "size": len(blob),
            "sha256": hashlib.sha256(blob).hexdigest(), "chunks": chunks}


class ArtifactsTest(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="zgui-artifacts-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.src = os.path.join(self.tmp, "src")
        os.mkdir(self.src)
        self.out = os.path.join(self.tmp, "out.bundle")
        self.target = os.path.join(self.tmp, "target")

    # ---------- helpers ----------

    def pack(self, paths, source=None, out=None, base=BASE, head=HEAD):
        return run_cli(pack_args(source or self.src, out or self.out,
                                 paths, base, head))

    def unpack(self, bundle=None, target=None):
        return run_cli(unpack_args(bundle or self.out,
                                   target or self.target))

    def assert_ok(self, proc, what):
        self.assertEqual(proc.returncode, 0,
                         "%s failed: rc=%s stderr=%s"
                         % (what, proc.returncode, proc.stderr))

    def assert_rejected(self, proc, what, needle=None):
        self.assertNotEqual(proc.returncode, 0,
                            "%s should be rejected; stdout=%s"
                            % (what, proc.stdout))
        if needle is not None:
            self.assertIn(needle, proc.stderr)

    def assert_target_absent(self):
        self.assertFalse(os.path.lexists(self.target),
                         "target must not exist after a failed unpack")

    def listing(self):
        return sorted(os.listdir(self.tmp))

    def make_bundle(self, files=None):
        """Pack a standard bundle: fa.bin (3 chunks), fb.empty (0 chunks),
        fc.txt (1 chunk). Returns fa.bin content."""
        if files is None:
            fa = bytes((i * 7 + 3) % 256 for i in range(2500))
            files = {"fa.bin": fa, "fb.empty": b"", "fc.txt": b"0123456789"}
        for rel, blob in files.items():
            make_tree(self.src, {rel: blob})
        proc = self.pack(sorted(files))
        self.assert_ok(proc, "pack")
        return files.get("fa.bin", b"")

    def mutated_bundle(self, name, mutate):
        """Copy self.out with a mutation applied; returns bad bundle path."""
        with open(self.out, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        mutate(data)
        bad = os.path.join(self.tmp, name)
        with open(bad, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        return bad

    # ---------- round trips (positive) ----------

    def test_roundtrip_binary_multi_chunk(self):
        fa = self.make_bundle()
        proc = self.unpack()
        self.assert_ok(proc, "unpack")
        self.assertEqual(sha_file(os.path.join(self.target, "fa.bin")),
                         hashlib.sha256(fa).hexdigest())
        with open(self.out, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
        entry = manifest["files"][0]
        self.assertEqual(entry["size"], 2500)
        self.assertEqual([c["length"] for c in entry["chunks"]],
                         [1000, 1000, 500])
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["files"], 3)
        self.assertEqual(summary["total_bytes"], 2500 + 0 + 10)

    def test_roundtrip_empty_file(self):
        self.make_bundle()
        proc = self.unpack()
        self.assert_ok(proc, "unpack")
        empty = os.path.join(self.target, "fb.empty")
        self.assertTrue(os.path.isfile(empty))
        self.assertEqual(os.path.getsize(empty), 0)
        with open(self.out, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
        empty_entry = [f for f in manifest["files"]
                       if f["path"] == "fb.empty"][0]
        self.assertEqual(empty_entry["chunks"], [])
        self.assertEqual(
            empty_entry["sha256"],
            hashlib.sha256(b"").hexdigest())

    def test_roundtrip_chunk_boundary_sizes(self):
        sizes = [1, 999, 1000, 1001, 2000]
        files = {"s%04d.bin" % n: bytes((i * 13 + 1) % 256 for i in range(n))
                 for n in sizes}
        self.make_bundle(files)
        self.assert_ok(self.unpack(), "unpack")
        for rel, blob in files.items():
            self.assertEqual(
                sha_file(os.path.join(self.target, *rel.split("/"))),
                hashlib.sha256(blob).hexdigest(), rel)

    def test_roundtrip_nested_paths_and_same_basename(self):
        files = {"deep/nest/ed/x.bin": b"\x00\xff" * 700,
                 "other/y.bin": b"Y" * 1500,
                 "deep/nest/ed/x.txt": b"txt"}
        self.make_bundle(files)
        self.assert_ok(self.unpack(), "unpack")
        for rel, blob in files.items():
            got = os.path.join(self.target, *rel.split("/"))
            self.assertEqual(sha_file(got),
                             hashlib.sha256(blob).hexdigest(), rel)

    def test_pack_is_deterministic(self):
        make_tree(self.src, {"a.bin": b"A" * 1500})
        self.assert_ok(self.pack(["a.bin"], out=self.out), "pack 1")
        second = self.out + ".2"
        self.assert_ok(self.pack(["a.bin"], out=second), "pack 2")
        self.assertEqual(sha_file(self.out), sha_file(second))

    def test_unpack_refuses_existing_target_second_time(self):
        self.make_bundle()
        self.assert_ok(self.unpack(), "unpack 1")
        first = self.listing()
        self.assert_rejected(self.unpack(), "unpack 2", "already exists")
        self.assertEqual(self.listing(), first)

    def test_unpack_requires_existing_parent(self):
        self.make_bundle()
        deep = os.path.join(self.tmp, "no", "such", "target")
        self.assert_rejected(
            run_cli(unpack_args(self.out, deep)), "missing parent")

    # ---------- pack rejections ----------

    def test_pack_rejects_zero_and_six_files(self):
        make_tree(self.src, {"f%d.txt" % i: b"x" for i in range(6)})
        self.assert_rejected(self.pack([]), "0 files")
        self.assert_rejected(
            self.pack(["f%d.txt" % i for i in range(6)]), "6 files")
        self.assertFalse(os.path.lexists(self.out))

    def test_pack_rejects_absolute_and_traversal(self):
        make_tree(self.src, {"ok.txt": b"ok"})
        for bad in ["/etc/hosts", "../escape.txt", "a/../../up.txt",
                    "./ok.txt", "a//b.txt", "ok.txt/"]:
            self.assert_rejected(self.pack([bad]), "bad path %r" % bad)
        self.assertFalse(os.path.lexists(self.out))
        self.assertFalse(os.path.lexists(
            os.path.join(os.path.dirname(self.src), "escape.txt")))

    def test_pack_rejects_backslash_path(self):
        make_tree(self.src, {"ok.txt": b"ok"})
        self.assert_rejected(self.pack(["a\\b.txt"]), "backslash")

    def test_pack_rejects_duplicate_path(self):
        make_tree(self.src, {"dup.txt": b"dup"})
        self.assert_rejected(self.pack(["dup.txt", "dup.txt"]), "duplicates")

    def test_pack_rejects_symlink_artifact(self):
        outside = os.path.join(self.tmp, "outside.txt")
        with open(outside, "wb") as fh:
            fh.write(b"secret")
        os.symlink(outside, os.path.join(self.src, "link.txt"))
        self.assert_rejected(self.pack(["link.txt"]), "symlink file", "symlink")

    def test_pack_rejects_symlink_parent(self):
        realdir = os.path.join(self.tmp, "realdir")
        os.mkdir(realdir)
        with open(os.path.join(realdir, "f.txt"), "wb") as fh:
            fh.write(b"data")
        os.symlink(realdir, os.path.join(self.src, "sub"))
        self.assert_rejected(self.pack(["sub/f.txt"]), "symlink parent")

    def test_pack_rejects_dangling_symlink(self):
        os.symlink(os.path.join(self.tmp, "nope"),
                   os.path.join(self.src, "dangling.txt"))
        self.assert_rejected(self.pack(["dangling.txt"]), "dangling symlink")

    def test_pack_rejects_symlink_source_root(self):
        make_tree(self.src, {"a.txt": b"a"})
        link = os.path.join(self.tmp, "srclink")
        os.symlink(self.src, link)
        self.assert_rejected(self.pack(["a.txt"], source=link), "root symlink")

    def test_pack_rejects_missing_source_root(self):
        self.assert_rejected(
            self.pack(["a.txt"], source=os.path.join(self.tmp, "gone")),
            "missing root")

    def test_pack_rejects_directory_artifact(self):
        os.mkdir(os.path.join(self.src, "adir"))
        self.assert_rejected(self.pack(["adir"]), "directory", "regular file")

    def test_pack_rejects_existing_output_without_overwrite(self):
        make_tree(self.src, {"a.txt": b"a"})
        with open(self.out, "wb") as fh:
            fh.write(b"CANARY")
        self.assert_rejected(self.pack(["a.txt"]), "existing output",
                             "never overwrite")
        with open(self.out, "rb") as fh:
            self.assertEqual(fh.read(), b"CANARY")

    def test_pack_rejects_oversize_file(self):
        big = os.path.join(self.src, "big.bin")
        with open(big, "wb") as fh:
            fh.truncate(8 * MIB + 1)
        self.assert_rejected(self.pack(["big.bin"]), ">8MiB", "8 MiB")
        self.assertFalse(os.path.lexists(self.out))

    def test_pack_rejects_total_over_16mib(self):
        for i in range(3):
            with open(os.path.join(self.src, "t%d.bin" % i), "wb") as fh:
                fh.truncate(8 * MIB)
        self.assert_rejected(self.pack(["t0.bin", "t1.bin", "t2.bin"]),
                             "total >16MiB", "total size exceeds")
        self.assertFalse(os.path.lexists(self.out))

    def test_pack_rejects_bad_base_head_hex(self):
        make_tree(self.src, {"a.txt": b"a"})
        for base, head in [("Z" * 40, HEAD), (BASE, "b" * 39),
                           (BASE.upper(), HEAD), (BASE, "b" * 41)]:
            self.assert_rejected(self.pack(["a.txt"], base=base, head=head),
                                 "bad hex base=%r head=%r" % (base, head))

    def test_pack_stdout_is_bounded_summary(self):
        make_tree(self.src, {"a.bin": b"B" * 1500})
        proc = self.pack(["a.bin"])
        self.assert_ok(proc, "pack")
        self.assertEqual(proc.stdout.count("\n"), 1)
        self.assertLess(len(proc.stdout), 500)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["files"], 1)
        self.assertEqual(summary["total_bytes"], 1500)
        self.assertEqual(summary["bundle_sha256"], sha_file(self.out))
        self.assertNotIn("Qg==", proc.stdout)  # no base64 payload on stdout

    # ---------- unpack rejections (mutated manifests) ----------

    def test_unpack_rejects_manifest_type_and_key_mutations(self):
        self.make_bundle()
        mutations = [
            ("size-as-string", lambda d: d["files"][0].__setitem__(
                "size", "2500")),
            ("bool-chunk-size", lambda d: d.__setitem__("chunk_size", True)),
            ("wrong-chunk-size", lambda d: d.__setitem__("chunk_size", 999)),
            ("bad-base-hex", lambda d: d.__setitem__("base", "Z" * 40)),
            ("short-head", lambda d: d.__setitem__("head", "b" * 39)),
            ("missing-key", lambda d: d.pop("session_id")),
            ("extra-key", lambda d: d.__setitem__("notes", "free-form")),
            ("files-not-list", lambda d: d.__setitem__("files", {"a": 1})),
            ("files-empty", lambda d: d.__setitem__("files", [])),
            ("bad-sha-format", lambda d: d["files"][0].__setitem__(
                "sha256", "X" * 64)),
            ("chunk-index-string", lambda d: d["files"][0]["chunks"][0]
                .__setitem__("index", "0")),
            ("length-float", lambda d: d["files"][0]["chunks"][0]
                .__setitem__("length", 1000.0)),
            ("unsupported-schema", lambda d: d.__setitem__(
                "schema", "zcode-gui-artifacts/v0")),
        ]
        for name, mutate in mutations:
            with self.subTest(name):
                bad = self.mutated_bundle("bad-%s.json" % name, mutate)
                before = self.listing()
                proc = run_cli(unpack_args(bad, self.target))
                self.assert_rejected(proc, name)
                self.assert_target_absent()
                self.assertEqual(self.listing(), before)

    def test_unpack_rejects_duplicate_file_path(self):
        self.make_bundle()
        bad = self.mutated_bundle(
            "dup-path.json",
            lambda d: d["files"][1].__setitem__("path",
                                                d["files"][0]["path"]))
        self.assert_rejected(run_cli(unpack_args(bad, self.target)),
                             "duplicate path", "duplicate")

    def test_unpack_rejects_traversal_path_zero_disk(self):
        self.make_bundle()
        bad = self.mutated_bundle(
            "traversal.json",
            lambda d: d["files"][1].__setitem__("path", "../evil.txt"))
        before = self.listing()
        self.assert_rejected(run_cli(unpack_args(bad, self.target)),
                             "traversal", "..")
        self.assert_target_absent()
        self.assertEqual(self.listing(), before)
        self.assertFalse(os.path.lexists(os.path.join(self.tmp, "evil.txt")))

    def test_unpack_rejects_nested_path_conflict(self):
        self.make_bundle()
        bad = self.mutated_bundle(
            "conflict.json",
            lambda d: d["files"][2].__setitem__(
                "path", d["files"][0]["path"] + "/inner"))
        self.assert_rejected(run_cli(unpack_args(bad, self.target)),
                             "path conflict")
        self.assert_target_absent()

    def test_unpack_rejects_chunk_defects(self):
        self.make_bundle()
        mutations = [
            ("missing-chunk", lambda d: d["files"][0]["chunks"].pop(1)),
            ("duplicate-offset", lambda d: d["files"][0]["chunks"][1]
                .__setitem__("offset", 0)),
            ("gapped-offset", lambda d: d["files"][0]["chunks"][1]
                .__setitem__("offset", 1001)),
            ("short-nonfinal-chunk", lambda d: d["files"][0]["chunks"][0]
                .__setitem__("length", 999)),
            ("bad-index", lambda d: d["files"][0]["chunks"][1]
                .__setitem__("index", 7)),
            ("bad-base64", lambda d: d["files"][0]["chunks"][0]
                .__setitem__("base64", "!!!")),
            ("base64-length-mismatch", lambda d: d["files"][0]["chunks"][0]
                .__setitem__("base64",
                             base64.b64encode(b"\x01" * 999).decode("ascii"))),
            ("extra-chunk-key", lambda d: d["files"][0]["chunks"][0]
                .__setitem__("note", "x")),
            ("final-length-mismatch", lambda d: d["files"][0]["chunks"][2]
                .__setitem__("length", 499)),
        ]
        for name, mutate in mutations:
            with self.subTest(name):
                bad = self.mutated_bundle("bad-%s.json" % name, mutate)
                before = self.listing()
                proc = run_cli(unpack_args(bad, self.target))
                self.assert_rejected(proc, name)
                self.assert_target_absent()
                self.assertEqual(self.listing(), before)

    def test_unpack_rejects_tampered_digest_zero_disk(self):
        self.make_bundle()
        good_sha = json.load(open(self.out, encoding="utf-8"))[
            "files"][0]["sha256"]
        flipped = ("0" if good_sha[0] != "0" else "1") + good_sha[1:]
        bad = self.mutated_bundle(
            "tampered.json",
            lambda d: d["files"][0].__setitem__("sha256", flipped))
        before = self.listing()
        self.assert_rejected(run_cli(unpack_args(bad, self.target)),
                             "tampered digest", "mismatch")
        self.assert_target_absent()
        self.assertEqual(self.listing(), before)

    def test_unpack_rejects_per_file_over_8mib(self):
        self.make_bundle()
        bad = self.mutated_bundle(
            "big-file.json",
            lambda d: d["files"][1].__setitem__("size", 8 * MIB + 1))
        self.assert_rejected(run_cli(unpack_args(bad, self.target)),
                             "per-file over limit", "size")
        self.assert_target_absent()

    def test_unpack_rejects_total_over_16mib(self):
        zeros = b"\x00" * (8 * MIB)
        manifest = {
            "schema": "zcode-gui-artifacts/v1",
            "task_id": "TASK-TEST", "session_id": "session-test",
            "branch": "feat/test", "base": BASE, "head": HEAD,
            "chunk_size": CHUNK,
            "files": [synth_entry("big1.bin", zeros),
                      synth_entry("big2.bin", zeros),
                      synth_entry("one.txt", b"x")],
        }
        bad = os.path.join(self.tmp, "total-over.json")
        with open(bad, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh)
        self.assert_rejected(run_cli(unpack_args(bad, self.target)),
                             "total over limit", "total")
        self.assert_target_absent()

    def test_unpack_rejects_duplicate_json_keys(self):
        self.make_bundle()
        with open(self.out, "r", encoding="utf-8") as fh:
            text = fh.read()
        bad_text = text.replace("{\n", '{\n  "chunk_size": 1000,\n', 1)
        self.assertEqual(text.count('"chunk_size"'), 1)
        self.assertEqual(bad_text.count('"chunk_size"'), 2)
        bad = os.path.join(self.tmp, "dup-keys.json")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write(bad_text)
        proc = run_cli(unpack_args(bad, self.target))
        self.assert_rejected(proc, "duplicate keys", "duplicate JSON key")
        self.assert_target_absent()

    def test_unpack_rejects_existing_target_without_overwrite(self):
        self.make_bundle()
        os.mkdir(self.target)
        canary = os.path.join(self.target, "canary.txt")
        with open(canary, "wb") as fh:
            fh.write(b"KEEP")
        self.assert_rejected(self.unpack(), "existing target",
                             "already exists")
        with open(canary, "rb") as fh:
            self.assertEqual(fh.read(), b"KEEP")
        self.assertEqual(sorted(os.listdir(self.target)), ["canary.txt"])

    def test_unpack_rejects_symlink_target(self):
        self.make_bundle()
        dangling = os.path.join(self.tmp, "dangling-target")
        os.symlink(os.path.join(self.tmp, "nope"), dangling)
        self.assert_rejected(
            run_cli(unpack_args(self.out, dangling)), "symlink target")

    def test_unpack_rejects_symlink_bundle(self):
        self.make_bundle()
        link = os.path.join(self.tmp, "bundle-link")
        os.symlink(self.out, link)
        self.assert_rejected(
            run_cli(unpack_args(link, self.target)), "symlink bundle")

    def test_unpack_rejects_non_json_and_invalid_utf8(self):
        self.make_bundle()
        junk = os.path.join(self.tmp, "junk.json")
        with open(junk, "wb") as fh:
            fh.write(b"\xff\xfe\x00bad")
        self.assert_rejected(run_cli(unpack_args(junk, self.target)),
                             "invalid utf-8")
        with open(junk, "w", encoding="utf-8") as fh:
            fh.write("hello, not json")
        self.assert_rejected(run_cli(unpack_args(junk, self.target)),
                             "not json")

    # ---------- emit-chunk ----------

    def test_emit_chunk_fixed_keys_and_first_chunk(self):
        fa = self.make_bundle()
        proc = run_cli(["emit-chunk", "--bundle", self.out,
                        "--file", "fa.bin", "--chunk", "0"])
        self.assert_ok(proc, "emit-chunk 0")
        self.assertEqual(proc.stdout.count("\n"), 1)
        emit = json.loads(proc.stdout)
        self.assertEqual(set(emit.keys()), EMIT_KEYS)
        self.assertEqual(emit["bundle_sha256"], sha_file(self.out))
        self.assertEqual(emit["file"], "fa.bin")
        self.assertEqual(emit["index"], 0)
        self.assertEqual(emit["offset"], 0)
        self.assertEqual(emit["length"], 1000)
        self.assertEqual(base64.b64decode(emit["base64"]), fa[:1000])

    def test_emit_chunk_final_chunk(self):
        fa = self.make_bundle()
        proc = run_cli(["emit-chunk", "--bundle", self.out,
                        "--file", "fa.bin", "--chunk", "2"])
        self.assert_ok(proc, "emit-chunk 2")
        emit = json.loads(proc.stdout)
        self.assertEqual(emit["offset"], 2000)
        self.assertEqual(emit["length"], 500)
        self.assertEqual(base64.b64decode(emit["base64"]), fa[2000:])

    def test_emit_chunk_is_bounded_single_line(self):
        self.make_bundle()
        proc = run_cli(["emit-chunk", "--bundle", self.out,
                        "--file", "fa.bin", "--chunk", "1"])
        self.assert_ok(proc, "emit-chunk 1")
        line = proc.stdout.strip()
        self.assertNotIn("\n", line)
        self.assertLess(len(line), 1000 * 4 // 3 + 300)

    def test_emit_chunk_out_of_range_and_unknown_file(self):
        self.make_bundle()
        proc = run_cli(["emit-chunk", "--bundle", self.out,
                        "--file", "fa.bin", "--chunk", "3"])
        self.assert_rejected(proc, "index out of range")
        self.assertEqual(proc.stdout, "")
        proc = run_cli(["emit-chunk", "--bundle", self.out,
                        "--file", "nope.bin", "--chunk", "0"])
        self.assert_rejected(proc, "unknown file")
        proc = run_cli(["emit-chunk", "--bundle", self.out,
                        "--file", "fb.empty", "--chunk", "0"])
        self.assert_rejected(proc, "empty file has no chunks")

    def test_emit_chunk_negative_index(self):
        self.make_bundle()
        proc = run_cli(["emit-chunk", "--bundle", self.out,
                        "--file", "fa.bin", "--chunk", "-1"])
        self.assert_rejected(proc, "negative index")


if __name__ == "__main__":
    unittest.main(verbosity=2)
