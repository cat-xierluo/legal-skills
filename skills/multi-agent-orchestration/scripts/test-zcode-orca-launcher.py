#!/usr/bin/env python3
"""Real subprocess consumers of the native launch bridge; never start a model."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

BRIDGE=Path(__file__).with_name("zcode-orca-launcher.py")
class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name).resolve()
        self.requests=self.root/"requests"; self.requests.mkdir(mode=0o700)
        self.wt=self.root/"worktree"; self.wt.mkdir()
        self.env=dict(os.environ, ORCA_TERMINAL_HANDLE="term-native",ORCA_WORKTREE_ID="wt-1")
        for cmd in (["git","init","-b","worker",str(self.wt)], ["git","-C",str(self.wt),"-c","user.name=Fixture","-c","user.email=fixture@example.invalid","commit","--allow-empty","-m","fixture"]):
            subprocess.run(cmd,check=True,capture_output=True)
        context=self.wt/".claude"/"agent-sessions"/"session-1";context.mkdir(parents=True)
        self.zcode=self.root/"zcode"
        self.zcode.write_text('#!/usr/bin/env python3\nimport os,json,sys\nprint(json.dumps({"argv":sys.argv[1:],"context":os.environ.get("WORKER_SESSION_CONTEXT"),"kept":os.environ.get("KEPT"),"handle":os.environ.get("ORCA_TERMINAL_HANDLE")}))\n'); self.zcode.chmod(0o700)
        authroot=self.root/"agent-authority";authroot.mkdir(mode=0o700)
        self.authority=authroot/"launch.json"
        self.authority.write_text(json.dumps({"schema":"multi-agent-orchestration.authority-receipt.v1","session":"session-1","worktree":str(self.wt),"branch":"worker"}));self.authority.chmod(0o600)
        self.command=f"env WORKER_SESSION_CONTEXT={context} KEPT=retained {self.zcode} --mode build"
        self.launch=context/"launch.sh"
        self.metadata=context/"METADATA.json"
        self.meta={"schema":"multi-agent-orchestration.worktree-metadata.v1","worktree":str(self.wt),"branch":"worker","session":{"id":"session-1","context":str(context),"orca":{"worktree_id":"wt-1","runtime_id":"runtime-1","terminal_handle":""}},"runtime":{"worker_backend":"zcode-cli","harness_authority":{"worker_backend":"zcode-cli"},"command":self.command},"execution_authority":{"authority_receipt_file":str(self.authority),"authority_receipt_sha256":hashlib.sha256(self.authority.read_bytes()).hexdigest()}}
        self.save()
        self.orca=self.root/"orca"
        self.orca.write_text('#!/usr/bin/env python3\nimport json,sys\na=sys.argv[1:]\nif a[0]=="status":r={"runtime":{"reachable":True,"runtimeId":"runtime-1","appVersion":"1.4.218"}}\nelif a[:2]==["worktree","show"]:r={"worktree":{"id":"wt-1","path":'+repr(str(self.wt))+'}}\nelif a[:2]==["terminal","show"]:r={"terminal":{"handle":"term-native","worktreeId":"wt-1"}}\nelse:raise SystemExit(90)\nprint(json.dumps({"ok":True,"_meta":{"runtimeId":"runtime-1"},"result":r}))\n');self.orca.chmod(0o700)
    def tearDown(self):self.tmp.cleanup()
    def save(self):
        self.meta["runtime"]["command"]=self.command
        self.metadata.write_text(json.dumps(self.meta))
        quote=subprocess.run(["/bin/bash","-c",'printf %q "$1"',"_",self.command],check=True,capture_output=True).stdout
        self.launch.write_bytes(b"#!/bin/bash\n# fixture PM wrapper\nexec bash -c "+quote+b"\n");self.launch.chmod(0o700)
    def run_cli(self,*args,env=None,cwd=None):
        return subprocess.run([sys.executable,str(BRIDGE),*map(str,args)],env=env or self.env,cwd=cwd or self.wt,capture_output=True,text=True)
    def prepare(self):
        p=self.run_cli("prepare","--requests-root",self.requests,"--metadata",self.metadata,"--authority",self.authority,"--orca-bin",self.orca,"--runtime-id","runtime-1","--worktree-id","wt-1","--run-id","run-1","--task-id","task-1","--coordinator-handle","term-pm")
        self.assertEqual(p.returncode,0,p.stderr)
        self.request=Path(json.loads(p.stdout)["request_file"])
        return self.request
    def launch_cli(self,*argv,env=None,cwd=None):return self.run_cli("launch","--requests-root",self.requests,"--default-zcode",self.zcode,"--",*argv,env=env,cwd=cwd)
    def alter(self,**values):
        r=json.loads(self.request.read_text());r.update(values);self.request.write_text(json.dumps(r))
    def receipt(self,handle="term-native",state="ready"):
        p=self.root/"receipt.json";p.write_text(json.dumps({"ok":True,"_meta":{"runtimeId":"runtime-1"},"result":{"state":state,"runId":"run-1","taskId":"task-1","dispatchId":"disp-1","effects":[{"kind":"worktree","action":"reused","id":"wt-1"},{"kind":"terminal","role":"agent","action":"created","id":handle}]}}));return p
    def test_real_consumer_preserves_wrapper_and_binds_created(self):
        self.prepare();p=self.launch_cli("--mode","yolo")
        self.assertEqual(p.returncode,0,p.stderr);out=json.loads(p.stdout)
        self.assertEqual(out["argv"],["--mode","build"]);self.assertEqual(out["kept"],"retained");self.assertEqual(out["context"],str(self.metadata.parent))
        p=self.run_cli("bind-receipt","--requests-root",self.requests,"--request-file",self.request,"--receipt",self.receipt())
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)["terminal_ownership"],"created")
        self.assertEqual(len(list(self.requests.glob("*.bound.json"))),1)
    def test_no_request_fallback_preserves_native_argv(self):
        p=self.launch_cli("--mode","yolo","--flag=value");self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)["argv"],["--mode","yolo","--flag=value"])
    def test_claimed_request_never_falls_back(self):
        self.prepare();self.assertEqual(self.launch_cli().returncode,0);self.assertEqual(self.launch_cli().returncode,64)
    def test_expired_pending_never_falls_back(self):self.prepare();self.alter(expires_at=time.time()-1);self.assertEqual(self.launch_cli().returncode,64)
    def test_metadata_drift_refused(self):self.prepare();self.meta["branch"]="other";self.metadata.write_text(json.dumps(self.meta));self.assertEqual(self.launch_cli().returncode,64)
    def test_launch_drift_refused(self):self.prepare();self.launch.write_text("#!/bin/bash\necho untrusted\n");self.assertEqual(self.launch_cli().returncode,64)
    def test_authority_drift_refused(self):self.prepare();self.authority.write_text("{}");self.assertEqual(self.launch_cli().returncode,64)
    def test_environment_identity_refused(self):self.prepare();self.assertEqual(self.launch_cli(env=dict(self.env,ORCA_WORKTREE_ID="other")).returncode,64)
    def test_runtime_drift_refused(self):self.prepare();self.alter(runtime_id="runtime-other");self.assertEqual(self.launch_cli().returncode,64)
    def test_duplicate_pending_refused(self):
        self.prepare();other=self.requests/"11111111-1111-1111-1111-111111111111.request.json";other.write_bytes(self.request.read_bytes());other.chmod(0o600);self.assertEqual(self.launch_cli().returncode,64)
    def test_manifest_permissions_refused(self):self.prepare();self.request.chmod(0o644);self.assertEqual(self.launch_cli().returncode,64)
    def test_symlink_root_refused(self):
        alias=self.root/"alias";alias.symlink_to(self.requests,target_is_directory=True)
        self.assertEqual(self.run_cli("preflight","--requests-root",alias,"--app-version","1.4.218").returncode,64)
    def test_symlink_ancestor_refused(self):
        alias=self.root/"alias";alias.symlink_to(self.root,target_is_directory=True)
        self.assertEqual(self.run_cli("preflight","--requests-root",alias/"requests","--app-version","1.4.218").returncode,64)
    def test_unsupported_version_zero_side_effects(self):
        self.assertEqual(self.run_cli("preflight","--requests-root",self.requests,"--app-version","1.4.217").returncode,64);self.assertEqual(list(self.requests.iterdir()),[])
    def test_original_prompt_refused_before_request(self):
        self.command += " --prompt task";self.save();p=self.run_cli("prepare","--requests-root",self.requests,"--metadata",self.metadata,"--authority",self.authority,"--orca-bin",self.orca,"--runtime-id","runtime-1","--worktree-id","wt-1","--run-id","run-1","--task-id","task-1","--coordinator-handle","term-pm");self.assertEqual(p.returncode,64);self.assertEqual(list(self.requests.iterdir()),[])
    def test_environment_prompt_text_is_not_headless(self):self.command=self.command.replace("KEPT=retained","KEPT=--prompt");self.save();self.prepare();self.assertEqual(self.launch_cli().returncode,0)
    def test_native_prompt_refused(self):self.prepare();self.assertEqual(self.launch_cli("--prompt=task").returncode,64)
    def test_receipt_handle_mismatch_refused(self):
        self.prepare();self.assertEqual(self.launch_cli().returncode,0);p=self.run_cli("bind-receipt","--requests-root",self.requests,"--request-file",self.request,"--receipt",self.receipt("term-other"));self.assertEqual(p.returncode,64);self.assertEqual(len(list(self.requests.glob("*.claimed.json"))),1)
    def test_worktree_git_drift_refused(self):
        self.prepare();subprocess.run(["git","-C",str(self.wt),"checkout","-b","other"],check=True,capture_output=True);self.assertEqual(self.launch_cli().returncode,64)
    def test_manifest_duplicate_json_key_refused(self):
        self.prepare();self.request.write_text('{"schema":"x","schema":"y"}');p=self.launch_cli();self.assertEqual(p.returncode,64);self.assertNotIn("invalid",p.stderr)
    def test_other_workspace_fallback_without_consumption(self):
        self.prepare();p=self.launch_cli("--mode","yolo",cwd=self.root);self.assertEqual(p.returncode,0);self.assertTrue(self.request.exists())
    def test_unmatched_manifest_malformed_refuses(self):
        self.prepare();self.request.write_text("invalid");self.assertEqual(self.launch_cli(cwd=self.root).returncode,64)
    def test_concurrent_launch_claims_exactly_once(self):
        self.prepare()
        argv=[sys.executable,str(BRIDGE),'launch','--requests-root',str(self.requests),'--default-zcode',str(self.zcode),'--']
        processes=[subprocess.Popen(argv,cwd=self.wt,env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
        outputs=[p.communicate(timeout=15) for p in processes]
        self.assertEqual(sorted(p.returncode for p in processes),[0,64])
        self.assertEqual(len(list(self.requests.glob('*.claimed.json'))),1)
    def test_malformed_nonce_cannot_escape_request_root(self):
        self.prepare();self.alter(nonce='../outside');self.assertEqual(self.launch_cli().returncode,64)
        self.assertFalse((self.root/'outside.claimed.json').exists())
    def test_frozen_wrapper_must_execute_exact_command(self):
        self.launch.write_text('#!/bin/bash\necho unrelated\n');self.launch.chmod(0o700)
        p=self.run_cli('prepare','--requests-root',self.requests,'--metadata',self.metadata,'--authority',self.authority,'--orca-bin',self.orca,'--runtime-id','runtime-1','--worktree-id','wt-1','--run-id','run-1','--task-id','task-1','--coordinator-handle','term-pm')
        self.assertEqual(p.returncode,64);self.assertEqual(list(self.requests.iterdir()),[])
    def bind_ready(self):
        return self.run_cli('bind-receipt','--requests-root',self.requests,'--request-file',self.request,'--receipt',self.receipt())
    def test_bound_replay_is_refused_instead_of_ordinary_fallback(self):
        self.prepare();self.assertEqual(self.launch_cli().returncode,0);self.assertEqual(self.bind_ready().returncode,0)
        p=self.launch_cli('--mode','yolo');self.assertEqual(p.returncode,64);self.assertEqual(p.stdout,'');self.assertIn('request_already_consumed',p.stderr)
    def test_expired_bound_tombstone_still_refuses_replay(self):
        self.prepare();self.assertEqual(self.launch_cli().returncode,0);self.assertEqual(self.bind_ready().returncode,0)
        bound=next(self.requests.glob('*.bound.json'));r=json.loads(bound.read_text());r['expires_at']=time.time()-1;bound.write_text(json.dumps(r))
        self.assertEqual(self.launch_cli().returncode,64)
    def test_pending_receipt_refused_without_metadata_or_completion(self):
        self.prepare();self.assertEqual(self.launch_cli().returncode,0)
        p=self.run_cli('bind-receipt','--requests-root',self.requests,'--request-file',self.request,'--receipt',self.receipt(state='pending'))
        self.assertEqual(p.returncode,64);self.assertEqual(json.loads(self.metadata.read_text())['session']['orca']['terminal_handle'],'')
        self.assertFalse(self.authority.with_suffix('.completion.json').exists());self.assertEqual(len(list(self.requests.glob('*.claimed.json'))),1)
    def test_missing_receipt_state_refused(self):
        self.prepare();self.assertEqual(self.launch_cli().returncode,0)
        receipt=self.receipt();r=json.loads(receipt.read_text());r['result'].pop('state');receipt.write_text(json.dumps(r))
        p=self.run_cli('bind-receipt','--requests-root',self.requests,'--request-file',self.request,'--receipt',receipt)
        self.assertEqual(p.returncode,64)
    def test_explicit_new_session_can_follow_bound_same_worktree(self):
        self.prepare();self.assertEqual(self.launch_cli().returncode,0);self.assertEqual(self.bind_ready().returncode,0)
        old=json.loads(next(self.requests.glob('*.bound.json')).read_text())
        # 129 distinct archived sessions must not exhaust the active-request budget.
        import uuid
        for n in range(128):
            archived=dict(old,nonce=str(uuid.uuid4()),session='archive-'+str(n))
            path=self.requests/(archived['nonce']+'.bound.json');path.write_text(json.dumps(archived));path.chmod(0o600)
        context=self.metadata.parent.with_name('session-2');context.mkdir()
        self.metadata=context/'METADATA.json';self.launch=context/'launch.sh'
        self.meta['session']['id']='session-2';self.meta['session']['context']=str(context)
        self.command=self.command.replace('session-1','session-2')
        a=json.loads(self.authority.read_text());a['session']='session-2';self.authority=self.authority.with_name('new-launch.json');self.authority.write_text(json.dumps(a));self.authority.chmod(0o600)
        self.meta['execution_authority']['authority_receipt_file']=str(self.authority);self.meta['execution_authority']['authority_receipt_sha256']=hashlib.sha256(self.authority.read_bytes()).hexdigest()
        self.save();self.prepare();p=self.launch_cli();self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['context'],str(context))
    def register_fixture(self,fail=False,state="ready"):
        log=self.root/"rpc-log.jsonl"
        self.orca.write_text("""#!/usr/bin/env python3
