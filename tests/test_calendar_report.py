"""Tests for gogos.calendar.calendar_report — pure renderers, no network."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


def _slim_data(events: list[dict] | None = None) -> dict:
    if events is None:
        events = [
            {
                "id": "e1",
                "summary": "Team standup",
                "status": "confirmed",
                "start": "2026-06-19T08:00:00+00:00",
                "start_datetime_utc": "2026-06-19T08:00:00+00:00",
                "end_datetime_utc": "2026-06-19T08:30:00+00:00",
                "all_day": False,
                "duration_minutes": 30,
                "location": "Google Meet",
                "organizer_email": "boss@example.com",
                "organizer_name": "Boss",
                "attendees": [{"email": "me@example.com", "self": True}],
                "attendee_count": 2,
                "has_conference": True,
                "is_recurring": True,
                "visibility": "default",
                "transparency": "opaque",
                "html_link": "https://cal.google.com/x",
                "source": "google_calendar",
            }
        ]
    return {
        "account": "personal",
        "period": "today",
        "time_min": "2026-06-19T00:00:00+01:00",
        "time_max": "2026-06-19T23:59:59+01:00",
        "count": len(events),
        "events": events,
        "source": "google_calendar",
    }


def _brief_data(events: list[dict] | None = None) -> dict:
    if events is None:
        events = [
            {
                "id": "e1",
                "summary": "Team standup",
                "prep": "Review yesterday's blockers.",
                "notes": "Daily sync with the team.",
            }
        ]
    return {
        "account": "personal",
        "period": "today",
        "event_count": len(events),
        "summary": "Light day with one morning standup.",
        "focus_gaps": ["09:00–17:00 — large afternoon block"],
        "risks": [],
        "events": events,
    }


# ---------------------------------------------------------------------------
# render_report — Markdown
# ---------------------------------------------------------------------------

def test_render_report_contains_header():
    from gogos.calendar.calendar_report import render_report
    brief = _brief_data()
    slim = _slim_data()
    md = render_report(brief, slim, Path("/tmp/brief.json"), Path("/tmp/slim.json"), "2026-06-19T09:00:00")
    assert "# Calendar Brief" in md
    assert "personal" in md
    assert "today" in md


def test_render_report_cites_sources():
    from gogos.calendar.calendar_report import render_report
    md = render_report(
        _brief_data(), _slim_data(),
        Path("/tmp/brief.json"), Path("/tmp/slim.json"),
        "2026-06-19T09:00:00"
    )
    assert "/tmp/brief.json" in md
    assert "/tmp/slim.json" in md


def test_render_report_contains_timestamp():
    from gogos.calendar.calendar_report import render_report
    md = render_report(
        _brief_data(), _slim_data(),
        Path("/tmp/b.json"), Path("/tmp/s.json"),
        "2026-06-19T09:00:00"
    )
    assert "2026-06-19" in md


def test_render_report_shows_summary():
    from gogos.calendar.calendar_report import render_report
    md = render_report(
        _brief_data(), _slim_data(),
        Path("/tmp/b.json"), Path("/tmp/s.json"),
    )
    assert "Light day with one morning standup" in md


def test_render_report_shows_focus_gaps():
    from gogos.calendar.calendar_report import render_report
    md = render_report(
        _brief_data(), _slim_data(),
        Path("/tmp/b.json"), Path("/tmp/s.json"),
    )
    assert "Focus Gaps" in md
    assert "09:00" in md


def test_render_report_shows_event_with_prep():
    from gogos.calendar.calendar_report import render_report
    md = render_report(
        _brief_data(), _slim_data(),
        Path("/tmp/b.json"), Path("/tmp/s.json"),
    )
    assert "Team standup" in md
    assert "Review yesterday" in md


def test_render_report_empty_events():
    from gogos.calendar.calendar_report import render_report
    brief = _brief_data(events=[])
    brief["event_count"] = 0
    brief["focus_gaps"] = []
    slim = _slim_data(events=[])
    md = render_report(brief, slim, Path("/tmp/b.json"), Path("/tmp/s.json"))
    assert "No events" in md


def test_render_report_no_risks_section_when_empty():
    from gogos.calendar.calendar_report import render_report
    brief = _brief_data()
    brief["risks"] = []
    md = render_report(brief, _slim_data(), Path("/tmp/b.json"), Path("/tmp/s.json"))
    assert "Risks" not in md


def test_render_report_shows_risks():
    from gogos.calendar.calendar_report import render_report
    brief = _brief_data()
    brief["risks"] = ["Back-to-back: meeting ends 10:00, next starts 10:00"]
    md = render_report(brief, _slim_data(), Path("/tmp/b.json"), Path("/tmp/s.json"))
    assert "Risks" in md
    assert "Back-to-back" in md


# ---------------------------------------------------------------------------
# render_html_report
# ---------------------------------------------------------------------------

def test_render_html_contains_doctype():
    from gogos.calendar.calendar_report import render_html_report
    html = render_html_report(
        _brief_data(), _slim_data(),
        Path("/tmp/b.json"), Path("/tmp/s.json"),
    )
    assert "<!DOCTYPE html>" in html


def test_render_html_escapes_content():
    from gogos.calendar.calendar_report import render_html_report
    brief = _brief_data()
    slim = _slim_data()
    slim["events"][0]["summary"] = "<script>alert(1)</script>"
    html = render_html_report(brief, slim, Path("/tmp/b.json"), Path("/tmp/s.json"))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_html_cites_sources():
    from gogos.calendar.calendar_report import render_html_report
    html = render_html_report(
        _brief_data(), _slim_data(),
        Path("/tmp/brief.json"), Path("/tmp/slim.json"),
    )
    assert "/tmp/brief.json" in html
    assert "/tmp/slim.json" in html


def test_render_html_shows_title():
    from gogos.calendar.calendar_report import render_html_report
    html = render_html_report(
        _brief_data(), _slim_data(),
        Path("/tmp/b.json"), Path("/tmp/s.json"),
    )
    assert "Calendar Brief" in html
    assert "personal" in html


def test_render_html_empty_events():
    from gogos.calendar.calendar_report import render_html_report
    brief = _brief_data(events=[])
    brief["event_count"] = 0
    slim = _slim_data(events=[])
    html = render_html_report(brief, slim, Path("/tmp/b.json"), Path("/tmp/s.json"))
    assert "No events" in html


# ---------------------------------------------------------------------------
# report() — I/O entry point
# ---------------------------------------------------------------------------

def test_report_io_writes_files(tmp_path, monkeypatch):
    from gogos.calendar import calendar_report
    monkeypatch.setattr("gogos.paths.STORAGE_ROOT", tmp_path / ".core/storage")

    brief_path = tmp_path / "brief.json"
    slim_path = tmp_path / "slim.json"
    brief_path.write_text(json.dumps(_brief_data()))
    slim_path.write_text(json.dumps(_slim_data()))

    with patch("subprocess.Popen"):
        result = calendar_report.report("personal", brief_path, slim_path)

    assert result == 0
    md_files = list((tmp_path / ".core/storage").rglob("latest.md"))
    html_files = list((tmp_path / ".core/storage").rglob("latest.html"))
    assert len(md_files) == 1
    assert len(html_files) == 1
    assert "Calendar Brief" in md_files[0].read_text()


def test_report_io_missing_brief(tmp_path, monkeypatch):
    from gogos.calendar.calendar_report import report
    monkeypatch.setattr("gogos.paths.STORAGE_ROOT", tmp_path / ".core/storage")
    slim_path = tmp_path / "slim.json"
    slim_path.write_text(json.dumps(_slim_data()))
    result = report("personal", tmp_path / "missing.json", slim_path)
    assert result == 1


def test_report_io_missing_slim(tmp_path, monkeypatch):
    from gogos.calendar.calendar_report import report
    monkeypatch.setattr("gogos.paths.STORAGE_ROOT", tmp_path / ".core/storage")
    brief_path = tmp_path / "brief.json"
    brief_path.write_text(json.dumps(_brief_data()))
    result = report("personal", brief_path, tmp_path / "missing.json")
    assert result == 1
