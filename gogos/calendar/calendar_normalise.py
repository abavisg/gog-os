"""Google Calendar event normalisation — pure function core + thin I/O wrapper.

Entry point: normalise(account, raw_path) or run as
  python -m gogos.calendar.calendar_normalise <account> <raw_json_path>
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from gogos.auth.accounts import resolve_account
from gogos.paths import latest_alias, storage_path


def _parse_utc(dt_str: str) -> str:
    """Parse an RFC-3339 datetime string and return UTC ISO-8601. Returns '' on failure."""
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            return dt.isoformat() + "Z"
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""


def _duration_minutes(event: dict) -> int | None:
    """Return event duration in minutes, or None for all-day events."""
    if event.get("all_day"):
        return None
    start = _parse_utc(event.get("start_datetime", ""))
    end = _parse_utc(event.get("end_datetime", ""))
    if not start or not end:
        return None
    try:
        delta = datetime.fromisoformat(end) - datetime.fromisoformat(start)
        return max(0, int(delta.total_seconds() // 60))
    except Exception:
        return None


def _effective_start(event: dict) -> str:
    """Return the best available start time as UTC ISO-8601 (or date string for all-day)."""
    if event.get("all_day"):
        return event.get("start_date", "")
    return _parse_utc(event.get("start_datetime", ""))


def normalise_event(raw: dict) -> dict:
    """Pure function: projected raw event dict → normalised schema dict."""
    return {
        "id": raw.get("id", ""),
        "summary": raw.get("summary", "") or "(No title)",
        "status": raw.get("status", ""),
        "start": _effective_start(raw),
        "start_datetime_utc": _parse_utc(raw.get("start_datetime", "")),
        "end_datetime_utc": _parse_utc(raw.get("end_datetime", "")),
        "all_day": raw.get("all_day", False),
        "duration_minutes": _duration_minutes(raw),
        "location": raw.get("location", ""),
        "organizer_email": raw.get("organizer_email", ""),
        "organizer_name": raw.get("organizer_name", ""),
        "attendees": raw.get("attendees", []),
        "attendee_count": raw.get("attendee_count", 0),
        "has_conference": raw.get("conference_data", False),
        "is_recurring": raw.get("recurrence", False),
        "visibility": raw.get("visibility", "default"),
        "transparency": raw.get("transparency", "opaque"),
        "html_link": raw.get("html_link", ""),
        "source": "google_calendar",
    }


def normalise_raw(raw_data: dict) -> dict:
    """Normalise a full raw fetch output dict (as written by calendar_fetch)."""
    account = raw_data.get("account", "")
    period = raw_data.get("period", "")
    events = [normalise_event(e) for e in raw_data.get("events", [])]
    return {
        "account": account,
        "period": period,
        "time_min": raw_data.get("time_min", ""),
        "time_max": raw_data.get("time_max", ""),
        "count": len(events),
        "events": events,
        "source": "google_calendar",
    }


def normalise(account: str, raw_path: Path) -> int:
    """I/O wrapper: read raw JSON, normalise, write slim JSON + alias. Returns exit code."""
    try:
        raw_data = json.loads(raw_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read raw file {raw_path}: {exc}", file=sys.stderr)
        return 1

    result = normalise_raw(raw_data)

    # Resolve the alias to its canonical email so calendar fetch/normalise agree
    # on the storage directory regardless of the alias passed on the CLI.
    account = resolve_account(account)
    dated_dir = storage_path("calendar", account, "events")
    (dated_dir / "slim.json").write_text(json.dumps(result, indent=2))

    alias = latest_alias(dated_dir, "latest-slim.json")
    alias.write_text(json.dumps(result, indent=2))

    print(f"OK  Normalised {result['count']} event(s) → {alias}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage: python -m gogos.calendar.calendar_normalise <account> <raw_json_path>",
            file=sys.stderr,
        )
        sys.exit(1)
    sys.exit(normalise(sys.argv[1], Path(sys.argv[2])))
