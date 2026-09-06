#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test-mem-budget-probe.py — 物理内存预算 lane（v2.21.0）fail-closed 语义测试。

覆盖（任务合同 TASK-2026-09-06-MEM-BUDGET）：
  - vm_stat / memory_pressure / vm.swapusage 各输出形态解析；
  - swap 高压时额度折算收紧（warn 折半、critical 归零）；
  - 读取全失败 exit 1 且不输出额度（fail-closed，绝不编造）；
  - --json 输出 memory-budget.summary.v1 schema 字段稳定；
  - 低内存 fixture 下 spawn-worker.sh 预检拒绝：专用 exit code 4 + 可诊断原因
    （当前可用 / 预算 / 缺口），且发生在任何 worktree / terminal 副作用之前；
  - 正常放行输出 SPAWN_WORKER_MEM_BUDGET: available=X budget=Y slots=N；
  - SPAWN_WORKER_MEM_BUDGET_BYTES=0 显式直通（关门 opt-out）。

E2E 用例复用 test-spawn-worker-orca.sh 的 fake Orca CLI 模式（临时 git 仓 +
fake orca/fake ps），与真实 Orca runtime 完全隔离。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(SCRIPT_DIR, "mem_budget_probe.py")
SPAWN_WORKER = os.path.join(SCRIPT_DIR, "spawn-worker.sh")

sys.path.insert(0, SCRIPT_DIR)
import mem_budget_probe as mbp  # noqa: E402

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


def check(label, condition, detail=""):
    if condition:
        ok(label)
    else:
        bad(label, detail)


def probe_env(**overrides):
    env = dict(os.environ)
    env.pop("MEM_BUDGET_FIXTURE_DIR", None)
    env.pop("SPAWN_WORKER_MEM_BUDGET_BYTES", None)
    env.update(overrides)
    return env


def run_probe(args=(), env=None, timeout=30):
    proc = subprocess.run([sys.executable, PROBE, "--json", *args],
                          capture_output=True, text=True, env=env or probe_env(),
                          timeout=timeout)
    payload = None
    try:
        payload = json.loads(proc.stdout)
    except (ValueError, TypeError):
        pass
    return proc.returncode, payload


GIB = 1024 ** 3
TOTAL_32G = 32 * GIB
BUDGET_DEFAULT = 3 * GIB


def vm_stat_text(page_size, free, speculative, inactive, extra_lines=""):
    lines = [
        "Mach Virtual Memory Statistics: (page size of %d bytes)" % page_size,
        "Pages free:                               %d." % free,
        "Pages speculative:                        %d." % speculative,
        "Pages inactive:                           %d." % inactive,
    ]
    return "\n".join(lines + ([extra_lines] if extra_lines else [])) + "\n"


def write_fixture(directory, **files):
    os.makedirs(directory, exist_ok=True)
    for name, content in files.items():
        with open(os.path.join(directory, mbp.FIXTURE_FILES[name]), "w",
                  encoding="utf-8") as stream:
            stream.write(content)


# ---- 单元：vm_stat 解析（含 16384/4096 两代 page size 与行集差异） ----
parsed = mbp.parse_vm_stat(vm_stat_text(16384, 600000, 300000, 148576))
check("vm_stat parses 16k-page form into page size and available bytes",
      parsed and parsed["page_size"] == 16384
      and parsed["available_bytes"] == 1048576 * 16384,
      f"(got={parsed})")

parsed = mbp.parse_vm_stat(vm_stat_text(4096, 500000, 0, 300000))
check("vm_stat parses legacy 4k-page form",
      parsed and parsed["page_size"] == 4096
      and parsed["available_bytes"] == 800000 * 4096,
      f"(got={parsed})")

parsed = mbp.parse_vm_stat(
    "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
    "Pages free:                               100.\n")
check("vm_stat tolerates missing speculative/inactive lines",
      parsed and parsed["available_bytes"] == 100 * 16384, f"(got={parsed})")

check("vm_stat without the page-size header is unusable",
      mbp.parse_vm_stat("Pages free:  100.\n") is None)
check("vm_stat without Pages free is unusable",
      mbp.parse_vm_stat(
          "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
          "Pages wired down: 100.\n") is None)
