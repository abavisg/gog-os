# GogOS

A Claude Code-native, local-first personal operating system. Turns Gmail, Google Calendar, local logs, and news feeds into structured daily briefs — locally, with no write-back without explicit approval.

## Non-negotiable principles

1. **Local-first.** Nothing leaves the machine unless the user approves it.
2. **Read-only first.** Write-back (Gmail labels/archive/delete, Calendar writes, sending email, posting) only after explicit two-step approval.
3. **Scripts normalise; models interpret.** Never pass raw API data to a Claude skill. The pipeline is always `API → normalised slim JSON → skill → Markdown report`.
4. **Privacy gates live in code, not prompts.** e.g. `gmail_fetch` hard-asserts no message body ever reaches storage. Keep these assertions; don't loosen them.
5. **Every report cites its source artefacts.**

## Architecture (5 layers)

| Layer | Location |
|---|---|
| Interface — slash commands | `.claude/commands/*.md` |
| Reasoning — Claude skills | `.claude/skills/*/SKILL.md` |
| Scripts — deterministic Python | `gogos/**/*.py` |
| Storage — dated artefacts | `.core/storage/**` |
| Config | `.core/config/**` |

A command orchestrates: it runs `gogos` scripts to produce slim JSON, hands that JSON to a skill, and the skill emits a report. See `docs/ARCHITECTURE.md` for the full contract.

## Storage conventions

Dated directories via `gogos.paths.storage_path(module, account, kind, date)`. Always write a dated file **and** a `latest-*` alias.

```
.core/storage/gmail/personal/inbox/2026-06-04/latest-slim.json
.core/storage/calendar/personal/events/2026-06-04/latest-slim.json
.core/storage/reports/briefs/2026-06-04/morning-brief.md
.core/storage/logs/2026-06-04/activity.jsonl
```

Timestamps stored as **UTC** internally; rendered local (`Europe/London`, override via `GOGOS_TIMEZONE`) only at report time.

## Accounts

Alias → email resolution lives in `gogos/auth/accounts.py` (config in `.core/config/accounts.json`). Commands take an alias (`personal`, `work`); scripts resolve it. Tokens are per-account at `chmod 600`.

## Script conventions

- Module docstring documents the entry point and the `python -m gogos.<module>` invocation.
- `from __future__ import annotations` at top; type hints throughout.
- Exit non-zero on failure, errors to stderr, create parent dirs, never silently skip auth failures.
- Both an importable function (`fetch(...)`, `normalise(...)`) and a `__main__` CLI.

## Approval gate (state-changing ops)

1. Write a proposed action to `.core/storage/approvals/<account>/<date>/{operation}.json`.
2. Apply only after explicit user confirmation.

## Model selection

**Default is Sonnet, left unpinned in front matter** so it tracks the current Sonnet and isn't frozen to a version. Do **not** add `model: claude-sonnet-4-6` (or any pinned Sonnet) to a skill/command — omit the `model:` key and it inherits the Sonnet default.

Pin a model in front matter **only** where a specific skill genuinely needs it:

| When | Pin |
|---|---|
| Architecture review / system critique | Opus (e.g. `model: claude-opus-4-8`) |
| Normal implementation and reasoning | *(omit — Sonnet default)* |
| Report formatting / simple summaries | Haiku (e.g. `model: claude-haiku-4-5-20251001`) |

**Fable is excluded** — we don't have access to it. Never select or pin a Fable model.

Today all five skills are normal-reasoning, so none pin a model. Add a pin only when a new skill clearly falls into the Opus or Haiku row above.

## Working on this repo

- Run tests: `.venv/bin/python -m pytest -q` — keep the suite green.
- New modules follow the existing shape: `fetch` → `normalise` → `report`, each tested under `tests/test_<module>_*.py`.
- Status of modules: `docs/IMPLEMENTATION_PLAN.md` is the source of truth (the README table can lag). **Next up: Phase 5 — TaskOS.**
- EmailOS end-to-end behaviour and safety invariants: `docs/EMAILOS.md`.
- Some commands (`/morning-brief`, `/log`, `/end-day`, `/news-brief`) exist as stubs ahead of their backing modules — don't assume a command means the module is built.
