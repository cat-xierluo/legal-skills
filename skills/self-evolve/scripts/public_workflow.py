#!/usr/bin/env python3
"""Incremental local scan -> current-Agent packet -> validated HTML. No model API."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import uuid
from collections import Counter, deque
from contextlib import contextmanager, closing
from datetime import datetime, timezone
from pathlib import Path

from dream_sweep import summarize_records, record_text_events, is_context_noise, is_report_noise
from dream_sweep import strip_framework_injection, has_unclosed_host_context
from privacy_gate import sanitize_structured_text
from refresh_skill_inventory import _DEFAULT_AGENT_SKILL_DIRS, build_inventory
from runtime_sessions import ADAPTER_VERSION, Source, discover, load, sources, stamp
from self_evolve_paths import DATA_ROOT, assert_external_write_path, assert_runtime_ready

SCHEMA = "1"
PACKET_SCHEMA = "self-evolve-agent-packet-v1"
ANALYSIS_SCHEMA = "self-evolve-agent-analysis-v1"
MAX_EVIDENCE = 80
MAX_ANALYSIS_BYTES = 2 * 1024 * 1024
MAX_USER_EVIDENCE_CHARS = 100_000
USER_EVIDENCE_TRUNCATED = "<user-turn-budget-truncated>"
USER_QUERY_WRAPPER = re.compile(r"^\s*<user_query>\s*(.*?)\s*</user_query>\s*$",
                                re.IGNORECASE | re.DOTALL)
USER_REQUEST_HEADER = re.compile(r"\s*##\s*My request:\s*", re.IGNORECASE)
CODEX_ATTACHMENT_HEADER = re.compile(r"#\s*Files mentioned by the user\s*:.*?(?=##\s*My request\s*:|\Z)",
                                     re.IGNORECASE | re.DOTALL)
PROFILE_PLACEHOLDER = re.compile(r"<[^<>\n]{1,160}>")
CORRECTION_LANGUAGE = re.compile(
    r"(?:不对|不是这样|这样不行|不行|错了|理解错|写错|说错|误判|不要|别把|别改|请保留|改回|"
    r"wrong|mistake|misunderstood|don't|do not|keep the original|restore)",
    re.IGNORECASE,
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def atomic(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".self-evolve-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        Path(name).replace(path)
    finally:
        Path(name).unlink(missing_ok=True)


def write_json(path: Path, value) -> None:
    atomic(path, json.dumps(value, ensure_ascii=False, indent=2).encode() + b"\n")


@contextmanager
def locked(root: Path):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / "scan.lock").open("a+b") as handle:
        os.chmod(root / "scan.lock", 0o600)
        try:
            if os.name == "nt":  # no mandatory Unix-only dependency
                import msvcrt
                handle.seek(0)
                handle.write(b"0")
                handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("scan_already_running") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


EXPECTED_TABLES = ("meta", "sessions", "runs", "run_sessions", "analyses", "reviewed_evidence")
REQUIRED_COLUMNS = {
    "meta": {"key", "value"},
    "sessions": {"session_key", "runtime", "revision", "adapter", "status",
                 "content_hash", "summary_json", "first_processed",
                 "last_processed", "last_seen", "error"},
    "runs": {"run_id", "started_at", "finished_at", "status",
             "packet_digest", "coverage_json", "stats_json"},
    "run_sessions": {"run_id", "session_key", "outcome"},
    "analyses": {"analysis_id", "run_id", "packet_digest", "created_at",
                 "analysis_hash", "analysis_json"},
    "reviewed_evidence": {"evidence_id", "analysis_id"},
}


def _precheck_ledger_files(path: Path) -> None:
    """Refuse dangerous ledger shapes with zero sqlite side effects (A-F1-R1/R2).

    Even mode=ro connections create/rewrite SHM and recover zero-byte mains,
    so every refusal decision happens on file metadata or a temp COPY only.
    """
    wal = path.with_name(path.name + "-wal")
    shm = path.with_name(path.name + "-shm")
    if not path.exists():
        if wal.exists() or shm.exists():
            # 主库缺失但伴生文件在：不是新用户（新用户应所有文件均不存在），
            # 可写初始化会新建主库并删除原 WAL。
            raise ValueError(
                "unsupported_ledger_schema; 主库缺失但存在 WAL/SHM（疑似崩溃现场），"
                "保留原文件，不自动重建")
        return
    size = path.stat().st_size
    if size == 0:
        if wal.exists() or shm.exists():
            raise ValueError(
                "unsupported_ledger_schema; 零字节主库带未合并 WAL/SHM（疑似崩溃现场），"
                "保留原文件，不自动重建")
        return  # truly fresh: zero-byte main without sidecars initializes cleanly
    # Non-zero main: always validate a temp COPY. 实测无伴生的 WAL 模式主库在
    # 原地 ro 打开后也会创建 WAL/SHM（A-F1-R1-R3-NOSIDECAR），所以无例外全走副本，
    # 副本中 WAL 最新已提交内容仍可读到。
    with tempfile.TemporaryDirectory(prefix="self-evolve-ledger-precheck-") as td:
        copy_root = Path(td)
        shutil.copy2(path, copy_root / path.name)
        for sidecar in (wal, shm):
            if sidecar.exists():
                shutil.copy2(sidecar, copy_root / sidecar.name)
        copy_path = copy_root / path.name
        with closing(sqlite3.connect(copy_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)) as ro:
            ro.execute("PRAGMA query_only=ON")
            _assert_ledger_structure(ro)


def _assert_ledger_structure(ro: sqlite3.Connection) -> None:
    tables = {row[0] for row in ro.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not set(EXPECTED_TABLES).issubset(tables):
        raise ValueError(
            f"unsupported_ledger_schema; 缺表 {sorted(set(EXPECTED_TABLES) - tables)}，"
            "保留原数据库，不自动重建")
    row = ro.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if not row or row[0] != SCHEMA:
        # No version row or a foreign version means this file was not
        # created by the current workflow schema.
        raise ValueError("unsupported_ledger_schema; 保留原数据库，不自动重建")
    for table, required in REQUIRED_COLUMNS.items():
        columns = {r[1] for r in ro.execute(f"PRAGMA table_info({table})")}
        if not required.issubset(columns):
            raise ValueError(
                f"unsupported_ledger_schema; {table} 表列结构与当前版本不符，"
                "保留原数据库，不自动重建")


def _open_database(root: Path) -> sqlite3.Connection:
    path = root / "ledger.sqlite"
    _precheck_ledger_files(path)
    # Verified (or brand-new): now open writable and create any missing tables.
    conn = sqlite3.connect(path, timeout=3)
    try:
        os.chmod(path, 0o600)
        conn.row_factory = sqlite3.Row
        # Keep all state in this dedicated data root. No schema reset on corrupt/unknown versions.
        conn.executescript("""
          CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS sessions(
            session_key TEXT PRIMARY KEY,runtime TEXT NOT NULL,revision TEXT NOT NULL,
            adapter TEXT NOT NULL,status TEXT NOT NULL,content_hash TEXT NOT NULL,
            summary_json TEXT NOT NULL,first_processed TEXT NOT NULL,last_processed TEXT NOT NULL,
            last_seen TEXT NOT NULL,error TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS runs(
            run_id TEXT PRIMARY KEY,started_at TEXT NOT NULL,finished_at TEXT,
            status TEXT NOT NULL,packet_digest TEXT,coverage_json TEXT,stats_json TEXT);
          CREATE TABLE IF NOT EXISTS run_sessions(
            run_id TEXT NOT NULL,session_key TEXT NOT NULL,outcome TEXT NOT NULL,
            PRIMARY KEY(run_id,session_key));
          CREATE TABLE IF NOT EXISTS analyses(
            analysis_id TEXT PRIMARY KEY,run_id TEXT NOT NULL,packet_digest TEXT NOT NULL,
            created_at TEXT NOT NULL,analysis_hash TEXT NOT NULL,analysis_json TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS reviewed_evidence(
            evidence_id TEXT PRIMARY KEY,analysis_id TEXT NOT NULL);
        """)
        row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if row and row[0] != SCHEMA:
            conn.close()
            raise ValueError("unsupported_ledger_schema; 保留原数据库，不自动重建")
        conn.execute("INSERT OR IGNORE INTO meta VALUES('schema_version',?)", (SCHEMA,))
        conn.execute("INSERT OR IGNORE INTO meta VALUES('initialized_at',?)", (now(),))
        conn.commit()
        return conn
    except Exception:
        conn.close()
        raise


@contextmanager
def database(root: Path):
    with closing(_open_database(root)) as conn:
        with conn:
            yield conn


def public_inventory(home: Path) -> list[dict]:
    paths = {alias: home / rel for alias, rel in _DEFAULT_AGENT_SKILL_DIRS if (home / rel).is_dir()}
    paths["zcode"] = home / ".zcode/skills"
    skills = []
    for item in build_inventory(paths)["skills"]:
        skill_id = item["id"]
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", skill_id):
            continue
        try:
            skills.append({"id": skill_id, "description": sanitize_structured_text(item["description"])[:500],
                           "installed_in": item["source_aliases"], "version": sanitize_structured_text(item["version"])[:60]})
        except ValueError:
            continue  # never copy private config / paths into a public packet
    return skills


def summarize(item, inventory: list[dict]) -> tuple[dict, str, str]:
    records, dialect, content_hash, completeness = load(item)
    if not item.row_id and stamp(item.path) != item.revision:
        raise ValueError("source_changed_during_read")
    # App-only page snapshots are wrappers, not user intent or evidence.
    records = [r for r in records if not any(t.strip().startswith("<external_codex_apps_open_page>") for _role,t in record_text_events(r,dialect))]
    # Keep raw user events for provenance validation below. Assistant/tool
    # text is not a correction source, so strip host wrappers when collecting
    # the summary timeline.
    events = [(r, (t if r == "human" else strip_framework_injection(t)))
              for rec in records for r, t in record_text_events(rec, dialect)
              if (t if r == "human" else strip_framework_injection(t)).strip()]
    # Some Codex writers mirror user input across event_msg and response_item.
    # Preserve the record order and collapse adjacent copies only, so a later
    # response turn is never discarded merely because it uses response_item.
    timeline_events: list[tuple[str, str]] = []
    previous: tuple[str, str] | None = None
    for role, text in events:
        if (role, text) == previous:
            continue
        timeline_events.append((role, text))
        previous = (role, text)
    summary = summarize_records(item.path, dialect, records, [], inventory,
                                source_variant=item.source.runtime)
    if summary is None:
        raise ValueError("summary_unavailable")
    if not events:
        # Metadata-only sessions are retained as filtered, never misreported as meaningful dialogue.
        summary.noise_reasons.append("metadata_only")
    safe = lambda text: sanitize_structured_text(str(text))
    # Conservative business-material exclusion: filename labels can contain names
    # even when pattern-based redaction cannot reliably infer every person name.
    private_business = bool(re.search(r"司法鉴定|鉴定意见书|起诉状|判决书|法院通知|送达文书", summary.topic_title))
    if private_business:
        return {"runtime": item.source.runtime, "reason": "business_material_requires_manual_review"}, content_hash, "quarantined"
    title = safe(summary.topic_title)[:200]
    excerpts = [safe(t)[:1000] for t in summary.evidence_snippets[:6]]
    # Authoritative role provenance: excerpts stay untyped, but the texts the
    # reader actually typed are kept separately so downstream contracts can tell
    # a user turn from an agent turn without guessing from wording.
    user_excerpts = []
    user_chars = 0
    user_turns_truncated = False
    if completeness != "index_excerpt":
        # Index excerpts have no reliable roles (the search index stores flat text).
        saw_assistant = False
        for role, text in timeline_events:
            if role == "assistant":
                saw_assistant = True
                continue
            if role != "human" or not saw_assistant:
                continue
            # A truncated or mismatched host wrapper means the whole turn
            # cannot be trusted as human words: check the raw turn, before
            # paired-block stripping can hide a cross-type close or a nested
            # opener. Only then strip the well-formed wrappers.
            if has_unclosed_host_context(text):
                continue
            text = strip_framework_injection(text)
            if is_context_noise(text):
                continue
            wrapped = USER_QUERY_WRAPPER.fullmatch(text)
            if wrapped:
                text = wrapped.group(1)
            # Codex prefixes attached-file listings (with host boilerplate) to
            # the real request inside one user turn; only the text after the
            # request separator is the reader's own words. When the separator
            # is absent the whole turn is attachment scaffolding and is dropped.
            if CODEX_ATTACHMENT_HEADER.search(text):
                text = CODEX_ATTACHMENT_HEADER.sub("", text)
                text = USER_REQUEST_HEADER.sub("", text)
                cleaned = re.sub(r"\s+", " ", text).strip()
                if not cleaned:
                    continue
            text = USER_REQUEST_HEADER.sub("", text)
            cleaned = re.sub(r"\s+", " ", text).strip()
            if not cleaned:
                continue
            # Keep later correction turns too: a hard six-turn cap silently erased
            # nearly all material in active sessions. Individual turns remain
            # bounded; the per-session aggregate has an explicit truncation marker.
            excerpt = safe(cleaned)[:2000]
            if user_chars + len(excerpt) > MAX_USER_EVIDENCE_CHARS:
                user_turns_truncated = True
                break
            user_excerpts.append(excerpt)
            user_chars += len(excerpt)
        user_excerpts = list(dict.fromkeys(user_excerpts))
        if user_turns_truncated:
            user_excerpts.append(USER_EVIDENCE_TRUNCATED)
    # Index text is often one long line, which the legacy report-noise filter drops.
    # Keep bounded, explicitly untyped excerpts rather than inventing user/assistant roles.
    if completeness == "index_excerpt" and not excerpts:
        chunks = [t.strip() for rec in records for _role, t in record_text_events(rec, dialect)]
        pieces = [part for text in chunks for part in re.split(r"(?<=[。！？.!?])\s*|[\n\r]+", text) if 12 <= len(part.strip()) <= 1000 and not is_report_noise(part)]
        if not pieces:
            pieces = [text[i:i+600] for text in chunks for i in range(0, min(len(text), 24000), 600)]
        if pieces:
            excerpts = [safe(pieces[round(i*(len(pieces)-1)/max(1,min(6,len(pieces))-1))])[:1000] for i in range(min(6,len(pieces)))]
    signals = [safe(t)[:300] for t in (summary.upgrade_signals + summary.article_signals)[:8]]
    decisions = [safe(t)[:500] for t in summary.decisions[:6]]
    # A conservative triage, not a semantic quality score; borderline material remains visible.
    selected = bool(events and excerpts and (signals or summary.summary_policy in {"summarize_candidate", "cluster_candidate", "aggregate_only"}))
    sid = summary.session_id
    session_ref = "s-" + hashlib.sha256(sid.encode()).hexdigest()[:24]
    semantic_hash = digest(events)
    evidence = "ev-" + digest([session_ref, semantic_hash])[:24]
    value = {"evidence_id": evidence, "session_ref": session_ref, "runtime": item.source.runtime,
             "title": title, "class": summary.session_class, "selected": selected,
             "reason": "可复用/纠错/写作信号，等待 Agent 判断" if selected else "确定性初筛未发现明显信号；非最终价值判断",
             "completeness": completeness, "excerpts": excerpts, "user_excerpts": user_excerpts,
             "signals": signals, "decisions": decisions,
             "related_skills": list(dict.fromkeys(s for s in summary.related_skills if any(s == x["id"] for x in inventory)))}
    return value, content_hash, "selected" if selected else "filtered"


def _coverage(catalog) -> list[dict]:
    return [{"runtime": s.runtime, "format": s.format, "status": s.status,
             "discovered": s.discovered, "errors": s.errors} for s in catalog]


def _empty_session_summary(item) -> dict:
    """Minimal, honest summary for structurally valid sessions with no conversation."""
    sid = str(item.row_id[1] if item.row_id else item.path.stem)
    session_ref = "s-" + hashlib.sha256(sid.encode()).hexdigest()[:24]
    return {"evidence_id": "ev-" + digest([session_ref, "empty_session"])[:24],
            "session_ref": session_ref, "runtime": item.source.runtime,
            "title": "（空会话：结构有效但无对话内容）", "class": "empty_session", "selected": False,
            "reason": "结构有效但无对话消息；非读取失败", "completeness": "empty",
            "excerpts": [], "signals": [], "decisions": [], "related_skills": []}


def _save_session(conn, item, status, summary, content_hash, error=""):
    ts = now()
    conn.execute("""INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(session_key) DO UPDATE SET revision=excluded.revision,adapter=excluded.adapter,
        status=excluded.status,content_hash=excluded.content_hash,summary_json=excluded.summary_json,
        last_processed=excluded.last_processed,last_seen=excluded.last_seen,error=excluded.error""",
        (item.key, item.source.runtime, item.revision, ADAPTER_VERSION, status, content_hash,
         json.dumps(summary, ensure_ascii=False), ts, ts, ts, error))



def publish_report(run_dir: Path, stem: str, packet: dict, analysis: dict | None, *, require_existing: bool = False, adoptions: dict | None = None) -> int:
    """Publish every secondary page before the overview; never replace a prior snapshot."""
    from public_report import render_bundle
    options = {"adoptions": adoptions} if adoptions is not None else {}
    bundle = {name: html.encode() for name, html in render_bundle(packet, analysis, stem=stem, **options).items()}
    for name, raw in bundle.items():
        path = run_dir / name
        if path.exists():
            if not path.is_file() or path.is_symlink() or path.read_bytes() != raw:
                raise ValueError("report_bundle_changed")
        elif require_existing:
            raise ValueError("report_bundle_incomplete")
    if not require_existing:
        overview = stem + ".html"
        # Only expose the overview after all sibling pages are present.
        for name in [n for n in bundle if n != overview] + [overview]:
            path = run_dir / name
            if not path.exists():
                atomic(path, bundle[name])
        if any((run_dir / name).read_bytes() != raw for name,raw in bundle.items()):
            raise ValueError("report_bundle_changed")
    return len(bundle)


def scan(root: Path, home: Path, custom: list[str], max_sessions: int) -> dict:
    if not 1 <= max_sessions <= 10000:
        raise ValueError("max_sessions 必须介于 1 和 10000")
    sources(home, custom)  # reject invalid arguments before ledger mutation
    with locked(root), database(root) as conn:
        profile_row = conn.execute("SELECT value FROM meta WHERE key='scan_profile'").fetchone()
        profile = json.loads(profile_row[0]) if profile_row else {}
        if profile and profile.get("home") != str(home):
            raise ValueError("scan_profile_home_mismatch; 使用原主目录或单独数据根")
        # Explicit custom roots are remembered for subsequent scheduled calls.
        custom = custom or profile.get("custom_sources", [])
        catalog = sources(home, custom)
        catalog_keys = {(s.runtime,s.format,str(s.root.resolve())) for s in catalog}
        for known in profile.get("known_sources", []):
            key = (known["runtime"],known["format"],known["root"])
            if key not in catalog_keys:
                catalog.append(Source(known["runtime"],known["format"],Path(known["root"])))
                catalog_keys.add(key)
        remembered = [{"runtime":s.runtime,"format":s.format,"root":str(s.root.resolve())} for s in catalog if s.root.exists() or any(k.get("root")==str(s.root.resolve()) for k in profile.get("known_sources",[]))]
        conn.execute("INSERT OR REPLACE INTO meta VALUES('scan_profile',?)", (json.dumps({"home":str(home),"custom_sources":custom,"known_sources":remembered}),))
        conn.execute("UPDATE runs SET status='interrupted',finished_at=? WHERE status='running'", (now(),))
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
        started = now()
        conn.execute("INSERT INTO runs(run_id,started_at,status) VALUES(?,?,'running')", (run_id, started))
        conn.commit()  # a killed process leaves an observable interrupted scan
        found = discover(catalog)
        stats = Counter(discovered=len(found))
        pending: dict[str, deque] = {}
        for item in found:
            existing = conn.execute("SELECT revision,adapter,status FROM sessions WHERE session_key=?", (item.key,)).fetchone()
            if existing and existing["revision"] == item.revision and existing["adapter"] == ADAPTER_VERSION and existing["status"] in {"selected", "filtered", "quarantined"}:
                conn.execute("UPDATE sessions SET last_seen=? WHERE session_key=?", (now(), item.key))
                conn.execute("INSERT INTO run_sessions VALUES(?,?,'unchanged')", (run_id, item.key))
                stats["unchanged"] += 1
            else:
                pending.setdefault(item.source.runtime, deque()).append((item, bool(existing)))
        for runtime, queue in pending.items():
            # New/changed evidence first; repeated failures must not starve untouched history.
            def priority(entry):
                item, _ = entry
                previous = conn.execute("SELECT status FROM sessions WHERE session_key=?", (item.key,)).fetchone()
                try:
                    modified = int(item.revision.split(":")[0 if item.row_id else 1])
                except (ValueError, IndexError):
                    modified = 0
                return (bool(previous and previous[0] == "failed"), -modified, item.key)
            pending[runtime] = deque(sorted(queue, key=priority))
        inventory = public_inventory(home)
        processed = 0
        failures = []
        while any(pending.values()) and processed < max_sessions:
            # Fairness: one pending source per runtime each cycle; no high-volume source starvation.
            for queue in pending.values():
                if not queue or processed >= max_sessions:
                    continue
                item, existed = queue.popleft()
                try:
                    summary, content_hash, status = summarize(item, inventory)
                    _save_session(conn, item, status, summary, content_hash)
                    outcome = "updated" if existed else "new"
                    stats[outcome] += 1
                    stats[status] += 1
                except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
                    # Error category only: exception messages may contain transcript or private paths.
                    error = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r"[a-z0-9_]+", str(exc)) else type(exc).__name__
                    if error == "empty_session":
                        # Structurally valid but conversation-less: bookkept as filtered,
                        # never inflating failure stats or degrading source status.
                        _save_session(conn, item, "filtered", _empty_session_summary(item), "")
                        outcome = "updated" if existed else "new"
                        stats[outcome] += 1
                        stats["empty"] += 1
                        stats["filtered"] += 1
                    else:
                        _save_session(conn, item, "failed", {}, "", error)
                        outcome = "failed"
                        stats["failed"] += 1
                        item.source.errors += 1
                        item.source.status = "partial"
                        failures.append({"runtime":item.source.runtime,"error":error,"session_key":item.key[:16]})
                conn.execute("INSERT INTO run_sessions VALUES(?,?,?)", (run_id, item.key, outcome))
                processed += 1
        stats["pending_budget"] = sum(len(q) for q in pending.values())
        coverage = _coverage(catalog)
        counts = dict(conn.execute("SELECT status,count(*) FROM sessions GROUP BY status").fetchall())
        all_summaries = [json.loads(row[0]) for row in conn.execute("SELECT summary_json FROM sessions WHERE adapter=? AND status IN ('selected','filtered') ORDER BY first_processed,session_key", (ADAPTER_VERSION,))]
        # Independent evidence is a session, not a file copy or a second excerpt.
        unique = {}
        for s in all_summaries:
            prior = unique.get(s["session_ref"])
            if prior is None:
                s["source_aliases"] = [s["runtime"]]
                unique[s["session_ref"]] = s
            else:
                aliases = sorted(set(prior["source_aliases"] + [s["runtime"]]))
                if len(canonical(s)) > len(canonical(prior)):
                    s["source_aliases"] = aliases
                    unique[s["session_ref"]] = s
                else:
                    prior["source_aliases"] = aliases
        reviewed = {r[0] for r in conn.execute("SELECT evidence_id FROM reviewed_evidence")}
        candidates = [s for s in unique.values() if s["selected"] and s.get("excerpts") and s["evidence_id"] not in reviewed]
        # B-F2 送审轮转：曾在旧包中且被声明 dismissed（未消费）的证据后移，
        # 未送审过的证据优先——固定前截取不会让 dismissed 永久阻塞新证据。
        sent_ids: set[str] = set()
        for (past_run_id,) in conn.execute("SELECT run_id FROM runs WHERE status IN ('scanned','partial') ORDER BY started_at"):
            packet_path = root / "runs" / past_run_id / "packet.json"
            try:
                past = json.loads(packet_path.read_text())
            except (OSError, json.JSONDecodeError):
                continue  # 损坏/缺失的历史包不阻塞本轮，不计入 sent 集合
            if not isinstance(past, dict):
                continue  # 顶层非映射（如 []）→ 结构诊断并跳过，不让 AttributeError 冒泡
            evidence_list = past.get("evidence", [])
            if isinstance(evidence_list, list):
                sent_ids |= {e["evidence_id"] for e in evidence_list
                             if isinstance(e, dict) and isinstance(e.get("evidence_id"), str)}
        candidates.sort(key=lambda s: (s["evidence_id"] in sent_ids, s["evidence_id"]))
        evidence = candidates[:MAX_EVIDENCE]
        initialized = conn.execute("SELECT value FROM meta WHERE key='initialized_at'").fetchone()[0]
        packet = {"schema_version": PACKET_SCHEMA, "run_id": run_id, "initialized_at": initialized,
                  "started_at": started, "finished_at": now(), "stats": dict(stats), "coverage": coverage, "failures": failures,
                  "cumulative": {"stored_files_or_rows": sum(counts.values()), "by_status": counts,
                                 "unique_sessions": len(unique), "duplicate_views": len(all_summaries) - len(unique)},
                  "triage": [{k: s[k] for k in ("evidence_id", "runtime", "title", "selected", "reason", "completeness")} for s in list(unique.values())[:500]],
                  "evidence": evidence, "pending_analysis": len(candidates), "inventory": inventory,
                  "limitations": ["目录发现不等于全格式支持；unsupported / read_failed 是覆盖缺口",
                                   "初筛与最多 80 条脱敏抽样不是最终价值判断；无原文备份",
                                   "ZCode index_excerpt 无角色边界、可能截断，不是完整对话",
                                   "当前 Agent 的模型通道可能是云端；无需额外 API Key 不等于免费或离线",
                                   "累计数据包含历史会话；来源消失不自动删除历史记录"],
                  "analysis_status": "awaiting_agent" if evidence else "no_pending_evidence"}
        packet["packet_digest"] = digest(packet)
        run_dir = root / "runs" / run_id
        write_json(run_dir / "packet.json", packet)
        report_pages = publish_report(run_dir, "report", packet, None)
        status = "partial" if stats["failed"] or any(s.errors for s in catalog) else "scanned"
        conn.execute("UPDATE runs SET finished_at=?,status=?,packet_digest=?,coverage_json=?,stats_json=? WHERE run_id=?",
                     (now(), status, packet["packet_digest"], json.dumps(coverage), json.dumps(dict(stats)), run_id))
        conn.commit()
        return {"status": status, "run_id": run_id, "stats": dict(stats), "pending_analysis": len(candidates),
                "packet": str(run_dir / "packet.json"), "report": str(run_dir / "report.html"), "report_pages": report_pages,
                "next_action": "当前 Agent 读取 packet 并分析，再 import-analysis" if evidence else ("继续 scan 补齐预算待处理历史" if stats["pending_budget"] else "无待分析证据；保留账本，下次增量扫描")}


def _text(value, field: str, *, max_len=6000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        raise ValueError(f"invalid_{field}")
    return sanitize_structured_text(value)


PROPOSAL_LAYERS = {"patch-existing", "add-reference", "add-template", "add-script", "create"}
EVIDENCE_STRENGTHS = {"cross-session", "single-session-correction", "one-off-context"}
PROFILE_BASES = {"observed_behavior", "user_correction", "agent_inference"}
PROFILE_CONFIDENCES = {"low", "medium", "high"}
PROFILE_KEYS = {"title", "body", "basis", "scope", "evidence_ids", "confidence", "next_review", "correction_quote"}


def _profile_correction_quote(by_id: dict, ids: list[str], quote: str) -> bool:
    """True when the quoted words really appear in a user-role excerpt.

    A "用户明确纠偏" claim must point at the reader's own words. The scan layer
    records user-role excerpts separately from the untyped excerpts, so the
    quote can only be matched against text the user actually wrote: an agent
    statement, a search-index excerpt or a redacted placeholder can never
    support the claim. Matching the exact quote also keeps the judgement
    reviewable — the report shows the same words next to the entry.
    """
    needle = re.sub(r"\s+", "", quote)
    if not needle:
        return False
    # A redaction placeholder is not human language. It cannot substantiate a
    # correction even when the same sanitized token appears in stored evidence.
    residual = PROFILE_PLACEHOLDER.sub(" ", quote)
    residual = re.sub(r"[\W_]+", "", residual, flags=re.UNICODE)
    if not residual:
        return False
    # A later user-role imperative can still be a fresh task. Conservative
    # correction language is required in the quoted words themselves, not merely
    # elsewhere in the same session, before exact-turn matching is attempted.
    if not CORRECTION_LANGUAGE.search(quote):
        return False
    for evidence_id in ids:
        evidence = by_id[evidence_id]
        if evidence.get("completeness") == "index_excerpt":
            continue
        user_excerpts = evidence.get("user_excerpts")
        if not isinstance(user_excerpts, list):
            continue
        for excerpt in user_excerpts:
            if isinstance(excerpt, str) and needle in re.sub(r"\s+", "", excerpt):
                return True
    return False


def _validate_profile(packet: dict, analysis: dict, refs: set[str]) -> list[dict]:
    """Validate optional, evidence-bound profile observations."""
    if "profile" not in analysis:
        return []
    items = analysis.get("profile")
    if not isinstance(items, list) or len(items) > 12:
        raise ValueError("invalid_profile")
    by_id = {e["evidence_id"]: e for e in packet["evidence"]}
    seen_titles: set[str] = set()
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict) or set(item) != PROFILE_KEYS:
            raise ValueError("invalid_profile_item")
        basis = item.get("basis")
        confidence = item.get("confidence")
        if not isinstance(basis, str) or basis not in PROFILE_BASES:
            raise ValueError("invalid_profile_basis")
        if not isinstance(confidence, str) or confidence not in PROFILE_CONFIDENCES:
            raise ValueError("invalid_profile_confidence")
        ids = item.get("evidence_ids")
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 12
                or any(not isinstance(e, str) or e not in refs for e in ids)):
            raise ValueError("unknown_or_missing_profile_evidence")
        ids = list(dict.fromkeys(ids))
        sessions = {
            by_id[e].get("session_ref", "").strip()
            for e in ids
            if isinstance(by_id[e].get("session_ref"), str)
            and by_id[e]["session_ref"].strip()
        }
        if confidence == "high" and (basis == "agent_inference" or len(sessions) < 3):
            raise ValueError("high_profile_requires_three_sessions_and_not_inference")
        quote = item.get("correction_quote")
        if not isinstance(quote, str):
            raise ValueError("invalid_profile_correction_quote")
        if basis == "user_correction":
            if not quote.strip():
                raise ValueError("user_correction_requires_user_turn_evidence")
            if not _profile_correction_quote(by_id, ids, quote):
                raise ValueError("user_correction_quote_not_in_user_turn")
        elif quote.strip():
            raise ValueError("profile_correction_quote_only_for_user_correction")
        title = _text(item.get("title"), "profile_title", max_len=200)
        if title in seen_titles:
            raise ValueError("duplicate_profile_title")
        seen_titles.add(title)
        out.append({
            "title": title,
            "body": _text(item.get("body"), "profile_body", max_len=3000),
            "basis": basis,
            "scope": _text(item.get("scope"), "profile_scope", max_len=1000),
            "evidence_ids": ids,
            "confidence": confidence,
            "next_review": _text(item.get("next_review"), "profile_next_review", max_len=1000),
            "correction_quote": sanitize_structured_text(quote)[:1000],
        })
    return out



def validate_analysis(packet: dict, analysis: dict) -> dict:
    if not isinstance(analysis, dict) or analysis.get("schema_version") != ANALYSIS_SCHEMA or analysis.get("packet_digest") != packet["packet_digest"]:
        raise ValueError("analysis_packet_mismatch")
    result = {"schema_version": ANALYSIS_SCHEMA, "packet_digest": packet["packet_digest"], "overview": _text(analysis.get("overview"), "overview")}
    refs = {e["evidence_id"] for e in packet["evidence"]}
    inventory = {s["id"] for s in packet["inventory"]}
    for field in ("patterns", "skill_proposals"):
        items = analysis.get(field)
        if not isinstance(items, list) or len(items) > 40:
            raise ValueError("invalid_analysis_list")
        out = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("invalid_analysis_item")
            ids = item.get("evidence_ids")
            if not isinstance(ids, list) or not ids or any(not isinstance(e, str) or e not in refs for e in ids):
                raise ValueError("unknown_or_missing_evidence")
            row = {"title": _text(item.get("title"), "title", max_len=200), "evidence_ids": list(dict.fromkeys(ids))}
            if field == "patterns":
                row.update(explanation=_text(item.get("explanation"), "explanation"), next_step=_text(item.get("next_step"), "next_step"))
            else:
                action, target = item.get("action"), item.get("target_skill")
                if not isinstance(action, str) or action not in {"upgrade", "reference", "create"} or not isinstance(target, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", target):
                    raise ValueError("invalid_skill_target")
                if action != "create" and target not in inventory:
                    raise ValueError("skill_not_in_inventory")
                if action == "create" and target in inventory:
                    raise ValueError("create_duplicates_installed_skill")
                points = item.get("change_points")
                if not isinstance(points, list) or not 1 <= len(points) <= 20:
                    raise ValueError("invalid_change_points")
                row.update(action=action, target_skill=target, rationale=_text(item.get("rationale"), "rationale"),
                           change_points=[_text(p, "change_point", max_len=1000) for p in points])
                # Hermes-informed proposal metadata (SE-261022-HERMES-LOOP):
                # both fields stay optional for v1 analyses. When supplied, they
                # are machine-readable and constrained to stable enums so later
                # reports cannot accidentally invent a new taxonomy.
                proposal_layer = item.get("proposal_layer")
                if "proposal_layer" in item and (not isinstance(proposal_layer, str) or proposal_layer not in PROPOSAL_LAYERS):
                    raise ValueError("invalid_proposal_layer")
                evidence_strength = item.get("evidence_strength")
                if "evidence_strength" in item and (not isinstance(evidence_strength, str) or evidence_strength not in EVIDENCE_STRENGTHS):
                    raise ValueError("invalid_evidence_strength")
                if proposal_layer is not None and ((action == "create") != (proposal_layer == "create")):
                    raise ValueError("proposal_action_layer_mismatch")
                if evidence_strength == "cross-session":
                    sessions = {e.get("session_ref", "").strip() for e in packet["evidence"]
                                if e["evidence_id"] in ids and isinstance(e.get("session_ref"), str)
                                and e["session_ref"].strip()}
                    if len(sessions) < 2:
                        raise ValueError("cross_session_requires_independent_sessions")
                if proposal_layer is not None:
                    row["proposal_layer"] = proposal_layer
                if evidence_strength is not None:
                    row["evidence_strength"] = evidence_strength
                # B-F4 候选产物绑定（可选）：外置候选文件的路径+sha256+生成来源，
                # 结构校验 fail-closed；渲染层如实展示，绝不生成下载链接。
                cand = item.get("candidate_file")
                if cand is not None:
                    if (not isinstance(cand, dict)
                        or not isinstance(cand.get("path"), str) or not cand["path"].strip()
                        or len(cand["path"]) > 500
                        or not isinstance(cand.get("sha256"), str)
                        or not re.fullmatch(r"[0-9a-f]{64}", cand["sha256"])
                        or (cand.get("source") is not None and not isinstance(cand.get("source"), str))):
                        raise ValueError("invalid_candidate_file")
                    # B-F4（R2）：产物真实性核验在导入时（服务端）做——原始路径
                    # 先核验文件存在+哈希一致，核验结论入库；报告只见结论与哈希，
                    # 不见原始本机路径（脱敏合同），虚构路径/哈希核验为 False。
                    cand_path = Path(cand["path"]).expanduser()
                    try:
                        cand_verified = (cand_path.is_file() and not cand_path.is_symlink()
                                         and hashlib.sha256(cand_path.read_bytes()).hexdigest() == cand["sha256"])
                    except OSError:
                        cand_verified = False
                    row["candidate_file"] = {"sha256": cand["sha256"], "verified": cand_verified,
                                             **({"source": sanitize_structured_text(cand["source"])[:200]} if cand.get("source") else {})}
            out.append(row)
        result[field] = out
    if "profile" in analysis:
        result["profile"] = _validate_profile(packet, analysis, refs)
    # 逐证据处置合同（UP-03）：分析可显式声明每条证据的处置；缺省=未处理。
    # analyzed/insufficient_material 视为已处理（导入后不再送审）；dismissed
    # 仅登记 Agent 判断、证据跨轮保留待人工复核；未声明处置的证据同样保留——
    # 空/部分分析绝不静默消耗整包。
    dispositions = analysis.get("evidence_dispositions")
    if dispositions is not None:
        if not isinstance(dispositions, list) or any(
            not isinstance(d, dict)
            or not isinstance(d.get("evidence_id"), str) or d["evidence_id"] not in refs
            or d.get("disposition") not in {"analyzed", "dismissed", "insufficient_material"}
            or (d.get("note") is not None and not isinstance(d.get("note"), str))
            for d in dispositions
        ):
            raise ValueError("invalid_evidence_dispositions")
        seen_ids = [d["evidence_id"] for d in dispositions]
        if len(seen_ids) != len(set(seen_ids)):
            raise ValueError("invalid_evidence_dispositions")
        result["evidence_dispositions"] = [
            {"evidence_id": d["evidence_id"], "disposition": d["disposition"],
             **({"note": sanitize_structured_text(d["note"])[:500]} if d.get("note") else {})}
            for d in dispositions
        ]
    return result


def import_analysis(root: Path, packet_path: Path, analysis_path: Path) -> dict:
    if packet_path.stat().st_size > 4 * 1024 * 1024 or analysis_path.stat().st_size > MAX_ANALYSIS_BYTES:
        raise ValueError("input_size_budget_exceeded")
    packet = json.loads(packet_path.read_text())
    if not isinstance(packet, dict) or packet.get("schema_version") != PACKET_SCHEMA:
        raise ValueError("invalid_packet_schema")
    actual = dict(packet)
    expected = actual.pop("packet_digest", None)
    if expected != digest(actual):
        raise ValueError("packet_digest_invalid")
    if not re.fullmatch(r"[0-9]{8}T[0-9]{6}-[0-9a-f]{12}", str(packet.get("run_id", ""))):
        raise ValueError("invalid_run_id")
    analysis = validate_analysis(packet, json.loads(analysis_path.read_text()))
    with locked(root), database(root) as conn:
        row = conn.execute("SELECT packet_digest FROM runs WHERE run_id=?", (packet["run_id"],)).fetchone()
        if not row or row[0] != expected:
            raise ValueError("packet_not_bound_to_local_run")
        # An already-superseded packet cannot silently bless evidence changed by a later scan.
        current = {}
        for row in conn.execute(
                "SELECT summary_json FROM sessions WHERE adapter=? AND status='selected'",
                (ADAPTER_VERSION,)):
            summary = json.loads(row[0])
            current[summary.get("evidence_id")] = summary
        # Compare the provenance-bearing fields as well as the id. The id is
        # derived from conversation text, so a stale packet with the same id
        # could otherwise reintroduce pre-fix user_excerpts.
        if any(e["evidence_id"] not in current
               or canonical(e.get("user_excerpts")) != canonical(
                   current[e["evidence_id"]].get("user_excerpts"))
               for e in packet["evidence"]):
            raise ValueError("packet_evidence_superseded; 重新扫描取得当前证据包")
        # B-F1：处置冲突检查必须在发布报告/写 JSON 之前——拒绝导入不得留下
        # 任何新增产物（七页 HTML/分析 JSON）。
        packet_ids = {e["evidence_id"] for e in packet["evidence"]}
        already_reviewed = set()
        if packet_ids:
            placeholders = ",".join("?" * len(packet_ids))
            already_reviewed = {r[0] for r in conn.execute(
                f"SELECT evidence_id FROM reviewed_evidence WHERE evidence_id IN ({placeholders})",
                tuple(packet_ids))}
        dispositions = {d["evidence_id"]: d["disposition"] for d in analysis.get("evidence_dispositions", [])}
        consumed = [e["evidence_id"] for e in packet["evidence"]
                    if dispositions.get(e["evidence_id"]) in {"analyzed", "insufficient_material"}]
        if already_reviewed - set(consumed):
            # 账本已消费但本次修订未声明消费/声明 dismissed → 冲突修订拒绝；
            # 不发布、不写盘、账本与历史文件字节不动。
            raise ValueError("disposition_conflicts_reviewed")
        import public_report
        renderer_hash = hashlib.sha256(Path(public_report.__file__).read_bytes()).hexdigest()
        analysis_hash = digest([analysis, renderer_hash])
        prior = conn.execute("SELECT analysis_id FROM analyses WHERE run_id=? AND analysis_hash=?", (packet["run_id"], analysis_hash)).fetchone()
        analysis_id = prior[0] if prior else "analysis-" + uuid.uuid4().hex
        run_dir = root / "runs" / packet["run_id"]
        report_path = run_dir / (analysis_id + ".html")
        report_pages = publish_report(run_dir, analysis_id, packet, analysis, require_existing=bool(prior))
        if not prior:
            write_json(run_dir / (analysis_id + ".json"), analysis)
        if not prior:
            conn.execute("INSERT INTO analyses VALUES(?,?,?,?,?,?)", (analysis_id, packet["run_id"], expected, now(), analysis_hash, json.dumps(analysis, ensure_ascii=False)))
        # 逐证据处置合同（UP-03/B-F1）：冲突检查已在发布前完成（追加式账本
        # 状态——已消费证据不可被修订撤销/改判）；此处仅追加消费记录。
        for evidence_id in consumed:
            conn.execute("INSERT OR REPLACE INTO reviewed_evidence VALUES(?,?)", (evidence_id, analysis_id))
        conn.commit()
        # B-F1：consumed/retained 以账本现状（含历史消费）为准，不按单次声明。
        final_reviewed = already_reviewed | set(consumed)
        return {"status": "analysis_imported", "analysis_id": analysis_id, "report": str(report_path), "report_pages": report_pages,
                "evidence_consumed": len(final_reviewed & packet_ids), "evidence_retained": len(packet_ids - final_reviewed),
                "remaining_action": "建议待人审阅；未接受、应用或安装 Skill"}


def status(root: Path) -> dict:
    if not (root / "ledger.sqlite").exists():
        return {"status": "not_initialized", "next_action": "运行 scan 自动初始化"}
    with locked(root), database(root) as conn:
        return {"status": "initialized", "meta": dict(conn.execute("SELECT key,value FROM meta")),
                "sessions": dict(conn.execute("SELECT status,count(*) FROM sessions GROUP BY status")),
                "recent_runs": [dict(r) for r in conn.execute("SELECT run_id,started_at,finished_at,status FROM runs ORDER BY started_at DESC,run_id DESC LIMIT 10")],
                "analysis_count": conn.execute("SELECT count(*) FROM analyses").fetchone()[0]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("scan")
    p.add_argument("--home", type=Path, default=Path.home())
    p.add_argument("--max-sessions", type=int, default=200)
    p.add_argument("--source", action="append", default=[])
    p = sub.add_parser("import-analysis")
    p.add_argument("--packet", type=Path, required=True)
    p.add_argument("--analysis", type=Path, required=True)
    sub.add_parser("status")
    for command in ("register-proposals", "adoption-status", "render-adoptions"):
        p = sub.add_parser(command)
        p.add_argument("--analysis-id", required=command != "adoption-status")
    p = sub.add_parser("record-adoption")
    p.add_argument("--proposal-id", required=True)
    p.add_argument("--revision", required=True)
    p.add_argument("--event", type=Path, required=True)
    args = parser.parse_args()
    try:
        assert_runtime_ready()
        root = assert_external_write_path(DATA_ROOT / "runtime/public-workflow", label="public_workflow")
        if args.command == "scan":
            result = scan(root, args.home.expanduser().resolve(), args.source, args.max_sessions)
        elif args.command == "import-analysis":
            result = import_analysis(root, args.packet, args.analysis)
        elif args.command == "status":
            result = status(root)
        else:
            import public_adoption as adoption
            if args.command == "register-proposals":
                result = adoption.register_proposals(root, args.analysis_id)
            elif args.command == "record-adoption":
                if args.event.stat().st_size > MAX_ANALYSIS_BYTES:
                    raise ValueError("input_size_budget_exceeded")
                result = adoption.record_adoption(root, args.proposal_id, args.revision,
                                                  json.loads(args.event.read_text()))
            elif args.command == "render-adoptions":
                result = adoption.render_adoptions(root, args.analysis_id)
            else:
                result = adoption.adoption_status(root, args.analysis_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("status") == "partial" else 0
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
        # No raw transcript, credentials or private exception detail in diagnostics.
        error = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print(json.dumps({"status": "failed", "error": error}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
