# GogOS v2 — re-architecture proposal

Status: **proposal, 2026-10-23**. Nothing here is built. ClientOS (`Amplivibes/client-os`,
v1.20.2) is the reference and is not modified; only GogOS changes.

## 0. The one-paragraph version

GogOS today is a well-engineered email pipeline (Python, 403 tests, safety gates in
code) with nowhere to put what it learns. ClientOS is a mature knowledge system
(markdown wiki, registers, agents by tier, a learning loop, a health check) with no
write-back engine and no tests of its reasoning outputs. GogOS v2 keeps GogOS's
plumbing and borrows ClientOS's shape: **Intake** (deterministic connectors and a
single inbox) → **Intelligence** (agents + skills reasoning over a compounding
memory, under one evidence contract) → **Execution** (gated write-back, generated
artefacts, local state changes). A **Council** sits inside Intelligence as the
on-demand, multi-perspective mode. Modules are **life areas**, not data sources.

## 1. What each system got right, and what the other lacks

| | GogOS (keep) | ClientOS (adopt) |
|---|---|---|
| Fetch | Python connectors with a privacy gate in code, multi-account OAuth, pytest | Single inbox as the front door; every source lands as a dated markdown digest |
| Reasoning | Deterministic classifier (zero tokens, reproducible); injection-hardened skills | Agents by model tier; skills never run directly; one evidence contract applied everywhere |
| Memory | — (none: reports are written and never read back) | Wiki (timeless facts) + registers (stateful items with lifecycle) + dated observations; `[[wikilinks]]`; front matter schemas |
| Write-back | Gated apply engine, inverse plan + undo, never-delete invariant, source-scan tests | — (read-only by design; no engine) |
| Automation | launchd fetch, SessionStart nudge | Reactive / proactive / ad hoc modes; fetch on a timer, LLM processing on demand |
| Governance | CLAUDE.md principles | `/learn` + LEARNINGS.md (record → propose → approve), health check, versioned releases + migrations, deny/ask/allow permission posture |
| Owner model | implicit | `profile/` (ExecutiveOS): how the owner thinks and wants to be challenged, claims marked provisional until confirmed |

Two things ClientOS explicitly rejected that GogOS v2 also should not do: a separate
`intelligence/` directory tree (layers are *responsibilities*, folders follow the
data's lifecycle), and self-modifying prompts (learning is recorded and proposed,
never auto-applied).

## 2. The three layers, as responsibilities

```
            INTAKE                    INTELLIGENCE                    EXECUTION
  sources → connectors → inbox   →   agents + skills + council   →   write-back (gated)
            (deterministic,           over MEMORY                     artefacts (briefs, docs)
             zero LLM)                (wiki · registers · journal)    local state (journal, registers)
                                            ▲                                │
                                            └────── feedback: /learn ────────┘
```

**Intake** owns: authentication, fetching, normalising, the privacy gate, dedup
ledgers, caps, and writing one digest per source per run into `life/inbox/`. No LLM
in this path, ever. Python, tested. Today's `gmail_fetch/normalise` and
`calendar_fetch/normalise` are already this; they gain a markdown digest writer.

**Intelligence** owns: turning digests into memory (`/process-inbox`), producing
briefs and reviews (`/start-day`, `/end-day`, `/weekly-review`), ranking
(`/prioritise`), and on-demand thinking (`/council`, `/brainstorm`). It reasons
*only* over what is already in the repo. Three standing agents by tier (Opus /
Sonnet / Haiku), skills invoked only through agents or commands, one rules file.
The deterministic email classifier stays here as the zero-token first pass; the LLM
handles only what rules cannot (the Review bucket, free text, transcripts).

**Execution** owns three distinct kinds of action, with different gates:

| Kind | Example | Gate |
|---|---|---|
| External write-back | Gmail label+archive, calendar write, send, post | Two-step approval file, inverse plan, undo. Existing engine, unchanged. |
| Artefact | Morning brief, weekly review, a strategy note, a council verdict | None (local file), but every artefact cites its inputs |
| Local state | Journal entry, register item status, commitment kept/missed | None, but append-only or history-preserving, and indexed deterministically |

## 3. Memory — the part GogOS is missing

This is the substrate that makes the loop compound. Three stores, each with a
deterministic index script and no LLM in the indexer:

- **`life/wiki/<area>/<subject>.md`** — timeless facts. "What's true." One subject
  per page, `confidence:` honest, `[[wikilinks]]`, provenance line.
