"""Tests for gogos.core.paths: the life/ and me/ helpers and the gitignore boundary."""
from __future__ import annotations

import shutil
import subprocess

import pytest

from gogos.core import paths


def test_roots_are_monkeypatched_onto_tmp(tmp_path):
    assert paths.LIFE_ROOT == tmp_path / "life"
    assert paths.ME_ROOT == tmp_path / "me"


def test_helpers_resolve_under_life_root(life, clock):
    clock("2026-10-23T08:14:02Z")
    assert paths.inbox_dir() == life / "inbox"
    assert paths.wiki_dir("home") == life / "wiki" / "home"
    assert paths.wiki_dir("people") == life / "wiki" / "people"
    assert paths.registers_dir() == life / "registers"
    assert paths.registers_dir("waiting") == life / "registers" / "waiting"
    assert paths.journal_file() == life / "journal" / "2026-10-23.jsonl"
    assert paths.journal_file("2026-01-02") == life / "journal" / "2026-01-02.jsonl"
    assert paths.workspace_dir("car-lease") == life / "workspaces" / "car-lease"
    assert paths.reports_dir("start-day") == life / "reports" / "start-day" / "2026-10-23"
    assert paths.reports_dir("weekly", "2026-10-19") == life / "reports" / "weekly" / "2026-10-19"


def test_helpers_do_not_create_directories(tmp_path):
    paths.registers_dir("goal")
    paths.journal_file("2026-10-23")
    assert not (tmp_path / "life").exists()


def test_ref_round_trip(life):
    item = paths.registers_dir("waiting") / "invoice-from-acme.md"
    ref = paths.rel_ref(item)
    assert ref == "life/registers/waiting/invoice-from-acme.md"
    assert paths.resolve_ref(ref) == item


def test_storage_helpers_re_exported():
    # Other suites reload gogos.paths, so compare by origin rather than identity.
    assert paths.today.__module__ == "gogos.paths"
    assert paths.storage_path.__module__ == "gogos.paths"


def _check_ignore(rel: str) -> int:
    return subprocess.run(
        ["git", "check-ignore", "-q", rel], cwd=paths.REPO_ROOT,
        capture_output=True,
    ).returncode


@pytest.mark.skipif(shutil.which("git") is None
                    or not (paths.REPO_ROOT / ".git").exists(),
                    reason="needs the git checkout")
def test_gitignore_boundary():
    # Reads only the repo's .gitignore rules; no file is created or opened.
    assert _check_ignore("life/inbox/x") == 0
    assert _check_ignore(".core/x") == 0
    assert _check_ignore("life/wiki/x") == 1
    assert _check_ignore("life/registers/goal/x.md") == 1
    assert _check_ignore("me/profile.md") == 1
