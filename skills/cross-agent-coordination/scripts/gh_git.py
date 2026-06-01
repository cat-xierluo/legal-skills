#!/usr/bin/env python3
"""Git 操作脚本"""
import argparse
import base64
import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from collab_lib import get_agent_identity, get_current_agent, get_token as resolve_token, load_config


def configure_git_identity(dest, identity):
    run(['git', 'config', 'user.name', identity['git_name']], cwd=dest)
    run(['git', 'config', 'user.email', identity['git_email']], cwd=dest)


def resolve_identity(dest, explicit_agent=''):
    config = load_config(dest)
    agent = get_current_agent(config, explicit_agent)
    return get_agent_identity(config, agent)


def get_token(dest=None, agent=''):
    return resolve_token(load_config(dest or '.'), agent)


def run(cmd, cwd=None):
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def capture(cmd, cwd=None):
    return subprocess.check_output(cmd, cwd=str(cwd) if cwd else None).decode('utf-8').strip()


def parse_repo(repo_url):
    repo_url = repo_url.strip()
    m = re.search(r'github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)', repo_url)
    if not m:
        raise SystemExit(f"无法解析 GitHub 仓库地址: {repo_url}")
    return m.group('owner'), m.group('repo')


def clean_repo_url(repo_url):
    owner, repo = parse_repo(repo_url)
    return f"https://github.com/{owner}/{repo}.git"


def git_auth_args(token):
    if not token:
        return []
    raw = f"x-access-token:{token}".encode("utf-8")
    encoded = base64.b64encode(raw).decode("ascii")
    return ['-c', f'http.extraHeader=Authorization: Basic {encoded}']


def git_with_token(token, git_args, cwd=None):
    run(['git', *git_auth_args(token), *git_args], cwd=cwd)


def github_api(method, url, token, payload=None):
    data = None
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'Content-Type': 'application/json',
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode('utf-8')
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8')
        try:
            detail = json.loads(body)
        except json.JSONDecodeError:
            detail = {'message': body}
        return exc.code, detail


def cmd_clone(args):
    token = get_token('.', args.agent)
    if not token: raise SystemExit("需要 GITHUB_TOKEN 或本地配置 token")
    dest = Path(args.dest).expanduser()
    if dest.exists():
        git_with_token(token, ['fetch', '--all'], cwd=dest)
        git_with_token(token, ['pull'], cwd=dest)
    else:
        git_with_token(token, ['clone', clean_repo_url(args.repo), str(dest)])
        run(['git', 'remote', 'set-url', 'origin', clean_repo_url(args.repo)], cwd=dest)

def cmd_branch(args):
    dest = Path(args.dest).expanduser()
    identity = resolve_identity(dest, args.agent)
    configure_git_identity(dest, identity)
    run(['git', 'checkout', '-B', args.name], cwd=dest)
    print(f"AGENT:{identity['id']}")
    print(f"GIT_AUTHOR:{identity['git_name']} <{identity['git_email']}>")

def cmd_commit(args):
    dest = Path(args.dest).expanduser()
    identity = resolve_identity(dest, args.agent)
    configure_git_identity(dest, identity)
    run(['git', 'add', '-A'], cwd=dest)
    run(['git', 'commit', '-m', args.message], cwd=dest)
    print(f"AGENT:{identity['id']}")
    print(f"GIT_AUTHOR:{identity['git_name']} <{identity['git_email']}>")

def cmd_push(args):
    dest = Path(args.dest or '.').expanduser()
    identity = resolve_identity(dest, args.agent)
    try:
        origin = capture(['git', 'remote', 'get-url', 'origin'], cwd=dest)
    except subprocess.CalledProcessError:
        raise SystemExit("当前仓库没有 Git remote，无法 push")
    token = get_token(dest, identity['id'])
    if not token: raise SystemExit("需要 GITHUB_TOKEN 或本地配置 token")
    run(['git', 'remote', 'set-url', 'origin', clean_repo_url(origin)], cwd=dest)
    branch = capture(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=dest)
    git_with_token(token, ['push', '-u', 'origin', branch], cwd=dest)
    # 返回分支名和仓库信息
    print(f"BRANCH:{branch}")
    print(f"REPO:{clean_repo_url(origin)}")
    print(f"AGENT:{identity['id']}")
    print(f"GITHUB_ACTOR:{identity['github_user'] or '取决于实际执行 push/PR 的账号'}")

