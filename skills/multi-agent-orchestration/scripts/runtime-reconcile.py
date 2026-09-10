#!/usr/bin/env python3
"""只读验证捕获证据，生成 runtime/resource 观察与确定性结算收据。"""
import argparse
import json
from pathlib import Path
import runtime_settlement as runtime


class Parser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps({'ok': False, 'complete': False, 'settlement_state': 'UNSETTLED', 'lifecycle_mutations': False,
                          'errors': [{'code': 'INVALID_ARGUMENT', 'message': message}]}, ensure_ascii=False))
        raise SystemExit(2)


def main():
    parser = Parser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name, flag in (('observe', 'request'), ('reconcile', 'snapshot'), ('verify', 'receipt')):
        command = sub.add_parser(name)
        command.add_argument('--' + flag, required=True, type=Path)
        if name != 'verify':
            command.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'observe':
            result = runtime.observe(args.request, args.output)
        elif args.command == 'reconcile':
            result = runtime.reconcile(args.snapshot, args.output)
        else:
            result = runtime.verify(args.receipt)
        code = 0
    except (runtime.SettlementError, ValueError, OSError, TypeError, KeyError, RecursionError) as exc:
        result = {'ok': False, 'complete': False, 'settlement_state': 'UNSETTLED', 'lifecycle_mutations': False,
                  'errors': [{'code': getattr(exc, 'code', 'INVALID_EVIDENCE'), 'message': str(exc)}]}
        code = 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