check("vm_stat garbage is unusable", mbp.parse_vm_stat("total nonsense") is None)

# ---- 单元：memory_pressure 解析（关键词句式 / 百分比句式 / 垃圾） ----
mp = mbp.parse_memory_pressure(
    "The system has sufficient space. (21% of memory in use by apps, 62% available)\n")
check("memory_pressure parses the sufficient-space keyword form",
      mp and mp["level"] == "normal" and mp["available_percent"] == 62.0
      and mp["used_percent"] == 21.0, f"(got={mp})")

mp = mbp.parse_memory_pressure(
    "The system is under increasing pressure. (70% of memory in use, 12% available)\n")
check("memory_pressure parses the increasing-pressure keyword as warn",
      mp and mp["level"] == "warn" and mp["available_percent"] == 12.0,
      f"(got={mp})")

mp = mbp.parse_memory_pressure("The system is in a critical memory situation.\n")
check("memory_pressure parses the critical keyword without percentages",
      mp and mp["level"] == "critical" and mp["available_percent"] is None,
      f"(got={mp})")

mp = mbp.parse_memory_pressure("Memory status: (5% of memory in use, 4% available)\n")
check("memory_pressure derives critical from a bare low-available percentage",
      mp and mp["level"] == "critical", f"(got={mp})")

mp = mbp.parse_memory_pressure("Memory status: (50% of memory in use, 60% available)\n")
check("memory_pressure derives normal from a bare healthy percentage",
      mp and mp["level"] == "normal", f"(got={mp})")

check("memory_pressure garbage is unusable",
      mbp.parse_memory_pressure("nothing recognizable here") is None)

# ---- 单元：vm.swapusage 解析 ----
swap = mbp.parse_swap_usage("total = 2048.00M  used = 512.00M  free = 1536.00M\n")
check("swapusage parses M-suffix values into bytes and a ratio",
      swap and swap["total_bytes"] == 2048 * 1024 * 1024
      and swap["used_bytes"] == 512 * 1024 * 1024
      and abs(swap["used_ratio"] - 0.25) < 1e-9, f"(got={swap})")

swap = mbp.parse_swap_usage("total = 2.00G  used = 1.50G  free = 0.50G\n")
check("swapusage parses G-suffix values",
      swap and swap["used_bytes"] == int(1.5 * GIB)
      and abs(swap["used_ratio"] - 0.75) < 1e-9, f"(got={swap})")

swap = mbp.parse_swap_usage("total = 0B  used = 0B  free = 0B\n")
check("swapusage with no configured swap reports zero pressure",
      swap and swap.get("no_swap") is True and swap["used_ratio"] == 0.0,
      f"(got={swap})")

check("swapusage garbage is unusable", mbp.parse_swap_usage("free lunch") is None)

# ---- 单元：压力聚合（swap 高压收紧档位） ----
agg = mbp.aggregate_pressure(None, None)
check("no pressure signals aggregate to normal without tightening",
      agg["level"] == "normal" and agg["tighten_factor"] == 1.0, f"(got={agg})")

agg = mbp.aggregate_pressure(None, {"used_ratio": 0.80, "no_swap": False})
check("swap used ratio >= 0.75 aggregates to warn (factor 0.5)",
      agg["level"] == "warn" and agg["tighten_factor"] == 0.5, f"(got={agg})")

agg = mbp.aggregate_pressure(None, {"used_ratio": 0.96, "no_swap": False})
check("swap used ratio >= 0.95 aggregates to critical (factor 0)",
      agg["level"] == "critical" and agg["tighten_factor"] == 0.0, f"(got={agg})")

agg = mbp.aggregate_pressure({"level": "critical", "used_percent": None,
                              "available_percent": None},
                             {"used_ratio": 0.10, "no_swap": False})
check("memory_pressure critical wins over a mild swap ratio",
      agg["level"] == "critical" and agg["tighten_factor"] == 0.0, f"(got={agg})")

# ---- 单元：预算解析（env / flag / 默认 / 非法 fail-closed） ----
budget, source = mbp.resolve_budget(None, {})
check("budget falls back to the 3 GiB default",
      budget == BUDGET_DEFAULT and source == "default", f"(got={budget},{source})")

