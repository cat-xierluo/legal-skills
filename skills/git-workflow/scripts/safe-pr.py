#!/usr/bin/env python3
"""Send only preflighted PR/squash text; no interactive/generated-text fallback.

Creation is draft-only. Squash requires separate merge authorization and the
existing review/CI gates; this helper is only the privacy publication boundary.
"""
import argparse
import json
import re
from urllib.parse import urlsplit
import subprocess
import sys

from privacy_check import Checker, OID, PrivacyError, read_text


def github_target(remote_url):
    """Normalize Git HTTPS/SSH URLs for gh --repo, without exposing credentials."""
    scp = re.fullmatch(r'(?:[^@/:]+@)?([A-Za-z0-9.-]+):([^?#]+)', remote_url)
    if scp and '://' not in remote_url:
        host, path = scp.groups()
    else:
        try:
            parsed = urlsplit(remote_url)
            if parsed.scheme not in ('https', 'ssh') or not parsed.hostname or parsed.query or parsed.fragment:
                raise ValueError
            if parsed.port not in (None, 22, 443):
                raise ValueError
            host, path = parsed.hostname, parsed.path.lstrip('/')
        except ValueError:
            raise PrivacyError('SAFE_PR_REMOTE_INVALID: 需要可核对的 GitHub HTTPS/SSH 远端') from None
    if path.endswith('.git'):
        path = path[:-4]
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', path):
        raise PrivacyError('SAFE_PR_REMOTE_INVALID: 远端仓库路径格式无效')
    return host.lower() + '/' + path


def gh(repo, *args):
    try:
        return subprocess.run(['gh', *args], cwd=repo, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode('utf-8')
    except (OSError, UnicodeError, subprocess.CalledProcessError):
        # A transport failure can follow server acceptance. Never auto-retry.
        raise PrivacyError('SAFE_PR_GH_FAILED: 操作未确认；请只读核对远端后再决定，勿盲目重试') from None


def remote_oid(checker, remote, ref):
    records = checker.git('ls-remote', '--exit-code', '--refs', remote, ref).decode('utf-8').splitlines()
    if len(records) != 1 or records[0].split('\t')[1] != ref:
        raise PrivacyError('SAFE_PR_REMOTE_UNKNOWN: 无法唯一确认远端对象')
    return records[0].split('\t')[0]


def pr_metadata(repo, target, remote_url):
    try:
        data = json.loads(gh(repo, 'pr', 'view', target, '--repo', remote_url,
                             '--json', 'headRefOid,baseRefName,title,body,state,isDraft'))
        if not isinstance(data, dict):
            raise ValueError
        return data
    except (ValueError, TypeError):
        raise PrivacyError('SAFE_PR_METADATA_INVALID: 无法完整读取 PR 元数据') from None


def run(args):
    checker = Checker(args.repo)
    if not OID.fullmatch(args.expected_head):
        raise PrivacyError('SAFE_PR_BAD_HEAD: 必须提供已审核的完整 head OID')
    # Read once: these exact strings are both checked and passed to gh.
    title, body = read_text(args.title_file), read_text(args.body_file)
    if not title.strip() or '\n' in title.rstrip('\n') or not body.strip():
        raise PrivacyError('SAFE_PR_TEXT_INVALID: 标题须为单行且正文非空')
    title = title.rstrip('\n')
    checker.scan_text(title, args.mode + ':title')
    checker.scan_text(body, args.mode + ':body')
    remote_url = github_target(checker.git('remote', 'get-url', args.remote).decode('utf-8').strip())
    if args.mode == 'create':
        base = args.base
        checker.git('check-ref-format', '--branch', args.head)
        head_ref = 'refs/heads/' + args.head
    else:
        metadata = pr_metadata(args.repo, args.number, remote_url)
        if metadata.get('headRefOid') != args.expected_head or metadata.get('state') != 'OPEN' or metadata.get('isDraft') is not False:
            raise PrivacyError('SAFE_PR_STATE_CHANGED: PR head/状态不符合已审核对象')
        base = metadata.get('baseRefName', '')
        head_ref = 'refs/pull/' + args.number + '/head'
        for key in ('title', 'body'):
            if not isinstance(metadata.get(key), str):
                raise PrivacyError('SAFE_PR_METADATA_INVALID: 缺少完整 PR 文本')
            checker.scan_text(metadata[key], 'pr:' + key)
    checker.git('check-ref-format', '--branch', base)
    base_ref = 'refs/heads/' + base
    base_oid = remote_oid(checker, args.remote, base_ref)
    head_oid = remote_oid(checker, args.remote, head_ref)
    if head_oid != args.expected_head:
        raise PrivacyError('SAFE_PR_HEAD_CHANGED: 远端 head 已变化，停止发布')
    # Fetch exactly the advertised objects; missing/unreadable history fails closed.
    checker.git('fetch', '--', args.remote, base_oid, head_oid)
    checker.scan_range(base_oid, head_oid)
    checker.finish()
    if remote_oid(checker, args.remote, base_ref) != base_oid or remote_oid(checker, args.remote, head_ref) != head_oid:
        raise PrivacyError('SAFE_PR_REMOTE_CHANGED: 预检期间远端发生变化')
    if args.mode == 'create':
        url = gh(args.repo, 'pr', 'create', '--repo', remote_url, '--draft',
                 '--base', base, '--head', args.head, '--title', title, '--body', body).strip()
        verified = pr_metadata(args.repo, url, remote_url)
        if verified.get('headRefOid') != head_oid or verified.get('title') != title or verified.get('body') != body or verified.get('baseRefName') != base:
            raise PrivacyError('SAFE_PR_POSTCHECK_FAILED: PR 已创建但对象或文本变化；需复核，勿再次创建')
        print(url)
    else:
        gh(args.repo, 'pr', 'merge', args.number, '--repo', remote_url, '--squash',
           '--match-head-commit', head_oid, '--subject', title, '--body', body)
        print('SAFE_PR_SQUASH_SENT: 请核对 mergedAt 与 merge commit')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='.')
    parser.add_argument('--remote', default='origin')
    sub = parser.add_subparsers(dest='mode', required=True)
    for mode in ('create', 'squash'):
        child = sub.add_parser(mode)
        child.add_argument('--expected-head', required=True)
        child.add_argument('--title-file', required=True)
        child.add_argument('--body-file', required=True)
        if mode == 'create':
            child.add_argument('--base', required=True)
            child.add_argument('--head', required=True)
        else:
            child.add_argument('--number', required=True, type=lambda s: str(int(s)) if int(s) > 0 else parser.error('PR 编号必须为正整数'))
    try:
        run(parser.parse_args())
        return 0
    except PrivacyError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
