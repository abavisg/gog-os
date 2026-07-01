"""Tests for gogos.gmail.gmail_ledger — storage roundtrip, fingerprint, drift log."""
from __future__ import annotations

import json

import pytest

from gogos.gmail import gmail_ledger


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolate the ledger under tmp storage with tmp config files."""
    rules = tmp_path / "rules.json"
    classify_cfg = tmp_path / "classify.json"
    rules.write_text('{"rules": []}')
    classify_cfg.write_text("{}")
    monkeypatch.setattr(gmail_ledger, "RULES_PATH", rules)
    monkeypatch.setattr(gmail_ledger, "_CLASSIFY_CONFIG_PATH", classify_cfg)
    monkeypatch.setattr(gmail_ledger, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(gmail_ledger, "resolve_account", lambda a: a)
    return tmp_path


def test_missing_ledger_starts_fresh(env):
    ledger = gmail_ledger.load_ledger("me@x.com")
    assert ledger["senders"] == {}
    assert not gmail_ledger.needs_relearn(ledger)


def test_corrupt_ledger_starts_fresh_with_warning(env, capsys):
    path = gmail_ledger.ledger_path("me@x.com")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken")
    ledger = gmail_ledger.load_ledger("me@x.com")
    assert ledger["senders"] == {}
    assert "WARN" in capsys.readouterr().err


def test_save_load_roundtrip(env):
    ledger = gmail_ledger.empty_ledger()
    gmail_ledger.record(ledger, "tldrnewsletter.com", "Newsletters", "builtin")
    path = gmail_ledger.save_ledger("me@x.com", ledger)
    assert path == gmail_ledger.ledger_path("me@x.com")
    assert path.name == "sender-ledger.json"

    loaded = gmail_ledger.load_ledger("me@x.com")
    assert gmail_ledger.lookup(loaded, "tldrnewsletter.com") == "Newsletters"
    assert loaded["senders"]["tldrnewsletter.com"]["source"] == "builtin"
    assert not gmail_ledger.needs_relearn(loaded)


def test_config_change_triggers_relearn(env):
    ledger = gmail_ledger.empty_ledger()
    gmail_ledger.save_ledger("me@x.com", ledger)

    gmail_ledger.RULES_PATH.write_text(
        json.dumps({"rules": [{"match": {"domain": "x.com"}, "category": "Review"}]}))
    loaded = gmail_ledger.load_ledger("me@x.com")
    assert gmail_ledger.needs_relearn(loaded)

    # Saving again refreshes the fingerprint — re-learn is a one-run event.
    gmail_ledger.save_ledger("me@x.com", loaded)
    assert not gmail_ledger.needs_relearn(gmail_ledger.load_ledger("me@x.com"))


def test_record_same_category_is_silent(env, capsys):
    ledger = gmail_ledger.empty_ledger()
    gmail_ledger.record(ledger, "a.com", "Newsletters", "builtin")
    gmail_ledger.record(ledger, "a.com", "Newsletters", "builtin")
    assert capsys.readouterr().err == ""


def test_record_changed_category_is_logged_never_silent(env, capsys):
    ledger = gmail_ledger.empty_ledger()
    gmail_ledger.record(ledger, "a.com", "Newsletters", "builtin")
    gmail_ledger.record(ledger, "a.com", "Review", "user-rule")
    err = capsys.readouterr().err
    assert "re-learned" in err and "Newsletters" in err and "Review" in err
    assert gmail_ledger.lookup(ledger, "a.com") == "Review"
    assert ledger["senders"]["a.com"]["source"] == "user-rule"


def test_empty_sender_is_never_recorded(env):
    ledger = gmail_ledger.empty_ledger()
    gmail_ledger.record(ledger, "", "Newsletters", "builtin")
    assert ledger["senders"] == {}
