#!/usr/bin/env python3
"""宿主attestation/同门CLI/真实tiny Node薄执行；不派Agent/不运行311。"""
import base64
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

import memory_task_admission as admission
import mem_budget_probe as probe
import host_memory_admission as host

ROOT=Path(__file__).resolve().parent
GIB=1024**3

class HostMemoryAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='host-memory-profile-')
        self.root=Path(self.tmp.name).resolve();self.root.chmod(0o700)
        self.now=time.time();self.thread=os.environ.get('CODEX_THREAD_ID')
        self.assertTrue(self.thread,'test requires actual current controller thread ID, never fake AgentPID')
        self.script=self.root/'tiny.mjs';self.script.write_text('import v8 from "node:v8"; console.log(JSON.stringify({heap:v8.getHeapStatistics().heap_size_limit,args:process.argv.slice(2)}));\n')
        self.node=str(Path(shutil.which('node')).resolve())
        self.measure={'kind':'node_measurement','task_id':'isolated-host-task','peak_rss_bytes':70057984,'heap_mb':480,'exit_code':0,'workload':'bounded_node_no_build_no_browser'}
        self.oom={'kind':'task_oom_history','task_id':'isolated-host-task','checked_at_epoch':self.now,'events':[],'coverage':'task_only_machine_unknown'}
        self.projection={'kind':'codex_host_tool_projection','task_id':'isolated-host-task','observed_at_epoch':self.now,
            'controller':{'thread_id':self.thread,'canonical_parent':'/root'},
            'selected_worker':{'canonical_path':'/root/isolated_worker','status':'completed','opaque_agent_uuid':None,'os_pid':None},
            'agents':[{'canonical_path':'/root','status':'running'},{'canonical_path':'/root/isolated_worker','status':'completed'}],
            'source':{'type':'original_controller_tool_attestation','tool':'collaboration.list_agents','platform_signed':False}}
        self.plan={'kind':'scoped_node_plan','task_id':'isolated-host-task','cwd':str(self.root),
            'argv':[self.node,'--max-old-space-size=480','--max-semi-space-size=1','tiny.mjs','--unit-only'],
            'entry_sha256':hashlib.sha256(self.script.read_bytes()).hexdigest()}
        self.obj={'schema':admission.SCHEMA,'task_id':'isolated-host-task','kind':'light_node','execution':'codex_host_followup',
            'serial_contract':{'coordinator':'original-controller','task_id':'isolated-host-task','writer_limit':1,'scope':'original_pm_serial_only'}}
        self.profile_path=self.root/'profile.json';self.save()
        self.raw={'hw_memsize':str(32*GIB)+'\n','vm_stat':'Mach Virtual Memory Statistics: (page size of 4096 bytes)\nPages free: 4194304.\nPages inactive: 0.\nSwapouts: 12.\nPageouts: 7.\n',
            'memory_pressure':'System-wide memory free percentage: 84%\n','vm_swapusage':'total = 1000M used = 960M free = 40M\n','kernel_pressure':'2\n'}
        self.env=dict(os.environ)
        for key in ('NODE_OPTIONS','NODE_PATH','MEM_BUDGET_FIXTURE_DIR','SPAWN_WORKER_MEM_BUDGET_BYTES'):
            self.env.pop(key,None)

    def tearDown(self):self.tmp.cleanup()

    def artifact(self,name,obj):
        p=self.root/(name+'.json');p.write_text(json.dumps(obj));p.chmod(0o600)
        return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}

    def save(self):
        for name,obj in [('measurement',self.measure),('oom_history',self.oom),('host_projection',self.projection),('node_plan',self.plan)]:
            self.obj[name]=self.artifact(name,obj)
        self.profile_path.write_text(json.dumps(self.obj));self.profile_path.chmod(0o600)

    def profile(self):self.save();return admission.load_profile(str(self.profile_path))

    def samples(self):return [{'at_monotonic':t,'raw':copy.deepcopy(self.raw)} for t in (0.,10.,20.)]

    def fixture(self,raw=None):
        p=self.root/'fixture';p.mkdir(exist_ok=True)
        for name,value in (raw or self.raw).items():
            if value is not None:(p/probe.FIXTURE_FILES[name]).write_text(value)
        return p

    def cli(self,operation,*args):
        return subprocess.run([sys.executable,'-B',str(ROOT/'host_memory_admission.py'),operation,'--profile',str(self.profile_path),*args],env=self.env,capture_output=True,text=True,timeout=120)

    def test_actual_thread_host_binding_not_Node_PID_and_full_budget(self):
        p=self.profile();binding=admission.bind_host_profile(p)
        self.assertEqual(binding['host']['controller_thread_id'],os.environ['CODEX_THREAD_ID'])
        self.assertIsNone(binding['host']['agent_os_pid']);self.assertIsNone(binding['host']['opaque_agent_uuid'])
        self.assertFalse(binding['host']['platform_signed']);self.assertEqual(binding['budget_floor_bytes'],2*GIB)
        self.assertEqual(binding['reuse_discount_bytes'],0)
        value=admission.apply_profile(p,self.samples(),2*GIB,probe.evaluate)
        self.assertEqual(value['status'],'ok');self.assertEqual(value['slots'],1)
        self.assertEqual(value['task_admission']['host_binding']['execution'],'codex_host_followup')
        self.assertEqual(value['task_admission']['cross_pm_reservation'],'NOT_VERIFIED')

    def test_host_wrong_parent_thread_task_worker_unknown_status_or_pid(self):
        mutations=[lambda:self.projection['controller'].update(canonical_parent='/other'),lambda:self.projection['controller'].update(thread_id='wrong'),lambda:self.projection.update(task_id='wrong'),lambda:self.projection['selected_worker'].update(canonical_path='/root/missing'),lambda:self.projection['selected_worker'].update(status='running'),lambda:self.projection['selected_worker'].update(os_pid=os.getpid()),lambda:self.projection['selected_worker'].update(opaque_agent_uuid='invented')]
        for mutate in mutations:
            saved=copy.deepcopy(self.projection);mutate()
            with self.assertRaises(admission.AdmissionError):self.profile()
            self.projection=saved
        with patch.dict(os.environ,{'CODEX_THREAD_ID':''}):
            with self.assertRaises(admission.AdmissionError):self.profile()

    def test_projection_expired_future_duplicate_conflict_or_signed(self):
        for timestamp in (self.now-121,self.now+100,True,float('nan')):
            self.projection['observed_at_epoch']=timestamp
            with self.assertRaises(admission.AdmissionError):self.profile()
        self.projection['observed_at_epoch']=self.now
        saved=copy.deepcopy(self.projection)
        self.projection['agents'].append(copy.deepcopy(self.projection['agents'][1]))
        with self.assertRaises(admission.AdmissionError):self.profile()
        self.projection=saved;self.projection['agents'][1]['status']='running'
        with self.assertRaises(admission.AdmissionError):self.profile()
        self.projection=saved;self.projection['source']['platform_signed']=True
        with self.assertRaises(admission.AdmissionError):self.profile()

    def test_new_spawn_never_consumes_host(self):
        p=self.profile()
        with self.assertRaisesRegex(admission.AdmissionError,'cannot consume'):
            admission.bind_spawn(p,'codebuddy','codebuddy',ROOT)
        result=subprocess.run([sys.executable,str(ROOT/'memory_task_admission.py'),'bind-spawn','--profile',str(self.profile_path),'--backend','codebuddy','--command','codebuddy'],env=self.env,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,64,result.stderr)

    def test_same_core_all_pressure_growth_low_available_oom_and_zero_denied(self):
        p=self.profile()
        for key,value in [('kernel_pressure','4\n'),('kernel_pressure','3\n'),('vm_swapusage','total = 1000M used = 970M free = 30M\n'),('vm_stat',self.raw['vm_stat'].replace('Pageouts: 7.','Pageouts: 8.')),('vm_stat',self.raw['vm_stat'].replace('4194304','2'))]:
            rows=self.samples();rows[1]['raw'][key]=value
            self.assertEqual(admission.apply_profile(p,rows,2*GIB,probe.evaluate)['status'],'denied')
        with self.assertRaises(admission.AdmissionError):admission.apply_profile(p,self.samples(),0,probe.evaluate)
        self.oom['events']=[{'at_epoch':self.now-1,'type':'oom'}]
        self.assertEqual(admission.apply_profile(self.profile(),self.samples(),2*GIB,probe.evaluate)['status'],'denied')

    def test_real_inspect_and_readonly_admit_CLI_normal_and_highswap_shortwindow(self):
        result=self.cli('inspect');self.assertEqual(result.returncode,0,result.stdout)
        self.assertEqual(json.loads(result.stdout)['agent_action'],'none')
        result=self.cli('admit','--fixture-dir',str(self.fixture()))
        self.assertEqual(result.returncode,3,result.stdout)
        self.assertEqual(json.loads(result.stdout)['memory_gate']['task_admission']['sample_count'],1)
        low={**self.raw,'vm_swapusage':'total = 1000M used = 10M free = 990M\n'}
        result=self.cli('admit','--fixture-dir',str(self.fixture(low)))
        self.assertEqual(result.returncode,0,result.stdout)
        value=json.loads(result.stdout);self.assertEqual(value['slots'],1)
        self.assertEqual(value['memory_gate']['budget_bytes'],2*GIB)
        self.assertEqual(value['collection_mode'],'fixture_files');self.assertFalse(value['platform_signed']);self.assertFalse(value['authorizing_for_live_followup'])

    def test_tiny_real_Node_thin_mechanical_consumer_without_Agent_or_311(self):
        binding=admission.bind_host_profile(self.profile(),require_exists=True)
        with patch.dict(os.environ,self.env,clear=True):
            result=host._run_scoped_node(str(self.profile_path),binding)
        self.assertEqual(result['exit_code'],0,result['stderr'])
        actual=json.loads(result['stdout']);self.assertLessEqual(actual['heap'],512*1024**2)
        self.assertEqual(actual['args'],['--unit-only']);self.assertEqual(result['agent_action'],'none')
        self.assertEqual(result['business_completion'],'NOT_INFERRED')

    def test_future_plan_cwd_not_created_is_fact_but_execution_refused(self):
        self.plan['cwd']=str(self.root/'future-not-created');p=self.profile()
        binding=admission.bind_host_profile(p)
        self.assertFalse(binding['workload_node']['execution_ready'])
        self.assertEqual(binding['workload_node']['cwd_state'],'planned_not_created')
        with self.assertRaisesRegex(admission.AdmissionError,'does not exist'):
            host._run_scoped_node(str(self.profile_path),binding)

    def test_Node_plan_shell_env_alias_escape_symlink_or_hash_drift_refuse(self):
        for argv in (["/bin/bash",'-c','node x'],[self.node,'--max-old-space-size=4096','--max-semi-space-size=1','tiny.mjs'],[self.node,'--max-old-space-size=480','--max-semi-space-size=1','../tiny.mjs'],[self.node,'--max-old-space-size=480','--max-semi-space-size=1','tiny.mjs','--max_old_space_size=4096'],[self.node,'--max-old-space-size=480','--max-semi-space-size=1','tiny.mjs','../../outside']):
            saved=copy.deepcopy(self.plan);self.plan['argv']=argv
            with self.assertRaises(admission.AdmissionError):self.profile()
            self.plan=saved
        binding=admission.bind_host_profile(self.profile());self.script.write_text('throw Error("changed");')
        with self.assertRaises(admission.AdmissionError):host._run_scoped_node(str(self.profile_path),binding)

    def test_argument_symlink_physical_escape_refused(self):
        outside=self.root.parent/(self.root.name+'-outside')
        outside.mkdir()
        try:
            (self.root/'linked').symlink_to(outside,target_is_directory=True)
            self.plan['argv'].append('--output=linked/result.json')
            with self.assertRaisesRegex(admission.AdmissionError,'symlink escape'):
                self.profile()
        finally:
            outside.rmdir()

    def test_host_artifact_byte_drift_before_execution_refused(self):
        binding=admission.bind_host_profile(self.profile())
        p=self.root/'host_projection.json';p.write_text(p.read_text()+' ')
        with self.assertRaises(admission.AdmissionError):host._run_scoped_node(str(self.profile_path),binding)

    def test_cwd_replacement_keeps_entry_inode_but_binding_and_exec_refuse(self):
        expected=admission.bind_host_profile(self.profile())
        parked=self.root.with_name(self.root.name+'-parked')
        self.root.rename(parked);self.root.mkdir(mode=0o700)
        for path in list(parked.iterdir()):path.rename(self.root/path.name)
        try:
            current=admission.bind_host_profile(admission.load_profile(str(self.profile_path)))
            self.assertEqual(current['workload_node']['entry'],expected['workload_node']['entry'])
            self.assertNotEqual(current['workload_node']['cwd_identity'],expected['workload_node']['cwd_identity'])
            with self.assertRaisesRegex(admission.AdmissionError,'binding drift'):
                host._run_scoped_node(str(self.profile_path),expected)
        finally:
            for path in list(self.root.iterdir()):path.rename(parked/path.name)
            self.root.rmdir();parked.rename(self.root)

    def test_env_only_fixture_actual_CLI_is_non_authorizing_diagnostic(self):
        low={**self.raw,'vm_swapusage':'total = 1000M used = 10M free = 990M\n'}
        fixture=self.fixture(low)
        result=subprocess.run([sys.executable,'-B',str(ROOT/'host_memory_admission.py'),'admit','--profile',str(self.profile_path)],env={**self.env,'MEM_BUDGET_FIXTURE_DIR':str(fixture)},capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout)
        value=json.loads(result.stdout)
        self.assertEqual(value['collection_mode'],'fixture_files')
        self.assertEqual(value['memory_gate']['telemetry']['collection_mode'],'fixture_files')
        self.assertFalse(value['authorizing_for_live_followup'])
        self.assertEqual(value['authority_scope'],'non_authorizing_diagnostic')

    def test_unknown_or_conflicting_actual_collector_provenance_refused(self):
        from types import SimpleNamespace
        original=subprocess.run
        for mode in (None,'supplied_snapshots','live_readonly'):
            value=probe.evaluate(self.raw,2*GIB,'fixture')
            value['telemetry']['collection_mode']=mode
            def consumer(args,**kwargs):
                if len(args)>1 and str(args[1]).endswith('mem_budget_probe.py'):
                    return SimpleNamespace(returncode=0,stdout=json.dumps(value),stderr='')
                return original(args,**kwargs)
            with patch.object(host.subprocess,'run',side_effect=consumer):
                with self.assertRaisesRegex(admission.AdmissionError,'provenance'):
                    host.admit_profile(str(self.profile_path),str(self.fixture()))

    def test_bounded_combined_output_real_Node_stops_and_reaps_own_child(self):
        self.script.write_text('process.stdout.write("x".repeat(600000));process.stderr.write("y".repeat(600000));setTimeout(()=>{},10000);')
        self.plan['entry_sha256']=hashlib.sha256(self.script.read_bytes()).hexdigest()
        expected=admission.bind_host_profile(self.profile())
        created=[];actual_popen=subprocess.Popen
        def capture(*args,**kwargs):
            proc=actual_popen(*args,**kwargs);created.append(proc);return proc
        with patch.object(host.subprocess,'Popen',side_effect=capture):
            with self.assertRaisesRegex(admission.AdmissionError,'1048576-byte'):
                host._run_scoped_node(str(self.profile_path),expected)
        # Includes readonly Node observers and the exact own bounded workload;
        # each child must be reaped, no external PID/group cleanup.
        self.assertTrue(created)
        self.assertTrue(all(proc.poll() is not None for proc in created))

    def test_bounded_Node_timeout_reaps_own_child(self):
        self.script.write_text('setTimeout(()=>{},10000);')
        self.plan['entry_sha256']=hashlib.sha256(self.script.read_bytes()).hexdigest()
        expected=admission.bind_host_profile(self.profile())
        with patch.object(host,'NODE_TIMEOUT_SECONDS',.1):
            with self.assertRaisesRegex(admission.AdmissionError,'timeout'):
                host._run_scoped_node(str(self.profile_path),expected)

    def test_public_execution_refuses_offline_or_forged_receipt_and_runs_shared_gate(self):
        binding=admission.bind_host_profile(self.profile());encoded=admission.encode_binding(binding)
        result=self.cli('execute-node','--binding-b64',encoded,'--fixture-dir',str(self.fixture()))
        self.assertEqual(result.returncode,64)
        with patch.dict(os.environ,{'MEM_BUDGET_FIXTURE_DIR':str(self.fixture())}):
            with self.assertRaisesRegex(admission.AdmissionError,'offline fixture'):host.execute_node(str(self.profile_path),encoded)
        # Source is the actual helper function: no caller JSON status argument.
        self.assertNotIn('admission-b64',(ROOT/'host_memory_admission.py').read_text())

if __name__=='__main__':unittest.main(verbosity=2)
