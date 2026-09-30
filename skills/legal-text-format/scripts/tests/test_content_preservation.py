"""仅使用虚构文本验证格式化不可丢失法律内容。"""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(os.environ.get('LEGAL_FORMAT_SCRIPT', Path(__file__).resolve().parents[1] / 'format_legal_cases.py'))
spec = importlib.util.spec_from_file_location('formatter_under_test', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def render(text):
    return module.format_text(text, '虚构法院', 'https://example.test/source', '虚构测试')


class ContentPreservationTests(unittest.TestCase):
    def test_long_typical_meaning_is_not_truncated(self):
        body = '完整法律分析。' * 150 + '最后结论必须保留。'
        self.assertIn(body, render('案例1\n虚构合同案\n典型意义\n' + body))

    def test_no_meaning_multisection_keeps_last_paragraph(self):
        text = '案例1\n虚构合同案\n基本案情\n事实。\n\n裁判结果\n判项。\n\n' + '完整裁判说明。' * 70 + '\n\n最后判项必须保留。'
        self.assertIn('最后判项必须保留。', render(text))

    def test_multiple_cases_survive_long_final_section(self):
        text = '案例1\n虚构甲案\n典型意义\n' + '甲分析。' * 80 + '\n案例2\n虚构乙案\n典型意义\n' + '乙分析。' * 150 + '最后乙结论。'
        out = render(text)
        for token in ('案例1', '虚构甲案', '案例2', '虚构乙案', '最后乙结论。'):
            self.assertIn(token, out)

    def test_keyword_in_prose_does_not_end_case(self):
        for keyword in ('联系我们', '扫码获取', '来源', '知产财经', 'END', '查看专题'):
            with self.subTest(keyword=keyword):
                text = f'案例1\n虚构合同案\n基本案情\n被告文字“{keyword}”是证据。\n裁判结果\n最终判决。'
                out = render(text)
                self.assertIn(f'“{keyword}”是证据。', out)
                self.assertIn('最终判决。', out)

    def test_ambiguous_standalone_lines_are_preserved(self):
        text = '案例1\n虚构合同案\n基本案情\n以下为证据原文：\n联系我们\n来源：上海市高级人民法院\n裁判结果\n判决有效。'
        out = render(text)
        self.assertIn('联系我们', out)
        self.assertIn('来源：上海市高级人民法院', out)
        self.assertIn('判决有效。', out)

    def test_only_promo_looking_suffix_is_preserved(self):
        self.assertIn('联系我们', render('案例1\n虚构合同案\n基本案情\n联系我们'))

    def test_explicit_attribution_suffix_removed_without_case_loss(self):
        body = '完整分析。' * 150 + '最终结论。'
        out = render('案例1\n虚构合同案\n典型意义\n' + body + '\n来源：上海市高级人民法院\n联系我们\n')
        self.assertIn(body, out)
        self.assertNotIn('来源：上海市高级人民法院', out)
        self.assertNotIn('联系我们', out)

    def test_unrecognized_line_after_source_prevents_trimming(self):
        out = render('案例1\n虚构合同案\n典型意义\n来源：上海市高级人民法院\n来源是认定事实的必要依据。')
        self.assertIn('来源：上海市高级人民法院', out)
        self.assertIn('来源是认定事实的必要依据。', out)

    def test_case_number_preserved_across_title_forms(self):
        for title, number in [('案例1\n虚构合同案', '案例1'), ('案例一\n虚构合同案', '案例一'), ('/** 案例2 虚构合同案 **/', '案例2'), ('1、虚构合同案', '1、'), ('1. 虚构合同案', '1.'), ('一、虚构合同案', '一、')]:
            with self.subTest(title=title):
                self.assertIn(number, render(title + '\n基本案情\n事实。'))

    def test_decimals_grouping_percent_and_version_preserved(self):
        out = render('案例1\n虚构合同案\n基本案情\n金额1,234.56元，利率3.5%，编号1.2.3。')
        for value in ('1,234.56', '3.5%', '1.2.3'):
            self.assertIn(value, out)

    def test_bare_url_and_markdown_citation_preserved(self):
        for citation in ('https://example.test/a?q=1&x=2.5', '[来源](https://example.test/a?q=1)', '[原文](https://example.test/a_(b))', '`amount=1.23; path=a.b`'):
            with self.subTest(citation=citation):
                self.assertIn(citation, render('案例1\n虚构合同案\n基本案情\n出处：' + citation + '。'))

    def test_normal_prose_punctuation_still_converted(self):
        out = render('案例1\n虚构合同案\n基本案情\n法院(2026)称:甲,乙;"有效".是吗?是!')
        self.assertIn('法院（2026）称：甲，乙；“有效”。是吗？是！', out)

    def test_fullwidth_numbers_still_normalized(self):
        self.assertIn('金额123.45元', render('案例1\n虚构合同案\n基本案情\n金额１２３.４５元'))

    def test_quoted_footer_and_documentary_image_remain(self):
        text = '案例1\n虚构合同案\n基本案情\n> 来源：上海市高级人民法院\n![二维码证据](https://example.test/qr.png)\n裁判结果\n判决。'
        out = render(text)
        self.assertIn('> 来源：上海市高级人民法院', out)
        self.assertIn('![二维码证据](https://example.test/qr.png)', out)

    def test_prefix_and_later_april_date_do_not_drop_earlier_case(self):
        text = '必须保留的引述上下文。\n案例1\n虚构甲案\n基本案情\n甲方事实。\n案例2\n虚构乙案\n基本案情\n4月23日上午，乙方签约。\n裁判结果\n乙方判项。'
        out = render(text)
        for part in ('必须保留的引述上下文。', '案例1', '甲方事实。', '案例2', '乙方判项。'):
            self.assertIn(part, out)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / 'input.md').write_text(text, encoding='utf-8')
            subprocess.run([sys.executable, str(SCRIPT), 'input.md', 'out.md', '虚构法院', 'https://example.test', '虚构测试'], cwd=path, check=True, capture_output=True)
            self.assertIn('甲方事实。', (path / 'out.md').read_text(encoding='utf-8'))

    def test_explicit_prefix_marker_remains_supported(self):
        out = module.format_text('介绍\n案例1\n虚构合同案\n基本案情\n事实。', '虚构法院', 'https://example.test', '虚构测试', keep_from_marker='案例1')
        self.assertNotIn('介绍', out)
        self.assertIn('案例1', out)

    def test_email_and_www_links_preserved(self):
        text = '联系 foo.bar+case@example.test，网址 www.example.test/a?q=1.5。'
        out = render('案例1\n虚构合同案\n基本案情\n' + text)
        self.assertIn(text, out)

    def test_fenced_exhibits_remain_literal(self):
        for marker in ('```', '~~~~'):
            for closing in ('', '\n' + marker):
                with self.subTest(marker=marker, closed=bool(closing)):
                    block = marker + 'text\n案例1\n典型意义\n１２３.４５, http://example.test/a?x=1\n \n\n原文: test.\n来源：上海市高级人民法院' + closing
                    self.assertIn(block, render('案例1\n虚构合同案\n基本案情\n' + block))

    def test_standalone_end_is_ambiguous(self):
        self.assertTrue(render('案例1\n虚构合同案\n基本案情\nEND').endswith('END'))

    def test_tentative_titles_and_eof_markers_never_disappear(self):
        examples = (
            ('涉合成纠纷案\n基本案情\n事实完整', '涉合成纠纷案'),
            ('前段\n涉合成纠纷案\n后段', '涉合成纠纷案'),
            ('案例1', '案例1'),
            ('1.', '1.'),
            ('案例1\n```text\nvalue=1.2\n```', '```text\nvalue=1.2\n```'),
            ('案例1\n基本案情\n事实。', '### 基本案情'),
            ('案例1\n2. 虚构合同案\n事实。', '2. 虚构合同案'),
        )
        for text, expected in examples:
            with self.subTest(text=text):
                self.assertIn(expected, render(text))
                with tempfile.TemporaryDirectory() as temp:
                    path = Path(temp)
                    (path / 'input.md').write_text(text, encoding='utf-8')
                    subprocess.run([sys.executable, str(SCRIPT), 'input.md', 'out.md', '虚构法院', 'https://example.test', '虚构测试'], cwd=path, check=True, capture_output=True)
                    self.assertIn(expected, (path / 'out.md').read_text(encoding='utf-8'))

    def test_empty_input(self):
        self.assertTrue(render('').startswith('# 虚构测试'))

    def test_cli_short_input_last_character_bytes(self):
        for text in ('案例1\n虚构合同案\n基本案情\n完整末字终', '案例1\n虚构合同案\n基本案情\n完整句号。', '案例1\n虚构合同案\n基本案情\nEmoji结尾⚖'):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as temp:
                path = Path(temp)
                (path / 'input.md').write_text(text, encoding='utf-8')
                subprocess.run([sys.executable, str(SCRIPT), 'input.md', 'out.md', '虚构法院', 'https://example.test', '虚构测试'], cwd=path, check=True, capture_output=True)
                self.assertTrue((path / 'out.md').read_bytes().endswith(text.splitlines()[-1].encode('utf-8')))

    def test_cli_internal_markdown_rule_does_not_cut_body(self):
        text = '案例1\n虚构合同案\n基本案情\n事实。\n---\n裁判结果\n最终判项。'
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / 'input.md').write_text(text, encoding='utf-8')
            subprocess.run([sys.executable, str(SCRIPT), 'input.md', 'out.md', '虚构法院', 'https://example.test', '虚构测试'], cwd=path, check=True, capture_output=True)
            self.assertIn('最终判项。', (path / 'out.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
