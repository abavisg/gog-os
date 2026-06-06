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
    m = _reload()
    monkeypatch.setenv("GMAIL_MAX_RESULTS", "2")
    importlib.reload(m)

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

    rc = m.fetch("personal")
    assert rc == 0

    output = json.loads((tmp_path / "latest-raw.json").read_text())
    assert output["truncated"] is True
    assert output["count"] == 2
    assert len(output["messages"]) == 2

    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "truncated" in err.lower() or "GMAIL_MAX_RESULTS" in err


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
