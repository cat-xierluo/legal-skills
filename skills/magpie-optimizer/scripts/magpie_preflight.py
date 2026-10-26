#!/usr/bin/env python3
"""Read-only environment preflight for the magpie-optimizer Skill.

Purpose
    Report whether this machine meets the prerequisites for using
    magpie-optimizer: the Magpie CLI, the local gateway, the Python runtime,
    the connected agents, the route logs, the Magpie configuration files, the
    CLI capabilities, proxy/loopback risk and GUI-vs-CLI concurrency risk.

Read-only boundary
    Reads only: `magpie` read-only subcommands, the local Magpie config files
    (providers.json, settings.json, routing/), /etc/hosts and the local
    process table. It never writes Magpie configuration, never changes the
    gateway, never logs in, never starts a model request and never spends
    quota. The gateway probe is a single GET on /v1/magpie/concurrency.

Privacy
    The report carries no credential, no account identifier, no e-mail
    address, no absolute user path, no prompt text, no session title and no
    proxy URL: proxies are reported as presence and count only.

Exit codes
    0 = no failed check (warnings allowed), 1 = at least one failed check,
    2 = usage error or an unreadable overall input.
"""
import argparse
import datetime as dt
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.dont_write_bytecode = True

try:
    # Reuse the sibling script conventions when it is present.
    from magpie_route import Refused, require, parse_json, load, save_new
except ImportError:  # standalone copy outside the skill directory
    class Refused(Exception):
        pass

    def require(ok, reason):
        if not ok:
            raise Refused(reason)

    def parse_json(content):
        def unique(pairs):
            obj = {}
            for k, v in pairs:
                require(k not in obj, 'duplicate_json_key')
                obj[k] = v
            return obj
        return json.loads(content, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(Refused('non_finite_json')))

    def load(path):
        return parse_json(Path(path).read_bytes())

    def save_new(path, value):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")

SCHEMA = 'magpie-preflight.v1'
DEFAULT_GATEWAY = 'http://127.0.0.1:3425'
CONCURRENCY_PATH = '/v1/magpie/concurrency'
PLACEHOLDERS = {'—', '–', '-', 'none', 'null', 'n/a', 'off'}
FALSEY_PROXY = {'off', 'none', 'false', '0', 'disabled', 'no', 'null', '-', '—', ''}

# Vendor domains whose loopback resolution is a known proxy-bypass shape.
# Only the hostname is ever reported; the resolved address is never printed.
VENDOR_DOMAINS = frozenset({
    'chatgpt.com', 'openai.com', 'oaistatic.com', 'oaiusercontent.com',
    'anthropic.com', 'claude.ai',
    'deepseek.com', 'bigmodel.cn', 'zhipuai.cn', 'moonshot.cn', 'kimi.com',
    'minimaxi.com', 'minimax.io', 'minimax.chat', 'minimaxi.chat',
    'dashscope.aliyuncs.com', 'aliyuncs.com', 'siliconflow.cn', 'lingyiwanwu.com',
    'qianfan.baidu.com', 'baidubce.com', 'volces.com', 'stepfun.com',
    'baichuan-ai.com', 'huaweicloud.com', 'generativelanguage.googleapis.com',
    'googleapis.com', 'mistral.ai', 'cohere.com', 'groq.com', 'openrouter.ai',
    'together.xyz', 'amazonaws.com', 'x.ai', 'deepinfra.com', 'perplexity.ai',
})

# Trailing path-like run of a `magpie ls` line (may contain spaces, e.g.
# "~/Library/Application Support/...").
_PATH_RUN = re.compile(r'(?:~|\.{1,2}|/)[^\s]*(?:\s[^\s]+)*\s*$')
# A version may carry a leading "v" ("magpie v1.2.3").  The look-behind
# keeps the match from starting inside a word or inside a dotted number, so
# "v1.2.3" yields the whole "1.2.3" instead of the trailing "2.3".
_VERSION = re.compile(r'(?<![\w.])v?(\d+(?:\.\d+)+)')
_SPACES = re.compile(r'\s{2,}')


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------
def default_config_dir():
    base = os.environ.get('XDG_CONFIG_HOME')
    if not base:
        base = str(Path.home() / '.config')
    return Path(base) / 'magpie'


def run_cli(args, timeout=60):
    """Run a read-only Magpie CLI subcommand and return its stdout.

    Raise Refused when the binary is missing or the command fails; the raw
    stderr is never returned so that account or credential text cannot leak.
    """
    binary = shutil.which('magpie')
    require(binary is not None, 'magpie_cli_not_found')
    p = subprocess.run([binary, *args], capture_output=True, text=True, timeout=timeout)
    require(p.returncode == 0, 'magpie_cli_exit_' + str(p.returncode))
    return p.stdout


