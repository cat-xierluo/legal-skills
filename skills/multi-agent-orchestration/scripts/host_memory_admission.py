#!/usr/bin/env python3
"""原Codex宿主跟进的薄接口：只读同门准入、scoped Node执行；不派Agent。"""
import argparse
import selectors
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import memory_task_admission as admission
import mem_budget_probe as probe

ROOT=Path(__file__).resolve().parent


OUTPUT_MAX_BYTES = 1024 * 1024
NODE_TIMEOUT_SECONDS = 120


def _stop_owned_child(proc):
    # This Popen is exclusively created by this invocation. No process search,
    # external PID, process-group kill or Agent/user resource is accepted.
    if proc.poll() is None:
        try:
            proc.terminate()
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    else:
        proc.wait()


def _bounded_node(argv,cwd,env):
    proc=subprocess.Popen(argv,cwd=cwd,env=env,stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    chunks={'stdout':[],'stderr':[]};total=0
    deadline=time.monotonic()+NODE_TIMEOUT_SECONDS
    try:
        with selectors.DefaultSelector() as selector:
            for name,stream in (('stdout',proc.stdout),('stderr',proc.stderr)):
                os.set_blocking(stream.fileno(),False)
                selector.register(stream,selectors.EVENT_READ,name)
            while selector.get_map():
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    raise admission.AdmissionError('scoped Node execution timeout; exact child stopped/reaped')
                for key,_ in selector.select(min(.25,remaining)):
                    data=os.read(key.fileobj.fileno(),65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    total+=len(data)
                    if total>OUTPUT_MAX_BYTES:
                        raise admission.AdmissionError('scoped Node combined stdout/stderr exceeds 1048576-byte limit; exact child stopped/reaped')
                    chunks[key.data].append(data)
            remaining=deadline-time.monotonic()
            if remaining<=0:
                raise admission.AdmissionError('scoped Node execution timeout; exact child stopped/reaped')
            try:
                rc=proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                raise admission.AdmissionError('scoped Node execution timeout; exact child stopped/reaped')
        return {'returncode':rc,'stdout':b''.join(chunks['stdout']).decode('utf-8',errors='replace'),
                'stderr':b''.join(chunks['stderr']).decode('utf-8',errors='replace'),'output_bytes':total}
    finally:
        _stop_owned_child(proc)
        proc.stdout.close();proc.stderr.close()


def inspect_profile(path):
    profile=admission.load_profile(path)
    binding=admission.bind_host_profile(profile)
    return {'schema':'memory-task-host.inspection.v1','binding':binding,
            'admission':'NOT_PERFORMED','agent_action':'none','platform_signed':False}


def _run_scoped_node(path,expected):
    """机械Node执行步骤；公开CLI只在同进程实际资源门通过后调用。"""
    profile=admission.load_profile(path)
    binding=admission.bind_host_profile(profile,require_exists=True)
    if binding != expected:
        raise admission.AdmissionError('host/controller/Node binding drift before execution')
    workload=binding['workload_node']
    env=dict(os.environ)
    if env.get('NODE_OPTIONS') or env.get('NODE_PATH') or any(env.get(key) for key in env if key.startswith(('LD_','DYLD_'))):
        raise admission.AdmissionError('Node execution caller runtime override refused')
    fresh=admission.bind_host_profile(admission.load_profile(path),require_exists=True)
    if fresh!=binding:
        raise admission.AdmissionError('host/Node final execution identity drift')
    result=_bounded_node(workload['argv'],workload['cwd'],env)
    return {'schema':'memory-task-host.node-execution.v1','task_id':profile['task_id'],
            'binding':binding,'exit_code':result['returncode'],'stdout':result['stdout'],'stderr':result['stderr'],
            'output_bytes':result['output_bytes'],'output_limit_bytes':OUTPUT_MAX_BYTES,'timeout_seconds':NODE_TIMEOUT_SECONDS,
            'heap_limit_readback_bytes':workload['node']['observed_heap_bytes'],
            'agent_action':'none','business_completion':'NOT_INFERRED','platform_signed':False}


def execute_node(path,binding_b64):
    import base64
    if os.environ.get(probe.FIXTURE_ENV):
        raise admission.AdmissionError('offline fixture cannot authorize real Node execution')
    expected=json.loads(base64.urlsafe_b64decode(binding_b64))
    before=inspect_profile(path)['binding']
    if before!=expected:
        raise admission.AdmissionError('frozen expected host binding drift')
    # One shared policy invocation, not a second policy or a caller-forged receipt.
    rc,receipt=admit_profile(path)
    if rc!=0 or receipt['status']!='ok' or receipt['slots']!=1 or receipt.get('authorizing_for_live_followup') is not True:
        return rc if rc else 64,{'schema':'memory-task-host.execution-refused.v1',
            'resource_admission':receipt,'node_executed':False,'agent_action':'none'}
    if receipt['binding']!=expected:
        raise admission.AdmissionError('host binding changed across actual resource gate')
    result=_run_scoped_node(path,expected)
    result['resource_admission']=receipt
    return result['exit_code'],result


def admit_profile(path,fixture_dir=None):
    before=inspect_profile(path)['binding']
    args=[sys.executable,str(ROOT/'mem_budget_probe.py'),'--json','--task-profile',path]
    if fixture_dir:args.extend(['--fixture-dir',fixture_dir])
    result=subprocess.run(args,capture_output=True,text=True,timeout=90)
    try:payload=json.loads(result.stdout)
    except ValueError:raise admission.AdmissionError('shared memory gate produced invalid output')
    after=inspect_profile(path)['binding']
    if before!=after:raise admission.AdmissionError('host binding drift across shared admission gate')
    mode=payload.get('telemetry',{}).get('collection_mode')
    effective_fixture=fixture_dir or os.environ.get(probe.FIXTURE_ENV,'').strip() or None
    expected_mode='fixture_files' if effective_fixture else 'live_readonly'
    if mode not in {'fixture_files','live_readonly'} or mode!=expected_mode:
        raise admission.AdmissionError('shared gate actual collector provenance unknown/inconsistent')
    authorizing=mode=='live_readonly' and result.returncode==0 and payload.get('status')=='ok' and payload.get('slots')==1
    return result.returncode,{'schema':'memory-task-host.admission.v1','binding':after,
        'checked_at_epoch':time.time(),'status':payload.get('status'),'slots':payload.get('slots'),
        'memory_gate':payload,'collection_mode':mode,'authorizing_for_live_followup':authorizing,
        'authority_scope':'original_PM_still_requires_quota_scope_cancellation' if authorizing else 'non_authorizing_diagnostic',
        'agent_action':'none','platform_signed':False,'receipt_trust':'original_PM_local_attestation; not platform signature'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('operation',choices=['inspect','admit','execute-node'])
    parser.add_argument('--profile',required=True)
    parser.add_argument('--fixture-dir')
    parser.add_argument('--binding-b64')
    args=parser.parse_args()
    try:
        if args.operation=='inspect':rc,out=0,inspect_profile(args.profile)
        elif args.operation=='admit':rc,out=admit_profile(args.profile,args.fixture_dir)
        else:
            if not args.binding_b64 or args.fixture_dir:
                raise admission.AdmissionError('expected binding required; fixture cannot authorize execution')
            rc,out=execute_node(args.profile,args.binding_b64)
        print(json.dumps(out,ensure_ascii=False,sort_keys=True))
        return rc
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:
        print(json.dumps({'schema':'memory-task-host.refused.v1','status':'refused','slots':0,'reason':str(exc),'agent_action':'none'},ensure_ascii=False))
        return 64

if __name__=='__main__':
    sys.exit(main())
