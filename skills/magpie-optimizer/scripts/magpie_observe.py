#!/usr/bin/env python3
"""Read-only Magpie telemetry, coverage-aware diagnosis. Standard library only."""
import argparse
from collections import Counter, defaultdict
import datetime as dt
import gzip
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.dont_write_bytecode = True
from magpie_route import Refused, require, parse_json, load, save_new, cli, inventory, config_path

METRICS = ('calls', 'errors', 'retried', 'input', 'output', 'cache_read', 'cache_write', 'reasoning', 'cost', 'unpriced', 'timed', 'ttft_ms')
ROW_METRICS = ('in', 'out', 'cache_read', 'cache_write', 'reasoning', 'ms', 'status', 'cost')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def ref(value):
    return hashlib.sha256(str(value).encode()).hexdigest()[:20] if value else None


def project_numbers(obj, fields):
    out = {}
    for k in fields:
        if k in obj:
            v = obj[k]
            require(type(v) in (int, float) and math.isfinite(v) and v >= 0, 'invalid_numeric_field_' + k)
            out[k] = v
    return out


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Refused('gateway_redirect_refused')


class Gateway:
    def __init__(self, origin, timeout=180, budget=600):
        u = urllib.parse.urlsplit(origin)
        require(u.scheme == 'http' and u.hostname is not None and not u.username and not u.password
                and u.path in ('', '/') and not u.query and not u.fragment, 'gateway_origin_invalid')
        try:
            require(ipaddress.ip_address(u.hostname).is_loopback, 'gateway_must_be_numeric_loopback')
        except ValueError:
            raise Refused('gateway_must_be_numeric_loopback') from None
        require(1 <= timeout <= 600 and 1 <= budget <= 3600, 'read_budget_invalid')
        self.origin = origin.rstrip('/')
        self.timeout = timeout
        self.deadline = time.monotonic() + budget
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def get(self, path, params):
        require(path in ('usage', 'usage/requests', 'concurrency'), 'read_endpoint_not_allowed')
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, 'read_budget_exhausted')
        req = urllib.request.Request(self.origin + '/v1/magpie/' + path + '?' + urllib.parse.urlencode(params), method='GET')
        with self.opener.open(req, timeout=min(self.timeout, remaining)) as r:
            raw = r.read(64 * 1024 * 1024 + 1)
            require(len(raw) <= 64 * 1024 * 1024, 'response_too_large')
            return parse_json(raw)


def row_projection(r):
    require(isinstance(r, dict), 'request_row_invalid')
    out = {k: r[k] for k in ('t', 'agent', 'provider', 'model', 'req', 'effort', 'source', 'kind') if k in r}
    require(all(isinstance(v, str) for v in out.values()), 'request_label_schema_changed')
    out.update(project_numbers(r, ROW_METRICS))
    out['session_ref'] = ref(str(r.get('agent', '')) + ':' + str(r['session'])) if r.get('session') else None
    out['project_ref'] = ref(r.get('folder') or r.get('cwd'))
    out['priced'] = r.get('priced') if type(r.get('priced')) is bool else None
    return out


