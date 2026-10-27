# GogOS Architecture (v2)

GogOS is a Claude Code-native, local-first personal operating system. It turns
mail, calendar and manual capture into a compounding memory, and that memory into
briefs, reviews and gated actions.

This is the standing description. It replaces v1 (fetch, normalise, skill,
report) and absorbs `docs/REARCHITECTURE-PROPOSAL.md`, which is kept as the
historical record. Build status per slice is in `docs/IMPLEMENTATION_PLAN.md`;
each part below says whether it is **built** or which slice brings it.

## 1. The three layers

```
            INTAKE                    INTELLIGENCE                    EXECUTION
  sources → connectors → inbox   →   agents + skills + council   →   write-back (gated)
            (deterministic,           over MEMORY                     artefacts (briefs, docs)
             zero LLM)                (wiki · registers · journal)    local state (journal, registers)
                                            ▲                                │
                                            └────── feedback: /learn ────────┘
```

Layers are responsibilities, not folders; folders follow the data's lifecycle.

**Intake** owns authentication, fetching, dedup ledgers, caps, and one digest per
source per run into `life/inbox/`. No LLM in this path, ever.
*Built:* the Python Gmail and Calendar pipeline (`gogos/gmail/`, `gogos/calendar/`,
OAuth in `gogos/auth/`) and `/log` for manual capture. *Slice 3* replaces the
Python Google client with the `gog` connectors and writes digests.

**Intelligence** turns digests into memory (`/process-inbox`), produces briefs and
reviews (`/start-day`, `/end-day`, `/weekly-review`), ranks (`/prioritise`) and
thinks on demand (`/council`, `/brainstorm`). It reasons only over what is already
in the repo. The deterministic email classifier stays as the zero-token first pass.
*Built:* the classifier and five skills (`email-triage`, `calendar-brief`,
`daily-brief`, `news-curator`, `reflection-coach`). *Slices 4, 5 and 7* add the
rules file, agents, `/process-inbox`, the daily loop and the council.

**Execution** owns three kinds of action, each with its own gate:

| Kind | Example | Gate | Status |
|---|---|---|---|
| External write-back | Gmail label + archive | Two-step approval file, inverse plan, undo, never-delete invariant in code | built (`gmail_apply`, `gmail_undo`) |
| Artefact | A brief, a review, a council note | None, but it cites its inputs | built for email and calendar reports |
| Local state | Journal event, register status | None, but append-only or history-preserving, indexed deterministically | built (`gogos/core/`) |

## 2. Memory

Three stores, each with a deterministic indexer and no LLM in it. Schemas are in
`docs/specs/02-memory-substrate.md`; code is in `gogos/core/`. **Built.**

- **`life/wiki/<area>/<subject>.md`**: timeless facts. One subject per page,
  honest `confidence:`, `[[wikilinks]]`, a provenance line, never a copied mail
  body. `life/wiki/people/<name>.md` serves prep and occasions; it is not an area.
- **`life/registers/<kind>/<slug>.md`** (kind singular): stateful items with a
  lifecycle. Base schema plus a few fields per kind; status changes append to a
  `## History` section. `registers.py index` writes `_index.md` per kind and
  `registers/_index.json`, which is what briefs read.
- **`life/journal/YYYY-MM-DD.jsonl`**: append-only events, ULID ids, one
  `O_APPEND` write per line. Written by `/log` and by every register change.

| Register kind | Service | Fed by |
|---|---|---|
| `goal` | direction per area; habits carry `target_per_week` | the owner |
| `commitment` | "you said you'd", with `due` and an optional `goal` | `/log`, `/end-day`, process-inbox |
| `waiting` | follow-ups owed to the owner | `/log waiting`, sent mail |
| `renewal` | expiries, `review_by` ahead of the date | classifier rules, the owner |
| `occasion` | birthdays, anniversaries | the people wiki |
| `decision` | what was decided, confidence, `review_by`, `outcome` | council, the owner |
| `parked` | "not now", with a revisit date | `/brainstorm`, the owner |

Claude Code's task list is a projection of open commitments
(`gogos/core/kanban.py`, list id `gogos`); the register is the truth.

`me/` holds the owner's profile (claims provisional until confirmed), `areas.json`
and `themes.md`. It is the only tracked place for owner-specific content.

## 3. Areas × services

