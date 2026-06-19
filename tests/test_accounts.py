"""Tests for gogos.auth.accounts."""
from __future__ import annotations

import pytest


def test_known_accounts_default(monkeypatch):
    from gogos.auth import accounts
    monkeypatch.delenv("GOGOS_ACCOUNTS", raising=False)
    assert accounts.known_accounts() == ["personal", "work"]


def test_known_accounts_from_env(monkeypatch):
    from gogos.auth import accounts
    monkeypatch.setenv("GOGOS_ACCOUNTS", "personal,work,family")
    assert accounts.known_accounts() == ["personal", "work", "family"]


def test_known_accounts_strips_whitespace(monkeypatch):
    from gogos.auth import accounts
    monkeypatch.setenv("GOGOS_ACCOUNTS", " personal , work ")
    assert accounts.known_accounts() == ["personal", "work"]


def test_default_account_from_env(monkeypatch):
    from gogos.auth import accounts
    monkeypatch.setenv("GOGOS_DEFAULT_ACCOUNT", "work")
    assert accounts.default_account() == "work"


def test_default_account_fallback(monkeypatch):
    from gogos.auth import accounts
    monkeypatch.delenv("GOGOS_DEFAULT_ACCOUNT", raising=False)
    assert accounts.default_account() == "personal"


def test_validate_account_valid(monkeypatch):
    from gogos.auth import accounts
    monkeypatch.setenv("GOGOS_ACCOUNTS", "personal,work")
    accounts.validate_account("personal")  # must not raise
    accounts.validate_account("work")      # must not raise


def test_validate_account_invalid(monkeypatch):
    from gogos.auth import accounts
    monkeypatch.setenv("GOGOS_ACCOUNTS", "personal,work")
    with pytest.raises(ValueError, match="Unknown account 'family'"):
        accounts.validate_account("family")


def test_validate_account_error_lists_valid_accounts(monkeypatch):
    from gogos.auth import accounts
    monkeypatch.setenv("GOGOS_ACCOUNTS", "personal,work")
    with pytest.raises(ValueError, match="personal"):
        accounts.validate_account("bogus")
