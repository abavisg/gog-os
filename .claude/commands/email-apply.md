# /email-apply [account]

Implementation model: Sonnet (default — unpinned, tracks current Sonnet)

Purpose: take the latest triage produced by `/email-report` and **move** each
email into its `GSD/<Category>` folder — that is, add the `GSD/<Category>` label
and archive it (remove `INBOX`). This is a **write-back** command, gated by
explicit user confirmation.

## What "move" means here

Gmail has no folders — folders are labels. Moving an email to `GSD/Action`
means: add label `GSD/Action`, remove label `INBOX` (archive). Archived is NOT
deleted: the email stays searchable and can be dragged back to the inbox or to a
different folder at any time.

## Safety block — enforced at every step

- **Never deletes, trashes, or marks spam.** The engine (`gmail_apply._modify`)
  hard-asserts that the only label added is `GSD/<Category>` and the only label
  removed is `INBOX`. Any other mutation raises before touching Gmail.
- **Two-step approval.** A plan is proposed and shown to the user. Nothing is
  applied until the user explicitly confirms.
- **No auto-create.** If a `GSD/*` label is missing in the account, abort and
  tell the user to create it — do not create labels automatically.
- "Safe to Delete" only *moves* mail into that folder. Deletion is always a
  separate, manual action the user takes later.

## Account argument

Optional `account` — an alias (e.g. `abavisg`) or a full email. Resolved to the
canonical email before use. If omitted, the default account is used.

## Prerequisite

A recent `/email-report <account>` must have written `latest-triage.json` and
`latest-slim.json`. If they are missing, tell the user to run `/email-report`
first, and stop.

The account's token must have the `gmail.modify` scope. If a step fails with a
scope error, tell the user to run `/logout-google <account>` then
`/login-google <account>` to re-authenticate, and stop.

## Steps

### Step 1 — Build the move plan

Run:

```
python -m gogos.gmail.gmail_apply <account> plan
```

This reads the latest triage + slim, maps each email to `GSD/<Category>`, flags
stale emails, and writes a proposal (with `approved: false`) to:

```
.core/storage/approvals/<account>/<YYYY-MM-DD>/gmail-labels.json
```

It does **not** touch Gmail. If it fails (e.g. missing triage), print the error
and stop.

### Step 2 — Render the plan for approval

Read the proposal file and present a clear summary to the user:

- Total emails to move, grouped by destination folder, with a count per folder.
- A per-email line: `<subject>  —  <from>  →  GSD/<Category>`.
- If `stale_ids` is non-empty, surface a **stale-email warning**: these predate
  yesterday 00:00 and may indicate a missed run.

Then ask for explicit confirmation, e.g.:

> Move these N emails into their GSD folders? Nothing will be deleted — this only
> labels and archives, and is reversible. (yes / no)

**Do not proceed without a clear affirmative.** "no", silence, or ambiguity =
stop and do nothing.

### Step 3 — Apply (only after confirmation)

On explicit "yes", mark the proposal approved by setting `"approved": true` in
the proposal file (use a small write — edit the JSON value or re-write the file),
then run:

```
python -m gogos.gmail.gmail_apply <account> apply
```

The engine refuses to apply unless `approved` is true, re-validates every
mutation through the safety gate, and aborts (listing the missing label) if any
`GSD/*` label is absent — without partially applying.

### Step 4 — Report the result

Print a short summary: how many emails were moved, into which folders, and any
failures. Remind the user the moves are reversible (drag back from any folder),
and that "Safe to Delete" items were moved, not deleted.
