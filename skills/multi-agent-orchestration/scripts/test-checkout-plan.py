#!/usr/bin/env python3
"""隔离 Git/入口合同测试；不启动业务 Agent 或连接 Orca runtime。"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('checkout_plan',HERE/'checkout-plan.py')
policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(policy)


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='checkout-policy-');self.addCleanup(self.tmp.cleanup)
        self.repo=Path(self.tmp.name)/'repo';self.repo.mkdir()
        self.git('init','-b','main');self.git('config','user.name','Fixture');self.git('config','user.email','fixture@example.invalid')
        for s in ['技能/alpha','skills/beta','shared/lib']:
            p=self.repo/s;p.mkdir(parents=True);(p/'payload.txt').write_text('fixture\n')
            if s!='shared/lib':(p/'SKILL.md').write_text('---\nname: fixture\ndescription: test\n---\n')
        (self.repo/'AGENTS.md').write_text('root rules\n');self.git('add','.');self.git('commit','-m','fixture')
    def git(self,*args):return subprocess.check_output(['git','-C',str(self.repo),*args],stderr=subprocess.DEVNULL).decode().strip()
    def plan(self,**kwargs):
        args=dict(repo=self.repo,base='main',scopes=[],allow_paths=[],transport='git');args.update(kwargs);return policy.plan(**args)
    def test_infer_skill_roots_and_explicit_read_dependencies(self):
        p=self.plan(allow_paths=['技能/alpha/scripts/**']);self.assertEqual(p['scopes'],['技能/alpha']);self.assertEqual(p['mode'],'sparse')
        p=self.plan(scopes=['技能/alpha','shared/lib']);self.assertEqual(p['scopes'],['技能/alpha','shared/lib'])
    def test_review_or_ambiguous_write_scope_refused(self):
        for paths in [[],['.claude/agent-sessions/review/**'],['**']]:
            with self.assertRaisesRegex(ValueError,'CHECKOUT_SCOPE_REQUIRED'):self.plan(allow_paths=paths)
    def test_hidden_skill_repository_cannot_fall_back_to_full(self):
        self.git('rm','-r','技能','skills')
        target=self.repo/'.claude/skills/alpha';target.mkdir(parents=True)
        (target/'SKILL.md').write_text('---\nname: alpha\ndescription: fixture\n---\n')
        self.git('add','.');self.git('commit','-m','hidden skill fixture')
        self.assertEqual(self.plan(allow_paths=['.claude/skills/alpha/**'])['mode'],'sparse')
        with self.assertRaisesRegex(ValueError,'CHECKOUT_SCOPE_REQUIRED'):self.plan()
    def test_explicit_checkout_cannot_omit_allowed_business_paths(self):
        with self.assertRaisesRegex(ValueError,'WRITE_SCOPE_OUTSIDE'):self.plan(scopes=['技能/alpha'],allow_paths=['skills/beta/scripts/**'])
        self.assertEqual(self.plan(scopes=['技能/alpha'],allow_paths=['技能/alpha/scripts/**','AGENTS.md','.claude/agent-sessions/a/**'])['mode'],'sparse')
    def test_orca_capability_missing_refuses_before_resources(self):
        before=self.git('for-each-ref')
        with self.assertRaisesRegex(ValueError,'PARKED_FOR_CHECKOUT_CAPABILITY'):self.plan(scopes=['技能/alpha'],transport='orca')
        self.assertEqual(self.git('for-each-ref'),before);self.assertEqual(len(self.git('worktree','list','--porcelain').split('worktree '))-1,1)
    def test_invalid_scopes_types_and_budget(self):
        for scopes in [['..'],['/tmp'],['技能/alpha/payload.txt'],['技能/alpha\n'],['.'],'技能/alpha']:
            with self.assertRaises((ValueError,subprocess.CalledProcessError)):self.plan(scopes=scopes)
        for b in [0,True,1,'512']:
            with self.assertRaisesRegex(ValueError,'CHECKOUT_'):self.plan(scopes=['技能/alpha'],budget_mib=b)
    def test_full_requires_bound_reason_and_source(self):
        for args in [dict(full_reason='integration'),dict(full_source='task'),dict(full_reason='integration',full_source='task',scopes=['技能/alpha'])]:
            with self.assertRaisesRegex(ValueError,'FULL_REQUIRES'):self.plan(**args)
        self.assertEqual(self.plan(full_reason='task requires whole-repo integration',full_source='approved integration task')['mode'],'full')
    def test_ordinary_repository_preserves_full_default(self):
        other=Path(self.tmp.name)/'ordinary';other.mkdir()
        subprocess.run(['git','init','-b','main',str(other)],check=True,capture_output=True)
        for key,value in [('user.name','Fixture'),('user.email','fixture@example.invalid')]:subprocess.run(['git','-C',str(other),'config',key,value],check=True)
        (other/'file').write_text('fixture');subprocess.run(['git','-C',str(other),'add','.'],check=True)
        subprocess.run(['git','-C',str(other),'commit','-m','fixture'],check=True,capture_output=True)
        self.assertEqual(policy.plan(other,'main',[],[],'orca')['mode'],'full')
    def shell_create(self,branch,existing=False):
        tree=Path(self.tmp.name)/'selected'
        if existing:self.git('branch',branch)
        # Real shared spawn helpers, real Git creator, no launcher/runtime side effects.
        env={**os.environ,'SCRIPT_DIR':str(HERE),'PROJECT_DIR':str(self.repo),'WORKTREE':str(tree),'BRANCH':branch}
        script='''set -euo pipefail
BASE_REF=main; LIGHTWEIGHT_MODE=0; PROJECT_IS_GIT=1; NO_ORCA_MODE=1
BORROW_EXISTING_WORKTREE=""; CHECKOUT_BUDGET_MIB=512; CHECKOUT_FULL_REASON=""; CHECKOUT_FULL_SOURCE=""
CHECKOUT_SCOPES=('技能/alpha' 'shared/lib'); ALLOW_PATHS=(); DRY_RUN=0
source "$SCRIPT_DIR/spawn-worker-checkout.sh"
run() { "$@"; }
spawn_worker_checkout_preflight
spawn_worker_create_sparse
spawn_worker_checkout_verify
'''
        p=subprocess.run(['/bin/bash','-c',script],env=env,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr);self.assertTrue((tree/'技能/alpha/payload.txt').is_file());self.assertTrue((tree/'shared/lib/payload.txt').is_file());self.assertTrue((tree/'AGENTS.md').is_file());self.assertFalse((tree/'skills/beta/payload.txt').exists())
        self.assertEqual(subprocess.check_output(['git','-C',str(tree),'status','--porcelain']).decode(),'')
        self.assertEqual(self.git('rev-parse',branch),self.git('rev-parse','main'))
        return tree
    def test_real_spawn_creation_segment_sparse_new_branch(self):self.shell_create('new-worker')
    def test_real_spawn_creation_segment_existing_branch_not_reset(self):self.shell_create('existing-worker',True)
    def test_borrowed_sparse_scope_and_identity(self):
        tree=self.shell_create('borrowed')
        self.assertEqual(self.plan(scopes=['技能/alpha'],transport='orca',borrowed=str(tree))['mode'],'sparse')
        with self.assertRaisesRegex(ValueError,'BORROWED_SCOPE_MISMATCH'):self.plan(scopes=['skills/beta'],transport='orca',borrowed=str(tree))
    def test_wave_missing_scope_fails_before_rpc(self):
        manifest=Path(self.tmp.name)/'wave.json';manifest.write_text(json.dumps({'project':str(self.repo),'tasks':[{'key':'review','spec':'read target'}]}))
        p=subprocess.run(['python3',str(HERE/'checkout-plan.py'),'--wave-manifest',str(manifest)],capture_output=True,text=True)
        self.assertEqual(p.returncode,64);self.assertIn('CHECKOUT_SCOPE_REQUIRED',p.stderr)
    def test_wave_implicit_non_git_project_refused_explicit_preserved(self):
        caller=Path(self.tmp.name)/'non-git';caller.mkdir()
        manifest=caller/'wave.json';data={'tasks':[{'key':'review','checkout':{'scopes':['技能/alpha']}}]}
        manifest.write_text(json.dumps(data))
        command=['python3',str(HERE/'checkout-plan.py'),'--wave-manifest',str(manifest)]
        p=subprocess.run(command,cwd=caller,capture_output=True,text=True)
        self.assertEqual(p.returncode,64);self.assertIn('CHECKOUT_WAVE_PROJECT_REQUIRED',p.stderr)
        data['project']=str(caller);manifest.write_text(json.dumps(data))
        p=subprocess.run(command,cwd=caller,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['mode'],'non-Git-context')
    def test_shell_early_orca_gate_does_not_call_creator_or_rpc(self):
        env={**os.environ,'SCRIPT_DIR':str(HERE),'PROJECT_DIR':str(self.repo)}
        script='''set -euo pipefail
BASE_REF=main; BRANCH=worker; LIGHTWEIGHT_MODE=0; PROJECT_IS_GIT=1; NO_ORCA_MODE=0
BORROW_EXISTING_WORKTREE=""; CHECKOUT_BUDGET_MIB=512; CHECKOUT_FULL_REASON=""; CHECKOUT_FULL_SOURCE=""
CHECKOUT_SCOPES=('技能/alpha'); ALLOW_PATHS=()
source "$SCRIPT_DIR/spawn-worker-checkout.sh"
orca_cli() { echo unexpected-rpc >&2; exit 99; }
spawn_worker_checkout_preflight
'''
        p=subprocess.run(['/bin/bash','-c',script],env=env,capture_output=True,text=True)
        self.assertEqual(p.returncode,64);self.assertIn('PARKED_FOR_CHECKOUT_CAPABILITY',p.stderr);self.assertNotIn('unexpected-rpc',p.stderr)


if __name__=='__main__':unittest.main(verbosity=2)
