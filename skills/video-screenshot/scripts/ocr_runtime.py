"""Skill-owned backend cache discovery, independent of global Python package paths."""
from hashlib import sha256
import json
import os
import platform
from pathlib import Path
import shutil
import sys

SKILL = Path(__file__).resolve().parent.parent

def runtime_root(value=None):
    if value:
        return Path(os.path.abspath(os.path.expanduser(value)))
    return Path.home()/('.cache/video-screenshot/ocr')


def component_key(engine):
    source = SKILL/('scripts/scroll_vision.swift' if engine=='vision' else 'config/rapidocr-requirements.txt')
    identity=source.read_bytes()+platform.machine().encode()
    return engine+'-'+sha256(identity).hexdigest()[:16]


def prepared(engine, root=None):
    directory=runtime_root(root)/component_key(engine)
    marker=directory/'runtime.json'
    if not marker.is_file() or marker.is_symlink():
        return None
    try:
        data=json.loads(marker.read_text())
        if data.get('status')!='ready' or data.get('component_key')!=component_key(engine):
            return None
        relative=Path(data['executable_relative'])
        if relative.is_absolute() or '..' in relative.parts:
            return None
        executable=directory/relative
        if not executable.is_file() or not os.access(executable,os.X_OK):
            return None
        if sha256(executable.read_bytes()).hexdigest()!=data['executable_sha256']:
            return None
        return str(executable)
    except (ValueError,KeyError,OSError,TypeError):
        return None


def backend_candidates(requested, executable=None, rapid_python=None, root=None):
    vision=shutil.which(executable) if executable else prepared('vision',root) or shutil.which('video-screenshot-vision')
    rapid=shutil.which(rapid_python) if rapid_python else prepared('rapidocr',root)
    if requested=='vision':
        return [('vision',vision)] if vision else []
    if requested=='rapidocr':
        # Explicit legacy interpreter remains available; doctor will diagnose it.
        return [('rapidocr',rapid or sys.executable)]
    choices=[]
    if vision:
        choices.append(('vision',vision))
    if rapid:
        choices.append(('rapidocr',rapid))
    return choices
