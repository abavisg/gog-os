# Spec 3: intake via gog

## Purpose

Replace GogOS's own Google OAuth and Python API client with the ClientOS Gmail and
Calendar connectors (the `gog` CLI), write one digest per source per run into
`life/inbox/`, keep the deterministic classifier as the first pass, and re-point the
gated apply engine at `gog gmail batch modify`. See proposal §9 for the security
decision this implements.

## Scope

- `gogos/intake/gmail/` and `gogos/intake/calendar/`: fetch via `gog`, normalise to
  slim JSON, classify (gmail), write digest.
- `/sync [--source gmail,calendar] [--account a] [--days N] [--fetch-only]`.
- launchd job runs `sync --fetch-only`.
- `gogos/execution/gmail_apply.py`: `_modify` shells out to `gog`.
- `.claude/settings.json` permission posture.
- Removal of `google_auth.py`, `googleapiclient` and friends; `/login-google` and
  `/logout-google` become instructions for `gog auth`.

## Non-scope

`/process-inbox` (spec 4). Calendar writes. WhatsApp or other sources (spec 11).

## Design

### Prerequisite on the Mac (owner, once)

`brew install gogcli`; per account: `gog auth add <email> --services gmail,calendar
--gmail-scope <scope>`. Two tokens are the goal:

- a **read** identity with read-only scopes (`--readonly` at auth time);
- a **write** identity with `gmail.modify`, used only by the apply engine.

Whether `gog` can hold two credential sets for one address is unverified. The first
task of this slice is to test it (`gog auth list`). If it cannot, one `gmail.modify`
token is used and the runtime guards below carry the whole load. The result is
recorded in `docs/GOOGLE_INTEGRATIONS.md`.

`.core/config/accounts.json` is unchanged (alias → email). `gog -a <email>` selects
the account.

### Connectors

Copied from `client-os/connectors/_gmail_fetch.py` and `_calendar_fetch.py` with
their verified `gog` shape handling (thread wrapper, one-line sanitised bodies,
quote stripping, rate-limit backoff, `--` before queries, draft exclusion), adapted:

- Python module shape, not shell + env: `gogos/intake/gmail/fetch.py` exposes
  `fetch(account, days, query) -> raw` and `main()`; config comes from
  `.core/config/gmail/intake.json` (`query`, `max_threads`, `max_body_chars`,
  `days_default`) with the ClientOS defaults.
- Every `gog` invocation carries `--readonly --gmail-no-send --no-input --json
  --results-only -a <email>` and `--enable-commands-exact gmail.search,gmail.thread.get`
  (calendar: `calendar.events`). Exit codes 7 and 8 retry with backoff; 4 and 10 fail
  with "run gog auth add"; anything else fails loudly. A thread with no dated
  messages is a format change and fails loudly (`GMAIL_DEBUG=1` prints shape only).
- The dedup ledger moves to `.core/storage/gmail/<email>/gog-synced.tsv` (thread id,
  newest ingested ms). Calendar has no ledger (snapshot).

### Two outputs per gmail run

1. **Slim JSON** for the classifier: `.core/storage/gmail/<email>/inbox/<date>/latest-slim.json`
   with the existing schema (`id thread_id from to subject date snippet labels
   unsubscribe`), built from the headers of each new message. `gmail_classify`,
   `gmail_rules`, `gmail_ledger`, `gmail_reconcile` and `gmail_report` are unchanged
   consumers.
2. **Digest** for the Gardener: `life/inbox/gmail-<alias>-<date>[-HHMM].md` with
   capture front matter (`type: capture`, `source: gmail`, `account: <alias>`,
   `processed: false`), grouped **by classifier category**, each thread with the
   classifier's category and rationale on its heading line. Bodies (capped) are
   included **only for Action, Review and Events**; Information, Newsletters and Safe
   to Delete list subject, sender and date only. This keeps the digest useful and
   keeps bulk mail bodies out of the inbox entirely.

Classification therefore runs inside `/sync` after normalise, before the digest is
written. The Markdown/HTML `gmail_report` remains available via `/email-report` for
the per-account view and continues to feed `/email-apply`.

### Calendar

`life/inbox/calendar-<alias>-<date>.md`: past `days` plus `days_ahead` (default 7),
overwritten on a same-day rerun, descriptions capped at 500 characters, and the same
slim JSON as today for `calendar-brief`.

### `/sync`

```
python -m gogos.intake.sync [--source gmail,calendar] [--account alias,…] [--days N] [--fetch-only]
```

