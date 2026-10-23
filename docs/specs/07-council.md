# Spec 7: the Council

## Purpose

An on-demand, multi-perspective mode of the Intelligence layer for decisions and
plans that deserve more than one lens. Five seats argue over one evidence brief; a
Chair synthesises without manufacturing consensus; the verdict is recorded and later
reviewed. Proposal §7 is the design rationale; this spec is the build.

## Scope

- Agents: `council-chair` (opus) and five seats (sonnet).
- Skills: `council-position`, `council-synthesis`.
- Commands: `/council`, `/brainstorm`.
- Council note template; promotion of a verdict to a `decisions` register item;
  `parked` register entries from `/brainstorm`.

## Non-scope

Multi-provider model diversity (later, opt-in, behind `gogos/council/`). Automatic
convening from a brief. Any write by a seat.

## Design

### Agents

Seats: `.claude/agents/council-<seat>.md`, `model: sonnet`, `tools: Read, Glob, Grep`
(no Write, no Bash). Each file: the single mandate, what it reads first, the output
shape (below), and two or three named failure modes it exists to catch. Seats never
see the owner's current leaning; the Chair strips it from the brief.

| Seat | Mandate | Reads first |
|---|---|---|
| `council-strategist` | second-order effects, optionality, what the choice closes off | `registers/goals/`, area wiki |
| `council-skeptic` | the strongest case against; what would have to be true; the assumption most likely false | the brief and every path it cites |
| `council-operator` | running cost, what breaks first, the first two weeks in practice | `life/journal/` last 4 weeks, open commitments |
| `council-steward` | argues only from the owner's stated goals, themes and failure modes | `me/profile.md`, `me/themes.md`, goals |
| `council-historian` | prior decisions, their recorded confidence and outcomes, journal patterns | `registers/decisions/`, `life/reports/weekly/` |

Optional area seats `council-finance`, `council-wellness`, `council-family` share
one template with the area substituted; created on first use of `--seats +<area>`.

Chair: `.claude/agents/council-chair.md`, `model: opus`, `tools: Read, Glob, Grep,
Write`. The only writer. Applies the rules file strictly; may not report agreement
that was not in the positions; must name the cause of each disagreement.

### Seat output shape (`council-position` skill)

```
## <Seat>
**Position** (two sentences)
**Evidence** – paths, with the claim each supports
**The assumption I most want checked**
**Confidence** high|medium|low, because …
**What would change my mind**
**Provisional** – present only if reasoning from unconfirmed profile claims
```

Cross-examination round: each seat receives the other positions and returns either
`unchanged`, or a revised block with a one-line reason.

### `/council <question> [--seats +a,-b] [--context <workspace-slug|area>] [--no-cross]`

1. **Frame** (Chair). Resolve `--context`: a workspace slug loads its
   `_workspace.md` and `notes/`; an area loads its wiki index and open registers.
   Write `life/workspaces/<slug>/council-<date>-brief.md`: the question in one
   sentence; decision type (reversible / not); deadline if any; facts (cited),
   reported claims, assumptions, unknowns; what the memory does not contain. Strip
   any statement of the owner's preference from the prompt before it reaches seats.
   The slug is derived from the question or taken from `--context`; a new workspace
   is created from the template if none exists.
2. **Positions**. Launch the seats in parallel (one Agent call per seat, same brief).
   Default seats: the five above; `--seats` adds or removes.
3. **Cross-examination** (skipped with `--no-cross`). One round, parallel.
4. **Synthesis** (Chair, `council-synthesis` skill) →
   `life/workspaces/<slug>/council-<date>.md`:

```
---  report front matter, kind: council, status: review, sources: [brief, positions] ---
# Council — <question>
## Where the seats agree
## Where they disagree, and why          cause per item: evidence | values | risk appetite
## Recommendation                        ranked; the trade-off accepted; evidence it rests on
## Decision required                     what, by whom (the owner), by when
## Review point                          date and the signal that would show it worked
## What the council could not see
## Positions                             the five blocks, verbatim, after cross-examination
```

5. **Record**. Journal `council.held` with `ref`. The command then asks: *Decided
   (create a decision item) / Park (parked item with revisit date) / Leave as a note*.
   On "Decided": `registers/decisions/<slug>.md` with `decision_date`, `confidence`
   (the Chair's), `success_signal` (from Review point), `review_by`, `source` pointing
   at the council note. On "Park": `registers/parked/` with `revisit_by` and `origin`.

### `/brainstorm <topic> [--seats …] [--context …]`

Same framing; seats return **options** (title, one line, the question it raises,
one path if any) instead of positions; no cross-examination. The Chair dedups,
groups by theme, ranks nothing, and writes
`life/workspaces/<slug>/brainstorm-<date>.md`. The command offers to park any
option (`registers/parked/`). Use before a council on a wide question.

### Cost and limits

Default run: 1 Chair frame + 5 positions + 5 cross + 1 synthesis = 12 calls, two of
them Opus. `--no-cross` halves the seat calls. The command prints the seat count
before launching. Positions are capped at 300 words each by the skill.

## Acceptance criteria

- [ ] Health check: every `council-*` agent has `model: sonnet` and no Write/Bash;
      `council-chair` has `model: opus`; no skill carries `model:`.
- [ ] `/council "lease or buy the next car" --context car-2027` creates the brief with
      the owner's stated preference absent, five position files or sections, a
      synthesis with every section present, and a `council.held` journal event.
- [ ] Choosing "Decided" creates a decision item whose `source` resolves and whose
      `review_by` is the synthesis's review point.
- [ ] `/weekly-review` lists that decision when `review_by` passes (spec 5).
- [ ] `/brainstorm` produces grouped options with no ranking and offers parking.
- [ ] A run where all seats agree is marked by the Chair as "unanimous: treat with
      suspicion" in the synthesis.

## Tests

Markdown and agent files are validated by the health check (spec 8). A synthetic
workspace under `tests/fixtures/workspaces/` supports a manual acceptance run
recorded in the PR.

## Open questions

- Should the Steward be allowed to see the owner's leaning (it argues from the
  profile anyway)? Spec says no; the leaning reaches no seat.
