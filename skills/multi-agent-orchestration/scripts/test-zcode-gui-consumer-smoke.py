#!/usr/bin/env python3
# test-zcode-gui-consumer-smoke.py — 「用户调用 observe」消费者回归冒烟测试。
#
# 视角是真实消费者：设置依赖环境变量后，用一条 observe 命令观察一个合成
# SQLite 会话库，断言单行 JSON 结果、退出码与只读/不泄漏保证。不是对
# collector/adapter/observe 的全量单测，只钉住消费合同的关键面：
#
#   POS（当前候选必须全过）
#     1. completed 证据 → READY_FOR_PM_REVIEW，且三个 flags 恒为 false
#     2. running turn → 非 READY（TURN_RUNNING）
#     3. 末条 assistant 带 error → DELIVERY_ERROR，绝不误判 READY
#     4. 绑定错误（input 不存在）→ 失败闭合 exit 1 + INPUT_NOT_FOUND
#     5. 未知/缺列 schema → 失败闭合 exit 1 + DB_SCHEMA_INVALID
#     6. observe 前后 fixture 库文件 SHA-256 不变（只读保证）
#     7. 合成 CANARY / status_reason 秘密 / fixture 路径不出现在任何输出
#   NEG-C（当前候选必须失败闭合）
#     8. collector 输出合法 ok 但 exit 9 → exit 1 + OBS_COLLECTOR_FAILED
#     9. adapter 输出合法 READY 但 exit 7 → exit 1 + OBS_ADAPTER_FAILED
#   NEG-L（旧稿负控，可选：提供 ZCODE_GUI_OBSERVE_LEGACY 才运行）
#     10/11. 同一反例在旧稿 observe（无 exit-code 门控）必须「不满足断言」
#            （旧稿照样输出 OK/READY），证明反例确实钉住本回归的价值。
#            旧稿若意外通过该反例，负控判 FAIL（反例失效）。
#
# 依赖接入（环境变量，缺一不可地显式配置；observe 自身按同样顺序解析）：
#   ZCODE_GUI_OBSERVE          当前候选 observe 脚本路径
#   ZCODE_GUI_COLLECTOR        collector 脚本路径
#   ZCODE_GUI_ADAPTER          adapter 脚本路径
#   ZCODE_GUI_OBSERVE_LEGACY   旧稿 observe 路径（可选；缺省则 NEG-L 组 SKIP）
#
# 退出码：0 全部已运行断言通过；1 存在断言失败（含负控反例失效）；
#         2 依赖配置无效（部分设置 / 文件缺失 / 指纹与冻结版不符 / 错峰超时）；
#         77 三个核心依赖完全未配置（SKIP）。
#
# 冻结指纹内嵌于 EXPECTED_SHA256（仅指纹，不含任何依赖代码）。升级依赖时
# 须重新核对指纹并同步更新，回归结论才继续可迁移。
#
# Standard library only; supports Python 3.9+。
# License: MIT（通用工具类技能，见仓库 LICENSE 约定）。
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

SMOKE = "test-zcode-gui-consumer-smoke"

ENV_OBSERVE = "ZCODE_GUI_OBSERVE"
ENV_COLLECTOR = "ZCODE_GUI_COLLECTOR"
ENV_ADAPTER = "ZCODE_GUI_ADAPTER"
ENV_OBSERVE_LEGACY = "ZCODE_GUI_OBSERVE_LEGACY"

EXPECTED_SHA256 = {
    ENV_OBSERVE: "4480446b329ce21d6b3391d9e85e573aa860720c4b058ffc359a11eb51f395c2",
    ENV_COLLECTOR: "469020be3d53e9708d50e04b629c791582f80fb8dca6c8298c22ee5edf8cca8b",
    ENV_ADAPTER: "e596a5add9ee86198c651ef5e7a431d41c4e66bca7d3ebf49318e22021325489",
    ENV_OBSERVE_LEGACY: "eb90b9a94f706080311fe20a9549836c6b07e34d279fa4fad8d1dca89215751d",
}