import json,sys,subprocess,os
from pathlib import Path
a=sys.argv[1:]
with open(LOG,'a') as f:f.write(json.dumps(a)+'\\n')
if a[0]=='status':r={'runtime':{'reachable':True,'runtimeId':'runtime-1','appVersion':'1.4.218'}}
elif a[:2]==['worktree','show']:r={'worktree':{'id':'wt-1','path':WT}}
elif a[:2]==['terminal','show']:r={'terminal':{'handle':'term-native','worktreeId':'wt-1'}}
elif a[:2]==['orchestration','worker-start']:
 if FAIL:
  print(json.dumps({'ok':False,'error':{'code':'task_not_startable'},'result':{'residualResources':[]}}));raise SystemExit(1)
 assert '--agent' in a and a[a.index('--agent')+1]=='zcode' and '--terminal' not in a
 p=subprocess.run([sys.executable,BRIDGE,'launch','--requests-root',REQUESTS,'--default-zcode',ZCODE,'--','--mode','yolo'],cwd=WT,env=dict(os.environ,ORCA_TERMINAL_HANDLE='term-native',ORCA_WORKTREE_ID='wt-1'),capture_output=True)
 if p.returncode:sys.stderr.buffer.write(p.stderr);raise SystemExit(p.returncode)
 r={'state':RECEIPT_STATE,'runId':'run-1','taskId':'task-1','dispatchId':'disp-1','effects':[{'kind':'worktree','action':'reused','id':'wt-1'},{'kind':'terminal','role':'agent','action':'created','id':'term-native'}]}