Runs the selected connectors per account independently; one failing account is
reported and the rest continue; exit non-zero only if all fail. Writes one
`sync.run` journal event with counts. Without `--fetch-only` the command then
invokes `/process-inbox` (spec 4); until spec 4 lands, `/sync` is fetch-only and
says so. Default sources and days live in `.core/config/sync.json`.

### Scheduler

`gogos/system/scheduler.py` is kept; `run_scheduled` becomes `sync --fetch-only`
for every account plus one notification with counts ("12 new threads, 3 Action").
It never classifies into the start-day panel and never processes. Source-scan test:
the module references neither `gmail_apply` nor `process`.

### Apply engine via gog

`gogos/execution/gmail_apply.py` (moved from `gogos/gmail/`): `_modify` keeps
`_assert_safe` unchanged and then runs

```
gog --gmail-no-send --no-input --json -a <email> \
    --enable-commands-exact gmail.batch.modify \
    gmail batch modify <message_id> --add-label '<GSD/Category>' --remove-label INBOX
```

Label validation uses names (the gate already validates names). `fetch_label_map`
uses `gog gmail labels list` under `--readonly`. Undo mirrors it with `--add-label
INBOX --remove-label '<GSD/Category>'`. The approval file, inverse plan and
per-batch records from spec 1 are unchanged. `_service()` and every `googleapiclient`
import are removed. A source-scan test asserts the only `gog` invocation without
`--readonly` in the codebase is in `gmail_apply._modify` and `gmail_undo._modify_undo`.

### Permissions (`.claude/settings.json`)

Adopt ClientOS's structure. Deny: `Bash(gog)`, `Bash(gog *)`, `Bash(*/gog *)`,
`Bash(curl *googleapis.com*)`, credential-store reads, `Bash(env)`, `Read(//**/.env)`.
Ask: `Bash(git push *)`, `Bash(rm *)` and variants, `Bash(.venv/bin/python -m
gogos.execution.*)`. Allow: reads, `Bash(.venv/bin/python -m gogos.intake.*)`,
`Bash(.venv/bin/python -m gogos.core.*)`, `pytest`, `ruff`, read-only git. The hook
command from spec 1 stays.

### Removals

`gogos/auth/google_auth.py`, `gogos/auth/logout.py`, `tests/test_google_auth.py`,
`tests/test_logout.py`, the `google-*` dependencies in `pyproject.toml`.
`/login-google` and `/logout-google` commands are rewritten as short instruction
pages for `gog auth add` / `gog auth remove` run by the owner with `!`.
`.env.example` loses `GOOGLE_CREDENTIALS_PATH`. `docs/GOOGLE_INTEGRATIONS.md` is
rewritten around `gog`.

## Acceptance criteria

- [ ] `gog auth list` result (one or two identities per address) recorded in docs.
- [ ] `/sync --source gmail --account personal --days 2` writes slim JSON, a triage
      JSON and one digest grouped by category with bodies only under Action / Review
      / Events.
- [ ] Rerunning produces "nothing new" and no second digest.
- [ ] `/sync --source calendar` writes the snapshot and slim JSON; rerun overwrites.
- [ ] `/email-apply personal` end to end against a test label: approval file, apply via
      `gog`, per-batch record, `/email-undo` restores INBOX.
- [ ] `grep -rn googleapiclient gogos tests` returns nothing.
- [ ] Source-scan test for unguarded `gog` calls passes.
- [ ] From a Claude session, `gog gmail search …` typed directly is denied.

## Tests

- `tests/test_intake_gmail.py`: fixtures copied from ClientOS's verified `gog` shapes
  (synthetic content): thread wrapper, one-line bodies, draft exclusion, ledger
  advance only after write, rate-limit retry, format-change failure.
- `tests/test_intake_digest.py`: grouping, body inclusion rules, front matter.
- `tests/test_intake_calendar.py`.
- `tests/test_sync.py`: per-account isolation, exit codes, journal event.
- `tests/test_gmail_apply.py` extended: the exact `gog` argv, `_assert_safe` still
  gates, missing label aborts before any `gog` call.
- `tests/test_scheduler.py`: fetch-only, source scan.

## Open questions

- `gog gmail batch modify` accepts label names in the docs' examples; confirm on the
  Mac that nested names (`GSD/Action`) resolve, or switch to ids from `labels list`.
- Whether `--enable-commands-exact` names are `gmail.batch.modify` or `gmail.batch`;
  take from `gog --help` on install.
