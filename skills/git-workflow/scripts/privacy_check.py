#!/usr/bin/env python3
"""Shared, fail-closed privacy preflight. Python standard library only.

Heuristics flag data for review, not a claim that a case number is confidential.
Reviewed exceptions are local, exact-content-bound, and never directory ignores.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


class PrivacyError(Exception):
    """Safe diagnostic: never include input values or subprocess stderr."""


RULES = {
    'mobile': re.compile(r'(?<![A-Za-z0-9])1[3-9]\d{9}(?![A-Za-z0-9])'),
    'identity-number': re.compile(r'(?<![A-Za-z0-9])\d{17}[\dXx](?![A-Za-z0-9])'),
    'landline': re.compile(r'(?<!\d)0\d{2,3}-\d{7,8}(?!\d)'),
    'local-user-path': re.compile(r'(?:/(?:Users|home)/[\w.-]+|[A-Za-z]:\\Users\\[\w.-]+)'),
    'case-number': re.compile(r'[（(]\d{4}[）)][^\s（）()]{0,12}(?:民初|刑初|行初|民终|刑终|行终|民申|执(?:恢|保|异)?|破)\d+号'),
    'private-key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
}
REVIEW_FORMATS = {
    '.pdf', '.doc', '.docx', '.odt', '.xls', '.xlsx', '.ods', '.ppt', '.pptx', '.odp',
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.tiff', '.bmp', '.svg', '.heic',
    '.zip', '.gz', '.7z', '.rar', '.tar', '.mp3', '.wav', '.mp4', '.mov', '.mkv',
}
OID = re.compile(r'^(?:[0-9a-f]{40}|[0-9a-f]{64})$')


def digest(text):
    try:
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
    except UnicodeError:
        raise PrivacyError('PRIVACY_UNREADABLE_CONTENT: 文本或路径编码不可读') from None


def read_text(path):
    try:
        return Path(path).read_text(encoding='utf-8')
    except (OSError, UnicodeError):
        raise PrivacyError('PRIVACY_READ_FAILED: 无法完整读取 UTF-8 输入') from None


class Checker:
    def __init__(self, repo='.'):
        self.repo = str(repo)
        self.findings = []
        self.git('rev-parse', '--is-inside-work-tree')
        common = Path(os.fsdecode(self.git('rev-parse', '--git-common-dir')).strip())
        if not common.is_absolute():
            common = Path(self.repo) / common
        self.common = common.resolve()
        self.exceptions = self.load_exceptions()
        self.denylist = []
        root = Path(os.fsdecode(self.git('rev-parse', '--show-toplevel')).strip())
        for path in (self.common / 'privacy-denylist', root / '.githooks/local-denylist'):
            if path.exists():
                # Legacy blacklist must remain untracked; never echo its words.
                if path == root / '.githooks/local-denylist' and self.git('ls-files', '--', '.githooks/local-denylist').strip():
                    raise PrivacyError('PRIVACY_LOCAL_POLICY_TRACKED: 本地黑名单不得入库')
                self.denylist.extend(line.strip() for line in read_text(path).splitlines()
                                     if line.strip() and not line.lstrip().startswith('#'))

    def git(self, *args, input=None, env=None):
        try:
            result = subprocess.run(['git', '--no-replace-objects', '-C', self.repo, *args],
                                    input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    env=env, check=True)
            return result.stdout
        except (OSError, subprocess.CalledProcessError):
            raise PrivacyError('PRIVACY_GIT_READ_FAILED: Git 操作失败，未完成检查') from None

    def load_exceptions(self):
        path = self.common / 'privacy-reviewed.json'
        if not path.exists():
            return []
        try:
            data = json.loads(read_text(path))
            if not isinstance(data, list):
                raise ValueError
            for item in data:
                if not isinstance(item, dict) or set(item) != {
                    'rule', 'source_sha256', 'content_sha256', 'kind', 'reason', 'reviewed_by', 'evidence'
                }:
                    raise ValueError
                if item['rule'] not in {*RULES, 'binary-content'} or item['kind'] not in ('synthetic', 'public-judgment', 'reviewed-binary'):
                    raise ValueError
                if (item['rule'] == 'binary-content') != (item['kind'] == 'reviewed-binary'):
                    raise ValueError
                if item['kind'] == 'reviewed-binary' and not re.fullmatch(r'sha256:[0-9a-f]{64}', item['evidence']):
                    raise ValueError
                if item['kind'] == 'public-judgment' and (
                    item['rule'] != 'case-number' or not item['evidence'].startswith('https://')
                ):
                    raise ValueError
                if any(not isinstance(v, str) or not v.strip() for v in item.values()):
                    raise ValueError
                for key in ('source_sha256', 'content_sha256'):
                    if not re.fullmatch(r'[0-9a-f]{64}', item[key]):
                        raise ValueError
            return data
        except (ValueError, TypeError, AttributeError):
            raise PrivacyError('PRIVACY_POLICY_INVALID: 精确审查记录格式无效') from None

    def scan_text(self, text, source):
        source_hash, text_hash = digest(source), digest(text)
        for rule, pattern in [*RULES.items(), *(
            ('local-denylist', re.compile(re.escape(word))) for word in self.denylist
        )]:
            matches = list(pattern.finditer(text))
            if not matches:
                continue
            reviewed = any(item['rule'] == rule and item['source_sha256'] == source_hash
                           and item['content_sha256'] == text_hash for item in self.exceptions)
            if reviewed:
                continue
            for match in matches:
                self.findings.append((rule, source_hash, text_hash, text.count('\n', 0, match.start()) + 1))

    def scan_bytes(self, data, source):
        try:
            # A printable PDF/SVG/container is not a reviewed text document.
            opaque_file = source.startswith('blob:') and Path(source[5:]).suffix.lower() in REVIEW_FORMATS
            opaque_magic = data.startswith((b'%PDF-', b'PK\x03\x04', b'\x89PNG', b'\xff\xd8', b'GIF87a', b'GIF89a'))
            if opaque_file or opaque_magic:
                raise UnicodeError
            text = data.decode('utf-8')
            if '\0' in text:
                raise UnicodeError
        except UnicodeError:
            source_hash = digest(source)
            content_hash = hashlib.sha256(data).hexdigest()
            if not any(item['rule'] == 'binary-content' and item['source_sha256'] == source_hash
                       and item['content_sha256'] == content_hash for item in self.exceptions):
                self.findings.append(('binary-content', source_hash, content_hash, 0))
            return
        self.scan_text(text, source)

    def scan_tree_changes(self, tree, paths):
        for path in sorted(set(paths)):
            if path == '.githooks/local-denylist':
                raise PrivacyError('PRIVACY_LOCAL_POLICY_TRACKED: 本地黑名单不得出现在待发布变更')
            self.scan_text(path, 'path:' + path)
            entries = self.git('ls-tree', '-z', tree, '--', path).split(b'\0')
            for entry in filter(None, entries):
                meta, _ = entry.split(b'\t', 1)
                mode, kind, oid = meta.split()
                if kind != b'blob':
                    raise PrivacyError('PRIVACY_UNREADABLE_CONTENT: 子模块或目录不能按文本检查')
                self.scan_bytes(self.git('cat-file', 'blob', oid.decode('ascii')), 'blob:' + path)

    def scan_staged(self):
        tree = self.git('write-tree').decode('ascii').strip()
        paths = [os.fsdecode(p) for p in self.git('diff', '--cached', '--name-only', '-z', '--no-renames').split(b'\0') if p]
        self.scan_tree_changes(tree, paths)
        self.scan_bytes(self.git('diff', '--cached', '--no-ext-diff', '--no-textconv',
                                 '--no-renames', '--full-index', '--binary'), 'staged-patch')
        return tree

    def scan_range(self, base, head):
        # Only immutable OIDs: callers resolve/fetch their actual integration base.
        if not OID.fullmatch(base) or not OID.fullmatch(head):
            raise PrivacyError('PRIVACY_RANGE_INVALID: 范围必须使用完整不可变 OID')
        if self.git('rev-parse', '--is-shallow-repository').strip() != b'false':
            raise PrivacyError('PRIVACY_HISTORY_INCOMPLETE: 浅克隆不能证明完整历史')
        grafts = Path(os.fsdecode(self.git('rev-parse', '--git-path', 'info/grafts')).strip())
        if not grafts.is_absolute():
            grafts = Path(self.repo) / grafts
        if grafts.exists() and grafts.stat().st_size:
            raise PrivacyError('PRIVACY_HISTORY_INCOMPLETE: 拒绝 graft 改写历史视图')
        self.git('cat-file', '-e', base + '^{commit}')
        self.git('cat-file', '-e', head + '^{commit}')
        self.git('merge-base', '--is-ancestor', base, head)
        commits = self.git('rev-list', '--reverse', base + '..' + head).decode('ascii').splitlines()
        if not commits:
            raise PrivacyError('PRIVACY_EMPTY_RANGE: 待发布范围为空')
        # Fail if any object in the range is unavailable, not only net-diff blobs.
        self.git('rev-list', '--objects', '--missing=error', base + '..' + head)
        for oid in commits:
            if not OID.fullmatch(oid):
                raise PrivacyError('PRIVACY_RANGE_INVALID: 无效提交列表')
            self.scan_bytes(self.git('show', '-s', '--format=%B', oid), 'commit:' + oid + ':message')
            self.scan_bytes(self.git('show', '--format=', '--root', '-m', '--no-ext-diff',
                                     '--no-textconv', '--no-renames', '--full-index', '--binary', oid),
                            'commit:' + oid + ':patch')
            paths = [os.fsdecode(p) for p in self.git('diff-tree', '--root', '-m', '-r',
                     '--no-commit-id', '--name-only', '--no-renames', '-z', oid).split(b'\0') if p]
            self.scan_tree_changes(oid, paths)
        return len(commits)

    def finish(self):
        if self.findings:
            lines = ['PRIVACY_REVIEW_REQUIRED: 检测到待核对内容；未输出原文']
            for rule, source_hash, text_hash, line in sorted(set(self.findings)):
                lines.append(f'rule={rule} source_sha256={source_hash} content_sha256={text_hash} line={line}')
            raise PrivacyError('\n'.join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='.')
    sub = parser.add_subparsers(dest='mode', required=True)
    sub.add_parser('staged')
    text = sub.add_parser('text')
    text.add_argument('--file', required=True)
    text.add_argument('--source', default='commit-message')
    outgoing = sub.add_parser('range')
    outgoing.add_argument('--base-oid', required=True)
    outgoing.add_argument('--head-oid', required=True)
    args = parser.parse_args()
    try:
        checker = Checker(args.repo)
        if args.mode == 'staged':
            checker.scan_staged()
        elif args.mode == 'text':
            checker.scan_text(read_text(args.file), args.source)
        else:
            checker.scan_range(args.base_oid, args.head_oid)
        checker.finish()
        print('PRIVACY_OK')
        return 0
    except PrivacyError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
