# GogOS

A Claude Code-native personal AI operating system. Runs entirely as slash commands in your terminal.

## What it does

Turns Gmail, Google Calendar, local logs, and news feeds into structured daily briefs — locally, with no write-back without explicit approval.

**Core daily loop:**

1. Morning: `/morning-brief` — email + calendar + tasks + news in one brief.
2. Day: `/log [type] [text]` — fast activity, decision, and learning capture.
3. Evening: `/end-day` — review, carry forward, tomorrow seed list.

## Current state

| Module | Status |
|---|---|
| FoundationOS | Done |
| Google Auth (personal + work) | Done |
| EmailOS (read-only triage) | Done |
| CalendarOS (read-only brief) | Done |
| TaskOS | Next |
| BriefingOS | Planned |
| ActivityOS | Planned |
| ReflectionOS | Planned |
| NewsOS | Planned |

## Setup

```bash
cp .env.example .env
# Edit .env with your Google credentials path and account names
python -m gogos.system.setup_check
```

Then authenticate:

```
/login-google abavisg     # personal Gmail (default)
/login-google karehero    # work
```

Run your first email triage, then move emails into your GSD folders:

```
/email-report abavisg
/email-apply abavisg
```

## Principles

- Local-first. Nothing leaves your machine unless you approve it.
- Read-only first. Write-back only after explicit confirmation.
- Scripts normalise; models interpret. Never raw API → model.
- Every report cites its source artefacts.

## Docs

- `docs/PRD.md` — what this is and why.
- `docs/ARCHITECTURE.md` — layers, storage, model selection.
- `docs/IMPLEMENTATION_PLAN.md` — what's done, what's next.
- `docs/GOOGLE_INTEGRATIONS.md` — OAuth setup and data schemas.
- `docs/SECURITY.md` — gitignore, approval gates, OAuth safety.