def run_process(args, timeout=15):
    """Run a plain local command and return its stdout."""
    p = subprocess.run(list(args), capture_output=True, text=True, timeout=timeout)
    return p.stdout


def extract_version(text):
    """Return the version number in a CLI banner, without a leading 'v'."""
    m = _VERSION.search(text or '')
    return m.group(1) if m else None


def has_proxy(value):
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in FALSEY_PROXY
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) > 0
    if isinstance(value, (int, float)):
        return value != 0
    return bool(value)


def is_vendor_host(host):
    host = host.lower()
    return any(host == v or host.endswith('.' + v) for v in VENDOR_DOMAINS)


def safe_gateway_label(gateway):
    """Render a gateway without credentials, query or fragment."""
    try:
        parts = urllib.parse.urlsplit(gateway)
    except ValueError:
        return 'invalid'
    host = parts.hostname or ''
    try:
        port = parts.port
    except ValueError:
        port = None
    label = parts.scheme + '://' + host
    return label + (':' + str(port) if port else '')


def _result(code, status, detail, evidence=None):
    return {'code': code, 'status': status, 'detail': detail, 'evidence': evidence or {}}


# --------------------------------------------------------------------------
# public pure functions (stable names, imported by the test suite)
# --------------------------------------------------------------------------
def parse_agent_lines(text):
    """Parse the output of `magpie ls` / `magpie <agent>`.

    Returns a list of {'name': str, 'model': str|None, 'effort': str|None,
    'subagent_model': str|None, 'subagent_effort': str|None, 'raw': str}.
    Lines that cannot be parsed are skipped; no exception is raised.
    """
    rows = []
    for line in (text or '').splitlines():
        if not line.strip():
            continue
        raw = line[:-1] if line.endswith('\n') else line
        path, remainder = _split_config_path(raw)
        chunks = [c.strip() for c in remainder.split('·')]
        chunks = [c for c in chunks if c]
        if not chunks:
            continue
        head = chunks[0]
        fields = _SPACES.split(head.strip())
        name = fields[0].strip() if fields else ''
        if not name or not re.search(r'[A-Za-z0-9]', name):
            continue
        # A usable agent line carries a config path, a field separator or a
        # padded name/model pair; anything else is not an agent entry.
        if not (path or '·' in raw or len(fields) > 1):
            continue
        row = {'name': name, 'model': None, 'effort': None,
               'subagent_model': None, 'subagent_effort': None, 'raw': raw}
        if len(fields) > 1:
            row['model'] = _clean_value(fields[1])
        for chunk in chunks[1:]:
            tokens = chunk.split()
            if not tokens:
                continue
            key = tokens[0]
            if key == 'subagent' and len(tokens) > 2 and tokens[1] == 'model':
                row['subagent_model'] = _clean_value(tokens[2])
            elif key == 'subagent' and len(tokens) > 2 and tokens[1] == 'effort':
                row['subagent_effort'] = _clean_value(tokens[2])
            elif key == 'effort' and len(tokens) > 1:
                row['effort'] = _clean_value(tokens[1])
            elif key == 'model' and len(tokens) > 1:
                row['model'] = _clean_value(tokens[1])
        rows.append(row)
    return rows


def detect_loopback_hosts(hosts_text):
    """Return the sorted vendor hostnames of /etc/hosts that resolve to loopback.

    Only dotted domain names are kept; comments and blank lines are ignored.
    Addresses that point back to the machine (127.0.0.0/8, ::1, 0.0.0.0) are
    treated as loopback. The resolved address itself is never returned.
    """
    found = set()
    for line in (hosts_text or '').splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        if not _is_loopback_address(parts[0]):
            continue
        for host in parts[1:]:
            if '.' not in host:
                continue
            if is_vendor_host(host):
                found.add(host.lower())
    return sorted(found)


def summarize_checks(checks):
    """Return {'ok': n, 'warn': n, 'fail': n} counted by the status field."""
    counts = {'ok': 0, 'warn': 0, 'fail': 0}
    for check in checks or []:
        if not isinstance(check, dict):
            continue
        status = check.get('status')
        if status in counts:
            counts[status] += 1
    return counts


