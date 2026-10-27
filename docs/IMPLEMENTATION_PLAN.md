# Incremental Implementation Plan

This file is the source of truth for what is built and what comes next (the README
table can lag). Since 2026-10-23 the work is organised as the v2 build slices in
`docs/specs/README.md`; the design they build is `docs/ARCHITECTURE.md`. The v1
phases under DONE are kept as the record of what the slices build on.

## Rule

One slice at a time, one PR per slice. A slice is done when pytest and `run-tests.sh` are green, `health-check.sh` passes, the spec's acceptance criteria are ticked in the PR, and its entry moves here. No write-back until the read-only path is proven.

---

## DONE

### Phase A — FoundationOS
- `gogos/paths.py` — dated storage path resolver.
- `gogos/system/setup_check.py` — validates Python ≥3.11, required dirs, optional creds.
- `/setup-check` command wired to script.
- Tests passing.

### Phase A.5 — Google Auth
- `gogos/auth/google_auth.py` — OAuth helper, per-account tokens at `chmod 600`.
- `/login-google [account]` and `/logout-google [account]` with confirmation.
- Multi-account (`personal`, `work`) supported from the start.
- Tests passing.

### Phase B — EmailOS (read-only)
- `gogos/gmail/gmail_fetch.py` — metadata-only fetch, hard-asserts no body in output.
- `gogos/gmail/gmail_normalise.py` — raw → canonical slim JSON, UTC dates.
- `gogos/gmail/gmail_triage.py` — validates and writes triage JSON.
- `gogos/gmail/gmail_report.py` — Markdown + HTML report, auto-opens in Chrome.
- `email-triage` skill hardened against prompt injection.
- `/email-report [account]` end-to-end working.
- Tests passing.

### Phase B.5 — EmailOS write-back (move to GSD folders)
- OAuth scope bumped `gmail.readonly` → `gmail.modify` (label + archive, never delete).
- `gogos/gmail/gmail_apply.py` — builds a move plan from latest triage, applies on approval.
  Move = add `GSD/<Category>` label + remove `INBOX` (archive). Never trashes/deletes/spams;
  enforced by a single gated `_modify` and `_assert_safe`.
- Two-step approval: proposal written to `.core/storage/approvals/<account>/<date>/gmail-labels.json`
  with `approved: false`; applied only after explicit user confirmation.
- Missing `GSD/*` label → abort with a clear message (no auto-create, no partial apply).
- Stale-email warning surfaces inbox mail predating yesterday 00:00.
- `/email-apply [account]` command wired end-to-end.
- Tests passing (260/260), including the never-delete invariant.

### Phase 4 — CalendarOS (read-only)
- `gogos/calendar/calendar_fetch.py` — events for today/tomorrow/week, safe projection (no descriptions).
- `gogos/calendar/calendar_normalise.py` — raw → slim JSON, UTC dates, duration, all-day flag.
- `gogos/calendar/calendar_report.py` — Markdown + HTML brief, auto-opens in Chrome.
- `calendar-brief` skill — focus gaps, risks, per-event prep notes, injection-hardened.
- `/calendar-brief [account] [today|tomorrow|week]` end-to-end working.
- Tests passing (199/199).

### Phase 4.5 — EmailOS automation (unattended triage + batch drain)
- `gogos/gmail/gmail_classify.py` — deterministic, ordered first-match-wins classifier
  (normalised slim JSON → triage JSON, same schema `gmail_triage` validates). Runs with
  no human in the loop. Sender lists in `.core/config/gmail/classify.json` so they grow
  without code changes. Never-delete invariant (financial/security/civic/real-person
  never land in Safe to Delete) enforced by rule order and tested.
- `gogos/gmail/gmail_loop.py` + `/email-loop [account] [--yes]` — drains an inbox larger
  than the fetch cap by looping fetch→normalise→classify→triage→report→apply in batches
  until the inbox is empty. Bounded (max 20 iterations). `--yes` pre-authorises all
  batches; default pauses for approval per batch. Still never deletes.
- Automation design (now folded into `docs/EMAILOS.md`) — locked decisions: scheduled run stays read-only
  (fetch→classify→report→notify), moves remain manual via `/email-apply` / `/email-loop`.
- `docs/CONNECTOR_CONTRACT.md` — the `fetch(client, window)` / `normalise(raw)` seam every
  connector conforms to, ahead of extracting connectors into a separate repo.
