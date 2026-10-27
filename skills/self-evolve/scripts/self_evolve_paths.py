#!/usr/bin/env python3
"""Shared path policy for Self Evolve.

The skill source tree is immutable program/configuration data. Personal runtime,
review, proposal, panel, and audit artifacts live under one external state root.
"""

from __future__ import annotations

import os
import platform
import hashlib
import json
import tempfile
import time
from pathlib import Path
from typing import Final


SCRIPT_DIR: Final[Path] = Path(__file__).resolve().parent
SKILL_ROOT: Final[Path] = Path(
    os.environ.get("SELF_EVOLVE_SKILL_ROOT")
    or os.environ.get("SKILL_EVOLVE_SKILL_ROOT")
    or SCRIPT_DIR.parent
).expanduser()


def _data_root_from_config() -> Path | None:
    """从 config/data_root.yaml 读可选的 data_root。

    让外部数据根成为 YAML 里可看见、可改的配置项。data_root 与 skill 清单
    分置两文件,各管各的。

    合同（UP-CFG/A-F2）：文件缺失 → 返回 None（用平台默认）；文件存在但
    无法解释（PyYAML 缺失、YAML 损坏、顶层非映射、值非字符串/路径为空）→
    抛 ValueError,由调用方决定报错退出——**存在配置但解释失败绝不安静回退
    平台默认**,否则个人账本会被静默切换到另一个数据根重新扫描。
    """
    cfg = SKILL_ROOT / "config" / "data_root.yaml"
    if not cfg.exists():
        return None
    try:
        import yaml
    except ImportError as exc:
        raise ValueError(
            f"存在 {cfg} 但无法解析: 缺少 PyYAML。请 pip install pyyaml,"
            "或删除该文件改用平台默认/SELF_EVOLVE_DATA_ROOT"
        ) from exc
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"无法读取数据根配置 {cfg}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{cfg} 顶层必须是映射(data_root: ...),现在是 {type(data).__name__}")
    val = data.get("data_root")
    if val is None or (isinstance(val, str) and not val.strip()):
        return None
    if not isinstance(val, str):
        raise ValueError(f"{cfg} 的 data_root 必须是字符串路径,现在是 {type(val).__name__}")
    resolved = Path(val).expanduser()
    if not resolved.is_absolute():
        # 合同要求绝对路径（见 data_root.example.yaml）；相对路径几乎总来自
        # 坏值或截断（如 "{not: valid"），静默采纳会把账本重定向到任意目录。
        raise ValueError(
            f"{cfg} 的 data_root 必须是绝对路径,现在是 {val!r};"
            "留空表示使用平台默认"
        )
    return resolved


def default_data_root() -> Path:
    """外部数据根(个人 runtime/review/proposals/... 的存放处)。

    优先级:环境变量 SELF_EVOLVE_DATA_ROOT > config/data_root.yaml 的 data_root
    > 平台默认。默认地址保持 maoscripts/state/self-evolve,向后兼容、不挪已有数据。

    合同（A-F2）:配置存在但无法解释时不静默回退——错误记入
    ``data_root_config_error()``,由 assert_runtime_ready 在任何状态变更入口
    最先重抛;模块导入仅为路径派生使用回退值,避免所有 CLI 导入即崩。
    """
    configured = os.environ.get("SELF_EVOLVE_DATA_ROOT")
    if configured:
        return Path(configured).expanduser()
    global _DATA_ROOT_CONFIG_ERROR
    try:
        from_cfg = _data_root_from_config()
    except ValueError as exc:
        _DATA_ROOT_CONFIG_ERROR = str(exc)
        from_cfg = None
    if from_cfg is not None:
        return from_cfg
    if platform.system() == "Darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "maoscripts"
            / "state"
            / "self-evolve"
        )

    xdg_state = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg_state).expanduser() if xdg_state else Path.home() / ".local" / "state"
    return base / "self-evolve"


# 必须先于 DATA_ROOT 求值：default_data_root() 在导入期捕获坏配置错误时写入
# 此全局；若初始化行放在后面会把错误覆盖回 None（A-F2 实测踩中）。
_DATA_ROOT_CONFIG_ERROR: str | None = None
DATA_ROOT: Final[Path] = default_data_root()


