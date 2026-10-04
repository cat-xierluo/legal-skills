#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""zcode-pr-acceptance — 远端直发 PR 证据离线验收 CLI。

任务：TASK-2026-10-04-ZGUI-PR-ACCEPTANCE
仅使用 Python 标准库；运行时：

- 无网络请求、无 gh 调用、无 Git 变更、无 token 访问、无自动 merge
- 不读取环境变量秘密，不回显输入中的不可信自由文本，不输出秘密
- 输入为两份显式版本 JSON（PM 预期 expectations@1 + PM 新鲜读取的 GitHub 证据 evidence@1）
- 输出稳定 PASS/REJECT/UNKNOWN + 原因枚举 + 输入 SHA256 绑定 + 证据新鲜度判定

用法：
    python3 zcode-pr-acceptance.py --expectations exp.json --evidence ev.json \
        [--now-iso "2026-10-04T12:00:00Z"] [--out verdict.json]

退出码：0=PASS  10=REJECT  20=UNKNOWN  30=内部错误（参数错误沿用 argparse 的 2）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone

TOOL_VERSION = "1.0.0"
EXPECTATIONS_SCHEMA = "zgui-pr-acceptance/expectations@1"
EVIDENCE_SCHEMA = "zgui-pr-acceptance/evidence@1"
VERDICT_SCHEMA = "zgui-pr-acceptance/verdict@1"

EXIT_PASS = 0
EXIT_REJECT = 10
EXIT_UNKNOWN = 20
EXIT_INTERNAL = 30

# 判定为 UNKNOWN（证据不足/过期，无法下结论）而非 REJECT（证据无效或证明违规）的原因枚举
UNKNOWN_REASONS = {
    "BRANCH_PR_LIST_EMPTY",
    "BRANCH_PR_NOT_LISTED",
    "REQUIRED_CHECKS_UNSPECIFIED",
    "EVIDENCE_STALE",
    "EVIDENCE_TIME_INVALID",
}

# 全部以 \Z 锚定结尾：正则的 $ 会放过尾随换行（安全审查 P2-1）
SHA40_RE = re.compile(r"^[0-9a-f]{40}\Z")
SHA_RE = re.compile(r"^[0-9a-f]{40}\Z|^[0-9a-f]{64}\Z")
SID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}\Z")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z")
REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}\Z")
CHECK_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._/:(\)-]{0,127}\Z")
# 小数秒仅接受 3 或 6 位（毫秒/微秒）：CPython 3.8-3.10 的 fromisoformat
# 不接受其他位数，否则同一输入跨版本判定漂移（安全审查 P2-3）
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3}|\.\d{6})?Z\Z")

PR_STATES = {"OPEN", "CLOSED", "MERGED"}
REVIEW_VERDICTS = {"APPROVE", "REJECT"}
FILE_STATUSES = {"added", "changed", "modified", "renamed", "removed"}
CHECK_STATUSES = {"queued", "in_progress", "completed"}
CHECK_CONCLUSIONS = {
    "success", "failure", "neutral", "skipped",
    "timed_out", "action_required", "cancelled", "stale",
}
MAX_BLOCKERS = 100
MAX_LIST_LEN = 1000
FUTURE_TOLERANCE_SECONDS = 300


class Findings:
    """按固定顺序收集原因枚举；detail 仅允许结构化字段（sha/计数），禁止自由文本。"""

    def __init__(self) -> None:
        self.items: list[tuple[str, dict]] = []

    def add(self, reason: str, **detail: object) -> None:
        self.items.append((reason, detail))

    def reasons(self) -> list[str]:
        return [r for r, _ in self.items]

    def details(self) -> dict:
        out: dict = {}
        for r, d in self.items:
            out.setdefault(r, d if len(d) > 1 else (list(d.values())[0] if d else {}))
        return out

    def has(self, reason: str) -> bool:
        return any(r == reason for r, _ in self.items)

    def reject_level(self) -> bool:
        return any(r not in UNKNOWN_REASONS for r, _ in self.items)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_utc(value: str) -> datetime:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        raise ValueError("naive timestamp")
    return dt.astimezone(timezone.utc)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_plain_int(value: object) -> bool:
    # 显式排除 bool 冒充 int（Python 中 isinstance(True, int) 为 True）
    return isinstance(value, int) and not isinstance(value, bool)


