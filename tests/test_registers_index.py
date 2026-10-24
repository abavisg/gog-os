"""registers.index(): _index.md per kind and registers/_index.json."""
from __future__ import annotations

import json

from gogos.core import frontmatter, registers


def _build(clock):
    clock("2026-10-20T08:00:00Z", "2026-10-20")
    late = registers.create("commitment", "Late one", "home", due="2026-10-21")
    soon = registers.create("commitment", "Soon one", "work", due="2026-10-25")
    later = registers.create("commitment", "Later one", "work", due="2026-11-02")
    done = registers.create("commitment", "Done one", "work", due="2026-10-22")
    registers.set_status(done, "kept")
    registers.create("goal", "Learn Greek", "growth")
    clock("2026-10-23T08:00:00Z", "2026-10-23")
    return late, soon, later, done


def test_index_json_lists_open_items_with_derived_values(life, clock):
    late, soon, later, done = _build(clock)
    out_path = registers.index()
    assert out_path == life / "registers" / "_index.json"
    data = json.loads(out_path.read_text())

    assert data["today"] == "2026-10-23"
    open_refs = [r["ref"] for r in data["open"]]
    assert open_refs[:3] == [
        "life/registers/commitment/late-one.md",
        "life/registers/commitment/soon-one.md",
        "life/registers/commitment/later-one.md",
    ]
    goal = [r for r in data["open"] if r["register"] == "goal"][0]
    assert goal["kind"] == "outcome"
    assert goal["review_by"] == "none" and goal["derived"]["idle"] is True
    assert open_refs[-1] == goal["ref"]  # review_by none sorts last

    rec = data["open"][0]
    assert rec["title"] == "Late one" and rec["area"] == "home"
    assert rec["derived"] == {"moved_count": 0, "days_overdue": 2, "renegotiate": False,
                              "ignored": False, "idle": False, "at_risk": False}
    assert [r["slug"] for r in data["closed"]] == ["done-one"]


def test_index_md_per_kind_open_by_review_by_then_rest(life, clock):
    _build(clock)
    registers.index()
    md = (life / "registers" / "commitment" / "_index.md").read_text()
    meta, body = frontmatter.split(md)
    assert meta["type"] == "register" and meta["register"] == "commitment"
    assert meta["updated"] == "2026-10-23"

    open_part, rest = body.split("## Other", 1)
    rows = [line for line in open_part.splitlines() if line.startswith("| 2026")]
    assert [r.split("|")[2].strip() for r in rows] == [
        "[Late one](late-one.md)", "[Soon one](soon-one.md)", "[Later one](later-one.md)"]
    assert "overdue 2d" in rows[0] and "overdue" not in rows[1]
    assert "[Done one](done-one.md)" in rest and "kept" in rest


def test_every_kind_gets_an_index_even_when_empty(life, clock):
    clock("2026-10-23T08:00:00Z")
    registers.index()
    for kind in registers.KINDS:
        md = (life / "registers" / kind / "_index.md").read_text()
        assert "No open items." in md


def test_index_files_are_not_loaded_as_items(life, clock):
    _build(clock)
    registers.index()
    registers.index()  # second pass must not trip over its own _index.md
    assert all(i.path.name != "_index.md" for i in registers.load())


def test_cli_index_prints_path(life, clock, capsys):
    clock("2026-10-23T08:00:00Z")
    assert registers.main(["index"]) == 0
    assert capsys.readouterr().out.strip().endswith("life/registers/_index.json")
