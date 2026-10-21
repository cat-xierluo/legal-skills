#!/usr/bin/env python3
"""把 privacy_check 的阻断诊断映射回提交 / 文件 / 行，辅助人工核对与登记占位符例外。

privacy_check / safe-push / safe-pr 的 PRIVACY_REVIEW_REQUIRED 输出只有规则、两个摘要和行号；
本工具在指定范围内逐提交复算 checker 扫描的全部来源（commit message、commit patch、
path: 与 blob:），按 (rule, source_sha256, content_sha256) 精确匹配，把每组命中定位到
提交与文件，并打印命中行中的本机用户名段供人工核对。

用法：
  python3 privacy-map.py [--repo PATH] BASE HEAD [--record --reviewer 名字] [--reason-prefix 前缀] < 诊断文本

- 不联网、不改写历史、不打印黑名单词；定位依据与 privacy-preflight.md「定位来源」一致。
- --record 仅当规则为 local-user-path 且命中行中的用户名段全部属于占位符白名单时，把
  synthetic 例外写入 Git 公共目录的 privacy-reviewed.json，并复用 checker 的加载校验自检；
  其他规则、非占位符用户名或未能映射的诊断一律转人工并以退出码 2 结束，不静默放行。
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from privacy_check import Checker, PrivacyError, digest  # noqa: E402

DIAGNOSTIC = re.compile(r'rule=(\S+) source_sha256=([0-9a-f]{64}) content_sha256=([0-9a-f]{64}) line=(\d+)')
# 占位符用户名段：文档示例与合成夹具的常见取值；命中行含任何其他段都转人工。
PLACEHOLDER_SEGMENTS = frozenset({
    'demo', 'example', 'sample', 'test', 'testuser', 'user', 'username', 'someone',
    'alice', 'bob', 'carol', 'dummy', 'placeholder', 'your-path', 'yourpath', 'xxx', '...',
})
LOCAL_USER_PATH = re.compile(r'(?:/(?:Users|home)/([\w.-]+)|[A-Za-z]:[\\/]+Users[\\/]+([\w.-]+))')


def git(repo, *args):
    return subprocess.run(['git', '-C', repo, *args], check=True, capture_output=True).stdout


def is_ancestor(repo, base, head):
    return subprocess.run(['git', '-C', repo, 'merge-base', '--is-ancestor', base, head],
                          capture_output=True).returncode == 0


def source_lines(data, wanted_lines):
    text = data.decode('utf-8', 'replace').split('\n')
    for number in sorted(wanted_lines):
        segment = text[number - 1] if 0 < number <= len(text) else ''
        yield number, segment, [a or b for a, b in LOCAL_USER_PATH.findall(segment)]


class Candidate:
    __slots__ = ('source', 'content', 'commits')

    def __init__(self, source, content):
        self.source = source
        self.content = content
        self.commits = []


def collect_sources(repo, base, head):
    """按 checker 的 scan_range 语义枚举范围内每个提交的全部来源（message / patch / path / blob）。"""
    commits = git(repo, 'rev-list', '--reverse', f'{base}..{head}').decode().split()
    subjects = {oid: git(repo, 'log', '-1', '--format=%s', oid).decode().strip() for oid in commits}
    candidates = {}

    def add(source, content, oid):
        key = digest(source)
        candidate = candidates.get(key)
        if candidate is None:
            candidate = candidates[key] = Candidate(source, content)
        candidate.commits.append(f'{oid[:7]} {subjects[oid]}')

    for oid in commits:
        add('commit:' + oid + ':message', git(repo, 'show', '-s', '--format=%B', oid), oid)
        add('commit:' + oid + ':patch',
            git(repo, 'show', '--format=', '--root', '-m', '--no-ext-diff', '--no-textconv',
                '--no-renames', '--full-index', '--binary', oid), oid)
        raw_paths = git(repo, 'diff-tree', '--root', '-m', '-r', '--no-commit-id', '--name-only',
                        '--no-renames', '-z', oid).split(b'\0')
        for raw_path in sorted(set(p for p in raw_paths if p)):
            path = raw_path.decode('utf-8', 'surrogateescape')
            add('path:' + path, raw_path, oid)
            for entry in filter(None, git(repo, 'ls-tree', '-r', '-z', oid, '--', path).split(b'\0')):
                meta, entry_path = entry.split(b'\t', 1)
                _mode, kind, blob = meta.split()
                if kind != b'blob':
                    continue
                actual = entry_path.decode('utf-8', 'surrogateescape')
                add('blob:' + actual, git(repo, 'cat-file', 'blob', blob.decode('ascii')), oid)
    return candidates


def record_exceptions(repo, recordable, reviewer, reason_prefix):
    common = Path(git(repo, 'rev-parse', '--git-common-dir').decode().strip() or '.')
    if not common.is_absolute():
        common = Path(repo) / common
    path = common / 'privacy-reviewed.json'
    existing = json.loads(path.read_text()) if path.exists() else []
    have = {(item['rule'], item['source_sha256'], item['content_sha256']) for item in existing}
    added = 0
    for group in recordable:
        key = (group['rule'], group['source_sha256'], group['content_sha256'])
        if key in have:
            continue
        existing.append({
            'rule': group['rule'],
            'source_sha256': group['source_sha256'],
            'content_sha256': group['content_sha256'],
            'kind': 'synthetic',
            'reason': f'{reason_prefix}{group["source"]}（提交 {"; ".join(group["commits"])}）第 '
                      f'{group["lines"]} 行仅含占位符用户名段 {group["segments"]}（文档示例 / 合成夹具），'
                      '非真实本机目录；来源与内容摘要按诊断精确绑定并逐行核对。',
            'reviewed_by': reviewer,
            'evidence': f'git show {group["commits"][0].split()[0]} -- 相关路径；'
                        'privacy-map.py 按 (rule, source, content) 摘要匹配定位',
        })
        added += 1
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + '\n')
    # 复用 checker 的加载校验，确保写出的记录可被门禁接受。
    try:
        Checker(repo).load_exceptions()
    except PrivacyError as error:
        raise SystemExit(f'PRIVACY_MAP_RECORD_INVALID: 登记文件未通过 checker 校验：{error}')
    return path, added, len(existing)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--repo', default='.')
    parser.add_argument('base')
    parser.add_argument('head')
    parser.add_argument('--record', action='store_true', help='把全占位符 local-user-path 命中登记为 synthetic 例外')
    parser.add_argument('--reason-prefix', default='')
    parser.add_argument('--reviewer')
    args = parser.parse_args()
    if args.record and not (args.reviewer or '').strip():
        parser.error('--record 需要同时提供 --reviewer（审查记录的 reviewed_by 字段）')

    groups = {}
    for line in sys.stdin:
        match = DIAGNOSTIC.search(line)
        if match:
            rule, source_sha, content_sha, number = match.groups()
            groups.setdefault((rule, source_sha, content_sha), set()).add(int(number))
    if not groups:
        print('未从标准输入解析到任何诊断行（期望 PRIVACY_REVIEW_REQUIRED 下的 rule=... 行）')
        return 2

    base = git(args.repo, 'rev-parse', '--verify', f'{args.base}^{{commit}}').decode().strip()
    head = git(args.repo, 'rev-parse', '--verify', f'{args.head}^{{commit}}').decode().strip()
    if not is_ancestor(args.repo, base, head):
        print('PRIVACY_MAP_RANGE_INVALID: base 不是 head 的祖先')
        return 2

    candidates = collect_sources(args.repo, base, head)
    recordable, manual = [], []
    for (rule, source_sha, content_sha), lines in sorted(groups.items()):
        print(f'== rule={rule} src={source_sha[:12]}… cnt={content_sha[:12]}… lines={sorted(lines)}')
        candidate = candidates.get(source_sha)
        if candidate is None or hashlib.sha256(candidate.content).hexdigest() != content_sha:
            print('   !! 未在范围内任何提交的 message / patch / path / blob 来源中找到'
                  '（可能是 PR / squash 文本或其他范围）→ 人工')
            manual.append((rule, 'unmapped'))
            continue
        print(f'   来源={candidate.source}  提交={candidate.commits}')
        segments = set()
        for number, segment, found in source_lines(candidate.content, lines):
            segments.update(found)
            print(f'   L{number}: 用户名段={found or "—"}  | {segment.strip()[:110]}')
        if rule != 'local-user-path':
            print('   → 非 local-user-path 规则，占位符白名单不适用 → 人工')
            manual.append((rule, candidate.source))
        elif segments and segments <= PLACEHOLDER_SEGMENTS:
            print(f'   → 全部占位符 ✓ {sorted(segments)}')
            recordable.append({'rule': rule, 'source_sha256': source_sha, 'content_sha256': content_sha,
                               'source': candidate.source, 'commits': candidate.commits,
                               'lines': sorted(lines), 'segments': sorted(segments)})
        else:
            print(f'   → 含非占位符用户名段 {sorted(segments) or "（未解析出段）"} → 人工')
            manual.append((rule, candidate.source))

    if args.record and recordable:
        path, added, total = record_exceptions(args.repo, recordable, args.reviewer.strip(), args.reason_prefix)
        print(f'\n已写入 {added} 条例外到 {path}（现共 {total} 条，已通过 checker 加载校验）')
    elif recordable:
        print(f'\n{len(recordable)} 组可登记（加 --record --reviewer 写入 privacy-reviewed.json）')
    if manual:
        print(f'\n!! {len(manual)} 组需人工处理：{manual}')
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
