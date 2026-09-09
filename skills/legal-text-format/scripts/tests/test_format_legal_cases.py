import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from format_legal_cases import format_text


class FormatLegalCasesTests(unittest.TestCase):
    def test_formats_balanced_quotes_and_handles_footer_after_typical_meaning(self):
        source = """案例1
测试案
案情摘要
法院认为\"合同有效\"，当事人称'没有异议'。
典型意义
这是测试内容。
来源：上海市高级人民法院
"""

        result = format_text(
            source,
            court_name="测试法院",
            source_url="https://example.com/case",
            title="测试案例",
        )

        self.assertIn("“合同有效”", result)
        self.assertIn("‘没有异议’", result)
        self.assertNotIn("来源：上海市高级人民法院", result)

    def test_cli_can_write_to_current_directory(self):
        script = SCRIPTS_DIR / "format_legal_cases.py"
        with tempfile.TemporaryDirectory() as temp_dir:
            working_dir = Path(temp_dir)
            input_file = working_dir / "input.md"
            input_file.write_text("案例1\n测试案\n案情摘要\n测试内容。", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    str(input_file),
                    "result.md",
                    "测试法院",
                    "https://example.com/case",
                    "测试案例",
                ],
                cwd=working_dir,
                check=False,
                capture_output=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            output_file = working_dir / "result.md"
            output = output_file.read_text(encoding="utf-8")

        self.assertTrue(output_file.name == "result.md")
        self.assertIn("# 测试案例", output)

    def test_unmatched_quotes_are_preserved(self):
        source = "案例1\n测试案\n案情摘要\n该处只有一个\"引号。"

        result = format_text(
            source,
            court_name="测试法院",
            source_url="https://example.com/case",
            title="测试案例",
        )

        self.assertIn('一个"引号', result)


if __name__ == "__main__":
    unittest.main()
