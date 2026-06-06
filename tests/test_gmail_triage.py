"""Tests for gogos.gmail.gmail_triage — no network, no Gmail API."""
from __future__ import annotations

import importlib
import json


def _reload():
    import gogos.gmail.gmail_triage as m
    importlib.reload(m)
    return m


def _valid_triage(account: str = "personal", msg_ids: list[str] | None = None) -> dict:
    if msg_ids is None:
        msg_ids = ["18f1a2b3c4d5e6f7", "18f1a2b3c4d5e700"]
    return {
        "generated_at": "2026-06-06T10:00:00+00:00",
        "account": account,
        "items": [
            {
                "id": mid,
                "category": "Review",
                "confidence": 0.8,
                "rationale": "Test rationale",
                "suggested_action": "Review",
            }
            for mid in msg_ids
        ],
    }


# ---------------------------------------------------------------------------
# validate_triage
# ---------------------------------------------------------------------------

def test_validate_triage_passes_valid_input():
    m = _reload()
    m.validate_triage(_valid_triage())  # must not raise


def test_validate_triage_missing_top_level_key():
    import pytest
    m = _reload()
    bad = _valid_triage()
    del bad["generated_at"]
    with pytest.raises(ValueError, match="generated_at"):
        m.validate_triage(bad)


def test_validate_triage_missing_account_key():
    import pytest
    m = _reload()
    bad = _valid_triage()
    del bad["account"]
    with pytest.raises(ValueError, match="account"):
        m.validate_triage(bad)


def test_validate_triage_missing_items_key():
    import pytest
    m = _reload()
    bad = _valid_triage()
    del bad["items"]
    with pytest.raises(ValueError, match="items"):
        m.validate_triage(bad)


def test_validate_triage_items_not_list():
    import pytest
    m = _reload()
    bad = _valid_triage()
    bad["items"] = "not-a-list"
    with pytest.raises(ValueError, match="list"):
        m.validate_triage(bad)


def test_validate_triage_item_missing_id():
    import pytest
    m = _reload()
    triage = _valid_triage()
    del triage["items"][0]["id"]
    with pytest.raises(ValueError, match="id"):
        m.validate_triage(triage)


def test_validate_triage_item_missing_category():
    import pytest
    m = _reload()
    triage = _valid_triage()
    del triage["items"][0]["category"]
    with pytest.raises(ValueError, match="category"):
        m.validate_triage(triage)


def test_validate_triage_empty_items_list_passes():
    m = _reload()
    data = _valid_triage()
    data["items"] = []
    m.validate_triage(data)  # must not raise


# ---------------------------------------------------------------------------
# write_triage — I/O
# ---------------------------------------------------------------------------

def test_write_triage_creates_dated_file_and_alias(tmp_path, monkeypatch):
    m = _reload()
    dated_dir = tmp_path / "dated"
    dated_dir.mkdir()
    alias_path = tmp_path / "latest-triage.json"

    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: dated_dir)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: alias_path)

    rc = m.write_triage("personal", _valid_triage())

    assert rc == 0
    assert (dated_dir / "triage.json").exists()
    assert alias_path.exists()


def test_write_triage_alias_is_valid_json(tmp_path, monkeypatch):
    m = _reload()
    dated_dir = tmp_path / "dated"
    dated_dir.mkdir()
    alias_path = tmp_path / "latest-triage.json"

    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: dated_dir)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: alias_path)

    m.write_triage("personal", _valid_triage())

    data = json.loads(alias_path.read_text())
    assert "items" in data
    assert "generated_at" in data
    assert data["account"] == "personal"


def test_write_triage_message_ids_preserved(tmp_path, monkeypatch):
    m = _reload()
    dated_dir = tmp_path / "dated"
    dated_dir.mkdir()
    alias_path = tmp_path / "latest-triage.json"

    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: dated_dir)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: alias_path)

    ids = ["18f1a2b3c4d5e6f7", "18f1a2b3c4d5e700"]
    m.write_triage("personal", _valid_triage(msg_ids=ids))

    data = json.loads(alias_path.read_text())
    written_ids = [item["id"] for item in data["items"]]
    assert written_ids == ids


def test_write_triage_invalid_schema_returns_1(tmp_path, monkeypatch):
    m = _reload()
    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: tmp_path / f)

    bad = {"not": "valid"}
    rc = m.write_triage("personal", bad)
    assert rc == 1


def test_write_triage_uses_triage_storage_path(tmp_path, monkeypatch):
    """storage_path must be called with module='gmail', kind='triage'."""
    m = _reload()
    calls = []
    dated_dir = tmp_path / "dated"
    dated_dir.mkdir()

    def capturing_storage_path(module, account, kind, **kw):
        calls.append((module, account, kind))
        return dated_dir

    monkeypatch.setattr(m, "storage_path", capturing_storage_path)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: tmp_path / f)

    m.write_triage("personal", _valid_triage())

    assert len(calls) == 1
    assert calls[0] == ("gmail", "personal", "triage")


def test_write_triage_dated_and_alias_identical(tmp_path, monkeypatch):
    m = _reload()
    dated_dir = tmp_path / "dated"
    dated_dir.mkdir()
    alias_path = tmp_path / "latest-triage.json"

    monkeypatch.setattr(m, "storage_path", lambda *a, **kw: dated_dir)
    monkeypatch.setattr(m, "latest_alias", lambda d, f: alias_path)

    m.write_triage("personal", _valid_triage())

    dated_content = (dated_dir / "triage.json").read_text()
    alias_content = alias_path.read_text()
    assert dated_content == alias_content