def data_root_config_error() -> str | None:
    """配置存在但无法解释时的诊断;None 表示配置缺失/有效/被环境变量覆盖。"""
    return _DATA_ROOT_CONFIG_ERROR

# Compatibility: before v0.7.0 both state variables meant the runtime leaf,
# not the shared data root. Keep that interpretation to avoid silently moving
# an explicitly configured installation to <old-runtime>/runtime.
_legacy_runtime_override = os.environ.get("SELF_EVOLVE_RUNTIME_ROOT") or os.environ.get(
    "SELF_EVOLVE_STATE_ROOT"
) or os.environ.get("SKILL_EVOLVE_STATE_ROOT")
RUNTIME_ROOT: Final[Path] = (
    Path(_legacy_runtime_override).expanduser()
    if _legacy_runtime_override
    else DATA_ROOT / "runtime"
)
# 与 session-summaries 同根同级：会话原文 jsonl 的无损双保险备份。
# dream_sweep 写 summary 时同步 cp 原文到此，CC 删除原文后仍可按文件名找回。
RAW_SESSIONS_DIR: Final[Path] = RUNTIME_ROOT / "raw-sessions"
STATE_ROOT: Final[Path] = DATA_ROOT
REVIEW_ROOT: Final[Path] = Path(
    os.environ.get("SELF_EVOLVE_REVIEW_ROOT") or DATA_ROOT / "review"
).expanduser()
REVIEW_INBOX_ROOT: Final[Path] = REVIEW_ROOT / "inbox"
REVIEW_QUARANTINE_ROOT: Final[Path] = REVIEW_ROOT / "quarantine"
REVIEW_ARCHIVE_ROOT: Final[Path] = REVIEW_ROOT / "archive"
PROPOSALS_ROOT: Final[Path] = DATA_ROOT / "proposals"
PANEL_ROOT: Final[Path] = DATA_ROOT / "panel"
AUDIT_ROOT: Final[Path] = DATA_ROOT / "audit"
MIGRATIONS_ROOT: Final[Path] = DATA_ROOT / "migrations"
LAYOUT_PATH: Final[Path] = DATA_ROOT / "layout.json"
MIGRATION_MARKER_PATH: Final[Path] = MIGRATIONS_ROOT / "legacy-state-complete.json"
OWNER_MARKER_NAME: Final[str] = ".self-evolve-root.json"

LEGACY_RUNTIME_ROOT: Final[Path] = SKILL_ROOT / "runtime"
LEGACY_REVIEW_ROOT: Final[Path] = SKILL_ROOT / "review"


def writable_layout_errors() -> list[str]:
    """Return writable roots that would place personal state in the Skill tree."""
    try:
        skill_root = SKILL_ROOT.resolve()
    except OSError:
        skill_root = SKILL_ROOT.absolute()
    errors: list[str] = []
    for name, path in (
        ("data_root", DATA_ROOT),
        ("runtime_root", RUNTIME_ROOT),
        ("review_root", REVIEW_ROOT),
        ("proposals_root", PROPOSALS_ROOT),
        ("panel_root", PANEL_ROOT),
    ):
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path.absolute()
        if resolved == skill_root or skill_root in resolved.parents:
            errors.append(f"{name} must be outside the skill source tree")
    for name, path, role in _claim_roots():
        resolved = _resolve(path)
        if resolved in _unsafe_shared_roots():
            errors.append(f"{name} must be a dedicated leaf, not shared root {resolved}")
            continue
        try:
            is_mount = resolved.exists() and resolved.is_mount()
        except OSError:
            is_mount = False
        if is_mount:
            errors.append(f"{name} must be a directory below a filesystem mount point")
            continue
        if resolved.exists() and not resolved.is_dir():
            errors.append(f"{name} must be a directory")
            continue
        if not resolved.exists() or _owner_marker_valid(resolved, role):
            continue
        try:
            entries = list(resolved.iterdir())
        except OSError:
            errors.append(f"{name} cannot be inspected before ownership is claimed")
            continue
        # Another first-run process may have atomically installed the marker
        # after the validation above but before this directory listing.
        if entries == [resolved / OWNER_MARKER_NAME] and _owner_marker_valid(resolved, role):
            continue
        if entries and not (role == "data_root" and _legacy_layout_claimable(resolved)):
            errors.append(
                f"{name} is a non-empty unclaimed directory; choose a dedicated empty leaf "
                f"or preserve a valid {OWNER_MARKER_NAME}"
            )
    return errors


