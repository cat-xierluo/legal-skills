#!/usr/bin/env python3
"""Narrow existing-group updates and recovery plans through native Magpie CLI."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
sys.dont_write_bytecode = True
import magpie_route as m


def canonical(g):
    out = copy.deepcopy(g)
    out['routing'] = out.get('routing') or 'smart'
    affinity = out.pop('affinity', None)
    out['stays'] = out.get('stays') or affinity or 'auto'
    out.setdefault('rules', [])
    return out


def group_of(data, gid):
    matches = [g for g in data.get('groups', []) if g.get('id') == gid]
    m.require(len(matches) == 1, 'existing_group_required')
    return matches[0]


def rest(data, gid):
    out = copy.deepcopy(data)
    out['groups'] = [g for g in out.get('groups', []) if g['id'] != gid]
    return out


def raw_rule(r):
    out = {k: v for k, v in r.items() if k not in ('pause', 'use', 'time')}
    out['use'] = r.get('use', r.get('pause'))
    if 'pause' in r:
        out['pause'] = True
    if 'time' in r:
        out['time'] = {'from': r['time'][:5], 'to': r['time'][6:]}
    return out


def patch_steps(spec, before, data):
    m.require(set(spec) == {'schema', 'group', 'set', 'append_rules'} and spec['schema'] == 'magpie-group-change.v1', 'change_schema')
    gid = spec['group']
    m.require(isinstance(gid, str) and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]*', gid), 'group_id_invalid')
    edits = spec['set']
    m.require(isinstance(edits, dict) and set(edits) <= {'members', 'routing', 'stays'}, 'unsupported_change_field')
    new = copy.deepcopy(before)
    new.update(edits)
    # Reuse policy validators for member IDs and append-rule syntax without
    # imposing the create-only ID prefix on an already existing group.
    model = {'id': 'mpr-validation', 'members': new.get('members'), 'routing': new.get('routing') or 'smart',
             'stays': new.get('stays') or 'auto', 'rules': spec['append_rules']}
    m.validate({'schema': 'magpie-route-policy.v1', 'groups': [model]}, dict(data, groups=[]))
    dropped = set(before.get('members', [])) - set(new['members'])
    m.require(not dropped.intersection(r.get('use') for r in before.get('rules', [])), 'member_still_used_by_existing_rule')
    m.require(not dropped.intersection(before.get('off', [])), 'member_has_existing_off_state')
    steps = []
    current = copy.deepcopy(before)
    if edits:
        command = ['group', 'set', gid] + [('models' if k == 'members' else k) + '=' + (','.join(v) if k == 'members' else v) for k, v in edits.items()]
        current.update(edits)
        steps.append({'command': command, 'expected': copy.deepcopy(current)})
    for r in spec['append_rules']:
        current.setdefault('rules', []).append(raw_rule(r))
        command = ['group', 'rule', 'add', gid] + [k if v is True else k + '=' + str(v) for k, v in r.items()]
        steps.append({'command': command, 'expected': copy.deepcopy(current)})
    m.require(steps, 'empty_change')
    return steps


def make_plan(spec, path):
    raw = path.read_bytes()
    data = m.parse_json(raw)
    before = copy.deepcopy(group_of(data, spec['group']))
    steps = patch_steps(spec, before, data)
    version = m.cli(['--version']).strip()
    m.require(m.sha(path) == hashlib.sha256(raw).hexdigest(), 'configuration_drift')
    return {'schema': 'magpie-group-change-plan.v1', 'created_epoch': time.time(), 'config_path': str(path.resolve()),
            'config_sha256': hashlib.sha256(raw).hexdigest(), 'cli_version': version,
            'spec': spec, 'before': before, 'steps': steps, 'mode': 'change'}


def recovery_plan(applied_plan, path):
    m.require(applied_plan.get('schema') == 'magpie-group-change-plan.v1' and applied_plan.get('mode') == 'change', 'source_change_plan_required')
    data = m.load(path)
    gid = applied_plan['spec']['group']
    current = group_of(data, gid)
    candidates = [i+1 for i, step in enumerate(applied_plan['steps']) if canonical(current) == canonical(step['expected'])]
    m.require(candidates, 'changed_group_has_drifted_no_automatic_restore')
    completed_steps = max(candidates)
    target = applied_plan['before']
    steps, progress = [], copy.deepcopy(current)
    had_set = bool(applied_plan['spec']['set'])
    added = max(0, completed_steps - int(had_set))
    for _ in range(added):
        n = len(progress.get('rules', []))
        progress['rules'].pop()
        steps.append({'command': ['group', 'rule', 'rm', gid, str(n)], 'expected': copy.deepcopy(progress)})
    edits = {k: canonical(target)[k] for k in applied_plan['spec']['set']}
    if edits:
        progress.update(edits)
        command = ['group', 'set', gid] + [('models' if k == 'members' else k) + '=' + (','.join(v) if k == 'members' else v) for k, v in edits.items()]
        steps.append({'command': command, 'expected': copy.deepcopy(progress)})
    m.require(canonical(progress) == canonical(target), 'restore_shape_mismatch')
    return {'schema': 'magpie-group-change-plan.v1', 'created_epoch': time.time(), 'config_path': str(path.resolve()),
            'config_sha256': m.sha(path), 'cli_version': m.cli(['--version']).strip(), 'before': current,
            'spec': applied_plan['spec'], 'steps': steps, 'mode': 'restore', 'completed_source_steps': completed_steps, 'source_change_plan': applied_plan, 'source_plan_sha256': hashlib.sha256(json.dumps(applied_plan, sort_keys=True).encode()).hexdigest()}


def apply(plan, path):
    m.require(plan.get('schema') == 'magpie-group-change-plan.v1', 'plan_schema')
    m.require(0 <= time.time() - plan['created_epoch'] <= 900, 'plan_expired')
    m.require(plan['cli_version'] == m.cli(['--version']).strip(), 'cli_version_changed')
    raw = path.read_bytes()
    expected_hash = hashlib.sha256(raw).hexdigest()
    m.require(str(path.resolve()) == plan['config_path'] and expected_hash == plan['config_sha256'], 'configuration_drift')
    data = m.parse_json(raw)
    gid = plan['spec']['group']
    m.require(canonical(group_of(data, gid)) == canonical(plan['before']), 'group_before_mismatch')
    if plan['mode'] == 'change':
        m.require(patch_steps(plan['spec'], plan['before'], data) == plan['steps'], 'plan_commands_tampered')
    else:
        m.require(plan['mode'] == 'restore', 'plan_mode')
        source = plan.get('source_change_plan')
        m.require(isinstance(source, dict), 'restore_source_required')
        m.require(patch_steps(source['spec'], source['before'], data) == source['steps'], 'source_commands_tampered')
        regenerated = recovery_plan(source, path)
        m.require(regenerated['spec'] == plan['spec'] and regenerated['steps'] == plan['steps'], 'restore_commands_tampered')
    for step in plan['steps']:
        m.require(m.sha(path) == expected_hash, 'configuration_drift_between_commands')
        m.cli(step['command'])
        raw = path.read_bytes()
        after = m.parse_json(raw)
        m.require(rest(after, gid) == rest(data, gid), 'unrelated_configuration_changed')
        m.require(canonical(group_of(after, gid)) == canonical(step['expected']), 'postwrite_readback_mismatch')
        expected_hash = hashlib.sha256(raw).hexdigest()
    return {'status': 'CONFIG_READBACK_VERIFIED', 'mode': plan['mode'], 'group': gid, 'config_after_sha256': expected_hash, 'inference': 'NOT_VERIFIED'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    pl = sub.add_parser('plan'); pl.add_argument('--spec', required=True); pl.add_argument('--output', required=True)
    rec = sub.add_parser('recovery-plan'); rec.add_argument('--source-plan', required=True); rec.add_argument('--output', required=True)
    ap = sub.add_parser('apply'); ap.add_argument('--plan', required=True); ap.add_argument('--plan-sha256', required=True)
    ap.add_argument('--execute', action='store_true'); ap.add_argument('--receipt', required=True)
    args = p.parse_args(); path = m.config_path()
    if args.command == 'plan':
        result = make_plan(m.load(args.spec), path); m.save_new(args.output, result)
        print(json.dumps({'status': 'PLANNED_NOT_APPLIED', 'sha256': m.sha(args.output), 'output': args.output}))
    elif args.command == 'recovery-plan':
        result = recovery_plan(m.load(args.source_plan), path); m.save_new(args.output, result)
        print(json.dumps({'status': 'RECOVERY_PLANNED_NOT_APPLIED', 'sha256': m.sha(args.output), 'output': args.output}))
    else:
        m.require(args.execute, 'execute_required')
        content = Path(args.plan).read_bytes()
        m.require(hashlib.sha256(content).hexdigest() == args.plan_sha256, 'plan_sha_mismatch')
        m.require(not Path(args.receipt).exists(), 'receipt_exists')
        lock = path.parent / '.magpie-optimizer-writer.lock'
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600); os.close(fd)
        try:
            m.save_new(args.receipt, {'status': 'RUNNING_INSPECT_BEFORE_RETRY', 'plan_sha256': args.plan_sha256})
            try:
                result = apply(m.parse_json(content), path)
            except Exception:
                m.update_receipt(args.receipt, {'status': 'STOPPED_INSPECT_PARTIAL_STATE', 'auto_retry': False})
                raise
            m.update_receipt(args.receipt, dict(result, plan_sha256=args.plan_sha256))
        finally:
            lock.unlink()
        print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except (m.Refused, OSError, ValueError, KeyError, TypeError) as e:
        print(json.dumps({'status': 'REFUSED', 'reason': str(e) if isinstance(e, m.Refused) else type(e).__name__}), file=sys.stderr)
        sys.exit(2)
