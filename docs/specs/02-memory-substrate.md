# Spec 2: memory substrate

## Purpose

Give GogOS a place to keep what it learns: the `life/` tree, the owner's `me/`
profile, register items with a lifecycle, an append-only journal, and the `/log`
command. Every later slice reads or writes these. This is the slice that turns a
pipeline into an assistant.

## Scope

- `life/` and `me/` skeletons with the gitignore rules.
- Front matter schemas for every content type (this spec is the schema's home).
- `gogos/core/registers.py`: parse, validate, index, change status with history.
- `gogos/core/journal.py`: append, read, and the `/log` command.
- `me/profile.md`, `me/areas.json`, `me/themes.md`.
- Kanban projection of open commitments (sub-slice 2b, after the store).
- Absorb and delete `prototypes/goals_store/`.

## Non-scope

Any LLM step (spec 4). Connectors (spec 3). The briefs (spec 5). Wellness-specific
`/log` types beyond the generic shape (spec 6).

## Design

### Directories

```
me/
  profile.md        me/ is tracked
  areas.json
  themes.md
life/
  inbox/            gitignored (.gitignore: /life/inbox/)
  wiki/<area>/      tracked; wiki/people/ for people pages
  registers/<kind>/ tracked; _index.md per kind, _index.json at registers/
  journal/          tracked; YYYY-MM-DD.jsonl
  workspaces/       tracked
  reports/          tracked
.core/storage/      gitignored (already; .core/config/ stays tracked except secrets/ and accounts.json)
```

`gogos/core/paths.py` gains `LIFE_ROOT`, `ME_ROOT`, `inbox_dir()`, `wiki_dir(area)`,
`registers_dir(kind)`, `journal_file(date)`, `workspace_dir(slug)`, `reports_dir(kind,
date)`. `storage_path` stays for `.core/storage`.

### Front matter: base schema (every file under `life/` except `inbox/` and `journal/`)

```yaml
---
title: <human-readable>
type: wiki | register | workspace | report | profile
status: <per type>
area: wellness | finance | growth | family | home | work | none
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: []
sensitivity: <optional free label, e.g. family-health; descriptive only>
---
```

**wiki**: `section: <area or people>`, `confidence: high|medium|low`, `related: []`
(wikilinks). People pages add `birthday: MM-DD|none`, `last_contact: YYYY-MM-DD|none`
(written by the last-contact script in spec 9), `channels: []`.

**workspace** (`_workspace.md` index file): `goal`, `deadline: YYYY-MM-DD|none`,
`links: []`, `status: active|review|archived`.

**report**: `kind: start-day|end-day|weekly|council`, `period`, `sources: []`,
`status: draft|review|final`, `superseded_by: <path>|none`. A `final` report is
immutable; corrections are a dated `## Amendment YYYY-MM-DD` section or a superseding
file.

**profile**: `validation: provisional|confirmed`, `last_validated`, `content_approved:
YYYY-MM-DD|false`.

### Register items

Path `life/registers/<kind>/<slug>.md` with the kind singular (`registers/goal/`,
`registers/commitment/`), matching the `register:` field; slug kebab-case, never reused. Front matter:
base schema with `type: register`, `register: <kind>` (singular), `review_by:
YYYY-MM-DD|none`, `source: <path or [[wikilink]]>`, `related: []`, plus:

| kind | statuses | kind fields |
|---|---|---|
| `goal` | `active · achieved · paused · dropped` | `kind: outcome\|habit`, `priority: 1\|2\|3`, `target_per_week: int\|none` (habit only) |
| `commitment` | `open · kept · missed · dropped` | `due: YYYY-MM-DD[THH:MM]`, `goal: <slug>\|none`, `nudge_count: int` |
| `waiting` | `open · received · dropped` | `owed_by: <name or [[people/x]]>`, `asked_on: YYYY-MM-DD`, `channel: email\|chat\|in-person\|other`, `nudge_count: int` |
| `renewal` | `open · renewed · cancelled · expired` | `expires: YYYY-MM-DD`, `lead_days: int` (default 60; `review_by` = expires minus lead_days), `provider`, `amount: <text>\|unknown` |
| `occasion` | `open · done · skipped` | `date: MM-DD\|YYYY-MM-DD`, `person: [[people/x]]`, `recurrence: yearly\|once` |
| `decision` | `pending · reviewed` | `decision_date`, `confidence: high\|medium\|low`, `success_signal: <text>`, `outcome: pending\|helped\|did-not-help\|inconclusive\|not-reviewed`, `superseded_by: <path>\|none` |
| `parked` | `parked · revived · dropped` | `revisit_by: YYYY-MM-DD`, `origin: <path>` |

Body: free text, then a mandatory `## History` section, one line per event:
`- 2026-10-23T08:14:02Z created` · `- …Z status open → kept` · `- …Z due 2026-10-24 →
2026-10-27 (moved)` · `- …Z nudged (2)`. Derived values (`moved_count`, days
overdue) are computed from history, never stored.

**Rules carried from the goals prototype:** an outcome goal with no open commitment
is "idle"; a habit goal is "at risk" in a week when `kept_this_week < target_per_week`
and `open_commitments_this_week < target_per_week - kept_this_week`; a commitment
moved twice or more is a "renegotiate" candidate; a waiting item nudged twice and
still open is "ignored".

### `gogos/core/registers.py`

```
load(kind=None) -> list[Item]            parse + validate; invalid file = error with path and field
create(kind, title, area, **fields) -> Path   slug from title, collision → suffix -2
set_status(path, new_status, note="")     append history line, update `updated`, rewrite front matter only
set_field(path, field, value)             e.g. due; appends history "field old → new"
nudge(path)                               nudge_count += 1, history line
index() -> Path                           writes registers/<kind>/_index.md per kind and registers/_index.json
derived(item) -> dict                     moved_count, days_overdue, at_risk, idle, ignored
```

`_index.md` per kind: open items by `review_by` ascending, overdue flagged, then the
rest. `_index.json`: `{generated_at, today, open: [...], closed: [...]}`; each record is
the item's front matter plus `ref`, `slug`, `open` and `derived`. Consumers read `open`;
`closed` is there so "kept this week" needs no markdown parsing. The kind is the
`register` field (a goal's own `kind` is outcome or habit). This is what the briefs
read so they never parse markdown. CLI: `python -m gogos.core.registers index|list
<kind>|create <kind> --title … --area … [--field v]|status <path> <status>`.

Writes are tmp + `os.replace`. Concurrent writers (two Claude sessions) cannot
corrupt a file; the last writer wins on the same item, which is acceptable for a
single owner.

### Journal

`life/journal/YYYY-MM-DD.jsonl` (date from `today()`), one JSON object per line:

```json
{"id":"01JB…","ts":"2026-10-23T08:14:02Z","type":"log.workout","area":"wellness",
 "text":"run 5k","value":30,"unit":"min","ref":null,"source":"cli","meta":{}}
```

- `id` ULID. `type` is dotted: `log.<kind>` for owner entries (`activity decision
  learning note workout sleep weight energy meal waiting commitment`), `register.created`,
  `register.status`, `apply.gmail`, `artefact.written`, `sync.run`, `council.held`.
- `ref` is a repo path (register item, report, approval record) when the event is
  about a file.
- Append with `O_APPEND` in one `write()` call; a line is never partially written.
- `gogos/core/journal.py`: `append(event) -> id`, `read(date) -> list`,
  `read_range(start, end)`, `summarise(date) -> dict` (counts by type and area,
  numeric values aggregated), CLI `python -m gogos.core.journal log <type> <text>
  [--area a] [--value v --unit u] [--ref path]` and `… read [date]`.
- `/log <type> <text>` command: parses, infers area from type where unambiguous
  (`workout sleep weight energy meal → wellness`, `learning → growth`), asks for area
  otherwise; `log waiting "X from Y"` also creates a `waiting` register item and sets
  `ref`; `log commitment "X by Friday"` creates a `commitment` with `due` parsed from
  the text (ask if ambiguous). Prints one line of confirmation.

### `me/`

- `me/profile.md`: type `profile`, `validation: provisional`. Sections adapted from
  ClientOS's PROFILE.md for a personal context: how I decide, how I want to be
  challenged, communication preferences, writing voice, personal failure modes, and
  a **validation log** table (one row per claim: provisional · confirmed · revised ·
  rejected). Seeded with placeholders, never with invented claims; the Steward seat
  states "provisional" until rows are confirmed.
- `me/areas.json`: `[{"id":"wellness","title":"Wellness","priority":1,"weekly_question":"…"}, …]`
  for the six areas. Read by the index, the briefs, `/process-inbox` routing and the
  health check.
- `me/themes.md`: dated quarterly themes (`## 2026-Q4: <theme>`), read by the Steward
  and `/weekly-review`.

### 2b. Kanban projection

`gogos/core/kanban.py`: `sync()` writes every open `commitment` to the Claude Code task
list dir named by `CLAUDE_CODE_TASK_LIST_ID=gogos` (set in `.claude/settings.json`
env), stamping the register path into `metadata.gogos_ref`; `reconcile()` reads the
dir back and, for a task marked completed whose `gogos_ref` points at an open
commitment, calls `set_status(path, "kept", note="kanban")`. Tasks without a
`gogos_ref` are listed as "inbox from kanban" candidates in the next brief, never
imported silently. A fixture of the real on-disk task format lives in
`tests/fixtures/kanban/`; a test fails loudly if a required key disappears.

### Absorbing the prototype

`prototypes/goals_store/` is deleted in this slice. Its `suggestions()` rules move
into `registers.derived()`; its README's unanswered "Verdict" is answered in the PR
description: two entities confirmed, both as register kinds.

## Acceptance criteria

- [ ] `life/` and `me/` exist with the layout above; `git check-ignore life/inbox/x`
      and `.core/storage/x` succeed; `life/wiki/x` and `.core/config/gmail/categories.json`
      do not (amended 2026-10-24 after PR #17: `.core/config/` is tracked, decoupled config).
- [ ] Creating a commitment, moving its due date twice, then marking it kept produces
      a file with four history lines and `moved_count == 2` in `_index.json`.
- [ ] A malformed register file fails `index()` with the path and the field named.
- [ ] `/log workout "run 5k" --value 30 --unit min` appends one line; two concurrent
      appends produce two intact lines.
- [ ] `/log waiting "invoice from Acme"` creates `registers/waiting/invoice-from-acme.md`
      and a journal event with `ref` pointing at it.
- [ ] `kanban.sync()` then deleting the task dir then `sync()` again reproduces it;
      `reconcile()` on a completed task sets the commitment `kept` with a history line.
- [ ] `prototypes/` is gone; its rules are tested under `tests/test_registers_*.py`.

## Tests

`tests/test_registers_schema.py`, `test_registers_lifecycle.py`,
`test_registers_index.py`, `test_registers_derived.py`, `test_journal.py`,
`test_log_command.py` (CLI), `test_kanban.py`, `test_paths_life.py`. All build a
synthetic `life/` in `tmp_path` via a fixture that monkeypatches `LIFE_ROOT`; none
reads the real tree.

## Open questions

- Should `commitment.due` accept a time, or dates only? Spec assumes optional time.
- `occasion.date` for yearly items is `MM-DD`; leap-day birthdays map to 02-28 in
  non-leap years. Acceptable.
