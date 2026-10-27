---
description: Run the health check, review what a script cannot judge, and propose learnings for recurring findings
argument-hint: [--system | --life | --all]
allowed-tools: Read, Glob, Grep, Bash(bash .claude/scripts/health-check.sh:*), Bash(bash .claude/scripts/permission-check.sh:*), Bash(.venv/bin/python -m gogos.core.learnings:*)
---

# /health [--system | --life | --all]

Implementation model: Sonnet (default, unpinned).

Purpose: tell the owner whether the machinery is sound and where the memory needs
attention, then catch the drift a deterministic script cannot see.

Arguments: `$ARGUMENTS` (default `--all`)

## Steps

1. **Run the script** and show its output unedited:

   ```bash
   bash .claude/scripts/health-check.sh $ARGUMENTS
   ```

   The exit code tracks SYSTEM only. A SYSTEM `ISSUE` blocks pushing; a LIFE `warn`
   is advice. Add `bash .claude/scripts/permission-check.sh --audit` when the owner
   asks about prompts or permissions.

2. **Semantic review.** Read, do not run anything else:
   - Do the agent and skill descriptions in `.claude/agents/` and `.claude/skills/`
     still describe what they do?
   - Does any command point at a module, script or file that no longer exists or
     has been retired (compare with `docs/IMPLEMENTATION_PLAN.md`)?
   - Do `CLAUDE.md` and `docs/ARCHITECTURE.md` still match the layout on disk?

   Report each finding with the file path and one line on why it matters. Say
   "nothing found" when that is the case; do not invent findings.

3. **Learnings for recurring findings.** A finding is recurring when
   `docs/LEARNINGS.md` already has an entry about the same check or file, or the
   owner says it has come up before. For each one, append a proposed entry:

   ```bash
   .venv/bin/python -m gogos.core.learnings add --status proposed \
     --title "<short title>" --trigger "/health <check code>" \
     --lesson "<why it keeps happening>" --change "<exact file and edit>"
   ```

   Offer `/learn` for one-off findings instead of logging them.

4. **Summary.** One line per half: SYSTEM verdict, LIFE warnings, then the
   proposals made. Do not fix anything in this command; fixes are separate,
   approved work.

## Safety

- Read-only apart from `docs/LEARNINGS.md` (through the script) and the L8 hash
  ledger the health check keeps in `.core/storage/reports/`.
- Never print the contents of `.core/config/accounts.json`,
  `tests/fixtures/forbidden-terms.txt` or any credential when explaining an S4
  finding; name the file and the check only.
