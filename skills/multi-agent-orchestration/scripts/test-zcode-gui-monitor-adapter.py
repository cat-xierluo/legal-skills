#!/usr/bin/env python3
"""zcode-gui-monitor-adapter.py 的离线契约自测：固定监控状态与完成待审门。

全部用例通过真实 CLI 驱动，零网络、零外部副作用（临时目录自包含 fixture）。
覆盖：

  - 固定状态全量映射：INPUT_ACCEPTED / INPUT_FAILED、TURN_UNKNOWN /
    TURN_RUNNING / TURN_ERROR / TURN_CANCELLED、DELIVERY_PENDING /
    DELIVERY_ERROR、READY_FOR_PM_REVIEW、EVIDENCE_CONFLICT；
  - fail-closed 校验：坏 UTF-8/JSON/schema/类型、绑定不一致、摘要不匹配、
    期待 provider/model 不一致（provider 缺失不回落）、缺文件不创建、
    超 1MiB 上限；
  - completionEvidence 逐项一致：伪 complete=true、矛盾字段、无 turn 却有
    最终 assistant、turn 自身矛盾；旧成功不被最新 error 掩盖；
  - 泄露防线：未知字段、路径、敏感正文均不出现在任何输出；
  - 只读不变：重跑摘要一致、文件内容与目录条目不变；
  - 真实采集样例（存在时）：绑定实施者 session/input 应 READY_FOR_PM_REVIEW。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "zcode-gui-monitor-adapter.py"
REAL_EVIDENCE = Path(
    "/private/tmp/zcode-gui-evidence-pr-20261002/review/collector-real-binding-r2.json"
)
REAL_SHA256 = "c454d6f4b962727bf2a77011e45eacfcdb360bb07a53a4e9bc35482f5b0fad7e"
REAL_SESSION = "sess_d9fe1217-0629-452a-ac22-882a9f80f32d"
REAL_INPUT = "queue_01a0fcbd-14f6-787c-8c0d-51e076f351d7"

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
        "finalAssistant": {
            "found": True,
            "completed": True,
            "errorFree": True,
            "textAvailable": True,
            "providerId": FIXTURE_PROVIDER,
            "modelId": FIXTURE_MODEL,
            "messageId": "msg_final",
            "textLength": 42,
            "mode": "yolo",
        },
        "completionEvidence": {
            "complete": True,
            "turnCompleted": True,
            "finalAssistantCompleted": True,
            "finalAssistantErrorFree": True,
            "finalTextAvailable": True,
        },
        "liveness": {
            "authoritative": False,
            "note": "Cold read-only snapshot; missing fields are never inferred.",
        },
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

        # --- 输入两态（按任务顺序短路）---
        admitted = ready_payload()
        admitted["input"] = {"status": "admitted"}
        admitted["turn"] = {"found": True, "status": "running", "turnId": "turn_fixture"}
        admitted.pop("finalAssistant")
        admitted["completionEvidence"] = dict(CLEAN_COMPLETION)
        path = write_fixture(root, admitted, "admitted.json")
        expect_success("admitted", run_adapter(path), "INPUT_ACCEPTED")

        stale_success = ready_payload()
        stale_success["input"] = {"status": "failed"}
        path = write_fixture(root, stale_success, "failed.json")
        expect_success("failed掩盖旧成功", run_adapter(path), "INPUT_FAILED")

        # --- promoted 后的 turn 各态 ---
        no_turn = ready_payload()
        no_turn["turn"] = {"found": False}
        no_turn.pop("finalAssistant")
        no_turn["completionEvidence"] = dict(CLEAN_COMPLETION)
        path = write_fixture(root, no_turn, "no-turn.json")
        expect_success("promoted无turn", run_adapter(path), "TURN_UNKNOWN")

        path = write_fixture(root, turn_state_payload("running"), "running.json")
        expect_success("running", run_adapter(path), "TURN_RUNNING")
        path = write_fixture(root, turn_state_payload("cancelled"), "cancelled.json")
        expect_success("cancelled", run_adapter(path), "TURN_CANCELLED")
        path = write_fixture(root, turn_state_payload("queued"), "queued.json")
        expect_success("未知turn保留UNKNOWN", run_adapter(path), "TURN_UNKNOWN")

        old_success = turn_state_payload("error")
        old_success["finalAssistant"] = ready_payload()["finalAssistant"]
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
        expect_success("final未found", run_adapter(path), "DELIVERY_PENDING")

        latest_error = ready_payload()
        latest_error["finalAssistant"]["errorFree"] = False
        latest_error["completionEvidence"]["complete"] = False
        latest_error["completionEvidence"]["finalAssistantErrorFree"] = False
        path = write_fixture(root, latest_error, "delivery-error.json")
        expect_success("最新error", run_adapter(path), "DELIVERY_ERROR")

        # --- 伪完成 / 矛盾字段 → EVIDENCE_CONFLICT ---
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

        ghost = ready_payload()
        ghost["turn"] = {"found": False}
        ghost["completionEvidence"] = dict(CLEAN_COMPLETION)
        path = write_fixture(root, ghost, "ghost-final.json")
        expect_success("无turn却有final", run_adapter(path), "EVIDENCE_CONFLICT")

        self_contra = turn_state_payload("completed")
        self_contra["turn"]["found"] = False
        path = write_fixture(root, self_contra, "self-contradiction.json")
        expect_success("turn自身矛盾", run_adapter(path), "EVIDENCE_CONFLICT")

        # --- 坏类型 / 坏 schema ---
        bad_type = ready_payload()
        bad_type["finalAssistant"]["completed"] = "true"
        path = write_fixture(root, bad_type, "bad-type.json")
        expect_error("布尔伪装字符串", run_adapter(path), "EVIDENCE_TYPE_INVALID")

        bad_ce = ready_payload()
        bad_ce["completionEvidence"]["complete"] = "true"
        path = write_fixture(root, bad_ce, "bad-ce-type.json")
        expect_error("ce布尔伪装字符串", run_adapter(path), "EVIDENCE_TYPE_INVALID")

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
        no_provider["completionEvidence"]["complete"] = False
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

        # --- 真实采集样例（存在时）---
        if REAL_EVIDENCE.is_file():
            proc = run_adapter(REAL_EVIDENCE, session=REAL_SESSION, input_id=REAL_INPUT)
            result = expect_success("真实样例", proc, "READY_FOR_PM_REVIEW")
            if result:
                check(
                    "真实样例: 摘要固定",
                    result["evidenceSha256"] == REAL_SHA256,
                    result["evidenceSha256"],
                )
                check(
                    "真实样例: provider/model回显",
                    result["provider"] == FIXTURE_PROVIDER and result["model"] == FIXTURE_MODEL,
                    (result["provider"], result["model"]),
                )
            expect_success(
                "真实样例+摘要校验",
                run_adapter(
                    REAL_EVIDENCE,
                    session=REAL_SESSION,
                    input_id=REAL_INPUT,
                    extra=["--expected-evidence-sha256", REAL_SHA256],
                ),
                "READY_FOR_PM_REVIEW",
            )
            expect_error(
                "真实样例+错误绑定",
                run_adapter(REAL_EVIDENCE, session="sess_other", input_id=REAL_INPUT),
                "BINDING_MISMATCH",
            )
        else:
            print("SKIP 真实采集样例不存在（离线环境）")

    print(f"passed={passed} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
