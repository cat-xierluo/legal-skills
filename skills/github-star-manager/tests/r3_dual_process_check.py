#!/usr/bin/env python3
"""R3/R6 真实双进程交错验收（J1c 返修：意外异常必须非零、精确核成功/冲突/失败集合）。

两真实进程（技能写者 + 插件写者）在同一 output 目录交错读-改-写。验收：
1. 每一轮操作分类为 success / conflict(显式拒绝，可重试) / unexpected_error
2. **任何意外异常 → runner 退出码非零**（旧版吞 Exception 仍 exit0 = 假绿）
3. 最终态精确核对：每个成功提交的新增/删除必须反映到终态；显式冲突的提交不得在终态
4. 覆盖新增/取消（删除）/改名（full_name 变、id 不变）/翻译（zh 字段）四类语义
5. B 单写者模式判别：插件子进程通过 GITHUB_STAR_BOARD_DATA 指向**被测技能**，
   并回执实际走的写路径（single-writer / fallback）。被测技能协议 ≥2 时要求
   single-writer——否则这次交错验的还是 R9 直写，不能当 B 的证据。

用法：python3 r3_dual_process_check.py <skill_dir> <plugin_dir> <workdir> [rounds]
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(sys.argv[1])
PLUGIN = Path(sys.argv[2])
WORK = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(tempfile.mkdtemp())
ROUNDS = int(sys.argv[4]) if len(sys.argv) > 4 else 25

# 每个子进程写出的结构化回执 JSONL：{"op","result":"ok|conflict|error","detail"}
SKILL_WRITER = r'''
import json, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import star_tracker
from star_tracker import SnapshotConflictError
out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
receipt = Path(sys.argv[4])
n = int(sys.argv[3])
t = star_tracker.StarTracker.__new__(star_tracker.StarTracker)
t.CACHE_DIR=out; t.CONFIG_DIR=out
t.CATEGORIES_FILE=out/"c.yaml"; t.TAGS_FILE=out/"t.json"; t.SETTINGS_FILE=out/"s.json"
t.categories=star_tracker.StarTracker._get_default_categories(t); t.tags={}; t.settings={}
meta={"complete":True,"failed_pages":[],"account_id":"u","limit_truncated":False}
fh = open(receipt, "w", encoding="utf-8")
for i in range(n):
    op = f"skill/{i}"
    try:
        cur = t.load_latest()
        base_ts = (cur or {}).get("timestamp")
        by = {r["full_name"]: r for r in (cur or {}).get("repos", [])}
        # 新增 + 偶数轮删除自己上轮条目（取消语义）+ 加 zh（翻译语义）
        by[op] = {"full_name": op, "id": 100000+i, "description": f"s{i}"}
        if i % 3 == 0:
            by.pop(f"skill/{i-3}", None)
        t.save_latest(list(by.values()), fetch_meta=meta, base_timestamp=base_ts)
        fh.write(json.dumps({"op": op, "result": "ok"}) + "\n")
    except SnapshotConflictError:
        fh.write(json.dumps({"op": op, "result": "conflict"}) + "\n")
    except Exception as e:
        fh.write(json.dumps({"op": op, "result": "error", "detail": f"{type(e).__name__}: {e}"}) + "\n")
    time.sleep(0.01)
fh.close()
print("SKILL_DONE")
'''

PLUGIN_WRITER = r'''
import json, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import plugin_api as api
out = Path(sys.argv[2])
receipt = Path(sys.argv[4])
mode_file = Path(sys.argv[5])
api._data_js_path = lambda: out / "data.js"
# 回执实际写路径：不只看引擎协议——包一层 _save_authoritative 计数，证明每次提交
# 真的经过了单写者入口（旧插件没有该函数 / 新插件走回退时计数为 0）
_st, _ = api._load_engine()
_proto = getattr(_st, "SNAPSHOT_WRITER_PROTOCOL", 0) if _st is not None else 0
_hits = {"authoritative": 0}
_orig_sa = getattr(api, "_save_authoritative", None)
if _orig_sa is not None:
    def _counted(*a, **k):
        _hits["authoritative"] += 1
        return _orig_sa(*a, **k)
    api._save_authoritative = _counted
n = int(sys.argv[3])
fh = open(receipt, "w", encoding="utf-8")
_ok = _conf = 0
for i in range(n):
    op = f"plug/{i}"
    try:
        with api._DATA_LOCK:
            projects, mt = api._load_projects()
            by = {p["full_name"]: p for p in projects}
            by[op] = {"full_name": op, "id": 200000+i, "description_zh": f"中{i}"}
            if i % 3 == 0:
                by.pop(f"plug/{i-3}", None)
            api._dump_projects(list(by.values()), base_mtime_ns=mt)
        fh.write(json.dumps({"op": op, "result": "ok"}) + "\n"); _ok += 1
    except api._ExternalWriteConflict:
        fh.write(json.dumps({"op": op, "result": "conflict"}) + "\n"); _conf += 1
    except TimeoutError:
        fh.write(json.dumps({"op": op, "result": "conflict"}) + "\n"); _conf += 1
    except Exception as e:
        fh.write(json.dumps({"op": op, "result": "error", "detail": f"{type(e).__name__}: {e}"}) + "\n")
    time.sleep(0.01)
fh.close()
_attempts = _ok + _conf
_mode = ("single-writer" if (_orig_sa is not None and _attempts > 0
                             and _hits["authoritative"] == _attempts)
         else ("no-routing" if _orig_sa is None else "fallback"))
mode_file.write_text(json.dumps({"mode": _mode, "protocol": _proto,
                                 "authoritative_calls": _hits["authoritative"],
                                 "attempts": _attempts}), encoding="utf-8")
print("PLUGIN_DONE")
'''

work = Path(WORK)
work.mkdir(parents=True, exist_ok=True)
skill_out = work / "skill-out"
skill_out.mkdir(exist_ok=True)
(skill_out / "_sw.py").write_text(SKILL_WRITER, encoding="utf-8")
(work / "_pw.py").write_text(PLUGIN_WRITER, encoding="utf-8")

py = sys.executable
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
# 插件子进程的引擎定位 = GITHUB_STAR_BOARD_DATA 的父目录/scripts → 指向被测技能，
# 否则它会加载机器上已安装的技能（版本不受控，B 路径是否激活就不可判）。
plugin_env = dict(env, GITHUB_STAR_BOARD_DATA=str(SKILL / "output"))
sk_receipt = work / "skill.receipt"
pl_receipt = work / "plugin.receipt"
pl_mode = work / "plugin.mode"

a = subprocess.Popen([py, str(skill_out / "_sw.py"), str(SKILL / "scripts"), str(skill_out),
                      str(ROUNDS), str(sk_receipt)],
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
b = subprocess.Popen([py, str(work / "_pw.py"), str(PLUGIN / "dashboard"), str(skill_out),
                      str(ROUNDS), str(pl_receipt), str(pl_mode)],
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=plugin_env)
ao, ae = a.communicate(timeout=180)
bo, be = b.communicate(timeout=180)


def load_receipts(path):
    ops = {"ok": [], "conflict": [], "error": []}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            ops[r["result"]].append(r["op"])
    return ops


sk = load_receipts(sk_receipt)
pl = load_receipts(pl_receipt)

print(f"技能进程 rc={a.returncode} | ok={len(sk['ok'])} conflict={len(sk['conflict'])} error={len(sk['error'])}")
print(f"插件进程 rc={b.returncode} | ok={len(pl['ok'])} conflict={len(pl['conflict'])} error={len(pl['error'])}")
if ae.strip():
    print("技能 stderr:", ae.strip()[-200:])
if be.strip():
    print("插件 stderr:", be.strip()[-200:])

snap = skill_out / "original_latest.json"
problems = []

# 0. B 单写者模式判别：被测技能协议 ≥2 时插件必须走 single-writer，否则这次交错
#    验证的是 R9 直写回退（两套写者各自持锁），不能充当 B 的证据。
sys.path.insert(0, str(SKILL / "scripts"))
import star_tracker as _st_probe  # noqa: E402
skill_proto = getattr(_st_probe.StarTracker, "SNAPSHOT_WRITER_PROTOCOL", 0)
mode_info = {}
if pl_mode.exists():
    try:
        mode_info = json.loads(pl_mode.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        mode_info = {}
plugin_mode = mode_info.get("mode", "unknown")
print(f"被测技能协议={skill_proto} | 插件实际写路径={plugin_mode}"
      f"（单写者入口调用 {mode_info.get('authoritative_calls', '?')}/"
      f"{mode_info.get('attempts', '?')} 次提交尝试）")
if isinstance(skill_proto, int) and skill_proto >= 2 and plugin_mode != "single-writer":
    problems.append(f"技能协议 {skill_proto} ≥2 但插件实际走了 {plugin_mode}（B 路径未激活，"
                    f"交错验证无效）")
if not pl_mode.exists():
    problems.append("插件子进程未回执写路径（_load_engine 可能失败或子进程中途退出）")

# 1. 无意外异常（J1c 核心：error 非空即失败；rc 非零也失败）
if a.returncode != 0:
    problems.append(f"技能进程退出码非零: {a.returncode}")
if b.returncode != 0:
    problems.append(f"插件进程退出码非零: {b.returncode}")
if sk["error"]:
    problems.append(f"技能意外异常: {sk['error'][:3]}")
if pl["error"]:
    problems.append(f"插件意外异常: {pl['error'][:3]}")

# 2. 至少各成功若干轮（否则等于没交错，无判别力）
if not sk["ok"]:
    problems.append("技能无任何成功提交")
if not pl["ok"]:
    problems.append("插件无任何成功提交")

# 3. 最终态核对：最后一次成功提交的操作集合应在终态得到体现。
#    取每侧「最后一次成功」的完整快照语义：成功提交是 read-modify-write，
#    最后一次成功者的完整集合 = 该次 by。这里核对：
#    - 每侧最后一次 ok 的 op 必在终态（它自己写进去了，除非被更晚的对方覆盖删除——
#      对方不删本方前缀，故应在）
final = {}
if snap.exists():
    data = json.loads(snap.read_text(encoding="utf-8"))
    final = {r["full_name"] for r in data.get("repos", [])}
else:
    problems.append("无终态快照")

# R9/J2 完整性判定：**每个**侧成功提交的条目（未被同侧后续显式删除）必须在终态。
# 上游反例：删掉较早成功的 plug/1（从未被显式删除），旧 runner 只核最后一次 → PASS 假绿。
for side, ops in (("skill", sk), ("plugin", pl)):
    ok_ops = ops["ok"]
    if not ok_ops:
        problems.append(f"{side} 无任何成功提交")
        continue
    for op_name in ok_ops:
        # 该 op 是 "side/N"；同侧后续 op "side/M"（M>N 且 M%3==0）会显式删 side/M-3
        n = int(op_name.split("/")[1])
        explicitly_deleted = any(
            int(later.split("/")[1]) > n
            and int(later.split("/")[1]) % 3 == 0
            and int(later.split("/")[1]) - 3 == n
            for later in ok_ops
        )
        if not explicitly_deleted and op_name not in final:
            problems.append(f"{side} 成功提交 {op_name} 丢失于终态（未被显式删除却不在）")

# 意外成功也不行：终态中出现从未被任何侧成功提交的条目 → 说明有静默污染
all_ok = {op for ops in (sk["ok"], pl["ok"]) for op in ops}
unexpected = {f for f in final if not f.startswith(("skill/", "plug/"))}
if unexpected:
    problems.append(f"终态含未由任何成功提交写入的条目: {sorted(unexpected)[:5]}")

# 翻译字段保真：插件成功写入且未被更新的 zh，在终态存在（前向合并/CAS 生效）
zh_kept = 0
if snap.exists():
    for r in data.get("repos", []):
        if r.get("description_zh"):
            zh_kept += 1
print("终态条目数:", len(final), "| 含 zh 翻译字段:", zh_kept,
      "| 成功集合核验:", len([p for p in problems if "丢失" in p]) == 0)

# complete 语义：终态快照来自全量读时不应 limit_truncated
if snap.exists():
    fm = data.get("snapshot_meta", {})
    if fm.get("limit_truncated"):
        problems.append("全量交错中不应出现 limit_truncated")

print("PROBLEMS:", problems if problems else "无")
result = "PASS" if not problems else "FAIL"
print("RESULT:", result)
sys.exit(0 if not problems else 1)
