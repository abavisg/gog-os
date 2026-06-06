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


# ---------------------------------------------------------------------------
# Privacy gate — payload/body presence triggers failure
# ---------------------------------------------------------------------------

def test_privacy_gate_blocks_payload():
    m = _reload()
    record = {"id": "x", "payload": {"parts": [{"body": {"data": "secret"}}]}}
    with pytest.raises(RuntimeError, match="PRIVACY VIOLATION"):
        m._privacy_gate(record)


def test_privacy_gate_blocks_body_field():
    m = _reload()
    record = {"id": "x", "body": {"data": "secret"}}
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


def test_privacy_gate_passes_clean_record():
    m = _reload()
    record = {
        "id": "x",
        "threadId": "t1",
        "snippet": "hello",
        "labelIds": ["INBOX"],
        "headers": [],
    }
    m._privacy_gate(record)  # must not raise


def test_privacy_gate_payload_none_passes():
    """payload key present but value is None is not a violation."""
    m = _reload()
    record = {"id": "x", "payload": None}
    # payload=None should still raise because the key is present
    # — the gate is a hard field presence check
    with pytest.raises(RuntimeError, match="PRIVACY VIOLATION"):
        m._privacy_gate(record)


# ---------------------------------------------------------------------------
# metadata get call uses format="metadata" and exact headers
# ---------------------------------------------------------------------------

def test_get_uses_metadata_format(tmp_path, monkeypatch):
    m = _reload()
    msg = {
        "id": "msg1", "threadId": "t1", "snippet": "hi",
        "labelIds": [], "internalDate": "0", "headers": [],
    }
    svc = MagicMock()
    list_resp = MagicMock()
    list_resp.execute.return_value = {"messages": [{"id": "msg1"}]}
    svc.users().messages().list.return_value = list_resp

    get_mock = MagicMock()
    get_mock.execute.return_value = msg
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

def test_fetch_fails_when_body_in_response(tmp_path, monkeypatch):
    m = _reload()
    bad_msg = {
        "id": "msg1", "threadId": "t1", "snippet": "hi",
        "labelIds": [], "internalDate": "0", "headers": [],
        "body": {"data": "secret content"},
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


# ---------------------------------------------------------------------------
# Truncation flag and warning
# ---------------------------------------------------------------------------

def test_truncation_flag_set_at_max(tmp_path, monkeypatch, capsys):
    m = _reload()
    monkeypatch.setenv("GMAIL_MAX_RESULTS", "2")
    importlib.reload(m)

    # Return 3 ids from list — fetch will cap at 2 and set truncated=True
    msgs = [
        {"id": f"msg{i}", "threadId": f"t{i}", "snippet": f"s{i}",
         "labelIds": [], "internalDate": "0", "headers": []}
        for i in range(3)
    ]
    svc = MagicMock()
    list_resp = MagicMock()
    list_resp.execute.return_value = {"messages": [{"id": m2["id"]} for m2 in msgs]}
    svc.users().messages().list.return_value = list_resp

    get_mock = MagicMock()
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
    msg = {
        "id": "msg1", "threadId": "t1", "snippet": "hi",
        "labelIds": [], "internalDate": "0", "headers": [],
    }
    svc = MagicMock()
    list_resp = MagicMock()
    list_resp.execute.return_value = {"messages": [{"id": "msg1"}]}
    svc.users().messages().list.return_value = list_resp
    get_mock = MagicMock()
    get_mock.execute.return_value = msg
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

    # None of the write methods should have been called
    svc.users().messages().modify.assert_not_called()
    svc.users().messages().trash.assert_not_called()
    svc.users().messages().delete.assert_not_called()
    svc.users().messages().send.assert_not_called()
    svc.users().labels().patch.assert_not_called()


# ---------------------------------------------------------------------------
# Raw output contains no body material
# ---------------------------------------------------------------------------

def test_raw_output_has_no_bodies(tmp_path, monkeypatch):
    m = _reload()
    msg = {
        "id": "msg1", "threadId": "t1", "snippet": "hi",
        "labelIds": ["INBOX"], "internalDate": "0",
        "headers": [{"name": "From", "value": "a@b.com"}],
    }
    svc = MagicMock()
    list_resp = MagicMock()
    list_resp.execute.return_value = {"messages": [{"id": "msg1"}]}
    svc.users().messages().list.return_value = list_resp
    get_mock = MagicMock()
    get_mock.execute.return_value = msg
    svc.users().messages().get.return_value = get_mock

    monkeypatch.setattr(m, "_build_service", lambda account: svc)
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: tmp_path / f)

    m.fetch("personal")

    raw_text = (tmp_path / "latest-raw.json").read_text()
    # The word "body" should not appear as a key with content in the output
    data = json.loads(raw_text)
    for record in data["messages"]:
        assert "body" not in record or record.get("body") is None
        assert "raw" not in record
        assert "data" not in record
