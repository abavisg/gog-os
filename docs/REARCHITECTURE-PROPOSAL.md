# GogOS v2: re-architecture proposal

Status: **proposal with decisions recorded, 2026-10-23**. Nothing here is built.
ClientOS (`Amplivibes/client-os`, v1.20.2) is the reference and is not modified;
only GogOS changes. Open questions from the first draft were settled with the owner
on 2026-10-23 and are recorded in §12.

## 0. The one-paragraph version

GogOS today is a well-engineered email pipeline (Python, 403 tests, safety gates in
code) with nowhere to put what it learns. ClientOS is a mature knowledge system
(markdown wiki, registers, agents by tier, a learning loop, a health check) with no
write-back engine. GogOS v2 keeps GogOS's plumbing and borrows ClientOS's shape:
**Intake** (deterministic connectors and a single inbox) → **Intelligence** (agents
and skills reasoning over a compounding memory, under one evidence contract) →
**Execution** (gated write-back, generated artefacts, local state changes). A
**Council** sits inside Intelligence as the on-demand, multi-perspective mode.
Modules are **life areas**; executive-assistant services are **capabilities** that
apply to every area.

## 1. What each system got right, and what the other lacks

| | GogOS (keep) | ClientOS (adopt) |
|---|---|---|
| Fetch | Privacy gate in code, multi-account, pytest | Single inbox as the front door; every source lands as a dated markdown digest; `gog` CLI with keyring tokens and a runtime read-only guard |
| Reasoning | Deterministic classifier (zero tokens, reproducible); injection-hardened skills | Agents by model tier; skills never run directly; one evidence contract applied everywhere |
| Memory | none (reports are written and never read back) | Wiki (timeless facts) + registers (stateful items with lifecycle) + dated observations; `[[wikilinks]]`; front matter schemas |
| Write-back | Gated apply engine, inverse plan + undo, never-delete invariant, source-scan tests | none (read-only by design) |
| Automation | launchd fetch, SessionStart nudge | Reactive / proactive / ad hoc modes; fetch on a timer, LLM processing on demand |
| Governance | CLAUDE.md principles | `/learn` + LEARNINGS.md (record → propose → approve), health check, versioned releases + migrations, deny/ask/allow permission posture |
| Owner model | implicit | `profile/`: how the owner thinks and wants to be challenged, claims provisional until confirmed |

Two things ClientOS explicitly rejected that GogOS v2 also does not do: a separate
`intelligence/` directory tree (layers are *responsibilities*; folders follow the
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

**Intake** owns authentication, fetching, dedup ledgers, caps, and writing one digest
per source per run into `life/inbox/`. No LLM in this path, ever. Deterministic,
tested. Connectors are the ClientOS Gmail and Calendar connectors (via `gog`),
adopted as they stand, plus `/log` for manual capture.

**Intelligence** owns turning digests into memory (`/process-inbox`), producing
briefs and reviews (`/start-day`, `/end-day`, `/weekly-review`), ranking
(`/prioritise`), and on-demand thinking (`/council`, `/brainstorm`). It reasons
*only* over what is already in the repo. Three standing agents by tier (Opus /
Sonnet / Haiku), skills invoked only through agents or commands, one rules file.
The deterministic email classifier stays as the zero-token first pass; the LLM
handles only what rules cannot (the Review bucket, free text, bodies).

**Execution** owns three kinds of action, with different gates:

| Kind | Example | Gate |
|---|---|---|
| External write-back | Gmail label + archive, later calendar writes | Two-step approval file, inverse plan, undo. Existing engine, re-pointed at `gog`. |
| Artefact | Morning brief, weekly review, a council note, a nutrition plan | None (local file), but every artefact cites its inputs |
| Local state | Journal entry, register status, commitment kept or missed | None, but append-only or history-preserving, and indexed deterministically |

## 3. Memory: the part GogOS is missing

Three stores, each with a deterministic index script and no LLM in the indexer:

- **`life/wiki/<area>/<subject>.md`**: timeless facts. "What's true." One subject per
  page, `confidence:` honest, `[[wikilinks]]`, provenance line, never a copied email
  body. `life/wiki/people/<name>.md` is the substrate for meeting prep, occasions
  and last-contact; it is not an area and has no weekly section.
- **`life/registers/<kind>/<slug>.md`**: stateful items with a lifecycle. "What needs
  attention and where it stands." Base schema (`status`, `review_by`, `area`,
  `source`, `related`, `sensitivity` optional) plus two or three fields per kind.
  Status changes append to a `## History` section, never overwrite.