budget, source = mbp.resolve_budget(None, {"SPAWN_WORKER_MEM_BUDGET_BYTES": "1073741824"})
check("budget reads SPAWN_WORKER_MEM_BUDGET_BYTES from env",
      budget == GIB and source == "env", f"(got={budget},{source})")

budget, source = mbp.resolve_budget("3221225472", {"SPAWN_WORKER_MEM_BUDGET_BYTES": "1"})
check("--budget flag overrides the env value",
      budget == BUDGET_DEFAULT and source == "flag", f"(got={budget},{source})")

check("non-integer budget fails closed", mbp.resolve_budget("abc", {}) == (None, "flag"))
check("negative-shaped budget fails closed",
      mbp.resolve_budget(None, {"SPAWN_WORKER_MEM_BUDGET_BYTES": "-5"})[0] is None)

# ---- 集成：fixture 快照驱动 probe 子进程 ----
HEALTHY_MP = "The system has sufficient space. (21% of memory in use by apps, 62% available)\n"
HEALTHY_SWAP = "total = 2048.00M  used = 100.00M  free = 1948.00M\n"
HEALTHY_VM = vm_stat_text(16384, 600000, 300000, 148576)  # 16 GiB 可回收
LOWMEM_VM = vm_stat_text(16384, 200000, 70000, 57680)     # 5 GiB 可回收

FIXTURES = tempfile.mkdtemp(prefix="membudget-fixtures-")


def fixture(name, **files):
    path = os.path.join(FIXTURES, name)
    write_fixture(path, **files)
    return path


healthy_fx = fixture("healthy", hw_memsize="34359738368\n", vm_stat=HEALTHY_VM,
                     memory_pressure=HEALTHY_MP, vm_swapusage=HEALTHY_SWAP)
lowmem_fx = fixture("lowmem", hw_memsize="34359738368\n", vm_stat=LOWMEM_VM,
                    memory_pressure=HEALTHY_MP, vm_swapusage=HEALTHY_SWAP)
swaphigh_fx = fixture("swaphigh", hw_memsize="34359738368\n", vm_stat=HEALTHY_VM,
                      memory_pressure=HEALTHY_MP,
                      vm_swapusage="total = 8192.00M  used = 7000.00M  free = 1192.00M\n")
crit_fx = fixture("critical", hw_memsize="34359738368\n", vm_stat=HEALTHY_VM,
                  memory_pressure="The system is in a critical memory situation.\n",
                  vm_swapusage=HEALTHY_SWAP)
empty_fx = fixture("empty")
nohw_fx = fixture("nohw", vm_stat=HEALTHY_VM, memory_pressure=HEALTHY_MP)
garbage_fx = fixture("garbage", hw_memsize="34359738368\n", vm_stat="pages everywhere",
                     memory_pressure="no keywords no percentages")
pctonly_fx = fixture("pctonly", hw_memsize="34359738368\n", memory_pressure=HEALTHY_MP)
clamp_fx = fixture("clamp", hw_memsize="34359738368\n",
                   vm_stat=vm_stat_text(16384, 10 ** 7, 10 ** 6, 10 ** 6),
                   memory_pressure=HEALTHY_MP, vm_swapusage=HEALTHY_SWAP)
pctclamp_fx = fixture("pctclamp", hw_memsize="34359738368\n",
                      memory_pressure="Memory status: (10% of memory in use, 150% available)\n")

# 正常放行：健康快照 + 默认预算 → slots >= 1，schema 字段稳定。
code, out = run_probe(["--fixture-dir", healthy_fx])
OK_KEYS = {"schema", "status", "reason", "sources", "budget_bytes", "budget_source",
           "total_bytes", "page_size", "availability_basis", "available_bytes",
           "reserve_bytes", "safe_available_bytes", "pressure", "swap", "slots",
           "effective_available_bytes"}
check("healthy fixture allows spawn with slots >= 1",
      code == 0 and out and out["status"] == "ok" and out["slots"] >= 1,
      f"(code={code} out={out})")
