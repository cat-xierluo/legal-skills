#!/usr/bin/env python3
"""Build a release from an explicit file list stored in the selected Git commit."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

EXCLUDED = ("TASKS.md", "DECISIONS.md", "RESULT.md", "config/data_root.yaml",
            "config/core_skills.yaml", "config/asset_owners.yaml", "config/scheduled_tasks.yaml",
            "config/workmode.local.json")
ALLOWLIST = "config/release-files.json"


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args])


def _valid_path(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(part not in (".", "..", "") for part in value.split("/")) and str(path) == value


def _excluded(path: str) -> bool:
    return (path in EXCLUDED or path.startswith("state/") or
            (path.startswith("config/") and ".local." in path.split("/")[-1]))


def _homepage(content: bytes, homepage: str) -> bytes:
    if not homepage or re.search(r"[\r\n\x00]", homepage):
        raise ValueError("invalid_homepage")
    text = content.decode("utf-8")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing_frontmatter")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise ValueError("missing_frontmatter_end")
    matches = [i for i in range(1, end) if re.match(r"^homepage\s*:", lines[i])]
    if len(matches) > 1:
        raise ValueError("duplicate_homepage")
    line = "homepage: " + json.dumps(homepage, ensure_ascii=False) + "\n"
    if matches:
        lines[matches[0]] = line
    else:
        lines.insert(end, line)
    return "".join(lines).encode("utf-8")


def build(repo: Path, oid: str, output_dir: Path, *, homepage: str | None = None,
          skill_path: str | None = None) -> dict:
    oid = _git(repo, "rev-parse", "--verify", f"{oid}^{{commit}}").decode().strip()
    records = _git(repo, "ls-tree", "-r", "-z", "--full-tree", oid).split(b"\0")
    tree = {}
    for record in records:
        if not record:
            continue
        meta, name = record.split(b"\t", 1)
        mode, kind, blob = meta.decode().split()
        tree[name.decode("utf-8")] = (mode, kind, blob)
    if skill_path is None:
        choices = [p for p in ("self-evolve", "skills/self-evolve") if f"{p}/SKILL.md" in tree]
        if len(choices) != 1:
            raise ValueError("skill_path_missing_or_ambiguous")
        skill_path = choices[0]
    if not _valid_path(skill_path):
        raise ValueError("invalid_skill_path")
    prefix = skill_path + "/"
    entries = {p[len(prefix):]: v for p, v in tree.items() if p.startswith(prefix)}
    if ALLOWLIST not in entries:
        raise ValueError("release_allowlist_missing_in_source_oid")
    if any(not _valid_path(path) for path in entries):
        raise ValueError("invalid_source_path")
    if any(mode not in ("100644", "100755") or kind != "blob" for mode, kind, _ in entries.values()):
        raise ValueError("unsupported_symlink_or_git_entry")
    try:
        payload = json.loads(_git(repo, "cat-file", "blob", entries[ALLOWLIST][2]))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("invalid_release_allowlist") from exc
    if not isinstance(payload, dict) or set(payload) != {"files"} or not isinstance(payload["files"], list):
        raise ValueError("invalid_release_allowlist")
    files = payload["files"]
    if (not files or any(not _valid_path(p) or _excluded(p) or p == "release-manifest.json" for p in files)
            or len(files) != len(set(files)) or ALLOWLIST not in files or ".gitignore" not in files):
        raise ValueError("invalid_release_allowlist")
    missing = set(files) - set(entries)
    unknown = {p for p in entries if not _excluded(p)} - set(files)
    if missing:
        raise ValueError("release_allowlist_missing_files: " + ", ".join(sorted(missing)))
    if unknown:
        raise ValueError("release_unreviewed_files: " + ", ".join(sorted(unknown)))
    content = {p: _git(repo, "cat-file", "blob", entries[p][2]) for p in sorted(files)}
    if homepage is not None:
        if "SKILL.md" not in content:
            raise ValueError("release_skill_missing")
        content["SKILL.md"] = _homepage(content["SKILL.md"], homepage)
    bundle = output_dir.resolve() / f"self-evolve-{oid[:12]}"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.mkdir()  # atomic refusal to overwrite
    rows = [{"path": p, "sha256": hashlib.sha256(data).hexdigest()} for p, data in content.items()]
    manifest = {"schema": "self-evolve-release-manifest-v1", "oid": oid, "source_oid": oid,
                "source_skill_path": skill_path, "excluded": list(EXCLUDED),
                "homepage_override": homepage, "files": rows}
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    manifest["manifest_digest"] = digest
    manifest["manifest_sha256"] = digest
    for p, data in content.items():
        target = bundle / p
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (bundle / "release-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"oid": oid, "bundle": str(bundle), "file_count": len(rows), "manifest_sha256": digest,
            "excluded": list(EXCLUDED), "homepage_override": homepage}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--oid", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--skill-path")
    parser.add_argument("--homepage")
    args = parser.parse_args()
    try:
        result = build(args.repo, args.oid, args.output_dir, homepage=args.homepage, skill_path=args.skill_path)
        print(json.dumps({"status": "release_built", **result}, ensure_ascii=False, indent=1))
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
