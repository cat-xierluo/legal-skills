#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate-query-filters.py — 校验 research-plan / query 的 filter×interface 合法性。

把 references/07-research-middleware.md §9.1「字段归属接口速查表」从软约束
(worker 自觉读) 变成硬门禁 (脚本校验)。字段表以 scripts/yd_search.py 各
subparser 的 add_argument 为权威；改字段时同步更新 §9.1 与本表。

用法:
  python3 scripts/validate-query-filters.py <research-plan.json>
  python3 scripts/validate-query-filters.py --query '{"interface":"case","filters":{"wenshu-type":"民事"}}'
  python3 scripts/validate-query-filters.py <plan.json> --strict   # 未知 interface 也算违规

退出码: 0=全合法, 1=有违规 (可接 CI / pre-commit / hook)。
"""
import argparse, json, sys
from pathlib import Path

# 硬编码 fallback：仅当动态自省 yd_search.build_parser() 失败时使用。
# 已按 yd_search.py 源码（含 _add_law_filters helper、双别名、store_false）校准。
# 维护时以动态自省结果为准（见 VALID_FILTERS_LOAD_SOURCE），勿手改本表。
_HARDCODED = {
    "search": {"effect1", "sxx", "keep-industry", "rewrite-flag", "no-rewrite",
               "return-num", "law-start", "law-end"},
    "keyword": {"expand", "fgmc", "effect1", "sxx", "keep-industry", "search-mode",
                "fbrq-start", "fbrq-end", "ssrq-start", "ssrq-end", "top-k"},
    "case": {"ah", "title", "ay", "jbdw", "ajlb", "xzqh-p", "province", "wszl",
             "jarq-start", "jarq-end", "fxgc", "yyft", "ft-search-mode",
             "authority-only", "expand", "search-mode", "top-k"},
    "case-semantic": {"authority-only", "xzqh-p", "province", "fayuan", "wenshu-type",
                      "wszl", "cj", "rewrite-flag", "no-rewrite", "return-num",
                      "jarq-start", "jarq-end"},
    "detail": {"ft-name", "reference-date"},
    "case-detail": {"type", "id", "ah"},
    "regulation": {"expand", "search-mode", "fgmc", "effect1", "sxx", "keep-industry",
                   "fbrq-start", "fbrq-end", "ssrq-start", "ssrq-end", "top-k"},
    "regulation-detail": {"name", "fgid", "reference-date"},
}


def _load_valid_filters():
    """优先从同目录 yd_search.py 的 build_parser() 动态自省（零漂移）；
    失败回退 _HARDCODED。返回 (filters_dict, source_str)。"""
    try:
        import importlib.util
        yd = Path(__file__).resolve().parent / "yd_search.py"
        if not yd.exists():
            return {k: set(v) for k, v in _HARDCODED.items()}, "fallback(yd_search.py 缺失)"
        spec = importlib.util.spec_from_file_location("yd_search_for_validator", yd)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        parser = mod.build_parser()
        valid = {}
        for act in parser._actions:
            if isinstance(act, argparse._SubParsersAction):
                for name, sub in act.choices.items():
                    fields = set()
                    for a in sub._actions:
                        for opt in a.option_strings:
                            if opt in ("-h", "--help"):
                                continue
                            fields.add(opt.lstrip("-"))
                    valid[name] = fields
        if not valid:
            return {k: set(v) for k, v in _HARDCODED.items()}, "fallback(自省为空)"
        return valid, "dynamic(yd_search.build_parser)"
    except Exception as e:
        return {k: set(v) for k, v in _HARDCODED.items()}, f"fallback({type(e).__name__}: {e})"


VALID_FILTERS, VALID_FILTERS_LOAD_SOURCE = _load_valid_filters()

# 反查: 某字段通常属于哪些 interface (用于给违规信息提示"它属于谁")
FIELD_OWNERS = {}
for _iface, _fields in VALID_FILTERS.items():
    for _f in _fields:
        FIELD_OWNERS.setdefault(_f, []).append(_iface)


def _normalize(key):
    """filter key 统一去前导 -- / 前导 -。"""
    k = key.strip()
    while k.startswith("-"):
        k = k[1:]
    return k


def validate_queries(queries, case_id="?", strict=False):
    """对一组 query 校验 filter×interface。返回 violations 列表。"""
    violations = []
    for q in queries or []:
        qid = q.get("id") or "?"
        iface = (q.get("interface") or "").strip()
        if iface not in VALID_FILTERS:
            if strict or not iface:
                violations.append({
                    "case_id": case_id, "query_id": qid,
                    "interface": iface or "(空)",
                    "field": None,
                    "msg": "未知/缺失 interface" + (f"，已知: {sorted(VALID_FILTERS)}" if not iface else ""),
                })
            continue
        legal = VALID_FILTERS[iface]
        for raw_key in (q.get("filters") or {}).keys():
            k = _normalize(raw_key)
            if k not in legal:
                owners = FIELD_OWNERS.get(k, [])
                hint = f"（属 {owners[0]}）" if len(owners) == 1 else (
                    f"（属 {owners}）" if owners else "（未知字段）")
                violations.append({
                    "case_id": case_id, "query_id": qid,
                    "interface": iface, "field": raw_key,
                    "msg": f"--{k} 不被 {iface} 支持{hint}",
                })
    return violations


def _extract_cases(plan):
    if isinstance(plan, list):
        return [(c.get("case_id", f"#{i}"), c) for i, c in enumerate(plan)]
    if isinstance(plan, dict):
        cases = plan.get("cases") or plan.get("results") or []
        out = []
        for i, c in enumerate(cases):
            out.append((c.get("case_id", f"#{i}"), c))
        # 兼容顶层就是单个 case
        if not cases and "queries" in plan:
            out.append((plan.get("case_id", "?"), plan))
        return out
    return []


def validate_plan_file(path, strict=False):
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    all_v = []
    n_queries = 0
    for case_id, c in _extract_cases(plan):
        qs = c.get("queries") or []
        n_queries += len(qs)
        all_v += validate_queries(qs, case_id, strict)
    return all_v, n_queries


def main():
    ap = argparse.ArgumentParser(description="校验 research-plan 的 filter×interface 合法性 (§9.1 硬门禁)")
    ap.add_argument("plan", nargs="?", help="research-plan.json 路径")
    ap.add_argument("--query", help="单条 query JSON (如 '{\"interface\":\"case\",\"filters\":{...}}')")
    ap.add_argument("--strict", action="store_true", help="未知/缺失 interface 也算违规")
    args = ap.parse_args()

    if args.query:
        q = json.loads(args.query)
        v = validate_queries([q], "(单条)", args.strict)
        n = 1
    elif args.plan:
        v, n = validate_plan_file(args.plan, args.strict)
    else:
        ap.error("需要 plan 路径或 --query")

    if not v:
        print(f"✓ 合法：{n} 条 query 的 filter×interface 全部匹配 §9.1 字段表。")
        if VALID_FILTERS_LOAD_SOURCE.startswith("fallback"):
            print(f"⚠ 字段表为 {VALID_FILTERS_LOAD_SOURCE}（非动态自省），结果可能不准，请检查 yd_search.py。")
        return 0

    cases_hit = sorted({x["case_id"] for x in v})
    print(f"✗ {len(v)} 处 filter 违规（涉及 {len(cases_hit)} 个 case / {n} 条 query）：")
    for x in v:
        if x["field"] is None:
            print(f"  [{x['case_id']}] Q{x['query_id']} interface={x['interface']}: {x['msg']}")
        else:
            print(f"  [{x['case_id']}] Q{x['query_id']} interface={x['interface']}: {x['msg']}")
    print(f"\n参考: references/07-research-middleware.md §9.1 字段归属接口速查表。")
    if VALID_FILTERS_LOAD_SOURCE.startswith("fallback"):
        print(f"⚠ 字段表为 {VALID_FILTERS_LOAD_SOURCE}（非动态自省），结果可能不准，请检查 yd_search.py。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
