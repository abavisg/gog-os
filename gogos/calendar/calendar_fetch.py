"""Google Calendar event fetch — read-only, metadata only.

Entry point: fetch(account, period) or run as
  python -m gogos.calendar.calendar_fetch <account> [today|tomorrow|week]

period values:
  today     (default) — events from today 00:00 local time to today 23:59
  tomorrow  — events from tomorrow 00:00 to tomorrow 23:59
  week      — events from today 00:00 to 7 days from now 23:59
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

from gogos.auth.accounts import resolve_account
from gogos.auth.google_auth import get_credentials
from gogos.paths import latest_alias, storage_path

_DEFAULT_TZ = ZoneInfo(os.environ.get("GOGOS_TIMEZONE", "Europe/London"))
_MAX_RESULTS = 250
_VALID_PERIODS = {"today", "tomorrow", "week"}


def _resolve_period(period: str) -> tuple[str, str, str]:
    """Return (time_min_rfc3339, time_max_rfc3339, label) for the given period."""
    p = period.strip().lower()
    if p not in _VALID_PERIODS:
        raise ValueError(
            f"Invalid period '{period}'. Use 'today', 'tomorrow', or 'week'."
        )

    local_now = datetime.now(tz=_DEFAULT_TZ)
    today = local_now.date()

    if p == "today":
        start = datetime.combine(today, time.min, tzinfo=_DEFAULT_TZ)
        end = datetime.combine(today, time.max, tzinfo=_DEFAULT_TZ)
        label = "today"
    elif p == "tomorrow":
        tomorrow = today + timedelta(days=1)
        start = datetime.combine(tomorrow, time.min, tzinfo=_DEFAULT_TZ)
        end = datetime.combine(tomorrow, time.max, tzinfo=_DEFAULT_TZ)
        label = "tomorrow"
    else:  # week
        start = datetime.combine(today, time.min, tzinfo=_DEFAULT_TZ)
        end = datetime.combine(today + timedelta(days=7), time.max, tzinfo=_DEFAULT_TZ)
        label = "week"

    return start.isoformat(), end.isoformat(), label


def _build_service(account: str):
    creds = get_credentials(account)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _list_events(service, time_min: str, time_max: str) -> tuple[list[dict], bool]:
    """Return (events, truncated). Fetches from primary calendar only."""
    resp = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            maxResults=_MAX_RESULTS,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    items = resp.get("items", [])
    truncated = len(items) >= _MAX_RESULTS
    return items, truncated


def _safe_project(event: dict) -> dict:
    """Project a raw Calendar API event to the safe fields only — no full descriptions."""
    start = event.get("start", {})
    end = event.get("end", {})

    attendees_raw = event.get("attendees", []) or []
    attendees = [
        {
            "email": a.get("email", ""),
            "display_name": a.get("displayName", ""),
            "response_status": a.get("responseStatus", ""),
            "self": a.get("self", False),
            "organizer": a.get("organizer", False),
        }
        for a in attendees_raw
        if isinstance(a, dict)
    ]

    organizer = event.get("organizer", {}) or {}

    return {
        "id": event.get("id", ""),
        "summary": event.get("summary", ""),
        "status": event.get("status", ""),
        "html_link": event.get("htmlLink", ""),
        "created": event.get("created", ""),
        "updated": event.get("updated", ""),
        "start_date": start.get("date", ""),
        "start_datetime": start.get("dateTime", ""),
        "start_timezone": start.get("timeZone", ""),
        "end_date": end.get("date", ""),
        "end_datetime": end.get("dateTime", ""),
        "end_timezone": end.get("timeZone", ""),
        "all_day": bool(start.get("date") and not start.get("dateTime")),
        "location": event.get("location", ""),
        "organizer_email": organizer.get("email", ""),
        "organizer_name": organizer.get("displayName", ""),
        "attendees": attendees,
        "attendee_count": len(attendees),
        "conference_data": bool(event.get("conferenceData")),
        "recurrence": bool(event.get("recurrence") or event.get("recurringEventId")),
        "visibility": event.get("visibility", "default"),
        "transparency": event.get("transparency", "opaque"),
    }


def fetch(account: str, period: str = "today") -> int:
    """Fetch Calendar events for *account* and *period*. Returns exit code."""
    try:
        account = resolve_account(account)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        time_min, time_max, label = _resolve_period(period)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        service = _build_service(account)
        raw_events, truncated = _list_events(service, time_min, time_max)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if truncated:
        print(
            f"WARNING: result hit limit={_MAX_RESULTS}. Output may be truncated.",
            file=sys.stderr,
        )

    events = [_safe_project(e) for e in raw_events]

    output = {
        "account": account,
        "period": label,
        "time_min": time_min,
        "time_max": time_max,
        "events": events,
        "count": len(events),
        "truncated": truncated,
    }

    dated_dir = storage_path("calendar", account, "events")
    (dated_dir / "raw.json").write_text(json.dumps(output, indent=2))

    alias = latest_alias(dated_dir, "latest-raw.json")
    alias.write_text(json.dumps(output, indent=2))

    print(f"OK  Fetched {len(events)} event(s) [{label}] → {alias}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python -m gogos.calendar.calendar_fetch <account> [today|tomorrow|week]",
            file=sys.stderr,
        )
        sys.exit(1)
    _period = sys.argv[2] if len(sys.argv) > 2 else "today"
    sys.exit(fetch(sys.argv[1], _period))
