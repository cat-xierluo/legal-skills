#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pack/unpack bounded artifact bundles for safe cross-machine handoff.

Why: manually pasted base64 bundles across machines have been truncated,
lost their markers, or carried wrong offsets, forcing the receiver to redo
work. This CLI replaces raw base64 paste with an explicit manifest plus
bounded, self-describing chunks so truncation, corruption, and out-of-bounds
payloads are mechanically detectable.

Commands:
- ``pack``      : 1..5 regular files under one source root -> one JSON bundle file
- ``unpack``    : fully verify a bundle, then materialize it into a NEW target dir
- ``emit-chunk``: print exactly one bounded chunk JSON (fixed keys) for terminal transfer

Fixed protocol limits:
- chunk payload: 1000 raw bytes (~1368 base64 chars per emitted chunk)
- per file: 8 MiB; total: 16 MiB; files: 1..5; bundle file: 64 MiB

Safety invariants:
- pack accepts only relative paths to regular files; rejects path traversal,
  absolute paths, backslash paths, symlinks (including any parent component)
  and duplicate paths. The source root itself must not be a symlink.
- the whole bundle is written to a file, never flushed to stdout
- outputs are explicit NEW files/dirs: existing output/target is rejected,
  overwriting never happens, symlink targets are rejected
- unpack verifies manifest key sets/types, base64, offset contiguity, chunk
  completeness, per-file and total size, and SHA256 BEFORE any disk write;
  on any validation failure nothing is written to the target
- manifest holds only the fixed fields below; no environment or free-form
  metadata is captured

Boundary: this tool does NOT replace PR review/acceptance and does not prove
the provenance or trustworthiness of the producing side; it only makes
transfer truncation/corruption detectable.

