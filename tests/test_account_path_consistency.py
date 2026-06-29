"""Regression tests: every gmail/calendar module must key storage off the
CANONICAL email, not the raw alias passed on the CLI.

This guards the bug where gmail_fetch resolved the alias but normalise/triage/
apply did not, so they wrote to diverging directories (gmail/alias/... vs
gmail/email/...). All storage must land under the resolved email.
"""
from __future__ import annotations

import json

import pytest

ALIAS = "myalias"
EMAIL = "real@example.com"


@pytest.fixture
def resolving(tmp_path, monkeypatch):
    """Point every module's resolve_account at a temp registry: ALIAS -> EMAIL,
    and STORAGE_ROOT at a temp dir. Returns the storage root.
    """
    cfg = tmp_path / "accounts.json"
    cfg.write_text(json.dumps({
        "version": 1, "default": EMAIL, "aliases": {ALIAS: EMAIL},
    }))
    import gogos.auth.accounts as accounts
    monkeypatch.setattr(accounts, "_config_path", lambda: cfg)

    storage_root = tmp_path / ".core/storage"
    monkeypatch.setattr("gogos.paths.STORAGE_ROOT", storage_root)
    return storage_root


def _emails_under(storage_root, module):
    """Return the set of account-directory names that exist under a module dir."""
    base = storage_root / module
    return {p.name for p in base.iterdir()} if base.exists() else set()


def test_normalise_writes_under_resolved_email(resolving, tmp_path):
    from gogos.gmail import gmail_normalise
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps({
        "account": EMAIL, "messages": [
            {"id": "m1", "headers": [{"name": "Subject", "value": "Hi"}],
             "snippet": "s", "labelIds": ["INBOX"]},
        ],
    }))

    rc = gmail_normalise.normalise(ALIAS, raw)
    assert rc == 0
    # Must write under the EMAIL, never under the raw ALIAS.
    accounts = _emails_under(resolving, "gmail")
    assert EMAIL in accounts
    assert ALIAS not in accounts


def test_triage_writes_under_resolved_email(resolving):
    from gogos.gmail import gmail_triage
    triage = {
        "generated_at": "2026-06-29T00:00:00+00:00",
        "account": EMAIL,
        "items": [{"id": "m1", "category": "Review", "confidence": 0.5,
                   "rationale": "r", "suggested_action": "a"}],
    }
    rc = gmail_triage.write_triage(ALIAS, triage)
    assert rc == 0
    accounts = _emails_under(resolving, "gmail")
    assert EMAIL in accounts
    assert ALIAS not in accounts


def test_apply_plan_written_under_resolved_email(resolving):
    from gogos.gmail import gmail_apply
    triage = {"account": EMAIL, "items": [
        {"id": "m1", "category": "Review", "confidence": 0.5,
         "rationale": "r", "suggested_action": "a"}]}
    slim = {"messages": [{"id": "m1", "subject": "Hi", "from": "x@y.com",
                          "date": "2026-06-29T08:00:00+00:00"}]}

    gmail_apply.build_plan(ALIAS, triage=triage, slim=slim)

    # The approvals proposal must live under the resolved email.
    approvals = resolving / "approvals"
    accounts = {p.name for p in approvals.iterdir()} if approvals.exists() else set()
    assert EMAIL in accounts
    assert ALIAS not in accounts


def test_normalise_and_triage_agree_on_directory(resolving, tmp_path):
    """fetch->normalise->triage chain must converge on ONE account directory."""
    from gogos.gmail import gmail_normalise, gmail_triage
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps({"account": EMAIL, "messages": [
        {"id": "m1", "headers": [{"name": "Subject", "value": "Hi"}],
         "snippet": "s", "labelIds": ["INBOX"]}]}))
    gmail_normalise.normalise(ALIAS, raw)
    gmail_triage.write_triage(ALIAS, {
        "generated_at": "2026-06-29T00:00:00+00:00", "account": EMAIL,
        "items": [{"id": "m1", "category": "Review", "confidence": 0.5,
                   "rationale": "r", "suggested_action": "a"}]})

    # Exactly one account dir under gmail/, and it is the email.
    accounts = _emails_under(resolving, "gmail")
    assert accounts == {EMAIL}
