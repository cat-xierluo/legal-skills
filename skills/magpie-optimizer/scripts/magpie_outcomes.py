#!/usr/bin/env python3
"""Bind existing artifacts/acceptance records to requests and compare task outcomes."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
from magpie_route import Refused, require, load, save_new, sha
from magpie_observe import validate_complete_observation


def evaluate(manifest):
    require(isinstance(manifest, dict) and manifest.get('schema') == 'magpie-outcomes.v1', 'outcomes_schema')
    require(isinstance(manifest.get('records'), list) and manifest['records'], 'outcomes_empty')
    records, occupied, tasks, artifacts = [], set(), set(), set()
    for r in manifest['records']:
        require(set(r) == {'task_id', 'comparison_key', 'stage', 'observation', 'sessions', 'artifact', 'acceptance', 'rework_count', 'human_minutes'}, 'outcome_record_fields')
        require(r['stage'] in ('before', 'after') and isinstance(r['comparison_key'], str) and r['comparison_key'], 'comparison_invalid')
        require(isinstance(r['task_id'], str) and r['task_id'], 'task_id_invalid')
        task_key = (r['stage'], r['task_id'])
        require(task_key not in tasks, 'task_assigned_twice_combine_its_sessions')
        tasks.add(task_key)
        require(isinstance(r['sessions'], list) and r['sessions'] and len(set(r['sessions'])) == len(r['sessions']), 'sessions_required')
        require(type(r['rework_count']) is int and r['rework_count'] >= 0, 'rework_count_invalid')
        require(type(r['human_minutes']) in (int, float) and 0 <= r['human_minutes'] < 1000000, 'human_minutes_invalid')
        o = load(r['observation'])
        validate_complete_observation(o)
        rows = [row for row in o['ledger']['rows'] if row.get('session_ref') in r['sessions']]
        require(set(row['session_ref'] for row in rows) == set(r['sessions']), 'session_not_in_observation')
        for row in rows:
            key = (row.get('t'), row.get('agent'), row.get('source'), row.get('provider'), row.get('model'), row.get('session_ref'))
            require(key not in occupied, 'request_assigned_twice')
            occupied.add(key)
        artifact = Path(r['artifact'])
        require(artifact.is_file(), 'artifact_missing')
        artifact_key = (r['stage'], str(artifact.resolve()))
        require(artifact_key not in artifacts, 'artifact_counted_twice')
        artifacts.add(artifact_key)
        actual_hash = sha(artifact)
        a = load(r['acceptance'])
        require(a.get('schema') == 'magpie-acceptance.v1' and a.get('task_id') == r['task_id'], 'acceptance_binding_invalid')
        require(a.get('artifact_sha256') == actual_hash, 'artifact_changed_since_acceptance')
        require(type(a.get('accepted')) is bool and isinstance(a.get('reviewed_by'), str) and a['reviewed_by']
                and isinstance(a.get('criteria'), list) and a['criteria'], 'acceptance_evidence_missing')
        cost = sum(row.get('cost', 0) for row in rows) if all(row.get('priced') is True and 'cost' in row for row in rows) else None
        records.append({'task_id': r['task_id'], 'comparison_key': r['comparison_key'], 'stage': r['stage'],
                        'observation_sha256': sha(r['observation']), 'artifact_sha256': actual_hash, 'acceptance_sha256': sha(r['acceptance']),
                        'accepted': a['accepted'], 'reviewed_by': a['reviewed_by'], 'calls': len(rows),
                        'input': sum(row.get('in', 0) for row in rows), 'output': sum(row.get('out', 0) for row in rows),
                        'cache_read': sum(row.get('cache_read', 0) for row in rows),
                        'request_ms': sum(row.get('ms', 0) for row in rows), 'estimated_cost': cost,
                        'rework_count': r['rework_count'], 'human_minutes': r['human_minutes']})
    groups = defaultdict(lambda: defaultdict(list))
    for r in records:
        groups[r['comparison_key']][r['stage']].append(r)
    comparisons = []
    fields = ('calls', 'input', 'output', 'cache_read', 'request_ms', 'rework_count', 'human_minutes', 'estimated_cost')
    for key, stages in groups.items():
        before, after = stages['before'], stages['after']
        reason = None
        if not before or not after:
            reason = 'missing_before_or_after'
        elif not all(r['accepted'] for r in before + after):
            reason = 'quality_gate_not_met'
        def average(rs, field):
            vals = [r[field] for r in rs]
            return sum(vals) / len(vals) if vals and all(v is not None for v in vals) else None
        comparison = {'comparison_key': key, 'before_tasks': len(before), 'after_tasks': len(after),
                      'status': 'INSUFFICIENT_EVIDENCE' if reason else 'DESCRIPTIVE_COMPARISON', 'reason': reason,
                      'quality_basis': 'supplied_acceptance_bound_to_current_artifacts', 'causal_improvement_proven': False}
        if reason is None:
            comparison['per_accepted_task'] = {f: {'before': average(before, f), 'after': average(after, f)} for f in fields}
        comparisons.append(comparison)
    return {'schema': 'magpie-outcome-review.v1', 'records': records, 'comparisons': comparisons,
            'limits': ['验收语义来自具名评审，工具只核绑定与实际文件', '任务可比性来自用户提供的comparison_key，未由工具证明',
                       'request_ms为累计调用耗时，不能当作并发任务墙钟时间', '目录价是估算，不能当作实付费用', '小样本和平台变化不足以证明因果收益']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    out = evaluate(load(args.manifest))
    save_new(args.output, out)
    print(json.dumps({'status': 'OUTCOMES_REVIEWED', 'output': args.output}))


if __name__ == '__main__':
    try:
        main()
    except (Refused, OSError, ValueError, KeyError, TypeError) as e:
        print(json.dumps({'status': 'REFUSED', 'reason': str(e) if isinstance(e, Refused) else type(e).__name__}), file=sys.stderr)
        sys.exit(2)
