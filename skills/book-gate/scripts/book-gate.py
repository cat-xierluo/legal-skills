#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""book-gate：出版 acceptance harness 主入口。

用法：
  python3 book-gate.py verify <manuscript-dir> [--requirements R.yaml] [--stage markdown|all] [--out DIR]
  python3 book-gate.py status <evidence-dir>

核心：fail-closed 验收。每条 requirement 跑 verifier，输出 PASS/PARTIAL/FAIL/
NEEDS_HUMAN_REVIEW + 证据包（绑 candidate SHA + 规范版本 + gate 版本 + 逐项结果）。
任一 blocking 项 FAIL/ERROR/缺证 → 退出码 1，candidate 不能升级 SOURCE_VERIFIED。
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime

GATE_VERSION = '0.1.0'

# fail-closed 状态机（五支柱之 5）
STATES = [
    'CONTRACTED',      # 需求已立
    'IN_PROGRESS',     # worker 在写
    'CANDIDATE',       # worker done = 只到这（无权自批）
    'SOURCE_VERIFIED', # markdown 源经 book-gate 验证通过（本 v0.1 止步于此）
    'RENDERED',        # SVG/PNG 渲染验证通过（v0.2）
    'INDEPENDENT_VERIFIED',  # 独立 verifier 干净环境复验（v0.2）
    'MERGED',          # PR 合并 = 只到这（仍非最终）
    'RELEASE_VERIFIED',# 最终成品 hash 验证通过
    'CLOSED',          # 文档同步后
]


def _to_bool(v):
    return str(v).strip().lower() in ('true', '1', 'yes')


