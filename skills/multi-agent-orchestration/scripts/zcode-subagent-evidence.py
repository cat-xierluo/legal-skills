#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""zcode-subagent-evidence — 只读采集原生 Agent 子任务树(session.parent_id)证据。

安全与语义契约（详见 references/zcode-subagent-evidence.md）：
- 只读：URI mode=ro + PRAGMA query_only + 单一读事务快照；绝不创建、写入或修改数据库。
- 显式绑定：--root-session 与 --root-input 必须命中同一行 session_input
  （promoted_message_id 绑定；promoted_sequence 为精确 turn，缺省回退 admitted_sequence）。
- 只沿 session.parent_id 枚举真实后代；祖先/环/深度/节点数均有界。
- 仅输出白名单字段（身份/状态/模型/provider/mode/运行时间/工具数量）；
  禁止输出 payload、reasoning、工具参数/结果、标题、目录、账号、凭据。
- 禁止按标题或时间邻近猜子任务；无法证明归属该 root input 的后代一律保留歧义或标 UNKNOWN。
- 错误只输出固定错误码，不回显任何原生异常文本。

退出码：0 成功；2 用法错误；3 数据库/schema 错误；4 root 绑定失败；5 内部错误。
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from collections import deque
from pathlib import Path

TOOL = "zcode-subagent-evidence"
SCHEMA_VERSION = 1

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_DB = 3
EXIT_ROOT = 4
EXIT_INTERNAL = 5

# 白名单 token：仅允许紧凑标识符形态，天然排除含空格/斜杠/路径/自然语言的内容
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
# 终态集合（turn_usage.status 的原生取值）
TERMINAL_STATUSES = frozenset({"completed", "error", "cancelled", "failed", "stopped"})
# 单字段列表输出上限（防大输出）
LIST_CAP = 8

REQUIRED_TABLE_COLUMNS = {
    "session": ("id", "parent_id"),
    "session_input": ("session_id", "promoted_message_id"),
}
OPTIONAL_TABLES = ("tool_usage", "turn_usage", "model_usage")


def emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def fail(exit_code, code):
    emit({"ok": False, "error": {"code": code, "exit": exit_code}})
    return exit_code


def safe_token(value, key=None):
    """把列值收敛为白名单 token；None 表示 UNKNOWN。绝不回显原值。"""
    if isinstance(value, str):
        s = value.strip()
        if s and s[0] in "{[":
            # 允许 JSON 编码字段（如 {"model_id": ...}）；坏 JSON 一律 UNKNOWN
            try:
                parsed = json.loads(s)
            except Exception:
                return None
            if isinstance(parsed, dict):
                inner = parsed.get(key) if key else None
                if isinstance(inner, str):
                    s = inner.strip()
                else:
                    return None
            else:
                return None
        return s if TOKEN_RE.match(s) else None
    return None


def safe_int(value, lo=0, hi=10 ** 15):
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if lo <= value <= hi:
        return value
    return None


def table_columns(conn, table):
    quoted = '"%s"' % table.replace('"', '""')
    rows = conn.execute("PRAGMA table_info(%s)" % quoted).fetchall()
    return [r[1] for r in rows]


def table_exists(conn, table):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def open_readonly(db_path):
    if not os.path.isfile(db_path):
        return None, "db_file_missing"
    # as_uri() 做规范百分号编码（含 % 与空格），避免 SQLite URI 解码语义干扰路径
    uri = Path(db_path).as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5.0, isolation_level=None)
        conn.execute("PRAGMA query_only=ON")
        return conn, None
    except sqlite3.Error:
        return None, "db_open_failed"


def signature_code(exc):
    # 仅在内部做特征分类，绝不把 str(exc) 输出
    text = str(exc).lower()
    if "not a database" in text or "malformed" in text or "encrypted" in text:
        return "db_not_sqlite"
    return "db_query_failed"


