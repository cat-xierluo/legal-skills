"""Local workmode configuration and shared classification behavior."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import iteration_report
import workmode_config
import workmode_extract
import workmode_ledger


class WorkmodeConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "workmode.local.json"
        patcher = patch.object(workmode_config, "CONFIG_PATH", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, data):
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def sessions(self):
        return [
            {"session_id": "one", "topic_title": "alpha work", "evidence_snippets": ["alpha work"]},
            {"session_id": "two", "topic_title": "beta work", "evidence_snippets": ["beta work"]},
        ]

    def test_new_user_default_is_neutral_and_no_old_special_case(self):
        categories = workmode_config.load_focus_config()
        self.assertEqual(categories, workmode_config.DEFAULT_FOCUS_KEYWORDS)
        self.assertEqual(workmode_config.match_focus("律师 IP 法律 IP", categories), [])
        self.assertNotIn("律师 IP", workmode_ledger.build_analysis_prompt({}))

    def test_both_consumers_use_same_override_and_extra_rules(self):
        self.write({"focus_keywords": {"Synthetic": ["alpha"]},
                    "focus_extra_keywords": {"Synthetic": ["beta"]}})
        report = iteration_report._extract_focus_distribution(self.sessions())
        signals = workmode_extract._collect_signals(self.sessions())
        self.assertEqual(report["counts"], {"Synthetic": 2, "未匹配": 0})
        self.assertEqual([s[1] for s in signals if s[0] == "focus"], ["Synthetic", "Synthetic"])
        cluster = workmode_extract._cluster_signals(signals)[0]
        self.assertEqual(cluster["topic_key"], "focus:Synthetic")
        expected = "wmp-clu-" + hashlib.sha256("focus\0Synthetic".encode()).hexdigest()[:20]
        self.assertEqual(cluster["cluster_id"], expected)
        workmode_extract.build_packet([cluster])

    def test_bad_configuration_fails_in_both_consumers_without_disclosure(self):
        invalid = ['{ secret', '{"focus_keywords":{},"secret":"private-value"}',
                   '{"focus_keywords":{"X":[]}}', '{"focus_keywords":{"X":[42]}}',
                   '{"focus_keywords":{},"focus_extra_keywords":{"X":["y"]}}',
                   '{"focus_keywords":{},"focus_keywords":{}}']
        for raw in invalid:
            self.path.write_text(raw, encoding="utf-8")
            for consumer in (iteration_report._extract_focus_distribution, workmode_extract._collect_signals):
                with self.subTest(raw=raw, consumer=consumer.__name__):
                    with self.assertRaises(ValueError) as caught:
                        consumer(self.sessions())
                    self.assertEqual(str(caught.exception), "Invalid workmode configuration")

    def test_legacy_override_preserves_label_and_cluster_identity(self):
        # The synthetic override exercises the old base-plus-extra matching shape.
        self.write({"focus_keywords": {"Old Label": ["alpha"]},
                    "focus_extra_keywords": {"Old Label": ["beta"]}})
        signals = workmode_extract._collect_signals(self.sessions())
        clusters = workmode_extract._cluster_signals(signals)
        self.assertEqual(clusters[0]["topic_key"], "focus:Old Label")
        old_id = "wmp-clu-" + hashlib.sha256("focus\0Old Label".encode()).hexdigest()[:20]
        self.assertEqual(clusters[0]["cluster_id"], old_id)


if __name__ == "__main__":
    unittest.main()
