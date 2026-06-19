"""Tests for gogos.gmail.gmail_fetch — all Gmail API calls mocked, no network."""
from __future__ import annotations

import importlib
import json
from unittest.mock import MagicMock

import pytest


def _reload():
    import gogos.gmail.gmail_fetch as m
    importlib.reload(m)
    return m


def _clean_api_record(msg_id: str = "msg1") -> dict:
    """Minimal realistic metadata-format API response with payload.headers."""
    return {
        "id": msg_id,
        "threadId": f"t{msg_id}",
        "labelIds": ["INBOX"],
        "snippet": "hello",
        "sizeEstimate": 1024,
        "historyId": "999",
        "internalDate": "1749196800000",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "alice@example.com"},
                {"name": "To", "value": "me@example.com"},
                {"name": "Subject", "value": "Test subject"},
                {"name": "Date", "value": "Fri, 06 Jun 2026 08:00:00 +0000"},
            ],
        },
    }


# ---------------------------------------------------------------------------
# Privacy gate — metadata envelope (payload.headers only) must PASS
# ---------------------------------------------------------------------------

def test_privacy_gate_passes_metadata_payload_with_headers_only():
    m = _reload()
    record = {
        "id": "x",
        "payload": {
            "mimeType": "text/plain",
            "headers": [{"name": "From", "value": "a@b.com"}],
        },
    }
    m._privacy_gate(record)  # must not raise


def test_privacy_gate_passes_payload_with_no_body():
    m = _reload()
    record = {"id": "x", "payload": {"mimeType": "text/plain", "headers": []}}
    m._privacy_gate(record)  # must not raise


def test_privacy_gate_passes_clean_record_no_payload():
    m = _reload()
    record = {
        "id": "x",
        "threadId": "t1",
        "snippet": "hello",
        "labelIds": ["INBOX"],
        "headers": [],
    }
    m._privacy_gate(record)  # must not raise


def test_privacy_gate_passes_payload_none():
    """payload key absent or None is fine."""
    m = _reload()
    record = {"id": "x", "snippet": "hi"}
    m._privacy_gate(record)  # must not raise


# ---------------------------------------------------------------------------
# Privacy gate — body data anywhere in the tree MUST fail
# ---------------------------------------------------------------------------

def test_privacy_gate_blocks_payload_body_data():
    m = _reload()
    record = {
        "id": "x",
        "payload": {
            "mimeType": "text/plain",
            "headers": [],
            "body": {"size": 42, "data": "c2VjcmV0"},
        },
    }
    with pytest.raises(RuntimeError, match="PRIVACY VIOLATION"):
        m._privacy_gate(record)


def test_privacy_gate_blocks_payload_parts_body_data():
    m = _reload()
    record = {
        "id": "x",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [],
            "parts": [
                {"mimeType": "text/plain", "body": {"size": 10, "data": "aGVsbG8="}},
            ],
        },
    }
    with pytest.raises(RuntimeError, match="PRIVACY VIOLATION"):
        m._privacy_gate(record)


def test_privacy_gate_blocks_nested_parts_body_data():
    """Deeply nested part with body data must be caught."""
    m = _reload()
    record = {
        "id": "x",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [],
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {"mimeType": "text/html", "body": {"data": "PGh0bWw+"}},
                    ],
                },
            ],
        },
    }
    with pytest.raises(RuntimeError, match="PRIVACY VIOLATION"):
        m._privacy_gate(record)


def test_privacy_gate_blocks_payload_with_unexpected_keys():
    """Payload keys outside the safe set (e.g. 'raw') are a violation."""
    m = _reload()
    record = {
        "id": "x",
        "payload": {"mimeType": "text/plain", "headers": [], "raw": "base64data"},
    }
    with pytest.raises(RuntimeError, match="PRIVACY VIOLATION"):
        m._privacy_gate(record)


def test_privacy_gate_blocks_raw_field():
    m = _reload()
    record = {"id": "x", "raw": "base64encodedcontent"}
    with pytest.raises(RuntimeError, match="PRIVACY VIOLATION"):
        m._privacy_gate(record)


def test_privacy_gate_blocks_data_field():
    m = _reload()
    record = {"id": "x", "data": "somedata"}
    with pytest.raises(RuntimeError, match="PRIVACY VIOLATION"):
        m._privacy_gate(record)


