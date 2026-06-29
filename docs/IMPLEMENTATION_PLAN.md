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

---

## NEXT

### Phase 5 — TaskOS Local MVP

Build local task schema and `/task-add`, `/tasks-today`, `/task-done`.

Acceptance criteria:
- Append-safe creation, status updates preserve history.
- Morning brief can read open tasks.

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
