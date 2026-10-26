#!/usr/bin/env python3
"""Behavior and fault checks for telemetry, changes, and artifact-bound outcomes."""
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.dont_write_bytecode = True
import magpie_route as m
import magpie_observe as o
import magpie_change as c
import magpie_outcomes as a

REAL = '--real-cli' in sys.argv
if REAL:
    sys.argv.remove('--real-cli')


def row(i):
    return {'t': f'2026-10-15T00:00:{i:02d}Z', 'agent': 'fixture', 'provider': 'example', 'model': 'strong',
            'session': 'PRIVATE_SESSION', 'source': 'log', 'in': 100, 'out': 10, 'cache_read': 50, 'ms': 100,
            'status': 200, 'cost': .1, 'priced': True, 'prompt': 'SECRET_PROMPT', 'key': 'SECRET_KEY'}


def page(rows, total):
    return {'rows': rows, 'total': total, 'calls': total, 'errors': 0, 'through': {'calls': 0}, 'direct': {'calls': total}}


class ObserveTests(unittest.TestCase):
    def test_all_pages_and_recheck(self):
        rows = [row(i) for i in range(5)]
        def get(_, p):
            return page(rows[p['offset']:p['offset']+p['limit']], 5)
        result = o.read_ledger(get, 'week', '2026-10-15', page_size=2)
        self.assertEqual(result['status'], 'COMPLETE_PAGINATION')
        self.assertEqual(result['read_rows'], 5)
        encoded = json.dumps(result)
        for secret in ['PRIVATE_SESSION', 'SECRET_PROMPT', 'SECRET_KEY']:
            self.assertNotIn(secret, encoded)

    def test_cross_page_overlap_rejected(self):
        def get(_, params):
            return page([row(0), row(1)] if params['offset'] == 0 else [row(1), row(2)], 4)
        self.assertEqual(o.read_ledger(get, 'today', page_size=2)['status'], 'PARTIAL_RECORD_OVERLAP')

    def test_missing_source_stays_unspecified(self):
        r = o.row_projection(row(1));r.pop('source')
        self.assertEqual(o.request_groups([r])[0]['source'], 'unspecified')

    def test_timeout_is_pending(self):
        def get(*_): raise TimeoutError()
        result = o.read_ledger(get, 'today')
        self.assertEqual(result['status'], 'PENDING_TIMEOUT')
        self.assertIsNone(result['expected_rows'])

    def test_duplicate_page_and_total_drift(self):
        for mode in ['repeat', 'total']:
            calls = 0
            def get(_, params):
                nonlocal calls
                calls += 1
                return page([row(0)], 3 if calls == 1 or mode == 'repeat' else 4)
            result = o.read_ledger(get, 'week', page_size=1)
            self.assertEqual(result['status'], 'PARTIAL_REPEATED_PAGE' if mode == 'repeat' else 'PARTIAL_TOTAL_CHANGED')

    def test_final_head_drift_and_page_limit(self):
        count = 0
        def get(_, params):
            nonlocal count
            count += 1
            if count > 2: return page([row(9)], 2)
            return page([row(params['offset'])], 2)
        self.assertEqual(o.read_ledger(get, 'today', page_size=1)['status'], 'PARTIAL_HEAD_CHANGED')
        self.assertEqual(o.read_ledger(lambda *_: page([row(0)], 2), 'today', page_size=1, max_pages=1)['status'], 'PARTIAL_PAGE_LIMIT')

    def test_unknown_source_is_preserved(self):
        r = o.row_projection(dict(row(1), source='new-source'))
        self.assertEqual(r['source'], 'new-source')
        with self.assertRaises(m.Refused):o.row_projection(dict(row(1), cost=float('nan')))

    def test_window_conflict_not_valid_fill(self):
        sample={'agent':'a','session_ref':'s','time':'2026-10-15T00:00:00Z','tokens':300,'window':100,'parts':{'chat':300},'counted':True,'cache_read':0}
        summary=o.summarize_context([sample])[0]
        self.assertEqual(summary['window_metadata_conflict_samples'],1)
        self.assertIsNone(summary['max_window_fill'])

    def test_loopback_only(self):
        for url in ['https://remote.example', 'http://localhost:3425', 'http://127.0.0.1@remote.example', 'http://127.0.0.1:3425/path']:
            with self.assertRaises(m.Refused):o.Gateway(url)
        self.assertTrue(o.Gateway('http://127.0.0.1:3425'))

    def test_local_projection_and_time_filter(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root/'routing').mkdir()
            route = {'time': '2026-10-15T12:00:00Z', 'done': True, 'agent': 'fixture', 'session': 'PRIVATE_SESSION',
                     'status': 200, 'prompt': {'tokens': 100, 'window': 200, 'counted': True,
                     'parts': [{'kind': 'tools', 'tokens': 20, 'items': [{'text': 'SECRET_TEXT'}]}, {'kind': 'chat', 'tokens': 80}]}}
            (root/'routing/2026-10-15.jsonl').write_text(json.dumps(route)+'\n')
            (root/'sessions.json').write_text(json.dumps({'version': 19, 'files': {'SECRET_PATH': {'id': 'PRIVATE_SESSION', 'cwd': 'SECRET_PATH', 'title': 'SECRET_TITLE',
                           'days': {'2026-10-15': {'t': {'exec': 3}, 'm': {'strong': {'input': 100}}}}}}}))
            result = o.read_local(root, root, ['2026-10-15'])
            s = json.dumps(result)
            for secret in ['SECRET_TEXT','SECRET_PATH','SECRET_TITLE','PRIVATE_SESSION']:self.assertNotIn(secret,s)
            self.assertEqual(result['native']['tools'], [{'name':'exec','calls':3}])
            self.assertIsNone(result['native']['skill_calls'])
            summary = o.summarize_context(result['context']['rows'])[0]
            self.assertEqual(summary['parts_share']['tools'], .2)
            self.assertIsNone(summary['cache_ratio'])


