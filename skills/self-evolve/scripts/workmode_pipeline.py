#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""工作模式偏好:提炼 + 分析 + 入账(低频、幂等)。

照搬 info-evaluator preference_pipeline 的幂等架构:
  - source_digest 相同且上次分析 available → unchanged 短路(零模型调用)
  - pipeline.lock 互斥(LOCK_EX|LOCK_NB),重叠运行直接 already_running

与 preference_pipeline 的差别:extract 是同包直调(workmode_extract.extract,不
subprocess 跨 skill);分析调 workmode_ledger.analyze_packet(SiliconFlow DeepSeek-V3.2,
enable_thinking=False,temperature 0.0)。
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from self_evolve_paths import RUNTIME_ROOT  # noqa: E402
from workmode_ledger import (  # noqa: E402
    MODEL,
    WorkmodeLedger,
    analyze_packet,
    load_evidence_packet,
)
from workmode_extract import extract as extract_packet, DEFAULT_PACKET  # noqa: E402

DEFAULT_RUNTIME_DIR = RUNTIME_ROOT / "workmode-preference"
DEFAULT_STATUS = DEFAULT_RUNTIME_DIR / "pipeline-status.json"
DEFAULT_LOCK = DEFAULT_RUNTIME_DIR / "pipeline.lock"
STATUS_SCHEMA = "workmode-pipeline-status-v1"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        Path(temp_name).replace(path)
    finally:
        try:
            Path(temp_name).unlink()
        except FileNotFoundError:
            pass


def read_status(path: Path = DEFAULT_STATUS) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "never_run", "model": MODEL}
    return payload if isinstance(payload, dict) else {"status": "unreadable", "model": MODEL}


def _pipeline_result(
    *,
    status: str,
    started_at: str,
    packet: dict[str, Any] | None,
    ledger_status: dict[str, Any],
    model: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "schema_version": STATUS_SCHEMA,
        "status": status,
        "started_at": started_at,
        "finished_at": now_iso(),
        "model": model,
        "source_digest": packet.get("source_digest") if packet else None,
        "cluster_count": len(packet.get("clusters", [])) if packet else 0,
        "candidate_count": ledger_status.get("candidate_count", 0),
        "candidate_counts": ledger_status.get("counts", {}),
    }
    if details:
        result.update(details)
    return result


def run_loaded_packet(
    packet: dict[str, Any],
    *,
    model: str = MODEL,
    force: bool = False,
    response_text: str | None = None,
    ledger: WorkmodeLedger | None = None,
) -> tuple[dict[str, Any], int]:
    started_at = now_iso()
    store = ledger or WorkmodeLedger()
    before = store.status()
    if not packet["clusters"]:
        return (
            _pipeline_result(
                status="no_evidence",
                started_at=started_at,
                packet=packet,
                ledger_status=before,
                model=model,
            ),
            0,
        )
    last_analysis = before.get("last_analysis") or {}
    if (
        not force
        and last_analysis.get("source_digest") == packet.get("source_digest")
        and last_analysis.get("analysis_status") == "available"
    ):
        return (
            _pipeline_result(
                status="unchanged",
                started_at=started_at,
                packet=packet,
                ledger_status=before,
                model=model,
            ),
            0,
        )
    analysis = analyze_packet(packet, model=model, response_text=response_text)
    imported = store.import_analysis(analysis)
    after = store.status()
    status = str(analysis.get("analysis_status", "analysis_unavailable"))
    return (
        _pipeline_result(
            status=status,
            started_at=started_at,
            packet=packet,
            ledger_status=after,
            model=model,
            details={
                "imported": imported.get("imported", 0),
                "revised": imported.get("revised", 0),
                "analysis_candidate_count": len(analysis.get("candidates", [])),
                "filtered_candidate_count": len(analysis.get("filtered", [])),
                "issues": analysis.get("issues", []),
            },
        ),
        0,  # extract 已成功;分析降级(analysis_unavailable,如未配 key)不算失败,真异常由 main 的 except 捕获返回 1
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="工作模式偏好:提炼 + 分析 + 入账(幂等)")
    parser.add_argument("--since", default="14d", help="extract 时间窗(默认 14d)")
    parser.add_argument("--packet", type=Path, help="使用指定证据包;默认现 extract")
    parser.add_argument("--output-packet", type=Path, default=DEFAULT_PACKET, help="extract 产物落盘路径")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--force", action="store_true", help="证据摘要未变也重新分析")
    parser.add_argument("--response-file", type=Path, help="固定响应离线回放,不调模型")
    parser.add_argument("--status-only", action="store_true")
    parser.add_argument("--status-path", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--lock-path", type=Path, default=DEFAULT_LOCK)
    args = parser.parse_args(argv)
    if args.status_only:
        print(json.dumps(read_status(args.status_path), ensure_ascii=False))
        return 0

    args.lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = args.lock_path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            result = {"schema_version": STATUS_SCHEMA, "status": "already_running", "model": args.model}
            print(json.dumps(result, ensure_ascii=False))
            return 0
        started_at = now_iso()
        atomic_json(
            args.status_path,
            {
                "schema_version": STATUS_SCHEMA,
                "status": "running",
                "started_at": started_at,
                "finished_at": None,
                "model": args.model,
            },
        )
        # ① 提炼:同包直调 workmode_extract.extract,或读指定 packet
        if args.packet:
            packet = load_evidence_packet(args.packet)
        else:
            packet = extract_packet(args.since)
            atomic_json(args.output_packet, packet)  # 落盘供离线回放 / 审计
        response_text = (
            args.response_file.read_text(encoding="utf-8") if args.response_file else None
        )
        result, returncode = run_loaded_packet(
            packet, model=args.model, force=args.force, response_text=response_text
        )
        atomic_json(args.status_path, result)
        print(json.dumps(result, ensure_ascii=False))
        return returncode
    except Exception as exc:
        result = {
            "schema_version": STATUS_SCHEMA,
            "status": "error",
            "started_at": locals().get("started_at", now_iso()),
            "finished_at": now_iso(),
            "model": args.model,
            "error_type": type(exc).__name__,
        }
        atomic_json(args.status_path, result)
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        finally:
            lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