Areas are rows: **Wellness, Finance, Growth, Family, Home, Work** (`me/areas.json`).
Services are columns: commitments, waiting-on, renewals, occasions, prep, plan,
review. Every cell is meaningful, so services are capabilities (a register kind, a
skill or a command), not verticals, and **Plan is a command** (`/start-day`), not a
place. People, two countries and mobility are not areas (a wiki, a tag, Home).

A piece of thinking in progress lives in `life/workspaces/<slug>/` when its outcome
leaves a recurring obligation or a decision worth remembering.

## 4. Directory layout

```
CLAUDE.md                     routing contract
me/                           TRACKED. profile.md, areas.json, themes.md
gogos/                        TRACKED. Python: intake and execution engines, tested
  core/      paths, frontmatter, registers, journal, kanban, health, learnings
  gmail/ calendar/ auth/ system/   the v1 pipeline (moves under intake/ and execution/ in slice 3)
.claude/                      TRACKED
  commands/  slash commands      skills/  reasoning procedures
  scripts/   health-check.sh run-tests.sh permission-check.sh banner.sh
  settings.json                deny / ask / allow posture and the SessionStart hook
life/                         the memory
  inbox/     GITIGNORED. connector digests (may hold mail bodies) and drops
  wiki/ registers/ journal/ workspaces/ reports/   TRACKED
.core/
  config/    TRACKED decoupled config (categories, classifier lists, rubric, feeds);
             secrets/ and accounts.json GITIGNORED
  storage/   GITIGNORED. raw and slim JSON, approvals, ledgers, tokens
docs/        ARCHITECTURE.md, LEARNINGS.md, IMPLEMENTATION_PLAN.md, specs/
```

`.claude/agents/` and `.claude/rules/` arrive in slice 4.

## 5. The loops

| Mode | Trigger | What runs | LLM? | Status |
|---|---|---|---|---|
| Proactive | launchd (`/schedule-morning`) | the read-only morning triage, one notification | no | built; fetch-only `sync` in slice 3 |
| | SessionStart hook | `banner.sh`: one line of counts, offers `/start-day` | no | built |
| Reactive | `/sync`, a file in `life/inbox/` | connectors, then `/process-inbox` | fetch no, process yes | slices 3 and 4 |
| Ad hoc | `/start-day` | today's merged email panel; the full grid in slice 5 | yes | built (email) |
| | `/log <type> <text>` | one journal event; opens `waiting` or `commitment` items | no | built |
| | `/email-apply`, `/email-undo`, `/email-loop` | the gated engine | no | built |
| | `/end-day`, `/weekly-review` | reviews over journal, briefs and registers | yes | slice 5 |
| | `/council`, `/brainstorm` | §6 | yes | slice 7 |
| Governance | `/health`, `/learn` | §7 | script no, review yes | built |

No LLM in the fetch path, and processing is never scheduled: knowledge is not
rewritten without a human in the session.

## 6. The Council (slice 7)

On-demand, multi-perspective thinking for decisions worth four to six model calls.
Five seats on Sonnet with read-only tools (Strategist, Skeptic, Operator, Steward,
Historian), and an Opus Chair, the only writer. Frame, positions, one round of
cross-examination, synthesis that names the cause of each disagreement, then a
record in the workspace and, on "decided", a `decision` register item.
`docs/specs/07-council.md` has the detail.

## 7. Governance (built in slice 8)

- **Health check.** `.claude/scripts/health-check.sh` reports SYSTEM checks S1 to
  S8 (data boundary, agent and skill policy, command targets, decoupling, tests,
  areas, source-scan invariants, local permissions), which gate the exit code, and
  advisory LIFE checks L1 to L8 (front matter, wikilinks, register validity,
  overdue items, inbox age, journal gaps, profile validation, finalised reports).
  The LIFE half and S6 run in `gogos.core.health`, so register and front matter
  rules live in Python once. CI runs `--system`.
- **Bash tests.** `.claude/scripts/run-tests.sh` builds a synthetic repo per case
  and plants one violation per SYSTEM check.
- **Learning loop.** `/learn` and `/health` append to `docs/LEARNINGS.md` through
  `gogos.core.learnings`. The system records and proposes; the owner approves.
