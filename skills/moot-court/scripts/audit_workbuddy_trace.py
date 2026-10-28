#!/usr/bin/env python3
"""Passive audit of the observed WorkBuddy native span trace.

Policy: {"schema":"workbuddy-audit-policy-v1", "expected_root_session_id":"ID", "sessions":
  {"agent-ID":{"tools":["Read"],"read_paths":["/absolute/file"]}}}
An empty tools/read_paths pair means no tools. The report never includes content.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path


class AuditError(Exception):
    def __init__(self, code, reason):
        self.code, self.reason = code, reason


def fail(code, reason):
    raise AuditError(code, reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    try:
        return Path(path).read_bytes()
    except OSError:
        fail(2, 'input_unreadable')


def load(data):
    try:
        def pairs(items):
            result = {}
            for k, v in items:
                if k in result:
                    raise ValueError('duplicate key')
                result[k] = v
            return result
        return json.loads(data, object_pairs_hook=pairs)
    except (ValueError, UnicodeError, TypeError):
        fail(2, 'invalid_json')


def ident(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', value):
        fail(2, 'invalid_identifier')
    return value


def absolute(path):
    return isinstance(path, str) and os.path.isabs(path) and '..' not in Path(path).parts and '\x00' not in path


def parse_trace(data):
    spans = {}
    lines = data.splitlines()
    trace_id = None
    trace_ended = False
    for line, raw in enumerate(lines, 1):
        event = load(raw)
        if not isinstance(event, dict):
            fail(2, 'invalid_event')
        kind = event.get('type')
        if kind in ('trace_start', 'trace_end'):
            boundary = event.get('trace')
            if not isinstance(boundary, dict) or event.get('error') is not None or 'span' in event or boundary.get('error') is not None:
                fail(2, 'invalid_trace_boundary')
            boundary_id = ident(boundary.get('traceId'))
            if kind == 'trace_start':
                if line != 1 or trace_id is not None or boundary.get('status') != 'running':
                    fail(2, 'invalid_trace_start')
                trace_id = boundary_id
            else:
                if line != len(lines) or trace_id is None or boundary_id != trace_id or trace_ended:
                    fail(2, 'invalid_trace_end')
                if boundary.get('status') != 'ok' or boundary.get('error') is not None:
                    fail(3, 'unsuccessful_trace_end')
                summary = event.get('summary')
                if summary is not None and (not isinstance(summary, dict) or summary.get('traceId') != trace_id or summary.get('status') != 'ok'):
                    fail(2, 'invalid_trace_summary')
                trace_ended = True
            continue
        if kind not in ('span_start', 'span_end') or not isinstance(event.get('span'), dict):
            fail(2, 'invalid_event')
        s = event['span']; sid = ident(s.get('spanId'))
        if trace_id is None or s.get('traceId') != trace_id:
            fail(2, 'trace_id_mismatch')
        if kind == 'span_start':
            if sid in spans:
                fail(2, 'duplicate_span_start')
            spans[sid] = {'start': s, 'start_line': line}
        else:
            if sid not in spans or 'end' in spans[sid]:
                fail(2, 'orphan_or_duplicate_span_end')
            start = spans[sid]['start']
            for key in ('spanId', 'parentId', 'name', 'type', 'traceId', 'toolName'):
                if start.get(key) is not None and s.get(key) is not None and start[key] != s[key]:
                    fail(2, 'conflicting_span_identity')
            for key in ('toolInput', 'toolOutput'):
                if start.get(key) not in (None, '') and s.get(key) not in (None, '') and start[key] != s[key]:
                    fail(2, 'conflicting_span_payload')
            spans[sid]['end'] = s; spans[sid]['end_line'] = line
    if trace_id is None or not trace_ended:
        fail(3, 'missing_trace_boundary')
    if any('end' not in s for s in spans.values()):
        fail(3, 'unfinished_span')
    for sid, entry in spans.items():
        entry['span'] = dict(entry['start'])
        entry['span'].update({k: v for k, v in entry['end'].items() if v is not None and v != ''})
        parent = entry['span'].get('parentId')
        if parent is not None and parent not in spans:
            fail(3, 'missing_parent_span')
        if entry['end'].get('status') != 'ok':
            fail(3, 'unsuccessful_span')
        seen = {sid}
        while parent is not None:
            if parent in seen:
                fail(2, 'cyclic_span_parent')
            seen.add(parent)
            parent = spans[parent]['span'].get('parentId') if 'span' in spans[parent] else spans[parent]['start'].get('parentId')
    return spans


def json_string(value):
    if not isinstance(value, str):
        fail(2, 'expected_json_string')
    return load(value)


def valid_policy(policy):
    if not isinstance(policy, dict) or policy.get('schema') != 'workbuddy-audit-policy-v1' or not isinstance(policy.get('sessions'), dict):
        fail(2, 'invalid_policy')
    ident(policy.get('expected_root_session_id'))
    for session, rule in policy['sessions'].items():
        ident(session)
        if not isinstance(rule, dict) or set(rule) != {'tools', 'read_paths'}:
            fail(2, 'invalid_policy_rule')
        tools, paths = rule['tools'], rule['read_paths']
        if not isinstance(tools, list) or len(tools) != len(set(tools)) or any(x != 'Read' for x in tools):
            fail(2, 'invalid_policy_tools')
        if not isinstance(paths, list) or any(not absolute(p) for p in paths) or len(paths) != len(set(paths)):
            fail(2, 'invalid_policy_paths')
        if paths and 'Read' not in tools:
            fail(2, 'inconsistent_policy')
        for p in paths:
            if Path(p).is_dir():
                fail(2, 'policy_path_is_directory')


def audit(trace, index, policy, index_path):
    valid_policy(policy)
    if not isinstance(index, dict) or index.get('schema') != 'moot-court call index v1' or not isinstance(index.get('turns'), list) or not index['turns']:
        fail(2, 'invalid_calls_index')
    spans = parse_trace(trace)
    sessions, calls, violations = {}, [], []
    for sid, e in spans.items():
        s = e['span']
        if s.get('type') != 'function' or s.get('name') != 'Agent':
            continue
        if s.get('toolName') != 'Agent':
            fail(2, 'agent_tool_identity')
        obj = json_string(s.get('toolOutput'))
        try:
            sub = obj['subAgent']; session = ident(sub['sessionId']); descriptor = sub['descriptor']
            if descriptor['sessionId'] != session or descriptor['role'] != 'general-purpose':
                fail(2, 'descriptor_conflict')
            toolcall = ident(descriptor['parentToolCallId'])
            parent_session = ident(descriptor['parentSessionId'])
            root_session = ident(descriptor['rootSessionId'])
            if parent_session != policy['expected_root_session_id'] or root_session != policy['expected_root_session_id']:
                fail(3, 'descriptor_root_mismatch')
        except (KeyError, TypeError):
            fail(3, 'missing_descriptor')
        if session in sessions or any(x['tool_call_id'] == toolcall for x in calls):
            fail(2, 'duplicate_session_or_toolcall')
        parent_generations = []
        for gi, ge in spans.items():
            gs = ge['span']
            if gs.get('type') != 'generation' or gs.get('parentId') != s.get('parentId'):
                continue
            try:
                output = json_string(gs.get('toolOutput'))
                for completion in output:
                    for choice in completion.get('choices', []):
                        for call in choice.get('message', {}).get('tool_calls', []):
                            if call.get('id') == toolcall and call.get('function', {}).get('name') == 'Agent':
                                parent_generations.append((gi, ge, call))
            except (AuditError, TypeError, AttributeError):
                continue
        if len(parent_generations) != 1:
            fail(3, 'missing_or_ambiguous_parent_toolcall')
        parent_gen_id, parent_gen, parent_call = parent_generations[0]
        if parent_gen['end_line'] >= e['start_line']:
            fail(2, 'invalid_agent_call_order')
        if ('toolOutput' in parent_gen['span'].get('attributes', {}).get('tracePayloadTruncatedFields', [])
                or 'toolInput' in s.get('attributes', {}).get('tracePayloadTruncatedFields', [])):
            fail(3, 'truncated_agent_arguments')
        try:
            parent_args = json_string(parent_call['function']['arguments'])
            agent_args = json_string(s['toolInput'])
        except (AuditError, KeyError, TypeError):
            fail(3, 'missing_or_invalid_agent_arguments')
        if not isinstance(parent_args, dict) or not isinstance(agent_args, dict):
            fail(3, 'invalid_agent_arguments')
        if json.dumps(parent_args, sort_keys=True, ensure_ascii=True) != json.dumps(agent_args, sort_keys=True, ensure_ascii=True):
            fail(1, 'agent_arguments_mismatch')
        children = [(i, v) for i, v in spans.items() if v['span'].get('parentId') == sid and v['span'].get('type') == 'agent' and v['span'].get('name') == 'general-purpose']
        if len(children) != 1:
            fail(3, 'missing_or_ambiguous_child_agent')
        child_id, child = children[0]
        if not (e['start_line'] < child['start_line'] < child['end_line'] < e['end_line']):
            fail(2, 'invalid_child_span_order')
        descendants = []
        for i, v in spans.items():
            parent = v['span'].get('parentId')
            while parent and parent != child_id:
                parent = spans[parent]['span'].get('parentId')
            if parent == child_id:
                if not (child['start_line'] < v['start_line'] < v['end_line'] < child['end_line']):
                    fail(2, 'invalid_descendant_span_order')
                descendants.append((i, v))
        for _, v in descendants:
            item = v['span']
            if item.get('type') == 'agent':
                fail(3, 'nested_agent_not_supported')
            if item.get('type') not in ('generation', 'function', 'agent', 'custom'):
                fail(3, 'unknown_span_type')
            if item.get('type') == 'custom' and item.get('name') != 'mcp_tools':
                fail(3, 'unknown_custom_span')
        generations = [(i, v) for i, v in descendants if v['span'].get('type') == 'generation']
        if not generations:
            fail(3, 'missing_generation')
        generations.sort(key=lambda x: x[1]['end_line'])
        gen_id, gen = generations[-1]
        if 'toolOutput' in gen['span'].get('attributes', {}).get('tracePayloadTruncatedFields', []):
            fail(3, 'truncated_generation_output')
        payload = json_string(gen['span'].get('toolOutput'))
        try:
            if not isinstance(payload, list) or len(payload) != 1 or len(payload[0]['choices']) != 1:
                fail(3, 'ambiguous_generation')
            content = payload[0]['choices'][0]['message']['content']
            if not isinstance(content, str):
                fail(3, 'missing_generation_content')
        except (KeyError, TypeError):
            fail(3, 'missing_generation_content')
        agent_content = obj.get('content')
        if agent_content not in (content, content + '\n\n[Agent ID: ' + session + ']'):
            fail(1, 'agent_generation_mismatch')
        record = {'session_id': session, 'agent_span_id': sid, 'agent_lines': [e['start_line'], e['end_line']], 'child_span_id': child_id, 'child_lines': [child['start_line'], child['end_line']], 'generation_span_id': gen_id, 'generation_lines': [gen['start_line'], gen['end_line']], 'parent_generation_span_id': parent_gen_id, 'parent_generation_lines': [parent_gen['start_line'], parent_gen['end_line']], 'tool_call_id': toolcall, 'parent_session_id': descriptor['parentSessionId'], 'root_session_id': descriptor['rootSessionId'], 'tools': []}
        if session not in policy['sessions']:
            fail(3, 'missing_policy_session')
        rule = policy['sessions'][session]
        for ti, te in descendants:
            tool = te['span']
            if tool.get('type') != 'function':
                continue
            name = ident(tool.get('toolName'))
            if name != tool.get('name'):
                fail(2, 'tool_identity_conflict')
            item = {'span_id': ti, 'lines': [te['start_line'], te['end_line']], 'name': name, 'allowed': False}
            if name == 'Read' and name in rule['tools']:
                inp = json_string(tool.get('toolInput'))
                path = inp.get('file_path') if isinstance(inp, dict) else None
                if absolute(path) and not Path(path).is_dir():
                    resolved = os.path.realpath(path)
                    item['path_sha256'] = digest(path.encode())
                    item['resolved_path_sha256'] = digest(resolved.encode())
                    item['allowed'] = any(path == p and resolved == os.path.realpath(p) for p in rule['read_paths'])
            if not item['allowed']:
                violations.append('unapproved_tool_or_read')
            record['tools'].append(item)
        sessions[session] = {'record': record, 'content': content}
        calls.append(record)
    if not calls:
        fail(3, 'no_agent_calls')
    expected = []
    for prep in index.get('prep', []):
        expected.append(ident(prep.get('agent_id')))
    if index.get('reviewer') is not None:
        expected.append(ident(index['reviewer'].get('agent_id')))
    turn_results, sources = [], []
    root = Path(index_path).resolve().parent.parent
    turns_seen = set()
    for turn in index['turns']:
        try:
            turn_id = ident(turn['turn_id']); role = ident(turn['role']); session = ident(turn['agent_id'])
            if turn_id in turns_seen:
                fail(2, 'duplicate_turn')
            turns_seen.add(turn_id)
            expected.append(session)
            if 'agent_id_first_draft' in turn:
                expected.append(ident(turn['agent_id_first_draft']))
            files = []
            for key in ('packet', 'submission'):
                rel = turn[key]
                if not isinstance(rel, str) or os.path.isabs(rel) or '..' in Path(rel).parts:
                    fail(2, 'invalid_index_path')
                path = root / rel
                if not path.resolve().is_relative_to(root):
                    fail(2, 'invalid_index_path')
                data = read(path); files.append(load(data))
                sources.append({'turn_id': turn_id, 'kind': key, 'sha256': digest(data)})
            packet, submission = files
            assignment = packet['assignment']
            for field, value in (('turn_id', turn_id), ('role', role), ('run_id', index['run_id'])):
                if assignment.get(field) != value or submission.get(field) != value:
                    violations.append('assignment_mismatch')
            if session not in sessions:
                fail(3, 'indexed_session_missing')
            generated = load(sessions[session]['content'])
            if not isinstance(generated, dict) or not isinstance(submission.get('body'), str) or not isinstance(generated.get('body'), str):
                fail(2, 'invalid_submission')
            body_match = generated['body'] == submission['body']
            full_match = generated == submission
            if not body_match or not full_match:
                violations.append('submission_mismatch')
            turn_results.append({'turn_id': turn_id, 'role': role, 'session_id': session, 'first_draft_session_id': turn.get('agent_id_first_draft'), 'body_match': body_match, 'submission_match': full_match})
        except (KeyError, TypeError):
            fail(2, 'invalid_index_entry')
    if len(expected) != len(set(expected)):
        fail(2, 'duplicate_index_session')
    if set(expected) != set(sessions):
        fail(3, 'index_trace_session_mismatch')
    if set(policy['sessions']) != set(sessions):
        fail(3, 'policy_trace_session_mismatch')
    return calls, turn_results, sources, violations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('trace', 'calls-index', 'policy', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    report = {'schema': 'workbuddy-observed-audit-v1', 'status': 'NOT_VERIFIED', 'exit_code': 3, 'limitations': ['Only observed spans are audited; hidden calls and trace truncation cannot be excluded.', 'Current symlink resolution cannot establish historical targets or file permissions.', 'No strong isolation, semantic correctness, or Agent Teams verification is claimed.', 'Agent Teams: NOT_VERIFIED']}
    try:
        trace = read(args.trace); index_bytes = read(args.calls_index); policy_bytes = read(args.policy)
        report['inputs'] = {'trace_sha256': digest(trace), 'index_sha256': digest(index_bytes), 'policy_sha256': digest(policy_bytes)}
        calls, turns, sources, violations = audit(trace, load(index_bytes), load(policy_bytes), args.calls_index)
        report.update({'calls': calls, 'turns': turns, 'sources': sources, 'call_count': len(calls), 'session_count': len(calls), 'formal_submission_count': len(turns), 'violations': violations})
        report['exit_code'] = 1 if violations else 0
        report['status'] = 'VIOLATION' if violations else 'OBSERVED_PASS'
    except AuditError as exc:
        report['exit_code'] = exc.code
        report['status'] = 'VIOLATION' if exc.code == 1 else ('INPUT_ERROR' if exc.code == 2 else 'NOT_VERIFIED')
        report['reason'] = exc.reason
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        report.update({'exit_code': 2, 'status': 'INPUT_ERROR', 'reason': 'invalid_input_structure'})
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(args.output, flags, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=True, indent=2)
            stream.write('\n')
    except OSError:
        print('Cannot create new report.', file=sys.stderr)
        return 2
    print('status={} exit={}'.format(report['status'], report['exit_code']))
    return report['exit_code']


if __name__ == '__main__':
    sys.exit(main())