EXIT_PASS = 0
EXIT_ASSERT_FAILED = 1
EXIT_BAD_CONFIG = 2
EXIT_BUSY = 3
EXIT_SKIP = 77

FALSE_FLAGS = {
    "pmAccepted": False,
    "orcaSupervised": False,
    "livenessAuthoritative": False,
}

READY = "READY_FOR_PM_REVIEW"
OBS_COLLECTOR_FAILED = "OBS_COLLECTOR_FAILED"
OBS_ADAPTER_FAILED = "OBS_ADAPTER_FAILED"

# 错峰：检测本波其他 test-zcode-gui-* 测试进程在飞时等待，有界。
PEER_TEST_PATTERN = re.compile(r"test-zcode-gui-[A-Za-z0-9._-]+\.py")
PEER_WAIT_MAX_SECONDS = 120
PEER_POLL_SECONDS = 5
SUBPROC_TIMEOUT_SECONDS = 60

# 合成标记：绝不允许出现在任何 observe 输出中。
CANARY_TOKEN = "zgui-smoke-canary-7f3a9c"
CANARY_SECRET = "synthetic-status-secret-do-not-echo"

SESSION_READY = "sess-ready"
INPUT_READY = "in-ready"
SESSION_RUNNING = "sess-running"
INPUT_RUNNING = "in-running"
SESSION_ERRFINAL = "sess-errfinal"
INPUT_ERRFINAL = "in-errfinal"
SESSION_STUB = "sess-stub"
INPUT_STUB = "in-stub"
INPUT_MISSING = "in-nope"

results = []


