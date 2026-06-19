"""Tests for gogos.auth.account_mgmt CLI subcommands."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run(args: list[str], config_path: Path) -> subprocess.CompletedProcess:
    env = {"GOGOS_ACCOUNT_CONFIG": str(config_path)}
    import os
    full_env = {**os.environ, **env}
    return subprocess.run(
        [sys.executable, "-m", "gogos.auth.account_mgmt"] + args,
        capture_output=True,
        text=True,
        env=full_env,
    )


def _patch_and_run(monkeypatch, tmp_path: Path, initial: dict, args: list[str]):
    """Monkeypatch _config_path and run CLI subcommand in-process."""
    import gogos.auth.accounts as accts
    import gogos.auth.account_mgmt as mgmt
    import importlib

    cfg_file = tmp_path / "accounts.json"
    if initial is not None:
        cfg_file.write_text(json.dumps(initial))

    monkeypatch.setattr(accts, "_config_path", lambda: cfg_file)

    # Re-import to pick up monkeypatch
    importlib.reload(accts)
    monkeypatch.setattr(accts, "_config_path", lambda: cfg_file)

    cmd = args[0]
    rest = args[1:]
    fn = mgmt._COMMANDS.get(cmd)
    assert fn is not None, f"Unknown subcommand: {cmd}"
    return fn(rest), cfg_file


def _empty_config() -> dict:
    return {"version": 1, "default": None, "aliases": {}}


def _config_with(aliases: dict, default: str | None = None) -> dict:
    return {"version": 1, "default": default, "aliases": aliases}


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------

def test_cmd_add_success(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    cfg_file = tmp_path / "accounts.json"
    cfg_file.write_text(json.dumps(_empty_config()))
    monkeypatch.setattr(m, "_config_path", lambda: cfg_file)

    from gogos.auth.account_mgmt import cmd_add
    rc = cmd_add(["abavisg", "abavisg@gmail.com"])
    assert rc == 0
    data = json.loads(cfg_file.read_text())
    assert data["aliases"]["abavisg"] == "abavisg@gmail.com"


def test_cmd_add_duplicate_alias_exits_nonzero(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    cfg_file = tmp_path / "accounts.json"
    cfg_file.write_text(json.dumps(_config_with({"abavisg": "abavisg@gmail.com"}, "abavisg@gmail.com")))
    monkeypatch.setattr(m, "_config_path", lambda: cfg_file)

    from gogos.auth.account_mgmt import cmd_add
    rc = cmd_add(["abavisg", "other@gmail.com"])
    assert rc == 1


def test_cmd_add_wrong_arg_count(monkeypatch, tmp_path):
    from gogos.auth.account_mgmt import cmd_add
    assert cmd_add(["only_one"]) == 1


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------

def test_cmd_remove_success(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    cfg_file = tmp_path / "accounts.json"
    cfg_file.write_text(json.dumps(_config_with({"abavisg": "abavisg@gmail.com"}, "abavisg@gmail.com")))
    monkeypatch.setattr(m, "_config_path", lambda: cfg_file)

    from gogos.auth.account_mgmt import cmd_remove
    rc = cmd_remove(["abavisg"])
    assert rc == 0
    data = json.loads(cfg_file.read_text())
    assert "abavisg" not in data["aliases"]


def test_cmd_remove_nonexistent_exits_nonzero(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    cfg_file = tmp_path / "accounts.json"
    cfg_file.write_text(json.dumps(_empty_config()))
    monkeypatch.setattr(m, "_config_path", lambda: cfg_file)

    from gogos.auth.account_mgmt import cmd_remove
    assert cmd_remove(["nobody"]) == 1


# ---------------------------------------------------------------------------
# alias (rename)
# ---------------------------------------------------------------------------

def test_cmd_alias_success(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    cfg_file = tmp_path / "accounts.json"
    cfg_file.write_text(json.dumps(_config_with({"old": "a@b.com"}, "a@b.com")))
    monkeypatch.setattr(m, "_config_path", lambda: cfg_file)

    from gogos.auth.account_mgmt import cmd_alias
    rc = cmd_alias(["old", "new"])
    assert rc == 0
    data = json.loads(cfg_file.read_text())
    assert data["aliases"].get("new") == "a@b.com"
    assert "old" not in data["aliases"]


def test_cmd_alias_collision_exits_nonzero(monkeypatch, tmp_path):
    import gogos.auth.accounts as m
    cfg_file = tmp_path / "accounts.json"
    cfg_file.write_text(json.dumps(_config_with({"a": "a@b.com", "b": "b@b.com"}, "a@b.com")))
    monkeypatch.setattr(m, "_config_path", lambda: cfg_file)

    from gogos.auth.account_mgmt import cmd_alias
    assert cmd_alias(["a", "b"]) == 1


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def test_cmd_list_empty(monkeypatch, tmp_path, capsys):
    import gogos.auth.accounts as m
    monkeypatch.setattr(m, "_config_path", lambda: tmp_path / "no_such.json")
    monkeypatch.delenv("GOGOS_ACCOUNTS", raising=False)

    from gogos.auth.account_mgmt import cmd_list
    rc = cmd_list([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "No accounts" in out


def test_cmd_list_shows_entries(monkeypatch, tmp_path, capsys):
    import gogos.auth.accounts as m
    cfg_file = tmp_path / "accounts.json"
    cfg_file.write_text(json.dumps(_config_with(
        {"abavisg": "abavisg@gmail.com"},
        "abavisg@gmail.com",
    )))
    monkeypatch.setattr(m, "_config_path", lambda: cfg_file)

    from gogos.auth.account_mgmt import cmd_list
    rc = cmd_list([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "abavisg" in out
    assert "abavisg@gmail.com" in out
    assert "*" in out  # default marker