def test_privacy_gate_blocks_top_level_body_with_data():
    m = _reload()
    record = {"id": "x", "body": {"data": "secret content"}}
    with pytest.raises(RuntimeError, match="PRIVACY VIOLATION"):
        m._privacy_gate(record)


def test_privacy_gate_passes_top_level_body_with_no_data():
    """body present but empty (size only, no data) is acceptable."""
    m = _reload()
    record = {"id": "x", "body": {"size": 0}}
    m._privacy_gate(record)  # must not raise


# ---------------------------------------------------------------------------
# _project_message — safe projection
# ---------------------------------------------------------------------------

def test_project_extracts_headers_from_payload():
    m = _reload()
    record = _clean_api_record()
    projected = m._project_message(record)
    assert projected["headers"] == record["payload"]["headers"]


def test_project_drops_payload_key():
    m = _reload()
    record = _clean_api_record()
    projected = m._project_message(record)
    assert "payload" not in projected


def test_project_drops_size_estimate_and_history_id():
    m = _reload()
    record = _clean_api_record()
    projected = m._project_message(record)
    assert "sizeEstimate" not in projected
    assert "historyId" not in projected


def test_project_preserves_safe_fields():
    m = _reload()
    record = _clean_api_record("abc")
    projected = m._project_message(record)
    assert projected["id"] == "abc"
    assert projected["threadId"] == "tabc"
    assert projected["labelIds"] == ["INBOX"]
    assert projected["snippet"] == "hello"
    assert projected["internalDate"] == "1749196800000"


def test_project_no_body_data_in_output():
    m = _reload()
    record = _clean_api_record()
    projected = m._project_message(record)
    assert "body" not in projected
    assert "raw" not in projected
    assert "data" not in projected


def test_project_handles_missing_payload():
    m = _reload()
    record = {"id": "x", "threadId": "t", "snippet": "hi", "labelIds": []}
    projected = m._project_message(record)
    assert projected["headers"] == []
    assert "payload" not in projected


# ---------------------------------------------------------------------------
# metadata get call uses format="metadata" and exact headers
# ---------------------------------------------------------------------------

def test_get_uses_metadata_format(tmp_path, monkeypatch):
    m = _reload()
    svc = MagicMock()
    list_resp = MagicMock()
    list_resp.execute.return_value = {"messages": [{"id": "msg1"}]}
    svc.users().messages().list.return_value = list_resp

    get_mock = MagicMock()
    get_mock.execute.return_value = _clean_api_record("msg1")
    captured = {}

    def _get(**kwargs):
        captured.update(kwargs)
        return get_mock

    svc.users().messages().get.side_effect = _get

    monkeypatch.setattr(m, "_build_service", lambda account: svc)
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: tmp_path / f)

    m.fetch("personal")

    assert captured.get("format") == "metadata"
    assert captured.get("metadataHeaders") == ["From", "To", "Subject", "Date"]


# ---------------------------------------------------------------------------
# fetch() — account validation
# ---------------------------------------------------------------------------

def test_fetch_unknown_account_exits_nonzero(monkeypatch):
    m = _reload()
    monkeypatch.setenv("GOGOS_ACCOUNTS", "personal,work")
    result = m.fetch("bogus", "all")
    assert result == 1


def test_fetch_known_account_passes_validation(tmp_path, monkeypatch):
    m = _reload()
    monkeypatch.setenv("GOGOS_ACCOUNTS", "personal,work")
    svc = MagicMock()
    svc.users().messages().list().execute.return_value = {"messages": []}
    monkeypatch.setattr(m, "_build_service", lambda account: svc)
    monkeypatch.setattr("gogos.paths.STORAGE_ROOT", tmp_path / ".core/storage")
    result = m.fetch("work", "all")
    assert result == 0


# ---------------------------------------------------------------------------
# fetch() — privacy gate integration: body in API response → exit 1
# ---------------------------------------------------------------------------

def test_fetch_fails_when_body_data_in_response(tmp_path, monkeypatch):
    m = _reload()
    bad_msg = {
        "id": "msg1", "threadId": "t1", "snippet": "hi",
        "labelIds": [], "internalDate": "0",
        "payload": {
            "mimeType": "text/plain",
            "headers": [],
            "body": {"data": "secret content"},
        },
    }
    svc = MagicMock()
    list_resp = MagicMock()
    list_resp.execute.return_value = {"messages": [{"id": "msg1"}]}
    svc.users().messages().list.return_value = list_resp

    get_mock = MagicMock()
    get_mock.execute.return_value = bad_msg
    svc.users().messages().get.return_value = get_mock

    monkeypatch.setattr(m, "_build_service", lambda account: svc)
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: tmp_path / f)

    rc = m.fetch("personal")
    assert rc == 1

    # No output file should have been written
    assert not (tmp_path / "latest-raw.json").exists()