def _resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser().absolute()


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _mkdir_durable(path: Path) -> None:
    """Create each missing directory and persist its parent entry."""
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    for directory in reversed(missing):
        _fsync_directory(directory.parent)


def _is_within(path: Path, root: Path) -> bool:
    resolved_path = _resolve(path)
    resolved_root = _resolve(root)
    return resolved_path == resolved_root or resolved_root in resolved_path.parents


def _unsafe_shared_roots() -> set[Path]:
    """Return roots that must never be claimed or chmodded by this Skill."""
    candidates = {
        Path("/"),
        Path.home(),
        Path.home().parent,
        Path(tempfile.gettempdir()),
        Path("/tmp"),
        Path("/private/tmp"),
        Path("/var/tmp"),
    }
    return {_resolve(path) for path in candidates}


def _claim_roots() -> list[tuple[str, Path, str]]:
    """Return top-level roots that require an explicit ownership marker."""
    roots: list[tuple[str, Path, str]] = [("data_root", DATA_ROOT, "data_root")]
    for name, path, role in (
        ("runtime_root", RUNTIME_ROOT, "runtime_root"),
        ("review_root", REVIEW_ROOT, "review_root"),
    ):
        if not _is_within(path, DATA_ROOT):
            roots.append((name, path, role))
    unique: list[tuple[str, Path, str]] = []
    seen: set[Path] = set()
    for item in roots:
        resolved = _resolve(item[1])
        if resolved not in seen:
            unique.append(item)
            seen.add(resolved)
    return unique


def _owner_marker_valid(root: Path, role: str) -> bool:
    marker = root / OWNER_MARKER_NAME
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("schema_version") == "1.0"
        and payload.get("owner") == "self-evolve"
        and payload.get("role") == role
        and payload.get("canonical_root") == str(_resolve(root))
    )


def _legacy_layout_claimable(root: Path) -> bool:
    """Recognize a v0.7 state root created before ownership markers existed."""
    try:
        payload = json.loads((root / "layout.json").read_text(encoding="utf-8"))
        layout = payload.get("layout", {})
        configured = Path(str(layout.get("data_root", ""))).expanduser()
    except (OSError, json.JSONDecodeError, AttributeError, TypeError, ValueError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("schema_version") == "2.0"
        and isinstance(layout, dict)
        and bool(str(layout.get("data_root", "")))
        and _resolve(configured) == _resolve(root)
    )


def _claim_root(root: Path, role: str) -> None:
    resolved = _resolve(root)
    _mkdir_durable(resolved)
    marker = resolved / OWNER_MARKER_NAME
    if _owner_marker_valid(resolved, role):
        os.chmod(resolved, 0o700)
        return
    entries = [entry for entry in resolved.iterdir() if entry != marker]
    if entries and not (role == "data_root" and _legacy_layout_claimable(resolved)):
        raise ValueError(f"refusing to claim non-empty state root: {resolved}")
    payload = {
        "schema_version": "1.0",
        "owner": "self-evolve",
        "role": role,
        "canonical_root": str(resolved),
        "claimed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    temporary_name = ""
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{resolved.name}.owner-",
            suffix=".tmp",
            dir=str(resolved.parent),
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o600)
        try:
            # link(2) is a portable no-clobber atomic publish on the same
            # filesystem: readers see either no marker or the complete JSON.
            os.link(temporary_name, marker)
        except FileExistsError:
            if not _owner_marker_valid(resolved, role):
                raise ValueError(f"invalid state-root ownership marker: {marker}") from None
        else:
            directory_fd = os.open(resolved, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if temporary_name:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass
    os.chmod(resolved, 0o700)


def claim_state_roots() -> None:
    """Claim dedicated roots before changing their modes or creating children."""
    errors = writable_layout_errors()
    if errors:
        raise ValueError("; ".join(errors))
    for _name, path, role in _claim_roots():
        _claim_root(path, role)


def assert_external_write_path(path: Path, *, label: str = "write_path") -> Path:
    """Resolve and validate a caller-supplied destination before any write."""
    resolved = path.expanduser().resolve()
    skill_root = SKILL_ROOT.resolve()
    if resolved == skill_root or skill_root in resolved.parents:
        raise ValueError(f"{label} must be outside the skill source tree")
    if resolved in _unsafe_shared_roots():
        raise ValueError(f"{label} must not be a shared filesystem root")
    return resolved


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    _mkdir_durable(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary).replace(path)
        os.chmod(path, 0o600)
        _fsync_directory(path.parent)
    finally:
        try:
            Path(temporary).unlink()
        except FileNotFoundError:
            pass


def ensure_state_dirs(*, write_layout: bool = True) -> None:
    """Create the bounded directories used by runtime commands."""
    claim_state_roots()
    directories = (
        DATA_ROOT,
        RUNTIME_ROOT,
        REVIEW_INBOX_ROOT,
        REVIEW_QUARANTINE_ROOT,
        REVIEW_ARCHIVE_ROOT,
        PROPOSALS_ROOT,
        PANEL_ROOT,
        AUDIT_ROOT,
        MIGRATIONS_ROOT,
    )
    for path in directories:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path, 0o700)
    if write_layout and not LAYOUT_PATH.exists():
        _atomic_json(
            LAYOUT_PATH,
            {
                "schema_version": "2.0",
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "layout": state_layout(include_skill_root=False),
            },
        )