def check_rel_path(path: object) -> str:
    """返回 'ok' / 'traversal' / 'invalid'；只接受朴素相对 POSIX 路径。"""
    if not isinstance(path, str):
        return "invalid"
    if not path or len(path) > 512:
        return "invalid"
    if path.startswith("/") or path.startswith("~") or "\\" in path:
        return "traversal"
    if path != path.strip():
        return "traversal"
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in path):
        return "traversal"
    for seg in path.split("/"):
        if seg in ("", ".", ".."):
            return "traversal"
    return "ok"


def require_str(f: Findings, doc: dict, key: str, *, where: str,
                pattern: re.Pattern[str] | None = None,
                enums: set[str] | None = None) -> str | None:
    if key not in doc:
        f.add("SCHEMA_MISSING_FIELD", field=f"{where}.{key}")
        return None
    v = doc[key]
    if not isinstance(v, str):
        f.add("TYPE_MISMATCH", field=f"{where}.{key}", expected="string")
        return None
    if enums is not None and v not in enums:
        f.add("VALUE_INVALID", field=f"{where}.{key}")
        return None
    if pattern is not None and pattern.match(v) is None:
        f.add("VALUE_INVALID", field=f"{where}.{key}")
        return None
    return v


def require_bool(f: Findings, doc: dict, key: str, *, where: str) -> bool | None:
    if key not in doc:
        f.add("SCHEMA_MISSING_FIELD", field=f"{where}.{key}")
        return None
    v = doc[key]
    if not isinstance(v, bool):
        f.add("TYPE_MISMATCH", field=f"{where}.{key}", expected="bool")
        return None
    return v


def require_pos_int(f: Findings, doc: dict, key: str, *, where: str,
                    allow_zero: bool = False) -> int | None:
    if key not in doc:
        f.add("SCHEMA_MISSING_FIELD", field=f"{where}.{key}")
        return None
    v = doc[key]
    if isinstance(v, bool):
        f.add("BOOL_AS_INT", field=f"{where}.{key}")
        return None
    if not isinstance(v, int):
        f.add("TYPE_MISMATCH", field=f"{where}.{key}", expected="int")
        return None
    if v < (0 if allow_zero else 1):
        f.add("VALUE_INVALID", field=f"{where}.{key}")
        return None
    return v


def require_str_list(f: Findings, doc: dict, key: str, *, where: str,
                     unique_reason: str | None = None) -> list[str] | None:
    if key not in doc:
        f.add("SCHEMA_MISSING_FIELD", field=f"{where}.{key}")
        return None
    v = doc[key]
    if not isinstance(v, list):
        f.add("TYPE_MISMATCH", field=f"{where}.{key}", expected="list")
        return None
    if len(v) > MAX_LIST_LEN:
        f.add("VALUE_INVALID", field=f"{where}.{key}")
        return None
    for i, item in enumerate(v):
        if not isinstance(item, str):
            f.add("TYPE_MISMATCH", field=f"{where}.{key}[{i}]", expected="string")
            return None
    if unique_reason is not None and len(set(v)) != len(v):
        f.add(unique_reason, field=f"{where}.{key}")
        return None
    return v


def load_document(path: str, expected_schema: str, f: Findings,
                  which: str) -> tuple[dict | None, bytes | None]:
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        f.add("INPUT_MISSING", which=which)
        return None, None
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        f.add("INPUT_UNPARSEABLE", which=which)
        return None, raw
    if not isinstance(doc, dict):
        f.add("INPUT_NOT_OBJECT", which=which)
        return None, raw
    schema = doc.get("schema")
    if not isinstance(schema, str) or schema != expected_schema:
        f.add("SCHEMA_UNKNOWN", field="schema", expected=expected_schema)
        return None, raw
    return doc, raw


