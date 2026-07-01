# /email-undo [account]

Implementation model: Sonnet (default — unpinned, tracks current Sonnet)

Purpose: **reverse the most recent `/email-apply` (or `/email-loop`) batch** —
move every email that was filed into a `GSD/<Category>` folder back to the inbox.
This is the exact inverse of a move: remove the `GSD/<Category>` label and add
`INBOX` back (un-archive). Use it when a run mis-filed mail or you simply changed
your mind.

## What "undo" means here

Moving an email to `GSD/Action` added label `GSD/Action` and removed `INBOX`.
Undo does the opposite: **remove `GSD/Action`, add `INBOX`** — the message
returns to the inbox. Nothing is ever deleted; this only relabels.

## Safety block — enforced at every step

- **Never deletes, trashes, or marks spam.** The engine (`gmail_undo._modify_undo`)
  hard-asserts that the only label added is `INBOX` and the only label removed is a
  `GSD/<Category>` destination. Any other mutation raises before touching Gmail.
- **Reverses exactly what was applied.** Undo reads the applied-result record
  (`gmail-applied.json`) written when the batch was applied — only messages that
  *actually* moved are reversed. It never guesses from a proposal.
- **Aborts on a missing label** — if a `GSD/*` label the batch used no longer
  exists, undo stops without partially applying and tells you which is missing.

## Account argument

Optional `account` — an alias (e.g. `abavisg`) or a full email. Resolved to the
canonical email before use. If omitted, the default account is used.

The account's token must have the `gmail.modify` scope (the same scope apply
uses). On a scope error, tell the user to run `/logout-google <account>` then
`/login-google <account>`, and stop.

## Prerequisite

A prior `/email-apply` or `/email-loop` must have written
`.core/storage/approvals/<account>/<YYYY-MM-DD>/gmail-applied.json`. If it is
missing, tell the user there is no applied batch to undo, and stop.

## Steps

### Step 1 — Build the undo plan

Confirm with the user before touching Gmail. Read the latest
`gmail-applied.json` and summarise what will be reversed:

- Total emails to return to the inbox, grouped by the folder they came from.
- A per-email line where available: `<id>  ←  GSD/<Category>`.

Then ask for explicit confirmation, e.g.:

> Return these N emails from their GSD folders back to the inbox? Nothing will be
> deleted — this only relabels. (yes / no)

**Do not proceed without a clear affirmative.** "no", silence, or ambiguity =
stop and do nothing.

### Step 2 — Apply the undo (only after confirmation)

On explicit "yes", run:

```
python -m gogos.gmail.gmail_undo <account>
```

The engine re-validates every mutation through the inverse safety gate and aborts
(listing the missing label) if any `GSD/*` label the batch used is absent —
without partially applying.

### Step 3 — Report the result

Print a short summary: how many emails were returned to the inbox, from which
folders, and any failures.
