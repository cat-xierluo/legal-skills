#!/usr/bin/env python3
"""检查单份文书、单个受送达人的送达证据契约；不鉴真、不计算期限。"""
import argparse
import json
import re
from datetime import date
from pathlib import Path


ALLOWED_EVENTS = {
    "court_delivery_receipt": {"delivered"},
    "court_system_record": {"sent_success", "arrived"},
    "recipient_arrival_proof": {"arrived"},
}


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def assess_service(record):
    """输入必须经过原始证据核对；checked 标志不能替代证据真实性。"""
    def pending(reason):
        return {"status": "pending", "served_on": None,
                "evidence_refs": [], "reason": reason}

    if not isinstance(record, dict):
        return pending("invalid_record")
    document_id, recipient_id = record.get("document_id"), record.get("recipient_id")
    if not nonempty(document_id) or not nonempty(recipient_id):
        return pending("missing_document_or_recipient")
    basis = record.get("service_basis")
    if not isinstance(basis, dict) or basis.get("checked") is not True or not nonempty(basis.get("ref")):
        return pending("service_basis_not_checked")
    # 缺省也不等于“已检查且没有冲突”。
    if record.get("conflict_checked") is not True or record.get("has_conflict") is not False:
        return pending("conflict_unresolved")
    evidence = record.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return pending("missing_evidence")
    dates, refs = set(), []
    for item in evidence:
        if not isinstance(item, dict):
            return pending("invalid_evidence")
        kind = item.get("kind")
        if not isinstance(kind, str):
            return pending("invalid_evidence_kind")
        if kind not in ALLOWED_EVENTS:
            # 二维码、落款、普通短信时间等仅是线索，不可升级为送达事实。
            continue
        if item.get("checked") is not True:
            return pending("evidence_not_checked")
        ids = item.get("document_ids")
        if not isinstance(ids, list) or not ids or not all(nonempty(x) for x in ids):
            return pending("invalid_document_binding")
        if document_id not in ids or item.get("recipient_id") != recipient_id:
            return pending("document_or_recipient_mismatch")
        event = item.get("event")
        if not isinstance(event, str) or event not in ALLOWED_EVENTS[kind] or not nonempty(item.get("ref")):
            return pending("missing_delivery_event_or_ref")
        day = item.get("date")
        if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            return pending("invalid_service_date")
        try:
            date.fromisoformat(day)
        except ValueError:
            return pending("invalid_service_date")
        dates.add(day)
        refs.append(item["ref"])
    if not dates:
        return pending("no_qualifying_service_evidence")
    if len(dates) != 1:
        return pending("conflicting_service_dates")
    return {"status": "confirmed", "served_on": next(iter(dates)),
            "evidence_refs": list(dict.fromkeys(refs)), "reason": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path, help="经过核对的单文书送达证据 JSON")
    args = parser.parse_args()
    try:
        result = assess_service(json.loads(args.record.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, ValueError):
        print(json.dumps({"status": "error", "served_on": None,
                          "reason": "input_unreadable_or_invalid_json"}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "confirmed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
