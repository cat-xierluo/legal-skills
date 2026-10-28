#!/usr/bin/env python3
"""Audit an archived fixed-role WorkBuddy hearing without changing its records."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

import clerk
from audit_workbuddy_trace import AuditError, digest, ident, load, parse_trace, read


def stop(code, reason):
    raise AuditError(code, reason)


def obj_string(value):
    try:
        if isinstance(value, str):
            text = value.strip()
            fenced = re.fullmatch(r'```(?:json)?[ \t]*\n(.*)\n?```[ \t]*', text, re.DOTALL)
            if fenced:
                value = fenced.group(1)
        return load(value)
    except AuditError:
        stop(3, 'missing_or_truncated_trace_payload')


def review_prompt_payload(item, draft, sha):
    return json.dumps({'review_request': {'turn_id': item['turn_id'], 'role': item['role'], 'draft_sha256': sha},
                       'body': draft['body'], 'citations': draft['citations']},
                      ensure_ascii=False, separators=(',', ':'))


def local_file(root, rel):
    if not isinstance(rel, str) or not rel or Path(rel).is_absolute() or '..' in Path(rel).parts:
        stop(2, 'invalid_relative_path')
    p = root / rel
    if not p.resolve().is_relative_to(root):
        stop(2, 'path_outside_hearing')
    return p


def calls_from_trace(data, number):
    # A damaged or interrupted trace cannot establish complete observation.
    try:
        spans = parse_trace(data)
    except AuditError as exc:
        if exc.code == 1:
            raise
        stop(3, 'trace_incomplete_or_invalid')
    calls = []
    for sid, entry in spans.items():
        s = entry['span']
        if s.get('type') != 'function' or s.get('name') != 'Agent':
            continue
        if s.get('toolName') != 'Agent':
            stop(3, 'agent_identity_unverified')
        if any(s.get('attributes', {}).get('tracePayloadTruncatedFields', [])):
            stop(3, 'truncated_agent_payload')
        output, args = obj_string(s.get('toolOutput')), obj_string(s.get('toolInput'))
        try:
            sub = output['subAgent']; session = ident(sub['sessionId']); desc = sub['descriptor']
            toolcall = ident(desc['parentToolCallId'])
            if desc['sessionId'] != session or desc['role'] != 'general-purpose':
                stop(1, 'descriptor_mismatch')
            if not isinstance(args, dict) or not isinstance(args.get('prompt'), str):
                stop(3, 'missing_agent_prompt')
            root_session = ident(desc['rootSessionId'])
            if desc['parentSessionId'] != root_session:
                stop(3, 'nested_agent_unsupported')
        except (KeyError, TypeError):
            stop(3, 'missing_agent_descriptor')
        parents = []
        for pe in spans.values():
            ps = pe['span']
            if ps.get('type') != 'generation' or ps.get('parentId') != s.get('parentId'):
                continue
            if 'toolOutput' in ps.get('attributes', {}).get('tracePayloadTruncatedFields', []):
                stop(3, 'truncated_parent_generation')
            try:
                payload = obj_string(ps.get('toolOutput'))
                for completion in payload:
                    for choice in completion.get('choices', []):
                        for call in choice.get('message', {}).get('tool_calls', []):
                            if call.get('id') == toolcall and call.get('function', {}).get('name') == 'Agent':
                                parents.append((pe, obj_string(call['function']['arguments'])))
            except (TypeError, KeyError, AttributeError):
                stop(3, 'invalid_parent_generation')
        if len(parents) != 1 or parents[0][0]['end_line'] >= entry['start_line']:
            stop(3, 'parent_call_unverified')
        if parents[0][1] != args:
            stop(1, 'parent_arguments_mismatch')
        children = [(i, e) for i, e in spans.items() if e['span'].get('parentId') == sid and e['span'].get('type') == 'agent' and e['span'].get('name') == 'general-purpose']
        if len(children) != 1:
            stop(3, 'child_agent_unverified')
        child_id, child = children[0]
        if not entry['start_line'] < child['start_line'] < child['end_line'] < entry['end_line']:
            stop(3, 'child_order_unverified')
        descendants = []
        for i, e in spans.items():
            parent = e['span'].get('parentId')
            while parent and parent != child_id:
                parent = spans[parent]['span'].get('parentId')
            if parent == child_id:
                if not child['start_line'] < e['start_line'] < e['end_line'] < child['end_line']:
                    stop(3, 'descendant_order_unverified')
                if e['span'].get('type') == 'agent':
                    stop(3, 'nested_agent_unsupported')
                if e['span'].get('type') == 'generation':
                    descendants.append(e)
        if not descendants:
            stop(3, 'missing_child_generation')
        gen = max(descendants, key=lambda e: e['end_line'])['span']
        if 'toolOutput' in gen.get('attributes', {}).get('tracePayloadTruncatedFields', []):
            stop(3, 'truncated_child_generation')
        try:
            result = obj_string(gen['toolOutput'])
            if len(result) != 1 or len(result[0]['choices']) != 1:
                stop(3, 'ambiguous_generation')
            content = result[0]['choices'][0]['message']['content']
            if not isinstance(content, str):
                stop(3, 'missing_generation_content')
            if output['content'] not in (content, content + '\n\n[Agent ID: ' + session + ']'):
                stop(1, 'agent_generation_mismatch')
        except (KeyError, TypeError, IndexError):
            stop(3, 'missing_generation_content')
        calls.append({'trace_index': number, 'trace_line': entry['start_line'], 'end_line': entry['end_line'],
                      'session': session, 'resume': args.get('resume'), 'prompt': args['prompt'],
                      'content': content, 'toolcall': toolcall, 'root': root_session})
    return sorted(calls, key=lambda c: c['trace_line'])


def audit(root, traces, expected_root):
    all_calls = []
    trace_digests, trace_ids = [], []
    for n, trace in enumerate(traces, 1):
        data = read(trace)
        file_digest = digest(data)
        if file_digest in trace_digests:
            stop(2, 'duplicate_trace_input')
        first = load(data.splitlines()[0])
        if not isinstance(first, dict) or first.get('type') != 'trace_start' or not isinstance(first.get('trace'), dict):
            stop(2, 'invalid_trace_boundary')
        trace_id = ident(first['trace'].get('traceId'))
        if trace_id in trace_ids:
            stop(3, 'overlapping_trace_input')
        trace_digests.append(file_digest); trace_ids.append(trace_id)
        all_calls.extend(calls_from_trace(data, n))
    if not all_calls:
        stop(3, 'no_agent_calls')
    session_path = local_file(root, 'calls/role-sessions.json')
    session_data = load(read(session_path))
    try:
        role_entries = session_data['role_sessions']; support_entries = session_data['support_sessions']
        roles = {r['role']: ident(r['native_session_id']) for r in role_entries}
        support = [ident(r['native_session_id']) for r in support_entries]
    except (TypeError, KeyError):
        stop(3, 'session_index_missing_fields')
    if len(role_entries) != 3 or set(roles) != {'judge', 'plaintiff', 'defendant'}:
        stop(1, 'invalid_roles')
    sessions = list(roles.values()) + support
    if len(sessions) != len(set(sessions)):
        stop(1, 'duplicate_session')
    if expected_root is None:
        stop(3, 'expected_root_missing')
    expected_root_id = ident(expected_root)
    if len({call['root'] for call in all_calls}) != 1:
        stop(3, 'root_session_mismatch')
    if all_calls[0]['root'] != expected_root_id:
        stop(3, 'expected_root_mismatch')
    seen, toolcalls = set(), set()
    for call in all_calls:
        session = call['session']
        if session not in sessions:
            stop(1, 'unregistered_session')
        toolcall_key = (call['trace_index'], call['toolcall'])
        if toolcall_key in toolcalls:
            stop(1, 'duplicate_toolcall')
        toolcalls.add(toolcall_key)
        if session in seen:
            if call['resume'] != session:
                stop(1, 'resume_mismatch')
        elif call['resume'] is not None:
            stop(3, 'initial_session_not_observed')
        seen.add(session)
    if seen != set(sessions):
        stop(3, 'registered_session_not_observed')
    try:
        events = clerk.load_events(root / 'run'); state = clerk.replay(events)
    except (clerk.ClerkError, KeyError, TypeError, ValueError):
        stop(2, 'invalid_clerk_events')
    if state['case_type'] != 'civil' or state['closed'] is None or state['closed'].get('status') != 'closed' or state['active'] is not None or events[-1]['kind'] != 'close':
        stop(3, 'hearing_not_closed')
    if session_data.get('run_id') != state['run_id']:
        stop(1, 'session_run_mismatch')
    index_path = root / 'review-receipts/index.json'
    if not index_path.is_file():
        stop(3, 'receipt_index_missing')
    index = load(read(index_path))
    index_fields = {'schema', 'run_id', 'drafts', 'reviews', 'auxiliary_calls'}
    draft_fields = {'turn_id', 'role', 'draft_path', 'trace_index', 'trace_line'}
    review_fields = {'turn_id', 'role', 'draft_path', 'draft_sha256', 'judge_session_id',
                     'verdict', 'receipt_path', 'trace_index', 'trace_line'}
    auxiliary_fields = {'trace_index', 'trace_line', 'session_id', 'purpose'}
    if not isinstance(index, dict) or set(index) != index_fields or index.get('schema') != 'fixed-role-hearing-audit-v1' or index.get('run_id') != state['run_id'] or not isinstance(index.get('drafts'), list) or not isinstance(index.get('reviews'), list) or not isinstance(index.get('auxiliary_calls'), list):
        stop(2, 'invalid_receipt_index')
    lookup = {(c['trace_index'], c['trace_line']): c for c in all_calls}
    def locate(entry):
        key = (entry.get('trace_index'), entry.get('trace_line'))
        if any(type(v) is not int or v < 1 for v in key) or key not in lookup:
            stop(3, 'trace_location_unverified')
        return lookup[key]
    speeches = [e['payload'] for e in events if e['kind'] == 'speech']
    if len({s['turn_id'] for s in speeches}) != len(speeches):
        stop(1, 'duplicate_speech')
    drafts = {}
    draft_locations = set()
    for item in index['drafts']:
        if not isinstance(item, dict) or set(item) != draft_fields: stop(2, 'invalid_draft_entry')
        turn = item.get('turn_id'); role = item.get('role')
        if turn in drafts or role not in roles: stop(1, 'invalid_draft_binding')
        data = read(local_file(root, item.get('draft_path')))
        draft = load(data); call = locate(item)
        if call['session'] != roles[role]: stop(1, 'draft_session_mismatch')
        location = (call['trace_index'], call['trace_line'])
        if location in draft_locations: stop(1, 'duplicate_call_classification')
        draft_locations.add(location)
        native = obj_string(call['content'])
        if not isinstance(draft, dict) or not isinstance(native, dict) or draft != native or draft.get('turn_id') != turn or draft.get('role') != role:
            stop(1, 'native_draft_mismatch')
        drafts[turn] = (role, draft, digest(data), call)
    if set(drafts) != {s['turn_id'] for s in speeches}:
        stop(1, 'speech_draft_coverage_mismatch')
    for speech in speeches:
        if drafts[speech['turn_id']][1] != speech:
            stop(1, 'speech_draft_mismatch')
    accepted = set()
    review_locations = set()
    for item in index['reviews']:
        if not isinstance(item, dict) or set(item) != review_fields: stop(2, 'invalid_review_entry')
        turn, role = item.get('turn_id'), item.get('role')
        if role not in ('plaintiff', 'defendant') or item.get('verdict') not in ('ACCEPT', 'RETURN'):
            stop(1, 'invalid_review_binding')
        data = read(local_file(root, item.get('draft_path'))); draft = load(data)
        sha = item.get('draft_sha256')
        if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha) or sha != digest(data):
            stop(1, 'draft_digest_mismatch')
        if not isinstance(draft, dict) or draft.get('turn_id') != turn or draft.get('role') != role or not isinstance(draft.get('body'), str) or not draft['body'] or not isinstance(draft.get('citations'), list) or any(not isinstance(c, str) or not c for c in draft['citations']):
            stop(1, 'review_draft_invalid')
        call = locate(item)
        location = (call['trace_index'], call['trace_line'])
        if location in review_locations: stop(1, 'duplicate_call_classification')
        review_locations.add(location)
        if item.get('judge_session_id') != roles['judge'] or call['session'] != roles['judge']:
            stop(1, 'judge_session_mismatch')
        verdict = obj_string(call['content'])
        if not isinstance(verdict, dict) or verdict.get('verdict') != item['verdict']:
            stop(1, 'judge_verdict_mismatch')
        prior = []
        for candidate in all_calls:
            if candidate['session'] != roles[role] or (candidate['trace_index'], candidate['end_line']) >= (call['trace_index'], call['trace_line']):
                continue
            try:
                if obj_string(candidate['content']) == draft:
                    prior.append(candidate)
            except AuditError:
                pass
        if not prior:
            stop(1, 'reviewed_draft_not_observed')
        if review_prompt_payload(item, draft, sha) not in call['prompt']:
            stop(1, 'incomplete_review_prompt')
        receipt = read(local_file(root, item.get('receipt_path')))
        if call['content'].encode('utf-8') not in receipt:
            stop(1, 'receipt_content_mismatch')
        if item['verdict'] == 'ACCEPT':
            if turn in accepted or turn not in drafts or drafts[turn][0] != role or drafts[turn][1] != draft or drafts[turn][2] != sha:
                stop(1, 'accepted_draft_mismatch')
            if (call['trace_index'], call['trace_line']) <= (drafts[turn][3]['trace_index'], drafts[turn][3]['end_line']):
                stop(1, 'review_before_draft')
            accepted.add(turn)
    review_calls = set()
    for call in all_calls:
        try:
            output = obj_string(call['content'])
        except AuditError:
            output = None
        if '"review_request"' in call['prompt'] or (call['session'] == roles['judge'] and isinstance(output, dict) and 'verdict' in output):
            review_calls.add((call['trace_index'], call['trace_line']))
    if review_calls - review_locations:
        stop(1, 'unindexed_review_call')
    if review_locations - review_calls:
        stop(1, 'review_call_not_verdict')
    auxiliary_locations = set()
    for item in index['auxiliary_calls']:
        if not isinstance(item, dict) or set(item) != auxiliary_fields: stop(2, 'invalid_auxiliary_entry')
        session_id = ident(item.get('session_id'))
        purpose = item.get('purpose')
        if session_id not in sessions or not isinstance(purpose, str) or not purpose.strip():
            stop(1, 'invalid_auxiliary_entry')
        call = locate(item)
        if call['session'] != session_id: stop(1, 'auxiliary_session_mismatch')
        location = (call['trace_index'], call['trace_line'])
        if location in auxiliary_locations: stop(1, 'duplicate_call_classification')
        auxiliary_locations.add(location)
    observed_locations = {(call['trace_index'], call['trace_line']) for call in all_calls}
    classified_locations = draft_locations | review_locations | auxiliary_locations
    if observed_locations - classified_locations:
        stop(1, 'unclassified_call')
    if classified_locations - observed_locations:
        stop(3, 'call_location_unverified')
    if accepted != {s['turn_id'] for s in speeches if s['role'] in ('plaintiff', 'defendant')}:
        stop(1, 'acceptance_coverage_mismatch')
    return {'call_count': len(all_calls), 'session_count': len(seen), 'speech_count': len(speeches), 'review_count': len(index['reviews']), 'trace_sha256': trace_digests, 'expected_root_session_id': expected_root_id, 'observed_root_session_id': all_calls[0]['root'], 'role_sessions_sha256': digest(read(session_path)), 'index_sha256': digest(read(index_path)), 'event_count': len(events), 'event_last_hash': events[-1]['hash']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hearing', required=True); p.add_argument('--trace', action='append', required=True); p.add_argument('--output', required=True)
    p.add_argument('--expected-root-session')
    args = p.parse_args()
    report = {'schema': 'fixed-role-hearing-audit-report-v1', 'status': 'NOT_VERIFIED', 'exit_code': 3,
              'limitations': ['Observed trace only; no proof of hidden calls, isolation, Teams, legal correctness or confidentiality.', 'Receipt verdict and auxiliary purpose labels are indexed, not semantic judgments.', 'Classification proves every observed call is accounted for, not that its self-declared purpose is honest.']}
    hearing = Path(args.hearing).resolve()
    output = Path(args.output).resolve()
    if output == hearing or hearing in output.parents:
        print('Cannot write report inside hearing.', file=sys.stderr)
        return 2
    try:
        report.update(audit(hearing, args.trace, args.expected_root_session)); report.update(status='OBSERVED_PASS', exit_code=0)
    except AuditError as exc:
        report.update(status={1: 'VIOLATION', 2: 'INPUT_ERROR', 3: 'NOT_VERIFIED'}[exc.code], exit_code=exc.code, reason=exc.reason)
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        report.update(status='INPUT_ERROR', exit_code=2, reason='invalid_input_structure')
    try:
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=True, indent=2); stream.write('\n')
    except OSError:
        print('Cannot create new report.', file=sys.stderr); return 2
    print('status={} exit={}'.format(report['status'], report['exit_code']))
    return report['exit_code']


if __name__ == '__main__':
    sys.exit(main())
