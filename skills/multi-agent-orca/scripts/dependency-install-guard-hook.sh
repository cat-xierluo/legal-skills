#!/usr/bin/env bash
# codebuddy/qoder hook stdin 兼容 wrapper；Claude Code 同样可使用。
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
input=$(cat)
if [ -n "${WORKER_GUARD_ATTESTATION_FILE:-}" ] && [ ! -e "$WORKER_GUARD_ATTESTATION_FILE" ]; then
  python3 - "$WORKER_GUARD_ATTESTATION_FILE" "${WORKER_GUARD_BACKEND:-}" \
    "${WORKER_AUTHORITY_RECEIPT_FILE:-}" <<'PY' || true
import datetime, json, os, sys
path, backend, receipt = sys.argv[1:]
os.makedirs(os.path.dirname(path), exist_ok=True)
payload = {
    "schema": "multi-agent-orchestration.hook-attestation.v1",
    "attested_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "backend": backend,
    "authority_receipt_file": receipt,
    "hook_pid": os.getppid(),
}
try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    pass
else:
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
        fh.write("\n")
PY
fi
printf '%s' "$input" | python3 "$SCRIPT_DIR/dependency-install-guard.py"
