"""Tests for gogos.gmail.gmail_normalise — fixture-only, no network."""
from __future__ import annotations

import importlib
import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
RAW_SAMPLE = FIXTURES / "gmail_raw_sample.json"

_SCHEMA_KEYS = ("id", "thread_id", "account", "from", "to",
                "subject", "date", "snippet", "labels", "source")
_FORBIDDEN_KEYS = ("payload", "body", "raw", "data", "parts")


def _reload():
    import gogos.gmail.gmail_normalise as m
    importlib.reload(m)
    return m


def _raw_sample() -> dict:
    return json.loads(RAW_SAMPLE.read_text())


# ---------------------------------------------------------------------------
# Fixture sanity
# ---------------------------------------------------------------------------

def test_fixture_file_exists():
    assert RAW_SAMPLE.exists(), f"Fixture missing: {RAW_SAMPLE}"


def test_fixture_has_messages():
    data = _raw_sample()
    assert len(data["messages"]) > 0


# ---------------------------------------------------------------------------
# normalise_message — pure function
# ---------------------------------------------------------------------------

def test_schema_keys_present():
    m = _reload()
    raw_msg = _raw_sample()["messages"][0]
    result = m.normalise_message(raw_msg, "personal")
    for key in _SCHEMA_KEYS:
        assert key in result, f"Missing key: {key}"


def test_schema_no_forbidden_keys():
    m = _reload()
    raw_msg = _raw_sample()["messages"][0]
    result = m.normalise_message(raw_msg, "personal")
    for key in _FORBIDDEN_KEYS:
        assert key not in result, f"Forbidden key present: {key}"


def test_id_and_thread_id_copied():
    m = _reload()
    raw_msg = _raw_sample()["messages"][0]
    result = m.normalise_message(raw_msg, "personal")
    assert result["id"] == raw_msg["id"]
    assert result["thread_id"] == raw_msg["threadId"]


def test_account_injected():
    m = _reload()
    raw_msg = _raw_sample()["messages"][0]
    result = m.normalise_message(raw_msg, "work")
    assert result["account"] == "work"


def test_source_is_gmail():
    m = _reload()
    raw_msg = _raw_sample()["messages"][0]
    result = m.normalise_message(raw_msg, "personal")
    assert result["source"] == "gmail"


def test_labels_preserved():
    m = _reload()
    raw_msg = _raw_sample()["messages"][0]
    result = m.normalise_message(raw_msg, "personal")
    assert result["labels"] == raw_msg["labelIds"]
    assert "INBOX" in result["labels"]
    assert "UNREAD" in result["labels"]


def test_snippet_preserved():
    m = _reload()
    raw_msg = _raw_sample()["messages"][0]
    result = m.normalise_message(raw_msg, "personal")
    assert result["snippet"] == raw_msg["snippet"]


def test_from_header_extracted():
    m = _reload()
    raw_msg = _raw_sample()["messages"][0]
    result = m.normalise_message(raw_msg, "personal")
    assert "alice@example.com" in result["from"]


def test_subject_header_extracted():
    m = _reload()
    raw_msg = _raw_sample()["messages"][0]
    result = m.normalise_message(raw_msg, "personal")
    assert result["subject"] == "Meeting tomorrow"


# ---------------------------------------------------------------------------
# UTC date normalisation
# ---------------------------------------------------------------------------

def test_date_is_utc_iso8601_from_utc_input():
    """Date header already in UTC (+0000) → stored as UTC ISO-8601."""
    m = _reload()
    raw_msg = _raw_sample()["messages"][0]  # Date: Fri, 06 Jun 2026 08:00:00 +0000
    result = m.normalise_message(raw_msg, "personal")
    assert result["date"] == "2026-06-06T08:00:00+00:00"


def test_date_is_utc_iso8601_from_offset_input():
    """Date header with +0100 offset → stored as UTC (subtract 1 hour)."""
    m = _reload()
    raw_msg = _raw_sample()["messages"][1]  # Date: Fri, 06 Jun 2026 09:00:00 +0100
    result = m.normalise_message(raw_msg, "personal")
    assert result["date"] == "2026-06-06T08:00:00+00:00"


