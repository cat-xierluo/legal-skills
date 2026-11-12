#!/usr/bin/env python3
"""Bounded, metadata-only Magpie host sampling; no authentication content is read."""
import argparse
import json
import math
import os
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def interval_value(value):
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError('interval must be a number')
    if not math.isfinite(number) or not 0.1 <= number <= 60:
        raise argparse.ArgumentTypeError('interval must be finite and between 0.1 and 60')
    return number


def sample_count(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError('samples must be an integer')
    if not 2 <= number <= 60:
        raise argparse.ArgumentTypeError('samples must be between 2 and 60')
    return number


def hosts(timeout):
    # comm is used solely for filtering and is never included in output.
    result = subprocess.run(['ps', '-axo', 'pid=,ppid=,rss=,%cpu=,lstart=,comm='],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, timeout=timeout, check=True,
                            env={**os.environ, 'LC_ALL': 'C'})
    if not result.stdout.strip():
        raise ValueError('empty process sample')
    found = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 9)
        if len(fields) != 10:
            raise ValueError('unparseable process sample')
        pid, ppid, rss, cpu = int(fields[0]), int(fields[1]), int(fields[2]), float(fields[3])
        if pid <= 0 or ppid < 0 or rss < 0 or not math.isfinite(cpu) or cpu < 0:
            raise ValueError('invalid process sample')
        command = fields[9]
        if 'magpie-bun' in command or 'magpie/bun' in command:
            found.append({'pid': pid, 'ppid': ppid, 'rss_kib': rss, 'cpu_percent': cpu,
                          'started': ' '.join(fields[4:9])})
    return found


def auth_stat(config_dir):
    try:
        entry = (config_dir / 'plugin-auth.json').stat()
        return {'status': 'present', 'mtime_ns': entry.st_mtime_ns}
    except FileNotFoundError:
        return {'status': 'absent'}
    except OSError:
        return {'status': 'unknown'}


def create_output(path):
    # Create missing output directories privately; never change existing directories.
    parent = path.parent
    missing = []
    current = parent
    while not current.exists():
        missing.append(current)
        current = current.parent
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
        if stat.S_IMODE(directory.stat().st_mode) != 0o700:
            raise OSError('output directory must be private (0700)')
    if stat.S_IMODE(parent.stat().st_mode) != 0o700:
        raise OSError('output directory must be private (0700)')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.fchmod(fd, 0o600)
    return os.fdopen(fd, 'w', encoding='utf-8')


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def collect(args, output):
    start = time.monotonic()
    started_at = utc_now()
    samples = []
    segments = []
    active = {}
    changes = 0
    comparisons = 0
    previous_auth = None
    failed = False
    interrupted = False
    try:
        for index in range(args.samples):
            if index:
                remaining = 300 - (time.monotonic() - start)
                if remaining <= args.interval:
                    failed = True
                    break
                time.sleep(args.interval)
            remaining = 300 - (time.monotonic() - start)
            if remaining <= 0:
                failed = True
                break
            try:
                process = hosts(remaining)
            except (OSError, ValueError, subprocess.SubprocessError):
                process = None
                failed = True
            auth = auth_stat(args.config_dir)
            if auth['status'] == 'unknown':
                failed = True
            if previous_auth is not None and auth['status'] == previous_auth['status'] == 'present':
                comparisons += 1
                changes += auth['mtime_ns'] != previous_auth['mtime_ns']
            previous_auth = auth
            elapsed = time.monotonic() - start
            samples.append({'at': utc_now(), 'elapsed_seconds': round(elapsed, 3),
                            'hosts': process, 'auth': auth})
            new_active = {}
            for host in process or []:
                identity = (host['pid'], host['started'])
                segment = active.get(identity)
                if segment is None:
                    segment = {'pid': host['pid'], 'started': host['started'],
                               'first_sample': index, 'last_sample': index,
                               'first_rss_kib': host['rss_kib'], 'last_rss_kib': host['rss_kib'],
                               'rss_change_kib': 0, 'samples': 0}
                    segments.append(segment)
                segment['last_sample'] = index
                segment['last_rss_kib'] = host['rss_kib']
                segment['rss_change_kib'] = host['rss_kib'] - segment['first_rss_kib']
                segment['samples'] += 1
                new_active[identity] = segment
            active = new_active
    except KeyboardInterrupt:
        interrupted = True
        failed = True
    finished_at = utc_now()
    report = {
        'started_at': started_at, 'finished_at': finished_at,
        'status': 'interrupted' if interrupted else ('incomplete' if failed else 'complete'),
        'requested_samples': args.samples, 'requested_interval_seconds': args.interval,
        'collected_samples': len(samples),
        'coverage_seconds': round(samples[-1]['elapsed_seconds'] - samples[0]['elapsed_seconds'], 3) if len(samples) > 1 else 0,
        'observation_elapsed_seconds': round(time.monotonic() - start, 3),
        'samples': samples, 'host_segments': segments,
        'auth_change_count': changes if comparisons and comparisons == len(samples) - 1 else None,
        'auth_observed_change_count': changes if comparisons else None,
        'auth_comparisons': comparisons,
        'note': ('RSS and auth mtime changes are investigation leads only; RSS is neither heap '
                 'nor physical footprint. Auth counts cover observed adjacent present samples only.'),
    }
    json.dump(report, output, indent=2, allow_nan=False)
    output.write('\n')
    output.flush()
    return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('collect')
    command.add_argument('--samples', type=sample_count, default=6)
    command.add_argument('--interval', type=interval_value, default=10)
    command.add_argument('--output', type=Path, required=True)
    config_home = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    command.add_argument('--config-dir', type=Path, default=config_home / 'magpie')
    args = parser.parse_args(argv)
    if (args.samples - 1) * args.interval > 300:
        parser.error('observation duration must not exceed 300 seconds')
    try:
        with create_output(args.output) as output:
            return collect(args, output)
    except (OSError, ValueError):
        print('Unable to create or write private output.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
