#!/usr/bin/env python3
"""Isolated Git and native-CLI consumers; no production RPC, worker or model."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPTS=Path(__file__).parent.resolve()
HELPER=SCRIPTS/"borrowed-worktree.py"
class BorrowedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        self.project=self.root/"project";self.project.mkdir()
        self.wt=self.root/"long-lived";self.bin=self.root/"bin";self.bin.mkdir()
        self.env=dict(os.environ,PATH=str(self.bin)+os.pathsep+os.environ['PATH'])
        self.cmd(['git','init','-b','main',str(self.project)])
        self.cmd(['git','-C',str(self.project),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--allow-empty','-m','baseline'])
        self.cmd(['git','-C',str(self.project),'worktree','add','-b','feature/external',str(self.wt),'HEAD'])
        self.state=self.root/'state.json'
        self.data={'processes':[], 'cwd':str(self.root),'terminals':[], 'runtime':'runtime-1','branch':'feature/external','truncated':False}
        self.save()
        self.ps=self.bin/'ps';self.ps.write_text('#!/usr/bin/env python3\nimport json,sys,os\ns=json.load(open('+repr(str(self.state))+'))\nif "lstart=" in sys.argv:print("fixture-owner-start")\nelse:print(str(os.getppid())+" 1 python3 borrowed-worktree.py"+"\\n"+"\\n".join(s["processes"]) if s["processes"] else str(os.getppid())+" 1 python3 borrowed-worktree.py")\n');self.ps.chmod(0o700)
        self.lsof=self.bin/'lsof';self.lsof.write_text('#!/usr/bin/env python3\nimport json\ns=json.load(open('+repr(str(self.state))+'))\nprint("p101\\nfcwd\\nn"+s["cwd"])\n');self.lsof.chmod(0o700)
        self.orca=self.bin/'orca';self.orca.write_text('#!/usr/bin/env python3\nimport json,sys\ns=json.load(open('+repr(str(self.state))+'))\na=sys.argv[1:]\nif a[0]=="status":r={"runtime":{"runtimeId":s["runtime"],"reachable":True,"appVersion":"1.4.218","capabilities":["terminal.multiplex.v1","orchestration.contract.v1"]}}\nelif a[:2]==["worktree","show"]:r={"worktree":{"id":"repo-1::external","path":'+repr(str(self.wt))+',"branch":s["branch"]}}\nelif a[:2]==["terminal","list"]:r={"terminals":s["terminals"],"truncated":s["truncated"]}\nelse:raise SystemExit(99)\nprint(json.dumps({"ok":True,"_meta":{"runtimeId":s["runtime"]},"result":r}))\n');self.orca.chmod(0o700)
        self.contract=self.root/'approved.json';self.snapshot()
    def tearDown(self):self.tmp.cleanup()
    def cmd(self,argv):return subprocess.run(argv,check=True,capture_output=True,env=self.env,text=True)
    def save(self):self.state.write_text(json.dumps(self.data))
    def cli(self,action,*extra):
        args=[sys.executable,str(HELPER),action]
        if action in ('snapshot','validate','acquire'):
            args+=['--project',str(self.project),'--worktree',str(self.wt),'--branch','feature/external','--orca-bin',str(self.orca),'--session','new-session']
            if action=='snapshot':args+=['--orca-worktree-id','repo-1::external','--runtime-id','runtime-1','--approved-by','fixture:user']
            else:args+=['--contract',str(self.contract)]
        elif action=='protect':args+=['--project',str(self.project),'--worktree',str(self.wt),'--branch','feature/external']
        elif action=='release':args+=['--worktree',str(self.wt),'--session','new-session','--owner-pid',str(os.getpid())]
        return subprocess.run([*args,*map(str,extra)],capture_output=True,text=True,env=self.env)
    def snapshot(self):
        p=self.cli('snapshot');self.assertEqual(p.returncode,0,p.stderr);self.contract.write_text(p.stdout);self.contract.chmod(0o600)
    def acquire(self):
        p=self.cli('acquire','--owner-pid',os.getpid());self.assertEqual(p.returncode,0,p.stderr);return p
    def refused(self,p,code):self.assertEqual(p.returncode,64,p.stderr);self.assertIn(code,p.stderr);self.assertTrue(self.wt.is_dir())
    def test_readonly_snapshot_no_ledger(self):
        self.assertEqual(self.cli('validate').returncode,0);self.assertFalse((self.project/'.git'/'agent-borrowed-worktrees').exists())
    def test_acquire_persists_protection_and_release_only_lock(self):
        self.acquire();self.assertTrue(json.loads(self.cli('protect').stdout)['protected'])
        self.assertEqual(self.cli('release').returncode,0);self.assertTrue(json.loads(self.cli('protect').stdout)['protected'])
        self.assertTrue(self.wt.is_dir());self.cmd(['git','-C',str(self.project),'show-ref','--verify','refs/heads/feature/external'])
    def test_atomic_lock_contention_refused(self):
        self.acquire();self.refused(self.cli('acquire','--owner-pid',os.getpid()),'borrow_lock_contended')
    def test_approved_dirty_content_can_enter(self):
        (self.wt/'draft.txt').write_text('approved private fixture');self.snapshot();self.acquire()
    def test_untracked_content_drift_refused(self):
        (self.wt/'draft.txt').write_text('approved');self.snapshot();(self.wt/'draft.txt').write_text('changed');self.refused(self.cli('acquire','--owner-pid',os.getpid()),'dirty_snapshot_drift')
    def test_staged_content_drift_refused(self):
        (self.wt/'draft.txt').write_text('approved');self.cmd(['git','-C',str(self.wt),'add','draft.txt']);self.snapshot();(self.wt/'draft.txt').write_text('changed');self.cmd(['git','-C',str(self.wt),'add','draft.txt']);self.refused(self.cli('validate'),'dirty_snapshot_drift')
    def test_mode_drift_refused(self):
        file=self.wt/'draft.txt';file.write_text('approved');file.chmod(0o600);self.snapshot();file.chmod(0o700);self.refused(self.cli('validate'),'dirty_snapshot_drift')
    def test_rename_delete_drift_refused(self):
        file=self.wt/'draft.txt';file.write_text('approved');self.snapshot();file.rename(self.wt/'renamed.txt');self.refused(self.cli('validate'),'dirty_snapshot_drift')
    def test_symlink_target_drift_refused(self):
        link=self.wt/'draft-link';link.symlink_to('approved');self.snapshot();link.unlink();link.symlink_to('changed');self.refused(self.cli('validate'),'dirty_snapshot_drift')
    def test_native_cli_writer_refused(self):
        self.data['processes']=['101 1 python3 /opt/minimax_code/cli.py'];self.data['cwd']=str(self.wt);self.save();self.refused(self.cli('acquire','--owner-pid',os.getpid()),'active_native_writer')
    def test_writer_descendant_refused(self):
        self.data['processes']=['101 1 mcode','102 101 python3 edit-file.py'];self.data['cwd']=str(self.wt);self.save();self.refused(self.cli('validate'),'active_native_writer')
    def test_native_cli_alias_refused(self):
        (self.bin/'mcode').write_text('fixture');(self.bin/'writer-alias').symlink_to(self.bin/'mcode')
        self.data['processes']=['101 1 '+str(self.bin/'writer-alias')];self.data['cwd']=str(self.wt);self.save();self.refused(self.cli('validate'),'active_native_writer')
    def test_writer_real_subdirectory_cwd_refused(self):
        (self.wt/'sub').mkdir();self.snapshot();self.data['processes']=['101 1 node /opt/zcode-cli/dist/cli.js'];self.data['cwd']=str(self.wt/'sub');self.save();self.refused(self.cli('validate'),'active_native_writer')
    def test_lsof_failure_is_unknown_refused(self):
        self.data['processes']=['101 1 mcode'];self.save();self.lsof.write_text('#!/bin/sh\nexit 1\n');self.refused(self.cli('validate'),'dependency_or_read_failed')
    def test_ps_failure_refused(self):
        self.ps.write_text('#!/bin/sh\nexit 1\n');self.refused(self.cli('validate'),'dependency_or_read_failed')
    def test_malformed_process_inventory_refused(self):
        self.data['processes']=['unreadable'];self.save();self.refused(self.cli('validate'),'process_schema_unknown')
    def test_active_orca_terminal_refused(self):
        self.data['terminals']=[{'handle':'term-existing','worktreeId':'repo-1::external','connected':True}];self.save();self.refused(self.cli('validate'),'active_orca_terminal')
    def test_truncated_orca_inventory_refused(self):
        self.data['truncated']=True;self.save();self.refused(self.cli('validate'),'terminal_inventory_incomplete')
    def test_runtime_drift_refused(self):
        self.data['runtime']='other';self.save();self.refused(self.cli('validate'),'runtime_drift')
    def test_branch_head_drift_refused(self):
        self.cmd(['git','-C',str(self.wt),'checkout','-b','other']);self.refused(self.cli('validate'),'worktree_registration_mismatch')
    def test_legacy_session_refused(self):
        p=self.wt/'.claude'/'agent-sessions'/'old';p.mkdir(parents=True);(p/'METADATA.json').write_text('{}');self.snapshot();self.refused(self.cli('acquire','--owner-pid',os.getpid()),'existing_mao_session_requires_recovery')
    def test_tracked_session_path_cannot_be_excluded(self):
        p=self.wt/'.claude'/'agent-sessions'/'new-session';p.mkdir(parents=True);(p/'TASK.md').write_text('tracked');self.cmd(['git','-C',str(self.wt),'add','.claude']);self.snapshot();self.refused(self.cli('validate'),'session_path_already_tracked')
    def test_own_new_session_is_excluded_only_after_initial_proof(self):
        self.acquire();p=self.wt/'.claude'/'agent-sessions'/'new-session';p.mkdir(parents=True);(p/'METADATA.json').write_text('new-context')
        out=self.cli('validate','--owner-pid',os.getpid());self.assertEqual(out.returncode,0,out.stderr)
        (self.wt/'new-unapproved.txt').write_text('drift');self.refused(self.cli('validate','--owner-pid',os.getpid()),'dirty_snapshot_drift')
    def test_corrupt_ledger_fails_closed(self):
        self.acquire();marker=next((self.project/'.git'/'agent-borrowed-worktrees').glob('*.json'));marker.write_text('invalid');self.refused(self.cli('protect'),'borrow_contract_unknown')
    def test_missing_ledger_is_not_treated_as_ordinary_tree(self):
        self.acquire();marker=next((self.project/'.git'/'agent-borrowed-worktrees').glob('*.json'));marker.unlink();self.refused(self.cli('protect'),'ownership_ledger_missing_retain')
    def test_ignored_asset_is_refused_without_reading_contents(self):
        (self.wt/'.gitignore').write_text('ignored/\n');(self.wt/'ignored').mkdir();(self.wt/'ignored'/'material.txt').write_text('private fixture')
        self.refused(self.cli('snapshot'),'ignored_assets_uncovered')
    def test_tracked_full_mode_drift_refused(self):
        file=self.wt/'tracked.txt';file.write_text('approved');self.cmd(['git','-C',str(self.wt),'add','tracked.txt']);self.snapshot();file.chmod(0o600);self.refused(self.cli('validate'),'dirty_snapshot_drift')
    def test_assume_unchanged_cannot_hide_content_drift(self):
        file=self.wt/'tracked.txt';file.write_text('approved');self.cmd(['git','-C',str(self.wt),'add','tracked.txt']);self.cmd(['git','-C',str(self.wt),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','tracked']);self.cmd(['git','-C',str(self.wt),'update-index','--assume-unchanged','tracked.txt']);self.snapshot();file.write_text('hidden drift');self.refused(self.cli('validate'),'dirty_snapshot_drift')
    def test_ordinary_tree_has_no_borrowed_protection(self):self.assertFalse(json.loads(self.cli('protect').stdout)['protected'])
    def test_clean_worktree_borrowed_retains_tree_branch_and_deps(self):
        self.acquire();self.cli('release');shared=self.root/'shared';shared.mkdir();(self.wt/'node_modules').symlink_to(shared)
        p=subprocess.run(['bash',str(SCRIPTS/'clean-worktree.sh'),'--project',str(self.project),'--worktree',str(self.wt),'--branch','feature/external','--session','new-session','--execute','--delete-branch','--force-delete-branch'],capture_output=True,text=True,env=self.env)
        self.assertEqual(p.returncode,0,p.stderr);self.assertTrue(self.wt.is_dir());self.assertTrue((self.wt/'node_modules').is_symlink());self.cmd(['git','-C',str(self.project),'show-ref','--verify','refs/heads/feature/external'])
    def test_new_session_extra_assets_are_not_glob_excluded(self):
        self.acquire();p=self.wt/'.claude'/'agent-sessions'/'new-session';p.mkdir(parents=True);(p/'private-input.txt').write_text('not a spawn artifact')
        self.refused(self.cli('validate','--owner-pid',os.getpid()),'session_assets_uncovered')
    def test_new_session_symlink_artifact_is_refused(self):
        self.acquire();p=self.wt/'.claude'/'agent-sessions'/'new-session';p.mkdir(parents=True);(p/'METADATA.json').symlink_to(self.state)
        self.refused(self.cli('validate','--owner-pid',os.getpid()),'session_assets_uncovered')
    def test_session_ancestor_symlink_refused(self):
        target=self.root/'external-context';target.mkdir();(self.wt/'.claude').symlink_to(target,target_is_directory=True);self.snapshot()
        self.refused(self.cli('validate'),'session_directory_untrusted')
    def test_acquire_requires_real_owner_pid_and_new_session(self):
        self.refused(self.cli('acquire'),'borrow_owner_required')
        self.assertFalse((self.project/'.git'/'agent-borrowed-worktrees').exists())
    def test_duplicate_process_rows_are_incomplete(self):
        self.data['processes']=['101 1 mcode','101 1 mcode'];self.save();self.refused(self.cli('validate'),'process_inventory_incomplete')
    def test_nonexistent_writer_cwd_is_unknown(self):
        self.data['processes']=['101 1 mcode'];self.data['cwd']=str(self.root/'not-present');self.save();self.refused(self.cli('validate'),'borrow_contract_unknown')
    def native_fixture(self):
        # Generate the actual shared launch wrapper. Stub only the terminal API;
        # the final gate and Git inventory remain real subprocess consumers.
        import hashlib,shlex
        self.requests=self.root/'requests';self.requests.mkdir(mode=0o700)
        self.context=self.wt/'.claude'/'agent-sessions'/'new-session'
        self.zcode=self.bin/'zcode';self.zcode.write_text('#!/usr/bin/env python3\nimport json,os,sys\nprint(json.dumps({"argv":sys.argv[1:],"context":os.environ.get("WORKER_SESSION_CONTEXT"),"kept":os.environ.get("KEPT")}))\n');self.zcode.chmod(0o700)
        self.command='env WORKER_SESSION_CONTEXT='+shlex.quote(str(self.context))+' KEPT=retained '+shlex.quote(str(self.zcode))+' --mode build'
        q=shlex.quote
        setup='\n'.join(['set -eu',f'python3 {q(str(HELPER))} acquire --project {q(str(self.project))} --worktree {q(str(self.wt))} --branch feature/external --orca-bin {q(str(self.orca))} --session new-session --contract {q(str(self.contract))} --owner-pid $$ >/dev/null',
          f'SCRIPT_DIR={q(str(SCRIPTS))}',f'WORKTREE={q(str(self.wt))}',f'PROJECT_DIR={q(str(self.project))}',f'BORROW_EXISTING_WORKTREE={q(str(self.contract))}',f'ORCA_CLI_BIN={q(str(self.orca))}',f'COMMAND={q(self.command)}',
          'SESSION=new-session','BRANCH=feature/external','DRY_RUN=0','ORCA_MODE=force_tmux',f'ORCA_ZCODE_NATIVE_REQUESTS={q(str(self.requests))}',
          'run() { :; }',f'source {q(str(SCRIPTS/"spawn-worker-launch.sh"))}','launch_worker_session'])
        p=subprocess.run(['bash','-c',setup],capture_output=True,text=True,env=self.env);self.assertEqual(p.returncode,0,p.stderr)
        lock=next((self.project/'.git'/'agent-borrowed-locks').glob('*.lock'))
        self.owner=json.loads((lock/'owner.json').read_text())['owner_pid']
        aroot=self.root/'agent-authority';aroot.mkdir(mode=0o700);self.authority=aroot/'launch.json'
        self.authority.write_text(json.dumps({'schema':'multi-agent-orchestration.authority-receipt.v1','session':'new-session','worktree':str(self.wt),'branch':'feature/external','degradation_source':'fixture:user'}));self.authority.chmod(0o600)
        self.metadata=self.context/'METADATA.json'
        self.meta={'schema':'multi-agent-orchestration.worktree-metadata.v1','project':str(self.project),'worktree':str(self.wt),'branch':'feature/external','worktree_ownership':'borrowed',
          'borrowed_worktree':{'contract_file':str(self.contract),'contract_sha256':hashlib.sha256(self.contract.read_bytes()).hexdigest(),'lock_owner_pid':self.owner},
          'session':{'id':'new-session','context':str(self.context),'orca':{'worktree_id':'repo-1::external','runtime_id':'runtime-1','terminal_handle':''}},
          'runtime':{'worker_backend':'zcode-cli','harness_authority':{'worker_backend':'zcode-cli'},'command':self.command},
          'execution_authority':{'authority_receipt_file':str(self.authority),'authority_receipt_sha256':hashlib.sha256(self.authority.read_bytes()).hexdigest()}}
        self.metadata.write_text(json.dumps(self.meta))
        t=self.orca.read_text().replace('else:raise SystemExit(99)', 'elif a[:2]==["terminal","show"]:r={"terminal":{"handle":"term-new","worktreeId":"repo-1::external"}}\nelse:raise SystemExit(99)')
        self.orca.write_text(t)
        self.native_env=dict(self.env,ORCA_TERMINAL_HANDLE='term-new',ORCA_WORKTREE_ID='repo-1::external')
    def bridge(self,action,*args):
        return subprocess.run([sys.executable,str(SCRIPTS/'zcode-orca-launcher.py'),action,'--requests-root',str(self.requests),*map(str,args)],cwd=self.wt,env=self.native_env,capture_output=True,text=True)
    def native_prepare(self):
        p=self.bridge('prepare','--metadata',self.metadata,'--authority',self.authority,'--orca-bin',self.orca,'--runtime-id','runtime-1','--worktree-id','repo-1::external','--run-id','run-1','--task-id','task-1','--coordinator-handle','term-pm')
        self.assertEqual(p.returncode,0,p.stderr);self.request=Path(json.loads(p.stdout)['request_file'])
    def native_launch(self):return self.bridge('launch','--default-zcode',self.zcode,'--','--mode','yolo')
    def native_bind(self,action='reused',extra=False):
        effects=[{'kind':'worktree','action':action,'id':'repo-1::external'},{'kind':'terminal','action':'created','role':'agent','id':'term-new'}]
        if extra:effects.append({'kind':'worktree','action':'created','id':'other-worktree'})
        receipt=self.root/'receipt.json';receipt.write_text(json.dumps({'ok':True,'_meta':{'runtimeId':'runtime-1'},'result':{'state':'ready','runId':'run-1','taskId':'task-1','dispatchId':'dispatch-1','effects':effects}}))
        return self.bridge('bind-receipt','--request-file',self.request,'--receipt',receipt)
    def test_native_borrowed_preserves_context_and_reused_resource(self):
        self.native_fixture();self.native_prepare();p=self.native_launch();self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout),{'argv':['--mode','build'],'context':str(self.context),'kept':'retained'})
        # Worker writes are expected after launch; binding must not rerun prelaunch dirty gate.
        (self.context/'STATUS.json').write_text('{"status":"done"}')
        (self.context/'RESULT.md').write_text('legitimate Task result')
        (self.wt/'worker-output.txt').write_text('legitimate fixture output')
        self.cmd(['git','-C',str(self.wt),'add','worker-output.txt'])
        self.cmd(['git','-C',str(self.wt),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','authorized Task output'])
        p=self.native_bind();self.assertEqual(p.returncode,0,p.stderr);self.assertTrue(self.wt.is_dir())
        self.assertEqual(len(list(self.requests.glob('*.bound.json'))),1)
    def test_native_borrowed_late_dirty_refuses_without_claim_or_model(self):
        self.native_fixture();self.native_prepare();(self.wt/'outside.txt').write_text('late drift');p=self.native_launch();self.refused(p,'borrowed_late_gate_refused')
        self.assertEqual(p.stdout,'');self.assertTrue(self.request.exists());self.assertEqual(list(self.requests.glob('*.claimed.json')),[])
    def test_native_borrowed_late_writer_refuses_without_model(self):
        self.native_fixture();self.native_prepare();self.data['processes']=['101 1 mcode'];self.data['cwd']=str(self.wt);self.save();p=self.native_launch();self.refused(p,'borrowed_late_gate_refused');self.assertEqual(p.stdout,'')
    def test_frozen_launch_itself_checks_dirty_with_old_bridge(self):
        self.native_fixture();(self.wt/'outside.txt').write_text('late drift')
        p=subprocess.run(['bash',str(self.context/'launch.sh')],env=self.native_env,cwd=self.wt,capture_output=True,text=True)
        self.refused(p,'dirty_snapshot_drift');self.assertEqual(p.stdout,'')
    def test_native_borrowed_created_effect_cannot_bind(self):
        self.native_fixture();self.native_prepare();self.assertEqual(self.native_launch().returncode,0)
        self.refused(self.native_bind(action='created'),'borrowed_native_worktree_ownership_unknown')
        self.assertEqual(list(self.requests.glob('*.bound.json')),[])
    def test_native_borrowed_extra_worktree_effect_cannot_bind(self):
        self.native_fixture();self.native_prepare();self.assertEqual(self.native_launch().returncode,0)
        self.refused(self.native_bind(extra=True),'borrowed_native_worktree_ownership_unknown')
    def test_native_borrowed_authority_source_cannot_be_self_attested(self):
        import hashlib
        self.native_fixture();a=json.loads(self.authority.read_text());a['degradation_source']='different-pm';self.authority.write_text(json.dumps(a))
        self.meta['execution_authority']['authority_receipt_sha256']=hashlib.sha256(self.authority.read_bytes()).hexdigest();self.metadata.write_text(json.dumps(self.meta))
        p=self.bridge('prepare','--metadata',self.metadata,'--authority',self.authority,'--orca-bin',self.orca,'--runtime-id','runtime-1','--worktree-id','repo-1::external','--run-id','run-1','--task-id','task-1','--coordinator-handle','term-pm')
        self.refused(p,'borrowed_authority_source_mismatch');self.assertEqual(list(self.requests.glob('*.request.json')),[])
    def test_faulty_native_create_rollback_cannot_remove_borrowed_tree(self):
        import shlex
        self.acquire();self.cli('release');mutation=self.root/'mutation.log'
        shell='\n'.join(['set -eu','SCRIPT_DIR='+shlex.quote(str(SCRIPTS)), 'source '+shlex.quote(str(SCRIPTS/'spawn-worker-orca.sh')), 'orca_git_common_dir() { git -C "$1" rev-parse --path-format=absolute --git-common-dir; }', 'orca_cli() { echo forbidden > '+shlex.quote(str(mutation))+'; }', 'orca_rollback_created_worktree repo-1::external '+shlex.quote(str(self.wt))+' feature/external 0 '+shlex.quote(str(self.project/'.git'))])
        p=subprocess.run(['bash','-c',shell],env=self.env,capture_output=True,text=True)
        self.assertEqual(p.returncode,1,p.stderr);self.assertIn('ROLLBACK_BORROWED_RETAINED',p.stderr);self.assertFalse(mutation.exists());self.assertTrue(self.wt.is_dir())
    def cleanup_fixture(self,missing=False):
        self.acquire();self.cli('release')
        p=self.wt/'.claude'/'agent-sessions'/'new-session';p.mkdir(parents=True)
        (p/'METADATA.json').write_text(json.dumps({'schema':'multi-agent-orchestration.worktree-metadata.v1','project':str(self.project),'worktree':str(self.wt),'branch':'feature/external','branch_lifecycle':'ephemeral-worker','base_ref':'main','worktree_ownership':'borrowed','session':{'id':'new-session'}}))
        with (self.project/'.git'/'info'/'exclude').open('a') as f:f.write('\n.claude/agent-sessions/\n')
        if missing:
            for file in (self.project/'.git'/'agent-borrowed-worktrees').iterdir():file.unlink()
        tip=self.cmd(['git','-C',str(self.wt),'rev-parse','HEAD']).stdout.strip()
        gh=self.bin/'gh';gh.write_text('#!/usr/bin/env python3\nimport json,sys\na=sys.argv[1:]\nassert a[:2]==["pr","list"],"no external mutations allowed"\nprint(json.dumps([{ "state":"MERGED","headRefName":"feature/external","headRefOid":'+repr(tip)+',"number":1,"url":"https://fixture.invalid/pr/1"}] if "merged" in a else []))\n');gh.chmod(0o700)
        return tip
    def test_pm_cleanup_retains_borrowed_even_ephemeral_argument(self):
        tip=self.cleanup_fixture();p=subprocess.run(['bash',str(SCRIPTS/'pm-cleanup-worker.sh'),'--project',str(self.project),'--worktree',str(self.wt),'--branch','feature/external','--session','new-session','--pr','1','--expected-tip',tip,'--delivery-mode','remote-pr','--delivery-commit',tip,'--execute'],capture_output=True,text=True,env=self.env)
        self.assertEqual(p.returncode,11,p.stderr);self.assertIn('borrowed-external-worktree',p.stdout);self.assertTrue(self.wt.is_dir())
    def test_pm_cleanup_missing_known_ledger_refuses(self):
        tip=self.cleanup_fixture(missing=True);p=subprocess.run(['bash',str(SCRIPTS/'pm-cleanup-worker.sh'),'--project',str(self.project),'--worktree',str(self.wt),'--branch','feature/external','--session','new-session','--pr','1','--expected-tip',tip,'--delivery-mode','remote-pr','--delivery-commit',tip,'--execute'],capture_output=True,text=True,env=self.env)
        self.assertEqual(p.returncode,2,p.stderr);self.assertIn('BORROWED_LEDGER_MISSING',p.stderr);self.assertTrue(self.wt.is_dir())
    def test_post_merge_cleanup_retains_borrowed(self):
        self.cleanup_fixture();p=subprocess.run(['bash',str(SCRIPTS/'post-merge-cleanup.sh'),'--project',str(self.project),'--worktree',str(self.wt),'--branch','feature/external','--session','new-session','--repo','fixture/project','--execute'],capture_output=True,text=True,env=self.env)
        self.assertEqual(p.returncode,2,p.stderr);self.assertIn('borrowed_external_worktree',p.stdout+p.stderr);self.assertTrue(self.wt.is_dir())
    def test_post_merge_missing_known_ledger_refuses(self):
        self.cleanup_fixture(missing=True);p=subprocess.run(['bash',str(SCRIPTS/'post-merge-cleanup.sh'),'--project',str(self.project),'--worktree',str(self.wt),'--branch','feature/external','--session','new-session','--repo','fixture/project','--execute'],capture_output=True,text=True,env=self.env)
        self.assertEqual(p.returncode,2,p.stderr);self.assertIn('borrowed_ownership_unknown',p.stdout+p.stderr);self.assertTrue(self.wt.is_dir())
if __name__=='__main__':unittest.main()