class OutcomesTests(unittest.TestCase):
    def fixture(self, root):
        artifact = root/'artifact.txt'; artifact.write_text('real output')
        acceptance = root/'acceptance.json'
        acceptance.write_text(json.dumps({'schema':'magpie-acceptance.v1','task_id':'t1','artifact_sha256':m.sha(artifact),'accepted':True,'reviewed_by':'human','criteria':['matches source']}))
        observation = root/'observation.json'
        ledger = o.read_ledger(lambda *_: page([row(1)], 1), 'today')
        ledger['rows'][0]['session_ref'] = 's1';ledger['rows_sha256'] = o.digest(ledger['rows'])
        observation.write_text(json.dumps({'schema':'magpie-observation.v1','ledger':ledger}))
        r={'task_id':'t1','comparison_key':'extract-same-class','stage':'before','observation':str(observation),'sessions':['s1'],
           'artifact':str(artifact),'acceptance':str(acceptance),'rework_count':0,'human_minutes':3}
        return {'schema':'magpie-outcomes.v1','records':[r]}

    def test_insufficient_and_artifact_drift(self):
        with tempfile.TemporaryDirectory() as td:
            manifest=self.fixture(Path(td))
            result=a.evaluate(manifest)
            self.assertEqual(result['comparisons'][0]['status'],'INSUFFICIENT_EVIDENCE')
            Path(manifest['records'][0]['artifact']).write_text('changed')
            with self.assertRaisesRegex(m.Refused,'artifact_changed'):a.evaluate(manifest)

    def test_descriptive_comparison_not_causal(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);manifest=self.fixture(root)
            after=copy.deepcopy(manifest['records'][0]); after['stage']='after';after['task_id']='t2'
            acc=json.loads(Path(after['acceptance']).read_text());acc['task_id']='t2'
            (root/'acceptance2.json').write_text(json.dumps(acc));after['acceptance']=str(root/'acceptance2.json')
            obs=json.loads(Path(after['observation']).read_text());obs['ledger']['rows'][0]['t']='2026-10-16T00:00:00Z';obs['ledger']['rows_sha256']=o.digest(obs['ledger']['rows'])
            (root/'observation2.json').write_text(json.dumps(obs));after['observation']=str(root/'observation2.json')
            manifest['records'].append(after)
            result=a.evaluate(manifest)['comparisons'][0]
            self.assertEqual(result['status'],'DESCRIPTIVE_COMPARISON')
            self.assertFalse(result['causal_improvement_proven'])
            obs['ledger']['status']='PARTIAL_PAGE_LIMIT';(root/'observation2.json').write_text(json.dumps(obs))
            with self.assertRaisesRegex(m.Refused,'complete_observation'):a.evaluate(manifest)

    def test_inconsistent_complete_label_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            manifest=self.fixture(Path(td));p=Path(manifest['records'][0]['observation']);obs=json.loads(p.read_text())
            obs['ledger']['expected_rows']=99;p.write_text(json.dumps(obs))
            with self.assertRaisesRegex(m.Refused,'coverage_mismatch'):a.evaluate(manifest)

    def test_same_task_with_different_sessions_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            manifest=self.fixture(Path(td));second=copy.deepcopy(manifest['records'][0]);second['sessions']=['another-session']
            manifest['records'].append(second)
            with self.assertRaisesRegex(m.Refused,'task_assigned_twice'):a.evaluate(manifest)

    def test_double_assignment_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            manifest=self.fixture(Path(td));manifest['records']*=2
            with self.assertRaisesRegex(m.Refused,'assigned_twice'):a.evaluate(manifest)


