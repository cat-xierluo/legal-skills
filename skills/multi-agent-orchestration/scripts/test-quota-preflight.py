#!/usr/bin/env python3
# test-quota-preflight.py — P0-① spawn-worker quota preflight fail-closed 语义测试。
#
# 旧错误语义（本测试先钉住再修实现）：
#   - route_suggest 只在「自动补选」时看额度，显式 --api-provider 直接跳过额度检查；
#   - quota summary 缺失/过期/低于 stop line 时，spawn 仍然放行（fail-open）。
# 新语义（2026-09 复盘修复）：
#   - 只要个人配置启用 quota_aware_routing，spawn 在任何 worktree/terminal/lease/dispatch
#     副作用之前必须通过 quota preflight；summary 缺失、不可读、过期、provider 不属于
#     任何 lane、lane 无余量信号、低于 stop line、lane 不健康、claude-code 未解析出
#     provider —— 一律拒绝（exit 3 + allowed=false）；
#   - quota_aware_routing 未启用 → not_configured（无机械权威，放行并输出提示）；
#   - 绕过通道不在本模块：spawn-worker 侧仅接受显式 override 标志 + 非空授权来源。
# summary/config schema 与 route_suggest.py 完全一致（quota-aware-routing.summary.v1）。
import json
import subprocess
import sys
import tempfile
import os
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(SCRIPT_DIR, "quota_preflight.py")

passed = 0
failed = 0


def ok(label):
    global passed
    passed += 1
    print(f"PASS: {label}")


def bad(label, detail=""):
    global failed
    failed += 1
    print(f"FAIL: {label} {detail}", file=sys.stderr)


def run_gate(config, provider, backend, summary=None, now=None):
    """跑 quota_preflight.py，返回 (exit_code, stdout_json_or_None)。"""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as cf:
        json.dump(config, cf)
        config_path = cf.name
    args = [sys.executable, GATE, "--config", config_path,
            "--provider", provider, "--backend", backend]
    summary_path = None
    if summary is not None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as sf:
            json.dump(summary, sf)
            summary_path = sf.name
        args += ["--summary-file", summary_path]
    if now:
        args += ["--now", now]
    proc = subprocess.run(args, capture_output=True, text=True)
    os.unlink(config_path)
    if summary_path:
        os.unlink(summary_path)
    payload = None
    try:
        payload = json.loads(proc.stdout)
    except Exception:
        pass
    return proc.returncode, payload


def iso(minutes_ago):
    # 与 route_suggest.py 相同的 fromisoformat 解析面：使用 +00:00 而非 Z（3.10 兼容）
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


def base_config(**overrides):
    cfg = {
        "quota_aware_routing": {
            "enabled": True,
            "freshness_minutes": 30,
            "stop_line_percent": 15,
            "tier_policy": {"L1": ["fuel-a"]},
            "lanes": {
                "fuel-a": {"type": "fuel", "providers": ["prov-a"]},
                "reservoir-b": {"type": "reservoir", "providers": ["prov-b"]},
            },
        }
    }
    cfg["quota_aware_routing"].update(overrides)
    return cfg


def fresh_summary(remaining_a=80.0, generated_minutes_ago=5):
    return {
        "schema": "quota-aware-routing.summary.v1",
        "generated_at": iso(generated_minutes_ago),
        "lanes": {
            "fuel-a": {"type": "fuel", "remaining_percent": remaining_a, "health": "ok"},
            "reservoir-b": {"type": "reservoir", "health": "ok"},
        },
    }


def expect_deny(label, code, payload, expect_status=None):
    if code == 3 and payload and payload.get("allowed") is False:
        if expect_status and payload.get("status") != expect_status:
            bad(label, f"(status={payload.get('status')} want={expect_status})")
        else:
            ok(label)
    else:
        bad(label, f"(code={code} payload={payload})")


def expect_allow(label, code, payload, expect_status=None):
    if code == 0 and payload and payload.get("allowed") is True:
        if expect_status and payload.get("status") != expect_status:
            bad(label, f"(status={payload.get('status')} want={expect_status})")
        else:
            ok(label)
    else:
        bad(label, f"(code={code} payload={payload})")


# ---- 旧语义的显式 provider 旁路必须被否定：显式 provider 也要过 preflight ----
code, out = run_gate(base_config(), "prov-a", "claude-code",
                     summary=fresh_summary(remaining_a=9.0))
expect_deny("explicit provider below stop line is denied (old: explicit bypass)",
            code, out, "lane_below_stop_line")

code, out = run_gate(base_config(), "prov-a", "claude-code", summary=None)
expect_deny("explicit provider with missing summary is denied (old: explicit bypass)",
            code, out, "missing_summary")

code, out = run_gate(base_config(), "prov-a", "claude-code",
                     summary=fresh_summary(generated_minutes_ago=90))
expect_deny("explicit provider with stale summary is denied", code, out, "stale_summary")

code, out = run_gate(base_config(), "prov-unknown", "claude-code",
                     summary=fresh_summary())
