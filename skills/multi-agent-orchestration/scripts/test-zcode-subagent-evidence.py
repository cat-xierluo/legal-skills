#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test-zcode-subagent-evidence.py — zcode-subagent-evidence CLI 的黑盒契约测试。

用途
----
以真实小消费者方式（python3 subprocess 调用被测 CLI、解析 stdout 单行 JSON、
断言退出码契约）验证同目录下 zcode-subagent-evidence.py 的行为，覆盖：

1. 坏 schema：缺 session_input 表 → 退出码 3 db_schema_missing_table；
   session 缺 parent_id 列 → 退出码 3 db_schema_missing_column；非 SQLite 文件 → db_not_sqlite。
2. 坏 JSON：model/provider/mode 列存截断 JSON → 对应字段 UNKNOWN、不崩溃、不回显原文。
3. root 绑定：--root-input 属于另一 session → 退出码 4 root_input_not_bound；
   无关根的后代不出现在树里；根 session 不存在 → root_session_not_found。
4. 孤儿：child.parent_id 指向不存在的 session → 可作 root 运行，parent_exists=false。
5. 循环：A→B→A 互指与 parent_id 自指 → 有界终止、cycle_edges>0、节点不重复。
6. 截断：链深超过 --max-depth → truncated 含 max_depth（含 40 深链走默认 max_depth=32 路径）；
   星型子节点超过 --max-nodes → truncated 含 max_nodes（小上限 3/5）。
7. 非终态：turn_usage status='running' → status="running"、terminal=false。
8. 多轮归属歧义：根会话 2 条 promoted input → 子节点
   root_input_attribution=ambiguous_multiple_promoted_inputs 且 promoted_input_count==2；
   单 input → unique_promoted_input_in_root_session。
9. 缺字段：promoted/admitted_sequence 为 NULL → root.turn=="UNKNOWN"；无 model_usage 行 →
   models=="UNKNOWN"；无可选表 → sources 如实标 false。
10. 秘密金丝雀零输出：所有 fixture 的 title/directory/payload/error_message/raw_usage_json
    等列默认植入含空格与斜杠的 canary（ZCANARY1 ...），每个用例断言 stdout+stderr 均不含 canary。
11. 只读证明：0444 db 文件 + 0555 目录下运行成功、sha256 前后一致、无 -wal/-journal 新文件；
    --db 指向不存在路径 → 退出码 3 且运行后该文件仍不存在。
12. 用法错误：缺必选参数 / 含空格或斜杠的非法 id / 非法上限 → 退出码 2。

约束
----
* 纯标准库 unittest；直接 `python3 test-zcode-subagent-evidence.py` 运行，退出码即测试结果。
* 不 import 被测实现（subprocess 黑盒）。
* fixture 全部用 tempfile.TemporaryDirectory 在系统临时目录自建 SQLite，用完即删，
  绝不读取真实用户数据库（~/.zcode 下任何 db）。