def test_fetch_fails_when_raw_field_in_response(tmp_path, monkeypatch):
    m = _reload()
    bad_msg = {
        "id": "msg1", "threadId": "t1", "snippet": "hi",
        "labelIds": [], "internalDate": "0", "raw": "base64content",
    }
    svc = MagicMock()
    list_resp = MagicMock()
    list_resp.execute.return_value = {"messages": [{"id": "msg1"}]}
    svc.users().messages().list.return_value = list_resp

    get_mock = MagicMock()
    get_mock.execute.return_value = bad_msg
    svc.users().messages().get.return_value = get_mock

    monkeypatch.setattr(m, "_build_service", lambda account: svc)
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: tmp_path / f)

    rc = m.fetch("personal")
    assert rc == 1
    assert not (tmp_path / "latest-raw.json").exists()


def test_fetch_succeeds_with_metadata_payload(tmp_path, monkeypatch):
    """A real-world metadata response with payload.headers only must succeed."""
    m = _reload()
    svc = MagicMock()
    list_resp = MagicMock()
    list_resp.execute.return_value = {"messages": [{"id": "msg1"}]}
    svc.users().messages().list.return_value = list_resp

    get_mock = MagicMock()
    get_mock.execute.return_value = _clean_api_record("msg1")
    svc.users().messages().get.return_value = get_mock

    monkeypatch.setattr(m, "_build_service", lambda account: svc)
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: tmp_path / f)

    rc = m.fetch("personal")
    assert rc == 0
    assert (tmp_path / "latest-raw.json").exists()


# ---------------------------------------------------------------------------
# Truncation flag and warning
# ---------------------------------------------------------------------------

def test_truncation_flag_set_at_max(tmp_path, monkeypatch, capsys):
    """Numeric window of 2 with 3 available messages must truncate to 2."""
    m = _reload()

    msgs = [_clean_api_record(f"msg{i}") for i in range(3)]

    svc = MagicMock()
    list_resp = MagicMock()
    list_resp.execute.return_value = {"messages": [{"id": r["id"]} for r in msgs]}
    svc.users().messages().list.return_value = list_resp

    def _get(**kwargs):
        msg_id = kwargs["id"]
        rec = next(x for x in msgs if x["id"] == msg_id)
        inner = MagicMock()
        inner.execute.return_value = rec
        return inner

    svc.users().messages().get.side_effect = _get

    monkeypatch.setattr(m, "_build_service", lambda account: svc)
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: tmp_path / f)

    rc = m.fetch("personal", "2")
    assert rc == 0

    output = json.loads((tmp_path / "latest-raw.json").read_text())
    assert output["truncated"] is True
    assert output["count"] == 2
    assert len(output["messages"]) == 2

    err = capsys.readouterr().err
    assert "WARNING" in err


# ---------------------------------------------------------------------------
# Empty inbox
# ---------------------------------------------------------------------------

def test_empty_inbox_writes_valid_file(tmp_path, monkeypatch):
    m = _reload()
    svc = MagicMock()
    list_resp = MagicMock()
    list_resp.execute.return_value = {"messages": []}
    svc.users().messages().list.return_value = list_resp

    monkeypatch.setattr(m, "_build_service", lambda account: svc)
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: tmp_path / f)

    rc = m.fetch("personal")
    assert rc == 0

    alias = tmp_path / "latest-raw.json"
    assert alias.exists()
    data = json.loads(alias.read_text())
    assert data["messages"] == []
    assert data["truncated"] is False
    assert "count" in data


# ---------------------------------------------------------------------------
# Dated artefact + latest-raw.json alias both written
# ---------------------------------------------------------------------------

