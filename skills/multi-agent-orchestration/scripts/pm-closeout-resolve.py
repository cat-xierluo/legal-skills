#!/usr/bin/env python3
"""pm-closeout 的窄冲突解决器；只自动处理已声明的模式。"""

import argparse
import os
import pathlib
import re
import subprocess
import tempfile


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=False
    )


def run_git_bytes(*args: str, input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args], input=input_bytes, capture_output=True, check=False
    )


def fail(code: str, detail: str = "") -> "NoReturn":
    suffix = f": {detail}" if detail else ""
    print(f"{code}{suffix}")
    raise SystemExit(3)


def unmerged_paths() -> set[str]:
    result = run_git("diff", "--name-only", "--diff-filter=U")
    if result.returncode != 0:
        print("PM_CLOSEOUT_CONFLICT_SCAN_FAILED:", result.stderr.strip())
        raise SystemExit(3)
    return {line for line in result.stdout.splitlines() if line.strip()}


def git_oid(revision: str) -> str:
    result = run_git("rev-parse", "--verify", f"{revision}^{{commit}}")
    if result.returncode != 0 or not result.stdout.strip():
        fail("PM_CLOSEOUT_MAKEFILE_INVALID_REVISION", revision)
    return result.stdout.strip()


def tree_entry(revision: str, path: str) -> tuple[str, str]:
    result = run_git("ls-tree", revision, "--", path)
    match = re.fullmatch(r"(\d+) blob ([0-9a-f]+)\t" + re.escape(path), result.stdout.strip())
    if result.returncode != 0 or match is None:
        fail("PM_CLOSEOUT_MAKEFILE_TREE_ENTRY_INVALID", f"{revision}:{path}")
    mode, oid = match.groups()
    if mode not in {"100644", "100755"}:
        fail("PM_CLOSEOUT_MAKEFILE_TREE_MODE_UNSAFE", f"{revision}:{mode}")
    return mode, oid


def makefile_stage3_entry() -> tuple[str, str]:
    result = run_git("ls-files", "-u", "--", "Makefile")
    if result.returncode != 0:
        fail("PM_CLOSEOUT_MAKEFILE_INDEX_READ_FAILED", result.stderr.strip())
    entries: dict[int, tuple[str, str]] = {}
    for line in result.stdout.splitlines():
        match = re.match(r"^(\d+) ([0-9a-f]+) ([123])\tMakefile$", line)
        if match:
            mode, oid, stage = match.groups()
            entries[int(stage)] = (mode, oid)
    if set(entries) != {1, 2, 3} or any(
        mode not in {"100644", "100755"} for mode, _oid in entries.values()
    ):
        fail(
            "PM_CLOSEOUT_MAKEFILE_UNSAFE_INDEX_STAGES",
            repr(entries),
        )
    return entries[3]