class ChangeTests(unittest.TestCase):
    @unittest.skipUnless(REAL,'explicit --real-cli required')
    def test_real_update_and_restore(self):
        original=m.config_path(); old=m.sha(original) if original.exists() else None
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with patch.dict(os.environ, {'HOME':td,'USERPROFILE':td,'XDG_CONFIG_HOME':str(root/'.config'),'XDG_CACHE_HOME':str(root/'.cache'),
                                         'MAGPIE_NO_ACCOUNTS':'1','MAGPIE_ADDR':'127.0.0.1:39425'}):
                m.cli(['provider','add','example','url=http://127.0.0.1:9/v1','models=strong,cheap'])
                m.cli(['group','add','existing','models=example/strong,example/cheap','routing=smart'])
                path=m.config_path();before=m.load(path)
                spec={'schema':'magpie-group-change.v1','group':'existing','set':{'routing':'order','stays':'session'},
                      'append_rules':[{'pause':'example/cheap','time':'14:00-18:00'}]}
                plan=c.make_plan(spec,path)
                # An exact prefix state is recoverable after a timeout/crash.
                m.cli(plan['steps'][0]['command'])
                partial=c.recovery_plan(plan,path)
                self.assertEqual(partial['completed_source_steps'],1)
                c.apply(partial,path)
                specfile, planfile, receiptfile, recoveryfile = root/'spec.json',root/'plan.json',root/'receipt.json',root/'recovery.json'
                m.save_new(specfile,spec)
                def command(*args):
                    r=subprocess.run([sys.executable,str(Path(c.__file__)),*args],capture_output=True,text=True,timeout=30)
                    self.assertEqual(r.returncode,0,r.stderr)
                command('plan','--spec',str(specfile),'--output',str(planfile))
                plan=m.load(planfile)
                command('apply','--plan',str(planfile),'--plan-sha256',m.sha(planfile),'--execute','--receipt',str(receiptfile))
                self.assertEqual(m.load(receiptfile)['status'],'CONFIG_READBACK_VERIFIED')
                command('recovery-plan','--source-plan',str(planfile),'--output',str(recoveryfile))
                command('apply','--plan',str(recoveryfile),'--plan-sha256',m.sha(recoveryfile),'--execute','--receipt',str(root/'recovered.json'))
                self.assertEqual(c.canonical(c.group_of(m.load(path),'existing')),c.canonical(c.group_of(before,'existing')))
                plan=c.make_plan(spec,path);plan['steps'][0]['command']=['group','rm','existing']
                with self.assertRaisesRegex(m.Refused,'tampered'):c.apply(plan,path)
                plan=c.make_plan(spec,path);c.apply(plan,path)
                restored=c.recovery_plan(plan,path);restored['steps'][0]['command']=['group','rm','existing']
                with self.assertRaisesRegex(m.Refused,'tampered'):c.apply(restored,path)
                m.cli(['group','set','existing','stays=turn'])
                with self.assertRaisesRegex(m.Refused,'drifted'):c.recovery_plan(plan,path)
        if old:self.assertEqual(m.sha(original),old)


if __name__=='__main__':
    if '--fault-probe' in sys.argv:
        try:o.Gateway('https://remote.example')
        except m.Refused:
            print('REMOTE_GATEWAY_REJECTED');sys.exit(2)
        sys.exit(0)
    unittest.main(verbosity=2)