- **`life/registers/<kind>/<slug>.md`** — stateful items with a lifecycle. "What needs
  attention and where it stands." Kinds: `goals`, `commitments`, `decisions`,
  `risks`. Base schema (`status`, `review_by`, `area`, `source`, `related`) plus 2–3
  fields per kind. This absorbs the goals/commitments prototype: a goal is a
  register item (`kind: outcome|habit`, `priority`), a commitment is a register item
  with `due` and `goal`. Status changes append to a `## History` section, never
  overwrite.
- **`life/journal/YYYY-MM-DD.jsonl`** — append-only events. "What happened." Written
  by `/log`, by Execution (every apply, every artefact, every register change), and
  by hooks. This is what `/end-day` and `/weekly-review` read. It replaces the
  earlier TaskOS JSONL plan and ActivityOS in one primitive.

Claude Code's task list (kanban) becomes a *projection* of open `commitments`,
synced and reconciled exactly as the Phase 5 plan described; the register is the
truth.

## 4. Modules are life areas

Rename from data sources to areas. Each area is a wiki section, a tag on register
items and journal events, a section in the briefs, and an owner of zero or more
intake sources. Proposed starting set, from what the configs already reveal
(finance feeds, family/school in the rubric, health, learning tracks, content):

| Area | Intake sources (now / later) | What the brief surfaces |
|---|---|---|
| `work` | gmail (work account), calendar, later Slack/Linear via ClientOS pattern | actions, meetings needing prep, commitments due |
| `family` | gmail (personal), calendar, WhatsApp export | school/admin actions, events, commitments |
| `health` | manual `/log workout`, later Apple Health export | habit goals vs. target, streaks, at-risk |
| `finance` | gmail (bank/insurer senders), later news feeds | bills/renewals (Action), market signals |
| `learning` | manual `/log learning`, later feeds | track progress, idle tracks |
| `content` | manual `/log content`, later LinkedIn/Substack bridge | pipeline state, commitments |

`.core/config/modules/registry.json` becomes `life/areas.json` (or front matter in
`me/`) and is actually read: by the health check, the briefs, and `/process-inbox`
routing. Drop the `XOS` suffixes in docs to match the code.

## 5. Directory layout

```
CLAUDE.md                     routing contract (short; points at the layers)
me/                           the owner: profile.md (how I think, want to be challenged,
                              voice), areas.json (life areas + priorities). Tracked.
gogos/                        Python. Intake + Execution engines. Tested.
  intake/    gmail/ calendar/ journal/ (later: health/ news/ whatsapp/)
  execution/ gmail_apply.py gmail_undo.py (later: calendar_write.py)
  core/      paths.py accounts.py auth/ journal.py registers.py (index) digests.py
.claude/
  rules/     reasoning-and-evidence-contract.md   (adapted from ClientOS, personal)
  agents/    chief-of-staff.md (opus) analyst.md (sonnet) gardener.md (haiku)
             council-chair.md (opus) + council perspectives (see §7)
  skills/    email-triage calendar-brief daily-brief reflection prioritisation
             wiki-update register-update council-position council-synthesis
  commands/  start-day end-day weekly-review process-inbox sync log
             council brainstorm prioritise email-apply email-undo learn health
  scripts/   health-check.sh registers-index.sh journal-index.sh
  settings.json                tracked deny/ask/allow posture
life/                         LOCAL-ONLY (one .gitignore rule). The memory.
  inbox/     digests from connectors + anything dropped by hand
  wiki/      <area>/<subject>.md
  registers/ goals/ commitments/ decisions/ risks/  (+ _index.md each)
  journal/   YYYY-MM-DD.jsonl
  workspaces/<slug>/           a piece of thinking in progress (council notes live here)
  reports/   start-day/ end-day/ weekly/            dated + latest-*
.core/                        LOCAL-ONLY machine plumbing, as today
  config/    accounts.json gmail/ calendar/
  storage/   raw/slim JSON, approvals/, auth/, ledgers
docs/        ARCHITECTURE.md LEARNINGS.md CHANGELOG.md
```

Two local-only trees on purpose: `life/` is human-readable knowledge you would
grieve losing; `.core/storage/` is machine state you could regenerate. Different
backup posture, same privacy boundary.

## 6. The loops (reactive, proactive, ad hoc)