elif a[:2]==['orchestration','dispatch-show']:r={'dispatch':{'id':'disp-1','task_id':'task-1','assignee_handle':'term-native','run_id':'run-1','capability_hash':'a'*64,'process_incarnation':'process-1'}}
else:raise SystemExit(90)
print(json.dumps({'ok':True,'_meta':{'runtimeId':'runtime-1'},'result':r}))
""".replace('LOG',repr(str(log))).replace('WT',repr(str(self.wt))).replace('BRIDGE',repr(str(BRIDGE))).replace('REQUESTS',repr(str(self.requests))).replace('ZCODE',repr(str(self.zcode))).replace('FAIL',repr(fail)).replace('RECEIPT_STATE',repr(state)))
        return log
    def run_register(self,*args):
        return subprocess.run(['bash',str(BRIDGE.with_name('orca-supervised-register.sh')),'--agent','zcode','--worktree-id','wt-1','--metadata-file',str(self.metadata),'--launch-request-root',str(self.requests),'--authority-receipt',str(self.authority),'--task-id','task-1','--run-id','run-1','--coordinator-handle','term-pm','--runtime-id','runtime-1',*args],env=dict(self.env,ORCA_CLI_COMMAND=str(self.orca)),capture_output=True,text=True)
    def test_native_register_real_consumer_writes_created_completion(self):
        log=self.register_fixture();p=self.run_register()
        self.assertEqual(p.returncode,0,p.stderr)
        m=json.loads(self.metadata.read_text());self.assertEqual(m['session']['orca']['terminal_handle'],'term-native');self.assertEqual(m['session']['orca']['supervised']['terminal_ownership'],'created')
        self.assertEqual(m['session']['orca']['supervised']['dispatch_bind'],'ok')
        self.assertEqual(m['session']['orca']['tui_ready_method'],'orca_native_worker_start_fresh_composer')
        completion=json.loads(Path(m['execution_authority']['completion_authority_file']).read_text());self.assertEqual(completion['terminal_handle'],'term-native')
        calls=[json.loads(x) for x in log.read_text().splitlines()]
        self.assertEqual(sum(x[:2]==['orchestration','worker-start'] for x in calls),1)
        self.assertFalse(any(x[:2]==['terminal','create'] or x[:2]==['terminal','send'] for x in calls))
    def test_native_register_pending_receipt_never_writes_completion(self):
        log=self.register_fixture(state='pending');p=self.run_register();self.assertNotEqual(p.returncode,0)
        self.assertFalse(self.authority.with_suffix('.completion.json').exists())
        self.assertEqual(json.loads(self.metadata.read_text())['session']['orca']['terminal_handle'],'')
        self.assertNotIn('ORCAREG_WORKER_REGISTERED',p.stderr)
        calls=[json.loads(x) for x in log.read_text().splitlines()]
        self.assertEqual(sum(x[:2]==['orchestration','worker-start'] for x in calls),1)
        self.assertFalse(any(x[:2]==['orchestration','dispatch-show'] for x in calls))
    def test_native_failure_no_automatic_worker_retry(self):
        log=self.register_fixture(fail=True);p=self.run_register();self.assertNotEqual(p.returncode,0)
        calls=[json.loads(x) for x in log.read_text().splitlines()];self.assertEqual(sum(x[:2]==['orchestration','worker-start'] for x in calls),1)
        self.assertFalse(any(x[:2]==['orchestration','task-update'] for x in calls));self.assertEqual(len(list(self.requests.glob('*.request.json'))),1)
    def test_native_terminal_selector_mutex_zero_mutations(self):
        log=self.register_fixture();p=self.run_register('--terminal-handle','term-external');self.assertEqual(p.returncode,64);self.assertFalse(log.exists())
    def test_native_reset_failed_selector_refused(self):
        log=self.register_fixture();p=self.run_register('--reset-failed');self.assertEqual(p.returncode,64);self.assertFalse(log.exists())
if __name__=="__main__":unittest.main()
