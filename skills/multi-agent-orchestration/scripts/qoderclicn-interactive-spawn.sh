#!/usr/bin/env bash
# Legacy QoderWork helper retained only to return an actionable migration error.
# Do not create a terminal through this obsolete, ungated entry.
set -euo pipefail
printf '%s\n' 'ERROR: QoderWork helper is retired. Use render-runtime-profile.sh --backend qoder-cn and the gated spawn-worker.sh; see references/26-optional-cli-backends.md.' >&2
exit 64
