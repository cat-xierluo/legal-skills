#!/usr/bin/env python3
"""113 棵模板树版式静态回归，并生成逐树审计矩阵。"""
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
from layout_gate import audit_docx, load_policy  # noqa: E402
from pack_docx import pack_tree  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    elements = json.loads(
        (SKILL_DIR / "tests/fixtures/generic-smoke.json").read_text(encoding="utf-8")
    )["elements"]
    policy_path = SKILL_DIR / "config/layout-policy.json"
    templates = sorted(path for path in (SKILL_DIR / "templates").iterdir() if path.is_dir())
    root = Path(tempfile.mkdtemp(prefix="ecg-layout-all-"))
    results = []
    try:
        for index, source in enumerate(templates, 1):
            work = root / f"tree-{index:03d}"
            output = root / f"candidate-{index:03d}.docx"
            try:
                shutil.copytree(source, work)
                parts = load_text_parts(work)
                rules_result = apply_rules(
                    DocParts(parts), build_generic_rules(source, elements), elements
                )
                layout_stats = merge_sections_and_normalize(parts)
                save_text_parts(work, parts)
                policy = load_policy(policy_path, source.name)
                footers_fixed = fix_footers_and_pagination(
                    work, page_mode=policy.get("page_numbers", "required")
                )
                pack_tree(work, output)
                report = audit_docx(output, policy)
                results.append({
                    "tree": source.name,
                    "ok": report["ok"],
                    "layout_stats": layout_stats,
                    "footers_fixed": footers_fixed,
                    "rules": {
                        "applied": rules_result["applied"],
                        "skipped": rules_result["skipped"],
                        "errors": [
                            name for status, name in rules_result["details"] if status == "error"
                        ],
                    },
                    "measurements": report["measurements"],
                    "issues": report["issues"],
                })
            except Exception as exc:
                results.append({
                    "tree": source.name,
                    "ok": False,
                    "layout_stats": {},
                    "footers_fixed": 0,
                    "rules": {},
                    "measurements": {},
                    "issues": [{
                        "code": "ECG-LAYOUT-ALL-EXCEPTION",
                        "stage": "docx",
                        "message": f"{type(exc).__name__}: {exc}",
                    }],
                })
            finally:
                shutil.rmtree(work, ignore_errors=True)

        failed = [item for item in results if not item["ok"]]
        payload = {
            "schema_version": 1,
            "status": "DOCX_VERIFIED" if not failed else "FAIL",
            "scope": "113 template trees",
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
        for item in failed[:20]:
            messages = "; ".join(issue["message"] for issue in item["issues"][:3])
            print(f"  ✗ {item['tree']}: {messages}")
        print(f"[layout-all] 通过 {payload['passed']}/{payload['total']}，失败 {payload['failed']}")
        return 0 if not failed and len(results) == 113 else 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
