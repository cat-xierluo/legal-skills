# Worker Prompt Template

> 使用方式：PM 启动 worker 前复制本模板，替换 `{{...}}`。窄范围任务保留简洁版本，不要把无关背景塞进 prompt。

## Bootstrap-Only Prompt

```text
你是并行执行 worker。先不要读任务文件，不要实现代码。

Context:
- PM Host: {{pm_host}}
- Worker Backend: {{worker_backend}}
- Branch: {{branch_name}}
- Expected Base Ref: {{base_ref}}
- Worktree: {{worktree_path}}
- Session ID: {{session_id}}
- Session Context: {{session_context_path}}
- Wave ID: {{wave_id}}
- Wave Worker ID: {{wave_worker_id}}
- Runtime Profile: {{runtime_profile}}
- API Provider: {{api_provider}}
- Model: {{model_name}}
- Provider Slot: {{provider_slot}}
- Worker Type: {{worker_type}}

Isolation Gate:
- Before reading task files or implementing anything, confirm `pwd` is `{{worktree_path}}` and `git branch --show-current` is `{{branch_name}}`.
- If cwd, branch, or worktree isolation is wrong, write `{{session_context_path}}/STATUS.json` with `status=blocked`, `phase=bootstrap`, the mismatch details, and stop. Do not implement in the PM/main workspace.

Task:
1. 只创建 `{{session_context_path}}/STATUS.json`。
2. 参考 skill 模板 `templates/checkpoint-status.json`。
3. 写入当前 cwd、当前 branch、worktree、wave 信息、worker type、provider/model/slot、isolation gate 结果、可用 CLI 路径和版本、runtime profile、允许/禁止文件范围。
4. 不要写 token、完整环境变量、settings 内容或长日志。

Finish:
- STATUS 写完后回复一行：`bootstrap checkpoint written`。
```

## Full Worker Prompt

```text
你是并行执行 worker，不是唯一协作者。不要回退或覆盖其他人的改动。

Context:
- PM Host: {{pm_host}}
- Worker Backend: {{worker_backend}}
- Branch: {{branch_name}}
- Base Ref: {{base_ref}}
- Worktree: {{worktree_path}}
- Session ID: {{session_id}}
- Session Context: {{session_context_path}}
- Wave ID: {{wave_id}}
- Wave Worker ID: {{wave_worker_id}}
- Wave Role: {{wave_role}}
- Wave Exit Criteria: {{wave_exit_criteria}}
- Runtime Profile: {{runtime_profile}}
- API Provider: {{api_provider}}
- Model: {{model_name}}
- Provider Slot: {{provider_slot}}
- Worker Type: {{worker_type_ui_wiring_contract_extension_tauri_command_docs_research_custom}}
- Effort: {{effort_low_medium_high}}

Isolation Gate:
- Before reading task files or implementing anything, confirm `pwd` is `{{worktree_path}}` and `git branch --show-current` is `{{branch_name}}`.
- Update `STATUS.json` with the isolation gate result.
- If cwd, branch, or worktree isolation is wrong, set `status=blocked`, `phase=bootstrap`, `pm_action_required=true`, describe the mismatch, and stop. Do not implement in the PM/main workspace.

Background:
- Task Source: {{task_source}}
- Goal: {{goal}}
- Why now: {{why_this_task_matters}}
- Relevant inputs: {{inputs}}

Mission:
在限定范围内完成可 review 的最小闭环。PM 不会默认代你实现；你负责在本 worktree 内完成实现、验证、提交和 PR，PM 负责巡检、纠偏、review 和收口。

Scope:
- Allowed files: {{allowed_files}}
- Forbidden files: {{forbidden_files}}
- Shared dependencies / lockfiles / runtime config are forbidden unless the task explicitly allows them.
- Risk class: {{low_medium_high}}
- Shared-risk notes: {{shared_risk_notes}}

Expected Deliverables:
- Code/docs changes: {{deliverables}}
- Checkpoint files:
  - `{{session_context_path}}/STATUS.json`
  - `{{session_context_path}}/RESULT.md`
  - `{{session_context_path}}/PATCH_SUMMARY.md`
- Git/PR: commit, push, create PR when the task is complete.

Process:
1. Bootstrap: run the Isolation Gate and create or update `STATUS.json` before deep work.
2. Implement: stay inside Scope; do not expand the task.
3. Checkpoint: refresh `updated_at`, `phase`, `current_action`, `next_action`, tests, git fields and issues every 10-15 minutes or on phase changes.
4. Verify: run the commands below and record results.
5. Finish: write RESULT/PATCH_SUMMARY, commit, push and create PR. Confirm PR diff does not contain Session Context files.

Worker Type Rules:
- `ui-wiring`: no new dependencies; all listed frontend verification commands must pass.
- `contract-extension`: dependency, lockfile or shared contract changes are allowed only if listed in Scope; explain the shared impact in RESULT.
- `tauri-command`: record local native dependency limits. If `cargo build` needs a missing system library, run and record `cargo check --manifest-path src-tauri/Cargo.toml --offline` as the floor instead of treating missing native libs as implementation failure.
- `docs/research`: avoid DEC/TASK numbering races; see Decision ID Rule.

Commit Cadence:
- For long tasks, create a coherent checkpoint commit every 30-60 minutes or whenever a verified phase is complete.
- Do not wait until a very large final diff if smaller reviewable commits are available.
- Follow the project `git-workflow` / `git-batch-commit` rules for commit format; this prompt does not redefine them.
- After each commit, refresh `STATUS.json.git.last_commit_sha` and the current phase/action fields.

Decision ID Rule:
- If editing project decision logs, first grep existing IDs such as `^## DEC-` or `^### [DEC-`.
- Pick the next unused ID at write time. If another worker races and uses the same ID, renumber your entry during rebase instead of overwriting theirs.

Verification:
- {{verify_command_1}}
- {{verify_command_2}}
- {{verify_command_3}}

Verification Floor:
- For frontend/UI workers, run typecheck, tests, and build unless PM explicitly narrows verification.
- For Tauri/Rust workers, run `cargo check --manifest-path src-tauri/Cargo.toml --offline` as the required Rust floor; run `cargo build` only when local native dependencies are available.
- Record every skipped command with the exact reason in RESULT.md.

Autonomy:
- Do not wait for PM after partial completion.
- Continue until verified PR unless `needs_input=true`, `pm_action_required=true`, or the task is genuinely blocked.
- If blocked, update STATUS with blocker, issues, current_action and next_action.
- Do not ask PM to implement your assigned scope directly; ask only for missing input, permission, or correction.

Out of Scope:
- Do not modify forbidden files.
- Do not fix unrelated environment, dependency, CI or package issues.
- Do not submit checkpoint files, tokens, settings files, or local runtime state to Git/PR.

PM Correction:
If PM sends a correction, stop the deviating action immediately, update STATUS, apply the correction in this worktree, rerun relevant verification, then continue to Finish. Do not treat correction as a request to stop unless PM explicitly says stop.
```
