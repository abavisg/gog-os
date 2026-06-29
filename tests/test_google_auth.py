"""Tests for gogos.auth.google_auth — all network calls mocked."""
from __future__ import annotations

import importlib
import json
import stat
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload():
    import gogos.auth.google_auth as m
    importlib.reload(m)
    return m


def _fake_valid_creds(scopes=None):
    creds = MagicMock()
    creds.valid = True
    creds.expired = False
    creds.refresh_token = "rt"
    creds.scopes = set(scopes or [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/calendar.readonly",
    ])
    creds.to_json.return_value = json.dumps({"token": "REDACTED"})
    return creds


def _fake_expired_creds(scopes=None):
    creds = MagicMock()
    creds.valid = False
    creds.expired = True
    creds.refresh_token = "rt"
    creds.scopes = set(scopes or [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/calendar.readonly",
    ])
    creds.to_json.return_value = json.dumps({"token": "REDACTED"})
    return creds


# ---------------------------------------------------------------------------
# Token path construction
# ---------------------------------------------------------------------------

def test_token_path_email():
    m = _reload()
    path = m._token_path("user@example.com")
    assert path.parts[-1] == "google_token.json"
    assert path.parts[-2] == "user@example.com"
    assert path.parts[-3] == "auth"


def test_token_path_second_email():
    m = _reload()
    path = m._token_path("work@company.com")
    assert path.parts[-2] == "work@company.com"


def test_token_path_is_absolute():
    m = _reload()
    assert m._token_path("user@example.com").is_absolute()


def test_token_path_under_storage_root():
    m = _reload()
    path = m._token_path("user@example.com")
    assert ".core/storage/auth/user@example.com/google_token.json" in str(path).replace("\\", "/")


# ---------------------------------------------------------------------------
# Valid token reuse
# ---------------------------------------------------------------------------

def test_valid_token_reused(tmp_path, monkeypatch):
    m = _reload()
    token_file = tmp_path / "google_token.json"
    token_file.write_text(json.dumps({"token": "x"}))

    valid_creds = _fake_valid_creds()
    monkeypatch.setattr(m, "_token_path", lambda account: token_file)

    with patch("gogos.auth.google_auth.Credentials.from_authorized_user_file", return_value=valid_creds):
        result = m.get_credentials("personal")

    assert result is valid_creds
    # No write should have happened (to_json not called for a reuse)
    valid_creds.refresh.assert_not_called()


# ---------------------------------------------------------------------------
# Expired token refresh
# ---------------------------------------------------------------------------

def test_expired_token_refreshed_and_rewritten(tmp_path, monkeypatch):
    m = _reload()
    token_file = tmp_path / "google_token.json"
    token_file.write_text(json.dumps({"token": "old"}))

    expired_creds = _fake_expired_creds()
    monkeypatch.setattr(m, "_token_path", lambda account: token_file)

    with patch("gogos.auth.google_auth.Credentials.from_authorized_user_file", return_value=expired_creds), \
         patch("gogos.auth.google_auth.Request") as mock_request:
        result = m.get_credentials("personal")

    expired_creds.refresh.assert_called_once()
    assert token_file.exists()


def test_refreshed_token_written_with_0600(tmp_path, monkeypatch):
    m = _reload()
    token_file = tmp_path / "google_token.json"
    token_file.write_text(json.dumps({"token": "old"}))

    expired_creds = _fake_expired_creds()
    monkeypatch.setattr(m, "_token_path", lambda account: token_file)

    with patch("gogos.auth.google_auth.Credentials.from_authorized_user_file", return_value=expired_creds), \
         patch("gogos.auth.google_auth.Request"):
        m.get_credentials("personal")

    file_mode = stat.S_IMODE(token_file.stat().st_mode)
    assert file_mode == 0o600, f"Expected 0o600, got {oct(file_mode)}"


# ---------------------------------------------------------------------------
# Missing token triggers InstalledAppFlow
# ---------------------------------------------------------------------------

def test_missing_token_runs_flow(tmp_path, monkeypatch):
    m = _reload()
    token_file = tmp_path / "google_token.json"
    # token_file does NOT exist

    new_creds = _fake_valid_creds()
    monkeypatch.setattr(m, "_token_path", lambda account: token_file)
    monkeypatch.setattr(m, "_credentials_path", lambda: tmp_path / "creds.json")

    mock_flow = MagicMock()
    mock_flow.run_local_server.return_value = new_creds

    with patch("gogos.auth.google_auth.InstalledAppFlow.from_client_secrets_file", return_value=mock_flow):
        result = m.get_credentials("personal")

    mock_flow.run_local_server.assert_called_once_with(port=0)
    assert token_file.exists()