def read_ledger(get, period, day=None, page_size=500, max_pages=100):
    require(1 <= page_size <= 500 and 1 <= max_pages <= 2000, 'pagination_bounds_invalid')
    params = {'period': period}
    if day:
        dt.date.fromisoformat(day)
        params['day'] = day
    rows, pages, page_hashes, record_hashes = [], [], set(), set()
    total, first, status = None, None, 'PARTIAL_PAGE_LIMIT'
    for n in range(max_pages):
        params.update(offset=len(rows), limit=page_size)
        try:
            data = get('usage/requests', params)
            require(isinstance(data, dict) and isinstance(data.get('rows'), list), 'ledger_schema_changed')
            current = data.get('total')
            require(type(current) is int and current >= 0, 'ledger_total_invalid')
            if total is None:
                total, first = current, data
            if current != total:
                status = 'PARTIAL_TOTAL_CHANGED'
                break
            raw = data['rows']
            require(len(raw) <= page_size, 'page_size_exceeded')
            sig = digest(raw)
            if raw and sig in page_hashes:
                status = 'PARTIAL_REPEATED_PAGE'
                break
            page_hashes.add(sig)
            fingerprints = [digest(r) for r in raw]
            if len(set(fingerprints)) != len(fingerprints) or any(fp in record_hashes for fp in fingerprints):
                status = 'PARTIAL_RECORD_OVERLAP'
                break
            record_hashes.update(fingerprints)
            projected = [row_projection(r) for r in raw]
            pages.append({'offset': len(rows), 'count': len(raw), 'sha256': sig})
            rows.extend(projected)
            if len(rows) == total:
                status = 'COMPLETE_PAGINATION'
                break
            if not raw or len(rows) > total:
                status = 'PARTIAL_INCONSISTENT_PAGE'
                break
            print(json.dumps({'event': 'page_read', 'rows': len(rows), 'total': total}), file=sys.stderr, flush=True)
        except (OSError, ValueError, Refused) as e:
            status = 'PENDING_TIMEOUT' if isinstance(e, TimeoutError) else 'PARTIAL_READ_ERROR'
            break
    # Revalidate the head and total after reading multiple pages. This detects
    # most offset shifts; it cannot make the upstream into a transactional snapshot.
    if status == 'COMPLETE_PAGINATION' and len(pages) > 1:
        try:
            head = get('usage/requests', dict(params, offset=0, limit=page_size))
            if head.get('total') != total or digest(head.get('rows')) != pages[0]['sha256']:
                status = 'PARTIAL_HEAD_CHANGED'
        except (OSError, ValueError, Refused):
            status = 'PARTIAL_FINAL_RECHECK_FAILED'
    summary = {k: project_numbers((first or {}).get(k, {}), METRICS) for k in ('through', 'direct', 'reported')}
    if first:
        summary['all'] = project_numbers(first, METRICS)
    return {'status': status, 'expected_rows': total, 'read_rows': len(rows), 'pages': pages,
            'filter': {'period': period, 'day': day}, 'summary': summary, 'rows': rows, 'rows_sha256': digest(rows),
            'consistency': 'head_and_total_rechecked_not_transactional' if len(pages) > 1 else 'single_response'}


def read_local(config_dir, cache_dir, dates):
    context, session_refs = [], []
    route_files, missing, route_partial = [], [], 0
    allowed_parts = {'system', 'tools', 'memory', 'files', 'results', 'chat'}
    for day in dates:
        f = config_dir / 'routing' / (day + '.jsonl')
        if not f.exists():
            f = f.with_suffix('.jsonl.gz')
        if not f.exists():
            missing.append(day)
            continue
        file_hash = hashlib.sha256()
        count = 0
        opener = gzip.open if f.suffix == '.gz' else open
        with opener(f, 'rb') as h:
            for i, line in enumerate(h):
                count += len(line)
                require(count <= 128 * 1024 * 1024, 'route_day_read_limit')
                file_hash.update(line)
                try:
                    r = parse_json(line)
                except ValueError:
                    route_partial += 1
                    continue
                p = r.get('prompt')
                if not isinstance(p, dict) or not r.get('done') or r.get('error') or r.get('status', 0) >= 400 or r.get('kind'):
                    continue
                ts = r.get('time')
                require(isinstance(ts, str), 'route_time_missing')
                stamp = dt.datetime.fromisoformat(ts.replace('Z', '+00:00'))
                require(stamp.tzinfo is not None, 'route_time_without_zone')
                if stamp.astimezone().date().isoformat() not in dates:
                    continue
                vals = project_numbers(p, ('tokens', 'window', 'turns'))
                if vals.get('tokens', 0) <= 0:
                    continue
                parts = Counter()
                for part in p.get('parts', []):
                    value = project_numbers(part, ('tokens',)).get('tokens', 0)
                    kind = part.get('kind')
                    parts[kind if kind in allowed_parts else 'other'] += value
                usage = r.get('usage') or []
                cached = project_numbers(usage[-1], ('cache_read',)).get('cache_read', 0) if usage else None
                context.append({'agent': r.get('agent'), 'session_ref': ref(str(r.get('agent')) + ':' + str(r.get('session') or r.get('conv') or r.get('id'))),
                                'project_ref': ref(r.get('folder')), 'model': r.get('served') or r.get('model'), 'time': ts,
                                **vals, 'parts': dict(parts), 'counted': p.get('counted') is True, 'cache_read': cached})
        route_files.append({'day': day, 'decompressed_sha256': file_hash.hexdigest(), 'bytes_read': count})
    cache = cache_dir / 'sessions.json'
    native = {'status': 'UNAVAILABLE', 'sessions': [], 'tools': [], 'skill_calls': None}
    if cache.exists():
        require(cache.stat().st_size <= 128 * 1024 * 1024, 'session_cache_read_limit')
        raw = cache.read_bytes()
        d = parse_json(raw)
        require(d.get('version') == 19 and isinstance(d.get('files'), dict), 'session_cache_version_not_supported')
        tools, skills = Counter(), Counter()
        for obj in d['files'].values():
            matched = {day: v for day, v in obj.get('days', {}).items() if day in dates}
            if not matched:
                continue
            metrics = Counter()
            for day, daydata in matched.items():
                for model_metrics in daydata.get('m', {}).values():
                    metrics.update(project_numbers(model_metrics, ('input', 'output', 'cache_read', 'cache_write')))
                tools.update(project_numbers(daydata.get('t', {}), daydata.get('t', {}).keys()))
                skills.update(project_numbers(daydata.get('k', {}), daydata.get('k', {}).keys()))
            session_refs.append({'session_ref': ref(obj.get('id')), 'project_ref': ref(obj.get('cwd')),
                                 'days': sorted(matched), 'metrics': dict(metrics)})
        native = {'status': 'LOCAL_CACHE_NOT_LEDGER', 'cache_version': 19, 'cache_sha256': hashlib.sha256(raw).hexdigest(),
                  'cache_modified_at': dt.datetime.fromtimestamp(cache.stat().st_mtime, dt.timezone.utc).isoformat(),
                  'sessions': session_refs, 'tools': [{'name': k, 'calls': v} for k, v in tools.most_common()],
                  'skill_calls': sum(skills.values()) if skills else None,
                  'deduplication': 'per_cache_file_counts_do_not_add_to_ledger', 'tool_semantics': 'tool_names_not_shell_subcommands'}
    return {'context': {'status': 'RETAINED_ROUTE_SAMPLE' if context else 'NO_RETAINED_SAMPLES', 'files': route_files,
                        'missing_days': missing, 'malformed_lines': route_partial, 'rows': context}, 'native': native}


