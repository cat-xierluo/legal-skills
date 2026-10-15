#!/usr/bin/env python3
# test-quota-summary-zcode.py — zcode lane summary 适配器 fail-closed 语义测试。
#
# 钉住的语义（2026-09-05 集成决策）：
#   - 数据源优先级 stdin-obs > watch-log（新鲜度内）> 现场拉取；全部失败
#     exit 1 且不写文件——绝不编造 lane 数据放行（fail-closed）；
#   - 合并写入：只替换 zcode lane，其余 lane 与 generated_at 原样保留，
#     不得替其他生产方"续期"（provider-probe 停摆必须表现为 stale 而非被掩盖）；
#   - 无既有文件/无其他 lane 时 generated_at = 本次数据时刻；
#   - lane 记录：remaining_percent = 100 - tokens_pct 钳到 [0,100]，
#     resets_at 由 five_hour_reset_at(epoch ms) 转 ISO，可缺省；
#   - 产出可直接被 quota_preflight.py 消费（provider=zcode lane 判停线语义）。
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ADAPTER = os.path.join(SCRIPT_DIR, "quota_summary_zcode.py")
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


def run_adapter(out_path, *, watch_log=None, script=None, stdin_obs=None,
                freshness=None, lane=None, now=None):
    args = [sys.executable, ADAPTER, "--out", out_path]
    if watch_log:
        args += ["--watch-log", watch_log]
    if script:
        args += ["--script", script]
    if freshness is not None:
        args += ["--freshness-seconds", str(freshness)]
    if lane:
        args += ["--lane", lane]
    if now:
        args += ["--now", now]
    if stdin_obs is not None:
        args += ["--stdin-obs"]
        return subprocess.run(args, input=stdin_obs, capture_output=True,
                              text=True, timeout=60)
    return subprocess.run(args, capture_output=True, text=True, timeout=60)


def write_lines(tmpdir, name, records):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def fresh_ts(seconds_ago=0):
    return (datetime.now().astimezone() - timedelta(seconds=seconds_ago)).isoformat(timespec="seconds")


