#!/usr/bin/env python3
"""Short, structured local OCR diagnostics for models with limited reasoning."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
from ocr_runtime import backend_candidates
import shutil
import subprocess
import sys
import tempfile


def package_visibility():
    # Discovery only: never import the OCR package to inspect its location.
    code = "import importlib.util,json; print(json.dumps({n:(s.origin if (s:=importlib.util.find_spec(n)) else None) for n in ['PIL','rapidocr_onnxruntime','onnxruntime']}))"
    try:
        visible = subprocess.run([sys.executable, '-s', '-c', code], capture_output=True,
                                 text=True, timeout=15, check=False)
        if visible.returncode:
            return {}, 'isolated Python package inspection failed'
        isolated = json.loads(visible.stdout)
        normal = {}
        for name in ('PIL', 'rapidocr_onnxruntime', 'onnxruntime'):
            spec = importlib.util.find_spec(name)
            normal[name] = spec.origin if spec else None
        return {'normal': normal, 'isolated': isolated}, None
    except (OSError, ValueError, subprocess.TimeoutExpired, ImportError) as exc:
        return {}, str(exc)


def diagnose(args):
    report = {'schema': 'video-screenshot-environment/1', 'status': 'blocked',
              'engine': args.engine, 'python': sys.executable,
              'code': None, 'next_action': None, 'message': '',
              'engine_probe': 'not_run', 'automatic_install': False, 'cloud_fallback': False}
    def blocked(code, action, message):
        report.update(code=code, next_action=action, message=message)
        return report
    if not all(shutil.which(name) for name in ('ffmpeg', 'ffprobe')):
        return blocked('VIDEO_TOOLS_MISSING', 'report_missing_tools', '缺少ffmpeg/ffprobe；报告缺项，不自行安装或换云服务。')
    packages, error = package_visibility()
    report['packages'] = packages
    if error:
        return blocked('PYTHON_PROBE_FAILED', 'report_python_diagnostic', error)
    if not packages['normal'].get('PIL'):
        return blocked('PILLOW_NOT_VISIBLE', 'use_prepared_python', '当前Python看不到Pillow；使用已经准备好的Python环境，缺少时报告，不自行安装。')
    if args.engine == 'auto':
        try:
            from scroll_ocr import LocalOCR
            engine=LocalOCR('auto',args.ocr_executable,timeout=args.timeout,deny_network=args.deny_network,
                            rapid_python=args.rapid_python,runtime_dir=args.runtime_dir)
            report.update(status='ready',engine=engine.engine,code='LOCAL_OCR_PROBE_OK',next_action='run_scroll_text',
                          message='本地后端已通过实际探测，统一入口将使用同一缓存/参数。',engine_probe='executed',
                          engine_executable=engine.executable,backend_failures=engine.backend_selection_failures)
            return report
        except Exception as exc:
            return blocked('NO_LOCAL_BACKEND_READY','prepare_local_backend',str(exc))
    if args.engine == 'rapidocr':
        choices=backend_candidates('rapidocr',rapid_python=args.rapid_python,root=args.runtime_dir)
        if not choices:
            return blocked('RAPID_PYTHON_INVALID', 'report_python_diagnostic', '显式Rapid解释器不存在或不可执行，不回退其他Python。')
        selected=choices[0][1]
        if selected != sys.executable:
            probe=subprocess.run([selected,'-s','-c',"import importlib.util,json; print(json.dumps({n:(s.origin if (s:=importlib.util.find_spec(n)) else None) for n in ['PIL','rapidocr_onnxruntime','onnxruntime']}))"],capture_output=True,text=True,timeout=15,check=False)
            if probe.returncode:
                return blocked('PYTHON_PROBE_FAILED','report_python_diagnostic',probe.stderr[-1000:])
            packages={'normal':json.loads(probe.stdout),'isolated':json.loads(probe.stdout)}
            report['packages']=packages
            report['worker_python']=selected
        missing = [name for name in ('PIL', 'rapidocr_onnxruntime', 'onnxruntime') if not packages['isolated'].get(name)]
        hidden = [name for name in missing if packages['normal'].get(name)]
        report['missing_in_worker'] = missing
        report['hidden_by_user_site_isolation'] = hidden
        if hidden:
            return blocked('USER_SITE_PACKAGES_HIDDEN', 'use_prepared_python_or_explicit_vision',
                           '包在普通Python中可见，但python -s的OCR进程看不到用户级包目录。不能称全机未安装；使用包齐全的已有独立环境，macOS也可明确选择Vision分支。保留隔离，不自动重装。')
        if missing:
            return blocked('RAPIDOCR_DEPENDENCIES_NOT_VISIBLE', 'use_prepared_python',
                           '当前OCR进程缺少可见依赖：'+', '.join(missing)+'；报告当前解释器与缺项，不自行安装。')
    elif not backend_candidates('vision',args.ocr_executable,root=args.runtime_dir):
        report['swiftc'] = shutil.which('swiftc')
        return blocked('VISION_HELPER_MISSING', 'compile_helper_if_swiftc_available',
                       '本地Vision helper不可用。已有swiftc时按执行卡编译到仓库外工具目录；没有编译器则报告缺项，不自动安装。')
    if args.deny_network and not shutil.which('sandbox-exec'):
        return blocked('NETWORK_GUARD_MISSING', 'report_network_guard', '要求拒绝网络，但sandbox-exec不可用；保持阻塞，不冒充隔离。')
    try:
        from PIL import Image, ImageDraw, ImageFont
        from scroll_ocr import LocalOCR, OCRFailure
        with tempfile.TemporaryDirectory(prefix='scroll-env-probe-') as folder:
            image_path = Path(folder).resolve()/'probe.png'
            image = Image.new('RGB', (800, 240), 'white')
            draw = ImageDraw.Draw(image)
            font = ImageFont.load_default()
            draw.text((20, 80), 'LOCAL OCR PROBE 12345', font=font, fill='black')
            # Enlarge actual glyph pixels for a legible, non-sensitive test image.
            image = image.resize((1600, 480))
            image.save(image_path)
            engine = LocalOCR(args.engine, args.ocr_executable, batch_size=1,
                              timeout=args.timeout, deny_network=args.deny_network,rapid_python=args.rapid_python,runtime_dir=args.runtime_dir)
            records = engine.recognize([image_path])
            report['engine_probe'] = 'executed'
            report['engine_executable'] = engine.executable
            report['process_exit_codes'] = [x.get('exit_code') for x in engine.processes]
            probe_text = ''.join(line['text'] for line in records[0]['normalized_lines']).upper().replace(' ', '')
            if 'PROBE' not in probe_text or '12345' not in probe_text:
                return blocked('OCR_PROBE_EMPTY', 'report_engine_probe', '引擎未报错，但未识别到测试图的PROBE与12345锚点；不宣称可用。')
    except Exception as exc:
        report['engine_probe'] = 'failed'
        return blocked('OCR_PROBE_FAILED', 'report_engine_probe', f'{type(exc).__name__}: {exc}')
    report.update(status='ready', code='LOCAL_OCR_PROBE_OK', next_action='run_scroll_text',
                  message='实际非敏感图片OCR成功，可进入固定录屏入口；不代表真实正文准确率。')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine', choices=['auto','vision','rapidocr'], default='auto')
    p.add_argument('--ocr-executable')
    p.add_argument('--rapid-python')
    p.add_argument('--runtime-dir')
    p.add_argument('--deny-network', action='store_true')
    p.add_argument('--timeout', type=int, default=90)
    args=p.parse_args()
    if not 1 <= args.timeout <= 600:
        p.error('--timeout需在1—600秒之间')
    result=diagnose(args)
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['status']=='ready' else 2

if __name__=='__main__':raise SystemExit(main())