- **Permissions.** Tracked `.claude/settings.json`: deny direct `gog`, Google API
  calls, credential stores and non-PR GitHub writes; ask on push, history rewrites,
  `rm`, the PR flow and Gmail write-back; allow reads, the gogos modules, tests and
  the scripts. `settings.local.json` is gitignored and may hold only ask and deny
  rules (S8). `permission-check.sh --audit` explains the merged ruleset.
- **Decoupling.** Nothing under `gogos/`, `.claude/` or `docs/` names a person, an
  account or a client (S4); the system runs against an empty `life/` and `me/`
  (`run-tests.sh` baseline); nothing under `life/inbox/`, `.core/storage/`,
  `.core/config/secrets/` or `.core/config/accounts.json` is tracked (S1).
- **Versioning.** Deferred until a second machine depends on the repo; `main` is
  the version.

## 8. Google access (slice 3)

The `gog` connectors replace GogOS's own OAuth and Python Google client for reads.
The apply engine is re-pointed at `gog gmail batch modify` behind the existing gate:
the never-delete invariant stays in GogOS code; every read passes `--readonly`
(S7 checks it); `settings.json` denies direct `gog` to the assistant; scope is
`gmail.modify`, never full mail access or send. Bodies (up to 3,000 characters)
reach `life/inbox/` only, which is gitignored and emptied after processing.

Until slice 3 lands, reads and writes use `gogos/auth/google_auth.py` with
per-account tokens at `chmod 600` under `.core/storage/auth/`.

## 9. The ClientOS bridge (slice 10, design deferred)

GogOS owns the owner's obligations; a client instance owns that client's knowledge.
A read-only connector per instance will write a digest of open actions, meetings and
decisions awaiting the owner, titles only, each with a reference back to the
instance.

## 10. Conventions

- **Scripts normalise; models interpret.** Never pass raw API data to a model.
- **Privacy gates live in code**, not prompts: no message body reaches
  `.core/storage` (the Gmail snippet, up to about 100 characters, is the one
  exception); write-back can only add a `GSD/*` label and remove `INBOX`.
- **One `today()`**: `gogos.core.paths.today()`, the local date in
  `GOGOS_TIMEZONE` (default `Europe/London`). Stored timestamps are UTC.
- **Storage**: dated directories via `gogos.paths.storage_path(...)`, a dated file
  and a `latest-*` alias. Content under `life/` and `me/` carries front matter.
- **Every artefact cites its sources.** Finalised reports are amended, never edited
  (L8).
- **Script shape**: module docstring with the `python -m` invocation, `from
  __future__ import annotations`, type hints, errors to stderr, non-zero exit on
  failure, an importable function plus a CLI.
- **Models**: Sonnet by default, unpinned; pin Opus or Haiku only where a skill or
  agent needs it; never Fable. Skills never declare `model:` (S2).

## Decisions

| Date | Decision |
|---|---|
| 2026-10-23 | Track `me/` and `life/` in one private repo, provided the system stays decoupled; `life/inbox/`, `.core/storage/` and `.core/config/secrets/` are the gitignored exceptions. |
| 2026-10-23 | Adopt the ClientOS `gog` connectors including bodies; edit access via `gmail.modify` behind the existing gate. |
| 2026-10-23 | Council seats: Strategist, Skeptic, Operator, Steward, Historian; optional area seats. |
| 2026-10-23 | Areas: Wellness, Finance, Growth, Family (incl. pets), Home (incl. car, pool, documents), Work (thin, bridged). |
| 2026-10-23 | Executive-assistant services are capabilities, not verticals; "Plan" is `/start-day`. |
| 2026-10-23 | People are a wiki, not an area. Voice and content are parked (FractionalOS). |
| 2026-10-23 | Isolated research becomes a workspace only when it leaves an obligation or a decision. |
| 2026-10-23 | ClientOS bridge: titles may be kept in GogOS; detailed design is the last slice. |
| 2026-10-23 | First vertical: Wellness. |
| 2026-10-24 | `.core/config/` stays tracked as decoupled config; only `secrets/` and `accounts.json` are ignored there. |
| 2026-10-24 | Register directories are singular (`registers/goal/`), matching the `register:` field. |
| 2026-10-27 | `settings.local.json` is gitignored and holds no allow rules; the PR flow (create, ready, merge, close) asks rather than being denied. |
| 2026-10-27 | Versioned releases deferred until a second machine depends on the repo. |