def validate_expectations(doc: dict, f: Findings) -> dict:
    exp: dict = {}
    exp["task_sid"] = require_str(f, doc, "task_sid", where="expectations", pattern=SID_RE)
    exp["repo"] = require_str(f, doc, "repo", where="expectations", pattern=REPO_RE)
    exp["expected_base_ref"] = require_str(f, doc, "expected_base_ref", where="expectations", pattern=REF_RE)
    exp["expected_base"] = require_str(f, doc, "expected_base", where="expectations", pattern=SHA40_RE)
    exp["expected_head"] = require_str(f, doc, "expected_head", where="expectations", pattern=SHA40_RE)
    exp["expected_branch"] = require_str(f, doc, "expected_branch", where="expectations", pattern=REF_RE)

    paths = require_str_list(f, doc, "allowed_paths", where="expectations", unique_reason="PATH_DUPLICATE")
    if paths is not None:
        if not paths:
            f.add("VALUE_INVALID", field="expectations.allowed_paths")
            paths = None
        else:
            for p in paths:
                verdict = check_rel_path(p)
                if verdict == "traversal":
                    f.add("PATH_TRAVERSAL", field="expectations.allowed_paths")
                    paths = None
                    break
                if verdict == "invalid":
                    f.add("VALUE_INVALID", field="expectations.allowed_paths")
                    paths = None
                    break
    exp["allowed_paths"] = sorted(paths) if paths else None

    exp["author_sid"] = require_str(f, doc, "author_sid", where="expectations", pattern=SID_RE)
    exp["reviewer_sid"] = require_str(f, doc, "reviewer_sid", where="expectations", pattern=SID_RE)

    checks = require_str_list(f, doc, "required_checks", where="expectations", unique_reason="VALUE_INVALID")
    if checks is not None:
        for c in checks:
            if CHECK_NAME_RE.match(c) is None:
                f.add("VALUE_INVALID", field="expectations.required_checks")
                checks = None
                break
        if checks is not None and not checks:
            # 空必需 check 清单：不能以 all([]) 放行，显式 UNKNOWN
            f.add("REQUIRED_CHECKS_UNSPECIFIED", field="expectations.required_checks")
            checks = None
    exp["required_checks"] = checks

    exp["evidence_max_age_seconds"] = require_pos_int(f, doc, "evidence_max_age_seconds", where="expectations")

    if exp["author_sid"] and exp["reviewer_sid"] and exp["author_sid"] == exp["reviewer_sid"]:
        f.add("REVIEWER_NOT_INDEPENDENT", scope="expectations")
    return exp


