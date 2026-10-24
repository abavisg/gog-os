# Spec 8: governance

## Purpose

The small set of mechanisms that keep the system honest as it grows: a learning
loop that records and proposes, a health check that catches drift, a permission
posture that is tracked, and tests for the scripts. Copied from ClientOS wherever
the mechanism is already proven.

## Scope

- `/learn` and `docs/LEARNINGS.md`.
- `.claude/scripts/health-check.sh` and `/health`.
- `.claude/scripts/run-tests.sh` (bash tests for scripts; pytest stays for Python).
- `.claude/settings.json` posture (started in spec 3, completed here).
- SessionStart banner.
- `docs/ARCHITECTURE.md` v2, `docs/IMPLEMENTATION_PLAN.md` updated, `README.md`
  updated.

## Non-scope

Versioned releases, tags and migrations: deferred until a second machine depends on
the repo. Until then, `main` is the version.

## Design

### Learning loop

`docs/LEARNINGS.md` with ClientOS's entry format (`Status: noted | proposed | applied
| rejected`, Trigger, Lesson, Proposed change, Resolution), newest first. `/learn
<what happened>` distils the lesson, decides whether it warrants a change, appends
the entry, and **proposes** the exact edit without applying it; trivial fixes (a
broken link, a wrong date) may be applied and logged. `/health` appends `proposed`
entries for recurring findings.

### Health check

`.claude/scripts/health-check.sh`, bash 3.2, dependency-free except `python3` for
JSON. Reports **SYSTEM** and **LIFE** halves; the exit code tracks SYSTEM only,
except for checks that protect the data boundary, which are SYSTEM checks.

SYSTEM checks:

- S1 `.gitignore` contains `/life/inbox/`, `.core/storage/`, `.core/config/secrets/` and
  `.core/config/accounts.json`; `git ls-files` shows nothing under any of them
  (`.core/config/` is otherwise tracked, decoupled config); nothing matching `*token*`, `*.env`, `credentials*`.
- S2 every `.claude/agents/*.md` has `name`, `description`, `model`, `tools`; no
  `.claude/skills/*/SKILL.md` has `model:`; every agent named in a command exists;
  `gardener` is the only non-council agent with Bash; council seats have no Write.
- S3 every command's `python -m gogos.<module>` target imports (`python3 -c "import
  gogos.<module>"`).
- S4 `gogos/`, `.claude/`, `docs/` contain no email address from
  `.core/config/accounts.json`, no name from `me/profile.md`'s front matter owner
  field, no string from a `tests/fixtures/forbidden-terms.txt` the owner maintains
  (defaults to the account aliases). Synthetic fixtures only.
- S5 `pytest -q` passes; `run-tests.sh` passes.
- S6 `me/areas.json` ids match the `area` values used in `life/` front matter and in
  `gogos/core/registers.py`.
- S7 the source-scan invariants: no `gog` call without `--readonly` outside
  `gogos/execution/`; `gogos/core/brief.py` and `gogos/intake/` never import
  `gogos.execution`.
- S8 `settings.local.json` holds no `allow` rules.

LIFE checks (advisory):

- L1 front matter present and valid on every file under `life/wiki`, `registers`,
  `workspaces`, `reports`; `updated` not in the future; `status` in the allowed set.
- L2 wikilinks resolve (targets: wiki pages, register items, people pages).
- L3 register items validate (`registers.py` is the authority; the script calls it).
- L4 overdue `review_by` count per kind; `renewals` past `expires` still `open`.
- L5 `life/inbox/` item count and age of the oldest item (older than 3 days flagged).
- L6 journal: days in the last 14 with no events.
- L7 `me/profile.md` validation: count of provisional claims; last_validated age.
- L8 finalised reports unchanged since finalisation (hash recorded in `.core/storage/
  reports/final.sha256`).

`/health` runs the script, then a semantic review by the analyst (are the agent
descriptions still accurate, are commands pointing at retired modules), and offers
`/learn` entries for recurring findings.

### Script tests

`.claude/scripts/run-tests.sh`: builds a synthetic repo in `mktemp -d` (copies
`.claude/scripts/`, writes a fake `life/` with front matter cases, a fake
`settings.local.json` with an allow rule) and asserts each health check line fires
or stays quiet as expected. Discovered by the health check (S5). Fixture hygiene is
itself a test: no fixture may contain a real address or name.

### Permissions

Complete the `settings.json` from spec 3 using ClientOS's three arrays and the
trailing-wildcard rule (`Bash(git push *)`, spaced). `autoMode` allow / soft_deny /
hard_deny prose adapted: reading and editing under `life/` and `me/` is allowed;
deleting anything asks; any `gog` call, Google API call, credential read or outbound
send is hard-denied outside the connectors and the gated engine. `.claude/scripts/
permission-check.sh` is copied as-is (read-only by contract).

### Banner

SessionStart hook prints one line: `◇ GogOS · <n> inbox items · <n> commitments due
today · <n> uncommitted` using only local files; offers `/start-day` when today's
report does not exist. Replaces the current nudge.

### Documents

- `docs/ARCHITECTURE.md` v2: the proposal's §2 to §10 as the standing description,
  decisions moved to a `## Decisions` log with dates.
- `docs/IMPLEMENTATION_PLAN.md`: DONE / NEXT rewritten around the slices; the old
  Phase 5 to 9 text removed; "source of truth" statement kept.
- `README.md`: what it is, the daily loop, the areas, setup via `gog`, command table.
- `docs/EMAILOS.md`, `docs/GOOGLE_INTEGRATIONS.md`, `docs/SECURITY.md` updated for
  `gog`, digests, and the tracked / gitignored boundary.
- `docs/REARCHITECTURE-PROPOSAL.md` kept as the historical record with a banner
  pointing at ARCHITECTURE.md.

## Acceptance criteria

- [ ] `health-check.sh` exits 0 on the repo at the end of this slice; each SYSTEM
      check has a `run-tests.sh` case that makes it fail on a synthetic violation.
- [ ] Adding an `allow` rule to `settings.local.json` fails S8.
- [ ] Writing an account email into a docs file fails S4.
- [ ] `/learn` appends a `proposed` entry and does not edit the proposed file.
- [ ] Banner prints in under 200 ms with no network.
- [ ] CI runs `health-check.sh --system` in addition to pytest and ruff.

## Tests

`run-tests.sh` itself; `tests/test_health_bridge.py` asserts `registers.py
validate` is what L3 calls (no duplicated schema).

## Open questions

- Should the banner also show release debt once tags exist? Yes, when spec 11-era
  versioning arrives; not now.
