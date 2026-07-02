# GogOS Architecture

Local-first modular pipeline. Deterministic Python scripts fetch and normalise; Claude skills interpret; commands orchestrate.

```
API → normalised slim JSON → Claude skill → Markdown report
```

Never pass raw API data directly to a model. Privacy gates live in code, not prompts — e.g. `gmail_fetch` hard-asserts no message body ever reaches storage.

## Layers

| Layer | Location | Role |
|---|---|---|
| Interface — slash commands | `.claude/commands/*.md` | Orchestrate: run scripts, invoke skills, display reports |
| Reasoning — Claude skills | `.claude/skills/*/SKILL.md` | Interpret slim JSON, emit structured output |
| Scripts — deterministic Python | `gogos/**/*.py` | Fetch, normalise, classify, apply, report |
| Storage — dated artefacts | `.core/storage/**` | All generated data, gitignored |
| Config | `.core/config/**` | Accounts, categories, classifier rules, feeds |

A command runs `gogos` scripts to produce slim JSON, hands that JSON to a skill, and the skill's output is rendered into a report. Connectors (the service-facing fetch/normalise code) follow the seam defined in [CONNECTOR_CONTRACT.md](CONNECTOR_CONTRACT.md).

## Storage conventions

Dated directories via `gogos.paths.storage_path(module, account, kind, date)`. Always write a dated file **and** a `latest-*` alias.

```
.core/storage/gmail/<account>/inbox/<date>/latest-raw.json      # fetch output (metadata only)
.core/storage/gmail/<account>/inbox/<date>/latest-slim.json     # normalised
.core/storage/gmail/<account>/triage/<date>/latest-triage.json  # classified
.core/storage/gmail/<account>/sender-ledger.json                # sender → category consistency
.core/storage/calendar/<account>/events/<date>/latest-slim.json
.core/storage/reports/email/<account>/<date>/latest.md          # + latest.html
.core/storage/reports/start-day/all/<date>/latest.md            # merged multi-account panel
.core/storage/approvals/<account>/<date>/gmail-labels.json      # proposed moves + undo.json
.core/storage/auth/<account>/google_token.json                  # chmod 600
```

Timestamps are stored as **UTC** internally and rendered local (`Europe/London`, override via `GOGOS_TIMEZONE`) only at report time.

## Accounts

Commands take an alias (`personal`, `work`); `gogos/auth/accounts.py` resolves it to a canonical email (config in `.core/config/accounts.json`). Storage paths and API calls always use the email. Tokens are per-account.

## Script conventions

- Module docstring documents the entry point and the `python -m gogos.<module>` invocation.
- Both an importable function (`fetch(...)`, `normalise(...)`) and a `__main__` CLI.
- Exit non-zero on failure, errors to stderr, create parent dirs, never silently skip auth failures.
- Each module follows `fetch` → `normalise` → `report`, tested under `tests/test_<module>_*.py`.

## Approval gates

Read-only operations need no approval after setup.

State-changing operations (Gmail labels/archive, Calendar writes, sending email, posting) require a two-step flow:

1. Write the proposed action to `.core/storage/approvals/<account>/<date>/{operation}.json`.
2. Apply only after explicit user confirmation.

Gmail write-back is further constrained in code: the only permitted mutations are adding a `GSD/*` label and removing `INBOX` (archive). Delete/trash/spam are never called — see [EMAILOS.md](EMAILOS.md).

## Model selection

Default is **Sonnet, left unpinned in front matter** so it tracks the current Sonnet. Do not pin a Sonnet version. Pin a model only where a skill genuinely needs it:

| When | Pin |
|---|---|
| Architecture review / system critique | Opus (e.g. `model: claude-opus-4-8`) |
| Normal implementation and reasoning | *(omit — Sonnet default)* |
| Report formatting / simple summaries | Haiku (e.g. `model: claude-haiku-4-5-20251001`) |

Today all skills are normal-reasoning, so none pin a model.
