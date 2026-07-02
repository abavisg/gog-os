# Google Integrations

OAuth setup and the data GogOS reads from Gmail and Google Calendar.

## One-time Google Cloud setup

1. Create a Google Cloud project.
2. Enable the Gmail API and the Google Calendar API.
3. Configure the OAuth consent screen.
4. Create an OAuth Client ID of type **Desktop app**.
5. Download the credentials JSON to `.core/config/secrets/google_credentials.json` (gitignored — see [SECURITY.md](SECURITY.md)).
6. `/account-add <alias> <email>`, then `/login-google <alias>`.
7. Validate with `/setup-check`.

## OAuth model

`InstalledAppFlow` local desktop flow (`gogos/auth/google_auth.py`). One token per account containing both scopes, stored at `.core/storage/auth/<account>/google_token.json`, mode `0600`. Expired tokens refresh automatically; a scope change is detected and surfaced — `/logout-google <account>` and re-authenticate.

## Scopes (current)

```text
https://www.googleapis.com/auth/gmail.modify
https://www.googleapis.com/auth/calendar.readonly
```

`gmail.modify` exists solely so `/email-apply` can label + archive. It does not permit permanent deletion, and GogOS never calls a delete/trash endpoint — the enforcement lives in `gmail_apply` (see [EMAILOS.md](EMAILOS.md)). Calendar remains read-only; a Calendar write scope would be added only behind the approval gate.

## Gmail fetch

Message list query defaults to since-yesterday (window-controlled), each message fetched with `format="metadata"` and metadata headers only — `From, To, Subject, Date, List-Unsubscribe` — plus Gmail's snippet and label ids. No body is ever requested or stored (hard-asserted in code).

Normalised record (`gmail_normalise` is authoritative):

```json
{
  "id": "gmail-message-id",
  "thread_id": "gmail-thread-id",
  "account": "personal",
  "from": "Sender <sender@example.com>",
  "to": "Giorgos <giorgos@example.com>",
  "subject": "Subject",
  "date": "2026-06-04T08:10:00+00:00",
  "snippet": "Short Gmail snippet",
  "labels": ["INBOX", "UNREAD"],
  "unsubscribe": "<https://example.com/unsub>",
  "source": "gmail"
}
```

## Calendar fetch

Events list with `calendarId="primary"`, `singleEvents=True`, `orderBy="startTime"`, and `timeMin`/`timeMax` from the requested period (today/tomorrow/week). Safe projection: event descriptions are never fetched into storage.

Normalised record (`calendar_normalise` is authoritative): `id, summary, status, start, start_datetime_utc, end_datetime_utc, all_day, duration_minutes, location, organizer_email, organizer_name, attendees, attendee_count, has_conference, is_recurring, visibility, transparency, html_link, source, account` — datetimes stored UTC, rendered local at report time.

## Credential safety

`credentials.json`, token files, `.env`, and everything under `.core/storage/` are gitignored and never committed. Full rules in [SECURITY.md](SECURITY.md).
