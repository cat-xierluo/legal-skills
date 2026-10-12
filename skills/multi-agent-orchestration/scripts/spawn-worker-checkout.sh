#!/usr/bin/env bash
# Only read-only planning before Orca auto-registration/lease/resource effects.
spawn_worker_checkout_preflight() {
  [ "$LIGHTWEIGHT_MODE" -eq 0 ] && [ "$PROJECT_IS_GIT" -eq 1 ] || return 0
  local transport="orca" checkout_base="$BASE_REF"
  local borrowed_tree=""
  [ "$NO_ORCA_MODE" -eq 0 ] || transport="git"
  if [ -n "$BORROW_EXISTING_WORKTREE" ]; then
    checkout_base=$(jq -er '.head' "$BORROW_EXISTING_WORKTREE") || return 64
    borrowed_tree=$(jq -er '.worktree' "$BORROW_EXISTING_WORKTREE") || return 64
  elif git -C "$PROJECT_DIR" show-ref --verify --quiet "refs/heads/$BRANCH"; then
    checkout_base="$BRANCH"
  fi
  local args=(--repo "$PROJECT_DIR" --base "$checkout_base" --transport "$transport" --budget-mib "$CHECKOUT_BUDGET_MIB") s
  if [ "${#CHECKOUT_SCOPES[@]}" -gt 0 ]; then
    for s in "${CHECKOUT_SCOPES[@]}"; do args+=(--scope "$s"); done
  fi
  if [ "${#ALLOW_PATHS[@]}" -gt 0 ]; then
    for s in "${ALLOW_PATHS[@]}"; do args+=(--allow-path "$s"); done
  fi
  [ -z "$CHECKOUT_FULL_REASON" ] || args+=(--full-reason "$CHECKOUT_FULL_REASON")
  [ -z "$CHECKOUT_FULL_SOURCE" ] || args+=(--full-source "$CHECKOUT_FULL_SOURCE")
  [ -z "$borrowed_tree" ] || args+=(--borrowed "$borrowed_tree")
  CHECKOUT_PLAN_JSON=$(python3 "$SCRIPT_DIR/checkout-plan.py" "${args[@]}") || return $?
  CHECKOUT_MODE=$(printf '%s' "$CHECKOUT_PLAN_JSON" | jq -er '.mode') || return 64
  echo "SPAWN_WORKER_CHECKOUT_PLAN: $CHECKOUT_PLAN_JSON"
}

spawn_worker_create_sparse() {
  local creator="$SCRIPT_DIR/../../git-workflow/scripts/scoped-worktree.py"
  [ -f "$creator" ] || { echo "CHECKOUT_GIT_WORKFLOW_CREATOR_MISSING" >&2; return 64; }
  local oid args=(--repo "$PROJECT_DIR" --path "$WORKTREE" --branch "$BRANCH") s
  oid=$(printf '%s' "$CHECKOUT_PLAN_JSON" | jq -er '.base_oid') || return 64
  args+=(--base "$oid")
  while IFS= read -r s; do args+=(--scope "$s"); done < <(printf '%s' "$CHECKOUT_PLAN_JSON" | jq -r '.scopes[]')
  git -C "$PROJECT_DIR" show-ref --verify --quiet "refs/heads/$BRANCH" && args+=(--existing-branch)
  run python3 "$creator" "${args[@]}"
}

spawn_worker_checkout_verify() {
  [ "$LIGHTWEIGHT_MODE" -eq 0 ] || return 0
  [ "$DRY_RUN" -eq 0 ] || return 0
  local expected_oid actual_oid expected_scopes actual_scopes
  expected_oid=$(printf '%s' "$CHECKOUT_PLAN_JSON" | jq -er '.base_oid') || return 64
  actual_oid=$(git -C "$WORKTREE" rev-parse HEAD) || return 64
  [ "$actual_oid" = "$expected_oid" ] || { echo "CHECKOUT_HEAD_DRIFT" >&2; return 64; }
  [ "$CHECKOUT_MODE" = "sparse" ] || return 0
  expected_scopes=$(printf '%s' "$CHECKOUT_PLAN_JSON" | jq -r '.scopes[]' | LC_ALL=C sort)
  actual_scopes=$(git -c core.quotePath=false -C "$WORKTREE" sparse-checkout list | LC_ALL=C sort) || return 64
  if [ -z "$BORROW_EXISTING_WORKTREE" ] && [ "$actual_scopes" != "$expected_scopes" ]; then
    echo "CHECKOUT_ACTUAL_SCOPE_MISMATCH" >&2; return 64
  fi
  # The ordinary isolation gate still verifies branch/common-dir identity next.
}
