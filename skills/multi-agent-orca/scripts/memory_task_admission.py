#!/usr/bin/env python3
"""显式任务内存实验合同；默认 lane 不调用本模块。无跨 PM reservation。"""
import argparse
import base64
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time

GIB = 1024 ** 3
SCHEMA = 'memory-task-admission.profile.v1'
MAX_AGE = 3600
OOM_LOOKBACK = 24 * 3600

class AdmissionError(ValueError):
    pass

def number(value, name, integer=False, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum or (integer and not isinstance(value, int)):
        raise AdmissionError(f'{name}: invalid finite number')
    return value

def private_json(path):
    p = Path(path)
    if not p.is_absolute() or str(p.resolve()) != str(p) or p.is_symlink():
        raise AdmissionError('evidence path must be absolute canonical nonlink')
    info = p.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022 or info.st_size > 1024 * 1024:
        raise AdmissionError('evidence must be owned regular nonwritable file')
    raw = p.read_bytes()
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise AdmissionError('evidence object required')
    return obj, hashlib.sha256(raw).hexdigest()

def bound_artifact(ref, task_id, kind):
    if not isinstance(ref, dict) or set(ref) != {'path', 'sha256'}:
        raise AdmissionError(f'{kind}: exact path/hash reference required')
    obj, digest = private_json(ref['path'])
    if digest != ref['sha256'] or obj.get('task_id') != task_id or obj.get('kind') != kind:
        raise AdmissionError(f'{kind}: artifact identity/hash mismatch')
    return obj

def load_profile(path, now=None):
    obj, digest = private_json(path)
    allowed = {'schema','task_id','kind','execution','measurement','oom_history','serial_contract','session','host_projection','node_plan','minimax_contract'}
    if set(obj) - allowed or obj.get('schema') != SCHEMA:
        raise AdmissionError('unknown profile schema/keys')
    task = obj.get('task_id')
    if not isinstance(task, str) or not task.strip() or len(task) > 160:
        raise AdmissionError('task_id required')
    if obj.get('kind') not in {'light_node','heavy','bounded_minimax_unmeasured'} or obj.get('execution') not in {'new_spawn','existing_session','codex_host_followup'}:
        raise AdmissionError('unknown workload/execution')
    now = time.time() if now is None else number(now,'now')
    oom = bound_artifact(obj.get('oom_history'), task, 'task_oom_history')
    if set(oom) != {'task_id','kind','checked_at_epoch','events','coverage'} or oom.get('coverage') != 'task_only_machine_unknown':
        raise AdmissionError('OOM coverage must disclose machine unknown')
    checked = number(oom['checked_at_epoch'], 'OOM checked_at')
    if not 0 <= now - checked <= MAX_AGE or not isinstance(oom['events'],list):
        raise AdmissionError('OOM evidence stale/future/unknown')
    recent = False
    for event in oom['events']:
        if not isinstance(event,dict) or set(event) != {'at_epoch','type'} or event['type'] != 'oom':
            raise AdmissionError('unknown OOM event')
        at = number(event['at_epoch'],'OOM at')
        if at > checked:
            raise AdmissionError('OOM event after evidence')
        recent |= now - at <= OOM_LOOKBACK
    serial = obj.get('serial_contract')
    if not isinstance(serial,dict) or set(serial) != {'coordinator','task_id','writer_limit','scope'} or not isinstance(serial['coordinator'],str) or not serial['coordinator'].strip() or serial['task_id'] != task or type(serial['writer_limit']) is not int or serial['writer_limit'] != 1 or serial['scope'] != 'original_pm_serial_only':
        raise AdmissionError('explicit original PM serial contract required')
    budget_floor = 3 * GIB
    if obj['kind'] == 'light_node':
        measure = bound_artifact(obj.get('measurement'),task,'node_measurement')
        if set(measure) != {'kind','task_id','peak_rss_bytes','heap_mb','exit_code','workload'} or measure['workload'] != 'bounded_node_no_build_no_browser' or type(measure['exit_code']) is not int or measure['exit_code'] != 0:
            raise AdmissionError('successful bounded Node measurement required')
        heap = number(measure['heap_mb'],'measured heap',True,1)
        peak = number(measure['peak_rss_bytes'],'peak RSS',True,1)
        if heap > 512:
            raise AdmissionError('measured heap above 512MiB')
        budget_floor = max(2 * GIB, peak + 512 * 1024 ** 2 + GIB)
    elif 'measurement' in obj:
        raise AdmissionError('heavy profile cannot use Node discount')
    if obj['kind'] == 'bounded_minimax_unmeasured':
        if obj['execution'] != 'new_spawn':
            raise AdmissionError('MiniMax unmeasured profile supports new_spawn only')
        contract = bound_artifact(obj.get('minimax_contract'),task,'bounded_minimax_contract')
        expected = {'kind':'bounded_minimax_contract','task_id':task,'workload':'standard_library_preview_or_readonly_routing_no_build_browser_video_server_install','rss_measurement':'not_measured','whole_worker_budget_bytes':3*GIB,'scope_enforcement':'original_PM_contract_not_process_sandbox'}
        if contract != expected:
            raise AdmissionError('explicit bounded MiniMax unmeasured contract required')
    elif 'minimax_contract' in obj:
        raise AdmissionError('MiniMax contract cannot be claimed by another workload')
    if obj['execution'] == 'existing_session':
        verify_session(obj.get('session'))
    elif 'session' in obj:
        raise AdmissionError('new spawn cannot claim an existing session')
    if obj['execution'] == 'codex_host_followup':
        if obj['kind'] != 'light_node':
            raise AdmissionError('host followup supports only explicit bounded light Node workload')
        host = bound_artifact(obj.get('host_projection'),task,'codex_host_tool_projection')
        verify_host_projection(host,task,now)
        plan = bound_artifact(obj.get('node_plan'),task,'scoped_node_plan')
        validate_node_plan(plan,task,require_exists=False)
    elif 'host_projection' in obj or 'node_plan' in obj:
        raise AdmissionError('host artifacts cannot be claimed by new spawn/existing Node runtime')
    return {**obj, '_sha256':digest,'_path':str(path),'_budget_floor':budget_floor,'_recent_oom':recent}

HOST_MAX_AGE = 120


def verify_host_projection(host,task,now=None):
    now = time.time() if now is None else number(now,'host check time')
    required={'kind','task_id','observed_at_epoch','controller','selected_worker','agents','source'}
    if not isinstance(host,dict) or set(host) != required or host['kind'] != 'codex_host_tool_projection' or host['task_id'] != task:
        raise AdmissionError('host projection task/schema mismatch')
    checked = number(host['observed_at_epoch'],'host observation')
    if not 0 <= now-checked <= HOST_MAX_AGE:
        raise AdmissionError('host projection stale/future')
    source=host['source']
    if source != {'type':'original_controller_tool_attestation','tool':'collaboration.list_agents','platform_signed':False}:
        raise AdmissionError('host source must disclose PM tool attestation, not platform signature')
    controller=host['controller'];worker=host['selected_worker']
    if not isinstance(controller,dict) or set(controller) != {'thread_id','canonical_parent'} or controller['canonical_parent'] != '/root' or not isinstance(controller['thread_id'],str) or not controller['thread_id'] or controller['thread_id'] != os.environ.get('CODEX_THREAD_ID'):
        raise AdmissionError('actual controller CODEX_THREAD_ID/parent mismatch or missing')
    if not isinstance(worker,dict) or set(worker) != {'canonical_path','status','opaque_agent_uuid','os_pid'}:
        raise AdmissionError('selected worker exact tool projection required')
    path=worker['canonical_path']
    if not isinstance(path,str) or not re.fullmatch(r'/root/[a-z0-9_]+(?:/[a-z0-9_]+)*',path) or worker['status'] != 'completed' or worker['opaque_agent_uuid'] is not None or worker['os_pid'] is not None:
        raise AdmissionError('worker unavailable/conflicting/unknown identity; Node PID is not Agent identity')
    agents=host['agents']
    if not isinstance(agents,list) or not agents:
        raise AdmissionError('formal host inventory missing')
    inventory={}
    for item in agents:
        if not isinstance(item,dict) or set(item) != {'canonical_path','status'} or not isinstance(item['canonical_path'],str) or item['canonical_path'] in inventory or item['status'] not in {'running','completed','idle'}:
            raise AdmissionError('host inventory malformed/duplicate/conflicting')
        inventory[item['canonical_path']]=item['status']
    if inventory.get('/root') != 'running' or inventory.get(path) != 'completed':
        raise AdmissionError('host inventory does not corroborate controller/selected worker')
    return {'controller_thread_id':controller['thread_id'],'parent':'/root','worker':path,
            'source':'original_controller_tool_attestation','platform_signed':False,
            'opaque_agent_uuid':None,'agent_os_pid':None,'observed_at_epoch':checked}


def validate_node_plan(plan,task,require_exists=False):
    if not isinstance(plan,dict) or set(plan) != {'kind','task_id','cwd','argv','entry_sha256'} or plan.get('kind') != 'scoped_node_plan' or plan.get('task_id') != task:
        raise AdmissionError('scoped Node plan task/schema mismatch')
    cwd=Path(plan['cwd'])
    if not cwd.is_absolute() or str(cwd.resolve()) != str(cwd) or cwd.is_symlink():
        raise AdmissionError('Node cwd must be canonical nonlink scoped path')
    cwd_identity=None
    if cwd.exists():
        info=cwd.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise AdmissionError('Node cwd must be owned directory, nonwritable by others')
        cwd_identity={'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid,'mode':stat.S_IMODE(info.st_mode)}
    elif require_exists:
        raise AdmissionError('planned Node cwd does not exist; execution refused')
    argv=plan['argv']
    if not isinstance(argv,list) or len(argv)<4 or any(not isinstance(x,str) or not x or '\x00' in x or '\n' in x for x in argv):
        raise AdmissionError('scoped Node literal argv required')
    interpreter=Path(argv[0])
    if not interpreter.is_absolute() or str(interpreter.resolve()) != str(interpreter):
        raise AdmissionError('Node interpreter must be canonical absolute path')
    if argv[1:3] != ['--max-old-space-size=480','--max-semi-space-size=1']:
        raise AdmissionError('scoped Node exact heap startup flags required')
    entry=Path(argv[3])
    if entry.is_absolute() or str(entry) != argv[3] or '..' in entry.parts or argv[3].startswith('-'):
        raise AdmissionError('scoped Node entry escapes cwd/unknown startup mode')
    path=cwd/entry
    if path.resolve() != path or path.is_symlink():
        raise AdmissionError('scoped Node entry symlink/path escape')
    if not isinstance(plan['entry_sha256'],str) or not re.fullmatch(r'[0-9a-f]{64}',plan['entry_sha256']):
        raise AdmissionError('planned Node entry content hash required')
    for arg in argv[4:]:
        if re.search(r'NODE_OPTIONS|max[-_]old[-_]space[-_]size|max[-_]semi[-_]space[-_]size|max[-_]heap[-_]size',arg,re.I):
            raise AdmissionError('scoped Node override conflict')
        value=arg.split('=',1)[-1]
        value_path=Path(value)
        resolved_value=(value_path if value_path.is_absolute() else cwd/value_path).resolve()
        if '..' in value_path.parts or not resolved_value.is_relative_to(cwd):
            raise AdmissionError('scoped argument path escape or symlink escape')
    node=trusted_node(str(interpreter))
    entry_identity=None
    if path.exists():
        entry_identity=file_fingerprint(path)
        if entry_identity['sha256'] != plan['entry_sha256']:
            raise AdmissionError('Node scoped entry content drift')
    elif require_exists:
        raise AdmissionError('Node scoped entry missing; execution refused')
    return {'cwd':str(cwd),'cwd_identity':cwd_identity,'argv':[node['path'],*argv[1:3],str(path),*argv[4:]],
            'node':node,'entry':entry_identity,'entry_sha256':plan['entry_sha256'],
            'cwd_state':'existing' if cwd.exists() else 'planned_not_created',
            'execution_ready':cwd.exists() and entry_identity is not None}


def bind_host_profile(profile,require_exists=False):
    if profile['execution'] != 'codex_host_followup':
        raise AdmissionError('host consumer requires codex_host_followup profile')
    host=bound_artifact(profile.get('host_projection'),profile['task_id'],'codex_host_tool_projection')
    identity=verify_host_projection(host,profile['task_id'])
    plan=bound_artifact(profile.get('node_plan'),profile['task_id'],'scoped_node_plan')
    node=validate_node_plan(plan,profile['task_id'],require_exists)
    return {'schema':'memory-task-host.binding.v1','profile_sha256':profile['_sha256'],
            'artifact_hashes':{key:profile[key]['sha256'] for key in ('measurement','oom_history','host_projection','node_plan')},
            'task_id':profile['task_id'],'execution':'codex_host_followup','host':identity,'workload_node':node,
            'budget_floor_bytes':profile['_budget_floor'],'reuse_discount_bytes':0,
            'agent_process_identity':'not_exposed_by_tool; never Node PID','cross_pm_reservation':'NOT_VERIFIED'}


def session_readback(pid):
    proc = subprocess.run(['/bin/ps','-p',str(pid),'-o','uid=','-o','lstart=','-o','command='],capture_output=True,text=True,timeout=5)
    line = proc.stdout.strip()
    match = re.fullmatch(r'(\d+)\s+(\w+\s+\w+\s+\d+\s+\d+:\d+:\d+\s+\d+)\s+(.+)',line)
    if proc.returncode or not match:
        raise AdmissionError('session disappeared/identity unreadable')
    return {'uid':int(match[1]),'start':match[2],'command_sha256':hashlib.sha256(match[3].encode()).hexdigest(),'argv':shlex.split(match[3])}

def verify_session(session):
    if not isinstance(session,dict) or set(session) != {'pid','uid','start','command_sha256'}:
        raise AdmissionError('exact existing Node process identity required')
    pid = number(session['pid'],'session pid',True,1)
    if type(session['uid']) is not int or session['uid'] != os.getuid():
        raise AdmissionError('session UID mismatch')
    actual = session_readback(pid)
    if any(actual[k] != session[k] for k in ('uid','start','command_sha256')):
        raise AdmissionError('session identity drift')
    argv = actual['argv']
    if not argv or Path(argv[0]).name != 'node':
        raise AdmissionError('existing Agent runtime is not a proven Node workload; unsupported')
    # Only one literal heap flag at Node argv head is supported. Future workload
    # commands sent to non-Node Agent sessions are intentionally unsupported.
    if len(argv) < 4 or not re.fullmatch(r'--max-old-space-size=([1-9]\d*)',argv[1]) or int(argv[1].split('=')[1]) > 480 or argv[2] != '--max-semi-space-size=1':
        raise AdmissionError('actual Node startup heap <=512MiB not proven')
    if any(re.search(r'NODE_OPTIONS|max[-_]old[-_]space[-_]size|max[-_]semi[-_]space[-_]size|max[-_]heap[-_]size',word,re.I) for word in argv[3:]):
        raise AdmissionError('session heap override conflict')
    return {k:actual[k] for k in ('uid','start','command_sha256')}

def file_fingerprint(path):
    path = Path(path).resolve(strict=True)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022:
        raise AdmissionError('launcher/interpreter must be regular nonwritable file')
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'device':info.st_dev,'inode':info.st_ino,'size':info.st_size}


def trusted_node(explicit_path=None):
    found = explicit_path or shutil.which('node')
    if not found:
        raise AdmissionError('Node interpreter unavailable')
    fingerprint = file_fingerprint(found)
    with open(fingerprint['path'],'rb') as stream:
        magic = stream.read(4)
    if magic not in (b'\x7fELF', b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xfe\xed\xfa\xce', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca', b'\xca\xfe\xba\xbf'):
        raise AdmissionError('Node interpreter is not a native binary; PATH wrapper refused')
    clean = dict(os.environ)
    clean.pop('NODE_OPTIONS',None)
    result = subprocess.run([fingerprint['path'],'--max-old-space-size=480','--max-semi-space-size=1','-e',
        'process.stdout.write(JSON.stringify({execPath:process.execPath,version:process.versions.node,heap:require("v8").getHeapStatistics().heap_size_limit}))'],
        env=clean,capture_output=True,text=True,timeout=5)
    try:
        observed = json.loads(result.stdout)
    except ValueError:
        raise AdmissionError('Node runtime observation unreadable')
    if result.returncode or Path(observed.get('execPath','')).resolve() != Path(fingerprint['path']) or not re.fullmatch(r'\d+\.\d+\.\d+',observed.get('version','')) or number(observed.get('heap'),'actual Node heap',True,1) > 512*1024**2 or file_fingerprint(found) != fingerprint:
        raise AdmissionError('Node runtime identity/heap observation failed')
    return {**fingerprint,'observed_heap_bytes':observed['heap'],'version':observed['version']}


def bind_spawn(profile, command, backend, script_dir, env=None):
    env = os.environ if env is None else env
    if profile['execution'] != 'new_spawn':
        raise AdmissionError('spawn cannot consume existing_session profile')
    if profile['kind'] == 'bounded_minimax_unmeasured':
        import minimax_memory_binding as mm
        try:
            plan = mm.command_plan(command,backend,script_dir,env)
        except (ValueError,OSError,KeyError) as exc:
            raise AdmissionError(str(exc)) from exc
        return {'schema':'memory-task-spawn.binding.v1','profile_sha256':profile['_sha256'],
                'artifact_hashes':{key:profile[key]['sha256'] for key in ('oom_history','minimax_contract')},
                'task_id':profile['task_id'],'execution':'new_spawn','kind':profile['kind'],
                'heap_mb':None,'whole_worker_budget_floor_bytes':3*GIB,'whole_worker_rss_measurement':'not_measured',
                'command_sha256':hashlib.sha256(command.encode()).hexdigest(),'backend':backend,'minimax':plan}
    words = shlex.split(command)
    if not words or any(word in {';','&&','||','|','<','>','exec'} for word in words) or any('\n' in word for word in words):
        raise AdmissionError('opaque command is unsupported by task binding')
    spec = importlib.util.spec_from_file_location('worker_command_validator',Path(script_dir)/'validate-worker-command.py')
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    validator.validate_safe_command_substitutions(command)
    resolved = []
    actual = validator.command_backend(words,expected=backend,trusted_claude_wrapper=str(Path(script_dir)/'claude-provider-env.sh'),trusted_zcode_driver=str(Path(script_dir)/'zcode-worker-driver.py'),shell_body=True,resolved_argv=resolved)
    if actual != backend or resolved != words:
        raise AdmissionError('shell/env wrapper ambiguous: explicit plain actual argv required')
    executable = Path(shutil.which(resolved[0]) or resolved[0]).resolve(strict=True)
    binding = {'schema':'memory-task-spawn.binding.v1','profile_sha256':profile['_sha256'],
        'artifact_hashes':{key:profile[key]['sha256'] for key in ('measurement','oom_history') if key in profile},
        'task_id':profile['task_id'],'execution':'new_spawn','kind':profile['kind'],
        'heap_mb':None,'command_sha256':hashlib.sha256(command.encode()).hexdigest(),
        'backend':backend,'argv':[str(executable),*resolved[1:]],'entry':file_fingerprint(executable)}
    if profile['kind'] != 'light_node':
        return binding
    if env.get('NODE_OPTIONS','') or env.get('SPAWN_WORKER_NODE_MAX_OLD_SPACE_MB','512') != '512':
        raise AdmissionError('light Node caller heap conflict')
    if re.search(r'NODE_OPTIONS|max[-_]old[-_]space[-_]size|max[-_]semi[-_]space[-_]size|max[-_]heap[-_]size',command,re.I):
        raise AdmissionError('command heap override conflict')
    with executable.open('rb') as stream:
        line = stream.readline(256).decode('utf-8',errors='strict').rstrip('\r\n')
    if line != '#!/usr/bin/env node' and not (line.startswith('#!/') and Path(line[2:]).name == 'node' and Path(line[2:]).is_file()):
        raise AdmissionError('actual worker runtime not proven Node; unsupported')
    node = trusted_node()
    if line != '#!/usr/bin/env node' and str(Path(line[2:]).resolve()) != node['path']:
        raise AdmissionError('shebang interpreter differs from proven Node binary')
    binding.update(heap_mb=512,old_space_mb=480,semi_space_mb=1,node=node,
        enforcement='canonical_Node_argv_and_exec_guard',child_override_protection='task_scope_only')
    return binding


def encode_binding(binding):
    return base64.urlsafe_b64encode(json.dumps(binding,sort_keys=True,separators=(',',':')).encode()).decode()


def verify_binding(path,command,backend,script_dir,encoded):
    try:
        expected = json.loads(base64.urlsafe_b64decode(encoded))
    except (ValueError,TypeError):
        raise AdmissionError('binding is unreadable')
    profile = load_profile(path)
    actual = bind_spawn(profile,command,backend,script_dir)
    if expected != actual:
        raise AdmissionError('profile/artifact/command/entry/interpreter binding drift')
    return profile,actual


def outer_environment(outer,original,kind):
    # Only the exact original argv suffix plus generated env assignments is
    # admitted; provider shell wrappers and arbitrary launchers are refused.
    if not outer.endswith(original):
        raise AdmissionError('outer command no longer has bound argv suffix')
    prefix = outer[:-len(original)]
    additions = {}
    for word in shlex.split(prefix):
        if word == 'env':
            continue
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*=.*',word,re.S):
            raise AdmissionError('unproven outer shell wrapper')
        name,value = word.split('=',1)
        if name in {'PATH','NODE_OPTIONS','NODE_PATH'} or name.startswith(('LD_','DYLD_')):
            raise AdmissionError('outer runtime override refused')
        additions[name] = value
    return additions


def render_launch(path,command,backend,script_dir,encoded,outer,execution_cwd=None,pregate_branch=None,pregate_head=None,pregate_common=None):
    profile,binding = verify_binding(path,command,backend,script_dir,encoded)
    additions = outer_environment(outer,command,binding['kind'])
    argv = [str(Path(sys.executable).resolve()),str(Path(__file__).resolve()),'exec-bound',
            '--profile',path,'--command',command,'--backend',backend,'--binding-b64',encoded,
            '--outer-command',outer]
    if binding['kind'] == 'bounded_minimax_unmeasured':
        import minimax_memory_binding as mm
        if not execution_cwd:
            raise AdmissionError('late existing worktree cwd binding required')
        cwd=mm.cwd_identity(execution_cwd,pregate_branch,pregate_head,pregate_common)
        argv += ['--execution-cwd-binding',encode_binding(cwd)]
    return shlex.join(argv)


def exec_bound(path,command,backend,script_dir,encoded,outer,execution_cwd_binding=None):
    profile,binding = verify_binding(path,command,backend,script_dir,encoded)
    additions = outer_environment(outer,command,binding['kind'])
    env = dict(os.environ)
    env.update(additions)
    if binding['kind'] == 'bounded_minimax_unmeasured':
        import minimax_memory_binding as mm
        if not execution_cwd_binding:
            raise AdmissionError('MiniMax actual cwd binding missing')
        mm.execute(binding['minimax'],env,json.loads(base64.urlsafe_b64decode(execution_cwd_binding)))
        raise AdmissionError('MiniMax exec unexpectedly returned')
    if binding['kind'] == 'light_node':
        # Never execute a mutable shebang or a PATH launcher. The fixed binary
        # and fixed startup flags are the only permitted Node entry.
        env.pop('NODE_OPTIONS',None)
        node = binding['node']['path']
        argv = [node,'--max-old-space-size=480','--max-semi-space-size=1',*binding['argv']]
    else:
        argv = binding['argv']
        if 'NODE_OPTIONS' not in env:
            env['NODE_OPTIONS']='--max-old-space-size=2048'
    # Last check immediately before exec; same path, inode and bytes must remain.
    if file_fingerprint(binding['entry']['path']) != binding['entry']:
        raise AdmissionError('entry changed at actual execution boundary')
    if binding['kind'] == 'light_node':
        current = file_fingerprint(node)
        if any(current[k] != binding['node'][k] for k in current):
            raise AdmissionError('interpreter changed at actual execution boundary')
    os.execve(argv[0],argv,env)


def counters(raw):
    values = []
    for name in ('Swapouts','Pageouts'):
        matches = re.findall(r'^'+name+r':\s*(\d+)\.?\s*$',raw or '',re.M)
        if len(matches) != 1:
            raise AdmissionError('missing/duplicate cumulative '+name)
        values.append(int(matches[0]))
    return tuple(values)

def strict_swap(raw):
    if not isinstance(raw,str):
        raise AdmissionError('raw swap unreadable')
    fields = {}
    for key in ('total','used','free'):
        tokens = re.findall(r'\b'+key+r'\s*=\s*(\S+)',raw)
        matches = [re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)([KMGT])',token) for token in tokens]
        if len(matches) != 1 or matches[0] is None:
            raise AdmissionError('raw swap missing/duplicate/invalid field')
        value,unit = matches[0].groups()
        fields[key] = float(value)*1024**({'K':1,'M':2,'G':3,'T':4}[unit])
        number(fields[key],'raw swap '+key)
    if fields['used'] > fields['total'] or fields['free'] > fields['total'] or abs(fields['used']+fields['free']-fields['total']) > 1024**2:
        raise AdmissionError('raw swap ledger inconsistent; clamping cannot authorize task')
    return fields


def apply_profile(profile, samples, budget, evaluator):
    """samples 是本 collector 记录的单调时钟/raw；从未声称 caller JSON 是现场。"""
    budget = number(budget,'budget',True,profile['_budget_floor'])
    payload = evaluator(samples[-1]['raw'],budget,'task_profile')
    receipt = {'schema':'memory-task-admission.receipt.v1','profile_sha256':profile['_sha256'],'task_id':profile['task_id'],'kind':profile['kind'],'execution':profile['execution'],'budget_floor_bytes':profile['_budget_floor'],'reuse_discount_bytes':0,'writer_limit':1,'coordination':'original_pm_serial_only','cross_pm_reservation':'NOT_VERIFIED','oom_coverage':'task_only_machine_unknown','sample_count':len(samples),'high_swap_exception':False}
    payload['task_admission'] = receipt
    payload['telemetry']['kernel_pressure']['used_for_admission'] = True
    def deny(reason):
        payload.update(status='denied',slots=0,reason=reason)
        return payload
    if profile['_recent_oom']:
        return deny('task recent OOM: no experimental admission')
    if profile['execution'] == 'existing_session':
        verify_session(profile.get('session'))
    if profile['execution'] == 'codex_host_followup':
        receipt['host_binding'] = bind_host_profile(profile)
    evaluated = []
    previous_time = None
    for sample in samples:
        timestamp = number(sample['at_monotonic'],'sample clock')
        if previous_time is not None and timestamp <= previous_time:
            return deny('nonmonotonic observation clock')
        previous_time = timestamp
        row = evaluator(sample['raw'],budget,'task_profile')
        evaluated.append(row)
        native = row['telemetry']['kernel_pressure']
        if native['level'] not in {'normal','warn'}:
            return deny('native pressure critical/unknown: opt-in hard refusal')
        if row.get('safe_available_bytes',0) < budget or row.get('availability_basis') != 'vm_stat':
            return deny('physical vm_stat reserve/budget not satisfied')
        mp = row['telemetry']['memory_pressure']
        if not row['telemetry']['sources']['memory_pressure']['parse_valid'] or mp['level'] == 'critical':
            return deny('memory pressure critical/unreadable')
        try:
            strict_swap(sample['raw'].get('vm_swapusage'))
        except AdmissionError as exc:
            return deny(str(exc))
        swap = row.get('swap')
        if not swap or any(not isinstance(swap[k],(int,float)) or isinstance(swap[k],bool) or not math.isfinite(swap[k]) or swap[k] < 0 for k in ('total_bytes','used_bytes','free_bytes')) or swap['used_bytes'] > swap['total_bytes']:
            return deny('invalid swap accounting')
    needs_exception = any(row.get('pressure',{}).get('level') in {'warn','critical'} for row in evaluated)
    legacy_needs_exception=needs_exception
    if profile['kind'] == 'bounded_minimax_unmeasured':
        receipt.update(whole_worker_rss_measurement='not_measured',whole_worker_rss_cap=None)
        needs_exception=True  # This experimental unmeasured contract always needs the complete window.
    if not needs_exception:
        if payload['status'] == 'ok':
            payload['slots'] = min(1,payload['slots'])
        return payload
    if profile['kind'] not in {'light_node','bounded_minimax_unmeasured'}:
        return deny('heavy workload cannot use swap exception')
    if any(row['telemetry']['memory_pressure']['level'] == 'warn' for row in evaluated):
        return deny('legacy native keyword/available-percent warning is not a swap-only exception')
    if len(samples) < 3 or samples[-1]['at_monotonic'] - samples[0]['at_monotonic'] < 20:
        return deny('stable observation requires >=20s and >=3 samples')
    try:
        counts = [counters(sample['raw'].get('vm_stat')) for sample in samples]
    except AdmissionError as exc:
        return deny(str(exc))
    for i in range(1,len(samples)):
        if counts[i] != counts[i-1]:
            return deny('swapouts/pageouts growth or counter rollback')
        if evaluated[i]['swap']['used_bytes'] > evaluated[i-1]['swap']['used_bytes']:
            return deny('swapused growth')
    # Keep legacy pressure/swap intact; this explicitly bounded decision is a
    # separate experimental authority, never a fake normal kernel reading.
    receipt.update(effective_capacity_bytes=min(row['safe_available_bytes'] for row in evaluated),effective_capacity_source='minimum_vm_stat_available_minus_legacy_reserve_across_window',budget_bytes=budget,legacy_effective_available_bytes=payload.get('effective_available_bytes'),high_swap_exception=legacy_needs_exception,window_seconds=samples[-1]['at_monotonic']-samples[0]['at_monotonic'],cumulative_deltas={'swapouts':0,'pageouts':0})
    payload.update(status='ok',slots=1,reason='experimental '+profile['kind']+' stable-window admission; original PM serial only; machine OOM unknown')
    return payload

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation',choices=['bind-spawn','render-launch','exec-bound'])
    parser.add_argument('--profile',required=True)
    parser.add_argument('--command',required=True)
    parser.add_argument('--backend',required=True)
    parser.add_argument('--script-dir',default=str(Path(__file__).parent))
    parser.add_argument('--binding-b64',default=None)
    parser.add_argument('--outer-command',default=None)
    parser.add_argument('--execution-cwd',default=None)
    parser.add_argument('--execution-cwd-binding',default=None)
    parser.add_argument('--pregate-branch',default=None)
    parser.add_argument('--pregate-head',default=None)
    parser.add_argument('--pregate-common',default=None)
    args = parser.parse_args()
    try:
        if args.operation == 'bind-spawn':
            profile = load_profile(args.profile)
            result = bind_spawn(profile,args.command,args.backend,args.script_dir)
            print(json.dumps(result,sort_keys=True))
        elif args.operation == 'render-launch':
            if not args.binding_b64 or not args.outer_command:
                raise AdmissionError('frozen binding and actual outer command required')
            print(render_launch(args.profile,args.command,args.backend,args.script_dir,args.binding_b64,args.outer_command,args.execution_cwd,args.pregate_branch,args.pregate_head,args.pregate_common))
        else:
            if not args.binding_b64 or not args.outer_command:
                raise AdmissionError('frozen binding and actual outer command required')
            exec_bound(args.profile,args.command,args.backend,args.script_dir,args.binding_b64,args.outer_command,args.execution_cwd_binding)
        return 0
    except (AdmissionError,OSError,ValueError,KeyError,TypeError) as exc:
        print('MEMORY_TASK_PROFILE_REFUSED: '+str(exc),file=sys.stderr)
        return 64

if __name__ == '__main__':
    sys.exit(main())