- **`life/journal/YYYY-MM-DD.jsonl`**: append-only events. "What happened." Written
  by `/log`, by Execution (every apply, every artefact, every register change), and
  by hooks. `/end-day` and `/weekly-review` read it.

Register kinds, each an executive-assistant service built once and tagged by area:

| Kind | Service it implements | Fed by |
|---|---|---|
| `goals` | direction per area; habit goals carry `kind: habit`, `target_per_week` | you |
| `commitments` | "you said you'd…", with `due` and optional `goal` | you, `/end-day`, process-inbox |
| `waiting` | follow-ups owed *to* you | sent mail, `/log waiting` |
| `renewals` | expiries and renewals, `review_by` ahead of the date | the classifier's financial / civic / insurer rules, you |
| `occasions` | birthdays, anniversaries, dated gestures | `people/` wiki |
| `decisions` | what was decided, confidence at the time, `review_by`, `outcome` | council, you |
| `parked` | "not now" with a revisit date | `/brainstorm`, you |

This absorbs `prototypes/goals_store/` (goals + commitments) and the Phase 5 TaskOS
plan. Claude Code's task list (kanban) becomes a *projection* of open commitments,
synced and reconciled as that plan described; the register is the truth.

## 4. The grid: areas × services

Areas are rows. Services are columns. Every cell is meaningful ("renewals in Home",
"commitments in Wellness"), which is why services are capabilities, not verticals,
and why **Plan is a command, not a place**: `/start-day` reads the whole grid and the
prioritisation skill collapses it to the five things that need you today.

### Areas (decided 2026-10-23)

| Area | Covers | Weekly question | Intake |
|---|---|---|---|
| **Wellness** | health, fitness, nutrition, sleep | Am I keeping the habits, and is anything trending wrong? | `/log workout\|sleep\|weight\|energy\|meal`; Apple Health export later, only once logging has held |
| **Finance** | budgeting, cash flow, savings, investments, retirement, renewals | What's due, what renewed silently, how are positions? | bank / insurer senders (already classified), you; feeds later |
| **Growth** | learning, skills, reading | Which tracks moved, which stalled, what did I learn? | `/log learning`, reading list |
| **Family** | partner, children, school, pets | What's coming, what did I promise, what needs a parent decision? | personal Gmail, calendar, WhatsApp export |
| **Home** | house, utilities, insurance, car, pool, documents | What's expiring, broken, or about to cost money? | Gmail (civic / financial rules), calendar, you |
| **Work** | *your obligations only*: commitments, meetings, waiting-ons | What needs me, what am I waiting on? | work Gmail, calendar, ClientOS bridge (§10) |

Not areas: **People** (the `people/` wiki, serving prep and occasions); **Two
countries** (a tag on Home and Finance items); **Mobility** (Home); **Voice /
content** (parked: most output relates to the fractional business, which is
FractionalOS territory); **Self / direction** (`me/`, the Steward seat, and what
`/weekly-review` answers by comparing the journal against goals).

### Workspaces

A piece of thinking in progress lives in `life/workspaces/<slug>/` (ClientOS's
pattern): a nutrition plan for a child, a car lease-vs-buy decision, pool
maintenance research. Disposable; the residue is not. Bring a task into GogOS when
**its outcome produces a recurring obligation or a decision you'll want to
remember**; a one-off answer can stay wherever you asked it.

## 5. Directory layout