def main():
    tmpdir = tempfile.mkdtemp(prefix="quota-summary-zcode-test-")

    # ── 1. 新鲜 watch-log → 写入 zcode lane，source=watch-log ──
    now_iso = datetime.now().astimezone().isoformat(timespec="seconds")
    reset_ms = int((datetime.now().astimezone() + timedelta(hours=4)).timestamp() * 1000)
    log = write_lines(tmpdir, "fresh.jsonl", [
        {"ts": fresh_ts(600), "tokens_pct": 90},
        {"ts": fresh_ts(30), "tokens_pct": 40, "five_hour_reset_at": reset_ms},
    ])
    out1 = os.path.join(tmpdir, "s1.json")
    r = run_adapter(out1, watch_log=log, now=now_iso)
    data = json.loads(r.stdout) if r.returncode == 0 else {}
    lane = data.get("lanes", {}).get("zcode", {})
    if (r.returncode == 0 and lane.get("remaining_percent") == 60.0
            and lane.get("source") == "watch-log"
            and data.get("generated_at") == lane.get("updated_at")
            and isinstance(lane.get("resets_at"), str)):
        ok("新鲜 watch-log 产出 zcode fuel lane")
    else:
        bad("新鲜 watch-log 产出 zcode fuel lane", f"rc={r.returncode} out={r.stdout} err={r.stderr}")

    # ── 2. 既有 summary 含其他 lane → 只替换 zcode，generated_at 不被改写 ──
    out2 = os.path.join(tmpdir, "s2.json")
    old_generated = "2026-09-05T16:31:10+08:00"
    with open(out2, "w", encoding="utf-8") as fh:
        json.dump({"schema": "quota-aware-routing.summary.v1",
                   "generated_at": old_generated,
                   "lanes": {"glm-api": {"type": "fuel", "remaining_percent": 8.0,
                                         "resets_at": "2026-09-05T18:44+08:00",
                                         "health": "ok"},
                             "zcode": {"type": "fuel", "remaining_percent": 1.0,
                                       "health": "ok"}}}, fh)
    r = run_adapter(out2, watch_log=log, now=now_iso)
    data = json.loads(r.stdout) if r.returncode == 0 else {}
    lanes = data.get("lanes", {})
    if (r.returncode == 0 and data.get("generated_at") == old_generated
            and lanes.get("glm-api", {}).get("remaining_percent") == 8.0
            and lanes.get("zcode", {}).get("remaining_percent") == 60.0):
        ok("合并保留其他 lane 与原 generated_at（不替别人续期）")
    else:
        bad("合并保留其他 lane 与原 generated_at", f"rc={r.returncode} data={data}")

    # ── 3. 日志过期 → 现场拉取回退（假脚本） ──
    stale_log = write_lines(tmpdir, "stale.jsonl", [
        {"ts": fresh_ts(3600), "tokens_pct": 40},
    ])
    fake = os.path.join(tmpdir, "fake-zcode-quota")
    with open(fake, "w", encoding="utf-8") as fh:
        fh.write("#!/usr/bin/env python3\n"
                 "import json,sys\n"
                 "print(json.dumps({'ok': True, 'tokens_pct': 25,"
                 " 'five_hour_reset_at': %d}))\n" % reset_ms)
    os.chmod(fake, 0o755)
    out3 = os.path.join(tmpdir, "s3.json")
    r = run_adapter(out3, watch_log=stale_log, script=fake, now=now_iso)
    data = json.loads(r.stdout) if r.returncode == 0 else {}
    lane = data.get("lanes", {}).get("zcode", {})
    if (r.returncode == 0 and lane.get("source") == "live-pull"
            and lane.get("remaining_percent") == 75.0):
        ok("日志过期回退现场拉取")
    else:
        bad("日志过期回退现场拉取", f"rc={r.returncode} data={data}")

    # ── 4. 全部失败 → exit 1，既有文件不被碰 ──
    out4 = os.path.join(tmpdir, "s4.json")
    with open(out4, "w", encoding="utf-8") as fh:
        fh.write('{"schema": "quota-aware-routing.summary.v1", "generated_at": "'
                 + old_generated + '", "lanes": {}}')
    before = open(out4, encoding="utf-8").read()
    r = run_adapter(out4, watch_log=stale_log,
                    script=os.path.join(tmpdir, "no-such-script"), now=now_iso)
    after = open(out4, encoding="utf-8").read()
    if r.returncode == 1 and before == after:
        ok("无数据 exit 1 且文件原样（fail-closed）")
    else:
        bad("无数据 exit 1 且文件原样", f"rc={r.returncode} changed={before != after}")

    # ── 5. 末行 tokens_pct=null → 向前找上一条可用记录 ──
    hole_log = write_lines(tmpdir, "hole.jsonl", [
        {"ts": fresh_ts(30), "tokens_pct": None},
        {"ts": fresh_ts(45), "tokens_pct": 55},
    ])
    out5 = os.path.join(tmpdir, "s5.json")
    r = run_adapter(out5, watch_log=hole_log, now=now_iso)
    data = json.loads(r.stdout) if r.returncode == 0 else {}
    if r.returncode == 0 and data.get("lanes", {}).get("zcode", {}).get("remaining_percent") == 45.0:
        ok("跳过 tokens_pct 缺失的观测行")
    else:
        bad("跳过 tokens_pct 缺失的观测行", f"rc={r.returncode} data={data}")

    # ── 6. --stdin-obs 直连（日志过期也不影响） ──
    out6 = os.path.join(tmpdir, "s6.json")
    r = run_adapter(out6, watch_log=stale_log, now=now_iso,
                    stdin_obs=json.dumps({"ok": True, "tokens_pct": 10,
                                          "five_hour_reset_at": reset_ms}))
    data = json.loads(r.stdout) if r.returncode == 0 else {}
    lane = data.get("lanes", {}).get("zcode", {})
    if (r.returncode == 0 and lane.get("source") == "stdin"
            and lane.get("remaining_percent") == 90.0):
        ok("stdin-obs 钩子直连优先")
    else:
        bad("stdin-obs 钩子直连优先", f"rc={r.returncode} data={data}")

    # ── 7. resets_at 缺省可接受；remaining 钳位 ──
    out7 = os.path.join(tmpdir, "s7.json")
    r = run_adapter(out7, watch_log=stale_log, now=now_iso,
                    stdin_obs=json.dumps({"tokens_pct": 105}))
    data = json.loads(r.stdout) if r.returncode == 0 else {}
    lane = data.get("lanes", {}).get("zcode", {})
    if (r.returncode == 0 and lane.get("remaining_percent") == 0.0
            and "resets_at" not in lane):
        ok("remaining 钳到 0 且 resets_at 可缺省")
    else:
        bad("remaining 钳位与 resets_at 缺省", f"rc={r.returncode} lane={lane}")

    # ── 8. 产出可被 quota_preflight.py 消费 ──
    config = {"quota_aware_routing": {
        "enabled": True,
        "lanes": {"zcode": {"type": "fuel", "providers": ["zcode"]}},
        "tier_policy": {"default": "zcode"},
        "freshness_minutes": 30,
        "stop_line_percent": 15,
    }}
    cfg_path = os.path.join(tmpdir, "personal.json")
    with open(cfg_path, "w", encoding="utf-8") as fh:
        json.dump(config, fh)
    # 8a. 余量充足（90%）→ 放行
    r = subprocess.run([sys.executable, GATE, "--config", cfg_path,
                        "--provider", "zcode", "--backend", "zcode",
                        "--summary-file", out6, "--now", now_iso],
                       capture_output=True, text=True, timeout=60)
    verdict = json.loads(r.stdout) if r.stdout.strip() else {}
    if r.returncode == 0 and verdict.get("status") == "ok":
        ok("预检门消费 zcode lane：余量充足放行")
    else:
        bad("预检门消费 zcode lane：余量充足放行", f"rc={r.returncode} out={r.stdout}")
    # 8b. 余量 0% → lane_below_stop_line 拒绝
    r = subprocess.run([sys.executable, GATE, "--config", cfg_path,
                        "--provider", "zcode", "--backend", "zcode",
                        "--summary-file", out7, "--now", now_iso],
                       capture_output=True, text=True, timeout=60)
    verdict = json.loads(r.stdout) if r.stdout.strip() else {}
    if r.returncode == 3 and verdict.get("status") == "lane_below_stop_line":
        ok("预检门消费 zcode lane：判停线拒绝")
    else:
        bad("预检门消费 zcode lane：判停线拒绝", f"rc={r.returncode} out={r.stdout}")

    # ── 9. 自定义 lane 名 ──
    out9 = os.path.join(tmpdir, "s9.json")
    r = run_adapter(out9, watch_log=stale_log, lane="bigmodel", now=now_iso,
                    stdin_obs=json.dumps({"tokens_pct": 50}))
    data = json.loads(r.stdout) if r.returncode == 0 else {}
    if r.returncode == 0 and "bigmodel" in data.get("lanes", {}) and "zcode" not in data["lanes"]:
        ok("自定义 lane 名生效")
    else:
        bad("自定义 lane 名生效", f"rc={r.returncode} data={data}")

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