def cmd_merge_pr(args):
    """自动合并 PR"""
    dest = Path(args.dest or '.').expanduser()
    identity = resolve_identity(dest, args.agent)
    # 解析仓库和 PR 号
    try:
        repo_url = args.repo or capture(['git', 'remote', 'get-url', 'origin'], cwd=dest)
    except subprocess.CalledProcessError:
        raise SystemExit("当前仓库没有 Git remote，无法合并 PR")
    token = get_token(dest, identity['id'])
    if not token: raise SystemExit("需要 GITHUB_TOKEN 或本地配置 token")
    owner, repo = parse_repo(repo_url)

    # 如果没指定 PR 号，从当前分支名提取
    pr_number = args.pr
    if not pr_number:
        branch = capture(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=dest)
        # 查找这个分支对应的 PR
        encoded_head = urllib.parse.quote(f"{owner}:{branch}", safe='')
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls?head={encoded_head}"
        status, body = github_api('GET', url, token)
        if status == 200 and body:
            pr_number = body[0]['number']

    if not pr_number:
        raise SystemExit("无法找到 PR 编号")

    # 合并 PR
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/merge"
    data = {
        "merge_method": args.strategy or "squash",
        "commit_title": f"Merge PR #{pr_number}",
    }
    status, body = github_api('PUT', url, token, data)

    if status == 200:
        print(f"✅ 已合并 PR #{pr_number}")
        # 删除远程分支
        branch = capture(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=dest)
        git_with_token(token, ['push', 'origin', '--delete', branch], cwd=dest)
        print(f"✅ 已删除远程分支 {branch}")
    else:
        print(f"❌ 合并失败: {body}")
        raise SystemExit(status)


def cmd_pr(args):
    """创建 PR，并在正文中记录 Agent 身份。"""
    dest = Path(args.dest or '.').expanduser()
    identity = resolve_identity(dest, args.agent)
    try:
        repo_url = args.repo or capture(['git', 'remote', 'get-url', 'origin'], cwd=dest)
    except subprocess.CalledProcessError:
        raise SystemExit("当前仓库没有 Git remote，无法创建 PR")
    token = get_token(dest, identity['id'])
    if not token:
        raise SystemExit("需要 GITHUB_TOKEN 或本地配置 token")
    owner, repo = parse_repo(repo_url)
    branch = args.head or capture(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=dest)
    title = args.title or f"chore: update from {identity['id']}"
    user_body = args.body or ''
    body = f"""## Agent Attribution

- Agent ID: {identity['id']}
- Git Author: {identity['git_name']} <{identity['git_email']}>
- Expected GitHub Actor: {identity['github_user'] or '取决于实际执行 PR 的账号'}

## Notes

{user_body}
""".strip()

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    status, response = github_api('POST', url, token, {
        'title': title,
        'body': body,
        'head': branch,
        'base': args.base,
    })
    if status == 201:
        print(f"PR_URL:{response['html_url']}")
        print(f"AGENT:{identity['id']}")
        print(f"GIT_AUTHOR:{identity['git_name']} <{identity['git_email']}>")
        print(f"GITHUB_ACTOR:{identity['github_user'] or '取决于实际执行 PR 的账号'}")
    else:
        print(f"❌ 创建 PR 失败: {response}")
        raise SystemExit(status)

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)

    clone = sub.add_parser('clone')
    clone.add_argument('--repo', required=True)
    clone.add_argument('--dest', required=True)
    clone.add_argument('--agent', default='')
    clone.set_defaults(func=cmd_clone)

    branch = sub.add_parser('branch')
    branch.add_argument('--dest', required=True)
    branch.add_argument('--name', required=True)
    branch.add_argument('--agent', default='')
    branch.set_defaults(func=cmd_branch)

    commit = sub.add_parser('commit')
    commit.add_argument('--dest', required=True)
    commit.add_argument('--message', required=True)
    commit.add_argument('--agent', default='')
    commit.set_defaults(func=cmd_commit)

    push = sub.add_parser('push')
    push.add_argument('--dest', nargs='?', default='.')
    push.add_argument('--agent', default='')
    push.set_defaults(func=cmd_push)

    pr = sub.add_parser('pr')
    pr.add_argument('--dest', nargs='?', default='.')
    pr.add_argument('--agent', default='', help='Agent ID（可选）')
    pr.add_argument('--title', default='', help='PR 标题（可选）')
    pr.add_argument('--body', default='', help='PR 正文补充（可选）')
    pr.add_argument('--base', default='main', help='目标分支')
    pr.add_argument('--head', default='', help='来源分支，默认当前分支')
    pr.add_argument('--repo', default='', help='仓库 URL（可选）')
    pr.set_defaults(func=cmd_pr)

    merge = sub.add_parser('merge')
    merge.add_argument('--pr', help='PR 编号（可选）')
    merge.add_argument('--strategy', choices=['merge','squash','rebase'], default='squash', help='合并策略')
    merge.add_argument('--repo', help='仓库 URL（可选）')
    merge.add_argument('--dest', nargs='?', help='仓库目录')
    merge.add_argument('--agent', default='', help='Agent ID（可选）')
    merge.set_defaults(func=cmd_merge_pr)

    args = p.parse_args()
    args.func(args)

if __name__ == '__main__':
    main()
