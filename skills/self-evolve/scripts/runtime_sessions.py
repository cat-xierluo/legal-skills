#!/usr/bin/env python3
"""Read-only, versioned local session adapters; no network or credential access."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from contextlib import closing
from pathlib import Path
from typing import Any

from dream_sweep import read_jsonl_with_stats

ADAPTER_VERSION = "14"
MAX_JSON_BYTES = 32 * 1024 * 1024


@dataclass
class Source:
    runtime: str
    format: str
    root: Path
    status: str = "not_found"
    discovered: int = 0
    errors: int = 0


@dataclass
class Session:
    source: Source
    path: Path
    revision: str
    row_id: tuple[str, str] | None = None

    @property
    def key(self) -> str:
        locator = str(self.path.resolve()) + (json.dumps(self.row_id) if self.row_id else "")
        return hashlib.sha256((self.source.runtime + ":" + locator).encode()).hexdigest()


def stamp(path: Path) -> str:
    s = path.stat()
    return f"{s.st_size}:{s.st_mtime_ns}:{s.st_ctime_ns}"


def sources(home: Path, custom: list[str]) -> list[Source]:
    codex = Path(os.environ.get("CODEX_HOME", str(home / ".codex"))) if home == Path.home() else home / ".codex"
    zbase = Path(os.environ.get("ZCODE_DATA_BASE_DIR", str(home))) if home == Path.home() else home
    specs = [
        ("claude", "claude", home / ".claude/projects"),
        ("claude", "claude", home / ".claude/transcripts"),
        *[("codex", "codex", codex / n) for n in ("sessions", "archived_sessions", "_quarantine")],
        *[(runtime, fmt, home / f".{runtime}/{leaf}") for runtime in ("workbuddy", "codebuddy")
          for fmt, leaf in (("claude", "projects"), ("trace", "traces"))],
        # QwenWorkCN stores Claude-dialect sessions (sessionId/parentUuid/message/cwd).
        ("qwenworkcn", "claude", home / ".qwenworkcn/projects"),
        ("zcode", "zcode-index", zbase / ".zcode/v2/tasks-index.sqlite"),
        ("gemini", "gemini", home / ".gemini/tmp"),
        *[(runtime, "unsupported", home / f".{runtime}") for runtime in
          ("qwen", "qoder", "qoderworkcn", "openclaw", "hermes", "opencode", "cursor", "trae")],
    ]
    # A custom runtime home supplements, rather than hides, the standard store.
    if codex != home / ".codex":
        specs.extend(("codex","codex",home / ".codex" / n) for n in ("sessions","archived_sessions","_quarantine"))
    if zbase != home:
        specs.append(("zcode","zcode-index",home / ".zcode/v2/tasks-index.sqlite"))
    result = [Source(*s) for s in specs]
    for raw in custom:
        label, sep, path = raw.partition("=")
        runtime, colon, fmt = label.partition(":")
        if not sep or not colon or not runtime.replace("-", "").isalnum() or fmt not in {"claude", "codex", "trace", "gemini"} or not path:
            raise ValueError("source 必须是 runtime:claude|codex|trace|gemini=目录")
        result.append(Source(runtime, fmt, Path(path).expanduser()))
    return result


def _walk(root: Path, fmt: str, source: Source):
    def onerror(_exc):
        source.errors += 1
    for base, dirs, files in os.walk(root, onerror=onerror, followlinks=False):
        depth = len(Path(base).relative_to(root).parts)
        dirs[:] = [d for d in dirs if d not in {"node_modules", ".git", "cache", "blobs", "snapshots"} and not (Path(base) / d).is_symlink()]
        if depth >= 12:
            if dirs:
                source.errors += 1  # depth cap is a coverage gap, never silent full coverage
            dirs[:] = []
        for name in files:
            if ((fmt in {"claude", "codex"} and name.endswith(".jsonl")) or
                (fmt == "trace" and name.startswith("trace_") and name.endswith(".json")) or
                (fmt == "gemini" and Path(base).name == "chats" and name.startswith("session-") and name.endswith(".json"))):
                yield Path(base) / name


def _snapshot_source_rows(path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    """Query a foreign source DB through a temp-copy consistent snapshot.

    合同（A-SQL-SRC-01 终版，R3）：immutable 直连会静默漏掉仅存在于 WAL 的
    已提交数据、且对活动生产库跳过锁与变化检测——改为把主库+伴生整体拷贝到
    临时目录、**在副本上执行实际查询**（副本生命周期覆盖查询本身，不再只是
    预检）；查询后复核源文件指纹，变化即报 source_changed_during_read（记账
    failed，下轮可重试）。孤立伴生（主库缺失而 WAL/SHM 在）显式失败，不冒充
    "未发现"。
    """
    wal = path.with_name(path.name + "-wal")
    shm = path.with_name(path.name + "-shm")
    if not path.exists():
        if wal.exists() or shm.exists():
            raise ValueError("source_db_crash_shape")
        raise ValueError("source_db_missing")
    zero_main = path.stat().st_size == 0
    sidecars = wal.exists() or shm.exists()
    if zero_main and sidecars:
        raise ValueError("source_db_crash_shape")

    def stamps() -> list[tuple]:
        return [(f.name, f.stat().st_size if f.exists() else None,
                 f.stat().st_mtime_ns if f.exists() else None) for f in (path, wal, shm)]

    before = stamps()
    with tempfile.TemporaryDirectory(prefix="self-evolve-src-snap-") as td:
        tmp = Path(td) / path.name
        shutil.copy2(path, tmp)
        for sidecar in (wal, shm):
            if sidecar.exists():
                shutil.copy2(sidecar, Path(td) / sidecar.name)
        with closing(sqlite3.connect(tmp.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)) as conn:
            rows = conn.execute(sql, params).fetchall()
    if stamps() != before:
        raise ValueError("source_changed_during_read")
    return rows


def discover(catalog: list[Source]) -> list[Session]:
    result: list[Session] = []
    seen: set[str] = set()
    for source in catalog:
        if not source.root.exists():
            if source.format == "zcode-index" and (
                source.root.with_name(source.root.name + "-wal").exists()
                or source.root.with_name(source.root.name + "-shm").exists()
            ):
                # 孤立伴生（主库缺失）：显式失败，不冒充"未发现"（R3 ORPHAN）。
                source.status = "read_failed"
                source.errors += 1
            continue
        if source.format == "unsupported":
            source.status = "unsupported"
            continue
        source.status = "available"
        try:
            if source.format == "zcode-index":
                rows = _snapshot_source_rows(
                    source.root,
                    "SELECT workspace_key, task_id, updated_at, length(searchable_text) FROM tasks WHERE deleted=0 ORDER BY updated_at, task_id")
                for workspace, task, updated, size in rows:
                    result.append(Session(source, source.root, f"{updated}:{size}", (workspace, task)))
                    source.discovered += 1
            else:
                for path in _walk(source.root, source.format, source):
                    real = str(path.resolve())
                    if real in seen:
                        continue
                    seen.add(real)
                    try:
                        result.append(Session(source, path, stamp(path)))
                        source.discovered += 1
                    except OSError:
                        source.errors += 1
        except (OSError, sqlite3.Error, ValueError):
            source.errors += 1
            source.status = "read_failed"
        if source.errors:
            source.status = "read_failed" if not source.discovered else "partial"
    return result


def flatten(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(flatten(v) for v in value)
    if isinstance(value, dict):
        return flatten(value.get("text", value.get("content", "")))
    return ""


def _json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def message(role: str, text: str, sid: str, ts: Any = None) -> dict:
    return {"type": role, "sessionId": sid, "timestamp": ts,
            "message": {"role": role, "content": text}}


def _sample(items: list, cap: int) -> list:
    if len(items) <= cap:
        return items
    # Evenly retain head, middle and tail, rather than only early context.
    return [items[round(i * (len(items) - 1) / (cap - 1))] for i in range(cap)]


def _load_jsonl_stats(path: Path, max_records: int) -> tuple[list[dict], Any]:
    """Read a JSONL transcript, letting open/decode failures propagate.

    合同（A-F3）：读取失败（权限、IO）必须作为异常上抛、由扫描按 failed
    记账——底层读取器吞掉 OSError 返回空统计的历史行为不得把读不到的文件
    解释成"空会话成功"。
    """
    try:
        path.open("rb").close()
    except OSError:
        raise
    return read_jsonl_with_stats(path, max_lines=max_records)


_TOOL_BLOCK_TYPES = {"tool_result", "tool_use", "function_call", "function_call_output"}
_TEXT_BLOCK_TYPES = {"text", "input_text", "output_text"}
# Reasoning-only blocks (Claude/WorkBuddy/CodeBuddy/QwenWorkCN all emit them)
# are dropped by the extractor by design, so they are a known shape.
_REASONING_BLOCK_TYPES = {"thinking", "redacted_thinking"}


def _content_extractable(content: Any) -> bool:
    """True exactly when the shape mirrors what extract_message_text consumes.

    合同（A-F3-R1/R4，第三轮）：白名单必须与提取器逐分支对齐——
    str 直取；dict 走 tool 块/text 键/递归 content 三支；list 逐项走
    str、text 系块、无 type 但有 str content/text 键的项；其余（数字、
    布尔、None、未知 type 块、未知结构）= 未知载荷，必须显式暴露。
    注意：list 里的 dict 块若 type 不在已知集合，提取器会静默丢弃——
    该内容"看不见"仍算漏放，所以未知 type 块判 False（媒体块等由
    上游确认消费语义后再加入白名单）。
    """
    if isinstance(content, str):
        return True
    if isinstance(content, dict):
        block_type = str(content.get("type") or "")
        if block_type in _TOOL_BLOCK_TYPES:
            return True
        if block_type in _REASONING_BLOCK_TYPES:
            return True
        if isinstance(content.get("text"), str):
            return True
        if "content" in content:
            return _content_extractable(content["content"])
        return False
    if isinstance(content, list):
        for item in content:
            if isinstance(item, str):
                continue
            if isinstance(item, dict):
                item_type = str(item.get("type") or "")
                if item_type in _TOOL_BLOCK_TYPES:
                    continue
                if item_type in _REASONING_BLOCK_TYPES:
                    continue
                if item_type in _TEXT_BLOCK_TYPES and isinstance(item.get("text"), str):
                    continue
                if not item_type and isinstance(item.get("content"), str):
                    continue
                if not item_type and isinstance(item.get("text"), str):
                    continue
                return False
            return False  # numbers/bools/None inside a list are unknown payloads
        return True
    return False


def _assert_known_payloads(fmt: str, records: list[dict]) -> None:
    """Expose message rows whose content shape the extractors cannot understand."""
    if fmt == "claude":
        for r in records:
            if r.get("type") == "tool_use":
                continue  # known conversation-less tool transcript
            # Tool-call and metadata rows (WorkBuddy/CodeBuddy) may carry a
            # `message` object holding usage metadata only; that is not a
            # conversation row and must not be judged as an unknown payload.
            if r.get("type") in {"function_call", "function_call_result", "reasoning",
                                 "session-meta", "ai-title", "file-history-snapshot"}:
                continue
            msg = r.get("message")
            is_message_row = (
                r.get("type") in {"user", "assistant"}
                or r.get("role") in {"user", "assistant"}
                or (isinstance(msg, dict) and msg.get("role") in {"user", "assistant"})
            )
            if (r.get("type") == "message" and r.get("role") in {"user", "assistant"}
                    and isinstance(msg, dict) and "usage" in msg
                    and not any(key in msg for key in ("role", "content", "text"))):
                # WorkBuddy/CodeBuddy use type=message plus a top-level role and
                # content. Tool rows reuse the same shape but carry a `message`
                # object with usage metadata instead of conversation content.
                # Exempt only known usage-only metadata, not the entire envelope.
                # Actual top-level content must retain the unknown-payload guard.
                is_message_row = False
            if not is_message_row:
                continue  # metadata rows (summary etc.) are legitimately textless
            # A-F3-R4：提取器 message 优先（message is not None 时完全忽略
            # 顶层 content）；字符串 message 与 dict message（text 键/content
            # 递归）都是可提取的合法形态（A-F3-R5）。
            if msg is not None:
                if isinstance(msg, str):
                    continue  # extract_message_text(str) yields the text
                if not isinstance(msg, dict):
                    raise ValueError("unsupported_message_payload")
                # dict message 走提取器同一套判定；没有 role 约束（human_text
                # 只看 message.role in {None,"",user}），content 可提取即合法。
                if not _content_extractable(msg.get("content")) and not isinstance(msg.get("text"), str):
                    raise ValueError("unsupported_message_payload")
            else:
                content = r.get("content")
                if not _content_extractable(content):
                    raise ValueError("unsupported_message_payload")
    elif fmt == "codex":
        for r in records:
            payload = r.get("payload")
            if r.get("type") != "response_item" or not isinstance(payload, dict):
                continue
            if payload.get("type") != "message":
                continue  # function_call/function_call_output shapes handled by extractor
            if not _content_extractable(payload.get("content")):
                raise ValueError("unsupported_message_payload")


def load(item: Session, max_records: int = 600) -> tuple[list[dict], str, str, str]:
    """Return records, dream_sweep dialect, content hash, completeness label."""
    fmt, path = item.source.format, item.path
    if fmt in {"claude", "codex"}:
        records, stats = _load_jsonl_stats(path, max_records)
        if not records and not stats.invalid_lines and not stats.total_lines:
            # A structurally valid but zero-line file is an empty session, not a read error.
            raise ValueError("empty_session")
        if stats.invalid_lines or not records:
            raise ValueError("invalid_or_empty_jsonl")
        # Claude records are the current envelope (type/message), the legacy top-level
        # transcript dialects (role/content or type/content), or known tool-only
        # transcripts (tool_use lines with no conversation); all feed the same
        # extractors, and conversation-less files degrade to filtered, not failed.
        recognized = any((r.get("type") in {"user", "assistant", "tool_use"} or isinstance(r.get("message"), dict) or r.get("role") in {"user", "assistant"}) if fmt == "claude" else r.get("type") in {"session_meta", "event_msg", "response_item", "turn_context"} for r in records)
        if not recognized:
            raise ValueError("unsupported_jsonl_schema")
        _assert_known_payloads(fmt, records)
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        label = "sampled_transcript" if stats.total_lines > stats.selected_lines else "transcript"
        return records, "claude-code" if fmt == "claude" else "codex", digest.hexdigest(), label
    if fmt == "zcode-index":
        rows = _snapshot_source_rows(
            path,
            "SELECT title, searchable_text, updated_at FROM tasks WHERE workspace_key=? AND task_id=? AND deleted=0",
            item.row_id)
        if not rows:
            # 发现后任务被软删/移除（快照查询空结果）：具名来源变化，不中断整轮。
            raise ValueError("source_changed_during_read")
        row = rows[0]
        if row is None or f"{row[2]}:{len(row[1] or '')}" != item.revision:
            raise ValueError("source_changed_during_read")
        title, text, _updated = row
        if not text or not text.strip():
            raise ValueError("index_text_unavailable")
        digest = hashlib.sha256(text.encode()).hexdigest()
        if len(text) > 24000:
            text = text[:8000] + "\n[索引中段抽样]\n" + text[len(text)//2-4000:len(text)//2+4000] + "\n" + text[-8000:]
        # Search indexes have no reliable roles or transcript completeness.
        return [message("user", text, item.row_id[1])], "claude-code", digest, "index_excerpt"
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("json_exceeds_32mb_budget")
    raw = path.read_bytes()
    data = json.loads(raw)
    records = []
    if fmt == "trace":
        if not isinstance(data, dict) or not isinstance(data.get("spans"), list):
            raise ValueError("unsupported_trace_schema")
        sid = str((data.get("trace") or {}).get("sessionId") or path.parent.name)
        previous_users: list[str] = []
        import re
        for span in sorted((s for s in data["spans"] if isinstance(s, dict)), key=lambda s: str(s.get("startedAt", ""))):
            if span.get("name") != "generation":
                continue
            ti = _json(span.get("toolInput"))
            if isinstance(ti, dict):
                ti = ti.get("messages", [])
            users = []
            if isinstance(ti, list):
                for m in ti:
                    if isinstance(m, dict) and m.get("role") == "user":
                        text = flatten(m.get("content"))
                        queries = re.findall(r"<user_query>(.*?)</user_query>", text, re.S)
                        users.extend(q.strip() for q in queries if q.strip()) if queries else users.append(text)
            elif isinstance(span.get("toolInput"), str):
                # Truncated JSON: only tagged user payloads, no system-template matches.
                raw_input = span["toolInput"].replace("the <user_query> tag", "the user-query tag")
                users = re.findall(r"<user_query>(.*?)</user_query>", raw_input, re.S)
            common = 0
            while common < min(len(users), len(previous_users)) and users[common] == previous_users[common]:
                common += 1
            for text in users[common:]:
                if text.strip():
                    records.append(message("user", text, sid, span.get("startedAt")))
            previous_users = users or previous_users
            output = _json(span.get("toolOutput"))
            if isinstance(output, list):
                output = output[0] if output else {}
            if isinstance(output, dict):
                choices = output.get("choices") or []
                if choices and isinstance(choices[0], dict):
                    text = flatten((choices[0].get("message") or {}).get("content"))
                    if text.strip():
                        records.append(message("assistant", text, sid, span.get("startedAt")))
    elif fmt == "gemini":
        if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
            raise ValueError("unsupported_gemini_schema")
        sid = str(data.get("sessionId") or path.stem)
        for m in data["messages"]:
            if not isinstance(m, dict) or m.get("type") not in {"user", "gemini"}:
                continue
            text = flatten(m.get("content"))
            if text.strip():
                records.append(message("user" if m["type"] == "user" else "assistant", text, sid, m.get("timestamp")))
    else:
        raise ValueError("unsupported_format")
    if not records:
        # Valid schema without conversation content is an empty session for chat stores;
        # trace files without generation spans keep the stricter no-conversation label.
        raise ValueError("empty_session" if fmt == "gemini" else "no_conversation_messages")
    label = "sampled_transcript" if len(records) > max_records else "transcript"
    return _sample(records, max_records), "claude-code", hashlib.sha256(raw).hexdigest(), label