# --------------------------------------------------------------------------
# internal parsing helpers
# --------------------------------------------------------------------------
def _split_config_path(line):
    """Split a trailing config path off a line; returns (path, remainder)."""
    m = _PATH_RUN.search(line)
    if not m:
        return None, line
    path = m.group(0).strip()
    if not path or ' ' in path and path.count('/') == 0:
        return None, line
    return path, line[:m.start()]


def _clean_value(value):
    value = (value or '').strip()
    if not value or value.lower() in PLACEHOLDERS:
        return None
    return value


def _is_loopback_address(address):
    address = address.strip()
    if address == '0.0.0.0':
        return True
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------
def check_magpie_cli(run=None):
    run = run or run_cli
    try:
        out = run(['--version'])
    except Refused as e:
        return _result('MAGPIE_CLI', 'fail', '未找到或无法执行 Magpie CLI（' + str(e) + '）')
    version = extract_version(out)
    if version:
        return _result('MAGPIE_CLI', 'ok', 'Magpie CLI 可用，版本 ' + version, {'version': version})
    return _result('MAGPIE_CLI', 'warn', 'Magpie CLI 可执行，但 --version 输出不像版本号',
                   {'version_found': False})


def check_gateway_health(gateway, timeout=5):
    try:
        parts = urllib.parse.urlsplit(gateway)
        port = parts.port
    except ValueError:
        raise Refused('gateway_url_invalid')
    if parts.scheme != 'http' or not parts.hostname or port is None:
        return _result('GATEWAY_HEALTH', 'fail', '只允许本机回环网关（需为 http://<数字回环地址>:<端口>）')
    if parts.username or parts.password or parts.path not in ('', '/') or parts.query or parts.fragment:
        return _result('GATEWAY_HEALTH', 'fail', '只允许本机回环网关（地址不得含凭据、路径或查询串）')
    try:
        address = ipaddress.ip_address(parts.hostname)
    except ValueError:
        return _result('GATEWAY_HEALTH', 'fail', '只允许本机回环网关（主机名必须是数字回环地址）')
    if not address.is_loopback:
        return _result('GATEWAY_HEALTH', 'fail', '只允许本机回环网关（目标不是数字回环地址）')
    url = gateway.rstrip('/') + CONCURRENCY_PATH
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(urllib.request.Request(url, method='GET'), timeout=timeout) as response:
            status = response.status
            response.read(4096)
    except urllib.error.HTTPError as e:
        status = e.code
    except Refused:
        return _result('GATEWAY_HEALTH', 'warn', '网关返回了重定向或非预期响应')
    except (urllib.error.URLError, TimeoutError, OSError):
        return _result('GATEWAY_HEALTH', 'fail', '网关不可用（连接失败或超时）')
    if 200 <= status < 300:
        return _result('GATEWAY_HEALTH', 'ok', '网关只读端点应答正常', {'http_status': status})
    return _result('GATEWAY_HEALTH', 'warn', '网关可达但只读端点返回非 2xx 状态', {'http_status': status})


def check_python():
    version = '.'.join(str(part) for part in sys.version_info[:3])
    if sys.version_info >= (3, 10):
        return _result('PYTHON', 'ok', 'Python 版本满足要求（>= 3.10）', {'version': version})
    return _result('PYTHON', 'fail', 'Python 版本低于 3.10，无法运行本 Skill 的脚本', {'version': version})


def check_agents(run=None):
    run = run or run_cli
    try:
        out = run(['ls'])
    except Refused as e:
        return _result('AGENTS', 'fail', '无法读取已接入 Magpie 的 Agent 列表（' + str(e) + '）')
    count = len(parse_agent_lines(out))
    if count > 0:
        return _result('AGENTS', 'ok', '已检测到已接入 Magpie 的 Agent', {'count': count})
    return _result('AGENTS', 'warn', '未检测到已接入 Magpie 的 Agent', {'count': 0})


def check_route_log(config_dir):
    directory = Path(config_dir) / 'routing'
    if not directory.exists():
        return _result('ROUTE_LOG', 'warn', '尚未产生路由日志（routing 目录不存在）', {'exists': False, 'files': 0})
    if not directory.is_dir():
        return _result('ROUTE_LOG', 'warn', 'routing 路径不是目录，尚未产生路由日志', {'exists': True, 'files': 0})
    try:
        files = sum(1 for entry in directory.iterdir() if entry.is_file())
    except OSError as e:
        return _result('ROUTE_LOG', 'fail', '路由日志目录存在但不可读（' + type(e).__name__ + '）')
    return _result('ROUTE_LOG', 'ok', '路由日志目录可读', {'exists': True, 'files': files})


