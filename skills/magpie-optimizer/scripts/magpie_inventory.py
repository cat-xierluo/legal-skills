#!/usr/bin/env python3
"""Read-only, desensitized Magpie inventory (agents / providers / groups / risks).

Purpose
    Produce a structured snapshot of this machine's Magpie setup so the
    operator can confirm the routing design and spot single-source tiers,
    dead members and unset account orders before publishing or paying.

Read-only boundary
    * Reads only the Magpie CLI read-only subcommands: ``--version``, ``ls``,
      ``providers``, ``groups``, ``group <id>``, ``models <agent>``,
      ``accounts --json``.
    * Reads only ``providers.json``, ``settings.json`` inside the Magpie
      config dir, plus an optional local profile file.
    * Never writes Magpie configuration, never switches a provider or group,
      never logs in, never copies a credential and never installs anything.

No model requests
    This script never asks the gateway for a model response and never spends
    quota. ``--gateway`` is recorded as a note only; no socket is opened.

Desensitization
    Account identifiers are masked (see :func:`mask_account`), provider ``key``
    values are never emitted, and agent config paths, rule intents, prompts,
    session titles, quota/balance readings and proxy URLs are omitted.

Severity convention
    Risks use exactly ``info`` / ``warn`` / ``high``. The published inventory
    example mentions high/medium/low but notes that the severity is decided
    per run against the cost boundary; this script standardises on
    info/warn/high so the schema stays stable across machines.

Exit codes
    0 = the scan completed and the report is usable, findings included; the
    findings themselves live in ``risks`` and are never a scan failure;
    1 = the report lost a required section and is not usable;
    2 = usage error or read error (one ``{"status":"REFUSED","reason":"..."}``
    line on stderr, never the upstream payload).

    A degraded machine (no CLI, no configuration) still exits 0: the report
    then carries empty collections plus the reason in ``notes``.
"""
import sys

sys.dont_write_bytecode = True

import argparse
import concurrent.futures
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

ThreadPoolExecutor = concurrent.futures.ThreadPoolExecutor

SCHEMA = "magpie-inventory.v1"
SEVERITIES = ("info", "warn", "high")
REDACTED = "***redacted***"

# Values the CLI prints in the model column that do not name a concrete model.
NON_MODEL_VALUES = {
    "", "-", "--", "—", "–", "n/a", "na", "none", "null", "unknown",
    "cli not found", "provider magpie", "auth custom", "default",
}

EFFORT_NAMES = {"low", "medium", "high", "xhigh", "max", "ultra", "none", "auto", "on"}
EFFORT_ORDER = ("low", "medium", "high", "xhigh", "max", "ultra")

PATH_TAIL_RE = re.compile(
    r"\s+(~?/[^\s]*(?:\s[^\s]*)*\.(?:json|jsonc|toml|yaml|yml|ini|cfg|conf|txt|md))$")
MODEL_ENTRY_RE = re.compile(r"^\s+(?P<id>[\w.\-]+/[\w.\-]+)(?:\s{2,}(?P<rest>.*))?$")
EFFORT_TOKEN_RE = re.compile(r"^[a-z]+(?:/[a-z]+)*$")


class Refused(Exception):
    """Usage or read error; the reason is a short code, never upstream text."""


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


def load_json_file(path):
    return parse_json(Path(path).read_bytes())


# --------------------------------------------------------------------------
# Pure functions (public contract; tests import these directly).
# --------------------------------------------------------------------------

def mask_account(value, labels=None):
    """Hide every identity; optional labels are local to one provider/scan."""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    if labels is None:
        return REDACTED
    if text not in labels:
        labels[text] = "account-" + str(len(labels) + 1)
    return labels[text]


def _source_count(member, servable, group_index, seen):
    if member in seen:
        return 0
    if member in group_index:
        nested = seen | {member}
        total = 0
        for sub in group_index[member]:
            total += _source_count(sub, servable, group_index, nested)
        return total
    return 1 if servable.get(member, False) else 0