def load_requirements(req_path):
    """加载 requirement 清单。优先 pyyaml，否则简版手解析。"""
    try:
        import yaml
        with open(req_path, encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        return _parse_yaml_fallback(req_path)


def _parse_yaml_fallback(req_path):
    """无 pyyaml 时的简版解析（支持本 skill requirements.yaml 结构）。"""
    reqs = []
    cur = None
    with open(req_path, encoding='utf-8') as f:
        for raw in f:
            s = raw.strip()
            if s.startswith('- id:'):
                if cur:
                    reqs.append(cur)
                cur = {'id': s.split(':', 1)[1].strip()}
            elif cur and ':' in s and not s.startswith('-') and not s.startswith('#'):
                k, v = s.split(':', 1)
                val = v.strip()
                if val.startswith('"') and val.endswith('"'):
                    val = val[1:-1]
                cur[k.strip()] = val
    if cur:
        reqs.append(cur)
    return {'requirements': reqs, 'schema_version': '0.1.0'}


def candidate_sha(manuscript_dir):
    """manuscript 目录所有 .md 内容聚合 sha256 = candidate 身份。"""
    h = hashlib.sha256()
    files = []
    for root, _, fns in os.walk(manuscript_dir):
        for fn in fns:
            if fn.endswith('.md'):
                files.append(os.path.join(root, fn))
    for f in sorted(files):
        with open(f, 'rb') as fh:
            h.update(fh.read())
        h.update(b'\x00')  # 分隔符防拼接歧义
    return h.hexdigest()


def run_verifier(verifier_name, manuscript_dir):
    """按 'checkers.markdown_checker.no_mermaid' 调度函数。"""
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    module_path, func_name = verifier_name.rsplit('.', 1)
    mod = __import__(module_path, fromlist=[func_name])
    func = getattr(mod, func_name)
    return func(manuscript_dir)


def verify(manuscript_dir, req_path, stage='all', out_dir=None):
    """跑 requirement，输出证据包。fail-closed（blocking 缺证/失败 → 退出码 1）。"""
    spec = load_requirements(req_path)
    reqs = spec.get('requirements', [])
    if stage != 'all':
        reqs = [r for r in reqs if r.get('stage') == stage]

    sha = candidate_sha(manuscript_dir)
    results = []
    blocking_fail = False

    for r in reqs:
        rid = r.get('id', '?')
        verifier = r.get('verifier', '').strip()
        blocking = _to_bool(r.get('blocking', 'true'))
        needs_human = _to_bool(r.get('needs_human_review', 'false'))

        if not verifier or needs_human:
            # 五支柱之 1：无验证器 → 强制 NEEDS_HUMAN_REVIEW，不能默认通过
            results.append({'req_id': rid, 'verdict': 'NEEDS_HUMAN_REVIEW',
                            'stage': r.get('stage'),
                            'note': r.get('note') or '无自动验证器，需人工复核'})
            if blocking:
                blocking_fail = True  # blocking 项缺证也阻断（fail-closed）
            continue

        try:
            findings = run_verifier(verifier, manuscript_dir)
            hard = [f for f in findings if f.severity == 'hard']
            soft = [f for f in findings if f.severity == 'soft']
            if hard:
                verdict = 'FAIL'
                if blocking:
                    blocking_fail = True
            elif soft:
                verdict = 'PARTIAL'
            else:
                verdict = 'PASS'
            results.append({'req_id': rid, 'verdict': verdict, 'stage': r.get('stage'),
                            'blocking': blocking,
                            'hard_count': len(hard), 'soft_count': len(soft),
                            'findings': [f.to_dict() for f in findings[:20]]})
        except Exception as e:
            results.append({'req_id': rid, 'verdict': 'ERROR', 'stage': r.get('stage'),
                            'blocking': blocking, 'error': f'{type(e).__name__}: {e}'})
            if blocking:
                blocking_fail = True

    evidence = {
        'candidate_sha': sha,
        'manuscript_dir': os.path.abspath(manuscript_dir),
        'spec_schema_version': spec.get('schema_version'),
        'gate_version': GATE_VERSION,
        'verified_at': datetime.now().isoformat(timespec='seconds'),
        'stage': stage,
        'next_state_if_pass': 'SOURCE_VERIFIED' if stage in ('all', 'markdown') else None,
        'results': results,
        'overall': 'BLOCKED' if blocking_fail else 'SOURCE_VERIFIED_CANDIDATE',
    }

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f'evidence-{sha[:12]}.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(evidence, f, ensure_ascii=False, indent=2)
        print(f'evidence bundle: {path}')

    print(f"candidate_sha: {sha[:12]}…  overall: {evidence['overall']}  stage: {stage}")
    for r in results:
        if r['verdict'] != 'PASS':
            detail = ''
            if 'hard_count' in r:
                detail = f"{r['hard_count']} hard / {r['soft_count']} soft"
            else:
                detail = r.get('note') or r.get('error', '')
            print(f"  [{r['verdict']}] {r['req_id']} ({r.get('stage')}): {detail}")

    return 1 if blocking_fail else 0


def main():
    ap = argparse.ArgumentParser(prog='book-gate', description='出版 acceptance harness（fail-closed）')
    sub = ap.add_subparsers(dest='cmd', required=True)
    v = sub.add_parser('verify', help='验证 candidate（blocking FAIL → 退出码 1）')
    v.add_argument('manuscript_dir')
    v.add_argument('--requirements', '-r', default=None)
    v.add_argument('--stage', default='all', choices=['all', 'markdown', 'svg', 'png', 'docx'])
    v.add_argument('--out', default=None, help='证据包输出目录')
    s = sub.add_parser('status', help='查看证据包')
    s.add_argument('evidence_dir')
    args = ap.parse_args()

    if args.cmd == 'verify':
        here = os.path.dirname(os.path.abspath(__file__))
        req_default = os.path.join(here, '..', 'requirements.yaml')
        req_path = args.requirements or req_default
        out_dir = args.out or os.path.join(os.path.dirname(args.manuscript_dir.rstrip('/')),
                                            '.book-gate-evidence')
        sys.exit(verify(args.manuscript_dir, req_path, args.stage, out_dir))
    elif args.cmd == 'status':
        for fn in sorted(os.listdir(args.evidence_dir)):
            if fn.startswith('evidence-') and fn.endswith('.json'):
                with open(os.path.join(args.evidence_dir, fn), encoding='utf-8') as f:
                    ev = json.load(f)
                print(f"{fn}: {ev['overall']} sha={ev['candidate_sha'][:12]}… "
                      f"({sum(1 for r in ev['results'] if r['verdict']=='FAIL')} FAIL / "
                      f"{sum(1 for r in ev['results'] if r['verdict']=='PARTIAL')} PARTIAL / "
                      f"{sum(1 for r in ev['results'] if r['verdict']=='NEEDS_HUMAN_REVIEW')} HUMAN)")


if __name__ == '__main__':
    main()
