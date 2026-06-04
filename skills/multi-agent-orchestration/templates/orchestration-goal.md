# Orchestration Goal Contract

## Goal

- Goal ID: {{goal_id}}
- Objective: {{objective}}
- Task source: {{task_source}}
- Scope includes: {{included_task_types_or_sections}}
- Scope excludes: {{excluded_task_types_or_files}}
- Base ref: {{base_ref}}
- Started at: {{started_at}}

## Autonomy

- Mode: {{plan_only_auto_launch_auto_review_auto_merge}}
- Max waves: {{max_waves}}
- Max workers per wave: {{max_workers_per_wave}}
- Max total workers: {{max_total_workers}}
- Max runtime / budget: {{time_or_budget_limit}}
- Provider slots: {{provider_slot_plan}}
- Merge policy: {{merge_policy_summary}}

Autonomy modes:
- `plan-only`: PM may propose the next Wave but must ask before launch.
- `auto-launch`: PM may launch the next Wave after continue conditions pass.
- `auto-review`: PM may review worker results and send corrections without asking.
- `auto-merge`: PM may merge only when project `git-workflow` rules, CI/verification, PR review, and permissions all pass.

## Success Conditions

- {{success_condition_1}}
- {{success_condition_2}}
- {{success_condition_3}}

Default success condition:
- No executable pending task remains within scope, all launched workers are `merged` / `done-unmerged` / `blocked` / `deferred`, required trunk verification passes, and project docs/task source are updated.

## Continue Conditions

- Previous Wave has no unresolved failed worker, blocking PR conflict, base drift, trunk verification failure, or unclear task dependency.
- Completed tasks are marked in the task source before selecting the next Wave.
- Next tasks have clear allowed/forbidden files and independent verification.
- Provider/model performance is acceptable, or routing has been adjusted.
- The Goal limits above have not been reached.

## Stop Conditions

- Worker failed, blocked in a way that affects future work, or ignored PM correction twice.
- PR mergeability, CI, test result, base state, permission, or task source is unclear.
- Next work needs user product judgment, destructive operation, sensitive data handling, or unapproved dependency/runtime changes.
- Remaining tasks are too coupled for safe parallel execution.
- Any Goal limit is reached.

## Wave Loop State

| Wave | Started | Closed | Workers | Exit states | Continue decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| {{wave_id}} | {{started_at}} | {{closed_at}} | {{worker_count}} | {{exit_states}} | {{continue_stop}} | {{notes}} |

## Host Goal Prompt

Use this only in a host that supports slash goals. It wraps the PM loop; it does not replace worktree/session/checkpoint gates.

```text
/goal Continue this multi-agent orchestration goal until the success conditions or stop conditions in {{goal_contract_path}} are met.

Rules:
- Act as PM only. Do not implement business code in the main workspace.
- For each Wave, read the task source, choose only safe parallel tasks, start isolated workers, verify checkpoint files, review results, and merge only if the merge policy allows.
- After each Wave, write/update the Wave summary and decide continue vs stop from the Goal Contract.
- Stop immediately and report if any stop condition is hit.
```

## Final Summary

- Completed tasks: {{completed_tasks}}
- Deferred tasks: {{deferred_tasks}}
- Blocked tasks: {{blocked_tasks}}
- Waves run: {{waves_run}}
- Workers run: {{workers_run}}
- Provider/model findings: {{provider_model_findings}}
- Remaining user decisions: {{remaining_user_decisions}}