```
CLAUDE.md                     routing contract (short; points at the layers)
me/                           TRACKED. profile.md (how I think, how to challenge me, voice;
                              claims provisional until confirmed), areas.json, themes.md
gogos/                        TRACKED. Python. Intake + Execution engines. Tested.
  intake/    gmail/ calendar/ journal/ clientos/ (later: health/ whatsapp/)
  execution/ gmail_apply.py gmail_undo.py (later: calendar_apply.py)
  core/      paths.py journal.py registers.py digests.py
.claude/                      TRACKED.
  rules/     reasoning-and-evidence-contract.md (adapted from ClientOS, personal)
  agents/    chief-of-staff (opus) analyst (sonnet) gardener (haiku)
             council-chair (opus) council-{strategist,skeptic,operator,steward,historian} (sonnet)
  skills/    triage calendar-brief daily-brief reflection prioritisation wiki-update
             register-update meeting-prep council-position council-synthesis
  commands/  start-day end-day weekly-review process-inbox sync log
             council brainstorm prioritise email-apply email-undo learn health
  scripts/   health-check.sh registers-index.sh journal-index.sh last-contact.sh
  settings.json                tracked deny / ask / allow posture
life/                         the memory
  inbox/     GITIGNORED. digests from connectors (may contain mail bodies) + drops
  wiki/      TRACKED.  <area>/<subject>.md, people/<name>.md
  registers/ TRACKED.  goals/ commitments/ waiting/ renewals/ occasions/ decisions/ parked/
  journal/   TRACKED.  YYYY-MM-DD.jsonl
  workspaces/TRACKED.  <slug>/
  reports/   TRACKED.  start-day/ end-day/ weekly/   (dated + latest-*)
.core/                        GITIGNORED. machine plumbing
  config/    accounts.json gmail/ calendar/
  storage/   raw/slim JSON, approvals/, ledgers
docs/        ARCHITECTURE.md LEARNINGS.md CHANGELOG.md
```

**Decoupling, as three checks the health check runs:** the system (`gogos/`,
`.claude/`, `docs/`) contains no personal fact (could it ship verbatim to someone
else?); the system runs against an empty `life/` and `me/` (packaging smoke test);
nothing under `life/inbox/` or `.core/` is ever tracked (assertion, not convention).
`life/` can later become its own nested private repo without touching the system.

## 6. The loops

| Mode | Trigger | What runs | LLM? |
|---|---|---|---|
| **Reactive** | `/sync [--source …]` or a file dropped in `life/inbox/` | connectors (fetch) → `/process-inbox` (file, distil to wiki, promote register items, write journal events) | fetch: no · process: yes (Haiku files, Sonnet judges) |
| **Proactive** | launchd at ~07:30 | fetch only, zero LLM, leaves digests in the inbox; one macOS notification | no |
| | SessionStart hook | one-line nudge with counts; never runs the pipeline | no |
| | optional cloud scheduled task | a ping with counts only; never the system of record | yes, but sees only counts |
| **Ad hoc** | `/start-day` | process-inbox if needed → the grid → prioritisation → one screen: needs you, schedule, commitments due, waiting-ons overdue, habits at risk, renewals near | yes (Sonnet) |
| | `/log <type> <text>` | one journal event; also opens a `waiting` or `commitment` item when the type says so | no |
| | `/end-day` | journal + brief + registers → kept / slipped / decisions / tomorrow seed; names slipped items without judgement | yes (Sonnet) |
| | `/weekly-review` | the ClientOS weekly-brief pattern: diff against the previous review, decisions due for review carried forward until resolved, drift against `me/themes.md`, "what we can't see" always present; Wellness before output | yes (Sonnet, escalates to Opus) |
| | `/email-apply`, `/email-undo`, `/email-loop` | the gated engine, now via `gog` | no |
| | `/council`, `/brainstorm` | §7 | yes |

No LLM in the fetch path, and processing is never scheduled: knowledge is not
rewritten without a human in the session. `/loop` can drive an in-session cadence
without changing that rule.

## 7. The Council

**When.** A decision you keep deferring; a plan before you commit money, time or a
relationship to it; an idea you suspect you like too much. Not for "what should I do
today". Expect four to six model calls; it is deliberately more expensive than a
normal command.

**Seats.** Each is a `.claude/agents/council-<seat>.md` on Sonnet with Read / Glob /
Grep only (seats cannot write), one fixed mandate, one required output shape. The
Chair is Opus and is the only writer.

| Seat | Mandate | Reads | Guards against |
|---|---|---|---|
| **Strategist** | second-order effects, optionality, what this closes off | goals, area wiki | the plan that solves today and costs next year |
| **Skeptic** | the strongest case against; what would have to be true; the assumption most likely false | the brief and its cited evidence | motivated reasoning |
| **Operator** | what it costs to run, what breaks first, what the first two weeks look like | journal, commitments | plans that assume a version of you with more time |
| **Steward** | argues only from your stated goals, themes and named failure modes | `me/`, goals | drift from what you said you wanted |
| **Historian** | "we have been here before": prior decisions, their recorded confidence and outcome; journal patterns | decisions, weekly reviews | repeating a decision whose last outcome was `did-not-help` or `not-reviewed` |

