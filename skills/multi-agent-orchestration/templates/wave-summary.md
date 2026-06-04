# Wave Summary

## Wave

- Wave ID: {{wave_id}}
- Base ref: {{base_ref}}
- Goal: {{wave_goal}}
- Started at: {{started_at}}
- Closed at: {{closed_at}}

## Workers

| Worker | Branch | Type | Provider / Model | Slot | Exit state | PR | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| {{wave_worker_id}} | {{branch_name}} | {{worker_type}} | {{api_provider}} / {{model_name}} | {{provider_slot}} | {{merged_blocked_deferred_restarted}} | {{pr_url}} | {{notes}} |

Exit states: `merged`, `done-unmerged`, `blocked`, `deferred`, `restarted`.

## Provider And Model Review

| Worker | Isolation | STATUS | Commit cadence | Scope | Verification | Review fixes | Quality notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| {{wave_worker_id}} | {{ok_or_issue}} | {{ok_or_issue}} | {{ok_or_issue}} | {{ok_or_issue}} | {{ok_or_issue}} | {{count}} | {{notes}} |

## Decisions

- Parallelism: {{keep_increase_reduce_next_wave_worker_count}}
- Provider routing: {{provider_routing_changes}}
- Deferred items: {{deferred_items}}
- Next wave entry criteria: {{next_wave_entry_criteria}}
