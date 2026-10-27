#!/usr/bin/env python3
"""Interactive on-demand sediment mode for Self Evolve.

Subcommands:
  map    — print the dynamic asset map (inventory + core_skills + optional
           asset_owners). Implemented (Task 2).
  commit — privacy-gate an agent-written draft and persist it through the
           proposal lifecycle. Implemented (Task 3).

The agent does analysis + interaction; this script does mechanical lifecycle plumbing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml  # PyYAML is a project dependency

from self_evolve_paths import (  # noqa: E402
    PROPOSALS_ROOT,
    REVIEW_ARCHIVE_ROOT,
    REVIEW_INBOX_ROOT,
    RUNTIME_ROOT,
    SCRIPT_DIR,
    SKILL_ROOT,
    assert_external_write_path,
    assert_runtime_ready,
    _fsync_directory,
)
from proposal_store import ProposalStore, ProposalStoreCorruptionError  # noqa: E402

ASSET_OWNERS_YAML = SKILL_ROOT / "config" / "asset_owners.yaml"
CORE_SKILLS_YAML = SKILL_ROOT / "config" / "core_skills.yaml"
INVENTORY_JSON = RUNTIME_ROOT / "skill-inventory.json"


def load_asset_owners(path: Path) -> list[dict]:
    """Load optional asset_owners.yaml. Missing/empty → []. Malformed → ValueError."""
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML in {path}: {exc}") from exc
    owners = data.get("asset_owners") if isinstance(data, dict) else None
    if owners is None:
        return []
    if not isinstance(owners, list) or not all(isinstance(o, dict) for o in owners):
        raise ValueError(f"asset_owners in {path} must be a list of mappings")
    return owners


def _load_inventory(path: Path) -> dict:
    """Read skill-inventory.json. Raises ``ValueError`` on corrupt JSON.

    The caller must check ``path.exists()`` first to distinguish missing-file
    (graceful "缺失" notice) from corrupt-file (distinct "损坏" notice) — both
    used to collapse to the same ``{}`` and the ambiguity trapped agents in a
    re-generate loop.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(str(exc)) from exc
    return data if isinstance(data, dict) else {}


def _load_core_skills(path: Path) -> dict:
    """Read core_skills.yaml. Missing / malformed → {} (graceful, non-fatal)."""
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        # core_skills is a curated hint layer — if it's broken the map still
        # works off inventory alone. Contrast load_asset_owners, which raises
        # ValueError: asset_owners is small and correctness-critical for
        # routing, so a malformed file there should fail loudly.
        return {}
    return data if isinstance(data, dict) else {}


def _cell(value) -> str:
    """Render a markdown-table cell: None becomes empty and ``|`` is escaped so
    a pipe inside a value cannot break the column grid."""
    if value is None:
        return ""
    return str(value).replace("|", "\\|")


