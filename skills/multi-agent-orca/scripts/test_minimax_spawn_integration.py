#!/usr/bin/env python3
"""完整生产spawn入口隔离消费者；Orca、ancestry、collector/clock均明确fixture。"""
import hashlib,json,os,shlex,subprocess,sys,unittest
from pathlib import Path
import test_minimax_memory_admission as unit
ROOT=Path(__file__).resolve().parent

PYTHON_SHIM=r'''import os,sys,runpy,json,subprocess
from pathlib import Path
args=sys.argv[1:];target=args[0] if args else ''
if target.endswith('mem_budget_probe.py'):
 sys.path.insert(0,str(Path(target).parent))
 import importlib.util
 spec=importlib.util.spec_from_file_location('fixture_shared_probe',target);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 raw=json.loads(Path(os.environ['E2E_RAW']).read_text());clock=iter((0.,0.,10.,10.,20.))
 m.collect_real=lambda:dict(raw)
 m.time.monotonic=lambda:next(clock,20.)
 m.time.sleep=lambda seconds:None
 if os.environ.get('E2E_SCENARIO')=='probe_input_drift':Path(os.environ['E2E_INPUT']).write_text('changed fixture input')
 sys.argv=args
 rc=m.main()
 Path(os.environ['E2E_PROBE_DONE']).write_text('fixture_collector_and_virtual_clock_only; not live authorization')
 raise SystemExit(rc)
if target.endswith('memory_task_admission.py') and 'render-launch' in args:
 scenario=os.environ.get('E2E_SCENARIO','')
 count_file=Path(os.environ['E2E_ROOT'])/'render-count'
 count=int(count_file.read_text())+1 if count_file.exists() else 1;count_file.write_text(str(count))
 if scenario=='guard_output_drift' and count>=2:
  print('python3 opaque-untrusted-guard');raise SystemExit(0)
 if scenario.startswith('late_'):
  cwd=Path(args[args.index('--execution-cwd')+1])
  if scenario=='late_git':subprocess.run(['/usr/bin/git','-C',str(cwd),'checkout','-b','fixture-drift'],check=True,capture_output=True)
  if scenario=='late_cwd':cwd.rename(cwd.with_name(cwd.name+'-retained'));cwd.mkdir()
  if scenario=='late_install':Path(os.environ['E2E_CHUNK']).write_text('fixture drift')
  if scenario=='late_input':Path(os.environ['E2E_INPUT']).write_text('fixture drift')
os.execv(os.environ['E2E_REAL_PYTHON'],[os.environ['E2E_REAL_PYTHON'],*args])
'''
ORCA_SHIM=r'''import sys,os,json,subprocess
from pathlib import Path
args=sys.argv[1:];root=Path(os.environ['E2E_ROOT']);project=os.environ['E2E_PROJECT'];ws=root/'orca-workspaces';ws.mkdir(exist_ok=True)
with (root/'orca-calls.jsonl').open('a') as f:f.write(json.dumps(args)+'\n')
def emit(result):print(json.dumps({'ok':True,'_meta':{'runtimeId':'fixture-runtime'},'result':result}))
def value(flag):return args[args.index(flag)+1]
def wt(path):return {'worktree':{'id':'fixture-repo::'+str(path),'path':str(path)}}
key=tuple(args[:2])
if key==('worktree','current'):emit(wt(project))
elif key==('worktree','ps'):emit({'worktrees':[]})
elif args==['status','--json']:emit({'runtime':{'reachable':True,'runtimeId':'fixture-runtime','appVersion':'1.4.9','capabilities':['terminal.multiplex.v1','orchestration.contract.v1']}})
elif key==('worktree','create'):
 path=ws/value('--name');subprocess.run(['/usr/bin/git','-C',project,'worktree','add','-q','-b',value('--name'),str(path),'HEAD'],check=True,capture_output=True);emit(wt(path))
elif key==('worktree','show'):
 ref=value('--worktree');path=ref.split('::',1)[-1].removeprefix('path:').removeprefix('id:');emit(wt(path))
elif key==('terminal','create'):
 ref=value('--worktree');cwd=ref.split('::',1)[-1].removeprefix('path:').removeprefix('id:');command=value('--command')
 (root/'terminal-boundary.json').write_text(json.dumps({'command':command,'cwd':cwd,'fixture':True}))
 result=subprocess.run(['bash','-c',command],cwd=cwd,env=os.environ,capture_output=True,text=True,timeout=15)
 (root/'execution.json').write_text(json.dumps({'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'fixture_only':True}))
 if result.returncode:print(result.stderr,file=sys.stderr);raise SystemExit(result.returncode)
 emit({'terminal':{'handle':'fixture-terminal'}})
elif key==('terminal','show'):emit({'terminal':{'handle':'fixture-terminal','connected':True,'writable':True,'orphaned':False,'exitCause':None}})
else:print('FIXTURE_UNEXPECTED_ORCA_CALL '+repr(args),file=sys.stderr);raise SystemExit(64)
'''

