#!/usr/bin/env python3
"""Local Magpie inventory and create-only routing plans; Python stdlib only."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid


class Refused(Exception):
    pass


def require(ok, reason):
    if not ok:
        raise Refused(reason)


def parse_json(content):
    def unique(pairs):
        obj = {}
        for k, v in pairs:
            require(k not in obj, "duplicate_json_key")
            obj[k] = v
        return obj
    return json.loads(content, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(Refused("non_finite_json")))


def load(path):
    return parse_json(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_new(path, value):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


def update_receipt(path, value):
    temp = Path(path).with_name(Path(path).name + "." + uuid.uuid4().hex + ".tmp")
    save_new(temp, value)
    os.replace(temp, path)


def config_path():
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "magpie/providers.json"


def cli(args):
    binary = shutil.which("magpie")
    require(binary is not None, "magpie_missing_install_existing_official_cli")
    p = subprocess.run([binary, *args], capture_output=True, text=True, timeout=60)
    # Raw CLI stdout/stderr can contain account identifiers or credentials.
    require(p.returncode == 0, "magpie_command_failed_" + str(p.returncode))
    return p.stdout


def inventory(data):
    provider_fields = {"id", "name", "models", "off", "hidden", "maxConcurrency", "queueSize", "queueWait", "rpm"}
    group_fields = {"id", "name", "members", "routing", "stays", "affinity", "off", "disabled", "hidden", "context", "levels", "classifier"}
    providers = []
    for p in data.get("providers", []):
        q = {k: v for k, v in p.items() if k in provider_fields}
        q["account_concurrency_values"] = list(p.get("accountConcurrency", {}).values())
        providers.append(q)
    groups = []
    for g in data.get("groups", []):
        q = {k: v for k, v in g.items() if k in group_fields}
        # Folder rules and free-text intents can contain private project data.
        q["rules"] = [{k: v for k, v in r.items() if k in {"use", "pause", "time", "days", "tokens", "effort", "images", "compact"}} for r in g.get("rules", [])]
        groups.append(q)
    return {"schema": "magpie-inventory.v1", "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "providers": providers, "groups": groups, "auto_groups_disabled": data.get("noAutoGroups", False)}


def quotas(raw):
    require(isinstance(raw, list), "quota_schema_changed")
    fields = {"provider", "kind", "plan", "balance", "readAt", "until"}
    wf = {"name", "used", "remaining", "resetsAt", "display", "amount", "limit", "unit"}
    return [{**{k: v for k, v in q.items() if k in fields},
             "error_present": bool(q.get("error")),
             "windows": [{k: v for k, v in w.items() if k in wf} for w in q.get("windows", [])]}
            for q in raw]


def validate(policy, data, creating=True):
    require(isinstance(policy, dict) and set(policy) == {"schema", "groups"}, "policy_fields")
    require(policy["schema"] == "magpie-route-policy.v1", "policy_schema")
    require(isinstance(policy["groups"], list) and 0 < len(policy["groups"]) <= 8, "group_count")
    known = {p["id"] + "/" + m for p in data.get("providers", []) if not p.get("off") and not p.get("hidden") for m in p.get("models", [])}
    ids = set()
    existing = {g.get("id") for g in data.get("groups", [])} | {g.get("name") for g in data.get("groups", [])}
    for g in policy["groups"]:
        require(isinstance(g, dict) and set(g) == {"id", "members", "routing", "stays", "rules"}, "group_fields")
        gid = g["id"]
        require(isinstance(gid, str) and re.fullmatch(r"mpr-[a-z0-9]+(?:-[a-z0-9]+)*", gid), "group_id_must_use_mpr_prefix")
        require(gid not in ids, "duplicate_group")
        require(not creating or gid not in existing, "existing_group_collision")
        ids.add(gid)
        require(g["routing"] in ("order", "smart", "usage", "pace"), "routing_not_supported")
        require(g["stays"] in ("auto", "session", "turn"), "stays_not_supported")
        ms = g["members"]
        require(isinstance(ms, list) and 0 < len(ms) <= 12 and all(isinstance(m, str) for m in ms), "members_invalid")
        require(len(set(ms)) == len(ms), "duplicate_member")
        require(all(m in known and not any(c in m for c in [",", "\n", "\r", "\x00"]) for m in ms), "unknown_disabled_or_pattern_model")
        require(isinstance(g["rules"], list) and len(g["rules"]) <= 20, "rules_invalid")
        for rule in g["rules"]:
            require(isinstance(rule, dict) and set(rule) <= {"use", "pause", "time", "effort", "tokens", "images", "compact"}, "rule_fields")
            require(("use" in rule) != ("pause" in rule), "rule_needs_one_action")
            require(rule.get("use", rule.get("pause")) in ms, "rule_member_missing")
            require(len(rule) > 1, "unconditional_rule")
            if "pause" in rule:
                require(set(rule) == {"pause", "time"}, "pause_requires_time_only")
            if "time" in rule:
                require(isinstance(rule["time"], str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d-(?:[01]\d|2[0-3]):[0-5]\d", rule["time"]), "time_invalid")
                require(rule["time"][:5] != rule["time"][6:], "empty_time_window")
            if "effort" in rule:
                require(rule["effort"] in ("on", "low", "medium", "high", "xhigh", "max"), "effort_invalid")
            if "tokens" in rule:
                require(type(rule["tokens"]) is int and rule["tokens"] > 0, "tokens_invalid")
            for k in ("images", "compact"):
                if k in rule:
                    require(rule[k] is True, "flag_must_be_true")
    return policy


def commands(group):
    gid = group["id"]
    yield ["group", "add", gid, "models=" + ",".join(group["members"]), "routing=" + group["routing"], "stays=" + group["stays"]]
    for r in group["rules"]:
        yield ["group", "rule", "add", gid] + [k if v is True else k + "=" + str(v) for k, v in r.items()]


def normalize_actual(g):
    require(set(g) <= {"id", "name", "members", "routing", "stays", "affinity", "rules"}, "unexpected_created_group_fields")
    require(g.get("name", g["id"]) == g["id"], "created_group_name_changed")
    rules = []
    for r in g.get("rules", []):
        require(set(r) <= {"use", "pause", "time", "effort", "tokens", "images", "compact"}, "unexpected_persisted_rule_fields")
        q = {k: v for k, v in r.items() if k not in {"pause", "use", "time"}}
        q["pause" if r.get("pause") else "use"] = r["use"]
        if "time" in r:
            q["time"] = r["time"]["from"] + "-" + r["time"]["to"]
        rules.append(q)
    require(not any(g.get(k) for k in ("off", "disabled", "hidden")), "created_group_not_fully_enabled")
    return {"id": g["id"], "members": g.get("members"), "routing": g.get("routing") or "smart", "stays": g.get("stays") or g.get("affinity") or "auto", "rules": rules}


def verify_state(before, after, completed):
    target_ids = {g["id"] for g in completed}
    rest = dict(after)
    rest["groups"] = [g for g in after.get("groups", []) if g["id"] not in target_ids]
    reference = dict(before)
    reference.setdefault("groups", [])
    require(rest == reference, "unrelated_configuration_changed")
    for desired in completed:
        actual = [g for g in after.get("groups", []) if g["id"] == desired["id"]]
        require(len(actual) == 1 and normalize_actual(actual[0]) == desired, "postwrite_readback_mismatch")


def make_plan(policy, path):
    content = Path(path).read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    data = parse_json(content)
    validate(policy, data)
    version = cli(["--version"]).strip()
    require(sha(path) == digest, "configuration_drift_during_plan")
    return {"schema": "magpie-route-plan.v1", "created_epoch": time.time(), "config_sha256": digest,
            "config_path": str(path.resolve()), "cli_version": version,
            "policy": policy, "commands": [c for g in policy["groups"] for c in commands(g)],
            "scope": "create_groups_only_no_agent_switch", "clock": str(dt.datetime.now().astimezone().tzinfo)}


def apply(plan, path):
    require(plan.get("schema") == "magpie-route-plan.v1", "plan_schema")
    require(0 <= time.time() - plan["created_epoch"] <= 900, "plan_expired")
    require(cli(["--version"]).strip() == plan["cli_version"], "cli_version_changed")
    content = Path(path).read_bytes()
    require(str(path.resolve()) == plan["config_path"] and hashlib.sha256(content).hexdigest() == plan["config_sha256"], "configuration_drift")
    before = parse_json(content)
    policy = validate(plan["policy"], before)
    require(plan["commands"] == [c for g in policy["groups"] for c in commands(g)], "plan_commands_tampered")
    completed = []
    expected_hash = plan["config_sha256"]
    for g in policy["groups"]:
        for i, command in enumerate(commands(g)):
            require(sha(path) == expected_hash, "configuration_drift_between_commands")
            cli(command)
            desired = dict(g, rules=g["rules"][:i])
            after_bytes = Path(path).read_bytes()
            after = parse_json(after_bytes)
            verify_state(before, after, completed + [desired])
            expected_hash = hashlib.sha256(after_bytes).hexdigest()
        completed.append(g)
    return {"status": "CONFIG_READBACK_VERIFIED", "groups": [g["id"] for g in completed],
            "config_after_sha256": expected_hash, "inference": "NOT_VERIFIED", "agent_switch": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    inv = sub.add_parser("inspect")
    inv.add_argument("--live", action="store_true", help="ask Magpie quota; may refresh providers/plugins")
    inv.add_argument("--output", required=True)
    pl = sub.add_parser("plan")
    pl.add_argument("--policy", required=True)
    pl.add_argument("--output", required=True)
    ap = sub.add_parser("apply")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--plan-sha256", required=True)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--receipt", required=True)
    args = p.parse_args()
    path = config_path()
    if args.command == "inspect":
        out = inventory(load(path))
        if args.live:
            out["quotas"] = quotas(json.loads(cli(["quota", "--json"])))
        save_new(args.output, out)
        print(json.dumps({"status": "OBSERVED", "output": args.output}))
    elif args.command == "plan":
        out = make_plan(load(args.policy), path)
        save_new(args.output, out)
        print(json.dumps({"status": "PLANNED_NOT_APPLIED", "output": args.output, "sha256": sha(args.output)}))
    else:
        require(args.execute, "apply_requires_execute")
        require(not Path(args.receipt).exists(), "receipt_exists")
        plan_bytes = Path(args.plan).read_bytes()
        require(hashlib.sha256(plan_bytes).hexdigest() == args.plan_sha256, "plan_sha_mismatch")
        plan = parse_json(plan_bytes)
        lock = path.parent / ".magpie-optimizer-writer.lock"
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        try:
            # Reserve a writable journal before any gateway mutation. A killed
            # process leaves RUNNING rather than silently losing its receipt.
            save_new(args.receipt, {"status": "RUNNING_INSPECT_BEFORE_RETRY", "plan_sha256": args.plan_sha256})
            try:
                result = apply(plan, path)
            except Exception:
                update_receipt(args.receipt, {"status": "STOPPED_INSPECT_PARTIAL_STATE", "plan_sha256": args.plan_sha256,
                                             "config_sha256": sha(path) if path.exists() else None, "auto_retry": False})
                raise
            update_receipt(args.receipt, dict(result, plan_sha256=args.plan_sha256))
        finally:
            lock.unlink()
        print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except (Refused, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as e:
        # Do not echo upstream payloads, raw JSON, file contents or CLI stderr.
        reason = str(e) if isinstance(e, Refused) else type(e).__name__
        print(json.dumps({"status": "REFUSED", "reason": reason}), file=sys.stderr)
        sys.exit(2)
