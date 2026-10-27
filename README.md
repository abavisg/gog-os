# GogOS

A Claude Code-native, local-first personal operating system. It runs as slash
commands in your terminal and keeps its memory as plain files in this repo.

## What it is

GogOS works like an executive assistant across six areas of life. It reads your
mail and calendar, takes what you log by hand, and keeps a compounding memory: a
wiki of facts, registers of things with a lifecycle (commitments, things you are
waiting on, renewals, occasions, decisions) and an append-only journal. Briefs and
reviews read that memory. Anything that changes the outside world, such as moving
mail, needs your explicit approval first.

Design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Status:
[docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) (the source of truth).

## The daily loop

1. **Morning:** `/start-day`. A read-only triage of every account in one panel;
   it grows into the full brief over the areas in slice 5.
2. **File:** `/email-apply [account]` moves triaged mail into `GSD/*` labels after
   you approve the plan. `/email-undo` reverses the last batch.
3. **During the day:** `/log <type> <text>`. One line into the journal;
   `/log waiting ...` and `/log commitment ...` also open a register item.
4. **Evening:** `/end-day` (stub until slice 5): kept, slipped, tomorrow's seed.
5. **When something feels off:** `/health`, and `/learn` to record the lesson.

## The areas

| Area | Covers |
|---|---|
| Wellness | health, fitness, nutrition, sleep |
| Finance | budgeting, cash flow, savings, investments, renewals |
| Growth | learning, skills, reading |
| Family | partner, children, school, pets |
| Home | house, utilities, insurance, car, documents |
| Work | your own obligations: commitments, meetings, waiting-ons |

Services such as commitments, waiting-on, renewals and occasions apply to every
area. The areas, their order and their weekly questions live in `me/areas.json`.

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env    # then set the path to your Google OAuth client file
.venv/bin/python -m gogos.system.setup_check
bash .claude/scripts/health-check.sh
```

Google access today goes through GogOS's own OAuth client (see
[docs/GOOGLE_INTEGRATIONS.md](docs/GOOGLE_INTEGRATIONS.md) for the Google Cloud
side):

```
/account-add personal you@example.com
/login-google personal
/email-report personal
```

Slice 3 replaces this with the `gog` CLI and its keyring tokens; this section will
change with it.

## Commands

| Command | What it does |
|---|---|
| `/start-day` | Read-only morning triage across all accounts, merged panel |
| `/log <type> <text>` | Append a journal event; `waiting` and `commitment` open register items |
| `/email-report [account] [window]` | Read-only triage report for one account |
| `/email-apply [account]` | Move triaged email into `GSD/*` labels (two-step approval) |
| `/email-undo [account]` | Reverse the last applied batch |
| `/email-loop [account] [--yes]` | Drain an oversized inbox in batches |
| `/calendar-brief [account] [today\|tomorrow\|week]` | Read-only calendar brief |
| `/schedule-morning [HH:MM\|off\|status]` | Install or remove the daily read-only triage (launchd) |
| `/health [--system\|--life\|--all]` | Health check plus a review of what a script cannot judge |
| `/learn [what happened]` | Record a lesson and propose a change for approval |
| `/setup-check` | Validate the environment and required directories |
| `/account-add` `/account-list` `/account-alias` `/account-remove` `/account-migrate` | Manage alias to email mappings |
| `/login-google [account]` `/logout-google [account]` | Per-account Google OAuth |
| `/morning-brief` `/end-day` `/news-brief` | Stubs; their modules come in later slices |

## Principles

- **Local-first.** Nothing leaves your machine unless you approve it.
- **Read-only first.** Write-back only after explicit two-step approval, and never delete.
- **Scripts normalise; models interpret.** Never raw API data to a model.
- **Privacy gates live in code**, not prompts, and the health check enforces the
  data boundary.
- **Every report cites its source artefacts.**
- **The system records and proposes; you approve.** Nothing rewrites itself.

## Docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): layers, memory, loops, governance, decisions.
- [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md): what is done and what is next.
- [docs/specs/](docs/specs/README.md): one spec per build slice.
- [docs/EMAILOS.md](docs/EMAILOS.md): EmailOS end to end and its safety invariants.
- [docs/SECURITY.md](docs/SECURITY.md): the data boundary, approval gates, OAuth safety.
- [docs/LEARNINGS.md](docs/LEARNINGS.md): the improvement log.
- [docs/CONNECTOR_CONTRACT.md](docs/CONNECTOR_CONTRACT.md), [docs/GOOGLE_INTEGRATIONS.md](docs/GOOGLE_INTEGRATIONS.md), [docs/PRD.md](docs/PRD.md).