check("healthy fixture emits the stable memory-budget.summary.v1 key set",
      out and set(out.keys()) == OK_KEYS, f"(keys={sorted(out.keys()) if out else None})")
check("schema field values keep byte-level types and units",
      out and out["schema"] == "memory-budget.summary.v1"
      and out["total_bytes"] == TOTAL_32G and out["page_size"] == 16384
      and out["availability_basis"] == "vm_stat"
      and isinstance(out["slots"], int)
      and set(out["pressure"].keys()) == {"level", "tighten_factor", "signals"}
      and set(out["swap"].keys()) == {"total_bytes", "used_bytes", "free_bytes",
                                      "used_ratio"},
      f"(out={out})")
check("healthy fixture computes reserve as max(2GiB, 10% total)",
      out and out["reserve_bytes"] == int(TOTAL_32G * 0.10)
      and out["safe_available_bytes"] == 16 * GIB - int(TOTAL_32G * 0.10),
      f"(out={out})")
healthy_slots = out["slots"] if out else None

# swap 高压：同一可用性下额度折算收紧（warn 折半 → slots 减半档）。
code, swap_out = run_probe(["--fixture-dir", swaphigh_fx])
check("swap high pressure tightens the slot ledger (warn halves capacity)",
      code == 0 and swap_out and swap_out["pressure"]["level"] == "warn"
      and swap_out["pressure"]["tighten_factor"] == 0.5
      and swap_out["slots"] < healthy_slots
      and swap_out["slots"] == (16 * GIB - int(TOTAL_32G * 0.10)) // 2 // BUDGET_DEFAULT,
      f"(code={code} out={swap_out})")

# 压力 critical：slots 直接归零，deny。
code, crit_out = run_probe(["--fixture-dir", crit_fx])
check("critical pressure zeroes slots and denies",
      code == 3 and crit_out and crit_out["status"] == "denied"
      and crit_out["slots"] == 0, f"(code={code} out={crit_out})")

# 低内存：deny + 诊断含 可用/预算/缺口。
code, low_out = run_probe(["--fixture-dir", lowmem_fx])
check("low-memory fixture denies with exit 3",
      code == 3 and low_out and low_out["status"] == "denied"
      and low_out["slots"] == 0, f"(code={code} out={low_out})")
reason = low_out["reason"] if low_out else ""
check("denial reason carries available/budget/deficit diagnostics",
      "safe_available=" in reason and "budget=" in reason and "缺口" in reason,
      f"(reason={reason!r})")

# 读取全失败：exit 1，payload 无任何额度字段。
code, empty_out = run_probe(["--fixture-dir", empty_fx])
check("all sources missing exits 1 with no quota fields",
      code == 1 and empty_out and empty_out["status"] == "unprobeable"
      and "slots" not in empty_out and "available_bytes" not in empty_out
      and "safe_available_bytes" not in empty_out,
      f"(code={code} out={empty_out})")

code, nohw_out = run_probe(["--fixture-dir", nohw_fx])
check("missing hw.memsize alone is unprobeable (never invent totals)",
      code == 1 and nohw_out and nohw_out["status"] == "unprobeable"
      and "total_bytes" not in nohw_out and "slots" not in nohw_out,
      f"(code={code} out={nohw_out})")

code, garbage_out = run_probe(["--fixture-dir", garbage_fx])
check("unreadable vm_stat/memory_pressure snapshots fail closed",
      code == 1 and garbage_out and garbage_out["status"] == "unprobeable",
      f"(code={code} out={garbage_out})")

# memory_pressure 百分比兜底基准（vm_stat 缺席）。
code, pct_out = run_probe(["--fixture-dir", pctonly_fx])
check("memory_pressure percentage is a valid availability fallback basis",
      code == 0 and pct_out and pct_out["availability_basis"] == "memory_pressure_percent"
      and pct_out["page_size"] is None
      and pct_out["available_bytes"] == int(TOTAL_32G * 0.62),
      f"(code={code} out={pct_out})")

