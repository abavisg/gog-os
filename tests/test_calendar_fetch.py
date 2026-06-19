"""Tests for gogos.calendar.calendar_fetch — all Calendar API calls mocked, no network."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


def _make_service(events: list[dict], next_page_token: str | None = None):
    resp = {"items": events}
    if next_page_token:
        resp["nextPageToken"] = next_page_token

    mock_list = MagicMock()
    mock_list.execute.return_value = resp

    mock_events = MagicMock()
    mock_events.list.return_value = mock_list

    svc = MagicMock()
    svc.events.return_value = mock_events
    return svc


def _sample_event(event_id: str = "evt1", all_day: bool = False) -> dict:
    if all_day:
        return {
            "id": event_id,
            "summary": "Holiday",
            "status": "confirmed",
            "htmlLink": "https://calendar.google.com/event?eid=xxx",
            "created": "2026-06-01T00:00:00.000Z",
            "updated": "2026-06-01T00:00:00.000Z",
            "start": {"date": "2026-06-19"},
            "end": {"date": "2026-06-20"},
            "organizer": {"email": "me@example.com"},
        }
    return {
        "id": event_id,
        "summary": "Team standup",
        "status": "confirmed",
        "htmlLink": "https://calendar.google.com/event?eid=xxx",
        "created": "2026-06-01T09:00:00.000Z",
        "updated": "2026-06-01T09:00:00.000Z",
        "start": {"dateTime": "2026-06-19T09:00:00+01:00", "timeZone": "Europe/London"},
        "end": {"dateTime": "2026-06-19T09:30:00+01:00", "timeZone": "Europe/London"},
        "organizer": {"email": "boss@example.com", "displayName": "Boss"},
        "attendees": [
            {"email": "me@example.com", "self": True, "responseStatus": "accepted"},
            {"email": "other@example.com", "responseStatus": "accepted"},
        ],
        "conferenceData": {"entryPoints": []},
    }


# ---------------------------------------------------------------------------
# _resolve_period
# ---------------------------------------------------------------------------

def test_resolve_period_today():
    from gogos.calendar.calendar_fetch import _resolve_period
    t_min, t_max, label = _resolve_period("today")
    assert label == "today"
    assert "T00:00:00" in t_min
    assert "T23:59:59" in t_max


def test_resolve_period_tomorrow():
    from gogos.calendar.calendar_fetch import _resolve_period
    t_min, t_max, label = _resolve_period("tomorrow")
    assert label == "tomorrow"


def test_resolve_period_week():
    from gogos.calendar.calendar_fetch import _resolve_period
    t_min, t_max, label = _resolve_period("week")
    assert label == "week"
    from datetime import datetime
    start = datetime.fromisoformat(t_min)
    end = datetime.fromisoformat(t_max)
    assert (end - start).days >= 6


def test_resolve_period_invalid():
    from gogos.calendar.calendar_fetch import _resolve_period
    with pytest.raises(ValueError, match="Invalid period"):
        _resolve_period("last_week")


def test_resolve_period_case_insensitive():
    from gogos.calendar.calendar_fetch import _resolve_period
    _, _, label = _resolve_period("TODAY")
    assert label == "today"


# ---------------------------------------------------------------------------
# _safe_project
# ---------------------------------------------------------------------------

def test_safe_project_timed_event():
    from gogos.calendar.calendar_fetch import _safe_project
    raw = _sample_event("e1")
    p = _safe_project(raw)
    assert p["id"] == "e1"
    assert p["summary"] == "Team standup"
    assert p["all_day"] is False
    assert p["start_datetime"] == "2026-06-19T09:00:00+01:00"
    assert p["conference_data"] is True
    assert p["attendee_count"] == 2
    assert len(p["attendees"]) == 2
    assert p["attendees"][0]["email"] == "me@example.com"
    assert p["attendees"][0]["self"] is True


def test_safe_project_all_day():
    from gogos.calendar.calendar_fetch import _safe_project
    raw = _sample_event("e2", all_day=True)
    p = _safe_project(raw)
    assert p["all_day"] is True
    assert p["start_date"] == "2026-06-19"
    assert p["start_datetime"] == ""
    assert p["conference_data"] is False


def test_safe_project_no_attendees():
    from gogos.calendar.calendar_fetch import _safe_project
    raw = _sample_event("e3")
    del raw["attendees"]
    p = _safe_project(raw)
    assert p["attendees"] == []
    assert p["attendee_count"] == 0


def test_safe_project_no_body_fields():
    """Projected output must never carry description or body."""
    from gogos.calendar.calendar_fetch import _safe_project
    raw = _sample_event("e4")
    raw["description"] = "Secret meeting notes"
    p = _safe_project(raw)
    assert "description" not in p
    assert "Secret" not in json.dumps(p)


# ---------------------------------------------------------------------------
# fetch() — account validation
# ---------------------------------------------------------------------------

def test_fetch_unknown_account_exits_nonzero(monkeypatch):
    from gogos.calendar import calendar_fetch
    monkeypatch.setenv("GOGOS_ACCOUNTS", "personal,work")
    result = calendar_fetch.fetch("bogus", "today")
    assert result == 1


def test_fetch_known_account_passes_validation(tmp_path, monkeypatch):
    from gogos.calendar import calendar_fetch
    monkeypatch.setenv("GOGOS_ACCOUNTS", "personal,work")
    monkeypatch.setattr(calendar_fetch, "_build_service", lambda account: _make_service([]))
    monkeypatch.setattr("gogos.paths.STORAGE_ROOT", tmp_path / ".core/storage")
    result = calendar_fetch.fetch("work", "today")
    assert result == 0


# ---------------------------------------------------------------------------
# fetch() — integration with mocked service
# ---------------------------------------------------------------------------

def test_fetch_writes_files(tmp_path, monkeypatch):
    from gogos.calendar import calendar_fetch

    monkeypatch.setattr(calendar_fetch, "_build_service", lambda account: _make_service([_sample_event()]))
    monkeypatch.setattr(
        "gogos.paths.STORAGE_ROOT", tmp_path / ".core/storage"
    )

    result = calendar_fetch.fetch("personal", "today")
    assert result == 0

    import gogos.paths as paths
    paths.STORAGE_ROOT = tmp_path / ".core/storage"
    import importlib
    importlib.reload(calendar_fetch)

    # Check file was written
    storage_files = list((tmp_path / ".core/storage").rglob("latest-raw.json"))
    assert len(storage_files) == 1
    data = json.loads(storage_files[0].read_text())
    assert data["count"] == 1
    assert data["events"][0]["id"] == "evt1"
    assert "description" not in json.dumps(data)


def test_fetch_empty_calendar(tmp_path, monkeypatch):
    from gogos.calendar import calendar_fetch
    monkeypatch.setattr(calendar_fetch, "_build_service", lambda account: _make_service([]))
    monkeypatch.setattr("gogos.paths.STORAGE_ROOT", tmp_path / ".core/storage")

    result = calendar_fetch.fetch("personal", "today")
    assert result == 0
    storage_files = list((tmp_path / ".core/storage").rglob("latest-raw.json"))
    data = json.loads(storage_files[0].read_text())
    assert data["count"] == 0
    assert data["events"] == []


def test_fetch_invalid_period_exits_nonzero(monkeypatch):
    from gogos.calendar import calendar_fetch
    monkeypatch.setattr(calendar_fetch, "_build_service", lambda account: _make_service([]))
    result = calendar_fetch.fetch("personal", "last_year")
    assert result == 1


def test_fetch_no_write_api_calls(tmp_path, monkeypatch):
    """Verify no mutating Calendar API methods are called."""
    from gogos.calendar import calendar_fetch

    svc = _make_service([_sample_event()])
    monkeypatch.setattr(calendar_fetch, "_build_service", lambda account: svc)
    monkeypatch.setattr("gogos.paths.STORAGE_ROOT", tmp_path / ".core/storage")

    calendar_fetch.fetch("personal", "today")

    # Only .events().list() should have been called — no insert/update/delete/patch
    events_mock = svc.events.return_value
    assert events_mock.list.called
    assert not hasattr(events_mock, "insert") or not events_mock.insert.called
    assert not hasattr(events_mock, "update") or not events_mock.update.called
    assert not hasattr(events_mock, "delete") or not events_mock.delete.called