| Mode | Trigger | What runs | LLM? |
|---|---|---|---|
| **Reactive** | `/sync [--source …]` or a digest dropped in `life/inbox/` | connectors (fetch) → `/process-inbox` (file, distil to wiki, promote register items, write journal events) | fetch: no · process: yes (Haiku files, Sonnet judges) |
| **Proactive** | launchd at ~07:30 | fetch only, zero LLM, leaves digests in the inbox; one macOS notification | no |
| | SessionStart hook | one-line nudge with counts; never runs the pipeline | no |
| | optional cloud scheduled task | ping only ("3 actions, 2 commitments due"); never the system of record | yes, but reads nothing private beyond counts |
| **Ad hoc** | `/start-day` | process-inbox if needed → brief across areas: attention items, schedule, commitments due, habits at risk, risks overdue | yes (Sonnet) |
| | `/log <type> <text>` | one journal event | no |
| | `/end-day` | journal + brief + registers → kept/slipped/decisions/tomorrow seed; updates commitment statuses on confirmation | yes (Sonnet) |
| | `/weekly-review` | the ClientOS weekly-brief pattern: diff against the previous review, decisions due for review carried forward until resolved, "what we can't see" always present | yes (Sonnet, escalates to Opus for judgement) |
| | `/email-apply`, `/email-undo`, `/email-loop` | unchanged gated engine | no |
| | `/council`, `/brainstorm` | §7 | yes |

The rule from ClientOS holds: **no LLM in the fetch path, and processing is never
scheduled** — knowledge is not rewritten without a human in the session. `/loop`
can drive a self-paced in-session cadence (e.g. re-run `/sync` every 30 minutes
during a working block) without changing that rule.

## 7. The Council

**What it is.** An on-demand mode of the Intelligence layer for questions that
deserve more than one lens: a decision you are weighing, an idea you want stress-
tested, a plan you want attacked before you commit. Not a daily tool; a deliberate one.

**What it is not.** Not fake experts, not consensus theatre, and not a replacement
for the standing agents. Perspectives are *lenses on the same evidence*, and the
output keeps disagreements visible.

**Shape.**

```
/council <question> [--seats strategist,skeptic,operator,…] [--context <workspace|area>]
```

1. **Frame.** The Chair (Opus) restates the question, pulls context from
   `me/profile.md`, the relevant `life/wiki/<area>/`, open registers, and any
   workspace named. Writes the brief all seats receive. Marks what is fact,
   reported claim, assumption, unknown (the evidence contract).
2. **Positions, in parallel.** Each seat is a subagent (Sonnet) with one standing
   lens and the same brief. Default seats: **Strategist** (second-order effects,
   optionality), **Skeptic** (what would have to be true; strongest case against),
   **Operator** (what it costs to run; what breaks first), **Steward** (the owner's
   stated goals and failure modes from `me/profile.md`; says when the plan contradicts
   them). Optional seats by area: **Finance**, **Health**, **Family**. Each returns:
   position, evidence relied on, the assumption it would most want checked, and a
   confidence with a reason.
3. **Cross-examination.** Each seat sees the others' positions once and may revise
   or sharpen its disagreement. One round only; more is theatre.
4. **Synthesis.** The Chair writes the council note: where the seats agree, where
   they genuinely disagree and *why* (different evidence, different values, or
   different risk appetite), a **ranked recommendation with its trade-off**, the
   decision required, and a review date.
5. **Record.** The note lands in `life/workspaces/<slug>/council-YYYY-MM-DD.md`. If
   you decide, a `registers/decisions/` item is created on confirmation with the
   success signal, so `/weekly-review` later asks whether it helped.

**`/brainstorm`** is the divergent sibling: same seats, no synthesis, no
recommendation — a ranked list of options and the question each one raises, written
to the workspace. Use it before a council, not instead of one.

**Model diversity (optional, later).** The "LLM council" idea in its strongest form
queries *different providers* and has them review each other. That is a real option
behind a Python `gogos/council/` adapter, but it sends the brief off-machine to
several vendors, which crosses principle 1. If added, it is opt-in per call
(`--providers`), shows exactly what leaves the machine, and asks first. Start with
lens diversity inside Claude; add model diversity when a council verdict is found
wanting for lack of it, not before.

## 8. Governance (small, early, cheap)

- **Rules.** `.claude/rules/reasoning-and-evidence-contract.md`, adapted: claim
  types, cite sources, state confidence with a reason, rank and recommend, test
  urgency, name the owner. Applied by every agent and skill.
- **Learning loop.** `/learn` + `docs/LEARNINGS.md` (record → propose → approve).
  Already proven in ClientOS; copy the mechanism verbatim.
- **Health check.** One script that checks structure, front matter, wikilinks,
  register schemas, the `life/` ignore rule, no credentials in the tree, and runs
  pytest. SessionStart banner states release debt in words.
- **Permissions.** Tracked `settings.json` with deny (credential stores, direct
  Google API calls outside the connectors, any send) / ask (push, rm, apply) /
  allow (reads, connectors, index scripts). ClientOS's file is a good template.
