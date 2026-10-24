# Spec 6: Wellness, the first vertical

## Purpose

Prove the grid on the area with the most urgency and the least external intake.
Wellness covers health, fitness, nutrition and sleep. Its intake is `/log`; its
memory is habit goals and commitments; its output is the first section of the weekly
review and a line in the morning brief.

## Scope

- Structured `/log` types for wellness with units and validation.
- `gogos/core/wellness.py`: deterministic weekly summary from the journal.
- Habit goals and the at-risk rule wired into the briefs.
- `life/wiki/wellness/` seed pages (empty templates, no invented facts).

## Non-scope

Apple Health or any device import (spec 11, and only after logging has held for
several weeks). Nutrition plans as documents (those are workspaces). Medical advice
of any kind: the system reports what was logged against what was committed.

## Design

### Log types

| type | required | optional | unit | area |
|---|---|---|---|---|
| `workout` | text (what) | `--value <minutes>`, `--kind run\|strength\|cycle\|swim\|walk\|other`, `--intensity 1-5` | min | wellness |
| `sleep` | `--value <hours>` | `--quality 1-5`, text | h | wellness |
| `weight` | `--value <kg>` | | kg | wellness |
| `energy` | `--value 1-5` | text, `--when am\|pm` | score | wellness |
| `meal` | text | `--kind breakfast\|lunch\|dinner\|snack`, `--tags` | | wellness |
| `symptom` | text | `--severity 1-5` | | wellness |

`/log` validates ranges and units (spec 2's generic path) and rejects a `sleep` with
no value. Area is inferred. Shorthand is accepted by the command: `/log sleep 7.5`,
`/log energy 3 pm`, `/log workout run 5k 30`.

### Habit goals

`registers/goal/` items with `kind: habit`, `target_per_week`, and a new field
`counts: [log types]` naming which journal types count as "kept" for this habit
(`["workout"]`; or `["sleep"]` with `--min-value 7`). A commitment linked to the goal
also counts when kept. Two starter goals are created by the owner on day one (the
spec does not invent them).

### `gogos/core/wellness.py`

```
summary(week) -> dict
  per habit goal: target, kept (journal events matching `counts` + kept commitments), scheduled (open commitments this week), at_risk (spec 2 rule)
  sleep: nights logged, mean hours, nights under 7
  energy: entries, mean am/pm, days with both
  weight: first/last/delta if ≥2 entries
  workouts: count, minutes, by kind
  streaks: consecutive days with a workout or sleep log
  unlogged_days: dates with no wellness event
```

Written into `inputs.json` by `brief.py` for start-day and weekly. Pure function over
journal events; tested with synthetic events.

### In the briefs

- **`/start-day` Habits section** (spec 5): per habit goal, `kept/target this week`,
  `at risk` when the rule fires, and the suggested next slot from today's focus gaps
  ("90 min free 12:00; run?"). Suggestion only; a commitment is created on yes.
- **`/weekly-review` Wellness first**: the summary above in prose, then observations
  (what moved vs last week), then at most one inference labelled as such ("energy
  lower on days after fewer than 6.5 h sleep; 4 of 5 such days this week"). No
  medical interpretation; where a trend looks concerning the review says "worth
  raising with a professional" and nothing more.

### Wiki seeds

`life/wiki/wellness/_index.md` (what this area tracks and why), `routine.md`
(training plan, owner-written), `providers.md` (GP, dentist, physio: facts and
renewal links). Templates only; no content is generated.

## Acceptance criteria

- [ ] `/log sleep 7.5` and `/log sleep` (no value) behave as specified.
- [ ] A habit goal with target 3, two workouts logged and one open workout commitment
      this week is not at risk; with no open commitment it is.
- [ ] The weekly summary over a synthetic week reports every field above and lists
      unlogged days.
- [ ] `/start-day` shows `kept/target` per habit and offers a slot only when a focus
      gap exists.
- [ ] `/weekly-review` opens with Wellness and contains at most one labelled
      inference.

## Tests

`tests/test_log_wellness.py` (validation, shorthand, inference of area),
`tests/test_wellness_summary.py` (every summary field, streaks, at-risk rule,
`counts` with `--min-value`).

## Open questions

- Does nutrition want its own log shape (calories, macros) or is `meal` text plus
  tags enough for now? Spec assumes text until a real need shows.