def summarize_context(rows):
    out = []
    by = defaultdict(list)
    for r in rows:
        by[r['agent']].append(r)
    for agent, samples in sorted(by.items()):
        parts = Counter()
        for r in samples:
            parts.update(r['parts'])
        total = sum(parts.values())
        counted = [r for r in samples if r['counted'] and r['cache_read'] is not None]
        cached_denom = sum(r['tokens'] for r in counted)
        sessions = defaultdict(list)
        for r in samples:
            sessions[r['session_ref']].append(r)
        growth = []
        compacts = 0
        for rs in sessions.values():
            ordered = sorted(rs, key=lambda r: r['time'])
            for a, b in zip(ordered, ordered[1:]):
                if a['tokens'] >= 20000 and b['tokens'] < a['tokens'] * .6:
                    compacts += 1
                elif b['tokens'] > a['tokens']:
                    growth.append(b['tokens'] - a['tokens'])
        out.append({'agent': agent, 'samples': len(samples), 'sessions': len(sessions),
                    'median_prompt_tokens': statistics.median(r['tokens'] for r in samples),
                    'parts_share': {k: v / total for k, v in parts.items()} if total else {},
                    'cache_ratio': sum(min(r['cache_read'], r['tokens']) for r in counted) / cached_denom if cached_denom else None,
                    'median_growth_tokens': statistics.median(growth) if growth else None,
                    'compacts_inferred': compacts,
                    'window_metadata_conflict_samples': sum(1 for r in samples if r.get('window', 0) > 0 and r['tokens'] > r['window']),
                    'max_window_fill': max((r['tokens'] / r['window'] for r in samples if 0 < r.get('window', 0) and r['tokens'] <= r['window']), default=None)})
    return out



def request_groups(rows):
    groups = defaultdict(lambda: Counter())
    for row in rows:
        # Keep native log, explicit report, gateway and unknown labels separate.
        source = row.get('source') or 'unspecified'
        for dimension in ('agent', 'provider', 'model', 'session_ref'):
            key = (source, dimension, row.get(dimension) or 'unknown')
            acc = groups[key]
            acc['calls'] += 1
            for f in ('in', 'out', 'cache_read', 'cache_write', 'reasoning', 'ms'):
                acc[f] += row.get(f, 0)
            acc['errors'] += int(row.get('status', 0) >= 400)
    return [{'source': source, 'dimension': dimension, 'id': ident, **dict(metrics)}
            for (source, dimension, ident), metrics in sorted(groups.items())]


