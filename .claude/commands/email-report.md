# /email-report [account]

Implementation model: Claude Sonnet 4.6
Runtime triage model: Claude Sonnet 4.6

Purpose: fetch Gmail metadata, normalise it, classify via the email-triage skill,
and persist the triage JSON. Read-only only.

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

## What is NOT done here (deferred to B5)

- No Markdown report generation.
- No HTML report generation.
- No auto-open of any file.