Optional area seats with `--seats +finance,+wellness,+family`. The Steward states
"reasoning from provisional claims" until `me/profile.md` has confirmed ones.

**Procedure.**
1. **Frame** (Chair): one-sentence question; facts, reported claims, assumptions,
   unknowns from memory; reversible or not; deadline. Your current leaning is
   stripped from the brief.
2. **Positions** (seats, in parallel): position in two sentences; evidence with
   paths; the one assumption to check; confidence with a reason; what would change
   its mind.
3. **Cross-examination**: one round. Seats read each other and may revise.
4. **Synthesis** (Chair): agreements; disagreements with the *cause* named (different
   evidence, values, or risk appetite); a ranked recommendation with its trade-off;
   the decision required; the review date; what the council could not see. The Chair
   may not report consensus that was not there.
5. **Record**: `life/workspaces/<slug>/council-YYYY-MM-DD.md`. On "decided", a
   `registers/decisions/` item with the success signal and `review_by`.

**`/brainstorm`**: same seats, options instead of positions; the Chair dedups and
groups, ranks nothing, lists the question each option raises. Writes to the
workspace; parked options go to `registers/parked/`.

**Model diversity** (other providers reviewing each other) is a later, opt-in option
behind `gogos/council/`; it sends the brief off-machine, so it asks first and shows
what leaves. Start with lens diversity inside Claude.

## 8. Governance (small, early, cheap)

- **Rules.** `.claude/rules/reasoning-and-evidence-contract.md`, adapted from
  ClientOS: claim types, cite sources, confidence with a reason, rank and recommend,
  test urgency, name the owner; plus "distil the fact, never copy a body into the
  wiki".
- **Learning loop.** `/learn` + `docs/LEARNINGS.md`, copied from ClientOS verbatim.
- **Health check.** Structure, front matter, wikilinks, register schemas, the three
  decoupling checks of §5, no credentials in the tree; runs pytest and the bash
  tests. SessionStart banner states release debt in words.
- **Permissions.** Tracked `settings.json`: deny direct `gog`, Google API calls
  outside the connectors, credential stores, any send; ask on push, `rm`, apply;
  allow reads, connectors, index scripts. ClientOS's file is the template.
- **Tests.** pytest for Python; bash `run-tests.sh` for scripts, building synthetic
  `life/` trees in a temp dir.
- **Versioning.** Tag and changelog once a second machine depends on it.

## 9. Google access: adopt the ClientOS connectors, keep the gate (decided)

The ClientOS Gmail and Calendar connectors (`gog` CLI) replace GogOS's own OAuth and
Python Google client for reads. The apply engine is re-pointed at
`gog gmail batch modify <id> --add-label 'GSD/<Category>' --remove-label INBOX`.
Verified in gog's docs: that command exists; `--readonly` is a **runtime guard
independent of token scope** (rejects mutating HTTP methods before dispatch);
`--gmail-no-send` blocks sends; `--enable-commands-exact` restricts subcommands;
tokens live in the platform keyring.

Security posture, all parts required together:

1. **The never-delete invariant lives in GogOS code, not in the scope.** `gmail.modify`
   permits trash. The write-capable account is used by exactly one path,
   `gogos/execution/gmail_apply.py`, which still runs `_assert_safe` and the
   approval-file check, then shells out with
   `--enable-commands-exact gmail.batch.modify --gmail-no-send`.
2. **Every read path passes `--readonly`**, so the runtime guard protects connectors
   and the scheduled job even though the token could write.
3. **`settings.json` denies direct `gog`** to the assistant; only the connector scripts
   and the apply engine are allowed. ClientOS's settings already deny `gog` in that
   repo, so a session there cannot write to this mail either.
4. **Scope is `gmail.modify`**, never `mail.google.com` (permanent delete) and never
   `gmail.send`. Calendar edit, when wanted, follows the same pattern with a gated
   `calendar_apply.py` and an inverse plan that stores prior state.
