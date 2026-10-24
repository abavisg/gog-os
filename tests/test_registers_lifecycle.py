"""Register item lifecycle: create, move, nudge, change status, history appended."""
from __future__ import annotations

import json

import pytest

from gogos.core import paths, registers


def test_create_commitment_writes_front_matter_and_history(life, clock):
    clock("2026-10-23T08:14:02Z")
    path = registers.create("commitment", "Call the plumber", "home", due="2026-10-24")

    assert path == life / "registers" / "commitment" / "call-the-plumber.md"
    item = registers.load_item(path)
    assert item.meta["type"] == "register"
    assert item.meta["register"] == "commitment"
    assert item.meta["status"] == "open"
    assert item.meta["area"] == "home"
    assert item.meta["created"] == item.meta["updated"] == "2026-10-23"
    assert item.meta["due"] == "2026-10-24"
    assert item.meta["review_by"] == "2026-10-24"
    assert item.meta["goal"] == "none"
    assert item.meta["nudge_count"] == 0
    assert item.history == [("2026-10-23T08:14:02Z", "created")]


def test_slug_collision_gets_suffix(life, clock):
    clock("2026-10-23T08:00:00Z")
    a = registers.create("parked", "Pool cover", "home", revisit_by="2027-03-01")
    b = registers.create("parked", "Pool cover", "home", revisit_by="2027-04-01")
    c = registers.create("parked", "Pool  cover!", "home", revisit_by="2027-05-01")
    assert [a.name, b.name, c.name] == ["pool-cover.md", "pool-cover-2.md", "pool-cover-3.md"]


def test_move_twice_then_keep_gives_four_history_lines(life, clock):
    """Acceptance: four history lines and moved_count == 2 in _index.json."""
    clock("2026-10-23T08:00:00Z")
    path = registers.create("commitment", "Send the form", "family", due="2026-10-24")
    clock("2026-10-23T09:00:00Z")
    registers.set_field(path, "due", "2026-10-27")
    clock("2026-10-23T10:00:00Z")
    registers.set_field(path, "due", "2026-10-29T17:30")
    clock("2026-10-23T11:00:00Z")
    registers.set_status(path, "kept")

    text = path.read_text()
    history = text.split("## History", 1)[1].strip().splitlines()
    assert history == [
        "- 2026-10-23T08:00:00Z created",
        "- 2026-10-23T09:00:00Z due 2026-10-24 → 2026-10-27 (moved)",
        "- 2026-10-23T10:00:00Z due 2026-10-27 → 2026-10-29T17:30 (moved)",
        "- 2026-10-23T11:00:00Z status open → kept",
    ]
    out = json.loads(registers.index().read_text())
    [rec] = [r for r in out["closed"] if r["slug"] == "send-the-form"]
    assert rec["derived"]["moved_count"] == 2
    assert rec["status"] == "kept"


def test_set_status_keeps_body_and_appends_note(life, clock):
    clock("2026-10-23T08:00:00Z")
    path = registers.create("waiting", "Quote from builder", "home",
                            owed_by="Builder", body="Asked for a written quote.")
    before = path.read_text()
    clock("2026-10-25T12:00:00Z", "2026-10-25")
    registers.set_status(path, "received", note="arrived by email")

    after = path.read_text()
    assert "Asked for a written quote." in after
    # History is appended: the old file minus its front matter is a prefix.
    assert after.split("---", 2)[2].startswith(before.split("---", 2)[2].rstrip("\n"))
    assert after.rstrip().endswith(
        "- 2026-10-25T12:00:00Z status open → received (arrived by email)")
    assert registers.load_item(path).meta["updated"] == "2026-10-25"


def test_set_status_same_status_is_a_no_op(life, clock):
    clock("2026-10-23T08:00:00Z")
    path = registers.create("goal", "Read more", "growth")
    before = path.read_text()
    assert registers.set_status(path, "active") is False
    assert path.read_text() == before


def test_set_status_rejects_unknown_status(life, clock):
    clock("2026-10-23T08:00:00Z")
    path = registers.create("commitment", "X", "work", due="2026-10-24")
    with pytest.raises(registers.RegisterError) as exc:
        registers.set_status(path, "done")
    assert "status" in str(exc.value) and str(path) in str(exc.value)


