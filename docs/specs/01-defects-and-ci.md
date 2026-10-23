# Spec 1: defects and CI

## Purpose

Clear the five known defects from the 2026-10-23 review and add CI, so every later
slice lands on a repo that installs from a fresh clone and fails loudly when broken.

## Scope

1. `pip install -e .` works on a fresh clone.
2. Every applied batch is independently undoable and reconcilable.
3. One definition of "today".
4. Scheduled runs never block on interactive OAuth.
5. Docs name the files that exist.
6. CI runs tests and lint on every push and PR.
7. The SessionStart hook tolerates a missing `.venv`.

## Non-scope

Anything from spec 2 onwards. No new behaviour; no new storage layout. The
`prototypes/` directory stays until spec 2 absorbs it.

## Design

### 1. Packaging

`pyproject.toml` gains:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["gogos*"]
```

`gogos.egg-info/` is removed from git (`git rm -r --cached`) and `*.egg-info/` is
added to `.gitignore`.

### 2. Per-batch applied records

`gogos/gmail/gmail_apply._write_applied_result` writes
`approvals/<account>/<date>/gmail-applied-<HHMMSS>.json` (UTC time of apply) instead
of a fixed name. Each record carries `batch_id` (the filename stem) and
`undone_at: null`.

- `gmail_undo.load_applied` returns the **newest record with `undone_at` null**
  across all dates (not today only), so an undo after midnight still works. Undo
  sets `undone_at` on that record only.
- `gmail_reconcile.load_latest_applied` becomes `load_unreconciled_applied`: every
  record not yet marked `reconciled_at`, newest first. `detect_corrections` runs per
  record; `reconcile` marks each record `reconciled_at` after processing. The
  message-id keyed state still prevents double counting.
- `gmail_loop` needs no change: each `apply_plan` call writes its own record.

### 3. One today

`gogos/paths.py` gains `today() -> str` (local date in `GOGOS_TIMEZONE`) and
`now_utc() -> datetime`. Call sites that compute a date themselves are replaced:
`gmail_apply._approvals_dir` (was UTC), `gmail_fetch._resolve_window` (was system tz;
the "yesterday" window is built from `GOGOS_TIMEZONE`), `start_day._today`,
`gmail_report._now_local`, `calendar_report._now_local`. `storage_path` uses
`today()`.

### 4. Non-interactive auth

`google_auth.get_credentials(account, *, interactive: bool = True)`. With
`interactive=False`, a missing token or a token without a refresh token raises
`RuntimeError("Account <alias> needs /login-google; refusing to open a browser in an
unattended run")`. `scheduler.run_scheduled` and `start_day.run_account` pass
`interactive=False`. Spec 3 removes this module entirely; the fix is small and stops
a hang in the meantime.

### 5. Docs

Replace `undo.json` with `gmail-applied-<HHMMSS>.json` in `docs/ARCHITECTURE.md`,
`docs/EMAILOS.md`, `docs/IMPLEMENTATION_PLAN.md`. Add a line to `docs/SECURITY.md`
and `CLAUDE.md` principle 4 stating that the Gmail snippet (body-derived, up to
about 100 characters) is stored and shown to the model.

### 6. CI

`.github/workflows/ci.yml`: on push and pull_request, Python 3.12, `pip install -e
.[dev]`, `ruff check gogos tests`, `pytest -q`. `ruff --fix` is run once in this
slice for the 55 auto-fixable findings; the remaining 22 are either fixed or
suppressed with a reason. `ruff` config in `pyproject.toml` pins the rule set so
the count cannot creep.

### 7. Hook

`.claude/settings.json` SessionStart command becomes
`cd "$CLAUDE_PROJECT_DIR" && [ -x .venv/bin/python ] && .venv/bin/python -m
gogos.system.start_day --nudge || true`.

## Acceptance criteria

- [ ] `git clone && python -m venv .venv && .venv/bin/pip install -e .[dev]` succeeds.
- [ ] Two `apply_plan` calls in one day produce two records; `build_undo` reverses the
      second, then the first; `reconcile` learns from both.
- [ ] `grep -rn "datetime.now()" gogos` returns nothing; `approvals/` and `storage/`
      dates agree for a run at 00:30 local.
- [ ] `run_scheduled` with no token exits 1 within a second with the message above.
- [ ] `grep -rn "undo.json" docs` returns nothing.
- [ ] CI green on the PR; `ruff check` reports 0.
- [ ] Opening a session in a clone without `.venv` prints no hook error.

## Tests

- `tests/test_gmail_apply.py`: per-batch filenames; two applies, two records.
- `tests/test_gmail_undo.py`: newest-unundone selection across dates; `undone_at`
  set on one record only.
- `tests/test_gmail_reconcile.py`: two records, both reconciled, each marked.
- `tests/test_paths.py`: `today()` honours `GOGOS_TIMEZONE`; approvals dir equals
  storage dir date at a mocked 23:30 UTC in summer.
- `tests/test_google_auth.py`: `interactive=False` raises instead of calling
  `run_local_server`.

## Open questions

None.
