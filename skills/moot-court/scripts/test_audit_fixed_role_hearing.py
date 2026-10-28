#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import clerk

SCRIPT = Path(__file__).with_name('audit_fixed_role_hearing.py')


def encode(value):
    return json.dumps(value, ensure_ascii=False)


class FixedAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        for name in ('calls', 'role-drafts', 'review-receipts', 'run/events'):
            (self.root / name).mkdir(parents=True)
        self.trace = self.root / 'trace.jsonl'; self.out = self.root.parent / (self.root.name + '-out.json')
        self.sessions = {'judge': 'agent-j', 'plaintiff': 'agent-p', 'defendant': 'agent-d'}
        (self.root / 'calls/role-sessions.json').write_text(encode({'run_id': 'run', 'role_sessions': [{'role': k, 'native_session_id': v} for k, v in self.sessions.items()], 'support_sessions': []}))
        self.events = []; self.spans = []; self.started = set(); self.index = {'schema': 'fixed-role-hearing-audit-v1', 'run_id': 'run', 'drafts': [], 'reviews': [], 'auxiliary_calls': []}
        self.event('init', {'run_id': 'run', 'case_type': 'civil', 'max_turns': 5, 'manifest': {'documents': []}})
        self.add_span('start', 'root', None, 'cli', 'agent')
        for i, role in enumerate(('judge', 'plaintiff', 'defendant'), 1):
            turn = f'T-{i:04}'; draft = {'schema_version': 1, 'run_id': 'run', 'turn_id': turn, 'role': role, 'material_version': 1, 'read_through': 0, 'responds_to': [], 'body': 'SECRET **body** “quoted” ' + role, 'citations': ['E-1', 'E-2']}
            self.event('dispatch', {'turn_id': turn, 'role': role})
            path = f'role-drafts/{turn}.json'; raw = (encode(draft) + '\n').encode(); (self.root / path).write_bytes(raw)
            native_content = ('```json\n' + encode(draft) + '\n```'
                              if role == 'plaintiff' else encode(draft))
            loc = self.agent(role, 'produce', native_content)
            self.index['drafts'].append({'turn_id': turn, 'role': role, 'draft_path': path, **loc})
            if role != 'judge':
                review = encode({'verdict': 'ACCEPT', 'note': 'original “receipt” ' + turn})
                review_payload = json.dumps({'review_request': {'turn_id': turn, 'role': role, 'draft_sha256': hashlib.sha256(raw).hexdigest()},
                                             'body': draft['body'], 'citations': draft['citations']}, ensure_ascii=False, separators=(',', ':'))
                review_loc = self.agent('judge', 'Review ' + review_payload, review)
                receipt = f'review-receipts/{turn}.md'; (self.root / receipt).write_text(review)
                self.index['reviews'].append({'turn_id': turn, 'role': role, 'draft_path': path, 'draft_sha256': hashlib.sha256(raw).hexdigest(), 'judge_session_id': self.sessions['judge'], 'verdict': 'ACCEPT', 'receipt_path': receipt, **review_loc})
            self.event('speech', draft)
        self.event('close', {'status': 'closed', 'reason': 'done'})
        self.add_span('end', 'root', None, 'cli', 'agent')
        self.write()

    def tearDown(self):
        self.out.unlink(missing_ok=True)
        self.tmp.cleanup()

    def event(self, kind, payload):
        core = {'seq': len(self.events)+1, 'kind': kind, 'at': 'now', 'prev_hash': self.events[-1]['hash'] if self.events else None, 'payload': payload}
        self.events.append(dict(core, hash=clerk.digest(core)))

    def add_span(self, direction, sid, parent, name, kind, **values):
        span = {'traceId': 'trace', 'spanId': sid, 'parentId': parent, 'name': name, 'type': kind, **values}
        if direction == 'end': span['status'] = 'ok'
        self.spans.append({'type': 'span_' + direction, 'span': span})

    def agent(self, role, prompt, content):
        n = len(self.started) + sum(1 for e in self.spans if e['type'] == 'span_start' and e['span']['name'] == 'Agent') + 1
        session = self.sessions[role]; args = {'prompt': prompt}
        if session in self.started: args['resume'] = session
        self.started.add(session); sid = f'call-{n}'; cid = f'id-{n}'; parent = f'parent-{n}'; child = f'child-{n}'; gen = f'gen-{n}'
        self.add_span('start', parent, 'root', 'generation', 'generation')
        self.add_span('end', parent, 'root', 'generation', 'generation', toolOutput=encode([{'choices': [{'message': {'tool_calls': [{'id': cid, 'function': {'name': 'Agent', 'arguments': encode(args)}}]}}]}]))
        line = len(self.spans) + 2
        self.add_span('start', sid, 'root', 'Agent', 'function', toolName='Agent')
        self.add_span('start', child, sid, 'general-purpose', 'agent')
        self.add_span('start', gen, child, 'generation', 'generation')
        self.add_span('end', gen, child, 'generation', 'generation', toolOutput=encode([{'choices': [{'message': {'content': content}}]}]))
        self.add_span('end', child, sid, 'general-purpose', 'agent')
        self.add_span('end', sid, 'root', 'Agent', 'function', toolName='Agent', toolInput=encode(args), toolOutput=encode({'content': content, 'subAgent': {'sessionId': session, 'descriptor': {'sessionId': session, 'role': 'general-purpose', 'parentToolCallId': cid, 'parentSessionId': 'parent', 'rootSessionId': 'parent'}}}))
        return {'trace_index': 1, 'trace_line': line}

    def write(self):
        for i, event in enumerate(self.events, 1): (self.root / f'run/events/{i:06}.json').write_text(encode(event))
        (self.root / 'review-receipts/index.json').write_text(encode(self.index))
        events = [{'type': 'trace_start', 'trace': {'traceId': 'trace', 'status': 'running'}}] + self.spans + [{'type': 'trace_end', 'trace': {'traceId': 'trace', 'status': 'ok'}}]
        self.trace.write_text(''.join(encode(e) + '\n' for e in events))

    def run_audit(self, output=None, expected_root='parent', trace=None):
        command = [sys.executable, '-B', str(SCRIPT), '--hearing', str(self.root), '--trace', str(trace or self.trace)]
        if expected_root is not None:
            command += ['--expected-root-session', expected_root]
        command += ['--output', str(output or self.out)]
        p = subprocess.run(command, capture_output=True, text=True)
        return p.returncode

    def test_output_inside_hearing_and_unknown_index_field_rejected(self):
        inside = self.root / 'run/events/000099.json'
        self.assertEqual(self.run_audit(inside), 2); self.assertFalse(inside.exists())
        self.index['extra'] = True; self.write()
        self.assertEqual(self.run_audit(), 2)

    def alter_review_prompt(self, prompt):
        line = self.index['reviews'][0]['trace_line']; event = self.spans[line - 2]; sid = event['span']['spanId']
        for e in self.spans:
            s = e['span']
            if s['spanId'] == sid and e['type'] == 'span_end':
                args = json.loads(s['toolInput']); args['prompt'] = prompt; s['toolInput'] = encode(args)
                call_id = json.loads(s['toolOutput'])['subAgent']['descriptor']['parentToolCallId']
                for parent in self.spans:
                    if parent['type'] == 'span_end' and parent['span'].get('name') == 'generation' and parent['span'].get('parentId') == 'root':
                        obj = json.loads(parent['span']['toolOutput']); calls = obj[0]['choices'][0]['message']['tool_calls']
                        if calls[0]['id'] == call_id: calls[0]['function']['arguments'] = encode(args); parent['span']['toolOutput'] = encode(obj)
        self.write()

    def test_pass_private_report_and_resume(self):
        self.assertEqual(self.run_audit(), 0)
        self.assertNotIn('SECRET', self.out.read_text()); self.assertEqual(self.out.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(self.out.read_text())['session_count'], 3)

    def test_summary_rejected(self):
        self.alter_review_prompt('Summary E-1 E-2')
        self.assertEqual(self.run_audit(), 1)

    def test_reordered_citations_rejected(self):
        draft = json.loads((self.root / self.index['drafts'][1]['draft_path']).read_text())
        prompt = 'Review ' + json.dumps({'review_request': {'turn_id': draft['turn_id'], 'role': draft['role'], 'draft_sha256': '0' * 64},
                                         'body': draft['body'], 'citations': list(reversed(draft['citations']))}, ensure_ascii=False, separators=(',', ':'))
        self.alter_review_prompt(prompt)
        self.assertEqual(self.run_audit(), 1)

    def test_native_draft_format_difference(self):
        path = self.root / self.index['drafts'][1]['draft_path']; path.write_text(path.read_text().replace('**body**', 'body'))
        self.assertEqual(self.run_audit(), 1)

    def test_speech_difference(self):
        self.events[-4]['payload']['body'] += '!'
        for i, event in enumerate(self.events):
            event['prev_hash'] = self.events[i-1]['hash'] if i else None
            event['hash'] = clerk.digest({k:v for k,v in event.items() if k != 'hash'})
        self.write(); self.assertEqual(self.run_audit(), 1)

    def test_accepted_draft_must_match_formal_draft(self):
        review = self.index['reviews'][0]
        draft = json.loads((self.root / review['draft_path']).read_text())
        draft['body'] += ' altered'
        path = self.root / 'role-drafts/other.json'
        path.write_text(encode(draft))
        review['draft_path'] = 'role-drafts/other.json'
        review['draft_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.write(); self.assertEqual(self.run_audit(), 1)

    def test_missing_trace_location_and_resume_mismatch(self):
        self.index['reviews'][0]['trace_line'] = 999999
        self.write(); self.assertEqual(self.run_audit(), 3); self.out.unlink()
        self.index['reviews'][0]['trace_line'] = next(
            i + 2 for i, e in enumerate(self.spans)
            if e['type'] == 'span_start' and e['span']['spanId'].startswith('call-')
            and i + 2 > self.index['drafts'][1]['trace_line'])
        self.alter_review_prompt('irrelevant')
        # A missing resume is a separate observable violation; update both copies.
        for e in self.spans:
            if e['type'] == 'span_end' and e['span']['name'] == 'Agent':
                data = json.loads(e['span']['toolInput'])
                if 'resume' in data:
                    data['resume'] = 'wrong-session'; e['span']['toolInput'] = encode(data)
                    tool_id = json.loads(e['span']['toolOutput'])['subAgent']['descriptor']['parentToolCallId']
                    for parent in self.spans:
                        if parent['type'] == 'span_end' and parent['span'].get('name') == 'generation' and parent['span'].get('parentId') == 'root':
                            obj = json.loads(parent['span']['toolOutput'])
                            call = obj[0]['choices'][0]['message']['tool_calls'][0]
                            if call['id'] == tool_id:
                                call['function']['arguments'] = encode(data); parent['span']['toolOutput'] = encode(obj)
                    break
        self.write(); self.assertEqual(self.run_audit(), 1)

    def test_receipt_quote_and_wrong_session_and_short_digest(self):
        receipt = self.root / self.index['reviews'][0]['receipt_path']; receipt.write_text(receipt.read_text().replace('“', '"'))
        self.assertEqual(self.run_audit(), 1); self.out.unlink()
        receipt.write_text(encode({'verdict': 'ACCEPT', 'note': 'original “receipt” T-0002'})); self.index['reviews'][0]['judge_session_id'] = 'agent-p'; self.write()
        self.assertEqual(self.run_audit(), 1); self.out.unlink()
        self.index['reviews'][0]['judge_session_id'] = 'agent-j'; self.index['reviews'][0]['draft_sha256'] = '123456'; self.write()
        self.assertEqual(self.run_audit(), 1)

    def test_interrupted_and_truncated(self):
        text = self.trace.read_text(); self.trace.write_text(text.replace('"status": "ok"}}\n', '"status": "error"}}\n'))
        self.assertEqual(self.run_audit(), 3); self.out.unlink()
        self.trace.write_text(text[:-10]); self.assertEqual(self.run_audit(), 3)

    def test_unindexed_review_and_external_root_binding(self):
        saved = list(self.spans)
        end = self.spans.pop()
        self.agent('judge', 'hidden review', encode({'verdict': 'RETURN', 'reason': 'missing from index'}))
        self.spans.append(end); self.write()
        self.assertEqual(self.run_audit(), 1); self.out.unlink()
        # Restore a passing fixture before checking the independently supplied root.
        self.spans = saved; self.write(); self.assertEqual(self.run_audit(), 0); self.out.unlink()
        self.assertEqual(self.run_audit(expected_root=None), 3); self.out.unlink()
        self.assertEqual(self.run_audit(expected_root='other-root'), 3)

    def test_every_call_classified_and_marker_scanned_across_sessions(self):
        saved = list(self.spans)
        end = self.spans.pop()
        self.agent('judge', '请审阅此稿', '退回：理由不足，请补充证据。')
        self.spans.append(end); self.write()
        self.assertEqual(self.run_audit(), 1); self.out.unlink()
        self.spans = saved
        end = self.spans.pop()
        location = self.agent('judge', '庭前准备备忘', 'memo')
        self.spans.append(end)
        self.index['auxiliary_calls'].append({'trace_index': 1, 'trace_line': location['trace_line'],
                                              'session_id': 'agent-j', 'purpose': '庭前准备'})
        self.write(); self.assertEqual(self.run_audit(), 0); self.out.unlink()
        self.spans = saved; self.index['auxiliary_calls'] = []
        self.sessions['support'] = 'agent-s'
        (self.root / 'calls/role-sessions.json').write_text(encode({'run_id': 'run', 'role_sessions': [{'role': k, 'native_session_id': v} for k, v in self.sessions.items() if k != 'support'], 'support_sessions': [{'role': 'support', 'native_session_id': 'agent-s'}]}))
        end = self.spans.pop()
        self.agent('support', '{"review_request":{"turn_id":"T-9999"}}', encode({'verdict': 'RETURN'}))
        self.spans.append(end); self.write()
        self.assertEqual(self.run_audit(), 1)

    def test_duplicate_and_overlapping_trace(self):
        self.assertEqual(self.run_audit(), 0); self.out.unlink()
        duplicate = [sys.executable, '-B', str(SCRIPT), '--hearing', str(self.root), '--trace', str(self.trace), '--trace', str(self.trace), '--expected-root-session', 'parent', '--output', str(self.out)]
        self.assertEqual(subprocess.run(duplicate, capture_output=True, text=True).returncode, 2)
        self.out.unlink()
        lines = self.trace.read_text().splitlines(); first = json.loads(lines[0]); first['trace']['name'] = 'copy'
        same_id = self.root / 'trace-same-id.jsonl'; same_id.write_text(json.dumps(first) + '\n' + '\n'.join(lines[1:]) + '\n')
        overlap = [sys.executable, '-B', str(SCRIPT), '--hearing', str(self.root), '--trace', str(self.trace), '--trace', str(same_id), '--expected-root-session', 'parent', '--output', str(self.out)]
        self.assertEqual(subprocess.run(overlap, capture_output=True, text=True).returncode, 3)

    def test_repeated_toolcall_id_in_separate_traces_and_root_binding(self):
        self.sessions['support'] = 'agent-s'
        (self.root / 'calls/role-sessions.json').write_text(encode({'run_id': 'run', 'role_sessions': [{'role': k, 'native_session_id': v} for k, v in self.sessions.items() if k != 'support'], 'support_sessions': [{'role': 'support', 'native_session_id': self.sessions['support']}]}))
        original_spans = list(self.spans); original_started = set(self.started)
        self.spans = []; self.started = set()
        self.add_span('start', 'root', None, 'cli', 'agent')
        support_location = self.agent('support', 'support only', 'ok')
        self.add_span('end', 'root', None, 'cli', 'agent')
        self.index['auxiliary_calls'].append({'trace_index': 2, 'trace_line': support_location['trace_line'],
                                              'session_id': 'agent-s', 'purpose': '独立支持复核'})
        (self.root / 'review-receipts/index.json').write_text(encode(self.index))
        support_spans = self.spans; self.trace2 = self.root / 'trace2.jsonl'
        for event in support_spans:
            event['span']['traceId'] = 'trace2'
        self.trace2.write_text(''.join(encode(e) + '\n' for e in [{'type': 'trace_start', 'trace': {'traceId': 'trace2', 'status': 'running'}}] + support_spans + [{'type': 'trace_end', 'trace': {'traceId': 'trace2', 'status': 'ok'}}]))
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), '--hearing', str(self.root), '--trace', str(self.trace), '--trace', str(self.trace2), '--expected-root-session', 'parent', '--output', str(self.out)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.out.unlink()
        # Tool-call IDs only have to be unique within one trace file.
        first_id = 'id-1'
        for event in support_spans:
            if event['type'] == 'span_end' and event['span'].get('name') == 'Agent':
                output = json.loads(event['span']['toolOutput']); output['subAgent']['descriptor']['parentToolCallId'] = first_id; event['span']['toolOutput'] = encode(output)
            if event['type'] == 'span_end' and event['span'].get('name') == 'generation' and event['span'].get('parentId') == 'root':
                payload = json.loads(event['span']['toolOutput']); payload[0]['choices'][0]['message']['tool_calls'][0]['id'] = first_id; event['span']['toolOutput'] = encode(payload)
        self.trace2.write_text(''.join(encode(e) + '\n' for e in [{'type': 'trace_start', 'trace': {'traceId': 'trace2', 'status': 'running'}}] + support_spans + [{'type': 'trace_end', 'trace': {'traceId': 'trace2', 'status': 'ok'}}]))
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), '--hearing', str(self.root), '--trace', str(self.trace), '--trace', str(self.trace2), '--expected-root-session', 'parent', '--output', str(self.out)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.out.unlink()
        for event in support_spans:
            if event['type'] == 'span_end' and event['span'].get('name') == 'Agent':
                output = json.loads(event['span']['toolOutput']); output['subAgent']['descriptor']['rootSessionId'] = 'other-root'; event['span']['toolOutput'] = encode(output)
        self.trace2.write_text(''.join(encode(e) + '\n' for e in [{'type': 'trace_start', 'trace': {'traceId': 'trace2', 'status': 'running'}}] + support_spans + [{'type': 'trace_end', 'trace': {'traceId': 'trace2', 'status': 'ok'}}]))
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), '--hearing', str(self.root), '--trace', str(self.trace), '--trace', str(self.trace2), '--expected-root-session', 'parent', '--output', str(self.out)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)

    def test_existing_and_hardlink_output(self):
        self.out.write_text('preserve'); self.assertEqual(self.run_audit(), 2); self.assertEqual(self.out.read_text(), 'preserve')
        source = self.root / self.index['drafts'][0]['draft_path']; hard = self.root / 'hard'; os.link(source, hard); original = source.read_bytes()
        self.assertEqual(self.run_audit(hard), 2); self.assertEqual(source.read_bytes(), original)

    def test_real_opt_in(self):
        if not os.environ.get('MC_FIXED_ROLE_REAL'): self.skipTest('set MC_FIXED_ROLE_REAL=1 for archived interrupted run')
        for name in ('MC_FIXED_ROLE_HEARING', 'MC_FIXED_ROLE_TRACES', 'MC_FIXED_ROLE_ROOT_ID'):
            self.assertTrue(os.environ.get(name), 'real coverage requires ' + name)
        traces = json.loads(os.environ['MC_FIXED_ROLE_TRACES'])
        self.assertIsInstance(traces, list)
        self.assertTrue(traces)
        self.assertTrue(all(isinstance(path, str) and Path(path).is_file() for path in traces))
        cmd = [sys.executable, '-B', str(SCRIPT), '--hearing', os.environ['MC_FIXED_ROLE_HEARING']]
        for trace in traces:
            cmd += ['--trace', trace]
        cmd += ['--expected-root-session', os.environ['MC_FIXED_ROLE_ROOT_ID'], '--output', str(self.out)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)


if __name__ == '__main__': unittest.main()