class MiniMaxSpawnIntegration(unittest.TestCase):
    artifact=unit.MiniMaxTests.artifact
    save=unit.MiniMaxTests.save
    git=unit.MiniMaxTests.git
    def setUp(self):
        unit.MiniMaxTests.setUp(self)
        self.project=self.cwd;self.fakebin=self.root/'fakebin';self.fakebin.mkdir()
        self.executable(self.fakebin/'python3',PYTHON_SHIM)
        self.executable(self.root/'fake-orca',ORCA_SHIM)
        ps=self.fakebin/'ps';ps.write_text('#!/bin/bash\ncase "$*" in *"-o ppid="*) echo 1;; *"-o comm="*) echo /isolated/codex;; *"-o args="*) echo codex;; *) exit 1;; esac\n');ps.chmod(0o700)
        personal=self.root/'personal.json';personal.write_text(json.dumps({'_schema_version':'1.3','quota_aware_routing':{'enabled':False},'concurrency':{'max_per_provider':1}}));personal.chmod(0o600)
        raw=self.root/'raw.json';raw.write_text(json.dumps(self.raw))
        self.env.update(E2E_REAL_PYTHON=sys.executable,E2E_ROOT=str(self.root),E2E_PROJECT=str(self.project),E2E_RAW=str(raw),E2E_INPUT=str(self.stdin),E2E_CHUNK=str(self.chunk),E2E_PROBE_DONE=str(self.root/'probe-done'),ORCA_CLI_COMMAND=str(self.root/'fake-orca'),MULTI_AGENT_ORCHESTRATION_PERSONAL_CONFIG=str(personal),SPAWN_WORKER_MEMORY_TASK_PROFILE=str(self.profile_path),PATH=str(self.fakebin)+os.pathsep+self.env['PATH'])
        for key in ('ORCA_CLI_BIN','ORCA_TERMINAL_HANDLE','GIT_DIR','GIT_WORK_TREE','MEM_BUDGET_FIXTURE_DIR','SPAWN_WORKER_MEM_BUDGET_BYTES'):self.env.pop(key,None)
        self.session='fixture-worker';self.report={}
    def tearDown(self):
        out=os.environ.get('MAO_MINIMAX_INTEGRATION_EVIDENCE')
        if out:
            path=Path(out);path.mkdir(parents=True,exist_ok=True);(path/(self._testMethodName+'.json')).write_text(json.dumps(self.report,indent=2)+'\n')
        self.tmp.cleanup()
    def executable(self,path,body):path.write_text('#!'+sys.executable+'\n'+body);path.chmod(0o700)
    def run_spawn(self,scenario='',profile=True):
        env={**self.env,'E2E_SCENARIO':scenario}
        if not profile:env.pop('SPAWN_WORKER_MEMORY_TASK_PROFILE')
        argv=['bash',str(ROOT/'spawn-worker.sh'),'--project',str(self.project),'--base-ref','unit','--branch',self.session,'--session',self.session,'--worker-backend','minimax-code','--command',self.command,'--allow-prompt-only-install-guard','isolated fixture only; no model','--allow-paths','marker','--verify-cmd','true','--require-verification','--no-trust-auto','--no-permission-auto','--no-permission-auto-bg','--no-external-imports-auto']
        p=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=70)
        calls=[json.loads(x) for x in (self.root/'orca-calls.jsonl').read_text().splitlines()] if (self.root/'orca-calls.jsonl').exists() else []
        lease_root=self.project/'.git/orchestration/provider-leases'
        leases=list(lease_root.rglob('*.json')) if lease_root.exists() else []
        worktrees=[str(x) for x in (self.root/'orca-workspaces').glob('*')] if (self.root/'orca-workspaces').exists() else []
        contexts=[str(x) for x in self.root.rglob('METADATA.json')]
        self.report={'fixture_sources':['fake Orca CLI','ps ancestry','collect_real replacement with frozenraw and virtual20second clock; actual same probe/evaluator/profile/binding code'],'command':argv,'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'orca_calls':calls,'worktrees':worktrees,'contexts':contexts,'lease_files':list(map(str,leases)),'lease_root_created':lease_root.exists(),'probe_fixture_used':(self.root/'probe-done').exists(),'execution':json.loads((self.root/'execution.json').read_text()) if (self.root/'execution.json').exists() else None}
        boundary=self.root/'terminal-boundary.json'
        if boundary.exists():self.report['terminal_boundary']=json.loads(boundary.read_text());launch=Path(self.report['terminal_boundary']['command'].removeprefix('bash '));self.report['launch_bytes']=launch.read_text() if launch.exists() else None
        return p,calls
    def assert_zero_new_resources(self,p,calls,exit):
        self.assertEqual(p.returncode,exit,p.stderr)
        self.assertFalse(any(x[:2] in [['worktree','create'],['terminal','create']] or x[0]=='orchestration' for x in calls),calls)
        self.assertEqual(self.report['worktrees'],[]);self.assertEqual(self.report['contexts'],[]);self.assertEqual(self.report['lease_files'],[]);self.assertFalse(self.report['lease_root_created'])
    def test_bad_profile_before_every_resource(self):
        self.obj['schema']='unknown';self.save();p,c=self.run_spawn();self.assert_zero_new_resources(p,c,64)
    def test_bad_installation_before_every_resource(self):
        (self.install/'current').write_text('..');p,c=self.run_spawn();self.assert_zero_new_resources(p,c,64)
    def test_input_drift_at_shared_probe_before_resources(self):
        p,c=self.run_spawn('probe_input_drift');self.assert_zero_new_resources(p,c,4);self.assertTrue(self.report['probe_fixture_used']);self.assertIn('binding drift',p.stderr)
    def test_native_critical_shared_probe_zero_resources(self):
        self.raw['kernel_pressure']='4\n';Path(self.env['E2E_RAW']).write_text(json.dumps(self.raw));p,c=self.run_spawn();self.assert_zero_new_resources(p,c,4);self.assertTrue(self.report['probe_fixture_used']);self.assertIn('native pressure critical/unknown',p.stderr)
    def test_success_complete_entry_one_start_exact_native_execution(self):
        p,c=self.run_spawn();self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(sum(x[:2]==['worktree','create'] for x in c),1);self.assertEqual(sum(x[:2]==['terminal','create'] for x in c),1)
        self.assertFalse(any(x[:2] in [['terminal','send'],['terminal','wait']] or x[0]=='orchestration' for x in c),c)
        result=self.report['execution'];self.assertEqual(result['exit'],0);nonce=json.loads(result['stdout']);self.assertEqual(nonce['stdin'],'isolated nonce input\n');self.assertEqual(nonce['args'],['exec','--permission','full','--model','minimax/unit','--timeout','20m','--max-steps','60','--input','-']);self.assertEqual(nonce['heap'],2150629376)
        self.assertIn('budget=3221225472 slots=1',p.stdout);self.assertIn('exec-bound',self.report['launch_bytes']);self.assertIn('--execution-cwd-binding',self.report['launch_bytes'])
    def test_fresh_guard_output_drift_rejected_before_terminal(self):
        p,c=self.run_spawn('guard_output_drift');self.assertEqual(p.returncode,64,p.stderr);self.assertIn('MINIMAX_MEMORY_LAUNCH_GUARD_MISMATCH',p.stderr);self.assertTrue(self.report['worktrees']);self.assertFalse(any(x[:2]==['terminal','create'] for x in c),c)
    def test_late_git_drift_has_owned_worktree_but_zero_terminal(self):self.late('late_git')
    def test_late_cwd_drift_has_owned_worktree_but_zero_terminal(self):self.late('late_cwd')
    def test_late_install_drift_has_owned_worktree_but_zero_terminal(self):self.late('late_install')
    def test_late_input_drift_has_owned_worktree_but_zero_terminal(self):self.late('late_input')
    def late(self,kind):
        p,c=self.run_spawn(kind);self.assertEqual(p.returncode,64,p.stderr);self.assertEqual(sum(x[:2]==['worktree','create'] for x in c),1);self.assertFalse(any(x[:2]==['terminal','create'] or x[0]=='orchestration' for x in c),c);self.assertTrue(self.report['worktrees'])
    def test_legacy_default_three_GiB_highswap_still_denied(self):
        p,c=self.run_spawn(profile=False);self.assert_zero_new_resources(p,c,4);self.assertIn('SPAWN_WORKER_MEM_BUDGET_DENIED',p.stderr)

if __name__=='__main__':unittest.main(verbosity=2)
