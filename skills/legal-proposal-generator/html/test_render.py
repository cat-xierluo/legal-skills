import tempfile
import unittest
from pathlib import Path

from render import render_proposal


EXAMPLE = Path(__file__).with_name("example.md").read_text(encoding="utf-8")


class RenderProposalTest(unittest.TestCase):
    def render_with(self, text):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "proposal.md"
            source.write_text(EXAMPLE + "\n" + text, encoding="utf-8")
            return render_proposal(source)

    def test_navigation_and_escaped_table_separator(self):
        document = self.render_with(
            "## **附加**说明\n\n| 阶段 | 工作 |\n| --- | --- |\n| 核对 | 备注\\|对照 |\n"
        )
        self.assertIn('<a href="#chapter-5">附加说明</a>', document)
        self.assertIn('<h2 id="chapter-5"><strong>附加</strong>说明</h2>', document)
        self.assertIn("<td>备注|对照</td>", document)

    def test_table_must_not_omit_or_pad_cells(self):
        for row in ("| 核对 |", "| 核对 | 确认 | 限定条件 |"):
            with self.subTest(row=row), self.assertRaisesRegex(ValueError, "列数与表头不一致"):
                self.render_with(f"| 阶段 | 工作 |\n| --- | --- |\n{row}\n")


if __name__ == "__main__":
    unittest.main()
