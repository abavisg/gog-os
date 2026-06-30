# /email-loop [account] [--yes]

Implementation model: Sonnet (default — unpinned, tracks current Sonnet)

Purpose: clear an inbox that is **larger than the fetch cap** by running the
email pipeline in batches until the inbox is empty. Each batch is
fetch → normalise → classify → triage → build move plan → (approve) → apply.
Because applying archives each batch, the next `all` fetch sees the next slice,
so the inbox drains.

## Relationship to the other commands

- `/email-report` — read-only triage of one batch (no moves).
- `/email-apply` — move one batch's triaged emails into GSD folders.
- `/email-loop` — repeat the above until the inbox is empty. Use this when the
  inbox exceeds ~200 (the default `GOGOS_ALL_CAP`).

## Safety block

- **Never deletes.** Uses the same `gmail_apply` engine: only `GSD/*` labels
  added, only `INBOX` removed. The never-delete invariant is enforced in code.
- **Approval is preserved.** By default the loop builds the first batch's move
  plan and **stops for your approval** before any move. Nothing moves unattended
  unless you pass `--yes`.
- `--yes` pre-authorises **all** batches: the loop drains the whole inbox without
  pausing. Still never deletes; still reversible.
- A max-iteration bound (default 20) prevents an infinite loop.

## Account argument

Optional `account` — alias or full email, resolved before use. Default account
if omitted.

## Modes

### Default (approval-gated) — recommended for the first run

Run one batch read + plan, then show it and stop:

```
GOGOS_ALL_CAP=2000 python -m gogos.gmail.gmail_loop <account>
```

This fetches up to the cap, classifies, and builds the move plan, then prints:

```
OK  Batch ready: <N> move(s) proposed. Approve to apply ...
```

Then present the plan to the user exactly as `/email-apply` does (counts per
folder + the Action items + stale warning) and ask for confirmation. On **yes**,
either:
- apply this batch with `/email-apply <account>`, then re-run `/email-loop` for
  the next batch; or
- if the user says "do them all", re-run with `--yes` (next section).

### Drain everything (`--yes`) — pre-authorised

```
GOGOS_ALL_CAP=2000 python -m gogos.gmail.gmail_loop <account> --yes
```

The loop approves and applies each batch automatically, repeating until the
inbox is empty. Prints:

```
OK  Inbox drained in <K> batch(es); <total> email(s) moved.
```

Only use `--yes` when the user has explicitly said to move everything without
per-batch review (they still trust the classifier; nothing is deleted).

## Tuning the cap

Set `GOGOS_ALL_CAP` to control batch size. Higher = fewer, larger batches
(usually one pass clears everything); the default of 200 means more, smaller
batches. The loop is correct at any cap.

## After draining

Report: how many batches, total moved, and remind the user the moves are
reversible (drag back from any GSD folder) and that "Safe to Delete" items were
moved, not deleted. Suggest reviewing **GSD/Action** first.