def test_nudge_increments_and_logs(life, clock):
    clock("2026-10-23T08:00:00Z")
    path = registers.create("waiting", "Invoice from Acme", "work", owed_by="Acme")
    clock("2026-10-24T08:00:00Z")
    registers.nudge(path)
    clock("2026-10-25T08:00:00Z")
    registers.nudge(path)
    item = registers.load_item(path)
    assert item.meta["nudge_count"] == 2
    assert item.history[-2:] == [("2026-10-24T08:00:00Z", "nudged (1)"),
                                 ("2026-10-25T08:00:00Z", "nudged (2)")]


def test_nudge_rejects_kinds_without_nudge_count(life, clock):
    clock("2026-10-23T08:00:00Z")
    path = registers.create("goal", "Run", "wellness")
    with pytest.raises(registers.RegisterError, match="nudge_count"):
        registers.nudge(path)


def test_set_field_rejects_managed_fields(life, clock):
    clock("2026-10-23T08:00:00Z")
    path = registers.create("waiting", "Keys", "home", owed_by="Neighbour")
    for field in ("status", "nudge_count", "created", "register"):
        with pytest.raises(registers.RegisterError, match=field):
            registers.set_field(path, field, "x")


def test_set_field_validates_value(life, clock):
    clock("2026-10-23T08:00:00Z")
    path = registers.create("commitment", "X", "work", due="2026-10-24")
    before = path.read_text()
    with pytest.raises(registers.RegisterError, match="due"):
        registers.set_field(path, "due", "Friday")
    assert path.read_text() == before


def test_renewal_review_by_is_expires_minus_lead_days(life, clock):
    clock("2026-10-23T08:00:00Z")
    path = registers.create("renewal", "Home insurance", "home",
                            expires="2027-01-31", provider="Insurer")
    item = registers.load_item(path)
    assert item.meta["lead_days"] == 60
    assert item.meta["review_by"] == "2026-12-02"
    assert item.meta["amount"] == "unknown"
    registers.set_field(path, "lead_days", "30")
    assert registers.load_item(path).meta["review_by"] == "2027-01-01"


def test_commitment_due_move_carries_review_by(life, clock):
    clock("2026-10-23T08:00:00Z")
    path = registers.create("commitment", "X", "work", due="2026-10-24")
    registers.set_field(path, "due", "2026-10-30T09:00")
    assert registers.load_item(path).meta["review_by"] == "2026-10-30"


def test_create_requires_kind_fields(life, clock):
    clock("2026-10-23T08:00:00Z")
    with pytest.raises(registers.RegisterError, match="due"):
        registers.create("commitment", "No date", "work")
    assert list((life / "registers" / "commitment").glob("*.md")) == []


def test_writes_leave_no_temp_files(life, clock):
    clock("2026-10-23T08:00:00Z")
    path = registers.create("commitment", "X", "work", due="2026-10-24")
    registers.set_field(path, "due", "2026-10-25")
    registers.set_status(path, "dropped")
    registers.index()
    leftovers = [p.name for p in life.rglob("*") if p.is_file() and "tmp" in p.name]
    assert leftovers == []


def test_cli_create_status_list(life, clock, capsys):
    clock("2026-10-23T08:00:00Z")
    rc = registers.main(["create", "commitment", "--title", "Book dentist",
                         "--area", "wellness", "--due", "2026-10-28"])
    assert rc == 0
    ref = capsys.readouterr().out.strip().split()[-1]
    assert ref == "life/registers/commitment/book-dentist.md"

    assert registers.main(["status", ref, "kept"]) == 0
    assert registers.load_item(paths.resolve_ref(ref)).meta["status"] == "kept"

    capsys.readouterr()
    assert registers.main(["list", "commitment"]) == 0
    out = capsys.readouterr().out
    assert "book-dentist" in out and "kept" in out


def test_cli_create_error_exits_non_zero(life, clock, capsys):
    clock("2026-10-23T08:00:00Z")
    rc = registers.main(["create", "commitment", "--title", "X", "--area", "work"])
    assert rc == 1
    assert "due" in capsys.readouterr().err


def test_cli_unknown_kind(life, capsys):
    assert registers.main(["list", "chores"]) == 2
    assert "chores" in capsys.readouterr().err
