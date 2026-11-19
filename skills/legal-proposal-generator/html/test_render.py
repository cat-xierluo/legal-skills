import tempfile
import unittest
from pathlib import Path

from render import render_proposal


EXAMPLE = Path(__file__).with_name("example.md").read_text(encoding="utf-8")
TEMPLATES = Path(__file__).parents[1] / "templates"


class RenderProposalTest(unittest.TestCase):
    def render_source(self, markdown):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "proposal.md"
            source.write_text(markdown, encoding="utf-8")
            return render_proposal(source)

    def render_with(self, text):
        return self.render_source(EXAMPLE + "\n" + text)

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

    def test_blueprint_marks_only_the_selected_stages(self):
        source = (TEMPLATES / "html-service-blueprint.md").read_text(encoding="utf-8")
        document = self.render_source(source + "\n## 后记\n\n1. 等候委托方确认。\n")
        self.assertEqual(document.count('<ol class="scene-service-blueprint">'), 1)
        self.assertIn("<ol>\n<li>等候委托方确认。</li>", document)
        self.assertLess(document.index("核对交付"), document.index("确认下一步"))

    def test_decision_template_preserves_conditions_and_limits_in_rows(self):
        source = (TEMPLATES / "html-decision-strategy.md").read_text(encoding="utf-8")
        document = self.render_source(source)
        self.assertIn('<div class="table-scroll"><table class="scene-decision-strategy">', document)
        self.assertRegex(document, r"<td>回复只有转述或截图不完整</td>\s*"
                                   r"<td>补齐邮件线程和对应附件，再评估路径</td>\s*"
                                   r"<td>暂不据此认定已完成验收</td>")

    def test_scene_metadata_requires_an_unambiguous_section_and_block(self):
        source = (TEMPLATES / "html-service-blueprint.md").read_text(encoding="utf-8")
        for candidate, error in (
            (source.replace("html_scene: service_blueprint\n", ""), "同时填写"),
            (source.replace("html_section: 服务路径", "html_section: 未找到"), "唯一"),
            (source + "\n## 服务路径\n\n后记。\n", "唯一"),
            (source.replace("html_section: 服务路径", "html_section: 服务范围"), "顶层有序列表"),
        ):
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                self.render_source(candidate)

    def test_decision_scene_requires_three_columns_and_records(self):
        source = (TEMPLATES / "html-decision-strategy.md").read_text(encoding="utf-8")
        header = "| 核验条件 | 建议动作 | 风险边界 |\n| --- | --- | --- |\n"
        before = source.split(header)[0]
        for table in (header, "| 条件 | 动作 |\n| --- | --- |\n| 待确认 | 补证 |\n"):
            with self.subTest(table=table), self.assertRaisesRegex(ValueError, "三列及至少一条决策记录"):
                self.render_source(before + table)


if __name__ == "__main__":
    unittest.main()