def validate_evidence(doc: dict, f: Findings) -> dict:
    ev: dict = {}
    ev["collected_at"] = require_str(f, doc, "collected_at", where="evidence", pattern=ISO_RE)
    if ev["collected_at"] is not None:
        try:
            ev["collected_at_dt"] = parse_iso_utc(ev["collected_at"])
        except ValueError:
            f.add("VALUE_INVALID", field="evidence.collected_at")
            ev["collected_at"] = None
    ev["repo"] = require_str(f, doc, "repo", where="evidence", pattern=REPO_RE)

    pr_obj = doc.get("pr")
    if not isinstance(pr_obj, dict):
        f.add("TYPE_MISMATCH", field="evidence.pr", expected="object")
        pr_obj = {}
    pr: dict = {}
    pr["number"] = require_pos_int(f, pr_obj, "number", where="evidence.pr")
    pr["state"] = require_str(f, pr_obj, "state", where="evidence.pr", enums=PR_STATES)
    pr["is_draft"] = require_bool(f, pr_obj, "is_draft", where="evidence.pr")
    pr["branch"] = require_str(f, pr_obj, "branch", where="evidence.pr", pattern=REF_RE)
    pr["head_sha"] = require_str(f, pr_obj, "head_sha", where="evidence.pr", pattern=SHA40_RE)
    pr["base_ref"] = require_str(f, pr_obj, "base_ref", where="evidence.pr", pattern=REF_RE)
    pr["base_sha"] = require_str(f, pr_obj, "base_sha", where="evidence.pr", pattern=SHA40_RE)
    pr["author_sid"] = require_str(f, pr_obj, "author_sid", where="evidence.pr", pattern=SID_RE)

    files = pr_obj.get("files")
    if not isinstance(files, list):
        f.add("TYPE_MISMATCH", field="evidence.pr.files", expected="list")
        files = None
    elif len(files) > MAX_LIST_LEN:
        f.add("VALUE_INVALID", field="evidence.pr.files")
        files = None
    else:
        seen: list[str] = []
        ok = True
        for i, item in enumerate(files):
            if not isinstance(item, dict):
                f.add("TYPE_MISMATCH", field=f"evidence.pr.files[{i}]", expected="object")
                ok = False
                break
            path = item.get("path")
            status = item.get("status")
            blob = item.get("sha")  # 可选
            verdict = check_rel_path(path)
            if verdict == "traversal":
                f.add("PATH_TRAVERSAL", field=f"evidence.pr.files[{i}].path")
                ok = False
                break
            if verdict == "invalid":
                f.add("VALUE_INVALID", field=f"evidence.pr.files[{i}].path")
                ok = False
                break
            if not isinstance(status, str) or status not in FILE_STATUSES:
                f.add("VALUE_INVALID", field=f"evidence.pr.files[{i}].status")
                ok = False
                break
            if blob is not None and (not isinstance(blob, str) or SHA_RE.match(blob) is None):
                f.add("VALUE_INVALID", field=f"evidence.pr.files[{i}].sha")
                ok = False
                break
            if status == "removed":
                f.add("FILE_STATUS_UNSUPPORTED", field=f"evidence.pr.files[{i}].status", status="removed")
                ok = False
                break
            if status == "renamed":
                prev = item.get("previous_path")
                pv = check_rel_path(prev)
                if pv != "ok":
                    f.add("PATH_TRAVERSAL" if pv == "traversal" else "VALUE_INVALID",
                          field=f"evidence.pr.files[{i}].previous_path")
                    ok = False
                    break
                seen.append(prev)
            seen.append(path)
        if ok:
            if len(set(seen)) != len(seen):
                f.add("PATH_DUPLICATE", field="evidence.pr.files")
                files = None
            else:
                files = sorted(seen)
        else:
            files = None
    pr["files"] = files
    ev["pr"] = pr

    branch_prs = doc.get("branch_prs")
    if not isinstance(branch_prs, list):
        f.add("TYPE_MISMATCH", field="evidence.branch_prs", expected="list")
        branch_prs = None
    elif len(branch_prs) > MAX_LIST_LEN:
        f.add("VALUE_INVALID", field="evidence.branch_prs")
        branch_prs = None
    else:
        parsed: list[dict] = []
        ok = True
        for i, item in enumerate(branch_prs):
            if not isinstance(item, dict):
                f.add("TYPE_MISMATCH", field=f"evidence.branch_prs[{i}]", expected="object")
                ok = False
                break
            num = require_pos_int(f, item, "number", where=f"evidence.branch_prs[{i}]")
            state = require_str(f, item, "state", where=f"evidence.branch_prs[{i}]", enums=PR_STATES)
            branch = require_str(f, item, "branch", where=f"evidence.branch_prs[{i}]", pattern=REF_RE)
            head = require_str(f, item, "head_sha", where=f"evidence.branch_prs[{i}]", pattern=SHA40_RE)
            if num is None or state is None or branch is None or head is None:
                ok = False
                break
            parsed.append({"number": num, "state": state, "branch": branch, "head_sha": head})
        if ok:
            branch_prs = parsed
        else:
            branch_prs = None
    ev["branch_prs"] = branch_prs

    hc_obj = doc.get("head_checks")
    if not isinstance(hc_obj, dict):
        f.add("TYPE_MISMATCH", field="evidence.head_checks", expected="object")
        hc_obj = {}
    hc: dict = {}
    hc["head_sha"] = require_str(f, hc_obj, "head_sha", where="evidence.head_checks", pattern=SHA40_RE)
    checks = hc_obj.get("checks")
    if not isinstance(checks, list):
        f.add("TYPE_MISMATCH", field="evidence.head_checks.checks", expected="list")
        checks = None
    elif len(checks) > MAX_LIST_LEN:
        f.add("VALUE_INVALID", field="evidence.head_checks.checks")
        checks = None
    else:
        parsed_checks: list[dict] = []
        names: list[str] = []
        ok = True
        for i, item in enumerate(checks):
            if not isinstance(item, dict):
                f.add("TYPE_MISMATCH", field=f"evidence.head_checks.checks[{i}]", expected="object")
                ok = False
                break
            name = require_str(f, item, "name", where=f"evidence.head_checks.checks[{i}]", pattern=CHECK_NAME_RE)
            status = require_str(f, item, "status", where=f"evidence.head_checks.checks[{i}]", enums=CHECK_STATUSES)
            conclusion = item.get("conclusion")
            if conclusion is not None and (not isinstance(conclusion, str)
                                           or conclusion not in CHECK_CONCLUSIONS):
                f.add("VALUE_INVALID", field=f"evidence.head_checks.checks[{i}].conclusion")
                ok = False
                break
            if name is None or status is None:
                ok = False
                break
            names.append(name)
            parsed_checks.append({"name": name, "status": status, "conclusion": conclusion})
        if ok:
            if len(set(names)) != len(names):
                f.add("CHECK_DUPLICATE", field="evidence.head_checks.checks")
                checks = None
            else:
                checks = parsed_checks
        else:
            checks = None
    hc["checks"] = checks
    ev["head_checks"] = hc

    rv_obj = doc.get("review")
    if not isinstance(rv_obj, dict):
        f.add("TYPE_MISMATCH", field="evidence.review", expected="object")
        rv_obj = {}
    rv: dict = {}
    rv["reviewer_sid"] = require_str(f, rv_obj, "reviewer_sid", where="evidence.review", pattern=SID_RE)
    rv["head_sha"] = require_str(f, rv_obj, "head_sha", where="evidence.review", pattern=SHA40_RE)
    rv["verdict"] = require_str(f, rv_obj, "verdict", where="evidence.review", enums=REVIEW_VERDICTS)
    blockers = rv_obj.get("blockers")
    if not isinstance(blockers, list):
        f.add("TYPE_MISMATCH", field="evidence.review.blockers", expected="list")
        blockers = None
    elif len(blockers) > MAX_BLOCKERS:
        f.add("VALUE_INVALID", field="evidence.review.blockers")
        blockers = None
    else:
        # 只记计数，内容（自由文本）永不回显
        for b in blockers:
            if not isinstance(b, str):
                f.add("TYPE_MISMATCH", field="evidence.review.blockers", expected="string-item")
                blockers = None
                break
        if blockers is not None:
            rv["blockers_count"] = len(blockers)
    rv["blockers"] = blockers
    ev["review"] = rv
    return ev