Standard library only; no network, no git execution, no credential access,
no deletion of pre-existing files. Supports Python 3.9+.
"""

import argparse
import base64
import hashlib
import json
import os
import re
import stat
import sys

SCHEMA = "zcode-gui-artifacts/v1"
CHUNK_SIZE = 1000
MAX_FILES = 5
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_BUNDLE_BYTES = 64 * 1024 * 1024
MAX_STR_LEN = 512
MAX_PATH_LEN = 1024

HEX40_RE = re.compile(r"\A[0-9a-f]{40}\Z")
HEX64_RE = re.compile(r"\A[0-9a-f]{64}\Z")

TOP_KEYS = frozenset(("schema", "task_id", "session_id", "branch", "base",
                      "head", "chunk_size", "files"))
FILE_KEYS = frozenset(("path", "size", "sha256", "chunks"))
CHUNK_KEYS = frozenset(("index", "offset", "length", "base64"))
EMIT_KEYS = frozenset(("schema", "bundle_sha256", "file", "index",
                       "offset", "length", "base64"))


class ArtifactError(Exception):
    """Any rejection: bad input, corrupt bundle, or unsafe target."""


def _is_int(value):
    # bool is a subclass of int in Python; reject it explicitly everywhere.
    return type(value) is int


def _fail(msg):
    raise ArtifactError(msg)


def validate_rel_path(path):
    """Return path components for a strict relative POSIX path, else reject."""
    if not isinstance(path, str) or not path:
        _fail("path must be a non-empty string")
    if len(path) > MAX_PATH_LEN:
        _fail("path longer than %d chars: %r" % (MAX_PATH_LEN, path))
    if "\\" in path:
        _fail("backslash is not allowed in artifact paths: %r" % path)
    if path.startswith("/"):
        _fail("absolute path is not allowed: %r" % path)
    parts = path.split("/")
    for comp in parts:
        if comp == "":
            _fail("empty path component (double or trailing slash): %r" % path)
        if comp == ".":
            _fail("'.' component is not allowed: %r" % path)
        if comp == "..":
            _fail("path traversal '..' is not allowed: %r" % path)
    return parts


def _reject_dup_keys(pairs):
    seen = set()
    for key, _ in pairs:
        if key in seen:
            _fail("duplicate JSON key: %r" % key)
        seen.add(key)
    return dict(pairs)


def load_bundle(path):
    """Read and JSON-parse a bundle file; return (data, bundle_sha256)."""
    if not path:
        _fail("bundle path must be non-empty")
    if os.path.islink(path):
        _fail("bundle path is a symlink: %s" % path)
    try:
        st = os.lstat(path)
    except OSError:
        _fail("bundle file not found: %s" % path)
    if not stat.S_ISREG(st.st_mode):
        _fail("bundle is not a regular file: %s" % path)
    if st.st_size > MAX_BUNDLE_BYTES:
        _fail("bundle file exceeds %d bytes" % MAX_BUNDLE_BYTES)
    with open(path, "rb") as fh:
        raw = fh.read(MAX_BUNDLE_BYTES + 1)
    if len(raw) > MAX_BUNDLE_BYTES:
        _fail("bundle file exceeds %d bytes" % MAX_BUNDLE_BYTES)
    digest = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        _fail("bundle is not valid UTF-8 text")
    try:
        data = json.loads(text, object_pairs_hook=_reject_dup_keys)
    except ValueError as exc:
        _fail("bundle is not valid JSON: %s" % exc)
    if not isinstance(data, dict):
        _fail("bundle root must be a JSON object")
    return data, digest


def validate_manifest(data):
    """Fully validate the manifest and return [(path, verified_bytes), ...].

    Order: top-level keys/types -> per-file path/size/total/hash format ->
    chunk structure (index, offset, length) -> base64 decode -> SHA256.
    No disk writes happen anywhere in this function.
    """
    keys = set(data.keys())
    if keys != set(TOP_KEYS):
        missing = sorted(set(TOP_KEYS) - keys)
        extra = sorted(keys - set(TOP_KEYS))
        _fail("manifest top-level keys mismatch (missing=%s, unexpected=%s)"
              % (missing, extra))
    if data["schema"] != SCHEMA:
        _fail("unsupported schema: %r (expected %r)" % (data["schema"], SCHEMA))
    for field in ("task_id", "session_id", "branch"):
        value = data[field]
        if not isinstance(value, str) or not value or len(value) > MAX_STR_LEN:
            _fail("manifest field %s must be a non-empty string (<= %d chars)"
                  % (field, MAX_STR_LEN))
    for field in ("base", "head"):
        value = data[field]
        if not isinstance(value, str) or not HEX40_RE.match(value):
            _fail("manifest field %s must be 40 lowercase hex chars" % field)
    if not _is_int(data["chunk_size"]) or data["chunk_size"] != CHUNK_SIZE:
        _fail("chunk_size must be exactly %d" % CHUNK_SIZE)
    files = data["files"]
    if not isinstance(files, list) or not (1 <= len(files) <= MAX_FILES):
        _fail("files must be a list of 1..%d entries" % MAX_FILES)

    accepted_parts = []
    seen_paths = set()
    total = 0
    contents = []
    for entry in files:
        if not isinstance(entry, dict) or set(entry.keys()) != set(FILE_KEYS):
            _fail("file entry keys must be exactly %s" % sorted(FILE_KEYS))
        rel = entry["path"]
        parts = validate_rel_path(rel)
        if rel in seen_paths:
            _fail("duplicate file path: %r" % rel)
        seen_paths.add(rel)
        for prev in accepted_parts:
            shorter, longer = ((prev, parts) if len(prev) <= len(parts)
                               else (parts, prev))
            if longer[:len(shorter)] == shorter:
                _fail("file paths nest/conflict: %r vs %r"
                      % ("/".join(prev), "/".join(parts)))
        accepted_parts.append(parts)

        size = entry["size"]
        if not _is_int(size) or size < 0 or size > MAX_FILE_BYTES:
            _fail("file %r: size must be an int within 0..%d (8 MiB)"
                  % (rel, MAX_FILE_BYTES))
        total += size
        if total > MAX_TOTAL_BYTES:
            _fail("total size exceeds %d bytes (16 MiB)" % MAX_TOTAL_BYTES)
        sha = entry["sha256"]
        if not isinstance(sha, str) or not HEX64_RE.match(sha):
            _fail("file %r: sha256 must be 64 lowercase hex chars" % rel)

        chunks = entry["chunks"]
        if not isinstance(chunks, list):
            _fail("file %r: chunks must be a list" % rel)
        count = (size + CHUNK_SIZE - 1) // CHUNK_SIZE
        if len(chunks) != count:
            _fail("file %r: chunk count %d != expected %d for size %d"
                  % (rel, len(chunks), count, size))
        payload = bytearray()
        for i, chunk in enumerate(chunks):
            if not isinstance(chunk, dict) or set(chunk.keys()) != set(CHUNK_KEYS):
                _fail("file %r chunk %d: keys must be exactly %s"
                      % (rel, i, sorted(CHUNK_KEYS)))
            if not _is_int(chunk["index"]) or chunk["index"] != i:
                _fail("file %r chunk %d: index must be contiguous from 0"
                      % (rel, i))
            if not _is_int(chunk["offset"]) or chunk["offset"] != i * CHUNK_SIZE:
                _fail("file %r chunk %d: offset must be index*%d (contiguous, "
                      "no duplicates)" % (rel, i, CHUNK_SIZE))
            length = chunk["length"]
            if not _is_int(length) or length < 1 or length > CHUNK_SIZE:
                _fail("file %r chunk %d: length must be an int within 1..%d"
                      % (rel, i, CHUNK_SIZE))
            if i < count - 1 and length != CHUNK_SIZE:
                _fail("file %r chunk %d: only the final chunk may be short"
                      % (rel, i))
            if i == count - 1 and length != size - i * CHUNK_SIZE:
                _fail("file %r chunk %d: final chunk length %d != remaining %d"
                      % (rel, i, length, size - i * CHUNK_SIZE))
            b64 = chunk["base64"]
            if not isinstance(b64, str):
                _fail("file %r chunk %d: base64 must be a string" % (rel, i))
            try:
                blob = base64.b64decode(b64.encode("ascii"), validate=True)
            except (ValueError, UnicodeEncodeError):
                _fail("file %r chunk %d: invalid base64" % (rel, i))
            if len(blob) != length:
                _fail("file %r chunk %d: decoded %d bytes != declared length %d"
                      % (rel, i, len(blob), length))
            payload += blob
        digest = hashlib.sha256(bytes(payload)).hexdigest()
        if digest != sha:
            _fail("file %r: sha256 mismatch (manifest %s != actual %s)"
                  % (rel, sha, digest))
        contents.append((rel, bytes(payload)))
    return contents


def _chunks_for(data):
    chunks = []
    for offset in range(0, len(data), CHUNK_SIZE):
        piece = data[offset:offset + CHUNK_SIZE]
        chunks.append({
            "index": offset // CHUNK_SIZE,
            "offset": offset,
            "length": len(piece),
            "base64": base64.b64encode(piece).decode("ascii"),
        })
    return chunks


def _check_output_parent(path):
    parent = os.path.dirname(os.path.abspath(path))
    try:
        pst = os.lstat(parent)
    except OSError:
        _fail("parent directory does not exist: %s" % parent)
    if stat.S_ISLNK(pst.st_mode) or not stat.S_ISDIR(pst.st_mode):
        _fail("parent must be a real directory (not a symlink): %s" % parent)


def cmd_pack(args):
    for field in ("task", "session", "branch"):
        value = getattr(args, field)
        if not isinstance(value, str) or not value.strip() or len(value) > MAX_STR_LEN:
            _fail("--%s must be a non-empty string (<= %d chars)"
                  % (field, MAX_STR_LEN))
    if not HEX40_RE.match(args.base or ""):
        _fail("--base must be 40 lowercase hex chars")
    if not HEX40_RE.match(args.head or ""):
        _fail("--head must be 40 lowercase hex chars")

    paths = args.paths
    if not (1 <= len(paths) <= MAX_FILES):
        _fail("pack accepts 1..%d artifacts (got %d)" % (MAX_FILES, len(paths)))
    seen = set()
    for rel in paths:
        validate_rel_path(rel)
        if rel in seen:
            _fail("duplicate artifact path: %r" % rel)
        seen.add(rel)

    root = args.source
    try:
        rst = os.lstat(root)
    except OSError:
        _fail("cannot access source root: %s" % root)
    if stat.S_ISLNK(rst.st_mode):
        _fail("source root must not be a symlink: %s" % root)
    if not stat.S_ISDIR(rst.st_mode):
        _fail("source root must be a directory: %s" % root)

    if os.path.lexists(args.output):
        _fail("output already exists (never overwrite): %s" % args.output)

    # Walk each artifact path component-wise so any symlink (file or parent)
    # is rejected before a single byte is read.
    entries = []
    total = 0
    for rel in paths:
        cur = root
        parts = rel.split("/")
        st = None
        for depth, comp in enumerate(parts):
            cur = os.path.join(cur, comp)
            try:
                st = os.lstat(cur)
            except OSError:
                _fail("artifact not accessible at %r: %s"
                      % ("/".join(parts[:depth + 1]), rel))
            if stat.S_ISLNK(st.st_mode):
                _fail("artifact path contains a symlink at %r: %s"
                      % ("/".join(parts[:depth + 1]), rel))
            if depth < len(parts) - 1 and not stat.S_ISDIR(st.st_mode):
                _fail("artifact parent is not a directory: %s" % rel)
        if not stat.S_ISREG(st.st_mode):
            _fail("artifact is not a regular file: %s" % rel)
        if st.st_size > MAX_FILE_BYTES:
            _fail("file exceeds %d bytes (8 MiB): %s (%d)"
                  % (MAX_FILE_BYTES, rel, st.st_size))
        total += st.st_size
        if total > MAX_TOTAL_BYTES:
            _fail("total size exceeds %d bytes (16 MiB)" % MAX_TOTAL_BYTES)
        entries.append((rel, cur))

    _check_output_parent(args.output)

    file_entries = []
    total_bytes = 0
    chunk_total = 0
    for rel, cur in entries:
        with open(cur, "rb") as fh:
            data = fh.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            _fail("file exceeds %d bytes (8 MiB): %s" % (MAX_FILE_BYTES, rel))
        total_bytes += len(data)
        chunks = _chunks_for(data)
        chunk_total += len(chunks)
        file_entries.append({
            "path": rel,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "chunks": chunks,
        })
    if total_bytes > MAX_TOTAL_BYTES:
        _fail("total size exceeds %d bytes (16 MiB)" % MAX_TOTAL_BYTES)

    manifest = {
        "schema": SCHEMA,
        "task_id": args.task,
        "session_id": args.session,
        "branch": args.branch,
        "base": args.base,
        "head": args.head,
        "chunk_size": CHUNK_SIZE,
        "files": file_entries,
    }
    raw = (json.dumps(manifest, ensure_ascii=True, sort_keys=True,
                      indent=2) + "\n").encode("utf-8")
    with open(args.output, "xb") as fh:
        fh.write(raw)
    sys.stdout.write(json.dumps({
        "bundle": args.output,
        "bundle_sha256": hashlib.sha256(raw).hexdigest(),
        "files": len(file_entries),
        "total_bytes": total_bytes,
        "chunks": chunk_total,
    }, sort_keys=True) + "\n")
    return 0


def cmd_unpack(args):
    data, _ = load_bundle(args.bundle)
    contents = validate_manifest(data)

    target = args.target
    if not target:
        _fail("target must be non-empty")
    if os.path.lexists(target):
        _fail("target already exists (or is a symlink): %s" % target)
    parent = os.path.dirname(os.path.abspath(target))
    try:
        pst = os.lstat(parent)
    except OSError:
        _fail("target parent does not exist: %s" % parent)
    if stat.S_ISLNK(pst.st_mode):
        _fail("target parent is a symlink: %s" % parent)
    if not stat.S_ISDIR(pst.st_mode):
        _fail("target parent is not a directory: %s" % parent)

    # Everything is verified; only now create the target and write. The
    # target did not exist before this command, so on a write failure we
    # remove only what this command created inside it.
    os.mkdir(target)
    try:
        for rel, blob in contents:
            dest = os.path.join(target, *rel.split("/"))
            dirpath = os.path.dirname(dest)
            if dirpath:
                os.makedirs(dirpath, exist_ok=True)
            with open(dest, "xb") as fh:
                fh.write(blob)
    except OSError as exc:
        for walk_root, dirnames, filenames in os.walk(target, topdown=False):
            for name in filenames:
                try:
                    os.unlink(os.path.join(walk_root, name))
                except OSError:
                    pass
            for name in dirnames:
                try:
                    os.rmdir(os.path.join(walk_root, name))
                except OSError:
                    pass
        try:
            os.rmdir(target)
        except OSError:
            pass
        _fail("failed while writing target (rolled back): %s" % exc)

    total = sum(len(blob) for _, blob in contents)
    sys.stdout.write(json.dumps({
        "target": target,
        "files": len(contents),
        "total_bytes": total,
    }, sort_keys=True) + "\n")
    return 0


def cmd_emit_chunk(args):
    if not _is_int(args.chunk) or args.chunk < 0:
        _fail("--chunk must be a non-negative integer")
    data, bundle_sha = load_bundle(args.bundle)
    contents = validate_manifest(data)
    for rel, blob in contents:
        if rel == args.file:
            count = (len(blob) + CHUNK_SIZE - 1) // CHUNK_SIZE
            if args.chunk >= count:
                _fail("chunk index %d out of range for %r (%d chunks)"
                      % (args.chunk, rel, count))
            offset = args.chunk * CHUNK_SIZE
            piece = blob[offset:offset + CHUNK_SIZE]
            emit = {
                "schema": SCHEMA,
                "bundle_sha256": bundle_sha,
                "file": rel,
                "index": args.chunk,
                "offset": offset,
                "length": len(piece),
                "base64": base64.b64encode(piece).decode("ascii"),
            }
            assert set(emit.keys()) == EMIT_KEYS
            sys.stdout.write(json.dumps(emit, sort_keys=True) + "\n")
            return 0
    _fail("file not found in bundle: %r" % args.file)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="zcode-gui-artifacts.py",
        description="Pack/unpack bounded artifact bundles for cross-machine "
                    "handoff (stdlib only, offline).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pk = sub.add_parser("pack", help="pack 1..5 files into one bundle file")
    pk.add_argument("--source", required=True,
                    help="source root directory (must not be a symlink)")
    pk.add_argument("--task", required=True)
    pk.add_argument("--session", required=True)
    pk.add_argument("--branch", required=True)
    pk.add_argument("--base", required=True, help="40 lowercase hex chars")
    pk.add_argument("--head", required=True, help="40 lowercase hex chars")
    pk.add_argument("--output", required=True,
                    help="bundle file to create (must not exist)")
    pk.add_argument("paths", nargs="+", metavar="artifact",
                    help="1..5 relative regular-file paths under --source")

    up = sub.add_parser("unpack",
                        help="verify a bundle fully, then write a NEW target dir")
    up.add_argument("--bundle", required=True)
    up.add_argument("--target", required=True,
                    help="target directory to create (must not exist)")

    ec = sub.add_parser("emit-chunk",
                        help="print one bounded chunk JSON for terminal transfer")
    ec.add_argument("--bundle", required=True)
    ec.add_argument("--file", required=True,
                    help="exact relative path as recorded in the manifest")
    ec.add_argument("--chunk", required=True, type=int,
                    help="0-based chunk index")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.cmd == "pack":
            return cmd_pack(args)
        if args.cmd == "unpack":
            return cmd_unpack(args)
        if args.cmd == "emit-chunk":
            return cmd_emit_chunk(args)
    except ArtifactError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    except OSError as exc:
        print("error: os error: %s" % exc, file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
