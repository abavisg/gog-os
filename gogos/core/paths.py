"""Paths for the v2 memory tree (life/ and me/) plus the shared clock.

life/ holds the memory: inbox digests (gitignored), the wiki, registers, the
journal, workspaces and reports. me/ holds the owner's profile, areas and
themes. Both are resolved through LIFE_ROOT and ME_ROOT, read at call time so
tests can monkeypatch them onto a synthetic tree in tmp_path.

The clock and .core/storage helpers (today, now_utc, storage_path) live in
gogos.paths and are re-exported here, so v2 modules import one paths module.
Path helpers never create directories; writers create parents.

Library module; no CLI.
"""
from __future__ import annotations

from pathlib import Path

from gogos.paths import (  # noqa: F401 (re-exported)
    REPO_ROOT,
    STORAGE_ROOT,
    latest_alias,
    local_tz,
    now_utc,
    storage_path,
    today,
)

LIFE_ROOT: Path = REPO_ROOT / "life"
ME_ROOT: Path = REPO_ROOT / "me"


def inbox_dir() -> Path:
    """life/inbox/: connector digests and drops. Gitignored."""
    return LIFE_ROOT / "inbox"


def wiki_dir(area: str) -> Path:
    """life/wiki/<area>/, or life/wiki/people/ for people pages."""
    return LIFE_ROOT / "wiki" / area


def registers_dir(kind: str | None = None) -> Path:
    """life/registers/<kind>/, or life/registers/ when kind is None."""
    root = LIFE_ROOT / "registers"
    return root / kind if kind else root


def journal_file(date: str | None = None) -> Path:
    """life/journal/YYYY-MM-DD.jsonl; date defaults to today()."""
    return LIFE_ROOT / "journal" / f"{date or today()}.jsonl"


def workspace_dir(slug: str) -> Path:
    """life/workspaces/<slug>/."""
    return LIFE_ROOT / "workspaces" / slug


def reports_dir(kind: str, date: str | None = None) -> Path:
    """life/reports/<kind>/<YYYY-MM-DD>/; date defaults to today()."""
    return LIFE_ROOT / "reports" / kind / (date or today())


def rel_ref(path: Path) -> str:
    """A life/ path as the repo-relative ref stored in journal events and tasks.

    Built against LIFE_ROOT rather than REPO_ROOT, so a synthetic tree in a
    test yields the same "life/..." refs as the real one.
    """
    return "life/" + Path(path).resolve().relative_to(LIFE_ROOT.resolve()).as_posix()


def resolve_ref(ref: str) -> Path:
    """Inverse of rel_ref: "life/..." maps under LIFE_ROOT; other paths are taken as given."""
    if ref.startswith("life/"):
        return LIFE_ROOT / ref.removeprefix("life/")
    return Path(ref)
