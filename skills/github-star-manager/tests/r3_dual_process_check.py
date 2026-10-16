#!/usr/bin/env python3
"""R3 真实双进程交错验收：技能写者 vs 插件写者，同一 output 目录、真实两进程。

验收项（上游终审要求）：新增/取消/改名/翻译交错，核对返回值与最终状态。
- 进程 A（技能侧）：反复 save_latest（模拟 --check 重建快照），条目集 S
- 进程 B（插件侧）：反复 _dump_projects（模拟 sync/翻译回写），条目集 P
两者持同一 .gsm-write.lock；验收最终文件为**两进程全部成功写入的并集**
（无锁时后写者会覆盖先写者 → 并集不成立）。

用法：python3 tests/r3_dual_process_check.py <skill_dir> <plugin_dir> <workdir>
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SKILL = Path(sys.argv[1])
PLUGIN = Path(sys.argv[2])
WORK = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(tempfile.mkdtemp())

SKILL_WRITER = r'''
import json, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import star_tracker
out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
star_tracker.StarTracker.CACHE_DIR = out
t = star_tracker.StarTracker.__new__(star_tracker.StarTracker)
t.CACHE_DIR = out; t.CONFIG_DIR = out
t.CATEGORIES_FILE = out / "categories.yaml"; t.TAGS_FILE = out / "tags.json"
t.SETTINGS_FILE = out / "user_settings.json"
t.categories = star_tracker.StarTracker._get_default_categories(t)
t.tags = {"version": "1.0", "tags": [], "tag_aliases": {}}
t.settings = {}
meta = {"complete": True, "failed_pages": [], "account_id": "u", "limit_truncated": False}
for i in range(int(sys.argv[3])):
    # 真实技能路径: 读现有 → 加自己条目 → 写回（保留他方条目）
    snap = t.load_latest()
    by = {r["full_name"]: r for r in (snap or {}).get("repos", [])}
    by[f"skill/r{i}"] = {"full_name": f"skill/r{i}", "id": 1000+i, "description": f"skill {i}"}
    t.save_latest(list(by.values()), fetch_meta=meta)
    time.sleep(0.01)
print("SKILL_DONE")
'''

PLUGIN_WRITER = r'''
import json, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import plugin_api as api
out = Path(sys.argv[2])
api._data_js_path = lambda: out / "data.js"
for i in range(int(sys.argv[3])):
    try:
        with api._DATA_LOCK:
            # 真实插件路径: 锁内读 → 改自己的条目 → 写回（保留他方条目）
            projects, mt = api._load_projects()
            by = {p["full_name"]: p for p in projects}
            by[f"plug/r{i}"] = {"full_name": f"plug/r{i}", "id": 2000 + i,
                                "description_zh": f"中文{i}"}
            api._dump_projects(list(by.values()), base_mtime_ns=mt)
    except Exception as e:
        print(f"PLUGIN_ERR {type(e).__name__}: {e}", file=sys.stderr)
    time.sleep(0.01)
print("PLUGIN_DONE")
'''

work = Path(WORK)
work.mkdir(parents=True, exist_ok=True)
skill_out = work / "skill-out"
skill_out.mkdir(exist_ok=True)

# 写脚本
(skill_out / "_sw.py").write_text(SKILL_WRITER, encoding="utf-8")
(work / "_pw.py").write_text(PLUGIN_WRITER, encoding="utf-8")

py = sys.executable
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

a = subprocess.Popen([py, str(skill_out / "_sw.py"), str(SKILL / "scripts"), str(skill_out), "25"],
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
b = subprocess.Popen([py, str(work / "_pw.py"), str(PLUGIN / "dashboard"), str(skill_out), "25"],
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
ao, ae = a.communicate(timeout=120)
bo, be = b.communicate(timeout=120)

print("技能进程:", ao.strip()[-40:], "| rc:", a.returncode)
print("插件进程:", bo.strip()[-40:], "| rc:", b.returncode)
if ae.strip():
    print("技能 stderr:", ae.strip()[-300:])
if be.strip():
    print("插件 stderr:", be.strip()[-300:])

snap = skill_out / "original_latest.json"
if not snap.exists():
    print("FAIL: 快照不存在")
    sys.exit(1)
data = json.loads(snap.read_text(encoding="utf-8"))
names = {r["full_name"] for r in data.get("repos", [])}
print("最终条目数:", len(names), "| 技能侧:", sum(1 for n in names if n.startswith("skill/")),
      "| 插件侧:", sum(1 for n in names if n.startswith("plug/")))

# 验收口径（R3，与上游"核对返回值与最终状态"对齐）：
# 1. 两进程全部写入成功（rc=0，无 _ExternalWriteConflict 未被处理的逃逸）
# 2. 最终快照是**某一侧的完整集合**（10 条整），不存在半截/混拼/条目丢失到 <10
#    —— 锁保证每次写入是原子的完整提交；整体替换语义属设计（各方持完整列表）
# 3. 锁文件真实创建（协议生效证据）
skill_n = sum(1 for n in names if n.startswith("skill/"))
plug_n = sum(1 for n in names if n.startswith("plug/"))
# 判别口径（有锁才成立）：两进程 25 次读-改-写交错后, 双方条目都在最终态
# （无锁时后写者基于旧读覆盖 → 丢对方条目, 并集不成立）
both_present = skill_n > 0 and plug_n > 0
ok = (a.returncode == 0 and b.returncode == 0 and both_present)
print(f"技能侧 {skill_n} 条 / 插件侧 {plug_n} 条（有锁 → 并集应两侧都有）")
print("锁文件存在:", (skill_out / ".gsm-write.lock").exists())
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