def test_new_token_written_with_0600(tmp_path, monkeypatch):
    m = _reload()
    token_file = tmp_path / "google_token.json"

    new_creds = _fake_valid_creds()
    monkeypatch.setattr(m, "_token_path", lambda account: token_file)
    monkeypatch.setattr(m, "_credentials_path", lambda: tmp_path / "creds.json")

    mock_flow = MagicMock()
    mock_flow.run_local_server.return_value = new_creds

    with patch("gogos.auth.google_auth.InstalledAppFlow.from_client_secrets_file", return_value=mock_flow):
        m.get_credentials("personal")

    file_mode = stat.S_IMODE(token_file.stat().st_mode)
    assert file_mode == 0o600, f"Expected 0o600, got {oct(file_mode)}"


# ---------------------------------------------------------------------------
# Scope mismatch raises clear error
# ---------------------------------------------------------------------------

def test_scope_mismatch_raises(tmp_path, monkeypatch):
    m = _reload()
    token_file = tmp_path / "google_token.json"
    token_file.write_text(json.dumps({"token": "x"}))

    wrong_scope_creds = _fake_valid_creds(scopes=["https://www.googleapis.com/auth/gmail.send"])
    monkeypatch.setattr(m, "_token_path", lambda account: token_file)

    with patch("gogos.auth.google_auth.Credentials.from_authorized_user_file", return_value=wrong_scope_creds):
        with pytest.raises(RuntimeError, match="/logout-google personal"):
            m.get_credentials("personal")


def test_scope_mismatch_message_mentions_account(tmp_path, monkeypatch):
    m = _reload()
    token_file = tmp_path / "work_token.json"
    token_file.write_text(json.dumps({"token": "x"}))

    wrong_scope_creds = _fake_valid_creds(scopes=["https://mail.google.com/"])
    monkeypatch.setattr(m, "_token_path", lambda account: token_file)

    with patch("gogos.auth.google_auth.Credentials.from_authorized_user_file", return_value=wrong_scope_creds):
        with pytest.raises(RuntimeError, match="work"):
            m.get_credentials("work")


# ---------------------------------------------------------------------------
# Secret material must not appear in any raised exception message
# ---------------------------------------------------------------------------

def test_no_secret_in_exception_messages(tmp_path, monkeypatch):
    m = _reload()
    token_file = tmp_path / "google_token.json"
    token_file.write_text(json.dumps({"token": "x"}))

    secret = "CLIENT_SECRET_ULTRA_PRIVATE"
    wrong_scope_creds = _fake_valid_creds(scopes=["https://www.googleapis.com/auth/gmail.send"])
    wrong_scope_creds.to_json.return_value = json.dumps({"client_secret": secret})
    monkeypatch.setattr(m, "_token_path", lambda account: token_file)

    with patch("gogos.auth.google_auth.Credentials.from_authorized_user_file", return_value=wrong_scope_creds):
        with pytest.raises(RuntimeError) as exc_info:
            m.get_credentials("personal")

    assert secret not in str(exc_info.value)


# ---------------------------------------------------------------------------
# _write_token creates parent dirs and sets 0600
# ---------------------------------------------------------------------------

def test_write_token_creates_parents(tmp_path):
    m = _reload()
    deep_path = tmp_path / "auth" / "personal" / "google_token.json"
    creds = _fake_valid_creds()
    m._write_token(deep_path, creds)
    assert deep_path.exists()
    assert stat.S_IMODE(deep_path.stat().st_mode) == 0o600


# ---------------------------------------------------------------------------
# No real network — confirm Request is never called without mock
# ---------------------------------------------------------------------------

def test_valid_token_no_network(tmp_path, monkeypatch):
    """Valid token path must never call Request (no network)."""
    m = _reload()
    token_file = tmp_path / "google_token.json"
    token_file.write_text(json.dumps({"token": "x"}))

    valid_creds = _fake_valid_creds()
    monkeypatch.setattr(m, "_token_path", lambda account: token_file)

    with patch("gogos.auth.google_auth.Credentials.from_authorized_user_file", return_value=valid_creds), \
         patch("gogos.auth.google_auth.Request") as mock_req:
        m.get_credentials("personal")

    mock_req.assert_not_called()
