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
- `gogos/gmail/gmail_report.py` — Markdown report citing source artefacts.
- `email-triage` skill hardened against prompt injection.
- `/email-report [account]` end-to-end working.
- Tests passing.

---

## NEXT

### Phase 4 — CalendarOS MVP

Build Calendar fetch, normalise, brief skill invocation, and `/calendar-brief [account] [today|tomorrow|week]`.

Acceptance criteria:
- Fetches events for requested period.
- Handles all-day events and conflicts.
- Produces Markdown brief with prep needs and focus gaps.

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
