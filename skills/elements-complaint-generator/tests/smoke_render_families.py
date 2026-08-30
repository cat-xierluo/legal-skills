#!/usr/bin/env python3
"""按 manifest.doc_type 每个文书家族抽一棵模板做真实 PDF 渲染门禁。"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from fill_template import (  # noqa: E402
    DocParts,
    apply_rules,
    fix_footers_and_pagination,
    load_text_parts,
    merge_sections_and_normalize,
    save_text_parts,
)
from generic_rules import build_generic_rules  # noqa: E402
from layout_gate import check, load_policy  # noqa: E402
from pack_docx import pack_tree  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    manifest = json.loads(
        (SKILL_DIR / "templates/templates-manifest.json").read_text(encoding="utf-8")
    )
    representatives = {}
    for item in manifest["trees"]:
        representatives.setdefault(item["doc_type"], item["tree"])

    elements = json.loads(
        (SKILL_DIR / "tests/fixtures/generic-smoke.json").read_text(encoding="utf-8")
    )["elements"]
    policy_path = SKILL_DIR / "config/layout-policy.json"
    root = Path(tempfile.mkdtemp(prefix="ecg-render-families-"))
    results = []
    try:
        for index, (family, tree_name) in enumerate(sorted(representatives.items()), 1):
            source = SKILL_DIR / "templates" / tree_name
            work = root / f"tree-{index:02d}"
            output = root / f"candidate-{index:02d}.docx"
            try:
                shutil.copytree(source, work)
                parts = load_text_parts(work)
                rules_result = apply_rules(
                    DocParts(parts), build_generic_rules(source, elements), elements
                )
                errors = [name for status, name in rules_result["details"] if status == "error"]
                if errors:
                    raise RuntimeError(f"规则执行失败: {errors[:3]}")
                layout_stats = merge_sections_and_normalize(parts)
                save_text_parts(work, parts)
                policy = load_policy(policy_path, tree_name)
                fix_footers_and_pagination(
                    work, page_mode=policy.get("page_numbers", "required")
                )
                pack_tree(work, output)
                report = check(output, policy, rendered=True)
                results.append({
                    "family": family,
                    "tree": tree_name,
                    "ok": report["ok"],
                    "status": report["status"],
                    "layout_stats": layout_stats,
                    "issues": report["issues"],
                    "reports": report["reports"],
                })
            except Exception as exc:
                results.append({
                    "family": family,
                    "tree": tree_name,
                    "ok": False,
                    "status": "FAIL",
                    "layout_stats": {},
                    "issues": [{
                        "code": "ECG-RENDER-FAMILY-EXCEPTION",
                        "stage": "rendered",
                        "message": f"{type(exc).__name__}: {exc}",
                    }],
                    "reports": [],
                })
            finally:
                shutil.rmtree(work, ignore_errors=True)

        failed = [item for item in results if not item["ok"]]
        payload = {
            "schema_version": 1,
            "status": "DOMAIN_VERIFIED" if not failed else "FAIL",
            "scope": "one real PDF render per manifest.doc_type family",
            "total": len(results),
            "passed": len(results) - len(failed),
            "failed": len(failed),
            "results": results,
        }
        if args.json_output:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        for item in failed:
            detail = "; ".join(issue["message"] for issue in item["issues"][:3])
            print(f"  ✗ {item['family']} / {item['tree']}: {detail}")
        print(f"[render-families] 通过 {payload['passed']}/{payload['total']}，失败 {payload['failed']}")
        return 0 if not failed else 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