def validate_complete_observation(observation):
    require(observation.get('schema') == 'magpie-observation.v1', 'observation_schema')
    ledger = observation.get('ledger', {})
    require(ledger.get('status') == 'COMPLETE_PAGINATION', 'complete_observation_required')
    rows, pages = ledger.get('rows'), ledger.get('pages')
    require(isinstance(rows, list) and isinstance(pages, list), 'ledger_coverage_missing')
    require(type(ledger.get('expected_rows')) is int and ledger['expected_rows'] == len(rows)
            and type(ledger.get('read_rows')) is int and ledger['read_rows'] == len(rows), 'ledger_coverage_mismatch')
    require(ledger.get('rows_sha256') == digest(rows), 'ledger_rows_changed')
    offset = 0
    for page in pages:
        require(page.get('offset') == offset and type(page.get('count')) is int and page['count'] >= 0
                and isinstance(page.get('sha256'), str) and len(page['sha256']) == 64, 'ledger_pages_invalid')
        offset += page['count']
    require(offset == len(rows) and (pages or not rows), 'ledger_page_coverage_mismatch')
    require(len({digest(r) for r in rows}) == len(rows), 'ledger_duplicate_records')
    for r in rows:
        require(isinstance(r, dict) and isinstance(r.get('t'), str) and isinstance(r.get('agent'), str), 'ledger_row_schema')
        project_numbers(r, ROW_METRICS)
    total = ledger.get('summary', {}).get('all', {})
    if 'calls' in total:
        require(total['calls'] == len(rows), 'ledger_call_total_mismatch')
    for rowkey, totalkey in [('in','input'),('out','output'),('cache_read','cache_read'),('cache_write','cache_write')]:
        if totalkey in total:
            require(sum(r.get(rowkey, 0) for r in rows) == total[totalkey], 'ledger_metric_total_mismatch')
    return rows

