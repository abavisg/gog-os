# LEARNINGS.md: how GogOS improves over time

This is the system's improvement log: a record of problems found, corrections
made, and improvements proposed or applied. It is the **safe** self-improvement
mechanism: the system records and *proposes*; **the owner approves** before
anything behavioural changes. Nothing here is applied silently.

It is written by `/learn` and `/health` through `python -m gogos.core.learnings`,
which only ever touches this file, and it is reviewed by the owner.

## How to use

- `/learn <what happened>` records a lesson and, if warranted, proposes a fix.
- `/health` appends `proposed` entries for findings that keep coming back.
- Review `proposed` entries and approve or reject them. Approved changes are
  applied and the entry flips to `applied`.

Trivial, unambiguous fixes (a broken link, a wrong date) may be applied without
asking and are still logged here as `applied`.

## Entry format

Newest entries on top. Each entry:

```
### YYYY-MM-DD: <short title>
- **Status:** noted | proposed | applied | rejected
- **Trigger:** what surfaced this (a correction, a /health finding, friction).
- **Lesson:** the durable, reusable takeaway.
- **Proposed change:** exact file and edit (omitted when the status is noted).
- **Resolution:** (filled when applied or rejected) what was done and when.
```

## Entries

### 2026-10-27: A decoupling scan must cover every tracked system file and work with no terms
- **Status:** applied
- **Trigger:** PR #21 review R1 and R1b: S4 scanned gogos/, .claude/ and docs/ only, and checked zero terms in CI, so the owner's name in .core/config/ and the real address in tests/ passed
- **Lesson:** scope the scan by what ships (tests, tracked config and root docs included), and give it a rule that needs no secret input, or CI proves nothing
- **Proposed change:** health-check.sh S4: SYSTEM_PATHS widened; address rule with tests/fixtures/synthetic-addresses.txt; leaks replaced in config, tests and docs
- **Resolution:** applied 2026-10-27.

### 2026-10-27: Example values in commands must be placeholders
- **Status:** applied
- **Trigger:** the first run of health check S4 (slice 8) found the owner's account alias and address used as examples in eight commands, and the owner's GitHub org named in the proposal.
- **Lesson:** an example is still content. Anything under gogos/, .claude/ or docs/ uses `personal`, `work` and `you@example.com`, never a real alias or address, because S4 cannot tell an example from a leak.
- **Proposed change:** replace the examples in .claude/commands/{account-add,account-alias,calendar-brief,email-apply,email-report,email-undo,login-google,logout-google}.md and docs/REARCHITECTURE-PROPOSAL.md.
- **Resolution:** applied 2026-10-27 in the slice 8 branch.

### 2026-10-24: A spec amendment can land between review and merge
- **Status:** noted
- **Trigger:** PR #18 amended spec 2 (keep `.core/config/` tracked) after PR #17 was reviewed against the old text; #17 merged with a `/.core/` rule the amended spec no longer allowed, and PR #20 fixed it.
- **Lesson:** before merging a slice, re-read its spec on main. S1 now asserts the exact boundary, so the health check catches this class of drift.
