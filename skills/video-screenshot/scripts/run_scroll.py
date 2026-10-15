#!/usr/bin/env python3
"""One entry for weak models; uses the Skill's prepared Python when available."""
import argparse
from pathlib import Path
import subprocess
import sys
from ocr_runtime import prepared
p=argparse.ArgumentParser(add_help=False)
p.add_argument('--runtime-dir')
p.add_argument('--check-env',action='store_true')
p.add_argument('--verify-output')
known,_=p.parse_known_args()
python=prepared('rapidocr',known.runtime_dir) or sys.executable
script='check_scroll_text.py' if known.verify_output else ('check_scroll_env.py' if known.check_env else 'scroll_text.py')
if known.verify_output and known.check_env:
    p.error('诊断与输出检查不能同时指定')
args=[x for x in sys.argv[1:] if x!='--check-env']
if known.verify_output:
    args=['--verify-output',known.verify_output]
raise SystemExit(subprocess.run([python,'-s',str(Path(__file__).with_name(script)),*args],check=False).returncode)