def test_date_stored_as_string():
    m = _reload()
    raw_msg = _raw_sample()["messages"][0]
    result = m.normalise_message(raw_msg, "personal")
    assert isinstance(result["date"], str)


# ---------------------------------------------------------------------------
# Missing optional headers handled gracefully
# ---------------------------------------------------------------------------

def test_missing_subject_is_empty_string():
    """Third fixture message has no Subject header."""
    m = _reload()
    raw_msg = _raw_sample()["messages"][2]
    result = m.normalise_message(raw_msg, "personal")
    assert result["subject"] == ""


def test_missing_to_is_empty_string_or_present():
    """Third fixture message has empty To header."""
    m = _reload()
    raw_msg = _raw_sample()["messages"][2]
    result = m.normalise_message(raw_msg, "personal")
    assert isinstance(result["to"], str)


def test_no_headers_at_all_does_not_crash():
    m = _reload()
    raw_msg = {"id": "x", "threadId": "t", "snippet": "", "labelIds": []}
    result = m.normalise_message(raw_msg, "personal")
    assert result["from"] == ""
    assert result["to"] == ""
    assert result["subject"] == ""
    assert result["date"] == ""


def test_bad_date_header_returns_empty_string():
    m = _reload()
    raw_msg = {
        "id": "x", "threadId": "t", "snippet": "", "labelIds": [],
        "headers": [{"name": "Date", "value": "not-a-real-date"}],
    }
    result = m.normalise_message(raw_msg, "personal")
    assert result["date"] == ""


def test_empty_labels_is_list():
    m = _reload()
    raw_msg = {"id": "x", "threadId": "t", "snippet": "", "labelIds": []}
    result = m.normalise_message(raw_msg, "personal")
    assert result["labels"] == []
    assert isinstance(result["labels"], list)


# ---------------------------------------------------------------------------
# normalise_raw — batch normalisation
# ---------------------------------------------------------------------------

def test_normalise_raw_returns_all_messages():
    m = _reload()
    raw_data = _raw_sample()
    result = m.normalise_raw(raw_data)
    assert result["count"] == len(raw_data["messages"])
    assert len(result["messages"]) == len(raw_data["messages"])


def test_normalise_raw_account_propagated():
    m = _reload()
    result = m.normalise_raw(_raw_sample())
    for msg in result["messages"]:
        assert msg["account"] == "personal"


def test_normalise_raw_no_forbidden_fields():
    m = _reload()
    result = m.normalise_raw(_raw_sample())
    for msg in result["messages"]:
        for key in _FORBIDDEN_KEYS:
            assert key not in msg


# ---------------------------------------------------------------------------
# I/O wrapper — writes dated file + alias
# ---------------------------------------------------------------------------

def test_io_wrapper_writes_slim_and_alias(tmp_path, monkeypatch):
    m = _reload()
    dated_dir = tmp_path / "dated"
    dated_dir.mkdir()
    alias_path = tmp_path / "latest-slim.json"

    monkeypatch.setattr(m, "resolve_account", lambda a: a)
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: dated_dir)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: alias_path)

    rc = m.normalise("personal", RAW_SAMPLE)

    assert rc == 0
    assert (dated_dir / "slim.json").exists()
    assert alias_path.exists()


def test_io_wrapper_output_is_valid_json(tmp_path, monkeypatch):
    m = _reload()
    dated_dir = tmp_path / "dated"
    dated_dir.mkdir()
    alias_path = tmp_path / "latest-slim.json"

    monkeypatch.setattr(m, "resolve_account", lambda a: a)
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: dated_dir)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: alias_path)

    m.normalise("personal", RAW_SAMPLE)

    data = json.loads(alias_path.read_text())
    assert "messages" in data
    assert "count" in data
    assert data["source"] == "gmail"


def test_io_wrapper_missing_file_returns_1(tmp_path, monkeypatch):
    m = _reload()
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: tmp_path / f)

    rc = m.normalise("personal", tmp_path / "no_such_file.json")
    assert rc == 1