# 可用性钳位：vm_stat 荒高值不超过物理总量（钳到 32GiB 后仍足额放行）。
code, clamp_out = run_probe(["--fixture-dir", clamp_fx])
check("availability is clamped to the physical total",
      code == 0 and clamp_out and clamp_out["available_bytes"] == TOTAL_32G,
      f"(code={code} out={clamp_out})")

# 病态百分比兜底：memory_pressure 可用百分比 >100%（病态快照）时钳位到物理总量。
code, pctclamp_out = run_probe(["--fixture-dir", pctclamp_fx])
check("pathological memory_pressure percent above 100 clamps to the physical total",
      code == 0 and pctclamp_out
      and pctclamp_out["availability_basis"] == "memory_pressure_percent"
      and pctclamp_out["available_bytes"] == TOTAL_32G,
      f"(code={code} out={pctclamp_out})")

# env 覆盖：预算 1GiB 时低内存档变为可派发 1 slot。
code, over_out = run_probe(["--fixture-dir", lowmem_fx],
                           env=probe_env(SPAWN_WORKER_MEM_BUDGET_BYTES=str(GIB)))
check("smaller env budget reopens the low-memory fixture for one slot",
      code == 0 and over_out and over_out["budget_bytes"] == GIB
      and over_out["slots"] == 1, f"(code={code} out={over_out})")

# 预算 =0：显式直通，slots=null。
code, off_out = run_probe(["--fixture-dir", lowmem_fx],
                          env=probe_env(SPAWN_WORKER_MEM_BUDGET_BYTES="0"))
check("SPAWN_WORKER_MEM_BUDGET_BYTES=0 disables the gate (opt-out passthrough)",
      code == 0 and off_out and off_out["status"] == "disabled"
      and off_out["slots"] is None
      and "effective_available_bytes" not in off_out
      and "SPAWN_WORKER_MEM_BUDGET_BYTES=0" in off_out["reason"],
      f"(code={code} out={off_out})")

# 非法预算：fail-closed exit 1。
code, bad_out = run_probe([], env=probe_env(SPAWN_WORKER_MEM_BUDGET_BYTES="3GB"))
check("invalid env budget fails closed with config_invalid",
      code == 1 and bad_out and bad_out["status"] == "config_invalid"
      and "slots" not in bad_out, f"(code={code} out={bad_out})")

# 真实机器 smoke：无 fixture 时现场读源，本机必须可探测且 schema 一致。
code, real_out = run_probe([])
check("real-machine smoke probe stays probeable with a stable schema",
      code in (0, 3) and real_out
      and real_out.get("status") in ("ok", "denied")
      and real_out.get("schema") == "memory-budget.summary.v1"
      and isinstance(real_out.get("slots"), int),
      f"(code={code} out={real_out})")
if real_out and real_out.get("status") == "ok":
    print(f"  real-machine ledger: {real_out['reason']}")

# ---- E2E：spawn-worker.sh 内存门（fake Orca CLI，与真实 runtime 隔离） ----
# macOS 的 /var/folders 临时目录是 symlink；spawn-worker.sh 会把 --project 用
# pwd -P 物理化，fake orca 返回的路径必须同样是物理路径才能命中 auto 模式。
E2E_ROOT = os.path.realpath(tempfile.mkdtemp(prefix="membudget-e2e-"))
E2E_PROJECT = os.path.join(E2E_ROOT, "business repo")
E2E_WS = os.path.join(E2E_ROOT, "orca workspaces")
E2E_ORCA_BIN = os.path.join(E2E_ROOT, "fake-orca")
E2E_ORCA_LOG = os.path.join(E2E_ROOT, "orca-calls.log")
E2E_STATE = os.path.join(E2E_ROOT, "state")
E2E_FAKE_BIN = os.path.join(E2E_ROOT, "bin")
E2E_PERSONAL_CONFIG = os.path.join(E2E_ROOT, "personal-quota-disabled.json")
for directory in (E2E_PROJECT, E2E_WS, E2E_STATE, E2E_FAKE_BIN):
    os.makedirs(directory, exist_ok=True)


def git(project, *args):
    subprocess.run(["git", "-C", project, *args], check=True, capture_output=True,
                   text=True)


