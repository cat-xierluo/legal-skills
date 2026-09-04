#!/usr/bin/env python3
"""Regression tests for preflight_ledger.py."""

from __future__ import annotations

import copy
import sys

from preflight_ledger import validate_ledger


def valid_manifest() -> dict:
    return {
        "source_index": {"file": "source-index.json", "sha256": "a" * 64},
        "source_authority": {
            "mode": "current",
            "notices": [],
            "corrections": [],
            "acknowledgements": [],
            "correction_routes": [],
        },
        "chapters": [
            {"id": "CH-01", "section_headings": ["操作链与结果"]}
        ],
        "materials": [
            {
                "id": "MAT-001",
                "summary": "操作从入口开始并形成结果。",
                "source_refs": ["SRC-001#L0001-L0001"],
                "source_block_ids": ["BLK-00001"],
                "coverage_terms": ["入口", "形成结果"],
                "disposition": "include",
                "target_chapter_id": "CH-01",
                "target_section_heading": "操作链与结果",
            },
            {
                "id": "MAT-002",
                "summary": "设备调试。",
                "source_refs": ["SRC-001#L0002-L0002"],
                "source_block_ids": ["BLK-00002"],
                "coverage_terms": [],
                "disposition": "skip",
                "target_chapter_id": None,
                "target_section_heading": None,
                "skip_code": "device",
                "skip_reason": "只包含设备调试。",
            },
        ]
    }


def valid_source_index() -> dict:
    return {
        "authority": {"mode": "current", "notices": [], "corrections": []},
        "sources": [
            {
                "id": "SRC-001",
                "blocks": [
                    {"id": "BLK-00001", "source_ref": "SRC-001#L0001-L0001", "kind": "content", "char_count": 500, "preview": "操作从入口开始并形成结果"},
                    {"id": "BLK-00002", "source_ref": "SRC-001#L0002-L0002", "kind": "content", "char_count": 500, "preview": "设备调试过程不涉及旧称"},
                ],
            }
        ]
    }


def source_index_with_third_block() -> dict:
    source_index = valid_source_index()
    source_index["sources"][0]["blocks"].append(
        {"id": "BLK-00003", "source_ref": "SRC-001#L0003-L0003", "kind": "content", "char_count": 1500, "preview": "第三段课程内容"}
    )
    return source_index


def with_authority_contract(manifest: dict, source_index: dict) -> tuple[dict, dict]:
    notice = {
        "id": "AUTH-001",
        "source_block_id": "BLK-00001",
        "source_ref": "SRC-001#L0001-L0001",
        "controlling_titles": ["控制版"],
        "controlling_source_ids": ["SRC-001"],
        "section_hint": "勘误",
    }
    correction = {
        "id": "COR-001",
        "authority_id": "AUTH-001",
        "source_id": "SRC-001",
        "source_ref": "SRC-001#L0001-L0001",
        "original_text": "`旧称`",
        "revised_text": "统一使用现行名称。",
        "deprecated_terms": ["旧称"],
        "superseded_candidate_block_ids": ["BLK-00002"],
    }
    source_index["authority"] = {"mode": "current", "notices": [notice], "corrections": [correction]}
    manifest["source_authority"] = {
        "mode": "current",
        "notices": [notice],
        "corrections": [correction],
        "acknowledgements": [
            {
                "id": "AUTH-001",
                "action": "apply_control",
                "controlling_source_ids": ["SRC-001"],
                "reader_notice": None,
            }
        ],
        "correction_routes": [
            {
                "id": "COR-001",
                "target_chapter_id": "CH-01",
                "target_section_heading": "操作链与结果",
                "supersession_status": "no_matching_source_block",
                "superseded_source_block_ids": [],
                "supersession_note": "已检查普通来源块，未发现旧称被当作现行结论。",
                "candidate_block_reviews": [
                    {
                        "source_block_id": "BLK-00002",
                        "decision": "retained_current",
                        "evidence_quote": "设备调试过程不涉及旧称",
                        "reason": "该块只写设备调试，没有陈述或支持控制表中的旧称。",
                    }
                ],
            }
        ],
    }
    return manifest, source_index