def diagnose(observation):
    require(observation.get('schema') == 'magpie-observation.v1', 'observation_schema')
    ledger = observation['ledger']
    if ledger['status'] == 'COMPLETE_PAGINATION':
        validate_complete_observation(observation)
    findings = []
    def add(code, fact, hypothesis, action, metric, evidence):
        findings.append({'id': code, 'fact': fact, 'hypothesis': hypothesis, 'suggested_action': action,
                         'verification_metric': metric, 'evidence': evidence, 'automatic_change': False})
    if ledger['status'] != 'COMPLETE_PAGINATION':
        add('COVERAGE', f"请求读取状态 {ledger['status']}，已读 {ledger['read_rows']} / {ledger['expected_rows']}",
            '当前结果不足以判断完整时段消耗', '接续读取或选择已结束的一天；保留部分数据标签', '完整分页与首尾总量核对', 'ledger.status')
    total = ledger['summary'].get('all', {})
    calls = total.get('calls', 0)
    if calls and (total.get('errors', 0) + total.get('retried', 0)) / calls >= .02:
        add('RETRIES', {k: total.get(k) for k in ('calls', 'errors', 'retried')}, '限流、错误或回退可能增加成本和时延',
            '按供应商与会话检查状态和重试，比较账号总并发与队列', '每份验收产物重试数与耗时', 'ledger.summary.all')
    for ctx in observation['context_summary']:
        shares = ctx['parts_share']
        if ctx.get('window_metadata_conflict_samples', 0):
            add('WINDOW-METADATA-' + str(ctx['agent']), {'agent': ctx['agent'], 'samples_over_declared_window': ctx['window_metadata_conflict_samples']},
                '报告的提示词大于记录窗口，容量元数据或计数口径可能不一致', '核对组与实际模型窗口、计数来源，暂不按超出100%推断溢出',
                '元数据修正后重新计算有效窗口占用', 'context_summary')
        if shares.get('tools', 0) >= .1:
            add('TOOLS-' + str(ctx['agent']), {'agent': ctx['agent'], 'tool_definition_share': shares['tools'], 'samples': ctx['samples']},
                '工具定义值得检查，是否多余仍取决于任务依赖', '抽查定义中该任务不需要的工具，生成具名裁剪建议',
                '保留必要能力后的总输入、缓存与任务验收', 'context_summary')
        if shares.get('results', 0) >= .15:
            add('RESULTS-' + str(ctx['agent']), {'agent': ctx['agent'], 'tool_result_share': shares['results']},
                '部分返回可能过长或反复携带', '在同类任务试用有界搜索、摘要或结果分页', '工具回合数、总输入与漏项/返工', 'context_summary')
        if ctx.get('max_window_fill') is not None and ctx['max_window_fill'] >= .7:
            add('CONTEXT-' + str(ctx['agent']), {'agent': ctx['agent'], 'max_window_fill': ctx['max_window_fill'], 'cache_ratio': ctx['cache_ratio']},
                '高占用会话需要结合进展与缓存判断', '检查阶段交接、重复读取和压缩，比较后再决定新开会话',
                '质量不下降时总消耗、缓存与完成时间', 'context_summary')
    for g in observation.get('inventory', {}).get('groups', []):
        if g.get('disabled'):
            add('DISABLED-' + g['id'], {'group': g['id'], 'disabled': True}, '该组不能承担预期路由',
                '核对是否仍有任务依赖；只针对具名组提出修正', '客户端实际服务模型与验收', 'inventory.groups')
    return {'schema': 'magpie-diagnosis.v1', 'observation_sha256': digest(observation), 'observed_at': observation['observed_at'],
            'findings': findings, 'quality_evidence': 'NOT_PROVIDED',
            'limits': ['阈值仅用于选取检查对象，不等于证明浪费', '保留历史样本、缓存文件和完整请求账不能合并统计', '没有任务验收不能判断模型降级收益']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    c = sub.add_parser('collect')
    c.add_argument('--gateway', default='http://127.0.0.1:3425')
    c.add_argument('--period', choices=['today', 'week', 'month', 'all'], default='today')
    c.add_argument('--day', help='local calendar date; overrides period for request rows')
    c.add_argument('--timeout', type=int, default=180)
    c.add_argument('--budget', type=int, default=600)
    c.add_argument('--max-pages', type=int, default=100)
    c.add_argument('--output', required=True)
    d = sub.add_parser('diagnose')
    d.add_argument('--observation', required=True)
    d.add_argument('--output', required=True)
    args = p.parse_args()
    if args.command == 'diagnose':
        out = diagnose(load(args.observation))
    else:
        client = Gateway(args.gateway, args.timeout, args.budget)
        if args.day:
            dates = [dt.date.fromisoformat(args.day).isoformat()]
        else:
            n = {'today': 1, 'week': 7, 'month': 30, 'all': 30}[args.period]
            dates = [(dt.date.today() - dt.timedelta(days=i)).isoformat() for i in range(n)]
        started = time.monotonic()
        ledger = read_ledger(client.get, args.period, args.day, max_pages=args.max_pages)
        config_dir = config_path().parent
        cache_dir = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'magpie'
        try:
            local = read_local(config_dir, cache_dir, dates)
        except (OSError, ValueError, TypeError, KeyError, Refused) as e:
            reason = str(e) if isinstance(e, Refused) else type(e).__name__
            local = {'context': {'status': 'NOT_VERIFIED', 'reason': reason, 'rows': []},
                     'native': {'status': 'NOT_VERIFIED', 'reason': reason, 'sessions': [], 'tools': [], 'skill_calls': None}}

        out = {'schema': 'magpie-observation.v1', 'observed_at': dt.datetime.now(dt.timezone.utc).isoformat(),
               'local_clock': dt.datetime.now().astimezone().isoformat(), 'cli_version': cli(['--version']).strip(),
               'elapsed_seconds': round(time.monotonic() - started, 3), 'ledger': ledger,
               'request_groups': request_groups(ledger['rows']),
               **local, 'context_summary': summarize_context(local['context']['rows']),
               'inventory': inventory(load(config_path())),
               'dates_for_local_samples': dates, 'raw_content_exported': False}
    save_new(args.output, out)
    print(json.dumps({'status': out.get('ledger', {}).get('status', 'DIAGNOSIS_WRITTEN'), 'output': args.output}))


if __name__ == '__main__':
    try:
        main()
    except (Refused, OSError, ValueError, TypeError, KeyError) as e:
        print(json.dumps({'status': 'REFUSED', 'reason': str(e) if isinstance(e, Refused) else type(e).__name__}), file=sys.stderr)
        sys.exit(2)
