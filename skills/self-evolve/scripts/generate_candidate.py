#!/usr/bin/env python3
"""Generate reviewable candidate Skill drafts from an imported analysis.

合同（UP-04/B-F4，R2 终版）：
- 决定绑定提案身份：只有 proposal_store 中 target_skill 与提案内容指纹
  （fingerprint=proposal_type+change_points 的确定性哈希）都匹配的**当前**
  决定记录才授权生成——同名旧提案的旧决定不能授权内容不同的新提案。
- accepted 才生成候选草稿（含 sha256/来源分析/证据绑定）；rejected/observe
  生成决定说明 JSON；无决定记录不生成——建议不等于人工接受。
- 候选只写显式指定的外置目录，绝不写用户已安装的成熟 Skill。
- 报告侧的 candidate_file 展示由产物真实性核验决定（文件存在+哈希一致），
  不存在/不符时回退"尚无安装包"。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from proposal_store import ProposalStore, proposal_fingerprint  # noqa: E402
from self_evolve_paths import DATA_ROOT, assert_external_write_path, assert_runtime_ready  # noqa: E402

CANDIDATE_SCHEMA = "self-evolve-candidate-draft-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decision_for(store: ProposalStore, proposal: dict) -> dict | None:
    """Find the decision record that authorizes THIS proposal's content.

    匹配合同（R2 缺口1）：target_skill 与内容指纹（proposal_type+change_points，
    与 store.upsert 同一 fingerprint 算法）都必须一致——同名不同内容的旧决定
    不授权；没有匹配记录返回 None（不生成）。
    """
    target = proposal.get("target_skill", "")
    if not target:
        return None
    expected_fingerprint = proposal_fingerprint(
        target, "skill_upgrade", proposal.get("change_points", []))
    for item in store.list():
        if item.get("target_skill") != target:
            continue
        if item.get("proposal_fingerprint") != expected_fingerprint:
            continue  # 同名但内容不同的提案（旧决定不授权新内容）
        if item.get("human_decision") in {"accepted", "rejected", "observe"}:
            return item
    return None


def generate_candidates(analysis_path: Path, output_dir: Path, *,
                        reviewer: str, decisions_root: Path | None = None) -> list[dict]:
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    if analysis.get("schema_version") != "self-evolve-agent-analysis-v1":
        raise ValueError("invalid_analysis_schema")
    proposals = analysis.get("skill_proposals", [])
    decisions_root = decisions_root or (DATA_ROOT / "proposals")
    store = ProposalStore(decisions_root)
    generated = []
    output_dir = assert_external_write_path(output_dir, label="output_dir")
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    for proposal in proposals:
        target = proposal.get("target_skill", "")
        decision_row = _decision_for(store, proposal)
        if decision_row is None:
            continue  # 无匹配决定记录 → 不生成（建议不等于接受；同名旧决定不授权）
        decision = decision_row["human_decision"]
        if decision != "accepted":
            note = {
                "schema_version": CANDIDATE_SCHEMA,
                "target_skill": target, "decision": decision,
                "proposal_id": decision_row.get("proposal_id", ""),
                "proposal_fingerprint": decision_row.get("proposal_fingerprint", ""),
                "decision_reason": decision_row.get("decision_reason", ""),
                "analysis_hint": analysis_path.stem,
                "evidence_ids": proposal.get("evidence_ids", []),
                "source": "declined-candidate-note",
            }
            note_path = output_dir / f"{target}.{decision}.json"
            note_path.write_text(json.dumps(note, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            generated.append({"target_skill": target, "decision": decision,
                              "proposal_id": decision_row.get("proposal_id", ""), "file": str(note_path)})
            continue
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", target):
            raise ValueError("invalid_skill_target")
        body = (
            f"<!-- 候选草稿：由分析 {analysis_path.stem} 生成；"
            f"提案 {decision_row.get('proposal_id', '')}（决定=accepted，"
            f"reviewer={reviewer}）；使用前需人工审阅与真实验证。 -->\n\n"
            f"# {proposal['title']}\n\n"
            f"- 目标 Skill: {target}\n- 动作: {proposal['action']}\n"
            f"- 理由: {proposal['rationale']}\n\n"
            f"## 建议改动\n" + "".join(f"- {point}\n" for point in proposal["change_points"])
            + f"\n## 来源\n- 分析: {analysis_path.stem}\n- 证据: {', '.join(proposal['evidence_ids'])}\n"
            f"- 提案指纹: {decision_row.get('proposal_fingerprint', '')}\n"
        )
        candidate_path = output_dir / f"{target}-candidate.md"
        candidate_path.write_text(body, encoding="utf-8")
        generated.append({"target_skill": target, "decision": decision,
                          "proposal_id": decision_row.get("proposal_id", ""),
                          "file": str(candidate_path), "sha256": _sha256(candidate_path),
                          "source_analysis": analysis_path.stem,
                          "evidence_ids": proposal.get("evidence_ids", [])})
    return generated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True, help="已导入的分析 JSON（runs/<run>/<analysis>.json）")
    parser.add_argument("--output-dir", type=Path, required=True, help="外置候选目录（必须在本 Skill 树之外）")
    parser.add_argument("--reviewer", required=True, help="决定记录者标识（入候选文件头）")
    args = parser.parse_args()
    try:
        assert_runtime_ready()
        if args.analysis.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("input_size_budget_exceeded")
        results = generate_candidates(args.analysis, args.output_dir, reviewer=args.reviewer)
        print(json.dumps({"status": "candidates_generated", "count": len(results), "candidates": results},
                         ensure_ascii=False, indent=1))
        return 0
    except (OSError, ValueError) as exc:
        error = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print(json.dumps({"status": "failed", "error": error}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