def gather_node(conn, sid, cols, sources):
    node = {
        "session_id": sid,
        "parent_id": None,
        "depth": 0,
        "parent_exists": "UNKNOWN",
        "status": "UNKNOWN",
        "terminal": "UNKNOWN",
        "permission_mode": "UNKNOWN",
        "models": "UNKNOWN",
        "providers": "UNKNOWN",
        "modes": "UNKNOWN",
        "turn_count": "UNKNOWN",
        "tool_call_count": "UNKNOWN",
        "duration_ms": "UNKNOWN",
        "duration_source": "UNKNOWN",
        "root_input_attribution": "UNKNOWN",
    }
    select_cols = [c for c in ("parent_id", "permission", "time_created", "time_updated")
                   if c in cols]
    row = conn.execute(
        'SELECT %s FROM "session" WHERE id=?' % ",".join('"%s"' % c for c in select_cols),
        (sid,),
    ).fetchone()
    if row is None:
        return None
    rec = dict(zip(select_cols, row))
    raw_parent = rec.get("parent_id")
    parent_token = safe_token(raw_parent)
    if parent_token is not None:
        node["parent_id"] = parent_token
    elif raw_parent is None:
        node["parent_id"] = None  # 无父（典型为根会话）
    else:
        node["parent_id"] = "UNKNOWN"  # 非空但非法 token，不回显原值
    if "permission" in rec:
        node["permission_mode"] = safe_token(rec.get("permission")) or "UNKNOWN"

    agg = None
    if sources["turn_usage"]:
        agg = conn.execute(
            "SELECT COUNT(*), MIN(started_at), "
            "MAX(CASE WHEN completed_at IS NOT NULL THEN completed_at ELSE started_at END), "
            "SUM(tool_call_count) FROM turn_usage WHERE session_id=?",
            (sid,),
        ).fetchone()
        turn_count = safe_int(agg[0], lo=0, hi=10 ** 9)
        if turn_count is not None:
            node["turn_count"] = turn_count
        t_start, t_end = safe_int(agg[1]), safe_int(agg[2])
        if t_start is not None and t_end is not None and t_end >= t_start:
            node["duration_ms"] = t_end - t_start
            node["duration_source"] = "turn_usage_span"
        last = conn.execute(
            "SELECT status FROM turn_usage WHERE session_id=? "
            "ORDER BY started_at DESC, turn_id DESC LIMIT 1",
            (sid,),
        ).fetchone()
        last_status = safe_token(last[0]) if last else None
        if last_status:
            node["status"] = last_status
            node["terminal"] = last_status in TERMINAL_STATUSES

    if node["duration_ms"] == "UNKNOWN" and "time_created" in rec and "time_updated" in rec:
        c0, c1 = safe_int(rec.get("time_created")), safe_int(rec.get("time_updated"))
        if c0 is not None and c1 is not None and c1 >= c0:
            node["duration_ms"] = c1 - c0
            node["duration_source"] = "session_time_span"

    if sources["tool_usage"]:
        cnt = conn.execute(
            "SELECT COUNT(*) FROM tool_usage WHERE session_id=?", (sid,)
        ).fetchone()[0]
        node["tool_call_count"] = safe_int(cnt, hi=10 ** 9)
    elif sources["turn_usage"] and agg is not None:
        summed = safe_int(agg[3], hi=10 ** 9)
        if summed is not None:
            node["tool_call_count"] = summed

    if sources["model_usage"]:
        def distinct_list(column, key):
            rows = conn.execute(
                'SELECT DISTINCT "%s" FROM model_usage WHERE session_id=?' % column,
                (sid,),
            ).fetchall()
            vals = sorted({v for v in (safe_token(r[0], key=key) for r in rows) if v})
            return vals[:LIST_CAP] if vals else "UNKNOWN"

        node["models"] = distinct_list("model_id", "model_id")
        node["providers"] = distinct_list("provider_id", "provider_id")
        node["modes"] = distinct_list("mode", "mode")
    return node


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description="只读采集原生 Agent 子任务树(session.parent_id)证据（白名单输出，绝不泄露 payload/标题/目录/凭据）。",
    )
    parser.add_argument("--db", required=True, help="原生 SQLite 数据库文件路径")
    parser.add_argument("--root-session", required=True, dest="root_session",
                        help="根 session id（子代理的父会话）")
    parser.add_argument("--root-input", required=True, dest="root_input",
                        help="根 session_input.promoted_message_id（显式输入绑定）")
    parser.add_argument("--max-nodes", type=int, default=500,
                        help="后代节点数上限（默认 500）")
    parser.add_argument("--max-depth", type=int, default=32,
                        help="后代深度上限（默认 32）")
    args = parser.parse_args(argv)

    for ident in (args.root_session, args.root_input):
        if not TOKEN_RE.match(ident):
            return fail(EXIT_USAGE, "invalid_identifier")
    if not (1 <= args.max_nodes <= 10000 and 1 <= args.max_depth <= 512):
        return fail(EXIT_USAGE, "invalid_limit")

    db_path = os.path.abspath(args.db)
    conn, err = open_readonly(db_path)
    if conn is None:
        return fail(EXIT_DB, err)

    try:
        # 单一读事务快照
        conn.execute("BEGIN DEFERRED")
        for table, need_cols in REQUIRED_TABLE_COLUMNS.items():
            if not table_exists(conn, table):
                conn.execute("ROLLBACK")
                conn.close()
                return fail(EXIT_DB, "db_schema_missing_table")
            cols = table_columns(conn, table)
            for col in need_cols:
                if col not in cols:
                    conn.execute("ROLLBACK")
                    conn.close()
                    return fail(EXIT_DB, "db_schema_missing_column")
        sources = {t: table_exists(conn, t) for t in OPTIONAL_TABLES}
        session_cols = table_columns(conn, "session")
        input_cols = table_columns(conn, "session_input")

        root_row = conn.execute(
            'SELECT 1 FROM "session" WHERE id=?', (args.root_session,)
        ).fetchone()
        if root_row is None:
            conn.execute("ROLLBACK")
            conn.close()
            return fail(EXIT_ROOT, "root_session_not_found")

        seq_cols = [c for c in ("promoted_sequence", "admitted_sequence") if c in input_cols]
        input_rows = conn.execute(
            'SELECT promoted_message_id%s FROM session_input '
            "WHERE session_id=? AND promoted_message_id IS NOT NULL "
            "ORDER BY promoted_message_id" % (("," + ",".join('"%s"' % c for c in seq_cols)) if seq_cols else ""),
            (args.root_session,),
        ).fetchall()
        root_bind = next((r for r in input_rows if r[0] == args.root_input), None)
        if root_bind is None:
            conn.execute("ROLLBACK")
            conn.close()
            return fail(EXIT_ROOT, "root_input_not_bound")

        turn = "UNKNOWN"
        turn_source = "UNKNOWN"
        for i, col in enumerate(seq_cols, start=1):
            t = safe_int(root_bind[i])
            if t is not None:
                turn, turn_source = t, col
                break

        promoted_input_count = len(input_rows)
        if promoted_input_count == 1:
            attribution = "unique_promoted_input_in_root_session"
        else:
            attribution = "ambiguous_multiple_promoted_inputs"

        # selected turn：按 session_id + turn_usage.user_message_id 精确绑定本次 root input。
        # 无表/无绑定列/0 行/多行一律 UNKNOWN，绝不借会话最新 turn；ordinal 不是 native turn 身份。
        selected_turn = {
            "turn_id": "UNKNOWN", "status": "UNKNOWN", "terminal": "UNKNOWN",
            "tool_call_count": "UNKNOWN", "duration_ms": "UNKNOWN",
        }
        if not sources["turn_usage"]:
            turn_binding_status = "source_table_missing"
        elif "user_message_id" not in table_columns(conn, "turn_usage"):
            turn_binding_status = "binding_column_missing"
        else:
            hits = conn.execute(
                "SELECT turn_id, status, started_at, completed_at, tool_call_count "
                "FROM turn_usage WHERE session_id=? AND user_message_id=? ORDER BY turn_id",
                (args.root_session, args.root_input),
            ).fetchall()
            if len(hits) == 1:
                turn_binding_status = "bound_unique"
                h_tid, h_status, h_start, h_end, h_tools = hits[0]
                tok = safe_token(h_tid)
                if tok:
                    selected_turn["turn_id"] = tok
                st = safe_token(h_status)
                if st:
                    selected_turn["status"] = st
                    selected_turn["terminal"] = st in TERMINAL_STATUSES
                htc = safe_int(h_tools, hi=10 ** 9)
                if htc is not None:
                    selected_turn["tool_call_count"] = htc
                s0, s1 = safe_int(h_start), safe_int(h_end)
                if s0 is not None and s1 is not None and s1 >= s0:
                    selected_turn["duration_ms"] = s1 - s0
            elif len(hits) == 0:
                turn_binding_status = "no_matching_turn"
            else:
                turn_binding_status = "ambiguous_multiple_matching_turns"

        # 只沿 parent_id 枚举真实后代（BFS，有界，环安全）
        nodes = []
        visited = {args.root_session}
        frontier = deque([(args.root_session, 0)])
        cycle_edges = 0
        edge_count = 0
        max_depth_observed = 0
        truncation_reasons = []
        root_node = None

        while frontier:
            if len(nodes) >= args.max_nodes:
                truncation_reasons.append("max_nodes")
                break
            sid, depth = frontier.popleft()
            node = gather_node(conn, sid, session_cols, sources)
            if node is None:
                continue
            node["depth"] = depth
            if sid == args.root_session:
                node["root_input_attribution"] = "root_session_bound"
                root_node = node
            else:
                node["root_input_attribution"] = attribution
            pid = node["parent_id"]
            if isinstance(pid, str) and pid != "UNKNOWN":
                parent_exists = conn.execute(
                    'SELECT 1 FROM "session" WHERE id=?', (pid,)
                ).fetchone()
                node["parent_exists"] = parent_exists is not None
            nodes.append(node)
            max_depth_observed = max(max_depth_observed, depth)
            if depth >= args.max_depth:
                if conn.execute(
                    'SELECT 1 FROM "session" WHERE parent_id=? LIMIT 1', (sid,)
                ).fetchone():
                    truncation_reasons.append("max_depth")
                continue
            for (child,) in conn.execute(
                'SELECT id FROM "session" WHERE parent_id=? ORDER BY id', (sid,)
            ).fetchall():
                child_token = safe_token(child)
                if child_token is None:
                    continue
                if child_token in visited:
                    cycle_edges += 1
                    continue
                visited.add(child_token)
                edge_count += 1
                frontier.append((child_token, depth + 1))

        if root_node is None or root_node["session_id"] != args.root_session:
            conn.execute("ROLLBACK")
            conn.close()
            return fail(EXIT_ROOT, "root_session_not_found")

        root_parent_exists = root_node.get("parent_exists")
        result = {
            "ok": True,
            "tool": TOOL,
            "schema_version": SCHEMA_VERSION,
            "sources": dict(sources, session=True, session_input=True),
            "root": {
                "session_id": args.root_session,
                "root_input_promoted_message_id": args.root_input,
                "turn": turn,
                "turn_source": turn_source,
                "turn_binding_status": turn_binding_status,
                "selected_turn": selected_turn,
                "promoted_input_count": promoted_input_count,
                "parent_exists": root_parent_exists,
            },
            "tree": {
                "node_count": len(nodes),
                "edge_count": edge_count,
                "max_depth_observed": max_depth_observed,
                "cycle_edges": cycle_edges,
                "truncated": bool(truncation_reasons),
                "truncation_reasons": sorted(set(truncation_reasons)),
                "limits": {"max_nodes": args.max_nodes, "max_depth": args.max_depth},
                "nodes": nodes,
            },
            "attribution_note": (
                "session.parent_id 仅证明 session 级父子归属；当根会话存在多个 promoted input 时，"
                "无法证明后代属于本次 --root-input（歧义必须保留，不做时间/标题猜测）。"
            ),
            "session_aggregation_note": (
                "nodes[] 的 status/terminal/tool_call_count/duration_ms/turn_count 均为 session 维度"
                "聚合（root 节点含该会话全部 input 的 turns，其 status 取会话最新 turn）；"
                "本次 --root-input 的真实选中 turn 见 root.selected_turn"
                "（turn_usage.user_message_id 精确绑定，唯一命中才给值）；"
                "root.turn 仅为 session_input 序数（ordinal），不是 native turn 身份。"
            ),
        }
        conn.execute("ROLLBACK")
        conn.close()
        emit(result)
        return EXIT_OK
    except sqlite3.Error as exc:
        code = signature_code(exc)
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        conn.close()
        return fail(EXIT_DB, code)
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return fail(EXIT_INTERNAL, "internal_error")


if __name__ == "__main__":
    sys.exit(main())