def record(group, name, passed, detail):
    results.append({"group": group, "name": name, "passed": bool(passed), "detail": detail})
    mark = "PASS" if passed else "FAIL"
    sys.stdout.write("[%s] %-4s %s — %s\n" % (mark, group, name, detail))
    sys.stdout.flush()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_peers_and_wait():
    """错峰：本波其他 test-zcode-gui-* 测试在飞时有界等待。"""
    deadline = time.time() + PEER_WAIT_MAX_SECONDS
    while time.time() < deadline:
        try:
            out = subprocess.run(
                ["ps", "-axo", "command="],
                capture_output=True, text=True, timeout=15,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return True  # 无法探测时不停摆，交由测试自身串行性保证
        peers = [
            line.strip() for line in out.splitlines()
            if PEER_TEST_PATTERN.search(line)
            and "consumer-smoke" not in line
            and "ps -axo" not in line
        ]
        if not peers:
            return True
        sys.stdout.write(
            "peak-avoid: %d peer test(s) in flight, retrying in %ds (bounded %ds)\n"
            % (len(peers), PEER_POLL_SECONDS, PEER_WAIT_MAX_SECONDS)
        )
        sys.stdout.flush()
        time.sleep(PEER_POLL_SECONDS)
    return False


def build_workspace(root):
    """合成 SQLite fixtures：completed / running / assistant-error / 坏 schema。"""
    def create_db(name, setup):
        path = os.path.join(root, name)
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                "CREATE TABLE session_input ("
                " id TEXT, session_id TEXT, status TEXT,"
                " status_reason TEXT, promoted_message_id TEXT)"
            )
            conn.execute(
                "CREATE TABLE turn_usage ("
                " session_id TEXT, turn_id TEXT, user_message_id TEXT, status TEXT,"
                " completed_at TEXT, error_type TEXT, cancelled_by_user INTEGER)"
            )
            conn.execute(
                "CREATE TABLE message ("
                " id TEXT, session_id TEXT, data TEXT, sequence REAL)"
            )
            if setup == "badschema":
                # 故意缺 part.data 列 → collector 必须报 DB_SCHEMA_INVALID。
                conn.execute(
                    "CREATE TABLE part ("
                    " id TEXT, message_id TEXT, session_id TEXT, sequence INTEGER)"
                )
            else:
                conn.execute(
                    "CREATE TABLE part ("
                    " id TEXT, message_id TEXT, session_id TEXT, data TEXT,"
                    " sequence INTEGER)"
                )
            if setup in ("ready", "running", "errfinal"):
                conn.execute(
                    "INSERT INTO session_input VALUES (?,?,?,?,?)",
                    (
                        {"ready": INPUT_READY, "running": INPUT_RUNNING,
                         "errfinal": INPUT_ERRFINAL}[setup],
                        {"ready": SESSION_READY, "running": SESSION_RUNNING,
                         "errfinal": SESSION_ERRFINAL}[setup],
                        "promoted",
                        CANARY_TOKEN + " reason-secret=" + CANARY_SECRET + " path=" + root,
                        "msg-u1",
                    ),
                )
                turn_status = {"ready": "completed", "running": "running",
                               "errfinal": "completed"}[setup]
                conn.execute(
                    "INSERT INTO turn_usage (session_id, turn_id, user_message_id,"
                    " status, completed_at, error_type, cancelled_by_user)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (
                        {"ready": SESSION_READY, "running": SESSION_RUNNING,
                         "errfinal": SESSION_ERRFINAL}[setup],
                        "turn-1",
                        "msg-u1",
                        turn_status,
                        "2026-10-03T00:00:05Z" if turn_status == "completed" else None,
                        None,
                        0,
                    ),
                )
                conn.execute(
                    "INSERT INTO message VALUES (?,?,?,?)",
                    ("msg-u1",
                     {"ready": SESSION_READY, "running": SESSION_RUNNING,
                      "errfinal": SESSION_ERRFINAL}[setup],
                     json.dumps({"role": "user", "parentID": None}), 1.0),
                )
            if setup in ("ready", "errfinal"):
                assistant_data = {
                    "role": "assistant",
                    "parentID": "msg-u1",
                    "time": {"completed": "2026-10-03T00:00:05Z"},
                    "providerId": "zcode-gui",
                    "modelId": "synthetic-model",
                    "mode": "gui",
                }
                if setup == "errfinal":
                    # 末条 assistant 携带错误：绝不允许被判定为 READY。
                    assistant_data["error"] = {"code": "synthetic-failure"}
                conn.execute(
                    "INSERT INTO message VALUES (?,?,?,?)",
                    ("msg-a1",
                     {"ready": SESSION_READY, "errfinal": SESSION_ERRFINAL}[setup],
                     json.dumps(assistant_data), 2.0),
                )
                conn.execute(
                    "INSERT INTO part VALUES (?,?,?,?,?)",
                    ("p1", "msg-a1",
                     {"ready": SESSION_READY, "errfinal": SESSION_ERRFINAL}[setup],
                     json.dumps({"type": "text", "text": "synthetic final answer"}), 1),
                )
            conn.commit()
        finally:
            conn.close()
        return path

    return {
        "ready": create_db("ready.db", "ready"),
        "running": create_db("running.db", "running"),
        "errfinal": create_db("errfinal.db", "errfinal"),
        "badschema": create_db("badschema.db", "badschema"),
    }


STUB_COLLECTOR_SOURCE = r"""#!/usr/bin/env python3
# 私有最小 stub：输出完全合法的 collector ok 元数据，但以 exit 9 退出。
import argparse, json, sys
parser = argparse.ArgumentParser()
parser.add_argument("--db", required=True)
parser.add_argument("--session-id", required=True)
parser.add_argument("--input-id", required=True)
parser.add_argument("--include-final-text", action="store_true")
args = parser.parse_args()
meta = {
    "ok": True, "schemaVersion": 1,
    "sessionId": args.session_id, "inputId": args.input_id,
    "input": {"status": "promoted", "reasonPresent": False,
              "promotedMessageId": "msg-u1"},
    "turn": {"found": True, "turnId": "turn-stub", "status": "completed"},
    "finalAssistant": {"found": True, "messageId": "msg-a1", "completed": True,
                       "errorFree": True, "textAvailable": True, "textLength": 21,
                       "providerId": "stub-provider", "modelId": "stub-model",
                       "mode": "gui"},
    "completionEvidence": {"turnCompleted": True, "finalAssistantCompleted": True,
                           "finalAssistantErrorFree": True,
                           "finalTextAvailable": True, "complete": True},
    "liveness": {"authoritative": False, "note": "stub"},
}
sys.stdout.write(json.dumps(meta, sort_keys=True) + "\n")
sys.stdout.flush()
sys.exit(9)
"""

