#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkBuddy trace 全量审计:跑 ~/.workbuddy/traces/ 下所有 trace,
统计提取健康度,标出异常(空会话/漏抽/去重失败/全截断)。
复用 probe_workbuddy_trace.py 已验证的提取逻辑。
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
from probe_workbuddy_trace import extract_user_queries_robust  # noqa: E402

ROOT = Path.home() / ".workbuddy" / "traces"
TOOL_NAMES = {"Bash", "Read", "Write", "Glob", "Skill", "TaskCreate",
              "TaskUpdate", "Edit", "Grep", "WebFetch", "WebSearch"}
TRUNC_THRESHOLD = 99000  # toolInput 超过此长度视为被截断


def audit_one(f: Path) -> dict:
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        return {"path": str(f), "parse_fail": str(e)[:60]}
    spans = d.get("spans", [])
    gens = [s for s in spans if s.get("name") == "generation"]
    trunc = sum(1 for g in gens if len(g.get("toolInput") or "") > TRUNC_THRESHOLD)
    # 用户输入(全局去重)
    seen = set()
    for g in gens:
        for q in extract_user_queries_robust(g.get("toolInput")):
            seen.add(q.strip())
    # assistant 文本回复 + 工具调用
    asst = 0
    for s in gens:
        try:
            to = json.loads(s.get("toolOutput") or "")
            if isinstance(to, list) and to and isinstance(to[0], dict):
                msg = (to[0].get("choices") or [{}])[0].get("message", {})
                c = msg.get("content")
                if isinstance(c, str) and c.strip():
                    asst += 1
        except Exception:
            pass
    tools = sum(1 for s in spans if s.get("name") in TOOL_NAMES)
    return {
        "sid": f.parent.name, "spans": len(spans), "gens": len(gens),
        "trunc_gens": trunc, "user": len(seen), "asst": asst, "tools": tools,
    }


def main():
    files = sorted(ROOT.rglob("trace_*.json"))
    print(f"扫描 {ROOT}: 共 {len(files)} 个 trace 文件\n", file=sys.stderr)
    rows = []
    for i, f in enumerate(files, 1):
        rows.append(audit_one(f))
        if i % 50 == 0:
            print(f"  …已处理 {i}/{len(files)}", file=sys.stderr)

    n = len(rows)
    parse_fail = [r for r in rows if r.get("parse_fail")]
    ok = [r for r in rows if not r.get("parse_fail")]
    has_content = [r for r in ok if r["user"] > 0 or r["asst"] > 0 or r["tools"] > 0]
    empty = [r for r in ok if r["user"] == 0 and r["asst"] == 0 and r["tools"] == 0]

    def bucket(val, edges):
        for lo, hi, label in edges:
            if lo <= val < hi:
                return label
        return edges[-1][2]
    user_edges = [(0, 1, "0"), (1, 6, "1-5"), (6, 21, "6-20"), (21, 10**9, ">20")]
    trunc_edges = [(0, 1, "无截断"), (1, 10**9, "有截断")]

    print("=" * 60)
    print("WorkBuddy trace 全量审计汇总")
    print("=" * 60)
    print(f"总 trace 数        : {n}")
    print(f"parse 失败         : {len(parse_fail)}")
    print(f"有实质内容         : {len(has_content)} ({len(has_content)*100//max(len(ok),1)}%)")
    print(f"空会话(无user/asst/tool): {len(empty)}")
    print()
    print("用户输入数分布(去重后):")
    from collections import Counter
    uc = Counter(bucket(r["user"], user_edges) for r in ok)
    for _, _, lab in user_edges:
        print(f"  {lab:>6}: {uc.get(lab, 0)}")
    print()
    print("generation 截断分布:")
    tc = Counter(bucket(r["trunc_gens"], trunc_edges) for r in ok)
    print(f"  无截断: {tc.get('无截断', 0)}    有截断(≥1个gen>99KB): {tc.get('有截断', 0)}")
    # 全截断(所有 generation 都截断)的会话
    all_trunc = [r for r in ok if r["gens"] > 0 and r["trunc_gens"] == r["gens"]]
    print(f"  其中全部 generation 都截断: {len(all_trunc)}")
    print()

    # 异常清单
    print("=" * 60)
    print("需关注的异常(可能漏抽 / 去重失败 / 大空会话)")
    print("=" * 60)
    # A) 非空(span>20)但 user=0:可能漏抽
    suspect_miss = [r for r in ok if r["spans"] > 20 and r["user"] == 0]
    print(f"\n[A] span>20 但 user=0(疑似漏抽 user_query): {len(suspect_miss)}")
    for r in suspect_miss[:8]:
        print(f"    sid={r['sid']} spans={r['spans']} gens={r['gens']} trunc={r['trunc_gens']} asst={r['asst']} tools={r['tools']}")
    # B) user>20:可能去重失败
    suspect_dup = [r for r in ok if r["user"] > 20]
    print(f"\n[B] user>20(疑似去重失败): {len(suspect_dup)}")
    for r in suspect_dup[:8]:
        print(f"    sid={r['sid']} user={r['user']} spans={r['spans']} gens={r['gens']}")
    # C) parse 失败
    print(f"\n[C] parse 失败: {len(parse_fail)}")
    for r in parse_fail[:8]:
        print(f"    {r['path']}: {r['parse_fail']}")


if __name__ == "__main__":
    main()