- **Tests.** pytest stays for Python. Add a bash `run-tests.sh` for the index and
  health scripts, building synthetic `life/` trees in a temp dir, never reading the
  real one.
- **Versioning.** Tag releases and keep a CHANGELOG once a second machine or a
  second person depends on it; before that it is overhead.

## 9. What changes for the existing code

| Today | v2 |
|---|---|
| `gogos/gmail/gmail_fetch,normalise` | `gogos/intake/gmail/` + a digest writer (`life/inbox/gmail-<account>-<date>.md`, metadata + snippet only — the privacy gate is unchanged) |
| `gogos/gmail/gmail_classify,rules,ledger,reconcile` | unchanged, Intelligence first pass; its output is also written into the digest so the Gardener never re-classifies what a rule decided |
| `gogos/gmail/gmail_apply,undo,loop` | `gogos/execution/` unchanged; applies also append a journal event; per-batch applied records (fix the overwrite bug) |
| `gogos/calendar/*` | `gogos/intake/calendar/` + digest writer; the calendar-brief skill reads the digest |
| `gogos/system/start_day.py` | stays as the deterministic assembler; the `/start-day` command adds the Intelligence pass over `life/` |
| `email-triage` skill (LLM classifier) | retired; `/email-report` uses the deterministic classifier like every other path |
| `daily-brief`, `reflection-coach`, `news-curator` stubs | rewritten with inputs, output schema, injection rule, in the shape of `calendar-brief` |
| `prototypes/goals_store/` | absorbed into `registers/goals` + `registers/commitments`; delete |
| `.core/config/modules/registry.json` | `me/areas.json`, read by health check and briefs |
| `docs/IMPLEMENTATION_PLAN.md` Phase 5–9 | replaced by §10 |

Auth stays GogOS's own OAuth (it needs `gmail.modify` for the apply engine and has
multi-account tests); ClientOS's `gog` CLI is read-only and would mean two auth
paths. Revisit only if a read-only-only deployment appears.

## 10. Build order (one small PR per slice)

0. **ADR.** Turn this proposal into `docs/ARCHITECTURE.md` v2 after review. Decide
   the open questions in §11.
1. **Fix the known defects first** (pyproject/egg-info, per-batch applied record,
   non-interactive auth for scheduled runs, one `today()`). Add CI. Half a day.
2. **Memory substrate.** `life/` skeleton, `me/profile.md` (provisional claims,
   validation log), register base schema + `registers-index`, `journal.py` + `/log`.
   Tests. This is the slice that changes the system's nature.
3. **Intake → inbox.** Digest writers for gmail and calendar; `/sync`; launchd
   fetch-only job replaces the current scheduler's classify+report.
4. **Intelligence core.** Rules file, three agents, `wiki-update` and
   `register-update` skills, `/process-inbox`. First real `life/wiki/` pages.
5. **The daily loop.** `/start-day` over memory, `/end-day`, `/weekly-review`.
   Decisions register with `review_by` and carried-forward reviews.
6. **Council.** Chair + four default seats, `/council`, `/brainstorm`, council note
   template, decision promotion on confirmation.
7. **Governance.** `/learn`, health check, permissions posture, bash tests.
8. **New intake per area**, each earned by a real need: health export, finance
   senders as their own digest, news feeds, WhatsApp.

Slices 2–5 are the executive-assistant core; 6 is the thing you asked for and
depends on 2 (it needs memory to be useful); 7 is cheap and can slot anywhere.

## 11. Open questions for you

1. **Tracked vs local for `me/`.** ClientOS tracks `profile/` so every instance
   knows the owner. GogOS has one instance. Tracking it is convenient for a second
   machine and risky if the repo is ever public. Recommendation: track it, keep the
   repo private, and put nothing in it you would not put in a CV.
2. **Email bodies.** ClientOS ingests bodies (capped, quoted history stripped)
   because commitments live in bodies. GogOS has a hard metadata-only gate.
   Keep the gate (recommended for personal mail, where the classifier does the job)
   or allow bodies for an allow-listed set of senders/threads, written only to
   `life/inbox/` and never to `.core/storage/`? This is the single biggest privacy
   decision in v2 and should be an ADR either way.
3. **Council seats.** Are the four defaults the right lenses for you? The Steward
   seat only works once `me/profile.md` has confirmed claims; until then it reasons
   from hypotheses and says so.
4. **Area set.** Is the table in §4 the right first cut, and which one is *not* a
   module (something you track but do not want the system to brief you on)?