def single_source_tiers(members, servable, group_index):
    """Return the members that make up a single-source tier.

    ``servable`` maps ``'provider/model'`` to whether that member can serve
    traffic right now. ``group_index`` maps ``'group/<id>'`` to its members so
    nested groups can be expanded; a nested group contributes as many sources
    as it has servable members, and a nested group that cannot be resolved
    contributes zero.

    A tier that exposes more than one servable source is not a single-source
    tier, so nothing is returned for it. When the tier exposes at most one
    source, the returned list holds the members whose own source count is
    exactly one, in input order.
    """
    servable = servable or {}
    group_index = group_index or {}
    members = list(members or [])
    total = 0
    for member in members:
        total += _source_count(member, servable, group_index, frozenset())
    if total > 1:
        return []
    return [member for member in members
            if _source_count(member, servable, group_index, frozenset()) == 1]


def account_order_unset(providers):
    """Return the ids of providers that have several accounts but no order.

    ``providers`` is the provider list of ``providers.json``. A provider is
    considered multi-account when ``accountConcurrency`` holds at least two
    account entries or ``accountOrder`` holds at least two entries. A present
    and non-empty ``accountOrder`` counts as an explicit order.
    """
    out = []
    for provider in providers or []:
        if not isinstance(provider, dict):
            continue
        pid = provider.get("id")
        if not isinstance(pid, str) or not pid:
            continue
        concurrency = provider.get("accountConcurrency")
        order = provider.get("accountOrder")
        concurrency_count = len(concurrency) if isinstance(concurrency, dict) else 0
        order_count = len(order) if isinstance(order, list) else 0
        if not (concurrency_count >= 2 or order_count >= 2):
            continue
        order_set = isinstance(order, list) and order_count > 0
        if not order_set:
            out.append(pid)
    return out


# --------------------------------------------------------------------------
# Small helpers.
# --------------------------------------------------------------------------

def default_config_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base).expanduser() / "magpie"


def is_concrete_model(value):
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    if text.lower() in NON_MODEL_VALUES:
        return False
    # The CLI prints literal provider markers such as "provider magpie" or
    # "provider -" in the model column; they name no model.
    if text.lower().startswith("provider "):
        return False
    return True


def clean_effort(value):
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text.lower() in NON_MODEL_VALUES:
        return None
    return text


def sort_efforts(values):
    known = [e for e in EFFORT_ORDER if e in values]
    extra = sorted(e for e in values if e not in EFFORT_ORDER)
    return known + extra


def save_private(path, text):
    """Write the report with 0600 permissions, creating parent dirs."""
    target = Path(path).expanduser()
    if target.parent and not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(text)
        handle.write("\n")
    try:
        os.chmod(str(target), 0o600)
    except OSError:
        pass