# OS 生成的元数据文件（如 macOS .DS_Store），不能当 state 文件管：纳入会让
# migration marker 持续 flaky（Finder 自动改写 .DS_Store → 指纹变 → marker 失效 →
# migration_required 又 True → assert_runtime_ready 阻断）。该问题由 Finder
# 自动改写元数据文件触发，保留机制说明即可。
IGNORED_STATE_FILENAMES: Final[frozenset[str]] = frozenset({".DS_Store"})


def is_ignored_state_file(path: Path) -> bool:
    """True for OS-generated metadata files that must not be tracked as state."""
    return path.name in IGNORED_STATE_FILENAMES


# v1.0.0: legacy 源码树里的"活跃产出"——v0.7.0 后这些应全部写 external（DATA_ROOT）。
# 即使因路径 bug 残留在 legacy，也不算"需迁移冻结 state"，不参与 marker sha256 校验，
# 避免其追加/重写触发 migration_marker_valid flaky（legacy source-index
# 被一次 backfill 写入曾致 marker 反复失效，此为根治性防御）。
LEGACY_RUNTIME_ACTIVE_SUBTREES: Final[frozenset[str]] = frozenset({
    "dreaming", "session-summaries", "panel", "logs", "scheduler", "learning-candidates",
})
LEGACY_RUNTIME_ACTIVE_FILES: Final[frozenset[str]] = frozenset({
    "evaluation-log.jsonl", "hook-runs.jsonl", "skill-inventory.json",
    "skill-inventory.md", "extraction_sessions.json",
})


def is_legacy_active_artifact(path: Path) -> bool:
    """True for legacy 源码树活跃产出（非冻结 state），不计入迁移 marker 校验。"""
    try:
        runtime_rel = path.relative_to(LEGACY_RUNTIME_ROOT)
    except ValueError:
        runtime_rel = None
    if runtime_rel is not None:
        top = runtime_rel.parts[0] if runtime_rel.parts else ""
        if top in LEGACY_RUNTIME_ACTIVE_SUBTREES:
            return True
        return path.name in LEGACY_RUNTIME_ACTIVE_FILES
    try:
        review_rel = path.relative_to(LEGACY_REVIEW_ROOT)
    except ValueError:
        return False
    top = review_rel.parts[0] if review_rel.parts else ""
    return top == "output"


def legacy_state_files() -> list[Path]:
    """Return mutable in-tree legacy files, excluding the versioned placeholder
    and OS metadata (e.g. macOS .DS_Store) that cannot be tracked stably."""
    files: list[Path] = []
    if LEGACY_RUNTIME_ROOT.is_dir():
        files.extend(
            path
            for path in LEGACY_RUNTIME_ROOT.rglob("*")
            if path.is_file() and not is_ignored_state_file(path) and not is_legacy_active_artifact(path)
        )
    if LEGACY_REVIEW_ROOT.is_dir():
        placeholder = LEGACY_REVIEW_ROOT / "archive" / "README.md"
        files.extend(
            path
            for path in LEGACY_REVIEW_ROOT.rglob("*")
            if path.is_file() and path != placeholder and not is_ignored_state_file(path) and not is_legacy_active_artifact(path)
        )
    return sorted(files, key=lambda path: str(path))


