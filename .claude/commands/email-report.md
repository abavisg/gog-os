# /email-report [account] [window]

Implementation model: Claude Sonnet 4.6
Runtime triage model: Claude Sonnet 4.6

Purpose: fetch Gmail metadata, normalise it, classify via the email-triage skill,
and persist the triage JSON. Read-only only.

## Window argument

The optional `window` argument controls which emails are fetched:

- `yesterday` **(default)** — everything from yesterday 00:00 local time until now.
- `all` — full inbox, capped at 200; warns if the inbox exceeds that.
- `<N>` (e.g. `200`) — top N messages sorted by date.

If omitted, `yesterday` is used.

## Safety block — enforced at every step

- Read-only Gmail scopes only (`gmail.readonly`).
- No labels, no archive, no delete, no send.
- No full-body fetch.
- No write-back to Gmail of any kind.

## Steps

### Step 1 — Gmail metadata fetch (B1)

Run:

```
python -m gogos.gmail.gmail_fetch <account>
```

This fetches metadata-only (From/To/Subject/Date headers + snippet + labels).
It writes a dated raw JSON file and a `latest-raw.json` alias under
`.core/storage/gmail/<account>/inbox/<YYYY-MM-DD>/`.

Fail loudly (exit non-zero) and stop if this step fails.

### Step 2 — Normalise (B2)

Run:

```
python -m gogos.gmail.gmail_normalise <account> .core/storage/gmail/<account>/inbox/<date>/latest-raw.json
```

This converts the raw metadata to the canonical slim schema
(id, thread_id, account, from, to, subject, date UTC, snippet, labels, source)
and writes `latest-slim.json` in the same dated inbox directory.

Fail loudly and stop if this step fails.

### Step 3 — Triage via email-triage skill (B3/B4)

Invoke the `email-triage` skill, passing:

- The full contents of `latest-slim.json` as the normalised email JSON.
- The categories from `.core/config/gmail/categories.json`.
- The rubric from `.core/config/gmail/rubric.md`.

The skill returns strict JSON only — no prose — in this shape:

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

Every `id` in the output must match a real message `id` from `latest-slim.json`.
Every `category` must be one of the names defined in `categories.json`.
Do not invent message ids or categories.

### Step 4 — Write triage JSON (B4)

Run:

```
python -m gogos.gmail.gmail_triage <account> <path-to-triage-json>
```

Or pipe the skill output directly:

```
<triage JSON> | python -m gogos.gmail.gmail_triage <account>
```

This validates the triage JSON schema and writes:
- A dated `triage.json` under `.core/storage/gmail/<account>/triage/<YYYY-MM-DD>/`.
- A `latest-triage.json` alias in the same directory.

Fail loudly and stop if validation fails or the write fails.

### Step 5 — Render Markdown report (B5)

Run:

```
python -m gogos.gmail.gmail_report <account> \
  .core/storage/gmail/<account>/triage/<date>/latest-triage.json \
  .core/storage/gmail/<account>/inbox/<date>/latest-slim.json
```

This renders a Markdown report grouped by triage category. Each entry shows
sender, subject, suggested action, and confidence (as a percentage). The report
header cites both input artefact paths and a local-time generation timestamp.

Output is written to:
- `.core/storage/reports/email/<account>/<date>/email-report.md` (dated)
- `.core/storage/reports/email/<account>/<date>/latest.md` (alias)

No HTML is produced. Nothing is auto-opened. No write-back to Gmail.

If the triage file is missing, the script exits non-zero with a clear error.
Empty triage (zero items) renders a valid "nothing to triage" report and exits 0.
