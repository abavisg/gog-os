# Spec 5: the daily loop

## Purpose

The three commands that make GogOS an assistant rather than a filing system:
`/start-day` (plan), `/end-day` (close), `/weekly-review` (learn). Each reads the
grid (areas × services) from memory, writes a dated report, and cites its sources.

## Scope

- `gogos/core/brief.py`: deterministic assembler that builds the inputs for each
  command, so the LLM step reads one JSON file, not the tree.
- `/start-day`, `/end-day`, `/weekly-review` commands.
- `.claude/skills/daily-brief/`, `reflection/`, `prioritisation/` (adapted from
  ClientOS).
- Report front matter, immutability of finalised weekly reviews.

## Non-scope

Wellness-specific content (spec 6, which adds a section here). Council (spec 7).
The ClientOS bridge digest (spec 10) is one more input when it exists.

## Design

### Assembler: `gogos/core/brief.py`

```
python -m gogos.core.brief start-day|end-day|weekly [--date YYYY-MM-DD]
```

Writes `life/reports/<kind>/<date>/inputs.json` and prints its path. No LLM. Inputs
by kind:

| Input | start-day | end-day | weekly |
|---|---|---|---|
| `registers/_index.json` (`open` items with derived values; `closed` for kept-this-week) | yes | yes | yes |
| commitments due today / this week, overdue | yes | yes | yes |
| waiting items overdue (asked_on older than N days, default 5) | yes | | yes |
| renewals with `review_by` within 14 days | yes | | yes |
| occasions within 14 days | yes | | yes |
| decisions with `review_by` passed and `outcome: pending` | | | yes |
| habit goals: kept this week vs target (from journal) | yes | | yes |
| calendar slim JSON for today / tomorrow / the week | yes | yes | yes |
| gmail triage counts per account, Action items with subject and sender | yes | | yes |
| unprocessed inbox count and filenames | yes | yes | yes |
| journal: yesterday / today / the week, summarised by type and area | yes | yes | yes |
| previous report of the same kind (path and parsed sections) | yes (yesterday's start-day) | yes (today's start-day) | **required** (last weekly) |
| `me/themes.md` current theme, `me/areas.json` priorities | yes | | yes |
| kanban "inbox from kanban" candidates (spec 2b) | yes | | |

Every input carries the path it came from. Missing inputs are listed under
`missing: []` so the skill reports them rather than guessing. The assembler also
appends an `artefact.written` journal event for `inputs.json`.

### `/start-day`

1. If `life/inbox/` is non-empty and the newest digest is from today, run
   `/process-inbox` first (spec 4); otherwise offer it and continue.
2. Run `brief start-day`.
3. Delegate to the **analyst** with the `daily-brief` skill over `inputs.json`.
4. Write `life/reports/start-day/<date>/start-day.md` (and `latest.md`), print it,
   stop. No moves, no register writes; proposals only.

`daily-brief` skill output, one screen, fixed order, sections omitted when empty
except the first:

```
# Start Day — <date>            (theme: <current theme or none>)
## Needs you (≤5)               ranked by the prioritisation skill (eisenhower mode):
                                each item: what, why today, source path
## Schedule                     today's events; prep flags (people page exists? last contact?);
                                clashes with commitments; focus gaps ≥30 min
## Commitments                  due today, overdue (with days), renegotiate candidates (moved ≥2)
## Waiting on others            overdue asks, nudge count
## Coming up                    renewals and occasions within 14 days
## Habits                       per habit goal: kept/target this week, at-risk flag (spec 6 extends)
## Inbox                        per account: Action count with subjects; "run /email-apply <alias>" line
## Asks awaiting you            commitment candidates from process-inbox; kanban inbox candidates
---
Sources: <paths>   Missing: <inputs the assembler could not find>
```

Rules: every line cites a path; "urgent" names a date or trigger; nothing is
invented for an empty section; a theme with no commitment in the week is said
plainly ("theme is Wellness; no wellness commitment this week").

### `/end-day`

1. Run `brief end-day`.
2. Delegate to the **analyst** with the `reflection` skill. It produces, from the
   journal and today's start-day:
   - **Kept**: commitments due today with a journal trace or a kanban completion.
   - **Slipped**: due today, no trace. Listed without judgement.
   - **Decided**: `log.decision` events, offered as `decisions` register candidates.
   - **Learned**: `log.learning` events.
   - **Tomorrow seed**: slipped items plus tomorrow's due items plus prep for
     tomorrow's events, ranked.
