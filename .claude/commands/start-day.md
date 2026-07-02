# /start-day

Implementation model: Sonnet (default — unpinned, tracks current Sonnet)

Purpose: the single morning command. Runs EmailOS **read-only** across **all
registered accounts** (reconcile → fetch → normalise → classify per account)
and prints **one merged panel** where every item is account-tagged
`[personal]` / `[work]`. Then it **stops** — no moves.

Later phases fold CalendarOS and TaskOS digests into the same panel.

## Relationship to the other commands

- `/start-day` — read-only morning brief across all accounts (this command).
- `/email-report` — read-only triage of one account, full report.
- `/email-apply` — move one account's triaged emails into GSD folders (gated).
- `/email-undo` — reverse the last applied batch.

## Safety block — enforced in code, not just here

- **Read-only towards Gmail.** The backing module (`gogos.system.start_day`)
  never imports the apply engine — a test proves the source cannot reach
  write-back. No labels, no archive, no delete, no send.
- Fetch/classify/apply/undo/approval all remain **per-account**; only the view
  is merged.
- Reconcile runs first per account (learns from your manual moves since the
  last apply) — it reads label sets only and is best-effort: its failure never
  blocks the morning run.
- One account failing (e.g. expired token) does **not** kill the run: it is
  flagged loudly in the panel and on stderr, and the other accounts proceed.

## Steps

### Step 1 — run the merged read-only pipeline

```
python -m gogos.system.start_day
```

Runs every registered account (add `<alias-or-email>` arguments to restrict,
`--window all|<N>` to override the default `yesterday` window). Writes the
merged panel to `.core/storage/reports/start-day/all/<date>/start-day.md`
(plus `latest.md`) and prints it to stdout.

If it exits non-zero, print the error and stop (likely no accounts registered
or every token expired — suggest `/login-google`).

### Step 2 — display the panel

Print the panel (the script's stdout) to the conversation as the final output:
the merged 3-line digest, the account-tagged **Needs you** list, the
per-account **Queue** counts, and the source artefact paths.

### Step 3 — stop

Do **not** propose or apply any moves. If the user wants to file the queue,
point them at `/email-apply <account>` (per account, gated as always).

## SessionStart nudge

A SessionStart hook runs `python -m gogos.system.start_day --nudge`: it reads
only local artefacts (no network) and prints a one-line offer — with counts if
a scheduled run already triaged today, quiet if today's panel already exists.
The hook only ever **offers** `/start-day`; it never runs the pipeline and
never touches write-back.
