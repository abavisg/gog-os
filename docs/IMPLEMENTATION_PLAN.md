# Incremental Implementation Plan

## Rule

Build one module at a time. No dashboard. No write-back until read-only workflows are proven.

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
- `docs/EMAILOS_AUTOMATION.md` — locked decisions: scheduled run stays read-only
  (fetch→classify→report→notify), moves remain manual via `/email-apply` / `/email-loop`.
- `docs/CONNECTOR_CONTRACT.md` — the `fetch(client, window)` / `normalise(raw)` seam every
  connector conforms to, ahead of extracting connectors into a separate repo.
- Scheduling deferred: a cloud routine can't run the local pipeline (no venv/OAuth/storage);
  a local launchd/cron job is the path when we automate.
- Tests passing (289/289).

---

## NEXT

### Phase 4.6 — EmailOS finalisation

Close out EmailOS: make unattended runs safe and reversible, add user-controlled rules,
merge accounts, and give it a single morning entry point. Everything here stays inside
the existing privacy/approval gates (metadata-only, moves via label+archive, never delete).

**1. Undo / reverse a batch (`/email-undo`).**
- Every `apply` writes an **inverse plan** to `.core/storage/approvals/<account>/<date>/undo.json`
  alongside the move plan: for each moved message, the exact reversal (remove `GSD/<Category>`,
  restore `INBOX`).
- `/email-undo [account]` replays the latest `undo.json` through the same gated `_modify`,
  so undo is as safe as apply and never deletes. Makes unattended/scheduled moves reversible.

**2. User classification rules (override, safety-capped).**
- New config `.core/config/gmail/rules.json`: ordered user rules, each `{match, category}`
  where `match` targets sender domain / substring / pattern (e.g. `LinkedIn Jobs → GSD/Review`).
- User rules are checked **first** and win over built-in rules — **except** they can never
  route a financial/security/civic/real-person mail into `Safe to Delete`; the never-delete
  invariant stays absolute (a user rule that tries is refused, logged, and falls through).
- No new folders/labels — reuse the existing `GSD/Review` (read-then-delete/archive) and the
  current category set. Review is the holding pen; low-confidence built-in matches route there
  rather than to a destructive-ish category.

**3. Sender-consistency ledger (enforce + learn).**
- A local ledger `.core/storage/gmail/<account>/sender-ledger.json` records `sender → category`
  decisions. Same sender always classifies the same way within and across runs.
- Config or user-rule changes update the ledger (explicit re-learn), never a silent drift.
- Test asserts no sender splits two ways in a run; runtime asserts a new decision matches the
  ledger or updates it deliberately.

