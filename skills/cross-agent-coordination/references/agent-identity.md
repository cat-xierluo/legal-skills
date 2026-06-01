# Agent Identity And Git Attribution

Use this guide when commits and PRs need to show which agent did the work.

## Two Identities

| Layer | Controlled by | What it proves |
|---|---|---|
| Commit author | `git config user.name` and `git config user.email` | Who authored the commit content |
| GitHub actor / PR opener | The token or GitHub App used for API/push/PR actions | Which GitHub account or app performed the platform action |

Scripts can reliably set the commit author for each agent. The PR opener cannot be faked with Git config. If every PR is created with the user's PAT, GitHub will show the user as the PR actor even when commits are authored by Manus, AnyGen, OpenClaw, Codex, Claude Code, or Coze.

To make PR actors differ, provide a separate PAT or GitHub App token for that agent.

## Config Format

In local ignored `config/collab.yaml`:

```yaml
project:
  default_agent: codex

agents:
  codex:
    name: "Codex"
    email: "codex@agents.local"
    github_user: "codex-bot"
    token_env: "CODEX_GITHUB_TOKEN"
  manus:
    name: "Manus Bot"
    email: "manus@agents.local"
    github_user: "manus-bot"
    token_env: "MANUS_GITHUB_TOKEN"
    trigger_email: "manus-agent-inbox@example.com"
    reply_to: "collab-dispatch@example.com"
```

Fields:

- `name`: Git author name.
- `email`: Git author email. Use a unique stable email per agent.
- `github_user`: Expected GitHub actor. Used for PR body and audit notes.
- `token_env`: Environment variable that stores the agent-specific token.
- `trigger_email`: Dedicated mailbox or inbound email address used to trigger this agent.
- `reply_to`: Optional mailbox for agent responses/status updates.

Do not use `trigger_email` as the Git author email unless that is intentionally the same identity. `email` controls commit attribution; `trigger_email` controls where task instructions are sent.

## Token Priority

Scripts resolve tokens in this order:

1. Agent-specific `token_env`, such as `MANUS_GITHUB_TOKEN`.
2. Generic `GITHUB_TOKEN`.
3. Local ignored `github.token` in `config/collab.yaml`.

## Current Agent Priority

Scripts resolve the current agent in this order:

1. Explicit `--agent`.
2. `AGENT_ID` environment variable.
3. `project.default_agent`.
4. `agent.current` if present.
5. Built-in fallback `openclaw`.

## Recommended Agent IDs

| Agent ID | Typical name |
|---|---|
| `manus` | Manus Bot |
| `anygen` | AnyGen Bot |
| `openclaw` | OpenClaw |
| `codex` | Codex |
| `claude_code` | Claude Code |
| `coze` | Coze |
| `hermes` | Hermes |

## Workflow

Create a branch or commit as a specific agent:

```bash
python3 scripts/gh_git.py branch --dest . --agent manus --name agent/manus/260517001-研究-示例任务
python3 scripts/gh_git.py commit --dest . --agent manus --message "docs: update handoff"
python3 scripts/gh_git.py push --dest . --agent manus
python3 scripts/gh_git.py pr --dest . --agent manus --title "docs: Manus handoff update"
```

Create a task assigned to a specific agent:

```bash
python3 scripts/task_scaffold.py create --root . --assignee manus --type 研究 --topic "示例任务" --auto-commit
```

## Audit Rule

For traceability, every task README should include:

- `assignee`: stable agent ID responsible for the task.
- PR body: `Agent ID`, `Git Author`, and `Expected GitHub Actor`.

The `pr` command always writes these fields into the PR body so attribution remains visible even when the platform actor is a shared token:

```markdown
## Agent Attribution

- Agent ID: manus
- Git Author: Manus Bot <manus@agents.local>
- Expected GitHub Actor: manus-bot
```
