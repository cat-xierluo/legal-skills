#!/usr/bin/env python3
"""Build a synthetic, offline multi-Runtime demo for the teaching session.

Runs the real public workflow CLI inside a throwaway data root and a synthetic
HOME. Nothing here touches the real ledger, the real session stores, the network
or a model: it only writes JSONL/JSON fixtures and invokes
scripts/public_workflow.py with SELF_EVOLVE_DATA_ROOT pointed at a temp dir.
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import shutil
import subprocess
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
WORKFLOW = SCRIPTS / "public_workflow.py"
ANALYSIS_SCHEMA = "self-evolve-agent-analysis-v1"

CLAUDE_TEXT = "复盘这个验证流程，应该沉淀可复用检查清单和验收边界。以后按这个模板执行。"
CODEX_TEXT = "把发布前的回归拆成固定步骤，先跑单元测试，再核对发行包清单和验收口径。"
WORKBUDDY_TEXT = "跨 runtime 汇总时要注意去重口径，重复副本不能算成两个独立会话；复盘后沉淀检查清单。"
CODEBUDDY_TEXT = "整理失败分类的说明，沉淀成验收边界，让报告里能看到读取失败和格式未接入。"
GEMINI_TEXT = "把演示用的合成数据准备好，沉淀成可复用的模板，课堂上一轮扫描就能看到增量效果。"
ZCODE_TEXT = "索引摘录没有角色边界，展示时必须说明它不是完整对话记录，复盘时沉淀为验收边界。"


def _write(path: Path, lines) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in lines) + "\n", encoding="utf-8")
    return path


def claude_session(home: Path, name: str, sid: str, text: str) -> Path:
    return _write(home / ".claude" / "projects" / f"{name}.jsonl", [
        {"type": "user", "sessionId": sid, "message": {"role": "user", "content": text}},
        {"type": "assistant", "sessionId": sid, "message": {"role": "assistant", "content": "确定采用分层验证：先检查输入，再核真实产物。"}},
    ])


def codex_session(home: Path, sid: str, text: str) -> Path:
    return _write(home / ".codex" / "sessions" / f"{sid}.jsonl", [
        {"type": "session_meta", "payload": {"id": sid}},
        {"type": "event_msg", "payload": {"type": "user_message", "message": text}},
        {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                                              "content": [{"type": "output_text", "text": "回归步骤已固定。"}]}},
    ])


def workbuddy_trace(home: Path, sid: str, text: str) -> Path:
    messages = [{"role": "user", "content": "<user_query>" + text + "</user_query>"}]
    trace = {"trace": {"sessionId": sid},
             "spans": [{"name": "generation", "startedAt": "2026-10-21T02:00:00Z",
                        "toolInput": json.dumps(messages),
                        "toolOutput": json.dumps({"choices": [{"message": {"content": "去重口径已写明。"}}]})}]}
    path = home / ".workbuddy" / "traces" / "trace-wb" / "trace_a.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trace, ensure_ascii=False), encoding="utf-8")
    return path


def workbuddy_session(home: Path, sid: str, text: str) -> Path:
    # Top-level role dialect: type=message + role + content, plus a tool row
    # that carries message={usage}. This is the real on-disk shape.
    return _write(home / ".workbuddy" / "projects" / f"{sid}.jsonl", [
        {"type": "message", "role": "user", "sessionId": sid,
         "content": [{"type": "input_text", "text": text}]},
        {"type": "function_call", "role": "assistant", "sessionId": sid, "name": "read_file",
         "arguments": "{}", "message": {"usage": {"input_tokens": 1}}},
        {"type": "message", "role": "assistant", "sessionId": sid,
         "content": [{"type": "output_text", "text": "去重口径已写明。"}]},
    ])


def codebuddy_session(home: Path, sid: str, text: str) -> Path:
    # Same top-level role dialect as WorkBuddy.
    return _write(home / ".codebuddy" / "projects" / f"{sid}.jsonl", [
        {"type": "message", "role": "user", "sessionId": sid,
         "content": [{"type": "input_text", "text": text}]},
        {"type": "message", "role": "assistant", "sessionId": sid,
         "content": [{"type": "output_text", "text": "失败分类已补充。"}]},
    ])


def gemini_session(home: Path, sid: str, text: str) -> Path:
    path = home / ".gemini" / "tmp" / "p1" / "chats" / f"{sid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"sessionId": sid, "messages": [
        {"type": "user", "content": text},
        {"type": "gemini", "content": "合成数据就绪。"},
    ]}, ensure_ascii=False), encoding="utf-8")
    return path


def zcode_index(home: Path, sid: str, text: str) -> Path:
    db = home / ".zcode" / "v2" / "tasks-index.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db)) as conn:
        conn.execute("create table tasks(workspace_key text,task_id text,title text,"
                     "searchable_text text,updated_at integer,deleted integer)")
        conn.execute("insert into tasks values(?,?,?,?,?,0)", ("ws", sid, "合成任务", text, 1))
        conn.commit()
    return db


def unsupported_runtime(home: Path) -> Path:
    path = home / ".qwen"
    path.mkdir(parents=True, exist_ok=True)
    (path / "sessions").mkdir()
    return path


def build_fixtures(home: Path) -> dict[str, Path]:
    return {
        "claude": claude_session(home, "demo-claude", "demo-claude", CLAUDE_TEXT),
        "codex": codex_session(home, "demo-codex", CODEX_TEXT),
        "workbuddy": workbuddy_session(home, "demo-wb", WORKBUDDY_TEXT),
        "workbuddy-trace": workbuddy_trace(home, "demo-wb-trace", WORKBUDDY_TEXT),
        "codebuddy": codebuddy_session(home, "demo-codebuddy", CODEBUDDY_TEXT),
        "gemini": gemini_session(home, "session-demo", GEMINI_TEXT),
        "zcode": zcode_index(home, "demo-zcode", ZCODE_TEXT),
        "unsupported": unsupported_runtime(home),
    }


def broken_fixture(home: Path) -> Path:
    """A structurally valid JSONL whose schema the adapters do not recognize."""
    return _write(home / ".claude" / "projects" / "demo-broken.jsonl", [
        {"kind": "unknown-wrapper", "blob": "not a conversation"},
    ])


def unknown_payload_fixture(home: Path) -> Path:
    """A recognized message row whose content shape the extractor cannot read."""
    return _write(home / ".claude" / "projects" / "demo-unknown-payload.jsonl", [
        {"type": "user", "message": {"role": "user", "content": {"media": "image/png"}}},
    ])


def run_cli(root: Path, home: Path, *args: str) -> dict:
    env = dict(os.environ)
    env["SELF_EVOLVE_DATA_ROOT"] = str(root)
    env["HOME"] = str(home)
    for key in ("CODEX_HOME", "ZCODE_DATA_BASE_DIR", "SELF_EVOLVE_SKILL_ROOT",
                "SKILL_EVOLVE_SKILL_ROOT", "SELF_EVOLVE_RUNTIME_ROOT",
                "SELF_EVOLVE_STATE_ROOT", "SKILL_EVOLVE_STATE_ROOT", "SELF_EVOLVE_REVIEW_ROOT"):
        env.pop(key, None)
    proc = subprocess.run([sys.executable, str(WORKFLOW), *args],
                          capture_output=True, text=True, cwd=str(SCRIPTS.parent), env=env)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise SystemExit(f"CLI 无 JSON 输出 (rc={proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
    if proc.returncode not in (0, 1):
        raise SystemExit(f"演示命令失败 (rc={proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
    payload["_returncode"] = proc.returncode
    payload["_stderr"] = proc.stderr.strip()
    return payload


def analysis_from(packet: dict) -> dict:
    ids = [e["evidence_id"] for e in packet["evidence"]]
    return {
        "schema_version": ANALYSIS_SCHEMA,
        "packet_digest": packet["packet_digest"],
        "overview": "合成数据里可复用的是增量账本口径和失败可见性；跨 Runtime 规律仍受样本量限制。",
        "patterns": [{
            "title": "同一事实只在账本里记一次",
            "explanation": "多 Runtime 混合扫描时，去重按会话语义哈希合并，副本不增加独立会话数。",
            "evidence_ids": ids[:1],
            "next_step": "在讲义里用 cumulative.duplicate_views 解释副本计数。",
        }],
        "skill_proposals": [{
            "title": "增量信息挖掘课堂讲义",
            "action": "create",
            "target_skill": "teaching-incremental-mining",
            "rationale": "课堂需要一份可核对的演示流程，而不是口头描述。",
            "change_points": ["把 scan / import-analysis / status 三个入口写成可照抄的命令。"],
            "evidence_ids": ids[:1],
        }],
        'evidence_dispositions': [
            {'evidence_id': eid, 'disposition': 'analyzed',
             'note': '演示用合成证据：已在讲稿中引用。'}
            for eid in ids
        ],
    }


def summarize(result: dict, packet_path: str, label: str) -> dict:
    packet = json.loads(Path(packet_path).read_text(encoding="utf-8"))
    stats = packet["stats"]
    return {
        "label": label,
        "run_id": result.get("run_id"),
        "status": result.get("status"),
        "returncode": result["_returncode"],
        "stats": stats,
        "pending_analysis": result.get("pending_analysis"),
        "analysis_status": packet.get("analysis_status"),
        "runtimes_with_evidence": sorted({e["runtime"] for e in packet["evidence"]}),
        "coverage": [{"runtime": c["runtime"], "status": c["status"], "discovered": c["discovered"],
                      "errors": c["errors"]} for c in packet["coverage"] if c["status"] != "not_found"],
        "failures": packet.get("failures", []),
        "cumulative": packet.get("cumulative"),
        "report_pages": result.get("report_pages"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="保留临时目录，便于课堂现场打开报告")
    parser.add_argument("--rounds", type=int, default=2, help="扫描轮数（默认 2：首轮 + 增量未变）")
    args = parser.parse_args()

    base = Path(tempfile.mkdtemp(prefix="self-evolve-teaching-"))
    home = base / "home"
    root = base / "state"
    home.mkdir()
    root.mkdir()
    try:
        fixtures = build_fixtures(home)
        broken_fixture(home)
        unknown_payload_fixture(home)

        print("== 合成数据根 ==")
        print(json.dumps({"home": str(home), "state_root": str(root)}, ensure_ascii=False, indent=2))
        print("== 合成会话文件 ==")
        for name, path in fixtures.items():
            print(f"  {name:12s} {path.relative_to(home)}")

        # Round 1 uses a budget that lets every synthetic runtime appear, so the
        # classroom sees the multi-runtime coverage story.
        first = run_cli(root, home, "scan", "--home", str(home), "--max-sessions", "50")
        first_packet = first["packet"]
        print("\n== 第 1 轮 scan（预算 50：多 Runtime 汇总） ==")
        print(json.dumps(summarize(first, first_packet, "round-1"), ensure_ascii=False, indent=2))

        packet = json.loads(Path(first_packet).read_text(encoding="utf-8"))
        if not packet["evidence"]:
            print("\n[警告] 首轮没有送审证据，检查合成文本是否被初筛过滤。")
        analysis_path = base / "analysis.json"
        analysis_path.write_text(json.dumps(analysis_from(packet), ensure_ascii=False, indent=2), encoding="utf-8")
        imported = run_cli(root, home, "import-analysis", "--packet", first_packet,
                           "--analysis", str(analysis_path))
        print("\n== import-analysis ==")
        print(json.dumps({k: v for k, v in imported.items() if not k.startswith("_")},
                         ensure_ascii=False, indent=2))

        for round_no in range(2, args.rounds + 1):
            # A tight budget in round 2 shows pending_budget; the same run also
            # shows unchanged skipping for everything already processed.
            again = run_cli(root, home, "scan", "--home", str(home), "--max-sessions", "2")
            print(f"\n== 第 {round_no} 轮 scan（同一数据根，未改任何会话文件） ==")
            print(json.dumps(summarize(again, again["packet"], f"round-{round_no}"), ensure_ascii=False, indent=2))

        print("\n== status ==")
        print(json.dumps({k: v for k, v in run_cli(root, home, "status").items() if not k.startswith("_")},
                         ensure_ascii=False, indent=2))
        print("\n报告目录（七页同前缀，一起复制）：")
        print(Path(first_packet).parent)
        if args.keep:
            print("\n--keep：临时目录保留在 " + str(base))
        return 0
    finally:
        if not args.keep:
            shutil.rmtree(base)


if __name__ == "__main__":
    raise SystemExit(main())
