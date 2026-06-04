# Incremental Implementation Plan

## Rule

Build one module at a time. Do not start the dashboard. Do not add write-back until read-only workflows are proven.

## Phase 0: Claude Code Review

Model: Claude Opus 4.8

Prompt:

```text
Review the GogOS PRD and architecture. Challenge the scope. Identify the minimum viable rebuild path. Do not write code yet.
```

Done when Claude has identified risks and agrees the first implementation step is FoundationOS.

## Phase 1: FoundationOS

Model: Claude Sonnet 4.6

Build:

- Project folder structure.
- `.gitignore`.
- `.env.example`.
- Config loader.
- Storage path helper.
- Setup check script.
- Basic tests.
- `/setup-check` command.

Acceptance criteria:

- `python -m gogos.system.setup_check` runs.
- Required folders are created or validated.
- Missing credentials are reported clearly.
- No private files are committed.

## Phase 2: Google Auth Foundation

Model: Claude Sonnet 4.6

Build reusable Google OAuth helper, token storage per account, scope handling, `/login-google [account]`, and `/logout-google [account]` with confirmation.

Acceptance criteria:

- Login opens browser OAuth flow.
- Token is stored locally.
- Existing valid token is reused.
- Expired token refreshes.
- Logout deletes token only after confirmation.

## Phase 3: EmailOS MVP

Model: Claude Sonnet 4.6 for implementation.
Runtime models: Sonnet 4.6 for triage, Haiku 4.5 for report formatting.

Build Gmail fetch script, email normalisation schema, email categories config, triage rubric, `/email-report [account]`, and `email-triage` skill.

Acceptance criteria:

- Fetches inbox messages in metadata mode.
- Writes dated raw and normalised JSON.
- Produces triage JSON.
- Produces Markdown and HTML report.
- No write-back to Gmail.

## Phase 4: CalendarOS MVP

Model: Claude Sonnet 4.6

Build Calendar fetch script, event normalisation schema, `/calendar-brief [account] [today|tomorrow|week]`, and `calendar-brief` skill.

Acceptance criteria:

- Fetches events for requested period.
- Handles all-day events.
- Identifies conflicts and prep needs.
- Produces Markdown and HTML brief.

## Phase 5: TaskOS Local MVP

Model: Claude Sonnet 4.6

Build local task schema, `tasks.jsonl` or Markdown task file, `/task-add`, `/tasks-today`, `/task-done`, and carry-forward mechanism.

Acceptance criteria:

- Tasks can be added, listed, completed.
- Daily plan can consume tasks.

## Phase 6: BriefingOS MVP

Model: Claude Sonnet 4.6

Build `/morning-brief`, `daily-brief` skill, and aggregation from latest EmailOS, CalendarOS, and TaskOS outputs.

Acceptance criteria:

- One useful brief with top priorities, risks, schedule, and actions.
- Report references source artefacts.
- Handles missing modules gracefully.

## Phase 7: ActivityOS MVP

Model: Claude Sonnet 4.6 for implementation, Haiku 4.5 for simple summaries.

Build `/log [type] [text]`, daily JSONL log, and supported types: activity, decision, learning, workout, content, note.

Acceptance criteria:

- Appends only.
- Preserves timestamps.
- Can be consumed by ReflectionOS.

## Phase 8: ReflectionOS MVP

Model: Claude Sonnet 4.6

Build `/end-day` and `/weekly-review` reading daily logs, morning brief, email/calendar summaries.

Acceptance criteria:

- Produces completed/slipped/carry-forward summary.
- Identifies decisions and follow-ups.
- Produces tomorrow seed list.

## Phase 9: NewsOS MVP

Model: Claude Sonnet 4.6

Build feed config, `/news-brief [feed]`, manual source collection first, later automated search/API ingestion if desired.

Acceptance criteria:

- Configurable feeds exist.
- Summaries are relevant and source-linked.
- Noise is controlled.

## Phase 10: LearningOS, HealthOS, ContentOS Bridge

Model: Claude Sonnet 4.6

Build only after Morning Brief and Reflection loops work.

Acceptance criteria:

- These modules plug into briefs and reviews.
- They do not become isolated advice generators.

## Phase 11: Dashboard Decision

Model: Claude Opus 4.8

Only start after at least 2 weeks of useful command-line operation.

Decision criteria:

- Which reports are actually used?
- Which commands are repeated daily?
- Which data deserves a UI?
- Is a web app or desktop app justified?
