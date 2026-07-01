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
