#!/usr/bin/env python3
"""zcode-gui-monitor-adapter.py 的离线契约自测：固定监控状态与完成待审门。

全部用例通过真实 CLI 驱动，零网络、零外部副作用（临时目录自包含 fixture）。
覆盖：

  - 固定状态全量映射：INPUT_ACCEPTED / INPUT_FAILED、TURN_UNKNOWN /
    TURN_RUNNING / TURN_ERROR / TURN_CANCELLED、DELIVERY_PENDING /
    DELIVERY_ERROR、READY_FOR_PM_REVIEW、EVIDENCE_CONFLICT；
  - 采集器合法 nullable 形态：无 turn 时 {found:false,turnId:null,status:null}
    可达 INPUT_ACCEPTED / TURN_UNKNOWN；非 null 非字符串才类型拒绝；
  - completionEvidence 双向一致：过度声明与欠声明（任一方向矛盾）均
    EVIDENCE_CONFLICT；READY 需显式 complete=true，缺项保持未知不补全；
  - input/turn 矛盾：admitted/failed 携带 concrete turn/final → 冲突；
    input 缺失/unknown 即使观测全 true 也只 TURN_UNKNOWN，不得 READY；
  - fail-closed 校验：坏 UTF-8/JSON/schema/类型、绑定不一致、摘要不匹配、
    期待 provider/model 不一致（缺失不回落）、缺文件不创建、超 1MiB；
  - 泄露防线、只读不变（摘要一致、内容与目录条目不变）；
  - 真实采集样例：仅当环境变量 ZCODE_GUI_MONITOR_REAL_EVIDENCE /
    _REAL_SESSION / _REAL_INPUT 提供且文件存在时运行，否则明确 SKIP，
    默认前置不绑定任何远端路径或真实会话。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "zcode-gui-monitor-adapter.py"

REAL_EVIDENCE = os.environ.get("ZCODE_GUI_MONITOR_REAL_EVIDENCE", "")
REAL_SESSION = os.environ.get("ZCODE_GUI_MONITOR_REAL_SESSION", "")
REAL_INPUT = os.environ.get("ZCODE_GUI_MONITOR_REAL_INPUT", "")
REAL_SHA256 = os.environ.get("ZCODE_GUI_MONITOR_REAL_SHA256", "")
REAL_PROVIDER = os.environ.get("ZCODE_GUI_MONITOR_REAL_PROVIDER", "")
REAL_MODEL = os.environ.get("ZCODE_GUI_MONITOR_REAL_MODEL", "")

FIXTURE_SESSION = "sess_fixture"
FIXTURE_INPUT = "input_fixture"
FIXTURE_PROVIDER = "account:bigmodel-start-plan"
FIXTURE_MODEL = "GLM-5.3-Flash"

SUCCESS_KEYS = {
    "adapter",
    "schemaVersion",
    "sessionId",
    "inputId",
    "turnId",
    "evidenceSha256",
    "state",
    "provider",
    "model",
    "flags",
}
ERROR_KEYS = {"adapter", "schemaVersion", "error", "flags"}
FALSE_FLAGS = {"pmAccepted": False, "orcaSupervised": False, "livenessAuthoritative": False}

# 采集器真实无 turn 形态（PR250-R2）：found:false + null 字段。
NO_TURN_COLLECTOR = {"found": False, "turnId": None, "status": None}
FULL_FINAL = {
    "found": True,
    "completed": True,
    "errorFree": True,
    "textAvailable": True,
    "providerId": FIXTURE_PROVIDER,
    "modelId": FIXTURE_MODEL,
    "messageId": "msg_final",
    "textLength": 42,
    "mode": "yolo",
}
FULL_COMPLETION = {
    "complete": True,
    "turnCompleted": True,
    "finalAssistantCompleted": True,
    "finalAssistantErrorFree": True,
    "finalTextAvailable": True,
}
CLEAN_COMPLETION = {
    "complete": False,
    "turnCompleted": False,
    "finalAssistantCompleted": False,
    "finalAssistantErrorFree": False,
    "finalTextAvailable": False,
}

passed = 0
failed = 0


def check(label, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print(f"FAIL {label}: {detail}")


def ready_payload():
    return {
        "schemaVersion": 1,
        "sessionId": FIXTURE_SESSION,
        "inputId": FIXTURE_INPUT,
        "input": {"status": "promoted", "promotedMessageId": "msg_promoted"},
        "turn": {"found": True, "status": "completed", "turnId": "turn_fixture"},
        "finalAssistant": dict(FULL_FINAL),
        "completionEvidence": dict(FULL_COMPLETION),
        "liveness": {
            "authoritative": False,
            "note": "Cold read-only snapshot; missing fields are never inferred.",
        },
        "ok": True,
    }


def collector_admitted():
    """采集器真实合法快照：admitted 且尚无 turn（null 字段为合法默认值）。"""
    return {
        "schemaVersion": 1,
        "sessionId": FIXTURE_SESSION,
        "inputId": FIXTURE_INPUT,
        "input": {"status": "admitted"},
        "turn": dict(NO_TURN_COLLECTOR),
        "liveness": {"authoritative": False},
        "ok": True,
    }


def turn_state_payload(status):
    """turn 未完成时的真实快照形态：无最终 assistant，ce 全 false。"""
    payload = ready_payload()
    payload["turn"] = {"found": True, "status": status, "turnId": "turn_fixture"}
    payload.pop("finalAssistant")
    payload["completionEvidence"] = dict(CLEAN_COMPLETION)
    return payload


def write_fixture(root, payload, name="evidence.json"):
    path = root / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def run_adapter(evidence, session=FIXTURE_SESSION, input_id=FIXTURE_INPUT, extra=()):
    argv = [
        sys.executable,
        str(SCRIPT),
        "--evidence",
        str(evidence),
        "--session-id",
        session,
        "--input-id",
        input_id,
        *extra,
    ]
    return subprocess.run(argv, capture_output=True, text=True, timeout=60)


def parse_json_output(label, proc):
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        check(f"{label}: 输出为单行 JSON", False, f"{exc}: {proc.stdout[:200]!r}")
        return None


def expect_success(label, proc, state):
    check(f"{label}: exit 0", proc.returncode == 0, proc.returncode)
    check(f"{label}: 无 traceback", "Traceback" not in proc.stdout + proc.stderr)
    payload = parse_json_output(label, proc)
    if payload is None:
        return None
    check(f"{label}: 输出键固定", set(payload) == SUCCESS_KEYS, sorted(set(payload)))
    check(f"{label}: flags 恒 false", payload.get("flags") == FALSE_FLAGS, payload.get("flags"))
    check(f"{label}: state={state}", payload.get("state") == state, payload.get("state"))
    return payload


def expect_error(label, proc, code, secret_strings=()):
    check(f"{label}: nonzero", proc.returncode != 0, proc.returncode)
    check(f"{label}: exit 2", proc.returncode == 2, proc.returncode)
    check(f"{label}: 无 traceback", "Traceback" not in proc.stdout + proc.stderr)
    payload = parse_json_output(label, proc)
    if payload is not None:
        check(f"{label}: 错误键固定", set(payload) == ERROR_KEYS, sorted(set(payload)))
        check(f"{label}: error={code}", payload.get("error") == code, payload.get("error"))
        check(f"{label}: flags 恒 false", payload.get("flags") == FALSE_FLAGS, payload.get("flags"))
    blob = proc.stdout + proc.stderr
    for secret in secret_strings:
        check(f"{label}: 不泄露 {secret[:24]!r}", secret not in blob)


def main():
    with tempfile.TemporaryDirectory(prefix="zcode-gui-monitor-adapter-test-") as tmp:
        root = Path(tmp)

        # --- READY_FOR_PM_REVIEW 与输出契约 ---
        path = write_fixture(root, ready_payload())
        result = expect_success("ready", run_adapter(path), "READY_FOR_PM_REVIEW")
        if result:
            check(
                "ready: 绑定IDs回显",
                result["sessionId"] == FIXTURE_SESSION and result["inputId"] == FIXTURE_INPUT,
            )
            check("ready: turnId回显", result["turnId"] == "turn_fixture")
            check("ready: 摘要64hex", len(result["evidenceSha256"]) == 64)
            check(
                "ready: provider/model回显",
                result["provider"] == FIXTURE_PROVIDER and result["model"] == FIXTURE_MODEL,
            )
            check("ready: 未知字段丢弃", "liveness" not in result and "ok" not in result)

        # READY 需显式 complete=true：缺项/null 保持未知不补全 → DELIVERY_PENDING
        missing_complete = ready_payload()
        missing_complete["completionEvidence"].pop("complete")
        path = write_fixture(root, missing_complete, "missing-complete.json")
        expect_success("complete缺失不补全", run_adapter(path), "DELIVERY_PENDING")

        null_complete = ready_payload()
        null_complete["completionEvidence"]["complete"] = None
        path = write_fixture(root, null_complete, "null-complete.json")
        expect_success("complete=null不补全", run_adapter(path), "DELIVERY_PENDING")

        # --- 采集器合法 nullable 形态（F3 回归）---
        path = write_fixture(root, collector_admitted(), "collector-admitted.json")
        result = expect_success("采集器admitted无turn", run_adapter(path), "INPUT_ACCEPTED")
        if result:
            check("采集器admitted: turnId=null", result["turnId"] is None, result["turnId"])

        promoted_no_turn = collector_admitted()
        promoted_no_turn["input"] = {"status": "promoted"}
        path = write_fixture(root, promoted_no_turn, "collector-promoted.json")
        expect_success("采集器promoted无turn", run_adapter(path), "TURN_UNKNOWN")

        found_no_status = ready_payload()
        found_no_status["turn"] = {"found": True, "status": None, "turnId": None}
        found_no_status.pop("finalAssistant")
        found_no_status["completionEvidence"] = dict(CLEAN_COMPLETION)
        path = write_fixture(root, found_no_status, "found-null-status.json")
        expect_success("found=true但status=null", run_adapter(path), "TURN_UNKNOWN")

        # --- 输入两态（无 concrete turn 时正常映射）---
        failed_no_turn = collector_admitted()
        failed_no_turn["input"] = {"status": "failed"}
        path = write_fixture(root, failed_no_turn, "failed-no-turn.json")
        expect_success("failed无concrete turn", run_adapter(path), "INPUT_FAILED")

        # --- input/turn 矛盾（F1 回归）：已证非 promoted 携带 concrete turn/final ---
        admitted_turn = ready_payload()
        admitted_turn["input"] = {"status": "admitted"}
        path = write_fixture(root, admitted_turn, "admitted-turn.json")
        expect_success("admitted+completed turn", run_adapter(path), "EVIDENCE_CONFLICT")

        failed_turn = ready_payload()
        failed_turn["input"] = {"status": "failed"}
        path = write_fixture(root, failed_turn, "failed-turn.json")
        expect_success("failed+completed turn", run_adapter(path), "EVIDENCE_CONFLICT")

        admitted_final = collector_admitted()
        admitted_final["finalAssistant"] = dict(FULL_FINAL)
        path = write_fixture(root, admitted_final, "admitted-final.json")
        expect_success("admitted+concrete final", run_adapter(path), "EVIDENCE_CONFLICT")

        failed_final = collector_admitted()
        failed_final["input"] = {"status": "failed"}
        failed_final["finalAssistant"] = dict(FULL_FINAL)
        path = write_fixture(root, failed_final, "failed-final.json")
        expect_success("failed+concrete final", run_adapter(path), "EVIDENCE_CONFLICT")

        # --- input 缺失/unknown（N3 回归）：即使观测全 true 也不得 READY ---
        missing_input = ready_payload()
        missing_input.pop("input")
        path = write_fixture(root, missing_input, "missing-input.json")
        expect_success("input缺失+completed turn", run_adapter(path), "TURN_UNKNOWN")

        unknown_input = ready_payload()
        unknown_input["input"] = {"status": "queued"}
        path = write_fixture(root, unknown_input, "unknown-input.json")
        expect_success("input未知值+completed turn", run_adapter(path), "TURN_UNKNOWN")

        null_input = ready_payload()
        null_input["input"] = {"status": None}
        path = write_fixture(root, null_input, "null-input.json")
        expect_success("input=null+completed turn", run_adapter(path), "TURN_UNKNOWN")

        # --- promoted 后的 turn 各态（ce clean，正常进行中快照不误拒）---
        path = write_fixture(root, turn_state_payload("running"), "running.json")
        result = expect_success("running", run_adapter(path), "TURN_RUNNING")
        if result:
            check(
                "running: ce全false不误拒冲突",
                result["state"] == "TURN_RUNNING",
                result["state"],
            )
        path = write_fixture(root, turn_state_payload("cancelled"), "cancelled.json")
        expect_success("cancelled", run_adapter(path), "TURN_CANCELLED")
        path = write_fixture(root, turn_state_payload("queued"), "queued.json")
        expect_success("未知turn保留UNKNOWN", run_adapter(path), "TURN_UNKNOWN")

        old_success = turn_state_payload("error")
        old_success["finalAssistant"] = dict(FULL_FINAL)
        old_success["completionEvidence"].update(
            {
                "finalAssistantCompleted": True,
                "finalAssistantErrorFree": True,
                "finalTextAvailable": True,
            }
        )
        path = write_fixture(root, old_success, "old-success.json")
        expect_success("旧成功不掩盖最新error", run_adapter(path), "TURN_ERROR")

        # --- 交付三态 ---
        pending = ready_payload()
        del pending["finalAssistant"]["textAvailable"]
        pending["completionEvidence"]["complete"] = False
        pending["completionEvidence"]["finalTextAvailable"] = False
        path = write_fixture(root, pending, "pending.json")
        expect_success("final不全", run_adapter(path), "DELIVERY_PENDING")

        no_final = ready_payload()
        no_final.pop("finalAssistant")
        no_final["completionEvidence"] = dict(CLEAN_COMPLETION)
        no_final["completionEvidence"]["turnCompleted"] = True
        path = write_fixture(root, no_final, "no-final.json")
        expect_success("无final", run_adapter(path), "DELIVERY_PENDING")

        not_found = ready_payload()
        not_found["finalAssistant"] = {"found": False}
        not_found["completionEvidence"] = dict(CLEAN_COMPLETION)
        not_found["completionEvidence"]["turnCompleted"] = True
        path = write_fixture(root, not_found, "final-not-found.json")
        expect_success("final未found全false", run_adapter(path), "DELIVERY_PENDING")

        latest_error = ready_payload()
        latest_error["finalAssistant"]["errorFree"] = False
        latest_error["completionEvidence"]["complete"] = False
        latest_error["completionEvidence"]["finalAssistantErrorFree"] = False
        path = write_fixture(root, latest_error, "delivery-error.json")
        expect_success("最新error", run_adapter(path), "DELIVERY_ERROR")

        # --- completionEvidence 双向一致（F2 回归）：欠声明方向 ---
        for ce_key in (
            "complete",
            "turnCompleted",
            "finalAssistantCompleted",
            "finalAssistantErrorFree",
            "finalTextAvailable",
        ):
            under = ready_payload()
            under["completionEvidence"][ce_key] = False
            path = write_fixture(root, under, f"under-{ce_key}.json")
            expect_success(f"欠声明{ce_key}=false", run_adapter(path), "EVIDENCE_CONFLICT")

        # --- 过度声明方向 ---
        fake = ready_payload()
        fake["finalAssistant"]["errorFree"] = False
        fake["completionEvidence"]["finalAssistantErrorFree"] = False
        path = write_fixture(root, fake, "fake-complete.json")
        expect_success("伪complete=true", run_adapter(path), "EVIDENCE_CONFLICT")

        contra = turn_state_payload("running")
        contra["completionEvidence"]["turnCompleted"] = True
        path = write_fixture(root, contra, "contradiction.json")
        expect_success("turnCompleted与running矛盾", run_adapter(path), "EVIDENCE_CONFLICT")

        over_text = ready_payload()
        over_text["finalAssistant"]["textAvailable"] = False
        over_text["completionEvidence"]["complete"] = False
        path = write_fixture(root, over_text, "over-text.json")
        expect_success("ce与final字段矛盾", run_adapter(path), "EVIDENCE_CONFLICT")

        # --- finalAssistant 内部矛盾：found=false 却声明具体布尔 ---
        for key in ("completed", "errorFree", "textAvailable"):
            ghost_final = ready_payload()
            ghost_final["finalAssistant"]["found"] = False
            ghost_final["completionEvidence"] = dict(CLEAN_COMPLETION)
            ghost_final["completionEvidence"]["turnCompleted"] = True
            ce_key = "finalAssistant" + key[0].upper() + key[1:]
            ghost_final["completionEvidence"][ce_key] = True
            ghost_final["finalAssistant"][key] = True
            path = write_fixture(root, ghost_final, f"ghost-final-{key}.json")
            expect_success(f"final未found却{key}=true", run_adapter(path), "EVIDENCE_CONFLICT")

        # --- turn 自身矛盾 ---
        self_contra = turn_state_payload("completed")
        self_contra["turn"]["found"] = False
        path = write_fixture(root, self_contra, "self-contradiction.json")
        expect_success("turn自身矛盾", run_adapter(path), "EVIDENCE_CONFLICT")

        # --- 坏类型 / 坏 schema（非 null 非合法类型才拒绝）---
        bad_type = ready_payload()
        bad_type["finalAssistant"]["completed"] = "true"
        path = write_fixture(root, bad_type, "bad-type.json")
        expect_error("布尔伪装字符串", run_adapter(path), "EVIDENCE_TYPE_INVALID")

        bad_turn_status = ready_payload()
        bad_turn_status["turn"]["status"] = 123
        path = write_fixture(root, bad_turn_status, "bad-turn-status.json")
        expect_error("turn.status=123", run_adapter(path), "EVIDENCE_TYPE_INVALID")

        bad_turn_id = ready_payload()
        bad_turn_id["turn"]["turnId"] = ["turn_x"]
        path = write_fixture(root, bad_turn_id, "bad-turn-id.json")
        expect_error("turnId=数组", run_adapter(path), "EVIDENCE_TYPE_INVALID")

        bad_input_status = collector_admitted()
        bad_input_status["input"] = {"status": 7}
        path = write_fixture(root, bad_input_status, "bad-input-status.json")
        expect_error("input.status=7", run_adapter(path), "EVIDENCE_TYPE_INVALID")

        bad_session = ready_payload()
        bad_session["sessionId"] = 123
        path = write_fixture(root, bad_session, "bad-session-type.json")
        expect_error("sessionId坏类型", run_adapter(path), "EVIDENCE_TYPE_INVALID")

        schema_cases = (
            ("schemaVersion=2", lambda p: p.update(schemaVersion=2)),
            ("缺schemaVersion", lambda p: p.pop("schemaVersion", None)),
            ("schemaVersion字符串", lambda p: p.update(schemaVersion="1")),
        )
        for name, mutate in schema_cases:
            broken = ready_payload()
            mutate(broken)
            path = write_fixture(root, broken, "schema.json")
            expect_error(name, run_adapter(path), "EVIDENCE_SCHEMA_UNSUPPORTED")

        path = root / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        expect_error("坏JSON", run_adapter(path), "EVIDENCE_NOT_JSON")

        path = root / "bad-utf8.json"
        path.write_bytes(b'{"schemaVersion": 1, "sessionId": "\xff\xfe"}')
        expect_error("坏UTF8", run_adapter(path), "EVIDENCE_NOT_UTF8")

        path = root / "too-large.json"
        path.write_bytes(b" " * (1024 * 1024 + 1))
        expect_error("超1MiB", run_adapter(path), "EVIDENCE_TOO_LARGE")

        missing = root / "absent.json"
        before_entries = sorted(p.name for p in root.iterdir())
        expect_error(
            "缺文件",
            run_adapter(missing),
            "EVIDENCE_UNREADABLE",
            secret_strings=(str(missing),),
        )
        check("缺文件: 不创建文件", not missing.exists())
        check("缺文件: 目录无新增", sorted(p.name for p in root.iterdir()) == before_entries)

        # --- 绑定 / 摘要 / 期待 provider+model ---
        path = write_fixture(root, ready_payload(), "binding.json")
        expect_error("session绑定不一致", run_adapter(path, session="sess_other"), "BINDING_MISMATCH")
        expect_error("input绑定不一致", run_adapter(path, input_id="input_other"), "BINDING_MISMATCH")

        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        expect_success(
            "摘要一致",
            run_adapter(path, extra=["--expected-evidence-sha256", digest]),
            "READY_FOR_PM_REVIEW",
        )
        expect_error(
            "摘要不一致",
            run_adapter(path, extra=["--expected-evidence-sha256", "0" * 64]),
            "EVIDENCE_DIGEST_MISMATCH",
        )
        expect_error(
            "摘要格式非法",
            run_adapter(path, extra=["--expected-evidence-sha256", "xyz"]),
            "EVIDENCE_DIGEST_MISMATCH",
        )

        expect_error(
            "provider不一致",
            run_adapter(path, extra=["--expected-provider", "account:other"]),
            "PROVIDER_MISMATCH",
        )
        expect_error(
            "model不一致",
            run_adapter(path, extra=["--expected-model", "model-x"]),
            "MODEL_MISMATCH",
        )
        expect_success(
            "provider/model一致",
            run_adapter(
                path,
                extra=["--expected-provider", FIXTURE_PROVIDER, "--expected-model", FIXTURE_MODEL],
            ),
            "READY_FOR_PM_REVIEW",
        )

        no_provider = ready_payload()
        del no_provider["finalAssistant"]["providerId"]
        path = write_fixture(root, no_provider, "no-provider.json")
        result = expect_success("provider缺失仍unknown", run_adapter(path), "READY_FOR_PM_REVIEW")
        if result:
            check("provider缺失: 输出unknown", result["provider"] == "unknown", result["provider"])
        expect_error(
            "provider缺失不回落期待套餐",
            run_adapter(path, extra=["--expected-provider", FIXTURE_PROVIDER]),
            "PROVIDER_MISMATCH",
        )

        # --- 泄露防线 / 只读不变 ---
        leak = ready_payload()
        leak["reasoning"] = "SECRET-REASONING-BODY"
        leak["toolTranscript"] = [{"credential": "TOKEN-XYZ"}]
        leak["finalAssistant"]["text"] = "FINAL-TEXT-BODY"
        leak["input"]["reason"] = "INPUT-REASON-BODY"
        path = write_fixture(root, leak, "leak.json")
        proc = run_adapter(path)
        blob = proc.stdout + proc.stderr
        for secret in ("SECRET-REASONING-BODY", "TOKEN-XYZ", "FINAL-TEXT-BODY", "INPUT-REASON-BODY"):
            check(f"泄露防线: {secret} 不出现", secret not in blob)

        sensitive_dir = root / "sensitive"
        sensitive_dir.mkdir()
        path = write_fixture(sensitive_dir, ready_payload(), "secret-evidence-name.json")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        proc = run_adapter(path, extra=["--expected-evidence-sha256", "0" * 64])
        check("错误输出不含路径", str(sensitive_dir) not in proc.stdout + proc.stderr)

        before_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        before_entries = sorted(p.name for p in sensitive_dir.iterdir())
        run_adapter(path)
        run_adapter(path, extra=["--expected-evidence-sha256", digest])
        check("只读: 文件内容不变", hashlib.sha256(path.read_bytes()).hexdigest() == before_digest)
        check("只读: 目录条目不变", sorted(p.name for p in sensitive_dir.iterdir()) == before_entries)

        # --- 真实采集样例：仅由环境变量显式传入，缺省明确 SKIP ---
        real_path = Path(REAL_EVIDENCE) if REAL_EVIDENCE else None
        env_ready = bool(REAL_SESSION and REAL_INPUT and real_path and real_path.is_file())
        if env_ready:
            extra_env = []
            if REAL_SHA256:
                extra_env = ["--expected-evidence-sha256", REAL_SHA256]
            proc = run_adapter(real_path, session=REAL_SESSION, input_id=REAL_INPUT)
            result = expect_success("真实样例", proc, "READY_FOR_PM_REVIEW")
            if result and REAL_SHA256:
                check("真实样例: 摘要固定", result["evidenceSha256"] == REAL_SHA256, result["evidenceSha256"])
            if result and REAL_PROVIDER:
                check("真实样例: provider回显", result["provider"] == REAL_PROVIDER, result["provider"])
            if result and REAL_MODEL:
                check("真实样例: model回显", result["model"] == REAL_MODEL, result["model"])
            expect_success(
                "真实样例+期待校验",
                run_adapter(
                    real_path,
                    session=REAL_SESSION,
                    input_id=REAL_INPUT,
                    extra=[
                        *extra_env,
                        *(["--expected-provider", REAL_PROVIDER] if REAL_PROVIDER else []),
                        *(["--expected-model", REAL_MODEL] if REAL_MODEL else []),
                    ],
                ),
                "READY_FOR_PM_REVIEW",
            )
            expect_error(
                "真实样例+错误绑定",
                run_adapter(real_path, session="sess_other", input_id=REAL_INPUT),
                "BINDING_MISMATCH",
            )
        else:
            print(
                "SKIP 真实采集样例：需环境变量 ZCODE_GUI_MONITOR_REAL_EVIDENCE/"
                "_REAL_SESSION/_REAL_INPUT 且文件存在（默认前置不绑定远端路径）"
            )

    print(f"passed={passed} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
