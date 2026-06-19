# /calendar-brief [account] [today|tomorrow|week]

Implementation model: Claude Sonnet 4.6

Purpose: fetch Google Calendar events, analyse them via the calendar-brief skill,
and display a readable brief. Read-only only. No write-back to Google Calendar.

## Arguments

- `account`: alias (e.g. `abavisg`) or full email (e.g. `abavisg@gmail.com`).
  Resolved to canonical email before use. Defaults to the configured default account.
- `period`: `today`, `tomorrow`, or `week` (default: `today`)

## Steps

Run all steps silently (no raw JSON printed to the conversation at any point).
If a step fails, print the error and stop.

### Step 1 — Calendar event fetch

Run:

```
python -m gogos.calendar.calendar_fetch <account> <period>
```

Writes `latest-raw.json` under `.core/storage/calendar/<account>/events/<YYYY-MM-DD>/`.
Fail loudly and stop if this step fails.

### Step 2 — Normalise

Run:

```
python -m gogos.calendar.calendar_normalise <account> .core/storage/calendar/<account>/events/<date>/latest-raw.json
```

Writes `latest-slim.json` in the same dated directory.
Fail loudly and stop if this step fails.

### Step 3 — Brief via calendar-brief skill

Invoke the `calendar-brief` skill, passing:

- The contents of `latest-slim.json`.
- The period (`today`, `tomorrow`, or `week`).

**Do not print the brief JSON to the conversation.**
Hold it in memory for Step 4.

The skill returns strict JSON in this shape:

```json
{
  "account": "personal",
  "period": "today",
  "event_count": 3,
  "summary": "One sentence overview.",
  "focus_gaps": ["09:00–11:00 — 2h unblocked window"],
  "risks": ["Back-to-back: Standup ends 10:00, Design Review starts 10:00"],
  "events": [
    {
      "id": "<event id>",
      "summary": "<event title>",
      "prep": "What to prepare.",
      "notes": "Context notes."
    }
  ]
}
```

Every `id` must match a real event `id` from `latest-slim.json`.

### Step 4 — Write brief JSON

Write the brief JSON to a temp file, then run:

```
python -m gogos.calendar.calendar_report <account> /tmp/calendar_brief_output.json \
  .core/storage/calendar/<account>/events/<date>/latest-slim.json
```

Writes `latest.md` and `latest.html` under `.core/storage/reports/calendar/<account>/<YYYY-MM-DD>/`.
Fail loudly and stop if this step fails.

### Step 5 — Display report

Read the output file and **print its contents to the conversation** as the final output:

```
cat .core/storage/reports/calendar/<account>/<date>/latest.md
```

The script also opens `latest.html` in Google Chrome automatically.
No write-back to Google Calendar.
