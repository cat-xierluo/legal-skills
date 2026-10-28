#!/usr/bin/env python3
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('audit_workbuddy_trace.py')


class AuditCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'calls').mkdir()
        self.packet = self.root / 'calls/T-0001-packet.json'
        self.submission = self.root / 'calls/T-0001-submission.json'
        self.trace = self.root / 'trace.jsonl'
        self.index = self.root / 'calls/index.json'
        self.policy = self.root / 'policy.json'
        self.report = self.root / 'report.json'
        self.body = {'turn_id': 'T-0001', 'role': 'judge', 'run_id': 'run-1', 'body': 'SECRET BODY', 'citations': []}
        self.packet.write_text(json.dumps({'assignment': {'turn_id': 'T-0001', 'role': 'judge', 'run_id': 'run-1'}}))
        self.submission.write_text(json.dumps(self.body))
        self.idx = {'schema': 'moot-court call index v1', 'run_id': 'run-1', 'turns': [{'turn_id': 'T-0001', 'role': 'judge', 'agent_id': 'agent-one', 'packet': 'calls/T-0001-packet.json', 'submission': 'calls/T-0001-submission.json'}]}
        self.pol = {'schema': 'workbuddy-audit-policy-v1', 'expected_root_session_id': 'parent', 'sessions': {'agent-one': {'tools': ['Read'], 'read_paths': [str(self.packet)]}}}
        self.events = []
        self.span('agent-call', 'root', 'Agent', 'function', toolName='Agent', toolInput=json.dumps({'prompt': 'original task'}), toolOutput=json.dumps({'content': json.dumps(self.body), 'subAgent': {'sessionId': 'agent-one', 'descriptor': {'sessionId': 'agent-one', 'role': 'general-purpose', 'parentToolCallId': 'call-1', 'parentSessionId': 'parent', 'rootSessionId': 'parent'}}}))
        self.span('child', 'agent-call', 'general-purpose', 'agent')
        self.span('gen', 'child', 'generation', 'generation', toolOutput=json.dumps([{'id': 'completion-not-session', 'choices': [{'message': {'content': json.dumps(self.body)}}]}]))
        self.span('read', 'child', 'Read', 'function', toolName='Read', toolInput=json.dumps({'file_path': str(self.packet)}))
        self.span('internal', 'child', 'mcp_tools', 'custom')
        self.span('root', None, 'cli', 'agent')
        self.events.sort(key=lambda e: 0 if e['type'] == 'span_start' else 1)
        parent = {'spanId': 'parent-gen', 'parentId': 'root', 'name': 'generation', 'type': 'generation'}
        output = [{'choices': [{'message': {'tool_calls': [
            {'id': 'call-1', 'function': {'name': 'Agent', 'arguments': json.dumps({'prompt': 'original task'})}},
            {'id': 'call-first', 'function': {'name': 'Agent', 'arguments': json.dumps({'prompt': 'first task'})}}
        ]}}]}]
        self.events[0:0] = [{'type': 'span_start', 'span': dict(parent)},
                            {'type': 'span_end', 'span': dict(parent, status='ok', toolOutput=json.dumps(output))}]
        order = [('root', 'span_start'), ('parent-gen', 'span_start'), ('parent-gen', 'span_end'),
                 ('agent-call', 'span_start'), ('child', 'span_start'),
                 ('gen', 'span_start'), ('gen', 'span_end'),
                 ('read', 'span_start'), ('read', 'span_end'),
                 ('internal', 'span_start'), ('internal', 'span_end'),
                 ('child', 'span_end'), ('agent-call', 'span_end'), ('root', 'span_end')]
        self.events.sort(key=lambda e: order.index((e['span']['spanId'], e['type'])))

    def tearDown(self):
        self.tmp.cleanup()

    def span(self, sid, parent, name, kind, **end):
        base = {'spanId': sid, 'parentId': parent, 'name': name, 'type': kind}
        self.events.append({'type': 'span_start', 'span': dict(base)})
        self.events.append({'type': 'span_end', 'span': dict(base, status='ok', **end)})

    def run_cli(self, output=None):
        events = [{'type': 'trace_start', 'trace': {'traceId': 'trace-1', 'status': 'running'}}]
        for event in self.events:
            event = json.loads(json.dumps(event))
            if event['type'] in ('span_start', 'span_end'):
                event['span'].setdefault('traceId', 'trace-1')
            events.append(event)
        events.append({'type': 'trace_end', 'trace': {'traceId': 'trace-1', 'status': 'ok'}})
        self.trace.write_text(''.join(json.dumps(x) + '\n' for x in events))
        self.index.write_text(json.dumps(self.idx)); self.policy.write_text(json.dumps(self.pol))
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), '--trace', str(self.trace), '--calls-index', str(self.index), '--policy', str(self.policy), '--output', str(output or self.report)], capture_output=True, text=True)
        return result

    def set_read(self, path):
        for e in self.events:
            if e['span']['spanId'] == 'read' and e['type'] == 'span_end':
                e['span']['toolInput'] = json.dumps({'file_path': str(path)})

    def test_pass_and_no_leak(self):
        result = self.run_cli(); self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(self.report.read_text()); self.assertEqual(report['call_count'], 1)
        self.assertEqual(report['turns'][0]['submission_match'], True)
        self.assertNotIn('SECRET BODY', self.report.read_text())
        self.assertNotIn(str(self.packet), self.report.read_text())
        self.assertEqual(self.report.stat().st_mode & 0o777, 0o600)

    def test_unapproved_reads(self):
        for i, path in enumerate([self.root / 'events/x', self.root / 'calls/other-packet.json', '../packet']):
            self.set_read(path); result = self.run_cli(self.root / ('r' + str(i)))
            self.assertEqual(result.returncode, 1)

    def test_symlink_to_unapproved_and_allowed(self):
        other = self.root / 'other'; other.write_text('x')
        link = self.root / 'link'; link.symlink_to(other)
        self.set_read(link); self.assertEqual(self.run_cli().returncode, 1)
        self.report.unlink(); self.pol['sessions']['agent-one']['read_paths'] = [str(other)]
        self.assertEqual(self.run_cli().returncode, 1)
        self.report.unlink(); self.pol['sessions']['agent-one']['read_paths'] = [str(link)]
        self.assertEqual(self.run_cli().returncode, 0)

    def test_unknown_tools_and_prompt(self):
        for e in self.events:
            if e['span']['spanId'] == 'read':
                e['span']['name'] = 'Bash'; e['span']['toolName'] = 'Bash'
            if e['span']['spanId'] == 'parent-gen' and e['type'] == 'span_start':
                e['span']['toolInput'] = json.dumps({'prompt': 'Write Bash Read SECRET'})
        self.assertEqual(self.run_cli().returncode, 1)
        report = json.loads(self.report.read_text()); self.assertEqual([x['name'] for x in report['calls'][0]['tools']], ['Bash'])
        self.assertNotIn('SECRET', self.report.read_text())

    def test_bad_json_and_unfinished_and_conflict(self):
        self.events.pop(next(i for i, e in enumerate(self.events) if e['span']['spanId'] == 'read' and e['type'] == 'span_end'))
        self.assertEqual(self.run_cli().returncode, 3)
        self.report.unlink()
        for e in self.events:
            if e['span']['spanId'] == 'child' and e['type'] == 'span_end': e['span']['name'] = 'other'
        self.assertEqual(self.run_cli().returncode, 2)
        self.report.unlink()
        self.run_cli()
        self.report.unlink(); self.trace.write_text('{bad\n')
        p = subprocess.run([sys.executable, str(SCRIPT), '--trace', str(self.trace), '--calls-index', str(self.index), '--policy', str(self.policy), '--output', str(self.report)], capture_output=True)
        self.assertEqual(p.returncode, 2)

    def test_missing_policy(self):
        self.pol['sessions'] = {}
        self.assertEqual(self.run_cli().returncode, 3)

    def test_descriptor_root_binding(self):
        for e in self.events:
            if e['span']['spanId'] == 'agent-call' and e['type'] == 'span_end':
                out = json.loads(e['span']['toolOutput'])
                out['subAgent']['descriptor']['parentSessionId'] = 'other'
                e['span']['toolOutput'] = json.dumps(out)
        self.assertEqual(self.run_cli().returncode, 3)

    def test_parent_arguments_mismatch_or_missing(self):
        for e in self.events:
            if e['span']['spanId'] == 'parent-gen' and e['type'] == 'span_end':
                out = json.loads(e['span']['toolOutput'])
                call = out[0]['choices'][0]['message']['tool_calls'][0]
                call['function']['arguments'] = json.dumps({'prompt': 'different'})
                e['span']['toolOutput'] = json.dumps(out)
        self.assertEqual(self.run_cli().returncode, 1)
        self.report.unlink()
        del call['function']['arguments']
        e_parent = next(e for e in self.events if e['span']['spanId'] == 'parent-gen' and e['type'] == 'span_end')
        e_parent['span']['toolOutput'] = json.dumps(out)
        self.assertEqual(self.run_cli().returncode, 3)

    def test_nested_agent_generation_not_attributed(self):
        for e in self.events:
            if e['span']['spanId'] == 'gen':
                e['span']['parentId'] = 'other-agent'
        nested = {'spanId': 'other-agent', 'parentId': 'child', 'name': 'unrelated-agent', 'type': 'agent'}
        start = next(i for i, e in enumerate(self.events) if e['span']['spanId'] == 'gen' and e['type'] == 'span_start')
        end = next(i for i, e in enumerate(self.events) if e['span']['spanId'] == 'gen' and e['type'] == 'span_end')
        self.events.insert(end + 1, {'type': 'span_end', 'span': dict(nested, status='ok')})
        self.events.insert(start, {'type': 'span_start', 'span': dict(nested)})
        self.assertEqual(self.run_cli().returncode, 3)

    def test_trace_boundary_and_missing_end_status(self):
        for e in self.events:
            if e['span']['spanId'] == 'child' and e['type'] == 'span_end':
                del e['span']['status']
        self.assertEqual(self.run_cli().returncode, 3)
        self.report.unlink()
        self.events.append({'type': 'trace_end', 'span': {'bad': 'conflict'}, 'error': 'fatal'})
        self.assertNotEqual(self.run_cli().returncode, 0)

    def test_forged_submission(self):
        self.submission.write_text(json.dumps(dict(self.body, body='forged')))
        self.assertEqual(self.run_cli().returncode, 1)

    def test_main_generated_draft_is_not_child(self):
        for e in self.events:
            if e['span']['spanId'] == 'gen': e['span']['parentId'] = 'root'
        self.assertEqual(self.run_cli().returncode, 3)

    def test_first_draft_is_separate_session(self):
        self.idx['turns'][0]['agent_id_first_draft'] = 'agent-first'
        self.pol['sessions']['agent-first'] = {'tools': [], 'read_paths': []}
        out = {'content': json.dumps({'body': self.body['body']}), 'subAgent': {'sessionId': 'agent-first', 'descriptor': {'sessionId': 'agent-first', 'role': 'general-purpose', 'parentToolCallId': 'call-first', 'parentSessionId': 'parent', 'rootSessionId': 'parent'}}}
        self.span('first-call', 'root', 'Agent', 'function', toolName='Agent', toolInput=json.dumps({'prompt': 'first task'}), toolOutput=json.dumps(out))
        self.span('first-child', 'first-call', 'general-purpose', 'agent')
        self.span('first-gen', 'first-child', 'generation', 'generation', toolOutput=json.dumps([{'choices': [{'message': {'content': out['content']}}]}]))
        events = self.events[-6:]
        self.events[-6:] = []
        events.sort(key=lambda e: [('first-call', 'span_start'), ('first-child', 'span_start'),
                                   ('first-gen', 'span_start'), ('first-gen', 'span_end'),
                                   ('first-child', 'span_end'), ('first-call', 'span_end')].index((e['span']['spanId'], e['type'])))
        self.events[-1:-1] = events
        self.assertEqual(self.run_cli().returncode, 0)
        self.assertEqual(json.loads(self.report.read_text())['session_count'], 2)

    def test_reject_existing_output_and_source(self):
        self.report.write_text('unchanged')
        self.assertEqual(self.run_cli().returncode, 2); self.assertEqual(self.report.read_text(), 'unchanged')
        original = self.packet.read_bytes()
        self.assertEqual(self.run_cli(self.packet).returncode, 2); self.assertEqual(self.packet.read_bytes(), original)
        link = self.root / 'out-link'; link.symlink_to(self.packet)
        self.assertEqual(self.run_cli(link).returncode, 2); self.assertEqual(self.packet.read_bytes(), original)
        hard = self.root / 'out-hard'; os.link(self.packet, hard)
        self.assertEqual(self.run_cli(hard).returncode, 2); self.assertEqual(self.packet.read_bytes(), original)

    def test_real_opt_in(self):
        trace = os.environ.get('MC_WORKBUDDY_TRACE')
        policy = os.environ.get('MC_WORKBUDDY_POLICY')
        index = os.environ.get('MC_WORKBUDDY_INDEX')
        if not (trace and policy and index):
            self.skipTest('real trace, index and independently prepared policy not supplied')
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), '--trace', trace, '--calls-index', index, '--policy', policy, '--output', str(self.report)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(self.report.read_text())
        self.assertEqual((report['call_count'], report['formal_submission_count']), (18, 14))


if __name__ == '__main__':
    unittest.main()
