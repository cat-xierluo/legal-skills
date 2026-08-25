#!/bin/sh
# Compatibility entrypoint for the Course Generator v2.8 verifier.

set -eu

if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ 缺少系统依赖: python3" >&2
  echo "   macOS: brew install python" >&2
  echo "   Linux: sudo apt-get install python3" >&2
  exit 2
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
  echo "❌ Python 版本过低；Course Generator 验收器需要 Python 3.10+" >&2
  exit 2
fi

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$SCRIPT_DIR/verify_course.py" "$@"
