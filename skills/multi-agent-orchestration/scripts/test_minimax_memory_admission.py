#!/usr/bin/env python3
"""隔离MiniMax同门/完整闭包/固定Node执行消费者，无模型或Orca。"""
import base64,copy,hashlib,json,os,pty,shlex,shutil,subprocess,sys,time,unittest
from pathlib import Path
from unittest.mock import patch
import memory_task_admission as a
import minimax_memory_binding as mm
import mem_budget_probe as probe
import test_memory_task_admission as old
ROOT=Path(__file__).resolve().parent
GIB=1024**3

class MiniMaxTests(unittest.TestCase):
    def setUp(self):
        old.MemoryTaskAdmissionTests.setUp(self)
        self.obj['kind']='bounded_minimax_unmeasured';self.obj.pop('measurement')
        contract={'kind':'bounded_minimax_contract','task_id':self.obj['task_id'],'workload':'standard_library_preview_or_readonly_routing_no_build_browser_video_server_install','rss_measurement':'not_measured','whole_worker_budget_bytes':3*GIB,'scope_enforcement':'original_PM_contract_not_process_sandbox'}
        self.obj['minimax_contract']=self.artifact('contract',contract);self.save()
        self.install=self.root/'install';(self.install/'bin').mkdir(parents=True);self.release=self.install/'releases'/'unit';self.release.mkdir(parents=True)
        (self.install/'current').write_text('unit\n');(self.install/'bin/mcode').write_text(mm.WRAPPER)
        self.node=str(Path(shutil.which('node')).resolve());(self.release/'.mcode-launcher').write_text(mm.LAUNCHER.format(node="'"+self.node+"'"))
        self.entry=self.release/'lib/node_modules/@minimax-ai/code/cli.js';self.entry.parent.mkdir(parents=True)
        self.entry.write_text('const fs=require("fs"),v8=require("v8");console.log(JSON.stringify({nonce:"isolated-only",args:process.argv.slice(2),stdin:process.stdin.isTTY?null:fs.readFileSync(0,"utf8"),tty:!!process.stdin.isTTY,heap:v8.getHeapStatistics().heap_size_limit}));')
        self.chunk=self.entry.parent/'chunk.js';self.chunk.write_text('module.exports=1;')
        self.stdin=self.root/'input.txt';self.stdin.write_text('isolated nonce input\n')
        self.command="bash -lc "+shlex.quote(str(self.install/'bin/mcode')+' exec --permission full --model minimax/unit --timeout 20m --max-steps 60 --input - < '+str(self.stdin))
        self.cwd=self.root/'worktree';self.cwd.mkdir()
        self.git('init','-b','unit');(self.cwd/'marker').write_text('unit');self.git('add','marker');self.git('-c','user.name=Unit','-c','user.email=unit@example.invalid','commit','-m','unit')
        self.branch=self.git('branch','--show-current');self.head=self.git('rev-parse','HEAD');self.common=self.git('rev-parse','--path-format=absolute','--git-common-dir')
        self.env.pop('NODE_PATH',None);self.env.pop('SPAWN_WORKER_NODE_MAX_OLD_SPACE_MB',None)
    def tearDown(self):self.tmp.cleanup()
    artifact=old.MemoryTaskAdmissionTests.artifact
    save=old.MemoryTaskAdmissionTests.save
    profile=old.MemoryTaskAdmissionTests.profile
    samples=old.MemoryTaskAdmissionTests.samples
    def git(self,*args):
        p=subprocess.run(['/usr/bin/git','-C',str(self.cwd),*args],capture_output=True,text=True,timeout=5);self.assertEqual(p.returncode,0,p.stderr);return p.stdout.strip()
    def bind(self,command=None):return a.bind_spawn(self.profile(),command or self.command,'minimax-code',ROOT,self.env)
    def decide(self,rows=None):return a.apply_profile(self.profile(),rows or self.samples(),3*GIB,probe.evaluate)
    def test_floor_unmeasured_stable_positive(self):
        p=self.decide();self.assertEqual(p['slots'],1);self.assertEqual(p['task_admission']['budget_floor_bytes'],3*GIB);self.assertIsNone(p['task_admission']['whole_worker_rss_cap']);self.assertEqual(p['task_admission']['whole_worker_rss_measurement'],'not_measured')
        for b in (0,2*GIB):
            with self.assertRaises(a.AdmissionError):a.apply_profile(self.profile(),self.samples(),b,probe.evaluate)
    def test_normal_requires_full_window_no_fake_high_swap(self):
        self.raw['vm_swapusage']='total = 1000M used = 10M free = 990M\n'
        self.assertEqual(self.decide(self.samples()[:1])['slots'],0);r=self.decide();self.assertEqual(r['slots'],1);self.assertFalse(r['task_admission']['high_swap_exception'])
    def test_critical_unknown_low_available(self):
        for value in ('4\n','3\n','',None):
            rows=self.samples();rows[1]['raw']['kernel_pressure']=value;self.assertEqual(self.decide(rows)['slots'],0)
        rows=self.samples();rows[1]['raw']['vm_stat']=self.raw['vm_stat'].replace('4194304','2');self.assertEqual(self.decide(rows)['slots'],0)
    def test_growth_rollback_keyword_and_oom(self):
        for count in ('13','11'):
            rows=self.samples();rows[1]['raw']['vm_stat']=self.raw['vm_stat'].replace('Swapouts: 12','Swapouts: '+count);self.assertEqual(self.decide(rows)['slots'],0)
        for value in ('warn\n','10% available\n'):
            rows=self.samples();rows[0]['raw']['memory_pressure']=value;self.assertEqual(self.decide(rows)['slots'],0)
        self.oom['events']=[{'type':'oom','at_epoch':self.now-1}];self.oom['checked_at_epoch']=self.now;self.obj['oom_history']=self.artifact('oom',self.oom);self.assertEqual(self.decide()['slots'],0)
    def test_heavy_and_host_not_generalized(self):
        self.obj['kind']='heavy';self.obj.pop('minimax_contract');self.assertEqual(self.decide()['slots'],0)
        self.obj['kind']='bounded_minimax_unmeasured';self.obj['execution']='codex_host_followup'
        with self.assertRaises(a.AdmissionError):self.profile()
    def test_pointer_original_dotdot_and_canonical_child(self):
        for value in ('..','.','../unit','unit/..','x'*129):
            (self.install/'current').write_text(value)
            with self.assertRaises(ValueError):mm.installation(str(self.install/'bin/mcode'),self.env)
    def test_preread_cap_no_read_bytes(self):
        p=self.root/'large';p.write_bytes(b'x'*2048)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('unbounded read forbidden')):
            with self.assertRaises(ValueError):mm.identity(p,max_bytes=1024)
        self.chunk.write_bytes(b'x'*2048)  # Actually exceed the complete release bound before hashing.
        with patch.object(mm,'MAX_BYTES',1024):
            with self.assertRaises(ValueError):mm.installation(str(self.install/'bin/mcode'),self.env)
    def test_cwd_original_branch_head_swap_rejected(self):
        bound=mm.cwd_identity(str(self.cwd),self.branch,self.head,self.common);self.git('checkout','-b','changed')
        with self.assertRaises(ValueError):mm.cwd_identity(str(self.cwd),bound['branch'],bound['head'],bound['common_dir']['path'])
    def test_native_cwd_and_opaque_wrappers_rejected(self):
        for option in ('--cwd /tmp','--cwd=/tmp','--directory /tmp','--config-dir /tmp'):
            cmd=self.command.replace(' exec ',' exec '+option+' ')
            with self.assertRaises(ValueError):mm.command_plan(cmd,'minimax-code',ROOT,self.env)
        for cmd in ('env '+self.command,'bash -lc '+shlex.quote('"A=1" '+str(self.install/'bin/mcode')),'bash -lc '+shlex.quote('$(true) '+str(self.install/'bin/mcode'))):
            with self.assertRaises(ValueError):mm.command_plan(cmd,'minimax-code',ROOT,self.env)
    def test_current_chunk_entry_launcher_mode_profile_drift(self):
        binding=self.bind();encoded=a.encode_binding(binding)
        for path in (self.chunk,self.entry,self.release/'.mcode-launcher',self.install/'current'):
            raw=path.read_bytes();path.write_bytes(raw+b'\n')
            with self.assertRaises((a.AdmissionError,ValueError)):a.verify_binding(str(self.profile_path),self.command,'minimax-code',ROOT,encoded)
            path.write_bytes(raw)
        self.chunk.chmod(0o666)
        with self.assertRaises(ValueError):self.bind()
        self.chunk.chmod(0o644);self.obj['serial_contract']['coordinator']='changed';self.save()
        with self.assertRaises(a.AdmissionError):a.verify_binding(str(self.profile_path),self.command,'minimax-code',ROOT,encoded)
    def test_environment_stdin_size_symlink_and_node_wrapper(self):
        for key in ('NODE_OPTIONS','NODE_PATH','LD_PRELOAD','DYLD_INSERT_LIBRARIES'):
            with self.assertRaises(ValueError):mm.command_plan(self.command,'minimax-code',ROOT,{**self.env,key:'override'})
        self.stdin.write_bytes(b'x'*(1024**2+1))
        with self.assertRaises(ValueError):self.bind()
        self.stdin.unlink();self.stdin.symlink_to(self.chunk)
        with self.assertRaises(ValueError):self.bind()
        fake=self.root/'node';fake.write_text('#!/bin/sh\nexit 0\n');self.stdin.unlink();self.stdin.write_text('nonce')
        (self.release/'.mcode-launcher').write_text(mm.LAUNCHER.format(node="'"+str(fake)+"'"))
        with self.assertRaises(ValueError):self.bind()
    def test_real_Node_batch_nonce_nativeargv_stdin_once(self):
        binding=self.bind();launch=a.render_launch(str(self.profile_path),self.command,'minimax-code',ROOT,a.encode_binding(binding),self.command,str(self.cwd),self.branch,self.head,self.common)
        proc=subprocess.run(shlex.split(launch),cwd=self.cwd,env=self.env,capture_output=True,text=True,timeout=15)
        self.assertEqual(proc.returncode,0,proc.stderr);out=json.loads(proc.stdout);self.assertEqual(out['stdin'],'isolated nonce input\n');self.assertEqual(out['args'],binding['minimax']['native_argv']);self.assertLess(out['heap'],2056*1024**2)
    def test_interactive_PTY_nativeargv_inherited(self):
        command=str(self.install/'bin/mcode')+' --model minimax/unit';binding=self.bind(command)
        launch=a.render_launch(str(self.profile_path),command,'minimax-code',ROOT,a.encode_binding(binding),command,str(self.cwd),self.branch,self.head,self.common)
        master,slave=pty.openpty()
        try:
            p=subprocess.Popen(shlex.split(launch),cwd=self.cwd,env=self.env,stdin=slave,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);out,err=p.communicate(timeout=15);self.assertEqual(p.returncode,0,err);self.assertTrue(json.loads(out)['tty']);self.assertEqual(json.loads(out)['args'],['--model','minimax/unit'])
        finally:os.close(master);os.close(slave)
    def test_late_git_and_fixture_env_guard(self):
        binding=self.bind();launch=a.render_launch(str(self.profile_path),self.command,'minimax-code',ROOT,a.encode_binding(binding),self.command,str(self.cwd),self.branch,self.head,self.common)
        self.git('checkout','-b','late')
        p=subprocess.run(shlex.split(launch),cwd=self.cwd,env=self.env,capture_output=True,text=True,timeout=15);self.assertEqual(p.returncode,64)
        self.git('checkout','unit')
        p=subprocess.run(shlex.split(launch),cwd=self.cwd,env={**self.env,'MEM_BUDGET_FIXTURE_DIR':str(self.root)},capture_output=True,text=True,timeout=15);self.assertEqual(p.returncode,64)
    def test_spawn_pregate_original_values_consumed(self):
        source=(ROOT/'spawn-worker.sh').read_text();self.assertIn('--pregate-branch "${pregate_branch:-}"',source);self.assertIn('--pregate-head "${pregate_head:-}"',source);self.assertIn('--pregate-common "${pregate_common:-}"',source)
    def test_owner_and_cwd_inode_replacement(self):
        real=Path.lstat
        def changed(path):
            value=real(path)
            if path==self.chunk:
                values=list(value);values[4]=os.getuid()+1
                return os.stat_result(values)
            return value
        with patch.object(Path,'lstat',changed):
            with self.assertRaises(ValueError):self.bind()
        before=mm.cwd_identity(str(self.cwd),self.branch,self.head,self.common)
        renamed=self.root/'moved';self.cwd.rename(renamed);self.cwd.mkdir()
        with self.assertRaises(ValueError):mm.cwd_identity(str(self.cwd),before['branch'],before['head'],before['common_dir']['path'])
    def test_native_binary_changed_and_internal_link_escape(self):
        binary=self.root/'node-copy';shutil.copy2(self.node,binary)
        launcher=self.release/'.mcode-launcher';launcher.write_text(mm.LAUNCHER.format(node="'"+str(binary)+"'"))
        binding=self.bind();encoded=a.encode_binding(binding)
        with binary.open('ab') as f:f.write(b'nonce-drift')
        with self.assertRaises(a.AdmissionError):a.verify_binding(str(self.profile_path),self.command,'minimax-code',ROOT,encoded)
        link=self.release/'escape';link.symlink_to(self.root/'input.txt')
        with self.assertRaises(ValueError):self.bind()
    def test_real_git_head_and_common_dir_drift(self):
        before=mm.cwd_identity(str(self.cwd),self.branch,self.head,self.common)
        (self.cwd/'marker').write_text('changed');self.git('add','marker');self.git('-c','user.name=Unit','-c','user.email=unit@example.invalid','commit','-m','changed')
        with self.assertRaises(ValueError):mm.cwd_identity(str(self.cwd),before['branch'],before['head'],before['common_dir']['path'])
        with self.assertRaises(ValueError):mm.cwd_identity(str(self.cwd),self.branch,self.git('rev-parse','HEAD'),str(self.root))
    def test_fake_git_spawn_render_consumes_early_expected(self):
        binding=self.bind();expected=a.encode_binding(binding)
        with patch.object(mm,'cwd_identity',side_effect=ValueError('original pregate identity mismatch')) as mocked:
            with self.assertRaises(ValueError):a.render_launch(str(self.profile_path),self.command,'minimax-code',ROOT,expected,self.command,str(self.cwd),'early-branch','f'*40,self.common)
            mocked.assert_called_once_with(str(self.cwd),'early-branch','f'*40,self.common)
    def test_same_verified_buffer_parser_no_unbounded_path_reads(self):
        with patch.object(Path,'read_text',side_effect=AssertionError('grammar must use verified buffer')),patch.object(Path,'read_bytes',side_effect=AssertionError('unbounded bytes forbidden')):
            actual=mm.installation(str(self.install/'bin/mcode'),self.env)
        wrapper=(self.install/'bin/mcode').read_bytes()
        self.assertEqual(actual['wrapper']['sha256'],hashlib.sha256(wrapper).hexdigest())
        self.assertEqual(actual['current']['sha256'],hashlib.sha256((self.install/'current').read_bytes()).hexdigest())
    def test_3MiB_growth_and_replacement_after_verified_buffer_refused(self):
        original=mm.read_verified
        for target in (self.install/'bin/mcode',self.install/'current',self.release/'.mcode-launcher'):
            raw=target.read_bytes()
            for mutation in ('grow','replace'):
                done=False
                def inject(path,limit):
                    nonlocal done
                    result=original(path,limit)
                    if Path(path)==target and not done:
                        done=True
                        if mutation=='grow':
                            with target.open('ab') as f:f.write(b'x'*(3*1024**2))
                        else:
                            replacement=target.with_name(target.name+'.replacement');replacement.write_bytes(raw+b'x'*(3*1024**2));replacement.replace(target)
                    return result
                try:
                    with patch.object(mm,'read_verified',inject),patch.object(Path,'read_text',side_effect=AssertionError('no unbounded second parse')):
                        with self.assertRaises(ValueError):mm.installation(str(self.install/'bin/mcode'),self.env)
                finally:target.write_bytes(raw)
    def test_verified_MiniMax_log_is_separate_from_light_label(self):
        source=(ROOT/'spawn-worker.sh').read_text();function=source[source.index('node_mem_cap_setup() {'):source.index('\ndependency_install_guard_setup\n',source.index('node_mem_cap_setup() {'))]
        binding=self.bind();env={**self.env,'SCRIPT_DIR':str(ROOT),'COMMAND':self.command,'MEMORY_TASK_PROFILE':str(self.profile_path),'MEMORY_TASK_ORIGINAL_COMMAND':self.command,'MEMORY_TASK_BINDING_B64':a.encode_binding(binding),'WORKER_BACKEND_CANONICAL':'minimax-code','WORKTREE':str(self.cwd),'pregate_branch':self.branch,'pregate_head':self.head,'pregate_common':self.common}
        proc=subprocess.run(['bash','-c',function+'\nnode_mem_cap_setup\n'],env=env,capture_output=True,text=True,timeout=15)
        self.assertEqual(proc.returncode,0,proc.stderr);self.assertIn('old-space=2048MB semi-space=1MB',proc.stdout);self.assertIn('whole-worker budget>=3GiB; RSS not_measured',proc.stdout);self.assertNotIn('total<=512MiB',proc.stdout)
    def test_installed_readonly_chain_heap_no_model(self):
        installed_mcode=shutil.which('mcode')
        if installed_mcode is None:
            self.skipTest('LIVE_INSTALLED_MINIMAX_NOT_VERIFIED: mcode is not installed; genuine fixture and spawn tests remain required')
        actual=mm.installation(installed_mcode,self.env);self.assertGreater(actual['closure_count'],1000);self.assertEqual(actual['node']['heap'],2150629376)

if __name__=='__main__':unittest.main()