def semantic_checks(exp: dict, ev: dict, f: Findings, now: datetime) -> None:
    pr = ev["pr"]
    if exp["repo"] and ev["repo"] and exp["repo"] != ev["repo"]:
        f.add("REPO_MISMATCH", expected=exp["repo"], actual=ev["repo"])
    if exp["expected_base_ref"] and pr["base_ref"] and exp["expected_base_ref"] != pr["base_ref"]:
        f.add("BASE_MISMATCH", field="pr.base_ref", expected=exp["expected_base_ref"], actual=pr["base_ref"])
    if exp["expected_base"] and pr["base_sha"] and exp["expected_base"] != pr["base_sha"]:
        f.add("BASE_MISMATCH", field="pr.base_sha", expected=exp["expected_base"], actual=pr["base_sha"])
    if exp["expected_head"] and pr["head_sha"] and exp["expected_head"] != pr["head_sha"]:
        f.add("HEAD_MISMATCH", expected=exp["expected_head"], actual=pr["head_sha"])
    if exp["expected_branch"] and pr["branch"] and exp["expected_branch"] != pr["branch"]:
        f.add("BRANCH_MISMATCH", expected=exp["expected_branch"], actual=pr["branch"])
    if pr["state"] is not None and pr["state"] != "OPEN":
        f.add("PR_NOT_OPEN", actual=pr["state"])
    if pr["is_draft"] is True:
        f.add("PR_DRAFT")
    if exp["allowed_paths"] is not None and pr["files"] is not None:
        if exp["allowed_paths"] != pr["files"]:
            f.add("PATHS_MISMATCH",
                  expected_count=len(exp["allowed_paths"]), actual_count=len(pr["files"]))
    if exp["author_sid"] and pr["author_sid"] and exp["author_sid"] != pr["author_sid"]:
        f.add("AUTHOR_SID_MISMATCH", expected=exp["author_sid"], actual=pr["author_sid"])
    if pr["author_sid"] and ev["review"]["reviewer_sid"] and pr["author_sid"] == ev["review"]["reviewer_sid"]:
        f.add("REVIEWER_NOT_INDEPENDENT", scope="evidence")
    if exp["reviewer_sid"] and ev["review"]["reviewer_sid"] and exp["reviewer_sid"] != ev["review"]["reviewer_sid"]:
        f.add("REVIEWER_SID_MISMATCH", expected=exp["reviewer_sid"], actual=ev["review"]["reviewer_sid"])
    if exp["expected_head"] and ev["review"]["head_sha"] and exp["expected_head"] != ev["review"]["head_sha"]:
        f.add("REVIEW_HEAD_MISMATCH", expected=exp["expected_head"], actual=ev["review"]["head_sha"])
    if ev["review"]["verdict"] == "REJECT":
        f.add("REVIEW_VERDICT_REJECT")
    if ev["review"]["blockers"] is not None and len(ev["review"]["blockers"]) > 0:
        f.add("REVIEW_BLOCKERS", count=len(ev["review"]["blockers"]))

    if ev["branch_prs"] is not None:
        target_branch = pr["branch"]
        if not ev["branch_prs"]:
            f.add("BRANCH_PR_LIST_EMPTY")
        else:
            numbers = [e["number"] for e in ev["branch_prs"]]
            if len(set(numbers)) != len(numbers):
                f.add("BRANCH_PR_LIST_DUPLICATE")
            same_branch = [e for e in ev["branch_prs"]
                           if target_branch is None or e["branch"] == target_branch]
            if not same_branch:
                f.add("BRANCH_PR_NOT_LISTED")
            else:
                others = [e["number"] for e in same_branch
                          if pr["number"] is None or e["number"] != pr["number"]]
                if others:
                    f.add("DUPLICATE_BRANCH_PR", other_pr_numbers=sorted(set(others)))

    hc = ev["head_checks"]
    if exp["expected_head"] and hc["head_sha"] and exp["expected_head"] != hc["head_sha"]:
        f.add("CHECKS_HEAD_MISMATCH", expected=exp["expected_head"], actual=hc["head_sha"])
    if exp["required_checks"] is not None and hc["checks"] is not None:
        by_name = {c["name"]: c for c in hc["checks"]}
        for required in exp["required_checks"]:
            entry = by_name.get(required)
            if entry is None:
                f.add("REQUIRED_CHECK_MISSING", check=required)
                continue
            # 唯一算成功的组合：completed + success；pending/queued/failed/其他一律不算
            if entry["status"] != "completed" or entry["conclusion"] != "success":
                f.add("CHECK_NOT_SUCCESS", check=required,
                      status=entry["status"], conclusion=entry["conclusion"] or "null")

    if ev["collected_at_dt"] is not None and exp["evidence_max_age_seconds"] is not None:
        age = (now - ev["collected_at_dt"]).total_seconds()
        if age < -FUTURE_TOLERANCE_SECONDS:
            f.add("EVIDENCE_TIME_INVALID", skew_seconds=-int(age))
        elif age > exp["evidence_max_age_seconds"]:
            f.add("EVIDENCE_STALE", max_age_seconds=exp["evidence_max_age_seconds"])