def prepare_makefile_replay(
    worker_base_revision: str,
    worker_tip_revision: str,
    main_revision: str,
) -> tuple[bytes, int, str, str, str]:
    """Return replayed Makefile bytes without touching the conflicted worktree."""

    if not worker_base_revision or not worker_tip_revision or not main_revision:
        fail(
            "PM_CLOSEOUT_MAKEFILE_FROZEN_RANGE_REQUIRED",
            "the caller must freeze worker base/tip and the candidate main commit",
        )

    worker_base_oid = git_oid(worker_base_revision)
    worker_tip_oid = git_oid(worker_tip_revision)
    main_oid = git_oid(main_revision)
    merge_head = git_oid("MERGE_HEAD")
    if merge_head != main_oid:
        fail(
            "PM_CLOSEOUT_MAKEFILE_BASE_MISMATCH",
            f"MERGE_HEAD={merge_head} expected={main_oid}",
        )

    base_ancestor = run_git(
        "merge-base", "--is-ancestor", worker_base_oid, worker_tip_oid
    )
    if base_ancestor.returncode != 0:
        fail(
            "PM_CLOSEOUT_MAKEFILE_INVALID_WORKER_RANGE",
            f"base={worker_base_oid} tip={worker_tip_oid}",
        )
    tip_ancestor = run_git("merge-base", "--is-ancestor", worker_tip_oid, "HEAD")
    if tip_ancestor.returncode != 0:
        fail(
            "PM_CLOSEOUT_MAKEFILE_WORKER_TIP_NOT_ANCESTOR",
            worker_tip_oid,
        )

    worker_base_entry = tree_entry(worker_base_oid, "Makefile")
    worker_tip_entry = tree_entry(worker_tip_oid, "Makefile")
    if worker_base_entry[0] != worker_tip_entry[0]:
        fail(
            "PM_CLOSEOUT_MAKEFILE_MODE_CHANGE_UNSUPPORTED",
            f"base={worker_base_entry[0]} tip={worker_tip_entry[0]}",
        )

    changed = run_git(
        "diff",
        "--name-status",
        "--no-renames",
        worker_base_oid,
        worker_tip_oid,
        "--",
        "Makefile",
    )
    if changed.returncode != 0 or changed.stdout.splitlines() != ["M\tMakefile"]:
        fail(
            "PM_CLOSEOUT_MAKEFILE_WORKER_PATCH_UNSAFE",
            changed.stdout.strip() or "missing Makefile modification",
        )

    patch = run_git_bytes(
        "diff",
        "--binary",
        "--full-index",
        "--no-renames",
        worker_base_oid,
        worker_tip_oid,
        "--",
        "Makefile",
    )
    if patch.returncode != 0 or not patch.stdout:
        fail(
            "PM_CLOSEOUT_MAKEFILE_PATCH_BUILD_FAILED",
            patch.stderr.decode(errors="replace").strip(),
        )

    stage3 = run_git_bytes("show", ":3:Makefile")
    main_makefile = run_git_bytes("show", f"{main_oid}:Makefile")
    if stage3.returncode != 0 or main_makefile.returncode != 0:
        fail(
            "PM_CLOSEOUT_MAKEFILE_STAGE3_MISSING",
            stage3.stderr.decode(errors="replace").strip(),
        )
    stage3_entry = makefile_stage3_entry()
    main_entry = tree_entry(main_oid, "Makefile")
    if stage3.stdout != main_makefile.stdout or stage3_entry != main_entry:
        fail(
            "PM_CLOSEOUT_MAKEFILE_STAGE3_NOT_MAIN",
            f"main={main_oid} stage3={stage3_entry} main_entry={main_entry}",
        )
    mode = 0o755 if main_entry[0] == "100755" else 0o644

    with tempfile.TemporaryDirectory(prefix="pm-closeout-makefile-") as temporary:
        isolated_root = pathlib.Path(temporary)
        init = subprocess.run(
            ["git", "init", "-q"], cwd=isolated_root, capture_output=True, check=False
        )
        if init.returncode != 0:
            fail(
                "PM_CLOSEOUT_MAKEFILE_REPLAY_ENV_FAILED",
                init.stderr.decode(errors="replace").strip(),
            )
        isolated_makefile = isolated_root / "Makefile"
        isolated_makefile.write_bytes(stage3.stdout)
        isolated_makefile.chmod(mode)

        check = subprocess.run(
            ["git", "apply", "--check", "--binary", "--no-index", "-"],
            cwd=isolated_root,
            input=patch.stdout,
            capture_output=True,
            check=False,
        )
        if check.returncode != 0:
            fail(
                "PM_CLOSEOUT_MAKEFILE_REPLAY_CONFLICT",
                check.stderr.decode(errors="replace").strip(),
            )
        apply_result = subprocess.run(
            ["git", "apply", "--binary", "--no-index", "-"],
            cwd=isolated_root,
            input=patch.stdout,
            capture_output=True,
            check=False,
        )
        if apply_result.returncode != 0:
            fail(
                "PM_CLOSEOUT_MAKEFILE_REPLAY_FAILED",
                apply_result.stderr.decode(errors="replace").strip(),
            )
        replayed = isolated_makefile.read_bytes()

    return replayed, mode, worker_base_oid, worker_tip_oid, main_oid