expect_deny("explicit provider outside every lane is denied (provider/lane mismatch)",
            code, out, "provider_unknown_lane")

# ---- lane 在 summary 中缺席 → 无余量信号，fail-closed ----
summary = fresh_summary()
del summary["lanes"]["fuel-a"]
code, out = run_gate(base_config(), "prov-a", "claude-code", summary=summary)
expect_deny("lane missing from summary is denied (no signal)", code, out, "lane_no_signal")

# ---- 自动补选路径同样 fail-closed：claude-code 未解析出 provider ----
code, out = run_gate(base_config(), "", "claude-code", summary=fresh_summary())
expect_deny("claude-code with unresolved provider is denied (no verified lane)",
            code, out, "no_provider_selected")

# ---- 正向：额度健康的新鲜 summary 放行（自动与显式一致） ----
code, out = run_gate(base_config(), "prov-a", "claude-code", summary=fresh_summary())
expect_allow("fresh above-stop-line lane is allowed", code, out, "ok")

# ---- summary 不可读 / generated_at 缺失 ----
code, out = run_gate(base_config(), "prov-a", "claude-code",
                     summary={"schema": "quota-aware-routing.summary.v1", "lanes": {}})
expect_deny("summary without generated_at is unreadable -> denied", code, out,
            "unreadable_summary")

# ---- lane 健康度 ----
summary = fresh_summary()
summary["lanes"]["fuel-a"]["health"] = "down"
code, out = run_gate(base_config(), "prov-a", "claude-code", summary=summary)
expect_deny("unhealthy fuel lane is denied", code, out, "lane_unhealthy")

# ---- fuel lane 缺 remaining_percent → 无信号 ----
summary = fresh_summary()
del summary["lanes"]["fuel-a"]["remaining_percent"]
code, out = run_gate(base_config(), "prov-a", "claude-code", summary=summary)
expect_deny("fuel lane without remaining_percent is denied", code, out, "lane_no_signal")

# ---- 边界：remaining 恰好等于 stop line 视为停用（必须严格大于才可用） ----
code, out = run_gate(base_config(), "prov-a", "claude-code",
                     summary=fresh_summary(remaining_a=15.0))
expect_deny("lane exactly at stop line is denied", code, out, "lane_below_stop_line")

# ---- 非 claude backend 且无显式 provider：无 lane 概念，advisory 放行 ----
code, out = run_gate(base_config(), "", "codex", summary=fresh_summary())
expect_allow("non-claude backend without provider is advisory-allowed", code, out,
             "not_applicable")

# ---- 未启用 quota_aware_routing：not_configured 放行（无机械权威） ----
cfg = base_config()
cfg["quota_aware_routing"]["enabled"] = False
code, out = run_gate(cfg, "prov-a", "claude-code", summary=fresh_summary())
expect_allow("disabled quota routing is not_configured (allow with advisory)",
             code, out, "not_configured")

code, out = run_gate({"quota_aware_routing": {"enabled": True, "lanes": "oops"}},
                     "prov-a", "claude-code", summary=fresh_summary())
expect_deny("enabled routing with malformed lanes is denied (config_invalid)",
            code, out, "config_invalid")

# ---- 窗口重置时刻 ----
summary = fresh_summary()
summary["lanes"]["fuel-a"]["resets_at"] = iso(-10)  # 未来才重置 -> 正常可用
code, out = run_gate(base_config(), "prov-a", "claude-code", summary=summary)
expect_allow("future resets_at is a normal pass", code, out, "ok")

summary = fresh_summary()
summary["lanes"]["fuel-a"]["resets_at"] = iso(10)  # 已过期 -> pending_refresh，放行但带标记
code, out = run_gate(base_config(), "prov-a", "claude-code", summary=summary)
if code == 0 and out and out.get("allowed") and out.get("pending_refresh") is True:
    ok("passed resets_at is allowed with pending_refresh flag")
else:
    bad("passed resets_at is allowed with pending_refresh flag", f"(code={code} out={out})")

# ---- reservoir lane 只看 health ----
code, out = run_gate(base_config(), "prov-b", "claude-code", summary=fresh_summary())
expect_allow("reservoir lane passes on health=ok", code, out, "ok")
summary = fresh_summary()
summary["lanes"]["reservoir-b"]["health"] = "down"
code, out = run_gate(base_config(), "prov-b", "claude-code", summary=summary)
expect_deny("reservoir lane with health=down is denied", code, out, "lane_unhealthy")

# ---- --now 显式注入（决定 stale 判定的可测性） ----
code, out = run_gate(base_config(), "prov-a", "claude-code",
                     summary=fresh_summary(generated_minutes_ago=90),
                     now=(datetime.now(timezone.utc) - timedelta(minutes=80)).isoformat())
# now 取快照后 10 分钟 -> 不 stale
expect_allow("--now injected: snapshot age recomputed from --now", code, out, "ok")

print(f"quota-preflight tests: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
