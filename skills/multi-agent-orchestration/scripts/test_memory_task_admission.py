#!/usr/bin/env python3
"""隔离 profile/实际 CLI/真实 Node heap consumer；不启动 Agent/Orca。"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import mem_budget_probe as probe
import memory_task_admission as admission

ROOT = Path(__file__).parent
GIB = 1024**3

class MemoryTaskAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='memory-task-admission-')
        self.root = Path(self.tmp.name).resolve()
        self.now = time.time()
        self.measure = {'task_id':'isolated-node','kind':'node_measurement','peak_rss_bytes':69206016,'heap_mb':512,'exit_code':0,'workload':'bounded_node_no_build_no_browser'}
        self.oom = {'task_id':'isolated-node','kind':'task_oom_history','checked_at_epoch':self.now,'events':[],'coverage':'task_only_machine_unknown'}
        self.obj = {'schema':admission.SCHEMA,'task_id':'isolated-node','kind':'light_node','execution':'new_spawn','measurement':self.artifact('measure',self.measure),'oom_history':self.artifact('oom',self.oom),'serial_contract':{'coordinator':'isolated-pm','task_id':'isolated-node','writer_limit':1,'scope':'original_pm_serial_only'}}
        self.profile_path = self.root/'profile.json'
        self.save()
        self.raw = {'hw_memsize':str(32*GIB)+'\n','vm_stat':'Mach Virtual Memory Statistics: (page size of 4096 bytes)\nPages free: 4194304.\nPages inactive: 0.\nPages speculative: 0.\nSwapouts: 12.\nPageouts: 7.\n','memory_pressure':'System-wide memory free percentage: 84%\n','vm_swapusage':'total = 1000.00M  used = 960.00M  free = 40.00M\n','kernel_pressure':'1\n'}
        self.env = dict(os.environ)
        for key in ('NODE_OPTIONS','SPAWN_WORKER_NODE_MAX_OLD_SPACE_MB','SPAWN_WORKER_MEM_BUDGET_BYTES','MEM_BUDGET_FIXTURE_DIR','SPAWN_WORKER_MEMORY_TASK_PROFILE'):
            self.env.pop(key,None)
        self.node_entry = self.root/'codebuddy'
        self.node_entry.write_text('#!/usr/bin/env node\nconsole.log(require("v8").getHeapStatistics().heap_size_limit);\n')
        self.node_entry.chmod(0o700)
        self.env['PATH'] = str(self.root)+os.pathsep+self.env['PATH']

    def tearDown(self):
        self.tmp.cleanup()

    def artifact(self,name,obj):
        p=self.root/(name+'.json');p.write_text(json.dumps(obj));p.chmod(0o600)
        return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}

    def save(self):
        self.profile_path.write_text(json.dumps(self.obj));self.profile_path.chmod(0o600)

    def profile(self):
        self.save();return admission.load_profile(str(self.profile_path),self.now)

    def samples(self):
        return [{'at_monotonic':float(t),'raw':copy.deepcopy(self.raw)} for t in (0,10,20)]

    def decide(self,samples=None,profile=None,budget=2*GIB):
        return admission.apply_profile(profile or self.profile(),samples or self.samples(),budget,probe.evaluate)

    def bind(self,extra=(),env=None,command=None):
        return subprocess.run([sys.executable,str(ROOT/'memory_task_admission.py'),'bind-spawn','--profile',str(self.profile_path),'--backend','codebuddy','--command',command or str(self.node_entry),*extra],env=env or self.env,capture_output=True,text=True,timeout=10)

    def test_light_floor_real_peak_margin_no_zero_discount(self):
        p=self.profile();self.assertEqual(p['_budget_floor'],2*GIB)
        for budget in (0,1,2*GIB-1,True,float('nan')):
            with self.assertRaises(admission.AdmissionError):self.decide(budget=budget)

    def test_stable_highswap_separate_authority_keeps_legacy_risk(self):
        p=self.decide();self.assertEqual(p['status'],'ok');self.assertEqual(p['slots'],1)
        self.assertEqual(p['pressure']['level'],'critical');self.assertTrue(p['task_admission']['high_swap_exception'])
        self.assertEqual(p['task_admission']['cross_pm_reservation'],'NOT_VERIFIED')
        self.assertEqual(p['task_admission']['oom_coverage'],'task_only_machine_unknown')
        self.assertTrue(p['telemetry']['kernel_pressure']['used_for_admission'])
        self.assertEqual(probe.evaluate(self.raw,2*GIB,'legacy')['status'],'denied')

    def test_native_warn_stable_can_use_exception(self):
        self.raw['kernel_pressure']='2\n';self.assertEqual(self.decide()['status'],'ok')

    def test_native_critical_unknown_multiline_empty_always_deny(self):
        for raw in ('4\n','3\n','1\n2\n','',None):
            self.raw['kernel_pressure']=raw;self.assertEqual(self.decide()['slots'],0)

    def test_normal_low_swap_one_sample_preserves_one_slot(self):
        self.raw['vm_swapusage']='total = 1000.00M used = 10.00M free = 990.00M\n'
        p=self.decide(self.samples()[:1]);self.assertEqual(p['status'],'ok');self.assertEqual(p['slots'],1)
        self.assertFalse(p['task_admission']['high_swap_exception'])

    def test_window_count_span_and_monotonic(self):
        for times in ((0,20),(0,9,19),(0,0,20),(0,20,10),(0,float('nan'),20),(0,True,20)):
            rows=self.samples()[:len(times)]
            for row,t in zip(rows,times):row['at_monotonic']=t
            try:self.assertEqual(self.decide(rows)['status'],'denied')
            except admission.AdmissionError:pass

    def test_counter_growth_rollback_missing_duplicate(self):
        for raw in ('Swapouts: 13.\nPageouts: 7.\n','Swapouts: 11.\nPageouts: 7.\n','Swapouts: 12.\nPageouts: 8.\n','Swapouts: 12.\n','Swapouts: 12.\nSwapouts: 12.\nPageouts: 7.\n','Swapouts: -1.\nPageouts: 7.\n'):
            samples=self.samples();samples[1]['raw']['vm_stat']=self.raw['vm_stat'].split('Swapouts:')[0]+raw
            self.assertEqual(self.decide(samples)['status'],'denied')

    def test_swapused_growth_even_when_final_recovers_denied(self):
        rows=self.samples();rows[1]['raw']['vm_swapusage']='total = 1000.00M used = 970.00M free = 30.00M\n'
        self.assertEqual(self.decide(rows)['status'],'denied')

    def test_every_sample_physical_budget_reserve_and_unknown(self):
        for vm in (None,'garbage','Mach Virtual Memory Statistics: (page size of 4096 bytes)\nPages free: 2.\nSwapouts: 12.\nPageouts: 7.\n'):
            rows=self.samples();rows[1]['raw']['vm_stat']=vm
            self.assertEqual(self.decide(rows)['status'],'denied')

    def test_keyword_critical_and_percent_warning_not_swap_exception(self):
        for mp in ('critical memory situation\n','System-wide memory free percentage: garbage\n','garbage','System-wide memory free percentage: 10% available\n','10% available\n'):
            self.raw['memory_pressure']=mp
            self.assertEqual(self.decide()['status'],'denied')

    def test_heavy_floor_no_exception(self):
        self.obj['kind']='heavy';self.obj.pop('measurement');p=self.profile()
        self.assertEqual(p['_budget_floor'],3*GIB)
        self.assertEqual(self.decide(profile=p,budget=3*GIB)['status'],'denied')
        with self.assertRaises(admission.AdmissionError):self.decide(profile=p,budget=2*GIB)

    def test_task_recent_oom_stale_future_unknown_coverage(self):
        self.oom['events']=[{'at_epoch':self.now-1,'type':'oom'}];self.obj['oom_history']=self.artifact('oom',self.oom)
        self.assertEqual(self.decide()['status'],'denied')
        for checked in (self.now-3601,self.now+1,True,float('nan')):
            self.oom['checked_at_epoch']=checked;self.obj['oom_history']=self.artifact('oom',self.oom)
            with self.assertRaises(admission.AdmissionError):self.profile()
        self.oom.update(checked_at_epoch=self.now,events=[],coverage='machine_clean');self.obj['oom_history']=self.artifact('oom',self.oom)
        with self.assertRaises(admission.AdmissionError):self.profile()

    def test_profile_unknown_bool_numeric_and_artifact_hash_task_mismatch(self):
        for mutate in ('unknown','bool','hash','task','heap'):
            saved=copy.deepcopy(self.obj)
            if mutate=='unknown':self.obj['extra']=True
            elif mutate=='bool':self.obj['serial_contract']['writer_limit']=True
            elif mutate=='hash':self.obj['measurement']['sha256']='0'*64
            elif mutate=='task':self.obj['task_id']='wrong'
            else:
                measure={**self.measure,'heap_mb':True};self.obj['measurement']=self.artifact('bad',measure)
            with self.assertRaises(admission.AdmissionError):self.profile()
            self.obj=saved

    def test_profile_symlink_and_world_writable_rejected(self):
        link=self.root/'link.json';link.symlink_to(self.profile_path)
        with self.assertRaises(admission.AdmissionError):admission.load_profile(str(link))
        self.profile_path.chmod(0o666)
        with self.assertRaises(admission.AdmissionError):admission.load_profile(str(self.profile_path))

    def test_cli_binding_actual_node_shebang_not_json_claim(self):
        result=self.bind();self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['heap_mb'],512)
        self.node_entry.write_text('#!/bin/sh\nexit 0\n')
        result=self.bind();self.assertEqual(result.returncode,64);self.assertIn('not proven Node',result.stderr)

    def test_cli_override_env_cap_command_all_refuse(self):
        for change in ({'NODE_OPTIONS':'--max-old-space-size=4096'},{'SPAWN_WORKER_NODE_MAX_OLD_SPACE_MB':'0'},{'SPAWN_WORKER_NODE_MAX_OLD_SPACE_MB':'2048'}):
            result=self.bind(env={**self.env,**change});self.assertEqual(result.returncode,64,result.stderr)
        for command in ('env NODE_OPTIONS=--max-old-space-size=4096 '+str(self.node_entry),str(self.node_entry)+' --max_old_space_size=4096'):
            self.assertEqual(self.bind(command=command).returncode,64)

    def shell_cap(self,binding=None):
        source=(ROOT/'spawn-worker.sh').read_text();function=source[source.index('node_mem_cap_setup() {'):source.index('\ndependency_install_guard_setup\n',source.index('node_mem_cap_setup() {'))]
        binding=json.loads(self.bind().stdout) if binding is None else binding
        values={'SCRIPT_DIR':str(ROOT.resolve()),'MEMORY_TASK_PROFILE':str(self.profile_path),'MEMORY_TASK_ORIGINAL_COMMAND':str(self.node_entry),'MEMORY_TASK_BINDING_B64':admission.encode_binding(binding),'WORKER_BACKEND_CANONICAL':'codebuddy','COMMAND':str(self.node_entry)}
        import shlex
        return '\n'.join(k+'='+shlex.quote(v) for k,v in values.items())+'\n'+function+'\nnode_mem_cap_setup\neval "$COMMAND"\n'

    def test_real_node_consumer_uses_exact_spawn_enforcement_function(self):
        command=self.shell_cap()
        result=subprocess.run(['bash','-c',command],env=self.env,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        heap=int(result.stdout.splitlines()[-1]);self.assertLessEqual(heap,512*1024**2)
        self.assertIn('total<=512MiB old-space=480MB semi-space=1MB',result.stdout)
        result=subprocess.run(['bash','-c',command],env={**self.env,'NODE_OPTIONS':'--max-old-space-size=4096'},capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,64)

    def test_heavy_profile_replaced_light_gate_and_late_hard_refusal(self):
        light=copy.deepcopy(self.obj)
        self.obj['kind']='heavy';self.obj.pop('measurement');self.save()
        early=json.loads(self.bind().stdout)
        self.obj=light;self.save()
        result=subprocess.run(['bash','-c',self.shell_cap(early)],env=self.env,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,64,result.stderr)
        result=subprocess.run([sys.executable,str(ROOT/'mem_budget_probe.py'),'--json','--task-profile',str(self.profile_path),'--task-command',str(self.node_entry),'--task-backend','codebuddy','--task-binding-b64',admission.encode_binding(early),'--fixture-dir',str(ROOT/'fixtures/memory-admission-261002/snapshot-1')],env=self.env,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertIn('binding drift',json.loads(result.stdout)['reason'])

    def test_entry_shebang_replaced_shell_late_and_exec_guard_refuse(self):
        early=json.loads(self.bind().stdout);command=self.shell_cap(early)
        self.node_entry.write_text('#!/bin/sh\nnode --max-old-space-size=4096 -e "console.log(1)"\n')
        result=subprocess.run(['bash','-c',command],env=self.env,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,64,result.stderr)
        result=subprocess.run([sys.executable,str(ROOT/'memory_task_admission.py'),'exec-bound','--profile',str(self.profile_path),'--command',str(self.node_entry),'--backend','codebuddy','--binding-b64',admission.encode_binding(early),'--outer-command',str(self.node_entry)],env=self.env,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,64,result.stderr)

    def test_PATH_node_script_wrapper_is_not_trusted_interpreter(self):
        wrapper=self.root/'node';wrapper.write_text('#!/bin/sh\nexec '+str(Path(shutil.which('node')).resolve())+' --max-old-space-size=4096 "$@"\n');wrapper.chmod(0o700)
        result=self.bind();self.assertEqual(result.returncode,64,result.stderr)
        self.assertIn('native binary',result.stderr)

    def test_actual_existing_underscore_heap_override_rejected(self):
        node=str(Path(shutil.which('node')).resolve())
        child=subprocess.Popen([node,'--max-old-space-size=480','--max-semi-space-size=1','--max_old_space_size=4096','-e','setTimeout(()=>{},10000)'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=self.env)
        try:
            identity=admission.session_readback(child.pid)
            session={'pid':child.pid,**{k:identity[k] for k in ('uid','start','command_sha256')}}
            with self.assertRaisesRegex(admission.AdmissionError,'override'):
                admission.verify_session(session)
        finally:
            child.terminate();child.communicate(timeout=5)

    def test_raw_swap_over_total_invalid_or_duplicate_never_clamp_pass(self):
        for raw in ('total = 1000.00M used = 2000.00M free = 0.00M\n','total = 1000M used = nan used = 960M free = 40M\n','total = 1000M used = -1M free = 1001M\n','total = 1000M used = 960M free = 99M\n'):
            self.raw['vm_swapusage']=raw
            self.assertEqual(self.decide()['status'],'denied')
        self.raw['vm_swapusage']='total = 1000M used = 960M free = 40M\n'
        value=self.decide();receipt=value['task_admission']
        self.assertGreaterEqual(receipt['effective_capacity_bytes'],value['budget_bytes'])
        self.assertEqual(receipt['legacy_effective_available_bytes'],0)
        self.assertIn('minimum_vm_stat',receipt['effective_capacity_source'])


    def test_existing_identity_unknown_disappeared_nonnode_and_drift(self):
        self.obj['execution']='existing_session';self.obj['session']={'pid':99999999,'uid':os.getuid(),'start':'unknown','command_sha256':'0'*64}
        with self.assertRaises(admission.AdmissionError):self.profile()
        identity=admission.session_readback(os.getpid());self.obj['session']={'pid':os.getpid(),**{k:identity[k] for k in ('uid','start','command_sha256')}}
        with self.assertRaisesRegex(admission.AdmissionError,'not a proven Node'):self.profile()
        self.obj['session']['command_sha256']='0'*64
        with self.assertRaisesRegex(admission.AdmissionError,'drift'):self.profile()

    def test_spawn_never_accepts_existing_session_or_reuse_claim(self):
        p=self.profile();p['execution']='existing_session'
        with self.assertRaises(admission.AdmissionError):admission.bind_spawn(p,str(self.node_entry),'codebuddy',ROOT,self.env)
        self.obj['session']={'pid':os.getpid()}
        with self.assertRaises(admission.AdmissionError):self.profile()

    def test_probe_real_cli_fixture_zero_reject_window_no_fake_live(self):
        fixture=self.root/'fixture';fixture.mkdir()
        for name,raw in self.raw.items():(fixture/probe.FIXTURE_FILES[name]).write_text(raw)
        args=[sys.executable,str(ROOT/'mem_budget_probe.py'),'--json','--task-profile',str(self.profile_path),'--task-command',str(self.node_entry),'--task-backend','codebuddy','--fixture-dir',str(fixture)]
        result=subprocess.run(args,env=self.env,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,3,result.stderr);obj=json.loads(result.stdout)
        self.assertEqual(obj['slots'],0);self.assertEqual(obj['telemetry']['collection_mode'],'fixture_files')
        self.assertEqual(obj['task_admission']['sample_count'],1)
        result=subprocess.run(args+['--budget','0'],env=self.env,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,1,result.stderr);self.assertEqual(json.loads(result.stdout)['status'],'config_invalid')
        result=subprocess.run(args,env={**self.env,'NODE_OPTIONS':'--max-old-space-size=4096'},capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,1)

    def test_actual_profile_floor_and_normal_cli_consumer(self):
        fixture=self.root/'fixture';fixture.mkdir();self.raw['vm_swapusage']='total = 1000.00M used = 10.00M free = 990.00M\n'
        for name,raw in self.raw.items():(fixture/probe.FIXTURE_FILES[name]).write_text(raw)
        result=subprocess.run([sys.executable,str(ROOT/'mem_budget_probe.py'),'--json','--task-profile',str(self.profile_path),'--task-command',str(self.node_entry),'--task-backend','codebuddy','--fixture-dir',str(fixture)],env=self.env,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr);obj=json.loads(result.stdout)
        self.assertEqual(obj['budget_bytes'],2*GIB);self.assertEqual(obj['slots'],1)

if __name__=='__main__':
    unittest.main(verbosity=2)