git(E2E_PROJECT, "init", "-q")
git(E2E_PROJECT, "config", "user.email", "mem-budget@test.local")
git(E2E_PROJECT, "config", "user.name", "mem-budget-test")
git(E2E_PROJECT, "commit", "-q", "--allow-empty", "-m", "init")
with open(E2E_PERSONAL_CONFIG, "w", encoding="utf-8") as stream:
    stream.write('{"quota_aware_routing":{"enabled":false}}\n')

with open(E2E_ORCA_BIN, "w", encoding="utf-8") as stream:
    stream.write("""#!/usr/bin/env bash
# fake Orca CLI：测试状态文件驱动；每次调用原文追加进日志（源自 test-spawn-worker-orca.sh）。
state="${E2E_ORCA_STATE:?}"
log="${E2E_ORCA_LOG:?}"
printf '%s\\n' "$*" >> "$log"
resp_worktree() {
  jq -cn --arg id "repo-1::$1" --arg path "$1" '{result:{worktree:{id:$id,path:$path}}}'
}
case "$1 $2" in
  "worktree current")
    resp_worktree "$E2E_ORCA_PROJECT" ;;
  "status --json")
    printf '%s\\n' '{"result":{"runtime":{"appVersion":"1.4.9","capabilities":["terminal.multiplex.v1","orchestration.contract.v1"]}}}' ;;
  "worktree create")
    name=""
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --name) name="$2" ;;
      esac
      shift
    done
    wt_path="$E2E_ORCA_WS/$name"
    git -C "$E2E_ORCA_PROJECT" worktree add -q -b "$name" "$wt_path" HEAD >/dev/null 2>&1 || exit 1
    resp_worktree "$wt_path" ;;
  "worktree show")
    wt=""
    while [ "$#" -gt 0 ]; do
      case "$1" in
        id:*|path:*) wt="${1#id:}"; wt="${wt#path:}" ;;
      esac
      shift
    done
    case "$wt" in *::*) wt="${wt#*::}" ;; esac
    resp_worktree "$wt" ;;
  "terminal create")
    printf '%s\\n' '{"result":{"terminal":{"handle":"term-membudget"}}}' ;;
  "terminal wait")
    printf '%s\\n' '{"result":{"ok":true}}' ;;
  "orchestration run-create")
    printf '%s\\n' '{"result":{"run":{"id":"run-membudget","coordinator_handle":"term-pm-membudget"}}}' ;;
  "orchestration task-create")
    printf '%s\\n' '{"result":{"task":{"id":"task-membudget"}}}' ;;
  "orchestration worker-start")
    printf '%s\\n' '{"result":{"worker":{"dispatch":{"id":"ctx-membudget"}}}}' ;;
  "orchestration dispatch-show")
    printf '%s\\n' '{"result":{"dispatch":{"id":"ctx-membudget"}}}' ;;
  *) exit 1 ;;
esac
""")
os.chmod(E2E_ORCA_BIN, 0o755)

with open(os.path.join(E2E_FAKE_BIN, "ps"), "w", encoding="utf-8") as stream:
    stream.write("""#!/usr/bin/env bash
# 隔离测试进程树：给 harness 祖先链检测一个确定的单层 codex 链。
case "$*" in
  *"-o ppid="*) printf '%s\\n' '1' ;;
  *"-o comm="*) printf '%s\\n' '/usr/local/bin/codex' ;;
  *"-o args="*) printf '%s\\n' 'codex' ;;
  *) exit 1 ;;
esac
""")
os.chmod(os.path.join(E2E_FAKE_BIN, "ps"), 0o755)


