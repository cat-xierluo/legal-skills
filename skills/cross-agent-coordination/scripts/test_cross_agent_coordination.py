#!/usr/bin/env python3
"""Regression tests for cross-agent-coordination scripts."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TASK_SCAFFOLD = SCRIPT_DIR / "task_scaffold.py"
FIND_TASK = SCRIPT_DIR / "find_task.py"
EMAIL_TRIGGER = SCRIPT_DIR / "email_trigger.py"
GH_GIT = SCRIPT_DIR / "gh_git.py"


def run_cmd(args, cwd=None):
    return subprocess.run(
        [sys.executable, *map(str, args)],
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout


BOOK_ISSUES = """# 待创建 Issues 清单

### ✅ Issue #1: ch04 Agent 应用介绍
- **Lead Author**: 杨卫薪
- **依赖**: 无
#### 验收标准
- [ ] 平台对比客观

### ✅ Issue #2: ch05 第三方工具配置
- **Lead Author**: 杨卫薪
- **依赖**: Issue #1 完成
#### 验收标准
- [ ] 配置步骤可复现

### ✅ Issue #3: ch06 单个 Skill 的编写
- **Lead Author**: 杨卫薪

### ✅ Issue #4: ch07 法律 Skill 的迭代优化
- **Lead Author**: 杨卫薪

### ✅ Issue #5: ch09 诉讼文书生成
- **Lead Author**: 杨卫薪

### ✅ Issue #6: ch12 律所 IP 运营
- **Lead Author**: 杨卫薪

### ⬜ Issue #7: 确定 STYLE-GUIDE 关键决策
- **类型**: 整合
- **负责**: 杨卫薪确认
- **依赖**: 无
#### 需确定事项
- [ ] 方法论统一命名

### ✅ Issue #8: 全书术语一致性检查
- **类型**: 整合
- **依赖**: 所有章节完成

### ✅ Issue #9: 触发 Manus 调研任务
- **类型**: 研究（委托 Manus）
- **依赖**: Issue #7 确定后
- **目标**: 为 ch03 法律 AI 基础设施章节提供调研支撑
#### 调研任务
1. **法律 AI 产品生态调查**
   - 中国法律 AI 产品：法宝、华语原点、法天使、密率等
2. **MCP 生态与法律服务调查**
   - 法律相关 MCP 服务清单
#### 验收标准
- [ ] 形成产品对比表