def test_both_dated_and_alias_written(tmp_path, monkeypatch):
    m = _reload()
    svc = MagicMock()
    list_resp = MagicMock()
    list_resp.execute.return_value = {"messages": [{"id": "msg1"}]}
    svc.users().messages().list.return_value = list_resp
    get_mock = MagicMock()
    get_mock.execute.return_value = _clean_api_record("msg1")
    svc.users().messages().get.return_value = get_mock

    dated_dir = tmp_path / "dated"
    dated_dir.mkdir()
    alias_path = tmp_path / "latest-raw.json"

    monkeypatch.setattr(m, "_build_service", lambda account: svc)
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: dated_dir)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: alias_path)

    rc = m.fetch("personal")
    assert rc == 0
    assert (dated_dir / "raw.json").exists()
    assert alias_path.exists()


# ---------------------------------------------------------------------------
# No Gmail write API methods called
# ---------------------------------------------------------------------------

def test_no_write_api_calls(tmp_path, monkeypatch):
    m = _reload()
    svc = MagicMock()
    list_resp = MagicMock()
    list_resp.execute.return_value = {"messages": []}
    svc.users().messages().list.return_value = list_resp

    monkeypatch.setattr(m, "_build_service", lambda account: svc)
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: tmp_path / f)

    m.fetch("personal")

    svc.users().messages().modify.assert_not_called()
    svc.users().messages().trash.assert_not_called()
    svc.users().messages().delete.assert_not_called()
    svc.users().messages().send.assert_not_called()
    svc.users().labels().patch.assert_not_called()


# ---------------------------------------------------------------------------
# Raw output is a safe projection — no body/payload fields stored
# ---------------------------------------------------------------------------

def test_raw_output_contains_no_payload_key(tmp_path, monkeypatch):
    m = _reload()
    svc = MagicMock()
    list_resp = MagicMock()
    list_resp.execute.return_value = {"messages": [{"id": "msg1"}]}
    svc.users().messages().list.return_value = list_resp
    get_mock = MagicMock()
    get_mock.execute.return_value = _clean_api_record("msg1")
    svc.users().messages().get.return_value = get_mock

    monkeypatch.setattr(m, "_build_service", lambda account: svc)
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: tmp_path / f)

    m.fetch("personal")

    data = json.loads((tmp_path / "latest-raw.json").read_text())
    for record in data["messages"]:
        assert "payload" not in record, "payload must not be stored"
        assert "body" not in record, "body must not be stored"
        assert "raw" not in record, "raw must not be stored"
        assert "data" not in record, "data must not be stored"


def test_raw_output_headers_accessible_at_top_level(tmp_path, monkeypatch):
    """Projected records expose headers at top level for gmail_normalise."""
    m = _reload()
    svc = MagicMock()
    list_resp = MagicMock()
    list_resp.execute.return_value = {"messages": [{"id": "msg1"}]}
    svc.users().messages().list.return_value = list_resp
    get_mock = MagicMock()
    get_mock.execute.return_value = _clean_api_record("msg1")
    svc.users().messages().get.return_value = get_mock

    monkeypatch.setattr(m, "_build_service", lambda account: svc)
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: tmp_path / f)

    m.fetch("personal")

    data = json.loads((tmp_path / "latest-raw.json").read_text())
    assert len(data["messages"]) == 1
    rec = data["messages"][0]
    assert "headers" in rec
    assert isinstance(rec["headers"], list)
    from_headers = [h for h in rec["headers"] if h["name"] == "From"]
    assert from_headers, "From header must be present"
    assert from_headers[0]["value"] == "alice@example.com"


# ---------------------------------------------------------------------------
# _resolve_window — query / max_results logic
# ---------------------------------------------------------------------------

def test_resolve_window_yesterday_returns_after_before_query():
    m = _reload()
    query, max_results = m._resolve_window("yesterday")
    assert "after:" in query
    assert "before:" in query
    assert "in:inbox" in query
    assert max_results == 200


def test_resolve_window_yesterday_after_is_midnight_local():
    """after: epoch must be ≥ yesterday 00:00 and < today 00:00."""
    import time as _time
    from datetime import datetime, timedelta
    m = _reload()
    query, _ = m._resolve_window("yesterday")
    after_epoch = int(query.split("after:")[1].split()[0])
    local_now = datetime.now().astimezone()
    today_midnight = datetime.combine(local_now.date(), __import__("datetime").time.min, tzinfo=local_now.tzinfo)
    yesterday_midnight = today_midnight - timedelta(days=1)
    assert after_epoch == int(yesterday_midnight.timestamp())