def atomic_write(path: pathlib.Path, content: bytes, mode: int) -> None:
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.pm-closeout.", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def keep_both(text: str) -> str:
    def resolve(match: re.Match[str]) -> str:
        lines = [
            line
            for line in (match.group(1) + "\n" + match.group(2)).splitlines()
            if line.strip()
        ]
        return "\n".join(lines) + "\n"

    return re.sub(
        r"(?ms)^<<<<<<< HEAD\n(.*?)\n=======\n(.*?)\n>>>>>>> [^\n]+\n?",
        resolve,
        text,
    )


parser = argparse.ArgumentParser()
parser.add_argument("--worker-base", default="")
parser.add_argument("--worker-tip", default="")
parser.add_argument("--main-commit", default="")
args = parser.parse_args()

known_docs = ("docs/DECISIONS.md", "docs/TASKS.md", "CHANGELOG.md")
initial = unmerged_paths()
if not initial:
    fail("PM_CLOSEOUT_NO_UNMERGED_CONFLICTS")
allowed = {*known_docs, "Makefile"}
unexpected = sorted(initial - allowed)
if unexpected:
    fail("PM_CLOSEOUT_CONFLICT_UNMERGED", repr(unexpected))

resolved: list[str] = []
prepared_docs: dict[str, str] = {}
for relative in known_docs:
    if relative in initial:
        path = pathlib.Path(relative)
        if not path.is_file() or path.is_symlink():
            fail("PM_CLOSEOUT_CONFLICT_UNSAFE_PATH", relative)
        updated = keep_both(path.read_text())
        if "<<<<<<<" in updated or "=======" in updated or ">>>>>>>" in updated:
            fail("PM_CLOSEOUT_CONFLICT_LEFTOVER", relative)
        prepared_docs[relative] = updated

prepared_makefile: tuple[bytes, int, str, str, str] | None = None
if "Makefile" in initial:
    makefile = pathlib.Path("Makefile")
    if makefile.is_symlink() or not makefile.is_file():
        fail("PM_CLOSEOUT_MAKEFILE_UNSAFE_PATH")
    prepared_makefile = prepare_makefile_replay(
        args.worker_base, args.worker_tip, args.main_commit
    )

# 先在隔离目录验证 Makefile patch；全部可解后才改工作树。
for relative, updated in prepared_docs.items():
    path = pathlib.Path(relative)
    path.write_text(updated)
    staged = run_git("add", "--", relative)
    if staged.returncode != 0:
        fail("PM_CLOSEOUT_CONFLICT_STAGE_FAILED", f"{relative} {staged.stderr.strip()}")
    resolved.append(relative)

if prepared_makefile is not None:
    replayed, mode, worker_base_oid, worker_tip_oid, main_oid = prepared_makefile
    hashed = run_git_bytes("hash-object", "-w", "--stdin", input_bytes=replayed)
    if hashed.returncode != 0 or not hashed.stdout.strip():
        fail(
            "PM_CLOSEOUT_CONFLICT_STAGE_FAILED",
            f"Makefile {hashed.stderr.decode(errors='replace').strip()}",
        )
    atomic_write(pathlib.Path("Makefile"), replayed, mode)
    mode_string = "100755" if mode == 0o755 else "100644"
    zero_oid = "0" * 40
    index_transaction = (
        f"0 {zero_oid}\tMakefile\n"
        f"{mode_string} {hashed.stdout.decode().strip()}\tMakefile\n"
    ).encode()
    staged = run_git_bytes(
        "update-index", "--index-info", input_bytes=index_transaction
    )
    if staged.returncode != 0:
        fail(
            "PM_CLOSEOUT_CONFLICT_STAGE_FAILED",
            f"Makefile {staged.stderr.decode(errors='replace').strip()}",
        )
    resolved.append("Makefile")
    print(
        "PM_CLOSEOUT_MAKEFILE_REPLAYED_PENDING_VERIFY: "
        f"worker_base={worker_base_oid} worker_tip={worker_tip_oid} "
        f"origin_main={main_oid}"
    )

left = sorted(unmerged_paths())
if left:
    print("PM_CLOSEOUT_CONFLICT_UNMERGED:", left)
    raise SystemExit(3)

print("PM_CLOSEOUT_CONFLICTS_RESOLVED:", resolved)
