"""Tests for gogos.auth.logout — no real tokens, no network."""
from __future__ import annotations

import importlib
from unittest.mock import patch


def _reload():
    import gogos.auth.logout as m
    importlib.reload(m)
    return m


# ---------------------------------------------------------------------------
# Confirmation gate
# ---------------------------------------------------------------------------

def test_decline_leaves_token(tmp_path, monkeypatch, capsys):
    m = _reload()
    token = tmp_path / "auth" / "personal" / "google_token.json"
    token.parent.mkdir(parents=True)
    token.write_text("fake-token-data")

    monkeypatch.setattr(m, "_AUTH_ROOT", tmp_path / "auth")
    monkeypatch.setattr(m, "_token_path", lambda account: tmp_path / "auth" / account / "google_token.json")

    with patch("builtins.input", return_value="n"):
        rc = m.logout("personal")

    assert rc == 0
    assert token.exists(), "Token must not be deleted when user declines"
    out = capsys.readouterr().out
    assert "Aborted" in out


def test_accept_deletes_token(tmp_path, monkeypatch, capsys):
    m = _reload()
    token = tmp_path / "auth" / "personal" / "google_token.json"
    token.parent.mkdir(parents=True)
    token.write_text("fake-token-data")

    monkeypatch.setattr(m, "_AUTH_ROOT", tmp_path / "auth")
    monkeypatch.setattr(m, "_token_path", lambda account: tmp_path / "auth" / account / "google_token.json")

    with patch("builtins.input", return_value="y"):
        rc = m.logout("personal")

    assert rc == 0
    assert not token.exists(), "Token must be deleted when user confirms"
    out = capsys.readouterr().out
    assert "OK" in out


def test_confirmed_flag_skips_prompt(tmp_path, monkeypatch):
    m = _reload()
    token = tmp_path / "auth" / "work" / "google_token.json"
    token.parent.mkdir(parents=True)
    token.write_text("fake")

    monkeypatch.setattr(m, "_AUTH_ROOT", tmp_path / "auth")
    monkeypatch.setattr(m, "_token_path", lambda account: tmp_path / "auth" / account / "google_token.json")

    with patch("builtins.input") as mock_input:
        rc = m.logout("work", confirmed=True)

    mock_input.assert_not_called()
    assert rc == 0
    assert not token.exists()


def test_yes_full_word_also_accepted(tmp_path, monkeypatch):
    m = _reload()
    token = tmp_path / "auth" / "personal" / "google_token.json"
    token.parent.mkdir(parents=True)
    token.write_text("fake")

    monkeypatch.setattr(m, "_AUTH_ROOT", tmp_path / "auth")
    monkeypatch.setattr(m, "_token_path", lambda account: tmp_path / "auth" / account / "google_token.json")

    with patch("builtins.input", return_value="yes"):
        rc = m.logout("personal")

    assert rc == 0
    assert not token.exists()


# ---------------------------------------------------------------------------
# Missing token is graceful
# ---------------------------------------------------------------------------

def test_missing_token_exits_0(tmp_path, monkeypatch, capsys):
    m = _reload()
    monkeypatch.setattr(m, "_AUTH_ROOT", tmp_path / "auth")
    monkeypatch.setattr(m, "_token_path", lambda account: tmp_path / "auth" / account / "google_token.json")

    rc = m.logout("personal")

    assert rc == 0
    out = capsys.readouterr().out
    assert "MISSING" in out
    assert "nothing to do" in out


# ---------------------------------------------------------------------------
# Path confinement — cannot escape auth dir
# ---------------------------------------------------------------------------

def test_path_traversal_rejected(tmp_path, monkeypatch, capsys):
    m = _reload()
    # Simulate a malicious account value that would resolve outside auth root
    monkeypatch.setattr(m, "_AUTH_ROOT", tmp_path / "auth")
    # _token_path returns a path outside auth root
    monkeypatch.setattr(m, "_token_path", lambda account: tmp_path / "other" / "google_token.json")

    rc = m.logout("../../etc/passwd")

    assert rc == 1
    err = capsys.readouterr().err
    assert "ERROR" in err


def test_only_token_file_deleted_not_directory(tmp_path, monkeypatch):
    m = _reload()
    auth_dir = tmp_path / "auth"
    personal_dir = auth_dir / "personal"
    personal_dir.mkdir(parents=True)
    token = personal_dir / "google_token.json"
    token.write_text("fake")
    other_file = personal_dir / "other.json"
    other_file.write_text("keep-me")

    monkeypatch.setattr(m, "_AUTH_ROOT", auth_dir)
    monkeypatch.setattr(m, "_token_path", lambda account: personal_dir / "google_token.json")

    with patch("builtins.input", return_value="y"):
        m.logout("personal")

    assert not token.exists()
    assert other_file.exists(), "Only the token file must be deleted"
    assert personal_dir.exists(), "Parent directory must not be removed"


# ---------------------------------------------------------------------------
# No secret contents in output
# ---------------------------------------------------------------------------

def test_no_token_contents_in_output(tmp_path, monkeypatch, capsys):
    m = _reload()
    secret = "SUPER_SECRET_REFRESH_TOKEN_VALUE"
    token = tmp_path / "auth" / "personal" / "google_token.json"
    token.parent.mkdir(parents=True)
    token.write_text(secret)

    monkeypatch.setattr(m, "_AUTH_ROOT", tmp_path / "auth")
    monkeypatch.setattr(m, "_token_path", lambda account: tmp_path / "auth" / account / "google_token.json")

    with patch("builtins.input", return_value="y"):
        m.logout("personal")

    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err
