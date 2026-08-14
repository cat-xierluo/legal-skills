#!/usr/bin/env bash
# spawn-worker-metadata.sh — Session Context metadata writer for spawn-worker.sh.
# This file is sourced after spawn-worker.sh initializes runtime and authority globals.

write_metadata() {
  local enforcement_source worker_mirror_authoritative
  created_at=$(date -u "+%Y-%m-%dT%H:%M:%SZ")
  if [ "${#VERIFY_COMMANDS[@]}" -gt 0 ]; then
    verify_json=$(printf '%s\n' "${VERIFY_COMMANDS[@]}" | jq -R . | jq -s .)
  else
    verify_json="[]"
  fi

  echo "SPAWN_WORKER_METADATA: $METADATA_FILE"
  if [ "$DRY_RUN" -eq 1 ]; then
    return 0
  fi

  # v2.0：写 isolation_mode（worktree 或 lightweight）+ lightweight_auto 标记
  if [ "$LIGHTWEIGHT_MODE" -eq 1 ]; then
    isolation_mode_value="lightweight"
  else
    isolation_mode_value="worktree"
  fi
  if [ "$INSTALL_GUARD_MODE" = "hook" ]; then
    enforcement_source="pretool_hook_settings_wired_process_snapshot_runtime_unproven"
    worker_mirror_authoritative=false
  else
    enforcement_source="prompt_only_no_mechanical_enforcement"
    worker_mirror_authoritative=false
  fi

  jq -n \
    --arg schema "multi-agent-orchestration.worktree-metadata.v1" \
    --arg created_at "$created_at" \
    --arg project "$PROJECT_DIR" \
    --arg worktree "$WORKTREE" \
    --arg branch "$BRANCH" \
    --arg base_ref "$BASE_REF" \
    --arg base_sha "$BASE_SHA" \
    --arg session "$SESSION" \
    --arg session_context "$SESSION_CONTEXT" \
    --arg command "$COMMAND" \
    --arg worker_backend "$WORKER_BACKEND" \
    --arg pm_harness "$PM_HARNESS" \
    --arg pm_harness_source "$PM_HARNESS_SOURCE" \
    --argjson pm_harness_chain "$PM_HARNESS_CHAIN_JSON" \
    --argjson pm_allowed_worker_backends "$(printf '%s\n' $PM_ALLOWED_WORKER_BACKENDS | jq -R . | jq -s .)" \
    --arg worker_backend_canonical "$WORKER_BACKEND_CANONICAL" \
    --arg worker_command_sha256 "$WORKER_COMMAND_SHA256" \
    --arg runtime_profile "$RUNTIME_PROFILE" \
    --arg api_provider "$API_PROVIDER" \
    --arg model "$MODEL" \
    --arg provider_slot "$PROVIDER_SLOT" \
    --arg provider_lease_file "$PROVIDER_LEASE_FILE" \
    --arg provider_lease_root "$PROVIDER_LEASE_ROOT" \
    --arg provider_lease_limit "$PROVIDER_LEASE_LIMIT" \
    --arg provider_lease_key "$PROVIDER_LEASE_KEY" \
    --arg env_isolation "$ENV_ISOLATION" \
    --arg wave_id "$WAVE_ID" \
    --arg wave_worker_id "$WAVE_WORKER_ID" \
    --arg isolation_mode "$isolation_mode_value" \
    --argjson lightweight_auto "$LIGHTWEIGHT_AUTO" \
    --argjson verification_commands "$verify_json" \
    --argjson add_dirs "$(array_to_json "${ADD_DIRS[@]}")" \
    --argjson allow_paths "$(array_to_json "${ALLOW_PATHS[@]}")" \
    --arg install_guard_mode "$INSTALL_GUARD_MODE" \
    --arg install_authorization_file "$INSTALL_AUTH_FILE" \
    --arg install_authorization_source "$INSTALL_AUTHORIZATION_SOURCE" \
    --arg install_guard_degradation_source "$INSTALL_GUARD_DEGRADATION_SOURCE" \
    --arg git_expected_name "$GIT_EXPECTED_NAME" \
    --arg git_expected_email "$GIT_EXPECTED_EMAIL" \
    --arg git_integration_base "$GIT_INTEGRATION_BASE" \
    --arg safe_push_command "$SAFE_PUSH_COMMAND" \
    --arg authority_receipt_file "$AUTHORITY_RECEIPT_FILE" \
    --arg authority_receipt_sha256 "$AUTHORITY_RECEIPT_SHA256" \
    --arg guard_attestation_file "$GUARD_ATTESTATION_FILE" \
    --arg enforcement_source "$enforcement_source" \
    --argjson worker_mirror_authoritative "$worker_mirror_authoritative" \
    --argjson authorized_install_commands "$(array_to_json "${AUTHORIZED_INSTALL_COMMANDS[@]}")" \
    --argjson allowed_shell_commands "$(array_to_json "${EFFECTIVE_ALLOWED_SHELL_COMMANDS[@]}" | jq 'unique')" \
    --arg orca_mode "${ORCA_MODE:-force_tmux}" \
    --arg orca_worktree_id "${ORCA_WORKTREE_ID:-}" \
    --arg orca_worktree_path "${ORCA_WORKTREE_PATH:-}" \
    --arg orca_terminal_handle "${ORCA_TERMINAL_HANDLE:-}" \
    --arg orca_tui_ready_method "${ORCA_TUI_READY_METHOD:-orca_terminal_wait_tui-idle}" \
    --arg orca_app_version "${ORCA_APP_VERSION:-}" \
    --argjson orca_capabilities "${ORCA_CAPABILITIES_JSON:-[]}" \
    '{
      schema: $schema,
      created_at: $created_at,
      project: $project,
      worktree: $worktree,
      branch: $branch,
      base_ref: $base_ref,
      base_sha: $base_sha,
      isolation: {
        mode: $isolation_mode,
        lightweight_auto: $lightweight_auto
      },
      session: {
        id: $session,
        context: $session_context,
        orca: {
          mode: $orca_mode,
          worktree_id: $orca_worktree_id,
          worktree_path: $orca_worktree_path,
          terminal_handle: $orca_terminal_handle,
          tui_ready_method: $orca_tui_ready_method,
          app_version: $orca_app_version,
          capabilities: $orca_capabilities
        }
      },
      runtime: {
        harness_authority: {
          pm_harness: $pm_harness,
          evidence_source: $pm_harness_source,
          ancestry: $pm_harness_chain,
          allowed_worker_backends: $pm_allowed_worker_backends,
          worker_backend: $worker_backend_canonical
        },
        worker_backend: $worker_backend,
        runtime_profile: $runtime_profile,
        api_provider: $api_provider,
        model: $model,
        provider_slot: $provider_slot,
        provider_lease: {
          file: $provider_lease_file,
          root: $provider_lease_root,
          provider: $provider_lease_key,
          max_concurrency: ($provider_lease_limit | if . == "" then null else tonumber end)
        },
        env_isolation: $env_isolation,
        command: $command,
        command_sha256: $worker_command_sha256
      },
      wave: {
        id: $wave_id,
        worker_id: $wave_worker_id
      },
      verification: {
        commands: $verification_commands
      },
      execution_authority: {
        environment_mutation_policy: "deny_by_default",
        install_guard_mode: $install_guard_mode,
        install_authorization_file: $install_authorization_file,
        install_authorization_source: $install_authorization_source,
        authorized_install_commands: $authorized_install_commands,
        allowed_shell_commands: $allowed_shell_commands,
        degradation_source: $install_guard_degradation_source,
        enforcement_source: $enforcement_source,
        authority_receipt_file: $authority_receipt_file,
        authority_receipt_sha256: $authority_receipt_sha256,
        guard_attestation_file: $guard_attestation_file,
        worker_mirror_authoritative: $worker_mirror_authoritative,
        git_identity: {
          expected_name: $git_expected_name,
          expected_email: $git_expected_email,
          integration_base: $git_integration_base,
          safe_push_command: $safe_push_command,
          raw_git_push_allowed: false,
          commit_environment_bound: ($git_expected_name != "" and $git_expected_email != "")
        }
      },
      add_dirs: $add_dirs,
      allow_paths: $allow_paths,
      pr: {
        number: null,
        url: "",
        state: ""
      }
    }' > "$METADATA_FILE"
}