def legacy_state_present() -> bool:
    """Return whether old in-tree runtime state requires a blocking migration.

    v0.7.0 keeps only ``review/archive/README.md`` as a source-tree placeholder.
    Any other review file is mutable legacy state and must be copied explicitly.
    """
    return bool(legacy_state_files())


def migration_required() -> bool:
    """Fail closed until an explicit copy migration records completion."""
    return legacy_state_present() and not migration_marker_valid()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def migration_marker_valid() -> bool:
    """Verify the completion marker and its immutable migration manifest."""
    try:
        marker = json.loads(MIGRATION_MARKER_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(marker, dict) or marker.get("schema_version") != "1.1":
        return False
    if marker.get("source_files_preserved") is not True:
        return False
    manifest_name = marker.get("manifest")
    manifest_sha256 = marker.get("manifest_sha256")
    if not isinstance(manifest_name, str) or Path(manifest_name).name != manifest_name:
        return False
    if not isinstance(manifest_sha256, str) or not re_full_sha256(manifest_sha256):
        return False
    manifest = MIGRATIONS_ROOT / manifest_name
    try:
        if _sha256_file(manifest) != manifest_sha256:
            return False
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
        return False
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return False
    try:
        conflicts = int(summary.get("conflict", 0) or 0)
        errors = int(summary.get("error", 0) or 0)
    except (TypeError, ValueError):
        return False
    if conflicts != 0 or errors != 0:
        return False
    operations = payload.get("operations", [])
    if not isinstance(operations, list):
        return False
    covered_sources = {
        str(_resolve(Path(str(operation.get("source", ""))))): str(
            operation.get("source_sha256", "")
        )
        for operation in operations
        if isinstance(operation, dict)
        and operation.get("status") in {"copied", "same"}
        and operation.get("source")
    }
    for source in legacy_state_files():
        expected = covered_sources.get(str(_resolve(source)))
        try:
            actual = _sha256_file(source)
        except OSError:
            return False
        if not expected or expected != actual:
            return False
    return True


def re_full_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def assert_runtime_ready() -> None:
    """Apply the shared write boundary for every state-mutating entry point."""
    os.umask(0o077)
    if _DATA_ROOT_CONFIG_ERROR:
        # A present-but-uninterpretable data_root must never silently fall back
        # to the platform default: that would re-scan personal history into a
        # different ledger. Fail closed before any state directory is touched.
        raise ValueError(_DATA_ROOT_CONFIG_ERROR)
    errors = writable_layout_errors()
    if errors:
        raise ValueError("; ".join(errors))
    if legacy_state_present() and not migration_marker_valid():
        raise ValueError(
            "migration_required: preview with scripts/migrate_state.py --dry-run, "
            "then apply with scripts/migrate_state.py --apply"
        )
    ensure_state_dirs()


def state_layout(*, include_skill_root: bool = True) -> dict[str, str]:
    """Return a serializable state layout for diagnostics and panels."""
    layout = {
        "data_root": str(DATA_ROOT),
        "state_root": str(STATE_ROOT),
        "runtime_root": str(RUNTIME_ROOT),
        "raw_sessions_dir": str(RAW_SESSIONS_DIR),
        "review_root": str(REVIEW_ROOT),
        "review_inbox_root": str(REVIEW_INBOX_ROOT),
        "review_quarantine_root": str(REVIEW_QUARANTINE_ROOT),
        "review_archive_root": str(REVIEW_ARCHIVE_ROOT),
        "proposals_root": str(PROPOSALS_ROOT),
        "panel_root": str(PANEL_ROOT),
        "legacy_runtime_root": str(LEGACY_RUNTIME_ROOT),
        "legacy_review_root": str(LEGACY_REVIEW_ROOT),
    }
    if include_skill_root:
        layout["skill_root"] = str(SKILL_ROOT)
    return layout
