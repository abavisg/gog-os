"""Tests for gogos.calendar.calendar_normalise — pure functions, no network."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _raw_event(event_id: str = "e1", all_day: bool = False) -> dict:
    if all_day:
        return {
            "id": event_id,
            "summary": "Holiday",
            "status": "confirmed",
            "all_day": True,
            "start_date": "2026-06-19",
            "start_datetime": "",
            "start_timezone": "",
            "end_date": "2026-06-20",
            "end_datetime": "",
            "end_timezone": "",
            "location": "",
            "organizer_email": "me@example.com",
            "organizer_name": "",
            "attendees": [],
            "attendee_count": 0,
            "conference_data": False,
            "recurrence": False,
            "visibility": "default",
            "transparency": "transparent",
            "html_link": "https://calendar.google.com/event?eid=x",
        }
    return {
        "id": event_id,
        "summary": "Team standup",
        "status": "confirmed",
        "all_day": False,
        "start_date": "",
        "start_datetime": "2026-06-19T09:00:00+01:00",
        "start_timezone": "Europe/London",
        "end_date": "",
        "end_datetime": "2026-06-19T09:30:00+01:00",
        "end_timezone": "Europe/London",
        "location": "Google Meet",
        "organizer_email": "boss@example.com",
        "organizer_name": "Boss",
        "attendees": [
            {"email": "me@example.com", "self": True, "response_status": "accepted",
             "display_name": "", "organizer": False},
        ],
        "attendee_count": 1,
        "conference_data": True,
        "recurrence": True,
        "visibility": "default",
        "transparency": "opaque",
        "html_link": "https://calendar.google.com/event?eid=y",
    }


def _raw_fetch_output(events: list[dict]) -> dict:
    return {
        "account": "personal",
        "period": "today",
        "time_min": "2026-06-19T00:00:00+01:00",
        "time_max": "2026-06-19T23:59:59+01:00",
        "count": len(events),
        "events": events,
        "truncated": False,
    }


# ---------------------------------------------------------------------------
# normalise_event — pure function
# ---------------------------------------------------------------------------

def test_normalise_event_schema():
    from gogos.calendar.calendar_normalise import normalise_event
    result = normalise_event(_raw_event("e1"))

    required_keys = {
        "id", "summary", "status", "start", "start_datetime_utc", "end_datetime_utc",
        "all_day", "duration_minutes", "location", "organizer_email", "organizer_name",
        "attendees", "attendee_count", "has_conference", "is_recurring",
        "visibility", "transparency", "html_link", "source",
    }
    assert required_keys.issubset(result.keys()), f"Missing keys: {required_keys - result.keys()}"
    assert result["source"] == "google_calendar"


def test_normalise_event_utc_conversion():
    from gogos.calendar.calendar_normalise import normalise_event
    result = normalise_event(_raw_event("e1"))
    # BST +01:00 → UTC = 08:00
    assert "08:00:00" in result["start_datetime_utc"]
    assert "+00:00" in result["start_datetime_utc"]


def test_normalise_event_duration_minutes():
    from gogos.calendar.calendar_normalise import normalise_event
    result = normalise_event(_raw_event("e1"))
    assert result["duration_minutes"] == 30


def test_normalise_event_all_day():
    from gogos.calendar.calendar_normalise import normalise_event
    result = normalise_event(_raw_event("e2", all_day=True))
    assert result["all_day"] is True
    assert result["duration_minutes"] is None
    assert result["start"] == "2026-06-19"


def test_normalise_event_no_summary_fallback():
    from gogos.calendar.calendar_normalise import normalise_event
    raw = _raw_event("e3")
    raw["summary"] = ""
    result = normalise_event(raw)
    assert result["summary"] == "(No title)"


def test_normalise_event_missing_datetime_graceful():
    from gogos.calendar.calendar_normalise import normalise_event
    raw = _raw_event("e4")
    raw["start_datetime"] = ""
    raw["end_datetime"] = ""
    result = normalise_event(raw)
    assert result["start_datetime_utc"] == ""
    assert result["duration_minutes"] is None


# ---------------------------------------------------------------------------
# normalise_raw — wraps events list
# ---------------------------------------------------------------------------

def test_normalise_raw_count():
    from gogos.calendar.calendar_normalise import normalise_raw
    events = [_raw_event("e1"), _raw_event("e2", all_day=True)]
    result = normalise_raw(_raw_fetch_output(events))
    assert result["count"] == 2
    assert result["account"] == "personal"
    assert result["period"] == "today"
    assert result["source"] == "google_calendar"


def test_normalise_raw_empty():
    from gogos.calendar.calendar_normalise import normalise_raw
    result = normalise_raw(_raw_fetch_output([]))
    assert result["count"] == 0
    assert result["events"] == []


# ---------------------------------------------------------------------------
# normalise() — I/O wrapper
# ---------------------------------------------------------------------------

def test_normalise_io(tmp_path, monkeypatch):
    from gogos.calendar import calendar_normalise
    monkeypatch.setattr("gogos.paths.STORAGE_ROOT", tmp_path / ".core/storage")
    monkeypatch.setattr(calendar_normalise, "resolve_account", lambda a: a)

    raw_path = tmp_path / "raw.json"
    raw_path.write_text(json.dumps(_raw_fetch_output([_raw_event("e1")])))

    result = calendar_normalise.normalise("personal", raw_path)
    assert result == 0

    slim_files = list((tmp_path / ".core/storage").rglob("latest-slim.json"))
    assert len(slim_files) == 1
    data = json.loads(slim_files[0].read_text())
    assert data["count"] == 1
    assert data["events"][0]["source"] == "google_calendar"


def test_normalise_io_missing_file(tmp_path):
    from gogos.calendar.calendar_normalise import normalise
    result = normalise("personal", tmp_path / "nonexistent.json")
    assert result == 1


def test_normalise_io_invalid_json(tmp_path):
    from gogos.calendar.calendar_normalise import normalise
    bad = tmp_path / "bad.json"
    bad.write_text("not json{{{")
    result = normalise("personal", bad)
    assert result == 1
