#!/usr/bin/env python3
"""Classify a validated native MiniMax command without executing it."""
import argparse
import importlib.util
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location("worker_command", Path(__file__).with_name("validate-worker-command.py"))
worker_command = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker_command)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--command", required=True)
    parser.add_argument("--require-input", action="store_true")
    parser.add_argument("--supervised", type=int, choices=(0, 1), default=0)
    parser.add_argument("--task-id", default="")
    args = parser.parse_args()
    try:
        mode = worker_command.resolve_minimax_startup(args.command, require_input=args.require_input)
        if mode == "batch" and (args.supervised or args.task_id):
            raise worker_command.ValidationError("MINIMAX_BATCH_REQUIRES_TERMINAL_MANAGED")
        print(mode)
        return 0
    except worker_command.ValidationError as exc:
        print(f"MINIMAX_STARTUP_COMMAND_INVALID: {exc}", file=sys.stderr)
        return 64

if __name__ == "__main__":
    sys.exit(main())