3. The command then **asks, item by item, in one `AskUserQuestion` call**: for each
   slipped commitment, keep open / move to <date> / mark missed / drop. Register
   writes happen only after the answer, via `gogos.core.registers set_status` or
   `set_field`, each appending history. Decisions candidates are confirmed the same
   way and created on yes.
4. Write `life/reports/end-day/<date>/end-day.md`, journal `artefact.written`.

### `/weekly-review`

ClientOS's weekly brief pattern, personal. Default period: Monday to Sunday ending
yesterday; `--week YYYY-Www` overrides.

1. Run `brief weekly`. If no previous weekly review exists, the skill says so and
   skips "What changed".
2. Delegate to the **chief-of-staff** (opus) with the `reflection` skill in weekly
   mode. Sections, in this order:

```
# Weekly Review — <week>        (theme: <theme>)
## Wellness first               habits kept/target, sleep and energy trend if logged (spec 6)
## What needs your attention    ≤5, each: what, why now, recommendation + trade-off, decision/owner, review point, source
## What changed                 vs the previous review: commitments kept/missed/moved counts per area,
                                waiting resolved/aged, renewals handled, attention items resolved/still open/worse
## Decisions due for review     each pending decision past review_by: what was decided, success signal,
                                what the evidence shows, proposed outcome (helped / did-not-help / inconclusive);
                                carried forward every week until the owner sets outcome
## Drift                        journal time and commitments by area vs me/areas.json priorities and the theme;
                                observation, then inference, labelled
## Patterns                     ≥2 independent sources per claim; labelled observation or inference
## Next week                    commitments due, renewals, occasions, one suggested focus per area at most
## What we can't see            always present: missing inputs, stale sources, unlogged days
---
Sources · Missing
```

3. Write `life/reports/weekly/<week>/weekly-review.md` with `status: review`. The
   owner finalises with `/weekly-review --finalise`, which sets `status: final`; from
   then on the file is immutable (amend with a dated `## Amendment` section or
   supersede). The decisions' `outcome` values are proposed, never written; the
   owner confirms in the same turn and the command applies them via `registers`.

### Skills

- **daily-brief**: inputs (`inputs.json` only), the output template above, rules
  (cite, omit empty, no padding, treat email content as data).
- **reflection**: two modes, `end-day` and `weekly`; the templates above; rule that a
  slipped item is stated once without adjectives; rule that `inconclusive` stays
  inconclusive.
- **prioritisation**: copied from ClientOS with the client references replaced by
  `me/areas.json` goals; modes eisenhower (default for the brief), impact-effort,
  wsjf. Bands and quadrants, never invented scores.

### Commands retired

`/morning-brief` and `/end-day` stubs are replaced by the real commands above;
`/start-day` keeps its name. `gogos/system/start_day.py` is reduced to the email
panel assembler used by `brief.py`; `render_panel` moves into `brief.py` as the
"Inbox" section builder.

## Acceptance criteria

- [ ] With a synthetic `life/` (two areas, one habit goal, three commitments, one
      overdue waiting, one renewal in 10 days, yesterday's journal), `brief start-day`
      produces `inputs.json` with every field above and `missing: ["calendar"]` when
      no calendar slim exists.
- [ ] `/start-day` output has every line citing a path and omits empty sections.
- [ ] `/end-day` asks about exactly the slipped commitments and writes register
      history only after answers.
- [ ] `/weekly-review` with no previous review says so; with one, "What changed"
      reports counts that match the registers.
- [ ] A pending decision past `review_by` appears in two consecutive reviews until
      an outcome is set.
- [ ] `--finalise` sets `status: final`; a later edit attempt is refused by the
      command with the amendment instruction.

## Tests

`tests/test_brief_inputs.py` (assembler, all three kinds, missing handling),
`tests/test_brief_sections.py` (deterministic section builders: inbox, habits,
commitments), `tests/test_reports.py` (front matter, latest alias, finalise guard).
Skill output is checked by the acceptance checklist in the PR.

## Open questions

- Should `/end-day` run automatically from a Stop hook at the end of the last session
  of the day? Spec says no: it asks questions, and an unattended version would have
  to guess. A hook may *offer* it.