- Scheduling deferred: a cloud routine can't run the local pipeline (no venv/OAuth/storage);
  a local launchd/cron job is the path when we automate.
- Tests passing (289/289).

### Phase 4.6 — EmailOS finalisation (complete; scope locked 2026-07-01)

Full behaviour documented in `docs/EMAILOS.md`. Delivered as thin vertical slices,
one PR each, pinned parameter: auto-learn threshold N = 3 corrections.

- **Slice 1 — `List-Unsubscribe` capture.** Headers into fetch + normalise (`unsubscribe`
  field). Headers, not body — the privacy gate is unchanged and tested.
- **Slice 2 — `/email-undo`.** Every apply writes an inverse plan
  (`approvals/<account>/<date>/gmail-applied-<HHMMSS>.json`); undo reverses it through
  the inverse gate `_modify_undo`. Test proves apply→undo is a no-op on labels.
- **Slice 3 — user rules + sender ledger.** `.core/config/gmail/rules.json` overrides
  checked before built-ins, but can never route important mail to Safe to Delete (tested).
  `sender-ledger.json` guarantees a sender never classifies two ways in a run (tested).
- **Slice 4 — reconcile + auto-learn + unsubscribe surfacing.** `gmail_reconcile` detects
  manual moves since the last apply (label sets only); 3 corrections auto-learn the ledger
  (logged in the report, revertible); never-rescued senders with `List-Unsubscribe` are
  surfaced as candidates — you click the link yourself, zero write-back.
- **Slice 5 — digest header.** 3-line executive summary on the email report; grows as
  Calendar/Task digests join `/start-day`.
