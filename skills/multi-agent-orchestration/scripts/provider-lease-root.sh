#!/usr/bin/env bash
# Derive the trusted provider-lease registry from repository facts, never from
# worker-editable METADATA.json.

provider_lease_root_for_project() {
  local project_dir="$1" git_common_dir
  git_common_dir=$(git -C "$project_dir" rev-parse --git-common-dir 2>/dev/null || true)
  if [ -z "$git_common_dir" ]; then
    printf '%s\n' "${TMPDIR:-/tmp}/multi-agent-orchestration/provider-leases/non-git"
    return 0
  fi
  case "$git_common_dir" in
    /*) ;;
    *) git_common_dir="$project_dir/$git_common_dir" ;;
  esac
  git_common_dir=$(cd "$git_common_dir" 2>/dev/null && pwd -P) || return 1
  printf '%s\n' "$git_common_dir/orchestration/provider-leases"
}
