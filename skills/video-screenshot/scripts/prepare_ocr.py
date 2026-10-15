#!/usr/bin/env python3
"""Explicit backend preparation; never changes global Python or installs silently."""
import argparse
from hashlib import sha256
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
from ocr_runtime import SKILL,component_key,runtime_root,prepared


def prepare(engine,root,install=False,python=None):
    ready=prepared(engine,root)
    if ready:
        return {'engine':engine,'status':'ready','executable':ready,'reused':True}
    if engine=='rapidocr' and not install:
        return {'engine':engine,'status':'blocked','code':'EXPLICIT_DEPENDENCY_PREPARATION_REQUIRED',
                'next_action':'prepare_with_install_deps_only_when_authorized',
                'message':'两种适配均在Skill内；Rapid运行包/模型需独立环境。此入口不默认安装，明确准备时再传--install-deps；不改全局/user-site。'}
    commands=[]
    if engine=='vision':
        compiler=shutil.which('swiftc')
        if sys.platform!='darwin' or not compiler:
            return {'engine':engine,'status':'blocked','code':'VISION_COMPILER_UNAVAILABLE'}
    else:
        names=[python] if python else ['python3.12','python3.11','python3.10']
        candidates=[shutil.which(name) for name in names]
        rejected=[]
        chosen=None
        for candidate in dict.fromkeys(x for x in candidates if x):
            probe=subprocess.run([candidate,'-I','-c','import sys,json,platform; print(json.dumps({"version":list(sys.version_info[:2]),"architecture":platform.machine()}))'],capture_output=True,text=True,timeout=15,check=False)
            if probe.returncode:
                rejected.append({'python':candidate,'reason':'probe_failed'});continue
            info=json.loads(probe.stdout)
            if not [3,10]<=info['version']<[3,13]:
                rejected.append({'python':candidate,'reason':'unsupported_version','details':info});continue
            if info['architecture']!=platform.machine():
                rejected.append({'python':candidate,'reason':'architecture_mismatch','details':info});continue
            chosen=candidate;break
        if not chosen:
            return {'engine':engine,'status':'blocked','code':'SUPPORTED_NATIVE_PYTHON_NOT_FOUND','host_architecture':platform.machine(),'rejected':rejected,'message':'需要已有、与当前进程架构一致的Python3.10—3.12；不自动安装Python，不用Rosetta解释器冒充原生运行。'}
    for parent in [root,*root.parents]:
        if parent.is_symlink():
            raise ValueError('runtime目录/父目录为符号链接，拒绝写入')
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    directory=root/component_key(engine)
    directory.mkdir(mode=0o700)  # Never overwrite unknown or interrupted preparation.
    try:
        if engine=='vision':
            executable=directory/'video-screenshot-vision'
            commands=[[compiler,str(SKILL/'scripts/scroll_vision.swift'),'-o',str(executable)]]
        else:
            commands=[[chosen,'-I','-m','venv',str(directory/'venv')]]
            executable=directory/'venv/bin/python'
            # This package-install command is reachable only with explicit --install-deps.
            commands.append([str(executable),'-I','-m','pip','--isolated','install','--index-url','https://pypi.org/simple','--disable-pip-version-check','--no-cache-dir','-r',str(SKILL/'config/rapidocr-requirements.txt')])
        logs=[]
        for argv in commands:
            env={key:os.environ[key] for key in ['PATH','HOME','TMPDIR','LANG','LC_ALL','SYSTEMROOT'] if key in os.environ}
            proc=subprocess.run(argv,capture_output=True,text=True,timeout=600,check=False,env=env)
            logs.append({'argv':argv,'exit_code':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr})
            (directory/'prepare-processes.json').write_text(json.dumps(logs,ensure_ascii=False,indent=2)+'\n')
            if proc.returncode:
                raise RuntimeError('本地准备失败，保留诊断：'+str(directory))
        marker={'engine':engine,'status':'ready','component_key':component_key(engine),
                'executable_relative':str(executable.relative_to(directory)),
                'executable_sha256':sha256(executable.read_bytes()).hexdigest(),
                'host_architecture':platform.machine(),'python_probe':info if engine=='rapidocr' else None,
                'independent_environment':engine=='rapidocr','engine_probe':'not_run_use_check_scroll_env'}
        (directory/'runtime.json').write_text(json.dumps(marker,ensure_ascii=False,indent=2)+'\n')
        return {'engine':engine,'status':'ready','executable':str(executable),'engine_probe':'not_run'}
    except Exception as exc:
        (directory/'preparation-error.json').write_text(json.dumps({'status':'failed','error':str(exc)})+'\n')
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine',choices=['vision','rapidocr','both'],default='both')
    p.add_argument('--runtime-dir')
    p.add_argument('--install-deps',action='store_true',help='明确允许在Skill专属venv安装Rapid依赖/模型；可能联网，不改全局')
    p.add_argument('--python',help='已有Python3.10—3.12；不自动下载解释器')
    args=p.parse_args()
    try:
        results=[prepare(e,runtime_root(args.runtime_dir),args.install_deps,args.python) for e in (['vision','rapidocr'] if args.engine=='both' else [args.engine])]
        print(json.dumps({'results':results},ensure_ascii=False));return 0 if all(r['status']=='ready' for r in results) else 2
    except (ValueError,OSError,RuntimeError,subprocess.SubprocessError) as exc:
        print(json.dumps({'status':'blocked','error':str(exc)},ensure_ascii=False));return 2

if __name__=='__main__':raise SystemExit(main())