STUB_ADAPTER_SOURCE = r"""#!/usr/bin/env python3
# 私有最小 stub：输出完全合法的 adapter READY 载荷，但以 exit 7 退出。
import argparse, hashlib, json, sys
parser = argparse.ArgumentParser()
parser.add_argument("--evidence", required=True)
parser.add_argument("--session-id", required=True)
parser.add_argument("--input-id", required=True)
parser.add_argument("--expected-evidence-sha256", default=None)
parser.add_argument("--expected-provider", default=None)
parser.add_argument("--expected-model", default=None)
args = parser.parse_args()
with open(args.evidence, "rb") as handle:
    raw = handle.read()
payload = {
    "adapter": "zcode-gui-monitor-adapter", "schemaVersion": 1,
    "sessionId": args.session_id, "inputId": args.input_id,
    "turnId": "turn-stub",
    "evidenceSha256": hashlib.sha256(raw).hexdigest(),
    "state": "READY_FOR_PM_REVIEW",
    "provider": "stub-provider", "model": "stub-model",
    "flags": {"pmAccepted": False, "orcaSupervised": False,
              "livenessAuthoritative": False},
}
sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
sys.stdout.flush()
sys.exit(7)
"""


def write_stubs(root):
    paths = {}
    for name, source in (
        ("stub-collector-exit9.py", STUB_COLLECTOR_SOURCE),
        ("stub-adapter-exit7.py", STUB_ADAPTER_SOURCE),
    ):
        path = os.path.join(root, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(source)
        paths[name] = path
    return paths


class Runner:
    """以消费者方式调用 observe：依赖只经环境变量接入，命令行只有三要素。"""

    def __init__(self, observe_path, collector_path, adapter_path):
        self.observe_path = observe_path
        self.collector_path = collector_path
        self.adapter_path = adapter_path
        self.outputs = []  # 有界留存：(case, stdout, stderr)

    def run(self, case, db_path, session_id, input_id,
            collector_override=None, adapter_override=None, observe_path=None):
        env = dict(os.environ)
        env[ENV_COLLECTOR] = collector_override or self.collector_path
        env[ENV_ADAPTER] = adapter_override or self.adapter_path
        argv = [
            sys.executable, observe_path or self.observe_path,
            "--db", db_path,
            "--session-id", session_id,
            "--input-id", input_id,
        ]
        proc = subprocess.run(
            argv, env=env, capture_output=True, text=True,
            timeout=SUBPROC_TIMEOUT_SECONDS,
        )
        self.outputs.append((case, proc.stdout or "", proc.stderr or ""))
        payload = None
        try:
            payload = json.loads(proc.stdout)
        except ValueError:
            payload = None
        return proc.returncode, payload, proc.stdout, proc.stderr

    def leak_scan(self, workspace):
        """CANARY / 秘密 / fixture 路径绝不出现在任何 observe stdout/stderr。"""
        needles = [CANARY_TOKEN, CANARY_SECRET, workspace]
        offenders = []
        for case, stdout, stderr in self.outputs:
            haystack = (stdout or "") + "\n" + (stderr or "")
            for needle in needles:
                if needle in haystack:
                    offenders.append("%s leaks %s" % (case, needle[:24]))
        return offenders


def flags_are_false(payload):
    return isinstance(payload.get("flags"), dict) and all(
        payload["flags"].get(key) is False for key in FALSE_FLAGS
    )


def main():
    sys.stdout.write("== %s ==\n" % SMOKE)
    values = {name: (os.environ.get(name) or "").strip() for name in EXPECTED_SHA256}

    configured = [name for name in (ENV_OBSERVE, ENV_COLLECTOR, ENV_ADAPTER) if values[name]]
    if not configured:
        sys.stdout.write(
            "SKIP: core dependencies not configured.\n"
            "  set %s / %s / %s to the frozen scripts and re-run.\n"
            % (ENV_OBSERVE, ENV_COLLECTOR, ENV_ADAPTER)
        )
        return EXIT_SKIP
    missing = [name for name in (ENV_OBSERVE, ENV_COLLECTOR, ENV_ADAPTER) if not values[name]]
    if missing:
        sys.stdout.write(
            "FAIL(config): partial dependency configuration; missing: %s\n"
            "  configure all of %s / %s / %s or none.\n"
            % (", ".join(missing), ENV_OBSERVE, ENV_COLLECTOR, ENV_ADAPTER)
        )
        return EXIT_BAD_CONFIG

    for name, path in values.items():
        if not path:
            continue
        if not os.path.isfile(path):
            sys.stdout.write(
                "FAIL(config): %s does not point to a regular file: %s\n" % (name, path)
            )
            return EXIT_BAD_CONFIG
        actual = sha256_file(path)
        if actual != EXPECTED_SHA256[name]:
            sys.stdout.write(
                "FAIL(config): %s fingerprint mismatch for %s\n"
                "  expected %s\n  actual   %s\n"
                "  regression verdicts are frozen to the pinned versions;\n"
                "  re-verify and update EXPECTED_SHA256 before migrating them.\n"
                % (name, path, EXPECTED_SHA256[name], actual)
            )
            return EXIT_BAD_CONFIG
    sys.stdout.write(
        "deps: observe/collector/adapter fingerprints match the frozen pins%s\n"
        % ("; legacy counterexample armed" if values[ENV_OBSERVE_LEGACY] else
           "; legacy counterexample DISABLED (NEG-L group will be skipped)")
    )

    if not check_peers_and_wait():
        sys.stdout.write(
            "FAIL(busy): peer test-zcode-gui-* tests still in flight after %ds; "
            "refusing to contend.\n" % PEER_WAIT_MAX_SECONDS
        )
        return EXIT_BUSY

    workspace = tempfile.mkdtemp(prefix="zgui-consumer-smoke-")
    legacy_available = bool(values[ENV_OBSERVE_LEGACY])
    exit_code = EXIT_PASS
    try:
        dbs = build_workspace(workspace)
        stubs = write_stubs(workspace)
        runner = Runner(values[ENV_OBSERVE], values[ENV_COLLECTOR], values[ENV_ADAPTER])

        # ---- POS 1: completed → READY + 恒假 flags --------------------------
        before = sha256_file(dbs["ready"])
        rc, payload, stdout, _ = runner.run(
            "pos1", dbs["ready"], SESSION_READY, INPUT_READY)
        after = sha256_file(dbs["ready"])
        ok1 = (
            rc == 0 and payload is not None
            and payload.get("status") == "OK"
            and payload.get("state") == READY
            and payload.get("error") is None
            and flags_are_false(payload)
            and isinstance(payload.get("summary"), dict)
            and payload["summary"].get("finalAssistantFound") is True
        )
        record("POS", "ready_completed_maps_to_ready_with_false_flags", ok1,
               "rc=%s state=%s" % (rc, payload.get("state") if payload else "<unparseable>"))

        # ---- POS 2: running → 非 READY --------------------------------------
        rc, payload, _, _ = runner.run(
            "pos2", dbs["running"], SESSION_RUNNING, INPUT_RUNNING)
        ok2 = (
            rc == 0 and payload is not None
            and payload.get("status") == "OK"
            and payload.get("state") == "TURN_RUNNING"
            and payload.get("state") != READY
            and flags_are_false(payload)
        )
        record("POS", "running_turn_is_not_ready", ok2,
               "rc=%s state=%s" % (rc, payload.get("state") if payload else "<unparseable>"))

        # ---- POS 3: 末条 assistant error → DELIVERY_ERROR，不误判 READY ----
        rc, payload, _, _ = runner.run(
            "pos3", dbs["errfinal"], SESSION_ERRFINAL, INPUT_ERRFINAL)
        ok3 = (
            rc == 0 and payload is not None
            and payload.get("status") == "OK"
            and payload.get("state") == "DELIVERY_ERROR"
            and payload.get("state") != READY
        )
        record("POS", "assistant_error_maps_to_delivery_error_not_ready", ok3,
               "rc=%s state=%s" % (rc, payload.get("state") if payload else "<unparseable>"))

        # ---- POS 4: 绑定错误 → 失败闭合 -------------------------------------
        rc, payload, _, _ = runner.run(
            "pos4", dbs["ready"], SESSION_READY, INPUT_MISSING)
        ok4 = (
            rc == 1 and payload is not None
            and payload.get("status") == "ERROR"
            and payload.get("state") is None
            and payload.get("error", {}).get("code") == "INPUT_NOT_FOUND"
            and flags_are_false(payload)
        )
        record("POS", "wrong_binding_fails_closed_with_input_not_found", ok4,
               "rc=%s code=%s" % (
                   rc,
                   payload.get("error", {}).get("code")
                   if isinstance(payload, dict) else "<unparseable>"))

        # ---- POS 5: 未知/缺列 schema → 失败闭合 -----------------------------
        rc, payload, _, _ = runner.run(
            "pos5", dbs["badschema"], SESSION_READY, INPUT_READY)
        ok5 = (
            rc == 1 and payload is not None
            and payload.get("status") == "ERROR"
            and payload.get("error", {}).get("code") == "DB_SCHEMA_INVALID"
        )
        record("POS", "unknown_schema_fails_closed_with_db_schema_invalid", ok5,
               "rc=%s code=%s" % (
                   rc,
                   payload.get("error", {}).get("code")
                   if isinstance(payload, dict) else "<unparseable>"))

        # ---- POS 6: 库文件 SHA 不变（只读保证） -----------------------------
        ok6 = (before == after and len(before) == 64)
        record("POS", "database_file_sha256_untouched_by_observation", ok6,
               "sha stable=%s (%s…)" % (before == after, before[:12]))

        # ---- NEG-C1: collector 合法 ok 但 exit 9 → 固定失败 -----------------
        rc, payload, _, _ = runner.run(
            "neg-c1", dbs["ready"], SESSION_STUB, INPUT_STUB,
            collector_override=stubs["stub-collector-exit9.py"])
        ok_c1 = (
            rc == 1 and payload is not None
            and payload.get("status") == "ERROR"
            and payload.get("state") is None
            and payload.get("error", {}).get("code") == OBS_COLLECTOR_FAILED
        )
        record("NEG-C", "candidate_rejects_collector_legal_ok_exit9", ok_c1,
               "rc=%s code=%s" % (
                   rc,
                   payload.get("error", {}).get("code")
                   if isinstance(payload, dict) else "<unparseable>"))

        # ---- NEG-C2: adapter 合法 READY 但 exit 7 → 固定失败 ----------------
        rc, payload, _, _ = runner.run(
            "neg-c2", dbs["ready"], SESSION_READY, INPUT_READY,
            adapter_override=stubs["stub-adapter-exit7.py"])
        ok_c2 = (
            rc == 1 and payload is not None
            and payload.get("status") == "ERROR"
            and payload.get("state") is None
            and payload.get("error", {}).get("code") == OBS_ADAPTER_FAILED
        )
        record("NEG-C", "candidate_rejects_adapter_legal_ready_exit7", ok_c2,
               "rc=%s code=%s" % (
                   rc,
                   payload.get("error", {}).get("code")
                   if isinstance(payload, dict) else "<unparseable>"))

        # ---- POS 7: CANARY / 秘密 / 路径绝不外泄 ----------------------------
        offenders = runner.leak_scan(workspace)
        record("POS", "synthetic_canary_secrets_and_paths_never_leak",
               not offenders,
               "scanned %d observation(s); offenders=%s"
               % (len(runner.outputs), offenders or "none"))

        # ---- NEG-L1/L2: 同一反例在旧稿必须不满足断言（负控） ----------------
        if legacy_available:
            rc_old, payload_old, _, _ = runner.run(
                "neg-l1", dbs["ready"], SESSION_STUB, INPUT_STUB,
                collector_override=stubs["stub-collector-exit9.py"],
                observe_path=values[ENV_OBSERVE_LEGACY])
            # 旧稿无 exit-code 门控：合法 ok + exit 9 仍应输出 OK（漏洞复现）。
            legacy_vulnerable_c = (rc_old == 0 and payload_old is not None
                                   and payload_old.get("status") == "OK")
            record("NEG-L", "legacy_observe_fails_collector_exit9_counterexample",
                   legacy_vulnerable_c,
                   "legacy rc=%s status=%s (vulnerable=%s; counterexample %s)"
                   % (rc_old,
                      payload_old.get("status") if payload_old else "<unparseable>",
                      legacy_vulnerable_c,
                      "confirmed" if legacy_vulnerable_c else "INVALID"))

            rc_old, payload_old, _, _ = runner.run(
                "neg-l2", dbs["ready"], SESSION_READY, INPUT_READY,
                adapter_override=stubs["stub-adapter-exit7.py"],
                observe_path=values[ENV_OBSERVE_LEGACY])
            legacy_vulnerable_a = (
                rc_old == 0 and payload_old is not None
                and payload_old.get("status") == "OK"
                and payload_old.get("state") == READY
            )
            record("NEG-L", "legacy_observe_fails_adapter_exit7_counterexample",
                   legacy_vulnerable_a,
                   "legacy rc=%s status=%s state=%s (vulnerable=%s)"
                   % (rc_old,
                      payload_old.get("status") if payload_old else "<unparseable>",
                      payload_old.get("state") if payload_old else "-",
                      legacy_vulnerable_a))
        else:
            record("NEG-L", "legacy_observe_fails_collector_exit9_counterexample",
                   True, "SKIP: %s not configured" % ENV_OBSERVE_LEGACY)
            record("NEG-L", "legacy_observe_fails_adapter_exit7_counterexample",
                   True, "SKIP: %s not configured" % ENV_OBSERVE_LEGACY)

        # ---- 汇总 ------------------------------------------------------------
        pos = [r for r in results if r["group"] == "POS"]
        neg_c = [r for r in results if r["group"] == "NEG-C"]
        neg_l_ran = [r for r in results if r["group"] == "NEG-L"
                     and not r["detail"].startswith("SKIP")]
        hard = pos + neg_c + neg_l_ran
        failed = [r for r in hard if not r["passed"]]
        skipped = [r for r in results if r["detail"].startswith("SKIP")]

        sys.stdout.write(
            "== summary ==\n"
            "total=%d pass=%d fail=%d skip=%d (POS %d, NEG-C %d, NEG-L ran %d)\n"
            % (len(results), len(hard) - len(failed), len(failed), len(skipped),
               len(pos), len(neg_c), len(neg_l_ran))
        )
        for item in results:
            sys.stdout.write("  %-5s %-4s %s\n" % (
                "PASS" if item["passed"] else "FAIL",
                item["group"], item["name"]))
        if failed:
            exit_code = EXIT_ASSERT_FAILED
            sys.stdout.write("verdict: FAIL — %d assertion(s) failed\n" % len(failed))
        else:
            sys.stdout.write(
                "verdict: PASS — consumer contract holds%s\n"
                % (" (legacy counterexamples not run)" if not neg_l_ran else
                   " (legacy counterexamples confirmed)")
            )
        sys.stdout.flush()
        return exit_code
    except Exception as exc:  # 环境性意外（含超时/IO）：有界披露，不吐堆栈
        sys.stdout.write("FAIL(error): %s: %s\n"
                         % (type(exc).__name__, str(exc)[:200]))
        return EXIT_ASSERT_FAILED
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(EXIT_ASSERT_FAILED)
    except KeyboardInterrupt:
        sys.exit(EXIT_ASSERT_FAILED)