def test_resolve_window_yesterday_before_is_approximately_now():
    """before: epoch must be within a few seconds of now."""
    import time as _time
    m = _reload()
    before_start = int(_time.time())
    query, _ = m._resolve_window("yesterday")
    before_end = int(_time.time())
    before_epoch = int(query.split("before:")[1].split()[0])
    assert before_start <= before_epoch <= before_end + 1


def test_resolve_window_all_returns_inbox_query():
    m = _reload()
    query, max_results = m._resolve_window("all")
    assert query == "in:inbox"
    assert max_results == 200


def test_resolve_window_numeric_sets_max_results():
    m = _reload()
    query, max_results = m._resolve_window("50")
    assert query == "in:inbox"
    assert max_results == 50


def test_resolve_window_large_numeric():
    m = _reload()
    _, max_results = m._resolve_window("500")
    assert max_results == 500


def test_resolve_window_invalid_raises():
    m = _reload()
    import pytest
    with pytest.raises(ValueError, match="Invalid window"):
        m._resolve_window("last_week")


def test_resolve_window_zero_raises():
    m = _reload()
    import pytest
    with pytest.raises(ValueError, match="positive integer"):
        m._resolve_window("0")


def test_resolve_window_negative_raises():
    m = _reload()
    import pytest
    with pytest.raises(ValueError, match="positive integer"):
        m._resolve_window("-5")


# ---------------------------------------------------------------------------
# fetch() — window argument wired through
# ---------------------------------------------------------------------------

def test_fetch_default_window_is_yesterday(tmp_path, monkeypatch):
    """fetch() with no window arg must use the 'yesterday' query."""
    m = _reload()
    captured_queries = []

    svc = MagicMock()

    def _list(**kwargs):
        captured_queries.append(kwargs.get("q", ""))
        inner = MagicMock()
        inner.execute.return_value = {"messages": []}
        return inner

    svc.users().messages().list.side_effect = _list
    monkeypatch.setattr(m, "_build_service", lambda account: svc)
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: tmp_path / f)

    rc = m.fetch("personal")
    assert rc == 0
    assert any("after:" in q for q in captured_queries)


def test_fetch_numeric_window_caps_results(tmp_path, monkeypatch):
    """fetch('personal', '3') must pass maxResults=3."""
    m = _reload()
    captured = {}

    svc = MagicMock()

    def _list(**kwargs):
        captured["maxResults"] = kwargs.get("maxResults")
        inner = MagicMock()
        inner.execute.return_value = {"messages": []}
        return inner

    svc.users().messages().list.side_effect = _list
    monkeypatch.setattr(m, "_build_service", lambda account: svc)
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: tmp_path / f)

    rc = m.fetch("personal", "3")
    assert rc == 0
    assert captured["maxResults"] == 3


def test_fetch_all_warns_when_truncated(tmp_path, monkeypatch, capsys):
    """fetch with window='all' must warn when result hits the 200-cap."""
    m = _reload()
    msgs = [_clean_api_record(f"m{i}") for i in range(201)]

    svc = MagicMock()
    list_resp = MagicMock()
    list_resp.execute.return_value = {"messages": [{"id": r["id"]} for r in msgs]}
    svc.users().messages().list.return_value = list_resp

    def _get(**kwargs):
        msg_id = kwargs["id"]
        rec = next(x for x in msgs if x["id"] == msg_id)
        inner = MagicMock()
        inner.execute.return_value = rec
        return inner

    svc.users().messages().get.side_effect = _get

    monkeypatch.setattr(m, "_build_service", lambda account: svc)
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: tmp_path / f)

    rc = m.fetch("personal", "all")
    assert rc == 0
    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "200" in err


def test_fetch_invalid_window_returns_exit_1(tmp_path, monkeypatch):
    m = _reload()
    monkeypatch.setattr(m, "_build_service", lambda account: MagicMock())
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: tmp_path / f)

    rc = m.fetch("personal", "badwindow")
    assert rc == 1


def test_fetch_output_records_window(tmp_path, monkeypatch):
    """The written JSON must include the window value."""
    m = _reload()
    svc = MagicMock()
    list_resp = MagicMock()
    list_resp.execute.return_value = {"messages": []}
    svc.users().messages().list.return_value = list_resp

    monkeypatch.setattr(m, "_build_service", lambda account: svc)
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: tmp_path / f)

    m.fetch("personal", "all")

    data = json.loads((tmp_path / "latest-raw.json").read_text())
    assert data["window"] == "all"
