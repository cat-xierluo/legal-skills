from __future__ import annotations
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    import interactive_sediment as ise  # noqa: E402
except ImportError as exc:  # optional PyYAML dependency
    if exc.name != "yaml":
        raise
    raise unittest.SkipTest(f"interactive_sediment requires PyYAML: {exc}") from exc


class LoadAssetOwnersTests(unittest.TestCase):
    def test_missing_file_returns_empty_list(self):
        self.assertEqual(ise.load_asset_owners(Path("/nonexistent.yaml")), [])

    def test_empty_file_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "owners.yaml"
            p.write_text("# empty\n", encoding="utf-8")
            self.assertEqual(ise.load_asset_owners(p), [])

    def test_valid_entries_loaded(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "owners.yaml"
            p.write_text(
                "asset_owners:\n"
                "  - asset_type: 法律知识规则\n"
                "    owning_skill: legal-knowledge-engine\n"
                "    triggers: [裁判规则, 举证规则]\n",
                encoding="utf-8",
            )
            owners = ise.load_asset_owners(p)
            self.assertEqual(len(owners), 1)
            self.assertEqual(owners[0]["owning_skill"], "legal-knowledge-engine")

    def test_malformed_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "owners.yaml"
            p.write_text("asset_owners: 'not-a-list'\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                ise.load_asset_owners(p)

    def test_scalar_value_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "owners.yaml"
            p.write_text("asset_owners: 5\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                ise.load_asset_owners(p)

    def test_non_mapping_elements_raise(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "owners.yaml"
            p.write_text("asset_owners: [1, 2]\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                ise.load_asset_owners(p)


class BuildAssetMapTests(unittest.TestCase):
    def _write_inventory(self, root: Path, skills: list) -> None:
        import json
        (root).write_text(
            json.dumps({"generated_at": "x", "sources": {}, "skills": skills}),
            encoding="utf-8",
        )

    def test_map_contains_core_skills_and_total(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            inv = root / "runtime"
            inv.mkdir()
            self._write_inventory(inv / "skill-inventory.json", [
                {"id": "agent-email", "name": "agent-email", "title": "Agent Email",
                 "description": "邮件", "version": "0.3", "license": "MIT",
                 "source": "legal-skills", "path": "/x", "skill_md": "/x/SKILL.md", "modified_at": 1},
            ])
            core = root / "core_skills.yaml"
            core.write_text(
                "skill_sources: {}\n"
                "core_skills:\n"
                "  - id: litigation-service\n"
                "    display_name: 诉讼总控\n"
                "    function: 把控诉讼阶段\n"
                "    domain_keywords: [诉讼, 证据]\n"
                "    priority: high\n",
                encoding="utf-8",
            )
            owners = root / "owners.yaml"
            owners.write_text("asset_owners: []\n", encoding="utf-8")
            out = ise.build_asset_map(
                inventory_path=inv / "skill-inventory.json",
                core_skills_path=core,
                asset_owners_path=owners,
            )
        self.assertIn("litigation-service", out)
        self.assertIn("诉讼总控", out)
        self.assertIn("Inventory skill 总数：1", out)
        self.assertIn("Branch B 顾问模式", out)  # 空 owners 的提示

    def test_map_missing_inventory_reports_notice(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            out = ise.build_asset_map(
                inventory_path=root / "missing.json",
                core_skills_path=root / "missing.yaml",
                asset_owners_path=root / "missing.yaml",
            )
        self.assertIn("inventory 缺失", out)

    def test_map_corrupt_inventory_reports_corrupt_not_missing(self):
        # File exists but contains invalid JSON — must report "损坏" (corrupt),
        # NOT "缺失" (missing), so the agent isn't told to re-run refresh forever.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            inv_file = root / "skill-inventory.json"
            inv_file.write_text("{not json", encoding="utf-8")
            out = ise.build_asset_map(
                inventory_path=inv_file,
                core_skills_path=root / "missing.yaml",
                asset_owners_path=root / "missing.yaml",
            )
        self.assertIn("inventory 损坏", out)
        self.assertNotIn("inventory 缺失", out)

    def test_map_lists_declared_asset_owners(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            inv = root / "runtime"
            inv.mkdir()
            self._write_inventory(inv / "skill-inventory.json", [])
            owners = root / "owners.yaml"
            owners.write_text(
                "asset_owners:\n"
                "  - asset_type: 法律知识规则\n"
                "    owning_skill: legal-knowledge-engine\n"
                "    triggers: [裁判规则]\n",
                encoding="utf-8",
            )
            out = ise.build_asset_map(
                inventory_path=inv / "skill-inventory.json",
                core_skills_path=root / "missing.yaml",
                asset_owners_path=owners,
            )
        self.assertIn("legal-knowledge-engine", out)
        self.assertIn("法律知识规则", out)

    def test_map_warns_when_inventory_is_stale(self):
        # inventory generated_at 超过阈值 → map 输出过期警告（提示先 refresh）。
        # 防止 inventory 过期导致 commit 误判 ambiguous 等 silent 降级（2026-08-06 实测坑）。
        import json
        import datetime
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            inv_dir = root / "runtime"
            inv_dir.mkdir()
            old = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
            (inv_dir / "skill-inventory.json").write_text(
                json.dumps({"generated_at": old, "sources": {}, "skills": [
                    {"id": "x", "name": "x", "source": "s", "skill_md": ""}]}),
                encoding="utf-8")
            out = ise.build_asset_map(
                inventory_path=inv_dir / "skill-inventory.json",
                core_skills_path=root / "missing.yaml",
                asset_owners_path=root / "missing.yaml",
            )
        self.assertIn("过期", out)
        self.assertIn("refresh", out)

    def test_map_no_warning_when_inventory_fresh(self):
        # inventory generated_at 在阈值内 → 无过期警告。
        import json
        import datetime
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            inv_dir = root / "runtime"
            inv_dir.mkdir()
            fresh = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            (inv_dir / "skill-inventory.json").write_text(
                json.dumps({"generated_at": fresh, "sources": {}, "skills": [
                    {"id": "x", "name": "x", "source": "s", "skill_md": ""}]}),
                encoding="utf-8")
            out = ise.build_asset_map(
                inventory_path=inv_dir / "skill-inventory.json",
                core_skills_path=root / "missing.yaml",
                asset_owners_path=root / "missing.yaml",
            )
        self.assertNotIn("过期", out)


class CommitProposalTests(unittest.TestCase):
    """Task 3: commit_proposal privacy-gate + inbox persistence + proposal lifecycle.

    Uses explicit temp-dir roots passed to commit_proposal — never monkeypatches
    module-level state roots and never calls assert_runtime_ready (which would
    try to claim the real data root). The privacy gate runs as a real subprocess
    on a real temp draft file.
    """

    def _roots(self, base: Path) -> dict:
        """Create the four temp roots commit_proposal writes into."""
        review_inbox = base / "review_inbox"
        proposals = base / "proposals"
        review_archive = base / "review_archive"
        runtime = base / "runtime"
        for p in (review_inbox, proposals, review_archive, runtime):
            p.mkdir(parents=True, exist_ok=True)
        return {
            "review_inbox_root": review_inbox,
            "proposals_root": proposals,
            "review_archive_root": review_archive,
            "runtime_root": runtime,
        }

    def _write_skill_md(self, base: Path, skill_id: str, version: str) -> Path:
        """Write a synthetic SKILL.md; return its path."""
        skill_dir = base / "skills" / skill_id
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            f"# {skill_id}\nversion {version}\nstable skill content\n",
            encoding="utf-8",
        )
        return skill_md

    def _write_inventory(self, runtime: Path, skills: list) -> Path:
        import json
        inv = runtime / "skill-inventory.json"
        inv.write_text(
            json.dumps({"generated_at": "x", "sources": {}, "skills": skills}),
            encoding="utf-8",
        )
        return inv

    def test_commit_passing_gate_skill_upgrade_accepts(self):
        # Clean draft + uniquely resolved target → committed_accepted, and a
        # human_decision/accepted event actually lands in the proposal's event log.
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            roots = self._roots(base)
            draft = base / "draft.md"
            draft.write_text("# 提案\n纯方法论文本，无敏感信息。\n", encoding="utf-8")
            skill_md = self._write_skill_md(base, "agent-email", "0.3.1")
            inv = self._write_inventory(roots["runtime_root"], [
                {"id": "agent-email", "name": "agent-email", "title": "Agent Email",
                 "description": "邮件", "version": "0.3.1", "license": "MIT",
                 "source": "legal-skills", "path": str(skill_md.parent),
                 "skill_md": str(skill_md), "modified_at": 1},
            ])
            rc, info = ise.commit_proposal(
                draft=draft,
                proposal_type="skill_upgrade",
                summary="x",
                target_skill="agent-email",
                change_points=("CP-1",),
                inventory_path=inv,
                **roots,
            )
            self.assertEqual(rc, 0, info)
            self.assertEqual(info["status"], "committed_accepted")
            self.assertTrue(info["proposal_id"])
            self.assertTrue(info["artifact_ref"].startswith("review/inbox/"))
            # Artifact physically written (resolve to absorb the /var → /private/var symlink).
            self.assertTrue(Path(info["artifact_path"]).exists())
            written = list(roots["review_inbox_root"].glob("*.md"))
            self.assertEqual(len(written), 1)
            # decide(accepted) must have fired: load the proposal and check the event.
            from proposal_store import ProposalStore
            store = ProposalStore(
                root=roots["proposals_root"],
                review_inbox_root=roots["review_inbox_root"],
                review_archive_root=roots["review_archive_root"],
            )
            events = store.events(info["proposal_id"])
            kinds = [(e.get("kind"), e.get("decision")) for e in events]
            self.assertIn(("human_decision", "accepted"), kinds)
            projected = store.load(info["proposal_id"])
            self.assertEqual(projected["human_decision"], "accepted")

    def test_commit_failing_gate_fail_closed(self):
        # Sensitive draft (phone + identity) → privacy gate blocks, NOTHING written.
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            roots = self._roots(base)
            draft = base / "bad.md"
            draft.write_text("联系 13800138000 身份证 110101199003071234\n", encoding="utf-8")
            rc, info = ise.commit_proposal(
                draft=draft,
                proposal_type="article",
                summary="leaky",
                **roots,
            )
            self.assertNotEqual(rc, 0)
            self.assertEqual(info["status"], "privacy_blocked")
            # Fail-closed: no artifact written anywhere under review_inbox_root.
            files = list(roots["review_inbox_root"].rglob("*")) if roots["review_inbox_root"].exists() else []
            written = [f for f in files if f.is_file()]
            self.assertEqual(written, [])

    def test_commit_no_clobber_same_content(self):
        # Same draft committed twice → second is a no-op reuse (same path/ref).
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            roots = self._roots(base)
            draft = base / "draft.md"
            draft.write_text("# 提案\n纯方法论文本，无敏感信息。\n", encoding="utf-8")
            skill_md = self._write_skill_md(base, "agent-email", "0.3.1")
            inv = self._write_inventory(roots["runtime_root"], [
                {"id": "agent-email", "name": "agent-email", "version": "0.3.1",
                 "skill_md": str(skill_md), "path": str(skill_md.parent)},
            ])
            kwargs = dict(
                draft=draft, proposal_type="skill_upgrade", summary="x",
                target_skill="agent-email", change_points=("CP-1",),
                inventory_path=inv, **roots,
            )
            rc1, info1 = ise.commit_proposal(**kwargs)
            rc2, info2 = ise.commit_proposal(**kwargs)
            self.assertEqual(rc1, 0, info1)
            self.assertEqual(rc2, 0, info2)
            self.assertEqual(info1["artifact_path"], info2["artifact_path"])
            self.assertEqual(info1["artifact_ref"], info2["artifact_ref"])
            # Exactly one .md artifact in the inbox (reused, not duplicated).
            written = list(roots["review_inbox_root"].glob("*.md"))
            self.assertEqual(len(written), 1)
            # Idempotency: re-deciding the same accepted proposal must NOT append
            # a duplicate human_decision event (decide's same-branch short-circuits).
            from proposal_store import ProposalStore
            store = ProposalStore(
                root=roots["proposals_root"],
                review_inbox_root=roots["review_inbox_root"],
                review_archive_root=roots["review_archive_root"],
            )
            accepted = [
                e for e in store.events(info1["proposal_id"])
                if e.get("kind") == "human_decision" and e.get("decision") == "accepted"
            ]
            self.assertEqual(len(accepted), 1)

    def test_commit_article_candidate_only(self):
        # article has no target → committed_candidate (no decide/accepted path).
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            roots = self._roots(base)
            draft = base / "draft.md"
            draft.write_text("# 文章提案\n纯方法论文本，无敏感信息。\n", encoding="utf-8")
            rc, info = ise.commit_proposal(
                draft=draft, proposal_type="article", summary="article x",
                **roots,
            )
            self.assertEqual(rc, 0, info)
            self.assertEqual(info["status"], "committed_candidate")
            written = list(roots["review_inbox_root"].glob("*.md"))
            self.assertEqual(len(written), 1)
            # No human_decision event should exist for a candidate-only proposal.
            from proposal_store import ProposalStore
            store = ProposalStore(
                root=roots["proposals_root"],
                review_inbox_root=roots["review_inbox_root"],
                review_archive_root=roots["review_archive_root"],
            )
            events = store.events(info["proposal_id"])
            self.assertEqual(events, [])

    def test_commit_skill_upgrade_missing_target_is_candidate(self):
        # skill_upgrade with a target NOT in inventory → deferred as candidate
        # (target_resolution missing), not accepted.
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            roots = self._roots(base)
            draft = base / "draft.md"
            draft.write_text("# 提案\n纯方法论文本，无敏感信息。\n", encoding="utf-8")
            inv = self._write_inventory(roots["runtime_root"], [])  # empty inventory
            rc, info = ise.commit_proposal(
                draft=draft, proposal_type="skill_upgrade", summary="x",
                target_skill="nonexistent-skill", change_points=("CP-1",),
                inventory_path=inv, **roots,
            )
            self.assertEqual(rc, 0, info)
            self.assertEqual(info["status"], "committed_candidate")
            from proposal_store import ProposalStore
            store = ProposalStore(
                root=roots["proposals_root"],
                review_inbox_root=roots["review_inbox_root"],
                review_archive_root=roots["review_archive_root"],
            )
            projected = store.load(info["proposal_id"])
            self.assertEqual(projected["target_resolution"], "missing")
            self.assertEqual(projected["human_decision"], "pending")

    def test_commit_skill_upgrade_ambiguous_target_is_candidate(self):
        # skill_upgrade where target matches >1 inventory entry → deferred as
        # candidate with target_resolution="ambiguous" (not accepted).
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            roots = self._roots(base)
            draft = base / "draft.md"
            draft.write_text("# 提案\n纯方法论文本，无敏感信息。\n", encoding="utf-8")
            # Two entries share the same id → _resolve_inventory_target sees >1 match.
            inv = self._write_inventory(roots["runtime_root"], [
                {"id": "dup-skill", "name": "dup-skill", "version": "0.1",
                 "skill_md": "", "path": ""},
                {"id": "dup-skill", "name": "dup-skill", "version": "0.2",
                 "skill_md": "", "path": ""},
            ])
            rc, info = ise.commit_proposal(
                draft=draft, proposal_type="skill_upgrade", summary="x",
                target_skill="dup-skill", change_points=("CP-1",),
                inventory_path=inv, **roots,
            )
            self.assertEqual(rc, 0, info)
            self.assertEqual(info["status"], "committed_candidate")
            from proposal_store import ProposalStore
            store = ProposalStore(
                root=roots["proposals_root"],
                review_inbox_root=roots["review_inbox_root"],
                review_archive_root=roots["review_archive_root"],
            )
            projected = store.load(info["proposal_id"])
            self.assertEqual(projected["target_resolution"], "ambiguous")
            self.assertEqual(projected["human_decision"], "pending")


class MainCliTests(unittest.TestCase):
    def test_main_map_returns_zero_and_prints_map(self):
        # Exercises the argparse wiring + override args + rc=0 + stdout stream.
        # (commit_proposal is covered via direct calls above; main()-level commit
        # needs assert_runtime_ready which is environmental, so smoke map here.)
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            inv = root / "runtime"
            inv.mkdir()
            (inv / "skill-inventory.json").write_text(
                '{"generated_at":"x","sources":{},"skills":[]}', encoding="utf-8")
            core = root / "core_skills.yaml"
            core.write_text("skill_sources: {}\ncore_skills: []\n", encoding="utf-8")
            owners = root / "owners.yaml"
            owners.write_text("asset_owners: []\n", encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = ise.main([
                    "map",
                    "--inventory", str(inv / "skill-inventory.json"),
                    "--core-skills", str(core),
                    "--asset-owners", str(owners),
                ])
            self.assertEqual(rc, 0)
            self.assertIn("Self Evolve 资产地图", buf.getvalue())


class ResolveInventoryTargetTests(unittest.TestCase):
    """防御：inventory 重复登记/过期时，_resolve_inventory_target 应按 SKILL.md
    实际文件折叠重复条目，而非误判 ambiguous。实测发现旧 inventory 把同一物理
    skill 按多 source 各扫一次（litigation-skills/private-skills 配置重复），
    导致 interactive_sediment 的 in-chat auto-accept 路径静默失效（2026-08-06）。"""

    @staticmethod
    def _write_inv(root: Path, skills: list) -> Path:
        import json
        inv_path = root / "skill-inventory.json"
        inv_path.write_text(json.dumps({"skills": skills}), encoding="utf-8")
        return inv_path

    def test_same_file_duplicates_are_resolved(self):
        # 两条同 id 但 skill_md 指向同一文件 → resolved（折叠重复登记），并能算出 content sha。
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            skill_dir = root / "my-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\nname: my-skill\nversion: 1.2\n---\n# My Skill\n", encoding="utf-8")
            skill_md = str(skill_dir / "SKILL.md")
            inv = self._write_inv(root, [
                {"id": "my-skill", "name": "my-skill", "version": "1.2",
                 "source": "src-a", "skill_md": skill_md},
                {"id": "my-skill", "name": "my-skill", "version": "1.2",
                 "source": "src-b", "skill_md": skill_md},
            ])
            resolution, version, content_sha = ise._resolve_inventory_target(inv, root, "my-skill")
        self.assertEqual(resolution, "resolved")
        self.assertEqual(version, "1.2")
        self.assertNotEqual(content_sha, "")

    def test_different_file_duplicates_remain_ambiguous(self):
        # 两条同 id 但 skill_md 指向不同文件 → 仍 ambiguous（真正的同名歧义，不能折叠）。
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            sa = root / "a"; sa.mkdir()
            (sa / "SKILL.md").write_text("---\nname: dup\n---\n# A\n", encoding="utf-8")
            sb = root / "b"; sb.mkdir()
            (sb / "SKILL.md").write_text("---\nname: dup\n---\n# B\n", encoding="utf-8")
            inv = self._write_inv(root, [
                {"id": "dup", "name": "dup", "version": "1", "skill_md": str(sa / "SKILL.md")},
                {"id": "dup", "name": "dup", "version": "1", "skill_md": str(sb / "SKILL.md")},
            ])
            resolution, _, _ = ise._resolve_inventory_target(inv, root, "dup")
        self.assertEqual(resolution, "ambiguous")


class PendingVerificationsTests(unittest.TestCase):
    """验证回看：列出 applied 但未 verified 的提案，驱动交互沉淀时回看效果，
    补全 applied→verified 半圈（否则 verified 靠人手动记，闭环开环）。"""

    def test_returns_only_applied_unverified(self):
        proposals = [
            {"proposal_id": "a", "applied_commit": "abc", "outcome": "pending"},   # 在
            {"proposal_id": "b", "applied_commit": "def", "outcome": "verified"},  # 有结论，不在
            {"proposal_id": "c", "applied_commit": "", "outcome": "pending"},      # 未 applied，不在
        ]
        result = ise.pending_verifications(proposals=proposals)
        self.assertEqual([p["proposal_id"] for p in result], ["a"])

    def test_excludes_failed_and_inconclusive(self):
        # failed / inconclusive 也是"已验证（有结论）"，不再提示回看
        proposals = [
            {"proposal_id": "x", "applied_commit": "c1", "outcome": "failed"},
            {"proposal_id": "y", "applied_commit": "c2", "outcome": "inconclusive"},
            {"proposal_id": "z", "applied_commit": "c3", "outcome": "pending"},
        ]
        result = ise.pending_verifications(proposals=proposals)
        self.assertEqual([p["proposal_id"] for p in result], ["z"])

    def test_empty_input_returns_empty(self):
        self.assertEqual(ise.pending_verifications(proposals=[]), [])


if __name__ == "__main__":
    unittest.main()