def with_bulk_superseded_matrix(manifest: dict, source_index: dict) -> tuple[dict, dict]:
    """Build a mechanically plausible but semantically implausible all-delete matrix."""
    blocks = source_index["sources"][0]["blocks"]
    corrections = []
    routes = []
    for number in range(1, 13):
        block_id = f"BLK-{number + 2:05d}"
        preview = f"候选片段{number:02d}讨论相邻主题而非旧口径"
        blocks.append(
            {
                "id": block_id,
                "source_ref": f"SRC-001#L{number + 2:04d}-L{number + 2:04d}",
                "kind": "content",
                "char_count": 80,
                "preview": preview,
            }
        )
        correction_id = f"COR-{number:03d}"
        corrections.append(
            {
                "id": correction_id,
                "superseded_candidate_block_ids": [block_id],
            }
        )
        routes.append(
            {
                "id": correction_id,
                "target_chapter_id": "CH-01",
                "target_section_heading": "操作链与结果",
                "supersession_status": "blocks_identified",
                "superseded_source_block_ids": [block_id],
                "supersession_note": f"候选片段{number:02d}被判定承载旧结论并需要隔离。",
                "candidate_block_reviews": [
                    {
                        "source_block_id": block_id,
                        "decision": "superseded",
                        "evidence_quote": preview,
                        "reason": f"候选片段{number:02d}被逐项判断为直接支持旧结论。",
                    }
                ],
            }
        )
    source_index["authority"] = {"mode": "current", "notices": [], "corrections": corrections}
    manifest["source_authority"] = {
        "mode": "current",
        "notices": [],
        "corrections": corrections,
        "acknowledgements": [],
        "correction_routes": routes,
    }
    return manifest, source_index