def build_asset_map(
    *,
    inventory_path: Path,
    core_skills_path: Path,
    asset_owners_path: Path,
) -> str:
    """Build a read-only dynamic asset map from three sources.

    All three inputs are optional; missing/corrupt files degrade gracefully so
    the map can always render (e.g. before the first inventory refresh).
    """
    # Inventory: distinguish missing / corrupt / ok. A corrupt file previously
    # collapsed into the "missing" branch and printed the "run refresh" notice,
    # trapping the agent in a re-generate loop (refresh would re-write the same
    # corrupt content if the underlying generator was broken).
    inv: dict = {}
    inventory_state: str = "missing"
    inventory_error: str = ""
    if not inventory_path.exists():
        inventory_state = "missing"
    else:
        try:
            inv = _load_inventory(inventory_path)
            inventory_state = "ok"
        except ValueError as exc:
            inventory_state = "corrupt"
            inventory_error = str(exc)

    if inventory_state == "ok":
        skills_raw = inv.get("skills")
        skills: list = skills_raw if isinstance(skills_raw, list) else []
    else:
        skills = []

    core = _load_core_skills(core_skills_path)
    owners = load_asset_owners(asset_owners_path)

    lines: list[str] = ["# Self Evolve 资产地图", ""]
    if inventory_state == "missing":
        lines += [
            "⚠️ inventory 缺失:先运行 `python3 scripts/refresh_skill_inventory.py` 生成;",
            "  或由 agent 在交互流程中触发自举刷新。",
            "",
        ]
    elif inventory_state == "corrupt":
        lines += [
            f"⚠️ inventory 损坏:{inventory_error}; 检查文件或重新运行 "
            f"`python3 scripts/refresh_skill_inventory.py`。",
            "",
        ]
    else:
        lines.append(f"Inventory skill 总数：{len(skills)}")
        lines.append("")
        # 过期检测：generated_at 超 7 天提示先 refresh，防止 inventory 过期导致 commit
        # 误判 ambiguous 等 silent 降级（过期库存实测坑）。
        gen = inv.get("generated_at") if isinstance(inv, dict) else None
        if gen:
            try:
                import datetime as _dt
                gen_dt = _dt.datetime.strptime(str(gen), "%Y-%m-%d %H:%M:%S")
                if (_dt.datetime.now() - gen_dt).days > 7:
                    lines.append(
                        f"⚠️ inventory 可能过期（生成于 {gen}，超过 7 天）；建议先运行 "
                        f"`python3 scripts/refresh_skill_inventory.py` 刷新再做路由判断。"
                    )
                    lines.append("")
            except ValueError:
                pass

    core_list = core.get("core_skills") if isinstance(core, dict) else []
    if not isinstance(core_list, list):
        core_list = []
    lines.append("## 重点 Skill(core_skills.yaml,Branch A 优先精确匹配)")
    lines.append("")
    if core_list:
        lines.append("| id | 名称 | 功能 | 关键词 | 优先级 |")
        lines.append("|----|------|------|--------|--------|")
        for s in core_list:
            if not isinstance(s, dict):
                continue
            kw = ",".join(s.get("domain_keywords") or []) or "-"
            lines.append(
                f"| `{_cell(s.get('id'))}` | {_cell(s.get('display_name'))} | "
                f"{_cell(s.get('function'))} | {_cell(kw)} | {_cell(s.get('priority'))} |"
            )
    else:
        lines.append("(未配置 core_skills.yaml;Branch A 仅靠 inventory description 兜底匹配)")
    lines.append("")
    lines.append("## 全集 Skill(inventory,Branch A 兜底)")
    lines.append("")
    if skills:
        by_source: dict[str, list[str]] = {}
        for s in skills:
            if not isinstance(s, dict):
                continue
            by_source.setdefault(s.get("source", "?"), []).append(s.get("id", "?"))
        for src, ids in by_source.items():
            preview = ",".join(ids[:12]) + (",..." if len(ids) > 12 else "")
            lines.append(f"- `{src}`({len(ids)}):{preview}")
    else:
        lines.append("(无 inventory)")
    lines.append("")
    lines.append("## 非 skill 资产归属(asset_owners.yaml,可选)")
    lines.append("")
    if owners:
        for o in owners:
            lines.append(
                f"- {o.get('asset_type', '')} → `{o.get('owning_skill', '')}`"
                f" 触发:{','.join(o.get('triggers') or []) or '-'}"
            )
    else:
        lines.append("(为空 — 非 skill finding 走 Branch B 顾问模式)")
    return "\n".join(lines) + "\n"