def check_providers_json(config_dir):
    path = Path(config_dir) / 'providers.json'
    if not path.exists():
        return _result('PROVIDERS_JSON', 'fail', '未找到 Magpie 配置文件 providers.json')
    try:
        data = load(path)
    except (OSError, ValueError, Refused) as e:
        return _result('PROVIDERS_JSON', 'fail', 'providers.json 无法解析（' + type(e).__name__ + '）')
    if not isinstance(data, dict) or not isinstance(data.get('providers'), list):
        return _result('PROVIDERS_JSON', 'fail', 'providers.json 结构不符合预期（缺少 providers 列表）')
    groups = data.get('groups')
    return _result('PROVIDERS_JSON', 'ok', 'Magpie 配置文件可读且结构正常',
                   {'providers': len(data['providers']),
                    'groups': len(groups) if isinstance(groups, list) else 0})


def check_cli_capability(run=None):
    run = run or run_cli

    def help_text(args):
        try:
            return run(args)
        except (Refused, OSError, ValueError):
            return ''

    group_help = help_text(['group', '--help'])
    rule_help = help_text(['group', 'rule', '--help'])
    support = {
        'group_set': bool(re.search(r'\bgroup\s+set\b', group_help)),
        'group_rule_add': bool(re.search(r'\brule\s+add\b', rule_help)) or
                          bool(re.search(r'\bgroup\s+rule\s+add\b', group_help)),
        'rule_use_intent': ('use=' in rule_help and 'intent=' in rule_help),
    }
    if all(support.values()):
        return _result('CLI_CAPABILITY', 'ok', 'CLI 支持 group set、group rule add 与 use=/intent= 规则',
                       dict(support))
    if any(support.values()):
        return _result('CLI_CAPABILITY', 'warn', 'CLI 仅支持部分路由能力，自动化脚本需降级',
                       dict(support))
    return _result('CLI_CAPABILITY', 'fail', 'CLI 不支持 group set / group rule add，无法自动管理路由',
                   dict(support))


def check_proxy_loopback(config_dir):
    config_dir = Path(config_dir)
    global_proxy = False
    settings = config_dir / 'settings.json'
    if settings.exists():
        try:
            data = load(settings)
        except (OSError, ValueError, Refused):
            data = None
        if isinstance(data, dict):
            global_proxy = has_proxy(data.get('proxy')) or has_proxy(data.get('proxyCustom'))
    provider_proxy_count = 0
    providers = config_dir / 'providers.json'
    if providers.exists():
        try:
            data = load(providers)
        except (OSError, ValueError, Refused):
            data = None
        if isinstance(data, dict) and isinstance(data.get('providers'), list):
            provider_proxy_count = sum(
                1 for item in data['providers']
                if isinstance(item, dict) and has_proxy(item.get('proxy')))
    hosts_readable = True
    hosts_text = ''
    try:
        hosts_text = Path('/etc/hosts').read_text(errors='replace')
    except OSError:
        hosts_readable = False
    loopback_hosts = detect_loopback_hosts(hosts_text)
    evidence = {'global_proxy': global_proxy, 'provider_proxy_count': provider_proxy_count,
                'loopback_hosts': loopback_hosts}
    if loopback_hosts:
        return _result('PROXY_LOOPBACK_RISK', 'warn',
                       '厂商域名解析到回环时网关可能绕过全局代理直连（仅报疑似，不修改 hosts）', evidence)
    if not hosts_readable:
        return _result('PROXY_LOOPBACK_RISK', 'warn', '无法读取 /etc/hosts，无法确认回环解析风险', evidence)
    if global_proxy or provider_proxy_count:
        return _result('PROXY_LOOPBACK_RISK', 'ok', '已配置代理，未发现厂商域名回环解析', evidence)
    return _result('PROXY_LOOPBACK_RISK', 'ok', '未配置代理且未发现厂商域名回环解析，无风险特征', evidence)


def detect_gui_process(run=None):
    """Best-effort probe for a running Magpie GUI; True/False/None (unknown)."""
    run = run or run_process
    for args in (['ps', '-Ao', 'command='], ['ps', '-eo', 'args=']):
        try:
            text = run(args)
        except (OSError, ValueError, subprocess.SubprocessError):
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        for line in text.splitlines():
            lowered = line.lower()
            if 'magpie' in lowered and '.app/contents/macos' in lowered:
                return True
        return False
    return None