5. **Two tokens if `gog` allows it** (read-only for connectors, modify for the engine),
   so a compromised read path cannot write. Unverified: whether one address can hold
   two credential sets. Test on the Mac; fall back to one modify token plus 1 to 4.
6. **Bodies.** The connector writes up to 3,000 characters of body per message into
   the digest. Hence `life/inbox/` is gitignored, digests are deleted after
   processing, and the rules file forbids copying a body into the wiki. The
   injection surface widens from subjects to bodies; skills treat mail as data and
   the deny rules mean an injected instruction cannot reach a write.
7. The 2026-10-18 drafts fix (unsent drafts filed as sent) comes with the connector;
   keep its tests.

Side effect: the "scheduled run hangs on interactive OAuth" bug disappears with the
Python client.

## 10. The ClientOS bridge (design deferred to the end of the build)

ClientOS owns the client's knowledge; GogOS owns your obligations. GogOS is the
planner because only it sees all of your time. A read-only connector per ClientOS
instance writes `life/inbox/clientos-<slug>-<date>.md`: your open actions, today's
meetings with a prep flag, decisions awaiting you, each with a reference (path and
id in that instance) and a one-line title. **Titles may be kept** in GogOS's journal
and commitments (decided); client facts beyond the title stay in the instance, and
the brief says "open in `<slug>-os`" when context is needed. Work mail in the
personal inbox is tagged `area: work` and treated the same way. Detailed design is
the last slice, once the rest of the grid is running.

## 11. Build order (one small PR per slice)

0. **ADR.** Turn this proposal into `docs/ARCHITECTURE.md` v2.
1. **Known defects and CI.** pyproject / egg-info, per-batch applied record, one
   `today()`. Half a day.
2. **Memory substrate.** `life/` skeleton with the gitignore rules, `me/profile.md`
   (provisional claims, validation log), `me/areas.json`, `me/themes.md`, register
   base schema + `registers-index`, `journal.py` + `/log`. Tests. This slice changes
   the system's nature.
3. **Intake via `gog`.** Copy the ClientOS Gmail and Calendar connectors; `/sync`;
   launchd fetch-only job; apply engine re-pointed at `gog batch modify` behind the
   existing gate; settings.json posture. Remove the Python Google client.
4. **Intelligence core.** Rules file, three agents, `wiki-update`, `register-update`,
   `/process-inbox`. First `life/wiki/` pages.
5. **The daily loop.** `/start-day` over the grid, `/end-day`, `/weekly-review` with
   decision follow-through and theme drift.
6. **Wellness first vertical.** Five `/log` types, two habit goals, a Wellness section
   first in the weekly review. No Apple Health until the logging habit has held.
7. **Council.** Chair + five seats, `/council`, `/brainstorm`, `parked` register,
   decision promotion on confirmation.
8. **Governance.** `/learn`, health check with the decoupling checks, bash tests.
9. **Home and Family services.** Renewals register fed by the classifier; occasions
   from `people/`; last-contact script; workspace template.
10. **ClientOS bridge** (§10).
11. **Further intake, each earned by a real need**: Apple Health export, WhatsApp,
    finance feeds.

## 12. Decisions recorded (2026-10-23)

| Question | Decision |
|---|---|
| Track `me/` and `life/`? | Yes, everything in git in one private repo, provided the system stays decoupled (§5 checks). `life/inbox/` and `.core/` are the gitignored exceptions. |
| Email bodies and Google access | Adopt the ClientOS `gog` connectors including bodies; edit access via `gmail.modify` behind the existing gate (§9). |
| Council seats | Strategist, Skeptic, Operator, Steward, Historian; optional area seats. |
| Areas | Wellness · Finance · Growth · Family (incl. pets) · Home (incl. car, pool, documents) · Work (thin, bridged). |
| EA services | Capabilities (registers, skills, commands), not verticals. "Plan" is `/start-day`. |
| People | The `people/` wiki as substrate for prep and occasions; no area, no weekly section. |
| Voice / content | Parked; belongs with the fractional business (FractionalOS). |
| Isolated research tasks | Workspaces, when the outcome leaves a recurring obligation or a decision; otherwise stay elsewhere. |
| ClientOS bridge | Titles may be kept in GogOS; detailed design is the last slice. |
| First vertical | Wellness. |
