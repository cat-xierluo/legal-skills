#!/usr/bin/env python3
"""Build minimal synthetic contract DOCX files for T-401 clause-boundary micro cases.

Each controlled micro case supplies `provided_context.contract_excerpt` (a single
ambiguous clause) plus party_role / review_objective / review_intensity. This script
wraps the excerpt into a minimal two-party contract body so the contract-copilot
candidate can be driven on a real DOCX the way it would be in production.

The synthetic contracts are clearly marked 脱敏合成 and contain NO real client,
case number, or identity configuration, per legal-skill-evaluation 安全规则.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from docx import Document

MICRO_DIR = Path(__file__).resolve().parent.parent / "evals" / "contract-calibration-260730" / "micro-runs"
OUT_DIR = MICRO_DIR / "synthetic"

# case_id -> (contract_title, party_a_label, party_b_label)
CONTRACT_SHAPES = {
    "CONTRACT-MICRO-SERVICE-SCOPE": ("技术服务合同", "甲方（委托方）", "乙方（服务方）"),
    "CONTRACT-MICRO-ACCEPTANCE-PAYMENT": ("软件开发服务合同", "甲方（委托方）", "乙方（开发方）"),
    "CONTRACT-MICRO-CHANGE-FEE": ("设计服务合同", "甲方（委托方）", "乙方（设计方）"),
    "CONTRACT-MICRO-PENALTY-STACKING": ("服务合同", "甲方（委托方）", "乙方（服务方）"),
    "CONTRACT-MICRO-DESIGN-IP-USE": ("设计成果交付合同", "甲方（委托方）", "乙方（设计方）"),
    "CONTRACT-MICRO-NOTICE": ("供应合同", "甲方（采购方）", "乙方（供应方）"),
    "CONTRACT-MICRO-JURISDICTION": ("合作合同", "甲方（合作方）", "乙方（合作方）"),
    "CONTRACT-MICRO-PATENT-SUBJECT": ("专利实施许可合同", "许可方", "受让方"),
    "CONTRACT-MICRO-PATENT-SCOPE": ("专利普通许可合同", "许可方", "受让方"),
    "CONTRACT-MICRO-PATENT-FEE": ("专利许可合同", "许可方", "受让方"),
    "CONTRACT-MICRO-PATENT-INVALIDITY": ("专利许可合同", "许可方", "受让方"),
}


def build_one(case_id: str, payload: dict) -> Path:
    context = payload.get("provided_context", {})
    excerpt = str(context.get("contract_excerpt") or "").strip()
    party_role = str(context.get("party_role") or "").strip()
    objective = str(context.get("review_objective") or "").strip()
    intensity = str(context.get("review_intensity") or "").strip()
    title, pa, pb = CONTRACT_SHAPES[case_id]

    doc = Document()
    doc.add_heading(title, level=0)
    doc.add_paragraph("（脱敏合成合同，仅用于 legal-skill-evaluation T-401 受控微案例，不含真实客户、案号或身份配置。）")

    # 签约主体：按 party_role 标注“我方/对方”，帮助候选按立场审查。
    doc.add_paragraph(f"甲方：{pa}")
    doc.add_paragraph(f"乙方：{pb}")
    doc.add_paragraph(f"审查立场：{party_role}；审查目的：{objective}；审查口径：{intensity}。")

    doc.add_heading("合同条款", level=1)
    doc.add_paragraph(
        "第一条 鉴于双方就上述合同标的达成一致，特订立本合同，以资共同遵守。"
    )
    # 摘录条款作为第二条，编号清晰，便于候选定位微观层条款风险。
    doc.add_paragraph(f"第二条 {excerpt}")
    doc.add_paragraph(
        "第三条 其他条款（脱敏合成占位）：双方应本着诚实信用原则履行本合同，"
        "未尽事宜由双方另行协商确定。"
    )

    out_path = OUT_DIR / f"{case_id.lower()}.docx"
    doc.save(str(out_path))
    return out_path


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    inputs = sorted(MICRO_DIR.glob("*-input.json"))
    built = 0
    for path in inputs:
        payload = json.loads(path.read_text(encoding="utf-8"))
        case_id = payload.get("case_id")
        if not case_id or case_id not in CONTRACT_SHAPES:
            continue
        out = build_one(case_id, payload)
        print(f"built {out.name}")
        built += 1
    print(f"total built: {built}")


if __name__ == "__main__":
    sys.exit(main())
