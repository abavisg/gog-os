"""Shared fixtures. Every test runs against a synthetic life/ and me/ in tmp_path.

_isolate_memory is autouse: LIFE_ROOT and ME_ROOT are monkeypatched for every
test, so no test can read or write the real tree even by accident. Tests that
need the skeleton on disk ask for `life`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gogos.core import paths

AREAS = ("wellness", "finance", "growth", "family", "home", "work")
KINDS = ("goal", "commitment", "waiting", "renewal", "occasion", "decision", "parked")


@pytest.fixture(autouse=True)
def _isolate_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LIFE_ROOT", tmp_path / "life")
    monkeypatch.setattr(paths, "ME_ROOT", tmp_path / "me")


@pytest.fixture
def life(tmp_path) -> Path:
    """A synthetic life/ skeleton plus me/areas.json; returns the life/ root."""
    root = paths.LIFE_ROOT
    for area in (*AREAS, "people"):
        (root / "wiki" / area).mkdir(parents=True)
    for kind in KINDS:
        (root / "registers" / kind).mkdir(parents=True)
    for d in ("inbox", "journal", "workspaces", "reports"):
        (root / d).mkdir(parents=True)
    paths.ME_ROOT.mkdir(parents=True)
    (paths.ME_ROOT / "areas.json").write_text(json.dumps([
        {"id": a, "title": a.title(), "priority": i + 1, "weekly_question": "?"}
        for i, a in enumerate(AREAS)
    ]))
    return root


@pytest.fixture
def clock(monkeypatch):
    """Pin the clock: set(now_iso) fixes now_utc() and today() for core modules."""
    from datetime import datetime

    def set_(now: str, local_date: str | None = None) -> None:
        dt = datetime.fromisoformat(now.replace("Z", "+00:00"))
        monkeypatch.setattr(paths, "now_utc", lambda: dt)
        monkeypatch.setattr(paths, "today", lambda: local_date or dt.strftime("%Y-%m-%d"))

    return set_
