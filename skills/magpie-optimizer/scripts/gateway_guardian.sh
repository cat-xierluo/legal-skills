#!/bin/bash
# Read-only gateway inspection. Legacy action names remain accepted.
# No signals, service restarts, cache removal, or log truncation.
# DRY_RUN is accepted by older callers but never enables mutation.
set -uo pipefail

report_hosts() {
  local limit="${MAGPIE_RSS_LIMIT_MB:-4096}" data
  case "$limit" in ''|*[!0-9]*) echo 'Invalid MAGPIE_RSS_LIMIT_MB' >&2; return 2 ;; esac
  # ps comm avoids exposing credentials passed as command arguments.
  # These are candidates only: neither a name nor PPID=1 proves ownership.
  if ! data=$(ps -axo pid=,ppid=,rss=,comm= | awk -v limit="$limit" '
    /[m]agpie-bun|[m]agpie\/bun/ {
      rss=int($3/1024);
      printf "HOST_CANDIDATE pid=%s ppid=%s rss_mb=%d\n", $1,$2,rss;
      if (rss>limit) printf "GUARD_REVIEW_REQUIRED pid=%s limit_mb=%s\n",$1,limit;
    }'); then
    echo 'ERROR: host scan incomplete' >&2
    return 1
  fi
  [ -z "$data" ] || printf '%s\n' "$data"
  return 0
}

report_reap() {
  local data
  if ! data=$(ps -axo pid=,ppid=,stat=,comm= | awk '
    $3 ~ /^Z/ { zombies++ }
    $2==1 && /[m]agpie-bun|[m]agpie\/bun/ {
      printf "ORPHAN_REVIEW_REQUIRED pid=%s (ownership and IPC not verified)\n",$1
    }
    END { printf "ZOMBIES count=%d (parent must reap them)\n",zombies }'); then
    echo 'ERROR: process scan incomplete' >&2
    return 1
  fi
  printf '%s\n' "$data"
}

report_cache() {
  local dir="$HOME/.cache/magpie/calls-v15" count
  if [ -d "$dir" ]; then
    # Count NUL separators: no filenames printed, no process fork per file.
    if ! count=$(find "$dir" -type f -mtime +7 -print0 | tr -cd '\000' | wc -c | tr -d ' '); then
      echo 'ERROR: cache scan incomplete' >&2
      return 1
    fi
    echo "CACHE_REPORT older_than_7_days=$count action=none"
  else
    echo 'CACHE_REPORT directory_absent action=none'
  fi
}

report_status() {
  local failed=0
  echo 'READ_ONLY: no processes, services, configuration or caches will be changed'
  uptime || failed=1
  sysctl vm.swapusage || failed=1
  report_hosts || failed=1
  report_reap || failed=1
  return "$failed"
}

case "${1:-status}" in
  status) report_status ;;
  reap) report_reap ;;
  guard) report_hosts ;;
  cache) report_cache ;;
  all) failed=0; report_status || failed=1; report_cache || failed=1; exit "$failed" ;;
  *) echo 'Usage: gateway_guardian.sh {status|reap|guard|cache|all}' >&2; exit 2 ;;
esac
