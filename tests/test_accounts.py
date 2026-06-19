"""Tests for gogos.auth.accounts — config-file-based alias→email resolver."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_config(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "accounts.json"
    p.write_text(json.dumps(data))
    return p


def _patch_config(monkeypatch, tmp_path: Path, data: dict | None = None) -> Path:
    p = tmp_path / "accounts.json"
    if data is not None:
        p.write_text(json.dumps(data))
    import gogos.auth.accounts as m
    monkeypatch.setattr(m, "_config_path", lambda: p)
    return p


# ---------------------------------------------------------------------------
# load_accounts_config
# ---------------------------------------------------------------------------

def test_load_config_missing_file(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    monkeypatch.setattr(m, "_config_path", lambda: tmp_path / "no_such.json")
    cfg = m.load_accounts_config()
    assert cfg["aliases"] == {}
    assert cfg["default"] is None


def test_load_config_valid(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    data = {"version": 1, "default": "a@b.com", "aliases": {"a": "a@b.com"}}
    _patch_config(monkeypatch, tmp_path, data)
    cfg = m.load_accounts_config()
    assert cfg["aliases"]["a"] == "a@b.com"
    assert cfg["default"] == "a@b.com"


def test_load_config_malformed_json(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    p = tmp_path / "accounts.json"
    p.write_text("not { valid json }")
    monkeypatch.setattr(m, "_config_path", lambda: p)
    with pytest.raises(RuntimeError, match="Malformed"):
        m.load_accounts_config()


# ---------------------------------------------------------------------------
# resolve_account
# ---------------------------------------------------------------------------

def _config_with(aliases: dict, default: str | None = None) -> dict:
    return {"version": 1, "default": default, "aliases": aliases}


def test_resolve_alias_returns_email(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({"abavisg": "abavisg@gmail.com"}, "abavisg@gmail.com"))
    assert m.resolve_account("abavisg") == "abavisg@gmail.com"


def test_resolve_raw_email_registered(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({"abavisg": "abavisg@gmail.com"}, "abavisg@gmail.com"))
    assert m.resolve_account("abavisg@gmail.com") == "abavisg@gmail.com"


def test_resolve_raw_email_unregistered_raises_when_accounts_exist(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({"abavisg": "abavisg@gmail.com"}, "abavisg@gmail.com"))
    with pytest.raises(ValueError, match="not registered"):
        m.resolve_account("other@example.com")


def test_resolve_unknown_alias_raises(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({"abavisg": "abavisg@gmail.com"}, "abavisg@gmail.com"))
    with pytest.raises(ValueError, match="Unknown account"):
        m.resolve_account("nobody")


def test_resolve_first_run_bootstrap(monkeypatch, tmp_path):
    """When aliases map is empty, raw email passes through (first-run bootstrap)."""
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({}))
    assert m.resolve_account("brand_new@example.com") == "brand_new@example.com"


def test_resolve_unknown_alias_hints_known_aliases(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({"abavisg": "abavisg@gmail.com"}, "abavisg@gmail.com"))
    with pytest.raises(ValueError, match="abavisg"):
        m.resolve_account("typo")


# ---------------------------------------------------------------------------
# validate_account
# ---------------------------------------------------------------------------

def test_validate_account_passes_on_known(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({"a": "a@b.com"}, "a@b.com"))
    m.validate_account("a")  # must not raise


def test_validate_account_raises_on_unknown(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({"a": "a@b.com"}, "a@b.com"))
    with pytest.raises(ValueError):
        m.validate_account("bogus")


# ---------------------------------------------------------------------------
# known_accounts
# ---------------------------------------------------------------------------

def test_known_accounts_from_config(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with(
        {"abavisg": "abavisg@gmail.com", "karehero": "g@karehero.com"},
        "abavisg@gmail.com",
    ))
    accounts = m.known_accounts()
    assert "abavisg@gmail.com" in accounts
    assert "g@karehero.com" in accounts


def test_known_accounts_deduplicates(monkeypatch, tmp_path):
    """Two aliases pointing to the same email → appears once."""
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with(
        {"alias1": "a@b.com", "alias2": "a@b.com"},
        "a@b.com",
    ))
    assert m.known_accounts().count("a@b.com") == 1


def test_known_accounts_env_fallback(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    monkeypatch.setattr(m, "_config_path", lambda: tmp_path / "no_such.json")
    monkeypatch.setenv("GOGOS_ACCOUNTS", "personal,work")
    accounts = m.known_accounts()
    assert "personal" in accounts
    assert "work" in accounts


# ---------------------------------------------------------------------------
# default_account
# ---------------------------------------------------------------------------

def test_default_account_from_config(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({"a": "a@b.com"}, "a@b.com"))
    assert m.default_account() == "a@b.com"


def test_default_account_env_fallback(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    monkeypatch.setattr(m, "_config_path", lambda: tmp_path / "no_such.json")
    monkeypatch.setenv("GOGOS_DEFAULT_ACCOUNT", "me@example.com")
    monkeypatch.delenv("GOGOS_ACCOUNTS", raising=False)
    assert m.default_account() == "me@example.com"


def test_default_account_first_known_fallback(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({"a": "a@b.com"}, None))
    monkeypatch.delenv("GOGOS_DEFAULT_ACCOUNT", raising=False)
    assert m.default_account() == "a@b.com"


# ---------------------------------------------------------------------------
# add_account
# ---------------------------------------------------------------------------

def test_add_account_new(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({}))
    m.add_account("abavisg", "abavisg@gmail.com")
    cfg = m.load_accounts_config()
    assert cfg["aliases"]["abavisg"] == "abavisg@gmail.com"


def test_add_account_sets_default_when_first(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({}))
    m.add_account("abavisg", "abavisg@gmail.com")
    cfg = m.load_accounts_config()
    assert cfg["default"] == "abavisg@gmail.com"


def test_add_account_does_not_overwrite_default(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({"a": "a@b.com"}, "a@b.com"))
    m.add_account("b", "b@b.com")
    cfg = m.load_accounts_config()
    assert cfg["default"] == "a@b.com"


def test_add_account_duplicate_alias_raises(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({"a": "a@b.com"}, "a@b.com"))
    with pytest.raises(ValueError, match="already registered"):
        m.add_account("a", "other@b.com")


def test_add_account_invalid_alias_raises(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({}))
    with pytest.raises(ValueError, match="Invalid alias"):
        m.add_account("bad@alias", "a@b.com")


def test_add_account_invalid_email_raises(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({}))
    with pytest.raises(ValueError, match="Invalid email"):
        m.add_account("good", "notanemail")


def test_add_account_atomic_write(monkeypatch, tmp_path):
    """Confirms Path.replace() is used (atomic swap via .tmp file)."""
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({}))
    replaced: list[Path] = []
    orig_replace = Path.replace

    def tracking_replace(self: Path, target: Path) -> None:  # type: ignore[override]
        replaced.append(self)
        return orig_replace(self, target)

    monkeypatch.setattr(Path, "replace", tracking_replace)
    m.add_account("a", "a@b.com")
    assert any(".tmp" in str(p) for p in replaced)


# ---------------------------------------------------------------------------
# remove_account
# ---------------------------------------------------------------------------

def test_remove_account_by_alias(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({"a": "a@b.com"}, "a@b.com"))
    m.remove_account("a")
    cfg = m.load_accounts_config()
    assert "a" not in cfg["aliases"]


def test_remove_account_by_email_removes_all_aliases(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with(
        {"alias1": "a@b.com", "alias2": "a@b.com"},
        "a@b.com",
    ))
    m.remove_account("a@b.com")
    cfg = m.load_accounts_config()
    assert cfg["aliases"] == {}


def test_remove_account_clears_default(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({"a": "a@b.com"}, "a@b.com"))
    m.remove_account("a")
    cfg = m.load_accounts_config()
    assert cfg["default"] is None


def test_remove_account_updates_default_to_next(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with(
        {"a": "a@b.com", "b": "b@b.com"},
        "a@b.com",
    ))
    m.remove_account("a")
    cfg = m.load_accounts_config()
    assert cfg["default"] == "b@b.com"


def test_remove_account_nonexistent_raises(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({"a": "a@b.com"}, "a@b.com"))
    with pytest.raises(ValueError, match="not registered"):
        m.remove_account("nobody")


# ---------------------------------------------------------------------------
# rename_alias
# ---------------------------------------------------------------------------

def test_rename_alias_valid(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({"old": "a@b.com"}, "a@b.com"))
    m.rename_alias("old", "new")
    cfg = m.load_accounts_config()
    assert "old" not in cfg["aliases"]
    assert cfg["aliases"]["new"] == "a@b.com"


def test_rename_alias_collision_raises(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with(
        {"a": "a@b.com", "b": "b@b.com"},
        "a@b.com",
    ))
    with pytest.raises(ValueError, match="already in use"):
        m.rename_alias("a", "b")


def test_rename_alias_nonexistent_raises(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with({"a": "a@b.com"}, "a@b.com"))
    with pytest.raises(ValueError, match="not registered"):
        m.rename_alias("nobody", "new")


# ---------------------------------------------------------------------------
# list_accounts
# ---------------------------------------------------------------------------

def test_list_accounts_marks_default(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with(
        {"abavisg": "abavisg@gmail.com", "karehero": "g@karehero.com"},
        "abavisg@gmail.com",
    ))
    entries = m.list_accounts()
    defaults = [e for e in entries if e["default"]]
    assert len(defaults) == 1
    assert defaults[0]["email"] == "abavisg@gmail.com"


def test_list_accounts_sorted_by_alias(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    _patch_config(monkeypatch, tmp_path, _config_with(
        {"z": "z@b.com", "a": "a@b.com"},
        "a@b.com",
    ))
    aliases = [e["alias"] for e in m.list_accounts()]
    assert aliases == sorted(aliases)


def test_list_accounts_empty(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    monkeypatch.setattr(m, "_config_path", lambda: tmp_path / "no_such.json")
    monkeypatch.delenv("GOGOS_ACCOUNTS", raising=False)
    assert m.list_accounts() == []
