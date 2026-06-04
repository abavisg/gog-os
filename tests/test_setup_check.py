"""Tests for gogos.system.setup_check."""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from unittest.mock import patch


def _reload():
    import gogos.system.setup_check as m
    importlib.reload(m)
    return m


# ---------------------------------------------------------------------------
# Python version check
# ---------------------------------------------------------------------------

def test_python_version_ok(capsys):
    m = _reload()
    with patch.object(sys, "version_info", (3, 11, 0, "final", 0)):
        result = m.check_python_version()
    assert result is True
    assert "OK" in capsys.readouterr().out


def test_python_version_too_old(capsys):
    m = _reload()
    with patch.object(sys, "version_info", (3, 10, 0, "final", 0)):
        result = m.check_python_version()
    assert result is False
    assert "ERROR" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Required dirs
# ---------------------------------------------------------------------------

def test_required_dirs_created(tmp_path, monkeypatch):
    m = _reload()
    fake_dirs = [tmp_path / ".core/storage", tmp_path / ".core/config"]
    monkeypatch.setattr(m, "_REQUIRED_DIRS", fake_dirs)
    monkeypatch.setattr(m, "_REPO_ROOT", tmp_path)
    assert m.check_required_dirs() is True
    for d in fake_dirs:
        assert d.is_dir()


def test_required_dirs_already_exist(tmp_path, monkeypatch):
    m = _reload()
    d = tmp_path / ".core/storage"
    d.mkdir(parents=True)
    monkeypatch.setattr(m, "_REQUIRED_DIRS", [d])
    monkeypatch.setattr(m, "_REPO_ROOT", tmp_path)
    assert m.check_required_dirs() is True


# ---------------------------------------------------------------------------
# .env check
# ---------------------------------------------------------------------------

def test_env_present(tmp_path, monkeypatch, capsys):
    m = _reload()
    monkeypatch.setattr(m, "_REPO_ROOT", tmp_path)
    (tmp_path / ".env").write_text("SECRET=hunter2\n")
    m.check_env_file()
    out = capsys.readouterr().out
    assert "OK" in out
    assert "hunter2" not in out


def test_env_missing(tmp_path, monkeypatch, capsys):
    m = _reload()
    monkeypatch.setattr(m, "_REPO_ROOT", tmp_path)
    m.check_env_file()
    out = capsys.readouterr().out
    assert "MISSING" in out
    assert ".env.example" in out


# ---------------------------------------------------------------------------
# Google credentials check
# ---------------------------------------------------------------------------

def test_google_creds_present(tmp_path, monkeypatch, capsys):
    m = _reload()
    monkeypatch.setattr(m, "_REPO_ROOT", tmp_path)
    creds_file = tmp_path / "creds.json"
    secret_payload = json.dumps({"client_secret": "TOPSECRET123"})
    creds_file.write_text(secret_payload)
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", str(creds_file))
    m.check_google_credentials()
    out = capsys.readouterr().out
    assert "OK" in out
    assert "TOPSECRET123" not in out


def test_google_creds_missing_file(tmp_path, monkeypatch, capsys):
    m = _reload()
    monkeypatch.setattr(m, "_REPO_ROOT", tmp_path)
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", str(tmp_path / "no_such.json"))
    m.check_google_credentials()
    out = capsys.readouterr().out
    assert "MISSING" in out


def test_google_creds_env_var_not_set(tmp_path, monkeypatch, capsys):
    m = _reload()
    monkeypatch.setattr(m, "_REPO_ROOT", tmp_path)
    monkeypatch.delenv("GOOGLE_CREDENTIALS_PATH", raising=False)
    m.check_google_credentials()
    out = capsys.readouterr().out
    assert "MISSING" in out


# ---------------------------------------------------------------------------
# run() integration — exit codes
# ---------------------------------------------------------------------------

def test_run_exits_0_no_creds_no_env(tmp_path, monkeypatch):
    m = _reload()
    monkeypatch.setattr(m, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(m, "_REQUIRED_DIRS", [tmp_path / ".core/storage", tmp_path / ".core/config"])
    monkeypatch.delenv("GOOGLE_CREDENTIALS_PATH", raising=False)
    assert m.run() == 0


def test_run_exits_1_on_bad_python(tmp_path, monkeypatch):
    m = _reload()
    monkeypatch.setattr(m, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(m, "_REQUIRED_DIRS", [tmp_path / ".core/storage", tmp_path / ".core/config"])
    monkeypatch.delenv("GOOGLE_CREDENTIALS_PATH", raising=False)
    with patch.object(sys, "version_info", (3, 10, 0, "final", 0)):
        result = m.run()
    assert result == 1


# ---------------------------------------------------------------------------
# Subprocess: secret bytes must never appear in stdout or stderr
# ---------------------------------------------------------------------------

def test_no_secret_in_output(tmp_path):
    secret = "ULTRA_SECRET_VALUE_XYZ"
    creds_file = tmp_path / "fake_creds.json"
    creds_file.write_text(json.dumps({"client_secret": secret}))

    env_overrides = {
        "GOOGLE_CREDENTIALS_PATH": str(creds_file),
        "GOGOS_TIMEZONE": "Europe/London",
    }
    env = {**os.environ, **env_overrides}

    result = subprocess.run(
        [sys.executable, "-m", "gogos.system.setup_check"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert secret not in result.stdout
    assert secret not in result.stderr
