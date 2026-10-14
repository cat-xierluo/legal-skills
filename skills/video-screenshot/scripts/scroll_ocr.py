"""Local OCR adapters; failures are explicit and never become empty success."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


class OCRFailure(RuntimeError):
    pass


def normalize_lines(record):
    if not isinstance(record, dict) or record.get('error'):
        raise OCRFailure(str(record.get('error', 'invalid OCR object')) if isinstance(record, dict) else 'invalid OCR object')
    raw = record.get('lines')
    if not isinstance(raw, list):
        raise OCRFailure('OCR 缺少 lines 数组')
    result = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            result.append({'text': item, 'bbox': None, 'confidence': None, 'raw_index': index})
            continue
        if not isinstance(item, dict) or not isinstance(item.get('text'), str):
            raise OCRFailure('OCR 行格式错误')
        box, score = item.get('bbox'), item.get('confidence')
        if box is not None and (not isinstance(box, list) or len(box) != 4 or
                not all(isinstance(v, (int, float)) and math.isfinite(v) and -.02 <= v <= 1.02 for v in box) or
                box[0] >= box[2] or box[1] >= box[3]):
            raise OCRFailure('OCR bbox 须为有限、顺序正确的真实归一化框（仅容许2%边缘溢出）')
        if score is not None and (not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1):
            raise OCRFailure('OCR confidence 无效')
        result.append({'text': item['text'], 'bbox': box, 'confidence': score, 'raw_index': index, 'bbox_outside_image': bool(box and any(v < 0 or v > 1 for v in box))})
    # Boxless legacy helpers retain their original order and no invented coordinates.
    if result and all(x['bbox'] is not None for x in result):
        result.sort(key=lambda x: (round(x['bbox'][1], 2), x['bbox'][0]))
    return result


class LocalOCR:
    def __init__(self, engine, executable=None, batch_size=8, timeout=90, deny_network=False):
        self.engine, self.batch_size, self.timeout = engine, batch_size, timeout
        self.deny_network, self.calls, self.processes = deny_network, 0, []
        self.executable = None
        if engine == 'vision':
            self.executable = shutil.which(executable or 'video-screenshot-vision')
            if not self.executable:
                raise OCRFailure('缺少本地 Vision 可执行程序。用 swiftc scripts/scroll_vision.swift -o <仓库外路径> 编译后传 --ocr-executable；不自动安装或云回退。')
        elif engine == 'rapidocr':
            # Run in isolated Python process; disable old user-site leakage.
            self.executable = sys.executable
        else:
            raise OCRFailure('未知引擎')
        if deny_network and not shutil.which('sandbox-exec'):
            raise OCRFailure('--deny-network 需要 macOS sandbox-exec；不能冒充已隔离')

    def recognize(self, paths):
        results = []
        for start in range(0, len(paths), self.batch_size):
            batch = [str(p) for p in paths[start:start+self.batch_size]]
            argv = ([self.executable] + batch if self.engine == 'vision' else
                    [self.executable, '-s', str(Path(__file__).resolve()), '--worker'] + batch)
            if self.deny_network:
                argv = [shutil.which('sandbox-exec'), '-p', '(version 1)(allow default)(deny network*)'] + argv
            begun = time.monotonic()
            event = {'argv': argv, 'engine': self.engine, 'images': len(batch), 'deny_network': self.deny_network}
            self.calls += len(batch)
            env = {k: os.environ[k] for k in ('PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'SYSTEMROOT') if k in os.environ}
            try:
                proc = subprocess.run(argv, capture_output=True, text=True, timeout=self.timeout, env=env, check=False)
                event.update(exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
                if proc.returncode:
                    raise OCRFailure(f'{self.engine} 子进程退出 {proc.returncode}: {proc.stderr[-1500:]}')
                records = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
                if len(records) != len(batch) or [r.get('path') for r in records] != batch:
                    raise OCRFailure('OCR 返回数量/来源路径不匹配')
                for record in records:
                    record['normalized_lines'] = normalize_lines(record)
                    results.append(record)
            except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, AttributeError) as exc:
                event['error'] = str(exc)
                raise OCRFailure(f'OCR 运行失败: {exc}') from exc
            except OCRFailure as exc:
                event['error'] = str(exc)
                raise
            finally:
                event['elapsed_seconds'] = round(time.monotonic()-begun, 3)
                self.processes.append(event)
        return results


def worker(paths):
    try:
        from rapidocr_onnxruntime import RapidOCR
        engine = RapidOCR()
    except Exception as exc:
        print(f'RapidOCR 初始化失败: {type(exc).__name__}: {exc}\n请在独立环境安装 rapidocr-onnxruntime；不自动安装/云回退。', file=sys.stderr)
        return 3
    try:
        from PIL import Image
        for path in paths:
            with Image.open(path) as image:
                width, height = image.size
            values, _ = engine(path)
            lines = []
            for box, text, score in values or []:
                xs, ys = [float(p[0]) for p in box], [float(p[1]) for p in box]
                lines.append({'text': str(text), 'confidence': float(score),
                              'bbox': [min(xs)/width, min(ys)/height, max(xs)/width, max(ys)/height]})
            print(json.dumps({'path': path, 'lines': lines, 'error': ''}, ensure_ascii=False), flush=True)
    except Exception as exc:
        print(f'RapidOCR 识别失败: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 3
    return 0

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--worker':
        raise SystemExit(worker(sys.argv[2:]))
    raise SystemExit('仅供 scroll_text.py 调用')