- **Slice 6 — `/start-day` + multi-account merge + SessionStart hook.** One read-only
  morning command across all accounts, merged account-tagged panel, then stops (a test
  proves the module can't reach the apply engine). The hook only *offers* the command.
- **Slice 7 — local scheduler.** `/schedule-morning [HH:MM|off|status]` +
  `gogos/system/scheduler.py`: installs a launchd agent that runs the read-only pipeline
  per account at ~08:00 (report without browser auto-open), posts one macOS notification,
  and never writes the `/start-day` panel — the SessionStart nudge keeps its counts.
  Provably read-only (source-scan test); fires only while the Mac is on. Cloud routines
  stay out (no venv/OAuth/storage; see `docs/EMAILOS.md`).
- Tests passing (403/403).

**Parked (EmailOS v2 backlog — named, not scheduled):** gated one-click unsubscribe
(`/email-unsubscribe` — outbound send crossing the approval gate, needs a send scope);
VIP / waiting-on detection; snooze/defer a thread (TaskOS overlap); weekly email review
feeding ReflectionOS; low-confidence "Needs-Review" as a distinct signal beyond `GSD/Review`.

### v2 slice 1: defects and CI (`docs/specs/01-defects-and-ci.md`)
- Packaging: setuptools build-system plus `gogos*` package find, so `pip install -e .[dev]` works on a fresh clone; `gogos.egg-info/` untracked and ignored.
- Per-batch applied records: each apply writes `gmail-applied-<HHMMSS>.json` with `batch_id` and `undone_at`; undo takes the newest un-undone record across dates; reconcile re-checks every record applied in the last 14 days and not undone, stamping `last_reconciled_at`.
- One today: `gogos.paths.today()` and `now_utc()` back storage, approvals, the fetch "yesterday" window, `/start-day` and report timestamps, so all dates follow `GOGOS_TIMEZONE`.
- Non-interactive auth: `get_credentials(..., interactive=False)` raises instead of opening a browser; `start_day.run_account` (and so the scheduler) uses it.
- Docs: `undo.json` replaced by `gmail-applied-<HHMMSS>.json`; SECURITY.md and CLAUDE.md state the Gmail snippet exception.
- CI: `.github/workflows/ci.yml` runs `ruff check gogos tests` and `pytest -q` on push and PR; ruff rule set pinned; ruff reports 0.
- Hook: SessionStart runs the nudge only when `.venv/bin/python` exists, and never errors.
- Tests passing (421/421).

### v2 slice 2: memory substrate (`docs/specs/02-memory-substrate.md`)
- Paths and skeletons: `gogos/core/paths.py` adds `LIFE_ROOT`, `ME_ROOT` and the inbox, wiki, registers, journal, workspace and reports helpers; `life/` and `me/` are tracked, `/life/inbox/` is gitignored and `.core/config/` stays tracked (spec 2 as amended in PR #18).
- Registers: `gogos/core/registers.py` validates the seven kinds on the base front matter schema, appends `## History` lines, derives moved_count, days_overdue, renegotiate, ignored, idle and at_risk from history, and writes `registers/<kind>/_index.md` plus `registers/_index.json`.
- Journal and `/log`: `gogos/core/journal.py` appends ULID-keyed events in one `O_APPEND` write; `/log` infers the area where the type settles it, and `waiting` and `commitment` entries create register items.
- `me/`: `profile.md` (validation log, every row provisional), `areas.json` (the six areas) and `themes.md`, placeholders only.
- Kanban (2b): `gogos/core/kanban.py` projects open commitments into the `gogos` Claude Code task list and reconciles board completions back as `kept`; the real task format is pinned in `tests/fixtures/kanban/`.
- Carry-overs: `gmail_reconcile.load_recent_applied` (renamed); `prototypes/goals_store/` absorbed into `registers.derived()` and gone.
- Docs: this entry and the CLAUDE.md pointer to `life/`, `me/` and `/log`.
- Tests passing (569/569).

### v2 slice 8: governance (`docs/specs/08-governance.md`)
- Permissions: `.claude/settings.json` carries the deny / ask / allow arrays and the autoMode prose (direct `gog`, Google API calls, credential stores and non-PR GitHub writes denied; push, `rm`, the PR flow and Gmail write-back ask). `settings.local.json` is gitignored and untracked; its allow rules were folded in. `permission-check.sh` copied from ClientOS.
- Health check: `.claude/scripts/health-check.sh` (SYSTEM S1 to S8 gate the exit code; LIFE L1 to L8 advisory); the LIFE half and S6 in `gogos/core/health.py`; L3 is `registers.validate_all()` (`registers validate`).
- Bash tests: `.claude/scripts/run-tests.sh`, one synthetic violation per SYSTEM check, LIFE and banner cases, fixture hygiene.
- Learning loop: `/learn`, `/health` and `docs/LEARNINGS.md`, written only through `gogos/core/learnings.py`.
- Banner: `.claude/scripts/banner.sh` replaces the start-day nudge as the SessionStart hook.
- Decoupling: S4 found the owner's alias and address in eight command examples; replaced with placeholders.
- CI runs `health-check.sh --system` after ruff and pytest.
- Docs: ARCHITECTURE.md v2 with a Decisions log, this plan, README, SECURITY.md, the proposal banner.
- Tests passing (pytest 594/594, run-tests 37/37).

---

## NEXT

The remaining v2 slices, in dependency order. Each spec has its scope, acceptance
criteria and tests.

| Slice | Spec | Depends on | What it brings |
|---|---|---|---|
| 3 | [Intake via gog](specs/03-intake-via-gog.md) | 2 | `gog` connectors replace the Python Google client; digests in `life/inbox/`; `/sync`; fetch-only launchd job; apply engine via `gog gmail batch modify` |
| 4 | [Intelligence core](specs/04-intelligence-core.md) | 2, 3 | rules file, three agents, `wiki-update`, `register-update`, `/process-inbox` |
| 5 | [Daily loop](specs/05-daily-loop.md) | 2, 3, 4 | `/start-day` over the grid, `/end-day`, `/weekly-review` |
| 6 | [Wellness](specs/06-wellness.md) | 2, 5 | five `/log` types in use, two habit goals, Wellness first in the weekly review |
| 7 | [Council](specs/07-council.md) | 2, 4 | Chair and five seats, `/council`, `/brainstorm` |
| 9 | [Home and Family services](specs/09-home-and-family-services.md) | 3, 4, 5 | renewals from the classifier, occasions, last-contact, workspace template |
| 10 | [ClientOS bridge](specs/10-clientos-bridge.md) | 5 | deferred; the spec is open questions |
| 11 | [Further intake](specs/11-further-intake.md) | per source | Apple Health, WhatsApp, finance feeds, each earned by a real need |

Next up: **slice 3**.

---

## LATER

A dashboard only if the command-line loop proves insufficient. Versioned releases,
tags and migrations once a second machine depends on the repo.
