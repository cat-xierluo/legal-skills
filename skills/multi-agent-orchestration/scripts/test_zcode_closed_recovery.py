#!/usr/bin/env python3
"""Public CLI recovery consumers; real SQLite/Node/Git, fake Orca only."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zcode_closed_recovery as r
from completion_authority import dispatch_identity
ROOT=Path(__file__).resolve().parent

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.wt=self.root/'wt';self.wt.mkdir();subprocess.run(['git','init','-b','worker',str(self.wt)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(self.wt),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--allow-empty','-m','fixture'],check=True,capture_output=True)
        self.context=self.wt/'.claude/agent-sessions/session';self.context.mkdir(parents=True)
        ad=self.root/'agent-authority';ad.mkdir(mode=0o700);self.authority=ad/'session.json'
        self.json(self.authority,{'schema':'multi-agent-orchestration.authority-receipt.v1','session':'session','branch':'worker','worktree':str(self.wt)})
        ah=hashlib.sha256(self.authority.read_bytes()).hexdigest()
        self.old={'schema':'multi-agent-orchestration.completion-authority.v1','state':'active','task_id':'task_initial','dispatch_id':'ctx_initial','run_id':'run_one','terminal_handle':'term_old','runtime_id':'runtime_one','process_incarnation':'proc_old','capability_hash':'a'*64,'authority_receipt_file':str(self.authority),'authority_receipt_sha256':ah}
        self.cp=Path(r.completion_path(str(self.authority)));self.json(self.cp,self.old)
        self.node=str(Path(shutil.which('node')).resolve());self.entry=self.root/'entry.mjs';self.entry.write_text('console.log("isolated-resume-nonce");setInterval(()=>{},1000);');self.entry.chmod(0o700)
        self.zcode=self.root/'zcode';self.zcode.write_text('#!/bin/sh\nexec '+r.shlex.join([self.node,str(self.entry)])+' "$@"\n');self.zcode.chmod(0o700)
        command=r.shlex.join(['env','WORKER_SESSION_CONTEXT='+str(self.context),str(self.zcode),'--mode','yolo'])
        self.metadata=self.context/'METADATA.json';self.meta={'schema':'multi-agent-orchestration.worktree-metadata.v1','worktree':str(self.wt),'branch':'worker','runtime':{'worker_backend':'zcode-cli','command':command},'session':{'id':'session','context':str(self.context),'orca':{'worktree_id':'wt_one','runtime_id':'runtime_one','terminal_handle':'term_old','supervised':{'task_id':'task_initial','dispatch_id':'ctx_initial','run_id':'run_one','coordinator_handle':'term_pm','terminal_ownership':'created'}}},'execution_authority':{'authority_receipt_file':str(self.authority),'authority_receipt_sha256':ah}}
        self.json(self.metadata,self.meta)
        quote=subprocess.check_output(['/bin/bash','-c','printf %q "$1"','_',command]);self.launch=self.context/'launch.sh';self.launch.write_bytes(b'#!/bin/bash\n# original wrapper\nexec bash -c '+quote+b'\n');self.launch.chmod(0o700)
        self.db=self.root/'native.sqlite';c=sqlite3.connect(self.db);c.executescript('CREATE TABLE session(id,directory,path,parent_id,permission,version);CREATE TABLE session_entry(session_id,type,data,time_updated);')
        c.execute('INSERT INTO session VALUES(?,?,?,?,?,?)',('sess_fixture',str(self.wt),str(self.wt),None,'{"mode":"yolo"}','0.16.9'))
        self.model={'modelSelection':{'providerId':'account:fixture','modelId':'GLM-fixture','options':{'reasoningLevel':'max'}}};c.execute('INSERT INTO session_entry VALUES(?,?,?,?)',('sess_fixture','runtime/model_selection',json.dumps(self.model),1));c.commit();c.close();self.db.chmod(0o600)
        self.responses=self.root/'responses.json';self.log=self.root/'calls.jsonl'
        self.payloads={'ctx_initial':self.worker('ctx_initial','task_initial','term_old','proc_old','completed'),'ctx_failed':self.worker('ctx_failed','task_later','term_old','proc_old','failed'),'ctx_new':self.worker('ctx_new','task_later','term_new','proc_new','dispatched')}
        self.payloads['ctx_new']['result']['dispatch'].update(retryOfDispatchId='ctx_failed',capability_hash='b'*64,capabilityRevokedAt=None)
        self.save_responses();self.orca=self.root/'orca'
        self.orca.write_text('#!'+sys.executable+'\nimport json,sys\nfrom pathlib import Path\na=sys.argv[1:]\np=Path('+repr(str(self.responses))+')\nwith open('+repr(str(self.log))+',"a") as f:f.write(json.dumps(a)+"\\n")\nd=json.loads(p.read_text())\nif a[0]=="status":out={"ok":True,"_meta":{"runtimeId":"runtime_one"},"result":{"runtime":{"reachable":True,"runtimeId":"runtime_one","appVersion":"1.4.218"}}}\nelif a[:2]==["orchestration","run-show"]:out={"ok":True,"_meta":{"runtimeId":"runtime_one"},"result":{"run":{"id":"run_one","coordinator_handle":"term_pm","consumer_generation":4}}}\nelif a[:2]==["orchestration","worker-show"]:out=d[a[a.index("--dispatch")+1]]\nelif a[:2]==["terminal","show"]:out={"ok":True,"result":{"terminal":d["ctx_new"]["result"]["terminal"]}}\nelif a[:2]==["orchestration","dispatch-show"]:out=d["ctx_new"]\nelif a[:2]==["orchestration","worker-start"]:\n assert "--retry-of" in a and a[a.index("--retry-of")+1]=="ctx_failed" and "--retry-request" in a\n request=a[a.index("--retry-request")+1]\n import uuid\n assert request and str(uuid.UUID(request))==request\n intents=list(p.parent.glob("agent-authority/session.recovery-*.json"))\n assert len(intents)==1 and json.loads(intents[0].read_text())["retry_request"]==request\n out={"ok":True,"_meta":{"runtimeId":"runtime_one"},"result":{"state":"ready","dispatchId":"ctx_new","taskId":"task_later","runId":"run_one"}}\nelse:raise SystemExit(91)\nprint(json.dumps(out))\n');self.orca.chmod(0o700)
        self.args=argparse.Namespace(metadata=str(self.metadata),authority=str(self.authority),failed_dispatch='ctx_failed',provider_session='sess_fixture',provider='account:fixture',model='GLM-fixture',effort='max',orca_bin=str(self.orca),zcode_bin=str(self.zcode),zcode_entry=str(self.entry),zcode_node=self.node,native_db=str(self.db))
    def json(self,p,v):p.write_text(json.dumps(v));p.chmod(0o600)
    def worker(self,did,task,term,process,status):
        active=status=='dispatched';return {'ok':True,'_meta':{'runtimeId':'runtime_one'},'result':{'dispatch':{'id':did,'taskId':task,'task_id':task,'runId':'run_one','assigneeHandle':term,'processIncarnation':process,'status':status,'capabilityRevokedAt':None if active else '2026-10-02T12:00:00Z'},'worker':{'stage':'running' if active else 'process_exited','state':'ready' if active else 'failed'},'terminal':{'handle':term,'worktreeId':'wt_one','connected':active,'writable':active,'agentIdentity':'zcode','incarnationId':'inc_new' if active else 'inc_old'},'terminalResource':{'endpointIncarnation':process,'terminalHandle':term,'ownershipState':'external'},'projection':{'liveness':{'verdict':'live' if active else 'exited','source':'execution_host'}},'observation':{'exactWorker':True,'status':'live' if active else 'exited'}}}
    def save_responses(self):self.json(self.responses,self.payloads)
    def prepare(self):self.intent=r.prepare(self.args)['intent'];return self.intent
    def runner(self):
        self.prepare();o=r.load_intent(self.intent);o['state']='opening';r.save(self.intent,o)
        env={**os.environ,'ORCA_TERMINAL_HANDLE':'term_new','ORCA_WORKTREE_ID':'wt_one'}
        self.proc=subprocess.Popen([sys.executable,str(ROOT/'zcode-orca-launcher.py'),'resume-exec','--intent',self.intent],cwd=self.wt,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        def clean():
            if self.proc.poll() is None:self.proc.terminate()
            self.proc.communicate(timeout=5)
        self.addCleanup(clean)
        for _ in range(100):
            if r.load_intent(self.intent)['state']=='launched':
                try:r.verify(self.intent);return
                except (ValueError,subprocess.SubprocessError):pass
            if self.proc.poll() is not None:break
            time.sleep(.03)
        out,err=self.proc.communicate(timeout=3);self.fail('runner not verified '+err)
    def test_closed_different_task_chain_and_native_model(self):
        self.prepare();o=r.load_intent(self.intent);self.assertNotEqual(o['initial']['task_id'],o['failed']['task_id']);self.assertEqual(o['provider_provenance'],'NOT_ORCA_PROVIDER_PROVENANCE')
    def test_live_unknown_revocation_and_chain_refuse_zero_intent(self):
        for mutation in ('live','unknown','revoked','process','run','alias'):
            original=copy.deepcopy(self.payloads);d=self.payloads['ctx_failed']['result']
            if mutation in ('live','unknown'):d['projection']['liveness']['verdict']=mutation
            elif mutation=='revoked':d['dispatch']['capabilityRevokedAt']=None
            elif mutation=='process':d['dispatch']['processIncarnation']='wrong'
            elif mutation=='run':d['dispatch']['runId']='wrong'
            else:d['dispatch']['task_id']='wrong'
            self.save_responses()
            with self.assertRaises(ValueError):r.prepare(self.args)
            self.assertEqual(list(self.authority.parent.glob('*.recovery-*.json')),[]);self.payloads=original
    def test_wrong_model_and_multiple_native_root_refuse(self):
        self.args.model='wrong'
        with self.assertRaises(ValueError):r.prepare(self.args)
        self.args.model='GLM-fixture';c=sqlite3.connect(self.db);c.execute('INSERT INTO session VALUES(?,?,?,?,?,?)',('other',str(self.wt),str(self.wt),None,'{}','0'));c.commit();c.close()
        with self.assertRaises(ValueError):r.prepare(self.args)
    def test_first_reservation_replay_refused(self):
        self.prepare()
        with self.assertRaises(ValueError):r.prepare(self.args)
    def test_real_runner_exact_resume_yolo_zero_business_and_register_adopts(self):
        self.runner();out=r.load_intent(self.intent);self.assertEqual(out['runner_pid'],self.proc.pid)
        command=['bash',str(ROOT/'orca-supervised-register.sh'),'--worktree-id','wt_one','--terminal-handle','term_new','--task-id','task_later','--run-id','run_one','--coordinator-handle','term_pm','--runtime-id','runtime_one','--metadata-file',str(self.metadata),'--authority-receipt',str(self.authority),'--retry-of','ctx_failed','--closed-recovery',self.intent]
        p=subprocess.run(command,env={**os.environ,'ORCA_CLI_BIN':str(self.orca)},capture_output=True,text=True,timeout=20);self.assertEqual(p.returncode,0,p.stderr)
        self.assertTrue(all(line.startswith("ORCAREG_") and "=" in line for line in p.stdout.splitlines()),p.stdout)
        self.assertIn("ORCAREG_TERMINAL_HANDLE=term_new",p.stdout)
        self.assertIn("ORCAREG_COORDINATOR_HANDLE=term_pm",p.stdout)
        m=json.loads(self.metadata.read_text());self.assertEqual(m['session']['orca']['supervised']['task_id'],'task_later');self.assertEqual(json.loads(self.cp.read_text())['dispatch_id'],'ctx_new');self.assertEqual(m['session']['orca']['supervised']['terminal_ownership'],'external');self.assertEqual(m['recovery']['closed_session']['previous_terminal_ownership'],'created')
        calls=[json.loads(x) for x in self.log.read_text().splitlines()];self.assertEqual(sum(x[:2]==['orchestration','worker-start'] for x in calls),1)
        self.assertFalse(any(x[:2] in (['orchestration','task-create'],['orchestration','task-update'],['terminal','send']) for x in calls))
        p=subprocess.run(command,env={**os.environ,'ORCA_CLI_BIN':str(self.orca)},capture_output=True,text=True,timeout=20);self.assertNotEqual(p.returncode,0)
    def test_verify_model_drift_before_any_retry(self):
        self.runner();c=sqlite3.connect(self.db);c.execute('UPDATE session_entry SET data=?',(json.dumps({'modelSelection':{'providerId':'wrong','modelId':'wrong','options':{'reasoningLevel':'max'}}}),));c.commit();c.close()
        with self.assertRaises(ValueError):r.admit_retry(self.intent,'task_later','ctx_failed','term_new','run_one')
        self.assertNotIn('worker-start',self.log.read_text())
    def test_single_reservation_and_original_snapshot_drift(self):
        self.runner();r.admit_retry(self.intent,'task_later','ctx_failed','term_new','run_one')
        with self.assertRaises(ValueError):r.admit_retry(self.intent,'task_later','ctx_failed','term_new','run_one')
        self.launch.write_text('# changed')
        with self.assertRaises(ValueError):r.adopt(self.intent,'ctx_new')
    def test_adoption_write_interrupt_restores_metadata_and_completion(self):
        self.runner();r.admit_retry(self.intent,'task_later','ctx_failed','term_new','run_one');before=(self.metadata.read_bytes(),self.cp.read_bytes());original=r.atomic;fired=False
        def interrupted(path,raw):
            nonlocal fired
            if Path(path)==self.metadata and not fired:fired=True;raise OSError('controlled write interruption')
            return original(path,raw)
        with patch.object(r,'atomic',interrupted):
            with self.assertRaises(OSError):r.adopt(self.intent,'ctx_new')
        self.assertEqual(before,(self.metadata.read_bytes(),self.cp.read_bytes()));self.assertEqual(r.load_intent(self.intent)['state'],'adoption_failed_rolled_back')
        with self.assertRaises(ValueError):r.adopt(self.intent,'ctx_old_or_different')
        self.assertTrue(r.adopt(self.intent,'ctx_new')['ok'])
        with self.assertRaises(ValueError):r.adopt(self.intent,'ctx_new')
    def test_new_attempt_wrong_retry_runtime_incarnation_refuse(self):
        self.runner();r.admit_retry(self.intent,'task_later','ctx_failed','term_new','run_one')
        for key in ('retryOfDispatchId','processIncarnation','taskId','runId'):
            original=copy.deepcopy(self.payloads);self.payloads['ctx_new']['result']['dispatch'][key]='wrong';self.save_responses()
            with self.assertRaises(ValueError):r.adopt(self.intent,'ctx_new')
            self.payloads=original
    def test_concurrent_registers_start_once(self):
        self.runner()
        command=['bash',str(ROOT/'orca-supervised-register.sh'),'--worktree-id','wt_one','--terminal-handle','term_new','--task-id','task_later','--run-id','run_one','--coordinator-handle','term_pm','--runtime-id','runtime_one','--metadata-file',str(self.metadata),'--authority-receipt',str(self.authority),'--retry-of','ctx_failed','--closed-recovery',self.intent]
        processes=[subprocess.Popen(command,env={**os.environ,'ORCA_CLI_BIN':str(self.orca)},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
        codes=[]
        for proc in processes:
            out,err=proc.communicate(timeout=20);codes.append(proc.returncode)
        self.assertEqual(sum(x==0 for x in codes),1,codes)
        calls=[json.loads(x) for x in self.log.read_text().splitlines()]
        self.assertEqual(sum(x[:2]==['orchestration','worker-start'] for x in calls),1)
    def test_fresh_live_unknown_process_and_changed_owner_refuse(self):
        self.runner();r.admit_retry(self.intent,'task_later','ctx_failed','term_new','run_one')
        self.payloads['ctx_new']['result']['projection']['liveness']['verdict']='unverifiable';self.save_responses()
        with self.assertRaises(ValueError):r.adopt(self.intent,'ctx_new')
    def test_expired_unopened_intent_cannot_create(self):
        self.prepare();o=r.load_intent(self.intent);o['created_at']-=121;r.save(self.intent,o)
        with self.assertRaises(ValueError):r.open_terminal(self.intent)
        self.assertNotIn('terminal", "create',self.log.read_text())

    def test_post_start_commit_is_recorded_not_business_replayed(self):
        self.runner();r.admit_retry(self.intent,'task_later','ctx_failed','term_new','run_one')
        (self.wt/'authorized.txt').write_text('isolated authorized nonce')
        subprocess.run(['git','-C',str(self.wt),'add','authorized.txt'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(self.wt),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','authorized'],check=True,capture_output=True)
        self.assertTrue(r.adopt(self.intent,'ctx_new')['ok'])
        o=r.load_intent(self.intent);self.assertNotEqual(o['head'],o['post_start_observation']['head'])

    def test_conflicting_revocation_and_generation_aliases_refuse(self):
        self.payloads['ctx_failed']['result']['dispatch']['capability_revoked_at']=None;self.save_responses()
        with self.assertRaises(ValueError):r.prepare(self.args)
        owner={'ok':True,'_meta':{'runtimeId':'runtime_one'},'result':{'run':{'id':'run_one','coordinator_handle':'term_pm','consumer_generation':4,'consumerGeneration':5}}}
        with patch.object(r,'call',return_value=owner):
            with self.assertRaises(ValueError):r.run_owner(str(self.orca),'run_one','runtime_one')
        owner['result']['run']['consumerGeneration']=None
        with patch.object(r,'call',return_value=owner):
            with self.assertRaises(ValueError):r.run_owner(str(self.orca),'run_one','runtime_one')

    def test_known_live_unknown_status_alias_and_revoked_completion(self):
        d={'id':'ctx','taskId':'task','task_id':'other','assigneeHandle':'term','runId':'run','processIncarnation':'proc','capability_hash':'a'*64}
        with self.assertRaises(ValueError):dispatch_identity(d)
    def test_fixture_memory_refused_before_terminal_create(self):
        self.prepare()
        with patch.dict(os.environ,{'MEM_BUDGET_FIXTURE_DIR':'/fixture'}):
            with self.assertRaises(ValueError):r.open_terminal(self.intent)
        self.assertNotIn('terminal", "create',self.log.read_text())

    def diagnose_consumer(self):
        return subprocess.run([sys.executable,str(ROOT/'zcode_closed_recovery.py'),'diagnose','--intent',self.intent],capture_output=True,text=True,timeout=15)
    def diagnostic_bytes(self):
        return tuple(p.read_bytes() for p in (Path(self.intent),self.metadata,self.cp,self.authority))
    def test_diagnose_title_rewrite_and_null_identity_is_readonly(self):
        # exec/argv verification can precede Node's module initialization. Wait
        # for the owned fixture to install its handler before sending SIGUSR1.
        signal_ready=self.root/'signal-handler-ready'
        self.entry.write_text('import fs from "node:fs";process.on("SIGUSR1",()=>{process.title="zcode-cli"});'
                              + 'fs.writeFileSync(' + json.dumps(str(signal_ready)) + ',"ready");setInterval(()=>{},1000);')
        self.runner()
        deadline=time.monotonic()+3
        while not signal_ready.is_file() and self.proc.poll() is None and time.monotonic()<deadline:
            time.sleep(.02)
        self.assertTrue(signal_ready.is_file(),'owned Node fixture did not install its signal handler')
        self.assertIsNone(self.proc.poll(),'owned Node fixture exited before the signal')
        self.proc.send_signal(__import__('signal').SIGUSR1)
        for _ in range(100):
            command=subprocess.check_output(['/bin/ps','-ww','-p',str(self.proc.pid),'-o','command='],text=True).strip()
            if command=='zcode-cli':break
            time.sleep(.02)
        self.assertEqual(command,'zcode-cli')
        self.payloads['ctx_new']['result']['terminal']['agentIdentity']=None;self.save_responses();before=self.diagnostic_bytes()
        p=self.diagnose_consumer();self.assertEqual(p.returncode,0,p.stderr);out=json.loads(p.stdout)
        self.assertTrue(out['diagnostic_only']);self.assertFalse(out['ready_for_retry'])
        self.assertTrue({'missing_agentIdentity','title_rewritten','argv_not_proven'}<=set(out['statuses']))
        with self.assertRaises(ValueError):r.verify(self.intent)
        self.assertEqual(before,self.diagnostic_bytes())
    def test_diagnose_closed_process_remains_refused_and_readonly(self):
        self.runner();self.proc.terminate();self.proc.communicate(timeout=5)
        self.payloads['ctx_new']['result']['terminal'].update(connected=False,writable=False,agentIdentity=None);self.save_responses();before=self.diagnostic_bytes()
        p=self.diagnose_consumer();self.assertEqual(p.returncode,0,p.stderr);out=json.loads(p.stdout)
        self.assertTrue({'closed','runner_absent','argv_not_proven'}<=set(out['statuses']))
        self.assertTrue(out['diagnostic_only']);self.assertFalse(out['ready_for_retry'])
        with self.assertRaises(ValueError):r.verify(self.intent)
        self.assertEqual(before,self.diagnostic_bytes())
    def test_diagnose_known_live_still_not_retry_admission_and_model_guarded(self):
        self.runner();before=self.diagnostic_bytes();p=self.diagnose_consumer();self.assertEqual(p.returncode,0,p.stderr)
        out=json.loads(p.stdout);self.assertTrue(out['exact_argv_observed']);self.assertFalse(out['ready_for_retry']);self.assertEqual(before,self.diagnostic_bytes())
        c=sqlite3.connect(self.db);c.execute('UPDATE session_entry SET data=?',(json.dumps({'modelSelection':{'providerId':'wrong','modelId':'wrong','options':{'reasoningLevel':'max'}}}),));c.commit();c.close()
        self.assertEqual(self.diagnose_consumer().returncode,64);self.assertEqual(before,self.diagnostic_bytes())
        self.assertNotIn('worker-start',self.log.read_text())

if __name__=='__main__':unittest.main(verbosity=2)