"""

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest

CLI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zcode-subagent-evidence.py")
CANARY_MARK = "ZCANARY1"
CANARY = "ZCANARY1 secret /path ò"

if not os.path.isfile(CLI_PATH):
    raise RuntimeError("找不到被测 CLI: %s" % CLI_PATH)

SESSION_COLUMN_TYPES = {
    "id": "TEXT PRIMARY KEY",
    "parent_id": "TEXT",
    "permission": "TEXT",
    "time_created": "INTEGER",
    "time_updated": "INTEGER",
    "title": "TEXT",
    "directory": "TEXT",
}
SESSION_DEFAULTS = {
    "parent_id": None,
    "permission": "default",
    "time_created": 1000,
    "time_updated": 2000,
    "title": CANARY,
    "directory": CANARY,
}
EXPECTED_NODE_KEYS = {
    "session_id", "parent_id", "depth", "parent_exists", "status", "terminal",
    "permission_mode", "models", "providers", "modes", "turn_count",
    "tool_call_count", "duration_ms", "duration_source", "root_input_attribution",
}
EXPECTED_ROOT_KEYS = {
    "session_id", "root_input_promoted_message_id", "turn", "turn_source",
    "promoted_input_count", "parent_exists",
}
EXPECTED_TREE_KEYS = {
    "node_count", "edge_count", "max_depth_observed", "cycle_edges",
    "truncated", "truncation_reasons", "limits", "nodes",
}
ALL_TABLES = ("session", "session_input", "turn_usage", "tool_usage", "model_usage")


# ---------------------------------------------------------------------------
# fixture 行构造器（敏感列默认植入 canary，配合全局零泄漏断言）
# ---------------------------------------------------------------------------

def S(sid, parent=None, **kw):
    row = {"id": sid, "parent_id": parent, "permission": "default",
           "time_created": 1000, "time_updated": 2000,
           "title": CANARY, "directory": CANARY}
    row.update(kw)
    return row


def IN(session_id, promoted_message_id, promoted_sequence=None, admitted_sequence=None, **kw):
    row = {"session_id": session_id, "promoted_message_id": promoted_message_id,
           "promoted_sequence": promoted_sequence, "admitted_sequence": admitted_sequence,
           "payload": CANARY, "status": "promoted"}
    row.update(kw)
    return row


def TU(session_id, turn_id=1, status="completed", started_at=1000, completed_at=2000,
       tool_call_count=1):
    return {"session_id": session_id, "turn_id": turn_id, "status": status,
            "started_at": started_at, "completed_at": completed_at,
            "tool_call_count": tool_call_count}


def TO(session_id, tool_name="Bash", status="completed", error_message=CANARY):
    return {"session_id": session_id, "tool_name": tool_name,
            "status": status, "error_message": error_message}


def MU(session_id, provider_id="bigmodel", model_id="GLM-5.3", mode="primary",
       status="ok", raw_usage_json=CANARY):
    return {"session_id": session_id, "provider_id": provider_id, "model_id": model_id,
            "mode": mode, "status": status, "raw_usage_json": raw_usage_json}


def chain_sessions(n, prefix="c"):
    rows = [S("%s00" % prefix)]
    for i in range(1, n):
        rows.append(S("%s%02d" % (prefix, i), "%s%02d" % (prefix, i - 1)))
    return rows


def create_db(path, sessions, inputs, turns=(), tools=(), models=(),
              tables=ALL_TABLES,
              session_columns=("id", "parent_id", "permission", "time_created",
                               "time_updated", "title", "directory")):
    """在 path 处按原生 schema 子集自建 fixture SQLite。"""
    conn = sqlite3.connect(path)
    try:
        if "session" in tables:
            conn.execute("CREATE TABLE session (%s)" % ", ".join(
                "%s %s" % (c, SESSION_COLUMN_TYPES[c]) for c in session_columns))
            for s in sessions:
                values = [s.get(c, SESSION_DEFAULTS.get(c)) for c in session_columns]
                conn.execute(
                    "INSERT INTO session (%s) VALUES (%s)" % (
                        ",".join(session_columns), ",".join(["?"] * len(session_columns))),
                    values)
        if "session_input" in tables:
            conn.execute(
                "CREATE TABLE session_input ("
                "id INTEGER PRIMARY KEY, session_id TEXT, payload TEXT, "
                "promoted_sequence INTEGER, admitted_sequence INTEGER, "
                "promoted_message_id TEXT, status TEXT)")
            for i, r in enumerate(inputs, start=1):
                conn.execute(
                    "INSERT INTO session_input (id,session_id,payload,promoted_sequence,"
                    "admitted_sequence,promoted_message_id,status) VALUES (?,?,?,?,?,?,?)",
                    (r.get("id", i), r["session_id"], r.get("payload", CANARY),
                     r.get("promoted_sequence"), r.get("admitted_sequence"),
                     r.get("promoted_message_id"), r.get("status", "promoted")))
        if "turn_usage" in tables:
            conn.execute(
                "CREATE TABLE turn_usage ("
                "session_id TEXT, turn_id INTEGER, status TEXT, "
                "started_at INTEGER, completed_at INTEGER, tool_call_count INTEGER)")
            for t in turns:
                conn.execute(
                    "INSERT INTO turn_usage (session_id,turn_id,status,started_at,"
                    "completed_at,tool_call_count) VALUES (?,?,?,?,?,?)",
                    (t["session_id"], t["turn_id"], t["status"],
                     t["started_at"], t["completed_at"], t["tool_call_count"]))
        if "tool_usage" in tables:
            conn.execute(
                "CREATE TABLE tool_usage ("
                "id INTEGER PRIMARY KEY, session_id TEXT, tool_name TEXT, "
                "status TEXT, error_message TEXT)")
            for t in tools:
                conn.execute(
                    "INSERT INTO tool_usage (session_id,tool_name,status,error_message) "
                    "VALUES (?,?,?,?)",
                    (t["session_id"], t["tool_name"], t["status"], t["error_message"]))
        if "model_usage" in tables:
            conn.execute(
                "CREATE TABLE model_usage ("
                "id INTEGER PRIMARY KEY, session_id TEXT, provider_id TEXT, "
                "model_id TEXT, mode TEXT, status TEXT, raw_usage_json TEXT)")
            for m in models:
                conn.execute(
                    "INSERT INTO model_usage (session_id,provider_id,model_id,mode,status,"
                    "raw_usage_json) VALUES (?,?,?,?,?,?)",
                    (m["session_id"], m["provider_id"], m["model_id"],
                     m["mode"], m["status"], m["raw_usage_json"]))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI 小消费者辅助：subprocess 黑盒 + JSON 契约 + 全局 canary 零泄漏断言
# ---------------------------------------------------------------------------

def run_cli(args):
    return subprocess.run(
        [sys.executable, CLI_PATH] + list(args),
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)


def _assert_no_canary(proc):
    combined = (proc.stdout or "") + (proc.stderr or "")
    if CANARY_MARK in combined:
        raise AssertionError(
            "秘密金丝雀泄漏到 CLI 输出 (rc=%s): stdout=%r stderr=%r"
            % (proc.returncode, proc.stdout, proc.stderr))


def parse_output_json(proc):
    lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
    if len(lines) != 1:
        raise AssertionError("期望单行 JSON 输出，实际 %d 行: stdout=%r stderr=%r"
                             % (len(lines), proc.stdout, proc.stderr))
    return json.loads(lines[0])


def run_case(db, root_session, root_input, max_nodes=None, max_depth=None):
    args = ["--db", db, "--root-session", root_session, "--root-input", root_input]
    if max_nodes is not None:
        args += ["--max-nodes", str(max_nodes)]
    if max_depth is not None:
        args += ["--max-depth", str(max_depth)]
    proc = run_cli(args)
    _assert_no_canary(proc)
    return proc


def run_success(db, root_session, root_input, max_nodes=None, max_depth=None):
    proc = run_case(db, root_session, root_input, max_nodes=max_nodes, max_depth=max_depth)
    if proc.returncode != 0:
        raise AssertionError("期望退出码 0，实际 %s: stdout=%r stderr=%r"
                             % (proc.returncode, proc.stdout, proc.stderr))
    obj = parse_output_json(proc)
    if obj.get("ok") is not True:
        raise AssertionError("期望 ok=true，实际: %r" % (obj,))
    return obj


def run_failure(db, root_session, root_input, expected_exit, expected_code,
                max_nodes=None, max_depth=None):
    proc = run_case(db, root_session, root_input, max_nodes=max_nodes, max_depth=max_depth)
    if proc.returncode != expected_exit:
        raise AssertionError("期望退出码 %s，实际 %s: stdout=%r stderr=%r"
                             % (expected_exit, proc.returncode, proc.stdout, proc.stderr))
    obj = parse_output_json(proc)
    if obj.get("ok") is not False:
        raise AssertionError("期望 ok=false，实际: %r" % (obj,))
    if obj.get("error", {}).get("code") != expected_code:
        raise AssertionError("期望错误码 %s，实际: %r" % (expected_code, obj))
    if obj.get("error", {}).get("exit") != expected_exit:
        raise AssertionError("期望 error.exit=%s，实际: %r" % (expected_exit, obj))
    return obj


def node_by_id(obj, sid):
    for n in obj["tree"]["nodes"]:
        if n["session_id"] == sid:
            return n
    raise AssertionError("节点 %s 不在树中: %s"
                         % (sid, [n["session_id"] for n in obj["tree"]["nodes"]]))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def db_path(tmp, name="db.sqlite"):
    return os.path.join(tmp, name)


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

class TestOutputContract(unittest.TestCase):
    """成功路径：单行 JSON、白名单字段集合、退出码 0。"""

    def test_success_json_contract_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = db_path(tmp)
            create_db(
                db,
                sessions=[S("s_root"), S("s_child", "s_root", permission="acceptEdits")],
                inputs=[IN("s_root", "msg_root", promoted_sequence=3, admitted_sequence=4)],
                turns=[TU("s_child", turn_id=1, status="completed",
                          started_at=5000, completed_at=6500, tool_call_count=2)],
                tools=[TO("s_child"), TO("s_child")],
                models=[MU("s_child", provider_id="bigmodel", model_id="GLM-5.3",
                           mode="primary")])
            proc = run_case(db, "s_root", "msg_root")
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.count("\n"), 1, "成功输出必须是单行 JSON")
            obj = parse_output_json(proc)
            for key in ("ok", "tool", "schema_version", "sources", "root", "tree",
                        "attribution_note"):
                self.assertIn(key, obj)
            self.assertEqual(obj["sources"], {
                "session": True, "session_input": True, "turn_usage": True,
                "tool_usage": True, "model_usage": True})
            root = obj["root"]
            self.assertEqual(set(root), EXPECTED_ROOT_KEYS)
            self.assertEqual(root["session_id"], "s_root")
            self.assertEqual(root["root_input_promoted_message_id"], "msg_root")
            self.assertEqual(root["turn"], 3)
            self.assertEqual(root["turn_source"], "promoted_sequence")
            self.assertEqual(root["promoted_input_count"], 1)
            self.assertEqual(root["parent_exists"], "UNKNOWN")  # 根无 parent_id
            tree = obj["tree"]
            self.assertEqual(set(tree), EXPECTED_TREE_KEYS)
            self.assertEqual(tree["node_count"], 2)
            self.assertEqual(tree["edge_count"], 1)
            self.assertEqual(tree["max_depth_observed"], 1)
            self.assertEqual(tree["cycle_edges"], 0)
            self.assertIs(tree["truncated"], False)
            self.assertEqual(tree["truncation_reasons"], [])
            self.assertEqual(tree["limits"], {"max_nodes": 500, "max_depth": 32})
            root_node = node_by_id(obj, "s_root")
            self.assertEqual(set(root_node), EXPECTED_NODE_KEYS)
            self.assertEqual(root_node["depth"], 0)
            self.assertEqual(root_node["root_input_attribution"], "root_session_bound")
            child = node_by_id(obj, "s_child")
            self.assertEqual(child["depth"], 1)
            self.assertEqual(child["parent_id"], "s_root")
            self.assertIs(child["parent_exists"], True)
            self.assertEqual(child["status"], "completed")
            self.assertIs(child["terminal"], True)
            self.assertEqual(child["permission_mode"], "acceptEdits")
            self.assertEqual(child["models"], ["GLM-5.3"])
            self.assertEqual(child["providers"], ["bigmodel"])
            self.assertEqual(child["modes"], ["primary"])
            self.assertEqual(child["turn_count"], 1)
            self.assertEqual(child["tool_call_count"], 2)
            self.assertEqual(child["duration_ms"], 1500)
            self.assertEqual(child["duration_source"], "turn_usage_span")
            self.assertEqual(child["root_input_attribution"],
                             "unique_promoted_input_in_root_session")


class TestSchemaErrors(unittest.TestCase):
    """退出码 3：缺表 / 缺列 / 非 SQLite 文件。"""

    def test_missing_session_input_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = db_path(tmp)
            create_db(db, sessions=[S("s_root")], inputs=[],
                      tables=("session", "turn_usage", "tool_usage", "model_usage"))
            run_failure(db, "s_root", "msg_root", 3, "db_schema_missing_table")

    def test_session_missing_parent_id_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = db_path(tmp)
            create_db(db, sessions=[S("s_root")], inputs=[IN("s_root", "msg_root")],
                      session_columns=("id", "permission", "time_created",
                                       "time_updated", "title", "directory"))
            run_failure(db, "s_root", "msg_root", 3, "db_schema_missing_column")

    def test_not_sqlite_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = db_path(tmp)
            with open(db, "wb") as f:
                f.write(b"this is definitely not a sqlite database blob \x00\xff\xfe")
            run_failure(db, "s_root", "msg_root", 3, "db_not_sqlite")


class TestBadJsonFields(unittest.TestCase):
    """model/provider/mode 列坏 JSON → UNKNOWN、不崩溃、不回显原文。"""

    def test_bad_json_models_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = db_path(tmp)
            create_db(
                db,
                sessions=[S("s_root"), S("s_child", "s_root")],
                inputs=[IN("s_root", "msg_root")],
                models=[MU("s_child",
                           provider_id='{"provider_id": "BADPROV7',
                           model_id='{"model_id": "BADMODEL7',
                           mode='{"mode": "BADMODE7')])
            proc = run_case(db, "s_root", "msg_root")
            self.assertEqual(proc.returncode, 0, "坏 JSON 不应导致崩溃")
            self.assertNotIn("BADMODEL7", proc.stdout + proc.stderr)
            self.assertNotIn("BADPROV7", proc.stdout + proc.stderr)
            self.assertNotIn("BADMODE7", proc.stdout + proc.stderr)
            obj = parse_output_json(proc)
            child = node_by_id(obj, "s_child")
            self.assertEqual(child["models"], "UNKNOWN")
            self.assertEqual(child["providers"], "UNKNOWN")
            self.assertEqual(child["modes"], "UNKNOWN")

    def test_good_json_inner_token_extracted(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = db_path(tmp)
            create_db(
                db,
                sessions=[S("s_root"), S("s_child", "s_root")],
                inputs=[IN("s_root", "msg_root")],
                models=[MU("s_child",
                           provider_id='{"provider_id": "prov-1"}',
                           model_id='{"model_id": "glm-5.3"}',
                           mode='{"mode": "primary"}')])
            obj = run_success(db, "s_root", "msg_root")
            child = node_by_id(obj, "s_child")
            self.assertEqual(child["models"], ["glm-5.3"])
            self.assertEqual(child["providers"], ["prov-1"])
            self.assertEqual(child["modes"], ["primary"])


class TestRootBinding(unittest.TestCase):
    """退出码 4：跨 session 输入 / 根不存在；无关子树不得混入。"""

    def _fixture(self, tmp):
        db = db_path(tmp)
        create_db(
            db,
            sessions=[S("s_root"), S("s_child", "s_root"),
                      S("s_other"), S("s_other_child", "s_other")],
            inputs=[IN("s_root", "msg_root"), IN("s_other", "msg_other")])
        return db

    def test_root_input_bound_to_other_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self._fixture(tmp)
            run_failure(db, "s_root", "msg_other", 4, "root_input_not_bound")

    def test_unrelated_subtree_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self._fixture(tmp)
            obj = run_success(db, "s_root", "msg_root")
            ids = {n["session_id"] for n in obj["tree"]["nodes"]}
            self.assertEqual(ids, {"s_root", "s_child"})
            self.assertNotIn("s_other", ids)
            self.assertNotIn("s_other_child", ids)

    def test_root_session_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self._fixture(tmp)
            run_failure(db, "s_ghost", "msg_root", 4, "root_session_not_found")


class TestOrphanRoot(unittest.TestCase):
    """孤儿会话（parent 指向不存在的 session）可作 root 运行。"""

    def test_orphan_as_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = db_path(tmp)
            create_db(db,
                      sessions=[S("s_orphan", "s_ghost_parent")],
                      inputs=[IN("s_orphan", "msg_o")])
            obj = run_success(db, "s_orphan", "msg_o")
            self.assertIs(obj["root"]["parent_exists"], False)
            self.assertEqual(obj["tree"]["node_count"], 1)
            node = obj["tree"]["nodes"][0]
            self.assertEqual(node["session_id"], "s_orphan")
            self.assertEqual(node["parent_id"], "s_ghost_parent")
            self.assertIs(node["parent_exists"], False)


class TestCycles(unittest.TestCase):
    """循环防护：互指与自指均有界终止、cycle_edges>0、节点不重复。"""

    def test_two_session_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = db_path(tmp)
            create_db(db,
                      sessions=[S("s_a", "s_b"), S("s_b", "s_a")],
                      inputs=[IN("s_a", "msg_a")])
            obj = run_success(db, "s_a", "msg_a")
            tree = obj["tree"]
            self.assertGreaterEqual(tree["cycle_edges"], 1)
            ids = [n["session_id"] for n in tree["nodes"]]
            self.assertEqual(sorted(ids), ["s_a", "s_b"], "环中节点不得重复")
            self.assertEqual(tree["node_count"], 2)

    def test_self_reference_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = db_path(tmp)
            create_db(db,
                      sessions=[S("s_self", "s_self")],
                      inputs=[IN("s_self", "msg_s")])
            obj = run_success(db, "s_self", "msg_s")
            self.assertGreaterEqual(obj["tree"]["cycle_edges"], 1)
            self.assertEqual(obj["tree"]["node_count"], 1)
            self.assertIs(obj["root"]["parent_exists"], True)


class TestTruncation(unittest.TestCase):
    """--max-depth / --max-nodes 截断（含默认 max_depth=32 路径）。"""

    def test_max_depth_small_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = db_path(tmp)
            create_db(db, sessions=chain_sessions(12), inputs=[IN("c00", "msg_root")])
            obj = run_success(db, "c00", "msg_root", max_depth=3)
            tree = obj["tree"]
            self.assertEqual(tree["node_count"], 4)  # c00..c03
            self.assertIs(tree["truncated"], True)
            self.assertEqual(tree["truncation_reasons"], ["max_depth"])
            self.assertEqual(tree["max_depth_observed"], 3)
            self.assertEqual(node_by_id(obj, "c03")["depth"], 3)

    def test_default_depth_truncates_40_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = db_path(tmp)
            create_db(db, sessions=chain_sessions(40), inputs=[IN("c00", "msg_root")])
            obj = run_success(db, "c00", "msg_root")  # 默认 max_depth=32
            tree = obj["tree"]
            self.assertEqual(tree["node_count"], 33)  # c00..c32
            self.assertIs(tree["truncated"], True)
            self.assertIn("max_depth", tree["truncation_reasons"])
            self.assertNotIn("max_nodes", tree["truncation_reasons"])
            self.assertEqual(tree["max_depth_observed"], 32)
            self.assertEqual(tree["limits"], {"max_nodes": 500, "max_depth": 32})

    def _star_fixture(self, tmp):
        db = db_path(tmp)
        create_db(db,
                  sessions=[S("s_root")] + [S("k%d" % i, "s_root") for i in range(1, 8)],
                  inputs=[IN("s_root", "msg_root")])
        return db

    def test_max_nodes_star_limit_3(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self._star_fixture(tmp)
            obj = run_success(db, "s_root", "msg_root", max_nodes=3)
            tree = obj["tree"]
            self.assertEqual(tree["node_count"], 3)
            self.assertIs(tree["truncated"], True)
            self.assertEqual(tree["truncation_reasons"], ["max_nodes"])
            self.assertNotIn("max_depth", tree["truncation_reasons"])

    def test_max_nodes_star_limit_5(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self._star_fixture(tmp)
            obj = run_success(db, "s_root", "msg_root", max_nodes=5)
            tree = obj["tree"]
            self.assertEqual(tree["node_count"], 5)
            self.assertIs(tree["truncated"], True)
            self.assertIn("max_nodes", tree["truncation_reasons"])


class TestRunningStatus(unittest.TestCase):
    """turn_usage status='running' → status=running、terminal=false、不计完成。"""

    def test_running_not_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = db_path(tmp)
            create_db(
                db,
                sessions=[S("s_root"), S("s_child", "s_root")],
                inputs=[IN("s_root", "msg_root", promoted_sequence=1)],
                turns=[TU("s_child", turn_id=1, status="completed",
                          started_at=1000, completed_at=1500, tool_call_count=2),
                       TU("s_child", turn_id=2, status="running",
                          started_at=1600, completed_at=None, tool_call_count=1)],
                tables=("session", "session_input", "turn_usage", "model_usage"))
            obj = run_success(db, "s_root", "msg_root")
            child = node_by_id(obj, "s_child")
            self.assertEqual(child["status"], "running")
            self.assertIs(child["terminal"], False)
            self.assertNotEqual(child["status"], "completed")
            self.assertEqual(child["turn_count"], 2)
            self.assertEqual(child["duration_ms"], 600)  # max(1500,1600)-1000
            self.assertEqual(child["duration_source"], "turn_usage_span")
            # tool_usage 表缺失 → 回退 SUM(turn_usage.tool_call_count)
            self.assertIs(obj["sources"]["tool_usage"], False)
            self.assertEqual(child["tool_call_count"], 3)
            root_node = node_by_id(obj, "s_root")
            self.assertEqual(root_node["status"], "UNKNOWN")
            self.assertEqual(root_node["terminal"], "UNKNOWN")
            self.assertEqual(root_node["duration_ms"], 1000)  # session 时间跨度回退
            self.assertEqual(root_node["duration_source"], "session_time_span")


class TestAttribution(unittest.TestCase):
    """多轮 promoted input 归属歧义 vs 单 input 唯一归属。"""

    def test_multiple_promoted_inputs_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = db_path(tmp)
            create_db(
                db,
                sessions=[S("s_root"), S("s_child", "s_root")],
                inputs=[IN("s_root", "msg_a", promoted_sequence=1),
                        IN("s_root", "msg_b", promoted_sequence=2),
                        IN("s_root", None)])  # NULL promoted_message_id 不计数
            obj = run_success(db, "s_root", "msg_a")
            self.assertEqual(obj["root"]["promoted_input_count"], 2)
            child = node_by_id(obj, "s_child")
            self.assertEqual(child["root_input_attribution"],
                             "ambiguous_multiple_promoted_inputs")
            root_node = node_by_id(obj, "s_root")
            self.assertEqual(root_node["root_input_attribution"], "root_session_bound")

    def test_single_promoted_input_unique(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = db_path(tmp)
            create_db(
                db,
                sessions=[S("s_root"), S("s_child", "s_root")],
                inputs=[IN("s_root", "msg_a", promoted_sequence=1),
                        IN("s_root", None)])
            obj = run_success(db, "s_root", "msg_a")
            self.assertEqual(obj["root"]["promoted_input_count"], 1)
            child = node_by_id(obj, "s_child")
            self.assertEqual(child["root_input_attribution"],
                             "unique_promoted_input_in_root_session")


class TestMissingFields(unittest.TestCase):
    """缺字段 → UNKNOWN / sources 如实标 false。"""

    def test_null_sequences_turn_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = db_path(tmp)
            create_db(db,
                      sessions=[S("s_root"), S("s_child", "s_root")],
                      inputs=[IN("s_root", "msg_root",
                                 promoted_sequence=None, admitted_sequence=None)])
            obj = run_success(db, "s_root", "msg_root")
            self.assertEqual(obj["root"]["turn"], "UNKNOWN")
            self.assertEqual(obj["root"]["turn_source"], "UNKNOWN")

    def test_no_model_usage_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = db_path(tmp)
            create_db(db,
                      sessions=[S("s_root"), S("s_child", "s_root")],
                      inputs=[IN("s_root", "msg_root")],
                      models=[MU("s_other")])  # 仅无关 session 有行
            obj = run_success(db, "s_root", "msg_root")
            self.assertIs(obj["sources"]["model_usage"], True)
            for n in obj["tree"]["nodes"]:
                self.assertEqual(n["models"], "UNKNOWN")
                self.assertEqual(n["providers"], "UNKNOWN")
                self.assertEqual(n["modes"], "UNKNOWN")

    def test_no_optional_tables_sources_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = db_path(tmp)
            create_db(db,
                      sessions=[S("s_root"), S("s_child", "s_root")],
                      inputs=[IN("s_root", "msg_root")],
                      tables=("session", "session_input"))
            obj = run_success(db, "s_root", "msg_root")
            self.assertEqual(obj["sources"], {
                "session": True, "session_input": True,
                "turn_usage": False, "tool_usage": False, "model_usage": False})
            for n in obj["tree"]["nodes"]:
                self.assertEqual(n["status"], "UNKNOWN")
                self.assertEqual(n["terminal"], "UNKNOWN")
                self.assertEqual(n["turn_count"], "UNKNOWN")
                self.assertEqual(n["tool_call_count"], "UNKNOWN")
                self.assertEqual(n["models"], "UNKNOWN")
                self.assertEqual(n["providers"], "UNKNOWN")
                self.assertEqual(n["modes"], "UNKNOWN")
            root_node = node_by_id(obj, "s_root")
            self.assertEqual(root_node["duration_ms"], 1000)  # session 时间跨度回退
            self.assertEqual(root_node["duration_source"], "session_time_span")
            self.assertEqual(obj["root"]["turn"], "UNKNOWN")


class TestCanarySuppression(unittest.TestCase):
    """秘密金丝雀零输出（所有 fixture 默认植入 canary，本用例额外加强）。"""

    def test_canary_never_leaked(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = db_path(tmp)
            create_db(
                db,
                sessions=[S("s_root", permission=CANARY, title=CANARY, directory=CANARY),
                          S("s_child", "s_root", permission="acceptEdits")],
                inputs=[IN("s_root", "msg_root", payload=CANARY)],
                turns=[TU("s_child", status="completed")],
                tools=[TO("s_child", tool_name=CANARY, error_message=CANARY)],
                models=[MU("s_child", raw_usage_json=CANARY)])
            proc = run_case(db, "s_root", "msg_root")
            self.assertEqual(proc.returncode, 0)
            self.assertNotIn(CANARY_MARK, proc.stdout + proc.stderr)
            obj = parse_output_json(proc)
            root_node = node_by_id(obj, "s_root")
            self.assertEqual(root_node["permission_mode"], "UNKNOWN",
                             "canary 形态的 permission 必须被 token 白名单过滤为 UNKNOWN")
            child = node_by_id(obj, "s_child")
            self.assertEqual(child["permission_mode"], "acceptEdits")


class TestReadOnly(unittest.TestCase):
    """只读证明：0444/0555 下可运行且无写入；缺失库文件不被创建。"""

    def test_readonly_0444_0555_sha_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            dbdir = os.path.join(tmp, "dbdir")
            os.mkdir(dbdir)
            db = os.path.join(dbdir, "db.sqlite")
            create_db(db,
                      sessions=[S("s_root"), S("s_child", "s_root")],
                      inputs=[IN("s_root", "msg_root")],
                      turns=[TU("s_child", status="completed")])
            before_hash = sha256_file(db)
            before_entries = set(os.listdir(dbdir))
            os.chmod(db, 0o444)
            os.chmod(dbdir, 0o555)
            try:
                obj = run_success(db, "s_root", "msg_root")
                after_hash = sha256_file(db)
                after_entries = set(os.listdir(dbdir))
            finally:
                os.chmod(dbdir, 0o755)
                os.chmod(db, 0o644)
            self.assertIs(obj["ok"], True)
            self.assertEqual(obj["tree"]["node_count"], 2)
            self.assertEqual(after_hash, before_hash, "只读运行不得修改数据库文件")
            self.assertEqual(after_entries, before_entries, "目录内不得新增任何文件")
            for name in after_entries:
                self.assertFalse(name.endswith(("-wal", "-shm", "-journal")),
                                 "出现副作用文件: %s" % name)

    def test_missing_db_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "missing.sqlite")
            before = set(os.listdir(tmp))
            run_failure(db, "s_root", "msg_root", 3, "db_file_missing")
            self.assertFalse(os.path.exists(db), "db 文件缺失时不得被创建")
            self.assertEqual(set(os.listdir(tmp)), before)


class TestUsageErrors(unittest.TestCase):
    """退出码 2：缺必选参数 / 非法 id（空格、斜杠）/ 非法上限。"""

    def test_missing_required_argument(self):
        proc = run_cli(["--root-session", "s_root", "--root-input", "msg_root"])  # 缺 --db
        self.assertEqual(proc.returncode, 2)
        _assert_no_canary(proc)

    def test_invalid_identifier_with_space(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = db_path(tmp)
            create_db(db, sessions=[S("s_root")], inputs=[IN("s_root", "msg_root")])
            run_failure(db, "s_root", "bad input", 2, "invalid_identifier")

    def test_invalid_identifier_with_slash(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = db_path(tmp)
            create_db(db, sessions=[S("s_root")], inputs=[IN("s_root", "msg_root")])
            run_failure(db, "s/root", "msg_root", 2, "invalid_identifier")

    def test_invalid_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = db_path(tmp)
            create_db(db, sessions=[S("s_root")], inputs=[IN("s_root", "msg_root")])
            run_failure(db, "s_root", "msg_root", 2, "invalid_limit", max_nodes=0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
