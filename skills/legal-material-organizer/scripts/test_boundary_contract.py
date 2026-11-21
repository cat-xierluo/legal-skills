import unittest
from pathlib import Path


SKILL_FILE = Path(__file__).resolve().parents[1] / "SKILL.md"
NAMING_RULES = Path(__file__).resolve().parents[1] / "references" / "organization-and-naming-rules.md"
REPOSITORY_ROOT = SKILL_FILE.parents[1]


class BoundaryContractTest(unittest.TestCase):
    def test_single_readable_file_is_intake_boundary(self):
        text = SKILL_FILE.read_text(encoding="utf-8")
        self.assertIn("单个可读文件", text)
        self.assertIn("新材料接收与案件结构适配", text)
        self.assertIn("先入库，再分析", text)
        self.assertIn("不强制调用、创建或交接 new-case", text)

    def test_existing_case_structure_takes_precedence(self):
        text = NAMING_RULES.read_text(encoding="utf-8")
        self.assertIn("既有案件结构优先", text)
        self.assertIn("不得检测到某种预设后重建案件目录", text)
        self.assertIn("读取目标案件根目录的既有结构、材料清单和编号上限", text)

    def test_analysis_does_not_bypass_intake(self):
        skill = REPOSITORY_ROOT / "legal-case-analysis" / "SKILL.md"
        workflow = REPOSITORY_ROOT / "legal-case-analysis" / "references" / "workflow.md"
        if not skill.is_file() or not workflow.is_file():
            self.skipTest("cross-skill sources are not installed")
        self.assertIn("不得因已在对话中出现而直接成为证据来源", skill.read_text(encoding="utf-8"))
        self.assertIn("实质性事实/证据片段", workflow.read_text(encoding="utf-8"))
        self.assertNotIn("用户直接提供的可读文本", workflow.read_text(encoding="utf-8"))

    def test_new_case_has_no_material_side_effects(self):
        skill = REPOSITORY_ROOT / "new-case" / "SKILL.md"
        classification = REPOSITORY_ROOT / "new-case" / "references" / "classification-guide.md"
        trademark = REPOSITORY_ROOT / "new-case" / "assets" / "trademark.yaml"
        if not all(path.is_file() for path in (skill, classification, trademark)):
            self.skipTest("cross-skill sources are not installed")
        forbidden_fragments = (
            "cp -p",
            "mv 改名",
            "pdftotext",
            "mineru-ocr",
            "读取文件内容前几行",
            "日期读文件 mtime/birth time",
            "日期读 mtime/birth time",
            "文件名加 YYMMDD",
            "PDF CreationDate",
        )
        for path in (skill, classification, trademark):
            text = path.read_text(encoding="utf-8")
            for fragment in forbidden_fragments:
                self.assertNotIn(fragment, text)


if __name__ == "__main__":
    unittest.main()
