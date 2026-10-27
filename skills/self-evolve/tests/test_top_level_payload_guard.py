"""Synthetic regression: known envelopes must not hide unknown payloads."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import runtime_sessions as adapters
import dream_sweep


class TopLevelPayloadGuardTests(unittest.TestCase):
    def load_rows(self, rows):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / 'synthetic.jsonl'
            path.write_text('\n'.join(json.dumps(row) for row in rows) + '\n')
            session = adapters.Session(adapters.Source('synthetic', 'claude', Path(raw)),
                                       path, adapters.stamp(path))
            return adapters.load(session)

    def test_unknown_payload_is_rejected_for_both_roles(self):
        for role in ('user', 'assistant'):
            for payload in ([{'type': 'future_text', 'body': 'correction'}], 42, {'future': 'text'}):
                with self.subTest(role=role, payload=payload):
                    with self.assertRaisesRegex(ValueError, 'unsupported_message_payload'):
                        self.load_rows([{'type': 'message', 'role': role, 'content': payload}])

    def test_valid_text_does_not_hide_an_unknown_row(self):
        with self.assertRaisesRegex(ValueError, 'unsupported_message_payload'):
            self.load_rows([
                {'type': 'message', 'role': 'user', 'content': 'known text'},
                {'type': 'message', 'role': 'assistant', 'content': [{'type': 'future_text'}]},
            ])

    def test_usage_only_metadata_remains_accepted(self):
        self.load_rows([{'type': 'message', 'role': 'assistant',
                         'message': {'usage': {'input_tokens': 1}}}])

    def test_usage_cannot_hide_unknown_conversation_content(self):
        with self.assertRaisesRegex(ValueError, 'unsupported_message_payload'):
            self.load_rows([{'type': 'message', 'role': 'assistant',
                             'message': {'usage': {}, 'content': [{'type': 'future_text'}]}}])

    def test_known_top_level_and_nested_messages_keep_their_text(self):
        for payload in ({'content': 'known'}, {'message': 'known'},
                        {'message': {'content': 'known'}}):
            with self.subTest(payload=payload):
                row = {'type': 'message', 'role': 'user', **payload}
                self.load_rows([row])
                self.assertEqual(dream_sweep.claude_human_text(row), ['known'])


if __name__ == '__main__':
    unittest.main()
