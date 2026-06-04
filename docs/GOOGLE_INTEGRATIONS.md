# Google Integrations

## Source of truth

Use official Google Workspace Python quickstarts as the baseline for Gmail and Calendar integration.

## Requirements

- Python 3.10.7+ minimum.
- Prefer Python 3.11+ for the project.
- Google Cloud project.
- Gmail API enabled.
- Google Calendar API enabled.
- OAuth consent screen configured.
- OAuth Client ID of type Desktop app.
- `credentials.json` downloaded locally and never committed.

## Python libraries

```bash
python3 -m pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib python-dotenv pydantic pytest rich
```

## OAuth model

Use InstalledAppFlow for a local desktop flow.

Token files should be stored per account and per integration.

```text
.core/storage/auth/personal/google_token.json
.core/storage/auth/work/google_token.json
```

For simplicity, use one token per account containing both Gmail and Calendar scopes if both are enabled. If scopes change, delete and regenerate the token.

## Recommended read-only scopes

Gmail read-only:

```text
https://www.googleapis.com/auth/gmail.readonly
```

Calendar read-only:

```text
https://www.googleapis.com/auth/calendar.readonly
```

Later write scopes should be separate and gated by explicit user approval.

Potential later Gmail modify scope:

```text
https://www.googleapis.com/auth/gmail.modify
```

Potential later Calendar event scope:

```text
https://www.googleapis.com/auth/calendar.events
```

Do not add write scopes in the MVP.

## Gmail fetch strategy

Default mode: slim.

Use Gmail message list query:

```text
in:inbox newer_than:2d
```

For each message, fetch metadata format:

```python
service.users().messages().get(
    userId="me",
    id=message_id,
    format="metadata",
    metadataHeaders=["From", "To", "Subject", "Date"]
).execute()
```

Normalised email record:

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
  "source": "gmail"
}
```

## Calendar fetch strategy

Use Calendar API events list with:

- `calendarId="primary"`
- `singleEvents=True`
- `orderBy="startTime"`
- `timeMin` and `timeMax` based on requested period.

Normalised event record:

```json
{
  "id": "calendar-event-id",
  "account": "personal",
  "calendar_id": "primary",
  "title": "Event title",
  "start": "2026-06-04T09:00:00+01:00",
  "end": "2026-06-04T09:30:00+01:00",
  "all_day": false,
  "location": "",
  "attendees": [],
  "status": "confirmed",
  "description_present": true,
  "source": "google_calendar"
}
```

## Credential safety

Never commit:

- `credentials.json`
- token files
- `.env`
- report files containing private data
- raw Gmail/Calendar snapshots

Add these to `.gitignore`.

## Setup steps for user

1. Create Google Cloud project.
2. Enable Gmail API.
3. Enable Google Calendar API.
4. Configure OAuth consent screen.
5. Create OAuth Client ID, Desktop app.
6. Download credentials JSON.
7. Place it under `.core/config/secrets/google_credentials.json`.
8. Run `/login-google personal`.
9. Validate with `/setup-check`.