**4. Digest header on the report.**
- Add a 3-line executive summary at the top of the email report: counts by category with the
  important call-outs (e.g. "4 Action (2 financial), 1 Event needs RSVP, 62 Safe-to-Delete
  queued"). Designed to grow as Calendar/Task digests join it in `/start-day`.

**5. Multi-account merge (personal + work).**
- `/start-day` (and the email report) can run **both** accounts and present **one merged
  panel, each item account-tagged** `[personal]` / `[work]`. Fetch/classify/apply still run
  per-account under the hood; only the view is unified. Undo and approval remain per-account.

**6. `/start-day` orchestrator + SessionStart hook.**
- `/start-day` is the single morning command: runs EmailOS **read-only** (fetch → classify →
  triage → report) across accounts, prints the merged digest panel, and **stops**. No moves —
  write-back stays behind `/email-apply` / `/email-loop`.
- A SessionStart **hook** *offers* it ("Run /start-day? 12 new, 3 need action") — it nudges,
  never auto-runs write-back, preserving local-first + approval principles.
- Later, `/start-day` folds in CalendarOS and TaskOS digests (Phases 5–6).

**7. Local scheduler (unparks the morning run).**
- A local **launchd/cron** job runs the real `gogos` pipeline (has venv, OAuth token, storage)
  at ~08:00: fetch → classify → triage → report → **notify**, read-only. Fires only while the
  Mac is on. Moves stay manual. (Cloud routines remain out — they can't run the local pipeline.)

**Explore before building — unsubscribe surfacing (item 6 from recap):**
- For repeat `Safe to Delete` / `Newsletters` senders, surface the `List-Unsubscribe` header
  (a header, not body — stays within the metadata-only privacy gate) so one action kills the
  source. Open question: one-click unsubscribe (`List-Unsubscribe-Post`, RFC 8058) crosses into
  write-back and needs the approval gate; scope in a design pass before committing.

**Acceptance criteria:**
- `/email-undo` fully reverses the latest batch; a test proves apply→undo is a no-op on labels.
- User rules override built-ins but a test proves they can't push an important mail to Safe to Delete.
- Sender-ledger test proves no sender classifies two ways in a run.
- Digest header renders correct counts; merged panel account-tags every item.
- `/start-day` runs read-only across accounts and never moves; the hook only offers, never acts.
- Scheduler documented and installable; the scheduled run is provably read-only.

**Parked (EmailOS v2 backlog — named, not scheduled):** VIP / waiting-on detection; snooze/defer
a thread (TaskOS overlap); weekly email review feeding ReflectionOS; low-confidence "Needs-Review"
as a distinct signal beyond reusing `GSD/Review`.

### Phase 5 — TaskOS Local MVP

Local-first task store: no external service, no write-back gate needed (all data is
local). Follows the module shape — `add` / `list` / `update` functions + `__main__` CLI,
each tested — and the storage convention (dated file **and** a `latest-*` alias).

Modules:
- `gogos/tasks/task_store.py` — the store. A task is `{id, title, status, created_utc,
  updated_utc, due, tags, history[]}`; status ∈ `open | done | dropped`. Append-safe
  creation (new task never rewrites existing ones); every status change appends to
  `history[]` with a UTC timestamp rather than overwriting — status updates preserve
  history. Tasks persist to `.core/storage/tasks/<account-or-local>/tasks.jsonl`
  (append-only) with a derived `latest-open.json` slim projection for consumers.
- `gogos/tasks/task_report.py` — renders today's / open tasks to Markdown (mirrors the
  existing `*_report.py` shape). No skill needed for the MVP — deterministic listing.

Commands:
- `/task-add <title> [--due YYYY-MM-DD] [--tag ...]` — append a new open task.
- `/tasks-today` — list open tasks (due today or overdue first, then undated).
- `/task-done <id>` — mark done; appends to history, refreshes `latest-open.json`.

Acceptance criteria:
- Append-safe creation, status updates preserve history (nothing is ever rewritten in
  place; `history[]` is the audit trail).
- `latest-open.json` slim projection stays current after every mutation, so the morning
  brief (Phase 6) can read open tasks without parsing the full JSONL.
- Timestamps stored UTC, rendered local at report time (per storage conventions).
- Tests under `tests/test_tasks_*.py` cover: append-only creation, history preservation
  on `done`/`dropped`, and the `latest-open.json` projection.

### Phase 6 — BriefingOS MVP

Build `/morning-brief` aggregating latest EmailOS, CalendarOS, and TaskOS outputs.

Acceptance criteria:
- One useful brief with priorities, schedule, email actions, risks.
- Missing modules handled gracefully.
- Cites source artefacts.

### Phase 7 — ActivityOS MVP

Build `/log [type] [text]` writing to dated JSONL. Types: activity, decision, learning, workout, content, note.

Acceptance criteria:
- Append-only. Timestamped. Consumable by ReflectionOS.

### Phase 8 — ReflectionOS MVP

Build `/end-day` and `/weekly-review` reading daily logs and morning brief.

Acceptance criteria:
- Completed / slipped / decisions / follow-ups / tomorrow seed list.

### Phase 9 — NewsOS MVP

Build `/news-brief [feed]` from configured feeds. Manual source first, automated later.

Acceptance criteria:
- Source-linked, relevance-scored, low volume.

---

## LATER

Phases 10–11 (LearningOS, HealthOS, ContentOS Bridge) only after the Morning Brief and Reflection loops have been running usefully for at least two weeks.

Phase 12 (Dashboard) only if the command-line loop proves insufficient.