def run_spawn(branch, fixture_dir, budget=None, timeout=300):
    env = probe_env(
        ORCA_CLI_COMMAND=E2E_ORCA_BIN,
        E2E_ORCA_STATE=E2E_STATE, E2E_ORCA_LOG=E2E_ORCA_LOG,
        E2E_ORCA_PROJECT=E2E_PROJECT, E2E_ORCA_WS=E2E_WS,
        MULTI_AGENT_ORCHESTRATION_PERSONAL_CONFIG=E2E_PERSONAL_CONFIG,
        MEM_BUDGET_FIXTURE_DIR=fixture_dir,
        PATH=E2E_FAKE_BIN + os.pathsep + os.environ.get("PATH", ""),
    )
    if budget is not None:
        env["SPAWN_WORKER_MEM_BUDGET_BYTES"] = budget
    proc = subprocess.run(
        ["bash", SPAWN_WORKER,
         "--project", E2E_PROJECT, "--branch", branch, "--session", branch,
         "--worker-backend", "codebuddy",
         "--command", "codebuddy --permission-mode acceptEdits",
         "--no-trust-auto", "--no-permission-auto", "--no-permission-auto-bg",
         "--no-external-imports-auto", "--orca-supervised",
         "--task-spec", "mem budget gate e2e spec"],
        capture_output=True, text=True, env=env, timeout=timeout)
    return proc


def orca_log_text():
    try:
        with open(E2E_ORCA_LOG, encoding="utf-8") as stream:
            return stream.read()
    except OSError:
        return ""


# E2E 用例 1：低内存 fixture → 专用 exit 4 + 诊断 + 零 worktree/terminal 副作用。
open(E2E_ORCA_LOG, "w").close()
proc = run_spawn("membudget-deny", lowmem_fx)
mutation_calls = [line for line in orca_log_text().splitlines()
                  if re.search(r"worktree create|terminal create|run-create|"
                               r"task-create|worker-start", line)]
check("low-memory spawn is rejected with the dedicated exit code 4",
      proc.returncode == 4,
      f"(rc={proc.returncode} stderr={proc.stderr[-600:]})")
check("low-memory rejection prints the stable machine marker",
      "SPAWN_WORKER_MEM_BUDGET_DENIED" in proc.stderr
      and "PARKED_FOR_MEMORY" in proc.stderr,
      f"(stderr={proc.stderr[-600:]})")
check("low-memory rejection carries available/budget/deficit diagnostics",
      "safe_available=" in proc.stderr and "budget=" in proc.stderr
      and "缺口" in proc.stderr, f"(stderr={proc.stderr[-600:]})")
check("low-memory rejection happens before any worktree/terminal side effect",
      mutation_calls == [], f"(mutation_calls={mutation_calls})")
check("low-memory rejection leaves no Session Context on disk",
      not os.path.exists(os.path.join(E2E_PROJECT, ".claude", "agent-sessions")))
check("low-memory rejection leaves no worktree under the workspace root",
      not os.path.exists(os.path.join(E2E_WS, "membudget-deny")))

# E2E 用例 2：健康 fixture → 放行并输出 SPAWN_WORKER_MEM_BUDGET 账本行。
proc = run_spawn("membudget-ok", healthy_fx)
check("healthy fixture spawn passes the gate and exits 0",
      proc.returncode == 0, f"(rc={proc.returncode} stderr={proc.stderr[-800:]})")
ledger = re.search(r"SPAWN_WORKER_MEM_BUDGET: available=(\d+) budget=(\d+) slots=(\d+)",
                   proc.stdout)
check("healthy spawn logs the SPAWN_WORKER_MEM_BUDGET ledger line",
      bool(ledger), f"(stdout_tail={proc.stdout[-400:]})")
if ledger:
    check("ledger line reflects the fixture ledger (16GiB-3.2GiB safe, 3GiB budget)",
          int(ledger.group(1)) == 16 * GIB - int(TOTAL_32G * 0.10)
          and int(ledger.group(2)) == BUDGET_DEFAULT and int(ledger.group(3)) >= 1,
          f"(ledger={ledger.group(0)})")

# E2E 用例 3：SPAWN_WORKER_MEM_BUDGET_BYTES=0 → 直通放行。
proc = run_spawn("membudget-off", lowmem_fx, budget="0")
check("budget=0 keeps a low-memory spawn flowing (explicit opt-out)",
      proc.returncode == 0
      and "SPAWN_WORKER_MEM_BUDGET: disabled" in proc.stdout,
      f"(rc={proc.returncode} stdout_tail={proc.stdout[-400:]})")

# ---- 清理 ----
shutil.rmtree(FIXTURES, ignore_errors=True)
shutil.rmtree(E2E_ROOT, ignore_errors=True)

print(f"mem-budget-probe tests: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
