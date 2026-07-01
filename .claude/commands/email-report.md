# /email-report [account] [window]

Implementation model: Sonnet (default — unpinned, tracks current Sonnet)
Runtime triage model: Sonnet (default — unpinned, tracks current Sonnet)

Purpose: fetch Gmail metadata, triage it, and display a readable Markdown report.
Read-only only. The JSON is never printed to the conversation.

## Account argument

The optional `account` argument can be an alias (e.g. `abavisg`) or a full email
(e.g. `abavisg@gmail.com`). It is resolved to a canonical email before use — storage
paths and API calls always use the email. If omitted, the default account is used.

## Window argument

The optional `window` argument controls which emails are fetched:

- `yesterday` **(default)** — everything from yesterday 00:00 local time until now.
- `all` — full inbox, capped at 200; warns if the inbox exceeds that.
- `<N>` (e.g. `200`) — top N messages sorted by date.

If omitted, `yesterday` is used.

## Safety block — enforced at every step

- Read-only behaviour: this command never mutates Gmail, even though the
  account now holds the `gmail.modify` scope (used only by `/email-apply`).
- No labels, no archive, no delete, no send.
- No full-body fetch.
- No write-back to Gmail of any kind.

## Steps

Run all steps silently (no raw JSON printed to the conversation at any point).
If a step fails, print the error and stop.

### Step 1 — Gmail metadata fetch

Run:

```
python -m gogos.gmail.gmail_fetch <account> <window>
```

Writes `latest-raw.json` under `.core/storage/gmail/<account>/inbox/<YYYY-MM-DD>/`.
Fail loudly and stop if this step fails.

### Step 2 — Normalise

Run:

```
python -m gogos.gmail.gmail_normalise <account> .core/storage/gmail/<account>/inbox/<date>/latest-raw.json
```

Writes `latest-slim.json` in the same dated directory.
Fail loudly and stop if this step fails.

### Step 2.5 — Reconcile manual moves (read-only)

Run:

```
python -m gogos.gmail.gmail_reconcile <account>
```

Compares the last applied batch's current Gmail labels against where the
classifier filed them: manual moves become per-sender corrections, repeated
corrections auto-learn into the sender ledger (logged in the report), and
never-rescued senders with a `List-Unsubscribe` header become unsubscribe
candidates. Reads label sets only; never mutates Gmail.

If this step fails (e.g. nothing applied yet), print a one-line warning and
continue — the report simply has no reconciliation section.

### Step 3 — Triage via email-triage skill

Invoke the `email-triage` skill, passing:

- The full contents of `latest-slim.json` as the normalised email JSON.
- The categories from `.core/config/gmail/categories.json`.
- The rubric from `.core/config/gmail/rubric.md`.

**Do not print the triage JSON to the conversation.**
Hold it in memory for Step 4.

The skill returns strict JSON in this shape:

```json
{
  "generated_at": "<ISO-8601 timestamp>",
  "account": "<account>",
  "items": [
    {
      "id": "<message id from latest-slim.json>",
      "category": "<one of the configured categories>",
      "confidence": 0.0,
      "rationale": "<brief classification rationale>",
      "suggested_action": "<human-readable suggestion>"
    }
  ]
}
```

Every `id` must match a real message `id` from `latest-slim.json`.
Every `category` must be one of the names defined in `categories.json`.

### Step 4 — Write triage JSON

Write the triage JSON to a temp file, then run:

```
python -m gogos.gmail.gmail_triage <account> /tmp/triage_output.json
```

Writes `latest-triage.json` under `.core/storage/gmail/<account>/triage/<YYYY-MM-DD>/`.
Fail loudly and stop if validation fails.

### Step 5 — Render and display Markdown report

Run:

```
python -m gogos.gmail.gmail_report <account> \
  .core/storage/gmail/<account>/triage/<date>/latest-triage.json \
  .core/storage/gmail/<account>/inbox/<date>/latest-slim.json
```

Then read the output file and **print its contents to the conversation** as the final output.

```
cat .core/storage/reports/email/<account>/<date>/latest.md
```

The script also writes `latest.html` to the same directory and opens it in Google Chrome automatically.
No write-back to Gmail.
