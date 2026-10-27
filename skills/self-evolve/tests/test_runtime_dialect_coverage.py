"""Regression for the dialect gaps that made real sessions unreadable.

背景（SE-261021-TEACHING）：本机真实来源抽样显示，Claude/WorkBuddy/CodeBuddy
与 QwenWorkCN 的会话大量被判为 unsupported_message_payload——即“加载失败”，
课堂演示与同事自用都读不到内容。三类真实形态：

1. 推理块：助手回合只含 type=thinking 块（提取器按设计丢弃，但白名单此前
   判为未知载荷），Claude/QwenWorkCN 均会出现；
2. 工具行：WorkBuddy/CodeBuddy 的 function_call 行带 message={usage:...}，
   此前被当成对话行判为未知载荷；
3. 顶层 role 方言：WorkBuddy/CodeBuddy 用 type=message + 顶层 role +
   顶层 content 承载对话，此前提取器只认 type in {user,assistant}，导致
   “加载成功但文本为空”。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import dream_sweep as ds  # noqa: E402
import runtime_sessions as adapters  # noqa: E402


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
                    encoding="utf-8")
    return path


class DialectCoverageTests(unittest.TestCase):
    def test_reasoning_only_turn_is_a_known_shape(self) -> None:
        row = {"type": "assistant",
               "message": {"role": "assistant",
                           "content": [{"type": "thinking", "thinking": "内部推理", "signature": "s"}]}}
        self.assertTrue(adapters._content_extractable(row["message"]["content"]))
        self.assertEqual(ds.extract_message_text(row["message"]["content"]), [])

    def test_tool_call_row_with_usage_message_is_not_a_conversation_row(self) -> None:
        rows = [
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "问题"}]},
            {"type": "function_call", "role": "assistant", "name": "read_file",
             "message": {"usage": {"input_tokens": 1}}, "arguments": "{}"},
        ]
        with tempfile.TemporaryDirectory() as raw:
            path = _write_jsonl(Path(raw) / "session.jsonl", rows)
            source = adapters.Source("probe", "claude", Path(raw))
            item = adapters.Session(source=source, path=path, revision=adapters.stamp(path))
            records, label, digest, completeness = adapters.load(item)
        self.assertEqual(label, "claude-code")
        self.assertEqual(completeness, "transcript")
        self.assertTrue(digest)
        self.assertTrue(records)

    def test_top_level_role_dialect_yields_real_text(self) -> None:
        row = {"type": "message", "role": "assistant",
               "content": [{"type": "output_text", "text": "结构已摸清，现在写初稿。"}]}
        self.assertEqual(ds.extract_claude_text(row), ["结构已摸清，现在写初稿。"])
        human = {"type": "message", "role": "user",
                 "content": [{"type": "input_text", "text": "帮我看一下目录"}]}
        self.assertEqual(ds.claude_human_text(human), ["帮我看一下目录"])

    def test_qwenworkcn_is_registered_as_a_claude_dialect_source(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            (home / ".qwenworkcn/projects").mkdir(parents=True)
            specs = adapters.sources(home, [])
        qwen = [s for s in specs if s.runtime == "qwenworkcn"]
        self.assertEqual(len(qwen), 1)
        self.assertEqual(qwen[0].format, "claude")
        self.assertTrue(str(qwen[0].root).endswith(".qwenworkcn/projects"))
        # Runtimes without a verified format stay explicitly unsupported.
        unsupported = {s.runtime for s in specs if s.format == "unsupported"}
        for name in ("qoder", "openclaw", "hermes", "opencode", "cursor", "trae"):
            self.assertIn(name, unsupported)

    def test_adapter_version_is_bumped_so_old_rows_are_reread(self) -> None:
        # v14 separates Codex attachment headers from the real request and
        # rejects turns with unclosed host-context tags as user-turn sources.
        self.assertEqual(adapters.ADAPTER_VERSION, "14")


if __name__ == "__main__":
    unittest.main()
