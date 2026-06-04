# GogOS Architecture

## Architecture style

GogOS uses a local-first modular pipeline architecture.

Scripts handle deterministic operations: OAuth, API fetches, normalisation, file writes, validation.

Claude Code commands orchestrate workflows.

Claude skills/subagents handle reasoning-heavy tasks: classification, prioritisation, summarisation, reflection, report writing.

## Layers

1. Interface layer: Claude Code slash commands. Later, local web/desktop dashboard.
2. Orchestration layer: `.claude/commands/*.md`.
3. Reasoning layer: `.claude/skills/*/SKILL.md`.
4. Integration layer: `.core/scripts/*/*.py`.
5. Data layer: `.core/storage/**`.
6. Configuration layer: `.core/config/**`.

## Storage conventions

Use dated directories where useful.

```text
.core/storage/gmail/personal/inbox/2026-06-04/latest-slim.json
.core/storage/gmail/personal/triage/2026-06-04/triage.json
.core/storage/calendar/personal/2026-06-04/events.json
.core/storage/reports/briefs/2026-06-04/morning-brief.md
.core/storage/logs/2026-06-04/activity.jsonl
```

## Data contracts

Every module should produce a normalised JSON output before any model-generated summary.

Bad pattern:

```text
API data -> Claude -> report
```

Better pattern:

```text
API data -> normalised JSON -> Claude -> structured summary -> report
```

## Error handling

Every script must:

- Exit non-zero on failure.
- Print clear errors to stderr.
- Never silently skip auth failures.
- Create parent directories if needed.
- Avoid overwriting raw data unless writing to a `latest` alias.
- Preserve dated artefacts.

## Approval gates

Read-only operations do not need approval after setup.

State-changing operations require approval:

- Gmail label application.
- Gmail archive/delete.
- Calendar event creation/update/deletion.
- Sending email.
- Posting content externally.

Approval file pattern:

```text
.core/storage/approvals/YYYY-MM-DD/{operation}.json
```

The system should generate a proposed action file first. A separate command applies it after explicit user confirmation.