def run_cli(binary, args, timeout=90):
    """Run a read-only Magpie CLI command; return stdout or None on failure."""
    try:
        proc = subprocess.run([binary, *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def load_optional(path):
    try:
        if not Path(path).is_file():
            return None
        return load_json_file(path)
    except (OSError, ValueError, Refused):
        return None


# --------------------------------------------------------------------------
# CLI text parsing.
# --------------------------------------------------------------------------

def split_columns(text):
    return [part.strip() for part in re.split(r"\s{2,}", text.strip()) if part.strip()]


def parse_agent_row(line):
    """Parse one ``magpie ls`` row into agent fields."""
    body = PATH_TAIL_RE.sub("", line.rstrip()).rstrip()
    if not body.strip():
        return None
    segments = [seg.strip() for seg in body.split("·")]
    columns = split_columns(segments[0])
    if not columns:
        return None
    if len(columns) >= 2:
        name = " ".join(columns[:-1])
        model = columns[-1]
    else:
        name = columns[0]
        model = ""
    agent = {"name": name, "model": model, "effort": None,
             "subagent_model": None, "subagent_effort": None}
    for segment in segments[1:]:
        segment = segment.strip()
        match = re.match(r"^(?:effort|thinking)\s+(.+)$", segment)
        if match:
            agent["effort"] = clean_effort(match.group(1))
            continue
        match = re.match(r"^subagent model\s+(.+)$", segment)
        if match:
            agent["subagent_model"] = match.group(1).strip()
            continue
        match = re.match(r"^subagent effort\s+(.+)$", segment)
        if match:
            agent["subagent_effort"] = clean_effort(match.group(1))
    return agent


def parse_agent_list(text):
    agents = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        if not line.startswith((" ", "\t")):
            continue
        agent = parse_agent_row(line)
        if agent and agent["name"]:
            agents.append(agent)
    return agents


def parse_provider_rows(text):
    """Parse ``magpie providers`` rows into id / display name / state."""
    rows = []
    for line in (text or "").splitlines():
        if not line.strip() or not line.startswith((" ", "\t")):
            continue
        columns = split_columns(line)
        if len(columns) < 2:
            continue
        name, pid = columns[0], columns[1]
        if not re.fullmatch(r"[A-Za-z0-9][\w.\-]*", pid):
            continue
        status = " ".join(columns[3:4]) if len(columns) > 3 else ""
        account = None
        switched_off = "switched off" in status
        if "signed in as" in status:
            account = status.split("signed in as", 1)[1].strip()
        rows.append({"id": pid, "name": name, "off": switched_off, "account": account})
    return rows


def parse_group_rows(text):
    """Parse ``magpie groups`` rows: id, routing, stays, members, not-served."""
    rows = []
    pattern = re.compile(r"^\s+(?P<name>\S.*?)\s{2,}(?P<id>group/\S+)\s{2,}(?P<rest>.*)$")
    for line in (text or "").splitlines():
        match = pattern.match(line.rstrip())
        if not match:
            continue
        rest = match.group("rest")
        parts = re.split(r"\s{2,}", rest.strip())
        routing_segment = parts[0] if parts else ""
        member_segment = parts[1] if len(parts) > 1 else ""
        routing, stays, rules_hint = None, None, None
        for item in routing_segment.split("·"):
            item = item.strip()
            if not item:
                continue
            if item.startswith("stays "):
                stays = item[len("stays "):].strip()
            elif re.fullmatch(r"\d+\s+rules?", item):
                rules_hint = int(item.split()[0])
            elif routing is None:
                routing = item
        member_segment = re.split(r"←", member_segment)[0]
        members, not_served = [], {}
        for raw in member_segment.split("→"):
            raw = raw.strip()
            if not raw:
                continue
            reason = None
            notice = re.search(r"\((?:not served:[^)]*)\)\s*$", raw)
            if notice:
                reason = notice.group(0).strip("() ")
                raw = raw[:notice.start()].strip()
            if raw:
                members.append(raw)
                if reason:
                    not_served[raw] = reason
        rows.append({"name": match.group("name").strip(), "id": match.group("id"),
                     "routing": routing, "stays": stays, "rules_hint": rules_hint,
                     "members": members, "not_served": not_served})
    return rows


def parse_group_detail(text):
    """Parse ``magpie group <id>`` detail into routing / stays / members / rules."""
    detail = {"routing": None, "stays": None, "members": [], "rules": 0}
    section = None
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        body = line.strip()
        if indent <= 2:
            match = re.match(r"^(?P<key>[A-Za-z_][\w ]*?)\s{2,}(?P<rest>.*)$", body)
            if match:
                key = match.group("key").strip()
                rest = match.group("rest").strip()
                section = key
                if key == "routing":
                    detail["routing"] = rest.split()[0] if rest else None
                elif key == "stays":
                    detail["stays"] = rest.split()[0] if rest else None
                elif key == "models":
                    member = re.match(r"^\d+\s+(\S+)", rest)
                    if member:
                        detail["members"].append(member.group(1))
                elif key == "rules":
                    numbered = re.match(r"^(\d+)\s+", rest)
                    if numbered:
                        detail["rules"] = max(detail["rules"], int(numbered.group(1)))
                continue
            section = None
            continue
        if section == "models":
            member = re.match(r"^(\d+)\s+(\S+)", body)
            if member:
                detail["members"].append(member.group(2))
        elif section == "rules":
            numbered = re.match(r"^(\d+)\s+", body)
            if numbered:
                detail["rules"] = max(detail["rules"], int(numbered.group(1)))
    return detail


def parse_model_entries(text):
    """Parse ``magpie models <agent>``: model entries plus their effort levels."""
    entries = []
    for line in (text or "").splitlines():
        match = MODEL_ENTRY_RE.match(line.rstrip())
        if not match:
            continue
        model_id = match.group("id")
        rest = match.group("rest") or ""
        efforts = []
        for token in rest.split():
            token = token.strip()
            if EFFORT_TOKEN_RE.match(token) and all(part in EFFORT_NAMES for part in token.split("/")):
                efforts = token.split("/")
        entries.append({"id": model_id, "efforts": efforts})
    return entries


# --------------------------------------------------------------------------
# Risk helpers.
# --------------------------------------------------------------------------

def make_risk(code, severity, detail, where):
    return {"code": code, "severity": severity, "detail": detail, "where": where}


def find_profile(script_dir):
    for base in (script_dir.parent, Path.cwd()):
        candidate = base / "config" / "profile.local.json"
        if candidate.is_file():
            return candidate
    return None


def profile_expensive_models(profile):
    if not isinstance(profile, dict):
        return []
    found = []
    for key in ("expensive_models", "expensiveModels", "costly_models", "high_cost_models",
                "premium_models", "expensive"):
        value = profile.get(key)
        if isinstance(value, list):
            found += [item for item in value if isinstance(item, str)]
    for key in ("cost", "costs", "cost_profile"):
        value = profile.get(key)
        if isinstance(value, dict):
            for sub in ("expensive", "high", "premium", "costly"):
                items = value.get(sub)
                if isinstance(items, list):
                    found += [item for item in items if isinstance(item, str)]
    return found


def profile_aux_routes(profile):
    if not isinstance(profile, dict):
        return {}
    # magpie-profile.v1 nests auxiliary targets under the top-level profile.
    value = profile.get("auxiliary_routes")
    if isinstance(value, dict):
        return {k: v for k, v in value.items() if isinstance(v, str)}
    return {}


def profile_main_group(profile):
    if not isinstance(profile, dict):
        return None
    candidates = [profile]
    entry = profile.get("entry")
    if isinstance(entry, dict):
        candidates.insert(0, entry)
    for source in candidates:
        for key in ("main_group", "mainGroup", "entry_group", "entryGroup", "primary_group"):
            value = source.get(key)
            if isinstance(value, str) and value:
                return value
    return None


# --------------------------------------------------------------------------
# Inventory assembly.
# --------------------------------------------------------------------------

def build_agents(cli_path, rows, notes, deadline):
    """Parse every agent row and enrich it with the read-only per-agent views."""
    agents = []
    listings = {}
    details = {}
    if cli_path and rows:
        # The Magpie CLI is a separate process, so threads help; the calls stay
        # read-only and independent.
        with ThreadPoolExecutor(max_workers=6) as pool:
            detail_futures = {row["name"]: pool.submit(run_cli, cli_path, [row["name"]])
                               for row in rows}
            model_futures = {row["name"]: pool.submit(run_cli, cli_path, ["models", row["name"]])
                             for row in rows}
            for row in rows:
                name = row["name"]
                detail = parse_agent_row(detail_futures[name].result() or "")
                if detail and detail["name"]:
                    merged = dict(row)
                    for field in ("model", "effort", "subagent_model", "subagent_effort"):
                        if detail.get(field):
                            merged[field] = detail[field]
                    row = merged
                listing = model_futures[name].result()
                if listing is not None:
                    listings[name] = listing
                if deadline and time_exceeded(deadline):
                    notes.append("只读盘点因时间预算提前结束，部分 Agent 细节未补齐。")
                    break
    for row in rows:
        name = row["name"]
        model = row.get("model")
        if not is_concrete_model(model):
            model = None
        sub_model = row.get("subagent_model")
        if not is_concrete_model(sub_model):
            sub_model = None
        visible = len(parse_model_entries(listings[name])) if name in listings else None
        agents.append({
            "name": name,
            "model": model,
            "effort": row.get("effort"),
            "subagent_model": sub_model,
            "subagent_effort": row.get("subagent_effort"),
            "gateway_routed": bool(model) and ("group/" in model),
            "visible_models": visible,
        })
    return agents, listings


def time_exceeded(deadline):
    return time.monotonic() > deadline


def build_providers(cli_path, providers_json, accounts_json, cli_rows, settings, group_index, notes):
    by_id = {}
    for provider in (providers_json or {}).get("providers", []):
        if isinstance(provider, dict) and isinstance(provider.get("id"), str):
            by_id[provider["id"]] = provider
    cli_by_id = {row["id"]: row for row in cli_rows}

    account_labels = {}
    account_counts = {}
    identity_labels = {}
    for entry in accounts_json or []:
        if not isinstance(entry, dict):
            continue
        pid = entry.get("agent")
        user = entry.get("user")
        if not isinstance(pid, str):
            continue
        account_counts[pid] = account_counts.get(pid, 0) + 1
        label = mask_account(user, identity_labels.setdefault(pid, {}))
        if label:
            account_labels.setdefault(pid, [])
            if label not in account_labels[pid]:
                account_labels[pid].append(label)

    providers = []
    ids = list(by_id.keys())
    for pid in cli_by_id:
        if pid not in ids:
            ids.append(pid)
    for pid in ids:
        provider = by_id.get(pid, {})
        cli_row = cli_by_id.get(pid, {})
        models = provider.get("models")
        models = models if isinstance(models, list) else []
        labels = list(account_labels.get(pid, []))
        if not labels and cli_row.get("account"):
            fallback = mask_account(cli_row["account"], identity_labels.setdefault(pid, {}))
            if fallback:
                labels = [fallback]
        count = account_counts.get(pid, len(labels))
        off = bool(provider.get("off")) or bool(cli_row.get("off"))
        name = cli_row.get("name") or provider.get("name") or pid
        if not isinstance(name, str) or not name:
            name = pid
        providers.append({
            "id": pid,
            "name": name,
            "models": len(models),
            "accounts": count,
            "account_labels": labels,
            "multi_account": count >= 2,
            "enabled": not off,
            "account_order_set": bool(isinstance(provider.get("accountOrder"), list)
                                      and provider.get("accountOrder")),
            "capabilities": {
                "vision": provider_supports_vision(pid, settings, group_index),
                "reasoning_efforts": [],
            },
        })
    return providers, by_id


def provider_supports_vision(pid, settings, group_index):
    """True when the configured vision model belongs to this provider."""
    if not isinstance(settings, dict):
        return False
    vision = settings.get("vision")
    if not isinstance(vision, str) or not vision:
        return False
    references = [vision]
    if vision.startswith("group/"):
        members = group_index.get(vision) or []
        references += [m for m in members if "/" in m]
    for reference in references:
        if "/" not in reference:
            continue
        provider_id = reference.split("/", 1)[0]
        if provider_id == pid:
            return True
    return False


def apply_provider_efforts(providers, effort_map):
    for provider in providers:
        efforts = effort_map.get(provider["id"], set())
        provider["capabilities"]["reasoning_efforts"] = sort_efforts(efforts)


def build_groups(cli_path, cli_rows, providers_json, servable, group_index, notes):
    config_groups = {}
    for group in (providers_json or {}).get("groups", []):
        if not isinstance(group, dict) or not isinstance(group.get("id"), str):
            continue
        if group.get("hidden"):
            # Removed records: the CLI does not list them either.
            continue
        config_groups[group["id"]] = group

    groups = []
    seen = set()
    details = {}
    if cli_path and cli_rows:
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {row["id"]: pool.submit(run_cli, cli_path, ["group", row["id"].split("/", 1)[1]])
                       for row in cli_rows}
            for row in cli_rows:
                raw = futures[row["id"]].result()
                if raw:
                    details[row["id"]] = parse_group_detail(raw)
    for row in cli_rows:
        gid = row["id"]
        seen.add(gid)
        detail = details.get(gid) or {"routing": None, "stays": None, "members": [], "rules": 0}
        routing = detail.get("routing") or row.get("routing")
        stays = detail.get("stays") or row.get("stays")
        members = detail.get("members") or row.get("members") or []
        config_members = config_groups.get(gid.split("/", 1)[1], {}).get("members")
        if not members and isinstance(config_members, list):
            members = [m for m in config_members if isinstance(m, str)]
        rules = detail.get("rules") or row.get("rules_hint") or 0
        if not rules:
            config_rules = config_groups.get(gid.split("/", 1)[1], {}).get("rules")
            rules = len(config_rules) if isinstance(config_rules, list) else 0
        tiers = single_source_tiers(members, servable, group_index)
        groups.append({
            "id": gid,
            "routing": routing,
            "stays": stays,
            "members": len(members),
            "rules": rules,
            "single_source_tiers": tiers,
        })
    for gid, group in config_groups.items():
        full = "group/" + gid
        if full in seen:
            continue
        members = group.get("members")
        members = [m for m in members if isinstance(m, str)] if isinstance(members, list) else []
        rules = group.get("rules")
        groups.append({
            "id": full,
            "routing": group.get("routing"),
            "stays": group.get("affinity") or group.get("stays"),
            "members": len(members),
            "rules": len(rules) if isinstance(rules, list) else 0,
            "single_source_tiers": single_source_tiers(members, servable, group_index),
        })
    return groups


def build_servable_map(cli_rows, providers_json, group_index):
    """Decide which members can serve traffic right now."""
    by_id = {}
    for provider in (providers_json or {}).get("providers", []):
        if isinstance(provider, dict) and isinstance(provider.get("id"), str):
            by_id[provider["id"]] = provider
    cli_off = {row["id"] for row in cli_rows if row.get("off")}
    not_served = {}
    for row in cli_rows:
        for member, reason in row.get("not_served", {}).items():
            not_served[member] = reason

    servable = {}
    reasons = {}
    for group_members in group_index.values():
        for member in group_members:
            if member in servable:
                continue
            if member in not_served:
                servable[member] = False
                reasons[member] = "CLI 报告不可服务"
                continue
            if "/" not in member:
                servable[member] = False
                reasons[member] = "成员格式无法判定"
                continue
            pid, model = member.split("/", 1)
            provider = by_id.get(pid)
            if provider is None:
                servable[member] = True
                reasons[member] = ""
                continue
            if pid in cli_off or provider.get("off"):
                servable[member] = False
                reasons[member] = "供应商已关闭"
                continue
            if provider.get("hidden"):
                servable[member] = False
                reasons[member] = "供应商记录已隐藏"
                continue
            delisted = provider.get("delisted")
            if isinstance(delisted, list) and model in delisted:
                servable[member] = False
                reasons[member] = "模型已下架"
                continue
            models = provider.get("models")
            if isinstance(models, list) and models and model not in models:
                servable[member] = False
                reasons[member] = "模型未暴露"
                continue
            servable[member] = True
            reasons[member] = ""
    return servable, reasons


def collect_efforts(listings):
    """Map provider id -> effort levels seen in cached ``magpie models`` listings."""
    effort_map = {}
    for listing in listings.values():
        for entry in parse_model_entries(listing):
            pid = entry["id"].split("/", 1)[0]
            if pid == "group" or not entry["efforts"]:
                continue
            effort_map.setdefault(pid, set()).update(entry["efforts"])
    return effort_map


# --------------------------------------------------------------------------
# Scan.
# --------------------------------------------------------------------------

def scan(args):
    notes = []
    config_dir = Path(args.config_dir).expanduser() if args.config_dir else default_config_dir()
    script_dir = Path(__file__).resolve().parent

    cli_path = shutil.which("magpie")
    version = None
    agent_rows, provider_rows, group_rows = [], [], []
    accounts_json = None
    if cli_path:
        # The Magpie CLI is a separate process per call; run the read-only
        # commands concurrently so one scan stays inside a usable time budget.
        with ThreadPoolExecutor(max_workers=6) as pool:
            version_future = pool.submit(run_cli, cli_path, ["--version"], 20)
            agents_future = pool.submit(run_cli, cli_path, ["ls"])
            providers_future = pool.submit(run_cli, cli_path, ["providers"])
            groups_future = pool.submit(run_cli, cli_path, ["groups"])
            accounts_future = pool.submit(run_cli, cli_path, ["accounts", "--json"])
            raw_version = version_future.result()
            raw_agents = agents_future.result()
            raw_providers = providers_future.result()
            raw_groups = groups_future.result()
            raw_accounts = accounts_future.result()
        if raw_version:
            version = raw_version.strip().split()[-1] if raw_version.strip() else None
        if raw_agents is None:
            notes.append("magpie ls 读取失败，Agent 清单为空。")
        else:
            agent_rows = parse_agent_list(raw_agents)
        if raw_providers is None:
            notes.append("magpie providers 读取失败，供应商状态仅基于配置文件。")
        else:
            provider_rows = parse_provider_rows(raw_providers)
        if raw_groups is None:
            notes.append("magpie groups 读取失败，路由组仅基于配置文件。")
        else:
            group_rows = parse_group_rows(raw_groups)
        if raw_accounts is None:
            notes.append("magpie accounts --json 读取失败，账号数量按可见标签统计。")
        else:
            try:
                parsed_accounts = parse_json(raw_accounts)
                accounts_json = parsed_accounts if isinstance(parsed_accounts, list) else []
            except (ValueError, Refused):
                accounts_json = []
                notes.append("magpie accounts --json 返回内容无法解析，账号数量按可见标签统计。")
    else:
        notes.append("未检测到 Magpie CLI，仅基于配置文件盘点。")

    providers_json = load_optional(config_dir / "providers.json")
    if providers_json is None:
        notes.append("未读到 providers.json，仅基于 CLI 输出盘点。")
    settings = load_optional(config_dir / "settings.json")
    if settings is None:
        notes.append("未读到 settings.json，视觉模型等能力标记按不可判定处理。")
    if providers_json is None and not cli_path:
        notes.append("配置与 CLI 均不可用，本次盘点没有任何数据来源。")

    # Group index used for nested-group expansion.
    group_index = {}
    for row in group_rows:
        group_index[row["id"]] = list(row.get("members") or [])
    for group in (providers_json or {}).get("groups", []):
        if not isinstance(group, dict) or not isinstance(group.get("id"), str):
            continue
        if group.get("hidden"):
            continue
        full = "group/" + group["id"]
        members = group.get("members")
        if isinstance(members, list) and full not in group_index:
            group_index[full] = [m for m in members if isinstance(m, str)]

    servable, dead_reasons = build_servable_map(group_rows, providers_json, group_index)

    providers, providers_by_id = build_providers(cli_path, providers_json, accounts_json,
                                                 provider_rows, settings, group_index, notes)

    deadline = time.monotonic() + 240
    agents, model_listings = build_agents(cli_path, agent_rows, notes, deadline)
    if cli_path:
        effort_map = collect_efforts(model_listings)
        apply_provider_efforts(providers, effort_map)

    groups = build_groups(cli_path, group_rows, providers_json, servable, group_index, notes)

    risks = build_risks(groups, providers, providers_by_id, servable, dead_reasons,
                        group_index, providers_json, notes, script_dir, settings)

    notes.append("严重度统一使用 info/warn/high 三档；示例文件中的 high/medium/low 由盘点者按当次成本边界判定。")
    if args.gateway:
        notes.append("已提供网关地址，仅作标注记录；本次盘点未向网关发起任何模型请求。")

    return {
        "schema": SCHEMA,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "magpie_version": version,
        "agents": agents,
        "providers": providers,
        "groups": groups,
        "risks": risks,
        "notes": notes,
    }


def build_risks(groups, providers, providers_by_id, servable, dead_reasons, group_index,
                 providers_json, notes, script_dir, settings):
    risks = []
    group_by_id = {group["id"]: group for group in groups}
    member_lists = {}
    for row in group_index.items():
        member_lists[row[0]] = row[1]

    for group in groups:
        gid = group["id"]
        members = member_lists.get(gid, [])
        total = 0
        for member in members:
            total += effective_sources(member, servable, group_index, frozenset())
        if total <= 1:
            risks.append(make_risk(
                "SINGLE_SOURCE_TIER", "warn",
                "能力层只有 %d 个可服务来源，打满即整层失效。" % total, gid))
        for member in members:
            if servable.get(member, True):
                continue
            reason = dead_reasons.get(member) or "当前不可服务"
            risks.append(make_risk(
                "DEAD_MEMBER", "warn",
                "成员 %s 当前不可服务（%s），会产生无效尝试。" % (member, reason), gid))

    for pid in account_order_unset((providers_json or {}).get("providers", [])):
        risks.append(make_risk(
            "ACCOUNT_ORDER_UNSET", "warn",
            "该供应商有多个账号但未设置 accountOrder，Magpie 按余量智能挑选，可能与个人账号优先的意图相反。",
            pid))

    # Provider level cross-layer fallback: only reported when the field exists.
    fallback_fields = [p for p in (providers_json or {}).get("providers", [])
                       if isinstance(p, dict) and isinstance(p.get("fallback"), str)]
    if not fallback_fields:
        notes.append("provider 级 fallback 字段未在配置中暴露，跨层回退未检查。")
    else:
        for provider in fallback_fields:
            target = provider["fallback"]
            if target.startswith("group/") and target != provider.get("id"):
                risks.append(make_risk(
                    "CROSS_LAYER_FALLBACK", "warn",
                    "供应商级 fallback 指向 %s，跨层接管后成本与归因口径不一致。" % target,
                    provider.get("id")))

    profile_path = find_profile(script_dir)
    profile = load_optional(profile_path) if profile_path else None
    if profile is None:
        notes.append("未找到本地 profile，昂贵模型兜底与辅助路由未评估。")
    else:
        expensive = profile_expensive_models(profile)
        if not expensive:
            notes.append("本地 profile 未标记昂贵模型，昂贵模型兜底未评估。")
        else:
            for group in groups:
                gid = group["id"]
                members = member_lists.get(gid, [])
                for index, member in enumerate(members):
                    if member not in expensive or index == 0:
                        continue
                    risks.append(make_risk(
                        "EXPENSIVE_FALLBACK", "high",
                        "成员 %s 被本地 profile 标记为昂贵模型，且位于第 %d 位兜底位。"
                        % (member, index + 1), gid))
        aux = profile_aux_routes(profile)
        main_group = profile_main_group(profile)
        if aux and main_group and main_group in group_by_id:
            members = set(member_lists.get(main_group, []))
            settings_values = {k: v for k, v in (settings or {}).items()
                               if isinstance(v, str)}
            for kind, target in aux.items():
                if target in members:
                    continue
                if target not in settings_values.values():
                    continue
                risks.append(make_risk(
                    "AUX_CALLS_OUTSIDE_GROUP", "info",
                    "辅助调用 %s 指向 %s，不在主入口组 %s 内。"
                    % (kind, target, main_group), main_group))
    return risks


def effective_sources(member, servable, group_index, seen):
    if member in seen:
        return 0
    if member in group_index:
        nested = seen | {member}
        return sum(effective_sources(sub, servable, group_index, nested)
                   for sub in group_index[member])
    return 1 if servable.get(member, False) else 0


def main():
    parser = argparse.ArgumentParser(
        prog="magpie_inventory.py",
        description="只读盘点本机 Magpie 的 Agent、供应商、账号与路由组，并输出脱敏风险。",
        epilog=("退出码：0 = 盘点完成（问题记录在 risks 里，不等于失败）；1 = 报告缺字段不可用；"
                "2 = 用法错误或读取错误。本脚本不发起任何模型请求。"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", choices=["scan"], default="scan",
                        help="仅支持 scan（默认子命令，可省略）")
    parser.add_argument("--output", help="把盘点 JSON 写入该文件（权限 0600）")
    parser.add_argument("--config-dir", help="Magpie 配置目录（默认 ~/.config/magpie）")
    parser.add_argument("--gateway", help="网关地址，仅在 notes 中标注；本脚本不发起模型请求")
    args = parser.parse_args()
    result = scan(args)
    text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        save_private(args.output, text)
        print(json.dumps({"status": "SCANNED", "output": args.output,
                          "findings": len(result["risks"])}, ensure_ascii=False))
    else:
        print(text)
    required = ("schema", "generated_at", "magpie_version", "agents", "providers",
                "groups", "risks", "notes")
    if any(key not in result for key in required):
        # A report that lost a required section is not usable.
        print(json.dumps({"status": "INCOMPLETE_REPORT"}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (Refused, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        # Never echo upstream stdout/stderr, raw JSON or file contents.
        reason = str(error) if isinstance(error, Refused) else type(error).__name__
        print(json.dumps({"status": "REFUSED", "reason": reason}), file=sys.stderr)
        sys.exit(2)
