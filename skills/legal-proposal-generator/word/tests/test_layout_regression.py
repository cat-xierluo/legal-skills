"""用匿名内容检查生成的 Word 结构及附页选择。"""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
import zipfile


WORD = Path(__file__).resolve().parents[1]


class LayoutRegressionTest(unittest.TestCase):
    def test_generated_docx_semantics(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "proposal.md"
            source.write_text("""---
law_firm: 示例律师事务所
client: 示例企业
lawyer: 测试律师
date: 2026年9月23日
---
# 示例法律服务方案
## 一、范围
- 圆点条目
- 第二条目
1. 编号条目
2. 第二编号条目
> 引文内容
""", encoding="utf-8")
            config = root / "team-config.md"
            config.write_text("""## 主办律师介绍
<table>
<!-- 测试律师 -->
<tr><td><strong>测试律师 / 律师</strong><br><strong>专业领域：</strong>示例领域</td></tr>
</table>

## 律所简介

示例律师事务所简介。

## 律所荣誉

- 示例荣誉
""", encoding="utf-8")
            output = root / "proposal.docx"
            env = os.environ.copy()
            if not env.get("NODE_PATH"):
                npm = subprocess.run(["npm", "root", "-g"], check=True, capture_output=True, text=True)
                env["NODE_PATH"] = npm.stdout.strip()
            subprocess.run(["node", str(WORD / "render.js"), "--input", str(source),
                            "--output", str(output), "--cover", "C", "--full",
                            "--team-config", str(config), "--lawyers", "测试律师"],
                           check=True, capture_output=True, text=True, env=env)
            with zipfile.ZipFile(output) as package:
                document = package.read("word/document.xml").decode("utf-8")
                numbering = package.read("word/numbering.xml").decode("utf-8")
                footers = [package.read(name).decode("utf-8") for name in package.namelist()
                           if re.fullmatch(r"word/footer\d+\.xml", name)]
            self.assertEqual(document.count("<w:sectPr"), 5)
            self.assertIn('w:numFmt w:val="bullet"', numbering)
            self.assertIn('w:numFmt w:val="decimal"', numbering)
            self.assertIn('w:fill="FAFAFA"', document)
            footer_xml = "\n".join(footers)
            self.assertIn("PAGE", footer_xml)
            self.assertIn("服务团队", footer_xml)
            self.assertIn("律所简介", footer_xml)
            self.assertIn("荣誉资质", footer_xml)
            self.assertNotIn("SECTIONPAGES", footer_xml)

    def test_selected_back_matter_skips_unused_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / "team-config.md"
            config.write_text("""## 主办律师介绍
<table>
<!-- 测试律师甲 -->
<tr><td><strong>测试律师甲 / 律师</strong></td></tr>
<!-- 测试律师乙 -->
<tr><td><img src="missing-portrait.png"><strong>测试律师乙 / 律师</strong></td></tr>
</table>

## 相关法院判决书

![裁判样张](missing-judgment.png)

## 律所简介

示例律所简介。

## 律所荣誉

- 示例荣誉
""", encoding="utf-8")
            output = root / "proposal.docx"
            env = os.environ.copy()
            if not env.get("NODE_PATH"):
                npm = subprocess.run(["npm", "root", "-g"], check=True, capture_output=True, text=True)
                env["NODE_PATH"] = npm.stdout.strip()
            rendered = subprocess.run(["node", str(WORD / "render.js"), "--input", str(WORD / "examples/proposal.md"),
                                       "--output", str(output), "--full", "--team-config", str(config),
                                       "--lawyers", "测试律师甲", "--back-matter", "honors,team,firm"],
                                      capture_output=True, text=True, env=env)
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            with zipfile.ZipFile(output) as package:
                document = package.read("word/document.xml").decode("utf-8")
            self.assertEqual(document.count("<w:sectPr"), 5)
            self.assertNotIn("典型案例与既往判决", document)
            self.assertNotIn("测试律师乙", document)
            self.assertLess(document.index("服务团队介绍"), document.index("律所简介"))
            self.assertLess(document.index("律所简介"), document.index("律所荣誉与资质"))


if __name__ == "__main__":
    unittest.main()