def evaluate(exp_path: str, ev_path: str, now: datetime, clock_source: str) -> tuple[dict, int]:
    f = Findings()
    exp_doc, exp_raw = load_document(exp_path, EXPECTATIONS_SCHEMA, f, which="expectations")
    ev_doc, ev_raw = load_document(ev_path, EVIDENCE_SCHEMA, f, which="evidence")
    exp_sha = sha256_bytes(exp_raw) if exp_raw is not None else "UNKNOWN"
    ev_sha = sha256_bytes(ev_raw) if ev_raw is not None else "UNKNOWN"

    exp = validate_expectations(exp_doc, f) if exp_doc is not None else {}
    ev = validate_evidence(ev_doc, f) if ev_doc is not None else {}

    # 结构校验存在 REJECT 级问题时不做语义比较（缺字段无法可靠比对），原因仍全部输出
    if not f.reject_level():
        ev.setdefault("pr", {
            "number": None, "state": None, "is_draft": None, "branch": None,
            "head_sha": None, "base_ref": None, "base_sha": None,
            "author_sid": None, "files": None,
        })
        ev.setdefault("review", {"reviewer_sid": None, "head_sha": None, "verdict": None, "blockers": None})
        ev.setdefault("head_checks", {"head_sha": None, "checks": None})
        semantic_checks(exp, ev, f, now)

    if f.reject_level():
        decision = "REJECT"
    elif f.reasons():
        decision = "UNKNOWN"
    else:
        decision = "PASS"

    verdict = {
        "schema": VERDICT_SCHEMA,
        "tool_version": TOOL_VERSION,
        "decision": decision,
        "reasons": f.reasons(),
        "reason_details": f.details(),
        "task_sid": exp.get("task_sid"),
        "repo": exp.get("repo"),
        "pr_number": ev.get("pr", {}).get("number"),
        "expected_head": exp.get("expected_head"),
        "expected_base": exp.get("expected_base"),
        "inputs": {"expectations_sha256": exp_sha, "evidence_sha256": ev_sha},
        "clock": {"source": clock_source, "now_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ")},
        "evidence_age_seconds": (
            int((now - ev["collected_at_dt"]).total_seconds())
            if ev.get("collected_at_dt") is not None else None
        ),
        # 注入时钟时 generated_at_utc 同样取注入值，保证同输入字节级可复现（安全审查 P2-2）
        "generated_at_utc": (
            now.strftime("%Y-%m-%dT%H:%M:%SZ") if clock_source == "argument" else utc_now_iso()
        ),
        # CI 通过 ≠ 业务语义证明：语义结论只能来自不同 SID 的内容审查
        "business_semantics_proven": False,
    }
    exit_code = {"PASS": EXIT_PASS, "REJECT": EXIT_REJECT, "UNKNOWN": EXIT_UNKNOWN}[decision]
    return verdict, exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="zcode-pr-acceptance",
        description="远端直发 PR 证据离线验收（无网络/无 Git 变更/无秘密输出）",
    )
    parser.add_argument("--expectations", required=True, help="PM 预期 JSON（expectations@1）路径")
    parser.add_argument("--evidence", required=True, help="PM 新鲜读取的 GitHub 证据 JSON（evidence@1）路径")
    parser.add_argument("--now-iso", default=None,
                        help="测试用时钟覆盖（ISO-8601 UTC）；使用时 verdict.clock.source=argument")
    parser.add_argument("--out", default=None, help="可选：将 verdict JSON 另写至该路径")
    args = parser.parse_args(argv)

    try:
        if args.now_iso is not None:
            if ISO_RE.match(args.now_iso) is None:
                print("INVALID_NOW_ISO", file=sys.stderr)
                return EXIT_INTERNAL
            now = parse_iso_utc(args.now_iso)
            clock_source = "argument"
        else:
            now = datetime.now(timezone.utc)
            clock_source = "system"
        verdict, exit_code = evaluate(args.expectations, args.evidence, now, clock_source)
        text = json.dumps(verdict, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        print(text)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
        return exit_code
    except Exception as exc:  # noqa: BLE001 — 顶层兜底，不回显异常细节中的输入内容
        print(f"INTERNAL_ERROR:{type(exc).__name__}", file=sys.stderr)
        return EXIT_INTERNAL


if __name__ == "__main__":
    sys.exit(main())
