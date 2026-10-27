from __future__ import annotations

import copy
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import public_adoption as adoption
import public_workflow as flow
import public_report as report
from test_public_workflow import transcript


class PublicAdoptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'state'
        self.home = self.base / 'home'
        transcript(self.home / '.claude/projects/demo/session.jsonl')
        self.scan = flow.scan(self.root, self.home, [], 20)
        self.packet = json.loads(Path(self.scan['packet']).read_text())
        self.analysis = {'schema_version':flow.ANALYSIS_SCHEMA, 'packet_digest':self.packet['packet_digest'],
                         'overview':'合成验证流程，等待人工审阅。', 'patterns':[], 'skill_proposals':[
                             {'title':'验证清单', 'action':'create', 'target_skill':'synthetic-review',
                              'rationale':'明确验收边界。', 'change_points':['补充真实产物验证。'],
                              'evidence_ids':[self.packet['evidence'][0]['evidence_id']]}]}
        self.analysis_path = self.base / 'analysis.json'
        self.imported = self.import_analysis(self.analysis)
        self.aid = self.imported['analysis_id']
        self.historical = {p:p.read_bytes() for p in (self.root/'runs').rglob('*') if p.is_file()}
        self.sql_bytes = self.sql_snapshot()

    def import_analysis(self, value):
        self.analysis_path.write_text(json.dumps(value, ensure_ascii=False))
        return flow.import_analysis(self.root, Path(self.scan['packet']), self.analysis_path)

    def sql_snapshot(self):
        return {p.name:p.read_bytes() for p in self.root.glob('ledger.sqlite*')}

    def register(self):
        result = adoption.register_proposals(self.root, self.aid)
        self.proposal = result['proposals'][0]
        return result

    def event(self, status, request_id=None, **extra):
        return {'request_id':request_id or 'request-'+status, 'status':status,
                'actor':'合成执行者', 'reason':'隔离演示的登记结果。', **extra}

    def record(self, status, request_id=None, **extra):
        return adoption.record_adoption(self.root,self.proposal['proposal_id'],self.proposal['revision'],
                                        self.event(status,request_id,**extra))

    def unchanged(self, before):
        self.assertEqual((self.root/adoption.LEDGER).read_bytes(), before)
        self.assertEqual(self.sql_snapshot(), self.sql_bytes)
        for path, raw in self.historical.items():
            self.assertEqual(path.read_bytes(), raw)

    def test_registration_is_source_bound_atomic_idempotent_and_private(self):
        first = self.register()
        before = (self.root/adoption.LEDGER).read_bytes()
        with mock.patch.object(flow,'now',return_value='2099-01-01T00:00:00+00:00'):
            second = self.register()
        self.assertFalse(first['idempotent']);self.assertTrue(second['idempotent'])
        self.assertEqual(first['proposals'],second['proposals'])
        self.assertEqual(first['proposals'][0]['status'],'pending')
        self.assertEqual((self.root/adoption.LEDGER).stat().st_mode & 0o777,0o600)
        self.unchanged(before)
        self.assertEqual(adoption.adoption_status(self.root,self.aid)['proposals'],first['proposals'])
        self.assertEqual(len(adoption.adoption_status(self.root)['analyses']),1)

    def test_source_failure_creates_no_registration_or_report(self):
        before=set(self.root.rglob('*'))
        with self.assertRaisesRegex(ValueError,'unknown_adoption_analysis'):
            adoption.register_proposals(self.root,'analysis-forged')
        self.assertEqual(before,set(self.root.rglob('*')))
        self.assertFalse((self.root/adoption.LEDGER).exists())
        raw=Path(self.scan['packet']).read_bytes()
        packet=copy.deepcopy(self.packet);packet['evidence'][0]['summary']='伪造摘要'
        Path(self.scan['packet']).write_text(json.dumps(packet))
        with self.assertRaisesRegex(ValueError,'adoption_packet_hash_mismatch'):
            self.register()
        Path(self.scan['packet']).write_bytes(raw)
        analysis_file=Path(self.imported['report']).with_suffix('.json')
        analysis_file.write_text('{}')
        with self.assertRaisesRegex(ValueError,'adoption_analysis_hash_mismatch'):
            self.register()
        self.assertFalse((self.root/adoption.LEDGER).exists())
        self.assertEqual(self.sql_snapshot(),self.sql_bytes)

    def test_complete_state_chain_exact_references_and_request_idempotency(self):
        self.register()
        self.record('observe')
        accepted=self.record('accepted',authorization_ref='user-instruction-demo')
        before=(self.root/adoption.LEDGER).read_bytes()
        with mock.patch.object(flow,'now',return_value='2099-01-01T00:00:00+00:00'):
            repeat=self.record('accepted',authorization_ref='user-instruction-demo')
        self.assertTrue(repeat['idempotent']);self.assertEqual(accepted['event'],repeat['event'])
        self.unchanged(before)
        applied=self.record('applied',artifact_sha256='b'*64,file_scope=['references/demo.md'])
        verified=self.record('verified',applied_event_id=applied['event']['event_id'],verification_ref='isolated-cli-demo')
        snapshot=adoption.adoption_status(self.root,self.aid)
        self.assertEqual(snapshot['proposals'][0]['status'],'verified')
        self.assertEqual(len(snapshot['proposals'][0]['events']),4)
        self.assertEqual(verified['event']['applied_event_id'],applied['event']['event_id'])
        self.assertEqual(self.sql_snapshot(),self.sql_bytes)
        for path,raw in self.historical.items():self.assertEqual(path.read_bytes(),raw)

    def test_bad_event_fields_transitions_and_spoofing_leave_no_record(self):
        self.register()
        before=(self.root/adoption.LEDGER).read_bytes()
        invalid=[self.event('applied',commit_oid='c'*40,file_scope=['scripts/demo.py']),
                 self.event('accepted'),self.event('accepted',authorization_ref=None),
                 self.event('accepted',authorization_ref='demo',at='2026-01-01'),
                 self.event('pending'),self.event('accepted',authorization_ref='demo',analysis_id=self.aid),
                 self.event('accepted',authorization_ref='demo',event_id='forged'),
                 self.event('accepted',authorization_ref='demo',source={'analysis_id':self.aid}),
                 self.event('accepted',authorization_ref='demo',actor='token='+'abcdefghijklmnop123456'),
                 self.event('accepted',request_id='138'+'0013'+'8000',authorization_ref='demo')]
        for event in invalid:
            with self.subTest(event=event),self.assertRaises(ValueError):
                adoption.record_adoption(self.root,self.proposal['proposal_id'],self.proposal['revision'],event)
            self.unchanged(before)
        with self.assertRaisesRegex(ValueError,'unknown_adoption_proposal_revision'):
            adoption.record_adoption(self.root,'proposal-forged','f'*64,self.event('observe'))
        self.unchanged(before)

    def test_request_conflict_rejected_and_terminal_status(self):
        self.register();self.record('rejected','same-request')
        before=(self.root/adoption.LEDGER).read_bytes()
        with self.assertRaisesRegex(ValueError,'adoption_request_conflict'):
            self.record('observe','same-request')
        with self.assertRaisesRegex(ValueError,'invalid_adoption_transition'):
            self.record('accepted',authorization_ref='demo')
        self.unchanged(before)

    def test_applied_binding_scope_and_verification_exact_event(self):
        self.register();self.record('accepted',authorization_ref='demo')
        before=(self.root/adoption.LEDGER).read_bytes()
        for extra in ({'file_scope':['demo.md']}, {'commit_oid':'short','file_scope':['demo.md']},
                      {'artifact_sha256':None,'file_scope':['demo.md']},
                      {'commit_oid':'c'*40,'file_scope':[]}, {'commit_oid':'c'*40,'file_scope':['../escape']},
                      {'commit_oid':'c'*40,'file_scope':['/absolute/demo.md']},
                      {'commit_oid':'c'*40,'file_scope':['C:\\demo.md']}):
            with self.subTest(extra=extra),self.assertRaises(ValueError):self.record('applied',**extra)
            self.unchanged(before)
        applied=self.record('applied',commit_oid='c'*40,file_scope=['scripts/demo.py'])
        before=(self.root/adoption.LEDGER).read_bytes()
        with self.assertRaisesRegex(ValueError,'adoption_applied_event_mismatch'):
            self.record('failed',applied_event_id='evt-wrong',verification_ref='demo')
        self.unchanged(before)
        self.record('inconclusive',applied_event_id=applied['event']['event_id'],verification_ref='demo-needs-runtime')
        self.assertEqual(adoption.adoption_status(self.root,self.aid)['proposals'][0]['status'],'inconclusive')

    def test_new_revision_keeps_history_and_rejects_stale_events(self):
        old=self.register()['proposals'][0]
        self.record('accepted',authorization_ref='demo')
        newer=copy.deepcopy(self.analysis);newer['skill_proposals'][0]['rationale']='修订后的实施理由。'
        result=self.import_analysis(newer)
        self.sql_bytes=self.sql_snapshot()
        current=adoption.register_proposals(self.root,result['analysis_id'])['proposals'][0]
        self.assertEqual(current['proposal_id'],old['proposal_id'])
        self.assertNotEqual(current['revision'],old['revision']);self.assertEqual(current['status'],'pending')
        before=(self.root/adoption.LEDGER).read_bytes()
        with self.assertRaisesRegex(ValueError,'stale_adoption_revision'):
            self.record('applied',commit_oid='a'*40,file_scope=['demo.md'])
        self.unchanged(before)
        old_status=adoption.adoption_status(self.root,self.aid)['proposals'][0]
        self.assertEqual(old_status['status'],'accepted');self.assertEqual(len(old_status['events']),1)
        adoption.register_proposals(self.root,self.aid)
        with self.assertRaisesRegex(ValueError,'stale_adoption_revision'):
            self.record('observe')

    def _check_renderer_replay(self, original_registered):
        old = self.register()['proposals'][0] if original_registered else None
        if original_registered:
            self.record('accepted', authorization_ref='synthetic permission')
        changed = copy.deepcopy(self.analysis)
        changed['skill_proposals'][0]['rationale'] = 'A new content revision for independent review.'
        newer = self.import_analysis(changed)
        current = adoption.register_proposals(self.root, newer['analysis_id'])['proposals'][0]
        original = flow.digest
        def renderer_upgrade(value):
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], dict) and 'overview' in value[0]:
                return original([*value, 'synthetic-renderer-upgrade'])
            return original(value)
        with mock.patch.object(flow, 'digest', side_effect=renderer_upgrade):
            replay = self.import_analysis(self.analysis)
        replayed = adoption.register_proposals(self.root, replay['analysis_id'])['proposals'][0]
        if old:
            self.assertEqual(replayed['revision'], old['revision'])
        self.proposal = replayed
        before = (self.root / adoption.LEDGER).read_bytes()
        with self.assertRaisesRegex(ValueError, 'stale_adoption_revision'):
            if original_registered:
                self.record('applied', commit_oid='a'*40, file_scope=['demo.md'])
            else:
                self.record('accepted', authorization_ref='synthetic permission')
        self.assertEqual((self.root / adoption.LEDGER).read_bytes(), before)
        adoption.record_adoption(self.root, current['proposal_id'], current['revision'],
                                 self.event('accepted', 'accept-new', authorization_ref='new permission'))
        self.assertEqual(adoption.adoption_status(self.root, newer['analysis_id'])['proposals'][0]['status'], 'accepted')

    def test_renderer_replay_cannot_revive_superseded_content_revision(self):
        self._check_renderer_replay(True)

    def test_unregistered_old_import_cannot_be_promoted_by_renderer_replay(self):
        self._check_renderer_replay(False)

    def test_renderer_only_reimport_preserves_revision_and_decisions(self):
        old=self.register()['proposals'][0]
        self.record('accepted',authorization_ref='demo')
        # import-analysis includes renderer bytes in its storage identity; emulate
        # a renderer upgrade without changing proposal content or packet evidence.
        original=flow.digest
        def renderer_upgrade(value):
            if isinstance(value,list) and len(value)==2 and isinstance(value[0],dict) and 'overview' in value[0]:
                return original([*value,'synthetic-renderer-upgrade'])
            return original(value)
        with mock.patch.object(flow,'digest',side_effect=renderer_upgrade):
            newer=self.import_analysis(self.analysis)
        self.assertNotEqual(newer['analysis_id'],self.aid)
        self.sql_bytes=self.sql_snapshot()
        current=adoption.register_proposals(self.root,newer['analysis_id'])['proposals'][0]
        self.assertEqual(current['proposal_id'],old['proposal_id'])
        self.assertEqual(current['revision'],old['revision'])
        self.assertEqual(current['status'],'accepted')
        self.assertEqual(len(current['events']),1)
        self.record('applied',commit_oid='a'*40,file_scope=['demo.md'])
        self.assertEqual(adoption.adoption_status(self.root,newer['analysis_id'])['proposals'][0]['status'],'applied')

    def test_stable_id_normalizes_points_but_revision_is_precise(self):
        old=self.register()['proposals'][0]
        newer=copy.deepcopy(self.analysis);newer['skill_proposals'][0]['change_points']=['  补充真实产物验证。  ']
        result=self.import_analysis(newer)
        current=adoption.register_proposals(self.root,result['analysis_id'])['proposals'][0]
        self.assertEqual(current['proposal_id'],old['proposal_id']);self.assertNotEqual(current['revision'],old['revision'])

    def test_corrupt_unknown_and_semantically_broken_ledgers_preserved(self):
        self.register();self.record('observe')
        good=(self.root/adoption.LEDGER).read_bytes()
        broken=[]
        broken.append(b'{bad json');broken.append(b'{"schema_version":"future"}')
        ledger=json.loads(good);ledger['events'][0]['reason']='篡改内容';broken.append(json.dumps(ledger).encode())
        ledger=json.loads(good);ledger['events'][0]['revision']='a'*64;broken.append(json.dumps(ledger).encode())
        ledger=json.loads(good);ledger['events'][0]['at']=[];broken.append(json.dumps(ledger).encode())
        ledger=json.loads(good);ledger['analyses'][self.aid]['packet_digest']='f'*64;broken.append(json.dumps(ledger).encode())
        for raw in broken:
            (self.root/adoption.LEDGER).write_bytes(raw)
            with self.subTest(raw=raw[:100]),self.assertRaises(ValueError):adoption.adoption_status(self.root,self.aid)
            self.assertEqual((self.root/adoption.LEDGER).read_bytes(),raw)
            with self.assertRaises(ValueError):self.register()
            self.assertEqual((self.root/adoption.LEDGER).read_bytes(),raw)
        (self.root/adoption.LEDGER).write_bytes(good)

    def test_atomic_failure_lock_conflict_and_read_only_source_bytes(self):
        self.register()
        before=(self.root/adoption.LEDGER).read_bytes()
        with mock.patch.object(flow,'write_json',side_effect=OSError('synthetic write failure')):
            with self.assertRaises(OSError):self.record('observe')
        self.unchanged(before)
        with flow.locked(self.root):
            for operation in (lambda:self.register(),lambda:adoption.adoption_status(self.root),lambda:self.record('observe'),lambda:adoption.render_adoptions(self.root,self.aid)):
                with self.assertRaisesRegex(ValueError,'scan_already_running'):operation()
        self.unchanged(before)

    def test_live_wal_snapshot_source_is_read_only_and_budget_failure_preserves_ledger(self):
        with sqlite3.connect(self.root/'ledger.sqlite') as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute("INSERT INTO meta VALUES('synthetic-wal','latest')")
            conn.commit()
            self.sql_bytes=self.sql_snapshot()
            self.assertIn('ledger.sqlite-wal',self.sql_bytes)
            self.register()
            before=(self.root/adoption.LEDGER).read_bytes()
            self.unchanged(before)
            with mock.patch.object(adoption,'MAX_LEDGER_BYTES',len(before)+10):
                with self.assertRaisesRegex(ValueError,'adoption_ledger_size_budget_exceeded'):
                    self.record('observe')
            self.unchanged(before)

    def test_renderer_snapshot_binding_history_and_failure_does_not_duplicate_event(self):
        self.register();self.record('accepted',authorization_ref='demo')
        before=(self.root/adoption.LEDGER).read_bytes()
        with mock.patch.object(report,'render_bundle',side_effect=RuntimeError('synthetic renderer failure')):
            with self.assertRaises(RuntimeError):adoption.render_adoptions(self.root,self.aid)
        self.unchanged(before)
        calls=[]
        def fake(packet, analysis, *, stem, adoptions):
            calls.append(copy.deepcopy(adoptions))
            return {stem+'.html':json.dumps(adoptions,ensure_ascii=False)}
        with mock.patch.object(report,'render_bundle',side_effect=fake):
            first=adoption.render_adoptions(self.root,self.aid)
            old_bytes=Path(first['report']).read_bytes()
            repeat=adoption.render_adoptions(self.root,self.aid)
            self.assertEqual(first['report'],repeat['report'])
            self.record('applied',commit_oid='a'*40,file_scope=['demo.md'])
            second=adoption.render_adoptions(self.root,self.aid)
        self.assertNotEqual(first['report'],second['report'])
        self.assertEqual(Path(first['report']).read_bytes(),old_bytes)
        self.assertEqual(calls[0]['proposals'][0]['status'],'accepted')
        self.assertEqual(calls[-1]['proposals'][0]['status'],'applied')
        self.assertEqual(len(adoption.adoption_status(self.root,self.aid)['proposals'][0]['events']),2)

    def test_unregistered_source_absent_and_no_ledger_created_by_read(self):
        one=adoption.adoption_status(self.root,self.aid)
        with mock.patch.object(flow,'now',return_value='2099-01-01T00:00:00+00:00'):
            two=adoption.adoption_status(self.root,self.aid)
        self.assertEqual(one,two);self.assertEqual(one['proposals'],[])
        self.assertFalse((self.root/adoption.LEDGER).exists())

    def test_real_renderer_publishes_seven_pages_with_bound_states(self):
        self.register()
        first = adoption.render_adoptions(self.root, self.aid)
        self.assertEqual(first['report_pages'], 7)
        overview = Path(first['report'])
        files = report.page_files(overview.stem)
        old = {name: (overview.parent / name).read_bytes() for name in files.values()}
        self.record('accepted', authorization_ref='synthetic test permission')
        second = adoption.render_adoptions(self.root, self.aid)
        self.assertNotEqual(first['report'], second['report'])
        self.assertEqual(second, adoption.render_adoptions(self.root, self.aid))
        self.assertEqual(old, {name: (overview.parent / name).read_bytes() for name in files.values()})
        self.assertEqual(self.sql_snapshot(), self.sql_bytes)

    def test_real_cli_chain_and_failed_command_no_new_records(self):
        # Use the exact executable running this suite (PM requires python3.13).
        data_root=self.base/'cli-data';cli_root=data_root/'runtime/public-workflow'
        import shutil
        env={**os.environ,'SELF_EVOLVE_DATA_ROOT':str(data_root),'PYTHONDONTWRITEBYTECODE':'1'}
        def cli(*args, expected=0):
            result=subprocess.run([sys.executable,str(SCRIPTS/'public_workflow.py'),*args],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,expected,result.stderr)
            return json.loads(result.stdout if expected==0 else result.stderr)
        cli('status')  # claim the dedicated data root before copying synthetic state
        shutil.copytree(self.root,cli_root,dirs_exist_ok=True)
        registered=cli('register-proposals','--analysis-id',self.aid)
        proposal=registered['proposals'][0]
        def receipt(status,**extra):
            event_path=self.base/('cli-'+status+'.json');event_path.write_text(json.dumps(self.event(status,**extra)))
            return cli('record-adoption','--proposal-id',proposal['proposal_id'],'--revision',proposal['revision'],'--event',str(event_path))
        receipt('accepted',authorization_ref='synthetic-user-authorization')
        applied=receipt('applied',artifact_sha256='d'*64,file_scope=['references/demo.md'])
        receipt('verified',applied_event_id=applied['event']['event_id'],verification_ref='synthetic-runtime-invocation')
        snapshot=cli('adoption-status','--analysis-id',self.aid)
        self.assertEqual(snapshot['proposals'][0]['status'],'verified')
        before=(cli_root/adoption.LEDGER).read_bytes()
        failure=cli('register-proposals','--analysis-id','analysis-forged',expected=2)
        self.assertEqual(failure['error'],'unknown_adoption_analysis')
        self.assertEqual((cli_root/adoption.LEDGER).read_bytes(),before)