def check_gui_concurrent(run=None):
    detected = detect_gui_process(run)
    if detected is True:
        return _result('GUI_CLI_CONCURRENT', 'warn',
                       'GUI 正在运行，与 CLI 并发改配置可能互相覆盖', {'gui_process_detected': True})
    if detected is False:
        return _result('GUI_CLI_CONCURRENT', 'warn',
                       '未检测到正在运行的 Magpie GUI 进程（改动配置前仍建议确认 GUI 未运行）',
                       {'gui_process_detected': False})
    return _result('GUI_CLI_CONCURRENT', 'warn', '无法确认 GUI 进程状态',
                   {'gui_process_detected': None})


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Refused('gateway_redirect_refused')


# --------------------------------------------------------------------------
# report assembly
# --------------------------------------------------------------------------
def safe_check(code, func, *args, **kwargs):
    """Run one check; any exception becomes a failed row instead of a crash."""
    try:
        result = func(*args, **kwargs)
    except Refused as e:
        return _result(code, 'fail', '检查被拒绝：' + str(e))
    except Exception as e:  # noqa: BLE001 - a broken check must not kill the report
        return _result(code, 'fail', '检查执行异常：' + type(e).__name__)
    if not isinstance(result, dict) or result.get('status') not in ('ok', 'warn', 'fail'):
        return _result(code, 'fail', '检查返回了非法状态')
    result.setdefault('code', code)
    result.setdefault('detail', '')
    result.setdefault('evidence', {})
    return result


def build_report(gateway, config_dir, timeout=5, run=None, run_proc=None):
    checks = [
        safe_check('MAGPIE_CLI', check_magpie_cli, run),
        safe_check('GATEWAY_HEALTH', check_gateway_health, gateway, timeout),
        safe_check('PYTHON', check_python),
        safe_check('AGENTS', check_agents, run),
        safe_check('ROUTE_LOG', check_route_log, config_dir),
        safe_check('PROVIDERS_JSON', check_providers_json, config_dir),
        safe_check('CLI_CAPABILITY', check_cli_capability, run),
        safe_check('PROXY_LOOPBACK_RISK', check_proxy_loopback, config_dir),
        safe_check('GUI_CLI_CONCURRENT', check_gui_concurrent, run_proc),
    ]
    return {'schema': SCHEMA, 'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'gateway': safe_gateway_label(gateway), 'checks': checks,
            'summary': summarize_checks(checks)}


def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--gateway', default=argparse.SUPPRESS,
                        help='本地网关地址，默认 ' + DEFAULT_GATEWAY)
    common.add_argument('--output', default=argparse.SUPPRESS,
                        help='把报告写入该文件（新建，权限 0600）')
    common.add_argument('--config-dir', default=argparse.SUPPRESS,
                        help='Magpie 配置目录，默认 ~/.config/magpie')
    common.add_argument('--timeout', type=int, default=argparse.SUPPRESS,
                        help='网关探测超时秒数，默认 5')

    parser = argparse.ArgumentParser(prog='magpie_preflight.py', description=__doc__,
                                     parents=[common],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('check', help='运行环境体检（默认子命令）', parents=[common])
    args = parser.parse_args(argv)

    command = getattr(args, 'command', None) or 'check'
    if command != 'check':
        raise Refused('unknown_command_' + str(command))
    gateway = getattr(args, 'gateway', DEFAULT_GATEWAY)
    output = getattr(args, 'output', None)
    config_dir = getattr(args, 'config_dir', None) or default_config_dir()
    timeout = getattr(args, 'timeout', 5)
    if not isinstance(timeout, int) or not 1 <= timeout <= 60:
        raise Refused('timeout_out_of_range')

    # An unusable gateway URL is a usage error; a reachable but non-loopback
    # gateway is reported as a failed check instead.
    try:
        parts = urllib.parse.urlsplit(gateway)
        parts.port
    except ValueError:
        raise Refused('gateway_url_invalid')
    if not parts.scheme or not parts.hostname:
        raise Refused('gateway_url_invalid')

    report = build_report(gateway, config_dir, timeout)
    if output:
        save_new(output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(1 if report['summary']['fail'] else 0)


if __name__ == '__main__':
    try:
        main()
    except (Refused, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as e:
        # Do not echo upstream payloads, raw JSON, file contents or CLI stderr.
        reason = str(e) if isinstance(e, Refused) else type(e).__name__
        print(json.dumps({'status': 'REFUSED', 'reason': reason}), file=sys.stderr)
        sys.exit(2)
    except Exception as e:  # noqa: BLE001 - never leak a traceback with local paths
        print(json.dumps({'status': 'REFUSED', 'reason': type(e).__name__}), file=sys.stderr)
        sys.exit(2)
