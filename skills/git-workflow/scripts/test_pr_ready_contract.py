#!/usr/bin/env python3
"""Offline documentation contract; does not mutate any GitHub PR."""
import os
from pathlib import Path
import re
import unittest


class ReadyContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        default = Path(__file__).resolve().parents[1] / 'references' / 'pr-workflow.md'
        text = Path(os.environ.get('PR_WORKFLOW_DOC', default)).read_text(encoding='utf-8')
        cls.section = text.split('## 3. 合并前门禁', 1)[1].split('## 4.', 1)[0]

    def test_official_ready_command_targets_existing_pr_and_repo(self):
        self.assertIn("gh pr ready '<N>' --repo '<owner/repo>'", self.section)

    def test_same_pr_and_history_are_preserved(self):
        self.assertIn('同一个 PR', self.section)
        self.assertIn('不要为转 ready 关闭或重建 PR', self.section)
        self.assertNotRegex(self.section, r'转换标准操作：关闭.*重建')

    def test_before_and_after_identity_checks(self):
        for field in ('number/headRefOid/baseRefName', 'state=OPEN', 'isDraft=false', 'head/base 未变'):
            self.assertIn(field, self.section)

    def test_failure_does_not_trigger_recreation(self):
        self.assertIn('失败或网络结果不明', self.section)
        self.assertIn('先只读回查同一 PR', self.section)
        self.assertIn('停止并保留现场', self.section)

    def test_authorization_review_and_ci_remain_required(self):
        for gate in ('仅在授权和验收满足后', 'ready 不代表已获合并授权或检查通过', '独立 review', '最终 head 的 checks'):
            self.assertIn(gate, self.section)

    def test_official_reference_is_available(self):
        self.assertIn('https://cli.github.com/manual/gh_pr_ready', self.section)


if __name__ == '__main__':
    unittest.main()
