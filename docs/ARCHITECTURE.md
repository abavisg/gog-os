# GogOS Architecture

## Architecture style

Local-first modular pipeline. Scripts handle deterministic operations; Claude skills handle reasoning.

```
API → normalised JSON → Claude skill → Markdown report
```

Never pass raw API data directly to a model.

## Layers

1. **Interface:** Claude Code slash commands.
2. **Orchestration:** `.claude/commands/*.md`
3. **Reasoning:** `.claude/skills/*/SKILL.md`
4. **Scripts:** `gogos/**/*.py`
5. **Storage:** `.core/storage/**`
6. **Config:** `.core/config/**`

## Storage conventions

Dated directories. Always write a dated file and a `latest` alias.

```
.core/storage/gmail/personal/inbox/2026-06-04/latest-slim.json
.core/storage/gmail/personal/triage/2026-06-04/triage.json
.core/storage/calendar/personal/2026-06-04/events.json
.core/storage/reports/briefs/2026-06-04/morning-brief.md
.core/storage/logs/2026-06-04/activity.jsonl
```

Store timestamps as UTC internally. Render local (`Europe/London`) only at report time.

## Error handling

Every script must exit non-zero on failure, print errors to stderr, create parent directories, and never silently skip auth failures.

## Approval gates

Read-only operations need no approval after setup.

State-changing operations (Gmail labels/archive/delete, Calendar write, sending email, posting content) require a two-step flow:

1. Generate a proposed action file under `.core/storage/approvals/YYYY-MM-DD/{operation}.json`.
2. Apply only after explicit user confirmation.

## Model selection

| Task | Model |
|---|---|
| Architecture review / system critique | Opus 4.8 |
| Normal implementation and reasoning | Sonnet 4.6 |
| Report formatting / simple summaries | Haiku 4.5 |

Default to Sonnet for building and Haiku for simple runtime rendering. Use Opus only when the decision has architectural consequences.
