#!/usr/bin/env python3
"""Summarize explicitly named routing JSONL files without exporting their contents."""
import argparse
from contextlib import contextmanager
import datetime as dt
import gzip
import json
import math
import os
from pathlib import Path
import stat
import sys
import zlib

PARTS = ('system', 'tools', 'skills', 'memory', 'files', 'results', 'chat')
NET = ('send', 'own', 'wait')
USAGE = ('in', 'out', 'cache_read', 'reasoning')
KINDS = ('collab_spawn', 'routing', 'compacting', 'vision', 'web_search',
         'composer_predictions', 'thread_title', 'thread_description',
         'ambient_suggestions', 'ambient_suggestion_safety', 'agent_created_thread')
DEFAULT_BYTES = 256 * 1024 * 1024
MAX_BYTES = 1024 * 1024 * 1024
MAX_ROWS = 200000


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('timestamp')
    result = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('timezone required')
    return result.astimezone(dt.timezone.utc)


def cli_timestamp(value):
    try:
        return timestamp(value)
    except (ValueError, OverflowError):
        raise argparse.ArgumentTypeError('expected timezone-aware ISO8601 timestamp')


def positive_bytes(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError('max-bytes must be an integer')
    if not 1 <= number <= MAX_BYTES:
        raise argparse.ArgumentTypeError('max-bytes must be between 1 and 1073741824')
    return number


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return value if 0 <= value <= 1e15 and math.isfinite(value) else None
    except (OverflowError, TypeError):
        return None


def quantiles(values):
    if not values:
        return {'count': 0, 'p50': None, 'p90': None, 'p95': None}
    values.sort()
    # Nearest rank; avoid inventing measurements between requests.
    return {'count': len(values), **{f'p{p}': values[math.ceil(len(values) * p / 100) - 1]
                                    for p in (50, 90, 95)}}


def status_code(item):
    value = number(item.get('status')) if isinstance(item, dict) else None
    return int(value) if value is not None and 100 <= value <= 599 and float(value).is_integer() else None


def record_code(counts, item):
    code = status_code(item)
    if code is None:
        counts['unknown'] += 1
    else:
        codes = counts['codes']
        codes[str(code)] = codes.get(str(code), 0) + 1


class DuplicateInput(Exception):
    pass


class NonRegularInput(Exception):
    pass


@contextmanager
def open_input(path, seen):
    # Check before opening, then recheck the opened inode; O_NONBLOCK protects the race.
    if not stat.S_ISREG(os.stat(path).st_mode):
        raise NonRegularInput()
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as raw:
        info = os.fstat(raw.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise NonRegularInput()
        identity = (info.st_dev, info.st_ino)
        if identity in seen:
            raise DuplicateInput()
        seen.add(identity)
        if str(path).endswith('.gz'):
            with gzip.GzipFile(fileobj=raw, mode='rb') as source:
                yield source
        else:
            yield raw


def outcome(item):
    if not isinstance(item, dict):
        return 'unknown'
    status = number(item.get('status'))
    error = item.get('error')
    if error:
        return 'failure'
    if status is not None and 100 <= status <= 599 and float(status).is_integer():
        return 'success' if 200 <= status < 300 else ('failure' if status >= 400 else 'unknown')
    return 'unknown'


def new_parts():
    return {'records_with_parts': 0, 'missing_or_invalid_parts': 0, 'invalid_entries': 0,
            'unknown_kind_entries': 0, 'numeric_entries': 0, 'tokens': {k: 0 for k in (*PARTS, 'unknown')},
            'observations': {k: 0 for k in (*PARTS, 'unknown')},
            'counted_records': 0, 'estimated_records': 0, 'counted_unknown_records': 0,
            'tokens_by_counted': {'counted': None, 'estimated': None, 'unknown': None}}


def collect(paths, since, until, max_bytes):
    report = {'schema': 'magpie-efficiency.v1', 'status': 'complete',
              'window': {'since': since.isoformat(), 'until_exclusive': until.isoformat()},
              'coverage': {'uncompressed_bytes_read': 0, 'lines_read': 0, 'malformed_lines': 0,
                           'invalid_records_or_time': 0, 'outside_window': 0, 'in_flight': 0,
                           'completion_unknown': 0, 'finished_in_window': 0, 'read_errors': 0,
                           'non_regular_inputs': 0, 'duplicate_inputs': 0,
                           'truncated_by_byte_limit': False, 'truncated_by_row_limit': False},
              'final_status': {'success': 0, 'failure': 0, 'unknown': 0},
              'tries': {'records_with_tries': 0, 'missing_or_invalid_records': 0, 'success': 0,
                        'failure': 0, 'unknown': 0, 'recovered_after_failure': 0,
                        'recovery_unknown_records': 0},
              'final_http_status': {'codes': {}, 'unknown': 0},
              'try_http_status': {'codes': {}, 'unknown': 0},
              'by_kind': {},
              'prompt_total': {'observed_records': 0, 'missing_or_invalid_records': 0, 'sum': None,
                               'comparable_records': 0, 'uncomparable_records': 0,
                               'comparable_prompt_sum': None, 'comparable_parts_sum': None,
                               'difference_prompt_minus_parts': None, 'mismatched_records': 0},
              'success_latency_ms': {}, 'success_ttft_ms': {},
              'net': {}, 'parts': new_parts(),
              'usage': {'list_records': 0, 'multi_entry_records': 0, 'empty_list_records': 0,
                        'missing_records': 0, 'legacy_dict_records': 0, 'unsupported_records': 0, 'invalid_entries': 0,
                        'dict_entries': 0,
                        'raw_fields': {k: {'observed_entries': 0, 'missing_or_invalid_entries': 0, 'sum': None}
                                       for k in USAGE},
                        'legacy_dict_raw_fields': {k: {'observed_entries': 0, 'missing_or_invalid_entries': 0, 'sum': None}
                                                   for k in USAGE}},
              'notes': ['Complete indicates input reading only; in-flight and unknown completion are excluded, and field coverage varies.',
                        'Only supplied retained routing logs; not a complete ledger.',
                        'Window is based on record time, inclusive since and exclusive until.',
                        'Parts are observed prompt token estimates, not billing; shares include numeric unknown kinds.',
                        'Usage list raw fields only: observed in excludes cached input in the confirmed schema; no total input or billing is inferred.',
                        'Multiple usage entries are summed as raw observations; their overlap or accounting semantics are unknown.',
                        'Legacy dict usage raw fields are separate; their input/cache semantics are unknown.',
                        'HTTP codes and outcome(error-aware) are separate: a 200 with error metadata is not assumed successful. Auxiliary kinds are not main-task failures.',
                        'Network fields come only from tries; plugin fetch breakdown may be missing. Send does not identify proxy faults, and WS handshake send does not measure all WS message uploads.',
                        'Retry durations are not summed as wall time; observations are investigation candidates only.']}
    cov, tries, parts = report['coverage'], report['tries'], report['parts']
    latency, ttft = [], []
    net = {group: {k: [] for k in NET} for group in ('all_tries', 'successful_tries')}
    seen = set()
    usage_summary = report['usage']
    stop = False
    for path in paths:
        if stop:
            break
        try:
            with open_input(path, seen) as source:
                while True:
                    remaining = max_bytes - cov['uncompressed_bytes_read']
                    line = source.readline(remaining + 1)
                    if not line:
                        break
                    if len(line) > remaining:
                        cov['uncompressed_bytes_read'] += remaining
                        cov['truncated_by_byte_limit'] = True
                        stop = True
                        break
                    cov['uncompressed_bytes_read'] += len(line)
                    if cov['lines_read'] >= MAX_ROWS:
                        cov['truncated_by_row_limit'] = True
                        stop = True
                        break
                    cov['lines_read'] += 1
                    try:
                        row = json.loads(line, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                    except (ValueError, UnicodeDecodeError, RecursionError):
                        cov['malformed_lines'] += 1
                        continue
                    try:
                        if not isinstance(row, dict):
                            raise TypeError()
                        stamp = timestamp(row.get('time'))
                    except (ValueError, TypeError, OverflowError):
                        cov['invalid_records_or_time'] += 1
                        continue
                    if not since <= stamp < until:
                        cov['outside_window'] += 1
                        continue
                    if row.get('done') is False:
                        cov['in_flight'] += 1
                        continue
                    if row.get('done') is not True:
                        cov['completion_unknown'] += 1
                        continue
                    cov['finished_in_window'] += 1
                    final = outcome(row)
                    report['final_status'][final] += 1
                    record_code(report['final_http_status'], row)
                    raw_kind = row.get('kind')
                    kind = ('main_or_unspecified' if raw_kind in (None, '') else
                            raw_kind if isinstance(raw_kind, str) and raw_kind in KINDS else 'other')
                    kind_report = report['by_kind'].setdefault(kind, {
                        'records': 0, 'success': 0, 'failure': 0, 'unknown': 0,
                        'http_200_with_error': 0})
                    kind_report['records'] += 1
                    kind_report[final] += 1
                    kind_report['http_200_with_error'] += int(status_code(row) == 200 and bool(row.get('error')))
                    attempts = row.get('tries')
                    if not isinstance(attempts, list) or not attempts:
                        tries['missing_or_invalid_records'] += 1
                    else:
                        tries['records_with_tries'] += 1
                        states = [outcome(item) for item in attempts]
                        for attempt, state in zip(attempts, states):
                            tries[state] += 1
                            record_code(report['try_http_status'], attempt)
                            network = attempt.get('net') if isinstance(attempt, dict) else None
                            if isinstance(network, dict):
                                for key in NET:
                                    value = number(network.get(key))
                                    if value is not None:
                                        net['all_tries'][key].append(value)
                                        if state == 'success':
                                            net['successful_tries'][key].append(value)
                        if final == 'success' and 'failure' in states:
                            first_failure = states.index('failure')
                            if 'success' in states[first_failure + 1:]:
                                tries['recovered_after_failure'] += 1
                            else:
                                tries['recovery_unknown_records'] += 1
                    if final == 'success':
                        for key, target in (('ms', latency), ('ttft', ttft)):
                            value = number(row.get(key))
                            if value is not None:
                                target.append(value)
                    usage = row.get('usage')
                    if usage is None:
                        usage_summary['missing_records'] += 1
                    elif isinstance(usage, dict):
                        usage_summary['legacy_dict_records'] += 1
                        for key in USAGE:
                            metric = usage_summary['legacy_dict_raw_fields'][key]
                            value = number(usage.get(key))
                            if value is None:
                                metric['missing_or_invalid_entries'] += 1
                            else:
                                metric['observed_entries'] += 1
                                old_sum = metric['sum']
                                metric['sum'] = (old_sum if old_sum is not None else 0) + value
                    elif not isinstance(usage, list):
                        usage_summary['unsupported_records'] += 1
                    else:
                        usage_summary['list_records'] += 1
                        usage_summary['empty_list_records'] += int(not usage)
                        usage_summary['multi_entry_records'] += int(len(usage) > 1)
                        for entry in usage:
                            if not isinstance(entry, dict):
                                usage_summary['invalid_entries'] += 1
                                continue
                            usage_summary['dict_entries'] += 1
                            for key in USAGE:
                                metric = usage_summary['raw_fields'][key]
                                value = number(entry.get(key))
                                if value is None:
                                    metric['missing_or_invalid_entries'] += 1
                                else:
                                    metric['observed_entries'] += 1
                                    old_sum = metric['sum']
                                    metric['sum'] = (old_sum if old_sum is not None else 0) + value
                    prompt = row.get('prompt')
                    entries = prompt.get('parts') if isinstance(prompt, dict) else None
                    prompt_value = number(prompt.get('tokens')) if isinstance(prompt, dict) else None
                    totals = report['prompt_total']
                    if prompt_value is None:
                        totals['missing_or_invalid_records'] += 1
                    else:
                        totals['observed_records'] += 1
                        totals['sum'] = (totals['sum'] if totals['sum'] is not None else 0) + prompt_value
                    part_values = [number(e.get('tokens')) if isinstance(e, dict) else None
                                   for e in entries] if isinstance(entries, list) else []
                    if prompt_value is not None and part_values and all(v is not None for v in part_values):
                        subtotal = sum(part_values)
                        totals['comparable_records'] += 1
                        totals['mismatched_records'] += int(prompt_value != subtotal)
                        for key, value in (('comparable_prompt_sum', prompt_value), ('comparable_parts_sum', subtotal),
                                           ('difference_prompt_minus_parts', prompt_value - subtotal)):
                            totals[key] = (totals[key] if totals[key] is not None else 0) + value
                    else:
                        totals['uncomparable_records'] += 1
                    if not isinstance(entries, list):
                        parts['missing_or_invalid_parts'] += 1
                    else:
                        parts['records_with_parts'] += 1
                        counted = prompt.get('counted')
                        bucket = 'counted_records' if counted is True else ('estimated_records' if counted is False else 'counted_unknown_records')
                        parts[bucket] += 1
                        for entry in entries:
                            if not isinstance(entry, dict):
                                parts['invalid_entries'] += 1
                                continue
                            kind = entry.get('kind')
                            if not isinstance(kind, str) or kind not in PARTS:
                                kind = 'unknown'
                                parts['unknown_kind_entries'] += 1
                            value = number(entry.get('tokens'))
                            if value is None:
                                parts['invalid_entries'] += 1
                                continue
                            parts['numeric_entries'] += 1
                            parts['observations'][kind] += 1
                            parts['tokens'][kind] += value
                            basis = 'counted' if counted is True else ('estimated' if counted is False else 'unknown')
                            previous = parts['tokens_by_counted'][basis]
                            parts['tokens_by_counted'][basis] = (previous if previous is not None else 0) + value
        except DuplicateInput:
            cov['duplicate_inputs'] += 1
        except NonRegularInput:
            cov['non_regular_inputs'] += 1
        except (OSError, EOFError, ValueError, zlib.error):
            cov['read_errors'] += 1
            stop = True
    if cov['read_errors'] or cov['duplicate_inputs'] or cov['non_regular_inputs'] or cov['malformed_lines'] or cov['invalid_records_or_time'] or cov['truncated_by_byte_limit'] or cov['truncated_by_row_limit']:
        report['status'] = 'partial'
    total = sum(parts['tokens'].values())
    parts['numeric_token_total'] = total if parts['numeric_entries'] else None
    parts['shares'] = {k: (v / total if parts['observations'][k] else None)
                       for k, v in parts['tokens'].items()} if total else None
    parts['tokens'] = {k: (v if parts['observations'][k] else None)
                       for k, v in parts['tokens'].items()}
    parts['share_coverage'] = 'numeric_entries_only; invalid_or_missing_entries_not_in_denominator'
    report['success_latency_ms'] = quantiles(latency)
    report['success_ttft_ms'] = quantiles(ttft)
    report['net'] = {group: {key: {'observed_tries': len(values), 'sum': sum(values) if values else None}
                             for key, values in metrics.items()} for group, metrics in net.items()}
    return report


def private_output(path):
    parent = path.parent
    missing = []
    cursor = parent
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
        if stat.S_IMODE(directory.stat().st_mode) != 0o700:
            raise OSError('private directory required')
    if stat.S_IMODE(parent.stat().st_mode) != 0o700:
        raise OSError('private directory required')
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.fchmod(fd, 0o600)
    return os.fdopen(fd, 'w', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('logs', type=Path, nargs='+')
    parser.add_argument('--since', type=cli_timestamp, required=True)
    parser.add_argument('--until', type=cli_timestamp, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-bytes', type=positive_bytes, default=DEFAULT_BYTES)
    args = parser.parse_args(argv)
    if args.since >= args.until:
        parser.error('since must be before until')
    try:
        if any(args.output.resolve() == path.resolve() for path in args.logs):
            parser.error('input and output must be different paths')
        with private_output(args.output) as target:
            report = collect(args.logs, args.since, args.until, args.max_bytes)
            json.dump(report, target, indent=2, allow_nan=False)
            target.write('\n')
        return 0 if report['status'] == 'complete' else 1
    except (OSError, ValueError, OverflowError):
        print('Unable to write output or process input.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