### ✅ Issue #10: 全书结构与衔接审阅
- **类型**: 审阅
- **依赖**: 各篇章初稿完成
#### 审阅维度
- [ ] 全书叙事线连贯
"""


class CrossAgentCollabTests(unittest.TestCase):
    def test_config_uses_only_collab_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "monorepo.yaml").write_text(
                "project:\n  default_agent: codex\n",
                encoding="utf-8",
            )
            output = run_cmd([TASK_SCAFFOLD, "create", "--root", root, "--type", "研究", "--topic", "旧配置忽略", "--dry-run"])
            self.assertIn("DRY_RUN_ASSIGNEE:openclaw", output)

            (root / "config" / "collab.yaml").write_text(
                "project:\n  default_agent: codex\n",
                encoding="utf-8",
            )
            output = run_cmd([TASK_SCAFFOLD, "create", "--root", root, "--type", "研究", "--topic", "新配置生效", "--dry-run"])
            self.assertIn("DRY_RUN_ASSIGNEE:codex", output)

    def test_custom_type_template_and_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "templates" / "tasks").mkdir(parents=True)
            (root / "config" / "task-types.yaml").write_text(
                "task_types:\n  整合:\n    aliases: [integration]\n    description: merge\n    output_hint: output\n",
                encoding="utf-8",
            )
            (root / "templates" / "tasks" / "default.md").write_text(
                "---\nid: {{ id }}\nslug: {{ slug }}\ntitle: {{ title }}\ntype: {{ type }}\n---\n\n# {{ title }}\n\n## 验收标准\n\n完成。\n",
                encoding="utf-8",
            )
            run_cmd([
                TASK_SCAFFOLD,
                "create",
                "--root",
                root,
                "--type",
                "integration",
                "--topic",
                "全书术语一致性检查",
                "--field",
                "chapter=ch01",
                "--field",
                "target_words=15000",
                "--force-new",
            ])
            readme = next(root.glob("*-整合-*/README.md")).read_text(encoding="utf-8")
            self.assertIn("type: 整合", readme)
            self.assertIn("chapter: ch01", readme)
            self.assertIn("target_words: 15000", readme)

    def test_available_filters_dependencies_and_claim_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "collab.yaml").write_text(
                "project:\n  default_agent: codex\n  claim_policy: assigned_only\n",
                encoding="utf-8",
            )
            run_cmd([TASK_SCAFFOLD, "create", "--root", root, "--type", "研究", "--topic", "基础调研", "--assignee", "codex", "--force-new"])
            first = next(root.glob("*-研究-基础调研/README.md"))
            first_id = first.parent.name.split("-", 1)[0]
            first.write_text(first.read_text(encoding="utf-8").replace("status: todo", "status: done"), encoding="utf-8")
            run_cmd([
                TASK_SCAFFOLD,
                "create",
                "--root",
                root,
                "--type",
                "写作",
                "--topic",
                "章节写作",
                "--assignee",
                "codex",
                "--field",
                f"dependencies=[{first_id}]",
                "--force-new",
            ])
            run_cmd([
                TASK_SCAFFOLD,
                "create",
                "--root",
                root,
                "--type",
                "写作",
                "--topic",
                "阻塞章节",
                "--assignee",
                "codex",
                "--field",
                "dependencies=[999999999]",
                "--force-new",
            ])
            output = run_cmd([FIND_TASK, root, "--topic", "章节", "--available", "--agent", "codex"])
            self.assertIn("章节写作", output)
            self.assertNotIn("阻塞章节", output)

            (root / "config" / "collab.yaml").write_text(
                "project:\n  default_agent: codex\n  claim_policy: claim_pool\n",
                encoding="utf-8",
            )
            run_cmd([TASK_SCAFFOLD, "create", "--root", root, "--type", "研究", "--topic", "池任务", "--field", "assignee=", "--force-new"])
            output = run_cmd([FIND_TASK, root, "--topic", "池任务", "--available", "--agent", "codex"])
            self.assertIn("池任务", output)

    def test_email_trigger_includes_readme_context_without_removed_scripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "collab.yaml").write_text(
                "github:\n  repo_url: https://github.com/example/demo.git\nagents:\n  manus:\n    name: Manus Bot\n    email: manus@agents.local\n    token_env: MANUS_GITHUB_TOKEN\n    trigger_email: manus@example.com\n",
                encoding="utf-8",
            )
            run_cmd([TASK_SCAFFOLD, "create", "--root", root, "--type", "研究", "--topic", "法律AI产品生态调查", "--assignee", "manus", "--force-new"])
            readme = next(root.glob("*-研究-法律AI产品生态调查/README.md"))
            task_id = readme.parent.name.split("-", 1)[0]
            text = readme.read_text(encoding="utf-8")
            text = text.replace("## 目标\n", "## 目标\n\n调研法律 AI 产品。\n")
            text = text.replace("## 验收标准\n", "## 验收标准\n\n- 形成对比表。\n")
            readme.write_text(text, encoding="utf-8")
            output = run_cmd([EMAIL_TRIGGER, root, "--agent", "manus", "--task-id", task_id, "--topic", "法律AI产品生态调查"])
            self.assertIn("调研法律 AI 产品", output)
            self.assertIn("形成对比表", output)
            self.assertIn("python3 scripts/find_task.py", output)
            self.assertNotIn("generate_dashboard", output)

    def test_issues_md_available_filter_uses_issue_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "docs").mkdir()
            (root / "config" / "collab.yaml").write_text(
                "project:\n"
                "  default_agent: codex\n"
                "  issue_file: docs/TASKS.md\n"
                "  status_map:\n"
                "    \"⬜\": pending_confirmation\n"
                "    \"✅\": ready\n"
                "    \"🟢\": created\n"
                "  available_statuses: [ready, created, todo]\n"
                "  dependency_done_statuses: [ready, created, done, resolved, closed]\n"
                "  claim_policy: assigned_only\n"
                "agents:\n"
                "  manus:\n"
                "    name: Manus Bot\n",
                encoding="utf-8",
            )
            (root / "docs" / "TASKS.md").write_text(BOOK_ISSUES, encoding="utf-8")
            output = run_cmd([FIND_TASK, root, "--topic", "Manus", "--available", "--agent", "manus"])
            self.assertNotIn("Issue #9", output)

            (root / "docs" / "TASKS.md").write_text(
                BOOK_ISSUES.replace("### ⬜ Issue #7", "### ✅ Issue #7"),
                encoding="utf-8",
            )
            output = run_cmd([FIND_TASK, root, "--available", "--agent", "manus"])
            self.assertIn("Issue #9", output)
            self.assertIn("触发 Manus 调研任务", output)
            self.assertNotIn("Issue #7", output)

    def test_email_trigger_issue_includes_issues_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "docs").mkdir()
            (root / "config" / "collab.yaml").write_text(
                "github:\n  repo_url: https://github.com/example/book.git\n"
                "project:\n"
                "  issue_file: docs/TASKS.md\n"
                "  status_map:\n"
                "    \"⬜\": pending_confirmation\n"
                "    \"✅\": ready\n"
                "  available_statuses: [ready, created, todo]\n"
                "agents:\n"
                "  manus:\n"
                "    name: Manus Bot\n"
                "    email: manus@agents.local\n"
                "    trigger_email: manus@example.com\n",
                encoding="utf-8",
            )
            (root / "docs" / "TASKS.md").write_text(BOOK_ISSUES, encoding="utf-8")
            output = run_cmd([EMAIL_TRIGGER, root, "--agent", "manus", "--issue", "9"])
            self.assertIn("Issue #9", output)
            self.assertIn("Issue #7", output)
            self.assertIn("法律 AI 产品生态调查", output)
            self.assertIn("MCP 生态", output)
            self.assertIn("docs/TASKS.md", output)
            self.assertNotIn("token", output.lower())
            self.assertNotIn("generate_dashboard", output)

    def test_gh_git_sets_author_and_reports_missing_remote(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "collab.yaml").write_text(
                "project:\n  default_agent: codex\nagents:\n  codex:\n    name: Codex\n    email: codex@agents.local\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (root / "README.md").write_text("# demo\n", encoding="utf-8")
            output = run_cmd([GH_GIT, "commit", "--dest", root, "--agent", "codex", "--message", "docs: init"])
            self.assertIn("GIT_AUTHOR:Codex <codex@agents.local>", output)

            result = subprocess.run(
                [sys.executable, str(GH_GIT), "pr", "--dest", str(root), "--agent", "codex"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("当前仓库没有 Git remote", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
