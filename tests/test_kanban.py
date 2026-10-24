"""gogos.core.kanban: sync() and reconcile() against the real Claude Code task format."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from gogos.core import journal, kanban, paths, registers

FIXTURE = Path(__file__).parent / "fixtures" / "kanban"


def _tasks(d: Path) -> dict[str, dict]:
    return {p.name: json.loads(p.read_text()) for p in sorted(d.glob("*.json"))}


# --- the fixture pins the real format -------------------------------------------

def test_fixture_carries_every_required_key():
    """Fails loudly if a re-captured Claude Code task file drops a key we rely on."""
    files = sorted(FIXTURE.glob("*.json"))
    assert files, "tests/fixtures/kanban/ has no task files"
    for path in files:
        task = json.loads(path.read_text())
        missing = [k for k in kanban.REQUIRED_KEYS if k not in task]
        assert not missing, f"{path.name} lacks {missing}: Claude Code task format changed"
        assert task["status"] in kanban.TASK_STATUSES
        assert path.stem == task["id"]
    assert (FIXTURE / ".lock").exists()
    refs = [json.loads(p.read_text()).get("metadata", {}).get("gogos_ref") for p in files]
    assert any(r and r.startswith("life/registers/commitment/") for r in refs)


def test_task_dir_follows_env(monkeypatch, tmp_path):
    assert kanban.task_dir() == tmp_path / "claude" / "tasks" / "gogos"
    monkeypatch.setenv("CLAUDE_CODE_TASK_LIST_ID", "other")
    assert kanban.task_dir().name == "other"


def test_settings_pin_the_shared_list_id():
    settings = json.loads((paths.REPO_ROOT / ".claude" / "settings.json").read_text())
    assert settings["env"]["CLAUDE_CODE_TASK_LIST_ID"] == "gogos"


# --- reconcile --------------------------------------------------------------------

def _fixture_board() -> Path:
    d = kanban.task_dir()
    shutil.copytree(FIXTURE, d, ignore=shutil.ignore_patterns("README.md"))
    return d


def test_reconcile_on_the_real_format(life, clock):
    clock("2026-10-23T08:00:00Z")
    probe = registers.create("commitment", "Probe", "work", due="2026-10-24")
    d = _fixture_board()

    out = kanban.reconcile()
    # Task 1 is completed but has no gogos_ref: a candidate, never imported.
    assert out["inbox_candidates"] == [{"id": "1", "subject": "Probe task one",
                                        "description": "first probe", "status": "completed"}]
    # Task 2 points at the commitment but is still pending.
    assert out["kept"] == []
    assert registers.load_item(probe).is_open

    task = json.loads((d / "2.json").read_text())
    task["status"] = "completed"
    (d / "2.json").write_text(json.dumps(task, indent=2))
    clock("2026-10-23T09:30:00Z")
    out = kanban.reconcile()
    assert out["kept"] == ["life/registers/commitment/probe.md"]
    item = registers.load_item(probe)
    assert item.status == "kept"
    assert item.history[-1] == ("2026-10-23T09:30:00Z", "status open → kept (kanban)")

    assert kanban.reconcile()["kept"] == []  # already kept: idempotent


def test_reconcile_fails_loudly_on_a_missing_key(life):
    d = _fixture_board()
    task = json.loads((d / "2.json").read_text())
    del task["status"]
    (d / "2.json").write_text(json.dumps(task))
    with pytest.raises(kanban.KanbanFormatError, match="2.json.*status"):
        kanban.reconcile()


def test_reconcile_ignores_refs_outside_commitments(life, clock, capsys):
    clock("2026-10-23T08:00:00Z")
    waiting = registers.create("waiting", "Parcel from shop", "home", owed_by="Shop")
    d = kanban.task_dir()
    d.mkdir(parents=True)
    for i, ref in enumerate([paths.rel_ref(waiting), "life/registers/commitment/../goal/x.md",
                             "life/registers/commitment/missing.md"], 1):
        (d / f"{i}.json").write_text(json.dumps({
            "id": str(i), "subject": "x", "description": "", "status": "completed",
            "blocks": [], "blockedBy": [], "metadata": {"gogos_ref": ref}}))
    assert kanban.reconcile() == {"kept": [], "inbox_candidates": []}
    assert registers.load_item(waiting).is_open
    assert capsys.readouterr().err.count("skipped") == 3


def test_reconcile_with_no_board_is_empty(life):
    assert kanban.reconcile() == {"kept": [], "inbox_candidates": []}


# --- sync -----------------------------------------------------------------------------

def _commitments(clock):
    clock("2026-10-20T08:00:00Z")
    a = registers.create("commitment", "Book boiler service", "home", due="2026-10-28")
    b = registers.create("commitment", "Return library books", "growth",
                         due="2026-10-22T17:00")
    c = registers.create("commitment", "Old promise", "work", due="2026-10-21")
    registers.set_status(c, "dropped")
    return a, b, c


def test_sync_projects_open_commitments(life, clock):
    a, b, _ = _commitments(clock)
    out = kanban.sync()
    assert (out["created"], out["updated"], out["removed"]) == (2, 0, 0)

    d = kanban.task_dir()
    assert (d / ".lock").exists()
    tasks = _tasks(d)
    assert list(tasks) == ["1.json", "2.json"]  # ordered by due
    t1, t2 = tasks["1.json"], tasks["2.json"]
    for t in (t1, t2):
        assert all(k in t for k in kanban.REQUIRED_KEYS)
        assert t["status"] == "pending"
    assert t1["subject"] == "Return library books"
    assert t1["metadata"] == {"gogos_ref": paths.rel_ref(b), "due": "2026-10-22T17:00",
                              "area": "growth"}
    assert t2["metadata"]["gogos_ref"] == paths.rel_ref(a)
    assert "sync.run" in [e["type"] for e in journal.read()]


def test_deleting_the_board_then_sync_reproduces_it(life, clock):
    """Acceptance: sync, delete the task dir, sync again: the same board."""
    _commitments(clock)
    kanban.sync()
    d = kanban.task_dir()
    before = _tasks(d)
    shutil.rmtree(d)
    kanban.sync()
    assert _tasks(d) == before


def test_sync_is_idempotent(life, clock):
    _commitments(clock)
    kanban.sync()
    assert kanban.sync() == {"dir": str(kanban.task_dir()), "created": 0,
                             "updated": 0, "removed": 0}


def test_sync_keeps_foreign_tasks_and_kanban_completions(life, clock):
    a, _, _ = _commitments(clock)
    d = _fixture_board()  # ids 1 and 2 already taken; task 2's ref is not a commitment here
    kanban.sync()
    tasks = _tasks(d)
    assert tasks["1.json"]["subject"] == "Probe task one"  # no gogos_ref: left alone
    assert "2.json" not in tasks  # its commitment does not exist: dropped from the board
    assert {t["metadata"]["gogos_ref"] for n, t in tasks.items() if n != "1.json"} == {
        "life/registers/commitment/return-library-books.md", paths.rel_ref(a)}
    assert set(tasks) == {"1.json", "3.json", "4.json"}  # new ids never reuse taken ones

    # Completed on the board, still open in the register: sync must not undo it.
    ref_a = paths.rel_ref(a)
    name = next(n for n, t in tasks.items() if t.get("metadata", {}).get("gogos_ref") == ref_a)
    t = tasks[name]
    t["status"] = "completed"
    (d / name).write_text(json.dumps(t, indent=2))
    kanban.sync()
    assert json.loads((d / name).read_text())["status"] == "completed"

    kanban.reconcile()
    assert registers.load_item(a).status == "kept"
    kanban.sync()
    assert not (d / name).exists()  # kept commitments leave the board


def test_sync_updates_a_moved_due_date(life, clock):
    a, _, _ = _commitments(clock)
    kanban.sync()
    registers.set_field(a, "due", "2026-10-30")
    assert kanban.sync()["updated"] == 1
    task = _tasks(kanban.task_dir())["2.json"]
    assert task["metadata"]["due"] == "2026-10-30"
    assert task["description"].startswith("Due 2026-10-30")


def test_cli(life, clock, capsys):
    _commitments(clock)
    assert kanban.main(["sync"]) == 0
    assert json.loads(capsys.readouterr().out)["created"] == 2
    assert kanban.main(["reconcile"]) == 0
    assert kanban.main(["nope"]) == 2