def main() -> int:
    cases: list[tuple[str, dict, dict | None, bool, str | None]] = []
    cases.append(("valid", valid_manifest(), valid_source_index(), True, None))

    authority_manifest, authority_index = with_authority_contract(valid_manifest(), valid_source_index())
    cases.append(("authority-correction-routed", authority_manifest, authority_index, True, None))

    missing_route_manifest, missing_route_index = with_authority_contract(valid_manifest(), valid_source_index())
    missing_route_manifest["source_authority"]["correction_routes"] = []
    cases.append(("authority-correction-route-missing", missing_route_manifest, missing_route_index, False, "全部控制文档修正"))

    missing_review_manifest, missing_review_index = with_authority_contract(valid_manifest(), valid_source_index())
    missing_review_manifest["source_authority"]["correction_routes"][0]["candidate_block_reviews"] = []
    cases.append(("authority-candidate-review-missing", missing_review_manifest, missing_review_index, False, "逐项覆盖全部候选块"))

    copied_reason_manifest, copied_reason_index = with_authority_contract(valid_manifest(), valid_source_index())
    copied_reason_index["sources"][0]["blocks"].append(
        {
            "id": "BLK-00003",
            "source_ref": "SRC-001#L0003-L0003",
            "kind": "content",
            "char_count": 80,
            "preview": "第三个候选讨论相邻主题，不支持旧称",
        }
    )
    copied_reason_manifest["source_authority"]["corrections"][0]["superseded_candidate_block_ids"] = [
        "BLK-00002",
        "BLK-00003",
    ]
    copied_reason_manifest["source_authority"]["correction_routes"][0]["candidate_block_reviews"] = [
        {
            "source_block_id": "BLK-00002",
            "decision": "retained_current",
            "evidence_quote": "设备调试过程不涉及旧称",
            "reason": "该候选块只涉及相邻主题，并未陈述或支持旧口径。",
        },
        {
            "source_block_id": "BLK-00003",
            "decision": "retained_current",
            "evidence_quote": "第三个候选讨论相邻主题",
            "reason": "该候选块只涉及相邻主题，并未陈述或支持旧口径。",
        },
    ]
    cases.append(("authority-copied-review-reason", copied_reason_manifest, copied_reason_index, False, "不得为全部候选复制同一判断理由"))

    bulk_manifest, bulk_index = with_bulk_superseded_matrix(valid_manifest(), valid_source_index())
    cases.append(("authority-all-superseded-matrix", bulk_manifest, bulk_index, False, "不得把整张高召回矩阵一律判为 superseded"))

    wrong_quarantine_manifest, wrong_quarantine_index = with_authority_contract(valid_manifest(), valid_source_index())
    wrong_route = wrong_quarantine_manifest["source_authority"]["correction_routes"][0]
    wrong_route.update(
        {
            "supersession_status": "blocks_identified",
            "superseded_source_block_ids": ["BLK-00002"],
            "supersession_note": "第二个普通来源块明确复述了已经被控制文档替代的旧口径。",
            "candidate_block_reviews": [
                {
                    "source_block_id": "BLK-00002",
                    "decision": "superseded",
                    "evidence_quote": "设备调试过程不涉及旧称",
                    "reason": "第二个普通来源块明确复述旧口径，必须整体隔离。",
                }
            ],
        }
    )
    cases.append(("authority-superseded-wrong-skip-code", wrong_quarantine_manifest, wrong_quarantine_index, False, "authority_superseded"))

    valid_quarantine_manifest, valid_quarantine_index = with_authority_contract(valid_manifest(), valid_source_index())
    valid_route = valid_quarantine_manifest["source_authority"]["correction_routes"][0]
    valid_route.update(
        {
            "supersession_status": "blocks_identified",
            "superseded_source_block_ids": ["BLK-00002"],
            "supersession_note": "第二个普通来源块明确复述了已经被控制文档替代的旧口径。",
            "candidate_block_reviews": [
                {
                    "source_block_id": "BLK-00002",
                    "decision": "superseded",
                    "evidence_quote": "设备调试过程不涉及旧称",
                    "reason": "第二个普通来源块明确复述旧口径，必须整体隔离。",
                }
            ],
        }
    )
    valid_quarantine_manifest["materials"][1]["skip_code"] = "authority_superseded"
    valid_quarantine_manifest["materials"][1]["skip_reason"] = "该块的旧口径已由 COR-001 修订句替代。"
    cases.append(("authority-superseded-quarantined", valid_quarantine_manifest, valid_quarantine_index, True, None))

    skip_namespace = valid_manifest()
    skip_namespace["materials"][1]["id"] = "SKIP-002"
    cases.append(("skip-namespace", skip_namespace, valid_source_index(), False, "禁止 SKIP-*"))

    id_gap = valid_manifest()
    id_gap["materials"][1]["id"] = "MAT-003"
    cases.append(("id-gap", id_gap, valid_source_index(), False, "连续分配"))

    duplicate = valid_manifest()
    duplicate["materials"][1]["id"] = "MAT-001"
    cases.append(("duplicate", duplicate, valid_source_index(), False, "重复素材 ID"))

    fragmented = valid_manifest()
    fragmented["materials"] = []
    for number in range(1, 62):
        material = copy.deepcopy(valid_manifest()["materials"][0])
        material["id"] = f"MAT-{number:03d}"
        material["summary"] = f"同一操作链的第 {number} 个重复碎片。"
        fragmented["materials"].append(material)
    cases.append(("material-count-budget", fragmented, valid_source_index(), False, "超过 2 个 content block 对应的 60 项预算"))

    bad_skip_target = valid_manifest()
    bad_skip_target["materials"][1]["target_chapter_id"] = "CH-01"
    cases.append(("skip-target", bad_skip_target, valid_source_index(), False, "target_chapter_id 必须为 null"))

    missing_terms = valid_manifest()
    missing_terms["materials"][0]["coverage_terms"] = []
    cases.append(("include-terms", missing_terms, valid_source_index(), False, "1—3 个 coverage_terms"))

    generic_terms = valid_manifest()
    generic_terms["materials"][0]["coverage_terms"] = ["操作", "结果"]
    cases.append(("all-generic-terms", generic_terms, valid_source_index(), False, "不能全是通用词"))

    oral_terms = valid_manifest()
    oral_terms["materials"][0]["coverage_terms"] = ["我觉得", "形成结果"]
    cases.append(("oral-fragment-terms", oral_terms, valid_source_index(), False, "口语指代、语气词或截断片段"))

    mixed_disposition = valid_manifest()
    mixed_disposition["materials"][1]["source_block_ids"] = ["BLK-00001"]
    cases.append(("mixed-disposition", mixed_disposition, valid_source_index(), False, "不得同时进入 include 与 skip"))

    missing_source_refs = valid_manifest()
    missing_source_refs["materials"][0]["source_refs"] = []
    cases.append(("missing-source-refs", missing_source_refs, valid_source_index(), False, "source_refs 必须"))

    cases.append(("uncovered-content-block", valid_manifest(), source_index_with_third_block(), False, "未登记去向"))

    generic_skip = valid_manifest()
    generic_skip["materials"].append(
        {
            "id": "MAT-003",
            "summary": "笼统认定该段没有课程价值。",
            "source_refs": ["SRC-001#L0003-L0003"],
            "source_block_ids": ["BLK-00003"],
            "coverage_terms": [],
            "disposition": "skip",
            "target_chapter_id": None,
            "target_section_heading": None,
            "skip_code": "no_course_value",
            "skip_reason": "笼统认定无课程价值。",
        }
    )
    cases.append(("generic-skip-budget", generic_skip, source_index_with_third_block(), False, "generic skip 预算"))

    device_skip = copy.deepcopy(generic_skip)
    device_skip["materials"][2]["skip_code"] = "device"
    device_skip["materials"][2]["skip_reason"] = "只包含投影和设备调试。"
    cases.append(("large-device-near-miss", device_skip, source_index_with_third_block(), True, None))

    passed = 0
    for name, fixture, source_index, should_pass, expected_text in cases:
        failures = validate_ledger(copy.deepcopy(fixture), copy.deepcopy(source_index))
        if should_pass and failures:
            print(f"FAIL {name}: {failures}")
            continue
        if not should_pass and not failures:
            print(f"FAIL {name}: 未阻断违规样例")
            continue
        if expected_text and not any(expected_text in failure for failure in failures):
            print(f"FAIL {name}: 未找到预期错误 {expected_text!r}: {failures}")
            continue
        passed += 1
        print(f"PASS {name}")

    print(f"{passed}/{len(cases)} passed")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
