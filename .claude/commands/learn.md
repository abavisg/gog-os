---
description: Record a lesson or correction and propose a system improvement for approval
argument-hint: [what happened / what to learn from]
allowed-tools: Read, Bash(.venv/bin/python -m gogos.core.learnings:*)
---

# /learn [what happened]

Implementation model: Sonnet (default, unpinned).

Capture a learning and, where it justifies a change, propose a system improvement.

This is the safe self-improvement mechanism: the system **records** problems and
corrections and **proposes** fixes. It does not rewrite itself. The owner decides;
the assistant assists.

Arguments: `$ARGUMENTS`

## Input

`$ARGUMENTS` describes what happened: a mistake the owner corrected, a recurring
friction, a convention that keeps tripping things up, or a finding from `/health`.
If empty, ask what the system should learn from, or infer it from the recent
conversation and say what you inferred.

## Procedure

1. **Distil the lesson.** What is the durable, reusable takeaway? Strip the one-off
   detail and keep what will apply again. If it is a pure one-off with no general
   lesson, say so and do not log it.

2. **Decide whether it warrants a change.** Does the lesson imply an improvement to
   a doc, a skill, a command, `CLAUDE.md`, a script or the health check? Or is it
   just worth remembering? Read the file you would change first, so the proposal
   names the exact edit.

3. **Append the entry** with the script. It writes `docs/LEARNINGS.md` and nothing
   else:

   ```bash
   .venv/bin/python -m gogos.core.learnings add \
     --title "<short title>" --trigger "<what surfaced it>" --lesson "<the takeaway>" \
     --status proposed --change "<exact file and edit>"
   ```

   Use `--status noted` and no `--change` for a lesson with no edit attached.

4. **If a change is proposed**, show the owner the exact edit and ask for approval.
   **Do not apply it in this command.** On approval, apply the edit as ordinary
   work in the session, then mark the entry:

   ```bash
   .venv/bin/python -m gogos.core.learnings resolve \
     --title "<short title>" --status applied --resolution "<what was done>"
   ```

   On rejection, resolve it with `--status rejected` and the reason.

5. **Keep it honest.** Do not manufacture lessons to look busy. A good learning log
   is short and high-signal.

## Exceptions

The only changes that may be applied without asking are trivial, unambiguous fixes
(a broken link, a wrong date). Log them with `--status applied`.

## Safety

- Personal facts never go into `docs/LEARNINGS.md`: it is a system file and the
  health check (S4) scans it. Describe the lesson, not the person or the account.
- Never weaken a privacy gate, a deny rule or a never-delete invariant as a
  "lesson". Propose it, explain the risk, and let the owner decide.
