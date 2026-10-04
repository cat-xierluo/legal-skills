#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Integration runner: synthetic SQLite -> real collector -> real adapter.

Drives the frozen production pair end-to-end over a portable matrix of
synthetic counterexample databases built by zcode-gui-pipeline-fixtures.py:

    real subprocess collector (zcode-session-evidence.py, read-only SQLite)
        -> real metadata file on disk
        -> real subprocess adapter (zcode-gui-monitor-adapter.py)

Asserts, per named case: the exact adapter state or the exact expected error
code and exit, all adapter flags constant-false, the collector digest chain,
that the source database SHA-256 (and its directory) is unchanged by the run,
that metadata carries only the bound synthetic session (a planted decoy session
plus canary tokens in status_reason/reasoning/tool parts never surface), and —
as a negative control — that the historical initial adapter (3ed5679) rejects
collector-legal null turn scalars while the fixed adapter accepts them.

Exit codes: 0 all expected assertions held; 1 at least one real failure;
77 dependencies (collector/adapter) missing — inject them via --collector/
--adapter or the ZCODE_GUI_COLLECTOR / ZCODE_GUI_ADAPTER environment variables.
A missing legacy object only skips the negative control, never the suite.

Standard library only; supports Python 3.9+. Concise summary on stdout; the
verbose per-check log stays inside --workdir (default: a fresh tempdir).
"""

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_SKIP = 77

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_MODULE = "zcode-gui-pipeline-fixtures.py"
SIBLING_COLLECTOR = "zcode-session-evidence.py"
SIBLING_ADAPTER = "zcode-gui-monitor-adapter.py"
ENV_COLLECTOR = "ZCODE_GUI_COLLECTOR"
ENV_ADAPTER = "ZCODE_GUI_ADAPTER"
ENV_LEGACY = "ZCODE_GUI_ADAPTER_LEGACY"

# Historical initial adapter used only for the negative control; extracted
# read-only from git history into the private workdir, never committed here.
LEGACY_COMMIT = "3ed567971a7c6c41612d2cd611aef25ef9f8117f"
LEGACY_REPO_PATH = "skills/multi-agent-orchestration/scripts/zcode-gui-monitor-adapter.py"
LEGACY_EXPECTED_ERROR = "EVIDENCE_TYPE_INVALID"

# Fixed adapter contract: these flags are constant false in every emission.
ADAPTER_FALSE_FLAGS = {
    "pmAccepted": False,
    "orcaSupervised": False,
    "livenessAuthoritative": False,
}

SUBPROCESS_TIMEOUT = 90


class _Missing(object):
    """Sentinel for absent dot-path values (distinct from JSON null)."""


_MISSING = _Missing()


class CheckList(object):
    def __init__(self):
        self.items = []

    def check(self, ok, message):
        self.items.append((bool(ok), message))
        return ok

    @property
    def failures(self):
        return [msg for ok, msg in self.items if not ok]


def load_fixtures():
    path = os.path.join(SCRIPT_DIR, FIXTURES_MODULE)
    spec = importlib.util.spec_from_file_location("zcode_gui_pipeline_fixtures", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load %s" % FIXTURES_MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path):
    with open(path, "rb") as handle:
        return sha256_bytes(handle.read())


def dir_snapshot(directory):
    return sorted(os.listdir(directory))


def dig(payload, dotted):
    node = payload
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return _MISSING
        node = node[part]
    return node


def run_cmd(cmd):
    return subprocess.run(
        cmd, capture_output=True, timeout=SUBPROCESS_TIMEOUT,
        env=dict(os.environ),
    )


def decode(raw):
    return raw.decode("utf-8", "replace")


def parse_json_object(text):
    try:
        payload = json.loads(text)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def resolve_dependency(cli_value, env_name, sibling_name, cli_flag):
    """CLI flag > environment variable > sibling next to this runner."""
    if cli_value:
        if os.path.isfile(cli_value):
            return cli_value, "--%s" % cli_flag
        return None, "--%s points to a missing file: %s" % (cli_flag, cli_value)
    env_value = os.environ.get(env_name)
    if env_value:
        if os.path.isfile(env_value):
            return env_value, "env %s" % env_name
        return None, "env %s points to a missing file: %s" % (env_name, env_value)
    sibling = os.path.join(SCRIPT_DIR, sibling_name)
    if os.path.isfile(sibling):
        return sibling, "sibling %s" % sibling_name
    return None, None


def resolve_legacy_adapter(cli_value, workdir):
    value = cli_value or os.environ.get(ENV_LEGACY) or "auto"
    if value == "off":
        return None, "disabled via configuration"
    if value != "auto":
        if os.path.isfile(value):
            return value, "explicit path"
        return None, "explicit legacy path missing: %s" % value
    try:
        proc = subprocess.run(
            ["git", "-C", SCRIPT_DIR, "cat-file", "blob",
             "%s:%s" % (LEGACY_COMMIT, LEGACY_REPO_PATH)],
            capture_output=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, "auto extraction failed (git unavailable)"
    if proc.returncode != 0 or not proc.stdout:
        return None, ("historical object %s not reachable from this checkout"
                      % LEGACY_COMMIT[:12])
    legacy_path = os.path.join(workdir, "legacy-zcode-gui-monitor-adapter.py")
    with open(legacy_path, "wb") as handle:
        handle.write(proc.stdout)
    return legacy_path, "auto-extracted from %s" % LEGACY_COMMIT[:12]


def scan_leaks(text, tokens):
    return [token for token in tokens if token in text]


class Runner(object):
    def __init__(self, fixtures, ctx):
        self.fx = fixtures
        self.ctx = ctx

    def log(self, message):
        self.ctx["detail"].write(message + "\n")
        self.ctx["detail"].flush()

    def leak_tokens(self):
        fx = self.fx
        return tuple(fx.ALL_CANARY_TOKENS) + (fx.DECOY_SESSION_ID, fx.DECOY_TURN_ID)

    def check_process(self, checks, label, proc):
        self.log("--- %s ---" % label)
        self.log("$ %s" % " ".join(proc.args))
        self.log("exit=%d" % proc.returncode)
        self.log("stdout:\n%s" % decode(proc.stdout))
        self.log("stderr:\n%s" % decode(proc.stderr))
        hits = scan_leaks(decode(proc.stdout) + "\n" + decode(proc.stderr),
                         self.leak_tokens())
        checks.check(not hits, "%s must not leak canary/decoy tokens (found: %s)"
                     % (label, ", ".join(hits)))
        return proc

    def run_collector(self, checks, label, db_path, sid, iid, extra=()):
        cmd = [sys.executable, self.ctx["collector"], "--db", db_path,
               "--session-id", sid, "--input-id", iid] + list(extra)
        proc = self.check_process(checks, label, run_cmd(cmd))
        return proc

    def run_adapter(self, checks, label, spec, evidence_path, digest, sid, iid):
        resolved = [digest if arg == "{evidence_sha256}" else arg
                    for arg in spec.adapter_args]
        cmd = [sys.executable, self.ctx["adapter"], "--evidence", evidence_path,
               "--session-id", spec.adapter_session_id or sid,
               "--input-id", spec.adapter_input_id or iid] + resolved
        proc = self.check_process(checks, label, run_cmd(cmd))
        payload = parse_json_object(decode(proc.stdout))
        checks.check(payload is not None,
                     "%s emits a JSON object (got unparseable stdout)" % label)
        if payload is None:
            return
        if spec.adapter_error is not None:
            checks.check(payload.get("error") == spec.adapter_error,
                         "%s error == %s (got %r)" % (label, spec.adapter_error,
                                                      payload.get("error")))
        if spec.adapter_state is not None:
            checks.check(payload.get("state") == spec.adapter_state,
                         "%s state == %s (got %r)" % (label, spec.adapter_state,
                                                      payload.get("state")))
        for dotted, expected in sorted(spec.adapter_expect.items()):
            actual = dig(payload, dotted)
            checks.check(actual is not _MISSING and actual == expected,
                         "%s %s == %r (got %r)" % (label, dotted, expected, actual))
        if "flags" in payload:
            checks.check(payload["flags"] == ADAPTER_FALSE_FLAGS,
                         "%s flags constant-false (got %r)" % (label, payload["flags"]))
        if spec.adapter_exit == 0 and payload.get("error") is None:
            checks.check(payload.get("sessionId") == (spec.adapter_session_id or sid),
                         "%s echoes the bound sessionId" % label)
            checks.check(payload.get("inputId") == (spec.adapter_input_id or iid),
                         "%s echoes the bound inputId" % label)
            checks.check(payload.get("evidenceSha256") == digest,
                         "%s evidenceSha256 matches the metadata file digest" % label)

    def run_case(self, name):
        fx = self.fx
        spec = fx.CASES[name]
        checks = CheckList()
        self.log("=== case %s ===" % name)
        self.log("description: %s" % spec.description)
        base = fx.CASES[spec.reuses_db_of] if spec.reuses_db_of else spec
        sid, iid = base.session_id, base.input_id
        db_path = self.ctx["dbs"][name]

        try:
            checks.check(
                os.path.commonpath([os.path.abspath(db_path),
                                    os.path.abspath(self.ctx["workdir"])])
                == os.path.abspath(self.ctx["workdir"]),
                "fixture database stays inside the private workdir")
        except ValueError:
            checks.check(False, "fixture database path is not inside the workdir")

        db_dir = os.path.dirname(db_path)
        before_files = dir_snapshot(db_dir)
        before_sha = sha256_file(db_path)

        proc = self.run_collector(checks, "collector", db_path, sid,
                                  spec.collector_input_id or iid)
        checks.check(proc.returncode == spec.collector_exit,
                     "collector exit == %d (got %d)" % (spec.collector_exit,
                                                        proc.returncode))
        payload = parse_json_object(decode(proc.stdout))
        checks.check(payload is not None, "collector emits a JSON object")
        if payload is not None:
            if spec.collector_error is not None:
                error = payload.get("error")
                code = error.get("code") if isinstance(error, dict) else None
                checks.check(code == spec.collector_error,
                             "collector error code == %s (got %r)"
                             % (spec.collector_error, code))
            else:
                checks.check(payload.get("ok") is True, "collector reports ok=true")
                checks.check(payload.get("sessionId") == sid,
                             "collector metadata carries only the bound session")
                checks.check(payload.get("inputId") == iid,
                             "collector metadata carries only the bound input")
                for dotted, expected in sorted(spec.collector_expect.items()):
                    actual = dig(payload, dotted)
                    checks.check(actual is not _MISSING and actual == expected,
                                 "collector %s == %r (got %r)"
                                 % (dotted, expected, actual))

        after_files = dir_snapshot(db_dir)
        checks.check(after_files == before_files,
                     "collector leaves no journal/wal side files")
        checks.check(sha256_file(db_path) == before_sha,
                     "collector leaves the database byte-identical (SHA-256)")

        legacy_note = None
        if spec.adapter_exit is not None and proc.returncode == 0 and payload is not None:
            evidence_path = os.path.join(self.ctx["evidence_dir"], name + ".json")
            with open(evidence_path, "wb") as handle:
                handle.write(proc.stdout)
            digest = sha256_bytes(proc.stdout)
            self.run_adapter(checks, "adapter", spec, evidence_path, digest, sid, iid)

            if spec.legacy_control:
                if self.ctx["legacy"] is None:
                    legacy_note = "legacy control not executed: %s" % self.ctx["legacy_note"]
                else:
                    lproc = self.run_collector_probe_legacy(checks, evidence_path, sid, iid)
                    lpayload = parse_json_object(decode(lproc.stdout))
                    checks.check(
                        lproc.returncode == 2 and lpayload is not None
                        and lpayload.get("error") == LEGACY_EXPECTED_ERROR,
                        "negative control: historical adapter %s must reject"
                        " collector-legal null turn scalars with %s (exit=%d, got %r)"
                        % (LEGACY_COMMIT[:12], LEGACY_EXPECTED_ERROR, lproc.returncode,
                           lpayload.get("error") if lpayload else None))

        if spec.include_final_text_pass and proc.returncode == 0 and payload is not None:
            proc_ft = self.run_collector(checks, "collector(--include-final-text)",
                                         db_path, sid, iid,
                                         extra=("--include-final-text",))
            checks.check(proc_ft.returncode == 0,
                         "collector(--include-final-text) exit == 0 (got %d)"
                         % proc_ft.returncode)
            ft_payload = parse_json_object(decode(proc_ft.stdout))
            checks.check(ft_payload is not None
                         and dig(ft_payload, "completionEvidence.complete") is True,
                         "collector(--include-final-text) still reports complete")
            if proc_ft.returncode == 0 and ft_payload is not None:
                ft_path = os.path.join(self.ctx["evidence_dir"],
                                       name + ".fulltext.json")
                with open(ft_path, "wb") as handle:
                    handle.write(proc_ft.stdout)
                self.run_adapter(checks, "adapter(--include-final-text)", spec,
                                 ft_path, sha256_bytes(proc_ft.stdout), sid, iid)

        for ok, msg in checks.items:
            self.log("[%s] %s" % ("ok" if ok else "FAIL", msg))
        if checks.failures:
            return name, "FAIL", checks.failures[0]
        if legacy_note:
            return name, "SKIP", legacy_note
        return name, "PASS", "%d checks ok" % len(checks.items)

    def run_collector_probe_legacy(self, checks, evidence_path, sid, iid):
        cmd = [sys.executable, self.ctx["legacy"], "--evidence", evidence_path,
               "--session-id", sid, "--input-id", iid]
        return self.check_process(checks, "legacy adapter (negative control)",
                                  run_cmd(cmd))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="test-zcode-gui-evidence-pipeline",
        description="Synthetic SQLite -> real collector -> real adapter"
                    " integration matrix (stdlib only).",
    )
    parser.add_argument("--collector", help="path to zcode-session-evidence.py")
    parser.add_argument("--adapter", help="path to zcode-gui-monitor-adapter.py")
    parser.add_argument("--legacy-adapter",
                        help="historical initial adapter: path, 'auto' (default),"
                             " or 'off'")
    parser.add_argument("--workdir",
                        help="private directory for databases, evidence, logs"
                             " (default: a fresh tempdir)")
    parser.add_argument("--list-cases", action="store_true",
                        help="print the named case matrix and exit")
    args = parser.parse_args(argv)

    fx = load_fixtures()
    if args.list_cases:
        for name in fx.CASE_NAMES:
            print("%s: %s" % (name, fx.CASES[name].description))
        return EXIT_OK

    collector, collector_note = resolve_dependency(
        args.collector, ENV_COLLECTOR, SIBLING_COLLECTOR, "collector")
    adapter, adapter_note = resolve_dependency(
        args.adapter, ENV_ADAPTER, SIBLING_ADAPTER, "adapter")

    missing = []
    if collector is None:
        missing.append("collector: %s" % collector_note)
    if adapter is None:
        missing.append("adapter: %s" % adapter_note)
    if missing:
        print("SKIP zcode-gui-evidence-pipeline: real dependencies not available")
        for item in missing:
            print("  - %s" % item)
        print("  inject them via --collector/--adapter or env %s / %s"
              % (ENV_COLLECTOR, ENV_ADAPTER))
        return EXIT_SKIP

    workdir = args.workdir or tempfile.mkdtemp(prefix="zcode-gui-evidence-pipeline-")
    os.makedirs(workdir, exist_ok=True)
    cases_dir = os.path.join(workdir, "cases")
    evidence_dir = os.path.join(workdir, "evidence")
    os.makedirs(cases_dir, exist_ok=True)
    os.makedirs(evidence_dir, exist_ok=True)
    detail = open(os.path.join(workdir, "detail.log"), "w", encoding="utf-8")

    legacy, legacy_note = resolve_legacy_adapter(args.legacy_adapter, workdir)

    ctx = {
        "workdir": workdir,
        "cases_dir": cases_dir,
        "evidence_dir": evidence_dir,
        "detail": detail,
        "collector": collector,
        "adapter": adapter,
        "legacy": legacy,
        "legacy_note": legacy_note,
        "dbs": {},
    }

    for name in fx.CASE_NAMES:
        spec = fx.CASES[name]
        if spec.reuses_db_of:
            continue
        ctx["dbs"][name] = os.path.join(cases_dir, name + ".sqlite")
        fx.build_case(name, ctx["dbs"][name])
    for name in fx.CASE_NAMES:
        spec = fx.CASES[name]
        if spec.reuses_db_of:
            ctx["dbs"][name] = ctx["dbs"][spec.reuses_db_of]

    runner = Runner(fx, ctx)
    results = [runner.run_case(name) for name in fx.CASE_NAMES]

    detail.close()
    passed = [r for r in results if r[1] == "PASS"]
    failed = [r for r in results if r[1] == "FAIL"]
    skipped = [r for r in results if r[1] == "SKIP"]

    with open(os.path.join(workdir, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "collector": collector,
            "adapter": adapter,
            "legacy": legacy,
            "results": [{"name": n, "status": s, "detail": d} for n, s, d in results],
            "passed": len(passed),
            "failed": len(failed),
            "skipped": len(skipped),
        }, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    print("== zcode-gui-evidence-pipeline integration ==")
    print("collector: %s (%s)" % (collector, collector_note))
    print("adapter:   %s (%s)" % (adapter, adapter_note))
    print("legacy:    %s (%s)" % (legacy or "unavailable", legacy_note))
    for name, status, note in results:
        line = "%-38s %s" % (name, status)
        if status != "PASS":
            line += " | %s" % note
        print(line)
    print("summary: %d cases | %d PASS | %d FAIL | %d SKIP"
          % (len(results), len(passed), len(failed), len(skipped)))
    print("detail log: %s" % os.path.join(workdir, "detail.log"))
    return EXIT_FAILED if failed else EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(EXIT_FAILED)
