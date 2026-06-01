# Email Trigger Protocol

Use this guide when an external agent can be triggered by email, such as Manus, AnyGen, Coze, or another hosted agent.

## Purpose

Email triggering lets the user start an agent task without opening that agent's web UI. The email must still bind the work back to the collaboration repository so the result is submitted as a branch and PR.

## Safety Rules

- Generate an email draft first; do not send automatically unless the user explicitly asks.
- Prefer binding to an existing Issue in the configured task source with `--issue`.
- Task folders are context packages only. They do not override the configured task source status.
- If the email is for a new topic, instruct the recipient agent to run duplicate search before creating a folder.
- Never include secret tokens in the email body.
- Require the agent to open a PR, not push directly to `main`.
- Treat the email recipient as an adapter with specific capabilities, not as a task status owner.

## Config

In local ignored `config/collab.yaml`:

```yaml
agents:
  manus:
    name: "Manus Bot"
    email: "manus@agents.local"
    github_user: "manus-bot"
    token_env: "MANUS_GITHUB_TOKEN"
    trigger_email: "manus-agent-inbox@example.com"
    reply_to: "collab-dispatch@example.com"
    from_alias: "Collab Dispatcher <collab-dispatch@example.com>"
    capabilities: [web_research, citation_collection]
    trigger_modes: [email_draft]
    handoff_format: pull_request
```

Do not confuse `trigger_email` with `email`, which is the Git author email written into commits.

## Compose A Trigger

Bind to an existing issue:

```bash
python3 scripts/email_trigger.py . \
  --agent manus \
  --issue 9 \
  --instruction "补充最新资料，并提交 PR"
```

Bind to an existing task folder:

```bash
python3 scripts/email_trigger.py . \
  --agent manus \
  --task-id 260517001 \
  --topic "法律AI产品生态调查" \
  --instruction "补充最新资料，并提交 PR"
```

Create a `.eml` draft:

```bash
python3 scripts/email_trigger.py . \
  --agent manus \
  --task-id 260517001 \
  --topic "法律AI产品生态调查" \
  --output /tmp/manus-task.eml
```

Override the recipient address:

```bash
python3 scripts/email_trigger.py . --agent anygen --to agent@example.com --topic "律师AI指南"
```

## Email Format

Subject:

```text
[Cross-Agent-Coordination][260517001][manus] 法律AI产品生态调查
```

Body includes:

- repository URL
- bound Issue number, or task ID and slug when using a task folder
- configured task-source fields and sections: target, acceptance criteria, dependencies, source material, handoff requirements
- README sections as supplemental context when a task folder exists
- assignment instructions
- duplicate search command
- branch name
- commit, push, and PR commands
- expected Git author and GitHub actor
- handoff requirements

## Expected Recipient Behavior

The receiving agent should:

1. Clone or pull the repository.
2. Run `scripts/find_task.py` before adding new material.
3. Treat the configured task source as the task status source.
4. Integrate into an existing task folder when matched; otherwise create one only when durable materials or handoff notes are needed.
5. Commit with its configured Agent ID.
6. Open a PR with `scripts/gh_git.py pr`.
7. Update the configured task source; leave a handoff note in the task README only when a task folder exists.

## Adapter Capability Routing

Use `agents.<id>.capabilities` to decide where the work goes:

| Capability | Typical Agent | Suitable work |
|------------|---------------|---------------|
| `web_research` | Manus / browser-capable hosted agent | complex online research, source collection, competitive scans |
| `citation_collection` | Manus / research agent | gathering links, quotes, evidence tables |
| `image_generation` | AnyGen / image agent | visual assets, image variants, illustration drafts |
| `browser_ops` | browser automation agent | website interaction, form workflows, screenshot evidence |

The adapter must return results through a branch, PR, or durable handoff note. Do not accept a chat-only result as complete unless the user explicitly asked for a one-off answer.
