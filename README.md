# GogOS

A Claude Code-native, local-first personal operating system. Runs entirely as slash commands in your terminal.

## What it does

Turns Gmail, Google Calendar, local logs, and news feeds into structured daily briefs — locally, with no write-back without explicit approval.

**Core daily loop:**

1. Morning: `/start-day` — read-only email triage across all accounts, one merged panel. (Later: `/morning-brief` adds calendar, tasks, and news.)
2. File: `/email-apply [account]` — move triaged email into `GSD/*` folders, gated by your approval. `/email-undo` reverses the last batch.
3. Day: `/log [type] [text]` — fast activity, decision, and learning capture. *(stub — module not built yet)*
4. Evening: `/end-day` — review, carry forward, tomorrow seed list. *(stub — module not built yet)*

## Current state

Source of truth: [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md).

| Module | Status |
|---|---|
| FoundationOS (paths, setup check) | Done |
| Google Auth (multi-account OAuth) | Done |
| EmailOS (triage, gated write-back, undo, rules, auto-learn, `/start-day`, scheduler) | Done |
| CalendarOS (read-only brief) | Done |
| TaskOS | Next |
| BriefingOS, ActivityOS, ReflectionOS, NewsOS | Planned |

## Commands

| Command | What it does |
|---|---|
| `/setup-check` | Validate environment and required directories |
| `/account-add` `/account-list` `/account-alias` `/account-remove` `/account-migrate` | Manage alias→email account mappings |
| `/login-google [account]` `/logout-google [account]` | Per-account Google OAuth |
| `/start-day` | Read-only morning triage across all accounts, merged panel |
| `/email-report [account] [window]` | Read-only triage report for one account |
| `/email-apply [account]` | Move triaged email into GSD folders (two-step approval) |
| `/email-undo [account]` | Reverse the last applied batch |
| `/email-loop [account] [--yes]` | Drain an oversized inbox in batches |
| `/schedule-morning [HH:MM\|off\|status]` | Install/remove the daily read-only triage (launchd, ~08:00) |
| `/calendar-brief [account] [today\|tomorrow\|week]` | Read-only calendar brief |
| `/morning-brief` `/log` `/end-day` `/news-brief` | Stubs — backing modules not built yet |

## Setup

```bash
cp .env.example .env
# Edit .env with your Google credentials path
python -m gogos.system.setup_check
```

Register and authenticate your accounts (see [docs/GOOGLE_INTEGRATIONS.md](docs/GOOGLE_INTEGRATIONS.md) for the Google Cloud side):

```
/account-add personal you@gmail.com
/login-google personal
```

Then run your first triage and, when happy with the plan, file it:

```
/email-report personal
/email-apply personal
```

## Principles

- **Local-first.** Nothing leaves your machine unless you approve it.
- **Read-only first.** Write-back only after explicit two-step approval — and never delete.
- **Scripts normalise; models interpret.** Never raw API data → model.
- **Privacy gates live in code**, not prompts (e.g. no email body ever reaches storage).
- **Every report cites its source artefacts.**

## Docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — layers, storage, approval gates, model policy.
- [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) — what's done, what's next (source of truth).
- [docs/EMAILOS.md](docs/EMAILOS.md) — EmailOS end to end: pipeline, classifier, safety invariants, automation.
- [docs/CONNECTOR_CONTRACT.md](docs/CONNECTOR_CONTRACT.md) — the `fetch`/`normalise` seam every connector conforms to.
- [docs/GOOGLE_INTEGRATIONS.md](docs/GOOGLE_INTEGRATIONS.md) — OAuth setup, scopes, data schemas.
- [docs/SECURITY.md](docs/SECURITY.md) — gitignore, approval gates, OAuth safety.
- [docs/PRD.md](docs/PRD.md) — product vision and module roadmap.