def _resolve_inventory_target(
    inventory_path: Path | None,
    runtime_root: Path,
    target_skill: str,
) -> tuple[str, str, str]:
    """Resolve a target_skill against the inventory.

    Returns ``(resolution, version, target_content_sha256)`` where resolution is
    one of ``resolved`` / ``missing`` / ``ambiguous``. ``resolved`` requires a
    single matching entry (by ``id`` or ``name``) whose SKILL.md is readable;
    the content hash is the sha256 of that SKILL.md's bytes. Inventory read or
    SKILL.md read failures degrade to ``missing`` rather than raising — the
    caller treats both non-resolved resolutions as candidate-only. (Contrast
    ``_load_inventory``, which raises ValueError on corrupt JSON so
    ``build_asset_map`` can surface a distinct 损坏 notice; commit deliberately
    stays best-effort here.)
    """
    path = inventory_path if inventory_path is not None else (runtime_root / "skill-inventory.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ("missing", "", "")
    skills = data.get("skills") if isinstance(data, dict) else None
    if not isinstance(skills, list):
        return ("missing", "", "")
    matches = [
        s for s in skills
        if isinstance(s, dict) and (s.get("id") == target_skill or s.get("name") == target_skill)
    ]
    if len(matches) == 0:
        return ("missing", "", "")
    if len(matches) > 1:
        # 防御：inventory 可能把同一物理 skill 按多 source 重复登记（source 别名
        # 或过期未 refresh，旧 inventory 可能把同一 Skill 按两个别名各扫一次）。
        # 多条 matches 若指向同一 SKILL.md 文件，折叠成一个走
        # resolved；指向不同文件、或 skill_md 信息缺失无法判定时，才判 ambiguous。
        skill_md_paths: set[str] = set()
        for m in matches:
            raw = m.get("skill_md") or ""
            if not raw:
                base = m.get("path", "")
                raw = f"{base}/SKILL.md" if base else ""
            if raw:
                skill_md_paths.add(raw)
        if len(skill_md_paths) == 1:
            matches = matches[:1]
        else:
            return ("ambiguous", "", "")
    entry = matches[0]
    raw_version = entry.get("version", "")
    version = "" if raw_version is None else str(raw_version)
    skill_md_raw = entry.get("skill_md") or ""
    if not skill_md_raw:
        base = entry.get("path", "")
        skill_md_raw = f"{base}/SKILL.md" if base else ""
    if not skill_md_raw:
        return ("missing", version, "")
    try:
        content = Path(str(skill_md_raw)).expanduser().read_bytes()
    except OSError:
        return ("missing", version, "")
    return ("resolved", version, hashlib.sha256(content).hexdigest())


def commit_proposal(
    *,
    draft: Path,
    proposal_type: str,
    summary: str,
    target_skill: str = "",
    change_points: tuple[str, ...] = (),
    disposition: str = "candidate",
    inventory_path: Path | None = None,
    review_inbox_root: Path = REVIEW_INBOX_ROOT,
    proposals_root: Path = PROPOSALS_ROOT,
    review_archive_root: Path = REVIEW_ARCHIVE_ROOT,
    runtime_root: Path = RUNTIME_ROOT,
) -> tuple[int, dict]:
    """Privacy-gate an agent-written draft and persist it through the proposal lifecycle.

    Returns ``(rc, info)``:
      ``rc == 0`` success; ``rc == 2`` privacy_blocked (fail-closed, nothing
      written); ``rc == 3`` store_error (upsert/decide rejected the lifecycle
      transition — the artifact may already be on disk by then; privacy gate is
      the only fail-closed-for-writing case, per design); ``rc == 4``
      draft_unreadable (nothing written). Explicit temp-dir roots keep this
      function testable without touching the real external state root.
    """
    # 1. Read draft bytes (used for both hashing and the inbox copy).
    draft = draft.expanduser()
    try:
        draft_bytes = draft.read_bytes()
    except OSError as exc:
        return (4, {"status": "draft_unreadable", "error": str(exc)})

    # 2. Privacy gate (fail-closed): lint the draft via privacy_gate.py. If it
    #    flags anything, return before any write happens.
    try:
        gate = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "privacy_gate.py"), str(draft), "--json"],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        # Gate infrastructure unavailable (interpreter/script missing). Fail closed:
        # if privacy cannot be verified, write nothing.
        return (2, {"status": "privacy_blocked", "reason": f"gate unavailable: {exc}"})
    if gate.returncode != 0:
        reason = gate.stderr.strip() or gate.stdout.strip() or "privacy gate blocked"
        return (2, {"status": "privacy_blocked", "reason": reason})

    # 3. Artifact content hash (over the raw draft bytes that were just gated).
    artifact_content_sha256 = hashlib.sha256(draft_bytes).hexdigest()

    # 4. Write artifact to review_inbox_root, no-clobber + atomic (mkstemp + link).
    inbox_resolved = assert_external_write_path(review_inbox_root, label="review_inbox_root")
    inbox_resolved.mkdir(parents=True, exist_ok=True, mode=0o700)
    date_tag = time.strftime("%y%m%d")
    filename = f"{date_tag}_{proposal_type}_{artifact_content_sha256[:16]}.md"
    destination = inbox_resolved / filename
    fd, tmp_name = tempfile.mkstemp(prefix=f".{filename}.", dir=str(inbox_resolved))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(draft_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(tmp_name, destination)
        except FileExistsError:
            # Same content-derived filename already exists → reuse it (no-clobber).
            pass
        os.chmod(destination, 0o600)
        # Durably persist the link entry (content is fsync'd above) — matches the
        # _atomic_json / privacy_gate convention so a crash can't lose the name.
        _fsync_directory(inbox_resolved)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass

    # 5. artifact_ref MUST be the logical "review/inbox/<name>" form: the
    #    ProposalStore's _verify_current_artifact requires parts[:2] ==
    #    ("review", "inbox") when decide(accepted) re-reads & re-hashes the
    #    artifact. deep_dream.py builds the same shape.
    artifact_ref = f"review/inbox/{filename}"
    artifact_path_abs = str(destination)

    # 6. Build the store against the (possibly temp) roots.
    store = ProposalStore(
        root=proposals_root,
        review_inbox_root=inbox_resolved,
        review_archive_root=review_archive_root,
    )

    # 7. Branch: resolved skill_upgrade → upsert + decide(accepted).
    #    Everything else (article, unresolved/ambiguous skill_upgrade) →
    #    candidate-only upsert, no decide (acceptance requires a resolved target).
    try:
        if proposal_type == "skill_upgrade" and target_skill:
            resolution, version, target_content_sha = _resolve_inventory_target(
                inventory_path, runtime_root, target_skill
            )
            if resolution == "resolved":
                state, _created = store.upsert(
                    target_skill=target_skill,
                    target_version=version,
                    proposal_type="skill_upgrade",
                    change_points=change_points,
                    summary=summary,
                    machine_disposition=disposition,
                    artifact_paths=[artifact_ref],
                    privacy_status="passed",
                    artifact_content_sha256=artifact_content_sha256,
                    target_content_sha256=target_content_sha,
                    target_resolution="resolved",
                    actor="interactive-user",
                )
                item_id = state["proposal_id"]
                rev = state["revision_hash"]
                store.decide(
                    item_id,
                    decision="accepted",
                    reason="accepted in-conversation",
                    reviewer="interactive-user",
                    expected_revision_hash=rev,
                    expected_artifact_sha256=artifact_content_sha256,
                )
                return (
                    0,
                    {
                        "status": "committed_accepted",
                        "proposal_id": item_id,
                        "artifact_path": artifact_path_abs,
                        "revision_hash": rev,
                        "artifact_ref": artifact_ref,
                    },
                )
            # Unresolved skill_upgrade: defer as candidate with the diagnostic resolution.
            t_skill = target_skill
            t_version = ""
            t_resolution = resolution  # "missing" or "ambiguous"
            t_content_sha = ""
        elif proposal_type == "article":
            t_skill = ""
            t_version = ""
            t_resolution = "unknown"
            t_content_sha = ""
        else:
            # Non-skill_upgrade type with no target resolution path.
            t_skill = target_skill
            t_version = ""
            t_resolution = "unknown"
            t_content_sha = ""

        state, _created = store.upsert(
            target_skill=t_skill,
            target_version=t_version,
            proposal_type=proposal_type,
            change_points=change_points,
            summary=summary,
            machine_disposition=disposition,
            artifact_paths=[artifact_ref],
            privacy_status="passed",
            artifact_content_sha256=artifact_content_sha256,
            target_content_sha256=t_content_sha,
            target_resolution=t_resolution,
            actor="interactive-user",
        )
        return (
            0,
            {
                "status": "committed_candidate",
                "proposal_id": state["proposal_id"],
                "artifact_path": artifact_path_abs,
                "revision_hash": state["revision_hash"],
                "artifact_ref": artifact_ref,
            },
        )
    except (ValueError, ProposalStoreCorruptionError, OSError, KeyError) as exc:
        # upsert/decide rejected the lifecycle transition (integrity/IO/key
        # errors). Unexpected coding bugs (TypeError/AttributeError) intentionally
        # propagate so they surface as a traceback rather than being masked here.
        return (
            3,
            {
                "status": "store_error",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "artifact_path": artifact_path_abs,
                "artifact_ref": artifact_ref,
            },
        )


def pending_verifications(
    *,
    proposals: list[dict] | None = None,
    proposals_root: Path = PROPOSALS_ROOT,
    review_inbox_root: Path = REVIEW_INBOX_ROOT,
    review_archive_root: Path = REVIEW_ARCHIVE_ROOT,
) -> list[dict]:
    """Return proposals that are applied but not yet verified (outcome pending).

    Drives the verification look-back step of interactive sediment: on each
    sediment trigger, list these so the user can be prompted to look back on
    whether the applied change actually worked. Closes the applied→verified
    half of the loop — otherwise ``verified`` is only ever set by hand and the
    loop stays open.
    """
    if proposals is None:
        store = ProposalStore(
            root=proposals_root,
            review_inbox_root=review_inbox_root,
            review_archive_root=review_archive_root,
        )
        proposals = store.list()
    return [
        proposal
        for proposal in proposals
        if proposal.get("applied_commit") and proposal.get("outcome") == "pending"
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Interactive sediment mode for Self Evolve.")
    sub = parser.add_subparsers(dest="command", required=True)

    map_parser = sub.add_parser("map", help="print the dynamic asset map")
    map_parser.add_argument(
        "--inventory", type=Path, default=INVENTORY_JSON,
        help=f"skill-inventory.json path (default: {INVENTORY_JSON})",
    )
    map_parser.add_argument(
        "--core-skills", type=Path, default=CORE_SKILLS_YAML,
        help=f"core_skills.yaml path (default: {CORE_SKILLS_YAML})",
    )
    map_parser.add_argument(
        "--asset-owners", type=Path, default=ASSET_OWNERS_YAML,
        help=f"asset_owners.yaml path (default: {ASSET_OWNERS_YAML})",
    )

    commit = sub.add_parser("commit", help="privacy-gate and persist a draft proposal")
    commit.add_argument("--draft", type=Path, required=True)
    commit.add_argument(
        "--proposal-type", default="skill_upgrade", choices=["skill_upgrade", "article"],
    )
    commit.add_argument("--summary", required=True)
    commit.add_argument("--target-skill", default="")
    commit.add_argument(
        "--change-points", default="",
        help="comma-separated change points",
    )
    commit.add_argument(
        "--disposition", default="candidate",
        choices=["filtered", "candidate", "duplicate", "covered", "recommended"],
    )

    sub.add_parser(
        "verify-list",
        help="list applied-but-not-verified proposals (for look-back step)",
    )

    args = parser.parse_args(argv)

    if args.command == "map":
        print(
            build_asset_map(
                inventory_path=args.inventory,
                core_skills_path=args.core_skills,
                asset_owners_path=args.asset_owners,
            ),
            end="",
        )
        return 0

    if args.command == "verify-list":
        items = pending_verifications()
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return 0

    # commit
    try:
        assert_runtime_ready()  # production write-boundary guard (migration/claim checks)
    except ValueError as exc:
        print(
            json.dumps({"status": "runtime_not_ready", "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 5

    change_points = (
        tuple(p.strip() for p in args.change_points.split(",") if p.strip())
        if args.change_points else ()
    )
    rc, info = commit_proposal(
        draft=args.draft,
        proposal_type=args.proposal_type,
        summary=args.summary,
        target_skill=args.target_skill,
        change_points=change_points,
        disposition=args.disposition,
    )
    print(json.dumps(info, ensure_ascii=False), file=sys.stdout if rc == 0 else sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
