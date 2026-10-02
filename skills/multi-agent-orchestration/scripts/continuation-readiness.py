#!/usr/bin/env python3
"""Read existing Codex heartbeat configuration; never create jobs or claim autonomy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

SCHEMA = 'multi-agent-orchestration.continuation.v1'
LIMIT = 512 * 1024


class Rejected(Exception):
    def __init__(self, code, detail):
        self.code, self.detail = code, detail


def require(value, code, detail):
    if not value:
        raise Rejected(code, detail)


def read_bytes(path):
    # Bound reads even when the input grows after stat; no configuration writes.
    with path.open('rb') as handle:
        data = handle.read(LIMIT + 1)
    require(len(data) <= LIMIT, 'INPUT_TOO_LARGE', '输入超过512KiB；保留原件并缩小合同，不截断解析。')
    return data


def read_json(path):
    data = read_bytes(path)
    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'DUPLICATE_FIELD', 'JSON含重复字段，不能猜测持续策略。')
            value[key] = item
        return value
    value = json.loads(data, object_pairs_hook=unique_object)
    require(isinstance(value, dict), 'INVALID_OBJECT', '输入必须是JSON对象。')
    return value, hashlib.sha256(data).hexdigest()


def absolute_path(value, label):
    require(isinstance(value, str) and bool(value.strip()) and Path(value).is_absolute(),
            'ABSOLUTE_PATH_REQUIRED', label + '必须是绝对路径。')
    return Path(value).resolve(strict=True)


def interval_seconds(rule):
    require(isinstance(rule, str), 'SCHEDULE_UNVERIFIABLE', '无法读取正式heartbeat周期。')
    parts = rule.removeprefix('RRULE:').split(';')
    parsed = {}
    for part in parts:
        key, separator, value = part.partition('=')
        require(separator and key not in parsed, 'SCHEDULE_UNVERIFIABLE', '周期字段缺失或重复。')
        parsed[key] = value
    require(set(parsed) <= {'FREQ', 'INTERVAL'} and 'FREQ' in parsed,
            'SCHEDULE_UNVERIFIABLE', '此版本仅验证无额外过滤条件的MINUTELY/HOURLY周期。')
    unit = {'MINUTELY': 60, 'HOURLY': 3600}.get(parsed['FREQ'])
    count = parsed.get('INTERVAL', '1')
    require(unit is not None and bool(re.fullmatch(r'[0-9]+', count)) and 0 < int(count) <= 1440,
            'SCHEDULE_UNVERIFIABLE', '周期类型或间隔无法验证。')
    return unit * int(count)


def check_contract(path, automation_root):
    try:
        import tomllib
    except ImportError:
        raise Rejected('CONTINUATION_PYTHON_REQUIRED', '持续配置检查需要Python3.11+标准库tomllib；请用已配置的新版Python。')
    contract, digest = read_json(path)
    require(contract.get('schema') == SCHEMA, 'SCHEMA_UNSUPPORTED', '持续合同schema缺失或不支持。')
    project = absolute_path(contract.get('project_root'), 'project_root')
    require(project.is_dir(), 'PROJECT_INVALID', 'project_root不是目录。')
    source = absolute_path(contract.get('task_source'), 'task_source')
    require(source.is_file() and source.is_relative_to(project), 'TASK_SOURCE_INVALID',
            '原任务源必须是控制项目内的现有文件；不得使用新造的第二任务源。')
    owner = contract.get('pm_thread_id')
    require(isinstance(owner, str) and bool(owner.strip()), 'PM_OWNER_REQUIRED', '缺少原PM聊天身份。')
    auth = contract.get('authorization_ref')
    require(isinstance(auth, str) and bool(auth.strip()), 'AUTHORIZATION_REF_REQUIRED',
            '缺少原任务源授权指针；检查通过不会产生新授权。')
    flow = contract.get('on_worker_return')
    require(isinstance(flow, list) and all(isinstance(x, str) for x in flow)
            and {'independent_review', 'task_writeback', 'repair_or_next_ready'} <= set(flow),
            'RETURN_FLOW_REQUIRED', '必须声明独立验收、原任务写回及原问题修复/合法下一项。')
    budget = contract.get('max_interval_seconds')
    require(type(budget) is int and 0 < budget <= 86400, 'INTERVAL_BUDGET_REQUIRED',
            '必须给出正整数监测周期上限（秒，最多一天）。')
    job_id = contract.get('automation_id')
    require(isinstance(job_id, str) and bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,100}', job_id)),
            'AUTOMATION_ID_INVALID', '需要精确现有automation id，不能是路径或自然语言名称。')
    root = automation_root.resolve(strict=True)
    job_path = (root / job_id / 'automation.toml').resolve(strict=True)
    require(job_path.is_relative_to(root), 'AUTOMATION_PATH_ESCAPE', 'automation文件越出指定宿主目录。')
    raw = read_bytes(job_path)
    job = tomllib.loads(raw.decode('utf-8'))
    require(job.get('id') == job_id and job.get('kind') == 'heartbeat', 'AUTOMATION_IDENTITY_MISMATCH',
            '只接受身份一致、唤醒原聊天的正式heartbeat；新任务cron不能替代。')
    require(job.get('status') == 'ACTIVE', 'AUTOMATION_NOT_ACTIVE', '原监测未启用；不能宣称已持续运行。')
    require(job.get('target_thread_id') == owner, 'PM_TARGET_MISMATCH',
            '监测未绑定原PM；宏观总控心跳不能直接替代项目PM接续。')
    prompt = job.get('prompt')
    # Exact textual delimiters reject arbitrary Unicode path suffixes too.
    source_pattern = r'(?:^|[\s`"\'(<])' + re.escape(str(source)) + r'(?=$|[\s`"\')>,。！？；，])'
    require(isinstance(prompt, str) and re.search(source_pattern, prompt), 'TASK_BINDING_MISSING',
            '正式监测内容未指向精确原任务源；不能只监测终端或汇总状态。')
    interval = interval_seconds(job.get('rrule'))
    require(interval <= budget, 'INTERVAL_TOO_LONG', '正式监测周期超过合同上限。')
    return {
        'ok': True, 'readiness': 'CONFIGURED_NOT_PROVEN_AUTONOMOUS',
        'schema': SCHEMA, 'contract_sha256': digest,
        'automation_id': job_id, 'automation_config_sha256': hashlib.sha256(raw).hexdigest(),
        'pm_thread_id': owner, 'task_source': str(source), 'interval_seconds': interval,
        'autonomous_verified': False, 'first_automatic_tick': 'NOT_VERIFIED',
        'automatic_review_and_continuation': 'NOT_VERIFIED',
        'boundary': '只读配置检查；人工催促/恢复、ACTIVE配置或一次触发均不证明自动业务闭环。',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    entry = parser.add_mutually_exclusive_group(required=True)
    entry.add_argument('--contract', type=Path)
    entry.add_argument('--wave-manifest', type=Path)
    parser.add_argument('--automation-root', type=Path,
                        help='读取指定已安装宿主配置根；测试可指向隔离fixture，不写配置。')
    args = parser.parse_args()
    try:
        path = args.contract
        if args.wave_manifest:
            manifest, _ = read_json(args.wave_manifest)
            policy = manifest.get('execution_policy', 'one_wave')
            require(policy in ('one_wave', 'continuous'), 'EXECUTION_POLICY_INVALID', '执行策略只能是one_wave或continuous。')
            if policy == 'one_wave':
                require('continuation_contract' not in manifest, 'UNUSED_CONTINUATION_CONTRACT',
                        '单波模式不能携带未消费的持续合同。')
                print(json.dumps({'ok': True, 'readiness': 'ONE_WAVE_ONLY', 'autonomous_verified': False}))
                return 0
            value = manifest.get('continuation_contract')
            path = absolute_path(value, 'continuation_contract')
        root = args.automation_root or Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'automations'
        result = check_contract(path, root)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Rejected as exc:
        print(json.dumps({'ok': False, 'code': exc.code, 'detail': exc.detail}, ensure_ascii=False))
    except (OSError, ValueError, TypeError, RecursionError):
        # Avoid reflecting arbitrary prompt/config/credential content in errors.
        print(json.dumps({'ok': False, 'code': 'CONTINUATION_INPUT_UNREADABLE',
                          'detail': '原合同/任务源/正式配置缺失、不可读或格式错误；保留现有资源，核原件。'}, ensure_ascii=False))
    return 64


if __name__ == '__main__':
    raise SystemExit(main())
