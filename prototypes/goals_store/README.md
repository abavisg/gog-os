# PROTOTYPE — goals & commitments store

**Throwaway.** Delete this directory (or absorb `store.py` into `gogos/goals/`)
once the question below has a verdict. Not wired to real storage; state is
in-memory; the clock is simulated.

## Run

```
.venv/bin/python prototypes/goals_store/tui.py
```

## The question

Are **goals** and **commitments** one entity or two? The bet: **two** —

- a **goal** is declared and directional: `kind ∈ outcome | habit`, priority,
  optional `target_per_week`, no completion date required;
- a **commitment** is a dated, checkable promise, optionally linked to a goal;
  keeping/missing/moving it appends to `history[]`, never rewrites.

The model passes only if all three consumers of the real store work off it
without contortions:

1. **Accountability loop** — `due_within`, `overdue`, `ignored` (overdue +
   ≥2 nudges), `suggestions` (moved ≥2× → renegotiate; ignored → drop-or-replan;
   missed → reschedule offer; idle goal → commit a next step; habit under
   weekly target → at-risk).
2. **Attention engine** — `attention_context()`: active goals by priority with
   their open commitments; the slim projection a ranking skill would receive.
3. **Audit** — every mutation appends to the entity's `history[]` with a UTC
   timestamp; `moved_count` is derived from history, not stored.

## Things to try

- `T` a few times: watch the Acme reply go due → overdue, and suggestions change.
- `n` the overdue insurance once more, then `T` — see it graduate to "ignored".
- `k` the Thursday gym session, then declare nothing else — the habit goal
  goes at-risk as the week rolls.
- Drop goal `g3` (`G`, then `dropped`) — its commitments stay; is that right,
  or should dropping a goal cascade?

## Verdict (fill in before deleting)

- [ ] Two entities confirmed / refuted:
- [ ] Suggestions rules that felt right / wrong:
- [ ] Schema changes discovered:
- [ ] What the attention context was missing:
