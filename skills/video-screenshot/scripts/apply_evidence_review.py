#!/usr/bin/env python3
"""校验多模态证据线索答案并生成非破坏性复核结果。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="应用证据线索视觉复核答案")
    parser.add_argument("-i", "--input", required=True, help="extract.py 的基础输出目录")
    parser.add_argument("-r", "--review", required=True, help="填写完成的 vision_template.json")
    parser.add_argument("--evidence-dir", default=None, help="默认: <input>/_evidence_leads")
    return parser.parse_args()


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path, label: str) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{label} 必须是 JSON 对象")
    return data


def _validate_answer(
    raw: Any,
    expected_lead_id: str,
    allowed_categories: set[str],
) -> dict[str, Any]:
    fields = {"lead_id", "allowed_categories", "categories", "visible_fact_summary", "potential_use", "confidence"}
    if not isinstance(raw, dict) or set(raw) != fields:
        raise ValueError(f"答案字段被修改: {expected_lead_id}")
    if raw.get("lead_id") != expected_lead_id:
        raise ValueError(f"答案 lead_id 被修改: {expected_lead_id}")
    declared_allowed = raw.get("allowed_categories")
    if not isinstance(declared_allowed, list) or set(declared_allowed) != allowed_categories or len(declared_allowed) != len(allowed_categories):
        raise ValueError(f"allowed_categories 被修改: {expected_lead_id}")
    categories = raw.get("categories")
    if (
        not isinstance(categories, list)
        or not 1 <= len(categories) <= 3
        or any(not isinstance(item, str) or item not in allowed_categories for item in categories)
        or len(set(categories)) != len(categories)
    ):
        raise ValueError(f"categories 必须从允许列表选择 1—3 项: {expected_lead_id}")
    summary = raw.get("visible_fact_summary")
    potential_use = raw.get("potential_use")
    if not isinstance(summary, str) or not 4 <= len(summary.strip()) <= 300:
        raise ValueError(f"visible_fact_summary 长度应为 4—300: {expected_lead_id}")
    if not isinstance(potential_use, str) or not 4 <= len(potential_use.strip()) <= 300:
        raise ValueError(f"potential_use 长度应为 4—300: {expected_lead_id}")
    forbidden = re.compile(
        r"(足以证明|已经证明|证明了|可以证明|能够证明|必然构成|构成侵权|构成违法|"
        r"证据确凿|真实无误|真实性已确认|合法有效|法院必然|一定胜诉)"
    )
    if forbidden.search(summary) or forbidden.search(potential_use):
        raise ValueError(f"答案越过线索识别边界: {expected_lead_id}")
    sensitive_literal = re.compile(
        r"(https?://|www\.|[￥¥]\s*\d|\d{3,}|"
        r"[A-Za-z][A-Za-z0-9_-]{2,}|"
        r"(?:微信号|账号|电话|邮箱|地址|订单号|交易号)[:：]?\s*\S+)"
    )
    if sensitive_literal.search(summary) or sensitive_literal.search(potential_use):
        raise ValueError(f"答案含具体名称、金额、编号或联系方式，请改为泛化概括: {expected_lead_id}")
    confidence = raw.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0.0 <= float(confidence) <= 1.0:
        raise ValueError(f"confidence 必须在 0—1: {expected_lead_id}")
    return {
        "lead_id": expected_lead_id,
        "categories": categories,
        "visible_fact_summary": summary.strip(),
        "potential_use": potential_use.strip(),
        "confidence": round(float(confidence), 4),
    }


def main() -> int:
    args = parse_args()
    raw_root = Path(args.input).expanduser()
    if raw_root.is_symlink():
        print("错误: 基础输出目录是符号链接，拒绝跟随", file=sys.stderr)
        return 2
    root = raw_root.resolve()
    raw_evidence_dir = Path(args.evidence_dir).expanduser() if args.evidence_dir else root / "_evidence_leads"
    raw_review_path = Path(args.review).expanduser()
    if raw_evidence_dir.is_symlink() or raw_review_path.is_symlink():
        print("错误: 证据线索目录或复核答案是符号链接，拒绝跟随", file=sys.stderr)
        return 2
    evidence_dir = raw_evidence_dir.resolve()
    review_path = raw_review_path.resolve()
    result_path = evidence_dir / "evidence_review.json"
    try:
        if evidence_dir.is_symlink() or not evidence_dir.is_dir():
            raise ValueError("证据线索目录不存在或为符号链接")
        index_path = evidence_dir / "evidence_index.json"
        if index_path.is_symlink() or not index_path.is_file():
            raise ValueError("证据线索索引不存在或为符号链接")
        index = _load(index_path, "证据线索索引")
        if index.get("purpose") != "ranking_only_non_destructive_evidence_leads":
            raise ValueError("证据线索索引用途不受支持")
        report_path = root / "_report.json"
        if report_path.is_symlink() or not report_path.is_file():
            raise ValueError("基础报告不存在或为符号链接")
        if _sha(report_path) != index.get("source_report_sha256"):
            raise ValueError("基础报告与证据线索索引不一致")
        leads = index.get("leads")
        if not isinstance(leads, list):
            raise ValueError("证据线索索引缺少 leads")
        selected = [item for item in leads if isinstance(item, dict) and item.get("selected_for_contact_sheet") is True]
        ranks = [item.get("selection_rank") for item in selected]
        if (
            any(not isinstance(rank, int) or isinstance(rank, bool) or rank <= 0 for rank in ranks)
            or len(ranks) != len(set(ranks))
            or set(ranks) != set(range(1, len(selected) + 1))
        ):
            raise ValueError("联系表线索缺少连续且唯一的 selection_rank")
        selected.sort(key=lambda item: int(item["selection_rank"]))
        base_hashes: dict[str, str] = {}
        for lead in leads:
            if not isinstance(lead, dict):
                raise ValueError("证据线索项格式错误")
            filename = str(lead.get("filename") or "")
            path = root / filename
            if not re.fullmatch(r"frame_\d{3}_\d{2}m\d{2}s\.jpg", filename) or path.is_symlink() or not path.is_file():
                raise ValueError(f"非法基础帧引用: {filename}")
            if _sha(path) != lead.get("sha256"):
                raise ValueError(f"基础帧 SHA256 不一致: {filename}")
            base_hashes[filename] = str(lead["sha256"])

        review = _load(review_path, "视觉复核答案")
        if set(review) != {"schema_version", "status", "source_evidence_index_sha256", "operation", "answers"}:
            raise ValueError("视觉复核答案字段不完整或包含未知字段")
        if review.get("schema_version") != "1.0" or review.get("status") != "completed":
            raise ValueError("视觉复核答案必须使用 schema 1.0 且 status=completed")
        if review.get("operation") != "classify_and_summarize_only":
            raise ValueError("视觉复核不得改变操作类型")
        if review.get("source_evidence_index_sha256") != _sha(index_path):
            raise ValueError("视觉复核答案未绑定当前 evidence_index")
        answers = review.get("answers")
        if not isinstance(answers, list) or len(answers) != len(selected):
            raise ValueError("视觉复核答案未完整覆盖联系表线索")
        expected_ids = [str(item["lead_id"]) for item in selected]
        actual_ids = [str(item.get("lead_id") or "") for item in answers if isinstance(item, dict)]
        if actual_ids != expected_ids:
            raise ValueError("视觉复核答案顺序、数量或 lead_id 被修改")
        allowed_list = (index.get("vision_contract") or {}).get("allowed_categories") or []
        if (
            not isinstance(allowed_list, list)
            or not allowed_list
            or any(not isinstance(item, str) for item in allowed_list)
            or len(allowed_list) != len(set(allowed_list))
        ):
            raise ValueError("证据线索索引的允许类别非法")
        allowed = set(allowed_list)
        validated = [_validate_answer(raw, expected_id, allowed) for raw, expected_id in zip(answers, expected_ids)]
        if result_path.exists() or result_path.is_symlink():
            raise ValueError("evidence_review.json 已存在；为保留人工结果，拒绝覆盖")
        payload = {
            "schema_version": "1.0",
            "status": "completed",
            "operation": "classify_and_summarize_only",
            "source_evidence_index_sha256": _sha(index_path),
            "source_review_sha256": _sha(review_path),
            "base_frames_modified": False,
            "privacy": {
                "ocr_text_stored": False,
                "exact_entity_text_allowed": False,
                "model_summary_generalization_required": True,
            },
            "legal_boundary": "仅记录可见事实和可能用途，不认定真实性、合法性、关联性或证明力",
            "results": validated,
        }
        for filename, expected_sha in base_hashes.items():
            if _sha(root / filename) != expected_sha:
                raise ValueError(f"生成复核结果前基础帧发生变化: {filename}")
        with result_path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        print(f"完成: {result_path}")
        print(f"  线索复核: {len(validated)}")
        print("  基础帧修改: 0")
        return 0
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
